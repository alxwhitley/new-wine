#!/usr/bin/env python3
"""
youtube_ingest.py — Stage 3: ingest pass for the unified YouTube ingest pipeline.

Reads sources/youtube/ingest_queue.xlsx. For each row where ingest=TRUE AND
status=triaged:

  1. Resolve source via source_resolver (channel_name → alias lookup).
     Sentinel hit → status=needs_source, skip (no unattributed content).
  2. Fetch transcript: yt-dlp auto-captions first, Whisper-medium fallback.
  3. Clean via Groq (same CLEANING_PROMPT as scrape_individual_videos.py).
  4. Write temp .txt to sources/youtube/cleaned/ with correct metadata headers.
  5. Call ingest_file() directly (same path as all other documents):
       - chunk → embed → document row → chunks table
       - propositions (auto-fires for unlicensed sources)
       - topic tagging (Groq)
  6. Delete temp .txt; write status=done in sheet.

Idempotent: rows with status != "triaged" are skipped.
One bad video never kills the run — exceptions captured as status=failed.

Sheet: sources/youtube/ingest_queue.xlsx
Columns: url | video_title | channel_name | guess | ingest | status | resolved_source

Usage:
    python3 scripts/youtube_ingest.py              # process all ticked rows
    python3 scripts/youtube_ingest.py --limit 2    # demo: process first N rows only
    python3 scripts/youtube_ingest.py --dry-run    # resolve sources only, no writes
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# scripts/ must be in sys.path before heavy imports so that ingest, propositions,
# source_resolver, taxonomy, bible_refs etc. all resolve correctly.
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Heavy imports — after load_dotenv and sys.path setup
from ingest import ingest_file, embed_text, DB_PARAMS, supabase  # noqa: E402
from scrape_individual_videos import (  # noqa: E402
    find_ytdlp, try_auto_captions, download_and_whisper, clean_transcript,
)
from source_resolver import resolve_source_id, SENTINEL_SOURCE_ID  # noqa: E402

QUEUE_PATH   = ROOT / "sources" / "youtube" / "ingest_queue.xlsx"
CLEANED_DIR  = ROOT / "sources" / "youtube" / "cleaned"
COOKIES_PATH = ROOT / "scripts" / "youtube_cookies.txt"

COLUMNS = ["url", "video_title", "channel_name", "guess", "ingest", "status", "resolved_source"]
COL     = {name: i + 1 for i, name in enumerate(COLUMNS)}


# ── Sheet helpers ─────────────────────────────────────────────────────────────

def gcell(ws, row_idx: int, col_name: str):
    return ws.cell(row=row_idx, column=COL[col_name]).value


def scell(ws, row_idx: int, col_name: str, value) -> None:
    ws.cell(row=row_idx, column=COL[col_name], value=value)


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from watch?v= or youtu.be/ URL."""
    parsed = urlparse(url.strip())
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/").split("?")[0]
    return re.sub(r"[^\w]", "", url)[-16:]


def _slugify(title: str, max_len: int = 50) -> str:
    s = re.sub(r"[^\w\s]", "", title.lower())
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len].rstrip("_")


def _extract_speaker(title: str) -> str:
    """Best-effort speaker extraction from a video title.
    Handles patterns like 'by Sam Storms', '| Sam Storms', '- Michael Rowntree'.
    Returns '' if not found.
    """
    # "by Firstname Lastname" — most common in Convergence titles
    m = re.search(r"\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", title)
    if m:
        return m.group(1)
    # "- Firstname Lastname" or "| Firstname Lastname" at end
    m = re.search(r"[|\-—]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*(?:[|\-]|$)", title)
    if m:
        return m.group(1)
    return ""


def _write_transcript_file(
    path: Path,
    title: str,
    speaker: str,
    channel: str,
    url: str,
    cleaned: str,
) -> None:
    header = (
        "TITLE: {}\n"
        "SPEAKER: {}\n"
        "CHANNEL: {}\n"
        "SOURCE: {}\n"
        "URL: {}\n"
        "SOURCE_URL: {}\n"
        "PUBLISHED: NA\n"
        "DURATION_MIN: 0.0\n"
        "SOURCE_TYPE: sermon\n"
        "---\n\n"
    ).format(title, speaker, channel, channel, url, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + cleaned, encoding="utf-8")


_NA_VALUES = {"na", "none", "null", ""}


def _resolve_channel_name(ytdlp: str, url: str, channel_name: str) -> str:
    """If channel_name is missing or 'NA', fetch the real name from yt-dlp.
    Falls back to the original value if yt-dlp also returns nothing useful.
    """
    if channel_name.strip().lower() not in _NA_VALUES:
        return channel_name

    # yt-dlp single-video metadata fetch — no download
    cmd = [ytdlp, "-4", "--extractor-args", "youtube:player_client=android_vr,web_safari"]
    if COOKIES_PATH.exists():
        cmd += ["--cookies", str(COOKIES_PATH)]
    cmd += ["--flat-playlist", "--print", "%(channel)s", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return channel_name

    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and line.lower() not in _NA_VALUES:
            return line
    return channel_name


def _get_source_display_name(source_id: str) -> Optional[str]:
    try:
        result = (
            supabase.table("sources")
            .select("name")
            .eq("id", source_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["name"]
    except Exception:
        pass
    return None


# ── Per-video ingest ──────────────────────────────────────────────────────────

def ingest_video(
    ytdlp: str,
    url: str,
    video_title: str,
    channel_name: str,
    dry_run: bool = False,
) -> Tuple[str, str, str]:
    """
    Ingest one video end-to-end.

    Returns (status, resolved_source_display, log_reason).
    status is one of: "done" | "failed" | "needs_source" | "dry_run".
    Never raises — all exceptions captured and returned as ("failed", ..., reason).
    """

    # ── 1. Source resolution ──────────────────────────────────────────────────
    # channel_name may be "NA" when yt-dlp flat-playlist couldn't return it.
    # Fetch the real channel name from the video before trying alias lookup.
    if channel_name.strip().lower() in _NA_VALUES:
        print("  channel name is NA — fetching from yt-dlp...")
        channel_name = _resolve_channel_name(ytdlp, url, channel_name)
        print("    resolved channel: {!r}".format(channel_name))

    try:
        source_id, norm_key, via = resolve_source_id(supabase, channel_name, None)
    except Exception as exc:
        return "failed", "", "source resolution error: {}".format(exc)

    if source_id == SENTINEL_SOURCE_ID:
        return "needs_source", "", "no alias match for {!r}".format(channel_name)

    display_name = _get_source_display_name(source_id) or channel_name
    print("  source: {!r} → {!r} (via {})".format(norm_key, display_name, via))

    if dry_run:
        return "dry_run", display_name, "dry_run"

    # ── 2. Transcript fetch ───────────────────────────────────────────────────
    raw_text = None
    method = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("  transcript: trying auto-captions...")
        raw_text = try_auto_captions(ytdlp, url, tmp_dir)
        if raw_text:
            method = "captions"
            print("    {:,} words from captions".format(len(raw_text.split())))

    if not raw_text:
        print("  transcript: no captions — falling back to Whisper medium...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                raw_text = download_and_whisper(ytdlp, url, tmp_dir)
                if raw_text:
                    method = "whisper"
                    print("    {:,} words from Whisper".format(len(raw_text.split())))
            except Exception as exc:
                return "failed", display_name, "Whisper error: {}".format(exc)

    if not raw_text:
        return "failed", display_name, "no captions and Whisper returned nothing"

    # ── 3. Groq clean ─────────────────────────────────────────────────────────
    print("  cleaning via Groq ({:,} words, method={})...".format(len(raw_text.split()), method))
    try:
        cleaned = clean_transcript(raw_text)
        print("    {:,} words after cleaning".format(len(cleaned.split())))
    except Exception as exc:
        return "failed", display_name, "Groq clean error: {}".format(exc)

    # ── 4. Write temp .txt ────────────────────────────────────────────────────
    video_id = extract_video_id(url)
    fname    = "{}_{}.txt".format(video_id, _slugify(video_title))
    tmp_path = CLEANED_DIR / fname
    speaker  = _extract_speaker(video_title)
    _write_transcript_file(tmp_path, video_title, speaker, channel_name, url, cleaned)
    print("  wrote: {}  (speaker={!r})".format(fname, speaker or "—"))

    # ── 5. Ingest through the full pipeline ───────────────────────────────────
    ingest_status = None
    ingest_reason = None
    try:
        ingest_status, ingest_reason = ingest_file(tmp_path, is_copyrighted=True, skip_dedup=True)
    except Exception as exc:
        ingest_status = "error"
        ingest_reason = str(exc)
    finally:
        tmp_path.unlink(missing_ok=True)

    if ingest_status in ("processed", "skipped"):
        return "done", display_name, "method={}, ingest={}".format(method, ingest_status)
    else:
        return "failed", display_name, "ingest_file: {}/{}".format(ingest_status, ingest_reason)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube ingest — Stage 3 of the unified ingest pipeline"
    )
    parser.add_argument("--limit",   metavar="N", type=int,
                        help="Process at most N rows (use 2-3 for demo)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve sources only — no transcript fetch, no DB writes")
    args = parser.parse_args()

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found. Run: pip3 install yt-dlp")
        sys.exit(1)

    if not QUEUE_PATH.exists():
        print("ERROR: queue not found at {}".format(QUEUE_PATH))
        sys.exit(1)

    wb = openpyxl.load_workbook(QUEUE_PATH)
    ws = wb.active

    # Collect eligible rows: ingest=TRUE AND status=triaged
    candidates = []
    for r in range(2, ws.max_row + 1):
        ingest_val = str(gcell(ws, r, "ingest") or "").strip().upper()
        status_val = str(gcell(ws, r, "status") or "").strip().lower()
        url_val    = str(gcell(ws, r, "url") or "").strip()
        title_val  = str(gcell(ws, r, "video_title") or "").strip()
        if ingest_val == "TRUE" and status_val == "triaged" and url_val and title_val:
            candidates.append(r)

    if args.limit:
        candidates = candidates[: args.limit]

    mode = "(DRY-RUN) " if args.dry_run else ""
    print("\n── Stage 3: YouTube Ingest {}──────────────────────────────────".format(mode))
    print("  {} row(s) to process".format(len(candidates)))

    stats = {"done": 0, "failed": 0, "needs_source": 0}

    for row_idx in candidates:
        url          = str(gcell(ws, row_idx, "url")).strip()
        video_title  = str(gcell(ws, row_idx, "video_title")).strip()
        channel_name = str(gcell(ws, row_idx, "channel_name") or "").strip()

        print("\n{}".format("─" * 64))
        print("  {}".format(video_title[:72]))
        print("  {}".format(url))

        try:
            final_status, display_name, log_reason = ingest_video(
                ytdlp, url, video_title, channel_name, dry_run=args.dry_run
            )
        except Exception as exc:
            final_status = "failed"
            display_name = ""
            log_reason   = "unhandled: {}".format(exc)

        if final_status == "dry_run":
            print("  [DRY-RUN] would ingest → source: {!r}".format(display_name))
            continue

        print("  → status={}  source={!r}  ({})".format(final_status, display_name, log_reason))
        stats[final_status] = stats.get(final_status, 0) + 1

        if not args.dry_run:
            if final_status == "done":
                scell(ws, row_idx, "status",          "done")
                scell(ws, row_idx, "resolved_source", display_name)
            elif final_status == "needs_source":
                scell(ws, row_idx, "status",          "needs_source")
                scell(ws, row_idx, "resolved_source", "⚠ {}".format(log_reason))
            else:
                scell(ws, row_idx, "status", "failed")
                if display_name:
                    scell(ws, row_idx, "resolved_source", display_name)
            wb.save(QUEUE_PATH)

    print("\n── Results ──────────────────────────────────────────────────────")
    print("  done:         {}".format(stats.get("done", 0)))
    print("  failed:       {}".format(stats.get("failed", 0)))
    print("  needs_source: {}".format(stats.get("needs_source", 0)))


if __name__ == "__main__":
    main()
