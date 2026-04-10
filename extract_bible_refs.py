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
"""

import os
import sys
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "backend" / "app" / ".env")

# Allow importing scripts/bible_refs.py
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from bible_refs import extract_bible_references  # noqa: E402

from supabase import create_client  # noqa: E402


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_documents(force: bool) -> List[Dict]:
    """Fetch documents. If not force, skip those that already have bible_references."""
    result = (
        supabase.table("documents")
        .select("id, title, bible_references")
        .order("id")
        .execute()
    )
    docs = result.data or []
    if not force:
        docs = [d for d in docs if not d.get("bible_references")]
    return docs


def fetch_doc_content(doc_id: str) -> str:
    """Fetch all chunks for a document and concatenate in chunk_index order."""
    result = (
        supabase.table("chunks")
        .select("content, chunk_index")
        .eq("document_id", doc_id)
        .order("chunk_index")
        .execute()
    )
    chunks = result.data or []
    return "\n\n".join(c.get("content") or "" for c in chunks)


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    print(f"Fetching documents (force={force})...")
    docs = fetch_documents(force=force)
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
            content = fetch_doc_content(doc_id)
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

    print(f"\n{'=' * 60}")
    print(f"Done. {updated} updated, {empty} with no refs, {failed} failed")
    if dry_run:
        print("(dry run — no data was written)")


if __name__ == "__main__":
    main()
