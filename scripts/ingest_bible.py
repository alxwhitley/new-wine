#!/usr/bin/env python3
"""
New Wine WEB Bible Ingestion Script

Parses the World English Bible VPL file and inserts verses into the
Supabase verses table via psycopg2 direct connection.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

# ── Config ────────────────────────────────────────────────────────────────────

VPL_FILE = PROJECT_ROOT / "sources" / "bible" / "eng-web_vpl.txt"
BATCH_SIZE = 1000

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    print("Set it to your Supabase direct connection string, e.g.:")
    print("  SUPABASE_DB_URL=postgresql://user:password@host:5432/dbname")
    sys.exit(1)

# ── Book mapping ─────────────────────────────────────────────────────────────
# Maps VPL file abbreviations to (full_name, sbl_abbrev, book_number)

BOOK_MAP = {
    # type: Dict[str, Tuple[str, str, int]]
    "GEN": ("Genesis", "GEN", 1),
    "EXO": ("Exodus", "EXO", 2),
    "LEV": ("Leviticus", "LEV", 3),
    "NUM": ("Numbers", "NUM", 4),
    "DEU": ("Deuteronomy", "DEU", 5),
    "JOS": ("Joshua", "JOS", 6),
    "JDG": ("Judges", "JDG", 7),
    "RUT": ("Ruth", "RUT", 8),
    "1SA": ("1 Samuel", "1SA", 9),
    "2SA": ("2 Samuel", "2SA", 10),
    "1KI": ("1 Kings", "1KI", 11),
    "2KI": ("2 Kings", "2KI", 12),
    "1CH": ("1 Chronicles", "1CH", 13),
    "2CH": ("2 Chronicles", "2CH", 14),
    "EZR": ("Ezra", "EZR", 15),
    "NEH": ("Nehemiah", "NEH", 16),
    "EST": ("Esther", "EST", 17),
    "JOB": ("Job", "JOB", 18),
    "PSA": ("Psalms", "PSA", 19),
    "PRO": ("Proverbs", "PRO", 20),
    "ECC": ("Ecclesiastes", "ECC", 21),
    "SOL": ("Song of Solomon", "SNG", 22),
    "ISA": ("Isaiah", "ISA", 23),
    "JER": ("Jeremiah", "JER", 24),
    "LAM": ("Lamentations", "LAM", 25),
    "EZE": ("Ezekiel", "EZK", 26),
    "DAN": ("Daniel", "DAN", 27),
    "HOS": ("Hosea", "HOS", 28),
    "JOE": ("Joel", "JOL", 29),
    "AMO": ("Amos", "AMO", 30),
    "OBA": ("Obadiah", "OBA", 31),
    "JON": ("Jonah", "JON", 32),
    "MIC": ("Micah", "MIC", 33),
    "NAH": ("Nahum", "NAH", 34),
    "HAB": ("Habakkuk", "HAB", 35),
    "ZEP": ("Zephaniah", "ZEP", 36),
    "HAG": ("Haggai", "HAG", 37),
    "ZEC": ("Zechariah", "ZEC", 38),
    "MAL": ("Malachi", "MAL", 39),
    "MAT": ("Matthew", "MAT", 40),
    "MAR": ("Mark", "MRK", 41),
    "LUK": ("Luke", "LUK", 42),
    "JOH": ("John", "JHN", 43),
    "ACT": ("Acts", "ACT", 44),
    "ROM": ("Romans", "ROM", 45),
    "1CO": ("1 Corinthians", "1CO", 46),
    "2CO": ("2 Corinthians", "2CO", 47),
    "GAL": ("Galatians", "GAL", 48),
    "EPH": ("Ephesians", "EPH", 49),
    "PHI": ("Philippians", "PHP", 50),
    "COL": ("Colossians", "COL", 51),
    "1TH": ("1 Thessalonians", "1TH", 52),
    "2TH": ("2 Thessalonians", "2TH", 53),
    "1TI": ("1 Timothy", "1TI", 54),
    "2TI": ("2 Timothy", "2TI", 55),
    "TIT": ("Titus", "TIT", 56),
    "PHM": ("Philemon", "PHM", 57),
    "HEB": ("Hebrews", "HEB", 58),
    "JAM": ("James", "JAS", 59),
    "1PE": ("1 Peter", "1PE", 60),
    "2PE": ("2 Peter", "2PE", 61),
    "1JO": ("1 John", "1JN", 62),
    "2JO": ("2 John", "2JN", 63),
    "3JO": ("3 John", "3JN", 64),
    "JUD": ("Jude", "JUD", 65),
    "REV": ("Revelation", "REV", 66),
}

LINE_RE = re.compile(r'^(\S+)\s+(\d+):(\d+)\s+(.*)')


# ── Parse ────────────────────────────────────────────────────────────────────

def parse_vpl(max_verses=None):
    # type: (Optional[int]) -> List[Tuple]
    """Parse the VPL file. Returns list of tuples for insert.
    Each tuple: (verse_id, book, book_num, chapter, verse, text)"""
    rows = []  # type: List[Tuple]
    skipped_books = set()  # type: set

    with open(VPL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m = LINE_RE.match(line)
            if not m:
                continue

            vpl_abbrev = m.group(1)
            chapter = int(m.group(2))
            verse_num = int(m.group(3))
            text = m.group(4).strip()

            book_info = BOOK_MAP.get(vpl_abbrev)
            if not book_info:
                skipped_books.add(vpl_abbrev)
                continue

            full_name, sbl_abbrev, book_num = book_info
            verse_id = "{}.{}.{}".format(sbl_abbrev, chapter, verse_num)

            rows.append((verse_id, full_name, book_num, chapter, verse_num, text))

            if max_verses is not None and len(rows) >= max_verses:
                break

    if skipped_books:
        print("Skipped non-canonical books: {}".format(", ".join(sorted(skipped_books))))

    return rows


# ── Insert ───────────────────────────────────────────────────────────────────

def insert_verses(rows):
    # type: (List[Tuple]) -> int
    """Insert verses into Supabase via psycopg2. Returns number inserted."""
    conn = psycopg2.connect(SUPABASE_DB_URL)
    total_inserted = 0

    try:
        with conn.cursor() as cur:
            for batch_start in range(0, len(rows), BATCH_SIZE):
                batch = rows[batch_start:batch_start + BATCH_SIZE]

                execute_values(
                    cur,
                    """INSERT INTO verses (verse_id, book, book_num, chapter, verse, text)
                       VALUES %s
                       ON CONFLICT (verse_id) DO NOTHING""",
                    batch,
                )
                total_inserted += cur.rowcount
                conn.commit()

                processed = batch_start + len(batch)
                if processed % 5000 == 0 or processed == len(rows):
                    print("[PROGRESS] {}/{} verses processed, {} inserted".format(
                        processed, len(rows), total_inserted
                    ))
    finally:
        conn.close()

    return total_inserted


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    test_mode = "--test" in sys.argv
    max_verses = 100 if test_mode else None

    print("New Wine WEB Bible Ingestion")
    if test_mode:
        print("TEST MODE: limited to 100 verses")
    print("=" * 60)

    if not VPL_FILE.exists():
        print("ERROR: VPL file not found at {}".format(VPL_FILE))
        sys.exit(1)

    print("Parsing {}...".format(VPL_FILE.name))
    rows = parse_vpl(max_verses=max_verses)
    print("Parsed {} verses from 66 canonical books\n".format(len(rows)))

    if not rows:
        print("No verses to insert.")
        return

    inserted = insert_verses(rows)
    skipped = len(rows) - inserted

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("  Total parsed:   {}".format(len(rows)))
    print("  Inserted:       {}".format(inserted))
    print("  Skipped (dupes): {}".format(skipped))
    print("=" * 60)


if __name__ == "__main__":
    main()
