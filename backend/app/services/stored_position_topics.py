"""
stored_position_topics.py -- Project 2 "one-hop" stored-position matcher
(PLAN.md Open Decision #16 V1 list; docs/audits/position_topic_list_v1_
2026-08-07.md; docs/audits/position_layer_revival_diagnostic_2026-08-04.md's
"Revised design"). Deterministic phrase-list classification of a question
into one of the SIX adopted V1 position topic_keys, or None.

A match returns the stored `topic_key` (the resolution handle). The one-hop
answer path will later use that key to look up the current `positions` row
(scripts/serve_position.py::lookup_current_position) and feed its underlying
PROPOSITIONS -- never its rendered text -- into chat.py's existing retrieval/
generation/verification pipeline. THAT WIRING IS NOT BUILT HERE: this module
ships inert, no live caller, exactly as debate_topics.py first shipped. It
only answers "which stored position, if any, does this question match?".

Shape mirrors backend/app/services/debate_topics.py exactly: plain lower-cased
substring matching against short, hand-picked phrase lists -- no embedding
similarity, no confidence score, no LLM judgment call. This is deliberate and
prescribed by the V1 doc's "Matching posture" section: reuse the proven
discipline of match_position_paper()/debate_topics.py, closed registry of
topic keys, short hand-picked phrase lists, avoid bare single words that
over-trigger. Unlike position_papers.match_position_paper(), this matcher does
NOT embed the question -- it must stay cheap and deterministic because it runs
on every question once wired.

FAIL DIRECTION (V1 doc): no match -> None -> normal RAG, NEVER invent a
position. Every ambiguous case fails to None. Precedence, in order:

  1. Debate wins. If debate_topics.matched_debate_topic(question) is not None,
     return None -- a question that matches both a decision-#11 debate phrase
     and a V1 topic phrase must NOT inject a stored position (V1 doc
     "Relationship to other classifiers": "debate wins ... fail safe: do not
     inject a stored position on a debate topic").
  2. Paper-fenced topics out. If debate_topics.matched_settled_topic(question)
     is not None (currently just tongues), return None -- baptism/tongues are
     fenced by position PAPERS, explicitly OUT of V1, and must not be double-
     routed through this list. Tongues is the one paper-pillar deterministically
     catchable here; baptism is kept out by the narrowness of the six lists
     below rather than by adding an embedding call.
  3. Match the six. Collect every V1 topic whose phrase list hits. Exactly one
     -> return that topic_key. Zero -> None. TWO OR MORE -> None (near-tie /
     multi-match: "refuse match until resolved", V1 doc "Matching posture") --
     and log it (see _log_multi_match), the interesting case to disambiguate
     from real traffic.

Known limitation, disclosed not hidden (same posture as debate_topics.py's own
phrase-list gap): the phrase lists below are the starter anchors drafted in the
V1 doc table, covering the most natural real-user phrasings, NOT an exhaustive
enumeration of every way to ask about these six topics. Do not treat this as
"done" -- widen the lists from real evidence (the logged multi-match refusals
and, once wired, observed traffic), not from guessing harder up front.
"""

import datetime
import logging
from typing import Dict, List, Optional, Tuple

from app.services.debate_topics import matched_debate_topic, matched_settled_topic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phrase lists -- lower-cased substring matching, same discipline as
# debate_topics.py / scripts/positions.py::is_calvinism_predestination_topic().
# Each list is a short, hand-picked set of the most natural real-user phrasings
# for that topic (the V1 doc's "starter phrase anchors", table rows 45-50), not
# an exhaustive enumeration -- see module docstring. Deliberately avoid single
# common words that would over-trigger on unrelated questions: no bare "fast",
# "pray", "cross", or "holy" (the same discipline that keeps debate_topics off
# bare "apostle"/"healing"/"prophecy"/"tongue" and is_calvinism off bare
# "election").
# ---------------------------------------------------------------------------

FASTING_PHRASES = (
    "fasting",
    "how to fast",
    "why fast",
    "biblical fast",
    "fast and pray",
)

DELIVERANCE_PHRASES = (
    "deliverance",
    "spiritual warfare",
    "cast out demons",
    "casting out demons",
    "demonization",
    "demonic oppression",
)

PRAYER_PHRASES = (
    "how to pray",
    "how should i pray",
    "effective prayer",
    "prayer life",
    "intercession",
)

DIVINE_EXCHANGE_PHRASES = (
    "divine exchange",
    "exchange at the cross",
    "great exchange",
    "jesus took our",
    "what happened at the cross",
)

LOSE_SALVATION_PHRASES = (
    "lose salvation",
    "lose their salvation",
    "eternal security",
    "once saved always saved",
    "can a christian fall away",
    "perseverance of the saints",
)

HOLINESS_PHRASES = (
    "holiness",
    "personal purity",
    "sanctification",
    "holy living",
    "walk in holiness",
    "set apart",
)

# Registry: topic_key -> phrase list. The keys are the SIX adopted V1 topic_keys
# (docs/audits/position_topic_list_v1_2026-08-07.md), already in
# scripts/positions.py::normalize_topic_key() canonical form (lower-cased,
# whitespace-collapsed, trimmed). They are stored here as literal constants --
# NOT computed by importing normalize_topic_key -- deliberately: importing
# scripts/positions drags the Anthropic + embeddings clients (a ~1.3s import)
# and a backend->scripts path dependency into this per-answer hot-path service,
# which would contradict this module's "cheap and deterministic" contract and
# risk a prod import failure once chat.py imports this module. The byte-identity
# of these six keys against normalize_topic_key() is instead enforced by
# scripts/test_stored_position_topics.py, so any drift from the migration-077
# key contract is caught by the test, not paid for on every process start.
STORED_POSITION_TOPIC_PHRASES = {
    "fasting": FASTING_PHRASES,
    "deliverance from demons and spiritual warfare": DELIVERANCE_PHRASES,
    "how to pray effectively": PRAYER_PHRASES,
    "the divine exchange at the cross": DIVINE_EXCHANGE_PHRASES,
    "can a believer lose their salvation": LOSE_SALVATION_PHRASES,
    "holiness and personal purity": HOLINESS_PHRASES,
}  # type: Dict[str, Tuple[str, ...]]

STORED_POSITION_TOPIC_KEYS = tuple(STORED_POSITION_TOPIC_PHRASES.keys())


def _matched_topic_keys(question: str) -> List[str]:
    """Return every V1 topic_key whose phrase list `question` matches (lower-
    cased substring), in registry order. Zero, one, or many -- the caller
    (match_stored_position) applies the exactly-one rule."""
    q = question.lower()
    hits = []  # type: List[str]
    for key, phrases in STORED_POSITION_TOPIC_PHRASES.items():
        if any(p in q for p in phrases):
            hits.append(key)
    return hits


def _log_multi_match(question: str, keys: List[str]) -> None:
    """INFO-level breadcrumb for a multi-match refusal (question hit two or
    more V1 topic lists, so it fails to None per the fail-safe). This is the
    interesting case to disambiguate the phrase lists against real traffic --
    logged with the raw question and a UTC timestamp so a future session can
    tighten the anchors from actual usage rather than from guessing. Mirrors
    debate_topics._log_unmatched()."""
    logger.info(
        "stored_position_topics: multi-match refusal, returning None | "
        "ts=%s | matched=%s | question=%r",
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        keys,
        question,
    )


def match_stored_position(question: str) -> Optional[str]:
    """Return the stored V1 `topic_key` this question matches, or None.

    See the module docstring for the full precedence and fail direction. In
    short: debate topics win (None), paper-fenced tongues is out (None), then
    exactly one of the six V1 topic lists must hit (its key); zero or multiple
    hits both fail to None. None means "no stored position -- use normal RAG",
    never "invent a position"."""
    # 1. Debate wins -- never inject a stored position on a decision-#11 debate.
    if matched_debate_topic(question) is not None:
        return None
    # 2. Paper-fenced topics (tongues) are out of V1 -- do not double-route.
    if matched_settled_topic(question) is not None:
        return None
    # 3. Exactly one of the six V1 topic lists.
    hits = _matched_topic_keys(question)
    if len(hits) == 1:
        return hits[0]
    if len(hits) >= 2:
        _log_multi_match(question, hits)
        return None
    return None
