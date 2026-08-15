-- Migration 087: grant rhemata_readonly_analysis SELECT on quote_verification_log
--
-- Provisioning gap, not a design decision: quote_verification_log did not
-- exist yet when migration 084 created the rhemata_readonly_analysis role
-- and its named per-table grants (084 predates 085, which added this
-- table), so it was never included. It is NOT one of migration 084's
-- deliberately excluded user/auth/metering/operational tables (that list
-- is answer_jobs, app_settings, async_answer_config, contributor_requests,
-- conversations, deletion_requests, document_quote_clearance, feedback,
-- generation_model_config, guest_sessions, messages, pastors_cards,
-- provider_rate_usage, removed_urls, saved_words, source_ingest_queue,
-- source_ingest_domain_memory, source_license_audit, source_toggles,
-- study_pins, user_daily_usage, user_roles, user_usage -- quote_verification_log
-- is a corpus/quote-rail record, the same category as quotes and
-- quote_source_revisions, both of which the role already reads).
--
-- Same two-part pattern as migration 084 Part 2 + Part 3: a plain GRANT
-- SELECT is not sufficient on its own because quote_verification_log has
-- RLS enabled (migration 085) with only a service-role policy, so a
-- matching additive PERMISSIVE SELECT policy is required too, or the role
-- would see zero rows despite the grant.
--
-- SELECT only -- no INSERT/UPDATE/DELETE granted or intended.
--
-- Rollback (fully reversible, no data loss):
--   DROP POLICY "rhemata_readonly_analysis: select" ON quote_verification_log;
--   REVOKE SELECT ON quote_verification_log FROM rhemata_readonly_analysis;
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

GRANT SELECT ON quote_verification_log TO rhemata_readonly_analysis;

DROP POLICY IF EXISTS "rhemata_readonly_analysis: select" ON quote_verification_log;
CREATE POLICY "rhemata_readonly_analysis: select" ON quote_verification_log
  FOR SELECT TO rhemata_readonly_analysis USING (true);
