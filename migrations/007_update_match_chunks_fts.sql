-- Migration 007: Update match_chunks and search_chunks_fts to return
-- source_kind and citation_mode from the new taxonomy columns.
-- Also switches search_chunks_fts to use the stored fts column
-- and websearch_to_tsquery for better query parsing.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-07

-- 1. Drop and recreate match_chunks with new columns
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
  source_kind   text,
  citation_mode text,
  url           text,
  similarity    float
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
  -- Increase HNSW search beam for better recall on small corpus
  PERFORM set_config('hnsw.ef_search', '200', true);

  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.chunk_index,
    c.content,
    d.title,
    d.author,
    d.source_type,
    d.source_kind,
    d.citation_mode,
    d.url,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE (include_copyrighted OR d.is_copyrighted = false)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 2. Drop and recreate search_chunks_fts with stored fts column and new columns
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
  source_kind   text,
  citation_mode text,
  url           text,
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
    d.source_kind,
    d.citation_mode,
    d.url,
    ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) AS rank
  FROM chunks c
  JOIN documents d ON c.document_id = d.id
  WHERE
    c.fts @@ websearch_to_tsquery('english', query_text)
    AND (include_copyrighted OR d.is_copyrighted = false)
  ORDER BY rank DESC
  LIMIT match_count;
$$;
