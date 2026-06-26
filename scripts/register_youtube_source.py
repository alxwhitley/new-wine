#!/usr/bin/env python3
"""
register_youtube_source.py — Register new YouTube teachers in sources + source_aliases.

For each teacher:
  1. Fetch the real channel name from YouTube via yt-dlp (metadata only, no download).
  2. INSERT INTO sources (canonical name, unlicensed/hidden) if not already present.
  3. INSERT INTO source_aliases for:
       - normalized canonical name
       - normalized real channel string fetched from yt-dlp (if it differs)
     Skip each alias if it already exists.

Idempotent: safe to re-run. Per-teacher fault tolerant.

Usage:
    python3 scripts/register_youtube_source.py
    python3 scripts/register_youtube_source.py --dry-run
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# ── Import canonical normalization — MUST NOT be re-implemented here ─────────
# Alias normalization mismatch = silent resolution miss (migration 050 gotcha).
sys.path.insert(0, str(ROOT / "scripts"))
from source_resolver import normalize_alias_key, SENTINEL_SOURCE_ID  # noqa: E402

# ── DB connection (psycopg2 — PostgREST can't write service-role-only tables) ─
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    print("  SUPABASE_DB_URL=postgresql://user:password@host:5432/dbname")
    sys.exit(1)

# urlparse is required: Supabase pooler usernames contain a dot (postgres.{ref})
# which psycopg2.connect(uri) silently truncates — explicit kwargs work correctly.
_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host":     _parsed_db.hostname,
    "port":     _parsed_db.port or 5432,
    "user":     unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname":   _parsed_db.path.lstrip("/"),
}

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
    """Fetch the real channel name from YouTube. Metadata only — no video download."""
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

def get_or_create_source(
    conn, canonical_name: str, notes: str
) -> Tuple[str, bool]:
    """
    Return (source_id, created).
    New rows: license_status='unlicensed', visibility='hidden' (fail-closed).
    """
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
    """
    Insert alias_key → source_id if not already present.
    Returns True if inserted, False if it already existed.
    alias_key must be pre-normalized by the caller via normalize_alias_key().
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id FROM source_aliases WHERE alias_key = %s",
            (alias_key,),
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


# ── Per-teacher registration ───────────────────────────────────────────────────

def register_teacher(
    conn,
    ytdlp: str,
    canonical_name: str,
    channel_url: str,
    dry_run: bool = False,
) -> dict:
    """
    Register one teacher. Returns a result dict for the verification table.
    Errors are caught and returned in result["error"] — never raised to caller.
    """
    result = {
        "canonical_name":     canonical_name,
        "channel_url":        channel_url,
        "channel_name_yt":    None,
        "source_id":          None,
        "source_created":     False,
        "aliases_created":    [],
        "aliases_existing":   [],
        "error":              None,
    }

    # Step 1: fetch real channel name (metadata only)
    try:
        channel_name = fetch_channel_name(ytdlp, channel_url)
        result["channel_name_yt"] = channel_name
        if channel_name:
            print(f"  channel name from yt-dlp: {channel_name!r}")
        else:
            print(f"  ⚠  Could not fetch channel name — will register canonical name alias only")
    except Exception as e:
        result["error"] = f"yt-dlp error: {e}"
        print(f"  ✗ {result['error']}")
        return result

    # Build the alias list: canonical name always; yt-dlp name if it's different
    canonical_key = normalize_alias_key(canonical_name)
    aliases_to_try = [(canonical_key, canonical_name, "canonical name")]

    if channel_name:
        ch_key = normalize_alias_key(channel_name)
        if ch_key and ch_key != canonical_key:
            aliases_to_try.append((ch_key, channel_name, "yt-dlp channel name"))

    if dry_run:
        result["aliases_created"] = [k for k, _, _ in aliases_to_try]
        print(f"  [DRY RUN] would create aliases: {result['aliases_created']}")
        return result

    # Step 2: get or create source row
    try:
        notes = f"YouTube teacher registered via register_youtube_source.py — {channel_url}"
        source_id, created = get_or_create_source(conn, canonical_name, notes)
        result["source_id"] = source_id
        result["source_created"] = created
        label = "CREATED" if created else "EXISTS"
        print(f"  source [{label}]: {source_id}")
    except Exception as e:
        conn.rollback()
        result["error"] = f"source insert failed: {e}"
        print(f"  ✗ {result['error']}")
        return result

    # Step 3: insert aliases
    for alias_key, alias_display, note in aliases_to_try:
        try:
            inserted = ensure_alias(conn, alias_key, alias_display, source_id, note)
            if inserted:
                result["aliases_created"].append(alias_key)
                print(f"  alias CREATED: {alias_key!r}")
            else:
                result["aliases_existing"].append(alias_key)
                print(f"  alias EXISTS:  {alias_key!r}")
        except Exception as e:
            conn.rollback()
            print(f"  ⚠  alias '{alias_key}' failed: {e}")

    return result


# ── Teachers to register ───────────────────────────────────────────────────────

TEACHERS = [
    ("Andrew Wommack",  "https://www.youtube.com/@AndrewWommackMin"),
    ("Craig Keener",    "https://www.youtube.com/@CraigKeenerPhD"),
    ("David Pawson",    "https://www.youtube.com/@DavidPawsonMinistry"),
    ("Randy Clark",     "https://www.youtube.com/@Globalawakening1"),
    ("Mark Virkler",    "https://www.youtube.com/@cwgministries"),
    ("Vlad Savchuk",    "https://www.youtube.com/@vladhungrygen"),
    ("Sam Storms",      "https://www.youtube.com/@ConvergenceChurchOKC"),
    ("Roberts Liardon", "https://www.youtube.com/@RobertsLiardon"),
    ("R.T. Kendall",    "https://www.youtube.com/@rtkendall9949"),
]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Register YouTube teachers in sources + source_aliases"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without writing to the DB"
    )
    args = parser.parse_args()

    ytdlp = find_ytdlp()
    if not ytdlp:
        print("ERROR: yt-dlp not found. Run: pip3 install yt-dlp")
        sys.exit(1)
    print(f"yt-dlp: {ytdlp}")
    if args.dry_run:
        print("DRY-RUN mode — no DB writes\n")

    conn = None
    if not args.dry_run:
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            conn.autocommit = False
        except Exception as e:
            print(f"ERROR: DB connection failed: {e}")
            sys.exit(1)

    results = []
    for canonical_name, channel_url in TEACHERS:
        print(f"\n{'─' * 64}")
        print(f"  {canonical_name}")
        print(f"  {channel_url}")
        try:
            r = register_teacher(conn, ytdlp, canonical_name, channel_url, dry_run=args.dry_run)
        except Exception as e:
            r = {
                "canonical_name":   canonical_name,
                "channel_url":      channel_url,
                "channel_name_yt":  None,
                "source_id":        None,
                "source_created":   False,
                "aliases_created":  [],
                "aliases_existing": [],
                "error":            f"unhandled: {e}",
            }
            print(f"  ✗ Unhandled: {e}")
        results.append(r)

    if conn:
        conn.close()

    # ── Verification table ────────────────────────────────────────────────────
    W_NAME    = 24
    W_SID     = 38
    W_ALIASES = 50
    W_STATUS  = 10
    header_line = (
        f"{'TEACHER':<{W_NAME}} "
        f"{'SOURCE_ID':<{W_SID}} "
        f"{'ALIASES (created / existed)':<{W_ALIASES}} "
        f"STATUS"
    )
    sep = "═" * len(header_line)

    print(f"\n{sep}")
    print("VERIFICATION TABLE")
    print(sep)
    print(header_line)
    print("─" * len(header_line))

    all_ok = True
    for r in results:
        name_col = r["canonical_name"][:W_NAME - 1]

        if r["error"]:
            print(
                f"{name_col:<{W_NAME}} "
                f"{'—':<{W_SID}} "
                f"{r['error'][:W_ALIASES]:<{W_ALIASES}} "
                f"FAILED"
            )
            all_ok = False
            continue

        if args.dry_run:
            aliases_col = ", ".join(r["aliases_created"])[:W_ALIASES - 1]
            print(
                f"{name_col:<{W_NAME}} "
                f"{'(dry run)':<{W_SID}} "
                f"{aliases_col:<{W_ALIASES}} "
                f"DRY-RUN"
            )
            continue

        sid = r["source_id"] or "MISSING"
        on_sentinel = sid == SENTINEL_SOURCE_ID
        created_str  = ", ".join(r["aliases_created"])
        existing_str = ", ".join(f"[{k}]" for k in r["aliases_existing"])
        aliases_col  = ", ".join(filter(None, [created_str, existing_str]))[:W_ALIASES - 1]
        status = "SENTINEL ⚠" if on_sentinel else "OK"
        print(
            f"{name_col:<{W_NAME}} "
            f"{sid:<{W_SID}} "
            f"{aliases_col:<{W_ALIASES}} "
            f"{status}"
        )
        if on_sentinel:
            all_ok = False

    print(sep)
    if not args.dry_run:
        if all_ok:
            print("✓ All teachers registered — none on sentinel.")
        else:
            print("✗ One or more teachers failed or landed on sentinel. Review above.")
    print()


if __name__ == "__main__":
    main()
