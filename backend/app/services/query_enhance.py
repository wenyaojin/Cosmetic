"""
Query-side enhancements for RAG.

Two techniques attack distinct semantic gaps between user query and indexed docs:

1. **Query Rewriting** — close the lexical gap between colloquial user wording
   and professional medical terminology. We ask the LLM to generate N
   paraphrased queries using domain terms (e.g. 「鼻子塌」→「鼻基底凹陷」).

2. **HyDE (Hypothetical Document Embeddings)** — close the syntactic gap
   between an interrogative query and declarative source docs. We let the LLM
   draft a hypothetical answer; that draft, not the original question, is what
   we embed for vector search. The draft may be factually wrong; what matters
   is that its surface form matches real documents.

Both produce a list of `EnhancedQuery` items. Down-stream retrievers iterate
over them and fuse the results via RRF.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings
from app.core.llm import get_llm_client
from app.core.logging import get_logger

logger = get_logger("query_enhance")

EnhanceKind = Literal["original", "rewrite", "hyde"]


@dataclass
class EnhancedQuery:
    """A single query variant fed into the retriever."""

    text: str
    kind: EnhanceKind
    # Weight used in RRF fusion; rewrites and HyDE drafts each get slightly
    # less weight than the original so that obvious matches still dominate.
    weight: float = 1.0


_REWRITE_SYSTEM_PROMPT = (
    "你是医美领域检索助手。给定一个用户问题，请改写出 {n} 个**专业化、术语化**的检索查询，"
    "用于在医美知识库中召回相关文档。要求：\n"
    "- 把口语表达替换为医学术语（例如「鼻子塌」→「鼻基底凹陷 / 鼻背低平」）。\n"
    "- 覆盖不同角度（项目名、解剖结构、相关并发症、适应症等）。\n"
    "- 每条查询独立，不要套用「关于…」「请问…」之类的语气词。\n"
    "- 只输出 JSON 数组，例如 [\"query1\", \"query2\", ...]，不要任何额外说明。"
)


_HYDE_SYSTEM_PROMPT = (
    "你是医美专家。请针对用户的问题，给出一段简洁、专业的**假设性答案**（150 字以内）。"
    "不要使用问句；用陈述句、术语化、风格接近教科书或临床指南。"
    "你不需要保证事实完全正确——这段文字仅用于向量检索的语义匹配。"
    "直接输出答案，不要加任何前缀。"
)


def _safe_json_array(raw: str) -> list[str]:
    """Best-effort parse of a JSON array; tolerates code fences / stray text."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in parsed if str(x).strip()]


async def rewrite_query(query: str, n: int | None = None, *, trace=None) -> list[str]:
    settings = get_settings()
    n = n or settings.query_rewrite_n
    if n <= 0:
        return []

    llm = get_llm_client()
    messages = [
        {"role": "system", "content": _REWRITE_SYSTEM_PROMPT.format(n=n)},
        {"role": "user", "content": query},
    ]
    raw = await llm.chat(
        messages,
        temperature=0.4,
        max_tokens=512,
        trace=trace,
        generation_name="query_rewrite",
    )
    rewrites = _safe_json_array(raw)
    # Deduplicate vs. original (case-sensitive is fine for Chinese).
    rewrites = [r for r in rewrites if r and r != query]
    return rewrites[:n]


async def hyde_draft(query: str, *, trace=None) -> str | None:
    llm = get_llm_client()
    messages = [
        {"role": "system", "content": _HYDE_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    draft = await llm.chat(
        messages,
        temperature=0.3,
        max_tokens=256,
        trace=trace,
        generation_name="hyde_draft",
    )
    draft = draft.strip()
    return draft or None


async def enhance_query(
    query: str,
    *,
    use_rewrite: bool | None = None,
    use_hyde: bool | None = None,
    trace=None,
) -> list[EnhancedQuery]:
    """
    Produce the full list of query variants for downstream retrieval.

    The original query is always included with weight 1.0 so that we never
    do worse than vanilla RAG even if both enhancements misfire.
    """
    settings = get_settings()
    use_rewrite = settings.use_query_rewrite if use_rewrite is None else use_rewrite
    use_hyde = settings.use_hyde if use_hyde is None else use_hyde

    variants: list[EnhancedQuery] = [EnhancedQuery(text=query, kind="original", weight=1.0)]

    if use_rewrite:
        try:
            rewrites = await rewrite_query(query, trace=trace)
            variants.extend(EnhancedQuery(r, "rewrite", 0.8) for r in rewrites)
            logger.info("Query rewrite: %d variants", len(rewrites))
        except Exception as e:
            logger.warning("Query rewrite failed, skipping: %s", e)

    if use_hyde:
        try:
            draft = await hyde_draft(query, trace=trace)
            if draft:
                variants.append(EnhancedQuery(draft, "hyde", 0.7))
                logger.info("HyDE draft: %d chars", len(draft))
        except Exception as e:
            logger.warning("HyDE draft failed, skipping: %s", e)

    return variants
