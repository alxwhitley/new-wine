-- 088_source_ingest_runner.sql
-- Durable execution state for the cleared source-ingest queue.
--
-- Repository preparation does not apply this migration. Before a separately
-- approved apply, scripts/apply_migration_088.py must snapshot every queue
-- row's retain_original_text value to source_ingest_runner_review/.


-- Retaining complete extracted text is now a fixed queue policy. Existing
-- rows have never been consumed by a runner, so this changes future behavior
-- without claiming to reconstruct any historical document text.
UPDATE source_ingest_queue SET retain_original_text = true
WHERE retain_original_text IS DISTINCT FROM true;

ALTER TABLE source_ingest_queue
  ALTER COLUMN retain_original_text SET DEFAULT true,
  ALTER COLUMN retain_original_text SET NOT NULL,
  ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS worker_id text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS run_after timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS stage text NOT NULL DEFAULT 'queued',
  ADD COLUMN IF NOT EXISTS final_url text,
  ADD COLUMN IF NOT EXISTS content_sha256 text,
  ADD COLUMN IF NOT EXISTS fetched_bytes bigint,
  ADD COLUMN IF NOT EXISTS attempted_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stored_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS skipped_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS errored_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS result_document_id uuid REFERENCES documents(id) ON DELETE SET NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'source_ingest_queue_retain_original_text_true'
      AND conrelid = 'source_ingest_queue'::regclass
  ) THEN
    ALTER TABLE source_ingest_queue
      ADD CONSTRAINT source_ingest_queue_retain_original_text_true
      CHECK (retain_original_text = true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'source_ingest_queue_attempts_nonnegative'
      AND conrelid = 'source_ingest_queue'::regclass
  ) THEN
    ALTER TABLE source_ingest_queue
      ADD CONSTRAINT source_ingest_queue_attempts_nonnegative
      CHECK (attempts >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'source_ingest_queue_max_attempts_positive'
      AND conrelid = 'source_ingest_queue'::regclass
  ) THEN
    ALTER TABLE source_ingest_queue
      ADD CONSTRAINT source_ingest_queue_max_attempts_positive
      CHECK (max_attempts > 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'source_ingest_queue_counts_nonnegative'
      AND conrelid = 'source_ingest_queue'::regclass
  ) THEN
    ALTER TABLE source_ingest_queue
      ADD CONSTRAINT source_ingest_queue_counts_nonnegative CHECK (
        attempted_documents >= 0
        AND stored_documents >= 0
        AND skipped_documents >= 0
        AND errored_documents >= 0
      );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS source_ingest_queue_claim_idx
  ON source_ingest_queue (run_after, created_at)
  WHERE status = 'waiting' AND cleared_to_run = true;

CREATE INDEX IF NOT EXISTS source_ingest_queue_lease_idx
  ON source_ingest_queue (lease_expires_at)
  WHERE status = 'running';


-- Rollback (manual, only after validating the exact target database):
-- 1. Stop every source-ingest worker and confirm no row is running.
-- 2. DROP INDEX IF EXISTS source_ingest_queue_claim_idx;
--    DROP INDEX IF EXISTS source_ingest_queue_lease_idx;
-- 3. ALTER TABLE source_ingest_queue
--      DROP CONSTRAINT IF EXISTS source_ingest_queue_retain_original_text_true,
--      DROP CONSTRAINT IF EXISTS source_ingest_queue_attempts_nonnegative,
--      DROP CONSTRAINT IF EXISTS source_ingest_queue_max_attempts_positive,
--      DROP CONSTRAINT IF EXISTS source_ingest_queue_counts_nonnegative,
--      ALTER COLUMN retain_original_text DROP DEFAULT,
--      ALTER COLUMN retain_original_text DROP NOT NULL;
-- 4. Restore retain_original_text values from the pre-migration snapshot.
-- 5. ALTER TABLE source_ingest_queue
--      DROP COLUMN IF EXISTS attempts,
--      DROP COLUMN IF EXISTS max_attempts,
--      DROP COLUMN IF EXISTS worker_id,
--      DROP COLUMN IF EXISTS lease_expires_at,
--      DROP COLUMN IF EXISTS run_after,
--      DROP COLUMN IF EXISTS stage,
--      DROP COLUMN IF EXISTS final_url,
--      DROP COLUMN IF EXISTS content_sha256,
--      DROP COLUMN IF EXISTS fetched_bytes,
--      DROP COLUMN IF EXISTS attempted_documents,
--      DROP COLUMN IF EXISTS stored_documents,
--      DROP COLUMN IF EXISTS skipped_documents,
--      DROP COLUMN IF EXISTS errored_documents,
--      DROP COLUMN IF EXISTS result_document_id;
