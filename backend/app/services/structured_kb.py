"""
Structured knowledge base of project cards.

Why: factual queries ("how much does Restylane cost", "can pregnant women get
botox") are exactly where RAG hurts most — multiple source docs disagree, the
LLM picks one at random, hallucinations are common. Storing facts in a typed
table and answering factual intents from SQL bypasses the probabilistic
pipeline entirely.

This module provides two surfaces:

  • `extract_project_card_from_text(text)` — offline LLM extraction that turns
    one or more knowledge documents into a `ProjectCard` row. Runs during
    ingestion or batch-rebuilds.

  • `lookup_project_card(db, query)` / `find_relevant_cards(db, query)` —
    online lookups used by the agent. The recommend / risk-assessment nodes
    call these to fetch hard facts before generation.
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm_client
from app.core.logging import get_logger
from app.models.project_card import ProjectCard

logger = get_logger("structured_kb")


_EXTRACT_SYSTEM_PROMPT = (
    "你是医美知识结构化抽取器。给定一段或多段关于某个**医美项目**的资料，"
    "请抽取关键字段并输出 JSON。\n"
    "字段规范：\n"
    "  name              字符串，项目标准名（例如「玻尿酸填充」）。\n"
    "  aliases           字符串数组，别名/品牌名/英文名。\n"
    "  category          字符串，分类（注射填充 / 光电美肤 / 紧致抗衰 / 身体塑形 / 皮肤管理 / 其他）。\n"
    "  indications       字符串数组，适应症。\n"
    "  contraindications 字符串数组，禁忌症。\n"
    "  complications     对象数组，每项 {name, severity(轻/中/重/极重), rate(浮点数, 缺失填 null)}。\n"
    "  duration_months   [min, max] 整数；如不适用或未知，填 null。\n"
    "  price_rmb         [min, max] 整数；如不适用或未知，填 null。\n"
    "  recovery_days     字符串，例如「3-7 天」「无恢复期」；未知填 null。\n"
    "  description       100 字以内的中性描述。\n"
    "原文中没有的字段一律输出 null 或空数组，**禁止编造**。"
    "只输出 JSON 对象，不要任何额外说明。"
)


def _safe_json_object(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _coerce_int_pair(value) -> tuple[int | None, int | None]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None, None
    lo, hi = value
    try:
        return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)
    except (TypeError, ValueError):
        return None, None


async def extract_project_card_from_text(
    text: str, *, source_doc_ids: Iterable[str] = (), trace=None
) -> dict | None:
    """Run the LLM extractor and return a dict ready to pass to `upsert_project_card`."""
    llm = get_llm_client()
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    raw = await llm.chat(
        messages,
        temperature=0.1,
        max_tokens=1024,
        trace=trace,
        generation_name="card_extract",
    )
    obj = _safe_json_object(raw)
    if not obj or not obj.get("name"):
        logger.warning("Extractor returned no usable card")
        return None

    dur_min, dur_max = _coerce_int_pair(obj.get("duration_months"))
    price_min, price_max = _coerce_int_pair(obj.get("price_rmb"))

    return {
        "name": str(obj["name"]).strip(),
        "aliases": [str(a).strip() for a in obj.get("aliases") or [] if str(a).strip()],
        "category": str(obj.get("category") or "general").strip(),
        "indications": [str(x).strip() for x in obj.get("indications") or [] if str(x).strip()],
        "contraindications": [
            str(x).strip() for x in obj.get("contraindications") or [] if str(x).strip()
        ],
        "complications": obj.get("complications") or [],
        "duration_months_min": dur_min,
        "duration_months_max": dur_max,
        "price_rmb_min": price_min,
        "price_rmb_max": price_max,
        "recovery_days": obj.get("recovery_days"),
        "description": (obj.get("description") or "").strip(),
        "source_doc_ids": [str(d) for d in source_doc_ids],
    }


async def upsert_project_card(db: AsyncSession, card: dict) -> ProjectCard:
    """Insert a new card, or merge into an existing one matched by name."""
    existing = await db.scalar(select(ProjectCard).where(ProjectCard.name == card["name"]))

    if existing is None:
        row = ProjectCard(**card)
        db.add(row)
        await db.commit()
        return row

    for k, v in card.items():
        if v in (None, [], ""):  # don't overwrite with empties
            continue
        if k in ("aliases", "indications", "contraindications", "source_doc_ids"):
            merged = list({*(getattr(existing, k) or []), *v})
            setattr(existing, k, merged)
        else:
            setattr(existing, k, v)
    await db.commit()
    return existing


async def lookup_project_card(db: AsyncSession, name_or_alias: str) -> ProjectCard | None:
    """Exact-or-alias lookup. Used when the agent has already identified a project."""
    q = (
        select(ProjectCard)
        .where(
            or_(
                ProjectCard.name == name_or_alias,
                ProjectCard.aliases.any(name_or_alias),
            )
        )
        .limit(1)
    )
    return await db.scalar(q)


async def find_relevant_cards(
    db: AsyncSession, query: str, *, limit: int = 5
) -> list[ProjectCard]:
    """
    Fuzzy matcher used during agent's recommend step. Pure SQL ILIKE — fast,
    deterministic, and good enough for short Chinese tokens. If we ever need
    semantic project matching we can swap in pgvector against card embeddings.
    """
    pattern = f"%{query}%"
    q = (
        select(ProjectCard)
        .where(
            or_(
                ProjectCard.name.ilike(pattern),
                ProjectCard.description.ilike(pattern),
                ProjectCard.aliases.any(query),
                ProjectCard.indications.any(query),
            )
        )
        .limit(limit)
    )
    return list((await db.scalars(q)).all())


def card_to_context(card: ProjectCard) -> str:
    """Render a card into a deterministic, citation-friendly block for prompts."""
    lines = [f"【项目】{card.name}"]
    if card.aliases:
        lines.append(f"别名：{', '.join(card.aliases)}")
    if card.category:
        lines.append(f"分类：{card.category}")
    if card.indications:
        lines.append(f"适应症：{', '.join(card.indications)}")
    if card.contraindications:
        lines.append(f"禁忌症：{', '.join(card.contraindications)}")
    if card.duration_months_min is not None and card.duration_months_max is not None:
        lines.append(f"维持时间：{card.duration_months_min}-{card.duration_months_max} 个月")
    if card.price_rmb_min is not None and card.price_rmb_max is not None:
        lines.append(f"价格区间：{card.price_rmb_min}-{card.price_rmb_max} 元（仅供参考）")
    if card.recovery_days:
        lines.append(f"恢复期：{card.recovery_days}")
    if card.complications:
        comp_strs = []
        for c in card.complications:
            if isinstance(c, dict) and c.get("name"):
                sev = c.get("severity") or ""
                comp_strs.append(f"{c['name']}({sev})" if sev else c["name"])
        if comp_strs:
            lines.append(f"常见并发症：{', '.join(comp_strs)}")
    if card.description:
        lines.append(f"说明：{card.description}")
    return "\n".join(lines)
