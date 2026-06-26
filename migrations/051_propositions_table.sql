-- Migration 051: propositions table
-- Stores atomic proposition-level decompositions of chunk content.
-- Mirrors chunks as closely as possible:
--   - embedding: text-embedding-3-small, 1536 dims, cosine distance (same as chunks)
--   - fts: GENERATED ALWAYS AS stored column, same expression as chunks.fts
--     (migration 006: to_tsvector('english', coalesce(content, '')) STORED)
--   - HNSW: vector_cosine_ops, m=16, ef_construction=64 (confirmed pgvector defaults
--     via SELECT reloptions FROM pg_class WHERE relname = 'chunks_embedding_hnsw';
--     -- returned NULL, meaning no custom params were set on the chunks index)
-- Licensing resolves through document_id -> documents.source_id -> sources.
-- Retrieval RPC wiring is deferred to a later migration.
-- Created: 2026-06-25

CREATE TABLE IF NOT EXISTS propositions (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id       uuid        NOT NULL
                                REFERENCES documents (id)
                                ON DELETE CASCADE,
  content           text        NOT NULL,
  embedding         vector(1536),
  proposition_index int         NOT NULL,
  fts               tsvector
                                GENERATED ALWAYS AS (
                                  to_tsvector('english', coalesce(content, ''))
                                ) STORED,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- HNSW index on embedding -- ops class and params confirmed to match chunks_embedding_hnsw
-- (m=16, ef_construction=64 are pgvector defaults; reloptions NULL on live index)
CREATE INDEX IF NOT EXISTS propositions_embedding_hnsw
  ON propositions
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- GIN index on fts -- mirrors idx_chunks_fts_gin (migration 006)
CREATE INDEX IF NOT EXISTS propositions_fts_gin
  ON propositions
  USING GIN (fts);

-- btree index on document_id for fast per-document lookups and CASCADE deletes
CREATE INDEX IF NOT EXISTS propositions_document_id_idx
  ON propositions (document_id);
