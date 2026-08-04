-- 079_stage2_cutover.sql
-- Project 1, Stage 2 -- cutover schema (ADDITIVE; the traffic switch defaults OFF).
--
-- (1) corpus_version() -- the SHARED evidence-version signal that BOTH the async
--     reuse key and chat.py's SSE meta use (Alex's call: "use it in both places").
--     A REAL signal derived from the corpus state that actually changes an answer:
--     the document set (insert/delete/re-ingest), source license/visibility, the
--     disabled-source set, and safe_mode. STABLE + a single server-side statement
--     (~30ms measured) so it is safe to app-cache 60s. Deliberately does NOT scan
--     chunks -- max(chunks.created_at) is a ~2s seqscan (no index) on the 185k-row
--     hot table. KNOWN GAP: an in-place admin content edit that only re-chunks a
--     document (no documents-row change) is NOT reflected here. Acceptable while
--     reuse (async_answer_config.reuse_ttl_seconds) defaults OFF. When reuse goes
--     live, add a chunks.created_at index (CONCURRENTLY) or a documents.updated_at
--     bump and fold it into this function.
--
-- (2) async_answer_config.serving_enabled -- the seconds-reversible TRAFFIC switch,
--     default false. The frontend consults it via GET /async-chat/mode and routes
--     to the async path only when it is true AND the routes are mounted. Flip it
--     with one UPDATE; flip back the same way. Separate from the env-gated ROUTE
--     MOUNT (ASYNC_ANSWER_ENABLED) that controls whether the routes exist at all.
--
-- (3) answer_jobs.topics_established / result_meta -- carry the per-conversation
--     background-topic state into the producer (parity with chat.py's background-
--     topic injection) and the updated topic state back out to the client via the
--     result. answer_jobs currently holds 0 rows, so these adds are trivially safe.
--
-- Invariant 9: no semicolons inside -- comments.

CREATE OR REPLACE FUNCTION corpus_version() RETURNS text
LANGUAGE sql STABLE AS $corpusver$
  SELECT 'corpus_' || substr(md5(
    coalesce((SELECT count(*)::text FROM documents), '0') || '|' ||
    coalesce((SELECT max(created_at)::text FROM documents), '') || '|' ||
    coalesce((SELECT max(updated_at)::text FROM sources), '') || '|' ||
    coalesce((SELECT count(*)::text FROM source_toggles WHERE enabled = false), '0') || '|' ||
    coalesce((SELECT value FROM app_settings WHERE key = 'safe_mode'), '')
  ), 1, 16)
$corpusver$;

ALTER TABLE async_answer_config
  ADD COLUMN IF NOT EXISTS serving_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE answer_jobs
  ADD COLUMN IF NOT EXISTS topics_established jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE answer_jobs
  ADD COLUMN IF NOT EXISTS result_meta jsonb;

-- (4) Widen the outcome CHECK to include 'position_paper' -- the producer now
--     runs chat.py's position-paper (house-voice) interception, whose result has
--     that outcome. Idempotent (DROP IF EXISTS + ADD).
ALTER TABLE answer_jobs DROP CONSTRAINT IF EXISTS answer_jobs_outcome_check;
ALTER TABLE answer_jobs ADD CONSTRAINT answer_jobs_outcome_check
  CHECK (outcome IS NULL OR outcome IN
    ('answered','refused_attribution','no_material','position_paper','error'));
