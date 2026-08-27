#!/usr/bin/env python3.12
"""Deterministic checks for the B6 latency benchmark instrumentation."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services.async_answers import producer as producer_module  # noqa: E402
from app.services import answer_intent, answer_toolbox, reference_verifier  # noqa: E402
from app.services import single_teacher_lock  # noqa: E402
from app.services import position_papers, stored_position_topics  # noqa: E402
from app.services.async_answers.latency_trace import LatencyTrace  # noqa: E402
from app.services.async_answers.producer import ProducerResult  # noqa: E402
from answer_latency_benchmark import (  # noqa: E402
    assert_query_expansion_available,
    assert_runtime_constraints,
    load_fixture,
    run_case,
    summarize_fixture,
)


class FakeClock:
    def __init__(self, values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


class FakeMessages:
    def __init__(self, events):
        self._events = events
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._events)


class FakeClient:
    def __init__(self, events):
        self.messages = FakeMessages(events)


class FakeQuery:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error

    def select(self, *args):
        return self

    def in_(self, column, values):
        wanted = set(values)
        self.rows = [row for row in self.rows if row.get(column) in wanted]
        return self

    def eq(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) == value]
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        if self.error:
            raise self.error
        return SimpleNamespace(data=self.rows)


class SourceBoundaryDB:
    def __init__(
        self, aliases, documents, sources=None, alias_error=None,
        document_error=None, source_error=None,
    ):
        self.aliases = aliases
        self.documents = documents
        self.sources = sources or []
        self.alias_error = alias_error
        self.document_error = document_error
        self.source_error = source_error

    def table(self, name):
        if name == "source_aliases":
            return FakeQuery(list(self.aliases), self.alias_error)
        if name == "documents":
            return FakeQuery(list(self.documents), self.document_error)
        if name == "sources":
            return FakeQuery(list(self.sources), self.source_error)
        raise AssertionError("unexpected table: %s" % name)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("OK:", label)


def generation_events():
    usage_start = SimpleNamespace(
        input_tokens=120,
        cache_read_input_tokens=40,
        cache_creation_input_tokens=0,
    )
    usage_end = SimpleNamespace(output_tokens=17)
    return [
        SimpleNamespace(type="message_start", message=SimpleNamespace(usage=usage_start)),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text="<answer>Hello")),
        SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text=" world</answer>")),
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"), usage=usage_end),
    ]


def test_trace_records_nested_monotonic_spans():
    trace = LatencyTrace(clock=FakeClock([10.0, 10.2, 10.5, 11.0]))
    with trace.span("producer"):
        with trace.span("retrieval"):
            pass
    payload = trace.to_dict()
    check("trace schema is versioned", payload["schema_version"] == 1)
    check(
        "nested stages retain completion order and durations",
        payload["stages"] == [
            {"name": "retrieval", "duration_ms": 300.0},
            {"name": "producer", "duration_ms": 1000.0},
        ],
    )


def test_generation_trace_is_observational_only():
    plain_client = FakeClient(generation_events())
    traced_client = FakeClient(generation_events())

    with (
        patch.object(producer_module, "get_anthropic_client", return_value=plain_client),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        plain = producer_module._generate_and_capture([], ["Vlad Savchuk"])

    trace = LatencyTrace(clock=FakeClock([20.0, 20.1, 20.4, 21.0]))
    with (
        patch.object(producer_module, "get_anthropic_client", return_value=traced_client),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        traced = producer_module._generate_and_capture(
            [], ["Vlad Savchuk"], trace=trace, stage_name="generation.primary"
        )

    check("trace leaves the generation result byte-identical", traced == plain)
    check("trace leaves provider request arguments identical", traced_client.messages.calls == plain_client.messages.calls)
    stage = trace.to_dict()["stages"][0]
    check("generation duration is recorded", stage["duration_ms"] == 1000.0)
    check("first provider event offset is recorded", stage["first_event_ms"] == 100.0)
    check("first text offset is recorded", stage["first_text_ms"] == 400.0)
    check("generation token usage is recorded", stage["output_tokens"] == 17)


def test_generation_effort_defaults_to_unset_and_is_recorded_when_requested():
    default_client = FakeClient(generation_events())
    with (
        patch.object(producer_module, "get_anthropic_client", return_value=default_client),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        producer_module._generate_and_capture([], ["Vlad Savchuk"])
    check(
        "default generation call omits output_config (byte-identical to pre-candidate behavior)",
        "output_config" not in default_client.messages.calls[0],
    )

    effort_client = FakeClient(generation_events())
    trace = LatencyTrace(clock=FakeClock([20.0, 20.1, 20.4, 21.0]))
    with (
        patch.object(producer_module, "get_anthropic_client", return_value=effort_client),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        producer_module._generate_and_capture(
            [], ["Vlad Savchuk"], trace=trace, stage_name="generation.primary", effort="medium"
        )
    check(
        "effort candidate sets output_config.effort without touching thinking/max_tokens",
        effort_client.messages.calls[0]["output_config"] == {"effort": "medium"}
        and effort_client.messages.calls[0]["thinking"] == {"type": "disabled"},
    )
    stage = trace.to_dict()["stages"][0]
    check("trace records the requested effort", stage["effort"] == "medium")

    default_trace = LatencyTrace(clock=FakeClock([0.0, 0.1, 0.4, 1.0]))
    with (
        patch.object(producer_module, "get_anthropic_client", return_value=FakeClient(generation_events())),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        producer_module._generate_and_capture([], ["Vlad Savchuk"], trace=default_trace, stage_name="generation.primary")
    check(
        "trace labels an unset effort as default rather than omitting the field",
        default_trace.to_dict()["stages"][0]["effort"] == "default",
    )


def test_run_case_forwards_the_effort_candidate_variant():
    seen = []

    def fake_produce(
        db, question, messages=None, topics_established=None, trace=None,
        experimental_generation_effort=None,
    ):
        seen.append(experimental_generation_effort)
        with trace.span("producer.total"):
            pass
        return ProducerResult(
            answer="Candidate answer.", outcome="answered", model="test-model"
        )

    case = {
        "id": "effort-case",
        "category": "ordinary",
        "question": "What does the source teach about grace?",
        "messages": [],
    }
    try:
        record = run_case(
            case,
            repetition=1,
            supabase=object(),
            produce_fn=fake_produce,
            variant="effort_medium_v1",
        )
    except TypeError:
        check("run_case accepts the effort candidate variant", False)
        return

    check("effort candidate reaches the producer", seen == ["medium"])
    check("effort candidate variant is retained for blind pairing", record["variant"] == "effort_medium_v1")


def test_producer_trace_covers_the_guarded_answer_path():
    chunk = {
        "id": "chunk-1",
        "document_id": "doc-1",
        "title": "Test source",
        "author": "Vlad Savchuk",
        "content": "Grounded source text.",
        "citation_mode": "citable",
        "source_kind": "sermon_transcript",
    }
    citation = {
        "chunk_id": "chunk-1",
        "document_title": "Test source",
        "author": "Vlad Savchuk",
        "content": "Grounded source text.",
        "url": None,
    }
    trace = LatencyTrace()
    retrieval_trace_seen = []

    def fake_retrieve(db, question, injected_doc_ids=None, matched_pillar_key=None, trace=None):
        retrieval_trace_seen.append(trace)
        return [chunk], [citation], 1, False

    def fake_generate(history, permitted_names=None, trace=None, stage_name="generation", effort=None):
        with trace.span(stage_name):
            pass
        return "Vlad Savchuk answers from the source [1].", "<answer>ok</answer>", "end_turn", {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }, "test-model"

    with (
        patch.object(position_papers, "match_position_paper", return_value=None),
        patch.object(stored_position_topics, "match_stored_position", return_value=None),
        patch.object(producer_module, "_inject_background_topics", return_value=([], set(), {})),
        patch.object(producer_module, "_retrieve", side_effect=fake_retrieve),
        patch.object(reference_verifier, "build_retrieval_grounding", return_value=object()),
        patch.object(reference_verifier, "build_name_universe", return_value=[]),
        patch.object(reference_verifier, "ungrounded_prose_teachers", return_value=[]),
        patch.object(reference_verifier, "verify_references", return_value=[{"kind": "verse"}]),
        patch.object(answer_toolbox, "_ungrounded_reference_teachers", return_value=[]),
        patch.object(producer_module, "_generate_and_capture", side_effect=fake_generate),
        patch.dict(
            sys.modules,
            {"app.services.quotes": SimpleNamespace(quote_selection_enabled=lambda: False)},
        ),
    ):
        result = producer_module.produce(object(), "What does the source teach?", trace=trace)

    names = [stage["name"] for stage in trace.to_dict()["stages"]]
    required = {
        "routing",
        "background_context",
        "retrieval",
        "context_build",
        "grounding",
        "generation.primary",
        "attribution_validation",
        "reference_verification",
        "quote_selection",
        "producer.total",
    }
    check("producer trace covers every guarded stage", required.issubset(set(names)))
    check("producer forwards the same trace into retrieval", retrieval_trace_seen == [trace])
    check("instrumented producer still returns the verified answer", result.answer == "Vlad Savchuk answers from the source [1].")
    check("instrumented producer preserves citations", result.citations == [citation])


def test_experimental_teacher_routing_only_bypasses_topic_positions_when_required():
    helper = getattr(producer_module, "_match_stored_position_for_answer", None)
    if helper is None:
        check("producer exposes the experimental stored-position routing seam", False)
        return

    named_topic_questions = {
        "What does Derek Prince teach about fasting?": "fasting",
        "What does Derek Prince teach about deliverance?": "deliverance from demons and spiritual warfare",
        "What does Derek Prince teach about how to pray effectively?": "how to pray effectively",
        "What does Derek Prince teach about the divine exchange?": "the divine exchange at the cross",
        "Does Derek Prince teach that believers can lose salvation?": "can a believer lose their salvation",
        "What does Derek Prince teach about holiness?": "holiness and personal purity",
    }
    with patch.object(
        answer_intent,
        "requires_teacher_specific_retrieval",
        return_value=True,
    ):
        for question, topic_key in named_topic_questions.items():
            check(
                "current routing still matches %r" % topic_key,
                helper(question, None, False) == topic_key,
            )
            check(
                "candidate routing bypasses %r for named teachers" % topic_key,
                helper(question, None, True) is None,
            )

    with (
        patch.object(
            stored_position_topics,
            "match_stored_position",
            return_value="deliverance from demons and spiritual warfare",
        ),
        patch.object(
            answer_intent,
            "requires_teacher_specific_retrieval",
            return_value=False,
        ),
    ):
        check(
            "candidate routing preserves stored evidence for generic topic questions",
            helper("What is deliverance?", None, True)
            == "deliverance from demons and spiritual warfare",
        )


def test_explicit_named_teacher_source_boundary():
    apply_lock = getattr(single_teacher_lock, "apply_explicit_teacher_lock", None)
    filter_chunks = getattr(single_teacher_lock, "filter_chunks_to_source", None)
    if apply_lock is None or filter_chunks is None:
        check("explicit named-teacher source boundary exists", False)
        return

    aliases = [
        {"alias_key": "derek prince", "source_id": "source-derek"},
        {"alias_key": "derek prince ministries", "source_id": "source-derek"},
        {"alias_key": "vlad savchuk", "source_id": "source-vlad"},
    ]
    documents = [
        {"id": "doc-derek-1", "source_id": "source-derek"},
        {"id": "doc-derek-2", "source_id": "source-derek"},
        {"id": "doc-vlad", "source_id": "source-vlad"},
        {"id": "doc-unknown", "source_id": None},
    ]
    db = SourceBoundaryDB(
        aliases,
        documents,
        sources=[{"id": "source-derek", "name": "Derek Prince"}],
    )
    collapsed = [
        ("c-derek", (0.9, {"id": "c-derek", "document_id": "doc-derek-1", "author": "Malformed title"})),
        ("c-vlad", (0.8, {"id": "c-vlad", "document_id": "doc-vlad"})),
        ("c-unknown", (0.7, {"id": "c-unknown", "document_id": "doc-unknown"})),
    ]

    locked, source_id, applied = apply_lock(
        "What does Derek Prince teach about deliverance?", collapsed, db
    )
    check("single named teacher activates the source boundary", applied is True)
    check("single named teacher resolves to canonical source identity", source_id == "source-derek")
    check("initial retrieval excludes every other source", [row[0] for row in locked] == ["c-derek"])
    check("initial evidence uses the canonical teacher name", locked[0][1][1]["author"] == "Derek Prince")

    neighbors = [
        {"id": "n-derek", "document_id": "doc-derek-2", "author": None},
        {"id": "n-vlad", "document_id": "doc-vlad"},
        {"id": "n-unknown", "document_id": "doc-unknown"},
    ]
    filtered_neighbors = filter_chunks(neighbors, "source-derek", db)
    check("neighbor expansion cannot reintroduce another source", [c["id"] for c in filtered_neighbors] == ["n-derek"])
    check("neighbor evidence uses the canonical teacher name", filtered_neighbors[0]["author"] == "Derek Prince")

    unchanged, source_id, applied = apply_lock(
        "Compare Derek Prince and Vlad Savchuk on deliverance", collapsed, db
    )
    check("multi-teacher questions remain unrestricted", unchanged == collapsed and source_id is None and applied is False)

    generic, source_id, applied = apply_lock("What is deliverance?", collapsed, db)
    check("generic questions remain unrestricted", generic == collapsed and source_id is None and applied is False)

    failed_db = SourceBoundaryDB([], [], alias_error=RuntimeError("offline"))
    with patch.object(single_teacher_lock.logger, "exception", return_value=None):
        failed, source_id, applied = apply_lock(
            "What does Derek Prince teach about deliverance?", collapsed, failed_db
        )
    check("alias resolution failure fails closed", failed == [] and source_id is None and applied is True)

    document_failed_db = SourceBoundaryDB(
        aliases,
        [],
        sources=[{"id": "source-derek", "name": "Derek Prince"}],
        document_error=RuntimeError("offline"),
    )
    with patch.object(single_teacher_lock.logger, "exception", return_value=None):
        failed, source_id, applied = apply_lock(
            "What does Derek Prince teach about deliverance?", collapsed, document_failed_db
        )
    check("document identity failure fails closed", failed == [] and source_id == "source-derek" and applied is True)


def test_candidate_neighbor_expansion_hard_caps_an_oversized_initial_pool():
    cap_expansion = getattr(producer_module, "_bounded_neighbor_expansion", None)
    if cap_expansion is None:
        check("candidate exposes a hard-bounded neighbor merge", False)
        return

    initial = [{"id": "initial-%02d" % i} for i in range(27)]
    neighbors = [{"id": "neighbor-%02d" % i} for i in range(5)]
    bounded = cap_expansion(initial, neighbors, max_chunks=12)
    check("oversized initial retrieval is capped at twelve", len(bounded) == 12)
    check(
        "hard cap preserves retrieval rank order",
        [chunk["id"] for chunk in bounded]
        == ["initial-%02d" % i for i in range(12)],
    )

    bounded = cap_expansion(initial[:8], neighbors, max_chunks=12)
    check("neighbor expansion fills but never exceeds twelve", len(bounded) == 12)
    check("neighbor expansion preserves the initial eight", bounded[:8] == initial[:8])


def test_fixture_contract_is_bounded_and_unique():
    fixture = load_fixture(ROOT / "scripts" / "answer_latency_benchmark_cases.json")
    summary = summarize_fixture(fixture)
    check("fixture version is pinned", fixture["schema_version"] == 1)
    check("benchmark contains exactly twelve cases", summary["case_count"] == 12)
    check("case ids are unique", summary["unique_case_count"] == 12)
    check("two repetitions produce twenty-four baseline generations", summary["baseline_generations"] == 24)
    check("paid baseline estimate stays below two dollars", summary["estimated_baseline_cost_usd"] < 2.0)
    check("quote delivery is required off", fixture["constraints"]["quote_selection_enabled"] is False)


def test_fixture_loader_requires_the_complete_blind_comparison_contract():
    fixture = json.loads(
        (ROOT / "scripts" / "answer_latency_benchmark_cases.json").read_text()
    )
    contract = fixture.get("comparison_contract")
    check("fixture pins a blind comparison contract", isinstance(contract, dict))
    check("comparison runs two repetitions per variant", contract["repetitions_per_variant"] == 2)
    check("each paid variant has a $2.50 ceiling", contract["cost_ceiling_usd_per_variant"] == 2.5)
    check(
        "latency gate requires twenty-percent median improvement",
        contract["latency"]["minimum_median_improvement_fraction"] == 0.20,
    )
    check("latency gate requires ten paired case wins", contract["latency"]["minimum_paired_case_wins"] == 10)
    check("latency gate forbids p90 regression", contract["latency"]["allow_p90_regression"] is False)
    check(
        "all protected quality axes are pinned",
        contract["quality_axes"] == [
            "theological_accuracy",
            "teacher_representation",
            "retrieval_depth",
            "citation_source_faithfulness",
            "durable_job_recoverability",
        ],
    )
    check("blind packet hides variant identity", "variant" in contract["blind_fields_hidden"])
    check("blind packet hides timing identity", "trace" in contract["blind_fields_hidden"])

    del fixture["comparison_contract"]["quality_axes"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.json"
        path.write_text(json.dumps(fixture))
        try:
            load_fixture(path)
        except ValueError as exc:
            check("incomplete blind comparison contracts fail closed", "comparison_contract" in str(exc))
        else:
            raise AssertionError("fixture without protected quality axes was accepted")


def test_fixture_loader_rejects_duplicate_ids():
    fixture = {
        "schema_version": 1,
        "constraints": {"quote_selection_enabled": False},
        "cases": [
            {"id": "duplicate", "category": "ordinary", "question": "One?", "messages": []},
            {"id": "duplicate", "category": "ordinary", "question": "Two?", "messages": []},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.json"
        path.write_text(json.dumps(fixture))
        try:
            load_fixture(path)
        except ValueError as exc:
            check("duplicate ids fail closed", "duplicate case id" in str(exc))
        else:
            raise AssertionError("duplicate fixture ids were accepted")


def test_runtime_constraints_fail_closed():
    fixture = load_fixture(ROOT / "scripts" / "answer_latency_benchmark_cases.json")
    assert_runtime_constraints(
        fixture,
        quote_selection_enabled=False,
        generation_model="claude-sonnet-5",
        prompt_version="prompt_6ea8b855b412",
        policy_version="policy_v3:quote_selection=false",
    )
    try:
        assert_runtime_constraints(
            fixture,
            quote_selection_enabled=True,
            generation_model="claude-sonnet-5",
            prompt_version="prompt_6ea8b855b412",
            policy_version="policy_v3:quote_selection=true",
        )
    except RuntimeError as exc:
        check("quote-on runtime is refused", "quote selection must be disabled" in str(exc))
    else:
        raise AssertionError("quote-on runtime was accepted")


def test_query_expansion_uses_the_available_groq_model():
    class AvailableModelOnly:
        def create(self, **kwargs):
            if kwargs.get("model") != "openai/gpt-oss-120b":
                raise RuntimeError("model unavailable")
            message = SimpleNamespace(content=json.dumps({
                "paraphrases": ["How does fasting work?", "What is biblical fasting?"],
                "keywords": "fasting prayer scripture",
            }))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=AvailableModelOnly())
    )
    with (
        patch.object(answer_toolbox, "_get_ai", return_value=fake_client),
        patch.object(answer_toolbox.logger, "exception", return_value=None),
    ):
        variants, keywords = answer_toolbox.expand_query("What is fasting?")

    check("query expansion reaches the available Groq model", len(variants) == 3)
    check("query expansion retains provider keywords", keywords == "fasting prayer scripture")


def test_query_expansion_preflight_rejects_silent_fallback():
    probe = "How does biblical covenant language shape interpretation?"
    try:
        assert_query_expansion_available(
            lambda question: ([question], None),
            model="unavailable-model",
            probe=probe,
        )
    except RuntimeError as exc:
        check("query-expansion fallback fails the paid preflight", "fell back" in str(exc))
    else:
        raise AssertionError("silent query-expansion fallback passed preflight")

    result = assert_query_expansion_available(
        lambda question: ([question, "Covenant themes in biblical interpretation"], "covenant interpretation"),
        model="available-model",
        probe=probe,
    )
    check("query-expansion preflight records its model", result["model"] == "available-model")
    check("query-expansion preflight records variant depth", result["variant_count"] == 2)
    check("query-expansion preflight records keyword routing", result["keywords_present"] is True)


def test_run_case_records_trace_without_source_text():
    case = {
        "id": "case-1",
        "category": "ordinary",
        "question": "What does the source teach?",
        "messages": [],
    }

    def fake_produce(db, question, messages=None, topics_established=None, trace=None):
        with trace.span("producer.total"):
            pass
        return ProducerResult(
            answer="A grounded answer [1].",
            outcome="answered",
            citations=[{
                "chunk_id": "chunk-1",
                "document_title": "Test source",
                "author": "Test Teacher",
                "content": "copyrighted source text must not enter the trace",
                "url": "https://example.test/source",
            }],
            verified_references=[{"kind": "verse"}],
            retrieved_chunk_ids=["chunk-1", "chunk-2"],
            retrieved_point_ids=["chunk-1"],
            model="claude-sonnet-5",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.01,
            quote_ids=[],
        )

    record = run_case(case, repetition=2, supabase=object(), produce_fn=fake_produce)
    check("run record identifies the fixture and repetition", record["case_id"] == "case-1" and record["repetition"] == 2)
    check("run record retains answer text for blind review", record["answer"] == "A grounded answer [1].")
    check("run record retains source identity", record["citations"][0]["chunk_id"] == "chunk-1")
    check("run record excludes source passage text", "content" not in record["citations"][0])
    check("run record includes stage timing", record["trace"]["stages"][0]["name"] == "producer.total")
    check("run record reconciles retrieval depth", record["retrieved_chunk_count"] == 2 and record["retrieved_point_count"] == 1)


def test_run_case_records_and_forwards_the_candidate_variant():
    seen = []

    def fake_produce(
        db, question, messages=None, topics_established=None, trace=None,
        experimental_teacher_routing=False,
    ):
        seen.append(experimental_teacher_routing)
        with trace.span("producer.total"):
            pass
        return ProducerResult(
            answer="Candidate answer.", outcome="answered", model="test-model"
        )

    case = {
        "id": "candidate-case",
        "category": "named_teacher",
        "question": "What does Derek Prince teach about deliverance?",
        "messages": [],
    }
    try:
        record = run_case(
            case,
            repetition=1,
            supabase=object(),
            produce_fn=fake_produce,
            variant="teacher_specific_v1",
        )
    except TypeError:
        check("run_case accepts the approved candidate variant", False)
        return

    check("candidate variant reaches the producer", seen == [True])
    check("candidate variant is retained for blind pairing", record["variant"] == "teacher_specific_v1")


def main():
    test_trace_records_nested_monotonic_spans()
    test_generation_trace_is_observational_only()
    test_generation_effort_defaults_to_unset_and_is_recorded_when_requested()
    test_run_case_forwards_the_effort_candidate_variant()
    test_producer_trace_covers_the_guarded_answer_path()
    test_experimental_teacher_routing_only_bypasses_topic_positions_when_required()
    test_explicit_named_teacher_source_boundary()
    test_candidate_neighbor_expansion_hard_caps_an_oversized_initial_pool()
    test_fixture_contract_is_bounded_and_unique()
    test_fixture_loader_requires_the_complete_blind_comparison_contract()
    test_fixture_loader_rejects_duplicate_ids()
    test_runtime_constraints_fail_closed()
    test_query_expansion_uses_the_available_groq_model()
    test_query_expansion_preflight_rejects_silent_fallback()
    test_run_case_records_trace_without_source_text()
    test_run_case_records_and_forwards_the_candidate_variant()
    print("All answer-latency benchmark checks passed.")


if __name__ == "__main__":
    main()
