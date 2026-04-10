-- Migration 013: Bible references tracking
-- Adds bible_references text[] to documents, GIN index,
-- updates fts_weighted trigger to include bible_references (weight C),
-- and updates search_documents RPC with prefix search support
-- so "Romans 8" matches "Romans 8:1", "Romans 8:28", etc.
-- Run in Supabase SQL Editor.
-- Created: 2026-04-10

-- 1. Add column
ALTER TABLE documents ADD COLUMN IF NOT EXISTS bible_references text[] DEFAULT '{}';

-- 2. GIN index on the array
CREATE INDEX IF NOT EXISTS idx_documents_bible_refs
  ON documents USING GIN (bible_references);

-- 3. Update fts_weighted trigger to include bible_references at weight C.
-- Colons are stripped from references before vectorization so that
-- "Romans 8:28" becomes three tokens: romans, 8, 28 — this keeps the
-- tsvector parser happy (colons are reserved tsquery syntax) and lets
-- prefix queries like "romans:* & 8:*" match cleanly.
CREATE OR REPLACE FUNCTION documents_fts_weighted_update() RETURNS trigger AS $$
BEGIN
  NEW.fts_weighted :=
    setweight(to_tsvector('english', coalesce(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.author, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.source_name, '')), 'B') ||
    setweight(to_tsvector('english',
      replace(array_to_string(coalesce(NEW.bible_references, '{}'), ' '), ':', ' ')
    ), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS documents_fts_weighted_trigger ON documents;

CREATE TRIGGER documents_fts_weighted_trigger
  BEFORE INSERT OR UPDATE OF title, author, source_name, bible_references
  ON documents
  FOR EACH ROW
  EXECUTE FUNCTION documents_fts_weighted_update();

-- 4. Backfill fts_weighted for all existing rows so bible_references
-- (empty array for now) is represented in the vector.
UPDATE documents SET fts_weighted =
  setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(author, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(source_name, '')), 'B') ||
  setweight(to_tsvector('english',
    replace(array_to_string(coalesce(bible_references, '{}'), ' '), ':', ' ')
  ), 'C');

-- 5. Update search_documents RPC with prefix tsquery support.
-- Splits query_text on whitespace, strips colons + non-alphanumerics per token,
-- appends :* for prefix matching, joins with & into a to_tsquery expression.
-- Example: "Romans 8:28" -> "romans:* & 8:* & 28:*"
-- Example: "Romans 8"    -> "romans:* & 8:*"  (matches "Romans 8:1", "Romans 8:28", ...)
-- Falls back to plainto_tsquery on any parse error.
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
  _tokens text[];
  _parts text[] := '{}';
  _tok text;
  _sub text;
  _clean text;
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
  ORDER BY rank DESC
  LIMIT 20;
END;
$$;
