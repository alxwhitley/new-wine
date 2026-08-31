-- Migration 095: analytics degradation marker on answer_jobs (B7).
--
-- WHY. Until 2026-08-31 an analytics failure took the ANSWER away from a
-- real user. That coupling is removed (see recording.py) -- analytics now
-- fails to a skipped write, not a failed answer. This migration adds the
-- other half Alex required: a skipped recording must leave a TRACE.
--
-- The problem it solves is an ambiguity that already cost a phase of work
-- during the 2026-08-31 smoke. "No occurrence rows for these hours" and
-- "nobody searched during these hours" were byte-for-byte identical states.
-- After this migration they are not: answer_jobs always has one row per
-- accepted submission, so absence of rows means no traffic, while rows
-- carrying a non-NULL analytics_outcome mean analytics was degraded -- and
-- say exactly how many searches went unrecorded, and why.
--
-- WHY answer_jobs AND NOT A NEW TABLE. The marker has to survive the outage
-- it records. The two analytics legs use different transports -- consent
-- reads go over PostgREST, the occurrence write goes over direct Postgres --
-- so a marker written over direct Postgres survives a PostgREST outage
-- outright. And a job row is guaranteed to exist by the time analytics runs,
-- because jobs.enqueue() already succeeded over that same direct connection:
-- if direct Postgres were fully down, enqueue would have failed first and the
-- submission would never have reached the analytics step at all.
--
-- WHAT IT DELIBERATELY DOES NOT CONTAIN. No question text, no question
-- fingerprint, and no subject key. answer_jobs carries no user_id column, so
-- stamping a job creates no account-to-search linkage. This records THAT a
-- search went unrecorded, never what it was or whose it was -- it must never
-- become a back door that reconstructs the very occurrence the privacy
-- protections just refused to write.
--
-- RETENTION. answer_job_retention.py nulls question/answer/messages at 90
-- days and leaves instrumentation columns and created_at untouched, so the
-- marker and its timestamp outlive the content purge -- which is what makes
-- a historical "which hours were degraded" query answerable at all.
--
-- The CHECK is a closed set matching recording.DEGRADED_OUTCOMES. Adding a
-- fourth degraded outcome is therefore a deliberate migration, not a silent
-- code change. This cannot hurt availability: the stamp is best-effort and
-- wrapped, so a rejected value degrades to a log line, never to a failed
-- answer.
--
-- Rollback (fully reversible, no data loss to any existing column):
--   DROP INDEX idx_answer_jobs_analytics_outcome
--   ALTER TABLE answer_jobs DROP COLUMN analytics_outcome
--
-- Run via scripts/apply_migration_095.py --apply (attended).
-- Invariant 9: no semicolons inside -- comments.


ALTER TABLE answer_jobs
  ADD COLUMN analytics_outcome text
  CHECK (
    analytics_outcome IS NULL
    OR analytics_outcome IN (
      'skipped_consent_unreadable',
      'skipped_key_unavailable',
      'skipped_write_failed'
    )
  );

-- Partial index: the reporting query only ever scans marked rows, and this
-- keeps the healthy path (every row NULL) out of the index entirely.
CREATE INDEX idx_answer_jobs_analytics_outcome
  ON answer_jobs (created_at)
  WHERE analytics_outcome IS NOT NULL;
