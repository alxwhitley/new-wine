#!/usr/bin/env python3.12
"""Read-only biblical coverage audit fixture and runner.

The safe default validates and summarizes the fixture only. Networked retrieval
and paid answer sampling are opt-in modes added behind explicit flags.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = ROOT / "scripts" / "biblical_coverage_cases.json"

DOMAIN_IDS = (
    "storyline_covenant",
    "god_christ_spirit",
    "creation_sin_salvation",
    "formation_wisdom_suffering",
    "church_worship_mission",
    "old_testament_passages",
    "new_testament_passages",
    "language_history_context",
)

READ_RPC_NAMES = frozenset({"match_chunks", "search_chunks_fts", "match_lexicon_chunks"})
READ_TABLE_NAMES = frozenset({
    "app_settings", "background_topics", "chunks", "documents",
    "generation_model_config", "position_evidence", "positions", "propositions",
    "source_aliases", "source_toggles", "sources", "verses",
})
READ_QUERY_METHODS = frozenset({
    "eq", "execute", "in_", "limit", "neq", "or_", "order", "select",
})
MUTATION_METHODS = frozenset({"delete", "insert", "update", "upsert"})


class ReadOnlyQuery:
    """Fail-closed proxy for the query methods used by answer retrieval."""

    def __init__(self, query: Any):
        self._query = query

    def __getattr__(self, name: str):
        if name in MUTATION_METHODS:
            raise RuntimeError(f"forbidden mutation method in coverage audit: {name}")
        if name not in READ_QUERY_METHODS:
            raise RuntimeError(f"query method is not allowlisted for coverage audit: {name}")
        method = getattr(self._query, name)

        def call(*args, **kwargs):
            result = method(*args, **kwargs)
            if name == "execute":
                return result
            return ReadOnlyQuery(result)

        return call


class ReadOnlySupabase:
    """Allow only the exact table reads and search RPCs needed by retrieval."""

    def __init__(self, client: Any):
        self._client = client

    def table(self, name: str) -> ReadOnlyQuery:
        if name not in READ_TABLE_NAMES:
            raise RuntimeError(f"table is not allowlisted for coverage audit: {name}")
        return ReadOnlyQuery(self._client.table(name))

    def rpc(self, name: str, params: Dict[str, Any]) -> ReadOnlyQuery:
        if name not in READ_RPC_NAMES:
            raise RuntimeError(f"RPC is not allowlisted for coverage audit: {name}")
        return ReadOnlyQuery(self._client.rpc(name, params))


def load_fixture(path: Path) -> Dict[str, Any]:
    fixture = json.loads(path.read_text())
    if fixture.get("schema_version") != 1:
        raise ValueError("fixture schema_version must be 1")
    constraints = fixture.get("constraints")
    if not isinstance(constraints, dict):
        raise ValueError("fixture constraints must be an object")
    expected_constraints = {
        "database_writes_allowed": False,
        "llm_judge_allowed": False,
        "answer_sample_size": 12,
        "max_paid_cost_usd": 1.50,
    }
    for key, expected in expected_constraints.items():
        if constraints.get(key) != expected:
            raise ValueError(f"fixture constraint {key} must be {expected!r}")

    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != 48:
        raise ValueError("fixture must contain exactly 48 cases")
    ids = set()
    questions = set()
    domain_counts: Counter[str] = Counter()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every case must be an object")
        case_id = case.get("id")
        question = case.get("question")
        domain = case.get("domain")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
            raise ValueError(f"case id must be unique and nonempty: {case_id!r}")
        if not isinstance(question, str) or not question.strip() or question in questions:
            raise ValueError(f"question must be unique and nonempty: {question!r}")
        if domain not in DOMAIN_IDS:
            raise ValueError(f"unknown domain for {case_id}: {domain!r}")
        if case.get("named_teacher_intent") is not False:
            raise ValueError(f"case {case_id} must explicitly exclude named-teacher intent")
        ids.add(case_id)
        questions.add(question)
        domain_counts[domain] += 1
    if set(domain_counts) != set(DOMAIN_IDS) or set(domain_counts.values()) != {6}:
        raise ValueError("fixture must contain exactly six cases in every domain")
    answer_sample = fixture.get("answer_sample")
    if not isinstance(answer_sample, list) or len(answer_sample) != 12:
        raise ValueError("fixture answer_sample must contain exactly 12 cases")
    valid_case_ids = {case["id"] for case in cases}
    sample_ids = [item.get("case_id") for item in answer_sample if isinstance(item, dict)]
    if len(sample_ids) != 12 or len(set(sample_ids)) != 12 or not set(sample_ids) <= valid_case_ids:
        raise ValueError("answer_sample case ids must be unique and exist in cases")
    sample_classes = Counter(item.get("retrieval_classification") for item in answer_sample)
    if sample_classes != {"strong": 4, "thin": 4, "empty_or_misretrieved": 4}:
        raise ValueError("answer_sample must balance four cases in each retrieval class")
    return fixture


def summarize_fixture(fixture: Dict[str, Any]) -> Dict[str, Any]:
    cases = fixture["cases"]
    domain_counts = Counter(case["domain"] for case in cases)
    return {
        "case_count": len(cases),
        "unique_case_count": len({case["id"] for case in cases}),
        "unique_question_count": len({case["question"] for case in cases}),
        "named_teacher_case_count": sum(
            1 for case in cases if case["named_teacher_intent"]
        ),
        "domain_counts": dict(sorted(domain_counts.items())),
        "constraints": fixture["constraints"],
    }


def validated_output_path(path: Path) -> Path:
    resolved = path.resolve()
    local_root = (ROOT / "local").resolve()
    try:
        resolved.relative_to(local_root)
    except ValueError as exc:
        raise ValueError(f"coverage output must stay under {local_root}") from exc
    return resolved


def _bounded_excerpt(content: Any, limit: int = 400) -> str:
    return " ".join(str(content or "").split())[:limit]


def retrieval_record(
    case: Dict[str, Any],
    chunks: Iterable[Dict[str, Any]],
    citations: Iterable[Dict[str, Any]],
    *,
    citable_count: int,
    fallback_to_paper_voice: bool,
) -> Dict[str, Any]:
    chunk_list = list(chunks)
    citation_list = list(citations)
    source_kinds = Counter(
        str(chunk.get("source_kind") or chunk.get("source_type") or "unknown")
        for chunk in chunk_list
    )
    document_ids = {chunk.get("document_id") for chunk in chunk_list if chunk.get("document_id")}
    authors = {str(chunk.get("author")).strip() for chunk in chunk_list if chunk.get("author")}
    evidence = [
        {
            "chunk_id": chunk.get("id"),
            "document_id": chunk.get("document_id"),
            "title": chunk.get("title"),
            "author": chunk.get("author"),
            "source_kind": chunk.get("source_kind") or chunk.get("source_type") or "unknown",
            "citation_mode": chunk.get("citation_mode"),
            "excerpt": _bounded_excerpt(chunk.get("content")),
        }
        for chunk in chunk_list
    ]
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case["id"],
        "domain": case["domain"],
        "question": case["question"],
        "retrieved_chunk_count": len(chunk_list),
        "citation_count": len(citation_list),
        "citable_count_before_neighbor_expansion": citable_count,
        "unique_document_count": len(document_ids),
        "unique_author_count": len(authors),
        "source_kind_counts": dict(sorted(source_kinds.items())),
        "fallback_to_paper_voice": fallback_to_paper_voice,
        "commentary_word_study_policy": "hard_excluded",
        "evidence": evidence,
        "classification": None,
    }


def answer_record(
    case: Dict[str, Any], retrieval_classification: str, result: Any,
) -> Dict[str, Any]:
    citations = [
        {key: citation.get(key) for key in ("chunk_id", "document_title", "author", "url")}
        for citation in result.citations
    ]
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case["id"],
        "domain": case["domain"],
        "question": case["question"],
        "retrieval_classification": retrieval_classification,
        "outcome": result.outcome,
        "answer": result.answer,
        "answer_chars": len(result.answer),
        "citations": citations,
        "citation_count": len(citations),
        "verified_reference_count": len(result.verified_references),
        "retrieved_chunk_count": len(result.retrieved_chunk_ids),
        "retrieved_point_count": len(result.retrieved_point_ids),
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cache_read_tokens": result.cache_read_tokens,
        "cache_write_tokens": result.cache_write_tokens,
        "cost_usd": result.cost_usd,
        "quote_ids": list(result.quote_ids),
        "review": None,
    }


def _selected_cases(fixture: Dict[str, Any], case_id: str | None) -> list[Dict[str, Any]]:
    cases = fixture["cases"]
    if not case_id:
        return cases
    selected = [case for case in cases if case["id"] == case_id]
    if not selected:
        raise SystemExit(f"unknown --case-id: {case_id}")
    return selected


def run_retrieval(fixture: Dict[str, Any], *, output: Path, case_id: str | None) -> None:
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing coverage output: {output}")
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db.supabase import get_supabase
    from app.services import source_filter
    from app.services.async_answers.producer import _retrieve

    db = ReadOnlySupabase(get_supabase())
    source_filter.get_supabase = lambda: db
    source_filter._cache = None
    source_filter._cache_ts = 0.0

    counts = {"attempted": 0, "completed": 0, "errored": 0, "skipped": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        for case in _selected_cases(fixture, case_id):
            counts["attempted"] += 1
            try:
                chunks, citations, citable_count, fallback = _retrieve(db, case["question"])
                record = retrieval_record(
                    case,
                    chunks,
                    citations,
                    citable_count=citable_count,
                    fallback_to_paper_voice=fallback,
                )
            except Exception as exc:
                counts["errored"] += 1
                record = {
                    "schema_version": 1,
                    "case_id": case["id"],
                    "domain": case["domain"],
                    "question": case["question"],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            else:
                counts["completed"] += 1
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
    print(json.dumps({"output": str(output), "counts": counts}, indent=2, sort_keys=True))
    if counts["errored"] or counts["skipped"]:
        raise SystemExit(1)


def selected_answer_sample(
    fixture: Dict[str, Any], *, case_id: str | None, excluded_case_ids: Iterable[str],
) -> list[Dict[str, Any]]:
    excluded = set(excluded_case_ids)
    sample = [item for item in fixture["answer_sample"] if item["case_id"] not in excluded]
    if case_id:
        sample = [item for item in sample if item["case_id"] == case_id]
        if not sample:
            raise SystemExit(f"unknown or excluded --answer-case-id: {case_id}")
    return sample


def run_paid_answers(
    fixture: Dict[str, Any], *, output: Path, case_id: str | None,
    excluded_case_ids: Iterable[str], max_cost_usd: float,
) -> None:
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing coverage output: {output}")
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db.supabase import get_supabase
    from app.services import answer_toolbox, llm_client, position_papers, source_filter
    from app.services.async_answers import producer
    from app.services.quotes import quote_selection_enabled

    if quote_selection_enabled(os.environ):
        raise SystemExit("quote selection must remain disabled for the coverage audit")

    db = ReadOnlySupabase(get_supabase())
    for module in (answer_toolbox, llm_client, position_papers, source_filter):
        module.get_supabase = lambda db=db: db
    source_filter._cache = None
    source_filter._cache_ts = 0.0
    llm_client._model_cache = None
    llm_client._model_cache_ts = 0.0
    answer_toolbox._background_topics_loaded = False

    case_by_id = {case["id"]: case for case in fixture["cases"]}
    approved_ceiling = float(fixture["constraints"]["max_paid_cost_usd"])
    if max_cost_usd <= 0 or max_cost_usd > approved_ceiling:
        raise SystemExit(
            f"--max-cost-usd must be positive and no more than approved ${approved_ceiling:.2f}"
        )
    ceiling = max_cost_usd
    per_answer_reserve = approved_ceiling / len(fixture["answer_sample"])
    sample = selected_answer_sample(
        fixture, case_id=case_id, excluded_case_ids=excluded_case_ids,
    )
    counts = {"attempted": 0, "completed": 0, "errored": 0, "skipped": 0}
    total_cost = 0.0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        for selection in sample:
            case = case_by_id[selection["case_id"]]
            if total_cost + per_answer_reserve > ceiling + 1e-9:
                counts["skipped"] += 1
                continue
            counts["attempted"] += 1
            try:
                result = producer.produce(db, case["question"])
                record = answer_record(
                    case, selection["retrieval_classification"], result,
                )
                total_cost += float(result.cost_usd or 0.0)
                if result.quote_ids:
                    raise RuntimeError("quote ids were produced while quote selection was disabled")
                if total_cost > ceiling + 1e-9:
                    raise RuntimeError(
                        f"paid ceiling exceeded: ${total_cost:.6f} > ${ceiling:.2f}"
                    )
            except Exception as exc:
                counts["errored"] += 1
                record = {
                    "schema_version": 1,
                    "case_id": case["id"],
                    "domain": case["domain"],
                    "question": case["question"],
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1000],
                }
            else:
                counts["completed"] += 1
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
    print(json.dumps({
        "output": str(output),
        "counts": counts,
        "cost_usd": round(total_cost, 6),
        "cost_ceiling_usd": ceiling,
    }, indent=2, sort_keys=True))
    if counts["errored"] or counts["skipped"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or run the biblical coverage audit")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--run-retrieval-readonly", action="store_true")
    parser.add_argument("--run-paid-readonly", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--answer-case-id")
    parser.add_argument("--exclude-answer-case-id", action="append", default=[])
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    if args.run_paid_readonly and args.run_retrieval_readonly:
        raise SystemExit("choose one run mode")
    if args.run_paid_readonly:
        if args.output is None:
            raise SystemExit("--output under local/ is required for paid answers")
        run_paid_answers(
            fixture,
            output=validated_output_path(args.output),
            case_id=args.answer_case_id,
            excluded_case_ids=args.exclude_answer_case_id,
            max_cost_usd=(
                args.max_cost_usd
                if args.max_cost_usd is not None
                else float(fixture["constraints"]["max_paid_cost_usd"])
            ),
        )
        return
    if args.run_retrieval_readonly:
        if args.output is None:
            raise SystemExit("--output under local/ is required for retrieval")
        run_retrieval(
            fixture,
            output=validated_output_path(args.output),
            case_id=args.case_id,
        )
        return
    print(json.dumps(summarize_fixture(fixture), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
