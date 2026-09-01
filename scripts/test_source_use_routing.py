#!/usr/bin/env python3
"""Local Phase 4 source-routing contract tests; no network or real database."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.answer_toolbox import (  # noqa: E402
    BIBLICAL_CONTEXT_ANSWER_ENABLED,
    enrich_source_use_candidates,
    partition_source_use_candidates,
)
from app.services.source_use_policy import (  # noqa: E402
    ApprovedProtectedSourceRegistry,
    IssuePolicy,
    IssueRegistry,
    PresentationStance,
    QueryPolicy,
    SourceBoundary,
)


SOURCE_A = "11111111-1111-4111-8111-111111111111"
SOURCE_B = "22222222-2222-4222-8222-222222222222"
SOURCE_C = "33333333-3333-4333-8333-333333333333"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table_name):
        self.db = db
        self.table_name = table_name
        self.in_values = None

    def select(self, _columns):
        return self

    def in_(self, _column, values):
        self.in_values = set(values)
        return self

    def eq(self, _column, _value):
        return self

    def execute(self):
        self.db.executed.append(self.table_name)
        rows = self.db.rows_by_table.get(self.table_name, [])
        if self.in_values is None:
            return _Result(rows)
        key = "id" if self.table_name == "documents" else "chunk_id"
        return _Result([row for row in rows if row.get(key) in self.in_values])


class _DB:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.executed = []

    def table(self, name):
        return _Query(self, name)


def _chunk(chunk_id, document_id, source_kind="commentary"):
    return {
        "id": chunk_id,
        "document_id": document_id,
        "content": "content for " + chunk_id,
        "source_kind": source_kind,
        "citation_mode": "citable",
    }


def _policy(chunk_id, policy_class, issue_key=None, viewpoint_key=None):
    return {
        "chunk_id": chunk_id,
        "policy_class": policy_class,
        "protected_topic_keys": [],
        "issue_key": issue_key,
        "viewpoint_key": viewpoint_key,
        "rule_version": "biblical_context_v1",
        "is_current": True,
    }


class SourceUseRoutingTests(unittest.TestCase):
    def setUp(self):
        self.general = QueryPolicy(
            SourceBoundary.GENERAL,
            PresentationStance.SHARED_CHRISTIAN,
        )
        self.protected = QueryPolicy(
            SourceBoundary.PROTECTED_SPIRIT_FILLED,
            PresentationStance.HOUSE_POSITION,
            protected_topic_keys=("tongues",),
            house_topic_key="speaking_in_tongues",
        )
        self.issue_registry = IssueRegistry(
            (
                IssuePolicy(
                    "example_issue",
                    SourceBoundary.GENERAL,
                    viewpoint_slots=("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        ("view_alpha", frozenset({SOURCE_A})),
                        ("view_beta", frozenset({SOURCE_B})),
                    ),
                    query_phrases=("example issue",),
                ),
            )
        )

    def test_flag_defaults_off(self):
        self.assertFalse(BIBLICAL_CONTEXT_ANSWER_ENABLED)

    def test_enrichment_batches_source_and_current_policy_metadata(self):
        db = _DB(
            {
                "documents": [
                    {"id": "d1", "source_id": SOURCE_A},
                    {"id": "d2", "source_id": SOURCE_B},
                ],
                "source_passage_policy_versions": [
                    _policy("c1", "general_context"),
                    _policy("c2", "orthodox_viewpoint", "example_issue", "view_beta"),
                ],
            }
        )
        enriched = enrich_source_use_candidates(
            [_chunk("c1", "d1"), _chunk("c2", "d2")], db
        )
        self.assertEqual([item["_source_id"] for item in enriched], [SOURCE_A, SOURCE_B])
        self.assertEqual(enriched[0]["_source_policy"]["policy_class"], "general_context")
        self.assertEqual(enriched[1]["_source_policy"]["viewpoint_key"], "view_beta")
        self.assertEqual(db.executed, ["documents", "source_passage_policy_versions"])

    def test_duplicate_current_policy_rows_fail_closed_for_that_chunk(self):
        duplicate = _policy("c1", "general_context")
        db = _DB(
            {
                "documents": [{"id": "d1", "source_id": SOURCE_A}],
                "source_passage_policy_versions": [duplicate, dict(duplicate)],
            }
        )
        enriched = enrich_source_use_candidates([_chunk("c1", "d1")], db)
        self.assertNotIn("_source_policy", enriched[0])

    def test_general_route_separates_teacher_and_eligible_reference(self):
        candidates = [
            dict(_chunk("teacher", "d1", "sermon_transcript"), _source_id=SOURCE_A),
            dict(
                _chunk("context", "d2", "biblical_context"),
                _source_id=SOURCE_B,
                _source_policy=_policy("context", "general_context"),
            ),
            dict(_chunk("unknown", "d3"), _source_id=SOURCE_C),
            dict(_chunk("word", "d4", "word_study"), _source_id=SOURCE_C),
        ]
        partition = partition_source_use_candidates(
            candidates,
            self.general,
            ApprovedProtectedSourceRegistry({}),
            self.issue_registry,
        )
        self.assertEqual([c["id"] for c in partition.doctrinal], ["teacher"])
        self.assertEqual([c["id"] for c in partition.reference], ["context"])
        self.assertEqual(partition.viewpoint_evidence, ())

    def test_protected_route_uses_exact_topic_approved_source_ids(self):
        candidates = [
            dict(_chunk("approved", "d1", "sermon_transcript"), _source_id=SOURCE_A),
            dict(_chunk("general", "d2", "biblical_context"), _source_id=SOURCE_B,
                 _source_policy=_policy("general", "general_context")),
            dict(_chunk("word", "d3", "word_study"), _source_id=SOURCE_A),
        ]
        partition = partition_source_use_candidates(
            candidates,
            self.protected,
            ApprovedProtectedSourceRegistry({"tongues": frozenset({SOURCE_A})}),
            self.issue_registry,
        )
        self.assertEqual([c["id"] for c in partition.doctrinal], ["approved"])
        self.assertEqual(partition.reference, ())

    def test_empty_protected_registry_fails_closed(self):
        candidate = dict(
            _chunk("candidate", "d1", "sermon_transcript"),
            _source_id=SOURCE_A,
        )
        partition = partition_source_use_candidates(
            [candidate],
            self.protected,
            ApprovedProtectedSourceRegistry({}),
            self.issue_registry,
        )
        self.assertEqual(partition.doctrinal, ())
        self.assertEqual(partition.reference, ())

    def test_plural_route_requires_exact_issue_viewpoint_and_registered_source(self):
        plural_probe = QueryPolicy(
            SourceBoundary.GENERAL,
            PresentationStance.UNCERTAIN,
            issue_key="example_issue",
        )
        candidates = [
            dict(_chunk("alpha", "d1"), _source_id=SOURCE_A,
                 _source_policy=_policy("alpha", "orthodox_viewpoint", "example_issue", "view_alpha")),
            dict(_chunk("beta", "d2"), _source_id=SOURCE_B,
                 _source_policy=_policy("beta", "orthodox_viewpoint", "example_issue", "view_beta")),
            dict(_chunk("wrong-source", "d3"), _source_id=SOURCE_C,
                 _source_policy=_policy("wrong-source", "orthodox_viewpoint", "example_issue", "view_beta")),
            dict(_chunk("wrong-issue", "d4"), _source_id=SOURCE_A,
                 _source_policy=_policy("wrong-issue", "orthodox_viewpoint", "other_issue", "view_alpha")),
        ]
        partition = partition_source_use_candidates(
            candidates,
            plural_probe,
            ApprovedProtectedSourceRegistry({}),
            self.issue_registry,
        )
        self.assertEqual([c["id"] for c in partition.reference], ["alpha", "beta"])
        self.assertEqual(
            {(e.viewpoint_slot, e.source_id) for e in partition.viewpoint_evidence},
            {("view_alpha", SOURCE_A), ("view_beta", SOURCE_B)},
        )

    def test_one_source_cannot_supply_two_plural_slots(self):
        issue_registry = IssueRegistry(
            (
                IssuePolicy(
                    "example_issue",
                    SourceBoundary.GENERAL,
                    viewpoint_slots=("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        ("view_alpha", frozenset({SOURCE_A})),
                        ("view_beta", frozenset({SOURCE_A})),
                    ),
                    query_phrases=("example issue",),
                ),
            )
        )
        plural_probe = QueryPolicy(
            SourceBoundary.GENERAL,
            PresentationStance.UNCERTAIN,
            issue_key="example_issue",
        )
        candidates = [
            dict(_chunk("alpha", "d1"), _source_id=SOURCE_A,
                 _source_policy=_policy("alpha", "orthodox_viewpoint", "example_issue", "view_alpha")),
            dict(_chunk("beta", "d1"), _source_id=SOURCE_A,
                 _source_policy=_policy("beta", "orthodox_viewpoint", "example_issue", "view_beta")),
        ]
        partition = partition_source_use_candidates(
            candidates,
            plural_probe,
            ApprovedProtectedSourceRegistry({}),
            issue_registry,
        )
        self.assertEqual(len(partition.reference), 2)
        self.assertEqual(len({e.source_id for e in partition.viewpoint_evidence}), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
