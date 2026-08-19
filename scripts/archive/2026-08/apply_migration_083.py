#!/usr/bin/env python3
"""
apply_migration_083.py -- Apply and verify migration 083
(quote rail live-answer wiring: answer_jobs.quote_ids).

Idempotent: the migration itself uses ADD COLUMN IF NOT EXISTS. Schema-level
verification on a FRESH connection (migration 049 landmine, Invariant 9).

Usage:
  python3 scripts/apply_migration_083.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label, passed):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_db_conn():
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


def _has_column(cur, table, column):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def main():
    print("\nquote rail wiring -- migration 083 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _has_column(cur, "answer_jobs", "quote_ids"):
        print("Column answer_jobs.quote_ids already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "083_quote_rail_answer_jobs_wiring.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection ------------------------------------------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    check("answer_jobs.quote_ids column present", _has_column(cur2, "answer_jobs", "quote_ids"))

    cur2.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'answer_jobs' AND column_name = 'quote_ids'"
    )
    row = cur2.fetchone()
    check("answer_jobs.quote_ids is jsonb", row is not None and row[0] == "jsonb")

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
