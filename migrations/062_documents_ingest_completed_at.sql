-- Migration 062: add documents.ingest_completed_at (completeness stamp)
-- Nullable timestamp written by shared_ingest.py's atomic writer, inside
-- the same transaction as the document record + chunks + propositions, if
-- and only if the document landed whole (per the writer's own gated
-- definition: chunks+propositions for gated-on sources, chunks alone for
-- gated-off). Forward-only, no backfill: all ~3,800 pre-existing rows stay
-- NULL (unstamped) and are NOT treated as suspect -- default skip behavior
-- for an existing document is unchanged regardless of stamp presence.
-- Only a caller's explicit redo/reuse choice ever re-examines an existing
-- document; the skip-check itself does not read this column
-- (PLAN.md Decision 9, still open).

ALTER TABLE documents ADD COLUMN ingest_completed_at timestamptz;
