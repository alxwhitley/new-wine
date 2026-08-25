"""Deterministic per-page author-byline extraction and comparison.

Built for the autonomous site crawler (site_ingest_crawler.py): the whole
point of removing per-item human review is that this check has to catch,
by itself, exactly the failure that was found by hand on pastorvlad.org --
a "single teacher" domain that turned out to carry a different family
member's byline on one post. No LLM/AI judgment call here, matching
html_extract.py's posture in this same package: structural, deterministic
signal extraction only.

Three signal sources, checked in order of reliability -- the first one
that yields a name wins:
  1. <meta name="author"> / <meta property="article:author"> content
  2. JSON-LD structured data ("author": {"name": ...} or "author": "...")
  3. A "By <Name>" text pattern at the very start of the already-extracted
     article body (html_extract.extract_article_bounded's output -- NOT
     the raw page, since that function already isolated the article
     container from nav/footer noise)

Comparison is name-token overlap, not exact string equality -- "Craig
Keener" must match "Craig S. Keener" -- but requires every significant
token of the SHORTER normalized name to appear in the longer one, so
"Craig Keener" does not match "Craig Smith", and critically "Vlad
Savchuk" does not match "Lana Savchuk" (a shared surname alone is not a
match -- this is the exact case that has to be caught).

Absence of any signal is UNCONFIRMED, never treated as a pass. This
mirrors Invariant 11's "a reference may only be removed when CONFIRMED
NOT to contain it, never on mere failure to confirm" -- applied here in
the opposite direction: a byline only clears when CONFIRMED to match,
never on mere failure to find a conflicting name. UNCONFIRMED and
MISMATCH are both refusals; only CONFIRMED clears a candidate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple

_NOISE_TOKENS = frozenset(
    {
        "by",
        "posted",
        "written",
        "author",
        "dr",
        "dr.",
        "rev",
        "rev.",
        "pastor",
        "mr",
        "mr.",
        "mrs",
        "mrs.",
        "ms",
        "ms.",
        "jr",
        "jr.",
        "sr",
        "sr.",
    }
)

_BY_LINE_RE = re.compile(
    r"^\s*By[:\s]+([A-Z][\w'.\-]+(?:\s+[A-Z][\w'.\-]+){0,3})",
)

# Bound how far into the article body the "By <Name>" scan looks -- a name
# match found deep in unrelated prose (e.g. quoting someone else) is not a
# byline. Real bylines observed in this corpus's research sit in the first
# ~120 characters (often immediately followed by a date/read-time, e.g.
# "By Vlad Savchuk | May 25, 2026 | 10 minutes").
_BY_LINE_SCAN_CHARS = 200


@dataclass(frozen=True)
class BylineVerdict:
    status: str  # "confirmed" | "mismatch" | "unconfirmed"
    found_name: Optional[str]
    signal_source: Optional[str]  # "meta" | "json_ld" | "by_line" | None


class _HeadSignalParser(HTMLParser):
    """Collects <meta author> content and raw <script type=ld+json> bodies.

    Deliberately does not build a full tree (unlike html_extract.py's
    _ArticleTreeBuilder) -- this only needs two flat signal lists from
    anywhere in the document, not article-body isolation.
    """

    _AUTHOR_META_KEYS = frozenset({"author", "article:author", "og:author"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta_authors: List[str] = []
        self.ld_json_blobs: List[str] = []
        self._in_ld_json = False
        self._ld_json_parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").strip().lower()
            content = (attrs_dict.get("content") or "").strip()
            if key in self._AUTHOR_META_KEYS and content:
                self.meta_authors.append(content)
        elif tag == "script" and (attrs_dict.get("type") or "").strip().lower() == "application/ld+json":
            self._in_ld_json = True
            self._ld_json_parts = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld_json:
            self._in_ld_json = False
            blob = "".join(self._ld_json_parts).strip()
            if blob:
                self.ld_json_blobs.append(blob)

    def handle_data(self, data):
        if self._in_ld_json:
            self._ld_json_parts.append(data)


def _names_from_json_ld_value(value) -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            found.append(name.strip())
    elif isinstance(value, str) and value.strip():
        found.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            found.extend(_names_from_json_ld_value(item))
    return found


def _find_author_in_json_ld_node(node) -> List[str]:
    found: List[str] = []
    if isinstance(node, dict):
        if "author" in node:
            found.extend(_names_from_json_ld_value(node["author"]))
        for value in node.values():
            if isinstance(value, (dict, list)):
                found.extend(_find_author_in_json_ld_node(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_author_in_json_ld_node(item))
    return found


def _extract_json_ld_authors(blobs: List[str]) -> List[str]:
    found: List[str] = []
    for blob in blobs:
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        found.extend(_find_author_in_json_ld_node(parsed))
    return found


def _extract_by_line(article_text: str) -> Optional[str]:
    window = article_text[:_BY_LINE_SCAN_CHARS]
    match = _BY_LINE_RE.search(window)
    if not match:
        return None
    return match.group(1).strip()


def extract_byline_candidates(
    html_bytes: bytes, article_text: str
) -> List[Tuple[str, str]]:
    """Return (source_label, name) pairs in priority order. May be empty."""
    try:
        html_text = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        html_text = ""

    parser = _HeadSignalParser()
    if html_text:
        try:
            parser.feed(html_text)
            parser.close()
        except Exception:
            pass

    candidates: List[Tuple[str, str]] = []
    for name in parser.meta_authors:
        candidates.append(("meta", name))
    for name in _extract_json_ld_authors(parser.ld_json_blobs):
        candidates.append(("json_ld", name))
    by_line_name = _extract_by_line(article_text)
    if by_line_name:
        candidates.append(("by_line", by_line_name))
    return candidates


def _normalize_name(name: str) -> frozenset:
    lowered = re.sub(r"[|,].*$", "", name).strip().lower()
    tokens = re.findall(r"[a-z']+", lowered)
    return frozenset(t for t in tokens if t not in _NOISE_TOKENS and len(t) > 1)


def names_match(declared: str, found: str) -> bool:
    declared_tokens = _normalize_name(declared)
    found_tokens = _normalize_name(found)
    if not declared_tokens or not found_tokens:
        return False
    shorter, longer = (
        (declared_tokens, found_tokens)
        if len(declared_tokens) <= len(found_tokens)
        else (found_tokens, declared_tokens)
    )
    return shorter.issubset(longer)


def verify_byline(
    html_bytes: bytes, article_text: str, declared_author: str
) -> BylineVerdict:
    candidates = extract_byline_candidates(html_bytes, article_text)
    if not candidates:
        return BylineVerdict(status="unconfirmed", found_name=None, signal_source=None)

    for source, name in candidates:
        if names_match(declared_author, name):
            return BylineVerdict(status="confirmed", found_name=name, signal_source=source)

    # A confident signal existed but named someone else -- report the
    # first (highest-priority) one found as the mismatch reason.
    source, name = candidates[0]
    return BylineVerdict(status="mismatch", found_name=name, signal_source=source)
