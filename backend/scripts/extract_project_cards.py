"""
Batch-extract structured project cards from already-ingested documents.

Usage:
    uv run python -m scripts.extract_project_cards
    uv run python -m scripts.extract_project_cards --category 注射填充
    uv run python -m scripts.extract_project_cards --limit 5

Groups documents by `category`, joins their raw text, asks the LLM to extract
one ProjectCard per category. For richer KBs you may later switch to a
title-based grouping or pass an explicit project list.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.models.document import Document
from app.services.structured_kb import (
    extract_project_card_from_text,
    upsert_project_card,
)

logger = get_logger("scripts.extract_project_cards")

MAX_TEXT_CHARS = 12000  # keep extractor prompt under context window


async def run(category_filter: str | None, limit: int | None) -> None:
    factory = get_session_factory()
    async with factory() as db:
        q = select(Document)
        if category_filter:
            q = q.where(Document.category == category_filter)
        docs = list((await db.scalars(q)).all())

    if not docs:
        logger.warning("No documents found for category=%s", category_filter)
        return

    grouped: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        grouped[d.category].append(d)

    logger.info("Loaded %d docs in %d categories", len(docs), len(grouped))

    processed = 0
    for cat, ds in grouped.items():
        if limit is not None and processed >= limit:
            break

        combined = "\n\n---\n\n".join(
            f"# {d.title}\n{d.raw_content}" for d in ds if d.raw_content
        )
        if len(combined) > MAX_TEXT_CHARS:
            combined = combined[:MAX_TEXT_CHARS]

        source_ids = [str(d.id) for d in ds]
        logger.info("Extracting card for category=%s from %d docs", cat, len(ds))

        try:
            card = await extract_project_card_from_text(combined, source_doc_ids=source_ids)
        except Exception as e:
            logger.exception("Extraction failed for category=%s: %s", cat, e)
            continue

        if not card:
            logger.warning("Empty extraction for category=%s", cat)
            continue

        async with factory() as db:
            row = await upsert_project_card(db, card)
        logger.info("Upserted card '%s' (id=%s)", row.name, row.id)
        processed += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None, help="Only extract from this category")
    parser.add_argument("--limit", type=int, default=None, help="Max number of cards to write")
    args = parser.parse_args()
    asyncio.run(run(args.category, args.limit))


if __name__ == "__main__":
    main()
