#!/usr/bin/env python3
"""check_discovery_blog_links.py -- one-shot live check of Discovery-tab
candidates, labeling which ones actually look like a real blog/article
site versus which don't.

Why: Discovery's claimed_written_content_exists column is an automated
research pass's GUESS, never a real visit -- and in practice most claimed
candidates aren't real ongoing blogs (dead links, no article list,
PDF-only, a bio page with nothing to read, etc.). This script actually
fetches each unchecked candidate's link (the same SSRF-safe pinned fetch
source_ingest_queue.fetcher already uses) and runs the same post-link
detection site_ingest_crawler.py already uses on approved sites
(source_ingest_queue.link_discovery.discover_links) to see if the page
actually has real post-shaped links -- not just a claim.

Writes a new Discovery column, auto_link_check, one of:
  looks_like_blog  -- at least one real post-shaped link found.
  no_blog_detected -- fetched fine, found none.
  check_failed     -- couldn't fetch/check (network, blocked, etc.) --
                      NOT treated as "no blog". review_discovery_candidates.py
                      still shows these for manual review, since we
                      genuinely don't know either way.
Never touches verification_status -- that column stays Alex's own
decision, never an automated one. Only checks rows that don't already
have an auto_link_check value, so rerunning this later only costs
newly-added/unchecked rows.

review_discovery_candidates.py's queue skips auto_link_check ==
"no_blog_detected" -- so after this runs (with --apply), dead candidates
never surface in the interactive review tool.

Two modes, same convention as every other script that touches this data:
  no flags   -- DRY RUN. Fetches and classifies every unchecked candidate,
                prints the plan, writes nothing.
  --apply    -- Recomputes the identical checks fresh, writes
                auto_link_check + auto_link_check_at to every checked row,
                saving every 10 candidates so an interrupted run keeps
                whatever it already found.

2026-08-26: converted from the .xlsx workbook to
docs/ingestion/master_ingestion_queue_discovery.tsv (see
ingestion_sheet_io.py). The old Excel `~$` lock-file refusal is gone --
plain .tsv carries no such marker -- replaced by review_discovery_candidates.py's
mtime-based write guard (StaleFileError), which this script now goes
through the same as the interactive tool.

Run: python3.12 scripts/check_discovery_blog_links.py [--apply] [--limit N]

Python 3.12 (Invariant 1).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingestion_sheet_io as sheet_io
import review_discovery_candidates as review
from source_ingest_queue.fetcher import FetchRejected, FetchTransient, fetch_html
from source_ingest_queue.link_discovery import discover_links

MIN_POST_LINKS = 1
SAVE_EVERY = 10


def classify(link: str, *, fetch: Callable = fetch_html) -> Tuple[str, str]:
    """(status, detail). status is looks_like_blog / no_blog_detected /
    check_failed. Pure apart from the injected fetch call -- tests pass a
    fake fetch to exercise this without the network."""
    try:
        fetched = fetch(link)
    except (FetchRejected, FetchTransient) as exc:
        return "check_failed", str(exc)
    result = discover_links(fetched.content, fetched.final_url)
    if len(result.post_urls) >= MIN_POST_LINKS:
        return "looks_like_blog", f"{len(result.post_urls)} post-shaped link(s) found"
    return "no_blog_detected", "fetched fine, no post-shaped links found"


def rows_needing_check(rows: List[dict]) -> List[Tuple[dict, str, str]]:
    """(row, name, link) for every still-unverified Discovery row with a
    usable link and no auto_link_check value yet, in file order.
    Already-decided rows (Alex already said Yes/No) are skipped -- checking
    them would never change whether review_discovery_candidates.py shows
    them, so it's a pure waste of a network fetch."""
    pending = []
    for row in rows:
        name = row.get("name")
        if not name:
            continue
        status = row.get("verification_status")
        if str(status or "").strip().lower() != "unverified":
            continue
        if row.get("auto_link_check"):
            continue
        link = review._candidate_link(row)
        if not link:
            continue
        pending.append((row, str(name), link))
    return pending


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write results; omit for a dry run")
    parser.add_argument("--limit", type=int, default=None, help="cap how many new candidates to check this run")
    args = parser.parse_args(argv)

    discovery_mtime = review.DISCOVERY_PATH.stat().st_mtime
    headers, rows = sheet_io.read_tab(review.DISCOVERY_PATH)
    headers = review._ensure_columns(headers, rows, "auto_link_check", "auto_link_check_at")

    to_check = rows_needing_check(rows)
    if args.limit:
        to_check = to_check[: args.limit]

    print(f"{len(to_check)} candidate(s) need checking.")
    if not to_check:
        return 0

    def _save():
        nonlocal discovery_mtime
        review._refuse_if_changed(review.DISCOVERY_PATH, discovery_mtime)
        sheet_io.write_tab(review.DISCOVERY_PATH, headers, rows)
        discovery_mtime = review.DISCOVERY_PATH.stat().st_mtime

    counts = {"looks_like_blog": 0, "no_blog_detected": 0, "check_failed": 0}
    try:
        for i, (row, name, link) in enumerate(to_check, 1):
            status, detail = classify(link)
            counts[status] += 1
            print(f"[{i}/{len(to_check)}] {name} -> {status} ({detail})")
            if args.apply:
                row["auto_link_check"] = status
                row["auto_link_check_at"] = datetime.now(timezone.utc).isoformat()
                if i % SAVE_EVERY == 0:
                    _save()
                    print(f"  (progress saved: {i}/{len(to_check)})")

        if args.apply:
            _save()
            print(
                f"\nSaved. {counts['looks_like_blog']} look like real blogs, "
                f"{counts['no_blog_detected']} auto-skipped (no blog structure found), "
                f"{counts['check_failed']} couldn't be checked (still shown for manual review)."
            )
        else:
            print(
                f"\nDRY RUN complete -- nothing written. Would label: "
                f"{counts['looks_like_blog']} looks_like_blog, "
                f"{counts['no_blog_detected']} no_blog_detected, "
                f"{counts['check_failed']} check_failed. Rerun with --apply to save."
            )
    except review.StaleFileError as exc:
        print(f"\nRefusing to continue: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
