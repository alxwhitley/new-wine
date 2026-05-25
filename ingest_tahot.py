#!/usr/bin/env python3
"""
Ingest TAHOT (Hebrew OT) interlinear data into Supabase interlinear_words table.

Downloads TAHOT files from STEPBible-Data GitHub if not cached, parses them,
and inserts into the interlinear_words table with language='hebrew'.

Usage:
    cd /Users/alexwhitley/Desktop/rhemata
    python3 ingest_tahot.py              # full ingestion (all OT books)
    python3 ingest_tahot.py --test       # first 100 rows only
    python3 ingest_tahot.py --book GEN   # single book
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlretrieve

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

DB_URL = os.environ["SUPABASE_DB_URL"]
BATCH_SIZE = 1000
CACHE_DIR = Path("/tmp/tahot")

TAHOT_BASE = (
    "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/master/"
    "Translators%20Amalgamated%20OT%2BNT/"
)

TAHOT_FILES = {
    "Gen-Deu": "TAHOT%20Gen-Deu%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
    "Jos-Est": "TAHOT%20Jos-Est%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
    "Job-Sng": "TAHOT%20Job-Sng%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
    "Isa-Mal": "TAHOT%20Isa-Mal%20-%20Translators%20Amalgamated%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt",
}

TAHOT_TO_SBL = {
    "Gen": "GEN", "Exo": "EXO", "Lev": "LEV", "Num": "NUM", "Deu": "DEU",
    "Jos": "JOS", "Jdg": "JDG", "Rut": "RUT",
    "1Sa": "1SA", "2Sa": "2SA", "1Ki": "1KI", "2Ki": "2KI",
    "1Ch": "1CH", "2Ch": "2CH", "Ezr": "EZR", "Neh": "NEH", "Est": "EST",
    "Job": "JOB", "Psa": "PSA", "Pro": "PRO", "Ecc": "ECC", "Sng": "SNG",
    "Isa": "ISA", "Jer": "JER", "Lam": "LAM", "Ezk": "EZK", "Dan": "DAN",
    "Hos": "HOS", "Jol": "JOL", "Amo": "AMO", "Oba": "OBA", "Jon": "JON",
    "Mic": "MIC", "Nam": "NAM", "Hab": "HAB", "Zep": "ZEP",
    "Hag": "HAG", "Zec": "ZEC", "Mal": "MAL",
}

# Regex to parse reference: Book.Chapter.Verse[optional brackets]#Position=Type
REF_RE = re.compile(
    r'^(\w+)\.(\d+)\.(\d+)'   # Book.Chapter.Verse
    r'(?:\[[^\]]*\])?'         # optional [alt verse]
    r'(?:\([^)]*\))?'          # optional (alt verse)
    r'(?:\{[^}]*\})?'          # optional {alt verse}
    r'#(\d+)'                  # #Position
    r'=(.+)$'                  # =Type
)

# Extract root Strong's from dStrongs column like "H9003/{H7225G}" → "H7225"
ROOT_STRONGS_RE = re.compile(r'\{(H\d+)[A-Z]?\}')
SIMPLE_STRONGS_RE = re.compile(r'^(H\d+)')


def normalize_strongs(raw):
    # type: (str) -> Optional[str]
    """Extract and normalize root Strong's number from dStrongs column.

    Examples:
        'H9003/{H7225G}' → 'H7225'
        '{H1254A}'       → 'H1254'
        'H0853'          → 'H853'
    """
    # Prefer the last {Hxxxx} match (root word, not prefix)
    matches = ROOT_STRONGS_RE.findall(raw)
    if matches:
        m = re.match(r'^H(\d+)', matches[-1])
        if m:
            return "H" + str(int(m.group(1)))

    # Fallback: first H number token
    m = SIMPLE_STRONGS_RE.match(raw.split("/")[0].strip())
    if m:
        num = re.match(r'^H(\d+)', m.group(1))
        if num:
            return "H" + str(int(num.group(1)))

    return None


def clean_english(col):
    # type: (str) -> str
    """Strip bracket notation: '[the] earth' → 'the earth'."""
    return col.strip().replace("[", "").replace("]", "").replace("<", "").replace(">", "")


def download_tahot_files():
    # type: () -> List[Path]
    """Download TAHOT files to cache dir if not present. Return list of paths."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []  # type: List[Path]

    for label, filename in TAHOT_FILES.items():
        # Use a clean local filename
        local_name = "TAHOT_%s.txt" % label
        local_path = CACHE_DIR / local_name

        if local_path.exists() and local_path.stat().st_size > 1000:
            print("  Cached: %s" % local_name)
        else:
            url = TAHOT_BASE + filename
            print("  Downloading: %s ..." % label)
            urlretrieve(url, str(local_path))
            size_mb = local_path.stat().st_size / (1024 * 1024)
            print("    -> %.1f MB" % size_mb)

        paths.append(local_path)

    return paths


def parse_tahot_file(filepath, book_filter=None, max_rows=None):
    # type: (Path, Optional[str], Optional[int]) -> List[dict]
    """Parse a TAHOT file and return list of word dicts."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    words = []  # type: List[dict]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip comments and interlinear summary lines
        if stripped.startswith("#"):
            continue
        # Skip repeated header rows
        if stripped.startswith("Eng (Heb) Ref & Type\t"):
            continue

        fields = stripped.split("\t")
        if len(fields) < 6:
            continue

        ref_match = REF_RE.match(fields[0].strip())
        if not ref_match:
            continue

        tahot_book = ref_match.group(1)
        chapter = int(ref_match.group(2))
        verse = int(ref_match.group(3))
        position = int(ref_match.group(4))

        sbl_book = TAHOT_TO_SBL.get(tahot_book)
        if not sbl_book:
            continue

        if book_filter and sbl_book != book_filter:
            continue

        verse_id = "%s.%d.%d" % (sbl_book, chapter, verse)
        hebrew_word = fields[1].strip()
        transliteration = fields[2].strip() if len(fields) > 2 else ""
        english_gloss = clean_english(fields[3]) if len(fields) > 3 else ""
        strongs = normalize_strongs(fields[4]) if len(fields) > 4 else None
        morphology = fields[5].strip() if len(fields) > 5 else None

        words.append({
            "verse_id": verse_id,
            "word_position": position,
            "original_word": hebrew_word,
            "transliteration": transliteration,
            "strongs_number": strongs,
            "english_gloss": english_gloss,
            "morphology": morphology,
        })

        if max_rows and len(words) >= max_rows:
            break

    return words


def get_book_counts(cur):
    # type: (...) -> Dict[str, int]
    """Get existing row counts per book for resume safety."""
    cur.execute(
        "SELECT split_part(verse_id, '.', 1) AS book, COUNT(*) "
        "FROM interlinear_words WHERE language = 'hebrew' "
        "GROUP BY book"
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def main():
    parser = argparse.ArgumentParser(description="Ingest TAHOT Hebrew OT interlinear data")
    parser.add_argument("--test", action="store_true", help="First 100 rows only")
    parser.add_argument("--book", type=str, default=None, help="Single book, e.g. GEN")
    args = parser.parse_args()

    book_filter = None  # type: Optional[str]
    max_rows = None  # type: Optional[int]

    if args.test:
        max_rows = 100
        print("TEST MODE: first 100 rows only\n")
    elif args.book:
        book_filter = args.book.upper()
        if book_filter not in TAHOT_TO_SBL.values():
            print("Unknown book: %s" % book_filter)
            print("Valid books: %s" % ", ".join(sorted(TAHOT_TO_SBL.values())))
            sys.exit(1)
        print("Single book mode: %s\n" % book_filter)

    # Download files
    print("Checking TAHOT files...")
    paths = download_tahot_files()
    print()

    # Connect to DB
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Check existing Hebrew counts per book (resume safety)
    existing_books = get_book_counts(cur)
    if existing_books:
        total_existing = sum(existing_books.values())
        print("Existing Hebrew interlinear rows: %d (%d books)" % (total_existing, len(existing_books)))

    # Parse all files
    all_words = []  # type: List[dict]
    for filepath in paths:
        print("Parsing: %s" % filepath.name)
        words = parse_tahot_file(filepath, book_filter=book_filter, max_rows=max_rows)
        print("  %d words parsed" % len(words))
        all_words.extend(words)

        if max_rows and len(all_words) >= max_rows:
            all_words = all_words[:max_rows]
            break

    if not all_words:
        print("\nNo words parsed.")
        cur.close()
        conn.close()
        return

    # Check which books are already loaded and skip them
    books_in_batch = set(w["verse_id"].split(".")[0] for w in all_words)
    skip_books = set()  # type: set
    for book in books_in_batch:
        if book in existing_books and existing_books[book] > 0:
            print("  SKIP %s: already has %d rows" % (book, existing_books[book]))
            skip_books.add(book)

    if skip_books:
        all_words = [w for w in all_words if w["verse_id"].split(".")[0] not in skip_books]

    if not all_words:
        print("\nAll books already loaded. Nothing to do.")
        cur.close()
        conn.close()
        return

    verse_ids = set(w["verse_id"] for w in all_words)
    print("\nTotal to insert: %d words across %d verses" % (len(all_words), len(verse_ids)))

    # Batch insert
    insert_sql = """
        INSERT INTO interlinear_words
            (verse_id, word_position, original_word, transliteration, strongs_number, english_gloss, morphology, language)
        VALUES %s
        ON CONFLICT (verse_id, word_position) DO NOTHING
    """

    inserted = 0
    t0 = time.time()

    for batch_start in range(0, len(all_words), BATCH_SIZE):
        batch = all_words[batch_start:batch_start + BATCH_SIZE]
        values = [
            (
                w["verse_id"],
                w["word_position"],
                w["original_word"],
                w["transliteration"],
                w["strongs_number"],
                w["english_gloss"],
                w["morphology"],
                "hebrew",
            )
            for w in batch
        ]
        execute_values(cur, insert_sql, values)
        conn.commit()
        inserted += len(batch)

        if inserted % 5000 == 0 or inserted == len(all_words):
            elapsed = time.time() - t0
            print("  Inserted: %d / %d (%.1fs)" % (inserted, len(all_words), elapsed))

    cur.close()
    conn.close()

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("DONE in %.1fs" % elapsed)
    print("  Total words inserted: %d" % inserted)
    print("  Total verses covered: %d" % len(verse_ids))
    print("=" * 60)


if __name__ == "__main__":
    main()
