-- Migration 066: persist per-message citations and SP1 verified_references
-- so verse/teacher underlines and citation pills survive a conversation
-- reload. Confirmed by direct code trace (2026-07-19 refinement session):
-- neither column has ever existed on `messages` -- this data has only ever
-- lived in the single SSE meta event for the turn that generated it
-- (backend/app/routers/chat.py:1026-1031), discarded the moment that
-- response ends. Nullable: user-role messages and pre-migration assistant
-- rows never had this data and must keep degrading to plain text, not error.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS citations jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS verified_references jsonb;
