#!/usr/bin/env python3.12
"""
reingest_clf_youtube_2026-08-29.py — re-ingest CLF Church YouTube sermons whose
stored text was truncated by the now-removed Groq "cleaning" pass.

Background: youtube_ingest.py used to fetch captions via `--convert-subs srt`,
which flattens YouTube's rolling-window cue format into literally triplicated
text, then relied on a Groq model to undo that. Measured live 2026-08-29, the
model discarded ~60-75% of each sermon instead. The extraction path is now
json3 (no duplication to undo, no cleaning model), so these documents can be
rebuilt from source at full length.

Scope guard: only documents whose source is CLF Church AND whose url is a
YouTube url are eligible. The 15 non-YouTube CLF documents (prophetic training
notes etc.) are structurally unreachable from here.

Deletes go through direct SQL on purpose, NOT DELETE /admin/document/{id} —
that endpoint writes to removed_urls, which youtube_ingest.py treats as a
permanent blocklist and would refuse to re-ingest against.

Dry-run by default. --apply is required to write.

Usage:
    python3.12 scripts/reingest_clf_youtube_2026-08-29.py                    # dry run, all
    python3.12 scripts/reingest_clf_youtube_2026-08-29.py --url URL --apply  # one video
    python3.12 scripts/reingest_clf_youtube_2026-08-29.py --limit 5 --apply
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg2  # noqa: E402

import youtube_ingest as yi  # noqa: E402

CLF_SOURCE_ID = "29bfe81f-a150-4e43-baac-042e366fb4b3"


def connect():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


def immediate_repeats(text, span=5):
    w = text.split()
    return sum(1 for i in range(len(w) - 2 * span)
               if w[i:i + span] == w[i + span:i + 2 * span])


def fetch_doc(cur, url):
    """Current CLF document for this url, with its stored text. None if absent."""
    cur.execute("""
        select d.id, d.title, d.author, d.bible_references
        from documents d
        where d.source_id = %s and d.url = %s
    """, (CLF_SOURCE_ID, url))
    row = cur.fetchone()
    if not row:
        return None
    doc_id, title, author, refs = row
    cur.execute("select content from chunks where document_id = %s "
                "order by chunk_index", (doc_id,))
    text = " ".join(r[0] for r in cur.fetchall())
    return {"id": doc_id, "title": title, "author": author,
            "n_refs": len(refs or []), "words": len(text.split()),
            "repeats": immediate_repeats(text)}


def delete_doc(cur, doc_id, url):
    """Triple-guarded delete: id AND CLF source AND a YouTube url. chunks cascade."""
    cur.execute("""
        delete from documents
        where id = %s and source_id = %s and url = %s
          and (url ilike '%%youtube%%' or url ilike '%%youtu.be%%')
    """, (doc_id, CLF_SOURCE_ID, url))
    return cur.rowcount


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--limit", type=int, help="process at most N documents")
    ap.add_argument("--url", help="process only this video url")
    args = ap.parse_args()

    ytdlp = yi.find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found")
        sys.exit(1)

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("""
        select d.url, d.title, d.author
        from documents d
        where d.source_id = %s
          and (d.url ilike '%%youtube%%' or d.url ilike '%%youtu.be%%')
        order by d.created_at
    """, (CLF_SOURCE_ID,))
    targets = cur.fetchall()

    if args.url:
        targets = [t for t in targets if t[0] == args.url]
        if not targets:
            print(f"ERROR: no CLF YouTube document found with url {args.url}")
            sys.exit(1)
    if args.limit:
        targets = targets[:args.limit]

    # removed_urls is a permanent blocklist -- never re-ingest against it.
    cur.execute("select url from removed_urls")
    blocked = {r[0] for r in cur.fetchall()}
    targets = [t for t in targets if t[0] not in blocked]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n=== CLF YouTube re-ingest [{mode}] — {len(targets)} document(s) ===\n")

    results = []
    for i, (url, title, author) in enumerate(targets, 1):
        print("-" * 72)
        print(f"[{i}/{len(targets)}] {title[:64]}")
        print(f"  {url}")

        before = fetch_doc(cur, url)
        if not before:
            print("  SKIP: no current document")
            continue
        print(f"  before: {before['words']:,} words, {before['repeats']} repeats, "
              f"{before['n_refs']} bible refs, author={before['author']!r}")

        if not args.apply:
            print("  [dry-run] would delete + re-ingest")
            continue

        n = delete_doc(cur, before["id"], url)
        if n != 1:
            conn.rollback()
            print(f"  ABORT: delete matched {n} rows (expected 1) — rolled back")
            continue
        conn.commit()
        print(f"  deleted old document {before['id']}")

        status, display, reason = yi.ingest_video(
            ytdlp, url, title, "CLF Church", dry_run=False)
        print(f"  ingest: status={status} source={display!r} ({reason})")

        after = fetch_doc(cur, url)
        conn.commit()
        if not after:
            print("  !! FAILED: no document after re-ingest — "
                  "restore from local/2026-08/clf_youtube_backup_2026-08-29.json")
            results.append((title, before["words"], 0, "FAILED"))
            continue

        ratio = after["words"] / max(before["words"], 1)
        verdict = "OK" if (ratio > 1.5 and after["repeats"] <= 5) else "CHECK"
        print(f"  after:  {after['words']:,} words ({ratio:.1f}x), "
              f"{after['repeats']} repeats, {after['n_refs']} bible refs, "
              f"author={after['author']!r}  -> {verdict}")
        results.append((title, before["words"], after["words"], verdict))

    if results:
        print("\n" + "=" * 72)
        print(f"{'document':<44}{'before':>9}{'after':>9}{'':>3}")
        print("-" * 72)
        for title, b, a, v in results:
            print(f"{title[:43]:<44}{b:>9,}{a:>9,}  {v}")
        gained = sum(a for _, _, a, _ in results) - sum(b for _, b, _, _ in results)
        print("-" * 72)
        print(f"net words recovered: {gained:+,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
