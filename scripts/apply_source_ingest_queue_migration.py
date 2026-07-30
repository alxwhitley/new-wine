#!/usr/bin/env python3
"""
apply_source_ingest_queue_migration.py -- Apply and verify migration 075
(source_ingest_queue + source_ingest_domain_memory tables + RLS).

Schema-level verification only (table/columns/indexes/RLS policies), on a
FRESH connection per migration 049's known landmine (a stale connection can
report a table exists when it doesn't). Does not test RLS INSERT behavior
end-to-end -- that's covered by hitting the real backend endpoints, which
enforce access via require_admin_role, not raw table RLS.

Usage:
  python3 scripts/apply_source_ingest_queue_migration.py
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
    # type: (str, bool) -> None
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


def main():
    print("\nSource ingest queue -- migration 075 apply + verify")
    print("=" * 50)

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("SELECT to_regclass('public.source_ingest_queue')")
    already_applied = cur.fetchone()[0] is not None
    if already_applied:
        print("Table source_ingest_queue already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "075_source_ingest_queue.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection: confirm everything is really there -------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    cur2.execute("SELECT to_regclass('public.source_ingest_queue')")
    check("source_ingest_queue exists (fresh connection)", cur2.fetchone()[0] is not None)

    cur2.execute("SELECT to_regclass('public.source_ingest_domain_memory')")
    check("source_ingest_domain_memory exists (fresh connection)", cur2.fetchone()[0] is not None)

    cur2.execute(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_name = 'source_ingest_queue'"
    )
    cols = {row[0]: {"type": row[1], "nullable": row[2], "default": row[3]} for row in cur2.fetchall()}
    expected_cols = {
        "id", "url", "source_format", "source_scope", "attribute_to",
        "attribution_mode", "on_unknown_author", "retain_original_text",
        "status", "flag_reason", "cleared_to_run", "notes", "submitted_by",
        "created_at", "updated_at",
    }
    check("all expected columns present", expected_cols.issubset(cols.keys()))
    check(
        "retain_original_text is nullable with no forced default",
        cols.get("retain_original_text", {}).get("nullable") == "YES",
    )
    check(
        "cleared_to_run defaults false and is NOT NULL",
        cols.get("cleared_to_run", {}).get("nullable") == "NO"
        and "false" in (cols.get("cleared_to_run", {}).get("default") or "").lower(),
    )

    cur2.execute(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'source_ingest_queue'"
    )
    indexes = {row[0] for row in cur2.fetchall()}
    check(
        "status + cleared_to_run indexes present",
        "source_ingest_queue_status_idx" in indexes
        and "source_ingest_queue_cleared_to_run_idx" in indexes,
    )

    cur2.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'source_ingest_queue'")
    check("RLS enabled on source_ingest_queue", cur2.fetchone()[0] is True)

    cur2.execute("SELECT policyname FROM pg_policies WHERE tablename = 'source_ingest_queue'")
    policies = {row[0] for row in cur2.fetchall()}
    expected_policies = {
        "source_ingest_queue: own rows read",
        "source_ingest_queue: own row insert",
        "source_ingest_queue: service role full access",
    }
    check("all 3 source_ingest_queue RLS policies present", expected_policies.issubset(policies))

    cur2.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'source_ingest_domain_memory'")
    check("RLS enabled on source_ingest_domain_memory", cur2.fetchone()[0] is True)

    cur2.execute("SELECT policyname FROM pg_policies WHERE tablename = 'source_ingest_domain_memory'")
    dm_policies = {row[0] for row in cur2.fetchall()}
    check(
        "service-role-only policy present on source_ingest_domain_memory",
        "source_ingest_domain_memory: service role full access" in dm_policies
        and len(dm_policies) == 1,
    )

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
