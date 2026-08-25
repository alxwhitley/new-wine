#!/usr/bin/env python3
"""Attended fix: correct a mistake in
register_watchman_nee_source_and_queue_2026-08-25.py. NOT to be run inside
a Claude Code session -- same hard-rule/Auto-Mode reasoning as that
script.

The registration script set the new "Watchman Nee" source's
visibility='shown', following the general 2026-08-01 "new material
defaults to visible" decision (#12). That was wrong for THIS format:
Invariant 16 specifically requires a new web-article source to start
visibility='hidden' -- hidden staging exists so preparing a web article
can never make it retrievable until someone deliberately reviews and
flips it later. The processor correctly refused both queue rows with
flag_reason='source_visibility_not_hidden: declared source is not
hidden' -- attempts stayed at 0, nothing was written incorrectly, this
just corrects the mistake so the rows can be retried.

This script:
  1. Verifies the source is still exactly the state the registration
     script left it in (unlicensed / shown) before touching it -- refuses
     if anything unexpected has changed.
  2. Flips visibility to 'hidden'.
  3. Verifies both queue rows are still exactly needs_attention with the
     expected flag_reason, then resets each to the same state
     claim_next() requires (status='waiting', stage='queued',
     flag_reason=NULL) -- cleared_to_run is untouched, it was never
     modified by the needs_attention transition and should still be
     true from clear_watchman_nee_queue_rows_2026-08-25.py.

After this runs, retry the same two worker commands as before.
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

SOURCE_ID = "df64f6c3-c60d-42f0-b7ac-f99122d695c0"
ROW_IDS = [
    "968bbde1-b21e-4a80-963a-25e1aeb8e09f",
    "4ae497a5-3101-4600-a0cb-8ec7512f4b13",
]
EXPECTED_FLAG_REASON = "source_visibility_not_hidden: declared source is not hidden"


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL missing", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE id = %s",
            (SOURCE_ID,),
        )
        src = cur.fetchone()
        if not src or src["name"] != "Watchman Nee":
            raise RuntimeError(f"source {SOURCE_ID} not found or name changed: {src}")
        if src["license_status"] != "unlicensed" or src["visibility"] != "shown":
            raise RuntimeError(f"source not in the expected pre-fix state: {dict(src)}")

        cur.execute(
            "UPDATE sources SET visibility = 'hidden', updated_at = now() WHERE id = %s RETURNING visibility",
            (SOURCE_ID,),
        )
        updated_src = cur.fetchone()
        assert updated_src["visibility"] == "hidden"

        for row_id in ROW_IDS:
            cur.execute(
                "SELECT id, status, stage, flag_reason, cleared_to_run FROM source_ingest_queue WHERE id = %s",
                (row_id,),
            )
            current = cur.fetchone()
            if not current:
                raise RuntimeError(f"row {row_id} not found")
            if current["status"] != "needs_attention" or current["flag_reason"] != EXPECTED_FLAG_REASON:
                raise RuntimeError(f"row {row_id} not in the expected pre-fix state: {dict(current)}")
            if current["cleared_to_run"] is not True:
                raise RuntimeError(f"row {row_id} cleared_to_run unexpectedly {current['cleared_to_run']!r}")

            cur.execute(
                """
                UPDATE source_ingest_queue
                SET status = 'waiting', stage = 'queued', flag_reason = NULL, updated_at = now()
                WHERE id = %s
                RETURNING status, stage, flag_reason, cleared_to_run
                """,
                (row_id,),
            )
            reset = cur.fetchone()
            assert reset["status"] == "waiting"
            assert reset["stage"] == "queued"
            assert reset["flag_reason"] is None
            assert reset["cleared_to_run"] is True

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("RECONCILE")
    print(f"  source {SOURCE_ID} -> visibility=hidden")
    for row_id in ROW_IDS:
        print(f"  {row_id} -> status=waiting stage=queued flag_reason=NULL cleared_to_run=true")
    print("OK -- retry the worker for each row:")
    for row_id in ROW_IDS:
        print(f"  python3.12 scripts/source_ingest_worker.py --once --row-id {row_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
