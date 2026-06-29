#!/usr/bin/env python3
"""
demo_ravenhill_ingest.py — Stage 3 demo: ingest the first 5 Leonard Ravenhill
triaged rows from the Sermonindex tab.

Reuses the established ingest_video() path (transcript → Groq clean → embed →
documents + chunks rows). Writes status=done / resolved_source back to the
sheet on success. Reports captions vs. Whisper, chunk count, elapsed time, and
source UUID for each video.

Usage:
    python3 scripts/demo_ravenhill_ingest.py
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

SENTINEL = SENTINEL_SOURCE_ID
TARGET_NAME = "leonard ravenhill"
DEMO_LIMIT  = 5
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
    parser = argparse.ArgumentParser(description="Demo: ingest first 5 Leonard Ravenhill rows")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve source only — no transcript, no DB writes")
    args = parser.parse_args()

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found")
        sys.exit(1)

    # Find the first DEMO_LIMIT Ravenhill triaged rows
    wb  = openpyxl.load_workbook(str(QUEUE_PATH))
    ws  = wb[TAB]
    target_rows = []
    for r in range(2, ws.max_row + 1):
        title  = str(gcell(ws, r, "video_title") or "").strip()
        status = str(gcell(ws, r, "status") or "").strip().lower()
        url    = str(gcell(ws, r, "url") or "").strip()
        if status == "triaged" and TARGET_NAME in title.lower() and url:
            target_rows.append(r)
        if len(target_rows) == DEMO_LIMIT:
            break

    if not target_rows:
        print(f"ERROR: no triaged rows matching {TARGET_NAME!r} found in tab {TAB!r}")
        sys.exit(1)

    mode = "(DRY-RUN) " if args.dry_run else ""
    print(f"\n── Ravenhill Demo Ingest {mode}{'─' * 40}")
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
    print(f"\n{'═' * 64}")
    print("DEMO INGEST SUMMARY")
    print(f"{'═' * 64}")
    sentinel_hits = [r for r in results if r["source_uuid"] == SENTINEL and r["status"] == "done"]
    print(f"  Videos processed : {len(results)}")
    print(f"  Done             : {sum(1 for r in results if r['status'] == 'done')}")
    print(f"  Failed           : {sum(1 for r in results if r['status'] == 'failed')}")
    print(f"  Needs source     : {sum(1 for r in results if r['status'] == 'needs_source')}")
    print(f"  Sentinel hits    : {len(sentinel_hits)}")
    print(f"  Total elapsed    : {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    print()

    caption_count = sum(1 for r in results if "method=captions" in r["log"])
    whisper_count = sum(1 for r in results if "method=whisper" in r["log"])
    print(f"  Captions used    : {caption_count}")
    print(f"  Whisper used     : {whisper_count}")
    print()

    print(f"{'─' * 64}")
    print(f"  {'doc_id':<36}  {'title':<40}  {'source':<22}  chunks")
    print(f"{'─' * 64}")
    for r in results:
        if r["doc_info"]:
            doc_id, title, src_name, src_uuid = r["doc_info"]
            sentinel_flag = " ⛔SENTINEL" if src_uuid == SENTINEL else ""
            print(f"  {doc_id:<36}  {title[:38]:<40}  {src_name:<22}  {r['chunks']}{sentinel_flag}")
        else:
            print(f"  {'—':<36}  {r['title'][:38]:<40}  {r['status']}")

    if sentinel_hits:
        print(f"\n⛔  {len(sentinel_hits)} SENTINEL HIT(S) — STOP before full run!")
    else:
        print(f"\n✓  Zero sentinel hits — all {len([r for r in results if r['status']=='done'])} resolved correctly.")


if __name__ == "__main__":
    main()
