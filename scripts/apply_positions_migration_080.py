#!/usr/bin/env python3
"""
apply_positions_migration_080.py -- Apply and verify migration 080
(materialized "pass-both" eligibility signal: propositions.eligible +
its partial index).

Idempotent: detects whether the column already exists and skips the apply if
so. Schema-level verification on a FRESH connection (migration 049 landmine).
Does NOT backfill values -- eligible defaults to false for every row until
scripts/backfill_proposition_eligibility.py runs; that is a deliberately
separate step (schema change vs. data change).

Usage:
  python3 scripts/apply_positions_migration_080.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(ROOT / "scripts"))

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


def _has_col(cur, table, col):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, col),
    )
    return cur.fetchone() is not None


def main():
    print("\nPropositions eligibility signal -- migration 080 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _has_col(cur, "propositions", "eligible"):
        print("Column eligible already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "080_propositions_eligibility.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection ------------------------------------------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    check("column eligible present", _has_col(cur2, "propositions", "eligible"))

    cur2.execute(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name = 'propositions' AND column_name = 'eligible'"
    )
    nullable, default = cur2.fetchone()
    check("eligible NOT NULL", nullable == "NO")
    check("eligible DEFAULT false", default is not None and "false" in default.lower())

    cur2.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'propositions'")
    idx = {r[0] for r in cur2.fetchall()}
    check("propositions_eligible_idx present", "propositions_eligible_idx" in idx)

    cur2.execute("SELECT count(*) FROM propositions WHERE eligible = true")
    already_true = cur2.fetchone()[0]
    print(
        "  (info) %d proposition(s) already eligible=true -- 0 expected before "
        "the backfill script runs" % already_true
    )

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
