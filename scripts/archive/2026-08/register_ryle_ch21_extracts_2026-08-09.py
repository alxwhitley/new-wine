#!/usr/bin/env python3
"""
register_ryle_ch21_extracts_2026-08-09.py — one-off: add two hidden sources
for the two credited extracts inside J.C. Ryle's "Holiness: Its Nature,
Hindrances, Difficulties, and Roots", Ch. XXI ("Extracts from Old Writers").

Ryle's Ch. XXI reproduces two 17th-century Puritan sermons under their own
named authors, each with an explicit head credit and closing citation:
  (I.)  Robert Trail  (also spelled "Traill") — sanctification sermon
  (2.)  Thomas Brooks                          — necessity-of-holiness sermon

This script does NOT touch the source Ryle document (3f05746a-c848-4ecc-
9cea-6e1b1559a5dd), its chunks, or its propositions. It only:
  1. Creates two new `sources` rows (public_domain, visibility='hidden' —
     fail-closed, not to be flipped to 'shown' without Alex's review).
  2. Creates one `documents` row under each, containing exactly that
     writer's extracted text (head credit through closing cite).
  3. Runs both through shared_ingest.ingest_document() — the standard
     chokepoint — so chunks/embeddings/propositions are generated the
     normal way, not hand-rolled.

The extracted text is reconstructed from the live `chunks` table (chunk_index
569-581 of the Ryle document; documents.full_text is NULL for this doc), with
the chunker's own 80-token sliding-window overlap between consecutive chunks
resolved by longest-common-suffix/prefix merge (chunk_text() in
backend/app/services/chunker.py) — NOT a raw newline join, which would
duplicate ~80 tokens of text at every one of the 12 chunk boundaries in this
span. The merged, deduplicated text is then split at the two documented head
credits / closing cites. See docs/audits/ for the read-only survey this was
built from.

Idempotent. Safe to re-run (get_or_create_source / ensure_alias skip existing
rows; ingest_document() dedupes on url/source_name+filename).
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(ROOT / "scripts"))
from source_resolver import normalize_alias_key, SENTINEL_SOURCE_ID  # noqa: E402
from bible_refs import extract_bible_references  # noqa: E402
import shared_ingest  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]

_parsed = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed.hostname,
    "port": _parsed.port or 5432,
    "user": unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname": _parsed.path.lstrip("/"),
}

db = create_client(SUPABASE_URL, SUPABASE_KEY)

RYLE_DOC_ID = "3f05746a-c848-4ecc-9cea-6e1b1559a5dd"
CHUNK_START = 569
CHUNK_END = 581

TRAIL_HEAD = "(I.) Reverend Robert Trail, sometime Minister of Cranbrook, Kent. 1696."
BROOKS_HEAD = "(2.) Rev. Thomas Brooks, Rector of St. Margaret, Fish Street Hill, London. 1662."


# ── Chunk reconstruction ────────────────────────────────────────────────────

def fetch_span_chunks(conn, doc_id, start, end):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_index, content FROM chunks "
            "WHERE document_id = %s AND chunk_index BETWEEN %s AND %s "
            "ORDER BY chunk_index",
            (doc_id, start, end),
        )
        rows = cur.fetchall()
    expected = end - start + 1
    if len(rows) != expected:
        raise RuntimeError(
            f"expected {expected} chunks ({start}-{end}), got {len(rows)}"
        )
    return rows


def find_overlap(a: str, b: str, min_len: int = 20, max_len: int = 1200) -> int:
    """Largest suffix of a that is also a prefix of b (the chunker's own
    80-token sliding-window overlap between consecutive chunks)."""
    max_check = min(len(a), len(b), max_len)
    for length in range(max_check, min_len - 1, -1):
        if a[-length:] == b[:length]:
            return length
    return 0


def merge_chunks(rows) -> str:
    merged = rows[0][1]
    for idx, content in rows[1:]:
        ov = find_overlap(merged, content)
        if ov == 0:
            raise RuntimeError(f"no overlap found merging into chunk {idx} — refusing to guess a join point")
        merged += content[ov:]
    return merged


def split_extracts(merged: str):
    assert merged.count(TRAIL_HEAD) == 1, f"TRAIL_HEAD appears {merged.count(TRAIL_HEAD)} times"
    assert merged.count(BROOKS_HEAD) == 1, f"BROOKS_HEAD appears {merged.count(BROOKS_HEAD)} times"
    trail_start = merged.index(TRAIL_HEAD)
    brooks_start = merged.index(BROOKS_HEAD)
    assert trail_start < brooks_start
    trail_text = merged[trail_start:brooks_start].strip()
    brooks_text = merged[brooks_start:].strip()
    return trail_text, brooks_text


# ── Source registration (same pattern as register_jesus_image.py) ─────────

def get_or_create_source(conn, name: str, notes: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return str(row[0]), False
        cur.execute(
            """
            INSERT INTO sources (name, license_status, visibility, notes)
            VALUES (%s, 'public_domain', 'hidden', %s)
            RETURNING id
            """,
            (name, notes),
        )
        source_id = str(cur.fetchone()[0])
        conn.commit()
        return source_id, True


def ensure_alias(conn, alias_key: str, alias_display: str, source_id: str, note: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT source_id FROM source_aliases WHERE alias_key = %s", (alias_key,))
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO source_aliases (alias_key, alias_display, source_id, note)
            VALUES (%s, %s, %s, %s)
            """,
            (alias_key, alias_display, source_id, note),
        )
        conn.commit()
        return True


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False

    print(f"Fetching chunks {CHUNK_START}-{CHUNK_END} of Ryle document {RYLE_DOC_ID}...")
    rows = fetch_span_chunks(conn, RYLE_DOC_ID, CHUNK_START, CHUNK_END)
    merged = merge_chunks(rows)
    print(f"  merged span length: {len(merged)} chars (from {len(rows)} chunks, overlap-deduped)")

    trail_text, brooks_text = split_extracts(merged)
    print(f"  Trail extract:  {len(trail_text)} chars, {len(trail_text.split())} words")
    print(f"  Brooks extract: {len(brooks_text)} chars, {len(brooks_text.split())} words")

    notes_common = (
        "One-off source: 17th-century Puritan minister. Not part of the "
        "charismatic/Pentecostal teacher set — classic devotional/reference "
        "material. Text is a credited extract reproduced inside J.C. Ryle's "
        "'Holiness: Its Nature, Hindrances, Difficulties, and Roots', Ch. XXI "
        "('Extracts from Old Writers'), document_id={}, chunks {}-{}. "
        "Registered via register_ryle_ch21_extracts_2026-08-09.py. "
        "visibility='hidden' deliberately — not reviewed for serving yet."
    ).format(RYLE_DOC_ID, CHUNK_START, CHUNK_END)

    # ── Robert Trail source + aliases ──
    print("\nRobert Trail source...")
    trail_source_id, trail_created = get_or_create_source(conn, "Robert Trail", notes_common)
    print(f"  source [{'CREATED' if trail_created else 'EXISTS'}]: {trail_source_id}")
    for display, note in [
        ("Robert Trail", "canonical name (as headed in Ryle's text)"),
        ("Robert Traill", "alternate spelling used in the same text's closing citation"),
    ]:
        key = normalize_alias_key(display)
        created = ensure_alias(conn, key, display, trail_source_id, note)
        print(f"  alias [{'CREATED' if created else 'EXISTS'}]: {key!r}")

    # ── Thomas Brooks source + alias ──
    print("\nThomas Brooks source...")
    brooks_source_id, brooks_created = get_or_create_source(conn, "Thomas Brooks", notes_common)
    print(f"  source [{'CREATED' if brooks_created else 'EXISTS'}]: {brooks_source_id}")
    key = normalize_alias_key("Thomas Brooks")
    created = ensure_alias(conn, key, "Thomas Brooks", brooks_source_id, "canonical name")
    print(f"  alias [{'CREATED' if created else 'EXISTS'}]: {key!r}")

    conn.close()

    for label, sid in [("Trail", trail_source_id), ("Brooks", brooks_source_id)]:
        if sid == SENTINEL_SOURCE_ID:
            print(f"CRITICAL: {label} source_id == SENTINEL_SOURCE_ID — aborting.")
            sys.exit(1)

    # ── Documents, via the shared ingest chokepoint ──
    print("\nExtracting Bible references (Groq)...")
    trail_refs = extract_bible_references(trail_text)
    print(f"  Trail: {len(trail_refs)} reference(s)")
    brooks_refs = extract_bible_references(brooks_text)
    print(f"  Brooks: {len(brooks_refs)} reference(s)")

    print("\n── Ingesting Trail document ──")
    trail_result = shared_ingest.ingest_document(
        db=db,
        db_params=DB_PARAMS,
        title="Concerning Sanctification",
        body_text=trail_text,
        filename="ryle_holiness_ch21_trail_extract.txt",
        author="Robert Trail",
        year=1696,
        source_name="Robert Trail",
        source_type="sermon",
        source_kind="sermon_transcript",
        citation_mode="citable",
        is_copyrighted=False,
        topic_tags=["Holiness", "Sanctification"],
        bible_references=trail_refs,
        source_id=trail_source_id,
        file_path="one-off/ryle_holiness_ch21_trail_extract.txt",
    )
    print(f"Trail result: {trail_result['status']} / {trail_result['reason']}")
    print(f"  doc_id: {trail_result['doc_id']}")
    print(f"  chunks: {len(trail_result['chunks'])}")
    print(f"  propositions: {trail_result['propositions']}")

    print("\n── Ingesting Brooks document ──")
    brooks_result = shared_ingest.ingest_document(
        db=db,
        db_params=DB_PARAMS,
        title="The Necessity of Holiness",
        body_text=brooks_text,
        filename="ryle_holiness_ch21_brooks_extract.txt",
        author="Thomas Brooks",
        year=1662,
        source_name="Thomas Brooks",
        source_type="sermon",
        source_kind="sermon_transcript",
        citation_mode="citable",
        is_copyrighted=False,
        topic_tags=["Holiness", "Sanctification"],
        bible_references=brooks_refs,
        source_id=brooks_source_id,
        file_path="one-off/ryle_holiness_ch21_brooks_extract.txt",
    )
    print(f"Brooks result: {brooks_result['status']} / {brooks_result['reason']}")
    print(f"  doc_id: {brooks_result['doc_id']}")
    print(f"  chunks: {len(brooks_result['chunks'])}")
    print(f"  propositions: {brooks_result['propositions']}")

    summary = {
        "trail_source_id": trail_source_id,
        "trail_doc_id": trail_result["doc_id"],
        "trail_status": trail_result["status"],
        "trail_propositions": trail_result["propositions"],
        "brooks_source_id": brooks_source_id,
        "brooks_doc_id": brooks_result["doc_id"],
        "brooks_status": brooks_result["status"],
        "brooks_propositions": brooks_result["propositions"],
    }
    print("\n── Summary ──")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
