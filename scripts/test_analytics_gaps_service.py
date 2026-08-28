#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/gaps.py's actual
logic. test_admin_analytics_api.py mocks this module away entirely, so
resolve_gap()'s validation and create_retest()'s wiring had zero real
test coverage -- this file exercises both directly against a fake
Supabase client and fake Db/jobs.enqueue.

Run: python3.12 scripts/test_analytics_gaps_service.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

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

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def execute(self):
        for r in self.rows.values():
            if all(r.get(c) == v for c, v in self.filters):
                r.update(self.payload)
        return SimpleNamespace(data=[])


class _FakeSelectBuilder:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        matches = [r for r in self.rows.values() if all(r.get(c) == v for c, v in self.filters)]
        return SimpleNamespace(data=matches)


class _FakeGapTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_k):
        return _FakeSelectBuilder(self.rows)

    def update(self, payload):
        return _FakeUpdateBuilder(self.rows, payload)


class _FakeSupabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return _FakeGapTable(self.rows)


class _NoopDb:
    def run(self, fn):
        return fn(None)


def test_resolve_gap():
    from app.services.search_analytics import gaps

    rows = {
        "gap-no-retest": {"id": "gap-no-retest", "retest_outcome": None, "status": "open"},
        "gap-still-no-material": {"id": "gap-still-no-material", "retest_outcome": "no_material", "status": "open"},
        "gap-answered": {"id": "gap-answered", "retest_outcome": "answered", "status": "open"},
    }
    supabase = _FakeSupabase(rows)

    raised_no_retest = False
    try:
        gaps.resolve_gap(supabase, "gap-no-retest")
    except gaps.GapNotRetestedError:
        raised_no_retest = True
    check("resolve_gap refuses a gap with no retest at all (retest_outcome is None)", raised_no_retest)

    raised_still_no_material = False
    try:
        gaps.resolve_gap(supabase, "gap-still-no-material")
    except gaps.GapNotRetestedError:
        raised_still_no_material = True
    check("resolve_gap refuses a gap whose retest STILL returned no_material", raised_still_no_material)
    check("a refused resolve_gap call never flips status to resolved",
          rows["gap-still-no-material"]["status"] == "open")

    result = gaps.resolve_gap(supabase, "gap-answered")
    check("resolve_gap succeeds when the retest outcome is a real answer", result["status"] == "resolved")
    check("resolve_gap sets the gap's own status to resolved", rows["gap-answered"]["status"] == "resolved")
    check("resolve_gap stamps a resolved_at timestamp", rows["gap-answered"].get("resolved_at") is not None)
    check("resolve_gap stamps text_purge_at (for the 30-day retention purge)",
          rows["gap-answered"].get("text_purge_at") is not None)

    raised_not_found = False
    try:
        gaps.resolve_gap(supabase, "does-not-exist")
    except gaps.GapNotFoundError:
        raised_not_found = True
    check("resolve_gap raises GapNotFoundError for an unknown gap id, not a KeyError", raised_not_found)


def test_create_retest():
    from app.services.search_analytics import gaps
    from app.services.async_answers import jobs as jobs_module

    rows = {
        "gap-1": {"id": "gap-1", "redacted_question": "What is [redacted] deliverance?"},
        "gap-purged": {"id": "gap-purged", "redacted_question": None},
    }
    supabase = _FakeSupabase(rows)
    db = _NoopDb()

    with patch.object(jobs_module, "enqueue", return_value={"job": {"id": "job-retest-1"}}) as mock_enqueue, \
         patch.object(gaps, "create_occurrence", return_value="occ-retest-1") as mock_create_occ:
        result = gaps.create_retest(
            db, supabase, gap_id="gap-1",
            evidence_version="e1", prompt_version="p1", policy_version="policy_v3",
        )
        check("create_retest returns the new job id", result["job_id"] == "job-retest-1")
        check("create_retest returns the new occurrence id", result["occurrence_id"] == "occ-retest-1")
        check("create_retest submits the gap's REDACTED question, never anything else",
              mock_enqueue.call_args.kwargs["question"] == "What is [redacted] deliverance?")
        check("create_retest creates the occurrence with origin='admin_retest'",
              mock_create_occ.call_args.kwargs["origin"] == "admin_retest")
        check("create_retest's occurrence carries no subject_key (no personal subject behind an admin action)",
              mock_create_occ.call_args.kwargs["subject_key"] is None)
        check("create_retest stamps the gap's retest_occurrence_id with the new occurrence",
              rows["gap-1"]["retest_occurrence_id"] == "occ-retest-1")
        check("create_retest resets retest_outcome to None (a fresh retest is pending, not pre-judged)",
              rows["gap-1"]["retest_outcome"] is None)

    raised_purged = False
    try:
        gaps.create_retest(
            db, supabase, gap_id="gap-purged",
            evidence_version="e1", prompt_version="p1", policy_version="policy_v3",
        )
    except gaps.GapNotFoundError:
        raised_purged = True
    check("create_retest refuses a gap whose text has already been purged (nothing to retest with)",
          raised_purged)

    raised_unknown = False
    try:
        gaps.create_retest(
            db, supabase, gap_id="does-not-exist",
            evidence_version="e1", prompt_version="p1", policy_version="policy_v3",
        )
    except gaps.GapNotFoundError:
        raised_unknown = True
    check("create_retest raises GapNotFoundError for an unknown gap id", raised_unknown)


def main() -> int:
    test_resolve_gap()
    test_create_retest()
    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
