-- Migration 073: position layer foundation (PLAN.md #48, Phase 4 opening
-- session, 2026-07-28)
--
-- Two new tables only. No existing table is ALTERed, no existing row is
-- touched. Additive and reversible by dropping both tables.
--
-- A position is a stored, reviewable summary of what one teacher teaches on
-- one topic, generated from that teacher's existing statements (the
-- propositions table) only -- never from source/chunk text. This is the
-- layer PLAN.md #48 describes eventually replacing both the live per-request
-- answer path and the teacher-card synthesis in
-- backend/app/routers/study.py::get_teacher_card() (which today embeds a raw
-- CHUNK excerpt into a live Anthropic call on every request -- the exact
-- leak this layer exists to close). Nothing about that live path changes in
-- this migration -- these tables are not read by any serving code yet.
--
-- kind is structurally locked to 'teacher' by the CHECK constraint below.
-- Alex's standing ruling (2026-07-28): corpus-wide positions are banned
-- until the propositions backfill completes (#49), because a corpus-wide
-- position authored today would name whichever teachers happen to already
-- have statements as "the corpus" and invert the day Derek Prince's ~429
-- documents land. Widening this to allow 'corpus' requires a deliberate
-- future migration that changes the CHECK constraint itself -- not a runtime
-- flag any application code can flip. source_id is NOT NULL for the same
-- reason: every row today names exactly one teacher -- a future corpus-wide
-- migration would need to relax this column too, so the schema itself
-- cannot silently drift into producing an averaged, unattributed position.
--
-- Every column that carries generation provenance (prompt_version,
-- prompt_fingerprint, model) is NOT NULL, unlike propositions' nullable
-- provenance columns (migration 067) -- that nullability is exactly why
-- every one of the 2,409 live propositions has NULL provenance today
-- (CLAUDE.md Invariant 10 / Landmines). This table is built after that
-- lesson, not before it: an unstamped write is impossible here, not just
-- discouraged.
--
-- status is a lifecycle field, not a moderation queue: 'draft' (freshly
-- generated, not reviewed by Alex -- everything this session writes stays
-- here), 'approved' (Alex has read and accepted it -- a future session's
-- job), 'stale' (a future re-check found the evidence set has changed since
-- generation -- e.g. an evidence proposition was itself later flagged,
-- edited, or removed), 'retracted' (explicitly pulled, kept for the audit
-- trail rather than deleted).
--
-- Evidence is a real join table, not a prose mention or a text[] column of
-- IDs -- queryable, FK-enforced, and the honest-empty floor (a position must
-- cite at least N statements, enforced in application code before any
-- insert -- see scripts/positions.py) is checkable directly against this
-- table's row count for any position, not trusted from a stored count that
-- could drift.
--
-- ON DELETE RESTRICT on position_evidence.proposition_id is deliberate, not
-- CASCADE: if a proposition a position depends on is ever deleted, that
-- delete must fail loudly and force a human decision about the position,
-- never silently orphan or silently shrink a position's evidence out from
-- under it.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- no MCP write tools (guard_pretooluse.py denies
-- them for any subagent regardless).

CREATE TABLE IF NOT EXISTS positions (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  kind                text        NOT NULL DEFAULT 'teacher'
                                   CHECK (kind = 'teacher'),
  source_id           uuid        NOT NULL REFERENCES sources (id),
  topic               text        NOT NULL,
  content             text        NOT NULL,
  status              text        NOT NULL DEFAULT 'draft'
                                   CHECK (status IN ('draft', 'approved', 'stale', 'retracted')),
  prompt_version      text        NOT NULL,
  prompt_fingerprint  text        NOT NULL,
  model               text        NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS positions_source_id_idx ON positions (source_id);
CREATE INDEX IF NOT EXISTS positions_status_idx ON positions (status);
CREATE INDEX IF NOT EXISTS positions_prompt_fingerprint_idx ON positions (prompt_fingerprint);

CREATE TABLE IF NOT EXISTS position_evidence (
  position_id     uuid NOT NULL REFERENCES positions (id) ON DELETE CASCADE,
  proposition_id  uuid NOT NULL REFERENCES propositions (id) ON DELETE RESTRICT,
  PRIMARY KEY (position_id, proposition_id)
);

CREATE INDEX IF NOT EXISTS position_evidence_proposition_id_idx
  ON position_evidence (proposition_id);

ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE position_evidence ENABLE ROW LEVEL SECURITY;

-- Service-role only, both tables -- mirrors teacher_profiles (migration 064)
-- exactly. No public-read policy yet: nothing user-visible reads this table
-- this session, per this session's explicit no-serving-changes scope. A
-- future serving-path session adds a public read policy when (and only
-- when) something actually renders 'approved' positions to users.

CREATE POLICY "positions: service role full access"
  ON positions FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "position_evidence: service role full access"
  ON position_evidence FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
