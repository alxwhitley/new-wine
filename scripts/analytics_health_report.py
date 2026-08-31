#!/usr/bin/env python3
"""Answer the question the 2026-08-31 smoke could not: was analytics DOWN
during these hours, or did nobody search?

Before migration 095 those two states were byte-for-byte identical -- both
looked like "no rows in search_occurrences." This reads the marker
(answer_jobs.analytics_outcome, B7) and separates them:

  no rows for an hour           -> nobody searched
  searches > 0, unrecorded = 0  -> analytics healthy
  unrecorded > 0                -> analytics degraded, and by how much

READ-ONLY. Opens the connection with `readonly=True` and issues SELECTs
only. Needs no rhemata_readonly_analysis grants -- it uses the ordinary
service connection, so it works today with that role's grants still
deferred.

Prints no question text and no subject key: the marker deliberately holds
neither, and neither is read here.

  python3.12 scripts/analytics_health_report.py             # last 7 days
  python3.12 scripts/analytics_health_report.py --days 30
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Search-analytics health over time")
    parser.add_argument("--days", type=int, default=7, help="lookback window (default 7)")
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.set_session(readonly=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='answer_jobs' "
        "AND column_name='analytics_outcome'"
    )
    if cur.fetchone() is None:
        print("Migration 095 is not applied -- answer_jobs.analytics_outcome does not exist.")
        print("Until it is, a skipped recording leaves only a log line.")
        conn.close()
        return 2

    cur.execute(
        """
        SELECT date_trunc('hour', created_at) AS hour,
               count(*) AS searches,
               count(analytics_outcome) AS unrecorded,
               array_agg(DISTINCT analytics_outcome)
                 FILTER (WHERE analytics_outcome IS NOT NULL) AS reasons
        FROM answer_jobs
        WHERE created_at > now() - (%s * interval '1 day')
        GROUP BY 1 ORDER BY 1 DESC
        """,
        (args.days,),
    )
    rows = cur.fetchall()

    print("Search-analytics health, last %d day(s)" % args.days)
    print("=" * 78)
    if not rows:
        print("No searches at all in this window -- nothing was submitted.")
        print("(That is a genuine 'nobody searched', not an analytics gap.)")
        conn.close()
        return 0

    print("%-22s %9s %11s   %s" % ("HOUR (UTC)", "SEARCHES", "UNRECORDED", "STATE"))
    degraded_hours = 0
    total_lost = 0
    for r in rows:
        lost = r["unrecorded"] or 0
        total_lost += lost
        if lost:
            degraded_hours += 1
            state = "DEGRADED: %s" % ", ".join(r["reasons"] or [])
        else:
            state = "healthy"
        print("%-22s %9d %11d   %s"
              % (r["hour"].strftime("%Y-%m-%d %H:00"), r["searches"], lost, state))

    print("=" * 78)
    print("%d hour(s) with traffic, %d degraded, %d search(es) went unrecorded."
          % (len(rows), degraded_hours, total_lost))
    if total_lost:
        print("\nThose searches WERE answered -- analytics failing no longer costs a")
        print("user their answer (B7). What is missing is the analytics row only.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
