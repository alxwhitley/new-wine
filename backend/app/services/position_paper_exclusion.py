"""
position_paper_exclusion.py -- Alex's ruling (2026-08-06, resolving CLAUDE.md
Settled decision #8/#9's flagged 2026-08-01 conflict): Position Papers are
now silent context, never the served answer (see position_papers.py's own
updated module docstring). This module is the other half of that ruling:
where a position-paper's house position exists for a matched topic, retrieved
teacher material that genuinely CONTRADICTS it is excluded from the answer
entirely, rather than presented alongside it or silently reframed into
agreement -- the exact misrepresentation risk decision #9 named ("a house
guardrail tells the model to follow house framing regardless of how the
source puts it, which silently corrects a dissenting teacher into
agreement").

This is an explicit, authorized exception to this codebase's usual posture
against LLM-based judgment calls (Open Decision #20's five failed attempts
at a DIFFERENT problem, post-hoc claim-support verification). Alex was told
directly and accepts: whether a teacher "contradicts" a house position is a
per-answer model judgment, not a deterministic check, and will sometimes be
wrong in both directions. Not re-litigated here. What IS built to spec:
every exclusion is logged (question, teacher, topic, what was excluded) so
the false-exclusion rate is measurable later, per the same
measure-before-building discipline used elsewhere in this codebase.

ONE classification call normally (at most two after a call/parse failure),
not one per teacher: the retrieved
chunks (already capped to a small final set by the time this runs -- see
chat.py's own Step 4.5 / producer.py's mirror, both AFTER rerank + neighbor
expansion) are grouped by author, and a single structured call judges every
distinct author against the house position at once. Fails SAFE toward NOT
excluding on any parse or API error -- excluding a genuinely-consistent
teacher is a real product cost (thinner answers, more fallbacks), but
failing open here only risks an honestly-attributed dissenting view
reaching the reader, not a fabrication or a misrepresentation; CLAUDE.md's
ranked failure modes rate misrepresentation worse than an occasional
under-exclusion.
"""
from __future__ import annotations

import datetime
import json
import logging
from typing import Dict, List, Optional, Tuple

from app.services.llm_client import get_anthropic_client, get_generation_model

logger = logging.getLogger(__name__)

_CLASSIFIER_SYSTEM_PROMPT = (
    "You are checking retrieved teaching material against a stated house "
    "position, for a Bible-study research tool. You will be given the house "
    "position's own text, the user's question, and excerpts grouped by "
    "teacher. For EACH teacher listed, decide whether their excerpts, taken "
    "together, express a view that CONTRADICTS the house position on this "
    "specific question -- an actual contrary claim, not merely a different "
    "emphasis, a narrower focus, or simple silence on the point. A teacher "
    "who doesn't address the house position's specific claim at all does "
    "NOT contradict it. A teacher who explicitly asserts the opposite of "
    "what the house position states DOES contradict it.\n\n"
    "Respond with ONLY a JSON array, one object per listed teacher, nothing "
    "else -- no preamble, no markdown fences:\n"
    '[{"teacher": "<exact name as given>", "contradicts": true or false, '
    '"reason": "<one short sentence, required either way>"}]'
)


def _is_citable(chunk: dict) -> bool:
    """Same predicate as chat.py's own _is_citable() (duplicated, not
    imported -- chat.py imports this module, so the reverse would be
    circular; this check is small, stable, and long-established). Real,
    found live: silent_context commentary/lexicon rows (e.g. "Adam Clarke",
    "STEPBible / Tyndale House") carry an `author` field too and would
    otherwise reach the classifier as if they were a "teacher" whose
    material could contradict the house position -- nonsensical (they are
    never cited/named in an answer to begin with, so there is nothing to
    exclude), and inflated one real prompt to 9 "teachers" and a max_tokens
    cutoff during testing."""
    mode = chunk.get("citation_mode")
    if mode:
        return mode == "citable"
    return chunk.get("source_type") == "sermon"


def _group_chunks_by_author(chunks: List[dict]) -> Dict[str, List[dict]]:
    groups = {}  # type: Dict[str, List[dict]]
    for c in chunks:
        if c.get("_lexicon") or not _is_citable(c):
            continue
        author = (c.get("author") or "").strip()
        if not author:
            continue
        groups.setdefault(author, []).append(c)
    return groups


def _build_user_message(house_position_text: str, question: str, groups: Dict[str, List[dict]]) -> str:
    teacher_blocks = []
    for author, author_chunks in groups.items():
        excerpts = "\n".join(f"- {c.get('content', '')}" for c in author_chunks)
        teacher_blocks.append(f"Teacher: {author}\nExcerpts:\n{excerpts}")
    teachers_text = "\n\n".join(teacher_blocks)
    return (
        f"House position:\n{house_position_text}\n\n"
        f"Question: {question}\n\n"
        f"Retrieved material by teacher:\n\n{teachers_text}"
    )


def _log_exclusion(question: str, teacher: str, topic: str, reason: str) -> None:
    logger.info(
        "position_paper_exclusion: EXCLUDED | topic=%s | teacher=%r | "
        "reason=%r | ts=%s | question=%r",
        topic, teacher, reason,
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        question,
    )


def exclude_contradicting_teachers(
    pillar_key: str, house_position_text: str, question: str, chunks: List[dict]
) -> Tuple[List[dict], List[str]]:
    """Return (filtered_chunks, excluded_author_names). `chunks` is the
    caller's final, already-retrieved chunk list (post-rerank, post-neighbor-
    expansion -- the same list that will otherwise become the answer's
    context/citations unchanged). `house_position_text` is the matched
    pillar's own body (get_paper_body(pillar_key)), passed in rather than
    re-fetched here so the caller's own cache is reused, not duplicated.

    No chunks / no distinct authors -> no-op, (chunks, []). A classifier
    parse or API failure is retried once; a second failure -> no-op, fail-safe
    toward NOT excluding (see module docstring)."""
    groups = _group_chunks_by_author(chunks)
    if not groups:
        return chunks, []

    def _call_and_parse_classifier():
        client = get_anthropic_client()
        response = client.messages.create(
            model=get_generation_model(),
            max_tokens=2048,
            thinking={"type": "disabled"},
            system=[{"type": "text", "text": _CLASSIFIER_SYSTEM_PROMPT}],
            messages=[{
                "role": "user",
                "content": _build_user_message(house_position_text, question, groups),
            }],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)

    try:
        verdicts = _call_and_parse_classifier()
    except Exception:
        logger.warning(
            "position_paper_exclusion: classifier call/parse failed for pillar=%s "
            "-- retrying once",
            pillar_key,
            exc_info=True,
        )
        try:
            verdicts = _call_and_parse_classifier()
        except Exception:
            logger.exception(
                "position_paper_exclusion: classifier call/parse failed for "
                "pillar=%s -- failing safe, no exclusion applied this question",
                pillar_key,
            )
            return chunks, []

    excluded_authors = []  # type: List[str]
    for v in verdicts if isinstance(verdicts, list) else []:
        if not isinstance(v, dict):
            continue
        teacher = (v.get("teacher") or "").strip()
        if teacher and v.get("contradicts") is True and teacher in groups:
            excluded_authors.append(teacher)
            _log_exclusion(question, teacher, pillar_key, str(v.get("reason") or ""))

    if not excluded_authors:
        return chunks, []

    filtered = [c for c in chunks if (c.get("author") or "").strip() not in excluded_authors]
    return filtered, excluded_authors
