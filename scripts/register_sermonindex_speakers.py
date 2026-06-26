#!/usr/bin/env python3
"""
register_sermonindex_speakers.py — Register 13 SermonIndex archive preachers.

No yt-dlp needed — SermonIndex content is resolved by speaker name at ingest time.
Alias key = normalize_alias_key(display_string) — punctuation is preserved (no stripping).

All sources: license_status='unlicensed', visibility='hidden' (fail-closed).
Idempotent. Safe to re-run.

Frank Bartleman is checked first — he may already exist from the corpus backlog.
If so, only missing aliases are added; no duplicate source row is created.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

# MUST import from source_resolver — do not re-implement normalize_alias_key.
sys.path.insert(0, str(ROOT / "scripts"))
from source_resolver import normalize_alias_key, SENTINEL_SOURCE_ID  # noqa: E402

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

_parsed = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host":     _parsed.hostname,
    "port":     _parsed.port or 5432,
    "user":     unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname":   _parsed.path.lstrip("/"),
}

# ── Speakers + aliases ────────────────────────────────────────────────────────
# Each entry: (canonical_name, [alias_display_strings])
# normalize_alias_key() is applied to each display string to produce the key.
# Punctuation is preserved: "A.W. Tozer" → "a.w. tozer" (distinct from "aw tozer").

SPEAKERS = [
    ("David Wilkerson",  ["David Wilkerson"]),
    ("Carter Conlon",    ["Carter Conlon"]),
    ("Smith Wigglesworth", ["Smith Wigglesworth"]),
    ("Kathryn Kuhlman",  ["Kathryn Kuhlman"]),
    ("Duncan Campbell",  ["Duncan Campbell"]),
    ("Frank Bartleman",  ["Frank Bartleman"]),   # checked first — may already exist
    ("Zac Poonen",       ["Zac Poonen"]),
    ("Leonard Ravenhill",["Leonard Ravenhill"]),
    ("A.W. Tozer",       ["A.W. Tozer", "AW Tozer", "A W Tozer"]),
    ("Keith Green",      ["Keith Green"]),
    ("Paris Reidhead",   ["Paris Reidhead"]),
    ("Art Katz",         ["Art Katz"]),
    ("T. Austin-Sparks", ["T. Austin-Sparks", "T Austin-Sparks", "Austin-Sparks"]),
]


# ── DB helpers ────────────────────────────────────────────────────────────────

def check_bartleman(conn) -> Optional[dict]:
    """Query sources + source_aliases for any existing Bartleman entry."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name FROM sources WHERE LOWER(name) LIKE %s", ("%bartleman%",)
        )
        src_rows = cur.fetchall()

        cur.execute(
            "SELECT alias_key, alias_display, source_id FROM source_aliases "
            "WHERE alias_key LIKE %s", ("%bartleman%",)
        )
        alias_rows = cur.fetchall()

    if not src_rows and not alias_rows:
        return None
    return {
        "sources":  [(str(r[0]), r[1]) for r in src_rows],
        "aliases":  [(r[0], r[1], str(r[2])) for r in alias_rows],
    }


def get_or_create_source(conn, canonical_name: str) -> Tuple[str, bool]:
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
            (canonical_name, "SermonIndex archive preacher — registered via register_sermonindex_speakers.py"),
        )
        source_id = str(cur.fetchone()[0])
        conn.commit()
        return source_id, True


def ensure_alias(conn, alias_key: str, alias_display: str, source_id: str, note: str) -> bool:
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


# ── Per-speaker registration ──────────────────────────────────────────────────

def register_speaker(conn, canonical: str, alias_displays: List[str], bartleman_existing_id: Optional[str] = None) -> dict:
    result = {
        "canonical":        canonical,
        "source_id":        None,
        "source_created":   None,   # True=CREATED, False=EXISTS
        "aliases_created":  [],
        "aliases_existing": [],
        "error":            None,
    }

    try:
        if bartleman_existing_id:
            # Use the pre-existing source_id — don't touch the sources row
            source_id = bartleman_existing_id
            result["source_id"]      = source_id
            result["source_created"] = False  # EXISTS
        else:
            source_id, created = get_or_create_source(conn, canonical)
            result["source_id"]      = source_id
            result["source_created"] = created
    except Exception as exc:
        conn.rollback()
        result["error"] = "source error: {}".format(exc)
        return result

    seen_keys = set()
    for display in alias_displays:
        key = normalize_alias_key(display)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        try:
            inserted = ensure_alias(conn, key, display, source_id, "SermonIndex alias")
        except Exception as exc:
            conn.rollback()
            print("  ⚠  alias {!r} failed: {}".format(key, exc))
            continue
        if inserted:
            result["aliases_created"].append(key)
        else:
            result["aliases_existing"].append(key)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        conn.autocommit = False
    except Exception as exc:
        print("ERROR: DB connection failed: {}".format(exc))
        sys.exit(1)

    # ── Bartleman pre-check ───────────────────────────────────────────────────
    print("── Bartleman pre-check ──────────────────────────────────────────")
    existing = check_bartleman(conn)
    bartleman_existing_id = None

    if existing:
        print("  FOUND existing Bartleman entry:")
        for sid, name in existing["sources"]:
            print("    source: {!r} → {}".format(name, sid))
        for key, display, sid in existing["aliases"]:
            print("    alias:  {!r} ({!r}) → {}".format(key, display, sid))
        if existing["sources"]:
            bartleman_existing_id = existing["sources"][0][0]
            print("  → Will reuse source_id {} (no duplicate created)".format(bartleman_existing_id))
    else:
        print("  NOT found — will create fresh.")
    print()

    # ── Register all 13 ──────────────────────────────────────────────────────
    results = []
    for canonical, alias_displays in SPEAKERS:
        is_bartleman = "Bartleman" in canonical
        existing_id  = bartleman_existing_id if is_bartleman else None
        r = register_speaker(conn, canonical, alias_displays, bartleman_existing_id=existing_id)
        results.append((r, is_bartleman))

    conn.close()

    # ── Verification table ────────────────────────────────────────────────────
    W_NAME = 22
    W_SID  = 38
    W_AL   = 60

    header = "{:<{}} {:<{}} {:<{}} STATUS".format(
        "CANONICAL", W_NAME, "SOURCE_ID", W_SID, "ALIASES (created / [existed])", W_AL
    )
    sep = "═" * len(header)
    print(sep)
    print("VERIFICATION TABLE")
    print(sep)
    print(header)
    print("─" * len(header))

    all_ok = True
    for r, is_bartleman in results:
        name_col = r["canonical"][:W_NAME - 1]

        if r["error"]:
            print("{:<{}} {:<{}} {:<{}} FAILED".format(
                name_col, W_NAME, "—", W_SID, r["error"][:W_AL - 1], W_AL
            ))
            all_ok = False
            continue

        sid     = r["source_id"] or "MISSING"
        created = ", ".join(r["aliases_created"])
        existed = ", ".join("[{}]".format(k) for k in r["aliases_existing"])
        al_col  = ", ".join(filter(None, [created, existed]))[:W_AL - 1]

        on_sent = sid == SENTINEL_SOURCE_ID
        if on_sent:
            status = "SENTINEL ⚠"
            all_ok = False
        elif is_bartleman:
            status = "CREATED ✓" if r["source_created"] else "ALREADY-EXISTED ✓"
        else:
            status = "CREATED ✓" if r["source_created"] else "EXISTS ✓"

        print("{:<{}} {:<{}} {:<{}} {}".format(
            name_col, W_NAME, sid, W_SID, al_col, W_AL, status
        ))

    print(sep)
    print("✓ All 13 speakers registered — none on sentinel." if all_ok
          else "✗ One or more speakers failed or landed on sentinel. Review above.")
    print()


if __name__ == "__main__":
    main()
