"""
Sub-chunk exclusion detector for the quote rail (Project 3).

Whole-chunk exclusion is handled by chunks.quote_ineligible_reason. This module
detects non-teacher text *inside* a chunk that also contains legitimate teacher
material, so a quote candidate that overlaps the non-teacher span can be refused
without discarding the rest of the chunk.

Every detector here is deterministic and conservative: a span is only excluded
when there is an explicit structural marker identifying it as not the credited
teacher's own words. No LLM/AI judgment call is used.

Detected categories (expandable):
  - translator_note: a footnote signed "-- Translator".
  - block_quotation: a block quotation introduced by an explicit ":—" or
    "writes:" marker followed by an opening quotation mark.
  - muller_inline_quotation: long single-quoted paragraphs in the George
    Müller chapter of /With Christ in the School of Prayer/, where Murray
    quotes Müller inline without the usual attribution marker.
  - catechism_quotation: a Heidelberg/Dutch Reformed catechism or directory
    quotation introduced by an explicit heading.

All spans are byte/character offsets into the chunk content string.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# A detector returns a list of (start, end, reason) tuples.
SubchunkSpan = Tuple[int, int, str]


# ---------------------------------------------------------------------------
# Translator footnotes
# ---------------------------------------------------------------------------
# Two shapes seen in the wild:
#   "1 The Dutch version has: ... -- Translator"  (may wrap across lines)
#   "[The Christian's Secret ... -- Translator]"  (bracketed note)
#
# The marker is a digit NOT followed by a period, followed by horizontal
# whitespace and text on the same line. This avoids matching Murray's
# numbered teaching points ("1. So long as...").
_RE_TRANSLATOR_FOOTNOTE_LINE = re.compile(
    r"(?:^|\n)"
    r"(\s*\d+(?!\.)[^\S\n]+.*?--\s*Translator\b[^\n]*)",
    re.IGNORECASE | re.DOTALL,
)
_RE_TRANSLATOR_BRACKETED = re.compile(
    r"(\[[^\]]*?--\s*Translator\b[^\]]*?\])",
    re.IGNORECASE,
)


def _detect_translator_note_spans(content: str) -> List[SubchunkSpan]:
    """Detect footnote lines/paragraphs signed "-- Translator".

    Conservative: only excludes text that actually contains the signature. The
    signature itself is the marker; the preceding text on the same line/paragraph
    is the translator's note and is also excluded.
    """
    spans = []
    for m in _RE_TRANSLATOR_FOOTNOTE_LINE.finditer(content):
        spans.append((m.start(1), m.end(1), "translator_note"))
    for m in _RE_TRANSLATOR_BRACKETED.finditer(content):
        spans.append((m.start(1), m.end(1), "translator_note"))
    return spans


# ---------------------------------------------------------------------------
# Block quotations introduced by ":—" (colon-emdash) or explicit "writes:"
# ---------------------------------------------------------------------------
# The corpus uses the colon-emdash (":—") as a strong "quotation follows"
# marker. We accept it whether or not it is preceded by an explicit verb,
# because the marker itself plus an opening quotation mark is structural
# evidence that a block quotation follows.
#
# We also catch the related shape "writes:\n(parenthetical)\n‘quote..." seen
# in the George Müller chapter. This is slightly broader, so we require the
# quoted text to be at least 80 characters long to avoid short scripture
# citations.
_RE_QUOTATION_INTRO = re.compile(
    r":—\s*(?:\n|\r\n?)?\s*([\u2018\u201c\"'])",
)
_RE_WRITES_BLOCK = re.compile(
    r"\b(?:write|writes|wrote)\s*(?:\([^\)]+\)\s*)?[:;]\s*([\u2018\u201c\"'])",
    re.IGNORECASE,
)
_MIN_BLOCK_QUOTE_LEN = 80


def _find_block_quote_end(content: str, quote_start: int, opener: str) -> int:
    """Find a plausible end for a block quotation starting at quote_start.

    The opener is one of ‘ “ " '. We look for the first unbalanced matching
    closer after the opening mark. Nested same-direction quotes are handled
    with a depth counter. We only accept a closing mark when it is followed by
    whitespace or common sentence-ending punctuation -- this avoids treating
    an apostrophe inside a word (e.g. "God’s") as a closer.

    If no closer is found inside the chunk, the quotation is treated as
    continuing to the end of the chunk. This is conservative: a quote
    candidate that overlaps any part of the unclosed quotation is refused.
    """
    closer = {
        "\u2018": "\u2019",  # ‘ ’
        "\u201c": "\u201d",  # “ ”
        "\"": "\"",
        "'": "'",
    }.get(opener, opener)

    n = len(content)
    depth = 0
    for pos in range(quote_start + 1, n):
        ch = content[pos]
        if ch == opener:
            depth += 1
        elif ch == closer:
            if depth > 0:
                depth -= 1
            else:
                after = pos + 1
                if after >= n or content[after] in ("\n", "\r", " ", "\t", ".", ",", ";", "!", "?", ")", "]", "}"):
                    return after
                # Otherwise it is probably an apostrophe inside a word; keep looking.
    # No closing mark found inside this chunk; treat the rest as quoted.
    return n


def _detect_block_quotation_spans(content: str) -> List[SubchunkSpan]:
    """Detect block quotations introduced by structural markers.

    Accepts both the strong ":—" marker and the explicit "writes:"
    attribution shape. Only the quoted text is excluded, not the teacher's
    attribution clause before the marker.
    """
    spans = []
    for pattern in (_RE_QUOTATION_INTRO, _RE_WRITES_BLOCK):
        for m in pattern.finditer(content):
            # m.group(1) is the opening quotation mark. Its start is m.end(0) - 1.
            quote_start = m.end(0) - 1
            opener = m.group(1)
            quote_end = _find_block_quote_end(content, quote_start, opener)
            if quote_end - quote_start >= _MIN_BLOCK_QUOTE_LEN:
                spans.append((quote_start, quote_end, "block_quotation"))
    return spans


# ---------------------------------------------------------------------------
# Long marker-less quotations (typically direct Scripture citation)
# ---------------------------------------------------------------------------
# _detect_block_quotation_spans above only catches a quotation with an
# explicit ":—"/"writes:" lead-in marker. Empirically (2026-08-13 -- the 20
# Derek Prince documents that produced zero approved quotes despite passing
# every check below, see CLAUDE.md/PLAN.md), a teacher very often opens a
# quotation with nothing more than "He says," or no lead-in clause at all,
# relying only on the quotation marks themselves. A double-quote-delimited
# span this long is, in this corpus, almost always the quoted text of a
# passage rather than the teacher's own sentence. Threshold matches
# _MIN_BLOCK_QUOTE_LEN so short quoted phrases stay fair game.
_RE_LONG_DOUBLE_QUOTE = re.compile(r"([“\"])([^”\"]{80,}?)([”\"])", re.DOTALL)


def _detect_long_quotation_spans(content: str) -> List[SubchunkSpan]:
    """Detect long double-quote-delimited spans regardless of lead-in marker.

    Intentionally broader than _detect_block_quotation_spans: length alone
    is the signal, because a teacher's own extended original sentences
    essentially never run 80+ characters inside literal quotation marks in
    this corpus -- that shape is characteristic of a quoted passage.
    """
    spans = []
    for m in _RE_LONG_DOUBLE_QUOTE.finditer(content):
        spans.append((m.start(), m.end(), "long_quotation"))
    return spans


# ---------------------------------------------------------------------------
# Inline Müller quotations in the "George Muller" chapter
# ---------------------------------------------------------------------------
# Within the School of Prayer chapter on George Müller, Murray quotes
# Müller's journals/letters as long single-quoted paragraphs without a
# "writes:—" marker. Every long single-quoted span in this chapter is
# Müller's own words (or, rarely, an all-caps institution name). We only
# apply this inside chunks that actually mention Muller, so the false-
# exclusion surface is limited to that chapter.
_RE_MULLER_CHAPTER_MENTION = re.compile(r"\bMuller\b", re.IGNORECASE)
_RE_LONG_SINGLE_QUOTE = re.compile(
    r"([\u2018][^\u2019]{70,}[\u2019])",
    re.DOTALL,
)
_RE_ALLCAPS_SINGLE_QUOTE = re.compile(
    r"([\u2018][A-Z\s\-\n]+[\u2019])",
)


def _detect_muller_inline_spans(content: str) -> List[SubchunkSpan]:
    """Detect inline Müller quotations in the George Müller chapter.

    Conservative scope: only chunks that mention 'Muller'. Within those,
    exclude long single-quoted paragraphs (>70 chars inside the quotes)
    and all-caps single-quoted phrases (institution names). Short single
    quotes, such as the Scripture citations ('Sell that thou hast...'),
    are not excluded.
    """
    if not _RE_MULLER_CHAPTER_MENTION.search(content):
        return []
    spans = []
    for m in _RE_LONG_SINGLE_QUOTE.finditer(content):
        spans.append((m.start(1), m.end(1), "muller_inline_quotation"))
    for m in _RE_ALLCAPS_SINGLE_QUOTE.finditer(content):
        s, e = m.start(1), m.end(1)
        # Avoid double-covering a span already caught by the long-quote regex.
        if any(s >= es and e <= ee for es, ee, _ in spans):
            continue
        spans.append((s, e, "muller_inline_quotation"))
    return spans


# ---------------------------------------------------------------------------
# Catechism / directory quotations
# ---------------------------------------------------------------------------

_RE_CATECHISM_MARKER = re.compile(
    r"(?:Heidelberg\s+Catechism|Der\s+Heidelbergische\s+Catechismus|"
    r"Directory\s+of\s+Public\s+Worship|Westminster\s+Confession|"
    r"Heidelberg\s+Catechismus)",
    re.IGNORECASE,
)


def _detect_catechism_spans(content: str) -> List[SubchunkSpan]:
    """Detect catechism/directory Q&A text quoted inside a chunk.

    We only exclude the quoted Q&A text that follows an explicit marker, not
    the teacher's surrounding commentary. We require the quoted block to look
    like a catechism question ("What is it...?" / "Q. ... ?") to avoid
    matching mere bibliographic citations of the catechism.

    If a question is found, we also attempt to exclude the answer quote that
    immediately follows it in the same chunk. Answers that continue into the
    next chunk cannot be detected without cross-chunk context; they remain a
    documented residual risk.
    """
    spans = []
    for m in _RE_CATECHISM_MARKER.finditer(content):
        search_start = m.end()
        search_end = min(search_start + 600, len(content))
        snippet = content[search_start:search_end]

        # Look for a catechism question.
        qm = re.search(
            r"(?:^|\s)([\u2018\"'])(What\s+is\s+it[^\n]*?\?)[\u2019\"']?\s*(?:\n|\r\n?)",
            snippet,
            re.IGNORECASE,
        )
        if not qm:
            continue

        opener = qm.group(1)
        question_start = search_start + qm.start(1)
        question_end = _find_block_quote_end(content, question_start, opener)
        if question_end <= question_start + 3:
            continue
        spans.append((question_start, question_end, "catechism_quotation"))

        # Look for an answer quote immediately after the question.
        answer_start = question_end
        # Skip whitespace/blank lines.
        while answer_start < len(content) and content[answer_start] in ("\n", "\r", " ", "\t"):
            answer_start += 1
        if answer_start < len(content) and content[answer_start] == opener:
            # Answer starts with the same opening quote mark.
            answer_end = _find_block_quote_end(content, answer_start, opener)
            if answer_end > answer_start + 3:
                spans.append((answer_start, answer_end, "catechism_quotation"))
    return spans


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def detect_excluded_subspans(content: str) -> List[SubchunkSpan]:
    """Return all excluded (start, end, reason) spans inside the chunk content.

    Spans are sorted and deduplicated. The caller is responsible for checking
    whether a candidate quote's [start, end) interval overlaps any returned
    span. A conservative overlap rule is recommended: refuse if any character
    of the candidate lies inside an excluded span.
    """
    spans = []
    spans.extend(_detect_translator_note_spans(content))
    spans.extend(_detect_block_quotation_spans(content))
    spans.extend(_detect_long_quotation_spans(content))
    spans.extend(_detect_muller_inline_spans(content))
    spans.extend(_detect_catechism_spans(content))
    # Sort by start; merge overlapping/nested spans to keep the public list tidy.
    spans.sort(key=lambda s: (s[0], s[1]))
    merged = []
    for start, end, reason in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end), merged[-1][2] + "+" + reason)
        else:
            merged.append((start, end, reason))
    return merged


def candidate_overlaps_excluded_subspan(
    content: str, candidate_text: str, excluded_spans: List[SubchunkSpan]
) -> Tuple[bool, Optional[str]]:
    """Check whether candidate_text (an exact substring of content) overlaps
    any excluded sub-chunk span. Returns (overlaps, reason_or_none).
    """
    start = content.find(candidate_text)
    if start == -1:
        return False, None
    end = start + len(candidate_text)
    for es, ee, reason in excluded_spans:
        if start < ee and end > es:
            return True, reason
    return False, None
