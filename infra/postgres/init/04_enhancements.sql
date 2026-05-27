-- Migration: small-to-big chunking + structured project cards.
-- Idempotent — safe to run on a fresh DB or an existing one.

-- 1) doc_chunks: add parent linkage and a flag distinguishing parent rows.
ALTER TABLE doc_chunks
    ADD COLUMN IF NOT EXISTS parent_id UUID NULL,
    ADD COLUMN IF NOT EXISTS is_parent BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_doc_chunks_parent_id ON doc_chunks (parent_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_is_parent ON doc_chunks (is_parent);

-- 2) project_cards: structured fact table queried directly for factual intents.
CREATE TABLE IF NOT EXISTS project_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL UNIQUE,
    aliases TEXT[] NOT NULL DEFAULT '{}',
    category VARCHAR(50) NOT NULL DEFAULT 'general',
    indications TEXT[] NOT NULL DEFAULT '{}',
    contraindications TEXT[] NOT NULL DEFAULT '{}',
    complications JSONB NOT NULL DEFAULT '[]'::jsonb,
    duration_months_min INTEGER NULL,
    duration_months_max INTEGER NULL,
    price_rmb_min INTEGER NULL,
    price_rmb_max INTEGER NULL,
    recovery_days VARCHAR(64) NULL,
    description TEXT NOT NULL DEFAULT '',
    source_doc_ids TEXT[] NOT NULL DEFAULT '{}',
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_cards_category ON project_cards (category);
CREATE INDEX IF NOT EXISTS idx_project_cards_aliases  ON project_cards USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_project_cards_indications ON project_cards USING GIN (indications);
