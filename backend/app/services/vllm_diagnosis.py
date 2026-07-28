"""Local vLLM (Qwen3-VL-32B-Thinking) diagnosis service — PoC pipeline.

Takes a facial photo and produces a full 27-zone diagnosis JSON matching
`tmp/system_prompt_for_diagnosis.md` schema, using 3-shot in-context learning
from doctor-reviewed cases (b2/df/db across 25F/45F/54F age spread).

Deployment: vLLM OpenAI-compatible server on the H100 box, reached locally
through an SSH tunnel — so `vllm_base_url=http://localhost:8000/v1` works
identically from a dev laptop and from the server itself.
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from PIL import Image

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("services.vllm_diagnosis")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SYSTEM_PROMPT_PATH = _REPO_ROOT / "tmp" / "system_prompt_for_diagnosis.md"
_DEFAULT_FEW_SHOT_DIR = (
    _REPO_ROOT
    / "downloads"
    / "agentcare_customers"
    / "api_token_run_2026-06-17T06-34-09-075Z"
    / "contrast_filter_2026-06-17T07-55-26-363Z"
    / "images_by_patient"
)

# Fixed 2-shot roster for LEAVE-ONE-OUT eval:
#   Removed CASE003 (patient_dff3abf1, 45F) from the shots so we can feed her
#   photo at inference and see if the model interpolates from the 25F/54F
#   extremes. Keeps 25F + 54F to teach the age → severity-density gradient.
# Uses `diagnosis_doctor.json` (Slim schema, doctor-reviewed gold labels).
# Tuple: (patient_id, image_filename, age, gender)
# age/gender live here because we removed `demographics` from the JSON schema
# (it was training the model to fabricate patient_id at inference time).
_FEW_SHOT_PATIENTS = [
    ("patient_b2a332e5", "patient_b2a332e5_20260519_pre.png", 25, "female"),
    ("patient_0943db4f", "patient_0943db4f_20260516_pre.png", 54, "female"),
]

_FEW_SHOT_DIAGNOSIS_FILENAME = "diagnosis_doctor.json"

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _few_shot_root() -> Path:
    s = get_settings()
    return Path(s.vllm_few_shot_dir) if s.vllm_few_shot_dir else _DEFAULT_FEW_SHOT_DIR


# Max long-edge in pixels. Qwen3-VL tokenizes ~800 tokens/image at 768x768; at
# 1080p it explodes to ~3000. Diagnosis rules ("肤质、色素、红区、毛孔、静态纹路,
# 明显骨感、松弛、折痕") don't need 1080p — the medical signal saturates well
# below it. See PoC decision log.
_VLM_IMAGE_MAX_EDGE = 768
_VLM_IMAGE_JPEG_QUALITY = 88


def _resize_bytes_for_vlm(raw: bytes) -> tuple[bytes, str]:
    """Downscale (keep aspect ratio) + re-encode as JPEG. No-op if already small."""
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    long_edge = max(w, h)
    if long_edge > _VLM_IMAGE_MAX_EDGE:
        scale = _VLM_IMAGE_MAX_EDGE / long_edge
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_VLM_IMAGE_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), "jpeg"


def _encode_image_file(path: Path) -> str:
    resized, mime = _resize_bytes_for_vlm(path.read_bytes())
    b64 = base64.b64encode(resized).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


@lru_cache(maxsize=1)
def _load_few_shot_messages() -> list[dict[str, Any]]:
    """Assemble the 3-shot user/assistant turn pairs once and cache.

    Each shot = (user turn with image + short instruction) + (assistant turn
    with the ground-truth diagnosis.json as text). Model learns the mapping
    "front photo of this age/skin → this 27-zone JSON".
    """
    root = _few_shot_root()
    msgs: list[dict[str, Any]] = []

    for patient_id, image_name, age, gender in _FEW_SHOT_PATIENTS:
        patient_dir = root / patient_id
        diag_path = patient_dir / _FEW_SHOT_DIAGNOSIS_FILENAME
        img_path = patient_dir / image_name
        if not diag_path.exists() or not img_path.exists():
            logger.warning("few-shot missing: %s or %s", diag_path, img_path)
            continue

        diagnosis = json.loads(diag_path.read_text(encoding="utf-8"))
        image_uri = _encode_image_file(img_path)
        gender_cn = "女" if gender == "female" else "男"

        msgs.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_uri}},
                {
                    "type": "text",
                    "text": (
                        f"患者 {age}岁{gender_cn}，仅正面照。"
                        f"按规则手册给出 27 部位的完整 diagnosis JSON。"
                    ),
                },
            ],
        })
        msgs.append({
            "role": "assistant",
            "content": json.dumps(diagnosis, ensure_ascii=False, indent=2),
        })

    return msgs


def _strip_thinking(text: str) -> tuple[str, str | None]:
    """Split Qwen3-VL-Thinking output into (final_answer, thinking_trace).

    Decision 2/A: user-facing response is the JSON after </think>; the trace
    is logged for debugging but not shown.
    """
    think_match = _THINK_RE.search(text)
    thinking = think_match.group(0) if think_match else None
    final = _THINK_RE.sub("", text).strip()
    return final, thinking


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Recover the diagnosis JSON even when the model adds a preamble.

    Tries a straight parse first, then falls back to grabbing the outermost
    `{...}` — enough for well-behaved outputs; anything more mangled surfaces
    as None so the caller can log the raw text and reprompt.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.DOTALL)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None


def _client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(base_url=s.vllm_base_url, api_key=s.vllm_api_key)


async def diagnose_from_image(
    image_base64: str,
    *,
    age: int | None = None,
    gender: str | None = None,
    mime: str = "png",
) -> dict[str, Any] | None:
    """Run the full 3-shot diagnosis pipeline on a single front photo.

    Returns on success:
        {
          "diagnosis": <parsed 27-zone JSON>,
          "raw_text": <model output with thinking stripped>,
          "thinking": <the <think>...</think> block, or None>,
          "latency_sec": float,
          "usage": {input_tokens, output_tokens, ...},
        }
    Returns None on any failure (bad base64, vLLM error, JSON parse fail).
    """
    if not image_base64:
        return None

    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
    except Exception as exc:
        logger.warning("vllm_diagnosis: bad base64: %s", exc)
        return None

    try:
        resized, out_mime = _resize_bytes_for_vlm(raw_bytes)
    except Exception as exc:
        logger.warning("vllm_diagnosis: image resize failed: %s", exc)
        return None
    resized_b64 = base64.b64encode(resized).decode("ascii")
    logger.info(
        "vllm_diagnosis: user image %d KB → resized %d KB",
        len(raw_bytes) // 1024, len(resized) // 1024,
    )

    system_prompt = _load_system_prompt()
    few_shot = _load_few_shot_messages()
    if len(few_shot) < 2:
        logger.error("vllm_diagnosis: few-shot messages missing, cannot proceed")
        return None

    user_hint = "患者仅正面照，按规则手册给出 27 部位的完整 diagnosis JSON。"
    if age or gender:
        gender_cn = "女" if gender == "female" else ("男" if gender == "male" else "")
        user_hint = (
            f"患者 {age or '未知'}岁{gender_cn}，仅正面照。"
            f"按规则手册给出 27 部位的完整 diagnosis JSON。"
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *few_shot,
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{out_mime};base64,{resized_b64}"},
                },
                {"type": "text", "text": user_hint},
            ],
        },
    ]

    settings = get_settings()
    client = _client()

    start = time.time()
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=messages,
            temperature=0.3,
            top_p=0.8,
            max_tokens=10000,
        )
    except Exception as exc:
        logger.warning("vllm_diagnosis: vLLM call failed: %s", exc, exc_info=True)
        return None
    latency = time.time() - start

    raw = resp.choices[0].message.content or ""
    final_text, thinking = _strip_thinking(raw)
    diagnosis = _extract_json_block(final_text)

    if diagnosis is None:
        logger.warning(
            "vllm_diagnosis: JSON parse failed. raw head: %s", final_text[:500]
        )
        return None

    usage = resp.usage.model_dump() if resp.usage else {}
    logger.info(
        "vllm_diagnosis ok: %.1fs, in=%s out=%s",
        latency,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
    )

    return {
        "diagnosis": diagnosis,
        "raw_text": final_text,
        "thinking": thinking,
        "latency_sec": latency,
        "usage": usage,
    }
