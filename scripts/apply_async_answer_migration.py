#!/usr/bin/env python3
"""
apply_async_answer_migration.py -- Apply and verify migration 078 (async answer
path: answer_jobs + async_answer_config + provider_rate_usage).

Additive only. Idempotent: detects whether answer_jobs already exists and skips
the apply if so. Schema-level verification runs on a FRESH connection
(migration 049 landmine -- always re-verify from a new connection, never the
apply connection's own view).

Usage:
  python3 scripts/apply_async_answer_migration.py
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


def _table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s)", ("public." + table,))
    return cur.fetchone()[0] is not None


def _index_exists(cur, index):
    cur.execute("SELECT to_regclass(%s)", ("public." + index,))
    return cur.fetchone()[0] is not None


def main():
    print("\nAsync answer path -- migration 078 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _table_exists(cur, "answer_jobs"):
        print("Table answer_jobs already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "078_async_answer_path.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection (do NOT trust the apply connection's own view) -------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    for tbl in ("answer_jobs", "async_answer_config", "provider_rate_usage"):
        check("table %s present" % tbl, _table_exists(cur2, tbl))

    for idx in (
        "answer_jobs_claim_idx",
        "answer_jobs_lease_idx",
        "answer_jobs_active_dedup_idx",
        "answer_jobs_reuse_idx",
    ):
        check("index %s present" % idx, _index_exists(cur2, idx))

    # NOT NULL discipline on the columns that must never be silently NULL.
    cur2.execute(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'answer_jobs' AND column_name IN "
        "('dedup_key','question','status','evidence_version','prompt_version','policy_version')"
    )
    nullable = {r[0]: r[1] for r in cur2.fetchall()}
    for col in ("dedup_key", "question", "status", "evidence_version",
                "prompt_version", "policy_version"):
        check("answer_jobs.%s NOT NULL" % col, nullable.get(col) == "NO")

    # The config singleton seeded exactly one row.
    cur2.execute("SELECT count(*) FROM async_answer_config")
    check("async_answer_config seeded (1 row)", cur2.fetchone()[0] == 1)

    # Behavioural: the active-dedup unique index actually collides on a second
    # active job with the same dedup_key. Rolled back -- proof only, no data
    # left behind.
    import psycopg2

    ins = (
        "INSERT INTO answer_jobs (dedup_key, question, evidence_version, "
        "prompt_version, policy_version) VALUES "
        "('zzz-proof-078', 'zzz proof question 078', 'e', 'p', 'x')"
    )
    try:
        cur2.execute(ins)  # first active job -- OK
        cur2.execute(ins)  # second active job, same dedup_key -- must collide
        conn2.rollback()
        check("two active jobs on one dedup_key collide", False)
    except psycopg2.errors.UniqueViolation:
        conn2.rollback()
        check("two active jobs on one dedup_key collide", True)
    except Exception as exc:
        conn2.rollback()
        print("    (unexpected error: %r)" % exc)
        check("two active jobs on one dedup_key collide", False)

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
