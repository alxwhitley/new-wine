#!/usr/bin/env python3
"""
Backfill bible_references on all documents in Supabase.

For each document:
  1. Fetch all chunks (ordered by chunk_index) and concatenate content
  2. Call Groq (via scripts/bible_refs.py) to extract references
  3. Normalize and dedupe
  4. UPDATE documents SET bible_references = ... WHERE id = ...

Usage:
  python3 extract_bible_refs.py                 # process docs missing refs
  python3 extract_bible_refs.py --dry-run       # preview, no writes
  python3 extract_bible_refs.py --force         # re-process all, even if already set
  python3 extract_bible_refs.py --dry-run --force
  python3 extract_bible_refs.py --dry-run --limit 10 --source-kind commentary
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from bible_refs import extract_bible_references

from supabase import create_client  # noqa: E402


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_db_conn():
    """Direct PostgreSQL connection via psycopg2 (avoids PostgREST timeouts)."""
    db_url = os.environ["SUPABASE_DB_URL"]
    return psycopg2.connect(db_url, connect_timeout=30)


def fetch_documents(conn, force: bool, source_kind: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
    """Fetch documents via psycopg2. If not force, only those with empty/null bible_references."""
    query = "SELECT id, title, bible_references FROM documents WHERE 1=1"
    params = []
    if source_kind:
        query += " AND source_kind = %s"
        params.append(source_kind)
    if not force:
        query += " AND (bible_references IS NULL OR array_length(bible_references, 1) IS NULL)"
    query += " ORDER BY id"
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_doc_content(conn, doc_id: str) -> str:
    """Fetch all chunks for a document via psycopg2, concatenated in chunk_index order."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (doc_id,),
        )
        return "\n\n".join(row[0] or "" for row in cur.fetchall())


def main():
    parser = argparse.ArgumentParser(description="Backfill bible_references on documents")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--force", action="store_true", help="Re-process docs that already have refs")
    parser.add_argument("--limit", type=int, default=None, help="Max number of documents to process")
    parser.add_argument("--source-kind", type=str, default=None, help="Filter by source_kind (e.g. commentary)")
    args = parser.parse_args()

    dry_run = args.dry_run
    force = args.force

    conn = get_db_conn()
    print(f"Fetching documents (force={force}, source_kind={args.source_kind}, limit={args.limit})...")
    docs = fetch_documents(conn, force=force, source_kind=args.source_kind, limit=args.limit)
    print(f"Found {len(docs)} document(s) to process")

    if dry_run:
        print("[DRY RUN] No writes will be performed")

    updated = 0
    empty = 0
    failed = 0

    for i, doc in enumerate(docs, 1):
        doc_id = doc["id"]
        title = (doc.get("title") or "(untitled)")[:70]
        print(f"\n[{i}/{len(docs)}] {title}")

        try:
            content = fetch_doc_content(conn, doc_id)
            if not content.strip():
                print("  No chunk content — skipping")
                empty += 1
                continue

            refs = extract_bible_references(content)
            if refs:
                preview = ", ".join(refs[:5]) + (f" ... (+{len(refs) - 5} more)" if len(refs) > 5 else "")
                print(f"  Extracted {len(refs)} reference(s): {preview}")
            else:
                print("  No Bible references found")
                empty += 1

            if not dry_run:
                supabase.table("documents").update(
                    {"bible_references": refs}
                ).eq("id", doc_id).execute()
                updated += 1
        except Exception as e:
            print(f"  Failed: {e}")
            failed += 1

    conn.close()
    print(f"\n{'=' * 60}")
    print(f"Done. {updated} updated, {empty} with no refs, {failed} failed")
    if dry_run:
        print("(dry run — no data was written)")


if __name__ == "__main__":
    main()
