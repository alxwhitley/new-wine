#!/usr/bin/env python3
"""
reference_grounding.py — shared predicate: is a scripture reference a model
wrote actually GROUNDED in the source text it was extracted from? (PLAN.md
#45, 2026-07-28 root-cause fabrication fix.)

--------------------------------------------------------------------------
Why this exists
--------------------------------------------------------------------------
Step A (investigation, already approved) found that scripture-reference
fabrication in `propositions.content` is a model obedience failure, not a
prompt-wording gap: scripts/propositions.py's extraction prompt already
forbids inventing scripture references ("invent none it doesn't"), but the
Groq extraction call sometimes violates it anyway, and nothing downstream
ever checked. A now-deleted one-off script also proved extract_propositions()
is directly callable, bypassing process_document()'s gates entirely — so
this predicate is designed to be wired straight into extract_propositions()
itself (see propositions.py), the one place no caller can route around.

This module is the CHECK ONLY. It classifies; it does not strip, does not
log, and does not decide what to do with an UNGROUNDED/UNCERTAIN verdict —
that decision (boundary-safe span removal, seam cleanup, review-file
logging) lives in propositions.py, the caller, exactly like
closeness_check.classify() only classifies and process_document() is the one
that acts on PASS/QUOTE_CANDIDATE/HOLD_TOO_LITTLE.

--------------------------------------------------------------------------
Source-agnostic by design
--------------------------------------------------------------------------
check_reference_grounded()'s second argument is a plain `source_text: str`
— not a document_id, not a chunk list. propositions.py's real caller passes
the whole document text extract_propositions() already has in scope. A
LATER, SEPARATE step (Part 2, corpus-wide detection — not built this
session) can feed this exact same function chunk-reconstructed document
text with zero change to the predicate itself; do not fork it for that use.

--------------------------------------------------------------------------
Two independent grounding arms
--------------------------------------------------------------------------
1. CITATION-STRING arm (always runs, no DB access required): every
   scripture-reference-shaped substring in source_text is located via the
   same free-text scanner used to find the reference being checked in the
   first place (find_reference_spans() below), each candidate is parsed via
   app.services.reference_verifier._parse_verse_or_range() (imported, never
   forked), and compared by PARSED VALUE (abbrev, chapter, verse_start,
   verse_end) against the reference under test — not by raw string equality,
   so "Rom 8:28" in source_text still grounds a proposition that wrote
   "Romans 8:28". If a match is found, GROUNDED, span = that citation's own
   character span in source_text.

2. WORDING arm (only runs if verse_lookup is supplied): looks up the
   referenced verse's (or, for a range, every verse's) WEB text from
   verse_lookup (see closeness_check.build_verse_lookup — a live, read-only
   SELECT of the whole `verses` table, ~31,098 WEB-only rows), then searches
   source_text for a genuine run of that verse's own wording using
   closeness_check's anchor + gap-tolerant-extend + span-density-floor
   matcher (_anchor_extend_density_span — the exact same algorithm
   _find_quote_span already uses for the scripture-wording exemption fix,
   reused here verbatim rather than re-tuned). Catches the case where a
   teacher quotes a verse's actual wording without ever printing a
   chapter:verse citation string, or in a non-WEB translation whose wording
   still shares enough of a contiguous run with WEB's own text to pass the
   anchor+density bar. GROUNDED if found; span = the matched wording's own
   character span in source_text.

closeness_check is LAZY-IMPORTED, and ONLY inside the verse_lookup-supplied
branch of check_reference_grounded() — never at module import time, and
never on a call that doesn't supply verse_lookup. This preserves
propositions.py's existing lazy-import discipline (see that module's
top-of-file docstring): a caller that never builds/passes a verse_lookup —
which is every real caller as of this fix, since extract_propositions() has
no DB access of its own to build one — incurs zero import-time cost or
side effect from closeness_check.

BOOK_MAP (app.constants) and _parse_verse_or_range
(app.services.reference_verifier) ARE imported at module level here, same
as closeness_check.py already does. Neither carries a DB or network side
effect at import time (confirmed by reading both modules: BOOK_MAP is a
plain dict; _parse_verse_or_range is pure regex/dict-lookup code) — only
closeness_check's own module (whose build_verse_lookup/build_name_set/
VocabMatcher machinery is the heavier, DB-touching piece) is the one this
fix's lazy-import obligation actually gates.

--------------------------------------------------------------------------
Three-verdict output contract
--------------------------------------------------------------------------
  GROUNDED    citation string OR (if checkable) verse wording located in
              source_text. `span` is that location's own (start, end) in
              source_text.
  UNGROUNDED  the reference PARSES, but neither arm found it — including
              the case where verse_lookup WAS supplied and the wording arm
              was actually run and failed. A genuine "checked, not there."
  UNCERTAIN   groundedness cannot be determined either way. Two cases:
              (a) the reference string itself doesn't parse (not our job to
              decide reachability for a malformed reference — that's a
              different problem than fabrication); (b) the citation-string
              arm didn't find it AND verse_lookup wasn't supplied, so the
              wording arm never got to run — "not found by the one check we
              could run" is not the same claim as "checked and confirmed
              absent," so this must not be reported as UNGROUNDED.
  Fails toward UNCERTAIN in every genuinely indeterminate case — never
  toward a false GROUNDED (which would let a fabrication through) or a
  false UNGROUNDED (which would claim certainty this module doesn't have).

--------------------------------------------------------------------------
Out of scope (deferred to Part 2, a later step)
--------------------------------------------------------------------------
Bare scripture-attribution phrases with no parseable reference at all (e.g.
"as stated in the scripture") are NOT handled here. find_reference_spans()
only ever returns spans that _parse_verse_or_range() successfully parsed;
anything that doesn't parse to a real book/chapter/verse shape is left
alone entirely by this module's finder, by construction.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
Python 3.9 syntax (Optional[str], never str | None — Invariant 1). No
module-level client construction or env-var reads. stdlib + the same
sys.path-extension trick closeness_check.py already uses to reach
backend/app/*.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent / "backend"
for _p in (str(_THIS_DIR), str(_BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.constants import BOOK_MAP  # noqa: E402
from app.services.reference_verifier import _parse_verse_or_range  # noqa: E402
# _parse_verse_or_range is name-prefixed private in its home module; imported
# anyway per explicit direction (Step A confirmed facts) to reuse it rather
# than reforking book/chapter/verse parsing.

GROUNDED = "GROUNDED"
UNGROUNDED = "UNGROUNDED"
UNCERTAIN = "UNCERTAIN"

ParsedReference = Tuple[str, int, int, Optional[int]]  # (abbrev, chapter, verse_start, verse_end_or_None)


# ── Free-text scripture reference scanner ──────────────────────────────────
# Mirrors closeness_check.py's own _FREE_TEXT_SCRIPTURE_RE (BOOK_MAP-derived
# alternation, longest-book-name-first so e.g. "song of solomon" beats
# "song" at the same position) exactly, REIMPLEMENTED here rather than
# imported from closeness_check — see module docstring's lazy-import note
# for why: closeness_check's own module carries the DB-touching machinery
# this fix must not eagerly import, but BOOK_MAP itself is cheap and side
# -effect-free to import directly.

_BOOK_KEYS_BY_LENGTH = sorted(BOOK_MAP.keys(), key=len, reverse=True)
_BOOK_PATTERN = "|".join(re.escape(k) for k in _BOOK_KEYS_BY_LENGTH)
_REFERENCE_RE = re.compile(
    r"\b(?:" + _BOOK_PATTERN + r")\.?\s+\d{1,3}:\d{1,3}(?:[-–—]\d{1,3})?\b",
    re.IGNORECASE,
)


class ReferenceSpan(NamedTuple):
    """One candidate scripture reference located in a piece of text.
    `raw` is the EXACT substring matched (original casing/spacing/dots),
    `start`/`end` its character span in the text it was found in, `parsed`
    its (abbrev, chapter, verse_start, verse_end_or_None) tuple."""
    raw: str
    start: int
    end: int
    parsed: ParsedReference


def find_reference_spans(text: str) -> List[ReferenceSpan]:
    """Scans `text` for every scripture-reference-shaped substring and
    returns only the ones that survive real parsing via
    _parse_verse_or_range() (imported, not reimplemented) — a candidate that
    only superficially matches the alternation shape (e.g. book name
    followed by an unrelated "N:N" elsewhere) is silently skipped, never
    guessed at. Used both to find the reference under test within a
    proposition's own content (propositions.py's caller) and, inside
    check_reference_grounded()'s citation-string arm, to find every
    candidate citation already present in source_text to compare against."""
    out: List[ReferenceSpan] = []
    for m in _REFERENCE_RE.finditer(text):
        candidate = re.sub(r"\.", " ", m.group(0))
        candidate = re.sub(r"\s+", " ", candidate).strip()
        parsed = _parse_verse_or_range(candidate)
        if parsed is None:
            continue
        out.append(ReferenceSpan(raw=m.group(0), start=m.start(), end=m.end(), parsed=parsed))
    return out


class GroundingResult(NamedTuple):
    status: str                        # GROUNDED | UNGROUNDED | UNCERTAIN
    span: Optional[Tuple[int, int]]    # location in source_text, or None
    reason: str                        # short machine-readable explanation


def check_reference_grounded(
    reference: str,
    source_text: str,
    verse_lookup: Optional[Dict[str, str]] = None,
) -> GroundingResult:
    """Is `reference` (a single reference STRING, e.g. "Philippians 4:8-9",
    already isolated by the caller — this function does not scan running
    text for it) actually grounded in `source_text`? See module docstring
    for the two-arm design and the three-verdict contract.

    verse_lookup: optional (see closeness_check.build_verse_lookup). None
    (the default) means only the citation-string arm runs — sufficient for
    propositions.py's caller, which has no DB access of its own inside
    extract_propositions() to build one. Supplying it enables the wording
    arm too, for callers that have it available (e.g. this module's own
    test suite, or a future caller with a live connection).
    """
    parsed = _parse_verse_or_range(reference.strip())
    if parsed is None:
        # Not our job to judge a reference we can't even parse — a
        # different problem than "did the model fabricate a real-shaped
        # reference." Fail toward UNCERTAIN, never guess.
        return GroundingResult(UNCERTAIN, None, "unparseable_reference")

    # ── Arm 1: citation-string match ───────────────────────────────────────
    for candidate in find_reference_spans(source_text):
        if candidate.parsed == parsed:
            return GroundingResult(GROUNDED, (candidate.start, candidate.end), "citation_string_match")

    # ── Arm 2: verse-wording match (only if verse_lookup supplied) ─────────
    if verse_lookup:
        abbrev, chapter, verse_start, verse_end = parsed
        verse_text = _verse_range_text(verse_lookup, abbrev, chapter, verse_start, verse_end)
        if verse_text is None:
            # Citation parses, but doesn't resolve to any real verse row
            # (e.g. a bad chapter/verse number) -- no ground truth exists to
            # check wording against. Neither arm found it; the wording arm
            # was attempted but had nothing to search for, which is still a
            # genuine "checked, not there" for THIS reference's own text --
            # UNGROUNDED, not UNCERTAIN, since a reference that doesn't even
            # resolve to a real verse cannot be a legitimate citation.
            return GroundingResult(UNGROUNDED, None, "citation_and_wording_both_absent")

        span = _find_wording_span(source_text, verse_text)
        if span is not None:
            return GroundingResult(GROUNDED, span, "verse_wording_match")

        return GroundingResult(UNGROUNDED, None, "citation_and_wording_both_absent")

    # No citation string found, and no verse_lookup to run the wording arm
    # -- genuinely can't determine groundedness, not the same claim as
    # "checked and confirmed absent."
    return GroundingResult(UNCERTAIN, None, "wording_arm_unavailable")


def _verse_range_text(
    verse_lookup: Dict[str, str], abbrev: str, chapter: int, verse_start: int, verse_end: Optional[int],
) -> Optional[str]:
    """Concatenates verse text for a single verse or a full range, using the
    SAME verse_id key format ("{abbrev}.{chapter}.{verse}")
    reference_verifier._resolve_verse_row and closeness_check's own
    _verse_range_text both build. Reimplemented here (three lines, no DB
    access, no closeness_check import needed) rather than importing
    closeness_check._verse_range_text, so this helper stays available
    outside the lazy-import branch without pulling that module in early.
    Returns None if ANY endpoint is missing from verse_lookup -- no partial
    ground truth, no guessing at partial ranges."""
    end = verse_end if verse_end is not None else verse_start
    if end < verse_start:
        return None
    texts: List[str] = []
    for v in range(verse_start, end + 1):
        verse_id = "{0}.{1}.{2}".format(abbrev, chapter, v)
        t = verse_lookup.get(verse_id)
        if t is None:
            return None
        texts.append(t)
    return " ".join(texts)


def _find_wording_span(source_text: str, verse_text: str) -> Optional[Tuple[int, int]]:
    """Searches the WHOLE of source_text (not a citation-anchored window --
    unlike closeness_check._find_quote_span, this predicate has no
    guarantee a citation string exists anywhere nearby; a teacher can quote
    a verse's wording with no chapter:verse in sight) for a genuine run of
    verse_text's own wording, via closeness_check's anchor + gap-tolerant-
    extend + span-density-floor algorithm (_anchor_extend_density_span) --
    the exact same algorithm and constants _find_quote_span already uses,
    reused verbatim rather than re-tuned. Returns the tight (start, end)
    character span in source_text if a qualifying match is found, else
    None. Lazy-imports closeness_check -- see module docstring."""
    import closeness_check as cc

    verse_tokens = cc.tokenize(verse_text)
    if not verse_tokens:
        return None

    text_tokens = cc._tokenize_with_spans(source_text, 0)
    if not text_tokens:
        return None
    words = [t for t, _s, _e in text_tokens]

    found = cc._anchor_extend_density_span(words, verse_tokens)
    if found is None:
        return None
    first_a, last_a, _matched = found
    return text_tokens[first_a][1], text_tokens[last_a][2]
