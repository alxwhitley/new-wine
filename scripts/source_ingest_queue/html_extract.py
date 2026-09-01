"""Stdlib-only article-body isolation for queued single-page web sources.

No bs4/lxml dependency exists in backend/requirements.txt (confirmed not
installed in this environment either -- only present in a few standalone,
never-deployed scrape_*.py scripts) -- this module is built entirely on
html.parser.HTMLParser so the queue runner gains no new dependency. It
never crawls: it isolates ONE page's article body from navigation/footer/
sidebar/ad/comment noise, or refuses when it cannot do so defensibly.

Structural, deterministic rules only -- no LLM/AI judgment call:
  1. Hard-strip non-content tags (script, style, nav, header, footer,
     aside, form, ...) at parse time -- their text never enters the tree.
  2. Additionally strip any container whose class/id names a known junk
     region (nav, sidebar, comments, share, newsletter, ...) -- common
     real-world blog markup that isn't inside a semantic tag.
  3. Prefer an explicit <article> tag; then <main>; otherwise pick the
     remaining container with the most text and the lowest link density
     (a simplified readability-style heuristic), requiring it clear a
     minimum confidence floor or refusing rather than guessing.
  4. Refuse thin/empty results and refuse a page whose only substantial
     content is a password-gated login form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Dict, List, Optional, Union


def _bounded_detail(detail: str) -> str:
    return " ".join(str(detail).split())[:240]


class HtmlRejected(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _bounded_detail(detail)
        super().__init__("%s: %s" % (code, self.detail))


@dataclass(frozen=True)
class ExtractedArticle:
    title: str
    text: str
    word_count: int
    evidence: Dict[str, object]


# Same floor propositions.MIN_SUBSTANTIVE_WORD_COUNT already uses corpus-wide
# for "is there enough real content here" -- kept as a local literal rather
# than importing propositions.py (which pulls in DB/model client setup this
# module has no business depending on) to stay a pure text-processing unit.
_MIN_ARTICLE_WORDS = 50

# A page whose only substantial region is a login form is rejected outright;
# above this word count a password field is assumed to be an embedded widget
# (e.g. a header/comment login box) beside otherwise-real article content.
_LOGIN_PAGE_MAX_WORDS = 120

_HARD_MAX_TEXT_CHARS = 2_000_000  # defensive ceiling; fetch already caps bytes

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "iframe",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "button",
        "select",
        "textarea",
        "object",
        "embed",
        "canvas",
    }
)

_VOID_TAGS = frozenset(
    {
        "br",
        "hr",
        "img",
        "input",
        "meta",
        "link",
        "area",
        "base",
        "col",
        "embed",
        "source",
        "track",
        "wbr",
    }
)

_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "article",
        "section",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
        "tr",
        "table",
        "ul",
        "ol",
        "figure",
        "figcaption",
        "br",
    }
)

_CONTAINER_CANDIDATE_TAGS = frozenset({"div", "section"})

# Common real-world blog/CMS class/id naming for non-article regions that
# aren't wrapped in a semantic <nav>/<footer>/<aside> tag. Matched as a
# case-insensitive substring against the combined class+id attribute text.
_JUNK_REGION_RE = re.compile(
    r"(nav(bar|igation)?|menu|footer|header|sidebar|side-bar|comment|"
    r"share|social|related|subscribe|newsletter|advert|promo|cookie|"
    r"popup|modal|breadcrumb|widget|pagination|tag-list|author-box|"
    r"site-nav|masthead)",
    re.IGNORECASE,
)

# Layout wrappers can truthfully advertise that a page has a sidebar without
# being the sidebar themselves. Craig Keener's theme uses
# `cs-site-content cs-sidebar-enabled cs-sidebar-right` around the primary
# article; treating the substring "sidebar" as dispositive erased the whole
# article tree. This exception applies only when the sole junk signal is a
# sidebar layout marker and the same element identifies itself as primary
# content. Real sidebar widgets still take the normal junk path.
_PRIMARY_CONTENT_REGION_RE = re.compile(
    r"(?:^|[-_\s])(?:main|primary|site-content|content-area)(?:$|[-_\s])",
    re.IGNORECASE,
)
_SIDEBAR_ONLY_RE = re.compile(r"(?:sidebar|side-bar)", re.IGNORECASE)


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: Dict[str, Optional[str]], parent):
        self.tag = tag
        self.attrs = attrs
        self.children: List[Union["_Node", str]] = []
        self.parent = parent


def _is_junk_region(tag: str, attrs: Dict[str, Optional[str]]) -> bool:
    if tag not in _CONTAINER_CANDIDATE_TAGS:
        return False
    haystack = "%s %s" % (attrs.get("class") or "", attrs.get("id") or "")
    match = _JUNK_REGION_RE.search(haystack)
    if match is None:
        return False
    if _SIDEBAR_ONLY_RE.fullmatch(match.group(0)) and _PRIMARY_CONTENT_REGION_RE.search(haystack):
        return False
    return True


class _ArticleTreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {}, None)
        self.current = self.root
        self._skip_stack: List[str] = []  # tags currently suppressing content
        self.title_parts: List[str] = []
        self._in_title = False
        self.has_password_input = False

    def _in_skip(self) -> bool:
        return bool(self._skip_stack)

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k: v for k, v in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "input" and (attrs_dict.get("type") or "").strip().lower() == "password":
            self.has_password_input = True

        if self._in_skip():
            if tag not in _VOID_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _SKIP_TAGS or _is_junk_region(tag, attrs_dict):
            if tag not in _VOID_TAGS:
                self._skip_stack.append(tag)
            return
        if tag in _VOID_TAGS:
            return

        node = _Node(tag, attrs_dict, self.current)
        self.current.children.append(node)
        self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if not self._in_skip() and tag not in _VOID_TAGS:
            self.handle_endtag(tag)
        elif self._in_skip() and self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._skip_stack:
            if tag in self._skip_stack:
                # Pop back to (and including) the matching skip frame --
                # tolerant of unclosed tags inside the skipped region.
                while self._skip_stack and self._skip_stack.pop() != tag:
                    pass
            return
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._in_skip():
            return
        if data.strip():
            self.current.children.append(data)


def _node_text(node: _Node) -> str:
    parts: List[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
            continue
        child_text = _node_text(child)
        if not child_text:
            continue
        if child.tag in _BLOCK_TAGS:
            parts.append("\n" + child_text + "\n")
        else:
            parts.append(child_text)
    return "".join(parts)


def _link_word_count(node: _Node) -> int:
    total = 0
    for child in node.children:
        if isinstance(child, str):
            continue
        if child.tag == "a":
            total += len(_node_text(child).split())
        else:
            total += _link_word_count(child)
    return total


def _normalize_text(raw: str) -> str:
    lines = [" ".join(line.split()) for line in raw.split("\n")]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)


def _find_all(node: _Node, tag: str, out: List[_Node]) -> None:
    for child in node.children:
        if isinstance(child, str):
            continue
        if child.tag == tag:
            out.append(child)
        _find_all(child, tag, out)


def _find_first_text(node: _Node, tag: str) -> Optional[str]:
    found: List[_Node] = []
    _find_all(node, tag, found)
    for candidate in found:
        text = _normalize_text(_node_text(candidate))
        if text:
            return text.split("\n\n", 1)[0]
    return None


def _score_candidate(node: _Node) -> float:
    text = _node_text(node)
    words = len(text.split())
    if words == 0:
        return -1.0
    link_words = _link_word_count(node)
    link_density = min(1.0, link_words / words)
    return words * (1.0 - link_density)


def _select_container(root: _Node):
    """Return (node_or_none, evidence_container_label).

    An explicit <article> (then <main>) tag always wins when present, even
    if its own text turns out to be empty/thin -- that is a strong enough
    structural signal that the caller's word-count floor should be the
    thing that refuses it (article_too_thin), not "no container found at
    all" (no_article_body). Only the no-tag heuristic path requires a
    candidate to clear the confidence floor itself before being trusted.
    """
    articles: List[_Node] = []
    _find_all(root, "article", articles)
    if articles:
        return max(articles, key=_score_candidate), "article"

    mains: List[_Node] = []
    _find_all(root, "main", mains)
    if mains:
        return max(mains, key=_score_candidate), "main"

    candidates: List[_Node] = []
    for tag in _CONTAINER_CANDIDATE_TAGS:
        _find_all(root, tag, candidates)
    # Drop candidates that are ancestors of a higher/equal-scoring candidate
    # (e.g. a page-wrapper div containing a post-body div) so a huge wrapper
    # never wins purely by containing everything beneath it.
    scored = [(node, _score_candidate(node)) for node in candidates]
    scored = [pair for pair in scored if pair[1] > 0]
    if not scored:
        return None, "none"

    def _is_ancestor_of_another(node: _Node) -> bool:
        for other, _score in scored:
            probe = other.parent
            while probe is not None:
                if probe is node:
                    return True
                probe = probe.parent
        return False

    leafish = [pair for pair in scored if not _is_ancestor_of_another(pair[0])]
    pool = leafish or scored
    best_node, best_score = max(pool, key=lambda pair: pair[1])
    if best_score < _MIN_ARTICLE_WORDS:
        return None, "none"
    return best_node, "heuristic"


def extract_article_bounded(
    html_bytes: bytes,
    *,
    max_text_chars: int = _HARD_MAX_TEXT_CHARS,
    parser_factory: Callable[[], HTMLParser] = _ArticleTreeBuilder,
) -> ExtractedArticle:
    """Isolate one page's article body, or refuse defensibly.

    Never raises on merely messy/malformed markup -- html.parser.HTMLParser
    is deliberately lenient (unlike an XML parser) and this function treats
    "nothing recognizable extracted" as a normal refusal (no_article_body),
    not an exception. HtmlRejected is raised for every refusal path; an
    unexpected parser fault is wrapped as html_parse_failure rather than
    propagating a raw exception type callers would need to know about.
    """
    try:
        html_text = html_bytes.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - decode with errors="replace" cannot fail
        raise HtmlRejected("html_parse_failure", "could not decode response bytes") from exc

    builder = parser_factory()
    try:
        builder.feed(html_text)
        builder.close()
    except Exception as exc:
        raise HtmlRejected("html_parse_failure", "HTML parsing failed") from exc

    container, label = _select_container(builder.root)
    if container is None:
        if builder.has_password_input:
            raise HtmlRejected(
                "login_page", "page appears to be a login page, not an article"
            )
        raise HtmlRejected(
            "no_article_body", "no defensible article content container was found"
        )

    text = _normalize_text(_node_text(container))
    word_count = len(text.split())

    if builder.has_password_input and word_count <= _LOGIN_PAGE_MAX_WORDS:
        raise HtmlRejected(
            "login_page", "page appears to be a login page, not an article"
        )

    if word_count < _MIN_ARTICLE_WORDS:
        raise HtmlRejected(
            "article_too_thin",
            "extracted article body has only %d word(s)" % word_count,
        )

    if len(text) > max_text_chars:
        raise HtmlRejected("article_text_limit", "extracted article text is too large")

    title = " ".join("".join(builder.title_parts).split())
    if not title:
        title = _find_first_text(container, "h1") or ""

    return ExtractedArticle(
        title=title,
        text=text,
        word_count=word_count,
        evidence={"container": label, "word_count": word_count},
    )
