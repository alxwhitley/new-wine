#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/occurrences.py.
Uses fake Db/cursor/connection objects -- no real database.

Run: python3.12 scripts/test_analytics_occurrences.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if condition else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if condition:
        _pass += 1
    else:
        _fail += 1


class _FakeCursor:
    """Mimics a RealDictCursor over an in-memory search_occurrences table,
    just enough for occurrences.py's INSERT ... ON CONFLICT / SELECT shape."""

    def __init__(self, rows_by_submission_id):
        self._rows = rows_by_submission_id  # dict[submission_id] -> row dict
        self._last_result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        q = " ".join(query.split())
        if q.startswith("INSERT INTO search_occurrences"):
            submission_id = params[0]
            if submission_id in self._rows:
                self._last_result = None  # ON CONFLICT DO NOTHING -> no row returned
            else:
                row = {
                    "id": "occurrence-%s" % submission_id,
                    "submission_id": submission_id,
                }
                self._rows[submission_id] = row
                self._last_result = row
        elif q.startswith("SELECT id FROM search_occurrences WHERE submission_id"):
            submission_id = params[0]
            row = self._rows.get(submission_id)
            self._last_result = {"id": row["id"]} if row else None
        else:
            raise AssertionError("unexpected query: %s" % q)

    def fetchone(self):
        return self._last_result


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _FakeDb:
    def __init__(self):
        self._rows = {}
        self._cursor = _FakeCursor(self._rows)

    def run(self, fn):
        return fn(_FakeConnection(self._cursor))


class _AlwaysFailsDb:
    def run(self, fn):
        raise RuntimeError("simulated durable-write failure")


def main() -> int:
    from app.services.search_analytics.occurrences import (
        create_occurrence, fingerprint_question, OccurrenceWriteFailedError,
    )

    db = _FakeDb()
    occ_id_1 = create_occurrence(
        db, submission_id="sub-1", job_id="job-A", origin="user",
        subject_key="subject-x", subject_key_version=1, question="What is deliverance?",
    )
    occ_id_1_retry = create_occurrence(
        db, submission_id="sub-1", job_id="job-A", origin="user",
        subject_key="subject-x", subject_key_version=1, question="What is deliverance?",
    )
    check("a repeated submission_id returns the SAME occurrence id (idempotent retry)",
          occ_id_1 == occ_id_1_retry)

    occ_id_2 = create_occurrence(
        db, submission_id="sub-2", job_id="job-A", origin="user",
        subject_key="subject-y", subject_key_version=1, question="What is deliverance?",
    )
    check("two different submission_ids sharing one job_id create two distinct occurrences",
          occ_id_1 != occ_id_2)

    fp_a = fingerprint_question("subject-x", "What is deliverance?")
    fp_b = fingerprint_question("subject-x", "what is deliverance?")
    check("question fingerprint normalizes case/whitespace like jobs.py's dedup key", fp_a == fp_b)
    check("fingerprint does not contain the raw question text", "deliverance" not in fp_a.lower())

    raised = False
    try:
        create_occurrence(
            _AlwaysFailsDb(), submission_id="sub-3", job_id="job-B", origin="user",
            subject_key="subject-z", subject_key_version=1, question="What is deliverance?",
        )
    except OccurrenceWriteFailedError:
        raised = True
    check("a durable-write failure raises OccurrenceWriteFailedError (caller returns a retryable error)",
          raised)

    admin_occ = create_occurrence(
        db, submission_id="sub-retest-1", job_id="job-C", origin="admin_retest",
        subject_key=None, subject_key_version=None, question="What is deliverance?",
    )
    check("an admin_retest occurrence can be created with no subject_key", bool(admin_occ))

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
