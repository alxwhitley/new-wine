-- Migration 011: Add highlighted_snippet to search_documents function
-- Run in Supabase SQL Editor.
-- Created: 2026-04-09
-- Updated: 2026-04-09 — best-match chunk, markdown stripping, fallback

DROP FUNCTION IF EXISTS search_documents(text, text, text, boolean);

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
BEGIN
  -- Pre-compute the tsquery once
  IF query_text IS NOT NULL AND trim(query_text) <> '' THEN
    _query := plainto_tsquery('english', query_text);
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
            -- If ts_headline produces a match (contains <mark>), use it
            WHEN ts_headline('english', cleaned, _query,
              'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=false, MaxFragments=1'
            ) LIKE '%<mark>%'
            THEN ts_headline('english', cleaned, _query,
              'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=false, MaxFragments=1'
            )
            -- Fallback: plain substring of cleaned content
            ELSE left(cleaned, 200)
          END
        FROM (
          SELECT
            -- Strip markdown/metadata from the best-matching chunk
            regexp_replace(
              regexp_replace(
                regexp_replace(
                  regexp_replace(
                    regexp_replace(
                      c.content,
                      '^\[.*?\]\s*', '', 'n'          -- strip [New Wine | ...] header
                    ),
                    '(?m)^#{1,6}\s+.*$', '', 'g'       -- strip # headings
                  ),
                  '(?m)^---+\s*$', '', 'g'             -- strip --- dividers
                ),
                '(?m)^(TITLE|AUTHOR|ISSUE|DATE|PAGE_START|PAGE_END|SOURCE_TYPE|TOPIC_TAGS):.*$', '', 'g'  -- strip frontmatter
              ),
              '\*{1,2}([^*]+)\*{1,2}', '\1', 'g'       -- strip bold/italic markers
            ) AS cleaned
          FROM chunks c
          WHERE c.document_id = d.id
          ORDER BY ts_rank(to_tsvector('english', c.content), _query) DESC
          LIMIT 1
        ) best_chunk
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
    -- FTS filter: only apply when query_text is non-empty
    (
      _query IS NULL
      OR d.fts_weighted @@ _query
    )
    -- Author ILIKE filter
    AND (
      author_filter IS NULL
      OR d.author ILIKE '%' || author_filter || '%'
    )
    -- Source kind filter
    AND (
      source_kind_filter IS NULL
      OR d.source_kind = source_kind_filter
    )
    -- Copyright filter
    AND (
      include_copyrighted = true
      OR d.is_copyrighted = false
    )
  ORDER BY rank DESC
  LIMIT 20;
END;
$$;
