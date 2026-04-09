-- Migration 006: Add stored tsvector column and GIN index to chunks
-- Eliminates per-query to_tsvector() computation for full-text search.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-07

-- 1. Add stored generated tsvector column
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

-- 2. Create GIN index for fast FTS lookups
CREATE INDEX IF NOT EXISTS idx_chunks_fts_gin ON chunks USING GIN(fts);
