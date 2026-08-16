"""Transactional lifecycle operations for durable source-ingest jobs."""

from __future__ import annotations

import re
from typing import Optional

from app.services.async_answers.db import dict_cursor


_STAGES = frozenset(
    {
        "claimed",
        "fetching",
        "extracting",
        "resolving",
        "deduplicating",
        "metadata",
        "writing",
        "finalizing",
    }
)


def _reason(reason_code: str, detail: str) -> str:
    code = re.sub(r"[^a-z0-9_]+", "_", (reason_code or "").lower()).strip("_")
    code = code[:80] or "internal_error"
    bounded_detail = " ".join(str(detail or "").split())[:400]
    return "%s: %s" % (code, bounded_detail) if bounded_detail else code


def validate_reconciliation(
    attempted: int,
    stored: int,
    skipped: int,
    errored: int,
    *,
    allow_zero: bool = False,
) -> bool:
    counts = (attempted, stored, skipped, errored)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        return False
    if any(value < 0 for value in counts):
        return False
    if allow_zero and counts == (0, 0, 0, 0):
        return True
    return attempted == 1 and attempted == stored + skipped + errored


def reap_expired_leases(db) -> int:
    """Requeue expired work or fail it when its retry budget is exhausted."""
    def _reap(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET attempts = attempts + 1, "
                "    status = CASE WHEN attempts + 1 >= max_attempts "
                "                  THEN 'failed' ELSE 'waiting' END, "
                "    worker_id = NULL, lease_expires_at = NULL, "
                "    stage = CASE WHEN attempts + 1 >= max_attempts "
                "                 THEN 'failed' ELSE 'queued' END, "
                "    flag_reason = CASE WHEN attempts + 1 >= max_attempts "
                "                       THEN 'lease_expired: retry limit reached' "
                "                       ELSE 'lease_expired: reclaimed' END, "
                "    run_after = now(), "
                "    attempted_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                               THEN 1 ELSE attempted_documents END, "
                "    stored_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                            THEN 0 ELSE stored_documents END, "
                "    skipped_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                             THEN 0 ELSE skipped_documents END, "
                "    errored_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                             THEN 1 ELSE errored_documents END, "
                "    updated_at = now() "
                "WHERE status = 'running' AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at < now() RETURNING id"
            )
            return len(cursor.fetchall())

    return db.run(_reap)


def claim_next(db, worker_id: str, lease_seconds: int) -> Optional[dict]:
    """Reap expired work, then atomically claim one cleared ready row."""
    if not worker_id or isinstance(lease_seconds, bool) or lease_seconds <= 0:
        raise ValueError("worker_id and positive lease_seconds are required")
    reap_expired_leases(db)

    def _claim(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET status = 'running', worker_id = %s, stage = 'claimed', "
                "    flag_reason = NULL, "
                "    lease_expires_at = now() + (%s * interval '1 second'), "
                "    updated_at = now() "
                "WHERE id = ("
                "    SELECT id FROM source_ingest_queue "
                "    WHERE status = 'waiting' AND cleared_to_run = true "
                "      AND run_after <= now() "
                "    ORDER BY created_at "
                "    FOR UPDATE SKIP LOCKED "
                "    LIMIT 1"
                ") RETURNING *",
                (worker_id, lease_seconds),
            )
            return cursor.fetchone()

    return db.run(_claim)


def get_row(db, row_id: str, *, read_only: bool = False) -> Optional[dict]:
    def _get(conn):
        with dict_cursor(conn) as cursor:
            if read_only:
                cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                "SELECT * FROM source_ingest_queue WHERE id = %s", (row_id,)
            )
            return cursor.fetchone()

    return db.run(_get)


def heartbeat(db, row_id: str, worker_id: str, lease_seconds: int) -> bool:
    if isinstance(lease_seconds, bool) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")

    def _heartbeat(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET lease_expires_at = now() + (%s * interval '1 second'), "
                "    updated_at = now() "
                "WHERE id = %s AND worker_id = %s AND status = 'running' "
                "AND lease_expires_at > now() "
                "RETURNING id",
                (lease_seconds, row_id, worker_id),
            )
            return cursor.fetchone() is not None

    return db.run(_heartbeat)


def set_stage(db, row_id: str, worker_id: str, stage: str) -> bool:
    if stage not in _STAGES:
        raise ValueError("unsupported source-ingest stage")

    def _stage(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue SET stage = %s, updated_at = now() "
                "WHERE id = %s AND worker_id = %s AND status = 'running' "
                "AND lease_expires_at > now() "
                "RETURNING id",
                (stage, row_id, worker_id),
            )
            return cursor.fetchone() is not None

    return db.run(_stage)


def needs_attention(
    db,
    row_id: str,
    worker_id: str,
    reason_code: str,
    detail: str,
) -> bool:
    reason = _reason(reason_code, detail)

    def _attention(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET status = 'needs_attention', stage = 'needs_attention', "
                "    flag_reason = %s, worker_id = NULL, lease_expires_at = NULL, "
                "    attempted_documents = 0, stored_documents = 0, "
                "    skipped_documents = 0, errored_documents = 0, "
                "    updated_at = now() "
                "WHERE id = %s AND worker_id = %s AND status = 'running' "
                "AND lease_expires_at > now() "
                "RETURNING id",
                (reason, row_id, worker_id),
            )
            return cursor.fetchone() is not None

    return db.run(_attention)


def fail_or_requeue(
    db,
    row_id: str,
    worker_id: str,
    reason_code: str,
    detail: str,
    *,
    attempted: bool,
) -> Optional[str]:
    if not isinstance(attempted, bool):
        raise ValueError("attempted must be boolean")
    reason = _reason(reason_code, detail)

    def _fail(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET attempts = attempts + 1, "
                "    status = CASE WHEN attempts + 1 >= max_attempts "
                "                  THEN 'failed' ELSE 'waiting' END, "
                "    stage = CASE WHEN attempts + 1 >= max_attempts "
                "                 THEN 'failed' ELSE 'queued' END, "
                "    flag_reason = %s, worker_id = NULL, lease_expires_at = NULL, "
                "    run_after = CASE WHEN attempts + 1 >= max_attempts THEN run_after "
                "                     ELSE now() + (LEAST(300, "
                "                         (power(2, attempts) * 5)::integer) "
                "                         * interval '1 second') END, "
                "    attempted_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                               THEN 1 ELSE attempted_documents END, "
                "    stored_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                            THEN 0 ELSE stored_documents END, "
                "    skipped_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                             THEN 0 ELSE skipped_documents END, "
                "    errored_documents = CASE WHEN attempts + 1 >= max_attempts "
                "                             THEN 1 ELSE errored_documents END, "
                "    updated_at = now() "
                "WHERE id = %s AND worker_id = %s AND status = 'running' "
                "AND lease_expires_at > now() "
                "RETURNING status",
                (reason, row_id, worker_id),
            )
            row = cursor.fetchone()
            return row["status"] if row else None

    return db.run(_fail)


def complete(
    db,
    row_id: str,
    worker_id: str,
    outcome,
    *,
    final_url: str,
    content_sha256: str,
    fetched_bytes: int,
) -> bool:
    if outcome.status not in ("processed", "skipped"):
        raise ValueError("only successful or skipped outcomes can complete")
    if not validate_reconciliation(
        outcome.attempted,
        outcome.stored,
        outcome.skipped,
        outcome.errored,
    ):
        raise ValueError("source-ingest outcome does not reconcile")
    if (
        isinstance(fetched_bytes, bool)
        or not isinstance(fetched_bytes, int)
        or fetched_bytes < 0
    ):
        raise ValueError("fetched_bytes must be nonnegative")

    def _complete(conn):
        with dict_cursor(conn) as cursor:
            cursor.execute(
                "UPDATE source_ingest_queue "
                "SET status = 'done', stage = 'done', flag_reason = %s, "
                "    worker_id = NULL, lease_expires_at = NULL, "
                "    final_url = %s, content_sha256 = %s, fetched_bytes = %s, "
                "    result_document_id = %s, attempted_documents = %s, "
                "    stored_documents = %s, skipped_documents = %s, "
                "    errored_documents = %s, updated_at = now() "
                "WHERE id = %s AND worker_id = %s AND status = 'running' "
                "AND lease_expires_at > now() "
                "RETURNING id",
                (
                    _reason(outcome.reason, "") if outcome.reason else None,
                    final_url,
                    content_sha256,
                    fetched_bytes,
                    outcome.document_id,
                    outcome.attempted,
                    outcome.stored,
                    outcome.skipped,
                    outcome.errored,
                    row_id,
                    worker_id,
                ),
            )
            return cursor.fetchone() is not None

    return db.run(_complete)
