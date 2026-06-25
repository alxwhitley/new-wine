-- Migration 049: Seal the NULL source_id fail-open hole
-- Confirmed by 2026-06-24 diagnostic: the "d.source_id IS NULL OR ..." arm in
-- match_chunks and search_chunks_fts lets docs with no source row bypass the
-- visibility gate and safe_mode unconditionally (fail-open). This migration
-- closes that hole in four ordered steps.
-- ──────────────────────────────────────────────────────────────────────────────
-- Steps (order-dependent — do not reorder):
--   1. Insert sentinel source row (fixed UUID, unlicensed+hidden = fail-closed)
--   2. Backfill the 18 orphan docs onto the sentinel; abort if count ≠ 18
--   3. ALTER documents.source_id: DEFAULT sentinel, NOT NULL,
--      FK ON DELETE SET DEFAULT (was SET NULL)
--   4. Rewrite RPCs — remove the "source_id IS NULL" pass-through arm
-- Created: 2026-06-24

-- ── STEP 1: Sentinel source row ───────────────────────────────────────────────
-- Fixed UUID — hardcoded for reproducibility across environments.
-- license_status='unlicensed' + visibility='hidden' → permanently excluded by gate.
-- ⚠️  WARNING: NEVER DELETE THIS ROW.
--     documents.source_id now defaults to this UUID (ON DELETE SET DEFAULT).
--     Deleting it would cause every FK insert/update targeting it to fail with
--     a FK violation, and the column DEFAULT would reference a non-existent row.
--     If you must retire this sentinel, first re-assign all pointing documents
--     to a real source row, then remove the column DEFAULT, then delete.

INSERT INTO sources (
  id,
  name,
  slug,
  license_status,
  visibility,
  notes
) VALUES (
  '267a09ac-76f3-43fb-901f-3015aef88e22',
  'Unassigned — needs source',
  'unassigned',
  'unlicensed',
  'hidden',
  'Sentinel row. Documents land here when source_id is unknown at ingest time. '
  'Kept hidden so unassigned docs are excluded from retrieval until explicitly '
  'linked to a real source. NEVER DELETE — documents.source_id defaults to this UUID.'
);

-- ── STEP 2: Backfill orphan documents ────────────────────────────────────────
-- Exactly 18 documents had source_id IS NULL as of 2026-06-24 diagnostic.
-- If count ≠ 18 new orphans appeared since then — abort so the discrepancy is
-- investigated before proceeding.

DO $$
DECLARE
  updated_count int;
BEGIN
  UPDATE documents
    SET source_id = '267a09ac-76f3-43fb-901f-3015aef88e22'
  WHERE source_id IS NULL;

  GET DIAGNOSTICS updated_count = ROW_COUNT;

  IF updated_count <> 18 THEN
    RAISE EXCEPTION
      'Backfill count mismatch: expected 18 orphan documents, got %. '
      'New orphans may have appeared — investigate before proceeding.',
      updated_count;
  END IF;

  RAISE NOTICE 'Backfilled % documents onto sentinel source.', updated_count;
END;
$$;

-- ── STEP 3: Harden documents.source_id ────────────────────────────────────────
-- Set the sentinel as the column DEFAULT so future inserts that omit source_id
-- land on the sentinel (hidden) rather than NULL.
-- Set NOT NULL — the column can no longer hold NULL.
-- Recreate the FK as ON DELETE SET DEFAULT so deleting any source row sends
-- its documents to the sentinel rather than NULLing the column (which would
-- now violate NOT NULL).

ALTER TABLE documents
  ALTER COLUMN source_id SET DEFAULT '267a09ac-76f3-43fb-901f-3015aef88e22';

ALTER TABLE documents
  ALTER COLUMN source_id SET NOT NULL;

ALTER TABLE documents
  DROP CONSTRAINT documents_source_id_fkey;

ALTER TABLE documents
  ADD CONSTRAINT documents_source_id_fkey
    FOREIGN KEY (source_id)
    REFERENCES sources (id)
    ON DELETE SET DEFAULT;

-- ── STEP 4a: match_chunks — remove IS NULL pass-through arm ──────────────────
-- Gate is now purely the EXISTS eligibility check. Every doc has a source_id,
-- so the IS NULL arm is both incorrect and unnecessary.
-- All other logic (safe_mode variable, hnsw.ef_search, signatures) unchanged.

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
    AND EXISTS (
      SELECT 1 FROM sources s
      WHERE s.id = d.source_id
        AND (
          s.license_status IN ('public_domain', 'owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')
        )
    )
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ── STEP 4b: search_chunks_fts — remove IS NULL pass-through arm ─────────────
-- Same change: gate is now purely EXISTS. Language remains plpgsql (as of 048)
-- so the safe_mode_on variable is declared once per call.

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
    AND EXISTS (
      SELECT 1 FROM sources s
      WHERE s.id = d.source_id
        AND (
          s.license_status IN ('public_domain', 'owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')
        )
    )
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;
