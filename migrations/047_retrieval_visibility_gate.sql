-- Migration 047: Retrieval visibility gate
-- Adds a fail-closed per-source visibility filter at the SQL layer to
-- match_chunks (vector) and search_chunks_fts (FTS) RPCs.
-- HNSW index confirmed preserved (EXPLAIN shows chunks_embedding_hnsw used).
-- ──────────────────────────────────────────────────────────────────────────────
-- TWO VARIANTS — apply only one. Awaiting confirmation before running.
--
-- VARIANT (a) — RECOMMENDED
--   Gate on sources.license_status, ignoring documents.is_copyrighted.
--   Makes sources.visibility the true per-entity on/off switch for ALL
--   content regardless of the is_copyrighted flag (which is unreliable).
--   A source with license_status IN ('public_domain','owned') is always
--   retrievable regardless of visibility (Rhemata-owned and PD content are
--   never suppressible via the gate). Everything else — unlicensed OR
--   licensed — is gated by visibility.
--   Docs with source_id IS NULL pass through (no entity assigned). All 18
--   such docs are is_copyrighted=false as of Step 3b; new ingest should
--   always set source_id to remain fully gated.
--
-- VARIANT (b) — ALTERNATIVE (keep for reference)
--   Gate on documents.is_copyrighted as the trigger. Non-copyrighted docs
--   bypass the gate entirely. Problem: Derek Prince and other sources marked
--   is_copyrighted=false in the DB cannot be turned off via visibility even
--   if their source entity is set to 'hidden'. Use only if you want the gate
--   to apply exclusively to IS_COPYRIGHTED=true content.
-- ──────────────────────────────────────────────────────────────────────────────
-- Created: 2026-06-23

-- ── VARIANT (a): match_chunks ─────────────────────────────────────────────────

DROP FUNCTION IF EXISTS match_chunks(vector, int, boolean);

CREATE FUNCTION match_chunks(
  query_embedding     vector(1536),
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
  boost_factor  float,
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
    COALESCE(d.boost_factor, 1.0)::float AS boost_factor,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE
    -- Existing global copyrighted-content flag (chat.py passes true by default)
    (include_copyrighted OR d.is_copyrighted = false)
    -- VARIANT (a): gate on source license_status, ignoring is_copyrighted.
    -- PD/owned sources are always retrievable.
    -- All other sources (unlicensed, licensed) require visibility='shown'.
    -- Docs with no source_id assigned pass through (all are non-copyrighted
    -- as of Step 3b; new ingest must set source_id to stay gated).
    AND (
      d.source_id IS NULL
      OR EXISTS (
        SELECT 1 FROM sources s
        WHERE s.id = d.source_id
          AND (
            s.license_status IN ('public_domain', 'owned')
            OR s.visibility = 'shown'
          )
      )
    )
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ── VARIANT (a): search_chunks_fts ───────────────────────────────────────────

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
  boost_factor  float,
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
    COALESCE(d.boost_factor, 1.0)::float AS boost_factor,
    ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) AS rank
  FROM chunks c
  JOIN documents d ON c.document_id = d.id
  WHERE
    c.fts @@ websearch_to_tsquery('english', query_text)
    AND (include_copyrighted OR d.is_copyrighted = false)
    -- VARIANT (a): same gate as match_chunks
    AND (
      d.source_id IS NULL
      OR EXISTS (
        SELECT 1 FROM sources s
        WHERE s.id = d.source_id
          AND (
            s.license_status IN ('public_domain', 'owned')
            OR s.visibility = 'shown'
          )
      )
    )
  ORDER BY rank DESC
  LIMIT match_count;
$$;


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- VARIANT (b) — for reference only (commented out, DO NOT uncomment without
-- replacing the functions above first).
--
-- WHERE clause additions for VARIANT (b):
--
-- match_chunks / search_chunks_fts add:
--   AND (
--     d.is_copyrighted = false
--     OR EXISTS (
--       SELECT 1 FROM sources s
--       WHERE s.id = d.source_id
--         AND s.visibility = 'shown'
--     )
--   )
--
-- Limitation: docs with is_copyrighted=false bypass the gate regardless of
-- their source entity's visibility setting. Derek Prince (is_copyrighted=false
-- in DB) cannot be hidden via the visibility dial under this variant.
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
