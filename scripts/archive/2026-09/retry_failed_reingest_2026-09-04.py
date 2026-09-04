#!/usr/bin/env python3.12
"""
retry_failed_reingest_2026-09-04.py — one-off.

One document in the 2026-09-04 truncated-YouTube re-ingest batch failed at the
proposition/paraphrase step. That step rolls the whole ingest back, so the old
(truncated) row was already gone and no new row replaced it: the document was
left absent from the corpus entirely.

    You Might Be Failing God… And Not Even Know It  (Vlad Savchuk)
    https://www.youtube.com/watch?v=WgO8dhV36AY

The failure looked transient (`propositions: error`, no detail), so this
retries the same ingest rather than restoring the truncated backup. If the
retry fails again, restore from
local/2026-09/truncated_youtube_backup_20260904T154047Z.json instead and
investigate the extraction error before trying a third time.

Refuses to run if a document already exists at that url, so it can never
create the duplicate that `documents.url` has no constraint to prevent.

Dry-run by default.
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

import youtube_ingest as yi  # noqa: E402

URL = "https://www.youtube.com/watch?v=WgO8dhV36AY"
TITLE = "You Might Be Failing God… And Not Even Know It"
CHANNEL = "Vlad Savchuk"
EXPECTED_WORDS = 13529


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ytdlp = yi.find_ytdlp()
    if not ytdlp:
        sys.exit("ERROR: yt-dlp not found")

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    cur = conn.cursor()

    cur.execute("select id::text from documents where url = %s", (URL,))
    existing = [r[0] for r in cur.fetchall()]
    if existing:
        sys.exit("REFUSING: %d document(s) already exist at this url: %s"
                 % (len(existing), existing))

    cur.execute("select url from removed_urls where url = %s", (URL,))
    if cur.fetchone():
        sys.exit("REFUSING: url is in removed_urls (permanent blocklist)")

    print("document absent as expected — safe to re-ingest")
    print("  %s" % TITLE)
    print("  %s" % URL)
    if not args.apply:
        print("  [dry-run] would re-ingest via youtube_ingest.ingest_video()")
        return

    status, display, reason = yi.ingest_video(ytdlp, URL, TITLE, CHANNEL, dry_run=False)
    print("\n  ingest: status=%s source=%r (%s)" % (status, display, reason))

    cur.execute("""
        select id::text, coalesce(full_text, ''), author,
               (select count(*) from chunks c where c.document_id = d.id),
               (select count(*) from propositions p where p.document_id = d.id)
        from documents d where d.url = %s
    """, (URL,))
    rows = cur.fetchall()
    if len(rows) != 1:
        sys.exit("!! %d documents at this url after retry — expected exactly 1" % len(rows))
    doc_id, full_text, author, n_chunks, n_props = rows[0]
    words = len(full_text.split())
    print("  restored: %s" % doc_id)
    print("  %s words, %d chunks, %d propositions, author=%r"
          % ("{:,}".format(words), n_chunks, n_props, author))
    print("  expected ~{:,} words -> {}".format(
        EXPECTED_WORDS, "OK" if words >= EXPECTED_WORDS * 0.9 else "CHECK"))

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
