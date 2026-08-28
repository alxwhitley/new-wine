#!/usr/bin/env python3
"""Apply / verify migration 094 (deletion_audit_log).

Default is dry-run verification against the live schema WITHOUT applying.
Production apply requires an explicit --apply flag (Alex's attended gate).

Usage:
  python3 scripts/apply_migration_094.py           # verify only
  python3 scripts/apply_migration_094.py --apply   # apply then verify
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = ROOT / "migrations" / "094_deletion_audit_log.sql"
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label: str, passed: bool, detail: str = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if passed else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


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


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % table,))
    return cur.fetchone()[0] is not None


def rls_enabled(cur, table: str) -> bool:
    cur.execute(
        "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (table,)
    )
    row = cur.fetchone()
    return bool(row and row[0])


def has_service_role_policy(cur, table: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = %s "
        "AND qual LIKE %s",
        (table, "%service_role%"),
    )
    return cur.fetchone()[0] > 0


def has_no_grant(cur, table: str, role: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE table_schema = 'public' AND table_name = %s AND grantee = %s",
        (table, role),
    )
    return cur.fetchone()[0] == 0


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone()[0] > 0


def index_exists(cur, index: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", ("public.%s" % index,))
    return cur.fetchone()[0] is not None


def run_verify(cur) -> None:
    table = "deletion_audit_log"
    exists = table_exists(cur, table)
    check("%s exists" % table, exists)
    if not exists:
        # Mirrors the same fail-closed pattern fixed in
        # apply_migration_093.py 2026-08-28: don't query a table that isn't
        # there, since the ::regclass cast raises UndefinedTable and would
        # crash the rest of this verify pass instead of reporting FAIL.
        check("%s has RLS enabled" % table, False, "table does not exist")
        check("%s has a service_role policy" % table, False, "table does not exist")
        for role in ("anon", "authenticated"):
            check("%s has no grant to %s" % (table, role), False, "table does not exist")
        for column in (
            "id", "original_request_id", "deleted_user_id", "email",
            "requested_at", "resolved_at", "resolved_by", "outcome",
            "reconciliation", "failure_reason",
        ):
            check("%s.%s exists" % (table, column), False, "table does not exist")
        check("deletion_audit_log_deleted_user_id_idx exists", False, "table does not exist")
    else:
        check("%s has RLS enabled" % table, rls_enabled(cur, table))
        check("%s has a service_role policy" % table, has_service_role_policy(cur, table))
        for role in ("anon", "authenticated"):
            check("%s has no grant to %s" % (table, role), has_no_grant(cur, table, role))

        for column in (
            "id", "original_request_id", "deleted_user_id", "email",
            "requested_at", "resolved_at", "resolved_by", "outcome",
            "reconciliation", "failure_reason",
        ):
            check("%s.%s exists" % (table, column), column_exists(cur, table, column))

        check(
            "deletion_audit_log_deleted_user_id_idx exists",
            index_exists(cur, "deletion_audit_log_deleted_user_id_idx"),
        )

    # deletion_requests is a pre-existing table (unrelated to whether
    # deletion_audit_log above has been created yet), so these checks run
    # unconditionally.
    check(
        "deletion_requests.failure_reason exists",
        column_exists(cur, "deletion_requests", "failure_reason"),
    )
    cur.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname = 'deletion_requests_status_check'"
    )
    row = cur.fetchone()
    constraint_def = row[0] if row else ""
    check(
        "deletion_requests.status CHECK includes 'failed'",
        "'failed'" in constraint_def,
        constraint_def,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually apply the migration")
    args = parser.parse_args()

    sql = MIGRATION_PATH.read_text()

    conn = get_conn()
    conn.autocommit = False
    try:
        if args.apply:
            print("Applying migration 094...")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print("Applied.")
        with conn.cursor() as cur:
            run_verify(cur)
    finally:
        conn.close()

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
