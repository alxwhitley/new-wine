#!/usr/bin/env python3
"""Transactional contract checks for durable source-ingest queue jobs."""

import unittest

from source_ingest_queue.jobs import (
    claim_next,
    complete,
    fail_or_requeue,
    get_row,
    heartbeat,
    needs_attention,
    reap_expired_leases,
    set_stage,
    validate_reconciliation,
)
from source_ingest_queue.processor import ProcessOutcome


class RecordingCursor:
    def __init__(self, owner):
        self.owner = owner
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.owner.calls.append((" ".join(sql.split()), params))
        self.result = self.owner.results.pop(0) if self.owner.results else None

    def fetchone(self):
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def fetchall(self):
        if self.result is None:
            return []
        return self.result if isinstance(self.result, list) else [self.result]


class RecordingConnection:
    def __init__(self, owner):
        self.owner = owner

    def cursor(self, **kwargs):
        return RecordingCursor(self.owner)


class RecordingDb:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []

    def run(self, function):
        return function(RecordingConnection(self))


class ReconciliationTests(unittest.TestCase):
    def test_accepts_zero_attention_or_exact_one_document_terminal_counts(self):
        self.assertTrue(validate_reconciliation(0, 0, 0, 0, allow_zero=True))
        self.assertTrue(validate_reconciliation(1, 1, 0, 0))
        self.assertTrue(validate_reconciliation(1, 0, 1, 0))
        self.assertTrue(validate_reconciliation(1, 0, 0, 1))

    def test_rejects_negative_zero_or_mismatched_terminal_counts(self):
        cases = (
            (0, 0, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 1, 0),
            (-1, 0, 0, 0),
            (True, 1, 0, 0),
        )
        for counts in cases:
            with self.subTest(counts=counts):
                self.assertFalse(validate_reconciliation(*counts))


class ClaimTests(unittest.TestCase):
    def test_reaps_then_atomically_claims_one_cleared_ready_row(self):
        claimed = {
            "id": "11111111-1111-1111-1111-111111111111",
            "status": "running",
            "worker_id": "worker-1",
        }
        db = RecordingDb(results=[[], claimed])

        result = claim_next(db, "worker-1", 120)

        self.assertEqual(result, claimed)
        self.assertEqual(len(db.calls), 2)
        reap_sql, reap_params = db.calls[0]
        claim_sql, claim_params = db.calls[1]
        self.assertIn("status = 'running'", reap_sql)
        self.assertIn("lease_expires_at < now()", reap_sql)
        self.assertEqual(reap_params, None)
        for fragment in (
            "status = 'waiting'",
            "cleared_to_run = true",
            "run_after <= now()",
            "FOR UPDATE SKIP LOCKED",
            "LIMIT 1",
            "RETURNING *",
        ):
            self.assertIn(fragment, claim_sql)
        self.assertEqual(claim_params, ("worker-1", 120))

    def test_returns_none_when_no_row_is_claimable(self):
        db = RecordingDb(results=[[], None])

        self.assertIsNone(claim_next(db, "worker-1", 120))

    def test_verifier_can_scope_reap_and_claim_to_one_exact_row(self):
        claimed = {"id": "fixture-1", "status": "running"}
        db = RecordingDb(results=[[], claimed])

        self.assertEqual(
            claim_next(db, "worker-1", 120, only_row_id="fixture-1"), claimed
        )

        reap_sql, reap_params = db.calls[0]
        claim_sql, claim_params = db.calls[1]
        self.assertIn("id = %s", reap_sql)
        self.assertEqual(reap_params, ("fixture-1",))
        self.assertIn("id = %s", claim_sql)
        self.assertEqual(claim_params, ("worker-1", 120, "fixture-1"))


class LifecycleTests(unittest.TestCase):
    def test_get_row_can_force_a_read_only_transaction(self):
        row = {"id": "row-1", "status": "waiting"}
        db = RecordingDb(results=[None, row])

        self.assertEqual(get_row(db, "row-1", read_only=True), row)
        self.assertEqual(db.calls[0], ("SET TRANSACTION READ ONLY", None))
        self.assertIn("SELECT * FROM source_ingest_queue WHERE id = %s", db.calls[1][0])
        self.assertEqual(db.calls[1][1], ("row-1",))

    def test_heartbeat_and_stage_require_current_running_owner(self):
        heartbeat_db = RecordingDb(results=[{"id": "row-1"}])
        stage_db = RecordingDb(results=[{"id": "row-1"}])

        self.assertTrue(heartbeat(heartbeat_db, "row-1", "worker-1", 120))
        self.assertTrue(set_stage(stage_db, "row-1", "worker-1", "extracting"))

        for db in (heartbeat_db, stage_db):
            sql, params = db.calls[0]
            self.assertIn("id = %s", sql)
            self.assertIn("worker_id = %s", sql)
            self.assertIn("status = 'running'", sql)
            self.assertIn("lease_expires_at > now()", sql)
            self.assertEqual(params[-2:], ("row-1", "worker-1"))

        stale = RecordingDb(results=[None])
        self.assertFalse(heartbeat(stale, "row-1", "stale-worker", 120))

    def test_needs_attention_is_owned_zero_count_terminal_transition(self):
        db = RecordingDb(results=[{"id": "row-1"}])

        self.assertTrue(
            needs_attention(
                db,
                "row-1",
                "worker-1",
                "source_unresolved",
                "operator action required",
            )
        )

        sql, params = db.calls[0]
        self.assertIn("status = 'needs_attention'", sql)
        self.assertIn("attempted_documents = 0", sql)
        self.assertIn("stored_documents = 0", sql)
        self.assertIn("skipped_documents = 0", sql)
        self.assertIn("errored_documents = 0", sql)
        self.assertIn("id = %s", sql)
        self.assertIn("worker_id = %s", sql)
        self.assertIn("status = 'running'", sql)
        self.assertIn("lease_expires_at > now()", sql)
        self.assertEqual(
            params,
            ("source_unresolved: operator action required", "row-1", "worker-1"),
        )

    def test_fail_or_requeue_owns_row_backs_off_and_reconciles_at_ceiling(self):
        waiting_db = RecordingDb(results=[{"status": "waiting"}])
        failed_db = RecordingDb(results=[{"status": "failed"}])

        self.assertEqual(
            fail_or_requeue(
                waiting_db,
                "row-1",
                "worker-1",
                "dns_failure",
                "retry later",
                attempted=False,
            ),
            "waiting",
        )
        self.assertEqual(
            fail_or_requeue(
                failed_db,
                "row-1",
                "worker-1",
                "proposition_provider_failure",
                "rolled back",
                attempted=True,
            ),
            "failed",
        )

        for db in (waiting_db, failed_db):
            sql, params = db.calls[0]
            self.assertIn("attempts = attempts + 1", sql)
            self.assertIn("attempts + 1 >= max_attempts", sql)
            self.assertIn("power(2, attempts) * 5", sql)
            self.assertIn("attempted_documents = CASE", sql)
            self.assertIn("errored_documents = CASE", sql)
            self.assertIn("id = %s", sql)
            self.assertIn("worker_id = %s", sql)
            self.assertIn("status = 'running'", sql)
            self.assertIn("lease_expires_at > now()", sql)
            self.assertIn(
                "attempted_documents = CASE WHEN %s THEN 1 ELSE attempted_documents END",
                sql,
            )
            self.assertEqual(params[-2:], ("row-1", "worker-1"))

        self.assertEqual(
            waiting_db.calls[0][1],
            ("dns_failure: retry later", False, False, "row-1", "worker-1"),
        )
        self.assertEqual(
            failed_db.calls[0][1],
            (
                "proposition_provider_failure: rolled back",
                True,
                True,
                "row-1",
                "worker-1",
            ),
        )

    def test_lease_reaper_counts_attempt_only_after_writer_boundary(self):
        db = RecordingDb(results=[[]])

        reap_expired_leases(db)

        sql, params = db.calls[0]
        self.assertIn(
            "attempted_documents = CASE WHEN stage IN ('writing', 'finalizing') THEN 1 ELSE attempted_documents END",
            sql,
        )
        self.assertEqual(params, None)

    def test_complete_validates_before_owned_terminal_update(self):
        outcome = ProcessOutcome(
            status="processed",
            reason=None,
            document_id="doc-1",
            attempted=1,
            stored=1,
            skipped=0,
            errored=0,
        )
        db = RecordingDb(results=[{"id": "row-1"}])

        self.assertTrue(
            complete(
                db,
                "row-1",
                "worker-1",
                outcome,
                final_url="https://example.com/final.pdf",
                content_sha256="abc123",
                fetched_bytes=9,
            )
        )
        sql, params = db.calls[0]
        self.assertIn("status = 'done'", sql)
        self.assertIn("result_document_id = %s", sql)
        self.assertIn("attempted_documents = %s", sql)
        self.assertIn("id = %s", sql)
        self.assertIn("worker_id = %s", sql)
        self.assertIn("status = 'running'", sql)
        self.assertIn("lease_expires_at > now()", sql)
        self.assertEqual(params[-2:], ("row-1", "worker-1"))

        invalid = ProcessOutcome(
            status="processed",
            reason=None,
            document_id="doc-1",
            attempted=1,
            stored=0,
            skipped=0,
            errored=0,
        )
        untouched = RecordingDb()
        with self.assertRaises(ValueError):
            complete(
                untouched,
                "row-1",
                "worker-1",
                invalid,
                final_url="https://example.com/final.pdf",
                content_sha256="abc123",
                fetched_bytes=9,
            )
        self.assertEqual(untouched.calls, [])

    def test_reaper_requeues_or_fails_without_claiming(self):
        db = RecordingDb(results=[[{"id": "row-1"}, {"id": "row-2"}]])

        self.assertEqual(reap_expired_leases(db), 2)
        sql, params = db.calls[0]
        self.assertIn("attempts = attempts + 1", sql)
        self.assertIn("attempts + 1 >= max_attempts", sql)
        self.assertIn("attempted_documents = CASE", sql)
        self.assertIn("errored_documents = CASE", sql)
        self.assertIn("lease_expires_at < now()", sql)
        self.assertNotIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertEqual(params, None)


if __name__ == "__main__":
    unittest.main()
