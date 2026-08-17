#!/usr/bin/env python3
"""Repository-only regression coverage for the quote-selection containment gate.

Run from the repository root:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/test_quote_selection_gate.py
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services import quotes
from app.services.async_answers import producer
from app.services import (
    position_papers,
    reference_verifier,
    single_teacher_lock,
    stored_position_evidence,
    stored_position_topics,
)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if not condition:
        raise AssertionError(label)


def _producer_result_with_quote_gate(env_value, selector):
    """Exercise the real producer return value with all external work stubbed.

    The selection call is the one behavior under test; retrieval/generation are
    deterministic local fixtures so this test neither reads nor writes a database.
    """
    chunk = {
        "id": "chunk-1",
        "document_id": "document-1",
        "author": "Teacher One",
        "content": "Supported answer material.",
        "citation_mode": "citable",
    }
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(position_papers, "match_position_paper", return_value=None), \
         patch.object(stored_position_topics, "match_stored_position", return_value=None), \
         patch.object(stored_position_evidence, "fetch_stored_position_evidence", return_value=None), \
         patch.object(producer, "_inject_background_topics", return_value=([], set(), {})), \
         patch.object(producer, "_retrieve", return_value=([chunk], [], 1, False)), \
         patch.object(producer, "_build_context", return_value="context"), \
         patch.object(producer, "_build_history", return_value=[]), \
         patch.object(producer, "_generate_and_capture", return_value=("Teacher One gives a supported answer.", "raw", None, usage, "test-model")), \
         patch.object(reference_verifier, "build_retrieval_grounding", return_value={}), \
         patch.object(reference_verifier, "build_name_universe", return_value=[]), \
         patch.object(reference_verifier, "ungrounded_prose_teachers", return_value=False), \
         patch.object(reference_verifier, "verify_references", return_value=[]), \
         patch.object(producer, "estimate_cost_usd", return_value=0.0), \
         patch.object(single_teacher_lock, "resolve_source_ids_for_documents", return_value={"document-1": "source-1"}), \
         patch.object(quotes, "select_quotes_for_answer", selector):
        return producer.produce(object(), "What does the teacher say?")


def main():
    print("quote selection containment gate")
    print("=" * 60)

    check("absent flag disables quote selection", quotes.quote_selection_enabled({}) is False)
    check("false flag disables quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "false"}) is False)
    check("only exact true flag enables quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "true"}) is True)
    check("case variants do not enable quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "TRUE"}) is False)

    def selector_must_not_run(*_args, **_kwargs):
        raise AssertionError("disabled producer called quote selector")

    disabled_result = _producer_result_with_quote_gate(None, selector_must_not_run)
    check("disabled producer emits no quote IDs", disabled_result.quote_ids == [])

    enabled_result = _producer_result_with_quote_gate(
        "true", lambda *_args, **_kwargs: ["quote-1"]
    )
    check("enabled producer preserves selector output", enabled_result.quote_ids == ["quote-1"])


if __name__ == "__main__":
    main()
