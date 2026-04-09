-- Migration 005: Add source_kind and citation_mode taxonomy to documents
-- Decouples the content classification (source_kind) from the citation behavior (citation_mode).
-- Backfills existing rows based on current source_type values.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-07

-- 1. Add new columns
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_kind text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS citation_mode text;

-- 2. Backfill existing rows
UPDATE documents SET
  source_kind = CASE
    WHEN source_type = 'sermon' THEN 'sermon_transcript'
    WHEN source_type = 'background' THEN 'background_note'
    ELSE 'unknown'
  END,
  citation_mode = CASE
    WHEN source_type = 'sermon' THEN 'citable'
    WHEN source_type = 'background' THEN 'silent_context'
    ELSE 'silent_context'
  END
WHERE source_kind IS NULL;

-- 3. Indexes on documents
CREATE INDEX IF NOT EXISTS idx_documents_source_kind ON documents(source_kind);
CREATE INDEX IF NOT EXISTS idx_documents_citation_mode ON documents(citation_mode);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_source_year_issue ON documents(source, year, issue);

-- 4. Indexes on chunks
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_chunk ON chunks(document_id, chunk_index);

-- 5. Indexes on articles
CREATE INDEX IF NOT EXISTS idx_articles_document_id ON articles(document_id);
CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author);
