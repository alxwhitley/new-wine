#!/usr/bin/env python3.12
"""
repair_reingest_proof_author_2026-09-04.py — one-off.

The single-document proof for reingest_truncated_youtube_2026-09-04.py ran
BEFORE that script learned to preserve `documents.author`, so the rebuilt
"Cessationism 8" document was left with a null author where the original had
'Daniel Kolenda'. This restores it under exactly the same narrow rule the main
script now applies: restore only when the source's own name matches the value
being restored.

Superseded by the main script for every later document. Dry-run by default.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / "app" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg2  # noqa: E402

DOC_ID = "94a7a3c1-08ae-4bc3-8327-320bd562f1ab"
AUTHOR = "Daniel Kolenda"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("""
        select d.author, s.name, d.title
        from documents d join sources s on s.id = d.source_id
        where d.id = %s
    """, (DOC_ID,))
    row = cur.fetchone()
    if not row:
        sys.exit("ERROR: document %s not found" % DOC_ID)
    author, source_name, title = row
    print("document: %s" % title)
    print("  author now: %r   source: %r" % (author, source_name))

    if author is not None:
        print("  nothing to do — author already set")
        return
    if source_name.strip() != AUTHOR:
        sys.exit("ERROR: source name %r does not corroborate %r" % (source_name, AUTHOR))

    if not args.apply:
        print("  [dry-run] would set author = %r" % AUTHOR)
        return

    cur.execute("""
        update documents d
        set author = %s
        from sources s
        where d.id = %s and s.id = d.source_id
          and d.author is null and btrim(s.name) = btrim(%s)
    """, (AUTHOR, DOC_ID, AUTHOR))
    n = cur.rowcount
    if n != 1:
        conn.rollback()
        sys.exit("ABORT: matched %d rows (expected 1) — rolled back" % n)
    conn.commit()

    cur.execute("select author from documents where id = %s", (DOC_ID,))
    print("  author now: %r  (updated %d row)" % (cur.fetchone()[0], n))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
