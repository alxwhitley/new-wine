#!/usr/bin/env python3
"""
Ingest TAGNT interlinear data into Supabase interlinear_words table.

Usage:
    cd /Users/alexwhitley/Desktop/rhemata
    python3 ingest_interlinear.py              # full ingestion (all NT books)
    python3 ingest_interlinear.py --test       # Matthew 1 only
    python3 ingest_interlinear.py --book JHN   # single book
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

DB_URL = os.environ["SUPABASE_DB_URL"]
LEXICON_DIR = PROJECT_ROOT / "sources" / "lexicon"
BATCH_SIZE = 1000

TAGNT_FILES = [
    "TAGNT Mat-Jhn - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
    "TAGNT Act-Rev - Translators Amalgamated Greek NT - STEPBible.org CC-BY.txt",
]

# TAGNT book abbreviations → SBL 3-letter codes (just uppercase)
TAGNT_TO_SBL = {
    "Mat": "MAT", "Mrk": "MRK", "Luk": "LUK", "Jhn": "JHN",
    "Act": "ACT", "Rom": "ROM", "1Co": "1CO", "2Co": "2CO",
    "Gal": "GAL", "Eph": "EPH", "Php": "PHP", "Col": "COL",
    "1Th": "1TH", "2Th": "2TH", "1Ti": "1TI", "2Ti": "2TI",
    "Tit": "TIT", "Phm": "PHM", "Heb": "HEB", "Jas": "JAS",
    "1Pe": "1PE", "2Pe": "2PE", "1Jn": "1JN", "2Jn": "2JN",
    "3Jn": "3JN", "Jud": "JUD", "Rev": "REV",
}

# Regex to parse reference column: Book.Chapter.Verse[optional brackets]#Position=WordType
REF_RE = re.compile(
    r'^(\w+)\.(\d+)\.(\d+)'   # Book.Chapter.Verse
    r'(?:\[[^\]]*\])?'         # optional [KJV verse]
    r'(?:\([^)]*\))?'          # optional (NA verse)
    r'(?:\{[^}]*\})?'          # optional {other verse}
    r'#(\d+)'                  # #Position
    r'=(.+)$'                  # =WordType
)


def normalize_strongs(raw):
    # type: (str) -> str
    """Normalize Strong's number: G0976 → G976, strip disambiguation suffix."""
    m = re.match(r'^([GH])(\d+)', raw)
    if not m:
        return raw
    return m.group(1) + str(int(m.group(2)))


def parse_greek_column(col):
    # type: (str) -> Tuple[str, Optional[str]]
    """Parse 'Βίβλος (Biblos)' → ('Βίβλος', 'Biblos')."""
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', col.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return col.strip(), None


def parse_strongs_grammar(col):
    # type: (str) -> Tuple[Optional[str], Optional[str]]
    """Parse 'G0976=N-NSF' → ('G976', 'N-NSF')."""
    parts = col.strip().split("=", 1)
    if len(parts) == 2:
        return normalize_strongs(parts[0].strip()), parts[1].strip()
    return None, None


def clean_english(col):
    # type: (str) -> str
    """Strip bracket notation from English gloss: '[The] book' → 'The book'."""
    return col.strip().replace("[", "").replace("]", "")


def parse_tagnt_file(filepath, book_filter=None, chapter_filter=None):
    # type: (Path, Optional[str], Optional[int]) -> List[dict]
    """Parse a TAGNT file and return list of word dicts."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Find the header row to know where data starts
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Word & Type\t"):
            data_start = i + 1
            break

    if data_start == 0:
        print("  WARNING: Could not find data header in %s" % filepath.name)
        return []

    words = []  # type: List[dict]
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        fields = stripped.split("\t")
        if len(fields) < 4:
            continue

        ref_match = REF_RE.match(fields[0].strip())
        if not ref_match:
            continue

        tagnt_book = ref_match.group(1)
        chapter = int(ref_match.group(2))
        verse = int(ref_match.group(3))
        position = int(ref_match.group(4))

        sbl_book = TAGNT_TO_SBL.get(tagnt_book)
        if not sbl_book:
            continue

        if book_filter and sbl_book != book_filter:
            continue
        if chapter_filter is not None and chapter != chapter_filter:
            continue

        verse_id = "%s.%d.%d" % (sbl_book, chapter, verse)
        greek_word, transliteration = parse_greek_column(fields[1])
        english_gloss = clean_english(fields[2]) if len(fields) > 2 else ""
        strongs, morphology = parse_strongs_grammar(fields[3]) if len(fields) > 3 else (None, None)

        words.append({
            "verse_id": verse_id,
            "word_position": position,
            "original_word": greek_word,
            "transliteration": transliteration,
            "strongs_number": strongs,
            "english_gloss": english_gloss,
            "morphology": morphology,
        })

    return words


def main():
    parser = argparse.ArgumentParser(description="Ingest TAGNT interlinear data")
    parser.add_argument("--test", action="store_true", help="Process Matthew 1 only")
    parser.add_argument("--book", type=str, default=None, help="Process a single book, e.g. JHN")
    args = parser.parse_args()

    book_filter = None  # type: Optional[str]
    chapter_filter = None  # type: Optional[int]

    if args.test:
        book_filter = "MAT"
        chapter_filter = 1
        print("TEST MODE: Matthew 1 only\n")
    elif args.book:
        book_filter = args.book.upper()
        if book_filter not in TAGNT_TO_SBL.values():
            print("Unknown book: %s" % book_filter)
            print("Valid books: %s" % ", ".join(sorted(TAGNT_TO_SBL.values())))
            sys.exit(1)
        print("Single book mode: %s\n" % book_filter)

    # Check existing count
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM interlinear_words")
    existing_count = cur.fetchone()[0]
    print("Existing interlinear_words rows: %d" % existing_count)

    if existing_count > 0 and not args.test and not args.book:
        print("Table already has data. Continuing with ON CONFLICT DO NOTHING (safe to re-run).\n")

    # Parse all TAGNT files
    all_words = []  # type: List[dict]
    for filename in TAGNT_FILES:
        filepath = LEXICON_DIR / filename
        if not filepath.exists():
            print("WARNING: File not found: %s" % filename)
            continue
        print("Parsing: %s" % filename)
        words = parse_tagnt_file(filepath, book_filter=book_filter, chapter_filter=chapter_filter)
        print("  %d words parsed" % len(words))
        all_words.extend(words)

    if not all_words:
        print("\nNo words parsed.")
        cur.close()
        conn.close()
        return

    # Count unique verses
    verse_ids = set(w["verse_id"] for w in all_words)
    print("\nTotal: %d words across %d verses" % (len(all_words), len(verse_ids)))

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
                "greek",
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
