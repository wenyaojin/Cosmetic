-- GIN index on doc_chunks.tokens for BM25 full-text search
-- tokens column stores jieba-segmented text (space-separated)
-- 'simple' config treats each space-separated token as a lexeme
CREATE INDEX IF NOT EXISTS idx_doc_chunks_fts
    ON doc_chunks
    USING GIN (to_tsvector('simple', tokens));
