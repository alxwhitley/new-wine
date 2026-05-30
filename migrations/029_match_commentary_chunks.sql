-- Migration 029: RPC to vector-search chunks scoped to specific document IDs.
-- Used by GET /study/commentary when book-level pre-filter returns doc IDs.
-- Run in Supabase SQL Editor.
-- Created: 2026-05-30

CREATE OR REPLACE FUNCTION match_commentary_chunks(
  query_embedding vector(1536),
  match_count     int,
  document_ids    uuid[]
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
  WHERE c.document_id = ANY(document_ids)
    AND d.source_kind = 'commentary'
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
