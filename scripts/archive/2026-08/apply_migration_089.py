#!/usr/bin/env python3
"""Apply / verify migration 089 (quote quality pipeline columns).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex attended gate).

Usage:
  python3 scripts/apply_migration_089.py           # verify only
  python3 scripts/apply_migration_089.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "089_quote_quality_pipeline.sql"
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


def column_exists(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'quotes' AND column_name = %s
        """,
        (name,),
    )
    return cur.fetchone() is not None


def verify(cur) -> None:
    print("\nVerify migration 089 columns / legacy eligibility\n")
    for col in ("topic_ids", "quality_pipeline_version", "selection_eligible"):
        check("column quotes.%s exists" % col, column_exists(cur, col))

    if not column_exists(cur, "selection_eligible"):
        return

    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE quality_pipeline_version IS NULL AND selection_eligible = false),
          count(*) FILTER (WHERE quality_pipeline_version IS NULL AND selection_eligible = true),
          count(*) FILTER (WHERE quality_pipeline_version IS NOT NULL),
          count(*)
        FROM quotes
        """
    )
    legacy_ineligible, legacy_eligible, pipeline_rows, total = cur.fetchone()
    check(
        "all legacy rows (NULL pipeline version) are selection_eligible=false",
        legacy_eligible == 0,
        "legacy_ineligible=%s legacy_still_eligible=%s pipeline_rows=%s total=%s"
        % (legacy_ineligible, legacy_eligible, pipeline_rows, total),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration 089 to the live database (attended gate).",
    )
    args = parser.parse_args()

    print("\nmigration 089 — quote quality pipeline")
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
