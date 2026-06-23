-- Migration 048: Global safe-mode switch
-- Adds app_settings key/value table and a 'safe_mode' flag.
-- When safe_mode='on', only PD/owned sources are retrievable regardless of
-- individual sources.visibility values — visibility column is never written.
-- Turning safe_mode back 'off' restores the exact prior per-entity state.
-- ──────────────────────────────────────────────────────────────────────────────
-- Gate logic summary:
--   A source is eligible when:
--     license_status IN ('public_domain','owned')          -- always
--   OR
--     safe_mode IS OFF AND visibility = 'shown'            -- unlicensed/shown
--                                                            only when not in
--                                                            safe mode
--
-- source_id IS NULL still passes through (18 non-copyrighted docs, unchanged).
-- ──────────────────────────────────────────────────────────────────────────────
-- Created: 2026-06-23

-- ── PART 1: app_settings table ────────────────────────────────────────────────

CREATE TABLE app_settings (
  key        text PRIMARY KEY,
  value      text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Default OFF — applying this migration changes nothing about what is served
INSERT INTO app_settings (key, value) VALUES ('safe_mode', 'off');

-- RLS: service role full access only (same pattern as sources, migration 043)
ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "app_settings: service role full access" ON app_settings
  FOR ALL
  USING  (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- ── PART 2a: match_chunks (plpgsql — safe_mode read once as variable) ─────────

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
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
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
    (include_copyrighted OR d.is_copyrighted = false)
    AND (
      d.source_id IS NULL
      OR EXISTS (
        SELECT 1 FROM sources s
        WHERE s.id = d.source_id
          AND (
            s.license_status IN ('public_domain', 'owned')
            OR (NOT safe_mode_on AND s.visibility = 'shown')
          )
      )
    )
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ── PART 2b: search_chunks_fts (converted plpgsql — safe_mode read once) ──────
-- Was LANGUAGE sql in migrations 026/047. Converted to plpgsql so the flag
-- can be read into a variable once per call rather than as a per-row subquery.

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
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
  ts_query tsquery := websearch_to_tsquery('english', query_text);
BEGIN
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
    ts_rank_cd(c.fts, ts_query) AS rank
  FROM chunks c
  JOIN documents d ON c.document_id = d.id
  WHERE
    c.fts @@ ts_query
    AND (include_copyrighted OR d.is_copyrighted = false)
    AND (
      d.source_id IS NULL
      OR EXISTS (
        SELECT 1 FROM sources s
        WHERE s.id = d.source_id
          AND (
            s.license_status IN ('public_domain', 'owned')
            OR (NOT safe_mode_on AND s.visibility = 'shown')
          )
      )
    )
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;
