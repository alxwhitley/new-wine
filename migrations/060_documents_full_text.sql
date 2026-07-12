-- Migration 060: add documents.full_text
-- Nullable text column storing the full pre-chunk document body captured at
-- ingest time by shared_ingest.py. Forward-only: existing rows stay NULL,
-- no backfill (PLAN.md Decision 7).

ALTER TABLE documents ADD COLUMN full_text text;
