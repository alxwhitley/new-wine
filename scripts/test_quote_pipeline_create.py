#!/usr/bin/env python3
"""Unit tests for quality-pipeline fields on create_and_approve_quote.

DB-free FakeDb. Run: python3 scripts/test_quote_pipeline_create.py
"""
from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import quotes
from app.services.quote_verifier import QuoteVerification

failures = []
PRINCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"
CHUNK_CONTENT = (
    "Prefix sentence ends here. "
    "We're all going to answer to God personally for the lives we've led. "
    "I think it's important to bear that in mind. "
    "Then the teaching continues afterward with more material."
)
# A mid-chunk span that looks like a clean sentence for the fake verifier.
CANDIDATE = (
    "We're all going to answer to God personally for the lives we've led. "
    "I think it's important to bear that in mind."
)


def check(label: str, cond: bool, detail: str | None = None) -> None:
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)
        if detail:
            print("         %s" % detail)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeInsert:
    def __init__(self, row):
        self._row = row

    def execute(self):
        return _FakeResult([self._row])


class _FakeQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._rows = list(db.tables.get(table_name, []))
        self._limit = None
        self._filters = []

    def select(self, _cols):
        return self

    def eq(self, field, value):
        self._filters.append((field, value))
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def neq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) != value]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self._rows
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResult(rows)

    def insert(self, row):
        full = dict(row)
        full.setdefault("id", str(uuid.uuid4()))
        full.setdefault("created_at", self._db.next_timestamp())
        self._db.tables.setdefault(self._table_name, []).append(full)
        return _FakeInsert(full)


class FakeDb:
    def __init__(self):
        self.tables = {}
        self._clock = 0

    def next_timestamp(self):
        self._clock += 1
        return (
            datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self._clock)
        ).isoformat()

    def table(self, name):
        return _FakeQuery(self, name)


@contextmanager
def _noop_lock(*_a, **_k):
    yield


def _seed():
    db = FakeDb()
    db.tables["chunks"] = [
        {"id": "chunk-1", "document_id": "doc-1", "content": CHUNK_CONTENT}
    ]
    db.tables["documents"] = [
        {"id": "doc-1", "source_id": PRINCE_ID, "title": "Fixture"}
    ]
    db.tables["quotes"] = []
    db.tables["quote_source_revisions"] = []
    db.tables["quote_verification_log"] = []
    return db


def main() -> int:
    print("\nquote pipeline create fields")
    print("=" * 60)

    db = _seed()

    def fake_verify(_db, chunk_id, quote_text, teacher_source_id):
        return QuoteVerification(True, None, "accepted")

    with patch.object(quotes, "_creation_lock", _noop_lock), patch.object(
        quotes, "verify_quote_candidate", side_effect=fake_verify
    ), patch.object(quotes, "_enforce_quote_cap", return_value=None), patch.object(
        quotes, "_require_confirmed_teacher", return_value=None
    ):
        row = quotes.create_and_approve_quote(
            db,
            "chunk-1",
            CANDIDATE,
            PRINCE_ID,
            "Fasting and Prayer",
            "Restated point here.",
            "user-1",
            topic_ids=["Fasting and Prayer", "Spiritual Disciplines"],
            quality_pipeline_version=quotes.QUALITY_PIPELINE_VERSION_V1,
            status="pending",
        )

    print("\n1. pending + pipeline fields:")
    check("status pending", row.get("status") == "pending", repr(row.get("status")))
    check("no approved_by", row.get("approved_by") is None)
    check(
        "topic_ids stored",
        row.get("topic_ids") == ["Fasting and Prayer", "Spiritual Disciplines"],
        repr(row.get("topic_ids")),
    )
    check(
        "pipeline version",
        row.get("quality_pipeline_version") == "quote_quality_v1",
        repr(row.get("quality_pipeline_version")),
    )
    check("selection_eligible True", row.get("selection_eligible") is True)
    check("primary topic", row.get("topic") == "Fasting and Prayer")

    print("\n2. default approved path unchanged shape:")
    db2 = _seed()
    with patch.object(quotes, "_creation_lock", _noop_lock), patch.object(
        quotes, "verify_quote_candidate", side_effect=fake_verify
    ), patch.object(quotes, "_enforce_quote_cap", return_value=None), patch.object(
        quotes, "_require_confirmed_teacher", return_value=None
    ):
        row2 = quotes.create_and_approve_quote(
            db2,
            "chunk-1",
            CANDIDATE,
            PRINCE_ID,
            "Faith",
            "note",
            "user-1",
        )
    check("default approved", row2.get("status") == "approved")
    check("approved_by set", row2.get("approved_by") == "user-1")
    check("no pipeline stamp", row2.get("quality_pipeline_version") is None)

    print("\n3. reject bad status:")
    db3 = _seed()
    raised = False
    try:
        with patch.object(quotes, "_creation_lock", _noop_lock), patch.object(
            quotes, "_require_confirmed_teacher", return_value=None
        ):
            quotes.create_and_approve_quote(
                db3,
                "chunk-1",
                CANDIDATE,
                PRINCE_ID,
                "Faith",
                "note",
                "user-1",
                status="draft",
            )
    except ValueError as e:
        raised = "status must be" in str(e)
    check("bad status ValueError", raised)

    print()
    if failures:
        print("%d check(s) failed" % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
