-- Add original_title to documents to preserve the real source title
-- before any future editorial rewrite. Nullable so existing rows are safe
-- until the backfill runs.

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS original_title text;
