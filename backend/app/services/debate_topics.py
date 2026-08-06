"""
debate_topics.py -- Project 2 phase 1 classifier (PLAN.md v5.24, CLAUDE.md
Settled decisions #10/#11). Deterministic phrase-list classification of a
question into "debate" or "settled", mirroring scripts/positions.py's
is_calvinism_predestination_topic() shape exactly: plain lower-cased
substring matching against a short, hand-picked phrase list, no embedding
similarity, no confidence score, no LLM judgment call. Not incidental --
LLM-based true/false judgment calls for this kind of question have already
been tried and abandoned five separate times in this system for a closely
related problem (CLAUDE.md's "generation-output verification guard" /
PLAN.md Open Decision #20); deterministic matching is the pattern that has
actually held up in production (is_calvinism_predestination_topic, live
since 2026-07-30).

Two categories (Alex's ruling): "debate" topics -- multiple teachers hold
genuinely different positions, presented on both sides (CLAUDE.md Settled
decision #11's four-topic anchor set: apostolic authority, eschatological
timing, healing mechanics, prophetic accountability) -- and "settled"
topics -- one dominant/settled voice or house position (currently just
speaking in tongues, decision #10: not required as initial evidence of
Spirit baptism, but reasonably expected for all).

DEFAULT IS "debate", NEVER "settled". Any question that does not clearly
match a known phrase falls through to "debate". This is deliberate, not an
oversight: wrongly broadening (treating an ordinary/settled topic as
"debate") just means a downstream consumer skips a piece of special-cased
handling it could safely have applied more narrowly -- a missed
optimization, not a correctness risk. Wrongly narrowing (missing a real
debate topic and calling it "settled") risks a single, confidently blended
answer on a topic where real named teachers genuinely disagree -- CLAUDE.md
ranked failure mode 2 (misrepresenting a teacher), worse than mode 3
(generic answers). See CLAUDE.md's Session Routing / PLAN.md v5.24 "Fail
direction decided" for the same rule applied to this classifier's first
consumer.

Known limitation, disclosed not hidden (same posture as the Calvinism
matcher's own unresolved-variant gap -- PLAN.md v5.6-5.10 flagged
"predestined," "predestinate," "Calvin on election" etc. as plausible
misses never ruled on): the phrase lists below cover the most natural real-
user phrasings found while building this, not an exhaustive enumeration of
every way to ask about these five topics. Do not treat an empty phrase
list addition as "done" -- widen it from real evidence, not from guessing
harder up front. Every question that falls through to the "debate" default
because nothing matched is logged via _log_unmatched() below, at INFO
level, with the raw question text and a UTC timestamp, so a future session
can review real production misses and widen these lists from actual usage
-- the same follow-up already queued for the Calvinism matcher's own
unresolved variant list.

Two public entry points:
  classify_topic(question) -> DEBATE | SETTLED
      The primary export. Two-value output only, per the design above.
  matched_debate_topic(question) -> Optional[str]
      Returns which of the four decision-#11 debate-topic keys matched
      (see DEBATE_TOPIC_KEYS), or None. classify_topic() does not expose
      this -- it collapses to the same "debate" bucket a topic that
      matched none of the four lists also falls into (the default) -- but
      a future consumer that specifically needs to exclude just the four
      named debate topics from some other pipeline step (e.g. the
      single-teacher retrieval lock this classifier was originally
      commissioned to unblock, CLAUDE.md #15 / PLAN.md v5.24 step 2) needs
      that distinction and would otherwise have to reimplement this
      matching from scratch. Exposed since it is already computed
      internally, not built as new speculative surface.
"""

import datetime
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEBATE = "debate"
SETTLED = "settled"

# ---------------------------------------------------------------------------
# Phrase lists -- lower-cased substring matching, same discipline as
# scripts/positions.py::is_calvinism_predestination_topic(). Each list is a
# short, hand-picked set of the most natural real-user phrasings for that
# topic, not an exhaustive enumeration -- see module docstring. Deliberately
# avoid single common words that would over-trigger on unrelated questions
# (the same discipline that keeps is_calvinism_predestination_topic off bare
# "election"): e.g. no bare "apostle", "healing", "prophecy", or "tongue".
# ---------------------------------------------------------------------------

# apostolic_authority -- the boundaries of apostolic ministry today.
# CLAUDE.md Settled decision #11's own carved-out settled exception (no one
# today holds the authority to write Scripture) is a fact about what the
# ANSWER should say on this topic, not a separate classification case here:
# a question about that exception ("can an apostle add to the Bible today")
# is still a question about apostolic authority and correctly lands DEBATE
# via the phrases below.
APOSTOLIC_AUTHORITY_PHRASES = (
    "apostolic authority",
    "apostolic ministry",
    "office of apostle",
    "office of an apostle",
    "are there apostles today",
    "apostles today",
    "modern-day apostle",
    "modern day apostle",
    "five-fold ministry",
    "fivefold ministry",
    "five fold ministry",
    "apostolic succession",
    "apostolic accountability",
    "new apostolic reformation",
)

# eschatological_timing -- end-times sequencing (rapture/tribulation timing,
# how to understand the millennium).
ESCHATOLOGICAL_TIMING_PHRASES = (
    "rapture",
    "tribulation",
    "millennium",
    "millennial reign",
    "end times",
    "end-times",
    "second coming",
    "pre-tribulation",
    "pretribulation",
    "post-tribulation",
    "posttribulation",
    "mid-tribulation",
    "midtribulation",
    "premillennial",
    "postmillennial",
    "amillennial",
    "eschatology",
    "eschatological",
)

# healing_mechanics -- whether healing is guaranteed in the atonement, why
# some who pray in faith are healed and others are not, how faith operates
# in receiving healing.
HEALING_MECHANICS_PHRASES = (
    "healing in the atonement",
    "healed in the atonement",
    "atonement provides healing",
    "guaranteed in the atonement",
    "why am i not healed",
    "why wasn't i healed",
    "why doesn't god heal",
    "why does god heal some and not others",
    "does god always heal",
    "gift of healing",
    "gifts of healing",
    "divine healing",
    "healing ministry",
    "by his stripes we are healed",
    "is it always god's will to heal",
)

# prophetic_accountability -- how a prophetic word should be tested,
# weighed, and held accountable; the boundaries of prophetic authority.
PROPHETIC_ACCOUNTABILITY_PHRASES = (
    "test a prophecy",
    "testing prophecy",
    "test a prophetic word",
    "false prophecy",
    "prophecy false",
    "false prophet",
    "prophetic accountability",
    "prophetic authority",
    "judge a prophecy",
    "judging a prophecy",
    "office of a prophet",
    "office of prophet",
    "modern-day prophet",
    "modern day prophet",
    "are there prophets today",
)

DEBATE_TOPIC_PHRASES = {
    "apostolic_authority": APOSTOLIC_AUTHORITY_PHRASES,
    "eschatological_timing": ESCHATOLOGICAL_TIMING_PHRASES,
    "healing_mechanics": HEALING_MECHANICS_PHRASES,
    "prophetic_accountability": PROPHETIC_ACCOUNTABILITY_PHRASES,
}  # type: Dict[str, Tuple[str, ...]]

# tongues -- the single confirmed settled/house topic (Alex's ruling,
# 2026-08-01, CLAUDE.md decision #10): not required as initial evidence of
# Spirit baptism, but reasonably expected for all. This is the ONLY phrase
# list where a false positive changes the classifier's output (every debate
# list above shares its "debate" result with the unmatched default, so a
# false positive there is a no-op) -- kept to phrases that are, in this
# corpus's real usage, essentially always about speaking in tongues
# specifically, not spiritual gifts or prayer generally.
TONGUES_PHRASES = (
    "speaking in tongues",
    "speak in tongues",
    "speaks in tongues",
    "gift of tongues",
    "praying in tongues",
    "pray in tongues",
    "prayer language",
    "unknown tongue",
    "unknown tongues",
    "interpretation of tongues",
    "initial evidence of the baptism",
    "initial evidence of spirit baptism",
    "initial evidence of the holy spirit",
)

SETTLED_TOPIC_PHRASES = {
    "tongues": TONGUES_PHRASES,
}  # type: Dict[str, Tuple[str, ...]]

DEBATE_TOPIC_KEYS = tuple(DEBATE_TOPIC_PHRASES.keys())
SETTLED_TOPIC_KEYS = tuple(SETTLED_TOPIC_PHRASES.keys())


def _matched_topic_key(question: str) -> Optional[str]:
    """Return whichever topic key's phrase list `question` matches, or None.

    Debate-topic lists are checked before the settled (tongues) list --
    ties go to "debate" (see module docstring's fail-direction rationale).
    In practice the two vocabularies do not overlap in this corpus, so
    order has not been observed to matter, but the precedence is explicit
    rather than left to dict iteration order.
    """
    q = question.lower()
    for key, phrases in DEBATE_TOPIC_PHRASES.items():
        if any(p in q for p in phrases):
            return key
    for key, phrases in SETTLED_TOPIC_PHRASES.items():
        if any(p in q for p in phrases):
            return key
    return None


def matched_debate_topic(question: str) -> Optional[str]:
    """Return which of the four decision-#11 debate-topic keys `question`
    matches (see DEBATE_TOPIC_KEYS), or None if it matches none of them --
    including if it matches the settled tongues list instead. See module
    docstring for why this is exposed separately from classify_topic()."""
    key = _matched_topic_key(question)
    return key if key in DEBATE_TOPIC_PHRASES else None


def _log_unmatched(question: str) -> None:
    """INFO-level breadcrumb for every question that falls through to the
    "debate" default with no phrase match, so a future session can review
    real misses and widen the lists above from actual usage rather than
    from guessing harder up front -- see module docstring."""
    logger.info(
        "debate_topics: no phrase match, defaulting to debate | "
        "ts=%s | question=%r",
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        question,
    )


def classify_topic(question: str) -> str:
    """Classify `question` as DEBATE or SETTLED. Deterministic phrase-list
    matching only -- see module docstring. Default on no match is DEBATE,
    never SETTLED, and the fallthrough is logged (_log_unmatched)."""
    key = _matched_topic_key(question)
    if key in SETTLED_TOPIC_PHRASES:
        return SETTLED
    if key is not None:
        return DEBATE
    _log_unmatched(question)
    return DEBATE
