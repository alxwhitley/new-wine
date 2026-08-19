#!/usr/bin/env python3
"""
register_jesus_image.py — Register Jesus Image as a YouTube source.

Jesus Image is a ministry (not a single speaker — playlist has multiple voices).
Aliases registered:
  - "jesus image"        (canonical name, normalized)
  - "jesus image church" (channel variant yt-dlp may return)

license_status='unlicensed', visibility='hidden' (fail-closed — banked not served).

Idempotent. Safe to re-run.
"""

import os
import sys
from pathlib import Path
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

CANONICAL_NAME = "Jesus Image"

# (alias_display, note) — key is derived via normalize_alias_key()
ALIASES = [
    ("Jesus Image",         "canonical name"),
    ("Jesus Image Church",  "channel variant — yt-dlp may return this string"),
]


def get_or_create_source(conn, name: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return str(row[0]), False
        cur.execute(
            """
            INSERT INTO sources (name, license_status, visibility, notes)
            VALUES (%s, 'unlicensed', 'hidden', %s)
            RETURNING id
            """,
            (name, "YouTube ministry registered via register_jesus_image.py"),
        )
        source_id = str(cur.fetchone()[0])
        conn.commit()
        return source_id, True


def ensure_alias(conn, alias_key, alias_display, source_id, note):
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


def main():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        conn.autocommit = False
    except Exception as exc:
        print("ERROR: DB connection failed: {}".format(exc))
        sys.exit(1)

    print("Registering: {}".format(CANONICAL_NAME))

    source_id, created = get_or_create_source(conn, CANONICAL_NAME)
    src_label = "CREATED" if created else "EXISTS"
    print("  source [{}]: {}".format(src_label, source_id))

    aliases_created = []
    aliases_existing = []
    for display, note in ALIASES:
        key = normalize_alias_key(display)
        try:
            inserted = ensure_alias(conn, key, display, source_id, note)
        except Exception as exc:
            conn.rollback()
            print("  ⚠  alias {!r} failed: {}".format(key, exc))
            continue
        if inserted:
            aliases_created.append(key)
            print("  alias CREATED: {!r}".format(key))
        else:
            aliases_existing.append(key)
            print("  alias EXISTS:  {!r}".format(key))

    conn.close()

    sentinel_hit = source_id == SENTINEL_SOURCE_ID
    print("")
    print("── Verification ──────────────────────────────────────────────────")
    print("  resolved source_id : {}".format(source_id))
    print("  alias keys created : {}".format(aliases_created))
    print("  alias keys existed : {}".format(aliases_existing))
    print("  NOT sentinel       : {}".format("YES ✓" if not sentinel_hit else "NO — CRITICAL ⚠"))
    if sentinel_hit:
        print("CRITICAL: source_id == SENTINEL_SOURCE_ID — registration landed on sentinel.")
        sys.exit(1)
    else:
        print("✓ Registration confirmed clean.")


if __name__ == "__main__":
    main()
