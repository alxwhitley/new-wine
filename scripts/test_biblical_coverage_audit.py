#!/usr/bin/env python3.12
"""Deterministic checks for the biblical coverage audit harness."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from biblical_coverage_audit import (  # noqa: E402
    DEFAULT_FIXTURE,
    DOMAIN_IDS,
    ReadOnlySupabase,
    answer_record,
    load_fixture,
    retrieval_record,
    selected_answer_sample,
    summarize_fixture,
    validated_output_path,
)


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print("OK:", label)


def test_fixture_contract() -> None:
    fixture = load_fixture(DEFAULT_FIXTURE)
    summary = summarize_fixture(fixture)
    check("fixture schema is versioned", fixture["schema_version"] == 1)
    check("fixture contains exactly 48 cases", summary["case_count"] == 48)
    check("all case ids are unique", summary["unique_case_count"] == 48)
    check("all questions are unique", summary["unique_question_count"] == 48)
    check("all eight domains are present", set(summary["domain_counts"]) == set(DOMAIN_IDS))
    check(
        "every domain contains exactly six cases",
        set(summary["domain_counts"].values()) == {6},
    )
    check("fixture excludes named-teacher intent", summary["named_teacher_case_count"] == 0)
    check("paid answer sample is capped at twelve", fixture["constraints"]["answer_sample_size"] == 12)
    check("paid ceiling is exactly $1.50", fixture["constraints"]["max_paid_cost_usd"] == 1.50)
    check("database writes are forbidden", fixture["constraints"]["database_writes_allowed"] is False)
    check("LLM judging is forbidden", fixture["constraints"]["llm_judge_allowed"] is False)
    sample = fixture["answer_sample"]
    check("answer sample contains exactly twelve cases", len(sample) == 12)
    check("answer sample ids are unique", len({item["case_id"] for item in sample}) == 12)
    check(
        "answer sample balances four strong, four thin, and four empty/misretrieved",
        {key: value for key, value in __import__("collections").Counter(
            item["retrieval_classification"] for item in sample
        ).items()} == {"strong": 4, "thin": 4, "empty_or_misretrieved": 4},
    )


class FakeQuery:
    def __init__(self) -> None:
        self.calls = []

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def eq(self, column: str, value: object):
        self.calls.append(("eq", column, value))
        return self

    def insert(self, _payload: object):
        raise AssertionError("underlying insert must never be reached")

    def execute(self):
        return SimpleNamespace(data=[])


class FakeSupabase:
    def __init__(self) -> None:
        self.query = FakeQuery()
        self.rpc_calls = []

    def table(self, name: str):
        self.table_name = name
        return self.query

    def rpc(self, name: str, params: dict):
        self.rpc_calls.append((name, params))
        return self.query


def test_readonly_boundary() -> None:
    wrapped = ReadOnlySupabase(FakeSupabase())
    wrapped.table("chunks").select("id").eq("id", "chunk-1").execute()
    check("read-only table chains are allowed", wrapped._client.table_name == "chunks")
    try:
        wrapped.table("chunks").insert({"id": "forbidden"})
    except RuntimeError as exc:
        check("table insert is blocked before I/O", "forbidden mutation" in str(exc))
    else:
        raise AssertionError("table insert was not blocked")
    wrapped.rpc("match_chunks", {"match_count": 1}).execute()
    check("known read RPC is allowed", wrapped._client.rpc_calls[-1][0] == "match_chunks")
    try:
        wrapped.rpc("unknown_or_write_rpc", {})
    except RuntimeError as exc:
        check("unknown RPC fails closed", "RPC is not allowlisted" in str(exc))
    else:
        raise AssertionError("unknown RPC was not blocked")


def test_retrieval_record_is_bounded_and_structured() -> None:
    chunks = [
        {
            "id": "chunk-1", "document_id": "doc-1", "title": "One",
            "author": "Author One", "source_kind": "book",
            "citation_mode": "citable", "content": "x" * 700,
        },
        {
            "id": "chunk-2", "document_id": "doc-2", "title": "Two",
            "author": "Author Two", "source_kind": "sermon_transcript",
            "citation_mode": "silent_context", "content": "short",
        },
    ]
    citations = [{"chunk_id": "chunk-1"}]
    record = retrieval_record(
        {"id": "case-1", "domain": "storyline_covenant", "question": "Question?"},
        chunks,
        citations,
        citable_count=1,
        fallback_to_paper_voice=False,
    )
    check("record counts retrieved chunks", record["retrieved_chunk_count"] == 2)
    check("record counts unique documents", record["unique_document_count"] == 2)
    check("record counts unique authors", record["unique_author_count"] == 2)
    check("record captures source-kind mix", record["source_kind_counts"] == {"book": 1, "sermon_transcript": 1})
    check("record bounds evidence excerpts", len(record["evidence"][0]["excerpt"]) == 400)
    check("record does not classify from counts", record["classification"] is None)


def test_output_is_confined_to_local() -> None:
    good = validated_output_path(ROOT / "local" / "coverage.jsonl")
    check("output under local is accepted", good.name == "coverage.jsonl")
    try:
        validated_output_path(ROOT / "docs" / "coverage.jsonl")
    except ValueError as exc:
        check("output outside local is rejected", "must stay under" in str(exc))
    else:
        raise AssertionError("output outside local was accepted")


def test_answer_record_captures_usage_without_judging() -> None:
    result = SimpleNamespace(
        answer="Grounded answer.", outcome="answered", citations=[{"chunk_id": "c1"}],
        verified_references=[{"verse_id": "JHN.1.1"}], retrieved_chunk_ids=["c1", "c2"],
        retrieved_point_ids=["c1"], model="test-model", input_tokens=100,
        output_tokens=20, cache_read_tokens=10, cache_write_tokens=0,
        cost_usd=0.0123, quote_ids=[],
    )
    record = answer_record(
        {"id": "case-1", "domain": "new_testament_passages", "question": "Question?"},
        "thin",
        result,
    )
    check("answer record retains measured classification", record["retrieval_classification"] == "thin")
    check("answer record captures actual cost", record["cost_usd"] == 0.0123)
    check("answer record captures retrieved depth", record["retrieved_chunk_count"] == 2)
    check("answer record leaves human review unset", record["review"] is None)


def test_answer_sample_can_checkpoint_then_resume_without_duplication() -> None:
    fixture = load_fixture(DEFAULT_FIXTURE)
    pilot = selected_answer_sample(fixture, case_id="spirit_work", excluded_case_ids=[])
    remainder = selected_answer_sample(
        fixture, case_id=None, excluded_case_ids=["spirit_work"],
    )
    check("single-case checkpoint selects one case", [x["case_id"] for x in pilot] == ["spirit_work"])
    check("resume set contains the other eleven cases", len(remainder) == 11)
    check("checkpoint and resume sets do not overlap", not ({x["case_id"] for x in pilot} & {x["case_id"] for x in remainder}))


def main() -> None:
    test_fixture_contract()
    test_readonly_boundary()
    test_retrieval_record_is_bounded_and_structured()
    test_output_is_confined_to_local()
    test_answer_record_captures_usage_without_judging()
    test_answer_sample_can_checkpoint_then_resume_without_duplication()
    print("\nBiblical coverage audit fixture checks passed.")


if __name__ == "__main__":
    main()
