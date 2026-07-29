-- Migration 074: proposition -> source chunk back-link (generator
-- bypass-proofing session, 2026-07-29/30)
--
-- Additive only. No existing table is ALTERed with a new NOT NULL column,
-- no existing row is touched. Every pre-existing proposition simply has
-- zero rows in this new table -- "which chunk(s) did this come from" stays
-- explicitly unknown for those rows, never guessed or backfilled. Mirrors
-- the honest-unknown posture migration 067 already established for
-- provenance (prompt_version/prompt_fingerprint/model, nullable, no
-- backfill) -- same posture, expressed here via absence-of-rows rather than
-- a NULL scalar, because the real relationship is many-to-many: extraction
-- operates on a document's FULL reconstructed text, not a single chunk, so
-- a stored proposition's only honest back-link is "every chunk that made up
-- the text this extraction call actually saw" -- never a single chunk id,
-- and never more precision than that.
--
-- A real join table, not a uuid[] array column on propositions -- the same
-- design call already made and documented for position_evidence (migration
-- 073): queryable in both directions, FK-enforced, and a chunk delete
-- cannot silently desync a stored array the way it could an unenforced list
-- of ids.
--
-- ON DELETE CASCADE from propositions: if a proposition itself is deleted,
-- its back-links are meaningless and should go with it (mirrors
-- propositions.document_id's own CASCADE from documents).
-- ON DELETE RESTRICT from chunks: mirrors position_evidence.proposition_id's
-- own RESTRICT (migration 073) -- deleting a chunk a live proposition
-- depends on must fail loudly and force a human decision, never silently
-- orphan or shrink a proposition's recorded provenance out from under it.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- no MCP write tools (guard_pretooluse.py denies them
-- for any subagent regardless).

CREATE TABLE IF NOT EXISTS proposition_chunks (
  proposition_id  uuid NOT NULL REFERENCES propositions (id) ON DELETE CASCADE,
  chunk_id        uuid NOT NULL REFERENCES chunks (id) ON DELETE RESTRICT,
  PRIMARY KEY (proposition_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS proposition_chunks_chunk_id_idx
  ON proposition_chunks (chunk_id);

ALTER TABLE proposition_chunks ENABLE ROW LEVEL SECURITY;

-- Service-role only, mirrors position_evidence (migration 073) exactly. No
-- public-read policy yet: nothing user-visible reads this table this
-- session -- a future serving-path session adds a public read policy when
-- (and only when) something actually renders back-links to users.
CREATE POLICY "proposition_chunks: service role full access"
  ON proposition_chunks FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
