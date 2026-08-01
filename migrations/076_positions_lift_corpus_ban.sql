-- Migration 076: lift the corpus-wide position ban (PLAN.md #48 serving-path
-- session, 2026-08-01) -- Alex's explicit 2026-08-01 decision.
--
-- Background. Migration 073 CHECK-locked positions.kind to exactly 'teacher'
-- and kept source_id NOT NULL, deliberately banning corpus-wide positions
-- until the propositions backfill (#49) completed -- a corpus-wide position
-- authored before Derek Prince's material landed would have named whichever
-- teachers happened to already have statements as "the corpus" and inverted
-- the day his documents were processed. That precondition is now satisfied:
-- the #49 backfill ran 2026-07-30 (850/857 eligible documents have
-- propositions, including 477 of Derek Prince's -- the exact trigger
-- CLAUDE.md Invariant 13 named). Alex judged that close enough to lift the
-- gate rather than wait for 857/857.
--
-- What this migration changes, and ONLY this:
--   1. Widens the kind CHECK from (kind = 'teacher') to
--      kind IN ('teacher','corpus'). The constraint is NOT dropped -- it
--      stays CHECK-locked to exactly those two values, so a third scope can
--      never appear by accident (a runtime typo, a forked caller). Widening
--      to a third scope would require another deliberate migration.
--   2. Makes source_id NULLABLE, and adds a scope/attribution coupling CHECK
--      so the two can never drift apart:
--        - a teacher position MUST name exactly one teacher (source_id NOT NULL)
--        - a corpus position MUST NOT name a single source (source_id NULL) --
--          its contributing teachers are derived from its evidence
--          (position_evidence -> propositions -> documents -> sources) at
--          build/serve time, never from a stored single-source pointer or a
--          stored taxonomy (the standing "contributors are derived from
--          evidence, never stored judgment" rule -- PLAN.md track PL).
--      This preserves migration 073's original guarantee ("the schema itself
--      cannot silently drift into producing an averaged, unattributed
--      position") in a corpus-aware form: an averaged position that named no
--      one would need source_id NULL AND kind='teacher', which this coupling
--      CHECK rejects.
--
-- What this migration deliberately does NOT touch:
--   - Provenance columns stay NOT NULL (CLAUDE.md Invariant 14) -- corpus
--     rows stamp prompt_version/prompt_fingerprint/model exactly like teacher
--     rows.
--   - Generation stays structurally source-blind (CLAUDE.md Invariant 12) --
--     no schema here feeds source/chunk text to the generator.
--   - The application-level refusal in scripts/positions.py::write_position()
--     is updated in the same commit as this migration, but remains a SECOND,
--     independent lock in addition to this CHECK, not a replacement for it --
--     corpus positions are still permitted in exactly two places that both
--     have to agree, never one.
--
-- Additive/reversible: no row is read or rewritten, only the two constraints
-- and the source_id nullability change. Reverting requires re-narrowing the
-- CHECK and re-adding NOT NULL (only safe while no corpus rows exist).
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- see scripts/apply_positions_migration_076.py.

ALTER TABLE positions DROP CONSTRAINT positions_kind_check;

ALTER TABLE positions
  ADD CONSTRAINT positions_kind_check CHECK (kind IN ('teacher', 'corpus'));

ALTER TABLE positions ALTER COLUMN source_id DROP NOT NULL;

ALTER TABLE positions
  ADD CONSTRAINT positions_scope_source_coupling CHECK (
    (kind = 'teacher' AND source_id IS NOT NULL)
    OR (kind = 'corpus' AND source_id IS NULL)
  );
