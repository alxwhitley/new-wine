-- Migration: Add is_copyrighted to documents table
-- Run this in the Supabase SQL Editor

-- 1. Add the column
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS is_copyrighted boolean NOT NULL DEFAULT false;

-- 2. Drop and recreate match_chunks with include_copyrighted parameter
--    (CREATE OR REPLACE can't change parameter signatures, so we drop first)
DROP FUNCTION IF EXISTS match_chunks(vector, int);
DROP FUNCTION IF EXISTS match_chunks(vector, int, boolean);

CREATE FUNCTION match_chunks(
  query_embedding vector(1536),
  match_count    int,
  include_copyrighted boolean DEFAULT false
)
RETURNS TABLE (
  id            uuid,
  document_id   uuid,
  chunk_index   int,
  content       text,
  title         text,
  author        text,
  source_type   text,
  similarity    float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    c.id,
    c.document_id,
    c.chunk_index,
    c.content,
    d.title,
    d.author,
    d.source_type,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE (include_copyrighted OR d.is_copyrighted = false)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 3. Drop and recreate search_chunks_fts with include_copyrighted parameter
DROP FUNCTION IF EXISTS search_chunks_fts(text, int);
DROP FUNCTION IF EXISTS search_chunks_fts(text, int, boolean);

CREATE FUNCTION search_chunks_fts(
  query_text          text,
  match_count         int,
  include_copyrighted boolean DEFAULT false
)
RETURNS TABLE (
  id            uuid,
  document_id   uuid,
  chunk_index   int,
  content       text,
  title         text,
  author        text,
  source_type   text,
  rank          real
)
LANGUAGE sql STABLE
AS $$
  SELECT
    c.id,
    c.document_id,
    c.chunk_index,
    c.content,
    d.title,
    d.author,
    d.source_type,
    ts_rank(to_tsvector('english', c.content), plainto_tsquery('english', query_text)) AS rank
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', query_text)
    AND (include_copyrighted OR d.is_copyrighted = false)
  ORDER BY rank DESC
  LIMIT match_count;
$$;
