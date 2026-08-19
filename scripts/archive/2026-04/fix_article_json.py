#!/usr/bin/env python3
"""
fix_article_json.py — One-off migration to fix magazine article chunks
whose content was stored as raw JSON (with topic_tags + body fields)
instead of parsed body text.

The malformed chunks have this format:
  [New Wine | Issue | Title by Author]

  ```json
  {"topic_tags": [...], "body": "
  actual article text that continues to end of chunk...

The JSON is truncated (never closed) because the body text exceeded
the chunk size. This script extracts everything after "body": " as
the article text, preserves the [header] prefix, and updates each chunk.
Also refreshes content_summary on affected documents.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

from supabase import create_client


def extract_body(content):
    """Extract body text from a chunk that contains raw JSON with a
    "body" field. The JSON is typically truncated (never closed).
    Returns (header, body) or None if not malformed."""
    # Must contain the "body": pattern
    body_match = re.search(r'"body"\s*:\s*"', content)
    if not body_match:
        return None

    # Check this isn't legitimate content that just mentions "body":
    # Malformed chunks always have ```json or topic_tags before the body
    has_json_fence = "```json" in content[:content.find('"body"')]
    has_topic_tags = '"topic_tags"' in content[:content.find('"body"')]
    if not has_json_fence and not has_topic_tags:
        return None

    # Extract [header] prefix if present
    header = ""
    if content.startswith("["):
        bracket_end = content.find("]")
        if bracket_end != -1:
            header = content[:bracket_end + 1]

    # Everything after "body": " is the article text
    body_start = body_match.end()
    body = content[body_start:]

    # Strip trailing JSON artifacts if the JSON was actually closed
    # (remove trailing ", "} , ```)
    body = re.sub(r'"\s*\}\s*(?:```\s*)?$', '', body)

    # Unescape JSON string escapes
    body = body.replace('\\"', '"')
    body = body.replace('\\n', '\n')
    body = body.replace('\\\\', '\\')

    return header, body.strip()


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("✗ SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        sys.exit(1)

    db = create_client(url, key)

    # Find malformed chunks: content contains "body": (inside JSON)
    result = db.table("chunks").select("id, document_id, content").like("content", '%"body":%').execute()
    candidates = result.data or []
    print(f"Found {len(candidates)} chunk(s) containing '\"body\":' — checking each...")

    fixed_chunks = 0
    skipped = 0
    fixed_docs = set()

    for chunk in candidates:
        content = chunk["content"]
        parsed = extract_body(content)
        if parsed is None:
            skipped += 1
            continue

        header, body = parsed
        if not body:
            print(f"  ⚠ Chunk {chunk['id'][:8]}...: empty body after extraction, skipping")
            skipped += 1
            continue

        # Rebuild chunk: [header]\n\nbody text
        if header:
            new_content = f"{header}\n\n{body}"
        else:
            new_content = body

        db.table("chunks").update({"content": new_content}).eq("id", chunk["id"]).execute()
        print(f"  ✓ Fixed chunk {chunk['id'][:8]}... ({len(body.split())} words)")
        fixed_chunks += 1
        fixed_docs.add(chunk["document_id"])

    # Refresh content_summary on affected documents
    fixed_summaries = 0
    for doc_id in fixed_docs:
        first_chunk = (
            db.table("chunks")
            .select("content")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .limit(1)
            .execute()
        )
        if first_chunk.data:
            new_summary = first_chunk.data[0]["content"][:200]
            db.table("documents").update({"content_summary": new_summary}).eq("id", doc_id).execute()
            fixed_summaries += 1

    print(f"\nDone.")
    print(f"  Candidates checked:      {len(candidates)}")
    print(f"  Chunks fixed:            {fixed_chunks}")
    print(f"  Skipped (not malformed): {skipped}")
    print(f"  Documents affected:      {len(fixed_docs)}")
    print(f"  Content summaries fixed: {fixed_summaries}")


if __name__ == "__main__":
    main()
