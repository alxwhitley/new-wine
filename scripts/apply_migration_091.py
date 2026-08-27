#!/usr/bin/env python3
"""Apply / verify migration 091 (teacher-specific routing flag, B6-F1).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex attended gate).
Applying this migration only ADDS the switch (default false) -- it does NOT
enable the named-teacher source-boundary correction. Flipping the column to
true is a separate, later, attended Database-write operation.

Usage:
  python3 scripts/apply_migration_091.py           # verify only
  python3 scripts/apply_migration_091.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "091_teacher_specific_routing_flag.sql"
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label: str, passed: bool, detail: str | None = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if passed else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_conn():
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def column_info(cur, table: str, column: str):
    """Returns (exists, is_nullable, column_default) -- the latter two are
    None if the column doesn't exist."""
    cur.execute(
        """
        SELECT is_nullable, column_default FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cur.fetchone()
    if row is None:
        return False, None, None
    return True, row[0] == "YES", row[1]


def verify(cur) -> None:
    print("\nVerify migration 091 column + default + live value\n")

    exists, nullable, default = column_info(
        cur, "async_answer_config", "experimental_teacher_routing_enabled"
    )
    check("async_answer_config.experimental_teacher_routing_enabled exists", exists)
    if not exists:
        print("\n  (migration not applied yet)")
        return

    check(
        "column is NOT NULL",
        nullable is False,
        "is_nullable=%r" % nullable,
    )
    check(
        "column default is false",
        default is not None and "false" in default.lower(),
        "column_default=%r" % default,
    )

    cur.execute(
        "SELECT experimental_teacher_routing_enabled FROM async_answer_config WHERE id = 1"
    )
    row = cur.fetchone()
    check("config row (id=1) exists", row is not None)
    if row is not None:
        check(
            "live value is false -- this migration does not enable the correction",
            row[0] is False,
            "experimental_teacher_routing_enabled=%r" % row[0],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration 091 to the live database (attended gate).",
    )
    args = parser.parse_args()

    print("\nmigration 091 — teacher-specific routing flag (B6-F1)")
    print("=" * 60)
    if not args.apply:
        print("Mode: VERIFY ONLY (pass --apply to mutate)\n")
    else:
        print("Mode: APPLY + VERIFY\n")

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    if args.apply:
        sql = MIGRATION_PATH.read_text()
        cur.execute(sql)
        conn.commit()
        print("Applied %s\n" % MIGRATION_PATH.name)
        # Fresh connection after apply (Invariant 9 / migration 049 lesson)
        cur.close()
        conn.close()
        conn = get_conn()
        conn.autocommit = True
        cur = conn.cursor()
    else:
        conn.autocommit = True

    verify(cur)
    cur.close()
    conn.close()

    print()
    print("%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
