#!/usr/bin/env python3
"""
demo_ravenhill_ingest.py — Stage 3 ingest for Leonard Ravenhill rows.

Processes all status=triaged rows in the Sermonindex tab whose title contains
"leonard ravenhill", up to --limit (default: all). Reuses the established
ingest_video() path (transcript → Groq clean → embed → documents + chunks).
Writes status=done / resolved_source back to the sheet on success.

Usage:
    python3 scripts/demo_ravenhill_ingest.py            # all remaining rows
    python3 scripts/demo_ravenhill_ingest.py --limit 5  # demo: first 5 only
    python3 scripts/demo_ravenhill_ingest.py --dry-run
"""

import argparse
import sys
import time
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from youtube_ingest import (  # noqa: E402
    find_ytdlp,
    gcell,
    scell,
    ingest_video,
    QUEUE_PATH,
)
from source_resolver import SENTINEL_SOURCE_ID  # noqa: E402
from ingest import supabase  # noqa: E402

SENTINEL    = SENTINEL_SOURCE_ID
TARGET_NAME = "leonard ravenhill"
TAB         = "Sermonindex"


def _source_id_for(display_name: str) -> str:
    """Look up the source UUID for a resolved display name."""
    result = (
        supabase.table("sources")
        .select("id")
        .ilike("name", display_name)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else "unknown"


def _docs_for_url(url: str):
    """Return (doc_id, title, source_name, source_id) for a freshly-ingested URL."""
    result = (
        supabase.table("documents")
        .select("id, title, source_id")
        .eq("url", url)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    d = result.data[0]
    src = supabase.table("sources").select("name").eq("id", d["source_id"]).limit(1).execute()
    src_name = src.data[0]["name"] if src.data else "—"
    return d["id"], d["title"], src_name, d["source_id"]


def _chunk_count_for(doc_id: str) -> int:
    result = supabase.table("chunks").select("id", count="exact").eq("document_id", doc_id).execute()
    return result.count or 0


def main():
    parser = argparse.ArgumentParser(description="Ingest Leonard Ravenhill rows from Sermonindex tab")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve source only — no transcript, no DB writes")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Process at most N rows (default: 0 = all remaining)")
    args = parser.parse_args()

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found")
        sys.exit(1)

    # Find all remaining Ravenhill triaged rows, up to --limit
    wb  = openpyxl.load_workbook(str(QUEUE_PATH))
    ws  = wb[TAB]
    target_rows = []
    for r in range(2, ws.max_row + 1):
        title  = str(gcell(ws, r, "video_title") or "").strip()
        status = str(gcell(ws, r, "status") or "").strip().lower()
        url    = str(gcell(ws, r, "url") or "").strip()
        if status == "triaged" and TARGET_NAME in title.lower() and url:
            target_rows.append(r)
        if args.limit and len(target_rows) == args.limit:
            break

    if not target_rows:
        print(f"ERROR: no triaged rows matching {TARGET_NAME!r} found in tab {TAB!r}")
        sys.exit(1)

    mode = "(DRY-RUN) " if args.dry_run else ""
    print(f"\n── Ravenhill Ingest {mode}{'─' * 44}")
    print(f"  {len(target_rows)} row(s) targeted in tab {TAB!r}")

    results = []
    run_start = time.time()

    for row_idx in target_rows:
        url          = str(gcell(ws, row_idx, "url")).strip()
        video_title  = str(gcell(ws, row_idx, "video_title")).strip()
        channel_name = str(gcell(ws, row_idx, "channel_name") or "").strip()

        print(f"\n{'─' * 64}")
        print(f"  {video_title[:72]}")
        print(f"  {url}")

        t0 = time.time()
        final_status, display_name, log_reason = ingest_video(
            ytdlp, url, video_title, channel_name, dry_run=args.dry_run
        )
        elapsed = time.time() - t0

        print(f"  → status={final_status}  source={display_name!r}  ({log_reason})")
        print(f"  elapsed: {elapsed:.1f}s")

        # Post-ingest: query DB for doc details + chunk count
        doc_info   = None
        chunk_cnt  = 0
        source_uuid = "—"
        if final_status == "done":
            doc_info = _docs_for_url(url)
            if doc_info:
                doc_id, _, src_name, src_uuid = doc_info
                chunk_cnt   = _chunk_count_for(doc_id)
                source_uuid = src_uuid
                sentinel_hit = src_uuid == SENTINEL
                print(f"  doc_id={doc_id}")
                print(f"  chunks={chunk_cnt}  source={src_name!r}  uuid={src_uuid}")
                if sentinel_hit:
                    print("  ⛔  SENTINEL HIT — source resolution bug!")

        # Write status back to sheet
        if not args.dry_run and final_status in ("done", "needs_source", "failed"):
            if final_status == "done":
                scell(ws, row_idx, "status",          "done")
                scell(ws, row_idx, "resolved_source", display_name)
            elif final_status == "needs_source":
                scell(ws, row_idx, "status",          "needs_source")
                scell(ws, row_idx, "resolved_source", f"⚠ {log_reason}")
            else:
                scell(ws, row_idx, "status", "failed")
                if display_name:
                    scell(ws, row_idx, "resolved_source", display_name)
            wb.save(str(QUEUE_PATH))

        results.append({
            "row":         row_idx,
            "title":       video_title,
            "url":         url,
            "status":      final_status,
            "source":      display_name,
            "source_uuid": source_uuid,
            "log":         log_reason,
            "chunks":      chunk_cnt,
            "elapsed_s":   elapsed,
            "doc_info":    doc_info,
        })

    total_elapsed = time.time() - run_start

    # Summary
    done_count       = sum(1 for r in results if r["status"] == "done")
    failed_count     = sum(1 for r in results if r["status"] == "failed")
    needs_src_count  = sum(1 for r in results if r["status"] == "needs_source")
    sentinel_hits    = [r for r in results if r["source_uuid"] == SENTINEL and r["status"] == "done"]
    total_chunks     = sum(r["chunks"] for r in results)
    caption_count    = sum(1 for r in results if "method=captions" in r["log"])
    whisper_count    = sum(1 for r in results if "method=whisper" in r["log"])

    print(f"\n{'═' * 64}")
    print("RAVENHILL INGEST SUMMARY")
    print(f"{'═' * 64}")
    print(f"  Videos processed : {len(results)}")
    print(f"  Done             : {done_count}")
    print(f"  Failed           : {failed_count}")
    print(f"  Needs source     : {needs_src_count}")
    print(f"  Sentinel hits    : {len(sentinel_hits)}")
    print(f"  Total chunks     : {total_chunks}")
    print(f"  Captions used    : {caption_count}")
    print(f"  Whisper used     : {whisper_count}")
    print(f"  Total elapsed    : {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")

    if sentinel_hits or needs_src_count:
        print(f"\n⛔  WARNING: {len(sentinel_hits)} sentinel hit(s), {needs_src_count} needs_source row(s)")
    else:
        print(f"\n✓  Zero sentinel / zero unresolved — all {done_count} resolved correctly.")


if __name__ == "__main__":
    main()
