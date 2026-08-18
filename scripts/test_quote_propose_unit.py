#!/usr/bin/env python3
"""Unit tests for app.services.quote_propose (parse / taxonomy / offsets).

No network, no DB. Includes a mutation check that the dry-run orchestration
path never calls create_and_approve_quote / raw INSERT helpers when those
are patched as forbidden.

Run from project root: python3 scripts/test_quote_propose_unit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.constants import VALID_TAGS
from app.services.quote_propose import (
    PROMPT_VERSION,
    ProposedQuote,
    build_propose_prompt,
    estimate_propose_cost_usd,
    filter_topic_ids,
    parse_propose_response,
    propose_from_window,
)

failures = []


def check(label: str, cond: bool, detail: str | None = None) -> None:
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)
        if detail:
            print("         %s" % detail)


def _window_with_quote() -> tuple[str, str, int, int]:
    prefix = "Opening throat-clearing. "
    quote = (
        "We're all going to answer to God personally for the lives we've led. "
        "I think it's important to bear that in mind."
    )
    suffix = " Then he continued with something else."
    window = prefix + quote + suffix
    start = len(prefix)
    end = start + len(quote)
    assert window[start:end] == quote
    return window, quote, start, end


def test_filter_topic_ids() -> None:
    print("\n1. filter_topic_ids:")
    # Pick two tags that exist in VALID_TAGS.
    known = sorted(VALID_TAGS)[:2]
    assert len(known) == 2
    out = filter_topic_ids(
        [known[0], "NOT_A_REAL_TAG", known[0], known[1], 12, None, ""]
    )
    check("keeps known tags only", out == [known[0], known[1]])
    check("dedupes", out.count(known[0]) == 1)
    check("unknown alone -> empty", filter_topic_ids(["Totally Fake Tag"]) == [])
    check("caps at 3", len(filter_topic_ids(sorted(VALID_TAGS)[:10])) == 3)


def test_parse_happy_path() -> None:
    print("\n2. parse happy path:")
    window, quote, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    payload = {
        "candidates": [
            {
                "quote_text": quote,
                "char_start": start,
                "char_end": end,
                "restated_point": "Each person answers to God for their life.",
                "topic_ids": [tag, "NOT_REAL"],
                "why_quotable": "Complete standalone claim about accountability.",
                "standalone_ok": True,
            }
        ]
    }
    cands, errors = parse_propose_response(json.dumps(payload), window)
    check("one candidate", len(cands) == 1, "got %d; errors=%s" % (len(cands), errors))
    check("no fatal errors", errors == [])
    if cands:
        c = cands[0]
        check("quote_text exact", c.quote_text == quote)
        check("offsets", c.char_start == start and c.char_end == end)
        check("unknown tag stripped", c.topic_ids == [tag])
        check("standalone_ok", c.standalone_ok is True)
        check("isinstance ProposedQuote", isinstance(c, ProposedQuote))


def test_offset_mismatch_refused() -> None:
    print("\n3. offset mismatch refused:")
    window, quote, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    payload = {
        "candidates": [
            {
                "quote_text": quote,
                "char_start": start + 1,  # wrong
                "char_end": end,
                "restated_point": "x",
                "topic_ids": [tag],
                "why_quotable": "y",
                "standalone_ok": True,
            }
        ]
    }
    cands, errors = parse_propose_response(json.dumps(payload), window)
    check("zero candidates", cands == [])
    check("offset_mismatch logged", any("offset_mismatch" in e for e in errors), str(errors))


def test_invented_quote_refused() -> None:
    print("\n4. invented quote text refused:")
    window, _, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    fake = "This sentence is not in the source window at all."
    payload = {
        "candidates": [
            {
                "quote_text": fake,
                "char_start": 0,
                "char_end": len(fake),
                "restated_point": "x",
                "topic_ids": [tag],
                "why_quotable": "y",
                "standalone_ok": True,
            }
        ]
    }
    # Offsets point at real window slice which won't equal fake → mismatch.
    cands, errors = parse_propose_response(json.dumps(payload), window)
    check("zero candidates", cands == [])
    check("has error", len(errors) >= 1)


def test_no_valid_tags_refused() -> None:
    print("\n5. no valid topic_ids refused:")
    window, quote, start, end = _window_with_quote()
    payload = {
        "candidates": [
            {
                "quote_text": quote,
                "char_start": start,
                "char_end": end,
                "restated_point": "x",
                "topic_ids": ["Definitely Not In Taxonomy"],
                "why_quotable": "y",
                "standalone_ok": True,
            }
        ]
    }
    cands, errors = parse_propose_response(json.dumps(payload), window)
    check("zero candidates", cands == [])
    check("no_valid_topic_ids", any("no_valid_topic_ids" in e for e in errors), str(errors))


def test_markdown_fence_and_standalone_false() -> None:
    print("\n6. markdown fence + standalone_ok false preserved:")
    window, quote, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    inner = {
        "candidates": [
            {
                "quote_text": quote,
                "char_start": start,
                "char_end": end,
                "restated_point": "x",
                "topic_ids": [tag],
                "why_quotable": "y",
                "standalone_ok": False,
            }
        ]
    }
    raw = "```json\n%s\n```" % json.dumps(inner)
    cands, errors = parse_propose_response(raw, window)
    check("parsed through fence", len(cands) == 1, str(errors))
    if cands:
        check("standalone_ok False kept", cands[0].standalone_ok is False)


def test_propose_from_window_uses_model_fn() -> None:
    print("\n7. propose_from_window with injected model_fn:")
    window, quote, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    payload = {
        "candidates": [
            {
                "quote_text": quote,
                "char_start": start,
                "char_end": end,
                "restated_point": "Accountability before God.",
                "topic_ids": [tag],
                "why_quotable": "Standalone doctrinal claim.",
                "standalone_ok": True,
            }
        ]
    }

    def fake_model(system: str, user: str) -> str:
        check("prompt_version in system", PROMPT_VERSION in system)
        check("taxonomy in system", "TAXONOMY" in system)
        check("SOURCE in user", user.startswith("SOURCE:"))
        return json.dumps(payload)

    batch = propose_from_window(window, model_fn=fake_model, model="mock-model")
    check("prompt_version stamped", batch.prompt_version == PROMPT_VERSION)
    check("model stamped", batch.model == "mock-model")
    check("one candidate", len(batch.candidates) == 1)


def test_build_prompt_includes_version() -> None:
    print("\n8. build_propose_prompt:")
    system, user = build_propose_prompt("hello world")
    check("version in system", "prompt_version=%s" % PROMPT_VERSION in system)
    check("user wraps SOURCE", "SOURCE:\nhello world" == user)


def test_cost_estimate_shape() -> None:
    print("\n9. estimate_propose_cost_usd:")
    est = estimate_propose_cost_usd(n_windows=90, avg_window_chars=1200)
    check("has est_cost_usd", "est_cost_usd" in est)
    check("positive cost", float(est["est_cost_usd"]) > 0)
    check("n_windows echoed", est["n_windows"] == 90)


def test_dry_run_orchestration_never_writes() -> None:
    """Mutation-style: dry-run helper must not touch write paths."""
    print("\n10. dry-run orchestration never calls write helpers:")
    # Import after path setup; patch the symbols the CLI would use.
    import propose_quotes_dry_run as dry  # noqa: E402

    window, quote, start, end = _window_with_quote()
    tag = sorted(VALID_TAGS)[0]
    payload = json.dumps(
        {
            "candidates": [
                {
                    "quote_text": quote,
                    "char_start": start,
                    "char_end": end,
                    "restated_point": "x",
                    "topic_ids": [tag],
                    "why_quotable": "y",
                    "standalone_ok": True,
                }
            ]
        }
    )

    calls = {"create": 0, "insert": 0}

    def forbidden_create(*args, **kwargs):
        calls["create"] += 1
        raise AssertionError("create_and_approve_quote must not be called in dry-run")

    def forbidden_insert(*args, **kwargs):
        calls["insert"] += 1
        raise AssertionError("raw INSERT helper must not be called in dry-run")

    chunk = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "title": "Fixture Sermon",
        "content": window,
        "teacher_source_id": "teacher-1",
        "chunk_index": 0,
    }

    with patch.object(dry, "create_and_approve_quote", new=forbidden_create), patch.object(
        dry, "raw_insert_quote", new=forbidden_insert
    ):
        rows = dry.evaluate_proposals_for_chunk(
            chunk,
            model_fn=lambda system, user: payload,
            run_verify=False,
        )

    check("produced rows", len(rows) >= 1, str(rows))
    check("create never called", calls["create"] == 0)
    check("insert never called", calls["insert"] == 0)
    check("no write side effects flag", all(r.get("wrote") is False for r in rows))


def main() -> int:
    print("\nquote_propose unit suite")
    print("=" * 60)
    test_filter_topic_ids()
    test_parse_happy_path()
    test_offset_mismatch_refused()
    test_invented_quote_refused()
    test_no_valid_tags_refused()
    test_markdown_fence_and_standalone_false()
    test_propose_from_window_uses_model_fn()
    test_build_prompt_includes_version()
    test_cost_estimate_shape()
    test_dry_run_orchestration_never_writes()

    print()
    if failures:
        print("%d check(s) failed" % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
