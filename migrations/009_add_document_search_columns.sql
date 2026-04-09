-- Migration 009: Add fts_weighted and content_summary to documents
-- Enables document-level full-text search with weighted ranking.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-09

-- 1. Add new columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS fts_weighted tsvector;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_summary text;

-- 2. GIN index on fts_weighted
CREATE INDEX IF NOT EXISTS idx_documents_fts_weighted_gin
  ON documents USING GIN(fts_weighted);

-- 3. Backfill fts_weighted for existing rows
UPDATE documents SET fts_weighted =
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(author, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(source_name, '')), 'B')
WHERE fts_weighted IS NULL;

-- 4. Backfill content_summary from the first chunk of each document
UPDATE documents d SET content_summary = sub.summary
FROM (
  SELECT document_id, left(content, 200) AS summary
  FROM chunks
  WHERE chunk_index = 0
) sub
WHERE d.id = sub.document_id
  AND d.content_summary IS NULL;

-- 5. Trigger function to auto-update fts_weighted
CREATE OR REPLACE FUNCTION documents_fts_weighted_update() RETURNS trigger AS $$
BEGIN
  NEW.fts_weighted :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.author, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.source_name, '')), 'B');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS documents_fts_weighted_trigger ON documents;

CREATE TRIGGER documents_fts_weighted_trigger
  BEFORE INSERT OR UPDATE OF title, author, source_name
  ON documents
  FOR EACH ROW
  EXECUTE FUNCTION documents_fts_weighted_update();
