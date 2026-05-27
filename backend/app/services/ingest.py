"""
Document ingestion with small-to-big (parent-child) chunking.

Motivation: vanilla one-size chunking is a compromise — small chunks have
sharp embeddings but lack context for the LLM, large chunks give the LLM
context but get diluted in vector search. Small-to-big resolves the tension:

  • **Child chunks** (~256 tokens) carry the embeddings used for retrieval.
  • **Parent chunks** (~1500 tokens) are what we hand to the LLM as context.

At query time we retrieve child chunks, then expand each hit to its parent
before deduplicating and sending to the model.

This module replaces the previous `ingest_document` in `services/rag.py`
(kept there for backward compat). New ingestion paths should call
`ingest_document_small_to_big` and the seed/batch scripts will be migrated
incrementally.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.embedding import get_embedding_client
from app.core.logging import get_logger
from app.core.tokenizer import tokenize_for_index
from app.models.document import Document, DocChunk

logger = get_logger("ingest")


def _split_by_size(content: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Paragraph-aware splitter. Same algorithm as the legacy `split_text` in
    rag.py but parameterised so we can use it for both parent and child layers.
    """
    if not content.strip():
        return []

    chunks: list[str] = []
    current = ""
    for para in content.split("\n\n"):
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n{para}" if current else para
            continue

        if current:
            chunks.append(current)

        if len(para) > chunk_size:
            buf = para
            while len(buf) > chunk_size:
                chunks.append(buf[:chunk_size])
                buf = buf[chunk_size - overlap :]
            current = buf
        else:
            current = para

    if current:
        chunks.append(current)
    return chunks


def _split_parent_into_children(
    parent_text: str, child_size: int, child_overlap: int
) -> list[str]:
    """Children inherit the parent's natural paragraph structure where possible."""
    children = _split_by_size(parent_text, child_size, child_overlap)
    # Guarantee at least one child per parent so retrieval can always reach it.
    return children or [parent_text[:child_size]]


async def ingest_document_small_to_big(
    db: AsyncSession,
    title: str,
    content: str,
    source: str = "",
    category: str = "general",
    authority_level: int = 4,
    published_at: date | None = None,
    metadata: dict | None = None,
) -> uuid.UUID:
    """
    Ingest one document with two-layer chunking.

    Schema usage:
      • Parent rows: is_parent=True, parent_id=NULL, embedding=NULL
        (we never search them directly; they exist purely to provide context).
      • Child rows: is_parent=False, parent_id=<parent.id>, embedding=<vec>.
    """
    settings = get_settings()

    doc = Document(
        title=title,
        source=source,
        category=category,
        authority_level=authority_level,
        published_at=published_at,
        raw_content=content,
        metadata_=metadata or {},
    )
    db.add(doc)
    await db.flush()

    parents = _split_by_size(content, settings.parent_chunk_size, settings.parent_chunk_overlap)
    if not parents:
        await db.commit()
        return doc.id

    emb_client = get_embedding_client()

    # Collect every child upfront so we can batch-embed once.
    child_records: list[tuple[uuid.UUID, str, int]] = []  # (parent_id, text, child_index)
    global_child_idx = 0

    for p_idx, parent_text in enumerate(parents):
        parent_row = DocChunk(
            doc_id=doc.id,
            chunk_text=parent_text,
            chunk_index=p_idx,
            embedding=None,
            tokens="",
            parent_id=None,
            is_parent=True,
        )
        db.add(parent_row)
        await db.flush()  # need parent_row.id for children

        children = _split_parent_into_children(
            parent_text, settings.child_chunk_size, settings.child_chunk_overlap
        )
        for child_text in children:
            child_records.append((parent_row.id, child_text, global_child_idx))
            global_child_idx += 1

    if not child_records:
        await db.commit()
        return doc.id

    child_texts = [c[1] for c in child_records]
    embeddings = await emb_client.embed_batch(child_texts)

    for (parent_id, text, idx), emb in zip(child_records, embeddings):
        db.add(
            DocChunk(
                doc_id=doc.id,
                chunk_text=text,
                chunk_index=idx,
                embedding=emb,
                tokens=tokenize_for_index(text),
                parent_id=parent_id,
                is_parent=False,
            )
        )

    await db.commit()
    logger.info(
        "Ingested '%s' → %d parents / %d children",
        title,
        len(parents),
        len(child_records),
    )
    return doc.id
