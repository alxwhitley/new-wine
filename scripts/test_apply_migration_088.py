#!/usr/bin/env python3
"""Fail-closed tests for the unapplied migration 088 operations tool."""

import json
import stat
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

import apply_migration_088


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
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return RecordingCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def valid_schema_results(*, retention_definition="CHECK ((retain_original_text = true))"):
    columns = [
        ("retain_original_text", "boolean", "NO", "true"),
        ("attempts", "integer", "NO", "0"),
        ("max_attempts", "integer", "NO", "3"),
        ("worker_id", "text", "YES", None),
        ("lease_expires_at", "timestamp with time zone", "YES", None),
        ("run_after", "timestamp with time zone", "NO", "now()"),
        ("stage", "text", "NO", "'queued'::text"),
        ("final_url", "text", "YES", None),
        ("content_sha256", "text", "YES", None),
        ("fetched_bytes", "bigint", "YES", None),
        ("attempted_documents", "integer", "NO", "0"),
        ("stored_documents", "integer", "NO", "0"),
        ("skipped_documents", "integer", "NO", "0"),
        ("errored_documents", "integer", "NO", "0"),
        ("result_document_id", "uuid", "YES", None),
    ]
    constraints = [
        ("source_ingest_queue_retain_original_text_true", retention_definition),
        ("source_ingest_queue_attempts_nonnegative", "CHECK ((attempts >= 0))"),
        ("source_ingest_queue_max_attempts_positive", "CHECK ((max_attempts > 0))"),
        (
            "source_ingest_queue_counts_nonnegative",
            "CHECK (((attempted_documents >= 0) AND (stored_documents >= 0) "
            "AND (skipped_documents >= 0) AND (errored_documents >= 0)))",
        ),
        (
            "source_ingest_queue_result_document_id_fkey",
            "FOREIGN KEY (result_document_id) REFERENCES documents(id) ON DELETE SET NULL",
        ),
    ]
    indexes = [
        (
            "source_ingest_queue_claim_idx",
            "CREATE INDEX source_ingest_queue_claim_idx ON source_ingest_queue "
            "USING btree (run_after, created_at) WHERE ((status = 'waiting'::text) "
            "AND (cleared_to_run = true))",
        ),
        (
            "source_ingest_queue_lease_idx",
            "CREATE INDEX source_ingest_queue_lease_idx ON source_ingest_queue "
            "USING btree (lease_expires_at) WHERE (status = 'running'::text)",
        ),
    ]
    policies = [
        ("source_ingest_queue: own rows read",),
        ("source_ingest_queue: own row insert",),
        ("source_ingest_queue: service role full access",),
    ]
    return [columns, constraints, indexes, (True,), policies, (7,), (0,)]


class ApplyGateTests(unittest.TestCase):
    def test_main_without_apply_exits_before_connection(self):
        connections = []

        result = apply_migration_088.main(
            [], connect_fn=lambda: connections.append(True)
        )

        self.assertEqual(result, 2)
        self.assertEqual(connections, [])

    def test_main_rejects_symlinked_review_root_before_connection(self):
        connections = []
        with tempfile.TemporaryDirectory() as temp_dir:
            real_root = Path(temp_dir) / "real-review"
            real_root.mkdir()
            linked_root = Path(temp_dir) / "linked-review"
            linked_root.symlink_to(real_root, target_is_directory=True)

            with self.assertRaises(ValueError):
                apply_migration_088.main(
                    ["--apply"],
                    connect_fn=lambda: connections.append(True),
                    review_root=linked_root,
                )

        self.assertEqual(connections, [])


class SnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_uuid_and_true_false_null_exactly(self):
        rows = [
            (uuid.UUID("11111111-1111-1111-1111-111111111111"), True),
            (uuid.UUID("22222222-2222-2222-2222-222222222222"), False),
            (uuid.UUID("33333333-3333-3333-3333-333333333333"), None),
        ]
        connection = RecordingConnection(results=[rows])

        snapshot = apply_migration_088._snapshot_rows(connection)

        self.assertEqual(
            snapshot,
            [
                {"id": "11111111-1111-1111-1111-111111111111", "retain_original_text": True},
                {"id": "22222222-2222-2222-2222-222222222222", "retain_original_text": False},
                {"id": "33333333-3333-3333-3333-333333333333", "retain_original_text": None},
            ],
        )
        self.assertEqual(
            connection.calls,
            [
                (
                    "SELECT id, retain_original_text FROM source_ingest_queue ORDER BY id",
                    None,
                )
            ],
        )

    def test_write_snapshot_is_private_inside_review_root_and_contains_no_secrets(self):
        rows = [
            {"id": "11111111-1111-1111-1111-111111111111", "retain_original_text": None}
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            review_root = Path(temp_dir) / "source_ingest_runner_review"
            review_root.mkdir()
            path = review_root / "retention-before.json"

            apply_migration_088._write_snapshot(
                rows, path, review_root=review_root
            )

            self.assertEqual(json.loads(path.read_text()), rows)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("password", path.read_text().lower())
            self.assertNotIn("database", path.read_text().lower())

    def test_snapshot_path_rejects_empty_root_outside_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "review"
            root.mkdir()
            outside = Path(temp_dir) / "outside.json"
            link = root / "escape.json"
            link.symlink_to(outside)

            for path in (Path(""), root, outside, link):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        apply_migration_088._validate_snapshot_path(
                            path, review_root=root
                        )

            real_root = Path(temp_dir) / "real-review"
            real_root.mkdir()
            linked_root = Path(temp_dir) / "linked-review"
            linked_root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaises(ValueError):
                apply_migration_088._validate_snapshot_path(
                    linked_root / "snapshot.json", review_root=linked_root
                )

    def test_write_snapshot_rejects_unexpected_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_root = Path(temp_dir) / "review"
            review_root.mkdir()
            path = review_root / "snapshot.json"

            with self.assertRaises(ValueError):
                apply_migration_088._write_snapshot(
                    [
                        {
                            "id": "11111111-1111-1111-1111-111111111111",
                            "retain_original_text": True,
                            "password": "must never be written",
                        }
                    ],
                    path,
                    review_root=review_root,
                )

            self.assertFalse(path.exists())

    def test_restore_uses_one_parameterized_update_per_snapshotted_row(self):
        rows = [
            {"id": "11111111-1111-1111-1111-111111111111", "retain_original_text": False},
            {"id": "22222222-2222-2222-2222-222222222222", "retain_original_text": None},
        ]
        connection = RecordingConnection()

        apply_migration_088._restore_retention_values(connection, rows)

        self.assertEqual(len(connection.calls), 2)
        for sql, _params in connection.calls:
            self.assertIn(
                "UPDATE source_ingest_queue SET retain_original_text = %s WHERE id = %s",
                sql,
            )
        self.assertEqual(
            [params for _sql, params in connection.calls],
            [
                (False, "11111111-1111-1111-1111-111111111111"),
                (None, "22222222-2222-2222-2222-222222222222"),
            ],
        )


class FixtureCleanupTests(unittest.TestCase):
    def test_cleanup_validates_exact_uuid_and_marker_before_delete(self):
        fixture_id = "44444444-4444-4444-4444-444444444444"
        marker = "https://example.invalid/rhemata-source-ingest-fixture/44444444"
        connection = RecordingConnection(results=[(fixture_id, marker), (fixture_id,)])

        self.assertTrue(
            apply_migration_088._cleanup_fixture(connection, fixture_id, marker)
        )

        self.assertEqual(len(connection.calls), 2)
        self.assertIn("SELECT id, url FROM source_ingest_queue WHERE id = %s", connection.calls[0][0])
        self.assertIn("DELETE FROM source_ingest_queue WHERE id = %s AND url = %s", connection.calls[1][0])
        self.assertEqual(connection.calls[1][1], (fixture_id, marker))

    def test_cleanup_refuses_invalid_or_mismatched_target(self):
        untouched = RecordingConnection()
        with self.assertRaises(ValueError):
            apply_migration_088._cleanup_fixture(
                untouched, "not-a-uuid", "https://example.invalid/fixture"
            )
        self.assertEqual(untouched.calls, [])

        mismatch = RecordingConnection(
            results=[
                (
                    "44444444-4444-4444-4444-444444444444",
                    "https://example.invalid/different",
                )
            ]
        )
        with self.assertRaises(RuntimeError):
            apply_migration_088._cleanup_fixture(
                mismatch,
                "44444444-4444-4444-4444-444444444444",
                "https://example.invalid/rhemata-source-ingest-fixture/44444444",
            )
        self.assertEqual(len(mismatch.calls), 1)


class SchemaVerificationTests(unittest.TestCase):
    def test_verifies_columns_constraints_indexes_rls_policies_and_counts(self):
        connection = RecordingConnection(results=valid_schema_results())

        report = apply_migration_088._verify_schema(connection, expected_count=7)

        self.assertEqual(report["queue_count"], 7)
        self.assertEqual(report["retention_not_true"], 0)
        self.assertEqual(report["indexes"], 2)

    def test_verification_fails_closed_on_count_change(self):
        connection = RecordingConnection(
            results=[[], [], [], (True,), [], (8,), (0,)]
        )
        with self.assertRaises(RuntimeError):
            apply_migration_088._verify_schema(connection, expected_count=7)

    def test_verification_rejects_correctly_named_but_wrong_constraint(self):
        connection = RecordingConnection(
            results=valid_schema_results(
                retention_definition="CHECK ((retain_original_text = false))"
            )
        )

        with self.assertRaises(RuntimeError):
            apply_migration_088._verify_schema(connection, expected_count=7)

    def test_verification_rejects_lookalike_numeric_default(self):
        results = valid_schema_results()
        results[0][1] = ("attempts", "integer", "NO", "10")
        connection = RecordingConnection(results=results)

        with self.assertRaises(RuntimeError):
            apply_migration_088._verify_schema(connection, expected_count=7)


class FullApplyFlowTests(unittest.TestCase):
    def test_apply_snapshots_then_uses_fresh_apply_and_verify_connections(self):
        rows = [
            (uuid.UUID("11111111-1111-1111-1111-111111111111"), None),
            (uuid.UUID("22222222-2222-2222-2222-222222222222"), False),
        ]
        preflight = RecordingConnection(results=[rows])
        apply_connection = RecordingConnection(results=[None])
        verify_connection = RecordingConnection()
        connections = [preflight, apply_connection, verify_connection]
        verify_calls = []
        claim_calls = []

        def connect():
            return connections.pop(0)

        with tempfile.TemporaryDirectory() as temp_dir:
            review_root = Path(temp_dir) / "source_ingest_runner_review"
            review_root.mkdir()
            snapshot_path = review_root / "before.json"
            result = apply_migration_088.main(
                ["--apply", "--snapshot", str(snapshot_path)],
                connect_fn=connect,
                review_root=review_root,
                verify_fn=lambda conn, count: (
                    verify_calls.append((conn, count))
                    or {"queue_count": count, "retention_not_true": 0, "indexes": 2}
                ),
                claim_verify_fn=lambda factory: (
                    claim_calls.append(factory)
                    or {
                        "attempted": 1,
                        "claimed": 1,
                        "double_claimed": 0,
                        "cleaned": 1,
                    }
                ),
            )

            self.assertEqual(result, 0)
            self.assertEqual(len(json.loads(snapshot_path.read_text())), 2)

        self.assertEqual(connections, [])
        self.assertTrue(preflight.closed)
        self.assertTrue(apply_connection.closed)
        self.assertTrue(verify_connection.closed)
        self.assertEqual(apply_connection.commits, 1)
        self.assertIn(
            "UPDATE source_ingest_queue SET retain_original_text = true",
            apply_connection.calls[0][0],
        )
        self.assertEqual(verify_calls, [(verify_connection, 2)])
        self.assertEqual(len(claim_calls), 1)


class ConcurrentClaimVerificationTests(unittest.TestCase):
    def test_two_claimers_are_scoped_to_one_fixture_and_cleanup_reconciles(self):
        fixture_id = "55555555-5555-5555-5555-555555555555"
        user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        marker = "https://example.invalid/rhemata-source-ingest-fixture/55555555"
        setup = RecordingConnection(
            results=[(0,), (user_id,), None, (fixture_id,)]
        )
        claimer_one = RecordingConnection()
        claimer_two = RecordingConnection()
        cleanup = RecordingConnection(
            results=[(fixture_id, marker), (fixture_id,)]
        )
        connections = [setup, claimer_one, claimer_two, cleanup]
        claim_calls = []
        claim_lock = threading.Lock()
        won = []

        def connect():
            return connections.pop(0)

        def claim(db, worker_id, lease_seconds, *, only_row_id=None):
            with claim_lock:
                claim_calls.append((db, worker_id, lease_seconds, only_row_id))
                if not won:
                    won.append(worker_id)
                    return {"id": only_row_id, "worker_id": worker_id}
                return None

        report = apply_migration_088._verify_concurrent_claim(
            connect,
            claim_fn=claim,
            uuid_fn=lambda: uuid.UUID(fixture_id),
        )

        self.assertEqual(
            report,
            {"attempted": 1, "claimed": 1, "double_claimed": 0, "cleaned": 1},
        )
        self.assertEqual(connections, [])
        self.assertEqual(len(claim_calls), 2)
        self.assertEqual({call[3] for call in claim_calls}, {fixture_id})
        self.assertEqual({call[2] for call in claim_calls}, {60})
        self.assertTrue(all(connection.closed for connection in (setup, claimer_one, claimer_two, cleanup)))
        self.assertEqual(setup.commits, 1)
        self.assertEqual(cleanup.commits, 1)
        self.assertIn("cleared_to_run = true", setup.calls[0][0])
        self.assertIn("status = 'running'", setup.calls[0][0])
        self.assertIn("INSERT INTO source_ingest_queue", setup.calls[2][0])
        self.assertIn("cleared_to_run = true", setup.calls[3][0])
        self.assertEqual(setup.calls[3][1], (fixture_id, marker))

    def test_refuses_fixture_write_when_any_other_work_is_active(self):
        setup = RecordingConnection(results=[(1,)])
        connections = [setup]

        with self.assertRaises(RuntimeError):
            apply_migration_088._verify_concurrent_claim(
                lambda: connections.pop(0),
                claim_fn=lambda *args, **kwargs: self.fail("claim should not run"),
                uuid_fn=lambda: uuid.uuid4(),
            )

        self.assertEqual(len(setup.calls), 1)
        self.assertIn("cleared_to_run = true", setup.calls[0][0])
        self.assertIn("status = 'running'", setup.calls[0][0])
        self.assertTrue(setup.closed)

    def test_connection_failure_after_fixture_commit_still_cleans_exact_fixture(self):
        fixture_id = "66666666-6666-6666-6666-666666666666"
        user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        marker = "https://example.invalid/rhemata-source-ingest-fixture/66666666"
        setup = RecordingConnection(results=[(0,), (user_id,), None, (fixture_id,)])
        first_claimer = RecordingConnection()
        cleanup = RecordingConnection(results=[(fixture_id, marker), (fixture_id,)])
        calls = 0

        def connect():
            nonlocal calls
            calls += 1
            if calls == 1:
                return setup
            if calls == 2:
                return first_claimer
            if calls == 3:
                raise OSError("second claim connection unavailable")
            if calls == 4:
                return cleanup
            self.fail("unexpected connection request")

        with self.assertRaises(OSError):
            apply_migration_088._verify_concurrent_claim(
                connect,
                claim_fn=lambda *args, **kwargs: self.fail("claim should not run"),
                uuid_fn=lambda: uuid.UUID(fixture_id),
            )

        self.assertEqual(calls, 4)
        self.assertTrue(first_claimer.closed)
        self.assertTrue(cleanup.closed)
        self.assertEqual(cleanup.commits, 1)
        self.assertEqual(cleanup.calls[1][1], (fixture_id, marker))


if __name__ == "__main__":
    unittest.main()
