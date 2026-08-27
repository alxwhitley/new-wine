#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/aggregation.py's
actual arithmetic and ranking logic. Uses a fake Supabase client -- no
real database. (test_admin_analytics_api.py mocks this module away
entirely, so it never exercises the real computation -- this file does.)

Run: python3.12 scripts/test_analytics_aggregation.py
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


class _FakeQuery:
    """Fixture rows already represent exactly the origin='user' /
    created_at>=since window -- eq/gte are no-ops here, matching the
    original fixtures (which carry no origin/created_at fields at all)."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, _col, _val):
        return self

    def gte(self, _col, _val):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _FakeGapQuery:
    """Real filtering for search_gap_details -- exercises the
    occurrence_id/status filter get_summary() actually applies."""

    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def in_(self, col, values):
        values = set(values)
        self._rows = [r for r in self._rows if r.get(col) in values]
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows)


class _FakeSupabase:
    def __init__(self, rows, gap_rows=None):
        self._rows = rows
        self._gap_rows = gap_rows or []

    def table(self, name):
        if name == "search_gap_details":
            return _FakeGapQuery(list(self._gap_rows))
        return _FakeQuery(list(self._rows))


def main() -> int:
    from app.services.search_analytics import aggregation

    rows = [
        # Deliverance Ministry: 3 total, 2 no_material -> failure_rate 0.667
        # -- one gap still open (dm-1), one already resolved (dm-2). The
        # topic still has an open gap because of dm-1.
        {"id": "occ-dm-1", "primary_topic": "Deliverance Ministry", "outcome": "no_material", "classification_status": "classified"},
        {"id": "occ-dm-2", "primary_topic": "Deliverance Ministry", "outcome": "no_material", "classification_status": "classified"},
        {"id": "occ-dm-3", "primary_topic": "Deliverance Ministry", "outcome": "answered", "classification_status": "classified"},
        # Speaking in Tongues: 4 total, 1 no_material -> failure_rate 0.25
        # -- its only gap (sit-1) has ALREADY BEEN RESOLVED, so this topic
        # must NOT count toward topics_with_open_gaps even though it has a
        # historical no_material occurrence.
        {"id": "occ-sit-1", "primary_topic": "Speaking in Tongues", "outcome": "no_material", "classification_status": "classified"},
        {"id": "occ-sit-2", "primary_topic": "Speaking in Tongues", "outcome": "answered", "classification_status": "classified"},
        {"id": "occ-sit-3", "primary_topic": "Speaking in Tongues", "outcome": "answered", "classification_status": "classified"},
        {"id": "occ-sit-4", "primary_topic": "Speaking in Tongues", "outcome": "answered", "classification_status": "pending"},
        # Unclassified: 1 total, answered
        {"id": "occ-u-1", "primary_topic": "Unclassified", "outcome": "answered", "classification_status": "classified"},
        # A pending row with no topic assigned yet
        {"id": "occ-p-1", "primary_topic": None, "outcome": None, "classification_status": "pending"},
    ]
    gap_rows = [
        {"occurrence_id": "occ-dm-1", "status": "open"},
        {"occurrence_id": "occ-dm-2", "status": "resolved"},
        {"occurrence_id": "occ-sit-1", "status": "resolved"},
    ]
    supabase = _FakeSupabase(rows, gap_rows=gap_rows)

    summary = aggregation.get_summary(supabase, days=30)
    check("monitored_searches counts every origin='user' row in the window", summary["monitored_searches"] == 9)
    check("no_material_count counts exactly the no_material outcomes", summary["no_material_count"] == 3)
    check("missing_content_rate is no_material / total", abs(summary["missing_content_rate"] - (3 / 9)) < 1e-9)
    check("topics_with_open_gaps counts only topics with a STILL-OPEN gap (1: Deliverance Ministry via dm-1) "
          "-- Speaking in Tongues' only gap is resolved and must not count",
          summary["topics_with_open_gaps"] == 1)
    check("unclassified_rate counts primary_topic == 'Unclassified' exactly (1/9), not the untagged-pending row too",
          abs(summary["unclassified_rate"] - (1 / 9)) < 1e-9)
    check("finalization_pending counts classification_status == 'pending'", summary["finalization_pending"] == 2)
    check("finalization_classified is total minus pending", summary["finalization_classified"] == 7)

    bars = aggregation.get_topic_bars(supabase, days=30)
    by_topic = {b["topic"]: b for b in bars}
    check("Deliverance Ministry totals 3 searches, 2 no_material",
          by_topic["Deliverance Ministry"]["total"] == 3 and by_topic["Deliverance Ministry"]["no_material"] == 2)
    check("Deliverance Ministry failure_rate is 2/3",
          abs(by_topic["Deliverance Ministry"]["failure_rate"] - (2 / 3)) < 1e-9)
    check("Speaking in Tongues totals 4 searches, 1 no_material",
          by_topic["Speaking in Tongues"]["total"] == 4 and by_topic["Speaking in Tongues"]["no_material"] == 1)
    check("an untagged-pending row buckets under the literal 'Unclassified' key, never crashes",
          by_topic["Unclassified"]["total"] == 2)

    check("ranked PRIMARILY by no_material count: Deliverance Ministry (2) outranks Speaking in Tongues (1)",
          bars.index(by_topic["Deliverance Ministry"]) < bars.index(by_topic["Speaking in Tongues"]))

    # Secondary tie-break: two topics with the SAME no_material count rank
    # by failure percentage.
    tie_rows = [
        {"primary_topic": "A", "outcome": "no_material", "classification_status": "classified"},
        {"primary_topic": "A", "outcome": "answered", "classification_status": "classified"},
        {"primary_topic": "A", "outcome": "answered", "classification_status": "classified"},
        {"primary_topic": "A", "outcome": "answered", "classification_status": "classified"},
        {"primary_topic": "B", "outcome": "no_material", "classification_status": "classified"},
        {"primary_topic": "B", "outcome": "answered", "classification_status": "classified"},
    ]
    tie_bars = aggregation.get_topic_bars(_FakeSupabase(tie_rows), days=30)
    tie_by_topic = {b["topic"]: b for b in tie_bars}
    check("both tied topics have exactly 1 no_material occurrence (a genuine tie on the primary key)",
          tie_by_topic["A"]["no_material"] == 1 and tie_by_topic["B"]["no_material"] == 1)
    check("secondary tie-break by failure percentage: B (50%) outranks A (25%) despite equal no_material count",
          tie_bars.index(tie_by_topic["B"]) < tie_bars.index(tie_by_topic["A"]))

    # Empty window: no crash, honest zeros rather than a division error.
    empty_summary = aggregation.get_summary(_FakeSupabase([]), days=30)
    check("an empty window returns 0 monitored_searches, not an error", empty_summary["monitored_searches"] == 0)
    check("an empty window's missing_content_rate is 0.0, not a ZeroDivisionError",
          empty_summary["missing_content_rate"] == 0.0)
    check("get_topic_bars on an empty window returns an empty list",
          aggregation.get_topic_bars(_FakeSupabase([]), days=30) == [])

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
