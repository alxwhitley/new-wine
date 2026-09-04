#!/usr/bin/env python3.12
"""
repair_reingest_authors_2026-09-04.py — one-off.

The 2026-09-04 truncated-YouTube re-ingest restored an author only where the
re-ingest left it NULL. It did nothing where the re-ingest wrote a WRONG name,
and on four documents it did exactly that — the speaker parser is title- and
transcript-derived, and CLAUDE.md already warns it is not reliable:

  doc                                              re-ingest wrote   was
  Being Filled with the Spirit                     'Joshua Lewis'    'Jack Deere'
  Dr. Brown Responds to Phil Johnson's ...         'Dr. Brown'       'Michael Brown'
  The Heresy of Cessationism 1 (The Scriptures)    'Daniel Kenda'    'Daniel Kolenda'
  What is the baptism of the Holy Spirit (with ..) 'Dr. Michael Brown' 'Michael Brown'

Why each is wrong, not merely different:
  - 'Joshua Lewis' is a DIFFERENT PERSON entirely, attached to Jack Deere's
    teaching. That is ranked failure mode #2 (misrepresenting a teacher) and
    it puts a wrong name into the answer path's permitted-name set.
  - 'Daniel Kenda' is the auto-captions' MISSPELLING of Daniel Kolenda.
  - 'Dr. Brown' / 'Dr. Michael Brown' are honorific-prefixed duplicate
    identities of the same man; CLAUDE.md records that these each draw their
    own share of the per-author 3-chunk retrieval cap.

Each is restored to the value the document carried before the re-ingest, which
in all four cases equals the source's own name. Guarded so it can only ever
write a value the source itself corroborates.

Dry-run by default.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / "app" / ".env")

import psycopg2  # noqa: E402

# (document_id, wrong value written by the re-ingest, value to restore)
FIXES = [
    ("5e5ef2e3-3d06-4e48-8ac5-4791036fd2f4", "Joshua Lewis",      "Jack Deere"),
    ("54bbb364-8b59-46e8-9623-a6d1627a6937", "Dr. Brown",         "Michael Brown"),
    ("014de875-7535-4d2b-b342-1cb7b7bd59da", "Daniel Kenda",      "Daniel Kolenda"),
    ("16e7c7c6-c5ed-406b-adb0-c77e4128b749", "Dr. Michael Brown", "Michael Brown"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    fixed = skipped = 0
    for doc_id, wrong, correct in FIXES:
        cur.execute("""
            select d.author, s.name, d.title
            from documents d join sources s on s.id = d.source_id
            where d.id = %s
        """, (doc_id,))
        row = cur.fetchone()
        if not row:
            print("SKIP %s — not found" % doc_id); skipped += 1; continue
        author, source_name, title = row
        print("%s" % title[:70])
        print("   author=%r  source=%r" % (author, source_name))

        if author == correct:
            print("   already correct"); skipped += 1; continue
        if author != wrong:
            print("   SKIP — expected %r, found %r; not touching" % (wrong, author))
            skipped += 1; continue
        if source_name.strip() != correct:
            print("   SKIP — source %r does not corroborate %r" % (source_name, correct))
            skipped += 1; continue

        if not args.apply:
            print("   [dry-run] would set author = %r" % correct); continue

        # Guarded: only from the exact wrong value, only to the source's own name.
        cur.execute("""
            update documents d
            set author = %s
            from sources s
            where d.id = %s and s.id = d.source_id
              and d.author = %s and btrim(s.name) = btrim(%s)
        """, (correct, doc_id, wrong, correct))
        if cur.rowcount != 1:
            conn.rollback()
            print("   ABORT: matched %d rows — rolled back" % cur.rowcount)
            skipped += 1; continue
        conn.commit()
        print("   -> %r" % correct)
        fixed += 1

    print("\nRECONCILIATION  attempted=%d fixed=%d skipped=%d"
          % (len(FIXES), fixed, skipped))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
