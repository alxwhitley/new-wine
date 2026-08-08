-- Migration 084: Read-only corpus-analysis database role
--
-- Adds ONE new Postgres role, `rhemata_readonly_analysis`, for unattended
-- overnight analysis jobs (Grok, Qwen, and future scripted runs) that need
-- to read corpus content but must never be able to write anything and must
-- never see user/auth/metering data. Additive only -- no existing role,
-- grant, or policy is modified.
--
-- Why grants alone aren't enough: every corpus table below has RLS enabled
-- (migration 037), and most policies gate on auth.role() = 'service_role',
-- which is a PostgREST JWT claim that a plain psycopg2 connection never
-- sets. A GRANT SELECT alone would have quietly returned zero rows on those
-- tables instead of the real data. So each such table also gets one new,
-- additive, PERMISSIVE SELECT policy scoped `TO rhemata_readonly_analysis`
-- (permissive policies OR together -- this does not touch or narrow the
-- existing "service role full access" policies at all, including their
-- INSERT/UPDATE/DELETE coverage for the service_role connection).
--
-- No blanket schema-wide grant, no ALTER DEFAULT PRIVILEGES: tables are
-- named explicitly so a future `CREATE TABLE` never becomes automatically
-- readable by this role.
--
-- Password is set separately by scripts/apply_migration_084.py (generated,
-- never embedded in this file) -- this file only creates the role shell,
-- grants, and policies, so it is safe to commit as-is.
--
-- Scope decisions (excluded on purpose -- user data, auth, metering, or
-- pure operational/admin-workflow state, none needed for corpus analysis):
--   answer_jobs, app_settings, async_answer_config, contributor_requests,
--   conversations, deletion_requests, document_quote_clearance, feedback,
--   generation_model_config, guest_sessions, messages, pastors_cards,
--   provider_rate_usage, removed_urls, saved_words, source_ingest_queue,
--   source_ingest_domain_memory, source_license_audit, source_toggles,
--   study_pins, user_daily_usage, user_roles, user_usage. The entire `auth`
--   schema is untouched -- no USAGE grant, so it stays fully inaccessible.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP POLICY "rhemata_readonly_analysis: select" ON documents;
--   DROP POLICY "rhemata_readonly_analysis: select" ON chunks;
--   DROP POLICY "rhemata_readonly_analysis: select" ON propositions;
--   DROP POLICY "rhemata_readonly_analysis: select" ON proposition_chunks;
--   DROP POLICY "rhemata_readonly_analysis: select" ON sources;
--   DROP POLICY "rhemata_readonly_analysis: select" ON source_aliases;
--   DROP POLICY "rhemata_readonly_analysis: select" ON positions;
--   DROP POLICY "rhemata_readonly_analysis: select" ON position_evidence;
--   DROP POLICY "rhemata_readonly_analysis: select" ON quotes;
--   DROP POLICY "rhemata_readonly_analysis: select" ON quote_source_revisions;
--   DROP POLICY "rhemata_readonly_analysis: select" ON teacher_profiles;
--   DROP POLICY "rhemata_readonly_analysis: select" ON document_work_groups;
--   DROP POLICY "rhemata_readonly_analysis: select" ON document_work_group_members;
--   REASSIGN OWNED BY rhemata_readonly_analysis TO postgres; -- no-op, role owns nothing
--   DROP OWNED BY rhemata_readonly_analysis; -- drops the role's own grants
--   DROP ROLE rhemata_readonly_analysis;
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.


-- ── PART 1: the role itself (no password yet -- set by the apply script) ────

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rhemata_readonly_analysis') THEN
    CREATE ROLE rhemata_readonly_analysis WITH
      LOGIN
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOREPLICATION
      NOBYPASSRLS
      PASSWORD NULL;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO rhemata_readonly_analysis;


-- ── PART 2: explicit per-table SELECT grants (named tables only) ────────────

GRANT SELECT ON
  documents,
  chunks,
  propositions,
  proposition_chunks,
  sources,
  source_aliases,
  verses,
  interlinear_words,
  excerpts,
  book_quotes,
  books,
  background_topics,
  jewish_perspectives,
  positions,
  position_evidence,
  teacher_profiles,
  quotes,
  quote_source_revisions,
  document_work_groups,
  document_work_group_members
TO rhemata_readonly_analysis;


-- ── PART 3: additive RLS policies for the tables gated to service_role only ──
-- (background_topics, book_quotes, books, excerpts, interlinear_words,
-- jewish_perspectives, verses already carry a `USING (true)` public-read
-- policy and need nothing further here.)

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON documents;
CREATE POLICY "rhemata_readonly_analysis: select" ON documents
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON chunks;
CREATE POLICY "rhemata_readonly_analysis: select" ON chunks
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON propositions;
CREATE POLICY "rhemata_readonly_analysis: select" ON propositions
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON proposition_chunks;
CREATE POLICY "rhemata_readonly_analysis: select" ON proposition_chunks
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON sources;
CREATE POLICY "rhemata_readonly_analysis: select" ON sources
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON source_aliases;
CREATE POLICY "rhemata_readonly_analysis: select" ON source_aliases
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON positions;
CREATE POLICY "rhemata_readonly_analysis: select" ON positions
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON position_evidence;
CREATE POLICY "rhemata_readonly_analysis: select" ON position_evidence
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON quotes;
CREATE POLICY "rhemata_readonly_analysis: select" ON quotes
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON quote_source_revisions;
CREATE POLICY "rhemata_readonly_analysis: select" ON quote_source_revisions
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON teacher_profiles;
CREATE POLICY "rhemata_readonly_analysis: select" ON teacher_profiles
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON document_work_groups;
CREATE POLICY "rhemata_readonly_analysis: select" ON document_work_groups
  FOR SELECT TO rhemata_readonly_analysis USING (true);

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON document_work_group_members;
CREATE POLICY "rhemata_readonly_analysis: select" ON document_work_group_members
  FOR SELECT TO rhemata_readonly_analysis USING (true);
