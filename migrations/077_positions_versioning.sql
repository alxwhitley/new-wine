-- Migration 077: position versioning + question-time lookup record shape
-- (PLAN.md #48 serving-path session, 2026-08-01).
--
-- The serving path (scripts/serve_position.py) needs two things migration
-- 073's original shape did not provide, both called for in the track-PL
-- design rules (PLAN.md):
--
--   1. VERSIONING ON REBUILD. "When a position is later rebuilt as more
--      evidence arrives, version it -- do not overwrite in place. An answer a
--      user already saw must not silently change underneath them." A rebuild
--      writes a NEW row (version N+1) that supersedes the prior one; the prior
--      row is retained, its is_current flipped to false. Nothing is ever
--      UPDATEd in place except the is_current flag on supersede.
--
--   2. SCOPE WIDENING WITHOUT A FROM-SCRATCH REWRITE. "A teacher position
--      must be able to widen to corpus scope as evidence arrives, without a
--      from-scratch rewrite. Record-shape requirement for the first position
--      written, not a later migration." A lineage's version N can be
--      kind='teacher' and version N+1 kind='corpus' -- same lineage_id, the
--      scope simply changes across versions. This is why the lookup key is
--      (topic_key, requested_teacher_id), NOT (topic_key, source_id): a topic
--      question's lineage is found the same way whether its current version is
--      teacher-dominated or corpus-scoped.
--
-- Columns added (all additive; no existing row is rewritten except the
-- one-time backfill of the 3 draft rows migration 073's opening proof left):
--
--   lineage_id          uuid    -- groups every version of one logical
--                                  position. v1's lineage_id = its own id;
--                                  every rebuild reuses the parent's.
--   version             int     -- monotonic within a lineage, starts at 1.
--   is_current          bool    -- exactly one current version per lineage
--                                  (enforced by the partial unique index
--                                  below). The serving path reads only
--                                  is_current rows.
--   supersedes_id       uuid    -- the version this row replaced (NULL for
--                                  v1). Explicit chain for audit.
--   topic_key           text    -- normalized topic (collapse whitespace runs
--                                  to single spaces, then trim, then lowercase)
--                                  for deterministic lookup. MUST match
--                                  scripts/positions.py::normalize_topic_key()
--                                  byte-for-byte -- the SQL below and that
--                                  function are the one contract, same posture
--                                  as normalize_alias_key/migration 050
--                                  (CLAUDE.md Invariant 6). This is a SEPARATE
--                                  normalization from alias keys -- do not
--                                  reuse or fork normalize_alias_key here.
--   requested_teacher_id uuid   -- the teacher a question EXPLICITLY named
--                                  ("what does Prince teach about X"), or NULL
--                                  for a topic/corpus question ("what does the
--                                  library teach about X", scope then
--                                  determined by evidence dominance). This is
--                                  the lineage discriminator, distinct from
--                                  source_id (the actual attributed teacher of
--                                  THIS version, which is NULL for a corpus
--                                  version). A teacher-explicit lineage always
--                                  stays teacher-scoped; only a topic lineage
--                                  (requested_teacher_id IS NULL) can widen
--                                  teacher->corpus.
--
-- Backfill of the 3 existing draft rows (all Vlad Savchuk, generated via
-- generate_teacher_positions.py --teacher, i.e. teacher-EXPLICIT questions):
--   lineage_id = id (each is its own v1 lineage), version = 1,
--   is_current = true, topic_key = normalize(topic),
--   requested_teacher_id = source_id (they were teacher-explicit, so the
--   requested teacher IS the attributed teacher).
--
-- Contributor breakdown is deliberately NOT a stored column. A corpus
-- position's "which teacher supplied how much" is derived at serve time from
-- position_evidence -> propositions -> documents -> sources -- a count from
-- the immutable evidence rows of that specific version, never a stored count
-- that could drift (migration 073's own stated philosophy: the evidence floor
-- is "checkable directly against this table's row count for any position, not
-- trusted from a stored count that could drift"). Same principle here.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL, per Session Routing's
-- Database-write row -- see scripts/apply_positions_migration_077.py.

ALTER TABLE positions ADD COLUMN IF NOT EXISTS lineage_id uuid;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1
  CHECK (version >= 1);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS is_current boolean NOT NULL DEFAULT true;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS supersedes_id uuid REFERENCES positions (id);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS topic_key text;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS requested_teacher_id uuid REFERENCES sources (id);

-- One-time backfill of the pre-existing rows.
UPDATE positions SET lineage_id = id WHERE lineage_id IS NULL;
-- Collapse-then-trim-then-lower, in exactly this order, so it matches Python's
-- str.strip() (which trims ALL whitespace, unlike SQL btrim which trims only
-- spaces): collapse every whitespace run to a single space FIRST, so a leading
-- tab/newline becomes a leading space that btrim then removes identically to
-- Python. normalize_topic_key() in scripts/positions.py mirrors this exactly.
UPDATE positions
  SET topic_key = lower(btrim(regexp_replace(topic, '\s+', ' ', 'g')))
  WHERE topic_key IS NULL;
UPDATE positions
  SET requested_teacher_id = source_id
  WHERE requested_teacher_id IS NULL AND kind = 'teacher';

ALTER TABLE positions ALTER COLUMN lineage_id SET NOT NULL;
ALTER TABLE positions ALTER COLUMN topic_key SET NOT NULL;

-- Lineage-identity guarantee: at most ONE current version per
-- (topic_key, requested_teacher). NULL requested_teacher_id (topic/corpus
-- questions) collapses to the all-zeros sentinel so two current corpus
-- positions for the same topic collide instead of both being allowed
-- (Postgres treats real NULLs as distinct in a unique index).
CREATE UNIQUE INDEX IF NOT EXISTS positions_current_lineage_idx
  ON positions (
    topic_key,
    COALESCE(requested_teacher_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE is_current;

CREATE INDEX IF NOT EXISTS positions_lineage_id_idx ON positions (lineage_id);
