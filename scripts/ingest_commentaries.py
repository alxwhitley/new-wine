#!/usr/bin/env python3
"""
Rhemata HistoricalChristianFaith Commentaries Ingestion Script

Reads commentary rows from a SQLite database, groups by father_name,
creates one document per father, chunks with tiktoken, embeds with OpenAI,
and inserts into Supabase via psycopg2.

Usage:
  python3 scripts/ingest_commentaries.py
  python3 scripts/ingest_commentaries.py --dry-run
  python3 scripts/ingest_commentaries.py --father "Augustine of Hippo"
  python3 scripts/ingest_commentaries.py --filter-charismatic
"""

import os
import sys
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, unquote

import openai
import psycopg2
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.services.chunker import chunk_text

# ── Config ────────────────────────────────────────────────────────────────────

SQLITE_PATH = Path("/tmp/commentaries-db/data.out")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBED_BATCH_SIZE = 100
CHUNK_INSERT_SLEEP = 0.5

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ── Theological Tagging ───────────────────────────────────────────────────────

REFORMED = {"John Calvin", "Martin Luther", "Ulrich Zwingli", "John Wesley", "CS Lewis", "GK Chesterton", "Douglas Wilson"}
CESSATIONIST = {"John Calvin", "Martin Luther", "Ulrich Zwingli", "Douglas Wilson"}
CHARISMATIC_FRIENDLY = {
    "Symeon the New Theologian", "Gregory Palamas", "Macarius of Egypt",
    "Isaac of Nineveh", "John of Dalyatha", "Diadochos of Photiki",
    "Evagrius Ponticus", "Desert Fathers", "Abba Poemen", "Ammonas of Egypt",
    "Anthony the Great", "John Cassian",
}
DESERT_FATHERS = {
    "Desert Fathers", "Abba Poemen", "Ammonas of Egypt", "Anthony the Great",
    "Macarius of Egypt", "Syncletica of Alexandria", "Isaiah the Solitary",
    "John of Karpathos", "Nilus of Sinai", "Dorotheos of Gaza", "Pachomius the Great",
}


def assign_tags(father_name, ts):
    # type: (str, Optional[int]) -> List[str]
    """Assign topic_tags based on father_name and year."""
    tags = []  # type: List[str]
    if father_name in REFORMED:
        tags.append("Reformed")
    if father_name in CESSATIONIST:
        tags.append("Cessationist")
    if father_name in CHARISMATIC_FRIENDLY:
        tags.append("Charismatic-Friendly")
    if father_name in DESERT_FATHERS:
        tags.append("Desert Fathers")
    # Patristic: ts < 800, not already tagged
    if ts is not None and ts < 800 and not tags:
        tags.append("Patristic")
    return tags


# ── Helpers ───────────────────────────────────────────────────────────────────

def embed_batch(texts):
    # type: (List[str]) -> List[List[float]]
    """Embed a batch of texts using OpenAI."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )
    return [item.embedding for item in response.data]


def check_existing_doc(title):
    # type: (str) -> Optional[str]
    """Check if document exists and has chunks. Returns:
    - None if document doesn't exist (proceed with ingestion)
    - "skip" if document exists with chunks (skip)
    - None after deleting empty document (proceed with ingestion)
    """
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE title = %s LIMIT 1", (title,))
            row = cur.fetchone()
            if row is None:
                return None  # doesn't exist, proceed

            doc_id = row[0]
            cur.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (doc_id,))
            chunk_count = cur.fetchone()[0]

            if chunk_count > 0:
                return "skip"

            # Document exists but has 0 chunks — delete and re-ingest
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
            conn.commit()
            return None  # proceed with ingestion
    finally:
        conn.close()


def insert_document(doc):
    # type: (Dict) -> None
    """Insert a document row via psycopg2."""
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO documents (id, title, author, source_name, source_type, source_kind,
                   is_copyrighted, citation_mode, topic_tags, bible_references, year)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    doc["id"], doc["title"], doc["author"], doc["source_name"],
                    doc["source_type"], doc["source_kind"], doc["is_copyrighted"],
                    doc["citation_mode"], doc["topic_tags"], [], doc.get("year"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def insert_single_chunk(row):
    # type: (Tuple) -> bool
    """Insert a single chunk via psycopg2. Opens and closes connection per insert."""
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chunks (id, document_id, content, embedding, chunk_index) "
                "VALUES (%s, %s, %s, %s::vector, %s)",
                row,
            )
        conn.commit()
        return True
    except Exception as e:
        print("    CHUNK INSERT ERROR: {}".format(e))
        return False
    finally:
        conn.close()


def format_row(row):
    # type: (Tuple) -> str
    """Format a commentary row into text content."""
    # row: (book, location_start, location_end, txt, source_title)
    book, loc_start, loc_end, txt, source_title = row
    if not txt or not txt.strip():
        return ""

    location = "{} {}-{}".format(book, loc_start, loc_end) if loc_start != loc_end else "{} {}".format(book, loc_start)

    if source_title and source_title.strip():
        return "{} ({}): {}".format(source_title.strip(), location, txt.strip())
    else:
        return "({}): {}".format(location, txt.strip())


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Parse CLI flags
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    filter_charismatic = "--filter-charismatic" in args
    father_filter = None  # type: Optional[str]
    for i, a in enumerate(args):
        if a == "--father" and i + 1 < len(args):
            father_filter = args[i + 1]

    print("Rhemata Commentary Ingestion")
    print("=" * 60)
    if dry_run:
        print("DRY RUN — no data will be inserted")
    if filter_charismatic:
        print("FILTER: Charismatic-Friendly and Desert Fathers only")
    if father_filter:
        print("FILTER: Single father — '{}'".format(father_filter))
    print()

    # Load SQLite data
    if not SQLITE_PATH.exists():
        print("ERROR: SQLite database not found at {}".format(SQLITE_PATH))
        sys.exit(1)

    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_cur = sqlite_conn.cursor()

    # Get all unique fathers with their min ts
    sqlite_cur.execute(
        "SELECT father_name, min(ts), count(*) FROM commentary GROUP BY father_name ORDER BY father_name"
    )
    fathers = sqlite_cur.fetchall()
    print("Total fathers in database: {}".format(len(fathers)))

    # Apply filters
    filtered = []  # type: List[Tuple]
    for father_name, min_ts, row_count in fathers:
        if father_filter and father_name != father_filter:
            continue
        tags = assign_tags(father_name, min_ts)
        if filter_charismatic:
            if "Charismatic-Friendly" not in tags and "Desert Fathers" not in tags:
                continue
        filtered.append((father_name, min_ts, row_count, tags))

    print("Fathers to process: {}\n".format(len(filtered)))

    if dry_run:
        print("{:<40} {:>6} {:>6}  {}".format("Father", "Rows", "Year", "Tags"))
        print("-" * 80)
        for father_name, min_ts, row_count, tags in filtered:
            print("{:<40} {:>6} {:>6}  {}".format(
                father_name[:40], row_count, min_ts or "?", ", ".join(tags) or "(none)"
            ))
        print("\n" + "=" * 60)
        print("DRY RUN COMPLETE — {} fathers, {} total rows".format(
            len(filtered), sum(r[2] for r in filtered)
        ))
        sqlite_conn.close()
        return

    # Ingest each father
    success = 0
    skipped = 0
    total_chunks = 0

    for idx, (father_name, min_ts, row_count, tags) in enumerate(filtered):
        title = father_name

        # Skip if exists with chunks
        status = check_existing_doc(title)
        if status == "skip":
            print("  SKIP '{}': document with chunks already exists".format(father_name))
            skipped += 1
            continue

        # Fetch all rows for this father
        sqlite_cur.execute(
            "SELECT book, location_start, location_end, txt, source_title "
            "FROM commentary WHERE father_name = ? ORDER BY book, location_start",
            (father_name,),
        )
        rows = sqlite_cur.fetchall()

        # Format and concatenate
        parts = []  # type: List[str]
        for row in rows:
            formatted = format_row(row)
            if formatted:
                parts.append(formatted)

        if not parts:
            print("  SKIP '{}': no content".format(father_name))
            skipped += 1
            continue

        body = "\n\n".join(parts)

        # Chunk
        chunks = chunk_text(body, chunk_target=550, overlap=80)
        if not chunks:
            print("  SKIP '{}': no chunks produced".format(father_name))
            skipped += 1
            continue

        # Create document
        doc_id = str(uuid.uuid4())
        insert_document({
            "id": doc_id,
            "title": title,
            "author": father_name,
            "source_name": "HistoricalChristianFaith Commentaries Database",
            "source_type": "commentary",
            "source_kind": "commentary",
            "is_copyrighted": False,
            "citation_mode": "citable",
            "topic_tags": tags,
            "year": min_ts,
        })

        # Embed and insert chunks in batches
        all_embeddings = []  # type: List[List[float]]
        for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch_end = min(batch_start + EMBED_BATCH_SIZE, len(chunks))
            batch = chunks[batch_start:batch_end]
            all_embeddings.extend(embed_batch(batch))

        chunk_rows = []  # type: List[Tuple]
        for chunk_index, (text, embedding) in enumerate(zip(chunks, all_embeddings)):
            embedding_str = "[{}]".format(",".join(str(v) for v in embedding))
            chunk_rows.append((
                str(uuid.uuid4()),
                doc_id,
                text,
                embedding_str,
                chunk_index,
            ))

        # Insert one chunk at a time with sleep between
        inserted = 0
        for chunk_row in chunk_rows:
            if insert_single_chunk(chunk_row):
                inserted += 1
            time.sleep(CHUNK_INSERT_SLEEP)

        total_chunks += inserted
        success += 1
        print("  OK '{}': {} rows -> {} chunks inserted [{}]".format(
            father_name, row_count, inserted, ", ".join(tags) or "no tags"
        ))

        # Progress
        if (idx + 1) % 10 == 0:
            print("\n  Progress: {}/{} processed ({} ingested, {} skipped, {} chunks total)\n".format(
                idx + 1, len(filtered), success, skipped, total_chunks
            ))

    sqlite_conn.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("  Total fathers: {}".format(len(filtered)))
    print("  Ingested: {}".format(success))
    print("  Skipped: {}".format(skipped))
    print("  Total chunks: {}".format(total_chunks))
    print("=" * 60)


if __name__ == "__main__":
    main()
