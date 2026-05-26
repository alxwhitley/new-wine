#!/usr/bin/env python3
"""
retag_sermons.py — Retag all sermon_transcript documents using Anthropic claude-haiku-4-5.

Uses the first 3 chunks of each document as tagging context (more context than the
previous Groq-based tagger). Validates all tags against taxonomy.md.

Usage:
  python3 scripts/retag_sermons.py                          # retag all untagged
  python3 scripts/retag_sermons.py --force                   # retag all, even already-tagged
  python3 scripts/retag_sermons.py --limit 5 --dry-run       # test run
  python3 scripts/retag_sermons.py --author "Derek Prince"   # single author
  python3 scripts/retag_sermons.py --suggest-tags            # also suggest new taxonomy tags
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")


# ── Load taxonomy from taxonomy.md ───────────────────────────────────────────

def load_valid_tags(taxonomy_path):
    # type: (Path) -> Set[str]
    """Parse taxonomy.md and extract all tag names."""
    text = taxonomy_path.read_text(encoding="utf-8")
    tags = set()  # type: Set[str]
    for line in text.splitlines():
        line = line.strip()
        # Skip headings, separators, blank lines
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        # Each line is comma-separated tags
        for tag in line.split(","):
            tag = tag.strip()
            if tag:
                tags.add(tag)
    return tags


TAXONOMY_PATH = ROOT / "taxonomy.md"
VALID_TAGS = load_valid_tags(TAXONOMY_PATH)
TAXONOMY_LIST = ", ".join(sorted(VALID_TAGS))

SYSTEM_PROMPT = """You are a theological taxonomy classifier. Based on this document, assign 3-6 topic tags from the taxonomy below.

STRICT RULES:
- Only assign a tag if the document CENTERS on that topic as a MAIN THEME — the topic must be a core subject the author is teaching, not a passing reference
- A single sentence or brief mention does NOT qualify. The topic must be developed across multiple paragraphs or be a clear structural focus of the document
- Ask yourself: 'Is this topic one of the 3-6 things this document is primarily ABOUT?' If no, do not assign it
- Prefer fewer, highly accurate tags over more loosely related ones
- 3-4 tags is ideal for a focused document. Only use 5-6 if the document genuinely covers that many distinct themes in depth
- Never assign a tag just because a keyword from the tag appears in the text
- You MUST only return tags from the exact list below. Do not create new tags. Do not modify tag names. Copy them exactly as written.

Return JSON only: {"tags": ["tag1", "tag2", ...]}

TAXONOMY (use ONLY these exact tags):
""" + TAXONOMY_LIST

BROADER_SYSTEM_PROMPT = """You are a theological taxonomy classifier. The previous attempt returned too few valid tags. Please try again with a broader view.

Assign 3-6 topic tags from the taxonomy below. Look for secondary themes and underlying theological topics, not just the primary subject.

You MUST only return tags from the exact list below. Copy them exactly as written.

Return JSON only: {"tags": ["tag1", "tag2", ...]}

TAXONOMY (use ONLY these exact tags):
""" + TAXONOMY_LIST

SUGGEST_PROMPT = """Given this document's content and the tags already assigned to it, are there 1-2 important theological topics it covers that are NOT represented in the assigned tags AND are NOT present in the provided tag list?

Only suggest tags for genuinely important themes that the taxonomy is missing. Do not suggest minor variations of existing tags.

Assigned tags: {assigned_tags}

Available tag list:
{taxonomy}

If there are good suggestions, return them. If the existing taxonomy covers this document well, return empty.

Return JSON only: {{"suggested_tags": [], "reason": ""}}"""

SUMMARY_PROMPT = """Write a 2 sentence summary of this document describing its core topic and main argument. Be specific — mention the author and key teaching points. Return only the summary, no preamble."""


# ── DB helpers ───────────────────────────────────────────────────────────────

def get_db_conn():
    """Connect to Supabase via psycopg2 using SUPABASE_DB_URL."""
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


def fetch_sermon_docs(conn, author=None, force=False):
    # type: (object, Optional[str], bool) -> List[Dict]
    """Fetch sermon_transcript documents. Skip already-tagged unless force=True."""
    query = """
        SELECT id, title, author, topic_tags
        FROM documents
        WHERE source_kind = 'sermon_transcript'
    """
    params = []  # type: List
    if not force:
        query += " AND (topic_tags IS NULL OR topic_tags = '{}')"
    if author:
        query += " AND author ILIKE %s"
        params.append("%{}%".format(author))
    query += " ORDER BY created_at ASC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_first_chunks(conn, doc_id, n=3):
    # type: (object, str, int) -> List[str]
    """Fetch the first N chunks of a document ordered by chunk_index."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index LIMIT %s",
            (doc_id, n),
        )
        return [row[0] for row in cur.fetchall()]


# ── Anthropic helper ─────────────────────────────────────────────────────────

def call_haiku(client, system, content):
    # type: (object, str, str) -> str
    """Call claude-haiku-4-5 and return raw text response."""
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": "DOCUMENT:\n{}".format(content)}],
        system=system,
    )
    return response.content[0].text.strip()


def parse_json_response(raw):
    # type: (str) -> dict
    """Parse JSON from LLM response, handling code fences."""
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        obj = re.search(r"\{[\s\S]*\}", raw)
        if obj:
            return json.loads(obj.group())
        raise


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Retag sermon_transcript documents via claude-haiku-4-5")
    parser.add_argument("--limit", type=int, default=0, help="Process only N documents")
    parser.add_argument("--author", type=str, default=None, help="Filter by author name (ILIKE)")
    parser.add_argument("--suggest-tags", action="store_true", help="Run a second pass to suggest new taxonomy tags")
    parser.add_argument("--dry-run", action="store_true", help="Print tags but don't update Supabase")
    parser.add_argument("--force", action="store_true", help="Retag already-tagged documents")
    args = parser.parse_args()

    print("Loading taxonomy from {}".format(TAXONOMY_PATH))
    print("  {} valid tags loaded\n".format(len(VALID_TAGS)))

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    conn = get_db_conn()
    db = get_supabase_client()

    docs = fetch_sermon_docs(conn, author=args.author, force=args.force)
    if args.limit > 0:
        docs = docs[:args.limit]

    if not docs:
        print("No documents to process.")
        conn.close()
        return

    print("Processing {} document(s){}{}\n".format(
        len(docs),
        " (dry run)" if args.dry_run else "",
        " (force retag)" if args.force else "",
    ))

    suggestions_path = ROOT / "sources" / "tag_suggestions.jsonl"

    stats = {"updated": 0, "skipped": 0, "failed": 0, "suggestions": 0}
    failed_docs = []  # type: List[str]

    for i, doc in enumerate(docs, 1):
        doc_id = doc["id"]
        title = doc.get("title") or "(no title)"
        author = doc.get("author") or "(no author)"

        # Fetch first 3 chunks
        chunks = fetch_first_chunks(conn, doc_id, n=3)
        if not chunks:
            print("[{:>4d}/{:<4d}] {} — {} → SKIPPED (no chunks)".format(i, len(docs), author, title[:60]))
            stats["skipped"] += 1
            continue

        content = "\n".join(chunks)

        # Tag
        try:
            raw = call_haiku(client, SYSTEM_PROMPT, content)
            result = parse_json_response(raw)
            tags = result.get("tags", [])
        except Exception as e:
            print("[{:>4d}/{:<4d}] {} — {} → FAILED: {}".format(i, len(docs), author, title[:60], e))
            failed_docs.append("{} — {}".format(author, title))
            stats["failed"] += 1
            continue

        valid_tags = [t for t in tags if t in VALID_TAGS]

        # Retry with broader prompt if < 3 valid tags
        if len(valid_tags) < 3:
            try:
                raw = call_haiku(client, BROADER_SYSTEM_PROMPT, content)
                result = parse_json_response(raw)
                retry_tags = [t for t in result.get("tags", []) if t in VALID_TAGS]
                if len(retry_tags) > len(valid_tags):
                    valid_tags = retry_tags
            except Exception:
                pass  # keep whatever we had

        valid_tags = valid_tags[:6]

        if not valid_tags:
            print("[{:>4d}/{:<4d}] {} — {} → SKIPPED (no valid tags)".format(i, len(docs), author, title[:60]))
            stats["skipped"] += 1
            continue

        # Generate content summary
        summary = ""
        try:
            summary = call_haiku(client, SUMMARY_PROMPT, content)
        except Exception as e:
            print("[{:>4d}/{:<4d}] {} — {} → SUMMARY FAILED: {}".format(i, len(docs), author, title[:60], e))

        # Update
        update_data = {"topic_tags": valid_tags}
        if summary:
            update_data["content_summary"] = summary
        if not args.dry_run:
            try:
                db.table("documents").update(update_data).eq("id", doc_id).execute()
            except Exception as e:
                print("[{:>4d}/{:<4d}] {} — {} → FAILED (update): {}".format(i, len(docs), author, title[:60], e))
                failed_docs.append("{} — {}".format(author, title))
                stats["failed"] += 1
                continue

        stats["updated"] += 1
        prefix = "[DRY] " if args.dry_run else ""
        print("[{:>4d}/{:<4d}] {}{}— {} → {}".format(i, len(docs), prefix, author + " ", title[:50], valid_tags))
        if summary:
            print("         SUMMARY: {}".format(summary[:120]))

        # Suggest tags (second pass)
        if args.suggest_tags:
            try:
                suggest_prompt = SUGGEST_PROMPT.format(
                    assigned_tags=json.dumps(valid_tags),
                    taxonomy=TAXONOMY_LIST,
                )
                suggest_raw = call_haiku(client, suggest_prompt, content)
                suggest_result = parse_json_response(suggest_raw)
                suggested = suggest_result.get("suggested_tags", [])
                reason = suggest_result.get("reason", "")

                if suggested:
                    entry = {
                        "doc_id": doc_id,
                        "title": title,
                        "author": author,
                        "assigned_tags": valid_tags,
                        "suggested_tags": suggested,
                        "reason": reason,
                    }
                    with open(suggestions_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry) + "\n")
                    stats["suggestions"] += 1
                    print("         SUGGEST: {} — {}".format(suggested, reason[:80]))
            except Exception as e:
                print("         SUGGEST FAILED: {}".format(e))

    conn.close()

    # Summary
    print("\n{}".format("=" * 64))
    print("SUMMARY")
    print("{}".format("=" * 64))
    print("  Total processed: {}".format(stats["updated"] + stats["skipped"] + stats["failed"]))
    print("  Updated:         {}".format(stats["updated"]))
    print("  Skipped:         {}".format(stats["skipped"]))
    print("  Failed:          {}".format(stats["failed"]))
    if args.suggest_tags:
        print("  Suggestions:     {}".format(stats["suggestions"]))
        if stats["suggestions"] > 0:
            print("  Suggestions file: {}".format(suggestions_path))

    if failed_docs:
        print("\nFailed documents:")
        for f in failed_docs:
            print("  - {}".format(f))


if __name__ == "__main__":
    main()
