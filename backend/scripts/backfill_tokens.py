"""Backfill tokens column for existing doc_chunks using jieba segmentation."""

import asyncio
from sqlalchemy import select, update
from app.core.database import get_session_factory, get_engine
from app.core.tokenizer import tokenize_for_index
from app.models.document import DocChunk
from app.core.logging import get_logger

logger = get_logger("backfill_tokens")


async def main():
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(DocChunk).where(
                (DocChunk.tokens == None) | (DocChunk.tokens == "")
            )
        )
        chunks = result.scalars().all()
        logger.info("Found %d chunks to backfill", len(chunks))

        for chunk in chunks:
            chunk.tokens = tokenize_for_index(chunk.chunk_text)

        await db.commit()
        logger.info("Backfill complete: %d chunks updated", len(chunks))


if __name__ == "__main__":
    asyncio.run(main())
