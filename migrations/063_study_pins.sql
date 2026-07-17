-- Migration 063: study_pins table for the SP2 global, account-level pin system.
-- Supersedes the SP0/161c4de in-memory, per-session pin state and the
-- inline-study-panel-spec's per-conversation/cap-4 design (see PLAN.md).
-- reference_type is deliberately a checked, extensible column: SP2 only ever
-- writes 'verse'; SP4 adds 'teacher' later without a schema change beyond
-- widening this CHECK constraint.

CREATE TABLE study_pins (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  reference_type  text NOT NULL DEFAULT 'verse' CHECK (reference_type IN ('verse')),
  verse_id        text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, reference_type, verse_id)
);

CREATE INDEX study_pins_user_id_idx ON study_pins (user_id);

ALTER TABLE study_pins ENABLE ROW LEVEL SECURITY;

-- Users manage only their own pins. Service-role (backend) bypasses RLS as usual.
CREATE POLICY study_pins_own_rows ON study_pins
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
