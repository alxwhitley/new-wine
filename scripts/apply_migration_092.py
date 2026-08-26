#!/usr/bin/env python3
"""Apply / verify migration 092 (conversation-level cumulative usage signal).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex attended gate).
Applying this migration only ADDS three columns, all defaulting to 0 -- it
does not change any existing behavior. conversation_store.py's own code
change (incrementing them, and async_chat.py surfacing the total) is a
separate, already-reviewed code change; this script only proves the schema
side landed correctly.

Usage:
  python3 scripts/apply_migration_092.py           # verify only
  python3 scripts/apply_migration_092.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "092_conversation_length_signal.sql"
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
    print("\nVerify migration 092 columns + defaults\n")

    for column in ("cumulative_input_tokens", "cumulative_output_tokens", "turn_count"):
        exists, nullable, default = column_info(cur, "conversations", column)
        check("conversations.%s exists" % column, exists)
        if not exists:
            print("\n  (migration not applied yet)")
            return
        check(
            "conversations.%s is NOT NULL" % column,
            nullable is False,
            "is_nullable=%r" % nullable,
        )
        check(
            "conversations.%s default is 0" % column,
            default is not None and default.strip().startswith("0"),
            "column_default=%r" % default,
        )

    cur.execute(
        "SELECT count(*) FROM conversations WHERE "
        "cumulative_input_tokens IS NULL OR cumulative_output_tokens IS NULL OR turn_count IS NULL"
    )
    (null_count,) = cur.fetchone()
    check(
        "no existing row has a NULL in the new columns (backfilled by the ADD COLUMN default)",
        null_count == 0,
        "null_count=%r" % null_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration 092 to the live database (attended gate).",
    )
    args = parser.parse_args()

    print("\nmigration 092 — conversation-level cumulative usage signal")
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
