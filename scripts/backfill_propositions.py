#!/usr/bin/env python3
"""
backfill_propositions.py -- runs the standard propositions.process_document()
path against already-ingested documents that currently have zero propositions
(PLAN.md #17/#49, the propositions backfill). Unlike ingest scripts, this
never touches documents/chunks -- both already exist for every target
document -- it only reconstructs each document's full text from its existing
chunks (chunk_index order, same convention as detect_reference_fabrication.py
/ eligible_statements.py) and calls process_document() exactly as
shared_ingest.py's real call site does, on the same live write connection.

store_propositions() is clear-then-insert by document_id, so this is safe to
re-run on a document that already has propositions -- but every document
this script is pointed at is expected to have zero, by construction of the
caller's selection query (LEFT JOIN propositions ... WHERE pr.id IS NULL).

Input: a JSON file, a list of objects each with at least "id" (document_id)
and "source_id". Output: a JSON log of per-document results, written next to
the input file.

Zero changes to any existing proposition row. No serving-layer code touched.
"""
from __future__ import annotations

import json
import os
import sys
import time
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


def run(targets: list, prompt_version: str = None) -> list:
    params = db_params()
    conn = psycopg2.connect(**params)
    results = []
    for i, t in enumerate(targets, 1):
        doc_id = t["id"]
        source_id = t["source_id"]
        label = f"[{i}/{len(targets)}] {t.get('author', '?')} -- {t.get('title', doc_id)}"
        print(label)
        started = time.time()
        try:
            with conn.cursor() as cur:
                text, chunk_ids = _reconstruct_text_and_chunk_ids(cur, doc_id)
            if text is None:
                print("  SKIP: no chunks found")
                results.append({**t, "result": "no_chunks", "elapsed_s": 0, "word_count": 0})
                continue
            word_count = len(text.split())
            # Named-teacher fix (2026-07-30): pass speaker=author/source_name
            # and prompt_version="v3.1" through when the caller asked for it
            # (CLI arg below) -- omitted entirely (both None) reproduces the
            # exact prior-session call shape byte-for-byte.
            kwargs = {}
            if prompt_version:
                kwargs["prompt_version"] = prompt_version
                kwargs["speaker"] = t.get("author") or t.get("source_name")
            outcome = propositions.process_document(
                conn, doc_id, source_id, text, embed_text, chunk_ids=chunk_ids, **kwargs,
            )
            elapsed = round(time.time() - started, 1)
            print(f"  {outcome}  ({word_count} words, {elapsed}s)")
            results.append({**t, "result": outcome, "elapsed_s": elapsed, "word_count": word_count})
        except Exception as exc:
            elapsed = round(time.time() - started, 1)
            print(f"  EXCEPTION: {exc!r}")
            conn.rollback()
            results.append({**t, "result": f"exception:{exc!r}", "elapsed_s": elapsed, "word_count": None})
    conn.close()
    return results


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: backfill_propositions.py <targets.json> [prompt_version]")
    in_path = Path(sys.argv[1])
    prompt_version = sys.argv[2] if len(sys.argv) == 3 else None
    targets = json.loads(in_path.read_text())
    print(f"Running standard generation path on {len(targets)} document(s)"
          f"{f' (prompt_version={prompt_version!r})' if prompt_version else ''}...\n")
    results = run(targets, prompt_version=prompt_version)
    out_path = in_path.with_name(in_path.stem + "_results.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote results to {out_path}")

    stored = [r for r in results if r["result"].startswith("stored:")]
    zero = [r for r in results if r["result"] in ("no_propositions", "too_thin_to_extract")]
    errors = [r for r in results if r["result"] not in ("no_chunks",) and not r["result"].startswith("stored:") and r["result"] not in ("no_propositions", "too_thin_to_extract")]
    total_stored = sum(int(r["result"].split(":")[1]) for r in stored)
    print(f"\n{len(stored)} documents stored propositions ({total_stored} total).")
    print(f"{len(zero)} documents produced zero (no_propositions/too_thin_to_extract).")
    if errors:
        print(f"{len(errors)} documents errored or were skipped unexpectedly: {[r['result'] for r in errors]}")
