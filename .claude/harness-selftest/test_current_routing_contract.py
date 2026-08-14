#!/usr/bin/env python3
"""Regression checks for the current repo-only harness constitution."""

import importlib.util
import os
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ACTIVE_ROOT = Path(os.environ.get("RHEMATA_ACTIVE_ROOT", REPO))
CODEX_GUARD_PATH = ACTIVE_ROOT / ".codex" / "hooks" / "guard_pretooluse.py"
CLAUDE_GUARD_PATH = ACTIVE_ROOT / ".claude" / "hooks" / "guard_pretooluse.py"
GUARD_PATH = CODEX_GUARD_PATH
EXECUTOR_PATH = ACTIVE_ROOT / ".codex" / "agents" / "executor.toml"
REVIEWER_PATH = ACTIVE_ROOT / ".codex" / "agents" / "planner-reviewer.toml"
GATE_PATH = ACTIVE_ROOT / ".codex" / "hooks" / "deterministic_gate.py"
CLAUDE_EXECUTOR_PATH = ACTIVE_ROOT / ".claude" / "agents" / "executor.md"
CLAUDE_REVIEWER_PATH = ACTIVE_ROOT / ".claude" / "agents" / "planner-reviewer.md"


def load_guard(path=GUARD_PATH):
    spec = importlib.util.spec_from_file_location(
        f"guard_pretooluse_{path.parent.parent.name}", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_both_configured_hooks_enforce_current_repo_only_boundary():
    for path in (CODEX_GUARD_PATH, CLAUDE_GUARD_PATH):
        guard = load_guard(path)
        assert not hasattr(guard, "check_rule_10_freeze")
        assert guard.check_production_db_boundary(
            "python3 scripts/ingest_magazine.py --dry-run"
        ) is None
        for command in (
            "python3 scripts/ingest_magazine.py",
            "python3 scripts/backfill_topics.py",
            "python3 scripts/migrate_sources.py",
            "python3 scripts/seed_sources.py",
            "python3 scripts/restore_sources.py",
            "python3 scripts/run_full_backfill.py",
            "python3 scripts/run_queue_ingest.py",
            "python3 scripts/apply_migration_085.py",
            'psql "$SUPABASE_DB_URL" -c "UPDATE sources SET visibility=shown"',
        ):
            assert guard.check_production_db_boundary(command) is not None
        assert guard.check_production_db_boundary(
            "python3 scripts/ingest_magazine.py --dry-run; "
            "python3 scripts/ingest_magazine.py"
        ) is not None
        assert guard.check_production_db_boundary(
            "python3 scripts/ingest_magazine.py --dry-run | "
            "python3 scripts/ingest_magazine.py"
        ) is not None
        assert guard.check_production_db_boundary(
            'echo --dry-run | psql "$DB" -c "UPDATE sources SET x=1"'
        ) is not None
        assert guard.check_production_db_boundary(
            "python3 scripts/ingest_magazine.py --dry-run=false"
        ) is not None
        assert guard.check_production_db_boundary(
            "python3 -m scripts.run_queue_ingest"
        ) is not None
        assert guard.check_production_db_boundary(
            'echo "UPDATE sources SET x=1" | psql "$DB"'
        ) is not None
        assert guard.check_production_db_boundary(
            'psql "$DB" --dry-run -c "UPDATE sources SET x=1"'
        ) is not None
        assert guard.check_production_db_boundary(
            'psql "$SUPABASE_DB_URL" -c "SELECT count(*) FROM sources"'
        ) is None


def test_settings_wire_the_two_explicit_hook_surfaces():
    claude_settings = (ACTIVE_ROOT / ".claude" / "settings.json").read_text()
    codex_settings = (ACTIVE_ROOT / ".codex" / "hooks.json").read_text()
    assert ".claude/hooks/guard_pretooluse.py" in claude_settings
    assert ".codex/hooks/guard_pretooluse.py" in codex_settings


def test_claude_side_agents_declare_the_verification_timeout_discipline():
    executor = CLAUDE_EXECUTOR_PATH.read_text()
    reviewer = CLAUDE_REVIEWER_PATH.read_text()

    # Executor: must point at the declared-ahead-timeout CLI, require a
    # timeout be declared before running, name the TIMED_OUT outcome, and
    # state the Claude-specific outer Bash-tool ceiling (600000ms / 10 min).
    assert "verification_commands" in executor
    assert "PYTHONPATH=scripts" in executor
    assert "declared" in executor and "before running" in executor.lower()
    assert "TIMED_OUT" in executor
    assert "600000" in executor

    # Executor: a raw Bash-tool `timeout` param on the command itself must be
    # explicitly stated as not an accepted substitute for the CLI.
    assert "not an accepted substitute" in executor.lower()

    # Planner-reviewer: must check the same discipline, plus (Claude-specific)
    # confirm the outer Bash-tool timeout, not just the declared packet timeout.
    assert "verification_commands" in reviewer
    assert "outer Bash" in reviewer or "outer Bash-tool" in reviewer

    # Planner-reviewer: must reject a raw Bash-tool timeout substituted for the CLI.
    assert "not an accepted substitute" in reviewer.lower()


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
