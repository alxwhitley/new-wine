#!/usr/bin/env python3
"""
apply_migration_087.py -- Apply and verify migration 087
(grant rhemata_readonly_analysis SELECT on quote_verification_log).

Narrow, additive, idempotent: one GRANT SELECT + one additive RLS policy on
a single table. No existing grant, policy, or role is modified.

Verification runs on FRESH connections (migration 049 landmine, Invariant 9):
  1. BEFORE: readonly role's read on quote_verification_log is rejected
     (confirms the gap is real, not already fixed)
  2. AFTER: readonly role can SELECT quote_verification_log
  3. AFTER: readonly role's write attempts (INSERT/UPDATE/DELETE) on
     quote_verification_log are still rejected
  4. AFTER: the existing read-write connection (SUPABASE_DB_URL / postgres
     role) is unchanged and still works

Usage:
  python3.12 scripts/apply_migration_087.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

ROLE_NAME = "rhemata_readonly_analysis"
READONLY_ENV_PATH = ROOT / "backend" / "app" / ".env.readonly-analysis"

_pass = 0
_fail = 0


def check(label, passed, detail=None):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_admin_conn():
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


def _read_readonly_password():
    for line in READONLY_ENV_PATH.read_text().splitlines():
        if line.startswith("READONLY_ANALYSIS_DB_URL="):
            url = line.split("=", 1)[1]
            return unquote(urlparse(url).password or "")
    raise RuntimeError("READONLY_ANALYSIS_DB_URL not found in %s" % READONLY_ENV_PATH)


def get_readonly_conn():
    import psycopg2

    p = urlparse(os.environ["SUPABASE_DB_URL"])
    host = p.hostname
    port = p.port or 5432
    admin_user = unquote(p.username or "")
    if "." in admin_user:
        project_ref = admin_user.split(".", 1)[1]
        ro_user = "%s.%s" % (ROLE_NAME, project_ref)
    else:
        ro_user = ROLE_NAME
    password = _read_readonly_password()
    return psycopg2.connect(
        host=host,
        port=port,
        user=ro_user,
        password=password,
        dbname=p.path.lstrip("/"),
    )


def main():
    print("\ngrant rhemata_readonly_analysis SELECT on quote_verification_log -- migration 087")
    print("=" * 84)

    # 0. BEFORE: confirm the gap is real on a fresh connection.
    try:
        ro_conn = get_readonly_conn()
        ro_conn.autocommit = True
        ro_cur = ro_conn.cursor()
        ro_cur.execute("SELECT count(*) FROM quote_verification_log;")
        check(
            "BEFORE: readonly role SELECT on quote_verification_log REJECTED",
            False,
            "read unexpectedly SUCCEEDED -- grant may already exist",
        )
        ro_cur.close()
        ro_conn.close()
    except Exception as e:
        check("BEFORE: readonly role SELECT on quote_verification_log REJECTED", True, "%r" % e)

    # 1. Apply the migration.
    admin_conn = get_admin_conn()
    cur = admin_conn.cursor()
    migration_sql = (ROOT / "migrations" / "087_grant_quote_verification_log_readonly.sql").read_text()
    cur.execute(migration_sql)
    admin_conn.commit()
    print("\nMigration 087 applied OK (grant + policy)\n")
    cur.close()
    admin_conn.close()

    print("Verification (fresh connections):")

    # 2. AFTER: role can now read the table.
    try:
        ro_conn = get_readonly_conn()
        ro_conn.autocommit = True
        ro_cur = ro_conn.cursor()
        ro_cur.execute("SELECT count(*) FROM quote_verification_log;")
        n = ro_cur.fetchone()[0]
        check(
            "AFTER: readonly role SELECT count(*) FROM quote_verification_log",
            True,
            "%d rows visible" % n,
        )
    except Exception as e:
        check("AFTER: readonly role SELECT count(*) FROM quote_verification_log", False, "%r" % e)
        ro_conn = None

    # 3. AFTER: writes are still rejected.
    if ro_conn is not None:
        try:
            ro_cur.execute("DELETE FROM quote_verification_log WHERE false;")
            check(
                "AFTER: readonly role DELETE FROM quote_verification_log REJECTED",
                False,
                "write unexpectedly SUCCEEDED",
            )
        except Exception as e:
            check("AFTER: readonly role DELETE FROM quote_verification_log REJECTED", True, "%r" % e)

        try:
            ro_cur.execute("INSERT INTO quote_verification_log DEFAULT VALUES;")
            check(
                "AFTER: readonly role INSERT INTO quote_verification_log REJECTED",
                False,
                "write unexpectedly SUCCEEDED",
            )
        except Exception as e:
            check("AFTER: readonly role INSERT INTO quote_verification_log REJECTED", True, "%r" % e)

        try:
            ro_cur.execute("UPDATE quote_verification_log SET decision = decision WHERE false;")
            check(
                "AFTER: readonly role UPDATE quote_verification_log REJECTED",
                False,
                "write unexpectedly SUCCEEDED",
            )
        except Exception as e:
            check("AFTER: readonly role UPDATE quote_verification_log REJECTED", True, "%r" % e)

        ro_cur.close()
        ro_conn.close()

    # 4. Existing read-write connection unchanged.
    try:
        main_conn = get_admin_conn()
        main_cur = main_conn.cursor()
        main_cur.execute("SELECT current_user;")
        u = main_cur.fetchone()[0]
        main_cur.execute("SELECT count(*) FROM quote_verification_log;")
        n = main_cur.fetchone()[0]
        check(
            "existing read-write connection (SUPABASE_DB_URL) still works",
            u == "postgres",
            "current_user=%s, quote_verification_log visible=%d" % (u, n),
        )
        main_cur.close()
        main_conn.close()
    except Exception as e:
        check("existing read-write connection (SUPABASE_DB_URL) still works", False, "%r" % e)

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
