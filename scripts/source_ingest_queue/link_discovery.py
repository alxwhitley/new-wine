"""Deterministic same-domain post-link and pagination discovery for one
blog/article index page.

Stdlib-only, same posture as html_extract.py and byline_verify.py in this
package: structural pattern matching, no LLM/AI judgment call, and no new
dependency. This is inherently a best-effort heuristic -- blog themes vary
a lot -- so it errs toward excluding a link rather than guessing, and the
caller (site_ingest_crawler.py) treats its output as candidates to filter
further (against already-known URLs and the byline check), never as a
final answer.

What counts as a "post link": an <a href> on the same registrable host as
the index page, whose path does not match a known non-post pattern
(category/tag/author/page-number archives, feeds, assets, anchors,
mailto/tel links, the index page itself).

What counts as a "next page" link: an <a> whose rel contains "next", or
whose visible text matches a common pagination label ("next", "older
posts", "more", or a bare page number greater than the current one).

Links inside <header>, <footer>, or <aside> are never treated as post
candidates -- that's where a theme's top nav ("About", "Books", "Free
Resources", ...) and sidebar links live, and without this a run's small
per-run candidate budget gets spent on menu items instead of real posts
(found live against craigkeener.com's actual header nav). <nav> itself is
deliberately NOT blanket-skipped -- article-list pagination controls are
often themselves wrapped in a <nav>, and skipping it would lose the next-
page link along with the menu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urljoin, urlsplit

_NON_POST_PATH_RE = re.compile(
    r"(^/(category|categories|tag|tags|author|authors|page|search|feed|rss|"
    r"wp-json|wp-admin|wp-content|wp-includes|cdn-cgi|cart|checkout|account|"
    r"login|signup|subscribe)(/|$))|(\.(jpg|jpeg|png|gif|svg|webp|css|js|"
    r"pdf|xml|json|ico)$)",
    re.IGNORECASE,
)

_NEXT_TEXT_RE = re.compile(
    r"^\s*(next|older\s*(posts?|entries)?|more\s*posts?|›|»|&raquo;)\s*$",
    re.IGNORECASE,
)

_SKIP_REGION_TAGS = frozenset({"header", "footer", "aside"})
_VOID_TAGS = frozenset(
    {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
)


@dataclass
class DiscoveryResult:
    post_urls: List[str] = field(default_factory=list)
    next_page_url: Optional[str] = None


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: List[dict] = []
        self._current: Optional[dict] = None
        self._text_parts: List[str] = []
        self._skip_stack: List[str] = []

    def _in_skip_region(self) -> bool:
        return bool(self._skip_stack)

    def handle_starttag(self, tag, attrs):
        if self._in_skip_region():
            if tag not in _VOID_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _SKIP_REGION_TAGS:
            self._skip_stack.append(tag)
            return
        if tag != "a":
            return
        attrs_dict = {k: (v or "") for k, v in attrs}
        href = attrs_dict.get("href")
        if not href:
            return
        self._current = {"href": href, "rel": attrs_dict.get("rel", "")}
        self._text_parts = []

    def handle_endtag(self, tag):
        if self._skip_stack:
            if tag in self._skip_stack:
                while self._skip_stack and self._skip_stack.pop() != tag:
                    pass
            return
        if tag != "a" or self._current is None:
            return
        self._current["text"] = " ".join("".join(self._text_parts).split())
        self.links.append(self._current)
        self._current = None
        self._text_parts = []

    def handle_data(self, data):
        if self._in_skip_region():
            return
        if self._current is not None:
            self._text_parts.append(data)


def same_registrable_host(a: str, b: str) -> bool:
    """Public: also used by site_ingest_crawler.py to dedupe against the
    existing source_ingest_queue table without a second implementation."""
    host_a = urlsplit(a).hostname or ""
    host_b = urlsplit(b).hostname or ""
    host_a = host_a[4:] if host_a.startswith("www.") else host_a
    host_b = host_b[4:] if host_b.startswith("www.") else host_b
    return bool(host_a) and host_a == host_b


def normalize_candidate_url(url: str) -> str:
    """Return the canonical form used for discovered and already-queued URLs."""
    split = urlsplit(url)
    return split._replace(fragment="", query="").geturl().rstrip("/")


def _looks_like_post_path(path: str) -> bool:
    if not path or path == "/":
        return False
    if _NON_POST_PATH_RE.search(path):
        return False
    return True


def discover_links(
    html_bytes: bytes, page_url: str, *, current_page_number: int = 1
) -> DiscoveryResult:
    try:
        html_text = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return DiscoveryResult()

    parser = _LinkParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        return DiscoveryResult()

    post_urls: List[str] = []
    seen = set()
    next_page_url: Optional[str] = None

    for link in parser.links:
        absolute = urljoin(page_url, link["href"])
        split = urlsplit(absolute)
        if split.scheme not in ("http", "https"):
            continue
        if not same_registrable_host(absolute, page_url):
            continue
        normalized = normalize_candidate_url(absolute)

        rel = (link.get("rel") or "").lower()
        text = link.get("text") or ""
        if next_page_url is None and (
            "next" in rel.split() or _NEXT_TEXT_RE.match(text)
        ):
            next_page_url = normalized
            continue
        page_number_match = re.fullmatch(r"\d{1,4}", text.strip())
        if (
            next_page_url is None
            and page_number_match
            and int(page_number_match.group()) == current_page_number + 1
        ):
            next_page_url = normalized
            continue

        if not _looks_like_post_path(split.path):
            continue
        if normalized in seen or normalized == page_url.rstrip("/"):
            continue
        seen.add(normalized)
        post_urls.append(normalized)

    return DiscoveryResult(post_urls=post_urls, next_page_url=next_page_url)
