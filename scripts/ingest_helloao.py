#!/usr/bin/env python3
"""
HelloAO Commentary Ingestion Script

Fetches commentary data from the HelloAO Bible API for three commentaries
(Matthew Henry, Adam Clarke, Jamieson-Fausset-Brown), creates one document
per book per commentary, and one chunk per verse commentary entry.

API format: https://bible.helloao.org/api/c/{commentary}/{book}/{chapter}.json

Resume-safe: checks existing documents by title before inserting.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from supabase import create_client
from app.services.embeddings import embed_text
from bible_refs import extract_bible_references
from source_resolver import resolve_source_id

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("ingest_helloao")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_DIR / "helloao_ingest.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(console_handler)

# ── Config ───────────────────────────────────────────────────────────────────

API_BASE = "https://bible.helloao.org/api/c"

COMMENTARIES = {
    "matthew-henry": {
        "slug": "matthew-henry",
        "author": "Matthew Henry",
        "source_name": "Matthew Henry's Commentary",
    },
    "adam-clarke": {
        "slug": "adam-clarke",
        "author": "Adam Clarke",
        "source_name": "Adam Clarke's Commentary",
    },
    "jamieson-fausset-brown": {
        "slug": "jamieson-fausset-brown",
        "author": "Jamieson, Fausset & Brown",
        "source_name": "Jamieson-Fausset-Brown Commentary",
    },
}

# Canonical book list: (api_id, display_name, chapter_count)
BOOKS = [
    ("GEN", "Genesis", 50), ("EXO", "Exodus", 40), ("LEV", "Leviticus", 27),
    ("NUM", "Numbers", 36), ("DEU", "Deuteronomy", 34), ("JOS", "Joshua", 24),
    ("JDG", "Judges", 21), ("RUT", "Ruth", 4), ("1SA", "1 Samuel", 31),
    ("2SA", "2 Samuel", 24), ("1KI", "1 Kings", 22), ("2KI", "2 Kings", 25),
    ("1CH", "1 Chronicles", 29), ("2CH", "2 Chronicles", 36), ("EZR", "Ezra", 10),
    ("NEH", "Nehemiah", 13), ("EST", "Esther", 10), ("JOB", "Job", 42),
    ("PSA", "Psalms", 150), ("PRO", "Proverbs", 31), ("ECC", "Ecclesiastes", 12),
    ("SNG", "Song of Solomon", 8), ("ISA", "Isaiah", 66), ("JER", "Jeremiah", 52),
    ("LAM", "Lamentations", 5), ("EZK", "Ezekiel", 48), ("DAN", "Daniel", 12),
    ("HOS", "Hosea", 14), ("JOL", "Joel", 3), ("AMO", "Amos", 9),
    ("OBA", "Obadiah", 1), ("JON", "Jonah", 4), ("MIC", "Micah", 7),
    ("NAM", "Nahum", 3), ("HAB", "Habakkuk", 3), ("ZEP", "Zephaniah", 3),
    ("HAG", "Haggai", 2), ("ZEC", "Zechariah", 14), ("MAL", "Malachi", 4),
    ("MAT", "Matthew", 28), ("MRK", "Mark", 16), ("LUK", "Luke", 24),
    ("JHN", "John", 21), ("ACT", "Acts", 28), ("ROM", "Romans", 16),
    ("1CO", "1 Corinthians", 16), ("2CO", "2 Corinthians", 13), ("GAL", "Galatians", 6),
    ("EPH", "Ephesians", 6), ("PHP", "Philippians", 4), ("COL", "Colossians", 4),
    ("1TH", "1 Thessalonians", 5), ("2TH", "2 Thessalonians", 3), ("1TI", "1 Timothy", 6),
    ("2TI", "2 Timothy", 4), ("TIT", "Titus", 3), ("PHM", "Philemon", 1),
    ("HEB", "Hebrews", 13), ("JAS", "James", 5), ("1PE", "1 Peter", 5),
    ("2PE", "2 Peter", 3), ("1JN", "1 John", 5), ("2JN", "2 John", 1),
    ("3JN", "3 John", 1), ("JUD", "Jude", 1), ("REV", "Revelation", 22),
]

OT_BOOKS = BOOKS[:39]  # Genesis through Malachi
NT_BOOKS = BOOKS[39:]  # Matthew through Revelation

BOOK_ID_TO_NAME = {b[0]: b[1] for b in BOOKS}
BOOK_NAME_TO_ID = {b[1].lower(): b[0] for b in BOOKS}

# Common abbreviation expansions for commentary text
ABBREVIATIONS = {
    r"\bch\.\s*": "chapter ",
    r"\bvv?\.\s*": "verse ",
    r"\bcf\.\s*": "compare ",
    r"\bcomp\.\s*": "compare ",
    r"\bi\.e\.\s*": "that is, ",
    r"\be\.g\.\s*": "for example, ",
    r"\bviz\.\s*": "namely, ",
    r"\bq\.d\.\s*": "as if to say, ",
    # Book name abbreviations
    r"\bJoh\.": "John",
    r"\bJoh ": "John ",
    r"\bMat\.": "Matthew",
    r"\bMk\.": "Mark",
    r"\bLk\.": "Luke",
    r"\bRom\.": "Romans",
    r"\bCor\.": "Corinthians",
    r"\bRev\.": "Revelation",
    r"\bEph\.": "Ephesians",
    r"\bPhil\.": "Philippians",
    r"\bCol\.": "Colossians",
    r"\bThess\.": "Thessalonians",
    r"\bTim\.": "Timothy",
    r"\bHeb\.": "Hebrews",
    r"\bJas\.": "James",
    r"\bPet\.": "Peter",
}

# ── Tagging (reused from ingest.py) ─────────────────────────────────────────

from groq import Groq
from taxonomy import VALID_TAGS, TAXONOMY_LIST

TAG_SYSTEM_PROMPT = f"""You are a theological taxonomy classifier. Based on this commentary text, assign 3-6 topic tags from the taxonomy below.

STRICT RULES:
- Only assign a tag if the commentary CENTERS on that topic as a MAIN THEME
- A single sentence or brief mention does NOT qualify
- Prefer fewer, highly accurate tags over more loosely related ones
- 3-4 tags is ideal. Only use 5-6 if the text genuinely covers that many distinct themes in depth
- You MUST only return tags from the exact list below. Do not create new tags.
- Return JSON only: {{"topic_tags": ["tag1", "tag2", ...]}}

TAXONOMY (use ONLY these exact tags):
{TAXONOMY_LIST}"""

MAX_TAG_CHARS = 4000

# ── Clients ──────────────────────────────────────────────────────────────────

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# ── Helpers ──────────────────────────────────────────────────────────────────


def fetch_chapter(commentary_slug, book_id, chapter):
    # type: (str, str, int) -> Optional[Dict]
    """Fetch a single chapter's commentary from the HelloAO API."""
    url = f"{API_BASE}/{commentary_slug}/{book_id}/{chapter}.json"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def strip_html(text):
    # type: (str) -> str
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text)


def expand_abbreviations(text):
    # type: (str) -> str
    """Expand common commentary abbreviations."""
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    return text


def preprocess_commentary(text):
    # type: (str) -> str
    """Clean commentary text: strip HTML, expand abbreviations, normalize whitespace."""
    text = strip_html(text)
    text = expand_abbreviations(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def doc_title(commentary_name, book_name):
    # type: (str, str) -> str
    """Generate document title."""
    return f"{commentary_name} - {book_name}"


def document_exists(title):
    # type: (str) -> bool
    """Check if a document with this title already exists (resume safety)."""
    result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    return len(result.data) > 0


def tag_document(content_sample):
    # type: (str) -> List[str]
    """Tag document using Groq. Returns list of valid tags. Non-fatal."""
    try:
        trimmed = content_sample[:MAX_TAG_CHARS]
        resp = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=300,
            messages=[
                {"role": "system", "content": TAG_SYSTEM_PROMPT},
                {"role": "user", "content": trimmed},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            tags = [t for t in data.get("topic_tags", []) if t in VALID_TAGS]
            if len(tags) < 2:
                # Retry once
                resp2 = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=300,
                    messages=[
                        {"role": "system", "content": TAG_SYSTEM_PROMPT},
                        {"role": "user", "content": trimmed},
                    ],
                )
                raw2 = (resp2.choices[0].message.content or "").strip()
                match2 = re.search(r"\{.*\}", raw2, re.DOTALL)
                if match2:
                    data2 = json.loads(match2.group())
                    tags = [t for t in data2.get("topic_tags", []) if t in VALID_TAGS]
            return tags
    except Exception as e:
        logger.warning("Tagging failed: %s", e)
    return []


# ── Ingestion ────────────────────────────────────────────────────────────────


def ingest_book(commentary_key, book_id, book_name, chapter_count):
    # type: (str, str, str, int) -> bool
    """Fetch all chapters for a book and ingest as one document with per-verse chunks."""
    commentary = COMMENTARIES[commentary_key]
    title = doc_title(commentary["source_name"], book_name)

    if document_exists(title):
        logger.info("SKIP (exists): %s", title)
        return False

    logger.info("Fetching: %s (%d chapters)", title, chapter_count)

    # Collect all verse commentaries across chapters
    all_verses = []  # type: List[Dict]
    full_text_parts = []  # type: List[str]

    for ch in range(1, chapter_count + 1):
        data = fetch_chapter(commentary["slug"], book_id, ch)
        if not data:
            logger.warning("  No data for %s %s ch %d", commentary_key, book_id, ch)
            continue

        # API structure: data.chapter.content = [{type: "verse", number: N, content: ["..."]}]
        chapter_obj = data.get("chapter", {})
        content_list = chapter_obj.get("content", [])

        for entry in content_list:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "verse":
                continue
            verse_num = entry.get("number")
            if verse_num is None:
                continue

            # content is an array of strings — join them
            raw_parts = entry.get("content", [])
            raw_text = "\n".join(str(p) for p in raw_parts if isinstance(p, str))
            if not raw_text.strip():
                continue

            cleaned = preprocess_commentary(raw_text)
            if cleaned:
                ref = f"{book_name} {ch}:{verse_num}"
                all_verses.append({
                    "ref": ref,
                    "chapter": ch,
                    "verse": int(verse_num),
                    "content": cleaned,
                })
                full_text_parts.append(f"{ref}: {cleaned}")

        # Be polite to the API
        time.sleep(0.1)

    if not all_verses:
        logger.warning("  No verse data found for %s", title)
        return False

    logger.info("  %d verse entries collected", len(all_verses))

    # Tag the document (use first ~4000 chars of combined text)
    full_text = "\n".join(full_text_parts)
    topic_tags = tag_document(full_text)
    if topic_tags:
        logger.info("  Tags: %s", ", ".join(topic_tags))

    # Extract bible references (the book itself is the primary reference)
    bible_refs = [book_name]

    # Resolve attribution -> source_id via alias table. ALIAS_MISS is
    # printed by the resolver on a miss; source_id falls to sentinel.
    _resolved_id, _norm_key, _via = resolve_source_id(
        supabase, commentary["source_name"], commentary["author"]
    )
    logger.info("Resolved source: %r -> %s (via %s)", _norm_key, _resolved_id, _via)

    # Insert document
    doc_data = {
        "title": title,
        "author": commentary["author"],
        "source_name": commentary["source_name"],
        "source_type": "commentary",
        "source_kind": "commentary",
        "citation_mode": "citable",
        "is_copyrighted": False,
        "topic_tags": topic_tags if topic_tags else None,
        "bible_references": bible_refs,
        "source_id": _resolved_id,
    }

    doc_result = supabase.table("documents").insert(doc_data).execute()
    if not doc_result.data:
        logger.error("  Failed to insert document for %s", title)
        return False

    doc_id = doc_result.data[0]["id"]

    # Insert one chunk per verse commentary
    for idx, verse in enumerate(all_verses):
        header = f"[{commentary['source_name']} | {verse['ref']}]"
        chunk_content = f"{header}\n\n{verse['content']}"

        embedding = embed_text(chunk_content)

        chunk_data = {
            "document_id": doc_id,
            "chunk_index": idx,
            "content": chunk_content,
            "embedding": embedding,
        }
        supabase.table("chunks").insert(chunk_data).execute()

        if (idx + 1) % 50 == 0:
            logger.info("  Embedded %d/%d chunks", idx + 1, len(all_verses))

    logger.info("  Done: %s (%d chunks)", title, len(all_verses))
    return True


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Ingest HelloAO Bible commentaries into Supabase")
    parser.add_argument("--commentary", type=str, choices=list(COMMENTARIES.keys()),
                        help="Ingest only this commentary (default: all)")
    parser.add_argument("--book", type=str, help="Ingest only this book (e.g. 'Genesis', 'ROM')")
    parser.add_argument("--testament", type=str, choices=["ot", "nt"],
                        help="Ingest only OT (Genesis-Malachi) or NT (Matthew-Revelation)")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: ingest only Genesis for each commentary")
    parser.add_argument("--time-limit", type=int, default=0,
                        help="Stop after this many minutes (0 = no limit)")
    args = parser.parse_args()

    start_time = time.time()

    # Determine which commentaries to process
    if args.commentary:
        commentary_keys = [args.commentary]
    else:
        commentary_keys = list(COMMENTARIES.keys())

    # Determine which books to process
    if args.book:
        # Match by name or API ID
        book_filter = args.book.lower()
        matching = [(bid, bname, bch) for bid, bname, bch in BOOKS
                     if bid.lower() == book_filter or bname.lower() == book_filter]
        if not matching:
            logger.error("Unknown book: %s", args.book)
            sys.exit(1)
        books_to_process = matching
    elif args.test:
        books_to_process = [BOOKS[0]]  # Genesis only
    elif args.testament == "ot":
        books_to_process = OT_BOOKS
    elif args.testament == "nt":
        books_to_process = NT_BOOKS
    else:
        books_to_process = BOOKS

    total_ingested = 0
    total_skipped = 0

    for commentary_key in commentary_keys:
        logger.info("=" * 60)
        logger.info("Commentary: %s", COMMENTARIES[commentary_key]["source_name"])
        logger.info("=" * 60)

        for book_id, book_name, chapter_count in books_to_process:
            # Check time limit
            if args.time_limit > 0:
                elapsed = (time.time() - start_time) / 60.0
                if elapsed >= args.time_limit:
                    logger.info("Time limit reached (%.1f min). Stopping.", elapsed)
                    logger.info("Total: %d ingested, %d skipped", total_ingested, total_skipped)
                    return

            try:
                if ingest_book(commentary_key, book_id, book_name, chapter_count):
                    total_ingested += 1
                else:
                    total_skipped += 1
            except Exception as e:
                logger.exception("Failed to ingest %s %s: %s", commentary_key, book_name, e)
                total_skipped += 1

    elapsed = (time.time() - start_time) / 60.0
    logger.info("=" * 60)
    logger.info("Done. %d ingested, %d skipped (%.1f min)", total_ingested, total_skipped, elapsed)


if __name__ == "__main__":
    main()
