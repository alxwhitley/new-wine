#!/usr/bin/env python3
"""
test_account_delete_request_e2e.py -- End-to-end verification of the
account deletion-request stub against the LIVE production API:
  POST /account/delete-request
  GET  /account/delete-requests
  POST /account/delete-requests/{id}/resolve

Run AFTER pushing to main and confirming the Railway deploy has finished
(see scripts/test_metering.py for the established pattern this follows).

Requires in backend/app/.env (or environment):
  SUPABASE_DB_URL      -- direct Postgres connection (service role)
  SUPABASE_URL         -- project URL
  SUPABASE_SERVICE_KEY -- service role key (for admin.generate_link)

Usage:
  python3 scripts/test_account_delete_request_e2e.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

SB_URL = os.environ["SUPABASE_URL"]
API_BASE = "https://rhemata-production.up.railway.app"
TEST_EMAIL = "creative@clf-church.com"

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


def jwt_for_email(db, email):
    """Mint a real access token for `email` via a Supabase magic link --
    same approach as scripts/test_metering.py."""
    link = db.auth.admin.generate_link({"type": "magiclink", "email": email})
    resp = httpx.get(
        f"{SB_URL}/auth/v1/verify",
        params={
            "token": link.properties.hashed_token,
            "type": "magiclink",
            "redirect_to": "http://localhost:3000",
        },
        follow_redirects=False,
    )
    fragment = resp.headers.get("location", "").split("#", 1)[1]
    token = parse_qs(fragment).get("access_token", [""])[0]
    if not token:
        raise RuntimeError("Failed to obtain JWT for %s" % email)
    return token, link.user.id


def main():
    from supabase import create_client

    print("\nAccount deletion requests -- end-to-end verification")
    print("=" * 50)

    db = create_client(SB_URL, os.environ["SUPABASE_SERVICE_KEY"])
    conn = get_db_conn()
    cur = conn.cursor()

    # -- Find an admin to test the admin-only endpoints -------------------------
    cur.execute("SELECT user_id FROM user_roles WHERE role = 'admin' LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("ERROR: no admin user found in user_roles -- cannot test admin endpoints")
        sys.exit(1)
    admin_user_id = row[0]
    cur.execute("SELECT email FROM auth.users WHERE id = %s", (admin_user_id,))
    admin_email = cur.fetchone()[0]

    user_jwt, user_id = jwt_for_email(db, TEST_EMAIL)
    admin_jwt, _ = jwt_for_email(db, admin_email)
    print(f"Test user: {TEST_EMAIL} ({user_id})")
    print(f"Admin:     {admin_email} ({admin_user_id})\n")

    cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_id,))
    conn.commit()

    try:
        # -- TEST 1: submit a deletion request -----------------------------------
        res = httpx.post(
            f"{API_BASE}/account/delete-request",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("POST /account/delete-request returns 200", res.status_code == 200)

        # -- TEST 2: duplicate submission is rejected ----------------------------
        res2 = httpx.post(
            f"{API_BASE}/account/delete-request",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("duplicate POST /account/delete-request returns 400", res2.status_code == 400)

        # -- TEST 3: admin can list the pending request --------------------------
        res3 = httpx.get(
            f"{API_BASE}/account/delete-requests",
            headers={"Authorization": f"Bearer {admin_jwt}"},
        )
        listed = res3.json() if res3.status_code == 200 else []
        found = next((r for r in listed if r["user_id"] == user_id), None)
        check("GET /account/delete-requests (admin) lists the new request", found is not None)

        # -- TEST 4: non-admin cannot list requests ------------------------------
        res4 = httpx.get(
            f"{API_BASE}/account/delete-requests",
            headers={"Authorization": f"Bearer {user_jwt}"},
        )
        check("GET /account/delete-requests (non-admin) returns 403", res4.status_code == 403)

        # -- TEST 5: admin can resolve it -----------------------------------------
        if found:
            res5 = httpx.post(
                f"{API_BASE}/account/delete-requests/{found['id']}/resolve",
                headers={"Authorization": f"Bearer {admin_jwt}"},
            )
            check("POST /account/delete-requests/{id}/resolve returns 200", res5.status_code == 200)

            cur.execute("SELECT status FROM deletion_requests WHERE id = %s", (found["id"],))
            status = cur.fetchone()[0]
            check("row status is 'resolved' after resolve", status == "resolved")
    finally:
        cur.execute("DELETE FROM deletion_requests WHERE user_id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
