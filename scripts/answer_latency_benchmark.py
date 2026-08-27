#!/usr/bin/env python3.12
"""B6 read-only answer-latency benchmark harness.

The safe default is fixture validation only. Paid generation requires the
explicit --run-paid-readonly flag and refuses to start while quote selection is
enabled. It calls producer.produce() directly, so it creates no answer_jobs,
conversation, message, or metering rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = ROOT / "scripts" / "answer_latency_benchmark_cases.json"
BASELINE_REPETITIONS = 2
ESTIMATED_COST_PER_GENERATION_USD = 0.075
BASELINE_COST_CEILING_USD = 2.50
BENCHMARK_VARIANTS = ("baseline", "teacher_specific_v1", "effort_medium_v1")
QUERY_EXPANSION_PROBE = "How does biblical covenant language shape interpretation?"
PROTECTED_QUALITY_AXES = [
    "theological_accuracy",
    "teacher_representation",
    "retrieval_depth",
    "citation_source_faithfulness",
    "durable_job_recoverability",
]


def load_fixture(path: Path) -> Dict[str, Any]:
    fixture = json.loads(path.read_text())
    if fixture.get("schema_version") != 1:
        raise ValueError("fixture schema_version must be 1")
    constraints = fixture.get("constraints")
    if not isinstance(constraints, dict) or constraints.get("quote_selection_enabled") is not False:
        raise ValueError("fixture must require quote_selection_enabled=false")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture cases must be a non-empty list")
    seen = set()
    for case in cases:
        case_id = case.get("id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("every case requires a non-empty string id")
        if case_id in seen:
            raise ValueError("duplicate case id: %s" % case_id)
        seen.add(case_id)
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError("case %s requires a non-empty question" % case_id)
        if not isinstance(case.get("messages", []), list):
            raise ValueError("case %s messages must be a list" % case_id)
    comparison = fixture.get("comparison_contract")
    latency = comparison.get("latency") if isinstance(comparison, dict) else None
    blind_fields = comparison.get("blind_fields_hidden", []) if isinstance(comparison, dict) else []
    if (
        not isinstance(comparison, dict)
        or comparison.get("repetitions_per_variant") != BASELINE_REPETITIONS
        or comparison.get("cost_ceiling_usd_per_variant") != BASELINE_COST_CEILING_USD
        or not isinstance(latency, dict)
        or latency.get("minimum_median_improvement_fraction") != 0.20
        or latency.get("minimum_paired_case_wins") != 10
        or latency.get("allow_p90_regression") is not False
        or comparison.get("quality_axes") != PROTECTED_QUALITY_AXES
        or comparison.get("human_review_required") is not True
        or not {"variant", "model", "trace", "cost_usd"}.issubset(set(blind_fields))
        or not comparison.get("hard_failures")
    ):
        raise ValueError("fixture comparison_contract is incomplete or changed")
    return fixture


def summarize_fixture(fixture: Dict[str, Any]) -> Dict[str, Any]:
    ids = [case["id"] for case in fixture["cases"]]
    generations = len(ids) * BASELINE_REPETITIONS
    return {
        "case_count": len(ids),
        "unique_case_count": len(set(ids)),
        "baseline_repetitions": BASELINE_REPETITIONS,
        "baseline_generations": generations,
        "estimated_baseline_cost_usd": round(
            generations * ESTIMATED_COST_PER_GENERATION_USD, 2
        ),
    }


def assert_runtime_constraints(
    fixture: Dict[str, Any],
    *,
    quote_selection_enabled: bool,
    generation_model: str,
    prompt_version: str,
    policy_version: str,
) -> None:
    constraints = fixture["constraints"]
    if quote_selection_enabled:
        raise RuntimeError("quote selection must be disabled for the B6 benchmark")
    expected = {
        "generation_model": generation_model,
        "prompt_version": prompt_version,
        "policy_version": policy_version,
    }
    for key, actual in expected.items():
        wanted = constraints.get(key)
        if wanted != actual:
            raise RuntimeError("runtime %s=%r does not match fixture %r" % (key, actual, wanted))


def assert_query_expansion_available(
    expand_fn: Callable[[str], Any],
    *,
    model: str,
    probe: str = QUERY_EXPANSION_PROBE,
) -> Dict[str, Any]:
    """Fail before a paid benchmark when expansion silently degrades."""
    variants, keywords = expand_fn(probe)
    if len(variants) < 2:
        raise RuntimeError(
            "query expansion fell back to the original query; refusing paid benchmark"
        )
    return {
        "model": model,
        "variant_count": len(variants),
        "keywords_present": bool(keywords),
    }


def _citation_metadata(citation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: citation.get(key)
        for key in ("chunk_id", "document_title", "author", "url")
    }


def run_case(
    case: Dict[str, Any],
    *,
    repetition: int,
    supabase: Any,
    produce_fn: Optional[Callable[..., Any]] = None,
    runtime_metadata: Optional[Dict[str, Any]] = None,
    variant: str = "baseline",
) -> Dict[str, Any]:
    from app.services.async_answers.latency_trace import LatencyTrace
    if produce_fn is None:
        from app.services.async_answers.producer import produce as produce_fn

    trace = LatencyTrace()
    trace.annotate(case_id=case["id"], repetition=repetition)
    messages = case.get("messages") or []
    topics_established = case.get("topics_established") or {}
    if variant not in BENCHMARK_VARIANTS:
        raise ValueError("unknown benchmark variant: %s" % variant)
    producer_options = {}
    if variant == "teacher_specific_v1":
        producer_options["experimental_teacher_routing"] = True
    elif variant == "effort_medium_v1":
        producer_options["experimental_generation_effort"] = "medium"
    result = produce_fn(
        supabase,
        case["question"],
        messages,
        topics_established,
        trace=trace,
        **producer_options,
    )
    if result.quote_ids:
        raise RuntimeError("quote ids were produced while the B6 quote-off constraint was active")

    record = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "messages_sha256": hashlib.sha256(
            json.dumps(messages, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "repetition": repetition,
        "variant": variant,
        "answer": result.answer,
        "answer_chars": len(result.answer),
        "outcome": result.outcome,
        "citations": [_citation_metadata(c) for c in result.citations],
        "citation_count": len(result.citations),
        "verified_reference_count": len(result.verified_references),
        "retrieved_chunk_ids": list(result.retrieved_chunk_ids),
        "retrieved_point_ids": list(result.retrieved_point_ids),
        "retrieved_chunk_count": len(result.retrieved_chunk_ids),
        "retrieved_point_count": len(result.retrieved_point_ids),
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cache_read_tokens": result.cache_read_tokens,
        "cache_write_tokens": result.cache_write_tokens,
        "cost_usd": result.cost_usd,
        "quote_ids": [],
        "trace": trace.to_dict(),
    }
    if runtime_metadata:
        record["runtime"] = dict(runtime_metadata)
    return record


def _local_output_path(path: Path) -> Path:
    resolved = path.resolve()
    local_root = (ROOT / "local").resolve()
    try:
        resolved.relative_to(local_root)
    except ValueError as exc:
        raise ValueError("benchmark output must stay under %s" % local_root) from exc
    return resolved


def _run_paid_readonly(args, fixture: Dict[str, Any]) -> None:
    if args.output is None:
        raise SystemExit("--output under local/ is required for a paid read-only run")
    output = _local_output_path(args.output)
    if output.exists():
        raise SystemExit("refusing to overwrite existing benchmark output: %s" % output)

    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / "app" / ".env")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.db.supabase import get_supabase
    from app.services import answer_toolbox
    from app.services.async_answers.producer import POLICY_VERSION, PROMPT_VERSION
    from app.services.llm_client import get_generation_model
    from app.services.quotes import quote_selection_enabled

    model = get_generation_model()
    quote_on = quote_selection_enabled(os.environ)
    policy = "%s:quote_selection=%s" % (POLICY_VERSION, "true" if quote_on else "false")
    assert_runtime_constraints(
        fixture,
        quote_selection_enabled=quote_on,
        generation_model=model,
        prompt_version=PROMPT_VERSION,
        policy_version=policy,
    )
    query_expansion = assert_query_expansion_available(
        answer_toolbox.expand_query,
        model=answer_toolbox.GROQ_MODEL,
    )

    cases = fixture["cases"]
    if args.case_id:
        cases = [case for case in cases if case["id"] == args.case_id]
        if not cases:
            raise SystemExit("unknown --case-id: %s" % args.case_id)
    elif args.repetitions != BASELINE_REPETITIONS:
        raise SystemExit("the full baseline requires exactly two repetitions")

    output.parent.mkdir(parents=True, exist_ok=True)
    counts = {"attempted": 0, "completed": 0, "errored": 0, "skipped": 0}
    total_cost = 0.0
    supabase = get_supabase()
    runtime = {
        "generation_model": model,
        "prompt_version": PROMPT_VERSION,
        "policy_version": policy,
        "quote_selection_enabled": False,
        "query_expansion": query_expansion,
    }
    with output.open("x") as handle:
        for repetition in range(1, args.repetitions + 1):
            for case in cases:
                if total_cost + ESTIMATED_COST_PER_GENERATION_USD > args.max_cost_usd:
                    counts["skipped"] += 1
                    continue
                counts["attempted"] += 1
                try:
                    record = run_case(
                        case,
                        repetition=repetition,
                        supabase=supabase,
                        runtime_metadata=runtime,
                        variant=args.variant,
                    )
                except Exception as exc:
                    counts["errored"] += 1
                    error_record = {
                        "schema_version": 1,
                        "case_id": case["id"],
                        "repetition": repetition,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1000],
                    }
                    handle.write(json.dumps(error_record, sort_keys=True) + "\n")
                    handle.flush()
                    continue
                counts["completed"] += 1
                total_cost += float(record["cost_usd"] or 0.0)
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()

    print(json.dumps({
        "output": str(output),
        "counts": counts,
        "cost_usd": round(total_cost, 6),
        "cost_ceiling_usd": args.max_cost_usd,
    }, indent=2, sort_keys=True))
    if counts["errored"] or counts["skipped"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or run the B6 latency benchmark")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--run-paid-readonly",
        action="store_true",
        help="Run real provider generations without creating production rows",
    )
    parser.add_argument("--case-id", help="Run one named fixture case before the full baseline")
    parser.add_argument("--repetitions", type=int, default=BASELINE_REPETITIONS)
    parser.add_argument("--variant", choices=BENCHMARK_VARIANTS, default="baseline")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-cost-usd", type=float, default=BASELINE_COST_CEILING_USD)
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    if args.run_paid_readonly:
        _run_paid_readonly(args, fixture)
        return
    payload = summarize_fixture(fixture)
    payload["cases"] = [{"id": case["id"], "category": case["category"]} for case in fixture["cases"]]
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
