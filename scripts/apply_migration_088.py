#!/usr/bin/env python3
"""Explicitly gated apply and verification tool for migration 088."""

from __future__ import annotations

import argparse
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "088_source_ingest_runner.sql"
REVIEW_ROOT = ROOT / "source_ingest_runner_review"
FIXTURE_PREFIX = "https://example.invalid/rhemata-source-ingest-fixture/"

load_dotenv(ROOT / "backend" / "app" / ".env")


def get_db_conn():
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    parsed = urlparse(db_url)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        dbname=parsed.path.lstrip("/"),
    )


def _snapshot_rows(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, retain_original_text "
            "FROM source_ingest_queue ORDER BY id"
        )
        rows = cursor.fetchall()
    return [
        {"id": str(row[0]), "retain_original_text": row[1]}
        for row in rows
    ]


def _validate_snapshot_path(path: Path, *, review_root: Path = REVIEW_ROOT) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("snapshot path must be absolute")
    if review_root.is_symlink():
        raise ValueError("review root must not be a symbolic link")
    root = review_root.resolve()
    resolved = path.resolve()
    if resolved == root or resolved.parent != root:
        raise ValueError("snapshot path must be directly inside the review root")
    if resolved.suffix != ".json" or not resolved.name:
        raise ValueError("snapshot path must name a JSON file")
    if path.is_symlink() or resolved.exists():
        raise ValueError("snapshot target must be a new regular file")
    return resolved


def _validate_snapshot_rows(rows) -> None:
    if not isinstance(rows, list):
        raise ValueError("snapshot rows must be a list")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "retain_original_text"}:
            raise ValueError("snapshot row contains unexpected fields")
        row_id = str(uuid.UUID(str(row["id"])))
        if row_id != row["id"]:
            raise ValueError("snapshot row UUID must be canonical")
        value = row["retain_original_text"]
        if value is not None and not isinstance(value, bool):
            raise ValueError("snapshot retention value is invalid")


def _write_snapshot(rows, path: Path, *, review_root: Path = REVIEW_ROOT) -> None:
    _validate_snapshot_rows(rows)
    target = _validate_snapshot_path(path, review_root=review_root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(target), flags, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            descriptor = -1
            json.dump(rows, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _restore_retention_values(connection, rows) -> None:
    with connection.cursor() as cursor:
        for row in rows:
            row_id = str(uuid.UUID(str(row["id"])))
            value = row["retain_original_text"]
            if value is not None and not isinstance(value, bool):
                raise ValueError("snapshot retention value is invalid")
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET retain_original_text = %s WHERE id = %s",
                (value, row_id),
            )


def _cleanup_fixture(connection, fixture_id: str, marker_url: str) -> bool:
    canonical_id = str(uuid.UUID(str(fixture_id)))
    if canonical_id != fixture_id:
        raise ValueError("fixture UUID must be canonical")
    if marker_url != FIXTURE_PREFIX + fixture_id.split("-", 1)[0]:
        raise ValueError("fixture marker does not match fixture UUID")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, url FROM source_ingest_queue WHERE id = %s",
            (fixture_id,),
        )
        row = cursor.fetchone()
        if row is None or str(row[0]) != fixture_id or row[1] != marker_url:
            raise RuntimeError("fixture cleanup target does not match")
        cursor.execute(
            "DELETE FROM source_ingest_queue WHERE id = %s AND url = %s "
            "RETURNING id",
            (fixture_id, marker_url),
        )
        deleted = cursor.fetchone()
        if deleted is None or str(deleted[0]) != fixture_id:
            raise RuntimeError("fixture cleanup did not delete exactly its target")
    return True


def _verify_schema(connection, expected_count: int) -> dict:
    def normalized(definition) -> str:
        return " ".join(str(definition or "").lower().split())

    def require_fragments(kind: str, name: str, definition: str, fragments) -> None:
        if any(fragment not in definition for fragment in fragments):
            raise RuntimeError(
                "migration 088 %s definition verification failed: %s"
                % (kind, name)
            )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'source_ingest_queue'"
        )
        columns = {
            row[0]: {"type": row[1], "nullable": row[2], "default": row[3]}
            for row in cursor.fetchall()
        }
        expected_types = {
            "retain_original_text": "boolean",
            "attempts": "integer",
            "max_attempts": "integer",
            "worker_id": "text",
            "lease_expires_at": "timestamp with time zone",
            "run_after": "timestamp with time zone",
            "stage": "text",
            "final_url": "text",
            "content_sha256": "text",
            "fetched_bytes": "bigint",
            "attempted_documents": "integer",
            "stored_documents": "integer",
            "skipped_documents": "integer",
            "errored_documents": "integer",
            "result_document_id": "uuid",
        }
        for name, data_type in expected_types.items():
            if columns.get(name, {}).get("type") != data_type:
                raise RuntimeError("migration 088 column verification failed: %s" % name)
        for name in (
            "retain_original_text",
            "attempts",
            "max_attempts",
            "run_after",
            "stage",
            "attempted_documents",
            "stored_documents",
            "skipped_documents",
            "errored_documents",
        ):
            if columns[name]["nullable"] != "NO":
                raise RuntimeError("migration 088 nullability verification failed: %s" % name)
        for name in (
            "worker_id",
            "lease_expires_at",
            "final_url",
            "content_sha256",
            "fetched_bytes",
            "result_document_id",
        ):
            if columns[name]["nullable"] != "YES":
                raise RuntimeError(
                    "migration 088 nullability verification failed: %s" % name
                )
        expected_defaults = {
            "retain_original_text": "true",
            "attempts": "0",
            "max_attempts": "3",
            "run_after": "now()",
            "stage": "'queued'::text",
            "attempted_documents": "0",
            "stored_documents": "0",
            "skipped_documents": "0",
            "errored_documents": "0",
        }
        for name, expected_default in expected_defaults.items():
            actual_default = normalized(columns[name]["default"])
            if expected_default != actual_default:
                raise RuntimeError(
                    "migration 088 default verification failed: %s" % name
                )
        for name in (
            "worker_id",
            "lease_expires_at",
            "final_url",
            "content_sha256",
            "fetched_bytes",
            "result_document_id",
        ):
            if columns[name]["default"] is not None:
                raise RuntimeError(
                    "migration 088 default verification failed: %s" % name
                )

        cursor.execute(
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'source_ingest_queue'::regclass"
        )
        constraints = {row[0]: normalized(row[1]) for row in cursor.fetchall()}
        expected_constraints = {
            "source_ingest_queue_retain_original_text_true": (
                "check",
                "retain_original_text = true",
            ),
            "source_ingest_queue_attempts_nonnegative": (
                "check",
                "attempts >= 0",
            ),
            "source_ingest_queue_max_attempts_positive": (
                "check",
                "max_attempts > 0",
            ),
            "source_ingest_queue_counts_nonnegative": (
                "check",
                "attempted_documents >= 0",
                "stored_documents >= 0",
                "skipped_documents >= 0",
                "errored_documents >= 0",
            ),
            "source_ingest_queue_result_document_id_fkey": (
                "foreign key (result_document_id)",
                "references documents(id)",
                "on delete set null",
            ),
        }
        for name, fragments in expected_constraints.items():
            definition = constraints.get(name)
            if definition is None:
                raise RuntimeError(
                    "migration 088 constraint verification failed: %s" % name
                )
            require_fragments("constraint", name, definition, fragments)

        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'source_ingest_queue'"
        )
        indexes = {row[0]: normalized(row[1]) for row in cursor.fetchall()}
        expected_indexes = {
            "source_ingest_queue_claim_idx": (
                "(run_after, created_at)",
                "status = 'waiting'",
                "cleared_to_run = true",
            ),
            "source_ingest_queue_lease_idx": (
                "(lease_expires_at)",
                "status = 'running'",
            ),
        }
        for name, fragments in expected_indexes.items():
            definition = indexes.get(name)
            if definition is None:
                raise RuntimeError(
                    "migration 088 index verification failed: %s" % name
                )
            require_fragments("index", name, definition, fragments)

        cursor.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE oid = 'source_ingest_queue'::regclass"
        )
        rls_row = cursor.fetchone()
        if rls_row is None or rls_row[0] is not True:
            raise RuntimeError("source_ingest_queue RLS is not enabled")

        cursor.execute(
            "SELECT policyname FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = 'source_ingest_queue'"
        )
        policies = {row[0] for row in cursor.fetchall()}
        expected_policies = {
            "source_ingest_queue: own rows read",
            "source_ingest_queue: own row insert",
            "source_ingest_queue: service role full access",
        }
        if not expected_policies.issubset(policies):
            raise RuntimeError("source_ingest_queue policy verification failed")

        cursor.execute("SELECT count(*) FROM source_ingest_queue")
        queue_count = int(cursor.fetchone()[0])
        if queue_count != expected_count:
            raise RuntimeError("source_ingest_queue count changed during migration")
        cursor.execute(
            "SELECT count(*) FROM source_ingest_queue "
            "WHERE retain_original_text IS DISTINCT FROM true"
        )
        retention_not_true = int(cursor.fetchone()[0])
        if retention_not_true != 0:
            raise RuntimeError("retention backfill verification failed")

    return {
        "queue_count": queue_count,
        "retention_not_true": retention_not_true,
        "indexes": len(expected_indexes),
    }


def _apply_migration(connection) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(MIGRATION_PATH.read_text())
        connection.commit()
    except Exception:
        connection.rollback()
        raise


class _ConnectionDb:
    def __init__(self, connection):
        self.connection = connection

    def run(self, function):
        try:
            result = function(self.connection)
            self.connection.commit()
            return result
        except Exception:
            self.connection.rollback()
            raise


def _verify_concurrent_claim(connect_fn, *, claim_fn=None, uuid_fn=uuid.uuid4):
    if claim_fn is None:
        from source_ingest_queue.jobs import claim_next

        claim_fn = claim_next

    fixture_id = str(uuid_fn())
    marker_url = FIXTURE_PREFIX + fixture_id.split("-", 1)[0]
    setup = connect_fn()
    fixture_created = False
    try:
        with setup.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM source_ingest_queue "
                "WHERE status = 'running' OR ("
                "status = 'waiting' AND cleared_to_run = true "
                "AND run_after <= now())"
            )
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError(
                    "concurrent claim verification requires no other active work"
                )
            cursor.execute(
                "SELECT id FROM auth.users ORDER BY created_at LIMIT 1"
            )
            user_row = cursor.fetchone()
            if user_row is None:
                raise RuntimeError("concurrent claim verification needs one auth user")
            submitted_by = str(user_row[0])
            cursor.execute(
                "INSERT INTO source_ingest_queue ("
                "id, url, source_format, source_scope, attribute_to, "
                "attribution_mode, on_unknown_author, retain_original_text, "
                "status, cleared_to_run, submitted_by, notes"
                ") VALUES (%s, %s, 'pdf', 'single', %s, 'declared', 'flag', "
                "true, 'waiting', false, %s, %s)",
                (
                    fixture_id,
                    marker_url,
                    "Migration 088 verification fixture",
                    submitted_by,
                    "migration 088 concurrent-claim fixture",
                ),
            )
            fixture_created = True
            cursor.execute(
                "UPDATE source_ingest_queue SET cleared_to_run = true "
                "WHERE id = %s AND url = %s AND cleared_to_run = false "
                "RETURNING id",
                (fixture_id, marker_url),
            )
            armed = cursor.fetchone()
            if armed is None or str(armed[0]) != fixture_id:
                raise RuntimeError("concurrent claim fixture could not be armed")
        setup.commit()
    except Exception:
        setup.rollback()
        raise
    finally:
        setup.close()

    claim_connections = []
    barrier = threading.Barrier(2)
    results = [None, None]
    errors = []
    threads = []
    started_threads = []
    cleaned = 0

    def _claim(index: int) -> None:
        connection = claim_connections[index]
        try:
            barrier.wait(timeout=5.0)
            results[index] = claim_fn(
                _ConnectionDb(connection),
                "migration-088-check-%d" % (index + 1),
                60,
                only_row_id=fixture_id,
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    try:
        for _index in (0, 1):
            claim_connections.append(connect_fn())
        threads = [
            threading.Thread(target=_claim, args=(index,), daemon=True)
            for index in (0, 1)
        ]
        for thread in threads:
            thread.start()
            started_threads.append(thread)
        for thread in threads:
            thread.join(timeout=10.0)

        if any(thread.is_alive() for thread in threads):
            raise RuntimeError(
                "concurrent claim verification threads did not finish; "
                "fixture retained for exact recovery: %s" % fixture_id
            )
        if errors:
            raise RuntimeError("concurrent claim verification worker failed") from errors[0]
    finally:
        started_ids = {id(thread) for thread in started_threads}
        for index, connection in enumerate(claim_connections):
            if index >= len(threads) or id(threads[index]) not in started_ids:
                connection.close()
        threads_stopped = not any(thread.is_alive() for thread in started_threads)
        if fixture_created and threads_stopped:
            cleanup = connect_fn()
            try:
                if _cleanup_fixture(cleanup, fixture_id, marker_url):
                    cleanup.commit()
                    cleaned = 1
            except Exception:
                cleanup.rollback()
                raise
            finally:
                cleanup.close()

    claimed = [
        row for row in results if row is not None and str(row.get("id")) == fixture_id
    ]
    foreign = [
        row for row in results if row is not None and str(row.get("id")) != fixture_id
    ]
    report = {
        "attempted": 1,
        "claimed": len(claimed),
        "double_claimed": max(0, len(claimed) - 1),
        "cleaned": cleaned,
    }
    if foreign or report != {
        "attempted": 1,
        "claimed": 1,
        "double_claimed": 0,
        "cleaned": 1,
    }:
        raise RuntimeError("concurrent claim verification did not reconcile")
    return report


def main(
    argv=None,
    *,
    connect_fn=None,
    review_root: Path = REVIEW_ROOT,
    verify_fn=None,
    claim_verify_fn=None,
) -> int:
    parser = argparse.ArgumentParser(description="Apply and verify migration 088")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="required acknowledgement for the production database write",
    )
    parser.add_argument("--snapshot", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.apply:
        print("REFUSED: migration 088 requires explicit --apply")
        return 2
    if connect_fn is None:
        connect_fn = get_db_conn
    if verify_fn is None:
        verify_fn = _verify_schema
    if claim_verify_fn is None:
        claim_verify_fn = _verify_concurrent_claim

    review_root = Path(review_root)
    if not review_root.is_absolute():
        raise ValueError("review root must be absolute")
    if review_root.is_symlink():
        raise ValueError("review root must not be a symbolic link")
    review_root.mkdir(parents=True, exist_ok=True)
    review_root = review_root.resolve(strict=True)
    snapshot_path = args.snapshot
    if snapshot_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = review_root / ("retention-before-%s.json" % timestamp)

    preflight = connect_fn()
    try:
        snapshot = _snapshot_rows(preflight)
    finally:
        preflight.close()
    _write_snapshot(snapshot, snapshot_path, review_root=review_root)

    apply_connection = connect_fn()
    try:
        _apply_migration(apply_connection)
    finally:
        apply_connection.close()

    verify_connection = connect_fn()
    try:
        schema_report = verify_fn(verify_connection, len(snapshot))
    finally:
        verify_connection.close()

    claim_report = claim_verify_fn(connect_fn)
    print(
        "migration_088 queue_count=%d retention_not_true=%d "
        "attempted=%d claimed=%d double_claimed=%d cleaned=%d"
        % (
            schema_report["queue_count"],
            schema_report["retention_not_true"],
            claim_report["attempted"],
            claim_report["claimed"],
            claim_report["double_claimed"],
            claim_report["cleaned"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
