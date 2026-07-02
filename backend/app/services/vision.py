"""Vision feature extraction service for the consult agent.

Wraps the V2 (domain-aware) prompt that vision_pilot.py validates against
the medical-aesthetic 9-principle clinical schema (bone / soft-tissue / skin).
Returns a structured dict with top_layer / top_feature / triggered_principles
plus the raw VLM text so the recommend node can inject it into LLM context.

Gracefully degrades to None on any failure so the agent pipeline never breaks
because of vision: text-only path is always a valid fallback.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import re
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("services.vision")

_ROOT = Path(__file__).resolve().parents[3]
_V2_PROMPT_PATH = _ROOT / "docs" / "vision_pilot" / "prompts" / "v2_domain_aware.txt"

# Pricing matches vision_pilot.PRICE_CNY_PER_1M for qwen3-vl-flash (CNY/1M tokens).
_PRICE_PER_1M = {
    "qwen3-vl-flash": {"input": 0.8, "output": 3.2},
}

_TOP_LAYER_RE = re.compile(r"top_layer\s*[:：]\s*([A-Za-z_]+)")
_TOP_FEATURE_RE = re.compile(r"top_feature\s*[:：]\s*(.+)")
_TRIGGERED_RE = re.compile(r"triggered_principles\s*[:：]\s*(.+)")

# 10 MB encoded ≈ 7.5 MB raw — bigger images get rejected to keep latency bounded
# and to stay within DashScope's reliable single-call size envelope.
_MAX_BASE64_BYTES = 10 * 1024 * 1024

_HEALTHY_LAYERS = {"none", "n/a", "无", "正常", ""}


def _load_v2_prompt() -> str:
    return _V2_PROMPT_PATH.read_text(encoding="utf-8")


def _detect_image_mime(image_bytes: bytes) -> str | None:
    """Sniff magic bytes to confirm the upload is actually an image."""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return None


def _api_key() -> str:
    s = get_settings()
    return s.dashscope_api_key or s.llm_api_key or ""


def _parse_summary(text: str) -> tuple[str | None, str | None, list[str]]:
    """Pull top_layer / top_feature / triggered_principles from V2's Summary block."""
    top_layer_match = _TOP_LAYER_RE.search(text)
    top_feature_match = _TOP_FEATURE_RE.search(text)
    triggered_match = _TRIGGERED_RE.search(text)

    top_layer = top_layer_match.group(1).strip().lower() if top_layer_match else None
    top_feature = (
        top_feature_match.group(1).strip().strip('"').strip("`").rstrip(".")
        if top_feature_match
        else None
    )

    triggered: list[str] = []
    if triggered_match:
        raw = triggered_match.group(1).strip().lstrip("[").rstrip("]")
        triggered = [t.strip() for t in raw.split(",") if t.strip()]

    return top_layer, top_feature, triggered


def _call_dashscope(image_data_uri: str, prompt: str, model: str) -> dict[str, Any]:
    """Sync DashScope call. Caller wraps with asyncio.to_thread."""
    import dashscope
    from dashscope import MultiModalConversation

    dashscope.api_key = _api_key()

    messages = [{
        "role": "user",
        "content": [
            {"image": image_data_uri},
            {"text": prompt},
        ],
    }]

    start = time.time()
    response = MultiModalConversation.call(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )
    latency = time.time() - start

    if getattr(response, "status_code", 200) != 200:
        raise RuntimeError(f"DashScope returned status {response.status_code}: {response}")

    content = response.output.choices[0].message.content
    if isinstance(content, list):
        text = "\n".join(
            str(item["text"]) for item in content
            if isinstance(item, dict) and "text" in item
        ).strip()
    else:
        text = str(content).strip()

    usage_obj = getattr(response, "usage", None)
    usage = dict(usage_obj.items()) if hasattr(usage_obj, "items") else (usage_obj or {})

    return {"text": text, "latency_sec": latency, "usage": usage}


def _estimate_cost(model: str, usage: dict[str, Any]) -> float | None:
    prices = _PRICE_PER_1M.get(model)
    if not prices:
        return None
    in_tok = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    out_tok = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    return in_tok * prices["input"] / 1_000_000 + out_tok * prices["output"] / 1_000_000


async def extract_visual_features(
    image_base64: str,
    model: str = "qwen3-vl-flash",
) -> dict[str, Any] | None:
    """Run V2 (domain-aware) extraction on a base64 image.

    Returns a dict on success:
        {top_layer, top_feature, triggered_principles, raw_text, latency_sec, estimated_cost_cny}
    Returns None on any failure (no key, invalid image, size cap, VLM error, parse miss).
    The caller (vision_extract node) treats None as "skip vision, run text-only".
    """
    if not image_base64:
        return None

    if len(image_base64) > _MAX_BASE64_BYTES:
        logger.warning("vision: base64 payload %d bytes exceeds cap, skipping", len(image_base64))
        return None

    if not _api_key():
        logger.warning("vision: DASHSCOPE_API_KEY/LLM_API_KEY not set, skipping VLM")
        return None

    try:
        image_bytes = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        logger.warning("vision: base64 decode failed: %s", exc)
        return None

    mime = _detect_image_mime(image_bytes)
    if not mime:
        logger.warning("vision: not a recognized image format (jpeg/png/webp)")
        return None

    image_data_uri = f"data:image/{mime};base64,{image_base64}"
    prompt = _load_v2_prompt()

    try:
        result = await asyncio.to_thread(_call_dashscope, image_data_uri, prompt, model)
    except Exception as exc:
        logger.warning("vision: VLM call failed: %s", exc, exc_info=True)
        return None

    text = result["text"]
    top_layer, top_feature, triggered = _parse_summary(text)

    if not top_layer or top_layer in _HEALTHY_LAYERS or not top_feature:
        logger.info("vision: V2 declared healthy/no-feature (top_layer=%s)", top_layer)
        return {
            "top_layer": top_layer or "none",
            "top_feature": None,
            "triggered_principles": [],
            "raw_text": text,
            "latency_sec": result["latency_sec"],
            "estimated_cost_cny": _estimate_cost(model, result["usage"]),
        }

    return {
        "top_layer": top_layer,
        "top_feature": top_feature,
        "triggered_principles": triggered,
        "raw_text": text,
        "latency_sec": result["latency_sec"],
        "estimated_cost_cny": _estimate_cost(model, result["usage"]),
    }
