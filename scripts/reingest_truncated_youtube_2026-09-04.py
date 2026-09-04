#!/usr/bin/env python3.12
"""
reingest_truncated_youtube_2026-09-04.py — rebuild YouTube sermon documents
whose stored text holds materially less than the speaker actually said.

Background: measured 2026-09-04 by re-fetching every pre-fix video's real json3
captions and comparing word counts against the stored document. Of 303
verifiable pre-fix documents, 14 store under 55% of what was said and 65 store
55-80%. The 80-90% band is consistent with correct filler removal and is NOT
treated as a defect here, so the target set is strictly `kept < 0.80`.

WHY THIS IS NOT THE CLF SCRIPT (reingest_clf_youtube_2026-08-29.py):
CLF Church is an `owned` source, so its documents carry ZERO propositions and a
plain `delete from documents` cascaded cleanly. Every source in this target set
is `unlicensed`, so these 79 documents carry 686 propositions and 1,552
proposition_chunks rows. Two RESTRICT constraints therefore stand in the way
and must be cleared deliberately, in order, or the delete simply fails:

  proposition_chunks.chunk_id  -> chunks       ON DELETE RESTRICT
  position_evidence.proposition_id -> propositions ON DELETE RESTRICT

The second is the real one: 18 evidence rows across 4 CURRENT stored positions
cite propositions extracted from truncated text. Those rows are deleted here
and the affected positions are REPORTED for rebuild -- this script never
rebuilds a position itself (scripts/positions.py owns that, and per Settled #22
a rebuild versions rather than overwrites).

Deletes go through direct SQL on purpose, NOT DELETE /admin/document/{id} --
that endpoint writes to removed_urls, which youtube_ingest.py treats as a
permanent blocklist and would refuse to re-ingest against.

Re-ingest calls youtube_ingest.ingest_video() PER URL. It never touches
sources/youtube/ingest_queue.xlsx, so it cannot trigger the 731 untriaged
Sermonindex / Philip Anthony Mitchell / Gabriel Heights rows that a bare
run_queue_ingest.py would.

Every document is backed up (text + metadata + propositions) BEFORE any delete.

Dry-run by default. --apply is required to write.

Usage:
    python3.12 scripts/reingest_truncated_youtube_2026-09-04.py                       # dry run, all 79
    python3.12 scripts/reingest_truncated_youtube_2026-09-04.py --doc-id UUID --apply # single-doc proof
    python3.12 scripts/reingest_truncated_youtube_2026-09-04.py --limit 5 --apply
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg2  # noqa: E402

import youtube_ingest as yi  # noqa: E402

MANIFEST = ROOT / "local" / "2026-09" / "truncated_youtube_targets_2026-09-04.json"
BACKUP_DIR = ROOT / "local" / "2026-09"
KEPT_CEILING = 0.80


def connect():
    return psycopg2.connect(os.environ["SUPABASE_DB_URL"])


def load_targets():
    """The frozen target list. Built read-only by the 2026-09-04 measurement."""
    if not MANIFEST.exists():
        sys.exit("ERROR: target manifest missing: %s" % MANIFEST)
    data = json.loads(MANIFEST.read_text())
    rows = [r for r in data["targets"] if r["kept"] < KEPT_CEILING]
    return data, rows


def doc_state(cur, doc_id):
    """Current stored state of one document. None if absent."""
    cur.execute("""
        select d.id::text, d.title, d.author, d.url, d.source_id::text,
               coalesce(array_length(d.bible_references, 1), 0)
        from documents d where d.id = %s
    """, (doc_id,))
    row = cur.fetchone()
    if not row:
        return None
    # Word count comes from documents.full_text, NEVER from concatenated chunks:
    # chunks overlap (chunk_target=550, overlap=80), so summing them inflates the
    # text by ~17% (CLAUDE.md YouTube-verification trap 1).
    cur.execute("select coalesce(full_text, '') from documents where id = %s", (doc_id,))
    full_text = cur.fetchone()[0]
    cur.execute("select count(*) from chunks where document_id = %s", (doc_id,))
    n_chunks = cur.fetchone()[0]
    cur.execute("select count(*) from propositions where document_id = %s", (doc_id,))
    n_props = cur.fetchone()[0]
    return {
        "id": row[0], "title": row[1], "author": row[2], "url": row[3],
        "source_id": row[4], "n_refs": row[5],
        "n_chunks": n_chunks, "words": len(full_text.split()),
        "n_props": n_props, "full_text": full_text,
    }


def find_by_url(cur, url):
    """Documents at this url. documents.url has NO unique constraint, so this
    deliberately returns a list -- more than one means a duplicate already
    exists and the caller must not proceed blindly."""
    cur.execute("select id::text from documents where url = %s", (url,))
    return [r[0] for r in cur.fetchall()]


def affected_positions(cur, doc_ids):
    cur.execute("""
        select pos.id::text, pos.topic, pos.kind, pos.is_current,
               count(*) filter (where p.document_id = any(%s::uuid[])) at_risk,
               count(*) total_ev
        from positions pos
        join position_evidence pe on pe.position_id = pos.id
        join propositions p on p.id = pe.proposition_id
        where pos.id in (
            select distinct pe2.position_id from position_evidence pe2
            join propositions p2 on p2.id = pe2.proposition_id
            where p2.document_id = any(%s::uuid[])
        )
        group by 1,2,3,4 order by at_risk desc
    """, (doc_ids, doc_ids))
    return cur.fetchall()


def backup(cur, targets):
    """Full text + metadata + propositions for every target, before any delete."""
    out = []
    for t in targets:
        st = doc_state(cur, t["id"])
        if not st:
            continue
        cur.execute("select id::text, content from propositions where document_id = %s", (t["id"],))
        st["propositions"] = [{"id": r[0], "content": r[1]} for r in cur.fetchall()]
        st["measured_kept"] = t["kept"]
        out.append(st)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = BACKUP_DIR / ("truncated_youtube_backup_%s.json" % stamp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"created": stamp, "documents": out}, indent=2))
    return path, len(out)


def pending_evidence(cur, doc_ids):
    """Evidence rows citing propositions from truncated text, recorded so the
    affected positions can be rebuilt afterwards. Read-only."""
    cur.execute("""
        select pe.position_id::text, pe.proposition_id::text, p.document_id::text
        from position_evidence pe
        join propositions p on p.id = pe.proposition_id
        where p.document_id = any(%s::uuid[])
    """, (doc_ids,))
    return cur.fetchall()


def restore_author(cur, doc_id, prior_author):
    """Put back an author the re-ingest dropped -- narrowly, and only when the
    prior value is corroborated by the source's own name.

    Why this is needed: `_verified_speaker()` (youtube_ingest.py, added by the
    2026-08-31 speaker audit) only records a speaker as `documents.author` when
    the title itself yields one. These titles mostly do not ("Cessationism 8"),
    so a re-ingest silently nulls an author that the June/July ingests had set.
    Proven live on the first proof document: 'Daniel Kolenda' -> None.

    Why that matters even though attribution still grounds: the source-id arm of
    `build_retrieval_grounding` covers the name (every teacher here has a
    matching `source_aliases` row), so this is NOT a grounding hole. But
    `producer.py` builds `permitted_names` from `documents.author` ALONE, so a
    null author silently switches off the single-author naming contract
    (`_missing_required_single_author` / the deterministic `Source voice`
    label, `ec42398`) for that document.

    Why it is safe: the restore fires only when the prior author string equals
    the source's own name exactly. It therefore re-asserts nothing new, and it
    cannot reintroduce the CLF-class defects (comma-joined authors, or a
    title-derived artifact like 'Sunday'), which by construction never equal
    their source name.
    """
    if not prior_author:
        return False
    cur.execute("""
        update documents d
        set author = %s
        from sources s
        where d.id = %s and s.id = d.source_id
          and d.author is null
          and btrim(s.name) = btrim(%s)
    """, (prior_author, doc_id, prior_author))
    return cur.rowcount == 1


def delete_doc(cur, doc_id, url, source_id):
    """Remove one document and everything hanging off it, in dependency order.

    The order is forced by two RESTRICT constraints and is NOT optional. A plain
    single-statement removal of the document row raises ForeignKeyViolation on
    proposition_chunks_chunk_id_fkey -- proven live 2026-09-04, rolled back with
    nothing lost. The CLF precedent never hit this because CLF Church is an
    `owned` source whose documents carry zero propositions.

      1. position_evidence -> propositions   RESTRICT  (must clear first)
      2. propositions      -> cascades proposition_chunks, which is the thing
                              RESTRICTing chunks
      3. documents         -> cascades chunks, now unreferenced

    Returns (n_evidence, n_propositions, n_documents). The caller commits.
    """
    cur.execute("""
        delete from position_evidence pe
        using propositions p
        where p.id = pe.proposition_id and p.document_id = %s
    """, (doc_id,))
    n_ev = cur.rowcount
    cur.execute("delete from propositions where document_id = %s", (doc_id,))
    n_props = cur.rowcount
    # Triple-guarded: id AND its own source AND a YouTube url.
    cur.execute("""
        delete from documents
        where id = %s and source_id = %s and url = %s
          and (url ilike '%%youtube%%' or url ilike '%%youtu.be%%')
    """, (doc_id, source_id, url))
    return n_ev, n_props, cur.rowcount


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--limit", type=int, help="process at most N documents")
    ap.add_argument("--doc-id", help="process only this document id")
    args = ap.parse_args()

    ytdlp = yi.find_ytdlp()
    if not ytdlp:
        sys.exit("ERROR: yt-dlp not found")

    meta, targets = load_targets()
    if args.doc_id:
        targets = [t for t in targets if t["id"] == args.doc_id]
        if not targets:
            sys.exit("ERROR: %s is not in the target manifest" % args.doc_id)
    if args.limit:
        targets = targets[:args.limit]

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    # removed_urls is a permanent blocklist -- never re-ingest against it.
    cur.execute("select url from removed_urls")
    blocked = {r[0] for r in cur.fetchall()}
    skipped_blocked = [t for t in targets if t["url"] in blocked]
    targets = [t for t in targets if t["url"] not in blocked]

    doc_ids = [t["id"] for t in targets]
    mode = "APPLY" if args.apply else "DRY-RUN"
    print("\n=== truncated YouTube re-ingest [%s] — %d document(s) ===" % (mode, len(targets)))
    print("    measurement: %s" % meta.get("measured"))
    if skipped_blocked:
        print("    %d skipped, url in removed_urls (permanent blocklist)" % len(skipped_blocked))

    pos = affected_positions(cur, doc_ids)
    if pos:
        print("\n    stored positions citing this evidence (rebuild after, never here):")
        for pid, topic, kind, is_cur, at_risk, total in pos:
            print("      %-40s %-8s current=%-5s  %d of %d evidence rows"
                  % (topic[:40], kind, is_cur, at_risk, total))

    # Pre-flight: refuse if a duplicate already exists at any target url.
    dupes = [(t["url"], find_by_url(cur, t["url"])) for t in targets]
    dupes = [(u, ids) for u, ids in dupes if len(ids) > 1]
    if dupes:
        print("\n    ABORT: %d url(s) already resolve to more than one document." % len(dupes))
        for u, ids in dupes[:5]:
            print("      %s -> %s" % (u, ids))
        sys.exit(1)

    if not args.apply:
        print("\n    [dry-run] would back up, clear %d evidence row(s), then per document:"
              % sum(r[4] for r in pos))
        print("    delete -> re-ingest from real captions -> verify word count rose\n")
        print("    %-42s %8s %8s %6s" % ("document", "stored", "real", "kept"))
        for t in targets[:80]:
            print("    %-42s %8d %8d %5.0f%%"
                  % (t["title"][:42], t["words"], t["real_words"], 100 * t["kept"]))
        exp_now = sum(t["words"] for t in targets)
        exp_after = sum(t["real_words"] for t in targets)
        print("    %-42s %8d %8d" % ("TOTAL", exp_now, exp_after))
        print("\n    expected recovery: +{:,} words ({:.2f}x)".format(exp_after - exp_now, exp_after / exp_now))
        cur.close(); conn.close()
        return

    path, n = backup(cur, targets)
    print("\n    backed up %d document(s) -> %s" % (n, path))

    # Record which evidence rows are about to go, so the affected positions can be
    # rebuilt afterwards. The removals themselves happen per document, inside that
    # document's own transaction -- a mid-run failure must never leave evidence
    # cleared for a document that was never rebuilt.
    ev_rows = pending_evidence(cur, doc_ids)
    (BACKUP_DIR / "cleared_position_evidence_2026-09-04.json").write_text(
        json.dumps([{"position_id": a, "proposition_id": b, "document_id": c}
                    for a, b, c in ev_rows], indent=2))
    print("    %d position_evidence row(s) recorded for rebuild" % len(ev_rows))

    stats = {"ok": 0, "check": 0, "failed": 0, "skipped": 0}
    results = []
    for i, t in enumerate(targets, 1):
        print("-" * 72)
        print("[%d/%d] %s" % (i, len(targets), t["title"][:60]))
        before = doc_state(cur, t["id"])
        if not before:
            print("  SKIP: document no longer present"); stats["skipped"] += 1; continue
        print("  before: {:,} words, {} chunks, {} propositions".format(
            before["words"], before["n_chunks"], before["n_props"]))

        try:
            n_ev, n_props, n = delete_doc(cur, before["id"], before["url"], before["source_id"])
        except Exception as exc:
            conn.rollback()
            print("  ABORT: removal raised (%s) — rolled back, nothing removed" % exc)
            stats["failed"] += 1; results.append((t["title"], before["words"], 0, "DELETE-FAILED")); continue
        if n != 1:
            conn.rollback()
            print("  ABORT: matched %d document rows (expected 1) — rolled back" % n)
            stats["failed"] += 1; results.append((t["title"], before["words"], 0, "DELETE-FAILED")); continue
        conn.commit()
        print("  removed: 1 document, %d propositions, %d position_evidence rows"
              % (n_props, n_ev))

        status, display, reason = yi.ingest_video(
            ytdlp, before["url"], before["title"], t["channel_name"], dry_run=False)
        print("  ingest: status=%s source=%r (%s)" % (status, display, reason))

        new_ids = find_by_url(cur, before["url"])
        conn.commit()
        if len(new_ids) != 1:
            print("  !! FAILED: %d documents at this url after re-ingest — restore from %s"
                  % (len(new_ids), path))
            stats["failed"] += 1; results.append((t["title"], before["words"], 0, "FAILED")); continue
        restored = restore_author(cur, new_ids[0], before["author"])
        if restored:
            conn.commit()
            print("  author restored: %r (re-ingest left it null)" % before["author"])
        after = doc_state(cur, new_ids[0])
        ratio = after["words"] / max(before["words"], 1)
        verdict = "OK" if ratio >= 1.15 else "CHECK"
        stats["ok" if verdict == "OK" else "check"] += 1
        print("  after:  {:,} words ({:.2f}x), {} chunks, {} propositions  -> {}".format(
            after["words"], ratio, after["n_chunks"], after["n_props"], verdict))
        results.append((t["title"], before["words"], after["words"], verdict))

    print("\n" + "=" * 72)
    print("%-44s%9s%9s" % ("document", "before", "after"))
    print("-" * 72)
    for title, b, a, v in results:
        print("%-44s%9s%9s  %s" % (title[:43], "{:,}".format(b), "{:,}".format(a), v))
    print("-" * 72)
    print("RECONCILIATION  attempted={} ok={} check={} failed={} skipped={}".format(
        len(targets), stats["ok"], stats["check"], stats["failed"], stats["skipped"]))
    print("net words recovered: {:+,}".format(
        sum(a for _, _, a, _ in results) - sum(b for _, b, _, _ in results)))
    if pos:
        print("\nSTILL TO DO — rebuild these positions via scripts/positions.py:")
        for pid, topic, kind, is_cur, at_risk, total in pos:
            if is_cur:
                print("  %s (%s)" % (topic, kind))

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
