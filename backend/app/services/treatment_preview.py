"""Treatment plan generator + qwen-image-edit preview (service layer).

Ported from tmp/generate_treatment_preview.py — the standalone script stays
as an experimentation entry point; this service is what the API uses.

Pipeline:
    diagnosis JSON
      → rule-based grouping into "skin plan" / "structural plan"
      → deterministic template renders an English edit instruction
        (fully derived from diagnosis fields — no per-user hardcoding)
      → qwen-image-edit generates the post-treatment simulation image
"""
from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any

from PIL import Image

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("services.treatment_preview")

_IMAGE_EDIT_MODEL = "qwen-image-edit"

# Problem-type → category (matches system_prompt "四、问题类型分类" codes)
_SKIN_TYPES = {"PIG", "TEX", "PORE", "RED", "WR"}
_STRUCT_TYPES = {"VOL", "SAG", "DYN", "FAT", "PROP"}

_ZONE_EN = {
    "额头": "forehead",
    "下眼睑皮肤": "lower eyelid skin",
    "内侧面颊/眼颊连接": "medial cheek / eye-cheek junction",
    "颧部/颧弓": "zygomatic / cheekbone area",
    "眉部/眉尾": "brow / brow tail",
    "泪沟/眶下凹陷": "tear trough / infraorbital hollow",
    "眼颊交界/睑颊沟": "lid-cheek junction",
    "苹果肌/前颊": "malar / anterior cheek",
    "侧颊/外侧面颊": "lateral cheek",
    "法令纹/鼻唇沟": "nasolabial fold",
    "口周两侧": "perioral / lateral mouth",
    "颌前沟/pre-jowl": "pre-jowl sulcus",
}

# problem_type → English visual-effect phrase (what should the skin LOOK like,
# not which device was used — image-edit models have no device→pixel knowledge).
_PROBLEM_EFFECT_EN = {
    "PIG":  "reduce pigmentation spots and even out skin tone",
    "TEX":  "refine skin texture and improve smoothness",
    "PORE": "slightly minimize enlarged pores (pores must remain visible)",
    "RED":  "reduce redness and diffuse erythema",
    "WR":   "soften fine wrinkles",
    "VOL":  "restore subtle volume and support",
    "SAG":  "gently lift and improve firmness",
    "DYN":  "soften dynamic expression lines",
    "FAT":  "refine contour subtly",
    "PROP": "improve proportional transition",
}

# severity_level → (adjective, magnitude). Product decision, not medical fact.
_SEVERITY_INTENSITY = {
    "mild":            ("very subtle", "~15%"),
    "mild_moderate":   ("subtle",      "~25%"),
    "moderate":        ("moderate",    "~40%"),
    "moderate_severe": ("noticeable",  "~55%"),
    "severe":          ("clear",       "~65%"),
}


def _is_plan_candidate(z: dict) -> bool:
    sev = z.get("severity_level", "")
    if sev == "none_or_maintenance" or sev.startswith("pending"):
        return False
    return bool(z.get("problem_types"))


def _classify_zone(z: dict) -> set[str]:
    types = set(z.get("problem_types") or [])
    cats = set()
    if types & _SKIN_TYPES:
        cats.add("skin")
    if types & _STRUCT_TYPES:
        cats.add("structural")
    return cats


def _summarize_zones(zones: list[dict], relevant_types: set[str]) -> str:
    parts = []
    for z in zones[:5]:
        types = [t for t in (z.get("problem_types") or []) if t in relevant_types]
        parts.append(f"{z['sub_area']}({','.join(types) or '?'})")
    return "、".join(parts)


def build_plans(diagnosis: dict) -> list[dict]:
    """Return skin plan (structural deferred; not validated in production yet)."""
    zones = diagnosis.get("professional_assessment", [])
    candidates = [z for z in zones if _is_plan_candidate(z)]
    skin_zones = [z for z in candidates if "skin" in _classify_zone(z)]
    plans: list[dict] = []
    if skin_zones:
        plans.append({
            "id": "skin",
            "title": "皮肤表层改善方案",
            "focus": "色素、纹理、毛孔、细纹等表层问题",
            "target_zones": skin_zones,
            "problem_summary": _summarize_zones(skin_zones, _SKIN_TYPES),
        })
    return plans


def build_edit_instruction(plan: dict) -> str:
    """Diagnosis-driven English prompt. See original file for design rationale."""
    relevant_types = _SKIN_TYPES if plan["id"] == "skin" else _STRUCT_TYPES

    zone_lines: list[str] = []
    for z in plan["target_zones"]:
        matching_types = [t for t in (z.get("problem_types") or []) if t in relevant_types]
        if not matching_types:
            continue

        zone_en = _ZONE_EN.get(z["sub_area"], z["sub_area"])
        sev = z.get("severity_level", "mild")
        adjective, pct = _SEVERITY_INTENSITY.get(sev, ("subtle", "~20%"))
        sev_label = sev.replace("_", "-")

        effects = [_PROBLEM_EFFECT_EN[t] for t in matching_types if t in _PROBLEM_EFFECT_EN]
        if not effects:
            continue
        effects_str = "; ".join(effects)

        zone_lines.append(
            f"- {zone_en} ({sev_label} {'+'.join(matching_types)}): "
            f"{adjective} ({pct}) — {effects_str}"
        )

    if not zone_lines:
        return ""

    return (
        "Preserve the subject's exact identity, facial structure, proportions, "
        "lighting, and natural pores. Realistic clinical dermatology "
        "post-treatment simulation. Maintain authentic micro-skin texture with "
        "genuine skin grain and zero plastic airbrushing or over-smoothing. "
        "Keep skin tone completely calm, neutral, and balanced with zero "
        "artificial facial redness or inflammation. Strictly preserve "
        "anatomical fidelity: do not hallucinate new fine lines, do not "
        "exaggerate existing wrinkles, and do not exacerbate original facial "
        "flaws. Subtle, realistic clinical refinement only, raw unedited "
        "photography style.\n\n"
        "Apply the following zone-specific improvements only:\n"
        + "\n".join(zone_lines)
        + "\n\nCritical: this is a medical treatment result, NOT a beauty filter. "
        "Do NOT smooth or airbrush the skin. Do NOT apply beauty filter effects. "
        "Do NOT add any text, watermark, label, or annotation."
    )


def _resize_source(raw: bytes, max_edge: int = 1024) -> bytes:
    """image-edit prefers 1024ish, not 768 (needs detail to preserve identity)."""
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > max_edge:
        scale = max_edge / long_edge
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def _edit_image_sync(image_bytes: bytes, instruction: str) -> tuple[bytes | None, dict]:
    """Sync call to qwen-image-edit — meant to be run via asyncio.to_thread."""
    import dashscope
    from dashscope import MultiModalConversation
    import urllib.request

    api_key = get_settings().dashscope_api_key
    if not api_key:
        return None, {"error": "DASHSCOPE_API_KEY not configured", "latency_sec": 0.0}
    dashscope.api_key = api_key

    resized = _resize_source(image_bytes)
    b64 = base64.b64encode(resized).decode("ascii")
    image_arg = f"data:image/jpeg;base64,{b64}"

    start = time.time()
    try:
        resp = MultiModalConversation.call(
            api_key=api_key,
            model=_IMAGE_EDIT_MODEL,
            messages=[{
                "role": "user",
                "content": [{"image": image_arg}, {"text": instruction}],
            }],
        )
    except Exception as exc:
        return None, {"error": str(exc), "latency_sec": time.time() - start}
    latency = time.time() - start

    if resp.status_code != 200:
        return None, {
            "error": f"status={resp.status_code} code={resp.code} msg={resp.message}",
            "latency_sec": latency,
        }

    try:
        content = resp.output.choices[0].message.content
        image_url = None
        for item in content if isinstance(content, list) else [content]:
            if isinstance(item, dict) and "image" in item:
                image_url = item["image"]
                break
        if not image_url:
            return None, {"error": "no image field in response", "latency_sec": latency}
    except Exception as exc:
        return None, {"error": f"unexpected response shape: {exc}", "latency_sec": latency}

    try:
        with urllib.request.urlopen(image_url, timeout=60) as r:
            img_bytes = r.read()
    except Exception as exc:
        return None, {"error": f"download failed: {exc}", "latency_sec": latency}

    usage = getattr(resp, "usage", None)
    usage_dict = dict(usage) if usage and hasattr(usage, "__iter__") else {}
    return img_bytes, {"latency_sec": latency, "usage": usage_dict, "image_url": image_url}


async def generate_preview_from_bytes(
    image_bytes: bytes, diagnosis: dict
) -> list[dict[str, Any]]:
    """Generate skin-plan post-op preview. Returns [{id, title, target_zones,
    problem_summary, instruction, after_image_base64, latency_sec, status}].
    Empty list if no plan applicable.
    """
    plans = build_plans(diagnosis)
    results: list[dict[str, Any]] = []
    for plan in plans:
        if plan["id"] != "skin":
            continue
        instruction = build_edit_instruction(plan)
        if not instruction:
            continue

        logger.info("treatment_preview: calling qwen-image-edit for plan=%s", plan["id"])
        img_bytes, meta = await asyncio.to_thread(_edit_image_sync, image_bytes, instruction)

        entry: dict[str, Any] = {
            "id": plan["id"],
            "title": plan["title"],
            "target_zones": [z["sub_area"] for z in plan["target_zones"]],
            "problem_summary": plan["problem_summary"],
            "instruction": instruction,
            "latency_sec": meta.get("latency_sec", 0.0),
        }
        if img_bytes is None:
            entry["status"] = "failed"
            entry["error"] = meta.get("error", "unknown")
            entry["after_image_base64"] = ""
            logger.warning("treatment_preview: %s failed: %s", plan["id"], entry["error"])
        else:
            entry["status"] = "ok"
            entry["after_image_base64"] = base64.b64encode(img_bytes).decode("ascii")
            logger.info(
                "treatment_preview: %s ok in %.1fs",
                plan["id"], entry["latency_sec"],
            )
        results.append(entry)
    return results
