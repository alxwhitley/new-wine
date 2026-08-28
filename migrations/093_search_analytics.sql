-- Migration 093: Search analytics and corpus-gap dashboard (Horizon item 4,
-- docs/roadmap.md).
--
-- Three new tables, all RLS-enabled, service-role-only -- same posture as
-- migration 082's quotes/document_quote_clearance (the backend connects
-- with the service_role key and bypasses RLS on every write -- RLS here is
-- defense-in-depth against a PostgREST anon/authenticated client ever
-- reaching these tables directly, which the frontend never does -- all
-- access is through backend REST endpoints).
--
-- analytics_consent: one row per account. Policy version + timestamps only
-- -- no question, topic, or answer data by construction (no column exists
-- to put it in).
--
-- search_occurrences: one row per accepted chat submission. No account id,
-- conversation id, or answer text by construction -- only an irreversible
-- HMAC-derived subject_key (NULL for admin-retest rows, which have no
-- personal subject). classification_status/classifier_* columns are the
-- provenance discipline CLAUDE.md Invariant 14 already requires for
-- `positions` -- stamped once, never silently NULL after classification.
--
-- search_gap_details: one row per no_material occurrence. Holds the
-- REDACTED question only (never the original), purged automatically 30
-- days after resolution -- anonymous counts and the resolution date are
-- retained forever, only the wording is deleted.
--
-- Rollback (fully reversible, no data loss to any existing table):
--   DROP TABLE search_gap_details
--   DROP TABLE search_occurrences
--   DROP TABLE analytics_consent
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.
-- Invariant 9: no semicolons inside -- comments.


-- ── PART 1: analytics_consent ────────────────────────────────────────────

CREATE TABLE analytics_consent (
  user_id               uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  policy_version        text        NOT NULL,
  acknowledged_at       timestamptz NOT NULL,
  withdrawn_at          timestamptz,
  subject_key           text        NOT NULL,
  subject_key_version   integer     NOT NULL,
  retired_subject_keys  jsonb       NOT NULL DEFAULT '[]'::jsonb,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE analytics_consent ENABLE ROW LEVEL SECURITY;
CREATE POLICY "analytics_consent: service role full access"
  ON analytics_consent FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON TABLE analytics_consent FROM anon, authenticated;


-- ── PART 2: search_occurrences ───────────────────────────────────────────

CREATE TABLE search_occurrences (
  id                         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  submission_id              text        NOT NULL UNIQUE,
  job_id                     uuid        NOT NULL REFERENCES answer_jobs(id),
  origin                     text        NOT NULL
                                          CHECK (origin IN ('user', 'admin_retest')),
  subject_key                text,
  subject_key_version        integer,
  question_fingerprint       text        NOT NULL,
  primary_topic              text,
  outcome                    text,
  classification_status      text        NOT NULL DEFAULT 'pending'
                                          CHECK (classification_status IN ('pending', 'classified', 'failed')),
  classifier_version         text,
  classifier_model           text,
  classifier_prompt_version  text,
  classifier_confidence      numeric(4,3),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  finalized_at               timestamptz,
  CHECK (
    (origin = 'user' AND subject_key IS NOT NULL AND subject_key_version IS NOT NULL)
    OR
    (origin = 'admin_retest' AND subject_key IS NULL AND subject_key_version IS NULL)
  )
);

CREATE INDEX idx_search_occurrences_job_id ON search_occurrences(job_id);
CREATE INDEX idx_search_occurrences_pending ON search_occurrences(classification_status)
  WHERE classification_status = 'pending';
CREATE INDEX idx_search_occurrences_subject_key ON search_occurrences(subject_key);
CREATE INDEX idx_search_occurrences_topic_outcome ON search_occurrences(primary_topic, outcome);

ALTER TABLE search_occurrences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "search_occurrences: service role full access"
  ON search_occurrences FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON TABLE search_occurrences FROM anon, authenticated;


-- ── PART 3: search_gap_details ───────────────────────────────────────────

CREATE TABLE search_gap_details (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  occurrence_id         uuid        NOT NULL UNIQUE REFERENCES search_occurrences(id) ON DELETE CASCADE,
  redacted_question     text,
  redaction_version     text        NOT NULL,
  redaction_status      text        NOT NULL
                                    CHECK (redaction_status IN ('redacted', 'redaction_failed')),
  status                text        NOT NULL DEFAULT 'open'
                                    CHECK (status IN ('open', 'resolved')),
  retest_occurrence_id  uuid        REFERENCES search_occurrences(id),
  retest_outcome        text,
  resolved_at           timestamptz,
  text_purge_at         timestamptz,
  purged_at             timestamptz,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_search_gap_details_status ON search_gap_details(status);
CREATE INDEX idx_search_gap_details_purge ON search_gap_details(text_purge_at)
  WHERE redacted_question IS NOT NULL;

ALTER TABLE search_gap_details ENABLE ROW LEVEL SECURITY;
CREATE POLICY "search_gap_details: service role full access"
  ON search_gap_details FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');
REVOKE ALL ON TABLE search_gap_details FROM anon, authenticated;
