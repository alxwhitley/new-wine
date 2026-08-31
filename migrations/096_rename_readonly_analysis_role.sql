-- Migration 096: Rename the read-only analysis role for the New Wine rename
--
-- Renames `rhemata_readonly_analysis` (migration 084) to
-- `newwine_readonly_analysis`. Part of the Rhemata -> New Wine product
-- rename (CLAUDE.md Settled decision #25).
--
-- Why a new migration rather than editing 084/087: both are already applied
-- to production. Rewriting an applied migration would make this repository
-- claim something was applied that never was. 084 and 087 are left exactly
-- as they were run, and this file records the change on top of them.
--
-- What follows the rename automatically, and why:
--   - The 14 RLS policies scoped TO this role. Policies store role OIDs,
--     not names, so a rename does not detach them.
--   - The SELECT grants on 21 tables, for the same reason.
--   - The role password. Verified live before writing this migration:
--     password_encryption is scram-sha-256 and the stored verifier begins
--     SCRAM-SHA-256$. A SCRAM verifier does not incorporate the username,
--     so RENAME preserves it. (Under md5 the verifier hashes username plus
--     password and RENAME would have blanked it, requiring a reset.)
--
-- What does NOT follow automatically, and must be done by hand after this
-- migration is applied:
--   - backend/app/.env.readonly-analysis. Its READONLY_ANALYSIS_DB_URL
--     embeds the Supabase pooler username `<role>.<project_ref>` and will
--     still say rhemata_readonly_analysis.jjerxncanaxlbdzcybab. Connections
--     fail until that username is updated. The password itself is unchanged.
--
-- Idempotent: re-running after a successful apply is a no-op rather than an
-- error, so a partial run can be retried safely.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rhemata_readonly_analysis')
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'newwine_readonly_analysis')
    THEN
        ALTER ROLE rhemata_readonly_analysis RENAME TO newwine_readonly_analysis;
        RAISE NOTICE 'Renamed rhemata_readonly_analysis to newwine_readonly_analysis';
    ELSIF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'newwine_readonly_analysis') THEN
        RAISE NOTICE 'newwine_readonly_analysis already exists - no action taken';
    ELSE
        RAISE EXCEPTION 'Neither role exists - refusing to continue';
    END IF;
END
$$;
