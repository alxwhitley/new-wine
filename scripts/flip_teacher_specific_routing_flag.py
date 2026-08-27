#!/usr/bin/env python3
"""Flip async_answer_config.experimental_teacher_routing_enabled (B6-F1).

This is the "smallest closure" step recorded in PLAN.md: migration 091 is
already applied live and answer_worker.py already reads this flag, but it is
still `false`, so production behavior for real users is unchanged. This
script flips it to `true`, activating the source-boundary named-teacher
correction for real traffic.

Default is dry-run verification (prints the live value, changes nothing).
Setting it requires an explicit --apply flag (attended Database-write gate
per CLAUDE.md's Session Routing hard rule -- run this from a plain terminal
or Codex, not delegated to a subagent).

Usage:
  python3 scripts/flip_teacher_specific_routing_flag.py            # verify only
  python3 scripts/flip_teacher_specific_routing_flag.py --apply    # flip to true, then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")


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


def read_value(cur) -> bool | None:
    cur.execute(
        "SELECT experimental_teacher_routing_enabled FROM async_answer_config WHERE id = 1"
    )
    row = cur.fetchone()
    return row[0] if row is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Flip the flag to true on the live database (attended gate).",
    )
    args = parser.parse_args()

    print("\nB6-F1 -- experimental_teacher_routing_enabled flip")
    print("=" * 60)
    if not args.apply:
        print("Mode: VERIFY ONLY (pass --apply to mutate)\n")
    else:
        print("Mode: APPLY (set true) + VERIFY\n")

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()

    before = read_value(cur)
    print("Current live value: %r" % (before,))

    if before is None:
        print("\nFAIL: no async_answer_config row with id=1 -- refusing to proceed.")
        cur.close()
        conn.close()
        return 1

    if not args.apply:
        cur.close()
        conn.close()
        print("\nDry run only -- nothing changed. Pass --apply to flip to true.")
        return 0

    if before is True:
        print("\nAlready true -- nothing to do.")
        cur.close()
        conn.close()
        return 0

    cur.execute(
        "UPDATE async_answer_config SET experimental_teacher_routing_enabled = true WHERE id = 1"
    )
    print("Executed UPDATE (autocommit).")

    # Fresh connection after write (Invariant 9 / migration 049 lesson).
    cur.close()
    conn.close()
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()

    after = read_value(cur)
    cur.close()
    conn.close()

    print("Post-write live value: %r" % (after,))
    ok = after is True
    print("\n%s" % ("PASS -- flag is now true" if ok else "FAIL -- flag did not flip"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
