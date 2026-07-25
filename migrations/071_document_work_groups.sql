-- Migration 071: document_work_groups + document_work_group_members --
-- a grouping mechanism so multiple documents rows can be recorded as one
-- underlying work (e.g. a YouTube clip and the full sermon it was cut
-- from, or a multi-part series). Each membership carries its own
-- human-readable reason (e.g. "clip of parent sermon", "part 3 of 11",
-- "duplicate under alternate title") so the relationship stays legible
-- without inferring it from titles or timestamps later.
--
-- This is deliberately additive only: it does NOT touch documents or
-- propositions in any way, and does not implement or gate any
-- evidence-weighting / distinct-voice-counting behavior -- that consumer
-- is explicitly out of scope for this migration and is future work.
-- No existing table is altered and no existing row is touched.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP TABLE document_work_group_members
--   DROP TABLE document_work_groups
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

CREATE TABLE document_work_groups (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at  timestamptz NOT NULL DEFAULT now(),
  note        text
);

ALTER TABLE document_work_groups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "document_work_groups: service role full access"
  ON document_work_groups FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE TABLE document_work_group_members (
  work_group_id  uuid NOT NULL REFERENCES document_work_groups(id) ON DELETE CASCADE,
  document_id    uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  reason         text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (work_group_id, document_id)
);

ALTER TABLE document_work_group_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "document_work_group_members: service role full access"
  ON document_work_group_members FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

CREATE INDEX idx_document_work_group_members_document_id
  ON document_work_group_members(document_id);
