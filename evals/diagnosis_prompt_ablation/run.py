"""A vs C diagnosis-prompt ablation runner.

Reads a sample sheet (see samples/README.md), runs both prompt conditions on
every sample, dumps raw outputs to results/<sheet_stem>_<timestamp>/.

Condition A: naive baseline (see prompts.NAIVE_PROMPT)
Condition C: production few-shot pipeline via backend.app.services.dashscope_diagnosis

Patient images are resolved from COSMETIC_DATA_ROOT (default: <repo>/downloads)
via glob against the `**/images_by_patient/<patient_id>/<patient_id>_<date>_pre.png`
convention — the data directory itself is gitignored (patient privacy).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from openai import AsyncOpenAI

from app.services.dashscope_diagnosis import diagnose_from_image_cloud

from prompts import NAIVE_PROMPT

_MODEL = "qwen-vl-max"
_DATA_ROOT = Path(os.environ.get("COSMETIC_DATA_ROOT", _REPO_ROOT / "downloads"))


def _resolve_image(patient_id: str, date: str) -> Path:
    filename = f"{patient_id}_{date}_pre.png"
    candidates = list(_DATA_ROOT.glob(f"**/images_by_patient/{patient_id}/{filename}"))
    if not candidates:
        raise FileNotFoundError(
            f"can't find {filename} under {_DATA_ROOT}. "
            f"Set COSMETIC_DATA_ROOT if your patient dataset lives elsewhere."
        )
    return candidates[0]


def _load_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def run_condition_A(image_b64: str, age: int | None, gender: str | None) -> dict:
    """Naive baseline: single-shot, no system prompt, no few-shot."""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    client = AsyncOpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=api_key,
    )
    start = time.time()
    resp = await client.chat.completions.create(
        model=_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": NAIVE_PROMPT},
            ],
        }],
        temperature=0.3,
        top_p=0.8,
        max_tokens=4000,
    )
    latency = time.time() - start
    return {
        "condition": "A",
        "prompt_used": NAIVE_PROMPT,
        "raw_output": resp.choices[0].message.content or "",
        "latency_sec": latency,
        "usage": resp.usage.model_dump() if resp.usage else {},
        "model": _MODEL,
        "user_inputs": {"age": age, "gender": gender},
    }


async def run_condition_C(image_b64: str, age: int | None, gender: str | None) -> dict:
    """Production few-shot path via dashscope_diagnosis service."""
    start = time.time()
    result = await diagnose_from_image_cloud(image_b64, age=age, gender=gender, model=_MODEL)
    latency = time.time() - start
    if result is None:
        return {"condition": "C", "error": "diagnose_from_image_cloud returned None", "latency_sec": latency}
    return {
        "condition": "C",
        "prompt_used": "diagnosis_system.md + 2-shot doctor cases (see backend/app/prompts/)",
        "diagnosis_json": result["diagnosis"],
        "raw_output": result["raw_text"],
        "latency_sec": latency,
        "usage": result["usage"],
        "estimated_cost_cny": result.get("estimated_cost_cny", 0.0),
        "model": _MODEL,
        "user_inputs": {"age": age, "gender": gender},
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", default=str(_HERE / "samples" / "default.json"),
                    help="Path to a sample sheet JSON (see samples/README.md)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run the first N samples (for smoke testing)")
    args = ap.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("[FAIL] DASHSCOPE_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    sheet_path = Path(args.samples).resolve()
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    samples = sheet["samples"][: args.limit] if args.limit else sheet["samples"]

    ts = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    run_dir = _HERE / "results" / f"{sheet_path.stem}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[..] sheet={sheet_path.name}  samples={len(samples)}  run_dir={run_dir}")

    manifest = {
        "sheet": sheet_path.name,
        "sheet_description": sheet.get("description", ""),
        "model": _MODEL,
        "started_at": ts,
        "samples": [],
    }

    for s in samples:
        pid = s["patient_id"]
        date = s["date"]
        age = s.get("user_inputs", {}).get("age")
        gender = s.get("user_inputs", {}).get("gender")
        print(f"\n=== {pid} ({date}) age={age} gender={gender} ===")

        img_path = _resolve_image(pid, date)
        img_b64 = _load_image_b64(img_path)

        print("  [A] naive prompt...")
        result_A = await run_condition_A(img_b64, age, gender)
        (run_dir / f"{pid}_A.json").write_text(
            json.dumps(result_A, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"      {result_A['latency_sec']:.1f}s")

        print("  [C] few-shot prompt...")
        result_C = await run_condition_C(img_b64, age, gender)
        (run_dir / f"{pid}_C.json").write_text(
            json.dumps(result_C, ensure_ascii=False, indent=2), encoding="utf-8")
        if "error" in result_C:
            print(f"      [FAIL] {result_C['error']}")
        else:
            print(f"      {result_C['latency_sec']:.1f}s, ¥{result_C.get('estimated_cost_cny', 0):.3f}")

        manifest["samples"].append({
            "patient_id": pid,
            "date": date,
            "source_image": img_path.name,
            "user_inputs": {"age": age, "gender": gender},
            "notes": s.get("notes", ""),
            "A_file": f"{pid}_A.json",
            "C_file": f"{pid}_C.json",
            "A_latency_sec": result_A["latency_sec"],
            "C_latency_sec": result_C.get("latency_sec", 0.0),
        })

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] wrote {len(samples)*2} outputs + manifest -> {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
