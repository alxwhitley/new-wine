#!/usr/bin/env python3
"""Regression tests for the autonomous site crawler's pure, deterministic
components: byline_verify.py, link_discovery.py, and the Approved Sites
tab-reading logic in site_ingest_crawler.py itself (load_approved_site /
load_all_approved_sites). No network, no database -- these are the
components that have to be right for unattended writes to be safe at all,
so they get direct, mutation-checked coverage.

Run: python3.12 scripts/test_site_ingest_crawler.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import ingestion_sheet_io

sys.path.insert(0, str(Path(__file__).resolve().parent))

import site_ingest_crawler
from source_ingest_queue.byline_verify import (
    extract_byline_candidates,
    names_match,
    verify_byline,
)
from source_ingest_queue.fetcher import FetchResult
from source_ingest_queue.link_discovery import discover_links, same_registrable_host

_checks = []
_failures = []


def check(label, condition):
    _checks.append(label)
    if not condition:
        _failures.append(label)
        print(f"FAIL: {label}")


# ---------------------------------------------------------------------------
# names_match -- the single most important function in this whole crawler.
# The real, live-found precedent this exists to catch: a shared surname on
# a family domain is NOT a match (Vlad Savchuk vs Lana Savchuk; Todd Korpi
# vs Tara Korpi; Francis Chan vs "Lisa Chan" -- all found this session).
# ---------------------------------------------------------------------------
check("exact match", names_match("Craig Keener", "Craig Keener"))
check("declared shorter, subset of found", names_match("Craig Keener", "Craig S. Keener"))
check("found shorter, subset of declared", names_match("Craig S. Keener", "Craig Keener"))
check("case-insensitive", names_match("craig keener", "CRAIG KEENER"))
check("honorific in found name ignored", names_match("Craig Keener", "Dr. Craig Keener"))
check("byline date-suffix trailing junk ignored", names_match("Vlad Savchuk", "Vlad Savchuk | May 25, 2026"))

check(
    "REAL PRECEDENT: shared surname, different first name is NOT a match (Vlad/Lana Savchuk)",
    not names_match("Vlad Savchuk", "Lana Savchuk"),
)
check(
    "REAL PRECEDENT: shared surname, different first name is NOT a match (Todd/Tara Korpi)",
    not names_match("Todd Korpi", "Tara Korpi"),
)
check(
    "REAL PRECEDENT: shared surname, different first name is NOT a match (Francis/Lisa Chan)",
    not names_match("Lisa Chan", "Francis Chan"),
)
check("unrelated names do not match", not names_match("Craig Keener", "Bill Johnson"))
check("empty found name never matches", not names_match("Craig Keener", ""))
check("empty declared name never matches", not names_match("", "Craig Keener"))

# ---------------------------------------------------------------------------
# extract_byline_candidates -- three signal sources, priority order.
# ---------------------------------------------------------------------------
meta_html = b"""<html><head>
<meta name="author" content="Craig Keener">
</head><body><article>text</article></body></html>"""
candidates = extract_byline_candidates(meta_html, "")
check("meta author extracted", ("meta", "Craig Keener") in candidates)

article_meta_html = b"""<html><head>
<meta property="article:author" content="Jean-Luc Trachsel">
</head><body></body></html>"""
candidates = extract_byline_candidates(article_meta_html, "")
check("article:author meta extracted", ("meta", "Jean-Luc Trachsel") in candidates)

json_ld_html = b"""<html><head>
<script type="application/ld+json">{"@type":"Article","author":{"@type":"Person","name":"Ray Hughes"}}</script>
</head><body></body></html>"""
candidates = extract_byline_candidates(json_ld_html, "")
check("json-ld object author extracted", ("json_ld", "Ray Hughes") in candidates)

json_ld_string_html = b"""<html><head>
<script type="application/ld+json">{"author": "Kris Vallotton"}</script>
</head></html>"""
candidates = extract_byline_candidates(json_ld_string_html, "")
check("json-ld string author extracted", ("json_ld", "Kris Vallotton") in candidates)

malformed_json_ld_html = b"""<html><head>
<script type="application/ld+json">{not valid json at all</script>
</head></html>"""
candidates = extract_byline_candidates(malformed_json_ld_html, "")
check("malformed json-ld does not raise, yields no json_ld candidate", not any(c[0] == "json_ld" for c in candidates))

by_line_text = "By Vlad Savchuk | May 25, 2026 | 10 minutes\n\nRest of the article body follows here."
candidates = extract_byline_candidates(b"<html></html>", by_line_text)
check("by-line text pattern extracted", any(c[0] == "by_line" and "Vlad Savchuk" in c[1] for c in candidates))

no_signal_text = "This article opens with a scripture quotation, not a byline at all."
candidates = extract_byline_candidates(b"<html></html>", no_signal_text)
check("no signal yields no candidates", candidates == [])

by_line_deep_in_text = "x" * 500 + "\nBy Someone Else"
candidates = extract_byline_candidates(b"<html></html>", by_line_deep_in_text)
check("by-line pattern only scanned near the top, not deep in the body", candidates == [])

priority_html = b"""<html><head>
<meta name="author" content="Craig Keener">
</head></html>"""
candidates = extract_byline_candidates(priority_html, "By Someone Else")
check("meta signal takes priority over by-line text when both present", candidates[0] == ("meta", "Craig Keener"))

# ---------------------------------------------------------------------------
# verify_byline -- end to end, the three real outcomes.
# ---------------------------------------------------------------------------
confirmed = verify_byline(meta_html, "", "Craig Keener")
check("verify_byline: confirmed status", confirmed.status == "confirmed")
check("verify_byline: confirmed found_name", confirmed.found_name == "Craig Keener")

lana_html = b"""<html><head><meta name="author" content="Lana Savchuk"></head></html>"""
mismatch = verify_byline(lana_html, "", "Vlad Savchuk")
check("verify_byline: REAL PRECEDENT mismatch caught (Vlad declared, Lana found)", mismatch.status == "mismatch")

unconfirmed = verify_byline(b"<html><body>no signals here</body></html>", "no by-line here either", "Craig Keener")
check("verify_byline: no signal is unconfirmed, not a silent pass", unconfirmed.status == "unconfirmed")

# Candidate screening must stop before queue insertion when the exact article
# extractor the worker will use has already refused the page. A metadata
# byline can establish authorship, but it cannot make an empty body ingestible.
thin_candidate = FetchResult(
    content=b'<html><head><meta name="author" content="Craig Keener"></head><body><article></article></body></html>',
    final_url="https://craigkeener.com/thin-post/",
    sha256="0" * 64,
    byte_count=105,
    filename="thin-post",
)
with patch.object(site_ingest_crawler, "fetch_html", return_value=thin_candidate):
    thin_result = site_ingest_crawler.check_candidate(
        "https://craigkeener.com/thin-post", "Craig S. Keener"
    )
check("candidate with refused article extraction is not confirmed", thin_result["outcome"] == "extraction_failed")
check("candidate extraction refusal retains the exact gate reason", str(thin_result.get("detail", "")).startswith("article_too_thin:"))

# ---------------------------------------------------------------------------
# link_discovery: same_registrable_host
# ---------------------------------------------------------------------------
check("same host matches", same_registrable_host("https://example.com/a", "https://example.com/b"))
check("www. is stripped for comparison", same_registrable_host("https://www.example.com/a", "https://example.com/b"))
check("different hosts do not match", not same_registrable_host("https://example.com/a", "https://evil.com/a"))
check("subdomain is NOT the same host (conservative)", not same_registrable_host("https://blog.example.com/a", "https://example.com/a"))


class _ExistingUrlCursor:
    def execute(self, sql):
        check("existing URL lookup queries only the queue URL column", sql == "SELECT url FROM source_ingest_queue")

    def fetchall(self):
        return [
            {"url": "https://craigkeener.com/remnant-radio-overcoming-hardship/"},
            {"url": "https://craigkeener.com/another-post/?utm_source=queue#section"},
            {"url": "https://example.com/not-craig/"},
        ]


known_craig_urls = site_ingest_crawler.existing_urls_for_domain(
    _ExistingUrlCursor(), "https://craigkeener.com/blog"
)
check(
    "queued trailing-slash URL matches discovery's slashless canonical form",
    "https://craigkeener.com/remnant-radio-overcoming-hardship" in known_craig_urls,
)
check(
    "queued URL query and fragment are removed by the shared canonical form",
    "https://craigkeener.com/another-post" in known_craig_urls,
)
check(
    "existing URL lookup remains scoped to the requested host",
    "https://example.com/not-craig" not in known_craig_urls,
)

# ---------------------------------------------------------------------------
# link_discovery: discover_links
# ---------------------------------------------------------------------------
index_html = b"""<html><body>
<a href="/my-testimony/">My testimony</a>
<a href="/animal-rights-ethics/">Animal rights ethics</a>
<a href="/category/theology/">Theology</a>
<a href="/tag/grace/">Grace</a>
<a href="/author/craig/">About the author</a>
<a href="https://otherdomain.com/post/">External post</a>
<a href="/page/2/">2</a>
<a href="mailto:hi@example.com">Email</a>
<a href="/img/logo.png">logo</a>
</body></html>"""
result = discover_links(index_html, "https://craigkeener.com/blog", current_page_number=1)
check("post links found", "https://craigkeener.com/my-testimony" in result.post_urls)
check("post links found (second)", "https://craigkeener.com/animal-rights-ethics" in result.post_urls)
check("category link excluded", not any("category" in u for u in result.post_urls))
check("tag link excluded", not any("/tag/" in u for u in result.post_urls))
check("author archive link excluded", not any("/author/" in u for u in result.post_urls))
check("external domain link excluded", not any("otherdomain" in u for u in result.post_urls))
check("image asset link excluded", not any(u.endswith(".png") for u in result.post_urls))
check("mailto link excluded", not any(u.startswith("mailto") for u in result.post_urls))
check("page-number pagination link found as next page", result.next_page_url == "https://craigkeener.com/page/2")

rel_next_html = b"""<html><body>
<a href="/newer-post/">A post</a>
<a rel="next" href="/blog/page/3/">Older Posts</a>
</body></html>"""
result2 = discover_links(rel_next_html, "https://example.com/blog", current_page_number=2)
check("rel=next takes priority", result2.next_page_url == "https://example.com/blog/page/3")

no_next_html = b"""<html><body><a href="/only-post/">Only post</a></body></html>"""
result3 = discover_links(no_next_html, "https://example.com/blog")
check("no next page yields None", result3.next_page_url is None)

nav_html = b"""<html><body>
<header><nav><a href="/about/">About</a><a href="/books/">Books</a></nav></header>
<main><a href="/my-testimony/">My testimony</a></main>
<aside><a href="/popular-tag/">Popular</a></aside>
<footer><a href="/contact/">Contact</a></footer>
</body></html>"""
result5 = discover_links(nav_html, "https://example.com/blog")
check("REAL PRECEDENT: header nav links excluded from post candidates (craigkeener.com)", "https://example.com/about" not in result5.post_urls)
check("header nav links excluded (second)", "https://example.com/books" not in result5.post_urls)
check("aside links excluded", "https://example.com/popular-tag" not in result5.post_urls)
check("footer links excluded", "https://example.com/contact" not in result5.post_urls)
check("real post link inside main is still found", "https://example.com/my-testimony" in result5.post_urls)
check("exactly one candidate survives nav/aside/footer exclusion", result5.post_urls == ["https://example.com/my-testimony"])

nav_with_pagination_html = b"""<html><body>
<main><a href="/some-post/">A post</a></main>
<nav class="pagination"><a rel="next" href="/blog/page/2/">Next</a></nav>
</body></html>"""
result6 = discover_links(nav_with_pagination_html, "https://example.com/blog")
check("pagination nav (not header/footer/aside) is NOT skipped -- next link still found", result6.next_page_url == "https://example.com/blog/page/2")

dedup_html = b"""<html><body>
<a href="/post-a/">A</a>
<a href="/post-a/">A again, different link text</a>
<a href="/post-a/?utm_source=x">A with query string</a>
</body></html>"""
result4 = discover_links(dedup_html, "https://example.com/blog")
check("duplicate/query-variant links collapse to one candidate", result4.post_urls.count("https://example.com/post-a") == 1)
check("only one candidate total after dedup", len(result4.post_urls) == 1)


# ---------------------------------------------------------------------------
# site_ingest_crawler: load_approved_site / load_all_approved_sites -- the
# crawler's entire input surface. A temp TSV file shaped like the real
# Approved Sites data; SHEET_PATH is monkeypatched to point at it for the
# duration of this block, then restored.
# ---------------------------------------------------------------------------
_APPROVED_HEADER = [
    "approved", "name", "attribute_to", "blog_url",
    "authorship_confidence", "scale_note", "proposal_notes", "approved_at",
]


def _build_approved_sites_file(rows):
    tmp = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False)
    tmp.close()
    path = Path(tmp.name)
    ingestion_sheet_io.write_tab(path, _APPROVED_HEADER, rows)
    return path


_original_sheet_path = site_ingest_crawler.SHEET_PATH
_test_wb_path = _build_approved_sites_file(
    [
        {"approved": "TRUE", "name": "Good Site", "attribute_to": "Good Site", "blog_url": "https://good.example.com/blog"},
        {"approved": "yes", "name": "Lowercase Truthy", "attribute_to": "Lowercase Truthy", "blog_url": "https://truthy.example.com/blog"},
        {"approved": "TRUE", "name": "Missing Blog Url", "attribute_to": "Missing Blog Url"},
        {"approved": "FALSE", "name": "Not Approved", "attribute_to": "Not Approved", "blog_url": "https://no.example.com/blog"},
        {"approved": None, "name": "Blank Approved", "attribute_to": "Blank Approved", "blog_url": "https://blank.example.com/blog"},
    ]
)

try:
    site_ingest_crawler.SHEET_PATH = _test_wb_path

    all_sites = site_ingest_crawler.load_all_approved_sites()
    all_names = {s["name"] for s in all_sites}
    check("load_all_approved_sites: TRUE row included", "Good Site" in all_names)
    check("load_all_approved_sites: lowercase truthy value ('yes') included", "Lowercase Truthy" in all_names)
    check("load_all_approved_sites: approved but missing blog_url is skipped, not crashed", "Missing Blog Url" not in all_names)
    check("load_all_approved_sites: FALSE row excluded", "Not Approved" not in all_names)
    check("load_all_approved_sites: blank approved cell excluded", "Blank Approved" not in all_names)
    check("load_all_approved_sites: exactly the two valid rows returned", len(all_sites) == 2)

    named = site_ingest_crawler.load_approved_site("Good Site")
    check("load_approved_site: exact name match returns the row", named["blog_url"] == "https://good.example.com/blog")

    named_ci = site_ingest_crawler.load_approved_site("good site")
    check("load_approved_site: case-insensitive name match", named_ci["name"] == "Good Site")

    try:
        site_ingest_crawler.load_approved_site("Not Approved")
        check("load_approved_site: unapproved named row raises SystemExit", False)
    except SystemExit:
        check("load_approved_site: unapproved named row raises SystemExit", True)

    try:
        site_ingest_crawler.load_approved_site("Missing Blog Url")
        check("load_approved_site: approved-but-incomplete named row raises SystemExit", False)
    except SystemExit:
        check("load_approved_site: approved-but-incomplete named row raises SystemExit", True)

    try:
        site_ingest_crawler.load_approved_site("Nonexistent Site")
        check("load_approved_site: unknown name raises SystemExit", False)
    except SystemExit:
        check("load_approved_site: unknown name raises SystemExit", True)
finally:
    site_ingest_crawler.SHEET_PATH = _original_sheet_path
    _test_wb_path.unlink(missing_ok=True)


print(f"\n{len(_checks) - len(_failures)}/{len(_checks)} checks passed")
if _failures:
    print("\nFAILED:")
    for f in _failures:
        print(f"  - {f}")
    raise SystemExit(1)
