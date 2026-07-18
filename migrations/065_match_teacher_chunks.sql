-- Migration 065: match_teacher_chunks -- vector search scoped to a specific
-- teacher's document_ids, for SP4's teacher-card position synthesis
-- (GET /study/teacher/{source_id}).
--
-- Mirrors match_commentary_chunks's gated, HNSW-forced shape (migrations 041
-- + 056) minus the source_kind='commentary' restriction -- a teacher's works
-- can be sermon_transcript, magazine_article, etc.
--
-- Defense in depth: the calling endpoint already restricts document_ids to
-- one already-is_source_servable-gated teacher before calling this, but the
-- gate is repeated here anyway (same reasoning migration 056 gave for
-- match_commentary_chunks: document_ids is a plain uuid[] parameter and
-- could in principle be called with ids that didn't come through the gate).
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

CREATE OR REPLACE FUNCTION match_teacher_chunks(
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
  author        text
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
BEGIN
  PERFORM set_config('hnsw.ef_search', '200', true);
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
    d.author
  FROM nearest n
  JOIN documents d ON d.id = n.document_id
  WHERE EXISTS (
    SELECT 1 FROM sources s
    WHERE s.id = d.source_id
      AND (
        s.license_status IN ('public_domain', 'owned')
        OR (NOT safe_mode_on AND s.visibility = 'shown')
      )
  );
END;
$$;
