#!/usr/bin/env python3
"""
apply_migration_081.py -- Apply and verify migration 081
(generation_model_config: the one-row control plane for the answer-
generation model ID, shared across sync + async call sites).

Idempotent: detects whether the table already exists and skips the apply if
so. Schema-level verification on a FRESH connection (migration 049 landmine,
Invariant 9).

Usage:
  python3 scripts/apply_migration_081.py
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


def _has_table(cur, table):
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % table,))
    return cur.fetchone()[0] is not None


def main():
    print("\ngeneration_model_config -- migration 081 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _has_table(cur, "generation_model_config"):
        print("Table generation_model_config already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "081_generation_model_config.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection ------------------------------------------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    check("table generation_model_config present", _has_table(cur2, "generation_model_config"))

    cur2.execute(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'generation_model_config' AND column_name = 'model'"
    )
    row = cur2.fetchone()
    check("model column present", row is not None)
    if row:
        nullable, default = row
        check("model NOT NULL", nullable == "NO")
        check("model DEFAULT 'claude-sonnet-5'", default is not None and "claude-sonnet-5" in default)

    cur2.execute("SELECT id, model FROM generation_model_config WHERE id = 1")
    seed = cur2.fetchone()
    check("singleton row (id=1) exists", seed is not None)
    if seed:
        check("seeded value == 'claude-sonnet-5'", seed[1] == "claude-sonnet-5")

    cur2.execute("SELECT count(*) FROM generation_model_config")
    total = cur2.fetchone()[0]
    check("exactly one row", total == 1)

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
