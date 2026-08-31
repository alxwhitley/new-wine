#!/usr/bin/env python3
"""Apply and verify migration 095 (analytics degradation marker, B7).

Adds answer_jobs.analytics_outcome plus its partial index. Additive and
fully reversible: no existing column is altered and no row is rewritten.

Production apply requires an explicit --apply flag (Alex's attended gate,
same convention as apply_migration_088.py / 093.py). A bare invocation
verifies current state and writes nothing.

  python3.12 scripts/apply_migration_095.py            # verify only
  python3.12 scripts/apply_migration_095.py --apply    # apply then verify

Rollback:
  DROP INDEX idx_answer_jobs_analytics_outcome
  ALTER TABLE answer_jobs DROP COLUMN analytics_outcome
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

MIGRATION = ROOT / "migrations" / "095_analytics_outcome_marker.sql"
COLUMN = "analytics_outcome"
INDEX = "idx_answer_jobs_analytics_outcome"
DEGRADED = ("skipped_consent_unreadable", "skipped_key_unavailable", "skipped_write_failed")

_pass = 0
_fail = 0


def check(label, passed, detail=None):
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if passed else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_conn():
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise RuntimeError("SUPABASE_DB_URL is not set (backend/app/.env)")
    return psycopg2.connect(url)


def column_exists(cur):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='answer_jobs' AND column_name=%s",
        (COLUMN,),
    )
    return cur.fetchone() is not None


def index_exists(cur):
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % INDEX,))
    return cur.fetchone()[0] is not None


def run_verify(cur):
    print("\nVerifying migration 095:")
    has_column = column_exists(cur)
    check("answer_jobs.%s exists" % COLUMN, has_column)
    check("partial index %s exists" % INDEX, index_exists(cur))

    if not has_column:
        # Stop here deliberately. The CHECK probes below distinguish
        # "constraint rejected this value" from "constraint accepted it" by
        # whether the UPDATE raises -- and an absent column ALSO makes it
        # raise, so running them now reports the rejection probes as PASS
        # for entirely the wrong reason. (Observed on this script's own
        # first dry run.) Nothing further is verifiable until the DDL runs.
        print("\n  Column absent -- skipping CHECK probes, which cannot")
        print("  distinguish a real constraint from a missing column.")
        return

    # The column must be nullable -- every healthy row leaves it NULL, and a
    # NOT NULL here would break every existing row and every normal write.
    cur.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='answer_jobs' AND column_name=%s",
        (COLUMN,),
    )
    row = cur.fetchone()
    check("column is nullable (healthy rows stay NULL)", row is not None and row[0] == "YES")

    # The CHECK is the closed set. Probe it for real inside a savepoint that
    # is always rolled back -- asserting the constraint text would only prove
    # the text exists, not that the database enforces it.
    cur.execute("SELECT id FROM answer_jobs LIMIT 1")
    sample = cur.fetchone()
    if sample is None:
        check("CHECK enforcement probe", False, "no answer_jobs row to probe against")
    else:
        job_id = sample[0]
        for value in DEGRADED:
            cur.execute("SAVEPOINT p")
            try:
                cur.execute(
                    "UPDATE answer_jobs SET %s = %%s WHERE id = %%s" % COLUMN, (value, job_id)
                )
                ok = True
            except psycopg2.Error:
                ok = False
            cur.execute("ROLLBACK TO SAVEPOINT p")
            check("CHECK accepts %r" % value, ok)

        cur.execute("SAVEPOINT p")
        try:
            cur.execute(
                "UPDATE answer_jobs SET %s = %%s WHERE id = %%s" % COLUMN,
                ("recorded", job_id),
            )
            rejected = False
        except psycopg2.Error:
            rejected = True
        cur.execute("ROLLBACK TO SAVEPOINT p")
        check("CHECK rejects a non-degraded value ('recorded')", rejected)

        cur.execute("SAVEPOINT p")
        try:
            cur.execute(
                "UPDATE answer_jobs SET %s = %%s WHERE id = %%s" % COLUMN,
                ("something_else", job_id),
            )
            rejected2 = False
        except psycopg2.Error:
            rejected2 = True
        cur.execute("ROLLBACK TO SAVEPOINT p")
        check("CHECK rejects an unknown value", rejected2)

    # Nothing was marked by applying the migration itself.
    cur.execute("SELECT count(*) FROM answer_jobs WHERE %s IS NOT NULL" % COLUMN)
    marked = cur.fetchone()[0]
    check("no row was marked by the migration itself", marked == 0,
          "marked=%d" % marked if marked else None)


def main():
    parser = argparse.ArgumentParser(description="Apply and verify migration 095")
    parser.add_argument("--apply", action="store_true",
                        help="required acknowledgement for the production schema write")
    args = parser.parse_args()

    conn = get_conn()
    conn.autocommit = False
    try:
        cur = conn.cursor()
        already = column_exists(cur)
        print("Current state: answer_jobs.%s %s" % (COLUMN, "EXISTS" if already else "absent"))

        if args.apply:
            if already:
                print("Column already present -- skipping DDL, verifying only.")
            else:
                print("Applying migration 095...")
                cur.execute(MIGRATION.read_text())
                conn.commit()
                print("Applied.")
        else:
            print("\nDRY RUN -- nothing was written. Re-run with --apply to apply.")
            if not already:
                print("Verification below will FAIL until the migration is applied.")

        run_verify(cur)
        conn.rollback()  # discard every probe savepoint
    finally:
        conn.close()

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
