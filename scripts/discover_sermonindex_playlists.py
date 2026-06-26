#!/usr/bin/env python3
"""
discover_sermonindex_playlists.py — Discovery-only tool.

Enumerates the per-speaker playlists on the SermonIndex YouTube channel
(/playlists tab), matches them against the 13 whitelisted speaker names,
and prints a match table for review.

Prints ONLY. No workbook writes, no Queue rows, no triage, no ingest.

Usage:
    python3 scripts/discover_sermonindex_playlists.py
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT    = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from source_resolver import normalize_alias_key   # noqa: E402
from youtube_triage import find_ytdlp             # noqa: E402

PLAYLISTS_URL  = "https://www.youtube.com/@sermonindex/playlists"
WHITELIST_FILE = SCRIPTS / "whitelist_sermonindex.txt"
COOKIES_PATH   = SCRIPTS / "youtube_cookies.txt"
TIMEOUT_SECS   = 120

# Canonical names for the 13 speakers — used for the "missing" report.
CANONICAL_NAMES = [
    "David Wilkerson",
    "Carter Conlon",
    "Smith Wigglesworth",
    "Kathryn Kuhlman",
    "Duncan Campbell",
    "Frank Bartleman",
    "Zac Poonen",
    "Leonard Ravenhill",
    "A.W. Tozer",
    "Keith Green",
    "Paris Reidhead",
    "Art Katz",
    "T. Austin-Sparks",
]

# Map alias variants back to canonical for clean output.
_VARIANT_TO_CANONICAL: Dict[str, str] = {
    "AW Tozer":        "A.W. Tozer",
    "A W Tozer":       "A.W. Tozer",
    "T Austin-Sparks": "T. Austin-Sparks",
    "Austin-Sparks":   "T. Austin-Sparks",
}

_NA = {"na", "none", "null", ""}


def _canonical(name: str) -> str:
    return _VARIANT_TO_CANONICAL.get(name, name)


def _match_playlist(playlist_title: str, wl_entries: List[str]) -> Optional[str]:
    """Return the first whitelist entry that matches the playlist title, or None.
    Uses normalize_alias_key + period-strip fallback for Tozer/Austin-Sparks variants.
    """
    norm_title        = normalize_alias_key(playlist_title)
    norm_title_nodots = norm_title.replace(".", "")
    for name in wl_entries:
        norm_name = normalize_alias_key(name)
        if not norm_name:
            continue
        if norm_name in norm_title:
            return name
        if norm_name.replace(".", "") in norm_title_nodots:
            return name
    return None


def enumerate_playlists(ytdlp: str) -> Optional[List[Tuple[str, str, Optional[int]]]]:
    """
    Flat-enumerate playlists from SermonIndex /playlists tab via yt-dlp.
    Returns list of (playlist_id, title, n_entries|None), or None on timeout.
    """
    cmd = [ytdlp, "-4", "--extractor-args", "youtube:player_client=android_vr,web_safari"]
    if COOKIES_PATH.exists():
        cmd += ["--cookies", str(COOKIES_PATH)]
    cmd += [
        "--flat-playlist",
        "--print", "%(id)s\t%(title)s\t%(n_entries)s",
        PLAYLISTS_URL,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        return None

    playlists = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        pid   = parts[0].strip()
        title = parts[1].strip()
        n_raw = parts[2].strip() if len(parts) > 2 else ""
        if not pid or pid.lower() in _NA:
            continue
        n_entries: Optional[int] = None
        if n_raw and n_raw.lower() not in _NA:
            try:
                n_entries = int(float(n_raw))
            except ValueError:
                pass
        playlists.append((pid, title, n_entries))

    return playlists


def main() -> None:
    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found. Run: pip3 install yt-dlp")
        sys.exit(1)

    if not WHITELIST_FILE.exists():
        print(f"ERROR: whitelist file not found: {WHITELIST_FILE}")
        sys.exit(1)

    wl_entries = [
        line.strip()
        for line in WHITELIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(f"Whitelist: {len(wl_entries)} entries for {len(CANONICAL_NAMES)} speakers")
    print(f"Enumerating {PLAYLISTS_URL} …")
    print()

    playlists = enumerate_playlists(ytdlp)

    if playlists is None:
        print(f"ERROR: yt-dlp timed out after {TIMEOUT_SECS}s on the /playlists tab.")
        print("Bot-detection likely. Try refreshing scripts/youtube_cookies.txt.")
        sys.exit(1)

    print(f"Found {len(playlists)} playlist(s) on the channel.\n")

    # Match each playlist against the whitelist
    matches: List[Tuple[str, str, str, Optional[int]]] = []
    matched_canonicals: Set[str] = set()

    for pid, title, n_entries in playlists:
        hit = _match_playlist(title, wl_entries)
        if hit:
            canon = _canonical(hit)
            url   = f"https://www.youtube.com/playlist?list={pid}"
            matches.append((canon, title, url, n_entries))
            matched_canonicals.add(canon)

    # ── Match table ───────────────────────────────────────────────────────────
    W_SPEAKER = 22
    W_TITLE   = 42
    W_N       = 6
    W_URL     = 55
    rule      = "═" * (W_SPEAKER + W_TITLE + W_N + W_URL + 8)

    if matches:
        print(rule)
        print("MATCHED PLAYLISTS")
        print(rule)
        print(
            f"  {'SPEAKER':<{W_SPEAKER}} {'PLAYLIST TITLE':<{W_TITLE}} "
            f"{'VIDEOS':>{W_N}}  URL"
        )
        print("─" * len(rule))
        for canon, title, url, n_entries in sorted(matches, key=lambda r: r[0]):
            n_str = str(n_entries) if n_entries is not None else "?"
            print(
                f"  {canon:<{W_SPEAKER}} {title[:W_TITLE-1]:<{W_TITLE}} "
                f"{n_str:>{W_N}}  {url}"
            )
        print(rule)
    else:
        print("No matching playlists found.")

    print()

    # ── Missing speakers ──────────────────────────────────────────────────────
    missing = [n for n in CANONICAL_NAMES if n not in matched_canonicals]
    if missing:
        print(f"NO MATCHING PLAYLIST for {len(missing)} of 13 speaker(s):")
        for name in missing:
            print(f"  — {name}")
    else:
        print("All 13 speakers have at least one matching playlist.")
    print()


if __name__ == "__main__":
    main()
