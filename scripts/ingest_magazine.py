#!/usr/bin/env python3
"""
Magazine Ingestion Script

Reads approved .md articles from sources/magazine/03_approved/{issue_stem}/,
parses frontmatter metadata, chunks body text, and inserts into
Supabase documents + chunks tables.

After successful ingestion, moves the issue folder to sources/magazine/04_ingested/.
"""

import os
import re
import sys
import shutil
import logging
import psycopg2
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

# Add backend to path so chunker/embeddings resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from supabase import create_client
from app.services.embeddings import embed_text
from app.services.chunker import chunk_text
from bible_refs import extract_bible_references
from source_resolver import (
    resolve_source_id,
    SENTINEL_SOURCE_ID,
    NEW_WINE_MAGAZINE_SOURCE_ID,
    print_resolution_table,
)
import propositions

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_parsed_db = urlparse(os.environ.get("SUPABASE_DB_URL", ""))
DB_PARAMS = {
    "host":     _parsed_db.hostname,
    "port":     _parsed_db.port or 5432,
    "user":     unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname":   (_parsed_db.path or "").lstrip("/"),
}

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
APPROVED_DIR = ROOT / "sources" / "magazine" / "03_approved"
INGESTED_DIR = ROOT / "sources" / "magazine" / "04_ingested"
ARCHIVED_DIR = ROOT / "sources" / "magazine" / "05_archived"
TRACKER_PATH = ROOT / "sources" / "magazine" / "rhemata_tracker.xlsx"

# -- SUPABASE ----------------------------------------------------------------

_db = None


def get_db():
    global _db
    if _db is None:
        _db = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _db


# -- FRONTMATTER PARSING -----------------------------------------------------

def parse_frontmatter(text: str) -> tuple:
    """Parse --- frontmatter --- block. Returns (metadata_dict, body_text)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    meta_block = match.group(1)
    body = match.group(2)

    meta = {}
    for line in meta_block.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()

    return meta, body


# -- INGESTION ---------------------------------------------------------------

def ingest_article(md_path: Path, issue_stem: str) -> bool:
    """Ingest a single .md article file into Supabase. Returns True on success."""
    text = md_path.read_text(encoding="utf-8")

    # Strip QA warning comments if present
    text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL)

    meta, body = parse_frontmatter(text)

    title = meta.get("TITLE", md_path.stem)
    author = meta.get("AUTHOR", "")
    issue = meta.get("ISSUE", "")
    date = meta.get("DATE", "")
    topic_tags_raw = meta.get("TOPIC_TAGS", "")
    topic_tags = [t.strip() for t in topic_tags_raw.split(",") if t.strip()] if topic_tags_raw else []
    frontmatter_refs_raw = meta.get("BIBLE_REFS", "")
    frontmatter_refs = [r.strip() for r in frontmatter_refs_raw.split(",") if r.strip()] if frontmatter_refs_raw else []

    # Clean author: truncate at parenthesis
    if "(" in author:
        author = author[:author.index("(")].rstrip()

    # Parse year from issue or date
    year = None
    year_match = re.search(r"(\d{4})", issue or date)
    if year_match:
        year = int(year_match.group(1))

    # Strip the markdown title and byline from body (already in metadata)
    body = re.sub(r"^#\s+.*?\n\*by .*?\*\s*\n*", "", body, count=1)
    body = body.strip()

    if not body or len(body) < 100:
        logger.warning("Skipping %s — body too short (%d chars)", md_path.name, len(body))
        return False

    db = get_db()

    # Extract Bible references from body (non-fatal — returns [] on failure)
    # Merge with any refs already extracted by regex during Pass 2
    bible_refs = extract_bible_references(body)
    if frontmatter_refs:
        seen = set(bible_refs)
        for r in frontmatter_refs:
            if r not in seen:
                bible_refs.append(r)
                seen.add(r)
    if bible_refs:
        print(f"  Bible refs: {len(bible_refs)} found ({', '.join(bible_refs[:5])}{'...' if len(bible_refs) > 5 else ''})")

    # Resolve source_id — New Wine Magazine is seeded in source_aliases (050).
    # Routing through resolve_source_id keeps miss-logging consistent with ingest.py.
    _resolved_id, _norm_key, _via = resolve_source_id(db, "New Wine Magazine", author or None)
    logger.info("Source resolved: key=%r id=%s via=%s", _norm_key, _resolved_id, _via)

    # Insert document
    doc_data = {
        "title": title,
        "original_title": title,
        "author": author or None,
        "source_name": "New Wine Magazine",
        "source_type": "magazine_article",
        "source_kind": "magazine_article",
        "citation_mode": "citable",
        "is_copyrighted": True,
        "issue": issue or None,
        "year": year,
        "topic_tags": topic_tags if topic_tags else None,
        "bible_references": bible_refs,
        "source_id": _resolved_id,
    }

    doc_result = db.table("documents").insert(doc_data).execute()
    if not doc_result.data:
        logger.error("Failed to insert document for %s", md_path.name)
        return False

    doc_id = doc_result.data[0]["id"]

    # Chunk and embed
    header = f"[New Wine | {date} | {title} by {author}]"
    chunks = chunk_text(body)

    for idx, chunk_content in enumerate(chunks):
        tagged = f"{header}\n\n{chunk_content}" if idx == 0 else chunk_content
        embedding = embed_text(tagged)

        chunk_data = {
            "document_id": doc_id,
            "chunk_index": idx,
            "content": f"{header}\n\n{chunk_content}",
            "embedding": embedding,
        }
        db.table("chunks").insert(chunk_data).execute()

    # Extract + store propositions (unlicensed sources only; non-fatal)
    _prop_conn = psycopg2.connect(**DB_PARAMS)
    try:
        prop_result = propositions.process_document(_prop_conn, doc_id, _resolved_id, body, embed_text)
    finally:
        _prop_conn.close()
    print(f"  propositions: {prop_result}")

    print(f"  Ingested: {title} ({len(chunks)} chunks)")
    return True


def ingest_issue(issue_dir: Path) -> Dict:
    """Ingest all .md files in an issue directory. Returns stats."""
    issue_stem = issue_dir.name
    md_files = sorted(issue_dir.glob("*.md"))

    # Skip flagged subfolder
    md_files = [f for f in md_files if "flagged" not in str(f)]

    if not md_files:
        print(f"  No .md files found in {issue_dir}")
        return {"ingested": 0, "skipped": 0}

    print(f"\nIngesting issue: {issue_stem} ({len(md_files)} articles)")

    ingested = 0
    skipped = 0

    for md_path in md_files:
        try:
            if ingest_article(md_path, issue_stem):
                ingested += 1
            else:
                skipped += 1
        except Exception as e:
            logger.exception("Failed to ingest %s", md_path.name)
            skipped += 1

    # Archive any PDF(s) in the issue folder before moving .md files to ingested
    pdf_files = sorted(issue_dir.glob("*.pdf"))
    if pdf_files:
        ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
        for pdf_path in pdf_files:
            archive_dest = ARCHIVED_DIR / pdf_path.name
            shutil.move(str(pdf_path), str(archive_dest))
            print(f"  PDF archived to: {archive_dest}")

    # Move to ingested
    INGESTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = INGESTED_DIR / issue_stem
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(issue_dir), str(dest))
    print(f"  Moved to: {dest}")

    return {"ingested": ingested, "skipped": skipped}


# -- MAIN --------------------------------------------------------------------

def run():
    """Scan 03_approved/ and ingest all issue folders."""
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)

    issue_dirs = sorted([d for d in APPROVED_DIR.iterdir() if d.is_dir()])
    if not issue_dirs:
        print(f"No issue folders found in {APPROVED_DIR}")
        return

    print(f"Found {len(issue_dirs)} issue folder(s) to ingest")

    total_ingested = 0
    total_skipped = 0

    for issue_dir in issue_dirs:
        stats = ingest_issue(issue_dir)
        total_ingested += stats["ingested"]
        total_skipped += stats["skipped"]

    print(f"\n{'='*60}")
    print(f"Done. {total_ingested} ingested, {total_skipped} skipped.")


def dry_run_sources_magazine() -> None:
    """Resolve attribution for every pending article in 03_approved/ and print
    a table.  No DB writes, no chunking, no embeddings.  The source_name is
    always 'New Wine Magazine' for this pipeline; resolution is via the
    source_aliases table so the same resolver path is exercised as ingest.py."""
    db = get_db()

    md_files = sorted(APPROVED_DIR.rglob("*.md"))
    # Mirror the ingest_issue filter — skip flagged subfolders
    md_files = [f for f in md_files if "flagged" not in str(f)]

    if not md_files:
        print(f"No .md files found under {APPROVED_DIR}")
        return

    print(f"[DRY-RUN-SOURCES] Found {len(md_files)} article(s) — resolving attribution only")

    rows = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        # Strip QA comments (mirrors ingest_article)
        text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL)
        meta, _ = parse_frontmatter(text)

        author = meta.get("AUTHOR", "") or ""
        if "(" in author:
            author = author[: author.index("(")].rstrip()

        # Magazine source_name is always fixed; still route through resolver so
        # miss-logging fires correctly for any unexpected alias gaps.
        source_name = "New Wine Magazine"
        source_id, norm_key, via = resolve_source_id(db, source_name, author or None)

        rows.append({
            "file":        md_path.name,
            "source_name": source_name,
            "author":      author or None,
            "norm_key":    norm_key,
            "source_id":   source_id,
            "via":         via,
        })

    print_resolution_table(rows, label=f"{len(md_files)} article(s) in 03_approved/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rhemata magazine ingestion")
    parser.add_argument(
        "--dry-run-sources",
        action="store_true",
        help="Resolve attribution strings and print source_id table — no DB writes, no chunking",
    )
    args = parser.parse_args()

    if args.dry_run_sources:
        dry_run_sources_magazine()
    else:
        run()
