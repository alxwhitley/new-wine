#!/usr/bin/env python3
"""Unit tests for the Postgres-backed adapter in
backend/app/services/search_analytics/finalizer.py. Scripts a fake
cursor's fetchall/fetchone results -- no real database.

Run: python3.12 scripts/test_analytics_finalizer_postgres_adapter.py
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


class _ScriptedCursor:
    """Returns pre-scripted results keyed by a recognizable substring of
    the query, in call order per key."""

    def __init__(self, scripts):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, query, params=None):
        self.executed.append((" ".join(query.split()), params))
        self._last_query = query

    def fetchall(self):
        for key, results in self.scripts.items():
            if key in self._last_query:
                return results.pop(0) if results else []
        return []

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


def main() -> int:
    from app.services.search_analytics.finalizer import PostgresTables

    cursor = _ScriptedCursor({
        "SELECT DISTINCT o.job_id": [[{"job_id": "job-A"}]],
    })
    conn = _FakeConn(cursor)
    tables = PostgresTables(conn)
    job_ids = tables.pending_job_ids()
    check("pending_job_ids queries search_occurrences joined to done answer_jobs",
          job_ids == ["job-A"])
    executed_query, executed_params = cursor.executed[0]
    check("the join filters on classification_status='pending' and status='done'",
          "classification_status = 'pending'" in executed_query and "j.status = 'done'" in executed_query)

    # 2026-08-27 privacy review, additional observation: the SQL-side LIMIT
    # must be parameterized from the constructor, not hardcoded, so it
    # always agrees with finalize_ready_jobs()'s own Python-side slice.
    check("LIMIT is a bound parameter, not a hardcoded literal", "LIMIT %s" in executed_query)
    check("the default limit (50) is passed as the actual bound parameter", executed_params == (50,))

    cursor2 = _ScriptedCursor({"SELECT DISTINCT o.job_id": [[]]})
    PostgresTables(_FakeConn(cursor2), limit=200).pending_job_ids()
    check("a custom limit is threaded through to the SQL-side cap",
          cursor2.executed[0][1] == (200,))

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
