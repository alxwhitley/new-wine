#!/usr/bin/env python3
"""
test_ingest_queue_endpoints.py -- Live verification of the source ingest
queue endpoints (migration 075 + backend/app/routers/ingest_queue.py)
against the real deployed production backend (Railway).

Uses a real, already-registered account (creative@clf-church.com, same one
scripts/test_deletion_requests_migration.py uses for RLS checks) to obtain a
genuine Supabase session via the admin generate_link -> /auth/v1/verify
exchange -- no password or interactive login needed, and no browser
automation required either: this hits the exact same JSON endpoints the
admin panel's fetch() calls hit, so it's a faithful proxy for "submitted
through the real form."

The account starts with no user_roles row (role defaults to 'user'). This
script:
  1. confirms the endpoint rejects it while non-admin (403)
  2. temporarily grants it 'admin' via direct DB write
  3. exercises validation (empty/malformed URL, no-name-and-no-per-item)
  4. inserts one real row through the real POST /ingest-queue endpoint
  5. confirms it landed via a direct DB query (not by trusting the response)
  6. exercises assign / drop / cleared-to-run
  7. cleans up every row it created and reverts the account's role

Usage:
  python3 scripts/test_ingest_queue_endpoints.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

API = "https://rhemata-production.up.railway.app"
TEST_EMAIL = "creative@clf-church.com"

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

    p = urlparse(os.environ["SUPABASE_DB_URL"])
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def get_session_token(service_db, email):
    link = service_db.auth.admin.generate_link({"type": "magiclink", "email": email})
    token_hash = link.properties.hashed_token
    resp = requests.post(
        f"{os.environ['SUPABASE_URL']}/auth/v1/verify",
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"], "Content-Type": "application/json"},
        json={"type": "magiclink", "token_hash": token_hash},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], link.user.id


def main():
    from supabase import create_client

    print("\nSource ingest queue -- live endpoint verification (production)")
    print("=" * 60)

    service_db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    token, user_id = get_session_token(service_db, TEST_EMAIL)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    conn = get_db_conn()
    cur = conn.cursor()

    # Sanity: confirm this account really has no role row before we start.
    cur.execute("SELECT role FROM user_roles WHERE user_id = %s", (user_id,))
    original_role_row = cur.fetchone()
    print(f"  (test account starts with user_roles row: {original_role_row})")

    created_row_ids = []

    try:
        # ── 1. Non-admin rejected ────────────────────────────────────────────
        r = requests.get(f"{API}/ingest-queue", headers=headers, timeout=15)
        check("non-admin GET /ingest-queue -> 403", r.status_code == 403)

        r = requests.post(
            f"{API}/ingest-queue",
            headers=headers,
            json={
                "url": "https://example.com/non-admin-should-not-land",
                "source_format": "web_page",
                "source_scope": "single",
                "attribute_to": "Nobody",
                "attribution_mode": "declared",
            },
            timeout=15,
        )
        check("non-admin POST /ingest-queue -> 403", r.status_code == 403)

        # ── 2. Grant temporary admin role ────────────────────────────────────
        cur.execute(
            "INSERT INTO user_roles (user_id, role) VALUES (%s, 'admin') "
            "ON CONFLICT (user_id) DO UPDATE SET role = 'admin'",
            (user_id,),
        )
        conn.commit()
        print("  (granted temporary admin role to test account)")

        # ── 3. Validation ─────────────────────────────────────────────────────
        r = requests.post(
            f"{API}/ingest-queue",
            headers=headers,
            json={"url": "", "source_format": "web_page", "source_scope": "single",
                  "attribution_mode": "declared", "attribute_to": "Bob"},
            timeout=15,
        )
        check("empty URL rejected (422)", r.status_code == 422)

        r = requests.post(
            f"{API}/ingest-queue",
            headers=headers,
            json={"url": "not-a-url", "source_format": "web_page", "source_scope": "single",
                  "attribution_mode": "declared", "attribute_to": "Bob"},
            timeout=15,
        )
        check("malformed URL rejected (422)", r.status_code == 422)

        r = requests.post(
            f"{API}/ingest-queue",
            headers=headers,
            json={"url": "https://example.com/test-source", "source_format": "web_page",
                  "source_scope": "single", "attribution_mode": "declared", "attribute_to": ""},
            timeout=15,
        )
        check("no name + not per-item rejected (422)", r.status_code == 422)

        # ── 4. Real insert through the real endpoint ─────────────────────────
        test_url = "https://example.com/blog/test-source-ingest-queue-verification"
        r = requests.post(
            f"{API}/ingest-queue",
            headers=headers,
            json={"url": test_url, "source_format": "web_page", "source_scope": "single",
                  "attribution_mode": "declared", "attribute_to": "Test Teacher"},
            timeout=15,
        )
        check("real insert -> 200", r.status_code == 200)
        row = r.json() if r.status_code == 200 else {}
        row_id = row.get("id")
        if row_id:
            created_row_ids.append(row_id)

        # ── 5. Confirm in DB directly (not trusting the response) ────────────
        cur.execute(
            "SELECT url, source_format, source_scope, attribute_to, attribution_mode, "
            "status, cleared_to_run, submitted_by FROM source_ingest_queue WHERE id = %s",
            (row_id,),
        )
        db_row = cur.fetchone()
        check(
            "row confirmed via direct DB query",
            db_row is not None
            and db_row[0] == test_url
            and db_row[5] == "waiting"
            and db_row[6] is False
            and str(db_row[7]) == user_id,
        )

        cur.execute(
            "SELECT attribute_to, attribution_mode FROM source_ingest_domain_memory WHERE domain = 'example.com'"
        )
        dm_row = cur.fetchone()
        check(
            "domain memory upserted for example.com",
            dm_row is not None and dm_row[0] == "Test Teacher" and dm_row[1] == "declared",
        )

        # ── 6. Domain-memory prefill lookup ──────────────────────────────────
        r = requests.get(
            f"{API}/ingest-queue/domain-memory",
            headers=headers,
            params={"url": "https://example.com/some/other/path"},
            timeout=15,
        )
        pf = r.json() if r.status_code == 200 else {}
        check(
            "domain-memory prefill returns the remembered name",
            r.status_code == 200 and pf.get("found") is True and pf.get("attribute_to") == "Test Teacher",
        )

        # ── 7. List returns the row ──────────────────────────────────────────
        r = requests.get(f"{API}/ingest-queue", headers=headers, timeout=15)
        listed = r.json() if r.status_code == 200 else {}
        queue_ids = {row_.get("id") for row_ in listed.get("queue", [])}
        check("GET /ingest-queue lists the new row", row_id in queue_ids)

        # ── 8. cleared_to_run toggle ──────────────────────────────────────────
        r = requests.patch(
            f"{API}/ingest-queue/{row_id}/cleared-to-run",
            headers=headers,
            json={"cleared_to_run": True},
            timeout=15,
        )
        check("cleared_to_run toggle -> 200", r.status_code == 200)
        cur.execute("SELECT cleared_to_run FROM source_ingest_queue WHERE id = %s", (row_id,))
        check("cleared_to_run persisted true in DB", cur.fetchone()[0] is True)

        # ── 9. needs_attention flow: assign + drop on two fresh rows ─────────
        cur.execute(
            "INSERT INTO source_ingest_queue "
            "(url, source_format, source_scope, attribution_mode, status, flag_reason, submitted_by) "
            "VALUES (%s, 'web_page', 'single', 'per_item', 'needs_attention', 'author not detected', %s) "
            "RETURNING id",
            ("https://example.com/needs-attention-assign", user_id),
        )
        assign_row_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO source_ingest_queue "
            "(url, source_format, source_scope, attribution_mode, status, flag_reason, submitted_by) "
            "VALUES (%s, 'web_page', 'single', 'per_item', 'needs_attention', 'author not detected', %s) "
            "RETURNING id",
            ("https://example.com/needs-attention-drop", user_id),
        )
        drop_row_id = cur.fetchone()[0]
        conn.commit()
        created_row_ids.extend([assign_row_id, drop_row_id])

        r = requests.get(f"{API}/ingest-queue", headers=headers, timeout=15)
        attn_ids = {row_.get("id") for row_ in r.json().get("needs_attention", [])}
        check("both needs_attention rows listed", {assign_row_id, drop_row_id}.issubset(attn_ids))

        r = requests.post(
            f"{API}/ingest-queue/{assign_row_id}/assign",
            headers=headers, json={"attribute_to": "Assigned Teacher"}, timeout=15,
        )
        check("assign -> 200", r.status_code == 200)
        cur.execute(
            "SELECT attribute_to, status, flag_reason FROM source_ingest_queue WHERE id = %s",
            (assign_row_id,),
        )
        db_assign = cur.fetchone()
        check(
            "assign persisted (attribute_to set, status waiting, flag cleared)",
            db_assign == ("Assigned Teacher", "waiting", None),
        )

        r = requests.post(
            f"{API}/ingest-queue/{drop_row_id}/drop",
            headers=headers, json={"reason": "test cleanup"}, timeout=15,
        )
        check("drop -> 200", r.status_code == 200)
        cur.execute("SELECT status, flag_reason FROM source_ingest_queue WHERE id = %s", (drop_row_id,))
        check("drop persisted (status failed)", cur.fetchone() == ("failed", "test cleanup"))

    finally:
        # ── Cleanup: remove every row this script created ────────────────────
        if created_row_ids:
            cur.execute(
                "DELETE FROM source_ingest_queue WHERE id = ANY(%s::uuid[])",
                (created_row_ids,),
            )
        cur.execute("DELETE FROM source_ingest_domain_memory WHERE domain = 'example.com'")
        # Revert the test account's role to its exact original state.
        if original_role_row is None:
            cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
        else:
            cur.execute(
                "UPDATE user_roles SET role = %s WHERE user_id = %s",
                (original_role_row[0], user_id),
            )
        conn.commit()
        cur.execute("SELECT role FROM user_roles WHERE user_id = %s", (user_id,))
        print(f"  (cleanup done -- test account role row now: {cur.fetchone()})")
        cur.close()
        conn.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
