#!/usr/bin/env python3
"""
ingest_new_position_papers_2026-08-13.py -- one-off script to bring the four
remaining draft position papers (divine_healing, gifts_of_the_spirit_overview,
prophecy_and_the_prophetic, five_fold_ministry) into the same live state as
the existing four pillars (baptism_holy_spirit, speaking_in_tongues,
deliverance_and_spiritual_warfare, prosperity_and_faith_teaching): a real
`documents` row + real `chunks` rows, ingested via the shared chokepoint
(scripts/shared_ingest.py::ingest_document()), under the same "Rhemata" house
source, silent_context, position_paper/position_paper.

Template confirmed by direct live-DB query against all four existing pillar
documents before writing this script (author=None, source_name="Rhemata",
source_type="position_paper", source_kind="position_paper",
citation_mode="silent_context", is_copyrighted=False, source_id=
bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf, file_path="docs/position_papers/<slug>.md").

The TITLE:/AUTHOR:/SOURCE_TYPE: frontmatter lines present in each draft file
are stripped before ingest -- confirmed live that none of the four existing
pillar documents carry these lines in their stored chunk content.

Run once, deliberately. Not idempotent by design (ingest_document() with the
default on_existing="skip" dedup keys on file_path suffix match, so a rerun
against an already-ingested file is a safe no-op, not a duplicate write).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / "backend" / "app" / ".env")

from supabase import create_client
import shared_ingest

RHEMATA_SOURCE_ID = "bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf"

PAPERS = [
    {
        "slug": "divine_healing",
        "title": "Divine Healing",
        "topic_tags": ["Divine Healing", "Healing in the Atonement", "Prayer for the Sick", "Gifts of Healing"],
    },
    {
        "slug": "gifts_of_the_spirit_overview",
        "title": "Gifts of the Spirit — Overview",
        "topic_tags": ["Gifts of the Spirit", "Spiritual Gifts Overview", "Laying On of Hands", "Impartation"],
    },
    {
        "slug": "prophecy_and_the_prophetic",
        "title": "Prophecy and the Prophetic",
        "topic_tags": ["Prophecy", "The Prophetic", "Testing Prophetic Words", "Words of Knowledge and Wisdom"],
    },
    {
        "slug": "five_fold_ministry",
        "title": "The Five-Fold Ministry",
        "topic_tags": ["Five-Fold Ministry", "Apostles and Prophets", "Church Leadership", "Equipping the Saints"],
    },
]

_FRONTMATTER_RE = re.compile(r"^(TITLE|AUTHOR|SOURCE_TYPE):.*\n?", re.MULTILINE)


def strip_frontmatter(raw: str) -> str:
    lines = raw.splitlines()
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or re.match(r"^(TITLE|AUTHOR|SOURCE_TYPE):", stripped, re.IGNORECASE):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip() + "\n"


def db_params():
    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def main():
    dry_run = "--dry-run" in sys.argv
    only = None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = arg.split("=", 1)[1]
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    params = db_params()

    results = {}
    for paper in PAPERS:
        slug = paper["slug"]
        if only and slug != only:
            continue
        file_path = ROOT / "docs" / "position_papers" / f"{slug}.md"
        raw = file_path.read_text(encoding="utf-8")
        body = strip_frontmatter(raw)
        doc_file_path = f"docs/position_papers/{slug}.md"

        already = shared_ingest.already_ingested(params, None, "Rhemata", doc_file_path)
        print(f"=== {slug} === already_ingested={already} body_chars={len(body)}")
        if dry_run:
            results[slug] = {"dry_run": True, "already_ingested": already, "body_chars": len(body)}
            continue

        result = shared_ingest.ingest_document(
            db=db,
            db_params=params,
            title=paper["title"],
            body_text=body,
            filename=f"{slug}.md",
            author=None,
            source_name="Rhemata",
            source_type="position_paper",
            source_kind="position_paper",
            citation_mode="silent_context",
            is_copyrighted=False,
            topic_tags=paper["topic_tags"],
            file_path=doc_file_path,
            source_id=RHEMATA_SOURCE_ID,
            on_existing="skip",
        )
        print(f"    -> {result}")
        results[slug] = result

    print("\n=== SUMMARY ===")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
