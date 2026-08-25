"""Pure canonical verified-transcript rendering and identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class CanonicalTranscriptPage:
    page_number: int
    transcript_start: int
    transcript_end: int


@dataclass(frozen=True)
class CanonicalVerifiedTranscript:
    text: str
    sha256: str
    pages: Tuple[CanonicalTranscriptPage, ...]


def canonical_verified_transcript(
    pages: Sequence[Tuple[int, str]],
) -> CanonicalVerifiedTranscript:
    """Render page text once with the durable delimiters used by every stage."""
    parts = []
    spans = []
    cursor = 0
    for page_number, page_text in pages:
        if parts:
            parts.append("\n\n")
            cursor += 2
        marker = f"=== PAGE {page_number} ===\n"
        parts.append(marker)
        cursor += len(marker)
        start = cursor
        parts.append(page_text)
        cursor += len(page_text)
        spans.append(
            CanonicalTranscriptPage(
                page_number=page_number,
                transcript_start=start,
                transcript_end=cursor,
            )
        )
    text = "".join(parts)
    return CanonicalVerifiedTranscript(
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        pages=tuple(spans),
    )
