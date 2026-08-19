"""Backfill era column on documents and books tables."""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import psycopg2

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

CLASSIC_AUTHORS = [
    "Derek Prince",
    "Bob Mumford",
    "Ern Baxter",
    "Charles Simpson",
    "Don Basham",
    "Oswald J. Smith",
    "Matthew Henry",
    "Adam Clarke",
]

CONTEMPORARY_AUTHORS = [
    "John Bevere",
    "Michael Brown",
    "Jack Deere",
]


def backfill_table(cur, table, authors, era, dry_run):
    placeholders = ", ".join(["%s"] * len(authors))
    cur.execute(
        f"SELECT count(*) FROM {table} WHERE lower(author) IN (SELECT lower(unnest(ARRAY[{placeholders}])))",
        authors,
    )
    row_count = cur.fetchone()[0]
    if dry_run:
        print(f"[DRY RUN] Would set era='{era}' on {row_count} rows in {table}")
    else:
        cur.execute(
            f"UPDATE {table} SET era = %s WHERE lower(author) IN (SELECT lower(unnest(ARRAY[{placeholders}])))",
            [era] + authors,
        )
        print(f"Set era='{era}' on {cur.rowcount} rows in {table}")


def main():
    parser = argparse.ArgumentParser(description="Backfill era column")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    for table in ["documents", "books"]:
        backfill_table(cur, table, CLASSIC_AUTHORS, "classic", args.dry_run)
        backfill_table(cur, table, CONTEMPORARY_AUTHORS, "contemporary", args.dry_run)

    if not args.dry_run:
        conn.commit()

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
