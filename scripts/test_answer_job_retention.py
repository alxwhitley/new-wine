#!/usr/bin/env python3
"""Isolated-fixture proof for backend/app/services/answer_job_retention.py
before any attended production schedule is created (Packet 4, Task 4.4 of
the 2026-08-28 back-to-back completion queue). No real database.

Run: python3.12 scripts/test_answer_job_retention.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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


class _FakeUpdateBuilder:
    def __init__(self, rows, payload):
        self.rows = rows
        self.payload = payload
        self.filters = []

    def lt(self, col, val):
        self.filters.append(("lt", col, val))
        return self

    def neq(self, col, val):
        self.filters.append(("neq", col, val))
        return self

    def execute(self):
        matched = 0
        for r in self.rows:
            ok = True
            for kind, col, val in self.filters:
                if kind == "lt" and not (r.get(col) is not None and r[col] < val):
                    ok = False
                if kind == "neq" and r.get(col) == val:
                    ok = False
            if ok:
                r.update(self.payload)
                matched += 1
        return SimpleNamespace(data=[{} for _ in range(matched)])


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def update(self, payload):
        return _FakeUpdateBuilder(self.rows, payload)


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeTable(self._rows)


def main() -> int:
    from app.services import answer_job_retention as retention

    rows = [
        {  # old enough, has real content -- must be purged
            "id": "job-old", "created_at": "2026-01-01T00:00:00+00:00",
            "question": "What does the Bible say about grace?",
            "answer": "A long real answer.", "messages": [{"role": "user", "content": "earlier turn"}],
            "cost_usd": 0.04,
        },
        {  # too recent -- must be left alone
            "id": "job-recent", "created_at": "2026-08-20T00:00:00+00:00",
            "question": "What is deliverance?",
            "answer": "A recent answer.", "messages": [],
            "cost_usd": 0.03,
        },
        {  # already purged -- must stay untouched (idempotency)
            "id": "job-already-purged", "created_at": "2025-01-01T00:00:00+00:00",
            "question": "[purged]", "answer": None, "messages": [],
            "cost_usd": 0.05,
        },
    ]
    supabase = _FakeSupabase(rows)

    purged = retention.purge_expired_answer_job_content(supabase, now_iso="2026-08-28T00:00:00+00:00")
    check("exactly one row is purged (old enough, not already purged)", purged == 1)

    old = rows[0]
    check("purged row's question is replaced with the sentinel, not left readable", old["question"] == "[purged]")
    check("purged row's answer is nulled", old["answer"] is None)
    check("purged row's messages (multi-turn context) is cleared", old["messages"] == [])
    check("purged row's cost_usd (instrumentation) is untouched", old["cost_usd"] == 0.04)

    recent = rows[1]
    check("a too-recent row keeps its real question text", recent["question"] == "What is deliverance?")
    check("a too-recent row keeps its real answer", recent["answer"] == "A recent answer.")

    already = rows[2]
    check("an already-purged row is left alone", already["cost_usd"] == 0.05)

    purged_again = retention.purge_expired_answer_job_content(supabase, now_iso="2026-08-28T00:00:00+00:00")
    check("running the purge twice in a row purges nothing new", purged_again == 0)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
