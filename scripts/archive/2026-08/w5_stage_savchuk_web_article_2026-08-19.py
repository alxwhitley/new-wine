#!/usr/bin/env python3
"""Attended W5 prep: staging source + alias + uncleared queue row.

Alex-approved 2026-08-19:
  - Create "Vlad Savchuk (web staging)" unlicensed + hidden
  - Alias only that exact display name (never steal live "vlad savchuk")
  - Insert web_page queue row for cleaned pastorvlad URL, cleared_to_run=false

No ingest write. No visibility change on live Vlad Savchuk.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
import os

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.services.source_resolver import normalize_alias_key  # noqa: E402

STAGING_NAME = "Vlad Savchuk (web staging)"
LIVE_SAVCHUK_ID = "74ed5fa1-9aac-4997-87ec-4be6724b49bd"
ARTICLE_URL = (
    "https://pastorvlad.org/how-to-develop-your-prayer-language-in-private/"
)
# Same admin submitter as the migration-088 PDF proof row.
SUBMITTED_BY = "4ba2f9ce-6788-47c7-9dcd-10e640fd199b"
NOTES_SOURCE = (
    "W5–W6 quarantined web-article staging source for "
    "pastorvlad.org prayer-language article (2026-08-19). "
    "Must stay visibility=hidden until answer-integrity review. "
    "Distinct from live Vlad Savchuk source."
)
NOTES_QUEUE = (
    "W5–W6 first quarantined web article: Vlad Savchuk, "
    "How to Develop Your Prayer Language in Private. "
    "Staging source only; cleared_to_run stays false until preview accepted."
)


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL missing", file=sys.stderr)
        return 2

    alias_key = normalize_alias_key(STAGING_NAME)
    if alias_key != "vlad savchuk (web staging)":
        print(f"unexpected alias_key={alias_key!r}", file=sys.stderr)
        return 2
    if alias_key == "vlad savchuk":
        print("refusing to touch live savchuk alias", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Guard: live Savchuk unchanged
        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE id = %s",
            (LIVE_SAVCHUK_ID,),
        )
        live = cur.fetchone()
        if not live or live["visibility"] != "shown":
            raise RuntimeError(f"live Savchuk unexpected: {live}")

        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE name = %s",
            (STAGING_NAME,),
        )
        existing = cur.fetchone()
        if existing:
            source_id = str(existing["id"])
            source_created = False
            if existing["visibility"] != "hidden" or existing["license_status"] != "unlicensed":
                raise RuntimeError(f"staging source wrong policy: {dict(existing)}")
        else:
            cur.execute(
                """
                INSERT INTO sources (name, license_status, visibility, notes)
                VALUES (%s, 'unlicensed', 'hidden', %s)
                RETURNING id, name, license_status, visibility
                """,
                (STAGING_NAME, NOTES_SOURCE),
            )
            row = cur.fetchone()
            source_id = str(row["id"])
            source_created = True

        cur.execute(
            "SELECT source_id FROM source_aliases WHERE alias_key = %s",
            (alias_key,),
        )
        alias_row = cur.fetchone()
        if alias_row:
            if str(alias_row["source_id"]) != source_id:
                raise RuntimeError(
                    f"alias {alias_key!r} points at {alias_row['source_id']}, expected {source_id}"
                )
            alias_created = False
        else:
            cur.execute(
                """
                INSERT INTO source_aliases (alias_key, alias_display, source_id, note)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    alias_key,
                    STAGING_NAME,
                    source_id,
                    "W5–W6 staging alias; do not point live 'vlad savchuk' here",
                ),
            )
            alias_created = True

        cur.execute(
            """
            SELECT id, url, attribute_to, cleared_to_run, status, source_format
            FROM source_ingest_queue
            WHERE url = %s OR url ILIKE %s
            ORDER BY created_at DESC
            """,
            (ARTICLE_URL, "%how-to-develop-your-prayer-language-in-private%"),
        )
        prior = cur.fetchall()
        if prior:
            raise RuntimeError(f"queue row already exists for this article: {prior}")

        cur.execute(
            """
            INSERT INTO source_ingest_queue (
              url, source_format, source_scope, attribute_to, attribution_mode,
              on_unknown_author, retain_original_text, status, cleared_to_run,
              notes, submitted_by
            ) VALUES (
              %s, 'web_page', 'single', %s, 'declared',
              'flag', true, 'waiting', false,
              %s, %s
            )
            RETURNING id, url, attribute_to, cleared_to_run, status, source_format,
                      source_scope, attribution_mode, retain_original_text
            """,
            (ARTICLE_URL, STAGING_NAME, NOTES_QUEUE, SUBMITTED_BY),
        )
        queue_row = cur.fetchone()

        # Reconciliation reads (same transaction)
        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE id = %s",
            (source_id,),
        )
        src = cur.fetchone()
        cur.execute(
            "SELECT alias_key, source_id FROM source_aliases WHERE alias_key = %s",
            (alias_key,),
        )
        alias = cur.fetchone()
        cur.execute(
            "SELECT alias_key, source_id FROM source_aliases WHERE alias_key = 'vlad savchuk'"
        )
        live_alias = cur.fetchone()
        cur.execute(
            "SELECT id, name, visibility FROM sources WHERE id = %s",
            (LIVE_SAVCHUK_ID,),
        )
        live_after = cur.fetchone()
        cur.execute(
            """
            SELECT id, url, attribute_to, cleared_to_run, status, source_format,
                   source_scope, attribution_mode, retain_original_text
            FROM source_ingest_queue WHERE id = %s
            """,
            (queue_row["id"],),
        )
        q = cur.fetchone()

        assert src["visibility"] == "hidden" and src["license_status"] == "unlicensed"
        assert str(alias["source_id"]) == source_id
        assert str(live_alias["source_id"]) == LIVE_SAVCHUK_ID
        assert live_after["visibility"] == "shown"
        assert q["cleared_to_run"] is False
        assert q["status"] == "waiting"
        assert q["source_format"] == "web_page"
        assert q["source_scope"] == "single"
        assert q["attribution_mode"] == "declared"
        assert q["retain_original_text"] is True
        assert q["attribute_to"] == STAGING_NAME

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("RECONCILE")
    print(f"  source_created={source_created} source_id={source_id}")
    print(f"  alias_created={alias_created} alias_key={alias_key!r}")
    print(f"  queue_id={queue_row['id']}")
    print(f"  url={ARTICLE_URL}")
    print(f"  attribute_to={STAGING_NAME!r}")
    print(f"  cleared_to_run=false status=waiting")
    print(f"  live_savchuk_visibility=shown (unchanged)")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
