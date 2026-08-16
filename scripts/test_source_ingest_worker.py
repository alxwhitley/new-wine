#!/usr/bin/env python3
"""Deterministic orchestration checks for the source-ingest worker."""

import threading
import unittest
from types import SimpleNamespace

import source_ingest_worker
from source_ingest_queue.processor import AttentionRequired, RetryableIngestError


class FakeDb:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeJobs:
    def __init__(self, claims=()):
        self.claims = list(claims)
        self.calls = []
        self.stage_results = []

    def claim_next(self, db, worker_id, lease_seconds):
        self.calls.append(("claim", db, worker_id, lease_seconds))
        if not self.claims:
            return None
        claim = self.claims.pop(0)
        if isinstance(claim, Exception):
            raise claim
        return claim

    def set_stage(self, db, row_id, worker_id, stage):
        self.calls.append(("stage", row_id, worker_id, stage))
        return self.stage_results.pop(0) if self.stage_results else True

    def complete(self, db, row_id, worker_id, outcome, **kwargs):
        self.calls.append(("complete", row_id, worker_id, outcome, kwargs))
        return True

    def needs_attention(self, db, row_id, worker_id, code, detail):
        self.calls.append(("attention", row_id, worker_id, code, detail))
        return True

    def fail_or_requeue(
        self, db, row_id, worker_id, code, detail, *, attempted
    ):
        self.calls.append(
            ("fail", row_id, worker_id, code, detail, attempted)
        )
        return "waiting"

    def get_row(self, db, row_id, *, read_only=False):
        self.calls.append(("get", row_id, read_only))
        return {"id": row_id, "url": "https://example.com/doc.pdf"}


class FakeHeartbeat:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.lost = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def prepared():
    return SimpleNamespace(
        final_url="https://example.com/final.pdf?private=query",
        content_sha256="abc123",
        fetched_bytes=9,
        source_id="source-1",
        page_count=3,
        chunk_count=2,
        duplicate=False,
    )


def outcome():
    return SimpleNamespace(
        status="processed",
        reason=None,
        document_id="doc-1",
        attempted=1,
        stored=1,
        skipped=0,
        errored=0,
    )


class WorkerTickTests(unittest.TestCase):
    def setUp(self):
        FakeHeartbeat.instances = []

    def worker(self, jobs, prepare_fn=None, execute_fn=None):
        return source_ingest_worker.Worker(
            db_factory=FakeDb,
            supabase_factory=lambda: "supabase",
            prepare_fn=prepare_fn or (lambda row, **kwargs: prepared()),
            execute_fn=execute_fn or (lambda value, **kwargs: outcome()),
            jobs_api=jobs,
            db_params_factory=lambda: {"dbname": "test"},
            heartbeat_factory=FakeHeartbeat,
            worker_id="worker-1",
            poll_interval=0,
            once=True,
        )

    def test_no_claim_returns_false_without_processor_calls(self):
        jobs = FakeJobs()
        worker = self.worker(
            jobs,
            prepare_fn=lambda *args, **kwargs: self.fail("no claim called processor"),
        )

        self.assertFalse(worker.tick())
        self.assertEqual([call[0] for call in jobs.calls], ["claim"])
        self.assertEqual(FakeHeartbeat.instances, [])

    def test_success_claims_stages_processes_and_completes_after_heartbeat_stop(self):
        jobs = FakeJobs(claims=[{"id": "row-1"}])
        boundaries = []

        def prepare_fn(row, **kwargs):
            boundaries.append(("prepare", row, kwargs))
            return prepared()

        def execute_fn(value, **kwargs):
            boundaries.append(("execute", value, kwargs))
            return outcome()

        worker = self.worker(jobs, prepare_fn=prepare_fn, execute_fn=execute_fn)

        self.assertTrue(worker.tick())
        self.assertEqual(
            [call[0] if call[0] != "stage" else call[3] for call in jobs.calls],
            ["claim", "fetching", "writing", "finalizing", "complete"],
        )
        self.assertEqual([item[0] for item in boundaries], ["prepare", "execute"])
        self.assertFalse(boundaries[0][2]["dry_run"])
        self.assertEqual(boundaries[0][2]["db"], "supabase")
        self.assertEqual(boundaries[0][2]["db_params"], {"dbname": "test"})
        self.assertEqual(len(FakeHeartbeat.instances), 1)
        self.assertTrue(FakeHeartbeat.instances[0].started)
        self.assertTrue(FakeHeartbeat.instances[0].stopped)
        complete_call = jobs.calls[-1]
        self.assertEqual(complete_call[4]["final_url"], prepared().final_url)
        self.assertEqual(complete_call[4]["content_sha256"], "abc123")
        self.assertEqual(complete_call[4]["fetched_bytes"], 9)

    def test_attention_and_retryable_errors_route_to_distinct_terminals(self):
        cases = (
            (
                AttentionRequired("source_unresolved", "operator action"),
                "attention",
                "source_unresolved",
                None,
            ),
            (
                RetryableIngestError(
                    "proposition_provider_failure", "rolled back", attempted=True
                ),
                "fail",
                "proposition_provider_failure",
                True,
            ),
        )

        for error, terminal, code, attempted in cases:
            with self.subTest(code=code):
                jobs = FakeJobs(claims=[{"id": "row-1"}])

                def raise_error(row, **kwargs):
                    raise error

                worker = self.worker(jobs, prepare_fn=raise_error)
                self.assertTrue(worker.tick())
                terminal_call = jobs.calls[-1]
                self.assertEqual(terminal_call[0], terminal)
                self.assertEqual(terminal_call[3], code)
                if attempted is not None:
                    self.assertEqual(terminal_call[-1], attempted)
                self.assertTrue(FakeHeartbeat.instances[-1].stopped)

    def test_unknown_processor_error_requeues_without_exposing_detail(self):
        jobs = FakeJobs(claims=[{"id": "row-1"}])

        def raise_unknown(row, **kwargs):
            raise RuntimeError("private source text")

        worker = self.worker(jobs, prepare_fn=raise_unknown)

        self.assertTrue(worker.tick())
        terminal_call = jobs.calls[-1]
        self.assertEqual(terminal_call[0], "fail")
        self.assertEqual(terminal_call[3], "internal_error")
        self.assertNotIn("private source text", terminal_call[4])
        self.assertFalse(terminal_call[5])

    def test_ownership_loss_stops_before_processor_or_completion(self):
        jobs = FakeJobs(claims=[{"id": "row-1"}])
        jobs.stage_results = [False]
        worker = self.worker(
            jobs,
            prepare_fn=lambda *args, **kwargs: self.fail("stale worker processed"),
        )

        self.assertTrue(worker.tick())
        self.assertEqual(
            [call[0] if call[0] != "stage" else call[3] for call in jobs.calls],
            ["claim", "fetching"],
        )
        self.assertTrue(FakeHeartbeat.instances[0].stopped)

    def test_loop_survives_one_claim_fault_and_continues_to_idle(self):
        jobs = FakeJobs(claims=[RuntimeError("pooler dropped")])
        worker = self.worker(jobs)

        worker.run()

        self.assertGreaterEqual(len(jobs.calls), 2)
        self.assertEqual(jobs.calls[0][0], "claim")
        self.assertEqual(jobs.calls[1][0], "claim")


class DryRunTests(unittest.TestCase):
    def test_dry_run_reads_without_claim_or_transition_and_redacts_query(self):
        jobs = FakeJobs()
        prepare_calls = []
        worker = source_ingest_worker.Worker(
            db_factory=FakeDb,
            supabase_factory=lambda: "supabase",
            prepare_fn=lambda row, **kwargs: (
                prepare_calls.append((row, kwargs)) or prepared()
            ),
            execute_fn=lambda *args, **kwargs: self.fail("dry run called writer"),
            jobs_api=jobs,
            db_params_factory=lambda: {"dbname": "test"},
            heartbeat_factory=FakeHeartbeat,
            worker_id="worker-1",
        )

        summary = worker.dry_run_row("row-1")

        self.assertEqual(jobs.calls, [("get", "row-1", True)])
        self.assertTrue(prepare_calls[0][1]["dry_run"])
        self.assertEqual(summary["final_url"], "https://example.com/final.pdf")
        self.assertNotIn("private", repr(summary))
        self.assertEqual(summary["source_id"], "source-1")
        self.assertEqual(summary["page_count"], 3)
        self.assertEqual(summary["chunk_count"], 2)


class HeartbeatTests(unittest.TestCase):
    def test_default_heartbeat_uses_own_db_and_marks_ownership_loss(self):
        called = threading.Event()
        databases = []

        class Jobs:
            @staticmethod
            def heartbeat(db, row_id, worker_id, lease_seconds):
                self.assertIs(db, databases[0])
                self.assertEqual((row_id, worker_id, lease_seconds), ("row-1", "worker-1", 30))
                called.set()
                return False

        def db_factory():
            database = FakeDb()
            databases.append(database)
            return database

        heartbeat = source_ingest_worker._LeaseHeartbeat(
            db_factory=db_factory,
            jobs_api=Jobs,
            row_id="row-1",
            worker_id="worker-1",
            lease_seconds=30,
            interval_seconds=0.01,
        )

        heartbeat.start()
        self.assertTrue(called.wait(1.0))
        heartbeat.stop()

        self.assertTrue(heartbeat.lost)
        self.assertEqual(len(databases), 1)
        self.assertTrue(databases[0].closed)


if __name__ == "__main__":
    unittest.main()
