"""E2E treatment preview endpoint.

Flow:
  image_base64 (+ optional age, gender)
    → dashscope qwen-vl-max diagnosis
    → treatment_preview.generate_preview_from_bytes (qwen-image-edit)
    → report_renderer.render (Markdown)
  Returns everything in one response.

Fixture branch:
  use_fixture="patient_dff3abf1" → skip both API calls, read pre-generated
  diagnosis + before/after images from tmp/. Turns a ~200s live call into
  a ~50ms local read for demo safety.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services import report_renderer, treatment_preview
from app.services.dashscope_diagnosis import diagnose_from_image_cloud

logger = get_logger("routers.treatment_preview")

router = APIRouter(prefix="/api/v1", tags=["treatment-preview"])

_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tmp"
_FIXTURE_DIAGNOSIS = _FIXTURE_ROOT / "smoke_diagnosis_output_cloud.json"
_FIXTURE_DIR = _FIXTURE_ROOT / "treatment_previews" / "patient_dff3abf1"


class PreviewRequest(BaseModel):
    image_base64: str | None = Field(None, description="Base64 (no data-uri prefix)")
    mime: Literal["png", "jpeg", "webp"] = "png"
    age: int | None = None
    gender: Literal["female", "male"] | None = None
    use_fixture: Literal["patient_dff3abf1"] | None = None


class PreviewPlan(BaseModel):
    id: str
    title: str
    target_zones: list[str]
    problem_summary: str
    instruction: str
    after_image_base64: str
    latency_sec: float
    status: str
    error: str | None = None


class PreviewResponse(BaseModel):
    diagnosis: dict[str, Any]
    diagnosis_latency_sec: float
    diagnosis_model: str
    before_image_base64: str
    plans: list[PreviewPlan]
    report_markdown: str


def _load_fixture() -> PreviewResponse:
    """Read pre-generated diagnosis + images from tmp/. Used for demo safety."""
    diag_data = json.loads(_FIXTURE_DIAGNOSIS.read_text(encoding="utf-8"))
    diagnosis = diag_data["diagnosis"]
    model_meta = {
        "model": diag_data.get("model", "qwen-vl-max"),
        "latency_sec": diag_data.get("latency_sec", 0.0),
        "usage": diag_data.get("usage", {}),
        "estimated_cost_cny": diag_data.get("estimated_cost_cny", 0.0),
    }

    before_bytes = (_FIXTURE_DIR / "original_pre.png").read_bytes()
    after_bytes = (_FIXTURE_DIR / "plan_skin.png").read_bytes()
    plans_manifest = json.loads((_FIXTURE_DIR / "plans.json").read_text(encoding="utf-8"))
    skin_plan = next(p for p in plans_manifest["plans"] if p["id"] == "skin")

    plan = PreviewPlan(
        id="skin",
        title=skin_plan["title"],
        target_zones=skin_plan.get("target_zones", []),
        problem_summary=skin_plan.get("problem_summary", ""),
        instruction=skin_plan["instruction"],
        after_image_base64=base64.b64encode(after_bytes).decode("ascii"),
        latency_sec=skin_plan.get("latency_sec", 0.0),
        status="ok",
    )

    report = report_renderer.render(
        diagnosis, model_meta=model_meta, age=45, gender="female"
    )

    return PreviewResponse(
        diagnosis=diagnosis,
        diagnosis_latency_sec=0.0,
        diagnosis_model="fixture",
        before_image_base64=base64.b64encode(before_bytes).decode("ascii"),
        plans=[plan],
        report_markdown=report,
    )


@router.post("/treatment-preview", response_model=PreviewResponse)
async def treatment_preview_endpoint(req: PreviewRequest) -> PreviewResponse:
    if req.use_fixture == "patient_dff3abf1":
        logger.info("treatment-preview: fixture path")
        try:
            return _load_fixture()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=f"fixture missing: {exc}")

    if not req.image_base64:
        raise HTTPException(
            status_code=400, detail="image_base64 required unless use_fixture is set"
        )

    logger.info(
        "treatment-preview: live path (age=%s gender=%s)", req.age, req.gender
    )

    diag_start = time.time()
    diag_result = await diagnose_from_image_cloud(
        req.image_base64, age=req.age, gender=req.gender, model="qwen-vl-max"
    )
    if diag_result is None:
        raise HTTPException(
            status_code=502, detail="qwen-vl-max diagnosis failed; see server logs"
        )
    diag_latency = time.time() - diag_start
    diagnosis = diag_result["diagnosis"]

    try:
        image_bytes = base64.b64decode(req.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"bad image_base64: {exc}")

    plans_out = await treatment_preview.generate_preview_from_bytes(image_bytes, diagnosis)
    plans = [PreviewPlan(**p) for p in plans_out]

    model_meta = {
        "model": diag_result.get("model", "qwen-vl-max"),
        "latency_sec": diag_result.get("latency_sec", 0.0),
        "usage": diag_result.get("usage", {}),
        "estimated_cost_cny": diag_result.get("estimated_cost_cny", 0.0),
    }
    report = report_renderer.render(
        diagnosis, model_meta=model_meta, age=req.age, gender=req.gender
    )

    return PreviewResponse(
        diagnosis=diagnosis,
        diagnosis_latency_sec=diag_latency,
        diagnosis_model=diag_result.get("model", "qwen-vl-max"),
        before_image_base64=req.image_base64,
        plans=plans,
        report_markdown=report,
    )
