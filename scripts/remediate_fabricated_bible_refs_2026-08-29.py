#!/usr/bin/env python3.12
"""
remediate_fabricated_bible_refs_2026-08-29.py — remove two fabricated scripture
references from "The Spiritual War Over the Unborn | Eric Davis".

Found during the post-re-ingest scripture audit (2026-08-29). Of 514 stored
references across the 49 CLF YouTube sermons, every one cites a book genuinely
named in its transcript, and all but these two are either explicitly spoken or
correctly inferred from quoted content. These two are neither:

  Psalm 2 — chapter number absent in every spoken/written form, and none of
            the psalm's signature content is present. (An earlier check
            appeared to find "rage", a Psalm 2 keyword; that was a substring
            false positive inside the word "encourage".)
  Psalm 3 — chapter number absent, no signature content, and the audit model
            independently reported "No mention of Psalm 3 in the transcript."

Deliberately NOT touched: references where the SPEAKER misstated a chapter or
verse and the extractor faithfully recorded it (e.g. a preacher saying
"Psalms 68 uh 19, sorry, wrong Psalms" before reading Psalm 116). Those are
accurate transcriptions of what was said; rewriting them would make the record
less faithful, not more. Same posture as CLAUDE.md Settled decision #27 —
remove from use, never silently "correct" content.

Dry-run by default. --apply is required to write.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

import psycopg2  # noqa: E402

DOC_ID = "0b6ac634-e327-4831-9009-bd191b269606"
DOC_TITLE_FRAGMENT = "Spiritual War Over the Unborn"
FABRICATED = ["Psalm 2", "Psalm 3"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    # Identity guard: refuse to run if the target row is not what we expect.
    cur.execute("select title, bible_references from documents where id = %s",
                (DOC_ID,))
    row = cur.fetchone()
    if not row:
        print(f"ABORT: document {DOC_ID} not found")
        sys.exit(1)
    title, refs = row
    if DOC_TITLE_FRAGMENT not in title:
        print(f"ABORT: document {DOC_ID} is {title!r}, "
              f"expected to contain {DOC_TITLE_FRAGMENT!r}")
        sys.exit(1)

    print(f"document: {title}")
    print(f"  before ({len(refs)}): {list(refs)}")

    present = [r for r in FABRICATED if r in refs]
    if not present:
        print("  nothing to remove — already clean")
        conn.close()
        return
    print(f"  removing: {present}")

    cur.execute("""
        select count(*) from chunks
        where document_id = %s and bible_references && %s::text[]
    """, (DOC_ID, FABRICATED))
    n_chunks = cur.fetchone()[0]
    print(f"  chunks also carrying one of these: {n_chunks}")

    if not args.apply:
        print("\n[DRY-RUN] no changes written. Re-run with --apply.")
        conn.close()
        return

    for ref in FABRICATED:
        cur.execute("""
            update documents set bible_references = array_remove(bible_references, %s)
            where id = %s
        """, (ref, DOC_ID))
        cur.execute("""
            update chunks set bible_references = array_remove(bible_references, %s)
            where document_id = %s
        """, (ref, DOC_ID))
    conn.commit()

    cur.execute("select bible_references from documents where id = %s", (DOC_ID,))
    after = cur.fetchone()[0]
    print(f"  after  ({len(after)}): {list(after)}")

    leftover = [r for r in FABRICATED if r in after]
    cur.execute("""
        select count(*) from chunks
        where document_id = %s and bible_references && %s::text[]
    """, (DOC_ID, FABRICATED))
    chunk_leftover = cur.fetchone()[0]
    print(f"\nverification: {len(refs) - len(after)} reference(s) removed from "
          f"the document, {chunk_leftover} chunk(s) still carrying one "
          f"(expected 0)")
    print("RESULT:", "OK" if not leftover and chunk_leftover == 0 else "INCOMPLETE")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
