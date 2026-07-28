"""PoC diagnosis endpoint: front photo → 27-zone diagnosis JSON via local vLLM."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.vllm_diagnosis import diagnose_from_image

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


class DiagnosisRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded front photo (no data-uri prefix)")
    age: int | None = None
    gender: str | None = Field(None, description="'female' | 'male'")
    mime: str = Field("png", description="'png' | 'jpeg' | 'webp'")


class DiagnosisResponse(BaseModel):
    diagnosis: dict
    latency_sec: float
    usage: dict
    thinking: str | None = None


@router.post("", response_model=DiagnosisResponse)
async def diagnose(req: DiagnosisRequest) -> DiagnosisResponse:
    result = await diagnose_from_image(
        req.image_base64, age=req.age, gender=req.gender, mime=req.mime
    )
    if result is None:
        raise HTTPException(status_code=502, detail="vLLM diagnosis failed; see server logs")
    return DiagnosisResponse(
        diagnosis=result["diagnosis"],
        latency_sec=result["latency_sec"],
        usage=result["usage"],
        thinking=result["thinking"],
    )
