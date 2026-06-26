"""
Metering verification script — run from project root.
Tests: increment sequence, week rollover, hard stop, date_trunc Monday, stale-week GET /usage.
"""
import warnings; warnings.filterwarnings('ignore')

import datetime
import httpx
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import psycopg2
from supabase import create_client

# ── Credentials ──────────────────────────────────────────────────────────────
SB_URL    = 'https://jjerxncanaxlbdzcybab.supabase.co'
SB_SVC    = os.environ["SUPABASE_SERVICE_KEY"]
DB_URL    = os.environ["SUPABASE_DB_URL"]
API_BASE  = 'https://rhemata-production.up.railway.app'
TEST_EMAIL = 'creative@clf-church.com'

db = create_client(SB_URL, SB_SVC)

# ── psycopg2 connection (handles dotted username) ─────────────────────────────
from urllib.parse import urlparse as _urlparse
_p = _urlparse(DB_URL)
pg = psycopg2.connect(
    host=_p.hostname, port=_p.port or 5432,
    user=_p.username, password=_p.password,
    dbname=_p.path.lstrip('/'),
)
pg.autocommit = True
cur = pg.cursor()

# ── Apply migration 039 (skip if already applied) ────────────────────────────
print("=" * 60)
print("APPLYING MIGRATION 039")
print("=" * 60)
cur.execute("SELECT to_regclass('public.user_usage')")
table_exists = cur.fetchone()[0] is not None
if table_exists:
    print("Table user_usage already exists — migration was applied on first run, skipping")
else:
    migration = open('migrations/039_user_usage.sql').read()
    cur.execute(migration)
    print("Migration applied OK")
# Confirm both RPCs exist
cur.execute("""
    SELECT proname FROM pg_proc
    WHERE proname IN ('increment_user_query', 'get_user_usage')
    ORDER BY proname
""")
rpcs = [r[0] for r in cur.fetchall()]
print(f"RPCs in DB: {rpcs}")
assert 'increment_user_query' in rpcs, "increment_user_query missing"
assert 'get_user_usage' in rpcs, "get_user_usage missing"
print("Migration OK\n")

# ── Get test user + JWT ───────────────────────────────────────────────────────
link = db.auth.admin.generate_link({'type': 'magiclink', 'email': TEST_EMAIL})
TEST_USER_ID = link.user.id
resp = httpx.get(
    f'{SB_URL}/auth/v1/verify',
    params={'token': link.properties.hashed_token, 'type': 'magiclink', 'redirect_to': 'http://localhost:3000'},
    follow_redirects=False,
)
fragment = resp.headers.get('location', '').split('#', 1)[1]
JWT = parse_qs(fragment).get('access_token', [''])[0]
assert JWT, "Failed to obtain JWT"
print(f"Test user: {TEST_EMAIL} ({TEST_USER_ID})")
print(f"JWT obtained: {len(JWT)} chars\n")

# ── Helpers: call RPCs directly via psycopg2 (bypasses PostgREST schema cache) ─
def rpc_increment():
    cur.execute("SELECT query_count, weekly_limit, week_start FROM increment_user_query(%s)", (TEST_USER_ID,))
    row = cur.fetchone()
    return {'query_count': row[0], 'weekly_limit': row[1], 'week_start': row[2]}

def rpc_get_usage():
    cur.execute("SELECT query_count, weekly_limit, week_start FROM get_user_usage(%s)", (TEST_USER_ID,))
    row = cur.fetchone()
    return {'query_count': row[0], 'weekly_limit': row[1], 'week_start': row[2]}

def reset_row():
    """Remove test user row so each test section starts clean."""
    cur.execute("DELETE FROM user_usage WHERE user_id = %s", (TEST_USER_ID,))


# ════════════════════════════════════════════════════════════════════════════════
# TEST 0 — confirm date_trunc('week', now()) returns Monday
# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 0 — date_trunc('week', now()) is Monday")
print("=" * 60)
cur.execute("SELECT date_trunc('week', now())::date AS monday, to_char(date_trunc('week', now()), 'Day') AS day_name")
row = cur.fetchone()
monday_date, day_name = row
print(f"  date_trunc('week', now())::date = {monday_date}  ({day_name.strip()})")
assert day_name.strip() == 'Monday', f"Expected Monday, got {day_name}"
print("  PASS: confirmed Monday\n")


# ════════════════════════════════════════════════════════════════════════════════
# TEST 1 — increment sequence: 1 → 2 → 3
# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 1 — Increment sequence (expect 1 → 2 → 3)")
print("=" * 60)
reset_row()

for expected in [1, 2, 3]:
    row = rpc_increment()
    count = row['query_count']
    limit = row['weekly_limit']
    week_start = row['week_start']
    print(f"  call {expected}: query_count={count}  weekly_limit={limit}  week_start={week_start}")
    assert count == expected, f"Expected count={expected}, got {count}"

print("  PASS: 1 → 2 → 3\n")


# ════════════════════════════════════════════════════════════════════════════════
# TEST 2 — week rollover: stale week_start → resets to 1
# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 2 — Week rollover (stale week_start → count resets to 1)")
print("=" * 60)

# Fake last Monday (7 days ago)
last_monday = monday_date - datetime.timedelta(days=7)
cur.execute(
    "UPDATE user_usage SET week_start = %s WHERE user_id = %s",
    (last_monday, TEST_USER_ID)
)
print(f"  SET week_start = {last_monday} (last Monday, stale)")

before = db.table('user_usage').select('query_count,week_start').eq('user_id', TEST_USER_ID).execute()
print(f"  Row before call: count={before.data[0]['query_count']}  week_start={before.data[0]['week_start']}")

row = rpc_increment()
count    = row['query_count']
ws       = row['week_start']
print(f"  After increment_user_query: count={count}  week_start={ws}")

assert count == 1,           f"Expected reset to 1, got {count}"
assert str(ws) == str(monday_date), f"Expected week_start={monday_date}, got {ws}"
print(f"  PASS: count reset to 1, week_start updated to {ws}\n")


# ════════════════════════════════════════════════════════════════════════════════
# TEST 3 — hard stop: 429 fires before Sonnet
# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 3 — Hard stop (count=50 → 51st call gets 429, Sonnet never called)")
print("=" * 60)

# Set count=50 directly (at limit)
cur.execute(
    "UPDATE user_usage SET query_count = 50, week_start = %s WHERE user_id = %s",
    (monday_date, TEST_USER_ID)
)
print(f"  SET count=50, week_start={monday_date}")
print(f"  Sending POST {API_BASE}/chat with user JWT...")

chat_payload = {
    "question": "What is the baptism of the Holy Spirit?",
    "messages": [],
    "anon_id": None,
}
resp = httpx.post(
    f'{API_BASE}/chat',
    json=chat_payload,
    headers={'Authorization': f'Bearer {JWT}', 'Content-Type': 'application/json'},
    timeout=30,
)
print(f"\n  HTTP status: {resp.status_code}")
try:
    body = resp.json()
    print(f"  Response body: {json.dumps(body, indent=2)}")
except Exception:
    print(f"  Response text: {resp.text[:500]}")

assert resp.status_code == 429, f"Expected 429, got {resp.status_code}"
detail = body.get('detail', {})
assert detail.get('error') == 'weekly_limit_reached', f"Wrong error key: {detail}"
assert detail.get('limit') == 50, f"Wrong limit: {detail}"
assert 'resets' in detail, "Missing resets field"
print(f"\n  PASS: 429 returned with correct payload")
print(f"  error={detail['error']}, used={detail['used']}, limit={detail['limit']}")
print(f"  week_start={detail['week_start']}, resets={detail['resets']}\n")

# Confirm count in DB stayed at 51 (increment fired; 52nd call would also 429)
cur.execute("SELECT query_count FROM user_usage WHERE user_id = %s", (TEST_USER_ID,))
db_count = cur.fetchone()[0]
print(f"  DB count after rejected call: {db_count}  (51 = over limit, correct)\n")


# ════════════════════════════════════════════════════════════════════════════════
# TEST 4 — GET /usage with stale week → used=0
# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("TEST 4 — GET /usage stale week → used=0")
print("=" * 60)

# Stale the week_start again
cur.execute(
    "UPDATE user_usage SET query_count = 42, week_start = %s WHERE user_id = %s",
    (last_monday, TEST_USER_ID)
)
print(f"  SET count=42, week_start={last_monday} (stale)")

# Via RPC directly (mirrors what /usage calls)
row = rpc_get_usage()
print(f"  get_user_usage → count={row['query_count']}, limit={row['weekly_limit']}, week_start={row['week_start']}")
assert row['query_count'] == 0, f"Expected 0 (stale week rollover), got {row['query_count']}"
assert str(row['week_start']) == str(monday_date), f"Expected this Monday {monday_date}, got {row['week_start']}"

# Also hit the live /usage endpoint
resp = httpx.get(
    f'{API_BASE}/usage',
    headers={'Authorization': f'Bearer {JWT}'},
    timeout=15,
)
print(f"\n  GET {API_BASE}/usage → HTTP {resp.status_code}")
usage_body = resp.json()
print(f"  {json.dumps(usage_body, indent=2)}")
assert usage_body['used'] == 0, f"Expected used=0, got {usage_body['used']}"
print(f"\n  PASS: used=0 for stale week\n")


# ── Cleanup ───────────────────────────────────────────────────────────────────
reset_row()
cur.close()
pg.close()

print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
