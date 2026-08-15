#!/usr/bin/env python3
"""Regression checks for the single-author answer attribution contract."""
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

from app.services.async_answers import producer as producer_module  # noqa: E402
from app.services.async_answers.producer import (  # noqa: E402
    POLICY_VERSION,
    _ensure_single_author_label,
    _generate_and_capture,
    _missing_required_single_author,
)


class _FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return []


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("OK:", label)


def main():
    anonymous = "Deliverance is exercised through the authority of Jesus [1]."
    named = "Vlad Savchuk teaches that deliverance rests on Jesus' authority [1]."

    check(
        "attribution behavior change invalidates pre-contract answer reuse",
        POLICY_VERSION == "policy_v3",
    )

    check(
        "single named source missing from prose is detected",
        _missing_required_single_author(anonymous, ["Vlad Savchuk"]),
    )
    check(
        "case-insensitive full-name occurrence satisfies the contract",
        not _missing_required_single_author(named.lower(), ["Vlad Savchuk"]),
    )
    check(
        "multi-author evidence does not impose a single-author contract",
        not _missing_required_single_author(anonymous, ["Vlad Savchuk", "Derek Prince"]),
    )
    check(
        "anonymous evidence does not impose a single-author contract",
        not _missing_required_single_author(anonymous, []),
    )

    labeled = _ensure_single_author_label(anonymous, ["Vlad Savchuk"])
    check(
        "missing single author receives a deterministic source label",
        labeled == "**Source voice: Vlad Savchuk**\n\n" + anonymous,
    )
    check(
        "already named answer stays byte-identical",
        _ensure_single_author_label(named, ["Vlad Savchuk"]) == named,
    )
    check(
        "multi-author answer stays byte-identical",
        _ensure_single_author_label(anonymous, ["Vlad Savchuk", "Derek Prince"]) == anonymous,
    )

    client = _FakeClient()
    with (
        patch.object(producer_module, "get_anthropic_client", return_value=client),
        patch.object(producer_module, "get_generation_model", return_value="test-model"),
    ):
        _generate_and_capture([], ["Vlad Savchuk"])
        _generate_and_capture([], ["Vlad Savchuk", "Derek Prince"])

    single_prompt = client.messages.calls[0]["system"][-1]["text"]
    multi_prompt = client.messages.calls[1]["system"][-1]["text"]
    check("single-author retry prompt requires the full name", "MUST identify Vlad Savchuk" in single_prompt)
    check("multi-author retry prompt does not force one voice", "MUST identify" not in multi_prompt)

    print("All single-author attribution contract checks passed.")


if __name__ == "__main__":
    main()
