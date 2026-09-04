#!/usr/bin/env python3.12
"""
silence_guest_interview_2026-09-04.py — one-off.

"The Truth About Nephilim, Watchers, and Demons" is a guest interview stored
under the Vlad Savchuk source with citation_mode='citable' and no author. Read
directly, its substantive doctrinal claims are the GUEST's, not Savchuk's:

    "Why did he rebel? >> He wanted to elevate himself above God.
     >> ...so is it their spirits that are demons?
     >> The evil spirits that we cast out of people today are the
        disembodied spirits of these Nephilim."

A retrieved chunk from it is attributed to Savchuk, which puts a guest's
position about Nephilim and the origin of demons in a living minister's mouth
-- ranked failure mode #2.

The fix is the standing rule already in CLAUDE.md, not a new mechanism: a
genuinely multi-speaker document goes citation_mode='silent_context'. Exactly
this was done to three CLF documents on 2026-08-31. The material stays
retrievable as context; it simply stops being attributable to one name.

HOW THIS DOCUMENT WAS FOUND, and why only one is treated here: four separate
mechanical detectors were tried and all four failed --

  - "&gt;&gt;" markers do NOT mean multi-speaker. In the sampled passages they
    are caption cue artifacts inside one person's continuous sentence
    ("...the really big decisions, &gt;&gt; right? When the big decisions...").
  - Short-turn ratio plus assent tokens finds preaching repetition and
    congregational call-and-response ("leave, / leave, / leave, / LEAVE.",
    "Lord Jesus, / I believe. / I believe"), not dialogue. 6 of its 8 hits
    were false.
  - Question-terminated turn pairs find rhetorical questions. Two documents
    confirmed by reading NOT to be interviews outrank the one that is.
  - Turn-pair density does not separate them either.

So this document was identified by READING, and only documents confirmed the
same way should be added here. Do not resurrect the detectors above; they are
recorded so the next session does not rebuild them.

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

# (document id, title fragment for the guard, reason)
TARGETS = [
    ("lIB6AXkN50s", "Nephilim",
     "guest interview; doctrinal claims are the guest's, attributed to the host"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    changed = skipped = 0
    for vid, frag, reason in TARGETS:
        cur.execute("""
            select d.id::text, d.title, d.author, d.citation_mode, s.name
            from documents d join sources s on s.id = d.source_id
            where d.url like %s and d.source_kind = 'sermon_transcript'
        """, ("%" + vid + "%",))
        rows = cur.fetchall()
        if len(rows) != 1:
            print("SKIP %s — matched %d documents, expected 1" % (vid, len(rows)))
            skipped += 1
            continue
        doc_id, title, author, mode, source = rows[0]
        print("%s" % title[:70])
        print("   source=%r author=%r citation_mode=%s" % (source, author, mode))
        print("   reason: %s" % reason)

        if frag.lower() not in title.lower():
            print("   SKIP — title guard %r did not match" % frag)
            skipped += 1
            continue
        if mode == "silent_context":
            print("   already silent_context — nothing to do")
            skipped += 1
            continue
        if mode != "citable":
            print("   SKIP — unexpected citation_mode %r" % mode)
            skipped += 1
            continue

        if not args.apply:
            print("   [dry-run] would set citation_mode = 'silent_context'")
            continue

        cur.execute("""
            update documents
            set citation_mode = 'silent_context'
            where id = %s and citation_mode = 'citable'
        """, (doc_id,))
        if cur.rowcount != 1:
            conn.rollback()
            print("   ABORT: matched %d rows — rolled back" % cur.rowcount)
            skipped += 1
            continue
        conn.commit()

        cur.execute("select citation_mode from documents where id = %s", (doc_id,))
        print("   -> citation_mode is now %r" % cur.fetchone()[0])
        changed += 1

    print("\nRECONCILIATION  attempted=%d changed=%d skipped=%d"
          % (len(TARGETS), changed, skipped))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
