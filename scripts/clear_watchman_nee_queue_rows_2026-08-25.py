#!/usr/bin/env python3
"""Attended prep: flip cleared_to_run=true on the two watchmannee.org queue
rows staged by register_watchman_nee_source_and_queue_2026-08-25.py. NOT to
be run inside a Claude Code session -- same hard-rule/Auto-Mode reasoning
as that script.

This is the deliberate second checkpoint that script left open. Verifies
each row still matches exactly what was staged (same url, same
attribute_to='Watchman Nee', still status='waiting', still
cleared_to_run=false) before flipping -- refuses instead of guessing if
anything about the row has changed since staging.

After this runs, the actual document fetch/store still doesn't happen
until the worker is run per row, separately:
  python3.12 scripts/source_ingest_worker.py --once --row-id <id>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / "backend" / "app" / ".env")

ROWS = [
    {
        "id": "968bbde1-b21e-4a80-963a-25e1aeb8e09f",
        "url": "https://www.watchmannee.org/major-teachings.html",
    },
    {
        "id": "4ae497a5-3101-4600-a0cb-8ec7512f4b13",
        "url": "https://www.watchmannee.org/scriptural-teachings.html",
    },
]


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL missing", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        for row in ROWS:
            cur.execute(
                """
                SELECT id, url, attribute_to, status, cleared_to_run
                FROM source_ingest_queue WHERE id = %s
                """,
                (row["id"],),
            )
            current = cur.fetchone()
            if not current:
                raise RuntimeError(f"row {row['id']} not found")
            if str(current["url"]) != row["url"]:
                raise RuntimeError(f"row {row['id']} url mismatch: {current['url']!r} != {row['url']!r}")
            if current["attribute_to"] != "Watchman Nee":
                raise RuntimeError(f"row {row['id']} attribute_to changed: {current['attribute_to']!r}")
            if current["status"] != "waiting":
                raise RuntimeError(f"row {row['id']} status changed: {current['status']!r} (expected 'waiting')")
            if current["cleared_to_run"] is not False:
                raise RuntimeError(f"row {row['id']} cleared_to_run already {current['cleared_to_run']!r}, not False -- refusing to touch")

            cur.execute(
                "UPDATE source_ingest_queue SET cleared_to_run = true WHERE id = %s RETURNING cleared_to_run",
                (row["id"],),
            )
            updated = cur.fetchone()
            assert updated["cleared_to_run"] is True

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("RECONCILE")
    for row in ROWS:
        print(f"  {row['id']} -> cleared_to_run=true  ({row['url']})")
    print("OK -- now run, one at a time:")
    for row in ROWS:
        print(f"  python3.12 scripts/source_ingest_worker.py --once --row-id {row['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
