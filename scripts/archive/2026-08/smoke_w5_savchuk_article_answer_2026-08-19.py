#!/usr/bin/env python3
"""W5–W6 answer-integrity smoke for the Savchuk web article.

Submits one async question that does NOT match the speaking_in_tongues
position paper (teacher-named), waits for the job, then checks whether the
quarantined article document is present in retrieved chunks / citations.

Usage:
  /private/tmp/rhemata-w1w4-venv/bin/python \\
    scripts/smoke_w5_savchuk_article_answer_2026-08-19.py
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

# Avoids match_position_paper → speaking_in_tongues (verified locally).
QUESTION = "What does Vlad Savchuk teach about developing a prayer language?"

ARTICLE_DOC_ID = "c97533db-7b48-46ec-b77f-239b703b8697"
STAGING_SOURCE_ID = "33cfa6b5-ae98-4c68-a41a-e1db52914546"
ARTICLE_TITLE = "How to Grow in Tongues and Strengthen Your Prayer Language"
STAGING_NAME = "Vlad Savchuk (web staging)"


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "backend/app/.env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _http_json(method: str, url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
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
    conn = psycopg2.connect(env["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT c.id::text AS chunk_id, c.chunk_index
        FROM chunks c
        WHERE c.document_id = %s
        ORDER BY c.chunk_index
        """,
        (ARTICLE_DOC_ID,),
    )
    article_chunks = cur.fetchall()
    article_chunk_ids = {r["chunk_id"] for r in article_chunks}
    print("article_chunks", len(article_chunk_ids), sorted(r["chunk_index"] for r in article_chunks))
    if len(article_chunk_ids) != 4:
        print("UNEXPECTED chunk count", file=sys.stderr)
        conn.close()
        return 2

    anon = f"smoke-w5-article-{uuid.uuid4()}"
    status, submit = _http_json(
        "POST",
        f"{API}/async-chat/submit",
        {"question": QUESTION, "messages": [], "anon_id": anon},
    )
    print("submit", status, json.dumps(submit)[:500])
    if status >= 400:
        conn.close()
        return 2
    job_id = submit.get("job_id")
    if not job_id:
        print("no job_id", file=sys.stderr)
        conn.close()
        return 2

    job = None
    for i in range(120):
        cur.execute(
            """
            SELECT id::text, status, outcome, policy_version, model,
                   answer, citations, verified_references, quote_ids,
                   retrieved_chunk_ids, last_error, finished_at
            FROM answer_jobs WHERE id = %s
            """,
            (job_id,),
        )
        job = cur.fetchone()
        st = (job or {}).get("status")
        print(f"poll {i}: status={st} outcome={(job or {}).get('outcome')}")
        if st in ("done", "failed", "canceled"):
            break
        time.sleep(2)
    else:
        print("timeout waiting for job", file=sys.stderr)
        conn.close()
        return 3

    if not job or job["status"] != "done":
        print("JOB_NOT_DONE", job and dict(job), file=sys.stderr)
        conn.close()
        return 4

    retrieved = [str(x) for x in (job.get("retrieved_chunk_ids") or [])]
    retrieved_hit = [cid for cid in retrieved if cid in article_chunk_ids]
    citations = job.get("citations") or []
    cite_hits = []
    for c in citations:
        cid = str(c.get("chunk_id") or "")
        author = c.get("author") or ""
        title = c.get("document_title") or ""
        if cid in article_chunk_ids or ARTICLE_TITLE in title or STAGING_NAME in author:
            cite_hits.append(
                {
                    "chunk_id": cid,
                    "author": author,
                    "document_title": title,
                    "url": c.get("url"),
                    "content_prefix": (c.get("content") or "")[:160],
                }
            )

    answer = job.get("answer") or ""
    report = {
        "job_id": job_id,
        "question": QUESTION,
        "outcome": job.get("outcome"),
        "policy_version": job.get("policy_version"),
        "model": job.get("model"),
        "n_retrieved_chunks": len(retrieved),
        "n_citations": len(citations),
        "n_verified_references": len(job.get("verified_references") or []),
        "quote_ids": job.get("quote_ids") or [],
        "article_chunk_ids_retrieved": retrieved_hit,
        "article_citations": cite_hits,
        "answer_contains_web_staging": STAGING_NAME in answer,
        "answer_contains_savchuk": "Savchuk" in answer or "savchuk" in answer.lower(),
        "answer_preview": answer[:1200],
        "answer_len": len(answer),
    }
    print(json.dumps(report, indent=2))

    out_path = ROOT / "docs/audits/_w5_smoke_raw_2026-08-19.json"
    out_path.write_text(json.dumps({"report": report, "full_answer": answer, "citations": citations}, indent=2))
    print("wrote", out_path)

    ok_retrieve = bool(retrieved_hit)
    ok_cite = bool(cite_hits)
    ok_outcome = job.get("outcome") == "answered"
    print(
        "CHECKS",
        {
            "outcome_answered": ok_outcome,
            "article_in_retrieved": ok_retrieve,
            "article_in_citations": ok_cite,
        },
    )
    conn.close()
    if not (ok_outcome and ok_retrieve and ok_cite):
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
