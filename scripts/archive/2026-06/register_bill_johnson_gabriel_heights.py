#!/usr/bin/env python3
"""
register_bill_johnson_gabriel_heights.py — Register Bill Johnson and Gabriel Heights.

Both: license_status='unlicensed', visibility='hidden' (fail-closed — banked not served).
Idempotent. Safe to re-run.

Bill Johnson:
  Canonical: "Bill Johnson"
  Channel:   youtube.com/@BillJohnsonMinistries
  Aliases:   bill johnson  |  bill johnson ministries  |  yt-dlp channel name (if different)

Gabriel Heights (ministry — multiple guest speakers, attributed at ministry level):
  Canonical: "Gabriel Heights"
  Channel:   youtube.com/@GabrielHeightsTelecasting
  Aliases:   gabriel heights  |  gabriel heights telecasting  |  yt-dlp channel name (if different)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# MUST import from source_resolver — do not re-implement normalize_alias_key.
# Alias normalization mismatch = silent resolution miss (migration 050 gotcha).
sys.path.insert(0, str(ROOT / "scripts"))
from source_resolver import normalize_alias_key, SENTINEL_SOURCE_ID  # noqa: E402

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

# urlparse required: Supabase pooler usernames contain a dot (postgres.{ref})
# which psycopg2.connect(uri) silently truncates — explicit kwargs work correctly.
_parsed = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host":     _parsed.hostname,
    "port":     _parsed.port or 5432,
    "user":     unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname":   _parsed.path.lstrip("/"),
}

# ── Sources to register ───────────────────────────────────────────────────────
# extra_aliases: display strings beyond the canonical name.
# yt-dlp result is appended if it differs from all keys already in the list.

SOURCES = [
    {
        "canonical":     "Bill Johnson",
        "channel_url":   "https://www.youtube.com/@BillJohnsonMinistries",
        "extra_aliases": ["Bill Johnson Ministries"],
    },
    {
        "canonical":     "Gabriel Heights",
        "channel_url":   "https://www.youtube.com/@GabrielHeightsTelecasting",
        "extra_aliases": ["Gabriel Heights Telecasting"],
    },
]

# ── yt-dlp helpers ────────────────────────────────────────────────────────────

def find_ytdlp() -> Optional[str]:
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


def fetch_channel_name(ytdlp: str, channel_url: str) -> Optional[str]:
    """Fetch real channel name via yt-dlp — metadata only, no download."""
    cmd = [
        ytdlp, "-4",
        "--flat-playlist",
        "--playlist-items", "1",
        "--print", "%(channel)s",
        channel_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return None
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and line not in ("NA", "None", "null"):
            return line
    return None


# ── DB operations ─────────────────────────────────────────────────────────────

def get_or_create_source(conn, canonical_name: str, notes: str) -> Tuple[str, bool]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (canonical_name,))
        row = cur.fetchone()
        if row:
            return str(row[0]), False
        cur.execute(
            """
            INSERT INTO sources (name, license_status, visibility, notes)
            VALUES (%s, 'unlicensed', 'hidden', %s)
            RETURNING id
            """,
            (canonical_name, notes),
        )
        source_id = str(cur.fetchone()[0])
        conn.commit()
        return source_id, True


def ensure_alias(
    conn, alias_key: str, alias_display: str, source_id: str, note: str
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id FROM source_aliases WHERE alias_key = %s", (alias_key,)
        )
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO source_aliases (alias_key, alias_display, source_id, note)
            VALUES (%s, %s, %s, %s)
            """,
            (alias_key, alias_display, source_id, note),
        )
        conn.commit()
        return True


# ── Per-source registration ───────────────────────────────────────────────────

def register_source(conn, ytdlp: str, entry: dict) -> dict:
    canonical     = entry["canonical"]
    channel_url   = entry["channel_url"]
    extra_aliases = entry.get("extra_aliases", [])

    result = {
        "canonical":       canonical,
        "channel_url":     channel_url,
        "channel_name_yt": None,
        "source_id":       None,
        "source_created":  False,
        "aliases_created": [],
        "aliases_existing":[],
        "error":           None,
    }

    # Step 1: fetch real channel name (metadata only)
    print("  fetching channel name from yt-dlp...")
    channel_name = fetch_channel_name(ytdlp, channel_url)
    result["channel_name_yt"] = channel_name
    if channel_name:
        print("  yt-dlp channel name: {!r}".format(channel_name))
    else:
        print("  ⚠  yt-dlp returned no channel name — will register without it")

    # Build alias list: canonical first, then explicit extras, then yt-dlp if new
    seen_keys = set()
    aliases_to_try = []  # [(key, display, note), ...]

    def _add_alias(display, note):
        key = normalize_alias_key(display)
        if key and key not in seen_keys:
            seen_keys.add(key)
            aliases_to_try.append((key, display, note))

    _add_alias(canonical, "canonical name")
    for ea in extra_aliases:
        _add_alias(ea, "explicit extra alias")
    if channel_name:
        _add_alias(channel_name, "yt-dlp channel name")

    # Step 2: get or create source row
    try:
        notes = "YouTube source registered via register_bill_johnson_gabriel_heights.py — {}".format(channel_url)
        source_id, created = get_or_create_source(conn, canonical, notes)
        result["source_id"]      = source_id
        result["source_created"] = created
        label = "CREATED" if created else "EXISTS"
        print("  source [{}]: {}".format(label, source_id))
    except Exception as exc:
        conn.rollback()
        result["error"] = "source insert failed: {}".format(exc)
        print("  ✗ {}".format(result["error"]))
        return result

    # Step 3: insert aliases
    for alias_key, alias_display, note in aliases_to_try:
        try:
            inserted = ensure_alias(conn, alias_key, alias_display, source_id, note)
        except Exception as exc:
            conn.rollback()
            print("  ⚠  alias {!r} failed: {}".format(alias_key, exc))
            continue
        if inserted:
            result["aliases_created"].append(alias_key)
            print("  alias CREATED: {!r}".format(alias_key))
        else:
            result["aliases_existing"].append(alias_key)
            print("  alias EXISTS:  {!r}".format(alias_key))

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found. Run: pip3 install yt-dlp")
        sys.exit(1)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        conn.autocommit = False
    except Exception as exc:
        print("ERROR: DB connection failed: {}".format(exc))
        sys.exit(1)

    results = []
    for entry in SOURCES:
        print("\n{}".format("─" * 64))
        print("  {}".format(entry["canonical"]))
        print("  {}".format(entry["channel_url"]))
        r = register_source(conn, ytdlp, entry)
        results.append(r)

    conn.close()

    # ── Verification table ────────────────────────────────────────────────────
    W_NAME  = 20
    W_SID   = 38
    W_YT    = 32
    W_AL    = 56

    header = (
        "{:<{}} {:<{}} {:<{}} {:<{}} STATUS".format(
            "CANONICAL", W_NAME, "SOURCE_ID", W_SID, "YT CHANNEL NAME", W_YT, "ALIASES", W_AL
        )
    )
    sep = "═" * len(header)
    print("\n{}".format(sep))
    print("VERIFICATION TABLE")
    print(sep)
    print(header)
    print("─" * len(header))

    all_ok = True
    for r in results:
        if r["error"]:
            print("{:<{}} {:<{}} {:<{}} {:<{}} FAILED".format(
                r["canonical"][:W_NAME - 1], W_NAME,
                "—", W_SID,
                "—", W_YT,
                r["error"][:W_AL - 1], W_AL,
            ))
            all_ok = False
            continue

        sid      = r["source_id"] or "MISSING"
        yt_name  = (r["channel_name_yt"] or "—")[:W_YT - 1]
        created  = ", ".join(r["aliases_created"])
        existing = ", ".join("[{}]".format(k) for k in r["aliases_existing"])
        al_col   = ", ".join(filter(None, [created, existing]))[:W_AL - 1]
        on_sent  = sid == SENTINEL_SOURCE_ID
        status   = "SENTINEL ⚠" if on_sent else "OK ✓"

        print("{:<{}} {:<{}} {:<{}} {:<{}} {}".format(
            r["canonical"][:W_NAME - 1], W_NAME,
            sid, W_SID,
            yt_name, W_YT,
            al_col, W_AL,
            status,
        ))
        if on_sent:
            all_ok = False

    print(sep)
    if all_ok:
        print("✓ All sources registered — none on sentinel.")
    else:
        print("✗ One or more sources failed or landed on sentinel. Review above.")
    print()


if __name__ == "__main__":
    main()
