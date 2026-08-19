#!/usr/bin/env python3
"""W9 Phase 1a: hide staging source + enqueue 3 uncleared pastorvlad rows.

Alex-approved via W9 manifest sign-off (2026-08-19):
  - Flip Vlad Savchuk (web staging) shown → hidden (write-gate only)
  - Insert three web_page queue rows, cleared_to_run=false
  - Leave live Vlad Savchuk untouched

No ingest write. No preview. No clearance.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

STAGING_ID = "33cfa6b5-ae98-4c68-a41a-e1db52914546"
STAGING_NAME = "Vlad Savchuk (web staging)"
LIVE_SAVCHUK_ID = "74ed5fa1-9aac-4997-87ec-4be6724b49bd"
SUBMITTED_BY = "4ba2f9ce-6788-47c7-9dcd-10e640fd199b"

ARTICLES = [
    {
        "url": "https://pastorvlad.org/tenways/",
        "title": "10 Ways to Know the Holy Spirit Better",
    },
    {
        "url": "https://pastorvlad.org/planted-not-buried-what-god-is-doing-while-you-wait/",
        "title": "Planted Not Buried: What God Is Doing While You Wait",
    },
    {
        "url": "https://pastorvlad.org/intrusive-thoughts-demon-stronghold-or-just-your-mind/",
        "title": "Intrusive Thoughts: Demon, Stronghold, or Just Your Mind?",
    },
]


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL missing", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    inserted = []

    try:
        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE id = %s",
            (LIVE_SAVCHUK_ID,),
        )
        live = cur.fetchone()
        if not live or live["visibility"] != "shown" or live["name"] != "Vlad Savchuk":
            raise RuntimeError(f"live Savchuk unexpected: {live}")

        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE id = %s",
            (STAGING_ID,),
        )
        staging = cur.fetchone()
        if not staging or staging["name"] != STAGING_NAME:
            raise RuntimeError(f"staging source unexpected: {staging}")
        if staging["license_status"] != "unlicensed":
            raise RuntimeError(f"staging license unexpected: {staging}")

        if staging["visibility"] != "hidden":
            cur.execute(
                """
                UPDATE sources
                SET visibility = 'hidden', updated_at = now()
                WHERE id = %s AND visibility = 'shown'
                RETURNING id, visibility
                """,
                (STAGING_ID,),
            )
            flipped = cur.fetchone()
            if not flipped or flipped["visibility"] != "hidden":
                raise RuntimeError(f"failed to hide staging: {flipped}")
            hide_flipped = True
        else:
            hide_flipped = False

        for art in ARTICLES:
            url = art["url"]
            cur.execute(
                """
                SELECT id::text, url, status, cleared_to_run
                FROM source_ingest_queue
                WHERE url = %s OR url ILIKE %s
                ORDER BY created_at DESC
                """,
                (url, "%" + url.rstrip("/").rsplit("/", 1)[-1] + "%"),
            )
            prior = cur.fetchall()
            if prior:
                raise RuntimeError(f"queue row already exists for {url}: {prior}")

            notes = (
                f"W9 batch 2026-08-19 item: Vlad Savchuk — {art['title']}. "
                "Staging source only; cleared_to_run stays false until preview accepted. "
                "Manifest: docs/audits/w9_web_article_batch_manifest_2026-08-19.md"
            )
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
                RETURNING id::text, url, attribute_to, cleared_to_run, status,
                          source_format, source_scope, attribution_mode,
                          retain_original_text
                """,
                (url, STAGING_NAME, notes, SUBMITTED_BY),
            )
            inserted.append(dict(cur.fetchone()))

        cur.execute(
            "SELECT id, name, visibility, license_status FROM sources WHERE id = %s",
            (STAGING_ID,),
        )
        staging_after = cur.fetchone()
        cur.execute(
            "SELECT id, name, visibility FROM sources WHERE id = %s",
            (LIVE_SAVCHUK_ID,),
        )
        live_after = cur.fetchone()
        cur.execute(
            "SELECT count(*)::int AS n FROM documents WHERE source_id = %s",
            (STAGING_ID,),
        )
        doc_count = cur.fetchone()["n"]

        assert staging_after["visibility"] == "hidden"
        assert staging_after["license_status"] == "unlicensed"
        assert live_after["visibility"] == "shown"
        assert len(inserted) == 3
        for q in inserted:
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
    print(f"  hide_flipped={hide_flipped}")
    print(f"  staging_id={STAGING_ID} visibility=hidden license=unlicensed")
    print(f"  live_savchuk_visibility=shown (unchanged)")
    print(f"  staging_docs_unchanged_count={doc_count}")
    for q in inserted:
        print(f"  queue_id={q['id']} url={q['url']} cleared=false status=waiting")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
