#!/usr/bin/env python3
"""
test_pastors_rls.py — Verify RLS policies for the three Pastors' Notes tables.

Run AFTER applying migration 038_pastors_notes.sql in Supabase SQL Editor.

Requires in backend/app/.env (or environment):
  SUPABASE_DB_URL    — direct Postgres connection (service role)
  SUPABASE_URL       — project URL
  SUPABASE_ANON_KEY  — public anon key (or NEXT_PUBLIC_SUPABASE_ANON_KEY)

Usage:
  python3 scripts/test_pastors_rls.py

Checks:
  1. anon client CANNOT insert into user_roles
  2. anon client CANNOT insert into contributor_requests
  3. anon client CANNOT insert into pastors_cards
  4. anon client CAN select published pastors_cards
  5. anon client CANNOT select removed pastors_cards
  6. authenticated user_b CANNOT read user_a's contributor_requests
"""

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# ── Connection helpers ────────────────────────────────────────────────────────

def get_db_conn():
    """Direct Postgres connection via SUPABASE_DB_URL (service role, bypasses RLS)."""
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
    """supabase-py client using the public anon key (respects RLS)."""
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


# ── Reporting ─────────────────────────────────────────────────────────────────

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


# ── Test helpers ──────────────────────────────────────────────────────────────

def anon_insert_blocked(anon, table, payload):
    # type: (object, str, dict) -> bool
    """Return True if the anon client's INSERT was denied (no rows created)."""
    try:
        resp = anon.table(table).insert(payload).execute()
        # supabase-py v2: empty data means no rows inserted → blocked
        return not getattr(resp, "data", None)
    except Exception:
        return True  # HTTP 403 / exception = blocked


def anon_select_rows(anon, table, eq_col, eq_val):
    # type: (object, str, str, str) -> list
    """Return rows visible to the anon client for a specific id."""
    try:
        resp = anon.table(table).select("id").eq(eq_col, eq_val).execute()
        return getattr(resp, "data", []) or []
    except Exception:
        return []


def rls_select_as_user(conn, query, params, auth_uid):
    # type: (object, str, tuple, str) -> list
    """
    Run query inside a transaction that sets the authenticated role and
    spoofs auth.uid() via request.jwt.claims — simulates Supabase RLS
    for an authenticated non-service user.
    Returns the rows visible under those claims, then rolls back.
    """
    claims = json.dumps({"sub": auth_uid, "role": "authenticated"})
    cur = conn.cursor()
    try:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL ROLE authenticated")
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            (claims,),
        )
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    except Exception as exc:
        raise exc
    finally:
        cur.execute("ROLLBACK")
        cur.close()


# ── Main test run ─────────────────────────────────────────────────────────────

def run(conn, anon):
    # ── Setup: insert test data bypassing FK constraints ─────────────────────
    # We use session_replication_role to skip FK checks so we don't need to
    # touch auth.users, then clean up with the same bypass.
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    card_pub_id = str(uuid.uuid4())
    card_rem_id = str(uuid.uuid4())
    req_id = str(uuid.uuid4())

    cur = conn.cursor()
    try:
        cur.execute("SET session_replication_role = replica")

        cur.execute("""
            INSERT INTO pastors_cards (id, user_id, verse_id, content, status)
            VALUES (%s, %s, 'JHN.1.1',
                    'Test published card — enough chars to clear the 50-char minimum check.',
                    'published')
        """, (card_pub_id, user_a))

        cur.execute("""
            INSERT INTO pastors_cards (id, user_id, verse_id, content, status)
            VALUES (%s, %s, 'JHN.1.1',
                    'Test removed card — enough chars to clear the 50-char minimum check here.',
                    'removed')
        """, (card_rem_id, user_a))

        cur.execute("""
            INSERT INTO contributor_requests (id, user_id, message, status)
            VALUES (%s, %s, 'Test request for RLS verification', 'pending')
        """, (req_id, user_a))

        cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        print("ERROR: Test data setup failed: %s" % e)
        sys.exit(1)

    try:
        # ── 1. anon cannot INSERT into user_roles ─────────────────────────────
        blocked = anon_insert_blocked(
            anon, "user_roles",
            {"user_id": str(uuid.uuid4()), "role": "user"},
        )
        check("anon cannot INSERT into user_roles", blocked)

        # ── 2. anon cannot INSERT into contributor_requests ───────────────────
        blocked = anon_insert_blocked(
            anon, "contributor_requests",
            {"user_id": str(uuid.uuid4()), "message": "test"},
        )
        check("anon cannot INSERT into contributor_requests", blocked)

        # ── 3. anon cannot INSERT into pastors_cards ──────────────────────────
        blocked = anon_insert_blocked(
            anon, "pastors_cards",
            {
                "user_id": str(uuid.uuid4()),
                "verse_id": "JHN.1.1",
                "content": "x" * 60,
            },
        )
        check("anon cannot INSERT into pastors_cards", blocked)

        # ── 4. anon CAN select published pastors_cards ────────────────────────
        rows = anon_select_rows(anon, "pastors_cards", "id", card_pub_id)
        check("anon CAN SELECT published pastors_cards", len(rows) == 1)

        # ── 5. anon CANNOT select removed pastors_cards ───────────────────────
        rows = anon_select_rows(anon, "pastors_cards", "id", card_rem_id)
        check("anon CANNOT SELECT removed pastors_cards", len(rows) == 0)

        # ── 6. authenticated user_b cannot read user_a's contributor_requests ─
        try:
            rows = rls_select_as_user(
                conn,
                "SELECT id FROM contributor_requests WHERE id = %s",
                (req_id,),
                user_b,  # authenticated as user_b, not user_a
            )
            check(
                "authenticated user_b cannot read user_a's contributor_requests",
                len(rows) == 0,
            )
        except Exception as e:
            check(
                "authenticated user_b cannot read user_a's contributor_requests (%s)" % e,
                False,
            )

    finally:
        # ── Cleanup: remove test rows ─────────────────────────────────────────
        cur.execute("SET session_replication_role = replica")
        cur.execute("DELETE FROM pastors_cards WHERE id IN (%s, %s)", (card_pub_id, card_rem_id))
        cur.execute("DELETE FROM contributor_requests WHERE id = %s", (req_id,))
        cur.execute("SET session_replication_role = DEFAULT")
        conn.commit()
        cur.close()


def main():
    print("\nPastors' Notes — RLS verification (migration 038)")
    print("=" * 50)

    try:
        conn = get_db_conn()
    except Exception as e:
        print("ERROR: Could not connect via SUPABASE_DB_URL: %s" % e)
        sys.exit(1)

    anon = get_anon_client()

    run(conn, anon)
    conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))

    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
