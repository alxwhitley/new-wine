#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/retention.py.

Run: python3.12 scripts/test_analytics_retention.py
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
    """Mimics supabase-py's postgrest filter chain closely enough for
    retention.py's one query: .not_ is a PROPERTY (real client convention,
    see backend/app/routers/admin.py's q.not_.ilike(...)) that negates the
    very next filter call."""

    def __init__(self, rows, payload):
        self.rows = rows
        self.payload = payload
        self.filters = []
        self._negate_next = False

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val))
        return self

    @property
    def not_(self):
        self._negate_next = True
        return self

    def is_(self, col, val):
        kind = "is_not_null" if self._negate_next else "is_null"
        self._negate_next = False
        self.filters.append((kind, col, val))
        return self

    def execute(self):
        matched = 0
        for r in self.rows:
            ok = True
            for kind, col, val in self.filters:
                if kind == "eq" and r.get(col) != val:
                    ok = False
                if kind == "lte" and not (r.get(col) is not None and r[col] <= val):
                    ok = False
                if kind == "is_not_null" and r.get(col) is None:
                    ok = False
                if kind == "is_null" and r.get(col) is not None:
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
    from app.services.search_analytics import retention

    rows = [
        {"id": "gap-1", "status": "resolved", "text_purge_at": "2026-01-01", "redacted_question": "old text", "purged_at": None},
        {"id": "gap-2", "status": "resolved", "text_purge_at": "2099-01-01", "redacted_question": "not yet due", "purged_at": None},
        {"id": "gap-3", "status": "open", "text_purge_at": None, "redacted_question": "still open", "purged_at": None},
        {"id": "gap-4", "status": "resolved", "text_purge_at": "2026-01-01", "redacted_question": None, "purged_at": "2026-02-01"},
    ]
    supabase = _FakeSupabase(rows)

    purged = retention.purge_expired_gap_text(supabase, now_iso="2026-08-27T00:00:00Z")
    check("exactly one row is purged (past due, resolved, still has text)", purged == 1)
    check("the purged row's text is nulled", rows[0]["redacted_question"] is None)
    check("a not-yet-due resolved row keeps its text", rows[1]["redacted_question"] == "not yet due")
    check("an open gap is never purged regardless of date", rows[2]["redacted_question"] == "still open")
    check("an already-purged row is left alone (idempotent)", rows[3]["purged_at"] == "2026-02-01")

    # Running again must be a no-op (idempotent).
    purged_again = retention.purge_expired_gap_text(supabase, now_iso="2026-08-27T00:00:00Z")
    check("running the purge twice in a row purges nothing new", purged_again == 0)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
