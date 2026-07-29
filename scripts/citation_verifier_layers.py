#!/usr/bin/env python3
"""
citation_verifier_layers.py — three-layer, cheapest-first scripture-reference
grounding check, built to widen recognition beyond reference_grounding.py's
compact-form-only scanner ("Hebrews 10:25") to spoken/free-form citation
shapes teachers actually use out loud ("verse 34 of chapter 8 here in
Romans", "the third chapter of 2 Timothy, verse 16").

--------------------------------------------------------------------------
Relationship to reference_grounding.py — NOT a replacement, NOT an edit
--------------------------------------------------------------------------
reference_grounding.py (propositions.py's always-on, unconditional caller,
per CLAUDE.md Invariant 11) is untouched by this file. This module is a
separate, wiring-proven-only build: nothing in propositions.py, closeness_
check.py, or reference_grounding.py imports or calls anything here. Layer 1
below REUSES reference_grounding.find_reference_spans() (imported, not
forked) for the compact-form case, so the existing regression guarantee is
structural, not just tested separately — see layer1_confirm()'s docstring.

--------------------------------------------------------------------------
Reused, never forked (per this build's own scope contract)
--------------------------------------------------------------------------
  - app.constants.BOOK_MAP                                (imported)
  - app.services.reference_verifier._parse_verse_or_range  (imported)
  - reference_grounding.find_reference_spans / GROUNDED / UNGROUNDED /
    UNCERTAIN / check_reference_grounded                   (imported)
  - propositions._get_groq / propositions.EXTRACTION_MODEL (imported, Layer 3)
Every candidate this module's own widened scanner proposes is normalized to
a canonical "Book C:V" or "Book C:V-E" string and re-validated through
_parse_verse_or_range() before being trusted anywhere downstream — this
module never invents its own book/chapter/verse resolution logic; it only
locates raw text shapes and hands the assembled candidate to the same
trusted parser reference_grounding.py already depends on.

--------------------------------------------------------------------------
Three layers, cheapest-first, short-circuit on first confirmation
--------------------------------------------------------------------------
Layer 1 (widened spoken-form scanner, regex-only, no DB/LLM): recognizes
compact form (reused) plus nine widened spoken/written shapes (eight
original spoken forms plus form 9, the "chapter N:M" colon-form-with-no-
"verse"-word gap, added and confirmed real against corpus text this
session) -- see find_layer1_candidates()'s own docstring for the full list.
Confirmation
requires EXACT parsed-tuple equality against the reference under test
(mirrors reference_grounding.check_reference_grounded()'s Arm 1) --
deliberately no range-containment credit.

Layer 2 (document-wide book scope, regex-only, no DB/LLM): given Layer 1
did not confirm, confirms iff the SAME book is named anywhere in the
document (any form Layer 1's book-recognition handles, including a bare
book name with nothing else nearby) AND the same (chapter, verse_start,
verse_end) combination is found anywhere in the document via a book-less
chapter/verse pattern that recovers BOTH numbers together -- never a
verse-only match with no chapter, which would be far too loose. No
proximity requirement between the two findings; whole-document scope is
deliberate. See layer2_confirm()'s docstring.

Layer 3 (LLM read, network -- OFF by default, gated by llm_enabled): only
reached when Layers 1 and 2 both fail to confirm. Asks the model whether
the source document text shows the teacher genuinely engaging the cited
passage (quoting, reading, or naming it in any form) -- a materially
different question than "does this exact citation string appear," which is
what Layers 1-2 already checked and failed to confirm. NOT accuracy-
validated this session -- see call_layer3_llm()'s docstring and this
build's own report for the disclosed limitation. Reuses propositions.
_get_groq()/EXTRACTION_MODEL; no new client, no env read at import time.

--------------------------------------------------------------------------
What this module deliberately does NOT do
--------------------------------------------------------------------------
  - Does not implement range-containment credit (crediting a single-verse
    citation because the source states a covering range) -- explicitly out
    of scope per this build's plan.
  - Does not fold reference_grounding.check_reference_grounded()'s wording
    arm in as an additive pre-LLM tier. That was offered as an OPTIONAL
    pure-reuse addition in the build plan; left out here to avoid inventing
    an unspecified "layer" number/semantics for it. See this build's own
    report for the explicit call-out.
  - Does not touch propositions.py, closeness_check.py, or reference_
    grounding.py. Nothing outside this file and its test file changed.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
Python 3.9 syntax (Optional[str], never str | None -- Invariant 1). No
module-level client construction or env-var reads beyond what propositions.py
already does (reuses its lazy Groq client getter). Same sys.path-extension
trick reference_grounding.py already uses to reach backend/app/*.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent / "backend"
for _p in (str(_THIS_DIR), str(_BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.constants import BOOK_MAP  # noqa: E402
from app.services.reference_verifier import _parse_verse_or_range  # noqa: E402
# _parse_verse_or_range is name-prefixed private in its home module; reused
# anyway, mirroring reference_grounding.py's own explicit precedent for the
# same import -- never reforked (this build's own scope contract).

import reference_grounding as rg  # noqa: E402
import propositions as pw  # noqa: E402
# propositions is imported ONLY for its lazy _get_groq()/EXTRACTION_MODEL --
# no module-level client construction happens as a result of this import;
# propositions.py itself never constructs one at import time either.

ParsedReference = Tuple[str, int, int, Optional[int]]  # (abbrev, chapter, verse_start, verse_end_or_None)


# ═══════════════════════════════════════════════════════════════════════════
# Step 1 — Number/ordinal word→int converter
# ═══════════════════════════════════════════════════════════════════════════
# Cardinals ("four"->4, "twenty-eight"->28, "one hundred fifty"->150),
# ordinals both word-form ("third"->3, "fifty-third"->53) and digit-suffix
# form ("53rd"->53, "1st"->1, "2nd"->2, "3rd"->3, "21st"->21), and pass-
# through for plain digit strings ("15"->15). NEVER guesses: an unrecognized
# token anywhere in the input (any token that isn't a known number word, in
# a position where it's actually valid -- see the ordinal-only-if-last rule
# below) makes the whole conversion return None. No partial credit, no
# best-effort fallback.

_CARDINAL_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_CARDINAL_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_ORDINAL_UNITS = {
    "zeroth": 0, "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
    "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
}
_ORDINAL_TENS = {
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
    "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90,
}

_DIGIT_FORM_RE = re.compile(r'^(\d+)(?:st|nd|rd|th)?$')

# Every recognized number word, longest-first, for building regex
# alternations elsewhere in this module (Layer 1's NUM fragment) --
# analogous to reference_grounding.py's own _BOOK_KEYS_BY_LENGTH precedent.
_NUMBER_WORDS_BY_LENGTH = sorted(
    set(_CARDINAL_UNITS) | set(_CARDINAL_TENS) | {"hundred", "thousand"} |
    set(_ORDINAL_UNITS) | set(_ORDINAL_TENS) | {"hundredth", "thousandth"},
    key=len, reverse=True,
)


def word_or_digit_to_int(s: Optional[str]) -> Optional[int]:
    """Converts a cardinal or ordinal number, in word form or digit form,
    to an int. Returns None for anything it cannot confidently resolve --
    never guesses a wrong-but-plausible integer for unrecognized input.

    Digit form (with or without an ordinal suffix): "15" -> 15, "53rd" -> 53,
    "1st" -> 1, "2nd" -> 2, "3rd" -> 3, "21st" -> 21 -- the suffix itself is
    not checked for grammatical correctness ("21rd" also parses as 21); this
    module only cares about the underlying integer, and a mismatched suffix
    in real prose is a vanishingly unlikely source of a wrong number.

    Word form: a hyphen- or space-separated run of number words, e.g.
    "twenty-eight" -> 28, "one hundred fifty" -> 150, "fifty-third" -> 53.
    An ordinal word (e.g. "third", "fifty-third"'s "third") is only valid as
    the FINAL token -- "third hundred" has no sensible reading and returns
    None, never a guess.
    """
    if s is None:
        return None
    s = s.strip().lower()
    if not s:
        return None

    m = _DIGIT_FORM_RE.match(s)
    if m:
        return int(m.group(1))

    tokens = [t for t in re.split(r'[\s-]+', s) if t]
    if not tokens:
        return None

    total = 0
    current = 0
    matched_any = False
    for idx, tok in enumerate(tokens):
        is_last = idx == len(tokens) - 1
        if tok in _CARDINAL_UNITS:
            current += _CARDINAL_UNITS[tok]
            matched_any = True
        elif tok in _CARDINAL_TENS:
            current += _CARDINAL_TENS[tok]
            matched_any = True
        elif tok == "hundred":
            current = (current or 1) * 100
            matched_any = True
        elif tok == "thousand":
            total += (current or 1) * 1000
            current = 0
            matched_any = True
        elif is_last and tok in _ORDINAL_UNITS:
            current += _ORDINAL_UNITS[tok]
            matched_any = True
        elif is_last and tok in _ORDINAL_TENS:
            current += _ORDINAL_TENS[tok]
            matched_any = True
        elif is_last and tok == "hundredth":
            current = (current or 1) * 100
            matched_any = True
        else:
            # Unrecognized token, or an ordinal word in a non-final
            # position ("third hundred") -- fail closed, never guess.
            return None

    if not matched_any:
        return None
    return total + current


# ═══════════════════════════════════════════════════════════════════════════
# Step 2 — Layer 1: widened spoken-form scanner
# ═══════════════════════════════════════════════════════════════════════════
# Design: a book-alternation fragment built from BOOK_MAP (longest-key-first,
# same technique reference_grounding.py already uses for its own
# _BOOK_PATTERN, so "song of solomon" wins over "song" at the same
# position), a NUM fragment matching either a digit(+ordinal-suffix) run or
# a word-form number phrase (validated for real by word_or_digit_to_int(),
# not by the regex alone -- the regex is deliberately permissive; the
# converter is the actual gate), a bounded/lazy GAP fragment for "book
# separated from numbers by intervening words" tolerance, and five distinct
# pattern shapes covering every required form:
#   PATTERN_A  -- "BOOK [gap] chapter N [gap] [and] verse(s) N[-M]"
#                 covers forms 1 (digits), 2 (ranges), 3 (spelled-out,
#                 period-tolerant), 6 (gap tolerance), 7 ("book of" prefix
#                 via the optional leading group), 8 (explicit "and").
#   PATTERN_B  -- "[the] ORDINAL chapter of BOOK [gap] verse(s) N[-M]"
#                 covers form 5 (ordinal chapters, word- and digit-suffix-
#                 form alike -- NUM handles both).
#   PATTERN_C1 -- "verse(s) N[-M] of chapter N [gap] in/of BOOK"
#                 covers form 4's "verse 34 of chapter 8 ... in Romans" shape.
#   PATTERN_C2 -- "verse(s) N[-M] of BOOK N"
#                 covers form 4's "verse 7 of Hebrews 5" shape.
#   PATTERN_D  -- "BOOK [gap] chapter N:M[-M2]" (colon form directly after
#                 the chapter number, no "verse(s)" word anywhere) -- covers
#                 form 9, the documented gap this build's own plan named
#                 up front ("Hebrews chapter 10:25") and confirmed real and
#                 common corpus-wide in this session's read-only
#                 characterization step (real examples: "Hebrews chapter
#                 10:25", "2 Thessalonians chapter 2:3", "Proverbs chapter
#                 6:10", "Acts chapter 1:7", "1 Thessalonians chapter 4:18",
#                 "2 Corinthians chapter 6:14" -- all found verbatim in live
#                 corpus documents, several directly matching a live
#                 "needs fixing" statement's own failing reference).
# Every pattern REQUIRES an explicit "chapter"/"verse(s)" structural marker
# -- there is no pattern anywhere in this module that accepts a bare
# "Book N M" adjacency with no such marker. This is the precision floor: a
# book word coinciding with two unrelated numbers in ordinary prose, with no
# chapter/verse marker nearby, matches none of these five patterns and
# therefore is never proposed as a candidate at all.
#
# Two hypothesized shapes deliberately NOT added here -- see this build's
# own report for the full real-corpus evidence:
#   - "v."/"vs." as a "verse" alias: real corpus instances exist, but EVERY
#     one found is either (a) an old-commentary Roman-numeral CHAPTER marker
#     in disguise ("Matt. v. 8" = Matthew chapter 5 verse 8, "v." = Roman
#     numeral V, not "verse" at all), or (b) a bare verse-only citation with
#     NO "chapter" keyword anywhere nearby (chapter established, if at all,
#     by an earlier sentence or a non-prose tag). A direct corpus-wide
#     regex sweep for the one shape that WOULD be safe to accept under this
#     module's own precision floor -- "chapter N" co-occurring with
#     "v./vs. M" within the same local span, either order -- returned zero
#     matches anywhere in the corpus. Confirmed real as a citation habit;
#     confirmed NOT to occur in a form this module can safely widen for.
#   - Bare colon-form reference with the book/chapter established only by
#     an earlier, non-adjacent mention (no marker directly attached to the
#     bare "N:M" itself): the one clean literal-shape instance found (a
#     repeated Vlad Savchuk quote citing "James 3:16" once, then repeating
#     the same quote later as bare "3:16") turned out not to be a real
#     verification gap at all -- the exact compact-form "James 3:16" earlier
#     in the SAME document already lets Layer 1's reused compact-form
#     scanner confirm it. A related, genuinely-unconfirmed real shape (Ern
#     Baxter, "Christ's Eternal Lordship" -- "the prayer recorded in John
#     17 ... 'authority over all mankind' (vs. 2 NAS)") has zero chapter OR
#     book marker attached to the number at all, which this module's own
#     precision floor explicitly forbids accepting in Layer 1. Both are
#     documented in this build's report as confirmed-real-but-intentionally-
#     unpatched, not silently dropped.

_NUMBER_WORD_ALT = "|".join(re.escape(w) for w in _NUMBER_WORDS_BY_LENGTH)
_NUM = (
    r'(?:\d{1,3}(?:st|nd|rd|th)?|(?:' + _NUMBER_WORD_ALT + r')'
    r'(?:[\s-]+(?:' + _NUMBER_WORD_ALT + r'))*)'
)

_BOOK_KEYS_BY_LENGTH = sorted(BOOK_MAP.keys(), key=len, reverse=True)
_BOOK_ALT = "|".join(re.escape(k) for k in _BOOK_KEYS_BY_LENGTH)

# 0-4 extra whitespace-delimited tokens, lazy (shortest match first) -- the
# "general gap tolerance, not literal adjacency" the build plan calls for.
# [.,]? immediately before this in each pattern absorbs punctuation
# ("John, my friend, ...") that would otherwise block \s+ from matching.
_GAP = r'(?:\s+\S+){0,4}?'
_RANGE_SEP = r'(?:\s*(?:-|–|—|through|to)\s*)'  # hyphen, en-dash, em-dash, "through", "to"

PATTERN_A = re.compile(
    r'\b(?:the\s+)?(?:book\s+of\s+)?(?P<book>' + _BOOK_ALT + r')[.,]?' + _GAP +
    r'\s+(?:the\s+)?chapter\s+(?P<chapter>' + _NUM + r')[.,]?\s*' + _GAP +
    r'\s*(?:and\s+)?verses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?\b',
    re.IGNORECASE,
)

PATTERN_B = re.compile(
    r'\b(?:the\s+)?(?P<chapter>' + _NUM + r')\s+chapter\s+of\s+'
    r'(?:the\s+book\s+of\s+)?(?P<book>' + _BOOK_ALT + r')[.,]?\s*' + _GAP +
    r'\s*verses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?\b',
    re.IGNORECASE,
)

PATTERN_C1 = re.compile(
    r'\bverses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?'
    r'\s+of\s+(?:the\s+)?chapter\s+(?P<chapter>' + _NUM + r')' + _GAP +
    r'\s+(?:in|of)\s+(?:the\s+book\s+of\s+)?(?P<book>' + _BOOK_ALT + r')\b',
    re.IGNORECASE,
)

PATTERN_C2 = re.compile(
    r'\bverses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?'
    r'\s+of\s+(?:the\s+book\s+of\s+)?(?P<book>' + _BOOK_ALT + r')[.,]?\s+(?P<chapter>' + _NUM + r')\b',
    re.IGNORECASE,
)

# PATTERN_D -- "BOOK [gap] chapter N:M[-M2]", the colon form written
# directly after the chapter number with NO "verse(s)" word anywhere
# ("Hebrews chapter 10:25", never "Hebrews chapter 10, verse 25"). Confirmed
# real and common in this build's own read-only characterization step (see
# this section's module-level comment above and this build's report).
# Structurally identical to PATTERN_A up through the chapter number -- same
# book-alternation fragment, same optional "book of"/"the" prefix, same
# _GAP tolerance between the book and the "chapter" keyword -- diverging
# only in how the verse number is attached: a bare colon directly against
# the chapter number, no verse-word alternative accepted here (that's
# PATTERN_A's job). The "chapter" keyword is still a hard requirement, same
# precision floor as every other pattern in this module.
PATTERN_D = re.compile(
    r'\b(?:the\s+)?(?:book\s+of\s+)?(?P<book>' + _BOOK_ALT + r')[.,]?' + _GAP +
    r'\s+(?:the\s+)?chapter\s+(?P<chapter>' + _NUM + r')\s*:\s*(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?\b',
    re.IGNORECASE,
)

_WIDENED_PATTERNS = [
    ("pattern_a_forward", PATTERN_A),
    ("pattern_b_ordinal_chapter_of_book", PATTERN_B),
    ("pattern_c1_inverted_chapter_in_book", PATTERN_C1),
    ("pattern_c2_inverted_book_chapter", PATTERN_C2),
    ("pattern_d_chapter_colon_form", PATTERN_D),
]


class LayerCandidate(NamedTuple):
    """One candidate scripture reference located by Layer 1's scanner.
    `raw`/`start`/`end` are the matched substring and its character span in
    the text it was found in; `parsed` is its (abbrev, chapter, verse_start,
    verse_end_or_None) tuple, ALREADY validated through
    _parse_verse_or_range() -- a candidate that fails that validation is
    never constructed in the first place (see find_layer1_candidates()).
    `source` names which sub-scanner produced it, for debugging only."""
    raw: str
    start: int
    end: int
    parsed: ParsedReference
    source: str


def find_layer1_candidates(text: str) -> List[LayerCandidate]:
    """Scans `text` for every reference-shaped substring Layer 1
    recognizes: the existing compact form ("Hebrews 10:25", REUSED via
    reference_grounding.find_reference_spans() -- not reimplemented, so the
    compact-form regression guarantee is structural) UNION the five widened
    spoken/written-form patterns above (including PATTERN_D, the "chapter
    N:M" colon form with no "verse" word).

    Every widened-pattern match is normalized to a canonical "Book C:V" or
    "Book C:V-E" string (using the SAME book text and int chapter/verse
    values the pattern captured) and re-validated through
    _parse_verse_or_range() before being trusted -- exactly the discipline
    reference_grounding.find_reference_spans() already enforces for the
    compact form. A candidate whose chapter/verse word(s) don't convert via
    word_or_digit_to_int(), or whose assembled canonical string doesn't
    survive _parse_verse_or_range() (e.g. the captured "book" text doesn't
    resolve via BOOK_MAP after all), is silently dropped -- never guessed.
    """
    out: List[LayerCandidate] = []

    for span in rg.find_reference_spans(text):
        out.append(LayerCandidate(span.raw, span.start, span.end, span.parsed, "compact_form_reused"))

    for name, pattern in _WIDENED_PATTERNS:
        for m in pattern.finditer(text):
            book_raw = m.group("book")
            chapter = word_or_digit_to_int(m.group("chapter"))
            vstart = word_or_digit_to_int(m.group("vstart"))
            if chapter is None or vstart is None:
                continue

            vend_raw = m.groupdict().get("vend")
            vend: Optional[int] = None
            if vend_raw:
                vend = word_or_digit_to_int(vend_raw)
                if vend is None:
                    continue

            canonical = "{0} {1}:{2}".format(book_raw, chapter, vstart)
            if vend is not None:
                canonical += "-{0}".format(vend)

            parsed = _parse_verse_or_range(canonical)
            if parsed is None:
                continue

            out.append(LayerCandidate(m.group(0), m.start(), m.end(), parsed, name))

    return out


def layer1_confirm(reference: str, source_text: str) -> bool:
    """True iff `reference`'s own parsed (abbrev, chapter, verse_start,
    verse_end) tuple EXACTLY matches some Layer-1 candidate found in
    `source_text` -- mirrors reference_grounding.check_reference_grounded()'s
    Arm 1 (`candidate.parsed == parsed`) exactly. No range-containment
    credit: a single-verse reference under test is never confirmed merely
    because the source states a covering range, and vice versa -- deliberate
    scope boundary, not an oversight.

    Returns False (never raises) if `reference` itself doesn't parse -- that
    is the caller's job to have already checked; this function's own
    contract is purely "does this already-parseable reference have an
    exact-match candidate in source_text."
    """
    parsed = _parse_verse_or_range(reference.strip())
    if parsed is None:
        return False
    for candidate in find_layer1_candidates(source_text):
        if candidate.parsed == parsed:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Step 3 — Layer 2: document-wide book scope
# ═══════════════════════════════════════════════════════════════════════════
# Given a reference Layer 1 did not confirm, Layer 2 confirms iff BOTH:
#   1. The same book is named ANYWHERE in the document -- including a bare
#      book name with no numbers nearby at all (e.g. "the book of Romans"
#      with nothing else attached). Reuses the exact same book-alternation
#      fragment (_BOOK_ALT) Layer 1's own patterns use, so "any form Layer
#      1's book-recognition handles" is true by construction, not by a
#      second hand-maintained list.
#   2. The same specific (chapter, verse_start, verse_end) combination is
#      found ANYWHERE in the document via a BOOK-LESS chapter/verse
#      pattern that recovers BOTH the chapter number AND the verse number
#      together -- never a verse-only match with no chapter, which would
#      credit any "verse 25" mention regardless of which chapter it's
#      actually under. The two book-less patterns below are PATTERN_A and
#      PATTERN_C1 with the book group removed entirely (not made optional --
#      removed), so a chapter/verse pair is only ever recovered from text
#      that actually states a chapter number, never inferred from a bare
#      verse mention.
# No proximity/window requirement between condition 1's book-mention and
# condition 2's chapter/verse-mention -- whole-document scope is deliberate.

_BOOK_MENTION_RE = re.compile(r'\b(?:book\s+of\s+)?(' + _BOOK_ALT + r')\b', re.IGNORECASE)

_BOOKLESS_CHAPTER_VERSE_RE = re.compile(
    r'\bchapter\s+(?P<chapter>' + _NUM + r')[.,]?\s*' + _GAP +
    r'\s*(?:and\s+)?verses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?\b',
    re.IGNORECASE,
)
_BOOKLESS_INVERTED_RE = re.compile(
    r'\bverses?\s+(?P<vstart>' + _NUM + r')'
    r'(?:' + _RANGE_SEP + r'(?P<vend>' + _NUM + r'))?'
    r'\s+of\s+(?:the\s+)?chapter\s+(?P<chapter>' + _NUM + r')\b',
    re.IGNORECASE,
)
_BOOKLESS_PATTERNS = [_BOOKLESS_CHAPTER_VERSE_RE, _BOOKLESS_INVERTED_RE]


def _books_named_in_document(text: str) -> Set[str]:
    """Every distinct book abbreviation named ANYWHERE in `text`, in any
    form Layer 1's own book-recognition handles (plain book name or "book
    of X" prefix), including a bare mention with no chapter/verse anywhere
    nearby. Longest-book-key-first via _BOOK_ALT, same precedent as
    reference_grounding.py's own book alternation."""
    found: Set[str] = set()
    for m in _BOOK_MENTION_RE.finditer(text):
        abbrev = BOOK_MAP.get(m.group(1).lower())
        if abbrev:
            found.add(abbrev)
    return found


def find_bookless_chapter_verse_pairs(text: str) -> List[Tuple[int, int, Optional[int]]]:
    """Every (chapter, verse_start, verse_end_or_None) triple found in
    `text` via a pattern that recovers BOTH numbers together, with no book
    name required or consumed. Deliberately does NOT match a bare
    "verse N" with no "chapter" marker anywhere in the same match -- see
    this section's own module-level comment for why that distinction is
    load-bearing."""
    out: List[Tuple[int, int, Optional[int]]] = []
    for pattern in _BOOKLESS_PATTERNS:
        for m in pattern.finditer(text):
            chapter = word_or_digit_to_int(m.group("chapter"))
            vstart = word_or_digit_to_int(m.group("vstart"))
            if chapter is None or vstart is None:
                continue
            vend_raw = m.groupdict().get("vend")
            vend: Optional[int] = None
            if vend_raw:
                vend = word_or_digit_to_int(vend_raw)
                if vend is None:
                    continue
            out.append((chapter, vstart, vend))
    return out


class Layer2Result(NamedTuple):
    confirmed: bool
    multi_book_document: bool
    distinct_book_count: int


def layer2_confirm(reference: str, source_text: str) -> Layer2Result:
    """See this section's module-level comment for the exact two-condition
    contract. `multi_book_document`/`distinct_book_count` describe
    `source_text` as a whole (how many distinct books it names anywhere),
    regardless of whether this call ends up confirmed -- always computed
    from the same book-mention scan, never a separate pass."""
    parsed = _parse_verse_or_range(reference.strip())
    books_named = _books_named_in_document(source_text)
    distinct_book_count = len(books_named)
    multi_book_document = distinct_book_count > 1

    if parsed is None:
        return Layer2Result(False, multi_book_document, distinct_book_count)

    abbrev, chapter, verse_start, verse_end = parsed
    if abbrev not in books_named:
        return Layer2Result(False, multi_book_document, distinct_book_count)

    for (c, vs, ve) in find_bookless_chapter_verse_pairs(source_text):
        if (c, vs, ve) == (chapter, verse_start, verse_end):
            return Layer2Result(True, multi_book_document, distinct_book_count)

    return Layer2Result(False, multi_book_document, distinct_book_count)


# ═══════════════════════════════════════════════════════════════════════════
# Step 4 — Layer 3: LLM read (mocked in tests, no real network call)
# ═══════════════════════════════════════════════════════════════════════════
# Reuses propositions._get_groq()/EXTRACTION_MODEL -- no new client built,
# no env read at import time (propositions._get_groq() itself is lazy).
#
# ACCURACY DISCLOSURE: this prompt is wiring-proven only this session (every
# test below mocks the LLM call entirely -- zero real network calls
# anywhere in the test file). It has not been run against real Groq output
# or evaluated for accuracy. Do not treat a passing test suite here as
# evidence this prompt reliably distinguishes genuine engagement from
# superficial mention in practice.

class LLMVerificationFailed(Exception):
    """Raised by call_layer3_llm() when the Groq call itself did not
    complete (network error, rate limit, timeout) or its response doesn't
    parse as the expected JSON shape. Mirrors propositions.
    PropositionExtractionFailed / rewrite_flagged_statement.RewriteFailed --
    a failed call must never be indistinguishable from a legitimate "no"
    verdict, and this function never silently guesses a verdict on either
    kind of failure."""


LAYER3_PROMPT = """\
You are checking whether a teacher's source document genuinely engages a specific scripture reference. You will be given the reference and the full text of the source document. Your job is ONLY to judge whether the teacher actually engages that passage somewhere in the document -- by quoting its wording, reading it aloud, paraphrasing it, or naming it in any recognizable form (including a spoken-style citation that doesn't look like a standard "Book C:V" string). Do not judge whether the reference is theologically apt or correctly applied -- only whether the passage is genuinely present and engaged with in this text.

THE REFERENCE TO CHECK:
{reference}

THE SOURCE DOCUMENT TEXT:
{source_text}

Output ONLY a JSON object, no preamble, no markdown fences, no explanation:
{{"engaged": true}} or {{"engaged": false}}
"""


def call_layer3_llm(reference: str, source_text: str) -> bool:
    """One Groq call. Returns True if the model judges the source document
    genuinely engages `reference`, False otherwise. Raises
    LLMVerificationFailed on any network/parse/shape failure -- never
    returns a guessed verdict."""
    prompt = LAYER3_PROMPT.format(reference=reference, source_text=source_text)
    try:
        client = pw._get_groq()
        resp = client.chat.completions.create(
            model=pw.EXTRACTION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        verdict = parsed["engaged"]
        if not isinstance(verdict, bool):
            raise LLMVerificationFailed(
                "'engaged' field is not a bool: {0!r}".format(verdict)
            )
        return verdict
    except LLMVerificationFailed:
        raise
    except Exception as exc:
        raise LLMVerificationFailed(str(exc)) from exc


# ═══════════════════════════════════════════════════════════════════════════
# Step 5 — Composition
# ═══════════════════════════════════════════════════════════════════════════

class VerificationResult(NamedTuple):
    confirmed: bool
    layer: Optional[int]     # which layer confirmed (1, 2, or 3), or None if none did
    reason: str               # short machine-readable explanation
    multi_book_document: bool  # only meaningful once Layer 2 has actually run -- see below
    distinct_book_count: int   # only meaningful once Layer 2 has actually run -- see below


def verify_reference_grounded(
    reference: str,
    source_text: str,
    verse_lookup: Optional[Dict[str, str]] = None,
    llm_enabled: bool = False,
) -> VerificationResult:
    """Tries Layer 1, then Layer 2, then (only if llm_enabled=True) Layer 3,
    cheapest-first, short-circuiting on first confirmation.

    `multi_book_document`/`distinct_book_count` describe `source_text` as
    Layer 2 saw it. They are only computed once Layer 2 actually runs (i.e.
    Layer 1 did not already confirm) -- if Layer 1 confirms, or the
    reference itself doesn't parse, these default to (False, 0) rather than
    running an extra, unnecessary book-scan pass just to populate them.

    `verse_lookup`: Layers 1-2 do NOT use it in this build (per the build
    plan, DB-backed wording-arm folding was left out -- see this module's
    top-of-file docstring "What this module deliberately does NOT do").
    Accepted here only so this function's signature matches the plan's
    specified shape; passing a non-None value has no effect in this build.

    Never raises for an ordinary "not confirmed" outcome, including a Layer
    3 LLM call failure (reported via `reason`, not propagated) -- the one
    exception is if `call_layer3_llm` itself is monkeypatched to raise
    something other than LLMVerificationFailed, which is a test-authoring
    bug, not a case this function is designed to swallow.
    """
    parsed = _parse_verse_or_range(reference.strip())
    if parsed is None:
        return VerificationResult(False, None, "unparseable_reference", False, 0)

    if layer1_confirm(reference, source_text):
        return VerificationResult(True, 1, "layer1_widened_scan_match", False, 0)

    layer2 = layer2_confirm(reference, source_text)
    if layer2.confirmed:
        return VerificationResult(
            True, 2, "layer2_document_wide_book_scope",
            layer2.multi_book_document, layer2.distinct_book_count,
        )

    if not llm_enabled:
        return VerificationResult(
            False, None, "not_confirmed_llm_disabled",
            layer2.multi_book_document, layer2.distinct_book_count,
        )

    try:
        engaged = call_layer3_llm(reference, source_text)
    except LLMVerificationFailed as exc:
        return VerificationResult(
            False, None, "layer3_llm_call_failed:{0}".format(exc),
            layer2.multi_book_document, layer2.distinct_book_count,
        )

    if engaged:
        return VerificationResult(
            True, 3, "layer3_llm_confirmed",
            layer2.multi_book_document, layer2.distinct_book_count,
        )
    return VerificationResult(
        False, None, "layer3_llm_denied",
        layer2.multi_book_document, layer2.distinct_book_count,
    )
