#!/usr/bin/env python3
"""
apply_migration_086.py -- Apply and verify migration 086
(quote rail: add 'pending' to quotes.status check constraint).

Idempotent: safe to run multiple times.

Usage:
  python3 scripts/apply_migration_086.py
"""
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


def main():
    print("\nmigration 086 — add 'pending' to quotes.status check")
    print("=" * 60)

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    migration_sql = (ROOT / "migrations" / "086_quote_pending_status.sql").read_text()
    cur.execute(migration_sql)
    conn.commit()
    print("Migration applied OK")

    # Verify
    cur.execute(
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conname = 'quotes_status_check' AND conrelid = 'quotes'::regclass
        """
    )
    row = cur.fetchone()
    if row and "pending" in row[0]:
        print("VERIFIED: quotes_status_check includes 'pending'")
        print("Constraint def:", row[0])
    else:
        print("FAIL: quotes_status_check does not include 'pending'")
        sys.exit(1)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
