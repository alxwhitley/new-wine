#!/usr/bin/env python3.12
"""Deterministic regression checks for shared teacher-specific routing intent."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


failures = []


def check(label, condition):
    status = "OK" if condition else "FAIL"
    print("  %s: %s" % (status, label))
    if not condition:
        failures.append(label)


def test_shared_gate_contract():
    try:
        intent = importlib.import_module("app.services.answer_intent")
    except ImportError:
        check("shared answer-intent gate exists", False)
        return

    check(
        "known full teacher alias requires teacher-specific retrieval",
        intent.contains_teacher_alias(
            "What does Derek Prince teach about deliverance?",
            {"derek prince", "vlad savchuk"},
        ),
    )
    check(
        "generic topic question does not invent teacher intent",
        not intent.contains_teacher_alias(
            "What is deliverance?",
            {"derek prince", "vlad savchuk"},
        ),
    )
    check(
        "teacher-list request requires teacher-specific retrieval",
        intent.is_teacher_retrieval_intent(
            "Which teachers in the library teach about deliverance?"
        ),
    )

    from app.services import position_papers
    with (
        patch.object(intent, "_teacher_aliases_cache", {"derek prince"}),
        patch.object(intent, "_teacher_aliases_load_failed", False),
    ):
        check(
            "position-paper routing consumes the shared named-teacher gate",
            position_papers._mentions_named_teacher(
                "What does Derek Prince teach about deliverance?"
            ),
        )
    check(
        "position-paper routing consumes the shared teacher-list gate",
        position_papers._is_retrieval_intent(
            "Which teachers teach about deliverance?"
        ),
    )

    with (
        patch.object(intent, "_teacher_aliases_cache", None),
        patch.object(intent, "_teacher_aliases_load_failed", False),
        patch.object(intent, "_load_teacher_aliases", side_effect=RuntimeError("offline")),
        patch.object(intent.logger, "exception", return_value=None),
    ):
        check(
            "alias-load failure fails closed to teacher-specific retrieval",
            intent.requires_teacher_specific_retrieval("What is deliverance?"),
        )


def main():
    test_shared_gate_contract()
    if failures:
        raise SystemExit("%d answer-intent check(s) failed" % len(failures))
    print("All shared answer-intent checks passed.")


if __name__ == "__main__":
    main()
