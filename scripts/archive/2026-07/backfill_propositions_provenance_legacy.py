#!/usr/bin/env python3
"""
backfill_propositions_provenance_legacy.py — one-time marker for rows that
predate provenance stamping (migration 067, 2026-07-23).

Every proposition written before this migration has no record of which
prompt version, fingerprint, or model produced it -- only a timestamp.
This script does NOT guess: it does not infer a version from created_at or
from the 2026-07-23 diagnostic's chronological evidence about which prompt
existed when. It marks affected rows with an explicit, clearly-labeled
"legacy_unknown" value in prompt_version and leaves prompt_fingerprint and
model NULL, since there is no real fingerprint or model to record for them.
A guessed value would be worse than an honest blank -- the whole point of
this field is to be trustworthy when investigating a suspected bad batch.

Targets `WHERE prompt_version IS NULL` rather than an unconditional update,
so it is safe to re-run and will never overwrite a real stamp written by
any ingest after migration 067.

Usage:
    python3 scripts/backfill_propositions_provenance_legacy.py --dry-run
    python3 scripts/backfill_propositions_provenance_legacy.py
"""

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

_parsed = urlparse(os.environ["SUPABASE_DB_URL"])
DB_PARAMS = {
    "host": _parsed.hostname,
    "port": _parsed.port or 5432,
    "user": unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname": _parsed.path.lstrip("/"),
}

LEGACY_MARKER = "legacy_unknown"


def main():
    parser = argparse.ArgumentParser(description="Mark pre-provenance propositions as legacy_unknown")
    parser.add_argument("--dry-run", action="store_true", help="Count only, no write")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM propositions WHERE prompt_version IS NULL")
    (to_mark,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM propositions")
    (total,) = cur.fetchone()
    print(f"Total propositions: {total}")
    print(f"Rows with no provenance (prompt_version IS NULL): {to_mark}")

    if args.dry_run:
        print("(DRY RUN — no write performed)")
        conn.close()
        return

    cur.execute(
        "UPDATE propositions SET prompt_version = %s WHERE prompt_version IS NULL",
        (LEGACY_MARKER,),
    )
    updated = cur.rowcount
    conn.commit()
    print(f"Marked {updated} rows with prompt_version = {LEGACY_MARKER!r}")
    print("prompt_fingerprint and model left NULL for these rows (no real value to record).")

    conn.close()


if __name__ == "__main__":
    main()
