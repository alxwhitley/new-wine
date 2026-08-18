#!/usr/bin/env python3
"""Unit tests for resolve_quote presentation fields (Task 7).

DB-free FakeDb. Run: python3 scripts/test_quote_resolve_presentation.py
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import quotes

failures = []
PRINCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"


def check(label: str, cond: bool, detail: str | None = None) -> None:
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)
        if detail:
            print("         %s" % detail)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._rows = list(db.tables.get(table_name, []))
        self._limit = None

    def select(self, _cols):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self._rows if self._limit is None else self._rows[: self._limit]
        return _FakeResult(rows)


class FakeDb:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _FakeQuery(self, name)


def main() -> int:
    print("\nresolve_quote presentation fields")
    print("=" * 60)

    print("\n1. restated_point_from_note:")
    note = (
        "Fasting humbles the soul before God.\n\n"
        "[why_quotable: standalone claim | prompt=quote_propose_v1 | pipeline=quote_quality_v1]"
    )
    check(
        "strips why trailer",
        quotes._restated_point_from_note(note) == "Fasting humbles the soul before God.",
    )
    check("empty -> None", quotes._restated_point_from_note("") is None)
    check("plain note kept", quotes._restated_point_from_note("Just a note.") == "Just a note.")

    print("\n2. resolve_quote payload:")
    db = FakeDb()
    db.tables["quotes"] = [
        {
            "id": "q1",
            "quote_text": "A verified excerpt.",
            "topic": "Fasting and Prayer",
            "topic_ids": ["Fasting and Prayer", "Spiritual Disciplines"],
            "reviewer_note": note,
            "teacher_source_id": PRINCE_ID,
            "status": "approved",
            "approved_at": "2026-08-19T00:00:00+00:00",
            "source_revision_id": "rev-1",
        }
    ]
    db.tables["quote_source_revisions"] = [
        {"id": "rev-1", "chunk_id": "chunk-1", "passage_text": "full", "captured_by": "u"}
    ]
    db.tables["chunks"] = [
        {"id": "chunk-1", "document_id": "doc-1", "content": "full"}
    ]
    db.tables["documents"] = [
        {"id": "doc-1", "title": "A Call To Corporate Fasting", "source_id": PRINCE_ID}
    ]

    resolved = quotes.resolve_quote(db, "q1")
    check("resolved", resolved is not None)
    assert resolved is not None
    check("teacher_name", resolved.get("teacher_name") == "Derek Prince", repr(resolved.get("teacher_name")))
    check("work_title", resolved.get("work_title") == "A Call To Corporate Fasting")
    check("topic", resolved.get("topic") == "Fasting and Prayer")
    check("topic_ids", resolved.get("topic_ids") == ["Fasting and Prayer", "Spiritual Disciplines"])
    check(
        "restated_point",
        resolved.get("restated_point") == "Fasting humbles the soul before God.",
    )

    print("\n3. pending/draft not resolved:")
    db.tables["quotes"][0]["status"] = "pending"
    check("pending -> None", quotes.resolve_quote(db, "q1") is None)

    print()
    if failures:
        print("%d check(s) failed" % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
