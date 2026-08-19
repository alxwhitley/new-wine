#!/usr/bin/env python3
"""Attended smoke after QUOTE_SELECTION_ENABLED=true.

Submits one async question, waits for completion, then checks:
  - resolve payload includes presentation fields for any quote_ids
  - every returned quote_id is quality_pipeline_version=quote_quality_v1
    and selection_eligible=true (no legacy IDs)

Usage:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/smoke_quote_selection_reenable_2026-08-19.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
API = "https://rhemata-production.up.railway.app"
QUESTION = (
    "What does it mean for believers to reign with Christ in this life, "
    "and how does spiritual authority relate to strongholds of the mind?"
)


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "backend/app/.env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            payload = json.loads(raw) if raw else {"raw": raw}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload


def main() -> int:
    env = _env()
    anon = f"smoke-quote-{uuid.uuid4()}"
    status, submit = _http_json(
        "POST",
        f"{API}/async-chat/submit",
        {"question": QUESTION, "messages": [], "anon_id": anon},
    )
    print("submit", status, json.dumps(submit)[:500])
    if status >= 400:
        return 2
    job_id = submit.get("job_id") or submit.get("id")
    if not job_id:
        print("no job_id", file=sys.stderr)
        return 2

    result = None
    for i in range(90):
        st, result = _http_json("GET", f"{API}/async-chat/result/{job_id}")
        state = (result or {}).get("status") or (result or {}).get("state")
        print(f"poll {i}: http={st} status={state}")
        if state in ("completed", "failed", "answered", "error", "refused"):
            break
        # some payloads nest under job
        if (result or {}).get("outcome") or (result or {}).get("answer"):
            break
        time.sleep(2)
    else:
        print("timeout waiting for job", file=sys.stderr)
        return 3

    print("result_keys", sorted((result or {}).keys()))
    quote_ids = (
        (result or {}).get("quote_ids")
        or ((result or {}).get("result") or {}).get("quote_ids")
        or ((result or {}).get("answer") or {}).get("quote_ids")
        or []
    )
    print("quote_ids", quote_ids)

    if quote_ids:
        st, resolved = _http_json(
            "POST",
            f"{API}/answer-quotes/resolve",
            {"quote_ids": quote_ids},
        )
        print("resolve", st, json.dumps(resolved, indent=2)[:2000])
        quotes = (resolved or {}).get("quotes") or []
        for q in quotes:
            missing = [k for k in ("teacher_name", "work_title", "topic_ids", "restated_point") if k not in q or q.get(k) in (None, [], "")]
            print("presentation_check", q.get("id"), "missing_or_empty=", missing)

    conn = psycopg2.connect(env["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if quote_ids:
        cur.execute(
            """
            SELECT id::text, status, selection_eligible, quality_pipeline_version
            FROM quotes WHERE id = ANY(%s::uuid[])
            """,
            (quote_ids,),
        )
        rows = cur.fetchall()
        print("db_rows", rows)
        bad = [
            r
            for r in rows
            if r["status"] != "approved"
            or not r["selection_eligible"]
            or r["quality_pipeline_version"] != "quote_quality_v1"
        ]
        if bad:
            print("LEGACY_OR_INELIGIBLE_IDS", bad, file=sys.stderr)
            conn.close()
            return 4
        print("OK all quote_ids are gold-pipeline approved+eligible")
    else:
        print("NOTE: no quote_ids on this answer (allowed if similarity below threshold)")
        cur.execute(
            """
            SELECT count(*)::int AS n
            FROM quotes
            WHERE quality_pipeline_version='quote_quality_v1'
              AND status='approved'
              AND selection_eligible=true
            """
        )
        print("gold_pool", cur.fetchone())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
