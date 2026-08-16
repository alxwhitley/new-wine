#!/usr/bin/env python3
"""Verify migration 088 defines the durable source-ingest runner contract."""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "migrations" / "088_source_ingest_runner.sql"


def main():
    if not MIGRATION_PATH.is_file():
        print("FAIL: missing migration: %s" % MIGRATION_PATH)
        return 1

    sql = MIGRATION_PATH.read_text()
    required = {
        "attempts integer NOT NULL DEFAULT 0",
        "max_attempts integer NOT NULL DEFAULT 3",
        "worker_id text",
        "lease_expires_at timestamptz",
        "run_after timestamptz NOT NULL DEFAULT now()",
        "stage text NOT NULL DEFAULT 'queued'",
        "final_url text",
        "content_sha256 text",
        "fetched_bytes bigint",
        "attempted_documents integer NOT NULL DEFAULT 0",
        "stored_documents integer NOT NULL DEFAULT 0",
        "skipped_documents integer NOT NULL DEFAULT 0",
        "errored_documents integer NOT NULL DEFAULT 0",
        "result_document_id uuid REFERENCES documents(id) ON DELETE SET NULL",
        "source_ingest_queue_claim_idx",
        "source_ingest_queue_lease_idx",
        "CHECK (retain_original_text = true)",
    }
    missing = sorted(fragment for fragment in required if fragment not in sql)

    failures = []
    if missing:
        failures.append("missing migration contracts: %r" % missing)
    if "UPDATE source_ingest_queue SET retain_original_text = true" not in sql:
        failures.append("retention backfill is missing")
    if "ALTER COLUMN retain_original_text SET NOT NULL" not in sql:
        failures.append("retention NOT NULL enforcement is missing")

    rollback_contracts = {
        "DROP INDEX IF EXISTS source_ingest_queue_claim_idx",
        "DROP INDEX IF EXISTS source_ingest_queue_lease_idx",
        "DROP CONSTRAINT IF EXISTS source_ingest_queue_retain_original_text_true",
        "ALTER COLUMN retain_original_text DROP DEFAULT",
        "ALTER COLUMN retain_original_text DROP NOT NULL",
        "restore retain_original_text values from the pre-migration snapshot",
    }
    missing_rollback = sorted(
        fragment
        for fragment in rollback_contracts
        if fragment.lower() not in sql.lower()
    )
    if missing_rollback:
        failures.append("missing rollback contracts: %r" % missing_rollback)

    new_columns = (
        "attempts",
        "max_attempts",
        "worker_id",
        "lease_expires_at",
        "run_after",
        "stage",
        "final_url",
        "content_sha256",
        "fetched_bytes",
        "attempted_documents",
        "stored_documents",
        "skipped_documents",
        "errored_documents",
        "result_document_id",
    )
    missing_drops = [
        column
        for column in new_columns
        if "DROP COLUMN IF EXISTS %s" % column not in sql
    ]
    if missing_drops:
        failures.append("rollback does not drop columns: %r" % missing_drops)

    if failures:
        print("%d migration check(s) FAILED:" % len(failures))
        for failure in failures:
            print("  - %s" % failure)
        return 1

    print("PASS: migration 088 defines runner state and rollback contracts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
