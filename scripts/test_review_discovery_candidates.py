#!/usr/bin/env python3
"""Regression tests for review_discovery_candidates.py's pure filtering
logic and its Discovery/Approved Sites read-modify-write behavior. Runs
entirely against throwaway temp TSV files -- never
docs/ingestion/master_ingestion_queue_discovery.tsv or
_approved_sites.tsv.

Run: python3.12 scripts/test_review_discovery_candidates.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

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
    check("approving an already-approved-elsewhere name preserves its original provenance", gamma_rows[0]["approved_at"] == "2026-01-01 -- prior manual approval")
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


# ---------------------------------------------------------------------------
# Existing proposal promotion -- a prefilled Approved Sites row with a blank
# `approved` cell must become a real approval in place, not merely suppress a
# duplicate while Discovery is marked verified.
# ---------------------------------------------------------------------------
_proposal_discovery_path, _proposal_approved_path = _build_test_files(
    [
        {
            "verification_status": "unverified",
            "already_in_corpus": False,
            "name": "Existing Proposal",
            "claimed_main_url": "https://new.example.com/blog",
        },
    ],
    [
        {
            "approved": "",
            "name": "Existing Proposal",
            "attribute_to": "Old Attribution",
            "blog_url": "https://old.example.com",
            "proposal_notes": "Prefilled proposal",
            "approved_at": "",
        },
    ],
)
try:
    tool.DISCOVERY_PATH = _proposal_discovery_path
    tool.APPROVED_PATH = _proposal_approved_path

    tool.approve_candidate("Existing Proposal", "https://new.example.com/blog")

    _, proposal_rows = sheet_io.read_tab(tool.APPROVED_PATH)
    check("existing proposal approval does not duplicate the Approved Sites row", len(proposal_rows) == 1)
    proposal = proposal_rows[0]
    check("existing proposal approval sets approved=TRUE", proposal["approved"] == "TRUE")
    check("existing proposal approval refreshes attribute_to", proposal["attribute_to"] == "Existing Proposal")
    check("existing proposal approval refreshes blog_url", proposal["blog_url"] == "https://new.example.com/blog")
    check("existing proposal approval records approval provenance", "review tool approval" in proposal["approved_at"])
    check("existing proposal approval preserves proposal notes", proposal["proposal_notes"] == "Prefilled proposal")
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_proposal_discovery_path.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# decide_and_advance -- controller-facing operation. A successful decision
# must persist through the real TSV write path and return the next candidate
# in one response, so the browser can close the reviewed site and navigate
# its reserved successor tab without a page reload or popup-blocked open.
# ---------------------------------------------------------------------------
_decision_discovery_path, _decision_approved_path = _build_test_files(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "First", "claimed_main_url": "https://first.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Second", "claimed_main_url": "https://second.example.com"},
    ]
)
try:
    tool.DISCOVERY_PATH = _decision_discovery_path
    tool.APPROVED_PATH = _decision_approved_path

    after_approve = tool.decide_and_advance(
        "approve", "First", "https://first.example.com"
    )
    check(
        "approve-and-advance returns the next candidate",
        after_approve == {
            "done": False,
            "candidate": {
                "name": "Second",
                "link": "https://second.example.com",
                "remaining": 1,
            },
        },
    )
    _, decision_approved_rows = sheet_io.read_tab(tool.APPROVED_PATH)
    check(
        "approve-and-advance persists the approval before returning",
        [row["name"] for row in decision_approved_rows] == ["First"],
    )

    after_reject = tool.decide_and_advance(
        "reject", "Second", "https://second.example.com"
    )
    check(
        "reject-and-advance returns the terminal state",
        after_reject == {"done": True, "candidate": None},
    )
    _, decision_discovery_rows = sheet_io.read_tab(tool.DISCOVERY_PATH)
    second_decision_row = next(
        row for row in decision_discovery_rows if row["name"] == "Second"
    )
    check(
        "reject-and-advance persists rejection before returning",
        second_decision_row["verification_status"] == "rejected",
    )

    try:
        tool.decide_and_advance("skip", "Second", "https://second.example.com")
        check("unknown controller decision is rejected", False)
    except ValueError:
        check("unknown controller decision is rejected", True)
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_decision_discovery_path.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Controller HTTP contract -- the real local app must expose a JSON decision
# endpoint so browser JavaScript can save and advance without a page reload.
# ---------------------------------------------------------------------------
_http_discovery_path, _http_approved_path = _build_test_files(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "HTTP First", "claimed_main_url": "https://http-first.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "HTTP Second", "claimed_main_url": "https://http-second.example.com"},
    ]
)
try:
    tool.DISCOVERY_PATH = _http_discovery_path
    tool.APPROVED_PATH = _http_approved_path
    client = TestClient(tool.app)
    landing = client.get("/")
    check("controller landing page succeeds", landing.status_code == 200)
    check(
        "controller exposes an explicit site-tab opener",
        'id="open-site"' in landing.text,
    )
    check(
        "controller exposes approve and reject decision controls",
        'id="approve"' in landing.text and 'id="reject"' in landing.text,
    )
    check(
        "controller exposes a visible tab-lifecycle status",
        'id="review-status"' in landing.text,
    )
    capability_match = re.search(
        r"const capability = (\"(?:[^\"\\]|\\.)*\");",
        landing.text,
    )
    controller_capability = (
        json.loads(capability_match.group(1)) if capability_match else "missing"
    )
    check(
        "controller receives an unguessable mutation capability in local HTML",
        capability_match is not None and len(controller_capability) >= 32,
    )
    response = client.post(
        "/decision",
        data={
            "action": "approve",
            "name": "HTTP First",
            "link": "https://http-first.example.com",
            "capability": controller_capability,
        },
    )
    check("controller decision endpoint succeeds", response.status_code == 200)
    check(
        "controller decision endpoint returns the fresh next candidate",
        response.json() == {
            "done": False,
            "candidate": {
                "name": "HTTP Second",
                "link": "https://http-second.example.com",
                "remaining": 1,
            },
        },
    )
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_http_discovery_path.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Extension API -- the extension must receive its candidate identity from the
# server, so a stale or spoofed browser payload can never decide another row.
# ---------------------------------------------------------------------------
_api_discovery_path, _api_approved_path = _build_test_files(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "API First", "claimed_main_url": "https://api-first.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "API Second", "claimed_main_url": "https://api-second.example.com"},
    ]
)
try:
    tool.DISCOVERY_PATH = _api_discovery_path
    tool.APPROVED_PATH = _api_approved_path
    client = TestClient(tool.app)

    api_current = client.get("/api/review/current")
    current_payload = api_current.json()
    check(
        "extension current endpoint returns the first fresh candidate",
        api_current.status_code == 200
        and current_payload.get("done") is False
        and current_payload.get("candidate") == {
            "name": "API First",
            "link": "https://api-first.example.com",
            "remaining": 2,
        }
        and set(current_payload) == {
            "done", "candidate", "capability", "revision",
        }
        and isinstance(current_payload.get("capability"), str)
        and len(current_payload.get("capability", "")) >= 32
        and isinstance(current_payload.get("revision"), str)
        and len(current_payload.get("revision", "")) >= 32,
    )

    before_start_discovery = tool.DISCOVERY_PATH.read_bytes()
    before_start_approved = tool.APPROVED_PATH.read_bytes()
    api_start = client.post("/api/review/start")
    start_payload = api_start.json()
    check(
        "extension start is read-only and returns the same candidate",
        api_start.status_code == 200
        and start_payload == current_payload
        and tool.DISCOVERY_PATH.read_bytes() == before_start_discovery
        and tool.APPROVED_PATH.read_bytes() == before_start_approved,
    )

    spoofed_approve = client.post(
        "/api/review/decision",
        data={
            "action": "approve",
            "capability": start_payload.get("capability", "missing"),
            "revision": start_payload.get("revision", "missing"),
            "name": "API Second",
            "link": "https://api-second.example.com",
        },
    )
    check(
        "extension decision ignores caller candidate identity and advances",
        spoofed_approve.status_code == 200
        and spoofed_approve.json()["candidate"]["name"] == "API Second",
    )
    _, approved_rows = sheet_io.read_tab(tool.APPROVED_PATH)
    check(
        "extension approval persists the server-selected first candidate",
        [row["name"] for row in approved_rows] == ["API First"],
    )

    api_done = client.post(
        "/api/review/decision",
        data={
            "action": "reject",
            "capability": spoofed_approve.json().get("capability", "missing"),
            "revision": spoofed_approve.json().get("revision", "missing"),
        },
    )
    check(
        "extension final decision returns terminal state",
        api_done.status_code == 200
        and api_done.json().get("done") is True
        and api_done.json().get("candidate") is None
        and set(api_done.json()) == {
            "done", "candidate", "capability", "revision",
        }
        and isinstance(api_done.json().get("revision"), str),
    )
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_api_discovery_path.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Every fallback/extension mutation route requires the unguessable capability.
# A cross-origin form/fetch can reach loopback, so loopback binding alone is
# not authorization. Missing and guessed values must fail before any TSV byte
# changes.
# ---------------------------------------------------------------------------
for route, base_data in (
    ("/yes", {"name": "Guarded", "link": "https://guarded.example.com"}),
    ("/no", {"name": "Guarded"}),
    (
        "/decision",
        {
            "action": "approve",
            "name": "Guarded",
            "link": "https://guarded.example.com",
        },
    ),
    (
        "/api/review/decision",
        {"action": "approve", "revision": "guessed-revision"},
    ),
):
    for capability_label, capability_data in (
        ("missing", {}),
        ("wrong", {"capability": "guessed-capability"}),
    ):
        guarded_discovery, guarded_approved = _build_test_files(
            [
                {
                    "verification_status": "unverified",
                    "already_in_corpus": False,
                    "name": "Guarded",
                    "claimed_main_url": "https://guarded.example.com",
                },
            ]
        )
        try:
            tool.DISCOVERY_PATH = guarded_discovery
            tool.APPROVED_PATH = guarded_approved
            client = TestClient(tool.app)
            before_discovery = guarded_discovery.read_bytes()
            before_approved = guarded_approved.read_bytes()
            denied = client.post(route, data={**base_data, **capability_data})
            check(
                f"{route} rejects {capability_label} mutation capability",
                denied.status_code == 403,
            )
            check(
                f"{route} {capability_label} capability refusal changes no TSV bytes",
                guarded_discovery.read_bytes() == before_discovery
                and guarded_approved.read_bytes() == before_approved,
            )
        finally:
            tool.DISCOVERY_PATH = _original_discovery_path
            tool.APPROVED_PATH = _original_approved_path
            shutil.rmtree(guarded_discovery.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# The extension decision is bound to the exact server-issued queue revision.
# If the first eligible row changes after GET/START, the old decision gets a
# 409 and both files remain byte-identical to their post-mutation state.
# ---------------------------------------------------------------------------
_revision_discovery_path, _revision_approved_path = _build_test_files(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Revision A", "claimed_main_url": "https://revision-a.example.com"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Revision B", "claimed_main_url": "https://revision-b.example.com"},
    ]
)
try:
    tool.DISCOVERY_PATH = _revision_discovery_path
    tool.APPROVED_PATH = _revision_approved_path
    client = TestClient(tool.app)
    issued = client.post("/api/review/start").json()

    revision_headers, revision_rows = sheet_io.read_tab(tool.DISCOVERY_PATH)
    revision_rows[0]["verification_status"] = "verified"
    sheet_io.write_tab(tool.DISCOVERY_PATH, revision_headers, revision_rows)
    after_mutation_discovery = tool.DISCOVERY_PATH.read_bytes()
    after_mutation_approved = tool.APPROVED_PATH.read_bytes()

    conflicted = client.post(
        "/api/review/decision",
        data={
            "action": "approve",
            "capability": issued.get("capability", "missing"),
            "revision": issued.get("revision", "missing"),
        },
    )
    check(
        "extension refuses a decision when the issued candidate revision changed",
        conflicted.status_code == 409,
    )
    check(
        "candidate revision conflict leaves both TSV files byte-identical",
        tool.DISCOVERY_PATH.read_bytes() == after_mutation_discovery
        and tool.APPROVED_PATH.read_bytes() == after_mutation_approved,
    )
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_revision_discovery_path.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Invalid actions are validated before the terminal/empty-queue return.
# ---------------------------------------------------------------------------
_invalid_discovery_path, _invalid_approved_path = _build_test_files([])
try:
    tool.DISCOVERY_PATH = _invalid_discovery_path
    tool.APPROVED_PATH = _invalid_approved_path
    client = TestClient(tool.app)
    issued = client.post("/api/review/start").json()
    before_discovery = tool.DISCOVERY_PATH.read_bytes()
    before_approved = tool.APPROVED_PATH.read_bytes()
    invalid = client.post(
        "/api/review/decision",
        data={
            "action": "skip",
            "capability": issued.get("capability", "missing"),
            "revision": issued.get("revision", "missing"),
        },
    )
    check("empty-queue extension request still rejects unknown action", invalid.status_code == 400)
    check(
        "unknown empty-queue action changes no TSV bytes",
        tool.DISCOVERY_PATH.read_bytes() == before_discovery
        and tool.APPROVED_PATH.read_bytes() == before_approved,
    )

    with patch.object(
        tool,
        "decide_current_and_advance",
        side_effect=tool.StaleFileError("Discovery file changed"),
    ):
        stale = client.post(
            "/api/review/decision",
            data={
                "action": "approve",
                "capability": issued.get("capability", "missing"),
                "revision": issued.get("revision", "missing"),
            },
        )
    check(
        "extension stale-file refusal is a retryable conflict",
        stale.status_code == 409
        and stale.json() == {"error": "Discovery file changed"},
    )
finally:
    tool.DISCOVERY_PATH = _original_discovery_path
    tool.APPROVED_PATH = _original_approved_path
    shutil.rmtree(_invalid_discovery_path.parent, ignore_errors=True)


print(f"\n{len(_checks) - len(_failures)}/{len(_checks)} checks passed")
if _failures:
    print("\nFAILED:")
    for f in _failures:
        print(f"  - {f}")
    raise SystemExit(1)
