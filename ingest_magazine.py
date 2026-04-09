#!/usr/bin/env python3
"""
Magazine Ingestion Script

Reads approved .md articles from pipeline/03_approved/{issue_stem}/,
parses frontmatter metadata, chunks body text, and inserts into
Supabase documents + chunks tables.

After successful ingestion, moves the issue folder to pipeline/04_ingested/.
"""

import os
import re
import sys
import shutil
import logging
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "backend" / "app" / ".env")

# Add backend to path so chunker/embeddings resolve
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from supabase import create_client
from app.services.embeddings import embed_text
from app.services.chunker import chunk_text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent
APPROVED_DIR = ROOT / "pipeline" / "03_approved"
INGESTED_DIR = ROOT / "pipeline" / "04_ingested"
TRACKER_PATH = ROOT / "pipeline" / "rhemata_tracker.xlsx"

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

    # Insert document
    doc_data = {
        "title": title,
        "author": author or None,
        "source_name": "New Wine Magazine",
        "source_type": "magazine_article",
        "source_kind": "magazine_article",
        "citation_mode": "citable",
        "is_copyrighted": True,
        "issue": issue or None,
        "year": year,
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


if __name__ == "__main__":
    run()
