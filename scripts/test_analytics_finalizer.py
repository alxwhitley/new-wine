#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/finalizer.py.
Uses an in-memory fake DB -- no real database, no network call (the
classifier and redactor are injected as fakes).

Run: python3.12 scripts/test_analytics_finalizer.py
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


class _FakeTables:
    """An in-memory stand-in for answer_jobs / search_occurrences /
    search_gap_details, just expressive enough for finalizer.py's actual
    queries. Not a SQL engine -- each method below implements exactly the
    one query shape the finalizer issues."""

    def __init__(self):
        self.answer_jobs = {}       # job_id -> {"status", "outcome", "question"}
        self.occurrences = {}       # occurrence_id -> dict
        self.gaps = {}              # gap_id -> dict
        self._next_gap_id = 1

    def pending_job_ids(self):
        return sorted({
            o["job_id"] for o in self.occurrences.values()
            if o["classification_status"] == "pending"
            and self.answer_jobs.get(o["job_id"], {}).get("status") == "done"
        })

    def occurrences_for_job(self, job_id):
        return [o for o in self.occurrences.values() if o["job_id"] == job_id
                and o["classification_status"] == "pending"]

    def gap_for_occurrence(self, occurrence_id):
        for g in self.gaps.values():
            if g["occurrence_id"] == occurrence_id:
                return g
        return None

    def gap_for_retest_occurrence(self, occurrence_id):
        for g in self.gaps.values():
            if g["retest_occurrence_id"] == occurrence_id:
                return g
        return None

    def create_gap(self, occurrence_id, redacted_text, redaction_status, redaction_version):
        gap_id = "gap-%d" % self._next_gap_id
        self._next_gap_id += 1
        self.gaps[gap_id] = {
            "id": gap_id,
            "occurrence_id": occurrence_id,
            "redacted_question": redacted_text,
            "redaction_status": redaction_status,
            "redaction_version": redaction_version,
            "status": "open",
            "retest_occurrence_id": None,
            "retest_outcome": None,
        }
        return gap_id


class _FakeDb:
    def __init__(self, tables: _FakeTables):
        self.tables = tables

    def run(self, fn):
        return fn(self.tables)


def _fake_classify(question):
    from types import SimpleNamespace
    return SimpleNamespace(
        topic="Deliverance Ministry", confidence=0.9,
        model="fake-model", prompt_version="fake_v1", prompt_fingerprint="fake-fp",
    )


def _fake_redact(question):
    from types import SimpleNamespace
    return SimpleNamespace(text="What is [redacted] deliverance?", status="redacted")


def main() -> int:
    from app.services.search_analytics.finalizer import finalize_ready_jobs

    # Scenario 1: two occurrences share one job, outcome=no_material,
    # origin=user for both -> one classification call (shared generation),
    # but TWO gap rows -- each occurrence is a separately countable search
    # event (spec: "search_gap_details -- one row per no_material
    # occurrence"; acceptance criterion 8, "repeated no_material
    # occurrences remain separately countable").
    tables = _FakeTables()
    tables.answer_jobs["job-A"] = {"status": "done", "outcome": "no_material", "question": "What is deliverance for me@example.com?"}
    tables.occurrences["occ-1"] = {
        "id": "occ-1", "job_id": "job-A", "origin": "user",
        "classification_status": "pending",
    }
    tables.occurrences["occ-2"] = {
        "id": "occ-2", "job_id": "job-A", "origin": "user",
        "classification_status": "pending",
    }
    db = _FakeDb(tables)

    calls = {"classify": 0}
    def counting_classify(q):
        calls["classify"] += 1
        return _fake_classify(q)

    result = finalize_ready_jobs(db, classify_fn=counting_classify, redact_fn=_fake_redact)
    check("classification runs exactly once per job, not once per occurrence", calls["classify"] == 1)
    check("both occurrences sharing the job are finalized", result["occurrences_finalized"] == 2)
    check("each occurrence sharing the job gets its OWN gap row (separately countable)",
          result["gaps_created"] == 2)
    check("both occurrence rows carry the same classified topic",
          tables.occurrences["occ-1"]["primary_topic"] == "Deliverance Ministry"
          and tables.occurrences["occ-2"]["primary_topic"] == "Deliverance Ministry")
    check("both occurrence rows are marked classified",
          tables.occurrences["occ-1"]["classification_status"] == "classified"
          and tables.occurrences["occ-2"]["classification_status"] == "classified")
    gap = list(tables.gaps.values())[0]
    check("the gap stores the REDACTED text, never the raw question",
          "me@example.com" not in gap["redacted_question"])

    # Scenario 2: an answered (non-no_material) job creates no gap.
    tables2 = _FakeTables()
    tables2.answer_jobs["job-B"] = {"status": "done", "outcome": "answered", "question": "What is deliverance?"}
    tables2.occurrences["occ-3"] = {"id": "occ-3", "job_id": "job-B", "origin": "user", "classification_status": "pending"}
    db2 = _FakeDb(tables2)
    result2 = finalize_ready_jobs(db2, classify_fn=_fake_classify, redact_fn=_fake_redact)
    check("an answered outcome creates no gap", result2["gaps_created"] == 0)

    # Scenario 3: an admin_retest occurrence with outcome=no_material
    # updates the EXISTING gap's retest_outcome, never creates a new gap.
    tables3 = _FakeTables()
    tables3.answer_jobs["job-C"] = {"status": "done", "outcome": "no_material", "question": "What is deliverance?"}
    tables3.occurrences["occ-orig"] = {"id": "occ-orig", "job_id": "job-orig", "origin": "user", "classification_status": "classified", "primary_topic": "Deliverance Ministry"}
    tables3.occurrences["occ-retest"] = {"id": "occ-retest", "job_id": "job-C", "origin": "admin_retest", "classification_status": "pending"}
    existing_gap_id = tables3.create_gap("occ-orig", "What is [redacted] deliverance?", "redacted", "v1")
    tables3.gaps[existing_gap_id]["retest_occurrence_id"] = "occ-retest"
    db3 = _FakeDb(tables3)
    result3 = finalize_ready_jobs(db3, classify_fn=_fake_classify, redact_fn=_fake_redact)
    check("an admin_retest occurrence creates NO new gap even on no_material", result3["gaps_created"] == 0)
    check("the admin_retest occurrence updates the linked gap's retest_outcome instead",
          tables3.gaps[existing_gap_id]["retest_outcome"] == "no_material")
    check("admin_retest counts toward gaps_updated, not gaps_created", result3["gaps_updated"] == 1)

    # Scenario 4: finalizer never touches answer_jobs.answer/citations/outcome.
    tables4 = _FakeTables()
    tables4.answer_jobs["job-D"] = {"status": "done", "outcome": "answered", "question": "What is deliverance?", "answer": "SENTINEL"}
    tables4.occurrences["occ-4"] = {"id": "occ-4", "job_id": "job-D", "origin": "user", "classification_status": "pending"}
    db4 = _FakeDb(tables4)
    finalize_ready_jobs(db4, classify_fn=_fake_classify, redact_fn=_fake_redact)
    check("finalizer never mutates answer_jobs.answer", tables4.answer_jobs["job-D"]["answer"] == "SENTINEL")
    check("finalizer never mutates answer_jobs.outcome", tables4.answer_jobs["job-D"]["outcome"] == "answered")

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
