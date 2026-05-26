#!/usr/bin/env python3
"""
scrape_channel_titles.py — Dump all video titles from YouTube channels into a CSV.
Uses yt-dlp --flat-playlist to get titles without downloading anything.

Usage:
  python3 scripts/scrape_channel_titles.py              # all channels
  python3 scripts/scrape_channel_titles.py --channel "Derek Prince"  # single channel
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_CSV = ROOT / "sources" / "channel_titles.csv"
COOKIES_PATH = ROOT / "scripts" / "youtube_cookies.txt"

CHANNELS = [
    {"name": "Jesus Image", "url": "https://www.youtube.com/@JesusImage"},
    {"name": "Bethel Music", "url": "https://www.youtube.com/@BethelMusic"},
    {"name": "Mercy Culture", "url": "https://www.youtube.com/@MercyCulture"},
    {"name": "Daniel Kolenda", "url": "https://www.youtube.com/@TheDanielKolendaShow"},
    {"name": "Derek Prince", "url": "https://www.youtube.com/@DerekPrinceMinistries"},
]


def find_ytdlp():
    candidates = [
        shutil.which("yt-dlp"),
        os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp"),
        os.path.expanduser("~/Library/Python/3.10/bin/yt-dlp"),
        os.path.expanduser("~/Library/Python/3.11/bin/yt-dlp"),
        os.path.expanduser("~/Library/Python/3.12/bin/yt-dlp"),
        os.path.expanduser("~/.local/bin/yt-dlp"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def scrape_titles(ytdlp, channel_url):
    cmd = [
        ytdlp, "-4",
        "--extractor-args", "youtube:player_client=android_vr,web_safari",
    ]
    if COOKIES_PATH.exists():
        cmd += ["--cookies", str(COOKIES_PATH)]
    cmd += ["--flat-playlist", "--print", "title", channel_url]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    titles = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not titles and result.returncode != 0:
        # Show YouTube-specific errors, not urllib3 warnings
        err_lines = [l for l in result.stderr.splitlines() if "ERROR" in l or "not found" in l.lower()]
        msg = err_lines[0] if err_lines else result.stderr.strip()[:300]
        raise RuntimeError(msg)
    return titles


def main():
    parser = argparse.ArgumentParser(description="Scrape YouTube channel video titles to CSV")
    parser.add_argument("--channel", help="Run a single channel by name (case-insensitive)")
    args = parser.parse_args()

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found. Run: pip3 install yt-dlp")
        sys.exit(1)

    channels = CHANNELS
    if args.channel:
        match = [c for c in CHANNELS if c["name"].lower() == args.channel.lower()]
        if not match:
            names = ", ".join(c["name"] for c in CHANNELS)
            print("ERROR: Channel '{}' not found. Available: {}".format(args.channel, names))
            sys.exit(1)
        channels = match

    print("yt-dlp:  {}".format(ytdlp))
    print("Output:  {}".format(OUTPUT_CSV))
    print("Channels: {}\n".format(len(channels)))

    all_rows = []

    for ch in channels:
        print("{} ...".format(ch["name"]), end=" ", flush=True)
        try:
            titles = scrape_titles(ytdlp, ch["url"])
            print("{} titles".format(len(titles)))
            for t in titles:
                all_rows.append((ch["name"], t))
        except Exception as e:
            print("FAILED: {}".format(str(e)[:200]))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["channel_name", "video_title"])
        writer.writerows(all_rows)

    print("\nWrote {} titles to {}".format(len(all_rows), OUTPUT_CSV))


if __name__ == "__main__":
    main()
