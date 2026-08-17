#!/usr/bin/env python3
"""
test_corpus_inventory_endpoint.py -- live verification for
GET /corpus-inventory/export (CORPUS-INV-001, 2026-08-17).

Standalone script, not pytest -- this repo's scripts/test_*.py convention.
Loads backend/app/.env (SUPABASE_URL/SUPABASE_SERVICE_KEY/
CORPUS_INVENTORY_API_KEY) before importing the app, drives it with an
in-process fastapi.testclient.TestClient (never real network traffic, never
a deployed instance), and independently cross-checks the CSV's row counts
against a SEPARATE live connection via the read-only
rhemata_readonly_analysis role (scripts/corpus_data_quality_sweep.py's
connect_readonly()) -- never the same client/credential used by the
endpoint itself.

Six checks:
  1. Valid key -> 200, correct header, row count == live `SELECT count(*)
     FROM documents` (no PostgREST pagination truncation).
  2. No key -> 404.
  3. Wrong key -> 404.
  4. No write path -- POST/PUT/DELETE all fail as writes (404/405, never
     2xx), plus a static grep of the router file for
     .insert(/.update(/.delete(/.upsert(.
  5. Payload shape -- exactly 3 columns/row; missing author/url rows are
     present (empty string), not dropped; empty-author row count matches
     an independently live-queried count.
  6. Schema hiding -- /openapi.json never mentions the route
     (include_in_schema=False).

Run: python3.12 scripts/test_corpus_inventory_endpoint.py
(Python 3.12 to match Invariant 1 / this repo's pinned deploy runtime --
the machine's bare `python3` is 3.9.6 and will not have fastapi installed.)
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / "backend" / "app" / ".env"

try:
    from dotenv import load_dotenv
except ImportError:
    print("FAIL: python-dotenv not installed in this interpreter")
    sys.exit(1)

if not ENV_PATH.exists():
    print("FAIL: %s does not exist -- cannot load credentials" % ENV_PATH)
    sys.exit(1)

load_dotenv(ENV_PATH)

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

import os  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
import corpus_data_quality_sweep as sweep  # noqa: E402

RESULTS = []


def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    line = "[%s] %s" % (status, label)
    if detail:
        line += " -- %s" % detail
    print(line)
    RESULTS.append(bool(condition))
    return bool(condition)


def main() -> int:
    api_key = os.environ.get("CORPUS_INVENTORY_API_KEY")
    if not api_key:
        print("FAIL: CORPUS_INVENTORY_API_KEY not set in %s" % ENV_PATH)
        return 1

    client = TestClient(app)

    # ---- Check 1: valid key -> full corpus, no truncation ----
    resp = client.get("/corpus-inventory/export", params={"key": api_key})
    ok_status = _check("Check 1a: valid key returns 200", resp.status_code == 200,
                        "status=%d" % resp.status_code)

    csv_text = resp.text if ok_status else ""
    reader = csv.reader(io.StringIO(csv_text)) if ok_status else None
    all_rows = list(reader) if reader else []
    header = all_rows[0] if all_rows else []
    body_rows = all_rows[1:] if all_rows else []

    _check(
        "Check 1b: header row is exactly author,title,canonical_url",
        header == ["author", "title", "canonical_url"],
        "header=%r" % (header,),
    )

    print("Connecting via rhemata_readonly_analysis for independent cross-check...")
    conn = sweep.connect_readonly()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM documents")
    live_total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM documents WHERE author IS NULL OR btrim(author) = ''")
    live_missing_author = cur.fetchone()[0]

    csv_row_count = len(body_rows)
    print("CSV row count (excluding header): %d" % csv_row_count)
    print("Live `SELECT count(*) FROM documents`: %d" % live_total)
    _check(
        "Check 1c: CSV row count exactly equals live document count",
        csv_row_count == live_total,
        "csv=%d live=%d" % (csv_row_count, live_total),
    )

    # ---- Check 2: no key -> 404 ----
    resp2 = client.get("/corpus-inventory/export")
    _check("Check 2: no key returns 404", resp2.status_code == 404,
           "status=%d" % resp2.status_code)

    # ---- Check 3: wrong key -> 404 ----
    resp3 = client.get("/corpus-inventory/export", params={"key": "definitely-wrong-value"})
    _check("Check 3: wrong key returns 404", resp3.status_code == 404,
           "status=%d" % resp3.status_code)

    # ---- Check 4: no write path ----
    post_resp = client.post("/corpus-inventory/export", params={"key": api_key})
    put_resp = client.put("/corpus-inventory/export", params={"key": api_key})
    delete_resp = client.delete("/corpus-inventory/export", params={"key": api_key})
    _check(
        "Check 4a: POST does not succeed as a write",
        post_resp.status_code in (404, 405),
        "status=%d" % post_resp.status_code,
    )
    _check(
        "Check 4b: PUT does not succeed as a write",
        put_resp.status_code in (404, 405),
        "status=%d" % put_resp.status_code,
    )
    _check(
        "Check 4c: DELETE does not succeed as a write",
        delete_resp.status_code in (404, 405),
        "status=%d" % delete_resp.status_code,
    )

    router_path = ROOT / "backend" / "app" / "routers" / "corpus_inventory.py"
    router_text = router_path.read_text(encoding="utf-8")
    write_matches = re.findall(r"\.(insert|update|delete|upsert)\(", router_text)
    print("Check 4d grep result for .insert(/.update(/.delete(/.upsert( in %s: %r"
          % (router_path, write_matches))
    _check(
        "Check 4d: zero real write-method calls in router file",
        len(write_matches) == 0,
        "matches=%r" % write_matches,
    )

    # ---- Check 5: payload shape ----
    shape_ok = all(len(r) == 3 for r in body_rows) if body_rows else False
    _check("Check 5a: every row has exactly 3 columns", shape_ok)

    empty_author_example = None
    empty_url_example = None
    empty_author_count = 0
    for r in body_rows:
        author, title, url = r
        if author == "":
            empty_author_count += 1
            if empty_author_example is None:
                empty_author_example = r
        if url == "" and empty_url_example is None:
            empty_url_example = r

    print("Empty-author example row: %r" % (empty_author_example,))
    print("Empty-canonical_url example row: %r" % (empty_url_example,))
    _check(
        "Check 5b: at least one empty-author row present",
        empty_author_example is not None,
    )
    _check(
        "Check 5c: at least one empty-canonical_url row present",
        empty_url_example is not None,
    )

    print("CSV empty-author row count: %d" % empty_author_count)
    print("Live `SELECT count(*) FROM documents WHERE author IS NULL OR btrim(author)=''`: %d"
          % live_missing_author)
    _check(
        "Check 5d: empty-author row count matches independent live query (144)",
        empty_author_count == live_missing_author == 144,
        "csv=%d live=%d expected=144" % (empty_author_count, live_missing_author),
    )

    conn.close()

    # ---- Check 6: schema hiding ----
    openapi_resp = client.get("/openapi.json")
    openapi_ok = openapi_resp.status_code == 200
    _check("Check 6a: /openapi.json is reachable", openapi_ok,
           "status=%d" % openapi_resp.status_code)
    if openapi_ok:
        openapi_text = openapi_resp.text
        _check(
            "Check 6b: /corpus-inventory/export does not appear in /openapi.json",
            "/corpus-inventory/export" not in openapi_text,
        )
    else:
        _check("Check 6b: /corpus-inventory/export does not appear in /openapi.json", False,
               "openapi.json unreachable")

    passed = sum(1 for r in RESULTS if r)
    total = len(RESULTS)
    print()
    print("%d/%d checks passed" % (passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
