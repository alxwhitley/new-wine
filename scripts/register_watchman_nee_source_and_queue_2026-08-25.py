#!/usr/bin/env python3
"""Attended prep: register the "Watchman Nee" source + alias, and queue two
watchmannee.org pages for later ingestion. NOT to be run inside a Claude
Code session -- Auto Mode blocks direct production DB writes here, and the
repo's standing hard rule requires every DB write to be an attended,
explicitly approved plain-script operation run from the primary Codex
session (or an equivalent attended terminal). This script only prepares
and reconciles the writes in one transaction; it does not clear either
queue row to run.

Context (2026-08-25 session): Alex asked to ingest
https://www.watchmannee.org/major-teachings.html. Both pages staged below
carry a trailing page citation crediting the text to WITNESS LEE, not
Watchman Nee -- e.g. major-teachings.html: "The Collected Works of Watchman
Nee, Volume 1, 'A Short Introduction in Memory of Brother Watchman Nee', by
Witness Lee"; scriptural-teachings.html: "Watchman Nee -- A Seer of the
Divine Revelation in the Present Age, by Witness Lee". Both pages read as
uniform third-person exposition ("He pointed out that...") with no
quotation marks or excerpt markers anywhere in the text -- nothing in the
page content itself distinguishes it as an assembly of Nee's own quoted
sentences rather than Lee's own composed introduction/exposition prose.
This was raised to Alex directly, with the specific textual evidence,
before this script was written. Alex's explicit decision (2026-08-25):
attribute to Watchman Nee anyway -- his reasoning is that Witness Lee
compiled/assembled the material but the underlying content is Watchman
Nee's own. Recorded here, not silently applied, so a future session can
see this was a deliberate call made with the citation conflict fully
disclosed, not an oversight.

Three other pages on the same site were checked and are NOT part of this
batch: christian-faith.html (no citation anywhere on the page --
authorship unconfirmed either way), life-ministry.html and
watchman-nee-testimony.html (both mix an unconfirmed-author narrative with
direct first-person Watchman Nee quotes in the same page -- the current
ingestion pipeline only supports one declared author per document;
attribution_mode='per_item' exists as a schema value but
source_ingest_queue/processor.py hard-refuses anything except 'declared',
so there is no way to split these correctly today). Alex's "go with
Watchman Nee" decision was about the Witness Lee byline specifically, not
a decision to also fold these three back in -- they stay excluded unless
Alex revisits them separately.

Both pages are (c) LIVING STREAM MINISTRY, all rights reserved --
explicitly not public domain, so license_status is 'unlicensed', never
'owned' (Invariant 8): paraphrased propositions only, never verbatim
serving. visibility='shown' below follows the standing 2026-08-01 decision
(#12, CLAUDE.md) that new material defaults to visible -- override to
'hidden' here before running if Alex wants extra caution for a
first-time, actively-enforced-copyright publisher.

Leaves both queue rows cleared_to_run=false, matching the precedent this
script follows (scripts/archive/2026-08/w5_stage_savchuk_web_article_2026-08-19.py)
-- a deliberate second checkpoint before the worker actually fetches and
stores anything. Flip cleared_to_run (or use the existing preview
pipeline) and run scripts/source_ingest_worker.py --once --row-id <id> for
each row as a separate, later attended step.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.services.source_resolver import normalize_alias_key  # noqa: E402
from sync_master_ingestion_queue import determine_default_submitted_by  # noqa: E402

SOURCE_NAME = "Watchman Nee"
SOURCE_VISIBILITY = "shown"  # override to "hidden" for extra caution -- see docstring
SOURCE_NOTES = (
    "Registered 2026-08-25 for watchmannee.org ingestion. Living Stream "
    "Ministry material -- explicit copyright, all rights reserved, "
    "reproduction prohibited. license_status='unlicensed' (never 'owned' "
    "-- Invariant 8): paraphrased propositions only, never verbatim "
    "serving. ATTRIBUTION NOTE: both staged pages carry a trailing page "
    "citation crediting the text to Witness Lee, not Watchman Nee -- e.g. "
    "'A Short Introduction in Memory of Brother Watchman Nee, by Witness "
    "Lee'. Raised to Alex directly with the specific textual evidence "
    "(uniform third-person exposition, no quotation/excerpt markers "
    "anywhere); Alex's explicit decision was to attribute to Watchman Nee "
    "anyway, reasoning that Witness Lee compiled/assembled Nee's own "
    "material. Recorded here so this is read as a deliberate call, not an "
    "oversight."
)

ARTICLES = [
    {
        "url": "https://www.watchmannee.org/major-teachings.html",
        "notes": (
            "watchmannee.org 'Major Teachings' page. Page's own trailing "
            "citation: The Collected Works of Watchman Nee, Volume 1, 'A "
            "Short Introduction in Memory of Brother Watchman Nee', by "
            "Witness Lee, pp. xxviii-xxxvi. (c) LIVING STREAM MINISTRY. "
            "Attributed here to Watchman Nee per Alex's explicit decision "
            "-- see source notes on the 'Watchman Nee' source row for the "
            "full attribution-conflict record."
        ),
    },
    {
        "url": "https://www.watchmannee.org/scriptural-teachings.html",
        "notes": (
            "watchmannee.org 'Other Crucial Scriptural Teachings' page. "
            "Page's own trailing citation: Watchman Nee -- A Seer of the "
            "Divine Revelation in the Present Age, by Witness Lee, pp. "
            "151-167. (c) LIVING STREAM MINISTRY. Attributed here to "
            "Watchman Nee per Alex's explicit decision -- see source notes "
            "on the 'Watchman Nee' source row for the full "
            "attribution-conflict record."
        ),
    },
]


def main() -> int:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL missing", file=sys.stderr)
        return 2

    alias_key = normalize_alias_key(SOURCE_NAME)
    if alias_key != "watchman nee":
        print(f"unexpected alias_key={alias_key!r}", file=sys.stderr)
        return 2

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            "SELECT id, name, license_status, visibility FROM sources WHERE name = %s",
            (SOURCE_NAME,),
        )
        existing = cur.fetchone()
        if existing:
            source_id = str(existing["id"])
            source_created = False
            if existing["license_status"] != "unlicensed":
                raise RuntimeError(f"existing Watchman Nee source has unexpected license_status: {dict(existing)}")
        else:
            cur.execute(
                """
                INSERT INTO sources (name, license_status, visibility, notes)
                VALUES (%s, 'unlicensed', %s, %s)
                RETURNING id, name, license_status, visibility
                """,
                (SOURCE_NAME, SOURCE_VISIBILITY, SOURCE_NOTES),
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
                (alias_key, SOURCE_NAME, source_id, "Registered 2026-08-25 for watchmannee.org ingestion."),
            )
            alias_created = True

        problems: list = []
        submitted_by = determine_default_submitted_by(cur, problems)
        if not submitted_by:
            raise RuntimeError(f"could not determine a default submitted_by: {problems}")

        queue_ids = []
        for article in ARTICLES:
            cur.execute(
                "SELECT id FROM source_ingest_queue WHERE url = %s",
                (article["url"],),
            )
            if cur.fetchone():
                raise RuntimeError(f"queue row already exists for {article['url']}")

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
                RETURNING id, url, cleared_to_run, status
                """,
                (article["url"], SOURCE_NAME, article["notes"], submitted_by),
            )
            queue_row = cur.fetchone()
            queue_ids.append(queue_row["id"])
            assert queue_row["cleared_to_run"] is False
            assert queue_row["status"] == "waiting"

        # Reconciliation reads (same transaction).
        cur.execute("SELECT id, name, license_status, visibility FROM sources WHERE id = %s", (source_id,))
        src = cur.fetchone()
        cur.execute("SELECT alias_key, source_id FROM source_aliases WHERE alias_key = %s", (alias_key,))
        alias = cur.fetchone()
        assert src["license_status"] == "unlicensed"
        assert str(alias["source_id"]) == source_id

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print("RECONCILE")
    print(f"  source_created={source_created} source_id={source_id} visibility={src['visibility']}")
    print(f"  alias_created={alias_created} alias_key={alias_key!r}")
    for article, queue_id in zip(ARTICLES, queue_ids):
        print(f"  queue_id={queue_id} url={article['url']} cleared_to_run=false status=waiting")
    print("OK -- both rows are staged but NOT cleared to run. Flip cleared_to_run and run")
    print("scripts/source_ingest_worker.py --once --row-id <id> for each, separately, when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
