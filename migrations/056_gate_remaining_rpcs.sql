-- Session 2b: port the license gate to the five retrieval RPCs that bypass
-- it entirely. match_chunks and search_chunks_fts (migration 049) are the
-- only two that read safe_mode and join to sources -- match_lexicon_chunks,
-- match_commentary_by_book, match_commentary_chunks, match_sermon_chunks_by_ref,
-- and search_documents do not. All five are called only by the backend under
-- the service key (confirmed) and none needs SECURITY DEFINER -- they match
-- the protected pair's INVOKER context.
--
-- Reference gate (verbatim from migration 049, match_chunks):
--   safe_mode_on boolean := (SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode')
--   AND EXISTS (
--     SELECT 1 FROM sources s
--     WHERE s.id = d.source_id
--       AND (s.license_status IN ('public_domain', 'owned')
--            OR (NOT safe_mode_on AND s.visibility = 'shown'))
--   )
--
-- IMPORTANT -- live-vs-file drift found before writing this migration:
-- match_commentary_by_book's LIVE definition does NOT match migration 028's
-- file. Live uses `EXISTS (SELECT 1 FROM unnest(bible_references) AS ref
-- WHERE ref LIKE book_name || '%')` (prefix match) and has NO
-- `citation_mode = 'citable'` filter -- both differ from the 028 file, which
-- was apparently patched live without a follow-up migration. This migration
-- preserves the LIVE behavior exactly and only adds the gate -- it does not
-- "fix" that drift, which is out of scope here. Verify live definitions with
-- pg_get_functiondef before editing any RPC in this repo -- do not trust
-- migration-file prose (same lesson as the migration-037 policy-name miss).
--
-- Run manually in the Supabase SQL editor. All five use CREATE OR REPLACE
-- with signatures unchanged from the live functions, so no DROP is needed --
-- this includes the two LANGUAGE sql -> plpgsql conversions (#2, #4), which
-- Postgres allows via OR REPLACE as long as argument types and return type
-- are unchanged.

-- ── 1. match_lexicon_chunks (migration 015) — plpgsql, add DECLARE + gate ────

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
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE d.source_kind = 'lexicon'
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

-- ── 2. match_commentary_by_book — gate FIRST, it feeds #3's document_ids ────
-- LANGUAGE sql -> plpgsql (to hold the DECLARE block, matching the pattern
-- used everywhere else in this migration and in migration 041). Preserves
-- the LIVE filter logic (LIKE-prefix unnest, no citation_mode arm) verbatim.

CREATE OR REPLACE FUNCTION match_commentary_by_book(book_name text)
RETURNS TABLE(id uuid)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
BEGIN
  RETURN QUERY
  SELECT d.id FROM documents d
  WHERE d.source_kind = 'commentary'
    AND EXISTS (
      SELECT 1 FROM unnest(d.bible_references) AS ref
      WHERE ref LIKE book_name || '%'
    )
    AND EXISTS (
      SELECT 1 FROM sources s
      WHERE s.id = d.source_id
        AND (
          s.license_status IN ('public_domain', 'owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')
        )
    );
END;
$$;

-- ── 3. match_commentary_chunks (migration 041) — plpgsql, add DECLARE + gate ─
-- Gated independently of #2 (defense in depth) -- document_ids is a plain
-- uuid[] parameter and could in principle be called with ids that did not
-- come through the now-gated match_commentary_by_book.

CREATE OR REPLACE FUNCTION match_commentary_chunks(
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
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
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
  WHERE d.source_kind = 'commentary'
    AND EXISTS (
      SELECT 1 FROM sources s
      WHERE s.id = d.source_id
        AND (
          s.license_status IN ('public_domain', 'owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')
        )
    );
END;
$$;

-- ── 4. match_sermon_chunks_by_ref (migration 036) — sql -> plpgsql, add gate ─

CREATE OR REPLACE FUNCTION match_sermon_chunks_by_ref(
    query_embedding vector(1536),
    verse_ref text,
    match_count int DEFAULT 10
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index int,
    content text,
    title text,
    author text,
    source_kind text,
    citation_mode text,
    similarity float
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
BEGIN
  RETURN QUERY
  SELECT
      c.id,
      c.document_id,
      c.chunk_index,
      c.content,
      d.title,
      d.author,
      d.source_kind,
      d.citation_mode,
      1 - (c.embedding <=> query_embedding) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE c.bible_references @> ARRAY[verse_ref]
    AND d.source_kind = 'sermon_transcript'
    AND d.citation_mode = 'citable'
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

-- ── 5. search_documents (migration 013) — plpgsql, add safe_mode_on + gate ──
-- The existing is_copyrighted arm is a SEPARATE, unreliable flag (per
-- CLAUDE.md -- the gate deliberately ignores it). Left untouched. The gate
-- is added alongside it, not in place of it. All tokenizing/ts_headline
-- logic is unchanged.

CREATE OR REPLACE FUNCTION search_documents(
  query_text text DEFAULT NULL,
  author_filter text DEFAULT NULL,
  source_kind_filter text DEFAULT NULL,
  include_copyrighted boolean DEFAULT false
)
RETURNS TABLE (
  id uuid,
  title text,
  author text,
  issue text,
  year int,
  content_summary text,
  highlighted_snippet text,
  rank real
)
LANGUAGE plpgsql
AS $$
DECLARE
  _query tsquery;
  _tokens text[];
  _parts text[] := '{}';
  _tok text;
  _sub text;
  _clean text;
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
BEGIN
  IF query_text IS NOT NULL AND trim(query_text) <> '' THEN
    _tokens := regexp_split_to_array(trim(query_text), '\s+');
    FOREACH _tok IN ARRAY _tokens LOOP
      -- Replace colons with spaces so "8:28" splits into two tokens.
      _tok := replace(_tok, ':', ' ');
      FOREACH _sub IN ARRAY regexp_split_to_array(_tok, '\s+') LOOP
        _clean := regexp_replace(_sub, '[^a-zA-Z0-9]', '', 'g');
        IF _clean <> '' THEN
          _parts := array_append(_parts, _clean || ':*');
        END IF;
      END LOOP;
    END LOOP;
    IF array_length(_parts, 1) IS NULL THEN
      _query := NULL;
    ELSE
      BEGIN
        _query := to_tsquery('english', array_to_string(_parts, ' & '));
      EXCEPTION WHEN OTHERS THEN
        _query := plainto_tsquery('english', query_text);
      END;
    END IF;
  ELSE
    _query := NULL;
  END IF;

  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.author,
    d.issue,
    d.year,
    d.content_summary,
    CASE
      WHEN _query IS NOT NULL THEN (
        SELECT
          CASE
            WHEN ts_headline('english', _cleaned, _query,
              'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=false, MaxFragments=1'
            ) LIKE '%<mark>%'
            THEN ts_headline('english', _cleaned, _query,
              'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=false, MaxFragments=1'
            )
            ELSE left(_cleaned, 200)
          END
        FROM (
          SELECT
            regexp_replace(
              regexp_replace(
                regexp_replace(
                  regexp_replace(
                    regexp_replace(
                      regexp_replace(
                        bc.chunk_content,
                        '^\[.*?\]\s*', '', 'n'
                      ),
                      '(?m)^#{1,6}\s+.*$', '', 'g'
                    ),
                    '(?m)^---+\s*$', '', 'g'
                  ),
                  '(?m)^(TITLE|AUTHOR|ISSUE|DATE|PAGE_START|PAGE_END|SOURCE_TYPE|TOPIC_TAGS):.*$', '', 'g'
                ),
                '\*{1,2}([^*]+)\*{1,2}', '\1', 'g'
              ),
              '(?i)^\s*by\s+[^\n]+\n*', '', 'n'
            ) AS _cleaned
          FROM (
            SELECT coalesce(
              (SELECT c.content FROM chunks c
               WHERE c.document_id = d.id
                 AND to_tsvector('english', c.content) @@ _query
               ORDER BY ts_rank(to_tsvector('english', c.content), _query) DESC
               LIMIT 1),
              (SELECT c.content FROM chunks c
               WHERE c.document_id = d.id
               ORDER BY c.chunk_index ASC
               LIMIT 1)
            ) AS chunk_content
          ) bc
        ) cleaned_chunk
      )
      ELSE NULL
    END AS highlighted_snippet,
    CASE
      WHEN _query IS NOT NULL
        THEN ts_rank(d.fts_weighted, _query)
      ELSE 0.0
    END::real AS rank
  FROM documents d
  WHERE
    (_query IS NULL OR d.fts_weighted @@ _query)
    AND (author_filter IS NULL OR d.author ILIKE '%' || author_filter || '%')
    AND (source_kind_filter IS NULL OR d.source_kind = source_kind_filter)
    AND (include_copyrighted = true OR d.is_copyrighted = false)
    AND EXISTS (
      SELECT 1 FROM sources s
      WHERE s.id = d.source_id
        AND (
          s.license_status IN ('public_domain', 'owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')
        )
    )
  ORDER BY rank DESC
  LIMIT 20;
END;
$$;

-- Verification (run on a FRESH connection, not the one that ran the DDL):
--   SELECT proname, prosrc ILIKE '%safe_mode_on%' AS has_gate
--     FROM pg_proc WHERE proname IN (
--       'match_lexicon_chunks', 'match_commentary_by_book',
--       'match_commentary_chunks', 'match_sermon_chunks_by_ref',
--       'search_documents'
--     ) AND pronamespace = 'public'::regnamespace
--   -- Expected: has_gate = true for all five (semicolon omitted from this
--   -- comment on purpose -- see migration 051's gotcha note)
