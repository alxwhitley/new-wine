#!/usr/bin/env python3
"""
apply_stage2_migration.py -- Apply and verify migration 079 (Stage 2 cutover
schema: corpus_version() fn + async_answer_config.serving_enabled +
answer_jobs.topics_established/result_meta).

Additive only. Idempotent (CREATE OR REPLACE / ADD COLUMN IF NOT EXISTS).
Verification runs on a FRESH connection (migration 049 landmine).

Usage:
  python3 scripts/apply_stage2_migration.py
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


def check(label, passed, detail=""):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s%s" % (tag, label, ("  -- " + detail if detail else "")))
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_db_conn():
    import psycopg2
    p = urlparse(os.environ["SUPABASE_DB_URL"])
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        user=unquote(p.username or ""), password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def _has_col(cur, table, col):
    cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, col),
    )
    return cur.fetchone() is not None


def main():
    print("\nStage 2 cutover -- migration 079 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()
    migration_sql = (ROOT / "migrations" / "079_stage2_cutover.sql").read_text()
    cur.execute(migration_sql)
    conn.commit()
    print("Migration applied OK (idempotent)")
    cur.close()
    conn.close()

    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    # corpus_version() exists and returns a stable non-empty value.
    cur2.execute("SELECT corpus_version()")
    v1 = cur2.fetchone()[0]
    cur2.execute("SELECT corpus_version()")
    v2 = cur2.fetchone()[0]
    check("corpus_version() returns a value", bool(v1) and v1.startswith("corpus_"), repr(v1))
    check("corpus_version() is stable across calls", v1 == v2)

    check("async_answer_config.serving_enabled present", _has_col(cur2, "async_answer_config", "serving_enabled"))
    # default must be false (traffic switch OFF).
    cur2.execute("SELECT serving_enabled FROM async_answer_config WHERE id=1")
    check("serving_enabled defaults OFF", cur2.fetchone()[0] is False)

    check("answer_jobs.topics_established present", _has_col(cur2, "answer_jobs", "topics_established"))
    check("answer_jobs.result_meta present", _has_col(cur2, "answer_jobs", "result_meta"))

    cur2.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid='answer_jobs'::regclass AND conname='answer_jobs_outcome_check'"
    )
    row = cur2.fetchone()
    check("outcome CHECK allows 'position_paper'", bool(row) and "position_paper" in row[0])

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
