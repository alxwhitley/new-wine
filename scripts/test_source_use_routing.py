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
    _valid_current_policy,
    enrich_source_use_candidates,
    partition_source_use_candidates,
    select_source_use_references,
)
from app.services.source_use_policy import (  # noqa: E402
    ApprovedProtectedSourceRegistry,
    IssuePolicy,
    IssueRegistry,
    PresentationStance,
    QueryPolicy,
    SourceBoundary,
    ViewpointEvidence,
)
from app.services.async_answers.producer import (  # noqa: E402
    _SOURCE_USE_CORPUS_GAP,
    _build_context,
    _finalize_source_use_policy,
    _initial_source_use_policy,
)
from app.services.async_answers import producer as producer_module  # noqa: E402
from app.services import answer_toolbox as toolbox_module  # noqa: E402


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
        self.eq_filters = {}
        self.limit_value = None

    def select(self, _columns):
        return self

    def in_(self, _column, values):
        self.in_values = set(values)
        return self

    def eq(self, column, value):
        self.eq_filters[column] = value
        return self

    def order(self, _column):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.db.executed.append(self.table_name)
        rows = self.db.rows_by_table.get(self.table_name, [])
        if self.in_values is not None:
            key = "id" if self.table_name == "documents" else "chunk_id"
            rows = [row for row in rows if row.get(key) in self.in_values]
        for key, value in self.eq_filters.items():
            rows = [row for row in rows if row.get(key) == value]
        if self.limit_value is not None:
            rows = rows[:self.limit_value]
        return _Result(rows)


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


def _policy(
    chunk_id, policy_class, issue_key=None, viewpoint_key=None,
    protected_topic_keys=None,
):
    return {
        "chunk_id": chunk_id,
        "policy_class": policy_class,
        "protected_topic_keys": list(protected_topic_keys or []),
        "issue_key": issue_key,
        "viewpoint_key": viewpoint_key,
        "rule_version": "biblical_context_v1",
        "classifier_kind": "deterministic",
        "model": None,
        "prompt_fingerprint": None,
        "reason_codes": ["fixture"],
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

    def test_policy_trust_boundary_rejects_absent_stale_and_malformed_rows(self):
        malformed = [
            dict(_policy("c1", "general_context"), protected_topic_keys=["tongues"]),
            _policy("c1", "orthodox_viewpoint", "example_issue", None),
            _policy("c1", "protected_spirit_filled"),
            _policy("c1", "protected_spirit_filled", protected_topic_keys=["unknown"]),
            dict(_policy("c1", "general_context"), classifier_kind="model"),
            dict(_policy("c1", "general_context"), reason_codes=[]),
            dict(_policy("c1", "general_context"), rule_version=" "),
        ]
        self.assertFalse(_valid_current_policy(None, "c1"))
        stale = dict(_policy("c1", "general_context"), is_current=False)
        self.assertFalse(_valid_current_policy(stale, "c1"))
        for row in malformed:
            with self.subTest(row=row):
                self.assertFalse(_valid_current_policy(row, "c1"))

    def test_mixed_and_uncertain_policy_rows_are_valid_but_never_answer_eligible(self):
        candidates = []
        for policy_class in ("mixed", "uncertain"):
            row = _policy(policy_class, policy_class)
            self.assertTrue(_valid_current_policy(row, policy_class))
            candidates.append(dict(
                _chunk(policy_class, "d-" + policy_class),
                _source_id=SOURCE_A,
                _source_policy=row,
            ))
        partition = partition_source_use_candidates(
            candidates,
            self.general,
            ApprovedProtectedSourceRegistry({}),
            self.issue_registry,
        )
        self.assertEqual(partition.reference, ())

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
        self.assertEqual(partition.reference[0]["_source_use_role"], "reference")
        self.assertEqual(partition.viewpoint_evidence, ())

    def test_protected_route_uses_exact_topic_approved_source_ids(self):
        candidates = [
            dict(_chunk("approved", "d1", "sermon_transcript"), _source_id=SOURCE_A),
            dict(_chunk("general", "d2", "biblical_context"), _source_id=SOURCE_B,
                 _source_policy=_policy("general", "general_context")),
            dict(_chunk("word", "d3", "word_study"), _source_id=SOURCE_A),
            dict(_chunk("approved-reference", "d4", "commentary"),
                 _source_id=SOURCE_A,
                 _source_policy=_policy("approved-reference", "general_context")),
        ]
        partition = partition_source_use_candidates(
            candidates,
            self.protected,
            ApprovedProtectedSourceRegistry({"tongues": frozenset({SOURCE_A})}),
            self.issue_registry,
        )
        self.assertEqual([c["id"] for c in partition.doctrinal], ["approved"])
        self.assertEqual(partition.reference, ())

    def test_current_policy_identity_changes_with_source_routing_gate(self):
        import types

        quote_module_name = "app.services.quotes"
        original_quote_module = sys.modules.get(quote_module_name)
        fake_quotes = types.ModuleType(quote_module_name)
        fake_quotes.quote_selection_enabled = lambda: False
        sys.modules[quote_module_name] = fake_quotes
        originals = (
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
            producer_module.get_disabled_filters,
            producer_module.get_corpus_version,
        )
        producer_module.get_disabled_filters = lambda: {
            "include_copyrighted": False,
            "source_kinds": [],
            "source_names": [],
        }
        producer_module.get_corpus_version = lambda _db: "corpus-v1"
        try:
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = False
            disabled = producer_module.current_policy(object())
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = True
            enabled = producer_module.current_policy(object())
        finally:
            (
                toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
                producer_module.get_disabled_filters,
                producer_module.get_corpus_version,
            ) = originals
            if original_quote_module is None:
                del sys.modules[quote_module_name]
            else:
                sys.modules[quote_module_name] = original_quote_module
        self.assertNotEqual(disabled["policy_version"], enabled["policy_version"])
        self.assertIn("biblical_context_answer=false", disabled["policy_version"])
        self.assertIn("biblical_context_answer=true", enabled["policy_version"])

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
            [c["_viewpoint_slot"] for c in partition.reference],
            ["view_alpha", "view_beta"],
        )
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

    def test_plural_reference_selection_preserves_each_available_slot(self):
        candidates = [
            {"id": "alpha-%d" % index, "_viewpoint_slot": "view_alpha"}
            for index in range(9)
        ] + [{"id": "beta", "_viewpoint_slot": "view_beta"}]
        scores = {
            candidate["id"]: float(100 - index)
            for index, candidate in enumerate(candidates)
        }
        selected = select_source_use_references(
            candidates, scores, issue_scoped=True, limit=8
        )
        self.assertEqual(len(selected), 8)
        self.assertIn("view_alpha", {item["_viewpoint_slot"] for item in selected})
        self.assertIn("view_beta", {item["_viewpoint_slot"] for item in selected})

    def test_route_is_bound_to_the_exact_position_paper_match(self):
        policy = _initial_source_use_policy(
            "Is speaking in tongues for today?", "speaking_in_tongues"
        )
        self.assertEqual(policy.source_boundary, SourceBoundary.PROTECTED_SPIRIT_FILLED)
        self.assertEqual(policy.presentation_stance, PresentationStance.HOUSE_POSITION)
        self.assertEqual(policy.house_topic_key, "speaking_in_tongues")

    def test_plural_finalization_requires_two_distinct_registered_sources(self):
        initial = QueryPolicy(
            SourceBoundary.GENERAL,
            PresentationStance.UNCERTAIN,
            issue_key="example_issue",
        )
        final = _finalize_source_use_policy(
            "Compare this example issue",
            initial,
            (
                ViewpointEvidence("view_alpha", SOURCE_A),
                ViewpointEvidence("view_beta", SOURCE_B),
            ),
            self.issue_registry,
        )
        self.assertEqual(final.presentation_stance, PresentationStance.PLURAL)
        one_sided = _finalize_source_use_policy(
            "Compare this example issue",
            initial,
            (ViewpointEvidence("view_alpha", SOURCE_A),),
            self.issue_registry,
        )
        self.assertEqual(one_sided.presentation_stance, PresentationStance.UNCERTAIN)

    def test_reference_and_viewpoint_context_are_structurally_labeled(self):
        chunks = [
            dict(
                _chunk("teacher", "d1", "sermon_transcript"),
                author="Teacher One",
                title="Sermon",
            ),
            dict(
                _chunk("context", "d2", "biblical_context"),
                author="Reference Work",
                title="Context",
                _source_use_role="reference",
            ),
            dict(
                _chunk("view", "d3", "commentary"),
                author="View Source",
                title="View",
                _source_use_role="viewpoint",
                _viewpoint_slot="view_alpha",
            ),
        ]
        context = _build_context(chunks, 3)
        self.assertIn("[Source 1]", context)
        self.assertIn("[Reference Context 1]", context)
        self.assertIn("[Viewpoint view_alpha 1]", context)

    def test_corpus_gap_copy_is_fixed_and_does_not_claim_consensus(self):
        self.assertEqual(
            _SOURCE_USE_CORPUS_GAP,
            "New Wine does not yet have enough registered source breadth to compare the approved viewpoints on this issue.",
        )

    def test_retrieve_wiring_keeps_one_doctrinal_pool_and_eligible_reference(self):
        from app.services import single_teacher_lock

        teacher = dict(
            _chunk("teacher", "d1", "sermon_transcript"),
            title="Sermon",
            author="Teacher One",
            chunk_index=0,
        )
        context = dict(
            _chunk("context", "d2", "biblical_context"),
            title="Context",
            author="Reference Work",
            chunk_index=0,
        )
        neighbor = dict(
            _chunk("neighbor", "d3", "biblical_context"),
            title="Neighbor Context",
            author="Reference Work",
            chunk_index=1,
        )
        db = _DB(
            {
                "documents": [
                    {"id": "d1", "source_id": SOURCE_A},
                    {"id": "d2", "source_id": SOURCE_B},
                    {"id": "d3", "source_id": SOURCE_C},
                ],
                "source_passage_policy_versions": [
                    _policy("context", "general_context"),
                    _policy("neighbor", "general_context"),
                ],
            }
        )
        originals = (
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
            toolbox_module.expand_query,
            toolbox_module.hybrid_search_rrf,
            toolbox_module._get_cohere,
            toolbox_module.fetch_neighbor_chunks_batch,
            producer_module.get_disabled_filters,
            producer_module.is_chunk_disabled,
            single_teacher_lock.apply_explicit_teacher_lock,
            single_teacher_lock.filter_chunks_to_source,
        )
        toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = True
        toolbox_module.expand_query = lambda _question: (["historical context"], None)
        toolbox_module.hybrid_search_rrf = lambda *_args, **_kwargs: (
            {
                "teacher": (1.0, teacher),
                "context": (0.9, context),
            },
            [0.0],
        )
        toolbox_module._get_cohere = lambda: None
        toolbox_module.fetch_neighbor_chunks_batch = (
            lambda *_args, **_kwargs: [neighbor]
        )
        producer_module.get_disabled_filters = lambda: {
            "include_copyrighted": False,
            "source_kinds": [],
            "source_names": [],
        }
        producer_module.is_chunk_disabled = lambda *_args, **_kwargs: False
        single_teacher_lock.apply_explicit_teacher_lock = (
            lambda _question, collapsed, _db: (collapsed, SOURCE_A, True)
        )
        single_teacher_lock.filter_chunks_to_source = (
            lambda chunks, _source_id, _db: [
                chunk for chunk in chunks if chunk.get("id") == "teacher"
            ]
        )
        try:
            chunks, citations, citable_count, fallback = producer_module._retrieve(
                db,
                "Give the historical context of this passage",
                query_policy=self.general,
                protected_source_registry=ApprovedProtectedSourceRegistry({}),
                issue_registry=self.issue_registry,
                experimental_teacher_source_lock=True,
            )
        finally:
            (
                toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
                toolbox_module.expand_query,
                toolbox_module.hybrid_search_rrf,
                toolbox_module._get_cohere,
                toolbox_module.fetch_neighbor_chunks_batch,
                producer_module.get_disabled_filters,
                producer_module.is_chunk_disabled,
                single_teacher_lock.apply_explicit_teacher_lock,
                single_teacher_lock.filter_chunks_to_source,
            ) = originals
        self.assertEqual(
            [chunk["id"] for chunk in chunks],
            ["teacher", "context", "neighbor"],
        )
        self.assertEqual(chunks[1]["_source_use_role"], "reference")
        self.assertEqual(chunks[2]["_source_use_role"], "reference")
        self.assertEqual(
            [citation["chunk_id"] for citation in citations],
            ["teacher", "context", "neighbor"],
        )
        self.assertEqual(citable_count, 2)
        self.assertFalse(fallback)

    def test_flag_off_retrieve_never_queries_passage_policy(self):
        commentary = dict(
            _chunk("commentary", "d2", "commentary"),
            title="Commentary",
            author="Commentator",
            chunk_index=0,
        )
        db = _DB({"documents": [], "source_passage_policy_versions": []})
        originals = (
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
            toolbox_module.expand_query,
            toolbox_module.hybrid_search_rrf,
            toolbox_module._get_cohere,
            toolbox_module.fetch_neighbor_chunks_batch,
            producer_module.get_disabled_filters,
            producer_module.is_chunk_disabled,
        )
        toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = False
        toolbox_module.expand_query = lambda _question: (["question"], None)
        toolbox_module.hybrid_search_rrf = lambda *_args, **_kwargs: (
            {"commentary": (1.0, commentary)}, [0.0]
        )
        toolbox_module._get_cohere = lambda: None
        toolbox_module.fetch_neighbor_chunks_batch = lambda *_args, **_kwargs: []
        producer_module.get_disabled_filters = lambda: {
            "include_copyrighted": False,
            "source_kinds": [],
            "source_names": [],
        }
        producer_module.is_chunk_disabled = lambda *_args, **_kwargs: False
        try:
            chunks, citations, _, _ = producer_module._retrieve(db, "question")
        finally:
            (
                toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
                toolbox_module.expand_query,
                toolbox_module.hybrid_search_rrf,
                toolbox_module._get_cohere,
                toolbox_module.fetch_neighbor_chunks_batch,
                producer_module.get_disabled_filters,
                producer_module.is_chunk_disabled,
            ) = originals
        self.assertEqual(chunks, [])
        self.assertEqual(citations, [])
        self.assertNotIn("source_passage_policy_versions", db.executed)

    def test_one_sided_registered_issue_returns_gap_before_generation(self):
        from app.services import position_papers, stored_position_evidence

        seen = {}
        originals = (
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
            position_papers.match_position_paper,
            position_papers.get_paper_body,
            stored_position_evidence.fetch_stored_position_evidence,
            producer_module._match_stored_position_for_answer,
            producer_module._inject_background_topics,
            producer_module._retrieve,
        )
        toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = True
        position_papers.match_position_paper = lambda _question: "divine_healing"
        position_papers.get_paper_body = lambda *_args: (_ for _ in ()).throw(
            AssertionError("registered issue reached the house-position fence")
        )
        stored_position_evidence.fetch_stored_position_evidence = lambda *_args: None
        producer_module._match_stored_position_for_answer = lambda *_args: None
        producer_module._inject_background_topics = (
            lambda *_args, **_kwargs: ([], set(), {})
        )

        def _empty_retrieve(*args, **kwargs):
            seen["matched_pillar_key"] = args[3]
            seen.update(kwargs)
            return [], [], 0, False

        producer_module._retrieve = _empty_retrieve
        try:
            result = producer_module._produce(
                object(),
                "Why does God heal some believers but not others?",
            )
        finally:
            (
                toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
                position_papers.match_position_paper,
                position_papers.get_paper_body,
                stored_position_evidence.fetch_stored_position_evidence,
                producer_module._match_stored_position_for_answer,
                producer_module._inject_background_topics,
                producer_module._retrieve,
            ) = originals
        self.assertEqual(result.answer, _SOURCE_USE_CORPUS_GAP)
        self.assertEqual(result.outcome, "no_material")
        self.assertEqual(seen["query_policy"].issue_key, "healing_mechanics")
        self.assertIsNone(seen["matched_pillar_key"])
        self.assertIn("protected_source_registry", seen)

    def test_protected_house_route_never_generates_from_house_paper_alone(self):
        from app.services import position_papers, stored_position_evidence

        originals = (
            toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
            position_papers.match_position_paper,
            position_papers.get_paper_body,
            stored_position_evidence.fetch_stored_position_evidence,
            producer_module._match_stored_position_for_answer,
            producer_module._inject_background_topics,
            producer_module._retrieve,
            producer_module._generate_and_capture,
        )
        toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED = True
        position_papers.match_position_paper = lambda _question: "speaking_in_tongues"
        position_papers.get_paper_body = lambda _key: "approved house fence"
        stored_position_evidence.fetch_stored_position_evidence = lambda *_args: None
        producer_module._match_stored_position_for_answer = lambda *_args: None
        producer_module._inject_background_topics = (
            lambda *_args, **_kwargs: ([], set(), {})
        )
        producer_module._retrieve = lambda *_args, **_kwargs: ([], [], 0, False)
        producer_module._generate_and_capture = lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(AssertionError("house paper alone reached generation"))
        try:
            result = producer_module._produce(
                object(), "What does New Wine believe about speaking in tongues?"
            )
        finally:
            (
                toolbox_module.BIBLICAL_CONTEXT_ANSWER_ENABLED,
                position_papers.match_position_paper,
                position_papers.get_paper_body,
                stored_position_evidence.fetch_stored_position_evidence,
                producer_module._match_stored_position_for_answer,
                producer_module._inject_background_topics,
                producer_module._retrieve,
                producer_module._generate_and_capture,
            ) = originals
        self.assertEqual(result.outcome, "no_material")
        self.assertEqual(result.model, "source_use_policy")

    def test_protected_background_context_uses_the_same_exact_source_allowlist(self):
        from app.services import source_resolver

        db = _DB(
            {
                "documents": [
                    {"id": "d1", "source_id": SOURCE_A},
                    {"id": "d2", "source_id": SOURCE_B},
                ],
                "chunks": [
                    {"document_id": "d1", "chunk_index": 0, "content": "approved"},
                    {"document_id": "d2", "chunk_index": 0, "content": "blocked"},
                ],
            }
        )
        originals = (
            toolbox_module._ensure_background_topics,
            toolbox_module.match_background_topics,
            toolbox_module._background_topics,
            source_resolver.is_source_servable,
        )
        toolbox_module._ensure_background_topics = lambda: None
        toolbox_module.match_background_topics = lambda _question: ["one", "two"]
        toolbox_module._background_topics = [
            {"topic_key": "one", "document_id": "d1", "title": "Approved"},
            {"topic_key": "two", "document_id": "d2", "title": "Blocked"},
        ]
        source_resolver.is_source_servable = lambda *_args: True
        try:
            parts, document_ids, _updated = producer_module._inject_background_topics(
                db,
                "question",
                [],
                {},
                allowed_source_ids={SOURCE_A},
            )
        finally:
            (
                toolbox_module._ensure_background_topics,
                toolbox_module.match_background_topics,
                toolbox_module._background_topics,
                source_resolver.is_source_servable,
            ) = originals
        self.assertEqual(document_ids, {"d1"})
        self.assertEqual(len(parts), 1)
        self.assertIn("approved", parts[0])
        self.assertNotIn("blocked", parts[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
