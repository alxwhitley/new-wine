-- Migration: Fix HNSW recall by increasing ef_search in match_chunks
-- The HNSW index misses valid results with default ef_search (40).
-- Switching to PLPGSQL allows us to SET hnsw.ef_search before querying.
-- Run this in the Supabase SQL Editor.

-- 1. Drop existing match_chunks
DROP FUNCTION IF EXISTS match_chunks(vector, int, boolean);

-- 2. Recreate as PLPGSQL with higher ef_search
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
    d.url,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE (include_copyrighted OR d.is_copyrighted = false)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
