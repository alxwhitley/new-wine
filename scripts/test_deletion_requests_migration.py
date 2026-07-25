#!/usr/bin/env python3
"""
test_deletion_requests_migration.py -- Apply and verify migration 068
(deletion_requests table + RLS).

Requires in backend/app/.env (or environment):
  SUPABASE_DB_URL      -- direct Postgres connection (service role)
  SUPABASE_URL         -- project URL
  SUPABASE_ANON_KEY    -- public anon key (or NEXT_PUBLIC_SUPABASE_ANON_KEY)
  SUPABASE_SERVICE_KEY -- service role key (for auth.admin.generate_link)

Usage:
  python3 scripts/test_deletion_requests_migration.py
"""

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# Real, already-registered account used only to obtain a genuine auth.users id
# for the "authenticated user can insert their own row" RLS check below --
# same convention scripts/test_metering.py already uses. A freshly-generated
# uuid4() cannot be used there: deletion_requests.user_id has a real FK to
# auth.users(id), and unlike the user_a setup insert a few lines below (which
# bypasses FK checks via session_replication_role = replica), the RLS-scoped
# insert runs as a normal role and WILL hit that FK before RLS is even
# evaluated -- a synthetic id fails with ForeignKeyViolation every time, in
# every environment, regardless of what the RLS policy itself would allow.
TEST_EMAIL = "creative@clf-church.com"


def get_db_conn():
    import psycopg2
    from urllib.parse import urlparse, unquote

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def get_anon_client():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY must be set")
        sys.exit(1)
    return create_client(url, key)


def get_real_user_id(service_db):
    # type: (object) -> str
    """Resolve a genuine auth.users id for TEST_EMAIL via the admin API.
    TEST_EMAIL is a real, already-registered account in this project, so
    this reuses that existing auth.users row. Note: if TEST_EMAIL did NOT
    already exist, generate_link(type="magiclink") would silently create
    one -- do not point this script at a different Supabase project without
    confirming TEST_EMAIL already exists there, or it will leave behind an
    unconfirmed auth.users row this script never cleans up."""
    link = service_db.auth.admin.generate_link({"type": "magiclink", "email": TEST_EMAIL})
    return link.user.id


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


def anon_insert_blocked(anon, table, payload):
    # type: (object, str, dict) -> bool
    try:
        resp = anon.table(table).insert(payload).execute()
        return not getattr(resp, "data", None)
    except Exception:
        return True


def rls_insert_as_user(conn, user_id, email):
    # type: (object, str, str) -> bool
    """Attempt an INSERT as an authenticated, non-service user. Always
    rolls back -- this only checks whether RLS would have allowed it."""
    claims = json.dumps({"sub": user_id, "role": "authenticated"})
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            (claims,),
        )
        cur.execute(
            "INSERT INTO deletion_requests (user_id, email) VALUES (%s, %s) RETURNING id",
            (user_id, email),
        )
        row = cur.fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        cur.execute("ROLLBACK")
        cur.close()


def main():
    print("\nAccount deletion requests -- migration 068 verification")
    print("=" * 50)

    conn = get_db_conn()
    cur = conn.cursor()

    # -- Apply migration if not already applied ---------------------------------
    cur.execute("SELECT to_regclass('public.deletion_requests')")
    already_applied = cur.fetchone()[0] is not None
    if already_applied:
        print("Table deletion_requests already exists -- skipping apply")
    else:
        migration_sql = (Path(__file__).resolve().parent.parent / "migrations" / "068_deletion_requests.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")

    # -- Fresh connection: confirm the table is really there ---------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()
    cur2.execute("SELECT to_regclass('public.deletion_requests')")
    exists = cur2.fetchone()[0] is not None
    check("deletion_requests exists (fresh connection)", exists)

    cur2.execute("SELECT relrowsecurity FROM pg_class WHERE relname = 'deletion_requests'")
    rls_enabled = cur2.fetchone()[0]
    check("RLS enabled on deletion_requests", rls_enabled is True)

    cur2.execute("SELECT policyname FROM pg_policies WHERE tablename = 'deletion_requests'")
    policies = {row[0] for row in cur2.fetchall()}
    expected = {
        "deletion_requests: own rows read",
        "deletion_requests: own row insert",
        "deletion_requests: service role full access",
    }
    check("all 3 RLS policies present", expected.issubset(policies))
    cur2.close()
    conn2.close()

    # -- RLS behavior checks -------------------------------------------------------
    from supabase import create_client
    service_db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    anon = get_anon_client()
    user_a = str(uuid.uuid4())
    user_b = get_real_user_id(service_db)

    # Idempotency: a prior run may have left a pending row for user_b if it
    # crashed between insert and cleanup.
    cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_b,))
    conn.commit()

    cur.execute("SET session_replication_role = replica")
    cur.execute(
        "INSERT INTO deletion_requests (user_id, email) VALUES (%s, %s)",
        (user_a, "test-a@example.com"),
    )
    cur.execute("SET session_replication_role = DEFAULT")
    conn.commit()

    try:
        blocked = anon_insert_blocked(
            anon, "deletion_requests",
            {"user_id": str(uuid.uuid4()), "email": "anon@example.com"},
        )
        check("anon cannot INSERT into deletion_requests", blocked)

        inserted = rls_insert_as_user(conn, user_b, "test-b@example.com")
        check("authenticated user CAN insert their own deletion_requests row", inserted)

        rows = anon.table("deletion_requests").select("id").eq("user_id", user_a).execute()
        check("anon cannot SELECT deletion_requests rows", len(getattr(rows, "data", []) or []) == 0)
    finally:
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM deletion_requests WHERE user_id IN (%s, %s)", (user_a, user_b))
        cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()

    cur.close()
    conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
