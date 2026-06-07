"""Run the cosmetic vision pilot experiment.

The pilot exercises two prompt stages that share an identical 9-principle clinical
schema (bone → soft tissue → skin), with recommendation injection as the only
inter-stage variable:

1. V2 (domain-aware) — independent extraction over the shared schema
2. V3 (recommendation-conditioned re-examination) — same schema, but sees V2's
   output and the agent's draft recommendation; refines V2 and audits the plan

V1 (naive baseline) is archived and only runs with --include-v1.

It intentionally stays outside the production chat agent/RAG pipeline so the
experiment can be repeated and scored without changing user-facing behavior.

Usage:
    cd Q:/Cosmetic/backend
    python -m scripts.vision_pilot --dry-run --limit 1
    python -m scripts.vision_pilot
    python -m scripts.vision_pilot summarize
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
PILOT_DIR = ROOT / "docs" / "vision_pilot"
PROMPTS_DIR = PILOT_DIR / "prompts"
DATA_DIR = PILOT_DIR / "data"
RUNS_DIR = PILOT_DIR / "runs"
REPORT_PATH = PILOT_DIR / "report.md"
SUMMARY_PATH = PILOT_DIR / "summary.json"

DEFAULT_MODELS = ("qwen3-vl-flash",)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Design-doc prices converted to CNY per 1M tokens.
PRICE_CNY_PER_1M = {
    "qwen3-vl-flash": {"input": 0.36, "output": 2.88},
    "qwen-vl-max": {"input": 11.5, "output": 46.0},
    "qwen3-vl-plus": {"input": 11.5, "output": 46.0},
}

RECOMMENDATION_RULES = [
    # Layer 1: 骨骼骨性层
    (re.compile(r"额结节|额头|颞部|眉弓|上庭"), "围绕上庭骨性凹陷进行面诊复核，谨慎评估是否需要骨膜层支撑填充方案"),
    (re.compile(r"眶骨|颧弓|颧骨|上颌骨|鼻基底|鼻梁|中庭"), "围绕中庭骨性支撑不足进行面诊复核，谨慎评估是否需要骨膜层支撑填充方案"),
    (re.compile(r"凸嘴|下颌骨|下巴|颏部|下庭"), "围绕下庭骨性结构进行面诊复核，谨慎评估是否需要骨性轮廓相关方案"),
    # Layer 2: 软组织层
    (re.compile(r"太阳穴|上睑|苹果肌|唇|人中|容量缺失|容积"), "围绕软组织容量缺失进行面诊复核，谨慎评估是否需要低剂量填充方案"),
    (re.compile(r"泪沟|眶下"), "围绕泪沟明显进行面诊复核，谨慎评估是否需要眶下区域改善方案"),
    (re.compile(r"法令纹|印第安纹|口角囊袋|下颌缘|双下巴|松弛|下垂|下移"), "围绕软组织松弛下移进行面诊复核，谨慎评估是否需要光电或埋线复位方案"),
    (re.compile(r"咬肌|肥厚|脂肪堆积"), "围绕局部肥厚进行面诊复核，谨慎评估是否需要瘦脸针或溶脂方案"),
    # Layer 3: 皮肤表层
    (re.compile(r"色斑|痘印|毛孔|暗沉|肤色不均|粗糙|肤质"), "围绕皮肤质地和色素问题进行面诊复核，谨慎评估是否需要光电或皮肤管理方案"),
    (re.compile(r"静态纹|皱纹"), "围绕静态纹进行面诊复核，谨慎评估是否需要填充与紧致联合方案"),
    (re.compile(r"颈纹|颈部"), "围绕颈纹/颈部松弛进行面诊复核，谨慎评估是否需要颈部年轻化方案"),
    (re.compile(r"眼角|眼袋|黑眼圈"), "围绕眼周问题进行面诊复核，谨慎评估是否需要眼周年轻化方案"),
]


@dataclass
class CallResult:
    text: str
    latency_sec: float
    usage: dict[str, Any]
    estimated_cost_cny: float | None


@dataclass
class RunScore:
    file: Path
    model: str
    v1_accuracy: float | None
    v2_accuracy: float | None
    v3_accuracy: float | None
    v3_incremental: float | None
    v3_new_hallucination: bool | None
    latencies: list[float]
    costs: list[float]


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def list_images(data_dir: Path) -> list[Path]:
    return sorted(
        path for path in data_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )


def estimate_cost_cny(model: str, usage: dict[str, Any]) -> float | None:
    prices = PRICE_CNY_PER_1M.get(model)
    if not prices:
        return None

    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    return (
        input_tokens * prices["input"] / 1_000_000
        + output_tokens * prices["output"] / 1_000_000
    )


def usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return dict(usage)
    if hasattr(usage, "items"):
        return dict(usage.items())
    if hasattr(usage, "__dict__"):
        return dict(usage.__dict__)
    return {"raw": str(usage)}


def extract_response_text(response: Any) -> str:
    try:
        content = response.output.choices[0].message.content
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Unexpected DashScope response shape: {response}") from exc

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                chunks.append(str(item["text"]))
        if chunks:
            return "\n".join(chunks).strip()
    return str(content).strip()


def api_key() -> str:
    load_dotenv(ENV_FILE)
    return os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("LLM_API_KEY") or ""


def call_qwen_vl(
    image_path: Path,
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int | None,
    dry_run: bool,
) -> CallResult:
    if dry_run:
        start = time.time()
        time.sleep(0.05)
        text = (
            f"[DRY RUN] model={model}; image={image_path.name}\n"
            "This placeholder verifies the local experiment pipeline only."
        )
        return CallResult(
            text=text,
            latency_sec=time.time() - start,
            usage={"input_tokens": 0, "output_tokens": 0},
            estimated_cost_cny=0.0,
        )

    key = api_key()
    if not key:
        raise RuntimeError("Set DASHSCOPE_API_KEY or LLM_API_KEY before running real VLM calls.")

    try:
        import dashscope
        from dashscope import MultiModalConversation
    except ImportError as exc:
        raise RuntimeError("dashscope is not installed. Run: python -m pip install dashscope") from exc

    dashscope.api_key = key
    import base64
    suffix = image_path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    image_payload = f"data:image/{mime};base64,{encoded}"
    messages = [{
        "role": "user",
        "content": [
            {"image": image_payload},
            {"text": prompt},
        ],
    }]
    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        call_kwargs["max_tokens"] = max_tokens

    start = time.time()
    response = MultiModalConversation.call(**call_kwargs)
    latency = time.time() - start

    if getattr(response, "status_code", 200) != 200:
        raise RuntimeError(f"DashScope call failed: {response}")

    usage = usage_to_dict(getattr(response, "usage", None))
    return CallResult(
        text=extract_response_text(response),
        latency_sec=latency,
        usage=usage,
        estimated_cost_cny=estimate_cost_cny(model, usage),
    )


TOP_LAYER_RE = re.compile(r"top_layer\s*[:：]\s*([A-Za-z_]+)")
TOP_FEATURE_RE = re.compile(r"top_feature\s*[:：]\s*(.+)")
TRIGGERED_PRINCIPLES_RE = re.compile(r"triggered_principles\s*[:：]\s*(.+)")

HEALTHY_LAYER_VALUES = {"none", "n/a", "无", "正常", ""}


def choose_top_feature(v2_output: str) -> tuple[str | None, list[str]]:
    """Parse V2 Summary block (top_layer / top_feature / triggered_principles).

    Returns (feature_or_None, audit_log). feature is the V2-declared `top_feature`
    string verbatim; None means V2 declared a healthy face (top_layer=none) or the
    Summary block was missing/malformed. audit_log records what we extracted so the
    run markdown can show why a given feature was (or wasn't) selected.

    Trusts V2's structured output rather than re-deriving sentiment in Python.
    """
    audit: list[str] = []

    top_layer_match = TOP_LAYER_RE.search(v2_output)
    top_feature_match = TOP_FEATURE_RE.search(v2_output)
    triggered_match = TRIGGERED_PRINCIPLES_RE.search(v2_output)

    if not top_layer_match:
        audit.append("[MALFORMED] no `top_layer:` field found in V2 output")
        return None, audit

    top_layer = top_layer_match.group(1).strip().lower()
    audit.append(f"[FIELD] top_layer = {top_layer}")

    if top_layer in HEALTHY_LAYER_VALUES:
        audit.append("[HEALTHY] V2 declared no problem layer; V3 will be skipped")
        return None, audit

    if not top_feature_match:
        audit.append("[MALFORMED] top_layer indicates a problem but `top_feature:` field missing")
        return None, audit

    top_feature = top_feature_match.group(1).strip().strip('"').strip("`").rstrip(".")
    audit.append(f"[FIELD] top_feature = {top_feature}")

    if triggered_match:
        triggered = triggered_match.group(1).strip()
        audit.append(f"[FIELD] triggered_principles = {triggered}")

    if not top_feature or top_feature.lower() in HEALTHY_LAYER_VALUES:
        audit.append("[HEALTHY] top_feature is empty/none despite top_layer set; treating as healthy")
        return None, audit

    return top_feature, audit


def recommendation_for(feature: str) -> str:
    for pattern, recommendation in RECOMMENDATION_RULES:
        if pattern.search(feature):
            return recommendation
    return "围绕该特征进行面诊复核，谨慎评估是否需要个性化医美改善方案"


def md_code(text: str) -> str:
    return "```text\n" + text.strip() + "\n```"


def format_cost(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def write_run_markdown(
    image_path: Path,
    model: str,
    v1: CallResult,
    v2: CallResult,
    v3: CallResult,
    top_feature: str,
    recommendation: str,
    sentiment_audit: list[str] | None = None,
) -> Path:
    output_path = RUNS_DIR / f"{image_path.stem}__{model}.md"
    generated_at = datetime.now().isoformat(timespec="seconds")
    payload = {
        "image": image_path.name,
        "model": model,
        "generated_at": generated_at,
        "top_feature": top_feature,
        "recommendation": recommendation,
        "sentiment_audit": sentiment_audit or [],
        "metrics": {
            "v1": {"latency_sec": v1.latency_sec, "usage": v1.usage, "estimated_cost_cny": v1.estimated_cost_cny},
            "v2": {"latency_sec": v2.latency_sec, "usage": v2.usage, "estimated_cost_cny": v2.estimated_cost_cny},
            "v3": {"latency_sec": v3.latency_sec, "usage": v3.usage, "estimated_cost_cny": v3.estimated_cost_cny},
        },
    }

    audit_block = (
        "\n".join(f"- {line}" for line in sentiment_audit)
        if sentiment_audit
        else "- (V2 Summary block not parsed)"
    )

    content = f"""# Vision Pilot Run: {image_path.name} / {model}

- Generated at: {generated_at}
- Image: `{image_path.resolve()}`
- Model: `{model}`
- V3 top feature: {top_feature}
- V3 simulated recommendation: {recommendation}

## V2 Summary Parse Audit

{audit_block}

## V1 Output

{md_code(v1.text)}

## V2 Output

{md_code(v2.text)}

## V3 Output

{md_code(v3.text)}

## Evaluation Table

| 维度 | V1 | V2 | V3 |
|---|---:|---:|---:|
| 使用医学术语 (Y/N) |  |  |  |
| 事实准确性 (1-5) |  |  |  |
| Hallucination 数量 (条) |  |  |  |
| V3 提供 V2 没有的新信息 (1-5) | - | - |  |
| V3 是否引入新幻觉 (Y/N) | - | - |  |
| Latency (秒) | {v1.latency_sec:.2f} | {v2.latency_sec:.2f} | {v3.latency_sec:.2f} |
| 输入 tokens | {v1.usage.get('input_tokens', '')} | {v2.usage.get('input_tokens', '')} | {v3.usage.get('input_tokens', '')} |
| 输出 tokens | {v1.usage.get('output_tokens', '')} | {v2.usage.get('output_tokens', '')} | {v3.usage.get('output_tokens', '')} |
| 估算成本 (CNY) | {format_cost(v1.estimated_cost_cny)} | {format_cost(v2.estimated_cost_cny)} | {format_cost(v3.estimated_cost_cny)} |

## Qualitative Notes

-

## Raw Metadata

```json
{json.dumps(payload, ensure_ascii=False, indent=2)}
```
"""
    output_path.write_text(content, encoding="utf-8")
    return output_path


def write_run_summary(run_files: list[Path]) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_files": [str(path.relative_to(PILOT_DIR)) for path in run_files],
    }
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    run_list = "\n".join(f"- [{path.name}](runs/{path.name})" for path in run_files)
    REPORT_PATH.write_text(
        f"""# Vision Pilot Report

- Generated at: {payload['generated_at']}
- Status: pending manual evaluation

## Quantitative Summary

Fill this table after scoring each run file.

| Model | V1 factual accuracy | V2 factual accuracy | V3 incremental info | V3 hallucination increased? | Avg latency/query | Est. total cost CNY |
|---|---:|---:|---:|---|---:|---:|
| qwen3-vl-flash |  |  |  |  |  |  |

## Qualitative Findings

1. Gold case:
2. Failure case:
3. Cost/latency observation:

## Decision

Decision: GO / PIVOT / KILL

Reason:

## Next Steps

- 

## Run Files

{run_list if run_list else '- No run files generated yet.'}
""",
        encoding="utf-8",
    )


def parse_number(value: str) -> float | None:
    value = value.strip()
    if not value or value == "-":
        return None
    match = re.search(r"\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"y", "yes", "是", "true"}:
        return True
    if normalized in {"n", "no", "否", "false"}:
        return False
    return None


def parse_table_row(text: str, label: str) -> list[str] | None:
    pattern = re.compile(rf"^\|\s*{re.escape(label)}\s*\|(.+)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    return [cell.strip() for cell in match.group(1).strip().strip("|").split("|")]


def parse_model(text: str, fallback: str) -> str:
    match = re.search(r"^- Model: `([^`]+)`", text, re.MULTILINE)
    return match.group(1) if match else fallback


def parse_run_score(path: Path) -> RunScore:
    text = path.read_text(encoding="utf-8")
    model = parse_model(text, path.stem.split("__")[-1])
    accuracy = parse_table_row(text, "事实准确性 (1-5)") or ["", "", ""]
    incremental = parse_table_row(text, "V3 提供 V2 没有的新信息 (1-5)") or ["", "", ""]
    hallucination = parse_table_row(text, "V3 是否引入新幻觉 (Y/N)") or ["", "", ""]
    latency = parse_table_row(text, "Latency (秒)") or []
    cost = parse_table_row(text, "估算成本 (CNY)") or []

    return RunScore(
        file=path,
        model=model,
        v1_accuracy=parse_number(accuracy[0]) if len(accuracy) > 0 else None,
        v2_accuracy=parse_number(accuracy[1]) if len(accuracy) > 1 else None,
        v3_accuracy=parse_number(accuracy[2]) if len(accuracy) > 2 else None,
        v3_incremental=parse_number(incremental[2]) if len(incremental) > 2 else None,
        v3_new_hallucination=parse_bool(hallucination[2]) if len(hallucination) > 2 else None,
        latencies=[value for value in (parse_number(cell) for cell in latency) if value is not None],
        costs=[value for value in (parse_number(cell) for cell in cost) if value is not None],
    )


def avg(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return sum(numeric) / len(numeric) if numeric else None


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def suggested_decision(v2_accuracy: float | None, v3_incremental: float | None, hallucination_increased: bool | None) -> str:
    if v2_accuracy is None or v3_incremental is None or hallucination_increased is None:
        return "PENDING"
    if v2_accuracy >= 4.0 and v3_incremental >= 3.5 and not hallucination_increased:
        return "GO"
    if v2_accuracy < 3.0 or hallucination_increased:
        return "KILL"
    return "PIVOT"


def command_run(args: argparse.Namespace) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    images = list_images(args.data_dir)
    if args.limit is not None:
        images = images[: args.limit]
    if not images:
        raise SystemExit(f"No images found in {args.data_dir}. Add .jpg/.png/.webp files first.")

    max_tokens = args.max_tokens if args.max_tokens > 0 else None
    v1_prompt = load_prompt("v1_naive.txt") if args.include_v1 else None
    v2_prompt = load_prompt("v2_domain_aware.txt")
    v3_template = load_prompt("v3_re_examination.txt")

    run_files: list[Path] = []
    skipped: list[tuple[str, str]] = []
    for image_path in images:
        for model in args.models:
            print(f"Running {image_path.name} with {model}...")
            if args.include_v1:
                v1 = call_qwen_vl(image_path, v1_prompt, model, args.temperature, max_tokens, args.dry_run)
            else:
                v1 = CallResult(text="[SKIPPED] V1 disabled (use --include-v1 to enable archived naive baseline)", latency_sec=0.0, usage={}, estimated_cost_cny=0.0)
            v2 = call_qwen_vl(image_path, v2_prompt, model, args.temperature, max_tokens, args.dry_run)
            top_feature, sentiment_audit = choose_top_feature(v2.text)
            if top_feature is None:
                msg = "V2 Summary 显示 top_layer=none 或字段缺失，跳过 V3 以避免 confirmation-bias 幻觉"
                print(f"  [SKIP V3] {image_path.name} / {model}: {msg}")
                skipped.append((f"{image_path.name} / {model}", msg))
                v3 = CallResult(text=f"[SKIPPED] {msg}", latency_sec=0.0, usage={}, estimated_cost_cny=0.0)
                recommendation = "(skipped: V2 declared healthy face / top_layer=none)"
            else:
                recommendation = recommendation_for(top_feature)
                v3_prompt = v3_template.format(v2_output=v2.text, recommendation=recommendation)
                v3 = call_qwen_vl(image_path, v3_prompt, model, args.temperature, max_tokens, args.dry_run)
            run_files.append(
                write_run_markdown(image_path, model, v1, v2, v3, top_feature or "(none)", recommendation, sentiment_audit)
            )

    write_run_summary(run_files)
    print(f"Wrote {len(run_files)} run file(s) under {RUNS_DIR}.")
    if skipped:
        print(f"V3 skipped for {len(skipped)} run(s):")
        for label, reason in skipped:
            print(f"  - {label}: {reason}")
    print(f"Report: {REPORT_PATH}")


def command_summarize() -> None:
    runs = [parse_run_score(path) for path in sorted(RUNS_DIR.glob("*.md"))]
    by_model: dict[str, list[RunScore]] = {}
    for run in runs:
        by_model.setdefault(run.model, []).append(run)

    rows = []
    model_decisions = []
    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "models": {},
    }
    for model, scores in sorted(by_model.items()):
        v1_acc = avg([score.v1_accuracy for score in scores])
        v2_acc = avg([score.v2_accuracy for score in scores])
        v3_inc = avg([score.v3_incremental for score in scores])
        hallucination_values = [score.v3_new_hallucination for score in scores if score.v3_new_hallucination is not None]
        hallucination_increased = any(hallucination_values) if hallucination_values else None
        avg_latency = avg([latency for score in scores for latency in score.latencies])
        total_cost = sum(cost for score in scores for cost in score.costs)
        decision = suggested_decision(v2_acc, v3_inc, hallucination_increased)
        model_decisions.append(decision)
        rows.append(
            f"| {model} | {fmt(v1_acc)} | {fmt(v2_acc)} | {fmt(v3_inc)} | "
            f"{'' if hallucination_increased is None else hallucination_increased} | "
            f"{fmt(avg_latency)} | {total_cost:.6f} | {decision} |"
        )
        summary["models"][model] = {
            "run_count": len(scores),
            "v1_factual_accuracy_avg": v1_acc,
            "v2_factual_accuracy_avg": v2_acc,
            "v3_incremental_info_avg": v3_inc,
            "v3_hallucination_increased": hallucination_increased,
            "avg_latency_sec": avg_latency,
            "estimated_total_cost_cny": total_cost,
            "suggested_decision": decision,
        }

    overall = "PENDING"
    if "GO" in model_decisions:
        overall = "GO"
    elif "PIVOT" in model_decisions:
        overall = "PIVOT"
    elif model_decisions and all(item == "KILL" for item in model_decisions):
        overall = "KILL"
    summary["suggested_overall_decision"] = overall
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    run_links = "\n".join(f"- [{run.file.name}](runs/{run.file.name})" for run in runs)
    REPORT_PATH.write_text(
        f"""# Vision Pilot Report

- Generated at: {summary['generated_at']}
- Status: summarized from manually filled run tables

## Quantitative Summary

| Model | V1 factual accuracy | V2 factual accuracy | V3 incremental info | V3 hallucination increased? | Avg latency/query | Est. total cost CNY | Suggested decision |
|---|---:|---:|---:|---|---:|---:|---|
{chr(10).join(rows) if rows else '| - |  |  |  |  |  |  | PENDING |'}

## Qualitative Findings

1. Gold case:
2. Failure case:
3. Cost/latency observation:

## Decision

Decision: {overall}

Reason: Fill this in after reviewing qualitative notes. Treat the script suggestion as a consistency check, not the final research judgment.

## Next Steps

- 

## Run Files

{run_links if run_links else '- No run files generated yet.'}
""",
        encoding="utf-8",
    )
    print(f"Wrote {REPORT_PATH}")
    print(f"Suggested overall decision: {overall}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or summarize the Cosmetic vision pilot.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run VLM calls and write run files")
    add_run_args(run_parser)

    subparsers.add_parser("summarize", help="Summarize manually scored run files")

    add_run_args(parser)
    return parser


def add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of images to process")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=700, help="Limit output tokens per call; use 0 for provider default")
    parser.add_argument("--dry-run", action="store_true", help="Generate placeholder outputs without API calls")
    parser.add_argument(
        "--include-v1",
        action="store_true",
        help="Also run V1 naive prompt (archived; default pipeline is V2+V3 only)",
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "summarize":
        command_summarize()
    else:
        command_run(args)


if __name__ == "__main__":
    main()
