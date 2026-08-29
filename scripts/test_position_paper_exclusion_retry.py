#!/usr/bin/env python3.12
"""Deterministic regression checks for classifier retry/fail-safe behavior."""

import sys
from pathlib import Path
from types import SimpleNamespace


_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services import position_paper_exclusion as exclusion  # noqa: E402


class _FakeMessages:
    def __init__(self, texts):
        self._texts = iter(texts)
        self.call_count = 0

    def create(self, **_kwargs):
        self.call_count += 1
        return SimpleNamespace(
            content=[SimpleNamespace(text=next(self._texts))],
        )


def _run_with_responses(texts):
    messages = _FakeMessages(texts)
    client = SimpleNamespace(messages=messages)
    original_get_client = exclusion.get_anthropic_client
    original_get_model = exclusion.get_generation_model
    original_logger_disabled = exclusion.logger.disabled
    exclusion.get_anthropic_client = lambda: client
    exclusion.get_generation_model = lambda: "test-model"
    exclusion.logger.disabled = True
    chunks = [{
        "author": "Test Teacher",
        "citation_mode": "citable",
        "content": "A retrieved excerpt.",
    }]
    try:
        result = exclusion.exclude_contradicting_teachers(
            "test_pillar",
            "House position text.",
            "Test question?",
            chunks,
        )
    finally:
        exclusion.get_anthropic_client = original_get_client
        exclusion.get_generation_model = original_get_model
        exclusion.logger.disabled = original_logger_disabled
    return chunks, result, messages.call_count


def test_blank_first_response_is_retried_once():
    chunks, result, call_count = _run_with_responses([
        "   ",
        '[{"teacher":"Test Teacher","contradicts":true,"reason":"Contrary claim."}]',
    ])
    assert call_count == 2, f"expected 2 classifier attempts, got {call_count}"
    assert result == ([], ["Test Teacher"]), result
    assert chunks, "fixture must contain the excluded teacher chunk"


def test_second_blank_response_preserves_fail_safe():
    chunks, result, call_count = _run_with_responses(["", "\n\t"])
    assert call_count == 2, f"expected exactly 2 classifier attempts, got {call_count}"
    assert result == (chunks, []), result


if __name__ == "__main__":
    test_blank_first_response_is_retried_once()
    test_second_blank_response_preserves_fail_safe()
    print("position_paper_exclusion retry checks passed")
