-- Migration 041: Rewrite match_commentary_chunks to prevent statement_timeout.
--
-- Root cause: The deployed function was plain SQL with no index hints.
-- PL/pgSQL generic plans (used after 5 calls) estimated a full-table seq scan
-- as cheaper than HNSW for large uuid[] arrays, causing 57014 statement_timeout
-- for high-commentary books (John has 150 doc IDs).
--
-- Fix:
--   1. Switch to LANGUAGE plpgsql to allow set_config() calls.
--   2. set_config('enable_seqscan', 'off', true)  — local to the transaction,
--      locks HNSW even in generic plan mode. Without this, the planner
--      estimates seq scan as cheaper for large = ANY($doc_ids) arrays.
--   3. CTE separates the HNSW scan from the documents JOIN, so the JOIN only
--      runs for the final match_count rows rather than every HNSW candidate.
--
-- EXPLAIN ANALYZE (John 1:1, 150 doc IDs):
--   Before: ~573ms cold, full-table seq scan, 57014 timeout via PostgREST
--   After:  200 HTTP, results in ~3s cold / ~200ms warm (HNSW-driven)
--
-- Must DROP first — LANGUAGE and column order differ from the deployed version.
-- Run in Supabase SQL Editor.
-- Created: 2026-06-16

DROP FUNCTION IF EXISTS match_commentary_chunks(vector, integer, uuid[]);

CREATE FUNCTION match_commentary_chunks(
  query_embedding vector(1536),
  match_count     int,
  document_ids    uuid[]
)
RETURNS TABLE (
  id            uuid,
  document_id   uuid,
  content       text,
  chunk_index   int,
  similarity    float,
  title         text,
  author        text,
  source_kind   text,
  source_type   text,
  citation_mode text,
  url           text
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
  PERFORM set_config('hnsw.ef_search', '200', true);
  -- Local to this transaction: prevents the planner from choosing a seq scan
  -- in generic plan mode when document_ids is a large array.
  PERFORM set_config('enable_seqscan', 'off', true);

  RETURN QUERY
  WITH nearest AS (
    SELECT
      c.id,
      c.document_id,
      c.content,
      c.chunk_index,
      1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    WHERE c.document_id = ANY(document_ids)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count
  )
  SELECT
    n.id,
    n.document_id,
    n.content,
    n.chunk_index,
    n.similarity,
    d.title,
    d.author,
    d.source_kind,
    d.source_type,
    d.citation_mode,
    d.url
  FROM nearest n
  JOIN documents d ON d.id = n.document_id
  WHERE d.source_kind = 'commentary';
END;
$$;
