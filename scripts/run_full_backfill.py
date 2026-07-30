#!/usr/bin/env python3
"""
run_full_backfill.py -- the full remaining propositions backfill (PLAN.md
#17/#49), using the v3.1 named-teacher path proven this session on two
independent 25-doc batches (0% "the author" rate, length unchanged ~38-39
words vs the v3 baseline, provenance stamped v3.1). Sequential, one document
at a time -- same call shape as backfill_propositions.py's proven wiring,
no concurrency (matches every other ingest script in this repo).

CRASH SAFETY / RESUMABILITY: every result (stored/zero/error/exception) is
appended to a JSONL log IMMEDIATELY after each document (flushed to disk,
not buffered in memory) -- a kill or crash at any point loses at most the
one in-flight document, never completed work. Re-running this script
resumes naturally: any doc_id already present in the log (any outcome, any
attempt) is excluded from the next target list before the pass starts, by
reading the log itself -- no separate state file.

ERROR HANDLING: a document that raises or returns "error" is logged and the
run continues to the next document -- one bad document never halts the
whole pass. After the full main pass finishes, every document whose LATEST
logged attempt is "error"/"exception:*" (and that has no "retry" attempt
logged yet) gets exactly ONE retry, same call shape, logged with
attempt="retry" so a second script run doesn't retry it again.

CONNECTION RESILIENCE: a long-lived single connection across 500+ sequential
calls can hit an idle/pooler disconnect. A psycopg2 OperationalError/
InterfaceError closes and reopens the connection, logs that one document as
an exception (picked up by the retry pass), and continues -- it does not
kill the run.

Zero changes to any existing proposition row: every target document is
selected because it CURRENTLY has zero propositions, so store_propositions()'s
clear-then-insert DELETE is always a no-op for these documents. No serving
layer code touched.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

import psycopg2  # noqa: E402
from app.services.embeddings import embed_text  # noqa: E402
import propositions  # noqa: E402

PRECEPT_AUSTIN_SOURCE_ID = "698e0596-a9c6-4890-958d-9199f1b8f762"
PROMPT_VERSION = "v3.1"

LOG_DIR = PROJECT_ROOT / "backfill_run_review"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "full_backfill_log.jsonl"


def db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def fetch_live_targets(params: dict) -> list:
    """Zero propositions, licensed/unlicensed, not Precept Austin -- the
    exact same criteria proven correct on both proving batches this
    session. One live snapshot at start; not re-queried mid-run (ingestion
    continuing in the background is out of this run's scope)."""
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id::text, d.title, d.author, s.name AS source_name, d.source_id::text
        FROM documents d
        JOIN sources s ON s.id = d.source_id
        LEFT JOIN propositions pr ON pr.document_id = d.id
        WHERE pr.id IS NULL
          AND s.license_status IN ('licensed', 'unlicensed')
          AND d.source_id != %s
        ORDER BY d.author, d.title
        """,
        (PRECEPT_AUSTIN_SOURCE_ID,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "author": r[2], "source_name": r[3], "source_id": r[4]}
        for r in rows
    ]


def load_log() -> list:
    if not LOG_PATH.exists():
        return []
    records = []
    for line in LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def append_log(record: dict) -> None:
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _reconstruct_text_and_chunk_ids(cur, document_id: str):
    cur.execute(
        "SELECT id::text, content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
        (document_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return None, []
    chunk_ids = [r[0] for r in rows]
    text = "\n".join(r[1] for r in rows)
    return text, chunk_ids


def process_one(conn, target: dict, attempt: str) -> dict:
    doc_id = target["id"]
    source_id = target["source_id"]
    started = time.time()
    with conn.cursor() as cur:
        text, chunk_ids = _reconstruct_text_and_chunk_ids(cur, doc_id)
    if text is None:
        return {
            **target, "attempt": attempt, "result": "no_chunks",
            "elapsed_s": 0, "word_count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    word_count = len(text.split())
    speaker = target.get("author") or target.get("source_name")
    outcome = propositions.process_document(
        conn, doc_id, source_id, text, embed_text, chunk_ids=chunk_ids,
        speaker=speaker, prompt_version=PROMPT_VERSION,
    )
    elapsed = round(time.time() - started, 1)
    return {
        **target, "attempt": attempt, "result": outcome,
        "elapsed_s": elapsed, "word_count": word_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_pass(targets: list, attempt: str, params: dict) -> None:
    conn = psycopg2.connect(**params)
    total = len(targets)
    for i, target in enumerate(targets, 1):
        label = f"[{attempt} {i}/{total}] {target.get('author') or target.get('source_name') or '?'} -- {target.get('title', target['id'])}"
        print(label, flush=True)
        try:
            record = process_one(conn, target, attempt)
            print(f"  {record['result']}  ({record['word_count']} words, {record['elapsed_s']}s)", flush=True)
            append_log(record)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            print(f"  CONNECTION ERROR: {exc!r} -- reopening connection and continuing", flush=True)
            append_log({
                **target, "attempt": attempt, "result": f"exception:{exc!r}",
                "elapsed_s": 0, "word_count": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            try:
                conn.close()
            except Exception:
                pass
            conn = psycopg2.connect(**params)
        except Exception as exc:
            print(f"  EXCEPTION: {exc!r}", flush=True)
            try:
                conn.rollback()
            except Exception:
                pass
            append_log({
                **target, "attempt": attempt, "result": f"exception:{exc!r}",
                "elapsed_s": 0, "word_count": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    conn.close()


def main() -> None:
    params = db_params()

    print("Querying live remaining backfill set...", flush=True)
    live_targets = fetch_live_targets(params)
    print(f"Live remaining count: {len(live_targets)}", flush=True)

    log = load_log()
    attempted_ids = {r["id"] for r in log}
    main_pass_targets = [t for t in live_targets if t["id"] not in attempted_ids]
    print(
        f"{len(attempted_ids)} document(s) already logged (resumed from a prior run of this "
        f"script) -- {len(main_pass_targets)} remaining for this pass.",
        flush=True,
    )

    if main_pass_targets:
        print(f"\n=== MAIN PASS: {len(main_pass_targets)} document(s) ===\n", flush=True)
        run_pass(main_pass_targets, "first", params)
    else:
        print("\nMain pass: nothing to do, all targets already attempted.", flush=True)

    # ── Retry pass: every doc whose LATEST attempt errored, and that has
    #    no retry attempt logged yet. Re-read the log fresh (not the
    #    in-memory `log` from before the main pass) so a resumed run picks
    #    up exactly where a prior crash left off. ──────────────────────────
    log = load_log()
    latest_by_id = {}
    for r in log:
        latest_by_id[r["id"]] = r  # last write wins -- log is append-only in time order
    retried_ids = {r["id"] for r in log if r.get("attempt") == "retry"}
    needs_retry = [
        r for doc_id, r in latest_by_id.items()
        if doc_id not in retried_ids
        and (r["result"] == "error" or str(r["result"]).startswith("exception:"))
    ]
    print(f"\n=== RETRY PASS: {len(needs_retry)} document(s) that errored on first attempt ===\n", flush=True)
    if needs_retry:
        retry_targets = [
            {"id": r["id"], "title": r.get("title"), "author": r.get("author"),
             "source_name": r.get("source_name"), "source_id": r.get("source_id")}
            for r in needs_retry
        ]
        run_pass(retry_targets, "retry", params)
    else:
        print("Nothing to retry.", flush=True)

    print("\n=== DONE ===", flush=True)


if __name__ == "__main__":
    main()
