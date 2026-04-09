-- Migration 010: Add search_documents SQL function
-- Document-level full-text search with optional filters.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-09

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
  rank real
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.author,
    d.issue,
    d.year,
    d.content_summary,
    CASE
      WHEN query_text IS NOT NULL AND trim(query_text) <> ''
        THEN ts_rank(d.fts_weighted, plainto_tsquery('english', query_text))
      ELSE 0.0
    END::real AS rank
  FROM documents d
  WHERE
    -- FTS filter: only apply when query_text is non-empty
    (
      query_text IS NULL
      OR trim(query_text) = ''
      OR d.fts_weighted @@ plainto_tsquery('english', query_text)
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
