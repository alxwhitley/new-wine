"""
SP1 reference-pointer verifier. Takes what the writer PROPOSED (parsed from
the model's <reference_mentions> block) and what the model ACTUALLY WROTE
(the final <answer> text), and returns only the subset that survives every
independent guard below. Anything that fails any guard is dropped silently
— this module never raises past its own top-level try/except, and never
partially-credits a mention.

Guard order (all four required, in this order for efficiency — a mention
must survive all of them):
  1. Presence  — the proposed string must literally appear in answer_text.
     Also the SOLE source of occurrence positions (verses: every match;
     teachers: first match only) — the model's own claims are never
     trusted for position.
  2. Resolution — verses: parse_ref (single or range) + a real verses-table
     row for every endpoint. Teachers: alias-key lookup against
     source_aliases, must not be the sentinel/MISS, must pass the license/
     visibility gate (is_source_servable).
  3. Biblical-figure backstop — independent of #2's result. Runs regardless
     of what source_aliases says.

See docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md for
the full design rationale.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.constants import BOOK_MAP
from app.services.biblical_figures import is_biblical_figure
from app.services.source_resolver import is_source_servable, normalize_alias_key

logger = logging.getLogger(__name__)

_MENTIONS_BLOCK_RE = re.compile(
    r"<reference_mentions>(.*?)</reference_mentions>", re.DOTALL
)
_MENTION_LINE_RE = re.compile(r"^(VERSE|TEACHER):\s*(.+)$")

_SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"


def parse_reference_mentions(raw_output: str) -> List[Dict]:
    """Extract and parse the <reference_mentions> block from the model's
    full raw output. Malformed or missing lines are skipped individually —
    never fatal, never drops the whole block for one bad line.
    """
    block_match = _MENTIONS_BLOCK_RE.search(raw_output)
    if not block_match:
        return []

    proposals = []  # type: List[Dict]
    for line in block_match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MENTION_LINE_RE.match(line)
        if not m:
            continue  # malformed line — skip silently, per-line fail-quiet
        kind, raw = m.group(1), m.group(2).strip()
        if not raw:
            continue
        proposals.append({"type": "verse" if kind == "VERSE" else "teacher", "raw": raw})
    return proposals


def find_occurrences(answer_text: str, raw: str) -> List[int]:
    """Literal, case-sensitive substring search. Returns every match start
    index, or [] if the string never appears — this IS the presence check.
    """
    if not raw:
        return []
    positions = []
    start = 0
    while True:
        idx = answer_text.find(raw, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _parse_verse_or_range(ref: str) -> Optional[Tuple[str, int, int, Optional[int]]]:
    """Parse 'Romans 8:28' or 'Romans 8:26-28' / 'Romans 8:26–28' into
    (abbrev, chapter, verse_start, verse_end_or_None). Reuses the same
    book-name matching BOOK_MAP already uses in app.routers.study.parse_ref
    — this is an extension to support ranges, not a fork of book matching.
    Returns None if the book, chapter, or verse can't be parsed at all
    (e.g. a vague reference like "verse 26" or "that chapter" has no book
    match and always returns None here).
    """
    ref = ref.strip()
    m = re.match(r'^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)(?:[-–](\d+))?$', ref)
    if not m:
        return None

    book_raw = m.group(1).strip().lower()
    chapter = int(m.group(2))
    verse_start = int(m.group(3))
    verse_end = int(m.group(4)) if m.group(4) else None

    book_normalized = re.sub(r'^(\d)\s*', r'\1 ', book_raw).strip()
    abbrev = BOOK_MAP.get(book_normalized) or BOOK_MAP.get(book_normalized.rstrip('s'))
    if not abbrev:
        return None

    return abbrev, chapter, verse_start, verse_end


def _resolve_verse_row(db, abbrev: str, chapter: int, verse: int) -> bool:
    verse_id = f"{abbrev}.{chapter}.{verse}"
    result = db.table("verses").select("verse_id").eq("verse_id", verse_id).limit(1).execute()
    return bool(result.data)


def verify_verse_mention(db, raw: str) -> bool:
    """True only if the whole reference (single verse or full range)
    resolves to real rows. A range fails whole if either endpoint is bad —
    no partial credit.
    """
    parsed = _parse_verse_or_range(raw)
    if not parsed:
        return False
    abbrev, chapter, verse_start, verse_end = parsed

    if not _resolve_verse_row(db, abbrev, chapter, verse_start):
        return False
    if verse_end is not None:
        if not _resolve_verse_row(db, abbrev, chapter, verse_end):
            return False
    return True


def verify_teacher_mention(db, raw: str) -> Optional[str]:
    """Returns the resolved source_id if this name passes every teacher
    guard, else None. Biblical-figure check runs first and short-circuits
    — a hit here means the alias table is never even consulted.
    """
    if is_biblical_figure(raw):
        return None

    key = normalize_alias_key(raw)
    if not key:
        return None

    alias_result = (
        db.table("source_aliases").select("source_id").eq("alias_key", key).limit(1).execute()
    )
    if not alias_result.data:
        return None

    source_id = alias_result.data[0]["source_id"]
    if source_id == _SENTINEL_SOURCE_ID:
        return None

    if not is_source_servable(db, source_id):
        return None

    return source_id


def verify_references(answer_text: str, raw_output: str, db) -> List[Dict]:
    """Top-level entry point. Never raises — any unexpected failure
    anywhere in this function results in an empty list, never a broken
    request. Returns a list of verified references, each:
        {"type": "verse", "raw": str, "positions": [int, ...]}
        {"type": "teacher", "raw": str, "position": int, "source_id": str}
    """
    try:
        proposals = parse_reference_mentions(raw_output)
        verified = []  # type: List[Dict]

        for proposal in proposals:
            raw = proposal["raw"]
            positions = find_occurrences(answer_text, raw)
            if not positions:
                continue  # presence check failed — model reported something not actually there

            if proposal["type"] == "verse":
                if not verify_verse_mention(db, raw):
                    continue
                verified.append({"type": "verse", "raw": raw, "positions": positions})
            else:
                source_id = verify_teacher_mention(db, raw)
                if not source_id:
                    continue
                verified.append({
                    "type": "teacher",
                    "raw": raw,
                    "position": positions[0],
                    "source_id": source_id,
                })

        return verified
    except Exception:
        logger.exception("Reference verification failed — returning no pointers")
        return []
