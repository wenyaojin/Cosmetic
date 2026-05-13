import uuid
import math
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from rank_bm25 import BM25Okapi
from app.models.document import Document, DocChunk
from app.core.embedding import get_embedding_client
from app.core.reranker import get_reranker_client
from app.core.tokenizer import tokenize, tokenize_for_index
from app.core.logging import get_logger

logger = get_logger("rag")

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
RRF_K = 60


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
        tokenized = tokenize_for_index(chunk_text)
        chunk = DocChunk(
            doc_id=doc.id,
            chunk_text=chunk_text,
            chunk_index=i,
            embedding=emb,
            tokens=tokenized,
        )
        db.add(chunk)

    await db.commit()
    logger.info("Ingested doc '%s' → %d chunks", title, len(chunks))
    return doc.id


async def search_vector(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
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

    params: dict = {"emb": emb_literal, "top_k": top_k}
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


async def search_bm25(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    category: str | None = None,
) -> list[dict]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    tsquery_str = " | ".join(query_tokens)

    sql = """
        SELECT
            c.id, c.doc_id, c.chunk_text, c.chunk_index, c.tokens,
            d.title, d.source, d.category, d.authority_level
        FROM doc_chunks c
        JOIN documents d ON d.id = c.doc_id
        WHERE to_tsvector('simple', c.tokens) @@ to_tsquery('simple', :tsquery)
    """
    if category:
        sql += " AND d.category = :category"
    sql += " LIMIT :limit"

    params: dict = {"tsquery": tsquery_str, "limit": top_k * 5}
    if category:
        params["category"] = category

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    if not rows:
        return []

    corpus = [row.tokens.split() for row in rows]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query_tokens)

    scored_rows = sorted(
        zip(rows, scores), key=lambda x: x[1], reverse=True
    )[:top_k]

    return [
        {
            "chunk_id": str(row.id),
            "doc_id": str(row.doc_id),
            "text": row.chunk_text,
            "title": row.title,
            "source": row.source,
            "category": row.category,
            "authority_level": row.authority_level,
            "bm25_score": float(score),
        }
        for row, score in scored_rows
        if score > 0
    ]


def rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, doc in enumerate(vector_results):
        cid = doc["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        doc_map[cid] = doc

    for rank, doc in enumerate(bm25_results):
        cid = doc["chunk_id"]
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
        doc_map[cid] = doc

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [
        {**doc_map[cid], "rrf_score": scores[cid]}
        for cid in sorted_ids
    ]


async def search_hybrid(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
    use_rerank: bool = True,
) -> list[dict]:
    retrieve_k = max(top_k * 4, 20)

    vector_results = await search_vector(db, query, top_k=retrieve_k, category=category)
    bm25_results = await search_bm25(db, query, top_k=retrieve_k, category=category)

    logger.info("Vector: %d hits, BM25: %d hits", len(vector_results), len(bm25_results))

    fused = rrf_fuse(vector_results, bm25_results)

    if not fused:
        return []

    candidates = fused[: top_k * 3]

    if use_rerank and len(candidates) > 1:
        reranker = get_reranker_client()
        try:
            rerank_results = await reranker.rerank(
                query=query,
                documents=[c["text"] for c in candidates],
                top_n=top_k,
            )
            reranked = []
            for r in rerank_results:
                idx = r["index"]
                if idx < len(candidates):
                    item = candidates[idx].copy()
                    item["rerank_score"] = r["relevance_score"]
                    reranked.append(item)
            logger.info("Reranked %d → %d results", len(candidates), len(reranked))
            return reranked
        except Exception as e:
            logger.warning("Rerank failed, falling back to RRF order: %s", e)

    return candidates[:top_k]


async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    return await search_hybrid(db, query, top_k=top_k, category=category)
