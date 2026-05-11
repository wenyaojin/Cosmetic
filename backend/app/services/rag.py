import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document, DocChunk
from app.core.embedding import get_embedding_client
from app.core.logging import get_logger

logger = get_logger("rag")

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


def split_text(content: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    if not content.strip():
        return []
    chunks = []
    paragraphs = content.split("\n\n")
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) > chunk_size:
                words = para
                while len(words) > chunk_size:
                    chunks.append(words[:chunk_size])
                    words = words[chunk_size - overlap:]
                current = words
            else:
                current = para
    if current:
        chunks.append(current)
    return chunks


async def ingest_document(
    db: AsyncSession,
    title: str,
    content: str,
    source: str = "",
    category: str = "general",
    authority_level: int = 4,
) -> uuid.UUID:
    doc = Document(
        title=title,
        source=source,
        category=category,
        authority_level=authority_level,
        raw_content=content,
    )
    db.add(doc)
    await db.flush()

    chunks = split_text(content)
    if not chunks:
        await db.commit()
        return doc.id

    emb_client = get_embedding_client()
    embeddings = await emb_client.embed_batch(chunks)

    for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
        chunk = DocChunk(
            doc_id=doc.id,
            chunk_text=chunk_text,
            chunk_index=i,
            embedding=emb,
        )
        db.add(chunk)

    await db.commit()
    logger.info("Ingested doc '%s' → %d chunks", title, len(chunks))
    return doc.id


async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    emb_client = get_embedding_client()
    query_emb = await emb_client.embed(query)

    emb_literal = "[" + ",".join(str(x) for x in query_emb) + "]"

    sql = """
        SELECT
            c.id, c.doc_id, c.chunk_text, c.chunk_index,
            d.title, d.source, d.category, d.authority_level,
            c.embedding <=> :emb AS distance
        FROM doc_chunks c
        JOIN documents d ON d.id = c.doc_id
    """
    if category:
        sql += " WHERE d.category = :category"
    sql += " ORDER BY distance ASC LIMIT :top_k"

    params = {"emb": emb_literal, "top_k": top_k}
    if category:
        params["category"] = category

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        {
            "chunk_id": str(row.id),
            "doc_id": str(row.doc_id),
            "text": row.chunk_text,
            "title": row.title,
            "source": row.source,
            "category": row.category,
            "authority_level": row.authority_level,
            "distance": float(row.distance),
        }
        for row in rows
    ]
