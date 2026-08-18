"""Deterministic quote serveability / quality gate (Settled decision #29).

Separates "worth serving as a standalone quote" from authenticity
(`quote_verifier.verify_quote_candidate`). Authenticity stays exact-substring,
speaker, boundary, and clearance checks. This module answers taste questions
with named, logged rules — wrong in both directions sometimes, by design.

V1 is deterministic only. Model-assisted scoring may be added later under the
same settled exception, still with named rules and logs — not a free-form
claim-support judge (Open Decision #20 shape remains rejected).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Calibrated for the quote rail UI; matches the Prince extractor's rough band.
MIN_QUOTE_CHARS = 80
MAX_QUOTE_CHARS = 500

# Openers that only work with surrounding context the reader will not see.
_DEIXIS_OPENER = re.compile(
    r"^\s*("
    r"Verse\s+\d+"
    r"|Chapter\s+\d+"
    r"|As I (?:said|mentioned|noted|pointed out)"
    r"|This is a wonderful verse"
    r"|Look at (?:verse|chapter)"
    r"|Turning to "
    r"|Now (?:then,? )?let(?:'s| us) (?:look|turn|read)"
    r")\b",
    re.IGNORECASE,
)

# Mid-argument connective openers from the 2026-08-19 quality sample class.
_CONNECTIVE_OPENER = re.compile(
    r"^\s*("
    r"Now I am not seeking"
    r"|On the other hand"
    r"|But notice that"
    r"|So being "
    r"|Therefore,? as far as I have been able"
    r"|I(?:'| a)?m not seeking to make a big issue"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QualityVerdict:
    ok: bool
    rule: str
    reason: Optional[str]


def assess_quote_quality(
    quote_text: str,
    *,
    restated_point: str | None = None,
    why_quotable: str | None = None,
    standalone_ok: bool | None = None,
) -> QualityVerdict:
    """Return whether a candidate is worth serving as a standalone quote.

    ``restated_point`` / ``why_quotable`` are accepted for forward compatibility
    with the LLM propose path; v1 does not score them. ``standalone_ok=False``
    from propose is honored as an immediate refuse.
    """
    del restated_point, why_quotable  # reserved for later rubric dimensions

    if standalone_ok is False:
        return QualityVerdict(
            False,
            "not_standalone",
            "propose marked standalone_ok=false",
        )

    text = (quote_text or "").strip()
    if not text:
        return QualityVerdict(False, "empty_text", "quote_text is empty")

    # Named taste failures before length so short deictic stubs still report
    # the real reason (e.g. "Verse 17, this is a wonderful verse.").
    if _DEIXIS_OPENER.search(text):
        return QualityVerdict(
            False,
            "deixis_opener",
            "opens with context-dependent deixis (verse/chapter pointer or similar)",
        )

    if _CONNECTIVE_OPENER.search(text):
        return QualityVerdict(
            False,
            "connective_prose",
            "opens as mid-argument connective prose, not a standalone claim",
        )

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        return QualityVerdict(
            False,
            "internal_paragraph_break",
            "candidate spans more than one blank-line paragraph",
        )

    n = len(text)
    if n < MIN_QUOTE_CHARS or n > MAX_QUOTE_CHARS:
        return QualityVerdict(
            False,
            "length_band",
            "length %d outside [%d, %d]" % (n, MIN_QUOTE_CHARS, MAX_QUOTE_CHARS),
        )

    return QualityVerdict(True, "accepted", None)
