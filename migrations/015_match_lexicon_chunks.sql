-- Migration 015: Add match_lexicon_chunks function for word-study retrieval.
-- Returns top N chunks from lexicon documents by vector similarity.
-- Run in Supabase SQL Editor.
-- Created: 2026-05-20

CREATE OR REPLACE FUNCTION match_lexicon_chunks(
  query_embedding vector(1536),
  match_count    int DEFAULT 5
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
  similarity    float
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
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
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.source_kind = 'lexicon'
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
