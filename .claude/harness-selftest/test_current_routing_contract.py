#!/usr/bin/env python3
"""Regression checks for the current repo-only harness constitution."""

import importlib.util
import os
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ACTIVE_ROOT = Path(os.environ.get("RHEMATA_ACTIVE_ROOT", REPO))
GUARD_PATH = ACTIVE_ROOT / ".Codex" / "hooks" / "guard_pretooluse.py"
EXECUTOR_PATH = ACTIVE_ROOT / ".Codex" / "agents" / "executor.toml"
REVIEWER_PATH = ACTIVE_ROOT / ".Codex" / "agents" / "planner-reviewer.toml"
GATE_PATH = ACTIVE_ROOT / ".Codex" / "hooks" / "deterministic_gate.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("guard_pretooluse", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"[PASS] {label}")


def main() -> None:
    guard = load_guard()

    for script in (
        "ingest_magazine.py",
        "ingest_lexicon.py",
        "ingest_helloao.py",
    ):
        check(
            guard.check_production_db_boundary(
                f"python3 scripts/{script} --dry-run"
            )
            is None,
            f"converted {script} is allowed for dry-run harness work",
        )
        check(
            guard.check_production_db_boundary(f"python3 scripts/{script}")
            is not None,
            f"real {script} execution is blocked by the repo-only boundary",
        )

    check(
        guard.check_production_db_boundary("python3 scripts/backfill_topics.py")
        is not None,
        "a newly named backfill script is blocked without maintaining a list",
    )
    check(
        guard.check_production_db_boundary(
            'psql "$SUPABASE_DB_URL" -c "UPDATE sources SET visibility=shown"'
        )
        is not None,
        "direct mutating SQL is blocked",
    )
    check(
        guard.check_production_db_boundary(
            'psql "$SUPABASE_DB_URL" -c "SELECT count(*) FROM sources"'
        )
        is None,
        "read-only SQL is not blocked by the production-write gate",
    )

    guard_source = GUARD_PATH.read_text()
    check(
        "UNCONVERTED_INGEST_SCRIPTS" not in guard_source,
        "the obsolete name-specific freeze is absent",
    )

    executor = EXECUTOR_PATH.read_text()
    reviewer = REVIEWER_PATH.read_text()
    gate_source = GATE_PATH.read_text()
    check(
        "CLAUDE.md`'s Session Routing" in executor,
        "executor points to current Session Routing authority",
    )
    check(
        "Start with\n`CLAUDE.md`'s `## Session Routing`" in reviewer,
        "reviewer points to current Session Routing authority",
    )
    check(
        "VERDICT: ACCEPT | REVISE | QUARANTINE | HUMAN_REQUIRED" in reviewer,
        "reviewer exposes the four current verdict states",
    )
    check(
        "new unlicensed sources still register `hidden` by default" not in reviewer,
        "reviewer no longer enforces the retired hidden-default policy",
    )
    check(
        not re.search(r"(?:PLAN|AGENTS)\.md:\d+", reviewer),
        "reviewer no longer relies on stale PLAN/AGENTS line references",
    )
    check(
        not re.search(
            r"(?:PLAN|AGENTS|CLAUDE)\.md:\d+", guard_source + gate_source
        ),
        "hook diagnostics no longer rely on stale governing-doc line references",
    )

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
