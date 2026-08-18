#!/usr/bin/env python3
"""Repo-only checks for migration 089 quote quality pipeline schema SQL.

Does not connect to the database and does not apply the migration.
Run: python3 scripts/test_quote_pipeline_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "089_quote_quality_pipeline.sql"
APPLY_PATH = ROOT / "scripts" / "apply_migration_089.py"

failures = []


def check(label: str, cond: bool, detail: str | None = None) -> None:
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)
        if detail:
            print("         %s" % detail)


def main() -> int:
    print("\nquote quality pipeline schema (migration 089) — repo checks")
    print("=" * 60)

    check("migration file exists", MIGRATION_PATH.is_file())
    check("apply script exists", APPLY_PATH.is_file())
    sql = MIGRATION_PATH.read_text()
    apply_src = APPLY_PATH.read_text()

    for needle in (
        "ADD COLUMN IF NOT EXISTS topic_ids text[]",
        "ADD COLUMN IF NOT EXISTS quality_pipeline_version text",
        "ADD COLUMN IF NOT EXISTS selection_eligible boolean NOT NULL DEFAULT true",
        "SET selection_eligible = false",
        "WHERE quality_pipeline_version IS NULL",
        "quotes_selection_eligible_idx",
    ):
        check("SQL contains %r" % needle, needle in sql)

    # Invariant 9: no semicolons inside -- comments
    bad_comment_semicolons = []
    for i, line in enumerate(sql.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("--") and ";" in stripped:
            bad_comment_semicolons.append(i)
    check(
        "no semicolons inside -- SQL comments (Invariant 9)",
        not bad_comment_semicolons,
        "lines: %s" % bad_comment_semicolons,
    )

    check("apply script defaults to dry-run (requires --apply)", '"--apply"' in apply_src)
    check("apply script refuses to run apply without flag", "args.apply" in apply_src)

    print()
    if failures:
        print("%d check(s) failed" % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
