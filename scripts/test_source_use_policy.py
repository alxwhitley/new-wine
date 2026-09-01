#!/usr/bin/env python3
"""Small, deterministic tests for the Phase 1 source-use policy contract.

No network, model, database, filesystem writes, or answer-path imports.

Run: python3.12 scripts/test_source_use_policy.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.source_use_policy import (  # noqa: E402
    APPROVED_HOUSE_TOPIC_KEYS,
    ISSUE_REGISTRY,
    PROTECTED_TOPIC_KEYS,
    ApprovedProtectedSourceRegistry,
    IssuePolicy,
    IssueRegistry,
    PassagePolicy,
    PresentationStance,
    SourceBoundary,
    ViewpointEvidence,
    classify_query,
    detect_protected_topics,
)


class SourceUsePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_path = ROOT / "scripts" / "biblical_coverage_cases.json"
        cls.fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_conceptual_enums_match_the_approved_design(self) -> None:
        self.assertEqual(
            {item.value for item in SourceBoundary},
            {"protected_spirit_filled", "general"},
        )
        self.assertEqual(
            {item.value for item in PresentationStance},
            {"house_position", "plural", "shared_christian", "uncertain"},
        )
        self.assertEqual(
            {item.value for item in PassagePolicy},
            {
                "general_context",
                "orthodox_viewpoint",
                "protected_spirit_filled",
                "mixed",
                "uncertain",
            },
        )

    def test_adversarial_fixture_routes_are_fail_closed(self) -> None:
        for case in self.fixture["policy_adversarial_cases"]:
            with self.subTest(case=case["id"]):
                policy = classify_query(
                    case["question"],
                    position_paper_matcher=(
                        (lambda _question, key=case["house_topic_key"]: key)
                        if "house_topic_key" in case
                        else None
                    ),
                )
                self.assertEqual(policy.source_boundary.value, case["expected_boundary"])
                self.assertEqual(policy.presentation_stance.value, case["expected_stance"])
                self.assertEqual(list(policy.protected_topic_keys), case["expected_protected_topic_keys"])
                self.assertEqual(policy.issue_key, case.get("expected_issue_key"))

    def test_adjacent_biblical_questions_do_not_become_charismatic_topics(self) -> None:
        questions = (
            "Who were the twelve apostles chosen by Jesus?",
            "What literary role does prophecy play in Isaiah?",
            "Where did Jesus heal Bartimaeus?",
            "What happened when the disciples laid hands on the sick in Acts?",
        )
        for question in questions:
            with self.subTest(question=question):
                self.assertEqual(detect_protected_topics(question), ())
                self.assertEqual(classify_query(question).source_boundary, SourceBoundary.GENERAL)

    def test_mixed_question_uses_protected_boundary_for_entire_query(self) -> None:
        policy = classify_query(
            "Where was Corinth, and should Christians still speak in tongues today?",
            position_paper_matcher=lambda _question: "speaking_in_tongues",
        )
        self.assertEqual(policy.source_boundary, SourceBoundary.PROTECTED_SPIRIT_FILLED)
        self.assertEqual(policy.presentation_stance, PresentationStance.HOUSE_POSITION)
        self.assertIn("tongues", policy.protected_topic_keys)

    def test_existing_debates_keep_their_independent_boundaries(self) -> None:
        expected = {
            "healing_mechanics": SourceBoundary.PROTECTED_SPIRIT_FILLED,
            "prophetic_accountability": SourceBoundary.PROTECTED_SPIRIT_FILLED,
            "apostolic_authority": SourceBoundary.PROTECTED_SPIRIT_FILLED,
            "eschatological_timing": SourceBoundary.GENERAL,
        }
        self.assertEqual(
            {key: ISSUE_REGISTRY.require(key).source_boundary for key in expected},
            expected,
        )

    def test_plural_requires_two_distinct_registered_evidenced_slots(self) -> None:
        registry = IssueRegistry(
            (
                IssuePolicy(
                    issue_key="fictional_orthodox_dispute",
                    source_boundary=SourceBoundary.GENERAL,
                    viewpoint_slots=("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        (
                            "view_alpha",
                            frozenset({"11111111-1111-4111-8111-111111111111"}),
                        ),
                        (
                            "view_beta",
                            frozenset({"22222222-2222-4222-8222-222222222222"}),
                        ),
                    ),
                    query_phrases=("fictional dispute",),
                ),
            )
        )
        one_sided = classify_query(
            "How should this fictional dispute be understood?",
            issue_key="fictional_orthodox_dispute",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
            ),
            issue_registry=registry,
        )
        balanced = classify_query(
            "How should this fictional dispute be understood?",
            issue_key="fictional_orthodox_dispute",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "22222222-2222-4222-8222-222222222222"),
            ),
            issue_registry=registry,
        )
        unregistered = classify_query(
            "How should this fictional dispute be understood?",
            issue_key="not_registered",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "22222222-2222-4222-8222-222222222222"),
            ),
            issue_registry=registry,
        )
        self.assertEqual(one_sided.presentation_stance, PresentationStance.UNCERTAIN)
        self.assertEqual(balanced.presentation_stance, PresentationStance.PLURAL)
        self.assertEqual(unregistered.presentation_stance, PresentationStance.UNCERTAIN)

    def test_protected_source_registry_intersects_multi_topic_approval(self) -> None:
        registry = ApprovedProtectedSourceRegistry(
            {
                "tongues": frozenset(
                    {
                        "11111111-1111-4111-8111-111111111111",
                        "22222222-2222-4222-8222-222222222222",
                    }
                ),
                "baptism_holy_spirit": frozenset(
                    {
                        "11111111-1111-4111-8111-111111111111",
                        "33333333-3333-4333-8333-333333333333",
                    }
                ),
            }
        )
        self.assertEqual(
            registry.allowed_source_ids(("tongues", "baptism_holy_spirit")),
            frozenset({"11111111-1111-4111-8111-111111111111"}),
        )
        self.assertEqual(registry.allowed_source_ids(("unapproved_topic",)), frozenset())

    def test_unknown_and_invalid_questions_take_the_safe_path(self) -> None:
        for question in ("", "   ", "Explain this difficult doctrinal question", None, 42):
            with self.subTest(question=question):
                policy = classify_query(question)
                self.assertEqual(policy.source_boundary, SourceBoundary.PROTECTED_SPIRIT_FILLED)
                self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)

        for malformed_issue_key in ([], {}, 42, "Not Canonical"):
            with self.subTest(issue_key=malformed_issue_key):
                policy = classify_query(
                    "Explain this difficult doctrinal question",
                    issue_key=malformed_issue_key,  # type: ignore[arg-type]
                )
                self.assertEqual(
                    policy.source_boundary,
                    SourceBoundary.PROTECTED_SPIRIT_FILLED,
                )
                self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)
                self.assertEqual(policy.reason_codes, ("invalid_explicit_issue_key",))

    def test_approved_protected_neighborhood_has_direct_coverage(self) -> None:
        cases = {
            "Are miracles for today?": "continuation_of_gifts",
            "Does God still give words of knowledge today?": "continuation_of_gifts",
            "How should Christians use discernment of spirits today?": "continuation_of_gifts",
            "Does prophecy continue in churches today?": "continuation_of_gifts",
            "Do believers receive the Spirit at conversion?": "baptism_holy_spirit",
            "Can Christians be filled with the Spirit after conversion?": "baptism_holy_spirit",
            "What does it mean to be sealed with the Holy Spirit?": "baptism_holy_spirit",
            "Does God still heal the sick today?": "divine_healing",
            "Why does God heal some believers but not others?": "healing_mechanics",
            "Does apostolic authority continue in the church today?": "apostolic_authority",
            "Should five-fold ministry function in churches today?": "modern_apostles_and_prophets",
            "Are prophets active in the church today?": "prophetic_accountability",
            "Can a Christian need deliverance from demonic oppression?": "deliverance_spiritual_warfare",
            "Does laying on of hands impart spiritual gifts today?": "anointing_impartation_manifestations",
            "Does God still speak through dreams and visions today?": "hearing_god_and_revelation",
            "Should churches expect signs and wonders in revival?": "revival_signs_and_wonders",
            "Can Christians receive supernatural languages in private prayer?": "tongues",
        }
        self.assertEqual(set(cases.values()), set(PROTECTED_TOPIC_KEYS))
        for question, expected_topic in cases.items():
            with self.subTest(question=question):
                self.assertIn(expected_topic, detect_protected_topics(question))
                self.assertEqual(classify_query(question).source_boundary, SourceBoundary.PROTECTED_SPIRIT_FILLED)

    def test_house_match_must_be_compatible_and_never_overrides_a_debate(self) -> None:
        cases = (
            ("Where was Corinth?", "speaking_in_tongues", PresentationStance.SHARED_CHRISTIAN),
            ("Why am I not healed?", "divine_healing", PresentationStance.UNCERTAIN),
            ("How should a church test a prophetic word?", "prophecy_and_the_prophetic", PresentationStance.UNCERTAIN),
            ("Do apostles still have authority today?", "five_fold_ministry", PresentationStance.UNCERTAIN),
            ("When is the rapture?", "speaking_in_tongues", PresentationStance.UNCERTAIN),
        )
        for question, pillar_key, expected_stance in cases:
            with self.subTest(question=question):
                policy = classify_query(
                    question,
                    position_paper_matcher=lambda _question, key=pillar_key: key,
                )
                self.assertEqual(policy.presentation_stance, expected_stance)

        for malformed_result in ([], 42, {"pillar": "speaking_in_tongues"}):
            with self.subTest(malformed_result=malformed_result):
                policy = classify_query(
                    "Should Christians still speak in tongues today?",
                    position_paper_matcher=lambda _question, result=malformed_result: result,
                )
                self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)

    def test_explicit_issue_must_match_detected_protected_issue(self) -> None:
        registry = IssueRegistry(
            (
                IssuePolicy(
                    issue_key="fictional_protected_issue",
                    source_boundary=SourceBoundary.PROTECTED_SPIRIT_FILLED,
                    viewpoint_slots=("view_alpha", "view_beta"),
                    protected_topic_keys=("prophetic_accountability",),
                ),
            )
        )
        policy = classify_query(
            "Why am I not healed?",
            issue_key="fictional_protected_issue",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "22222222-2222-4222-8222-222222222222"),
            ),
            issue_registry=registry,
        )
        self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)

    def test_registry_identities_are_canonical_and_structurally_valid(self) -> None:
        for slots in (("view", " view"), ("View", "view"), ("view-alpha", "view_beta")):
            with self.subTest(slots=slots):
                with self.assertRaises(ValueError):
                    IssuePolicy("fictional_issue", SourceBoundary.GENERAL, slots)

        invalid_source_sets = (
            frozenset({""}),
            frozenset({"   "}),
            frozenset({"not a structural id!"}),
            "11111111-1111-4111-8111-111111111111",
        )
        for source_ids in invalid_source_sets:
            with self.subTest(source_ids=source_ids):
                with self.assertRaises((TypeError, ValueError)):
                    ApprovedProtectedSourceRegistry({"tongues": source_ids})

    def test_plural_requires_distinct_canonical_sources(self) -> None:
        registry = IssueRegistry(
            (
                IssuePolicy(
                    "fictional_orthodox_dispute",
                    SourceBoundary.GENERAL,
                    ("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        (
                            "view_alpha",
                            frozenset({"11111111-1111-4111-8111-111111111111"}),
                        ),
                        (
                            "view_beta",
                            frozenset({"11111111-1111-4111-8111-111111111111"}),
                        ),
                    ),
                    query_phrases=("fictional dispute",),
                ),
            )
        )
        policy = classify_query(
            "How should this fictional dispute be understood?",
            issue_key="fictional_orthodox_dispute",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "11111111-1111-4111-8111-111111111111"),
            ),
            issue_registry=registry,
        )
        self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)

    def test_plural_rejects_a_structurally_valid_but_unregistered_source(self) -> None:
        registry = IssueRegistry(
            (
                IssuePolicy(
                    "fictional_orthodox_dispute",
                    SourceBoundary.GENERAL,
                    ("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        (
                            "view_alpha",
                            frozenset({"11111111-1111-4111-8111-111111111111"}),
                        ),
                        (
                            "view_beta",
                            frozenset({"22222222-2222-4222-8222-222222222222"}),
                        ),
                    ),
                    query_phrases=("fictional dispute",),
                ),
            )
        )
        policy = classify_query(
            "How should this fictional dispute be understood?",
            issue_key="fictional_orthodox_dispute",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "33333333-3333-4333-8333-333333333333"),
            ),
            issue_registry=registry,
        )
        self.assertEqual(policy.presentation_stance, PresentationStance.UNCERTAIN)

    def test_explicit_issue_cannot_reclassify_an_unrelated_or_unknown_query(self) -> None:
        unknown = classify_query(
            "Explain this difficult doctrinal question",
            issue_key="eschatological_timing",
        )
        self.assertEqual(unknown.source_boundary, SourceBoundary.PROTECTED_SPIRIT_FILLED)
        self.assertEqual(unknown.presentation_stance, PresentationStance.UNCERTAIN)

        registry = IssueRegistry(
            (
                IssuePolicy(
                    "fictional_orthodox_dispute",
                    SourceBoundary.GENERAL,
                    ("view_alpha", "view_beta"),
                    registered_source_ids_by_slot=(
                        (
                            "view_alpha",
                            frozenset({"11111111-1111-4111-8111-111111111111"}),
                        ),
                        (
                            "view_beta",
                            frozenset({"22222222-2222-4222-8222-222222222222"}),
                        ),
                    ),
                    query_phrases=("fictional dispute",),
                ),
            )
        )
        unrelated = classify_query(
            "Who were the twelve apostles chosen by Jesus?",
            issue_key="fictional_orthodox_dispute",
            viewpoint_evidence=(
                ViewpointEvidence("view_alpha", "11111111-1111-4111-8111-111111111111"),
                ViewpointEvidence("view_beta", "22222222-2222-4222-8222-222222222222"),
            ),
            issue_registry=registry,
        )
        self.assertNotEqual(unrelated.presentation_stance, PresentationStance.PLURAL)

    def test_registries_are_issue_scoped_and_have_no_teacher_family_taxonomy(self) -> None:
        self.assertTrue(PROTECTED_TOPIC_KEYS)
        self.assertTrue(APPROVED_HOUSE_TOPIC_KEYS)
        forbidden_names = {"teacher_family", "teacher_taxonomy", "theological_family"}
        exported_names = set(vars(sys.modules["app.services.source_use_policy"]))
        self.assertTrue(forbidden_names.isdisjoint(exported_names))
        for issue in ISSUE_REGISTRY.entries:
            self.assertFalse(hasattr(issue, "teachers"))
            self.assertFalse(hasattr(issue, "teacher_family"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
