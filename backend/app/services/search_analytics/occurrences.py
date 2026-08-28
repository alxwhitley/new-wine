"""Idempotent search-occurrence creation for the async answer path's
/submit route.

One occurrence per accepted submission -- created AFTER jobs.enqueue()
returns, since it needs a real job_id. A retried request carrying the
same submission_id returns the SAME occurrence (INSERT ... ON CONFLICT
DO NOTHING, fall back to SELECT), the same idempotency shape
async_answers/jobs.py's enqueue() already uses for answer_jobs itself --
reused here, not reinvented. Two different submission_ids that happen to
share one answer_jobs row (single-flight/reuse collapse) always produce
two distinct occurrence rows, because submission_id -- not job_id -- is
the occurrence's own identity key.

A failure to durably record the occurrence for a consented account must
never be swallowed -- OccurrenceWriteFailedError propagates so the caller
(async_chat.py's /submit) can return a retryable error rather than
silently accepting an unmonitored beta search.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import hashlib
from typing import Optional

from app.services.async_answers.db import dict_cursor


class OccurrenceWriteFailedError(Exception):
    """The occurrence could not be durably recorded. Callers with a
    consented account must surface this as a retryable error, never
    accept the submission silently."""


def fingerprint_question(subject_key: Optional[str], question: str) -> str:
    """Opaque, non-reversible fingerprint of (subject, normalized question).
    Normalization mirrors async_answers/jobs.py's _normalize_question --
    strip + collapse whitespace + lowercase -- so the same question asked
    twice with trivial formatting differences fingerprints identically."""
    normalized = " ".join((question or "").strip().split()).lower()
    blob = "%s:%s" % (subject_key or "", normalized)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def create_occurrence(
    db,
    *,
    submission_id: str,
    job_id: str,
    origin: str,
    subject_key: Optional[str],
    subject_key_version: Optional[int],
    question: str,
) -> str:
    fingerprint = fingerprint_question(subject_key, question)

    def _write(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "INSERT INTO search_occurrences "
                "(submission_id, job_id, origin, subject_key, subject_key_version, question_fingerprint) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (submission_id) DO NOTHING "
                "RETURNING id",
                (submission_id, job_id, origin, subject_key, subject_key_version, fingerprint),
            )
            row = cur.fetchone()
            if row:
                return row["id"]
            cur.execute(
                "SELECT id FROM search_occurrences WHERE submission_id = %s",
                (submission_id,),
            )
            existing = cur.fetchone()
            return existing["id"] if existing else None

    try:
        occurrence_id = db.run(_write)
    except Exception as exc:
        raise OccurrenceWriteFailedError(str(exc)) from exc

    if not occurrence_id:
        raise OccurrenceWriteFailedError(
            "occurrence insert returned no row and no existing row was found for submission_id=%s" % submission_id
        )
    return occurrence_id
