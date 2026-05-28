-- Migration 028: RPC to find commentary documents by book name.
-- Used by GET /study/commentary book-level pre-filter.
-- Run in Supabase SQL Editor.
-- Created: 2026-05-28

CREATE OR REPLACE FUNCTION match_commentary_by_book(book_name text)
RETURNS TABLE(id uuid)
LANGUAGE sql
STABLE
AS $$
  SELECT id FROM documents
  WHERE source_kind = 'commentary'
  AND citation_mode = 'citable'
  AND bible_references && ARRAY[book_name]::text[];
$$;
