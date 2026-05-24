#!/usr/bin/env python3
"""
Rhemata STEPBible Lexicon Ingestion Script
Parses TBESG, TBESH, and TFLSJ TSV files from sources/lexicon/,
embeds each lexical entry, and inserts into Supabase.
Supports resuming — re-run safely after a partial failure.
"""

import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import tiktoken
import openai
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / "backend" / "app" / ".env")

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
LEXICON_DIR = PROJECT_ROOT / "sources" / "lexicon"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBED_BATCH_SIZE = 100
INSERT_BATCH_SIZE = 5
INSERT_SLEEP = 2
RETRY_WAIT = 5
MAX_RETRIES = 5

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# File configs: (filename, document title)
FILE_CONFIGS = [
    (
        "TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt",
        "STEPBible Greek Lexicon (TBESG)",
    ),
    (
        "TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt",
        "STEPBible Hebrew Lexicon (TBESH)",
    ),
    (
        "TFLSJ  0-5624 - Translators Formatted full LSJ Bible lexicon - STEPBible.org CC BY.txt",
        "LSJ Greek Lexicon (TFLSJ) — Entries 0-5624",
    ),
    (
        "TFLSJ extra - Translators Formatted full LSJ Bible lexicon - STEPBible.org CC BY.txt",
        "LSJ Greek Lexicon (TFLSJ) — Extended Entries",
    ),
]

MAX_EMBED_TOKENS = 8000
_enc = tiktoken.get_encoding("cl100k_base")

STRONGS_RE = re.compile(r'^[GH]\d+$')
HTML_TAG_RE = re.compile(r'<[^>]+>')


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    cleaned = HTML_TAG_RE.sub(' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def truncate_for_embedding(text: str) -> str:
    """Truncate text to MAX_EMBED_TOKENS tokens if it exceeds the limit."""
    tokens = _enc.encode(text)
    if len(tokens) <= MAX_EMBED_TOKENS:
        return text
    truncated = _enc.decode(tokens[:MAX_EMBED_TOKENS])
    return truncated + " [truncated]"


def find_header_and_data(lines: List[str]) -> Tuple[Optional[Dict[str, int]], int]:
    """Find the TSV header row and return (column_map, data_start_line_index).
    column_map maps lowercase normalized column names to indices."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if '\t' not in stripped:
            continue
        fields = stripped.split('\t')
        first_lower = fields[0].strip().lower().rstrip('#')
        has_estrong = first_lower == 'estrong'
        has_gloss = any('gloss' in f.strip().lower() for f in fields)
        if has_estrong and has_gloss:
            col_map = {}  # type: Dict[str, int]
            for idx, f in enumerate(fields):
                name = f.strip().lower()
                if name.startswith('estrong'):
                    col_map['estrong'] = idx
                elif name == 'greek' or name == 'hebrew':
                    col_map['lemma'] = idx
                elif name == 'transliteration':
                    col_map['transliteration'] = idx
                elif name == 'gloss':
                    col_map['gloss'] = idx
                elif name == 'morph':
                    col_map['morph'] = idx
                elif idx == len(fields) - 1:
                    col_map['meaning'] = idx
            data_start = i + 1
            while data_start < len(lines):
                l = lines[data_start].strip()
                if l.startswith('===') or l == '':
                    data_start += 1
                else:
                    break
            return col_map, data_start
    return None, 0


def parse_file(filepath: Path) -> List[Dict[str, str]]:
    """Parse a STEPBible lexicon file and return list of entry dicts."""
    text = filepath.read_text(encoding='utf-8')
    lines = text.split('\n')

    col_map, data_start = find_header_and_data(lines)
    if col_map is None:
        print(f"  WARNING: Could not find header row in {filepath.name}")
        return []

    print(f"  Header columns: {col_map}")
    print(f"  Data starts at line {data_start + 1}")

    entries = []  # type: List[Dict[str, str]]
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        fields = stripped.split('\t')

        estrong_idx = col_map.get('estrong')
        gloss_idx = col_map.get('gloss')
        if estrong_idx is None or gloss_idx is None:
            continue
        if estrong_idx >= len(fields) or gloss_idx >= len(fields):
            continue

        strongs = fields[estrong_idx].strip()
        gloss = fields[gloss_idx].strip()

        if not STRONGS_RE.match(strongs) or not gloss:
            continue

        entry = {'strongs': strongs, 'gloss': gloss}

        lemma_idx = col_map.get('lemma')
        if lemma_idx is not None and lemma_idx < len(fields):
            entry['lemma'] = fields[lemma_idx].strip()

        translit_idx = col_map.get('transliteration')
        if translit_idx is not None and translit_idx < len(fields):
            entry['transliteration'] = fields[translit_idx].strip()

        meaning_idx = col_map.get('meaning')
        if meaning_idx is not None and meaning_idx < len(fields):
            raw_meaning_text = fields[meaning_idx].strip()
            if raw_meaning_text:
                entry['raw_meaning'] = raw_meaning_text
                entry['meaning'] = strip_html(raw_meaning_text)

        entries.append(entry)

    return entries


BOLD_RE = re.compile(r'<b>([^<]+)</b>')


def extract_bold_meanings(html_meaning: str) -> str:
    """Extract bolded sub-definitions from Abbott-Smith HTML meaning field.
    Returns a clean comma-separated string like 'a word, a saying, speech, doctrine'."""
    bolds = BOLD_RE.findall(html_meaning)
    # First bold is usually the lemma itself — skip it
    if bolds:
        bolds = bolds[1:]
    # Filter out very short or unhelpful entries
    cleaned = []
    for b in bolds:
        b = b.strip()
        if len(b) < 2 or b in ('id.', 'al.', 'cf.'):
            continue
        cleaned.append(b)
    return ', '.join(cleaned)


def format_chunk_content(entry: Dict[str, str], brief: bool = False) -> str:
    """Format a lexicon entry into chunk content text.
    If brief=True, use only gloss + extracted bold sub-meanings (no raw Abbott-Smith)."""
    strongs = entry['strongs']
    translit = entry.get('transliteration', '')
    lemma = entry.get('lemma', '')
    gloss = entry['gloss']
    meaning = entry.get('meaning', '')
    raw_meaning = entry.get('raw_meaning', '')

    parts = []
    if translit and lemma:
        parts.append(f"Strong's {strongs} ({translit} / {lemma}): {gloss}.")
    elif translit:
        parts.append(f"Strong's {strongs} ({translit}): {gloss}.")
    elif lemma:
        parts.append(f"Strong's {strongs} ({lemma}): {gloss}.")
    else:
        parts.append(f"Strong's {strongs}: {gloss}.")

    if brief and raw_meaning:
        # Extract clean sub-definitions from the HTML
        bold_meanings = extract_bold_meanings(raw_meaning)
        if bold_meanings:
            parts.append(bold_meanings)
    elif meaning:
        parts.append(meaning)

    return ' '.join(parts)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts using OpenAI."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
    )
    return [item.embedding for item in response.data]


def find_or_create_document(title: str) -> Tuple[str, int]:
    """Find existing document by title or create a new one.
    Returns (doc_id, existing_chunk_count)."""
    result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    if result.data:
        doc_id = result.data[0]["id"]
        count_result = supabase.table("chunks").select("id", count="exact").eq("document_id", doc_id).execute()
        existing = count_result.count if count_result.count is not None else 0
        return doc_id, existing

    doc_id = str(uuid.uuid4())
    supabase.table("documents").insert({
        "id": doc_id,
        "title": title,
        "author": "STEPBible / Tyndale House",
        "source_name": "STEPBible",
        "source_type": "background",
        "source_kind": "lexicon",
        "citation_mode": "silent_context",
        "is_copyrighted": False,
        "topic_tags": [],
        "bible_references": [],
    }).execute()
    return doc_id, 0


def insert_chunk_batch(rows: List[dict]) -> bool:
    """Insert a small batch of chunks via psycopg2 with ON CONFLICT DO NOTHING."""
    import psycopg2
    from psycopg2.extras import execute_values
    from urllib.parse import urlparse, unquote
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("    ERROR: SUPABASE_DB_URL not set")
        return False

    parsed = urlparse(db_url)
    db_params = {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }

    values = []
    for r in rows:
        embedding_str = "[%s]" % ",".join(str(v) for v in r["embedding"])
        values.append((r["id"], r["document_id"], r["content"], embedding_str, r["chunk_index"]))

    for attempt in range(MAX_RETRIES):
        try:
            conn = psycopg2.connect(**db_params)
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    "INSERT INTO chunks (id, document_id, content, embedding, chunk_index) "
                    "VALUES %s ON CONFLICT DO NOTHING",
                    values,
                    template="(%s, %s, %s, %s::vector, %s)",
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            if attempt < MAX_RETRIES - 1:
                print(f"    Insert failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {RETRY_WAIT}s: {e}")
                time.sleep(RETRY_WAIT)
            else:
                print(f"    Insert failed after {MAX_RETRIES} attempts, skipping batch at chunk_index {rows[0]['chunk_index']}: {e}")
                return False


def delete_document(title: str) -> None:
    """Delete a document and all its chunks by title via Supabase REST API."""
    result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    if not result.data:
        print(f"  No document found with title: {title}")
        return
    doc_id = result.data[0]["id"]

    chunk_count = supabase.table("chunks").select("id", count="exact").eq("document_id", doc_id).execute()
    total = chunk_count.count if chunk_count.count is not None else 0
    print(f"  Deleting {total} chunks for doc {doc_id[:12]}...")

    deleted = 0
    while True:
        batch = (
            supabase.table("chunks")
            .select("id")
            .eq("document_id", doc_id)
            .limit(50)
            .execute()
        )
        if not batch.data:
            break
        for row in batch.data:
            supabase.table("chunks").delete().eq("id", row["id"]).execute()
            deleted += 1
        if deleted % 500 == 0 or deleted >= total:
            print(f"    Deleted {deleted}/{total} chunks...")
        time.sleep(0.2)
    print(f"  Chunks deleted.")

    supabase.table("documents").delete().eq("id", doc_id).execute()
    print(f"  Deleted document {doc_id[:12]}... ({title})")


def ingest_file(filename: str, title: str, max_entries: Optional[int] = None, brief: bool = False) -> Dict[str, int]:
    """Ingest a single lexicon file. Returns stats dict.
    If brief=True, store only gloss + extracted bold sub-meanings (for TBESG)."""
    filepath = LEXICON_DIR / filename
    stats = {"parsed": 0, "inserted": 0, "skipped": 0}

    if not filepath.exists():
        print(f"\n  WARNING: File not found, skipping: {filename}")
        return stats

    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"  Title: {title}")
    if brief:
        print("  Mode: BRIEF (gloss + bold sub-meanings only)")
    print('='*60)

    entries = parse_file(filepath)
    if max_entries is not None:
        entries = entries[:max_entries]
    stats["parsed"] = len(entries)

    if not entries:
        print("  No entries parsed — skipping")
        return stats

    print(f"  {len(entries)} entries parsed")

    # Find existing document or create new one; check how many chunks already exist
    doc_id, existing_chunks = find_or_create_document(title)
    print(f"  Document ID: {doc_id}")

    # Format all chunk content
    chunk_texts = []  # type: List[str]
    for entry in entries:
        chunk_texts.append(format_chunk_content(entry, brief=brief))

    # Resume: skip entries that are already inserted
    start_from = existing_chunks
    if start_from > 0:
        if start_from >= len(chunk_texts):
            print(f"  All {len(chunk_texts)} entries already inserted — skipping")
            stats["inserted"] = len(chunk_texts)
            return stats
        print(f"  Resuming from entry {start_from} ({existing_chunks} already inserted)")

    remaining = chunk_texts[start_from:]

    # Embed in batches, insert in small sub-batches
    chunk_index = start_from
    total_inserted = existing_chunks
    for batch_start in range(0, len(remaining), EMBED_BATCH_SIZE):
        batch_end = min(batch_start + EMBED_BATCH_SIZE, len(remaining))
        batch = remaining[batch_start:batch_end]

        batch = [truncate_for_embedding(t) for t in batch]
        embeddings = embed_batch(batch)

        rows = []
        for text, embedding in zip(batch, embeddings):
            rows.append({
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "content": text,
                "embedding": embedding,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

        # Insert in small sub-batches
        for sub_start in range(0, len(rows), INSERT_BATCH_SIZE):
            sub_batch = rows[sub_start:sub_start + INSERT_BATCH_SIZE]
            if insert_chunk_batch(sub_batch):
                total_inserted += len(sub_batch)
            else:
                stats["skipped"] += len(sub_batch)
            if total_inserted % 500 == 0 and total_inserted > existing_chunks:
                print(f"  Progress: {total_inserted}/{len(chunk_texts)} entries inserted")
            time.sleep(INSERT_SLEEP)

    stats["inserted"] = total_inserted
    stats["skipped"] += stats["parsed"] - total_inserted
    print(f"  Done: {total_inserted} inserted, {stats['skipped']} skipped")
    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def print_resume_status():
    """Print current chunk counts in Supabase for each lexicon document."""
    print("\nCurrent Supabase chunk counts:")
    for _, title in FILE_CONFIGS:
        result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
        if result.data:
            doc_id = result.data[0]["id"]
            count_result = supabase.table("chunks").select("id", count="exact").eq("document_id", doc_id).execute()
            count = count_result.count if count_result.count is not None else 0
            print(f"  {title}: {count} chunks (doc {doc_id[:8]}...)")
        else:
            print(f"  {title}: not yet created")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Rhemata STEPBible Lexicon Ingestion")
    parser.add_argument("--test", action="store_true", help="Limit to 50 entries per file")
    parser.add_argument("--lexicon", type=str, default=None,
                        help="Run a single lexicon: TBESG, TBESH, or TFLSJ")
    parser.add_argument("--delete", action="store_true",
                        help="Delete existing document + chunks before ingesting")
    parser.add_argument("--sample", type=int, default=0,
                        help="Print N sample chunks after parsing (before ingesting)")
    args = parser.parse_args()

    max_entries = 50 if args.test else None

    # Map --lexicon shorthand to FILE_CONFIGS entries
    LEXICON_MAP = {
        "TBESG": [FILE_CONFIGS[0]],
        "TBESH": [FILE_CONFIGS[1]],
        "TFLSJ": [FILE_CONFIGS[2], FILE_CONFIGS[3]],
    }

    if args.lexicon:
        key = args.lexicon.upper()
        if key not in LEXICON_MAP:
            print(f"Unknown lexicon: {args.lexicon}. Choose from: {', '.join(LEXICON_MAP.keys())}")
            sys.exit(1)
        configs = LEXICON_MAP[key]
        print(f"Single lexicon mode: {key}")
    else:
        configs = FILE_CONFIGS

    print("Rhemata STEPBible Lexicon Ingestion")
    if args.test:
        print("TEST MODE: limited to 50 entries per file")
    print("="*60)

    print_resume_status()

    total_stats = {"parsed": 0, "inserted": 0, "skipped": 0}

    for filename, title in configs:
        brief = "TBESG" in title

        if args.delete:
            print(f"\nDeleting existing data for: {title}")
            delete_document(title)

        if args.sample > 0:
            # Parse and print samples, then continue to ingest
            filepath = LEXICON_DIR / filename
            entries = parse_file(filepath)
            if max_entries is not None:
                entries = entries[:max_entries]
            print(f"\n  Sample chunks ({args.sample}):")
            for i, entry in enumerate(entries[:args.sample]):
                chunk = format_chunk_content(entry, brief=brief)
                print(f"  [{i}] {chunk[:200]}")
            print()

        stats = ingest_file(filename, title, max_entries=max_entries, brief=brief)
        for k in total_stats:
            total_stats[k] += stats[k]

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"  Total parsed:   {total_stats['parsed']}")
    print(f"  Total inserted: {total_stats['inserted']}")
    print(f"  Total skipped:  {total_stats['skipped']}")
    print('='*60)


if __name__ == "__main__":
    main()
