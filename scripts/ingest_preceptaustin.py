#!/usr/bin/env python3
"""
Rhemata Precept Austin Word Study Ingestion Script

Reads extracted word study .txt files from sources/precept_austin/raw/,
chunks with tiktoken, embeds with OpenAI, and inserts into Supabase.
Chunk inserts use psycopg2 direct connection for reliability.
"""

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import openai
import psycopg2
from psycopg2.extras import execute_values
from supabase import create_client
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.services.chunker import chunk_text, token_len

# ── Config ────────────────────────────────────────────────────────────────────

# Language flag: --language hebrew|greek (default: greek)
_lang = "greek"
for _i, _a in enumerate(sys.argv[1:], 1):
    if _a == "--language" and _i < len(sys.argv) - 1:
        _lang = sys.argv[_i + 1].lower()

LANG_SUBDIRS = {"greek": "precept_austin", "hebrew": "precept_austin_hebrew"}
if _lang not in LANG_SUBDIRS:
    print("ERROR: --language must be 'greek' or 'hebrew'")
    sys.exit(1)

SOURCES_DIR = PROJECT_ROOT / "sources" / LANG_SUBDIRS[_lang]
RAW_DIR = SOURCES_DIR / "raw"
INDEX_FILE = SOURCES_DIR / "index.json"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBED_BATCH_SIZE = 100

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    print("Set it to your Supabase direct connection string, e.g.:")
    print("  SUPABASE_DB_URL=postgresql://user:password@host:5432/dbname")
    sys.exit(1)

from urllib.parse import urlparse, unquote
_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_index():
    # type: () -> Dict[str, Dict[str, str]]
    """Load index.json and return a dict keyed by strongs_number."""
    if not INDEX_FILE.exists():
        print("ERROR: index.json not found. Run scrape_preceptaustin.py first.")
        sys.exit(1)
    with open(INDEX_FILE) as f:
        entries = json.load(f)
    return {e["strongs_number"]: e for e in entries}


def embed_batch(texts):
    # type: (List[str]) -> List[List[float]]
    """Embed a batch of texts using OpenAI."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )
    return [item.embedding for item in response.data]


def insert_chunks_psycopg2(rows):
    # type: (List[Tuple]) -> int
    """Insert all chunks for a document via psycopg2 direct connection.
    Each row is (id, document_id, content, embedding, chunk_index).
    Returns number of rows inserted."""
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO chunks (id, document_id, content, embedding, chunk_index) VALUES %s",
                rows,
                template="(%s, %s, %s, %s::vector, %s)",
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def ingest_file(filepath, index_lookup):
    # type: (Path, Dict[str, Dict[str, str]]) -> bool
    """Ingest a single word study .txt file into Supabase."""
    filename = filepath.stem  # e.g. G1459_egkataleipo
    parts = filename.split("_", 1)
    if len(parts) != 2:
        print("  SKIP {}: unexpected filename format".format(filename))
        return False

    strongs_number = parts[0]
    transliteration = parts[1]

    # Look up english_word from index
    index_entry = index_lookup.get(strongs_number)
    english_word = index_entry["english_word"] if index_entry else transliteration

    title = "Word Study: {} ({}, {})".format(english_word, transliteration, strongs_number)

    # Check if excerpt already exists for this word study
    doc_result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    if doc_result.data:
        doc_id_existing = doc_result.data[0]["id"]
        excerpt_result = (
            supabase.table("excerpts")
            .select("id")
            .eq("document_id", doc_id_existing)
            .eq("excerpt_type", "word_study_article")
            .limit(1)
            .execute()
        )
        if excerpt_result.data:
            print("  SKIP {}: excerpt already exists".format(strongs_number))
            return False

    content = filepath.read_text(encoding="utf-8").strip()
    if not content:
        print("  SKIP {}: empty file".format(strongs_number))
        return False

    # Chunk the content
    chunks = chunk_text(content, chunk_target=550, overlap=80)
    if not chunks:
        print("  SKIP {}: no chunks produced".format(strongs_number))
        return False

    # Reuse existing document or create new one
    if doc_result.data:
        doc_id = doc_result.data[0]["id"]
        print("  Reusing existing document {}".format(doc_id[:12]))
    else:
        doc_id = str(uuid.uuid4())
        supabase.table("documents").insert({
            "id": doc_id,
            "title": title,
            "author": "Precept Austin",
            "source_name": "Precept Austin",
            "source_type": "background",
            "source_kind": "word_study",
            "citation_mode": "silent_context",
            "is_copyrighted": True,
            "topic_tags": [],
            "bible_references": [],
        }).execute()

    # Embed all chunks
    all_embeddings = []  # type: List[List[float]]
    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch_end = min(batch_start + EMBED_BATCH_SIZE, len(chunks))
        batch = chunks[batch_start:batch_end]
        all_embeddings.extend(embed_batch(batch))

    # Build rows for psycopg2 insert
    rows = []  # type: List[Tuple]
    for chunk_index, (text, embedding) in enumerate(zip(chunks, all_embeddings)):
        embedding_str = "[{}]".format(",".join(str(v) for v in embedding))
        rows.append((
            str(uuid.uuid4()),
            doc_id,
            text,
            embedding_str,
            chunk_index,
        ))

    # Insert all chunks in a single call
    inserted = insert_chunks_psycopg2(rows)

    print("  OK {} ({}): {} chunks, {} inserted".format(
        strongs_number, english_word, len(chunks), inserted
    ))
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Rhemata Precept Austin Word Study Ingestion ({})".format(_lang))
    print("=" * 60)
    print("Source dir: {}".format(SOURCES_DIR))

    index_lookup = load_index()
    print("Loaded {} entries from index.json".format(len(index_lookup)))

    txt_files = sorted(RAW_DIR.glob("*.txt"))
    if not txt_files:
        print("No .txt files found in {}".format(RAW_DIR))
        return

    print("Found {} word study files to ingest\n".format(len(txt_files)))

    success = 0
    skipped = 0

    for i, filepath in enumerate(txt_files):
        if ingest_file(filepath, index_lookup):
            success += 1
        else:
            skipped += 1

        if (i + 1) % 10 == 0:
            print("\n  Progress: {}/{} processed ({} ingested, {} skipped)\n".format(
                i + 1, len(txt_files), success, skipped
            ))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("  Total files: {}".format(len(txt_files)))
    print("  Ingested: {}".format(success))
    print("  Skipped: {}".format(skipped))
    print("=" * 60)


if __name__ == "__main__":
    main()
