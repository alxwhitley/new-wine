#!/usr/bin/env python3
"""
verify_chunk_alignment.py — standalone post-ingest spot-check tool.

For one stored document, selects up to ``sample_size`` chunks in
``chunk_index`` order, recomputes each embedding from the chunk's stored
``content``, and asks Postgres/pgvector to cosine-compare that fresh vector
with the row's stored ``embedding``. It prints one result per sampled chunk;
it deliberately does not apply a pass/fail threshold, so a low similarity is
a finding for the caller to investigate rather than a script crash.

This is a read-only diagnostic run after rows are committed. The current
shared ingest path computes chunk text and embeddings before writing, then
writes the document, chunks, propositions, and completion stamp through its
shared database connection. Fresh ingest inserts all chunks in one batch;
``on_existing="reuse"`` appends only the unstored tail using continued
``chunk_index`` values, while ``on_existing="delete_and_reingest"`` replaces
the old document and its dependent rows in an atomic swap. This script does
not participate in those writes and does not verify chunk boundaries,
proposition extraction, source resolution, completeness, or transaction
behavior — it checks only stored content/embedding pairing for the sample.

Usage:
  python3 scripts/verify_chunk_alignment.py --document-id <uuid>
  python3 scripts/verify_chunk_alignment.py --document-id <uuid> --sample-size 10
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.services.embeddings import embed_text


def db_params_from_env() -> dict:
    parsed = urlparse(os.environ["SUPABASE_DB_URL"])
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def spot_check(db_params: dict, document_id: str, sample_size: int = 5) -> List[Dict]:
    """Recompute embed_text(content) for up to sample_size chunks of
    document_id (lowest chunk_index first) and cosine-compare each against
    its stored embedding via `1 - (embedding <=> fresh::vector)`.

    Returns one dict per sampled chunk: {chunk_id, chunk_index,
    cosine_similarity}. Does not raise or judge a threshold -- a low
    similarity is a finding for the caller to act on, not a crash here.
    """
    conn = psycopg2.connect(**db_params)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, chunk_index, content FROM chunks "
                "WHERE document_id = %s ORDER BY chunk_index LIMIT %s",
                (document_id, sample_size),
            )
            rows = cur.fetchall()

            results = []
            for chunk_id, chunk_index, content in rows:
                fresh_embedding = embed_text(content)
                fresh_str = "[" + ",".join(str(v) for v in fresh_embedding) + "]"
                cur.execute(
                    "SELECT 1 - (embedding <=> %s::vector) AS cosine_similarity "
                    "FROM chunks WHERE id = %s",
                    (fresh_str, chunk_id),
                )
                (cosine_similarity,) = cur.fetchone()
                results.append({
                    "chunk_id": str(chunk_id),
                    "chunk_index": chunk_index,
                    "cosine_similarity": float(cosine_similarity),
                })
            return results
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Spot-check stored chunk embeddings against a freshly recomputed embedding"
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--sample-size", type=int, default=5)
    args = parser.parse_args()

    results = spot_check(db_params_from_env(), args.document_id, args.sample_size)
    if not results:
        print(f"No chunks found for document_id={args.document_id}")
        return
    for r in results:
        print(f"  chunk_index={r['chunk_index']:<4} cosine_similarity={r['cosine_similarity']:.6f}  id={r['chunk_id']}")


if __name__ == "__main__":
    main()
