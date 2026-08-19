#!/usr/bin/env python3
"""
backfill_phrase_refs.py — Scan documents and add implied bible references
based on phrase matching against sources/phrase_lookup.json.

Pure string matching, no LLM calls. Merges with existing bible_references.

Usage:
  python3 scripts/backfill_phrase_refs.py --dry-run --limit 5
  python3 scripts/backfill_phrase_refs.py --source-kind sermon_transcript
  python3 scripts/backfill_phrase_refs.py --author "Derek Prince" --force
  python3 scripts/backfill_phrase_refs.py --chunks --dry-run --limit 10
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")


def load_phrase_lookup(path):
    # type: (Path) -> Dict[str, List[str]]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def get_db_conn():
    import psycopg2
    from urllib.parse import urlparse, unquote

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def get_supabase_client():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def fetch_documents(conn, source_kind=None, author=None, force=False):
    # type: (object, Optional[str], Optional[str], bool) -> List[Dict]
    query = "SELECT id, title, author, source_kind, bible_references, content_summary FROM documents WHERE 1=1"
    params = []  # type: List
    if source_kind:
        query += " AND source_kind = %s"
        params.append(source_kind)
    if author:
        query += " AND author ILIKE %s"
        params.append("%{}%".format(author))
    if not force:
        query += " AND (bible_references IS NULL OR array_length(bible_references, 1) IS NULL OR array_length(bible_references, 1) <= 5)"
    query += " ORDER BY created_at ASC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_first_chunks(conn, doc_id, n=3):
    # type: (object, str, int) -> str
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index LIMIT %s",
            (doc_id, n),
        )
        return "\n".join(row[0] for row in cur.fetchall())


def fetch_all_chunks(conn, doc_id):
    # type: (object, str) -> List[Dict]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, content, bible_references FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (doc_id,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def match_phrases(text, phrase_lookup):
    # type: (str, Dict[str, List[str]]) -> Set[str]
    text_lower = text.lower()
    refs = set()  # type: Set[str]
    for phrase, ref_list in phrase_lookup.items():
        if phrase in text_lower:
            for ref in ref_list:
                refs.add(ref)
    return refs


def main():
    parser = argparse.ArgumentParser(description="Backfill bible_references via phrase matching")
    parser.add_argument("--source-kind", type=str, default=None, help="Filter to source_kind")
    parser.add_argument("--author", type=str, default=None, help="Filter by author (ILIKE)")
    parser.add_argument("--limit", type=int, default=0, help="Process only N documents")
    parser.add_argument("--dry-run", action="store_true", help="Print without updating")
    parser.add_argument("--force", action="store_true", help="Re-process docs with >5 existing refs")
    parser.add_argument("--chunks", action="store_true", help="Also backfill chunk-level bible_references")
    args = parser.parse_args()

    lookup_path = ROOT / "sources" / "phrase_lookup.json"
    phrase_lookup = load_phrase_lookup(lookup_path)
    print("Loaded {} phrases from {}".format(len(phrase_lookup), lookup_path.name))

    conn = get_db_conn()
    db = get_supabase_client()

    docs = fetch_documents(conn, source_kind=args.source_kind, author=args.author, force=args.force)
    if args.limit > 0:
        docs = docs[:args.limit]

    if not docs:
        print("No documents to process.")
        conn.close()
        return

    mode = "doc+chunk" if args.chunks else "doc-only"
    print("Processing {} document(s) [{}]{}{}\n".format(
        len(docs),
        mode,
        " (dry run)" if args.dry_run else "",
        " (force)" if args.force else "",
    ))

    stats = {"processed": 0, "updated": 0, "new_refs": 0, "failed": 0,
             "chunks_updated": 0, "chunk_refs_added": 0}

    for i, doc in enumerate(docs, 1):
        doc_id = doc["id"]
        title = doc.get("title") or "(no title)"
        author = doc.get("author") or "(no author)"

        try:
            # Build combined text for document-level matching
            summary = doc.get("content_summary") or ""
            first_chunks = fetch_first_chunks(conn, doc_id, n=3)
            combined = "{}\n{}".format(summary, first_chunks)

            if not combined.strip():
                stats["processed"] += 1
                continue

            # Document-level phrase matching
            matched_refs = match_phrases(combined, phrase_lookup)
            existing = set(doc.get("bible_references") or [])
            new_refs = matched_refs - existing

            doc_updated = False
            if new_refs:
                merged = sorted(existing | matched_refs)
                if not args.dry_run:
                    db.table("documents").update({"bible_references": merged}).eq("id", doc_id).execute()
                stats["updated"] += 1
                stats["new_refs"] += len(new_refs)
                doc_updated = True

                prefix = "[DRY] " if args.dry_run else ""
                new_list = sorted(new_refs)[:8]
                suffix = " ..." if len(new_refs) > 8 else ""
                print("[{:>4d}/{:<4d}] {}{} — {} → +{} doc refs: {}{}".format(
                    i, len(docs), prefix, author, title[:50], len(new_refs), new_list, suffix
                ))

            # Chunk-level phrase matching
            if args.chunks:
                all_chunks = fetch_all_chunks(conn, doc_id)
                chunk_count = 0
                chunk_ref_count = 0
                for chunk in all_chunks:
                    chunk_matched = match_phrases(chunk["content"], phrase_lookup)
                    if not chunk_matched:
                        continue
                    chunk_existing = set(chunk.get("bible_references") or [])
                    chunk_new = chunk_matched - chunk_existing
                    if not chunk_new:
                        continue
                    chunk_merged = sorted(chunk_existing | chunk_matched)
                    if not args.dry_run:
                        with conn.cursor() as cur:
                            cur.execute(
                                "UPDATE chunks SET bible_references = %s WHERE id = %s",
                                (chunk_merged, chunk["id"]),
                            )
                        conn.commit()
                    chunk_count += 1
                    chunk_ref_count += len(chunk_new)

                if chunk_count > 0:
                    stats["chunks_updated"] += chunk_count
                    stats["chunk_refs_added"] += chunk_ref_count
                    prefix = "[DRY] " if args.dry_run else ""
                    print("[{:>4d}/{:<4d}] {}  chunks: {}/{} updated, +{} refs".format(
                        i, len(docs), prefix, chunk_count, len(all_chunks), chunk_ref_count
                    ))

            stats["processed"] += 1

        except Exception as e:
            print("[{:>4d}/{:<4d}] {} — {} → FAILED: {}".format(i, len(docs), author, title[:50], e))
            stats["failed"] += 1

    conn.close()

    print("\n{}".format("=" * 64))
    print("SUMMARY")
    print("{}".format("=" * 64))
    print("  Total processed: {}".format(stats["processed"]))
    print("  Docs updated:    {}".format(stats["updated"]))
    print("  New doc refs:    {}".format(stats["new_refs"]))
    if args.chunks:
        print("  Chunks updated:  {}".format(stats["chunks_updated"]))
        print("  New chunk refs:  {}".format(stats["chunk_refs_added"]))
    print("  Failed:          {}".format(stats["failed"]))


if __name__ == "__main__":
    main()
