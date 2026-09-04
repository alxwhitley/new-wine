"""
Prose-channel quotation guard.

The problem this exists for (audit:
`docs/audits/2026-08/scripture_and_quotation_fidelity_2026-08-31.md`):
the answer writer emits verbatim quotations in ordinary prose, attributed
to named teachers. `reference_verifier` grounds the NAME, while the quote
rail's authenticity machinery (`quote_verifier.py`) governs the verified-
quote COMPONENT only. Neither prevents quotation typography in ordinary
prose. Measured on the five stored baseline answers: 7 verbatim teacher
quotations, of which one was
fabricated outright ("one who declares something not his own", credited to
a living minister, zero occurrences corpus-wide), one re-credited another
author's words to the teacher who was quoting him, and one silently
altered a teacher's wording and stripped his own hedge.

The system prompt already forbids this ("Never reproduce quotes or lift
phrasing verbatim, in any mode"). It is not holding. This module is the
deterministic enforcement behind that instruction and Settled decision
#17: verified-quote treatment belongs only to the verified-quote component;
attributed quotations in ordinary prose are prohibited regardless of
whether their wording appears in retrieved evidence.

DESIGN CONSTRAINTS, all load-bearing:

  * DETERMINISTIC ONLY. No model call, no judge, no scoring. Settled #4 /
    Open Decision #20 -- a model-based judge on the answer path has failed
    five times and must not be built. Every check here is string work:
    normalization and position arithmetic.
  * NARROW BY CONSTRUCTION. Only a quotation ATTRIBUTED to a permitted
    teacher name is checked. Scare quotes, terms of art, hypothetical
    non-quotations, and Scripture are deliberately out of scope. Settled
    #6 records the standing objection to a check that drowns in false
    positives from connective prose; a guard that fires on "heretical"
    would be worse than no guard, because its only remedy is regeneration
    and then refusal.
  * NEVER EDITS PROSE. This module reports; it does not rewrite. Surgical
    edits to generated prose are banned (mangling risk -- Settled #6/#15).
    The remedy is the existing, proven regenerate-once-then-refuse path in
    `producer.py`, which this plugs into rather than replacing.
  * NO I/O. Pure functions over strings, so the caller controls both the
    evidence set and the failure posture. Exceptions are allowed to
    propagate into `producer.py`'s existing handler, which refuses cleanly
    (fail-closed) -- consistent with `_missing_required_single_author`.

Nested quotation needs no special resolution here: because ordinary prose
cannot render attributed teacher quotations at all, a teacher quoting a
third party is rejected by the same deterministic rule.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Sequence

# --- Tuning constants, every one chosen from measured data in the audit,
# --- not guessed. Changing one is a deliberate act; see the note on each.

# Shortest real DEFECT observed was 6 words ("piping fresh oil into the
# lampstand"); shortest real clean quotation was 5 ("one who has
# supernatural knowledge"). 5 sits one word below the shortest defect and
# excludes the scare-quote/term-of-art band (1-3 words: "heretical",
# "demonic", "Thus saith the Lord") that this guard must never fire on.
MIN_QUOTED_WORDS = 5

# How far back a permitted teacher name may sit and still count as
# attributing the quotation. Measured attribution distances in the real
# answers ranged from 18 chars ("Prince warns that ...") to ~250 ("In his
# words, ..." inheriting the subject from the previous sentence). 400
# covers paragraph-scoped attribution with margin. Wider trades precision
# for recall; narrower silently drops the "In his words" shape.
ATTRIBUTION_WINDOW_CHARS = 400

# How far FORWARD of the closing quotation mark to look, for the Scripture
# check only. A verse citation trailing its quotation -- `"do not forbid
# speaking in tongues" (1 Cor 14:39)` -- sits entirely after the span, so
# a backward-only window would classify quoted Scripture as teacher
# wording, check it against teacher chunks, and fire on every correctly
# quoted verse. Deliberately tight: wide enough for a trailing
# parenthetical, too narrow to borrow a reference from the next sentence
# and wrongly excuse a real teacher quotation.
TRAILING_CITATION_WINDOW_CHARS = 80

_SINGLE_QUOTES = "‘’‚‛´`"
_DOUBLE_QUOTES = "“”„‟«»"
_DASHES = "‐‑‒–—―"

_TRANSLATION = {ord(c): "'" for c in _SINGLE_QUOTES}
_TRANSLATION.update({ord(c): '"' for c in _DOUBLE_QUOTES})
_TRANSLATION.update({ord(c): "-" for c in _DASHES})
_TRANSLATION[ord("…")] = "..."
_TRANSLATION[ord(" ")] = " "

_WHITESPACE_RE = re.compile(r"\s+")

# A surname must be at least this long to be usable as an attribution key
# on its own. Answers naturally introduce "Derek Prince" once and then
# write "Prince warns that ...", so full-name-only matching silently
# misses every subsequent attribution in a paragraph -- which is where the
# measured fabrication sits. Short tokens are excluded because a 2-3
# character surname would collide with ordinary words.
MIN_SURNAME_CHARS = 4

# Double-quoted spans only. Single quotes are excluded on purpose: an
# apostrophe inside ordinary prose ("Paul's", "'60s") is indistinguishable
# from an opening single quote without parsing, and every measured
# quotation used double quotes.
_QUOTED_SPAN_RE = re.compile(r'["“]([^"“”]{1,600})["”]')

# A Scripture reference sitting inside the window means the quoted span is
# Scripture, not teacher wording. Checking it against teacher chunks would
# never match and would fire on every correctly-quoted verse. Scripture
# fidelity is a real but SEPARATE problem (audit finding 3) with a
# separate fix; conflating them here would make this guard unusable.
_SCRIPTURE_REF_RE = re.compile(
    r'\b(?:[123]\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+\d+:\d+'
)

# A quotation introduced by a NEGATED existence/speech construction is a
# hypothetical the answer is explicitly denying -- "There is no passage
# that says, '...'". Checking it against a teacher's corpus is
# meaningless: it is asserted NOT to exist, so absence is the point, and
# flagging it would regenerate a correct answer. Measured live: this was
# 2 of 5 flags on the real baseline answers, the guard's entire
# false-positive population.
#
# Scoped to the same sentence by forbidding a sentence terminator between
# the negation and the quote. That boundary is what keeps this from
# becoming an evasion: "There is no passage that says X. Prince taught,
# '<fabrication>'" has a period in between, so the fabrication is still
# caught. It also survives coordination -- both halves of `no passage
# says "A," or "B"` are excluded, because neither is separated from the
# negation by a terminator.
_NEGATED_INTRODUCTION_RE = re.compile(
    r"\b(?:"
    r"no\s+(?:passage|verse|text|scripture|scriptures|place|statement|teaching|source|one|teacher)\b"
    r"|nowhere\b"
    r"|never\s+(?:said|says|say|taught|teaches|wrote|writes|claimed|claims)\b"
    r"|(?:does|did|do)\s+not\s+(?:say|says|teach|teaches|claim|claims|state|states)\b"
    r")[^.!?\n]{0,200}$"
)


def normalize_for_match(text: str) -> str:
    """Normalize teacher names and attribution windows for identity matching."""
    folded = unicodedata.normalize("NFKC", text).translate(_TRANSLATION)
    return _WHITESPACE_RE.sub(" ", folded).strip().casefold()


@dataclass(frozen=True)
class AttributedQuotation:
    """A double-quoted span in answer prose that a permitted teacher name
    appears to attribute. `text` is the raw span as written and
    `attributed_to` is the name that qualified it."""
    text: str
    attributed_to: str
    start: int


def _word_count(span: str) -> int:
    return len([w for w in span.split() if w])


def _last_word_start(haystack: str, needle: str) -> int | None:
    """Start of the last whole-word occurrence, or None when absent."""
    if not needle:
        return None
    matches = re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack)
    return max((match.start() for match in matches), default=None)


def _attribution_keys(raw_name: str) -> List[str]:
    """Every normalized form by which this teacher may be credited in
    prose: the full name, and the bare surname once it is long enough to
    be distinctive.

    The surname arm is required for RECALL, and its cost is understood:
    a common surname ("Brown") can match an ordinary word near a
    quotation, over-triggering the guard. That trade is deliberate. An
    over-trigger costs one regeneration; a miss puts fabricated words in a
    living minister's mouth (ranked failure mode #2). The asymmetry is the
    whole reason this module exists.
    """
    full = normalize_for_match(raw_name)
    if not full:
        return []
    keys = [full]
    surname = full.split()[-1] if full.split() else ""
    if len(surname) >= MIN_SURNAME_CHARS and surname != full:
        keys.append(surname)
    return keys


def extract_attributed_quotations(
    answer_text: str, permitted_names: Sequence[str]
) -> List[AttributedQuotation]:
    """Every double-quoted span long enough to be a real quotation, that a
    permitted teacher name attributes, and that is not Scripture.

    Order of the three filters is precision-first and deliberate: length
    is free, Scripture exclusion prevents the largest false-positive
    class, and name attribution is what narrows this to the failure mode
    the audit actually measured.
    """
    if not answer_text or not permitted_names:
        return []

    normalized_names = [
        (raw, _attribution_keys(raw))
        for raw in permitted_names
        if raw and raw.strip()
    ]
    normalized_names = [(raw, keys) for raw, keys in normalized_names if keys]
    if not normalized_names:
        return []

    found: List[AttributedQuotation] = []
    for match in _QUOTED_SPAN_RE.finditer(answer_text):
        span = match.group(1).strip()
        if _word_count(span) < MIN_QUOTED_WORDS:
            continue

        window_start = max(0, match.start() - ATTRIBUTION_WINDOW_CHARS)
        window = answer_text[window_start : match.start()]

        scripture_window = answer_text[
            window_start : match.end() + TRAILING_CITATION_WINDOW_CHARS
        ]
        if _SCRIPTURE_REF_RE.search(scripture_window):
            continue

        if _NEGATED_INTRODUCTION_RE.search(answer_text[:match.start()]):
            continue

        normalized_window = normalize_for_match(window)
        nearest_attribution = None
        for raw, keys in normalized_names:
            position = max(
                (
                    start
                    for key in keys
                    if (start := _last_word_start(normalized_window, key)) is not None
                ),
                default=None,
            )
            if position is not None and (
                nearest_attribution is None or position > nearest_attribution[0]
            ):
                nearest_attribution = (position, raw)
        attributed_to = nearest_attribution[1] if nearest_attribution else None
        if attributed_to is None:
            continue

        found.append(
            AttributedQuotation(
                text=span,
                attributed_to=attributed_to,
                start=match.start(),
            )
        )
    return found


def prohibited_prose_quotations(
    answer_text: str,
    permitted_names: Sequence[str],
) -> List[AttributedQuotation]:
    """Return attributed quotations prohibited in ordinary answer prose.

    Retrieved wording cannot authorize prose quotation typography. The caller
    regenerates once and then refuses; it never edits the answer surgically.
    """
    return extract_attributed_quotations(answer_text, permitted_names)
