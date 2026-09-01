"""
Prose-channel quotation guard.

The problem this exists for (audit:
`docs/audits/2026-08/scripture_and_quotation_fidelity_2026-08-31.md`):
the answer writer emits verbatim quotations in ordinary prose, attributed
to named teachers, and nothing checked the WORDING. `reference_verifier`
grounds the NAME -- it confirms that teacher's material was actually
retrieved -- and the quote rail's authenticity machinery
(`quote_verifier.py`) governs the verified-quote COMPONENT only. Neither
looks at a pair of quotation marks in prose. Measured on the five stored
baseline answers: 7 verbatim teacher quotations, of which one was
fabricated outright ("one who declares something not his own", credited to
a living minister, zero occurrences corpus-wide), one re-credited another
author's words to the teacher who was quoting him, and one silently
altered a teacher's wording and stripped his own hedge.

`system_prompt.txt:158` already forbids this ("Never reproduce quotes or
lift phrasing verbatim, in any mode"). It is not holding. This module is
the deterministic enforcement behind that instruction, and the control
Settled decision #17 names as required: "the prose channel must be
prevented from rendering quotation typography and verbatim-attribution
language."

DESIGN CONSTRAINTS, all load-bearing:

  * DETERMINISTIC ONLY. No model call, no judge, no scoring. Settled #4 /
    Open Decision #20 -- a model-based judge on the answer path has failed
    five times and must not be built. Every check here is string work:
    normalization, substring containment, position arithmetic. Same
    posture as `quote_verifier.py`'s exact-substring authenticity check.
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

KNOWN AND DELIBERATE LIMITATION -- nested quotation. If a teacher is
himself quoting someone else, that other person's words ARE present
verbatim in the retrieved chunk, so this guard passes them. The measured
Kolenda/Grudem case is exactly this shape. Detecting it requires resolving
attribution INSIDE source text, which Settled #16 already classes as a
hard, separate problem ("any unresolved nested quotation" is its own quote
ineligibility category). This guard closes fabrication and alteration; it
does not close nested misattribution, and must not be described as though
it does.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Sequence

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
    """Fold the punctuation and spacing variation that is NOT a
    misrepresentation into a single comparable form.

    This is load-bearing, not cosmetic. Proven against live corpus text:
    Derek Prince's genuine "what brought success in the '60s brings death
    in the '70s" is stored with curly U+2018 while the writer emits
    straight U+0027, so a raw substring comparison REJECTS an accurate
    quotation. Without this step the guard would regenerate and then
    refuse correct answers -- worse than not having it.

    Case is folded for the same reason: a quotation differing only in
    capitalization is not a misrepresentation, and refusing over one would
    be a pure false positive.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_TRANSLATION)
    return _WHITESPACE_RE.sub(" ", folded).strip().casefold()


@dataclass(frozen=True)
class AttributedQuotation:
    """A double-quoted span in answer prose that a permitted teacher name
    appears to attribute. `text` is the raw span as written; `normalized`
    is what actually gets matched; `attributed_to` is the name that
    qualified it."""
    text: str
    normalized: str
    attributed_to: str
    start: int


def _word_count(span: str) -> int:
    return len([w for w in span.split() if w])


def _contains_word(haystack: str, needle: str) -> bool:
    """Word-boundary containment, so a surname never matches inside a
    longer word."""
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


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
        window = answer_text[window_start : match.end()]

        scripture_window = answer_text[
            window_start : match.end() + TRAILING_CITATION_WINDOW_CHARS
        ]
        if _SCRIPTURE_REF_RE.search(scripture_window):
            continue

        if _NEGATED_INTRODUCTION_RE.search(answer_text[:match.start()]):
            continue

        normalized_window = normalize_for_match(window)
        attributed_to = next(
            (
                raw
                for raw, keys in normalized_names
                if any(_contains_word(normalized_window, key) for key in keys)
            ),
            None,
        )
        if attributed_to is None:
            continue

        found.append(
            AttributedQuotation(
                text=span,
                normalized=normalize_for_match(span),
                attributed_to=attributed_to,
                start=match.start(),
            )
        )
    return found


def ungrounded_prose_quotations(
    answer_text: str,
    evidence_texts: Iterable[str],
    permitted_names: Sequence[str],
) -> List[AttributedQuotation]:
    """The subset of attributed prose quotations that do NOT appear
    verbatim in the retrieved evidence.

    A returned non-empty list means the answer put words in a named
    teacher's mouth that his retrieved material does not contain -- ranked
    failure mode #2. The caller's remedy is regeneration, then refusal;
    never a surgical edit of the prose.

    Matching is exact containment after `normalize_for_match`. Nothing
    fuzzy, no similarity score, no threshold to tune: a near-miss IS the
    failure (the measured Prince case altered "to pipe the fresh oil" into
    "piping fresh oil" and dropped his hedge), so tolerating near-misses
    would defeat the purpose.
    """
    quotations = extract_attributed_quotations(answer_text, permitted_names)
    if not quotations:
        return []

    haystack = " \n ".join(
        normalize_for_match(text) for text in evidence_texts if text
    )
    if not haystack:
        # No evidence to check against: every attributed quotation is
        # unsupported by construction. Fail closed -- this is the same
        # posture as build_retrieval_grounding's `established` flag.
        return quotations

    return [q for q in quotations if q.normalized not in haystack]
