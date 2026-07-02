-- Session 1: lock corpus tables to service-role-only read.
--
-- Problem: documents and chunks have "Public can read documents" / "Public
-- can read chunks" RLS policies (USING true) from migration 037. The
-- frontend ships the anon key in the bundle, so the entire corpus --
-- including hidden and unlicensed content that migrations 043-050 built a
-- gate specifically to hide -- is dumpable via PostgREST with no auth.
-- propositions and removed_urls have RLS disabled entirely, so under
-- Supabase's default grants the anon key can read AND write them.
--
-- Fix: service-role-only access on all four tables. No EXISTS-gate rewrite
-- -- the backend is 100% service-key (backend/app/db/supabase.py), so it
-- bypasses RLS regardless of policy shape, and no anon caller legitimately
-- needs direct table access (confirmed: frontend never calls the retrieval
-- RPCs, and the only anon reads of these tables were AdminModal.tsx count
-- queries and a realtime subscription, moved to a backend endpoint /
-- removed alongside this migration).
--
-- NOTE: the live policy names on documents/chunks were "Public can read
-- documents" / "Public can read chunks" -- NOT "Public read documents" /
-- "Public read chunks" as migration 037's own header comment implies. Verify
-- actual names via pg_policies before editing policies in this repo; do not
-- trust migration-file prose. A DROP POLICY IF EXISTS with the wrong name
-- silently no-ops and leaves the permissive policy live.
--
-- Applied directly to production 2026-07-02 via psycopg2 (SUPABASE_DB_URL),
-- confirmed on a fresh connection. Kept here as the source-of-truth record;
-- statements are idempotent (DROP POLICY IF EXISTS + REVOKE ALL are safe to
-- re-run). Run manually in the Supabase SQL editor for any future replay.

-- documents: drop both public-read policies (correct + previously-assumed
-- names), add service-role-only SELECT, revoke all anon/authenticated grants.
DROP POLICY IF EXISTS "Public can read documents" ON documents;
DROP POLICY IF EXISTS "Public read documents" ON documents;
DROP POLICY IF EXISTS "Service read documents" ON documents;
CREATE POLICY "Service read documents" ON documents
  FOR SELECT USING (auth.role() = 'service_role');
REVOKE ALL ON documents FROM anon, authenticated;

-- chunks: same treatment.
DROP POLICY IF EXISTS "Public can read chunks" ON chunks;
DROP POLICY IF EXISTS "Public read chunks" ON chunks;
DROP POLICY IF EXISTS "Service read chunks" ON chunks;
CREATE POLICY "Service read chunks" ON chunks
  FOR SELECT USING (auth.role() = 'service_role');
REVOKE ALL ON chunks FROM anon, authenticated;

-- propositions: RLS was never enabled -- under Supabase defaults this means
-- anon/authenticated held table-level grants and could read AND write.
-- Enable RLS, add service-role-only policy, revoke default grants.
ALTER TABLE propositions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service access propositions" ON propositions;
CREATE POLICY "Service access propositions" ON propositions
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON propositions FROM anon, authenticated;

-- removed_urls: same gap as propositions -- no RLS, anon could read and
-- write the delete blocklist. Enable RLS, service-role-only, revoke grants.
ALTER TABLE removed_urls ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service access removed_urls" ON removed_urls;
CREATE POLICY "Service access removed_urls" ON removed_urls
  FOR ALL USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON removed_urls FROM anon, authenticated;

-- Verification (run on a FRESH connection, not the one that ran the DDL):
--   SELECT relname, relrowsecurity FROM pg_class
--     WHERE relname IN ('documents','chunks','propositions','removed_urls')
--     AND relnamespace = 'public'::regnamespace;
--   SELECT tablename, policyname, cmd FROM pg_policies
--     WHERE tablename IN ('documents','chunks','propositions','removed_urls');
--   SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
--     WHERE table_schema = 'public'
--     AND table_name IN ('documents','chunks','propositions','removed_urls')
--     AND grantee IN ('anon','authenticated');
--   -- Expected: rowsecurity = true on all 4; only "Service ..." policies
--   -- (service_role-gated) remain; zero rows in the grants query.
