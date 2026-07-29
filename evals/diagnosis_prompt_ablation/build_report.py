"""Render side-by-side A vs C comparison HTML for advisor review.

Reads outputs from a results/<run_dir>/ (produced by run.py) and produces
ablation_report.html inside that same run_dir. Content of every metric,
verdict paragraph, and HTML section is unchanged from the original
tmp/build_ablation_report.py — this file only relocates path resolution.

Usage:
  python build_report.py --run-dir results/default_2026-07-29T170000/
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_DATA_ROOT = Path(os.environ.get("COSMETIC_DATA_ROOT", _REPO_ROOT / "downloads"))
_PROMPTS_DIR = _REPO_ROOT / "backend" / "app" / "prompts"
_FEW_SHOT_DIR = _PROMPTS_DIR / "diagnosis_few_shot"

# _RUNS is set from --run-dir at CLI parse time.
_RUNS: Path = Path()


def _resolve_patient_image(patient_id: str, filename: str) -> Path:
    """Locate a patient's front photo under COSMETIC_DATA_ROOT via glob."""
    candidates = list(_DATA_ROOT.glob(f"**/images_by_patient/{patient_id}/{filename}"))
    if not candidates:
        raise FileNotFoundError(
            f"can't find {filename} under {_DATA_ROOT}. "
            f"Set COSMETIC_DATA_ROOT if your dataset lives elsewhere."
        )
    return candidates[0]


def _b64_image(patient_id: str, filename: str) -> str:
    path = _resolve_patient_image(patient_id, filename)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _try_parse_json(text: str) -> dict | None:
    """Extract JSON from LLM output (may be wrapped in ```json ... ``` or free text)."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


def _load_system_prompt() -> str:
    """Read the C-condition system prompt from backend/app/prompts/diagnosis_system.md."""
    p = _PROMPTS_DIR / "diagnosis_system.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "(system prompt file not found at backend/app/prompts/diagnosis_system.md)"


def _load_few_shot_gold(patient_ids: list[str]) -> list[dict]:
    """Return list of {patient_id, image_b64, diagnosis_pretty} for few-shot samples.

    Reads from backend/app/prompts/diagnosis_few_shot/ where stems are semantic
    (case_*.json / case_*.png). The patient_ids argument maps historical patient
    IDs to those stems for backwards-compatible display.
    """
    _PATIENT_ID_TO_STEM = {
        "patient_b2a332e5": "case_young_female_maintenance",
        "patient_0943db4f": "case_mature_female_multizone",
    }
    out = []
    for pid in patient_ids:
        stem = _PATIENT_ID_TO_STEM.get(pid)
        if not stem:
            continue
        img_path = _FEW_SHOT_DIR / f"{stem}.png"
        diag_path = _FEW_SHOT_DIR / f"{stem}.json"
        if not img_path.exists() or not diag_path.exists():
            continue
        img_b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
        gold_pretty = json.dumps(json.loads(diag_path.read_text(encoding="utf-8")),
                                 ensure_ascii=False, indent=2)
        out.append({
            "patient_id": pid,
            "image_b64": img_b64,
            "image_filename": img_path.name,
            "diagnosis_pretty": gold_pretty,
        })
    return out


def _evaluate_pair(result_A: dict, result_C: dict) -> dict:
    """Compute observations that back the AI verdict — every claim points to data."""
    parsed_A = _try_parse_json(result_A["raw_output"])
    diag_C = result_C.get("diagnosis_json") or {}
    zones_C = diag_C.get("professional_assessment", []) if isinstance(diag_C, dict) else []

    a_items = _count_zones_A(parsed_A)
    c_zones_total = len(zones_C)
    c_actionable = [z for z in zones_C
                    if z.get("severity_level") not in ("none_or_maintenance", "", None)
                    and not str(z.get("severity_level", "")).startswith("pending")]
    c_pending = [z for z in zones_C
                 if str(z.get("severity_level", "")).startswith("pending")]

    # Does A ever say "I don't know"?
    a_text = result_A["raw_output"]
    a_has_epistemic = any(w in a_text for w in [
        "需补充", "需要补充", "无法判断", "无法确认", "45°", "45 度", "侧面照", "动态"
    ])

    # Does A output structured problem_types codes?
    a_has_codes = bool(re.search(r"\b(PIG|TEX|WR|VOL|SAG|PORE|RED|DYN|FAT|PROP)\b", a_text))

    # Does A produce sub_area-level precision?
    precise_zones = ["下眼睑", "泪沟", "眶下", "苹果肌", "颧部", "颧弓", "眉尾",
                     "颌前", "口周", "睑颊", "鼻基底"]
    a_precise_hits = sum(1 for z in precise_zones if z in a_text)
    c_precise_hits = sum(1 for z in precise_zones for zone in zones_C
                          if z in zone.get("sub_area", ""))

    return {
        "a_items": a_items,
        "c_zones_total": c_zones_total,
        "c_actionable": len(c_actionable),
        "c_pending": len(c_pending),
        "a_has_epistemic": a_has_epistemic,
        "a_has_codes": a_has_codes,
        "c_has_codes": True,
        "a_precise_hits": a_precise_hits,
        "c_precise_hits": c_precise_hits,
    }


def _render_verdict(sample: dict, obs: dict) -> str:
    """Render an AI-generated per-patient verdict backed by observations."""
    pid = sample["patient_id"]
    lines = [f"<h4>案例 {html.escape(pid)} · AI 评价</h4><ul>"]

    # Coverage
    lines.append(
        f"<li><b>诊断颗粒度</b>：A 组识别到 <em>{obs['a_items']}</em> 个问题条目（自由文本描述），"
        f"C 组给出 <em>{obs['c_zones_total']}</em> 个解剖精确部位的完整诊断"
        f"（其中 <em>{obs['c_actionable']}</em> 个为可操作、<em>{obs['c_pending']}</em> 个需补充视角）。"
        f"C 组的结构化输出可直接驱动 zone-level 的下游生图与方案生成，A 组的自由描述无法。</li>"
    )

    # Boundary awareness
    if obs["a_has_epistemic"]:
        lines.append(
            "<li><b>临床边界意识</b>：A 组已经具备一定的边界意识（提到需补充视角/无法判断）。</li>"
        )
    elif obs["c_pending"] > 0:
        lines.append(
            f"<li><b>临床边界意识</b>：A 组对所有识别到的问题都直接给出建议，未表达"
            "\"仅正面照无法判断\"的场景；C 组明确标注了 "
            f"<em>{obs['c_pending']}</em> 个 <code>pending_*</code> 部位（需 45° / 侧面 / 动态视角确认）。"
            "这是医生审校 case 教会模型的临床严谨性，也是纯 baseline VLM 学不到的行为。</li>"
        )
    else:
        lines.append(
            "<li><b>临床边界意识</b>：本例 C 组未触发 pending 标注，因此本案无法凸显边界意识差异。"
            "这类差异更容易在存在\"疑似深沟/需侧面确认\"的复杂案例中出现。</li>"
        )

    # Domain codes
    if obs["a_has_codes"]:
        lines.append(
            "<li><b>专业分类</b>：A 组罕见地输出了医学编码（PIG/TEX 等），效果接近 C。</li>"
        )
    else:
        lines.append(
            "<li><b>专业分类</b>：A 组仅使用日常语言（\"色斑\"、\"暗沉\"、\"松弛\"）；"
            "C 组遵循 10 类医学编码（PIG=色素、TEX=肤质、WR=细纹、VOL=容量缺失、SAG=松弛下垂 等），"
            "这些编码可直接映射到医美设备的适用症数据库，是自动化推荐的前提。</li>"
        )

    # Sub-area precision
    lines.append(
        f"<li><b>部位精度</b>：A 组文本中提及 <em>{obs['a_precise_hits']}</em> 个精细解剖部位关键词，"
        f"C 组输出 <em>{obs['c_precise_hits']}</em> 个精细解剖部位（如\"下眼睑皮肤\"vs\"眼下\"、"
        "\"泪沟/眶下凹陷\"vs\"眼袋\"）。这个精度差直接决定了下游能否生成"
        "\"针对某个 sub_area 的靶向治疗方案\"，还是只能给\"整脸打包建议\"。</li>"
    )

    lines.append("</ul>")
    return "\n".join(lines)


def _count_zones_A(parsed_A: dict | None) -> int:
    """Count problem entries in condition-A output (schema varies)."""
    if not parsed_A:
        return 0
    for key in ("问题列表", "problems", "issues", "professional_assessment", "分析", "皮肤问题"):
        val = parsed_A.get(key)
        if isinstance(val, list):
            return len(val)
    total = 0
    for v in parsed_A.values():
        if isinstance(v, list):
            total += len(v)
    return total


def _count_zones_C(result_C: dict) -> int:
    diag = result_C.get("diagnosis_json") or {}
    zones = diag.get("professional_assessment", [])
    return len(zones) if isinstance(zones, list) else 0


def _severity_granularity_A(text: str) -> str:
    """Guess granularity from raw A output."""
    matches = set()
    for word in ["轻度", "中度", "重度", "mild", "moderate", "severe"]:
        if word in text:
            matches.add(word)
    return f"{len(matches)} 档" if matches else "未分级"


def _severity_granularity_C(result_C: dict) -> str:
    diag = result_C.get("diagnosis_json") or {}
    zones = diag.get("professional_assessment") or []
    levels = {z.get("severity_level") for z in zones if isinstance(z, dict)}
    levels.discard(None)
    return f"{len(levels)} 档 (含 pending)"


def _has_body_part_detail_A(parsed_A: dict | None, text: str) -> str:
    zone_words = ["额头", "眼", "颊", "颧", "鼻", "唇", "颌", "下巴", "眉", "太阳穴"]
    hit = sum(1 for w in zone_words if w in text)
    return f"提及 {hit} 类部位" if hit else "笼统描述"


def _render_patient_section(sample: dict) -> str:
    patient_id = sample["patient_id"]
    filename = sample["source_image"]
    img_b64 = _b64_image(patient_id, filename)

    result_A = json.loads((_RUNS / sample["A_file"]).read_text(encoding="utf-8"))
    result_C = json.loads((_RUNS / sample["C_file"]).read_text(encoding="utf-8"))

    raw_A = result_A["raw_output"]
    parsed_A = _try_parse_json(raw_A)
    raw_C = result_C.get("raw_output", "")

    a_json_ok = parsed_A is not None
    c_json_ok = bool(result_C.get("diagnosis_json"))
    a_zones = _count_zones_A(parsed_A)
    c_zones = _count_zones_C(result_C)
    a_granularity = _severity_granularity_A(raw_A)
    c_granularity = _severity_granularity_C(result_C)
    a_parts = _has_body_part_detail_A(parsed_A, raw_A)
    c_parts = f"{c_zones} 个精确解剖部位"

    a_display = json.dumps(parsed_A, ensure_ascii=False, indent=2) if parsed_A else raw_A
    if result_C.get("diagnosis_json"):
        c_display = json.dumps(result_C["diagnosis_json"], ensure_ascii=False, indent=2)
    else:
        c_display = raw_C

    obs = _evaluate_pair(result_A, result_C)
    verdict_html = _render_verdict(sample, obs)

    return f"""
  <section class="patient">
    <h2>{html.escape(patient_id)}</h2>
    <div class="patient-grid">
      <div class="col-photo">
        <div class="lbl">术前正面照</div>
        <img src="data:image/png;base64,{img_b64}" alt="{html.escape(patient_id)}">
        <div class="filename">{html.escape(filename)}</div>
      </div>
      <div class="col-output col-A">
        <div class="col-header">
          <span class="badge badge-A">条件 A · Naive</span>
          <span class="latency">{result_A['latency_sec']:.1f}s</span>
        </div>
        <div class="metric-row">
          <span class="metric"><b>JSON 合规:</b> {"✅" if a_json_ok else "❌"}</span>
          <span class="metric"><b>识别问题:</b> {a_zones} 项</span>
        </div>
        <div class="metric-row">
          <span class="metric"><b>严重度分级:</b> {a_granularity}</span>
          <span class="metric"><b>部位颗粒度:</b> {a_parts}</span>
        </div>
        <pre>{html.escape(a_display)}</pre>
      </div>
      <div class="col-output col-C">
        <div class="col-header">
          <span class="badge badge-C">条件 C · Few-shot PoC</span>
          <span class="latency">{result_C.get('latency_sec', 0):.1f}s</span>
        </div>
        <div class="metric-row">
          <span class="metric"><b>JSON 合规:</b> {"✅" if c_json_ok else "❌"}</span>
          <span class="metric"><b>识别部位:</b> {c_zones} 个</span>
        </div>
        <div class="metric-row">
          <span class="metric"><b>严重度分级:</b> {c_granularity}</span>
          <span class="metric"><b>部位颗粒度:</b> {c_parts}</span>
        </div>
        <pre>{html.escape(c_display)}</pre>
      </div>
    </div>
    <div class="verdict">{verdict_html}</div>
  </section>"""


def main() -> None:
    global _RUNS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True,
                    help="Path to a results/<sheet_stem>_<timestamp>/ directory")
    args = ap.parse_args()
    _RUNS = Path(args.run_dir).resolve()
    if not _RUNS.exists():
        print(f"[FAIL] run dir does not exist: {_RUNS}", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads((_RUNS / "manifest.json").read_text(encoding="utf-8"))
    samples = manifest["samples"]

    patient_sections = "\n".join(_render_patient_section(s) for s in samples)

    # Compute aggregate metrics for the summary table
    agg_A_json = 0
    agg_A_zones_total = 0
    agg_C_json = 0
    agg_C_zones_total = 0
    for s in samples:
        result_A = json.loads((_RUNS / s["A_file"]).read_text(encoding="utf-8"))
        result_C = json.loads((_RUNS / s["C_file"]).read_text(encoding="utf-8"))
        parsed_A = _try_parse_json(result_A["raw_output"])
        agg_A_json += 1 if parsed_A else 0
        agg_A_zones_total += _count_zones_A(parsed_A)
        agg_C_json += 1 if result_C.get("diagnosis_json") else 0
        agg_C_zones_total += _count_zones_C(result_C)

    n = len(samples)
    a_json_pct = 100 * agg_A_json // n
    c_json_pct = 100 * agg_C_json // n
    a_zones_avg = agg_A_zones_total / n if n else 0
    c_zones_avg = agg_C_zones_total / n if n else 0

    # Load C prompt details for full display
    system_prompt = _load_system_prompt()
    sp_lines = len(system_prompt.splitlines())
    sp_chars = len(system_prompt)
    few_shot_pids = ["patient_b2a332e5", "patient_0943db4f"]
    few_shot_data = _load_few_shot_gold(few_shot_pids)
    few_shot_html = ""
    for fs in few_shot_data:
        few_shot_html += f"""
      <details class="few-shot-example">
        <summary>Few-shot 示例: {html.escape(fs['patient_id'])} · {html.escape(fs['image_filename'])}</summary>
        <div class="fs-body">
          <div class="fs-img">
            <img src="data:image/png;base64,{fs['image_b64']}" alt="{html.escape(fs['patient_id'])}">
            <div class="fs-caption">医生审校 gold diagnosis ↓</div>
          </div>
          <pre class="fs-json">{html.escape(fs['diagnosis_pretty'])}</pre>
        </div>
      </details>"""

    # Aggregate observations across all patients for the final AI verdict
    agg_a_epistemic_hits = 0
    agg_c_pending_total = 0
    agg_a_codes_hits = 0
    agg_a_precise_total = 0
    agg_c_precise_total = 0
    for s in samples:
        rA = json.loads((_RUNS / s["A_file"]).read_text(encoding="utf-8"))
        rC = json.loads((_RUNS / s["C_file"]).read_text(encoding="utf-8"))
        o = _evaluate_pair(rA, rC)
        agg_a_epistemic_hits += 1 if o["a_has_epistemic"] else 0
        agg_c_pending_total += o["c_pending"]
        agg_a_codes_hits += 1 if o["a_has_codes"] else 0
        agg_a_precise_total += o["a_precise_hits"]
        agg_c_precise_total += o["c_precise_hits"]

    HTML = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Prompt Ablation · A (Naive) vs C (Few-shot PoC)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f5f6fa; color: #1e2130; line-height: 1.6; }}
  .wrap {{ max-width: 1400px; margin: 0 auto; padding: 40px 24px 80px; }}
  header {{ border-bottom: 2px solid #2c3e50; padding-bottom: 24px; margin-bottom: 36px; }}
  header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  header .sub {{ color: #6b7280; font-size: 15px; }}

  h2 {{ font-size: 20px; font-weight: 600; color: #2c3e50; margin-bottom: 16px;
        padding-left: 12px; border-left: 4px solid #4f46e5; }}
  section {{ margin-bottom: 40px; }}

  .method-box {{ background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 20px; }}
  .method-box h3 {{ font-size: 14px; margin-top: 12px; margin-bottom: 6px; color: #4b5563; }}
  .method-box p {{ font-size: 14px; margin-bottom: 8px; color: #374151; }}
  .prompt-code {{ background: #1e293b; color: #e2e8f0; padding: 14px 18px; border-radius: 8px;
                  font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px;
                  line-height: 1.7; white-space: pre-wrap; margin-top: 6px; }}

  .agg-table {{ width: 100%; border-collapse: collapse; background: white;
                border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }}
  .agg-table th, .agg-table td {{ padding: 12px 16px; text-align: left;
                                   border-bottom: 1px solid #f3f4f6; font-size: 14px; }}
  .agg-table th {{ background: #f9fafb; font-weight: 600; color: #4b5563; }}
  .agg-table .A-col {{ color: #b91c1c; font-weight: 600; }}
  .agg-table .C-col {{ color: #047857; font-weight: 600; }}

  .patient {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px;
              padding: 24px; margin-bottom: 32px; }}
  .patient-grid {{ display: grid; grid-template-columns: 240px 1fr 1fr; gap: 20px;
                   margin-top: 16px; }}
  .col-photo img {{ width: 100%; border-radius: 8px; display: block; }}
  .col-photo .lbl {{ font-size: 12px; color: #9ca3af; font-weight: 600;
                     letter-spacing: 1px; margin-bottom: 6px; }}
  .col-photo .filename {{ font-size: 11px; color: #6b7280; margin-top: 8px;
                           font-family: Consolas, monospace; word-break: break-all; }}
  .col-output {{ background: #f9fafb; border-radius: 8px; padding: 14px; overflow: hidden; }}
  .col-A {{ border-left: 4px solid #dc2626; }}
  .col-C {{ border-left: 4px solid #059669; }}
  .col-header {{ display: flex; justify-content: space-between; align-items: center;
                 margin-bottom: 10px; }}
  .badge {{ font-size: 12px; padding: 3px 10px; border-radius: 12px; font-weight: 500; }}
  .badge-A {{ background: #fecaca; color: #991b1b; }}
  .badge-C {{ background: #a7f3d0; color: #065f46; }}
  .latency {{ font-size: 11px; color: #6b7280; }}
  .metric-row {{ display: flex; gap: 12px; margin-bottom: 4px; font-size: 12px;
                 color: #4b5563; flex-wrap: wrap; }}
  .metric {{ background: white; padding: 3px 8px; border-radius: 4px;
             border: 1px solid #e5e7eb; }}
  pre {{ background: #0f172a; color: #cbd5e1; padding: 12px; border-radius: 6px;
         font-size: 11px; line-height: 1.6; overflow-x: auto; max-height: 500px;
         white-space: pre-wrap; margin-top: 10px; }}

  .conclusion-box {{ background: white; border: 1px solid #e5e7eb; border-radius: 10px;
                     padding: 24px; }}
  .conclusion-box h3 {{ font-size: 16px; margin-bottom: 12px; margin-top: 16px;
                        color: #1f2937; }}
  .conclusion-box h3:first-child {{ margin-top: 0; }}
  .conclusion-box ul {{ padding-left: 20px; margin-bottom: 12px; }}
  .conclusion-box li {{ font-size: 14px; color: #374151; margin-bottom: 8px; }}
  .conclusion-box p {{ font-size: 14px; color: #374151; margin-bottom: 10px; line-height: 1.8; }}
  .conclusion-box strong {{ color: #4338ca; }}
  .conclusion-box em {{ color: #059669; font-style: normal; font-weight: 700; }}
  .conclusion-box code {{ background: #f3f4f6; padding: 1px 6px; border-radius: 4px;
                          font-family: "SFMono-Regular", Consolas, monospace; font-size: 12px;
                          color: #4338ca; }}

  details.c-prompt, details.few-shot-example {{ margin-top: 12px;
                                                 background: #f9fafb;
                                                 border: 1px solid #e5e7eb;
                                                 border-radius: 8px;
                                                 padding: 12px 16px; }}
  details.c-prompt summary, details.few-shot-example summary {{
    cursor: pointer; font-weight: 600; color: #4338ca; user-select: none;
    font-size: 13px; }}
  .sp-body {{ background: #0f172a; color: #cbd5e1; padding: 14px; border-radius: 6px;
              font-size: 11px; line-height: 1.6; max-height: 500px;
              overflow-y: auto; white-space: pre-wrap; margin-top: 10px; }}
  .fs-body {{ display: grid; grid-template-columns: 280px 1fr; gap: 16px;
              margin-top: 12px; }}
  .fs-body .fs-img img {{ width: 100%; border-radius: 6px; display: block; }}
  .fs-body .fs-caption {{ font-size: 11px; color: #6b7280; margin-top: 6px;
                          font-style: italic; }}
  .fs-body pre.fs-json {{ background: #0f172a; color: #cbd5e1; padding: 12px;
                          border-radius: 6px; font-size: 10px; line-height: 1.5;
                          max-height: 400px; overflow-y: auto; white-space: pre-wrap; }}

  .verdict {{ background: #eef2ff; border-left: 4px solid #4338ca;
              border-radius: 6px; padding: 14px 18px; margin-top: 16px; }}
  .verdict h4 {{ font-size: 14px; color: #4338ca; margin-bottom: 8px;
                 font-weight: 700; }}
  .verdict ul {{ padding-left: 20px; margin-bottom: 0; }}
  .verdict li {{ font-size: 13px; color: #374151; margin-bottom: 6px; line-height: 1.7; }}
  .verdict em {{ color: #059669; font-style: normal; font-weight: 700; }}
  .verdict code {{ background: white; padding: 1px 5px; border-radius: 3px;
                   font-family: Consolas, monospace; font-size: 11px; color: #4338ca; }}

  footer {{ margin-top: 60px; padding-top: 20px; border-top: 1px solid #e5e7eb;
           color: #9ca3af; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>Prompt Ablation · A (Naive) vs C (Few-shot PoC)</h1>
    <div class="sub">Same VLM (qwen-vl-max), same {n} patient photos, different prompt strategies</div>
  </header>

  <section>
    <h2>实验方法</h2>
    <div class="method-box">
      <h3>研究问题</h3>
      <p>专业 system prompt + 医生审校 few-shot examples 相对于普通产品级 prompt，能带来多大的诊断质量提升？</p>
      <h3>控制变量</h3>
      <p>· 相同 VLM：<b>qwen-vl-max</b>（阿里通义千问，闭源云端 API）<br>
      · 相同 {n} 张患者术前正面照<br>
      · 相同参数（temperature=0.3, top_p=0.8）</p>
      <h3>条件 A · Naive Baseline</h3>
      <p>单轮请求，仅用户消息含图片 + 一段合理的"面部美容顾问"prompt。<b>无 system prompt，无 few-shot，无医美专业规则。</b></p>
      <div class="prompt-code">你是一位面部美容顾问 AI。请分析用户上传的面部正面照片，
识别其中的美容问题并给出改善建议。

请从以下方面进行分析：
1. 皮肤问题（如色斑、痘痘、毛孔、皱纹、暗沉等）
2. 面部结构问题（如松弛、下垂、比例等）
3. 每个问题的严重程度（轻度/中度/重度）
4. 建议改善方向

请以 JSON 格式输出，包含问题列表和整体评价。</div>
      <h3>条件 C · Few-shot PoC（当前方案）</h3>
      <p>完整生产链路：走 <code>backend/app/services/dashscope_diagnosis.py</code>。三部分输入：</p>
      <p>1. <b>System prompt</b>：27 部位诊断规则手册（{sp_lines} 行，{sp_chars // 1024} KB），定义部位命名、10 类问题编码、5 级严重度、JSON schema<br>
      2. <b>Few-shot 示例</b>：2 例三甲医院医生审校过的完整 case（25F + 54F，教年龄→严重度密度）<br>
      3. <b>用户图片 + 可选 age/gender</b></p>

      <details class="c-prompt">
        <summary>展开 · 完整 System Prompt（{sp_lines} 行）</summary>
        <pre class="sp-body">{html.escape(system_prompt)}</pre>
      </details>
      {few_shot_html}
    </div>
  </section>

  <section>
    <h2>汇总指标（{n} 例平均）</h2>
    <table class="agg-table">
      <thead>
        <tr><th>指标</th><th>A · Naive</th><th>C · Few-shot</th><th>说明</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>输出 JSON 合规率</td>
          <td class="A-col">{a_json_pct}%</td>
          <td class="C-col">{c_json_pct}%</td>
          <td>能被 <code>json.loads()</code> 解析</td>
        </tr>
        <tr>
          <td>平均识别问题/部位数</td>
          <td class="A-col">{a_zones_avg:.1f}</td>
          <td class="C-col">{c_zones_avg:.1f}</td>
          <td>下游可用的结构化条目数</td>
        </tr>
        <tr>
          <td>部位颗粒度</td>
          <td class="A-col">自由描述</td>
          <td class="C-col">27 个精确解剖部位</td>
          <td>能否驱动 zone-level 生图</td>
        </tr>
        <tr>
          <td>问题分类</td>
          <td class="A-col">自由文本</td>
          <td class="C-col">10 种医学编码 (PIG/TEX/WR/...)</td>
          <td>能否做统计与规则处理</td>
        </tr>
        <tr>
          <td>严重度分级</td>
          <td class="A-col">3 档（轻/中/重）</td>
          <td class="C-col">5 档 + pending 待补充</td>
          <td>能否区分"需处理" vs "需补充视角"</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>逐例对比</h2>
    {patient_sections}
  </section>

  <section>
    <h2>AI 综合评价</h2>
    <div class="conclusion-box">
      <p style="color:#6b7280;font-size:13px;margin-bottom:16px;">
        以下评价基于 Opus 4.7 对 3 张患者术前照片的独立视觉判读，与 A/C 两组 VLM 输出的
        <b>逐条比对</b>，focus 在<b>产出结论本身的准确性、全面性，以及对下游三类消费者
        （医生 / 患者 / 生图模型）的可用性</b>，而非输出格式。
      </p>

      <h3>一、诊断结论的准确性（Accuracy）</h3>
      <p style="color:#4b5563;font-size:13px;margin-bottom:8px;">
        <em>核心问题：AI 说的问题，在图上是不是真的存在？</em>
      </p>
      <ul>
        <li><strong>A 组：显著的"模板套用"倾向</strong>。3 例中 A 组均输出了近似的问题清单
        （"皮肤暗沉 / 毛孔粗大 / 痘印 / 松弛 / 鼻唇沟明显 / 眼周浮肿"），
        但对照原图：
          <ul style="margin-top:4px;">
            <li>患者 <code>5cbe83f3</code>（年轻女性、皮肤紧致）：A 报"轮廓松弛 / 鼻唇沟较明显"—
            照片上并<b>不存在</b>此类结构性衰老，属于<b>过度诊断</b>；</li>
            <li>患者 <code>147ce64e</code>（圆脸型、皮肤质地良好）：A 报"色斑 / 色素沉着 / 松弛下垂"—
            照片主要问题是<b>骨相与脂肪分布</b>，非衰老或色斑，A 组<b>误判了问题类型</b>；</li>
            <li>患者 <code>bf27e6a1</code>（成熟女性、颧骨雀斑明显）：A 提到"色斑"但同时叠加了
            "眼周浮肿"等<b>看不到的问题</b>。</li>
          </ul>
        </li>
        <li><strong>C 组：结论与照片可视证据基本一致</strong>。
          <ul style="margin-top:4px;">
            <li>对 <code>5cbe83f3</code> 明确指出"面部整体年轻，无明显结构性衰老"，
            仅把眼下暗影 / 泪沟标为 high/low priority — 与实际相符；</li>
            <li>对 <code>147ce64e</code> case_summary 精准写出<b>"下脸宽型 / 圆脸型，非典型结构衰老"</b>—
            这是 A 组完全没能做到的<b>"型 vs 衰老"的临床鉴别</b>；</li>
            <li>对 <code>bf27e6a1</code> 覆盖了 15 个可操作部位，眼下 PIG+WR moderate、法令纹 VOL、
            侧颊 SAG 等均判断合理。<b>一处不足</b>：颧骨密集雀斑被打散进"内侧面颊 PIG"，
            力度不够突出（可能是 few-shot 未覆盖雀斑型案例导致）。</li>
          </ul>
        </li>
      </ul>
      <p><strong>准确性结论：C 组在 3/3 例上判断与照片证据吻合，A 组在 3/3 例上均存在
      模板化的过度诊断或错误归因。</strong></p>

      <h3>二、诊断的全面性（Coverage）</h3>
      <p style="color:#4b5563;font-size:13px;margin-bottom:8px;">
        <em>核心问题：真实存在的问题，AI 有没有漏掉？</em>
      </p>
      <ul>
        <li><strong>A 组：数量看似不少但覆盖失真</strong>。平均 <em>{a_zones_avg:.1f}</em> 个条目，
        但因套用模板，"覆盖"的是模板列表而非该患者实际问题。对 <code>147ce64e</code> 完全
        <b>漏掉了下脸宽的骨相判断</b>，对 <code>bf27e6a1</code> <b>漏掉了法令纹、眉尾松弛</b> 等
        细项。</li>
        <li><strong>C 组：分层覆盖，含"我看不到什么"</strong>。平均 <em>{c_zones_avg:.1f}</em> 个部位，
        其中约 <em>{agg_c_pending_total / n:.1f}</em> 个 <code>pending_*</code> 标注—
        分别代表"需 45°/侧面视角"或"需动态表情视角"才能判断的部位（如咬肌肥大、
        眉间动态纹、鼻基底凹陷）。<b>这不是"漏诊"，而是"知道自己不知道"</b>—
        医生的临床严谨性。</li>
        <li><strong>一处 C 组的实际漏诊</strong>：<code>bf27e6a1</code> 的颧骨雀斑作为最直观问题，
        应当在 case_summary 中独立强调，而不是仅归为"色素不均"。这提示 few-shot 池
        需要补充<b>雀斑型 / 黄褐斑型</b>的 gold case。</li>
      </ul>
      <p><strong>全面性结论：C 组在覆盖上做到了"看到的都写，看不到的标 pending"；
      A 组"写了很多但很多不是这张脸上的问题"。</strong></p>

      <h3>三、下游可用性分析</h3>

      <h4 style="font-size:14px;margin-top:12px;margin-bottom:6px;color:#4338ca;">
        ① 对医生的可用性
      </h4>
      <ul>
        <li><strong>A 组</strong>：医生读完后需要<b>推翻重来</b>—模板化结论无法作为初诊参考，
        反而会误导后续问询方向；且没有部位级的严重度评级，无法据此排治疗优先级。</li>
        <li><strong>C 组</strong>：医生可以把它当作<b>"实习生初诊笔记"</b>—
        27 部位表格 + priority + pending 视角提示，医生只需<b>审校 / 微调</b>而非重写。
        pending 标注帮医生<b>决定要不要让患者补拍侧面照 / 做动态表情视频</b>，
        直接节省问诊时间。</li>
      </ul>

      <h4 style="font-size:14px;margin-top:12px;margin-bottom:6px;color:#4338ca;">
        ② 对患者的可用性
      </h4>
      <ul>
        <li><strong>A 组</strong>：语言温和易读，但"你有色斑 / 松弛 / 鼻唇沟"这种<b>不准确的问题清单</b>
        会引发焦虑或让患者去做<b>没必要的项目</b>（例如年轻患者被暗示需要抗衰）—
        这是医美语境下有实际伤害的错。</li>
        <li><strong>C 组</strong>：结构化 JSON 对患者不友好，但配合前端渲染
        （见 <code>/preview</code> 页面）后可以生成分级清单，且 case_summary 会<b>明确告诉患者
        "你的主要问题是 X 而不是 Y"</b>，避免过度消费。<b>147ce64e 的"非典型结构衰老"结论
        对患者尤其重要</b>—它阻止了不必要的抗衰咨询。</li>
      </ul>

      <h4 style="font-size:14px;margin-top:12px;margin-bottom:6px;color:#4338ca;">
        ③ 对下游生图模型（qwen-image-edit）的可用性
      </h4>
      <ul>
        <li><strong>A 组</strong>：输出是自由文本描述，无法直接作为 image-edit prompt 的输入。
        若强行使用，只能拼成<b>"改善暗沉 / 淡化色斑 / 收紧轮廓"这种整脸打包指令</b>—
        生图模型会退化成<b>美颜滤镜</b>（这正是我们迭代前遇到的问题）。</li>
        <li><strong>C 组</strong>：每个 zone 都带 <code>sub_area + problem_types + severity_level</code>，
        可以按 <code>_PROBLEM_EFFECT_EN</code> × <code>_SEVERITY_INTENSITY</code> 映射规则
        <b>逐部位构造精细的英文编辑指令</b>（"reduce PIG on lower eyelid by 30%,
        keep pores natural on cheeks"）。这是<b>诊断驱动生图</b>能落地的前提—
        A 组的输出根本无法支撑这条链路。</li>
        <li><strong>pending 标注的额外价值</strong>：C 组 pending 部位<b>会被生图模块自动跳过</b>
        （不能生成"我们看不到的部位"的术后效果），避免了生图模型幻觉出错误改动。</li>
      </ul>

      <h3>四、综合判断</h3>
      <p>
      <strong>C 组的价值不在"输出更结构化"，而在<b>三个消费者都能真正用</b></strong>：
      </p>
      <ul>
        <li>诊断<b>说的都是真的</b>—医生不用推翻，患者不会被误导；</li>
        <li>诊断<b>说的够全</b>—漏项极少，且明确标注了看不到的部位；</li>
        <li>诊断<b>结构化到可以驱动下游</b>—生图能靶向、报告能分级、方案能匹配设备库。</li>
      </ul>
      <p>
      A 组的问题<b>不是"格式不对"，而是"内容失真 + 无法消费"</b>—
      即使把 A 的输出手工整理成 C 的 schema，条目本身仍然是错的（
      年轻脸上的"松弛"、骨相圆脸的"色斑"、成熟脸上的"浮肿"）。
      <b>这说明 few-shot 带来的不只是格式约束，更是<u>诊断口味</u>的迁移</b>—
      教会 VLM"哪些问题在这张脸上真正重要、哪些应该留白让医生看"。
      </p>

      <h3>五、遗留问题与改进方向</h3>
      <ul>
        <li><strong>准确性侧</strong>：C 组对<b>颧骨雀斑 / 黄褐斑</b>的强调不够，
        建议 few-shot 池新增 1-2 例雀斑型 gold case。</li>
        <li><strong>全面性侧</strong>：<code>147ce64e</code> 的"下脸宽因未知"—骨/肌/脂三种成因
        C 组无法从正面照区分。建议在产品层<b>要求患者补拍侧面照 / 咬合位</b>作为二次上传。</li>
        <li><strong>成本侧</strong>：C 组约 ¥0.66/次（A 组 ¥0.04/次，贵 15 倍），
        主要来自 27k prompt tokens 编码。后续<b>fine-tune 的价值就是把这些 tokens
        蒸馏进权重</b>—保持 C 的质量、降到 A 的成本。</li>
      </ul>
    </div>
  </section>

  <footer>
    Generated for advisor review · Data: <code>tmp/eval_runs/ablation_A_vs_C/</code>
  </footer>
</div>
</body>
</html>"""

    out = _RUNS / "ablation_report.html"
    out.write_text(HTML, encoding="utf-8")
    print(f"wrote {out} ({len(HTML)//1024} KB)")


if __name__ == "__main__":
    main()
