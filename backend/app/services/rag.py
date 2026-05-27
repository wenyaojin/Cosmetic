import uuid
import math
from datetime import date
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from rank_bm25 import BM25Okapi
from app.models.document import Document, DocChunk
from app.core.config import get_settings
from app.core.embedding import get_embedding_client
from app.core.reranker import get_reranker_client
from app.core.tokenizer import tokenize, tokenize_for_index
from app.core.logging import get_logger
from app.services.query_enhance import EnhancedQuery, enhance_query
from app.services.ingest import ingest_document_small_to_big

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
    published_at: date | None = None,
    metadata: dict | None = None,
) -> uuid.UUID:
    """
    Public ingestion entry point. Routes to small-to-big when enabled, otherwise
    falls back to the legacy single-layer pipeline. Kept here so existing seed /
    batch scripts in `scripts/` keep working without edits.
    """
    settings = get_settings()
    if settings.use_small_to_big:
        return await ingest_document_small_to_big(
            db,
            title=title,
            content=content,
            source=source,
            category=category,
            authority_level=authority_level,
            published_at=published_at,
            metadata=metadata,
        )
    return await _ingest_document_flat(
        db,
        title=title,
        content=content,
        source=source,
        category=category,
        authority_level=authority_level,
        published_at=published_at,
        metadata=metadata,
    )


async def _ingest_document_flat(
    db: AsyncSession,
    title: str,
    content: str,
    source: str,
    category: str,
    authority_level: int,
    published_at: date | None,
    metadata: dict | None,
) -> uuid.UUID:
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
            parent_id=None,
            is_parent=False,
        )
        db.add(chunk)

    await db.commit()
    logger.info("Ingested (flat) doc '%s' → %d chunks", title, len(chunks))
    return doc.id


async def search_vector(
    db: AsyncSession,
    query: str,
    top_k: int = 20,
    category: str | None = None,
) -> list[dict]:
    """
    Vector search over **child** (or flat) chunks only — parent chunks are
    contextual and intentionally not searchable.
    """
    emb_client = get_embedding_client()
    query_emb = await emb_client.embed(query)
    emb_literal = "[" + ",".join(str(x) for x in query_emb) + "]"

    sql = """
        SELECT
            c.id, c.doc_id, c.chunk_text, c.chunk_index, c.parent_id,
            d.title, d.source, d.category, d.authority_level, d.metadata AS doc_metadata,
            c.embedding <=> :emb AS distance
        FROM doc_chunks c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.is_parent = FALSE AND c.embedding IS NOT NULL
    """
    if category:
        sql += " AND d.category = :category"
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
            "parent_id": str(row.parent_id) if row.parent_id else None,
            "text": row.chunk_text,
            "title": row.title,
            "source": row.source,
            "category": row.category,
            "authority_level": row.authority_level,
            "metadata": row.doc_metadata or {},
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
            c.id, c.doc_id, c.chunk_text, c.chunk_index, c.tokens, c.parent_id,
            d.title, d.source, d.category, d.authority_level, d.metadata AS doc_metadata
        FROM doc_chunks c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.is_parent = FALSE
          AND to_tsvector('simple', c.tokens) @@ to_tsquery('simple', :tsquery)
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
            "parent_id": str(row.parent_id) if row.parent_id else None,
            "text": row.chunk_text,
            "title": row.title,
            "source": row.source,
            "category": row.category,
            "authority_level": row.authority_level,
            "metadata": row.doc_metadata or {},
            "bm25_score": float(score),
        }
        for row, score in scored_rows
        if score > 0
    ]


def rrf_fuse(
    *result_lists: list[dict],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[dict]:
    """
    Variadic RRF fusion. Each list contributes 1 / (k + rank) * weight to the
    score of every chunk it contains. Order within each list defines rank.
    """
    if weights is None:
        weights = [1.0] * len(result_lists)
    assert len(weights) == len(result_lists)

    scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for w, results in zip(weights, result_lists):
        for rank, doc in enumerate(results):
            cid = doc["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
            doc_map[cid] = doc

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [{**doc_map[cid], "rrf_score": scores[cid]} for cid in sorted_ids]


async def _expand_to_parents(
    db: AsyncSession, child_hits: list[dict]
) -> list[dict]:
    """
    Replace each child hit with its parent chunk text (if any), preserving the
    retrieval score so downstream rerank can still order by relevance.

    Children sharing a parent collapse into a single entry, keeping the best
    score. Children without a parent (legacy flat chunks) pass through.
    """
    if not child_hits:
        return []

    parent_ids = {h["parent_id"] for h in child_hits if h.get("parent_id")}
    parent_map: dict[str, dict] = {}

    if parent_ids:
        sql = """
            SELECT
                c.id, c.doc_id, c.chunk_text, c.chunk_index,
                d.title, d.source, d.category, d.authority_level, d.metadata AS doc_metadata
            FROM doc_chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.id = ANY(:ids) AND c.is_parent = TRUE
        """
        result = await db.execute(text(sql), {"ids": list(parent_ids)})
        for row in result.fetchall():
            parent_map[str(row.id)] = {
                "chunk_id": str(row.id),
                "doc_id": str(row.doc_id),
                "text": row.chunk_text,
                "title": row.title,
                "source": row.source,
                "category": row.category,
                "authority_level": row.authority_level,
                "metadata": row.doc_metadata or {},
            }

    expanded: dict[str, dict] = {}
    for hit in child_hits:
        pid = hit.get("parent_id")
        if pid and pid in parent_map:
            key = pid
            parent = parent_map[pid]
        else:
            key = hit["chunk_id"]
            parent = {k: hit[k] for k in (
                "chunk_id", "doc_id", "text", "title", "source",
                "category", "authority_level", "metadata",
            )}

        prev = expanded.get(key)
        score = hit.get("rrf_score", hit.get("rerank_score", -hit.get("distance", 0.0)))
        if prev is None or score > prev["_score"]:
            expanded[key] = {**parent, "_score": score, "child_chunk_id": hit["chunk_id"]}

    return sorted(expanded.values(), key=lambda x: x["_score"], reverse=True)


async def search_hybrid(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
    use_rerank: bool = True,
) -> list[dict]:
    """
    Single-query hybrid retrieval. Kept as a public API for callers that
    explicitly do **not** want enhancements (e.g., ablation runs, eval
    harnesses). The agent path should use `search_enhanced` instead.
    """
    settings = get_settings()
    retrieve_k = max(top_k * 4, 20)

    vector_results = await search_vector(db, query, top_k=retrieve_k, category=category)
    bm25_results = await search_bm25(db, query, top_k=retrieve_k, category=category)

    logger.info("Vector: %d hits, BM25: %d hits", len(vector_results), len(bm25_results))

    fused = rrf_fuse(vector_results, bm25_results)
    if not fused:
        return []

    candidates = fused[: top_k * 3]

    if settings.use_small_to_big:
        candidates = await _expand_to_parents(db, candidates)

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
            logger.info("Reranked %d -> %d results", len(candidates), len(reranked))
            return reranked
        except Exception as e:
            logger.warning("Rerank failed, falling back to RRF order: %s", e)

    return candidates[:top_k]


async def search_enhanced(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
    use_rerank: bool = True,
    *,
    trace=None,
) -> list[dict]:
    """
    End-to-end enhanced retrieval.

      1.  Expand the user query into N variants (original + rewrites + HyDE).
      2.  Run hybrid (vector + BM25) over each variant.
      3.  Fuse all 2N result lists via weighted RRF.
      4.  Expand child hits to parent chunks (small-to-big).
      5.  Optional cross-encoder rerank against the **original** query
          (the rewrites were only used to widen recall, not to redefine
          what the user actually asked).
    """
    settings = get_settings()
    if not (settings.use_query_rewrite or settings.use_hyde):
        return await search_hybrid(db, query, top_k=top_k, category=category, use_rerank=use_rerank)

    variants: list[EnhancedQuery] = await enhance_query(query, trace=trace)
    retrieve_k = max(top_k * 4, 20)

    all_lists: list[list[dict]] = []
    weights: list[float] = []

    for v in variants:
        vec = await search_vector(db, v.text, top_k=retrieve_k, category=category)
        bm = await search_bm25(db, v.text, top_k=retrieve_k, category=category)
        all_lists.extend([vec, bm])
        weights.extend([v.weight, v.weight])

    fused = rrf_fuse(*all_lists, weights=weights)
    if not fused:
        return []

    candidates = fused[: top_k * 4]

    if settings.use_small_to_big:
        candidates = await _expand_to_parents(db, candidates)

    if use_rerank and len(candidates) > 1:
        reranker = get_reranker_client()
        try:
            # Rerank against the **original** query — the rewrites were a
            # recall device, not a redefinition of intent.
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
            logger.info(
                "Enhanced retrieval: %d variants → %d candidates → %d reranked",
                len(variants), len(candidates), len(reranked),
            )
            return reranked
        except Exception as e:
            logger.warning("Rerank failed, falling back to fused order: %s", e)

    return candidates[:top_k]


async def search_similar(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> list[dict]:
    return await search_hybrid(db, query, top_k=top_k, category=category)
