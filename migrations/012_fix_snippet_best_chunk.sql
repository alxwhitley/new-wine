-- Migration 012: Fix highlighted_snippet to use best-matching chunk via FTS
-- Falls back to chunk_index 0 when no chunk matches the query (tag-based results).
-- Also strips byline ("by ...") from snippet text.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-09

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
  ORDER BY rank DESC
  LIMIT 20;
END;
$$;
