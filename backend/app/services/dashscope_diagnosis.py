"""Cloud DashScope (qwen3-vl-flash) diagnosis service — PoC cheap-and-fast path.

Same 3-shot doctor-review prompt structure as vllm_diagnosis, but calls
DashScope's OpenAI-compatible endpoint instead of local vLLM. Trade-offs:
    - No `<think>` chain (flash doesn't support reasoning tokens)
    - ~10-20s latency vs local 30-90s
    - ~0.02 CNY / call vs local free-but-tied-up-a-H100
    - Lower model quality (7B-class flash vs 32B-class thinking)

Reuses `_load_system_prompt`, `_load_few_shot_messages`, `_extract_json_block`,
`_resize_bytes_for_vlm` from vllm_diagnosis so the prompt is byte-identical.
"""
from __future__ import annotations

import base64
import time
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.vllm_diagnosis import (
    _extract_json_block,
    _load_few_shot_messages,
    _load_system_prompt,
    _resize_bytes_for_vlm,
)

logger = get_logger("services.dashscope_diagnosis")


def _client() -> AsyncOpenAI:
    s = get_settings()
    api_key = s.dashscope_api_key or s.llm_api_key
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not set")
    return AsyncOpenAI(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=api_key,
    )


async def diagnose_from_image_cloud(
    image_base64: str,
    *,
    age: int | None = None,
    gender: str | None = None,
    model: str = "qwen3-vl-flash",
) -> dict[str, Any] | None:
    """Same signature as vllm_diagnosis.diagnose_from_image, cloud backend."""
    if not image_base64:
        return None

    try:
        raw_bytes = base64.b64decode(image_base64, validate=True)
    except Exception as exc:
        logger.warning("dashscope_diagnosis: bad base64: %s", exc)
        return None

    try:
        resized, out_mime = _resize_bytes_for_vlm(raw_bytes)
    except Exception as exc:
        logger.warning("dashscope_diagnosis: resize failed: %s", exc)
        return None
    resized_b64 = base64.b64encode(resized).decode("ascii")
    logger.info(
        "dashscope_diagnosis: user image %d KB → resized %d KB",
        len(raw_bytes) // 1024, len(resized) // 1024,
    )

    system_prompt = _load_system_prompt()
    few_shot = _load_few_shot_messages()
    if len(few_shot) < 2:
        logger.error("dashscope_diagnosis: few-shot messages missing")
        return None

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

    client = _client()
    start = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            top_p=0.8,
            max_tokens=6000,
        )
    except Exception as exc:
        logger.warning("dashscope_diagnosis: call failed: %s", exc, exc_info=True)
        return None
    latency = time.time() - start

    raw = resp.choices[0].message.content or ""
    diagnosis = _extract_json_block(raw)
    if diagnosis is None:
        logger.warning("dashscope_diagnosis: JSON parse failed. head: %s", raw[:500])
        return None

    usage = resp.usage.model_dump() if resp.usage else {}
    in_tok = usage.get("prompt_tokens", 0)
    out_tok = usage.get("completion_tokens", 0)
    # DashScope pricing per 1M tokens (input, output) in CNY. Fallback = flash rate.
    _PRICING = {
        "qwen3-vl-flash": (0.8, 3.2),
        "qwen3-vl-plus": (4.0, 12.0),
        "qwen-vl-max": (20.0, 20.0),
        "qwen-vl-max-latest": (20.0, 20.0),
    }
    price_in, price_out = _PRICING.get(model, _PRICING["qwen3-vl-flash"])
    cost_cny = in_tok * price_in / 1_000_000 + out_tok * price_out / 1_000_000

    logger.info(
        "dashscope_diagnosis ok: %.1fs, in=%s out=%s, cost≈¥%.4f",
        latency, in_tok, out_tok, cost_cny,
    )

    return {
        "diagnosis": diagnosis,
        "raw_text": raw,
        "thinking": None,  # flash has no thinking
        "latency_sec": latency,
        "usage": usage,
        "estimated_cost_cny": cost_cny,
        "model": model,
    }
