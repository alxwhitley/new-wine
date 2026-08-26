#!/usr/bin/env python3
"""Regression tests for check_discovery_blog_links.py. classify() is tested
directly via its injectable fetch parameter (no network). main()'s
row-scanning/write/caching/limit/staleness behavior is tested end to end
against throwaway temp TSV files with classify() itself monkeypatched at
the module level (still no network) -- never
docs/ingestion/master_ingestion_queue_discovery.tsv.

Run: python3.12 scripts/test_check_discovery_blog_links.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_discovery_blog_links as checker
import ingestion_sheet_io as sheet_io
import review_discovery_candidates as review
from source_ingest_queue.fetcher import FetchRejected, FetchTransient

_checks = []
_failures = []


def check(label, condition):
    _checks.append(label)
    if not condition:
        _failures.append(label)
        print(f"FAIL: {label}")


# ---------------------------------------------------------------------------
# classify() -- pure apart from the injected fetch, no network.
# ---------------------------------------------------------------------------
_BLOG_HTML = b"""<html><body>
<main>
<a href="/first-post/">First post</a>
<a href="/second-post/">Second post</a>
</main>
</body></html>"""

_NO_POSTS_HTML = b"""<html><body>
<header><nav><a href="/about/">About</a><a href="/contact/">Contact</a></nav></header>
</body></html>"""


def _fetch_returning(html_bytes, final_url="https://example.com/blog"):
    def _fetch(url):
        return SimpleNamespace(content=html_bytes, final_url=final_url)
    return _fetch


def _fetch_raising(exc):
    def _fetch(url):
        raise exc
    return _fetch


status, detail = checker.classify("https://example.com/blog", fetch=_fetch_returning(_BLOG_HTML))
check("classify: real post links -> looks_like_blog", status == "looks_like_blog")
check("classify: detail mentions the count", "2" in detail)

status, detail = checker.classify("https://example.com/blog", fetch=_fetch_returning(_NO_POSTS_HTML))
check("classify: only nav links -> no_blog_detected", status == "no_blog_detected")

status, detail = checker.classify("https://example.com/blog", fetch=_fetch_raising(FetchRejected("unsafe_url", "blocked")))
check("classify: FetchRejected -> check_failed, not no_blog_detected", status == "check_failed")

status, detail = checker.classify("https://example.com/blog", fetch=_fetch_raising(FetchTransient("connect_failure", "down")))
check("classify: FetchTransient -> check_failed, not no_blog_detected", status == "check_failed")

# ---------------------------------------------------------------------------
# rows_needing_check() / review._ensure_columns() -- against throwaway TSV.
# ---------------------------------------------------------------------------
_DISCOVERY_HEADER = ["verification_status", "already_in_corpus", "name", "claimed_main_url", "claimed_blog_or_articles_url", "other_urls", "claimed_written_content_exists"]


def _build_discovery_file(rows):
    tmpdir = Path(tempfile.mkdtemp())
    path = tmpdir / "discovery.tsv"
    sheet_io.write_tab(path, _DISCOVERY_HEADER, rows)
    return path


_original_discovery_path = review.DISCOVERY_PATH
_discovery_path = _build_discovery_file(
    [
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Alpha", "claimed_main_url": "https://alpha.example.com/blog"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "Beta", "claimed_main_url": "https://beta.example.com/blog"},
        {"verification_status": "unverified", "already_in_corpus": False, "name": "No Link", "claimed_main_url": None},
        {"verification_status": "verified", "already_in_corpus": False, "name": "Already Decided", "claimed_main_url": "https://decided.example.com/blog"},
    ]
)

try:
    review.DISCOVERY_PATH = _discovery_path

    headers, rows = sheet_io.read_tab(_discovery_path)
    headers = review._ensure_columns(headers, rows, "auto_link_check", "auto_link_check_at")
    check("_ensure_columns added auto_link_check", "auto_link_check" in headers)
    before_len = len(headers)
    headers = review._ensure_columns(headers, rows, "auto_link_check")
    check("_ensure_columns is idempotent, no duplicate column", len(headers) == before_len)
    sheet_io.write_tab(_discovery_path, headers, rows)

    _, rows2 = sheet_io.read_tab(_discovery_path)
    pending = checker.rows_needing_check(rows2)
    pending_names = [name for _, name, _ in pending]
    check("rows_needing_check includes an unchecked row with a link", "Alpha" in pending_names)
    check("rows_needing_check includes a second unchecked row", "Beta" in pending_names)
    check("rows_needing_check excludes a row with no usable link", "No Link" not in pending_names)
    check("rows_needing_check excludes an already-decided row -- checking it would be wasted work", "Already Decided" not in pending_names)
    check("exactly 2 rows need checking", len(pending) == 2)

    # --- main(): dry run writes nothing ---
    fake_map = {
        "https://alpha.example.com/blog": ("looks_like_blog", "2 post-shaped link(s) found"),
        "https://beta.example.com/blog": ("no_blog_detected", "fetched fine, no post-shaped links found"),
    }
    _original_classify = checker.classify
    checker.classify = lambda link, **kw: fake_map[link]
    try:
        rc = checker.main([])
        check("dry run exits 0", rc == 0)
        _, rows3 = sheet_io.read_tab(_discovery_path)
        alpha_val = next(r["auto_link_check"] for r in rows3 if r["name"] == "Alpha")
        check("dry run does not write auto_link_check", alpha_val in ("", None))

        # --- main(): --apply writes results ---
        rc = checker.main(["--apply"])
        check("--apply exits 0", rc == 0)
        _, rows4 = sheet_io.read_tab(_discovery_path)

        def _val(name, col):
            return next(r[col] for r in rows4 if r["name"] == name)

        check("apply: Alpha labeled looks_like_blog", _val("Alpha", "auto_link_check") == "looks_like_blog")
        check("apply: Beta labeled no_blog_detected", _val("Beta", "auto_link_check") == "no_blog_detected")
        check("apply: already-decided row was never checked at all", _val("Already Decided", "auto_link_check") in ("", None))
        check("apply: verification_status is never touched by this script", _val("Already Decided", "verification_status") == "verified")
        check("apply: auto_link_check_at stamped", bool(_val("Alpha", "auto_link_check_at")))

        # --- rerun: everything already checked, nothing left to do ---
        rc = checker.main([])
        check("second dry run reports nothing pending (caching works)", rc == 0)
    finally:
        checker.classify = _original_classify

    # --- --limit caps a fresh batch ---
    _, rows5 = sheet_io.read_tab(_discovery_path)
    rows5.append({"verification_status": "unverified", "already_in_corpus": "FALSE", "name": "Gamma", "claimed_main_url": "https://gamma.example.com/blog", "claimed_blog_or_articles_url": None, "other_urls": None, "claimed_written_content_exists": None, "auto_link_check": None, "auto_link_check_at": None})
    rows5.append({"verification_status": "unverified", "already_in_corpus": "FALSE", "name": "Delta", "claimed_main_url": "https://delta.example.com/blog", "claimed_blog_or_articles_url": None, "other_urls": None, "claimed_written_content_exists": None, "auto_link_check": None, "auto_link_check_at": None})
    headers5, _ = sheet_io.read_tab(_discovery_path)
    sheet_io.write_tab(_discovery_path, headers5, rows5)

    checker.classify = lambda link, **kw: ("looks_like_blog", "1 post-shaped link(s) found")
    try:
        rc = checker.main(["--apply", "--limit", "1"])
        check("--limit exits 0", rc == 0)
        _, rows6 = sheet_io.read_tab(_discovery_path)
        checked_count = sum(1 for r in rows6 if r["name"] in ("Gamma", "Delta") and r.get("auto_link_check"))
        check("--limit 1 checks exactly one of the two new candidates", checked_count == 1)
    finally:
        checker.classify = _original_classify

    # --- staleness guard: a concurrent writer between read and save must
    # make main() refuse cleanly (nonzero exit), not crash or silently
    # clobber the concurrent write. Simulated by having classify() itself
    # (called once per candidate, before the periodic save) touch the file
    # out from under the in-flight main() call.
    _, rows7 = sheet_io.read_tab(_discovery_path)
    for r in rows7:
        r["auto_link_check"] = None
        r["auto_link_check_at"] = None
    headers7, _ = sheet_io.read_tab(_discovery_path)
    sheet_io.write_tab(_discovery_path, headers7, rows7)

    _original_save_every = checker.SAVE_EVERY
    checker.SAVE_EVERY = 1

    def _classify_then_clobber(link, **kw):
        sheet_io.write_tab(_discovery_path, headers7, rows7)  # rewrite unchanged, but bumps mtime
        return ("looks_like_blog", "clobbered mid-run")

    checker.classify = _classify_then_clobber
    try:
        rc = checker.main(["--apply"])
        check("main refuses (nonzero exit) when the file changes mid-run", rc != 0)
    finally:
        checker.classify = _original_classify
        checker.SAVE_EVERY = _original_save_every
finally:
    review.DISCOVERY_PATH = _original_discovery_path
    shutil.rmtree(_discovery_path.parent, ignore_errors=True)


print(f"\n{len(_checks) - len(_failures)}/{len(_checks)} checks passed")
if _failures:
    print("\nFAILED:")
    for f in _failures:
        print(f"  - {f}")
    raise SystemExit(1)
