#!/usr/bin/env python3
"""
verify_chunk_alignment.py — standalone spot-check tool.

Recomputes the embedding for a stored chunk's `content` and cosine-compares
it against that chunk's stored `embedding`, using pgvector's own `<=>`
operator so no local vector-math dependency is needed. Same technique used
at #8 (chunk-header-bake verification) to prove text/embedding pairing
survived a conversion, rather than trust it.

Standalone by design (#9's diagnostic, Q6): not called from inside any
insert path (shared_ingest.py's psycopg2_batch or rest_per_chunk). Run
separately, after the fact, against real rows already committed to the DB.

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
