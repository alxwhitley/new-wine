#!/usr/bin/env python3
"""Regression tests for review_discovery_candidates.py's pure filtering
logic and its Discovery/Approved Sites read-modify-write behavior. Runs
entirely against throwaway temp TSV files -- never
docs/ingestion/master_ingestion_queue_discovery.tsv or
_approved_sites.tsv.

Run: python3.12 scripts/test_review_discovery_candidates.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingestion_sheet_io as sheet_io
import review_discovery_candidates as tool

_checks = []
_failures = []


def check(label, condition):
    _checks.append(label)
    if not condition:
        _failures.append(label)
        print(f"FAIL: {label}")


# ---------------------------------------------------------------------------
# _candidate_link -- pure, no I/O
# ---------------------------------------------------------------------------
check(
    "prefers claimed_blog_or_articles_url",
    tool._candidate_link({"claimed_blog_or_articles_url": "https://a.example.com", "claimed_main_url": "https://b.example.com"}) == "https://a.example.com",
)
check(
    "falls back to claimed_main_url",
    tool._candidate_link({"claimed_main_url": "https://b.example.com"}) == "https://b.example.com",
)
check(
    "falls back to first of other_urls",
    tool._candidate_link({"other_urls": "https://c.example.com; https://d.example.com"}) == "https://c.example.com",
)
check("no link anywhere yields None", tool._candidate_link({}) is None)
check(
    "blank strings treated as absent, falls through to next field",
    tool._candidate_link({"claimed_main_url": "   ", "other_urls": "https://d.example.com"}) == "https://d.example.com",
)

# ---------------------------------------------------------------------------
# build_queue -- pure, no I/O. Exercised with both real Python bools (as a
# caller with in-memory data would pass) AND TSV-shaped "TRUE"/"FALSE"/""
# strings (as a real file read actually returns) -- this is the exact
# distinction that mattered for the 2026-08-26 conversion: the old
# `is True`/`is False` identity checks silently stopped filtering anything
# once already_in_corpus/claimed_written_content_exists became strings.
# ---------------------------------------------------------------------------
_rows_bool = [
    {"name": "Eligible", "verification_status": "unverified", "already_in_corpus": False, "claimed_written_content_exists": True, "claimed_main_url": "https://ok.example.com"},
    {"name": "Already Verified", "verification_status": "verified", "already_in_corpus": False, "claimed_written_content_exists": True, "claimed_main_url": "https://x.example.com"},
    {"name": "Already Rejected", "verification_status": "rejected", "already_in_corpus": False, "claimed_written_content_exists": True, "claimed_main_url": "https://x.example.com"},
    {"name": "In Corpus", "verification_status": "unverified", "already_in_corpus": True, "claimed_written_content_exists": True, "claimed_main_url": "https://x.example.com"},
    {"name": "No Content", "verification_status": "unverified", "already_in_corpus": False, "claimed_written_content_exists": False, "claimed_main_url": "https://x.example.com"},
    {"name": "No Link", "verification_status": "unverified", "already_in_corpus": False, "claimed_written_content_exists": True},
    {"name": "Unknown Content Flag", "verification_status": "unverified", "already_in_corpus": False, "claimed_written_content_exists": None, "claimed_main_url": "https://ok2.example.com"},
]


def _as_tsv_strings(rows):
    """Same rows, but every value shaped the way sheet_io.read_tab() would
    actually hand them back: bools as 'TRUE'/'FALSE' strings, None as ''."""
    out = []
    for row in rows:
        out.append({k: sheet_io.escape_cell(v) for k, v in row.items()})
    return out


for label_suffix, rows_variant in (
    (" (Python bool fixtures)", _rows_bool),
    (" (TSV string fixtures, matching a real file read)", _as_tsv_strings(_rows_bool)),
):
    _queue = tool.build_queue(rows_variant)
    _queue_names = [r["name"] for r, _ in _queue]
    check("eligible row included" + label_suffix, "Eligible" in _queue_names)
    check("already-verified row excluded" + label_suffix, "Already Verified" not in _queue_names)
    check("already-rejected row excluded" + label_suffix, "Already Rejected" not in _queue_names)
    check("already-in-corpus row excluded" + label_suffix, "In Corpus" not in _queue_names)
    check("confirmed-no-content row excluded" + label_suffix, "No Content" not in _queue_names)
    check("row with no usable link excluded" + label_suffix, "No Link" not in _queue_names)
    check("unknown/blank content-exists flag included (not confirmed absent)" + label_suffix, "Unknown Content Flag" in _queue_names)
    check("exactly the two eligible rows returned" + label_suffix, len(_queue) == 2)
    check("sheet order preserved" + label_suffix, _queue_names == ["Eligible", "Unknown Content Flag"])

# ---------------------------------------------------------------------------
# _refuse_if_changed -- direct unit test of the mtime staleness guard that
# replaced the old Excel `~$` lock-file check.
# ---------------------------------------------------------------------------
_tmpdir0 = Path(tempfile.mkdtemp())
try:
    _probe = _tmpdir0 / "probe.tsv"
    _probe.write_text("x\n", encoding="utf-8")
    current_mtime = _probe.stat().st_mtime
    try:
        tool._refuse_if_changed(_probe, current_mtime)
        check("_refuse_if_changed does not raise when mtime is unchanged", True)
    except tool.StaleFileError:
        check("_refuse_if_changed does not raise when mtime is unchanged", False)

    stale_mtime = current_mtime - 100
    try:
        tool._refuse_if_changed(_probe, stale_mtime)
        check("_refuse_if_changed raises StaleFileError when mtime differs", False)
    except tool.StaleFileError:
        check("_refuse_if_changed raises StaleFileError when mtime differs", True)
finally:
    shutil.rmtree(_tmpdir0, ignore_errors=True)

# ---------------------------------------------------------------------------
# approve_candidate / reject_candidate / next_candidate -- end to end
# against throwaway TSV files. DISCOVERY_PATH / APPROVED_PATH are
# monkeypatched.
# ---------------------------------------------------------------------------
_DISCOVERY_HEADER = ["verification_status", "already_in_corpus", "name", "claimed_main_url", "claimed_blog_or_articles_url", "other_urls", "claimed_written_content_exists"]
_APPROVED_HEADER = ["approved", "name", "attribute_to", "blog_url", "authorship_confidence", "scale_note", "proposal_notes", "approved_at"]


def _build_test_files(discovery_rows, approved_rows=None):
    tmpdir = Path(tempfile.mkdtemp())
    discovery_path = tmpdir / "discovery.tsv"
    approved_path = tmpdir / "approved_sites.tsv"
    sheet_io.write_tab(discovery_path, _DISCOVERY_HEADER, discovery_rows)
    sheet_io.write_tab(approved_path, _APPROVED_HEADER, approved_rows or [])
    return discovery_path, approved_path


_original_discovery_path = tool.DISCOVERY_PATH
_original_approved_path = tool.APPROVED_PATH
_discovery_path, _approved_path = _build_test_files(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Alpha", "claimed_main_url": "https://alpha.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Beta", "claimed_main_url": "https://beta.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Already Approved Elsewhere", "claimed_main_url": "https://gamma.example.com"},
    ],
    # Pre-seed Approved Sites with a name that will collide, to exercise the dedupe guard.
    [
        {"approved": "TRUE", "name": "Already Approved Elsewhere", "attribute_to": "Already Approved Elsewhere", "blog_url": "https://gamma.example.com", "approved_at": "2026-01-01 -- prior manual approval"},
    ],
)

try:
    tool.DISCOVERY_PATH = _discovery_path
    tool.APPROVED_PATH = _approved_path

    first = tool.next_candidate()
    check("next_candidate returns the first eligible row", first is not None and first[0]["name"] == "Alpha")
    check("next_candidate reports the full remaining count", first is not None and first[2] == 3)

    tool.approve_candidate("Alpha", "https://alpha.example.com")

    d_headers2, d_rows2 = sheet_io.read_tab(tool.DISCOVERY_PATH)
    check("reviewed_at column was added", "reviewed_at" in d_headers2)
    check("review_notes column was added", "review_notes" in d_headers2)
    alpha_row = next(r for r in d_rows2 if r["name"] == "Alpha")
    check("approved Discovery row marked verified", alpha_row["verification_status"] == "verified")
    check("approved Discovery row got a reviewed_at stamp", bool(alpha_row["reviewed_at"]))
    check("approved Discovery row got a review_notes stamp", bool(alpha_row["review_notes"]))

    _, a_rows2 = sheet_io.read_tab(tool.APPROVED_PATH)
    alpha_approved = next(r for r in a_rows2 if r["name"] == "Alpha")
    check("approve wrote a new Approved Sites row with the right blog_url", alpha_approved["blog_url"] == "https://alpha.example.com")
    check("approve set approved=TRUE", str(alpha_approved["approved"]).strip().upper() == "TRUE")

    second = tool.next_candidate()
    check("next_candidate skips the now-approved row", second is not None and second[0]["name"] == "Beta")
    check("remaining count dropped by one", second is not None and second[2] == 2)

    tool.reject_candidate("Beta")
    _, d_rows3 = sheet_io.read_tab(tool.DISCOVERY_PATH)
    beta_row = next(r for r in d_rows3 if r["name"] == "Beta")
    check("rejected Discovery row marked rejected", beta_row["verification_status"] == "rejected")

    # Approve a candidate whose name already exists in Approved Sites -- should not duplicate.
    tool.approve_candidate("Already Approved Elsewhere", "https://gamma.example.com")
    _, a_rows4 = sheet_io.read_tab(tool.APPROVED_PATH)
    gamma_rows = [r for r in a_rows4 if r["name"] == "Already Approved Elsewhere"]
    check("approving an already-approved-elsewhere name does not duplicate the Approved Sites row", len(gamma_rows) == 1)
    _, d_rows4 = sheet_io.read_tab(tool.DISCOVERY_PATH)
    gamma_discovery = next(r for r in d_rows4 if r["name"] == "Already Approved Elsewhere")
    check("but the Discovery row is still marked verified", gamma_discovery["verification_status"] == "verified")

    final = tool.next_candidate()
    check("queue is empty once every row is decided", final is None)

    # Staleness guard, exercised through the real write path: mutate the
    # Discovery file's mtime forward after a read would have captured it,
    # by writing new content out from under a call already in flight is
    # hard to simulate synchronously -- covered directly above via
    # _refuse_if_changed instead. Here, confirm the exception type surfaces
    # correctly through approve_candidate/reject_candidate's call chain.
    check("StaleFileError is a RuntimeError (existing /yes /no error handling still catches it)", issubclass(tool.StaleFileError, RuntimeError))

    try:
        tool.approve_candidate("Someone Not In The Sheet", "https://nowhere.example.com")
        check("approving an unknown name raises RuntimeError", False)
    except RuntimeError:
        check("approving an unknown name raises RuntimeError", True)
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_discovery_path.parent, ignore_errors=True)


print(f"\n{len(_checks) - len(_failures)}/{len(_checks)} checks passed")
if _failures:
    print("\nFAILED:")
    for f in _failures:
        print(f"  - {f}")
    raise SystemExit(1)
