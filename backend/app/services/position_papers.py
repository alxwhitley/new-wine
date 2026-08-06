from __future__ import annotations

import json
import logging
import math
import re
from typing import Dict, Iterator, List, Optional, Tuple

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.llm_client import get_anthropic_client, get_generation_model
from app.services.source_resolver import normalize_alias_key

logger = logging.getLogger(__name__)

# ── Scope ────────────────────────────────────────────────────────────────
# This module serves a small, CLOSED, code-defined registry of Alex's own
# first-party owned house "position papers" — currently baptism_holy_spirit
# and speaking_in_tongues. It is NOT a generic "serve any silent_context
# document directly" mechanism, and must never become one: that would be a
# real license-gate bypass for arbitrary content. Registering a new pillar
# is safe specifically because it must be Alex's own owned house content,
# added deliberately to PILLARS below — never derived from an open table or
# a runtime flag. A DB-table-backed registry would need much stronger
# justification than this code constant; prefer the code constant.
#
# ── Architecture, corrected 2026-08-06 (Alex's ruling; resolves CLAUDE.md
# Settled decision #8's flagged 2026-08-01 conflict) ───────────────────────
# A position paper is CONSTRAINING SILENT CONTEXT, never a served answer.
# match_position_paper() still decides whether a question's topic has a
# matched house position; get_paper_body() still loads that paper's own
# text. But the caller (chat.py / its producer.py mirror) no longer
# bypasses retrieval on a match — retrieval runs completely normally, the
# paper's body is injected as bounding [House Position] silent context (the
# writer may not contradict it and may not copy its wording, cite it, or
# name it), and the answer is generated from real retrieved teacher
# material with real citations, through the normal guarded answer path.
# Retrieved material that genuinely contradicts the house position is
# excluded before generation (app.services.position_paper_exclusion), never
# silently reframed into agreement.
# generate_position_paper_answer() still exists and is UNCHANGED, but its
# role is now narrow: it backs ONLY the sanctioned No-Oracle-Rule fallback
# (render_paper_voice_with_disclaimer(), below) for the case where exclusion
# removes every retrieved teacher and would otherwise leave an empty
# answer — never the default path for a match. That fallback appends the
# standard disclaimer, unlike this function's own voice prompt (which still,
# correctly, forbids adding one itself — the disclaimer is appended
# deterministically in code, never left to the model to phrase).

# ── Anchor text constants ───────────────────────────────────────────────
# Named individually (rather than inlined into PILLARS below) so each is
# traceable to the calibration session that produced it, the same way the
# original single-pillar module documented its Phase A/B provenance.

# baptism_holy_spirit — calibrated 2026-07-30 (Phase A: 8 positives vs. 5
# clearly-different negatives, gap 0.0955; Phase B: added the water-baptism
# contrast anchor after threshold-alone let a water-baptism question score
# above threshold AND above 2 of the 8 real positives). ANCHOR_TITLE,
# ANCHOR_DESCRIPTION, and MATCH_THRESHOLD are the proven pure-refactor
# values from the single-pillar system — unchanged here.
BAPTISM_ANCHOR_TITLE = "Baptism of the Holy Spirit"
BAPTISM_ANCHOR_DESCRIPTION = (
    "The baptism of the Holy Spirit is a distinct work of God in a believer's "
    "life, separate from and subsequent to salvation, in which the Holy Spirit "
    "comes upon a person with power for witness, spiritual gifts, and "
    "supernatural ministry — an empowerment distinct from the indwelling "
    "presence received at conversion."
)
BAPTISM_CONTRAST_WATER = (
    "Water baptism as a sacrament: full immersion vs. sprinkling, believer's "
    "baptism vs. infant baptism, the physical ordinance of baptism in water."
)

# Bug fix, 2026-07-31 — NOT part of the pure refactor above, deliberately
# layered on top of it. A post-migration regression pass (testing tongues'
# own negative set against baptism through the combined registry, not
# something baptism's original single-pillar test set ever exercised)
# found this bug ALREADY LIVE in the committed single-pillar system: with
# only the water-baptism contrast, general-spiritual-gifts and
# gift-of-prophecy questions ("What are the nine gifts of the Spirit?",
# "How does the gift of prophecy work in a church service?", etc.) scored
# above MATCH_THRESHOLD and above the water-baptism contrast, so they were
# already being misrouted into the baptism position-paper bypass before
# tongues ever existed as a sibling pillar to reveal it. Unsurprising in
# hindsight — this pillar's own document lists "activation of spiritual
# gifts... prophecy, discernment" as part of what Spirit baptism produces,
# so it sits semantically close to both topics. These two anchors close
# that gap. Verified (real OpenAI embeddings, 2026-07-31) that all 4
# previously-misrouted questions now correctly fail to match (new
# contrast_sim comfortably exceeds their pos_sim: 0.5855, 0.5072, 0.7521,
# 0.6307 respectively) AND that all 8 of baptism's original positives still
# beat the new 3-way max contrast — though NOT with equal comfort: P1
# ("How can I be filled with God's power for ministry?") now clears its own
# max contrast by only +0.0113 (pos_sim 0.4503 vs. new max contrast 0.4390,
# the gifts anchor), down from +0.1659 against water-baptism alone — a real,
# thin margin, disclosed rather than smoothed over. Every other original
# positive kept a comfortable margin (smallest of the rest: P3 at +0.0559).
BAPTISM_CONTRAST_GIFTS_GENERAL = (
    "The spiritual gifts of 1 Corinthians 12 as their own catalog and topic — "
    "word of wisdom, word of knowledge, faith, gifts of healing, working of "
    "miracles, discernment of spirits, tongues, and interpretation of tongues — "
    "how each gift operates and who receives which gift, considered on its own "
    "terms as a topic of spiritual gifts, not as the baptism of the Holy Spirit "
    "that activates them."
)
BAPTISM_CONTRAST_PROPHECY = (
    "The gift of prophecy as its own topic — how prophetic ministry operates, "
    "who may prophesy, and how a prophetic word should be tested and received "
    "in the church — considered specifically as this one gift's function and "
    "qualifications, not as the baptism of the Holy Spirit that empowers it."
)
BAPTISM_MATCH_THRESHOLD = 0.3262  # unchanged — pure refactor value; the bug fix above widens contrast_anchors, not this threshold

# speaking_in_tongues — calibrated in this session (10 positives vs. 8
# negatives, gap 0.2233 between the lowest positive and the highest generic
# negative; every positive beats every one of its 3 contrast anchors, the
# smallest margin +0.0237). Needed 3 contrast anchors from the start,
# because speaking_in_tongues.md shares most of its scriptural grounding
# with baptism_holy_spirit (Acts 2/10/19), is entangled with the general
# spiritual gifts of 1 Corinthians 12, and is paired with prophecy
# throughout Acts — a single contrast anchor (as baptism needed) was
# insufficient and was never attempted.
TONGUES_ANCHOR_TITLE = "Speaking in Tongues: Public Gift and Private Prayer Language"
TONGUES_ANCHOR_DESCRIPTION = (
    "Speaking in tongues is a supernatural gift of the Holy Spirit in which a "
    "believer speaks in a language not learned through natural means — "
    "operating both as a public sign gift for corporate ministry, requiring "
    "interpretation for the church, and as a private prayer language for "
    "personal communion with God, addressed to God rather than to people."
)
TONGUES_CONTRAST_GIFTS = (
    "The broader spiritual gifts of 1 Corinthians 12 — word of wisdom, word "
    "of knowledge, faith, gifts of healing, working of miracles, and "
    "discernment of spirits — the diversity of gifts the Spirit distributes "
    "to different members of the church for the common good, apart from "
    "tongues itself."
)
TONGUES_CONTRAST_PROPHECY = (
    "The gift of prophecy — a Spirit-inspired word spoken in the speaker's "
    "own understood language to strengthen, encourage, and comfort the "
    "church, distinct from speaking in an unknown tongue."
)
TONGUES_CONTRAST_BAPTISM = (
    "The baptism of the Holy Spirit as a distinct empowering work of God "
    "subsequent to salvation, in which the Spirit comes upon a believer for "
    "power, ministry, and deeper communion with God, considered broadly — "
    "apart from any single accompanying sign such as speaking in tongues."
)

# Bug fix, 2026-07-31 — raised from 0.2989. The same combined-registry
# regression pass that found baptism's gifts/prophecy gap (see above) found
# a second, separate gap here: "What are Derek Prince's views on tithing
# and financial stewardship?" (one of baptism's own original teacher-
# citation negatives — never previously tested against tongues, since
# tongues didn't exist when it was written) scored pos_sim=0.3155 against
# tongues' anchors, above the old threshold (0.2989) and above tongues' own
# max contrast (0.2725), so it was matching speaking_in_tongues. Fixed by
# raising the threshold rather than adding a 4th contrast anchor: unlike
# the gifts/prophecy gap (a genuinely entangled neighboring topic that
# needs its own contrast anchor), this is a generic, topically-distant
# negative — the same category baptism's original design already excluded
# via threshold alone, not a dedicated contrast anchor. New threshold is
# the midpoint between the tithing question's pos_sim (0.3155) and the
# weakest of tongues' 10 original positives, TP2 (0.4106) — verified (real
# OpenAI embeddings, 2026-07-31) that the tithing question now falls below
# threshold (0.3155 < 0.3631) and all 10 original positives still clear it
# with margin (smallest: TP2 itself, at +0.0475 above the new threshold).
TONGUES_MATCH_THRESHOLD = 0.3631

# ── Additional contrast anchors — found live, 2026-08-01 (Phase 0 measurement
# pass, docs/audits/phase0_measurement_2026-08-01.md §7b) ──────────────────
# Two genuine anchor-vocabulary contamination cases, each fixed the SAME way
# the two 2026-07-31 bug fixes above were fixed: a new, disclosed, targeted
# contrast anchor — never by editing a positive anchor's own wording (that
# would shift every question's pos_sim, not just the contaminating one).

# baptism_holy_spirit's own anchor description contains the word "salvation"
# (it defines Spirit baptism as "separate from and subsequent to salvation"),
# which pulled in topically-unrelated eternal-security questions ("Can a
# believer lose their salvation?") purely on shared vocabulary. Verified live
# (real OpenAI embeddings, 2026-08-01): two phrasings of that exact question
# scored pos_sim 0.3401/0.3500 against baptism — barely above
# BAPTISM_MATCH_THRESHOLD (0.3262) and, against only the OLD contrast set,
# margins of +0.0519/+0.0889 — nowhere near as confident as a genuine
# baptism match (the thinnest genuine margin found, P1, is +0.0113, but P1's
# raw pos_sim is 0.4503, well above the salvation questions' 0.34-0.35
# cluster). Adding this contrast anchor pushes both salvation phrasings to a
# comfortably negative margin (-0.39 / -0.35) while leaving P1 and every
# other genuine baptism match unaffected (confirmed: P1's margin is
# untouched at 0.0113 because this anchor does not score higher than P1's
# existing max contrast for that question).
BAPTISM_CONTRAST_SALVATION = (
    "Whether a believer can lose their salvation, and the permanence and "
    "security of salvation itself — a distinct question of soteriology and "
    "eternal security, not the baptism of the Holy Spirit as a separate "
    "empowering work subsequent to being saved."
)

# speaking_in_tongues' anchor description includes "private prayer language
# for personal communion with God" — generic enough to pull in questions
# about hearing God's voice, personal guidance, and everyday spiritual
# communion generally, none of which are about tongues specifically.
# Verified live (real OpenAI embeddings, 2026-08-01): "How do I hear God's
# voice in daily life?" scored pos_sim 0.3665 against tongues — barely above
# TONGUES_MATCH_THRESHOLD (0.3631) and, against only the old contrast set, a
# thin +0.0220 margin. Two sibling general-topic questions ("What does it
# mean to fear the Lord?", "What is intercession and how do I practice it?")
# were also checked and also over-matched before this anchor was added.
# Adding it pushes all three to a comfortably negative margin.
TONGUES_CONTRAST_COMMUNION = (
    "Hearing God's voice, personal guidance, and everyday spiritual "
    "communion with God through prayer, Scripture, and the inner witness of "
    "the Spirit — a broad Christian-life topic distinct from the specific "
    "supernatural gift of speaking in an unlearned tongue."
)

# ── Standing debate-topic contrasts — SHARED across every pillar, current
# and future (Alex's ruling, 2026-08-01, pulled forward from Phase 1 items
# 1.5-1.7 per the Phase 0 report; eschatological timing added 2026-08-05):
# healing mechanics, prophetic accountability, apostolic authority, and
# eschatological timing remain live debates, presented with named teachers
# on both sides — never settled Rhemata teaching. This is exactly the
# structural fix Phase 0's finding called for: adding a new pillar's own
# contrast anchors previously did nothing to protect a SIBLING pillar or any
# FUTURE pillar from over-matching one of these four topics — each pillar's
# contrast_anchors list only ever defended that one pillar.
# These four anchors are merged into every pillar's contrast_sim at score
# time (see _pillar_scores below) rather than copy-pasted into each pillar's
# own contrast_anchors — a future pillar registered in PILLARS inherits this
# protection automatically, with no new code and nothing to remember.
HEALING_MECHANICS_DEBATE = (
    "The mechanics of physical healing — whether healing is guaranteed in "
    "the atonement for every believer today, why some who pray in faith are "
    "healed and others are not, and how faith operates in receiving "
    "healing. Teachers hold differing views on this; it is a live debate, "
    "not settled house teaching."
)
PROPHETIC_ACCOUNTABILITY_DEBATE = (
    "How a prophetic word should be tested, weighed, and held accountable "
    "in the church, and the boundaries of prophetic authority and "
    "correction. Teachers hold differing views on this; it is a live "
    "debate, not settled house teaching."
)
APOSTOLIC_AUTHORITY_DEBATE = (
    "The nature and boundaries of apostolic authority today — whether the "
    "office of apostle continues in some form, and how apostolic ministry "
    "should be exercised and held accountable, apart from the authority "
    "to write Scripture, which no one holds today. Teachers hold differing "
    "views on this; it is a live debate, not settled house teaching."
)
ESCHATOLOGICAL_TIMING_DEBATE = (
    "The timing and sequence of end-times events — whether the rapture "
    "precedes, coincides with, or follows the tribulation, and how the "
    "millennium should be understood. Teachers hold differing views on "
    "this; it is a live debate, not settled house teaching."
)
STANDING_DEBATE_CONTRASTS = [
    HEALING_MECHANICS_DEBATE,
    PROPHETIC_ACCOUNTABILITY_DEBATE,
    APOSTOLIC_AUTHORITY_DEBATE,
    ESCHATOLOGICAL_TIMING_DEBATE,
]

# Minimum required margin between a pillar's pos_sim and its (pillar-owned +
# shared standing-debate) contrast_sim to qualify — replaces a bare `>`
# comparison, which let a razor-thin, unstable margin (found live: the
# salvation question above routed on a margin under 0.002 difference
# between two phrasings of the identical question, before the contrast
# anchor above was added) confidently commit to an uncited house-voice
# answer. Calibrated against two real, live-measured floors, not picked in
# isolation: the smallest margin found among GENUINE matches is P1's
# +0.0113 (baptism, unchanged since 2026-07-31 calibration — see
# BAPTISM_MATCH_THRESHOLD's neighboring comment); every contaminated
# false-positive margin measured 2026-08-01, after the two new contrast
# anchors above already do most of the work, is comfortably negative.
# 0.008 sits with real buffer below the genuine floor (0.0113) without
# needing to be pushed flush against it — a defense-in-depth backstop for
# future thin-margin cases the anchors above don't happen to cover, not the
# primary mechanism for any of the cases fixed this pass.
MIN_QUALIFY_MARGIN = 0.008

# ── The registry ─────────────────────────────────────────────────────────
# Every per-pillar behavior this module needs is expressed here as data —
# no `if pillar_key == ...` branch exists anywhere below this point. If a
# future pillar needs something this shape can't express, that is a stop
# condition for whoever's adding it, not a reason to bolt on a branch.
#
# tie_break_priority: used ONLY when two or more qualifying pillars land
# within TIE_BREAK_EPSILON of each other on pos_sim (see match_position_paper
# below) — lower number wins. Alex's decision (2026-07-30): baptism wins
# ties, because speaking_in_tongues.md itself frames tongues as "one
# expression of" Spirit baptism — baptism is the broader, containing topic.
# This is a real, data-driven ranking (not list/dict iteration order) and
# generalizes: any future pillar gets an explicit priority assigned when it
# is added, not an implicit one inferred from where it sits in this list.
PILLARS = [
    {
        "pillar_key": "baptism_holy_spirit",
        "document_id": "a3884084-46f8-40be-929f-e34cb63ba8ac",
        "positive_anchors": [BAPTISM_ANCHOR_TITLE, BAPTISM_ANCHOR_DESCRIPTION],
        "contrast_anchors": [BAPTISM_CONTRAST_WATER, BAPTISM_CONTRAST_GIFTS_GENERAL, BAPTISM_CONTRAST_PROPHECY, BAPTISM_CONTRAST_SALVATION],
        "match_threshold": BAPTISM_MATCH_THRESHOLD,
        "voice_topic_name": "the baptism of the Holy Spirit",
        "tie_break_priority": 0,
    },
    {
        "pillar_key": "speaking_in_tongues",
        "document_id": "b884a5e1-d786-452f-8bf8-454bca0ab129",
        "positive_anchors": [TONGUES_ANCHOR_TITLE, TONGUES_ANCHOR_DESCRIPTION],
        "contrast_anchors": [TONGUES_CONTRAST_GIFTS, TONGUES_CONTRAST_PROPHECY, TONGUES_CONTRAST_BAPTISM, TONGUES_CONTRAST_COMMUNION],
        "match_threshold": TONGUES_MATCH_THRESHOLD,
        "voice_topic_name": "speaking in tongues",
        "tie_break_priority": 1,
    },
]

_PILLARS_BY_KEY = {p["pillar_key"]: p for p in PILLARS}  # type: Dict[str, dict]

# Near-tie epsilon for cross-pillar arbitration (see match_position_paper).
# Justified empirically against this session's real data, not picked as a
# round number in isolation:
#   - A real near-tie WAS found: "How do I receive the baptism of the Holy
#     Spirit and speak in tongues?" (one of baptism's own original,
#     previously-shipped positive test cases) scored pos_sim=0.6278 for
#     baptism vs. 0.6367 for tongues under the combined registry — margin
#     0.0089. This must be caught as a tie (it's a genuinely dual-topic
#     sentence with no principled single winner by pos_sim alone).
#   - A real, correctly-decided CLEAR win was also found: "Is speaking in
#     tongues the initial evidence of the baptism of the Holy Spirit?"
#     scored pos_sim=0.5958 (baptism) vs. 0.6660 (tongues) — margin 0.0702.
#     This must NOT be caught as a tie; tongues is the more specific,
#     correct subject of that question.
# TIE_BREAK_EPSILON = 0.02 sits with a >2x safety buffer above the real tie
# (0.0089) and a >3x safety buffer below the real clear win (0.0702) — not
# equidistant in raw terms, but comfortably clear of both boundary points
# found in actual calibration data, not chosen for roundness alone.
TIE_BREAK_EPSILON = 0.02


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ── Anchor embedding cache — keyed PER PILLAR, embedded at most once per
# pillar per process (never per request, never re-fetched for every pillar
# on every question — that N+1 risk didn't exist with 1 pillar and does
# with 2+, so this is deliberately a dict keyed by pillar_key, not a single
# flat set of module globals). ────────────────────────────────────────────
_anchor_cache = {}  # type: Dict[str, dict]

# Standing debate-topic contrast embeddings — embedded ONCE for the whole
# process (identical for every pillar), never per-pillar. Kept separate
# from _anchor_cache (which is keyed per pillar) since these are shared,
# not pillar-owned.
_standing_debate_vecs = None  # type: Optional[List[List[float]]]


def _ensure_standing_debate_contrasts():
    # type: () -> List[List[float]]
    global _standing_debate_vecs
    if _standing_debate_vecs is not None:
        return _standing_debate_vecs
    try:
        _standing_debate_vecs = [embed_text(c) for c in STANDING_DEBATE_CONTRASTS]
        logger.info(
            "Standing debate-topic contrasts embedded and cached: %d anchors",
            len(_standing_debate_vecs),
        )
    except Exception:
        logger.exception(
            "Failed to embed standing debate-topic contrasts — falling back "
            "to per-pillar contrasts only"
        )
        return []
    return _standing_debate_vecs


def _ensure_anchors(pillar: dict) -> None:
    key = pillar["pillar_key"]
    cached = _anchor_cache.get(key)
    if cached and cached.get("loaded"):
        return
    try:
        positive_vecs = [embed_text(a) for a in pillar["positive_anchors"]]
        contrast_vecs = [embed_text(c) for c in pillar["contrast_anchors"]]
        _anchor_cache[key] = {
            "loaded": True,
            "positive_vecs": positive_vecs,
            "contrast_vecs": contrast_vecs,
        }
        logger.info(
            "Position-paper anchors embedded and cached (%s): %d positive, %d contrast",
            key, len(positive_vecs), len(contrast_vecs),
        )
    except Exception:
        logger.exception("Failed to embed anchors for pillar=%s — matching disabled for this call", key)


def _pillar_scores(pillar: dict, q_vec: List[float]) -> Optional[Tuple[float, float]]:
    """Return (pos_sim, contrast_sim) for one pillar against an already-
    embedded question vector, or None if this pillar's anchors aren't
    available this call. pos_sim is the max similarity across all of this
    pillar's positive anchors; contrast_sim is the max similarity across
    this pillar's OWN contrast anchors AND the shared
    STANDING_DEBATE_CONTRASTS (beating the max is equivalent to beating
    every one individually)."""
    _ensure_anchors(pillar)
    cached = _anchor_cache.get(pillar["pillar_key"])
    if not cached or not cached.get("loaded"):
        return None
    pos_sim = max(_cosine(q_vec, v) for v in cached["positive_vecs"])
    all_contrast_vecs = cached["contrast_vecs"] + _ensure_standing_debate_contrasts()
    contrast_sim = max(_cosine(q_vec, v) for v in all_contrast_vecs)
    return pos_sim, contrast_sim


# ── Highest-priority gates — evaluated BEFORE any embedding similarity is
# computed, and BEFORE match_position_paper's own qualification logic runs
# at all (Alex's ruling, Phase 1 items 1.5-1.7). Both are deterministic: no
# embedding math can override either. This is the fix for the root
# fragility Phase 0 found, not a per-symptom patch — every future pillar
# calls the SAME match_position_paper() entry point, so both gates apply
# automatically without the next pillar's author needing to remember them.

_teacher_aliases_cache = None  # type: Optional[set]
_teacher_aliases_load_failed = False


def _ensure_teacher_aliases() -> None:
    """Lazy-load + cache every known source_aliases.alias_key once per
    process (read-only SELECT, same caching discipline as _ensure_body /
    _ensure_anchors above). 98 rows as of 2026-08-01 — small enough to hold
    in memory whole, same pattern chat.py's own match_background_topics()
    already uses for background-topic aliases.

    On load failure, does NOT cache an empty set — that would make
    _mentions_named_teacher return False for every question, silently
    disabling the veto (fail OPEN onto a misattribution risk, CLAUDE.md
    ranked failure mode 2). Instead sets _teacher_aliases_load_failed, so
    _mentions_named_teacher fails CLOSED: every question is treated as if
    it might name a teacher until this is fixed, deferring to the normal
    teacher-citation path rather than risking an uncited house-voice
    answer with a real teacher erased.
    """
    global _teacher_aliases_cache, _teacher_aliases_load_failed
    if _teacher_aliases_cache is not None or _teacher_aliases_load_failed:
        return
    try:
        db = get_supabase()
        result = db.table("source_aliases").select("alias_key").execute()
        _teacher_aliases_cache = {
            r["alias_key"] for r in (result.data or []) if r.get("alias_key")
        }
        logger.info(
            "Loaded %d source aliases for position-paper teacher-name gate",
            len(_teacher_aliases_cache),
        )
    except Exception:
        logger.exception(
            "Failed to load source_aliases — position-paper teacher-name "
            "gate fails CLOSED for this process (every question is treated "
            "as if it might name a teacher, so nothing is intercepted by a "
            "position paper until this is fixed, rather than failing open "
            "onto a misattribution risk)"
        )
        _teacher_aliases_load_failed = True


def _mentions_named_teacher(question: str) -> bool:
    """Return True if `question` names any known corpus teacher/source
    alias. Highest-priority gate (Phase 1 item 1.6): a question naming a
    specific teacher must never be intercepted by a position paper and
    answered in Rhemata's own uncited voice with that teacher absent
    entirely — confirmed live on two teachers (Derek Prince, Zac Poonen)
    against speaking_in_tongues, 2026-08-01.

    Reuses the canonical alias_key normalization
    (app.services.source_resolver.normalize_alias_key — Invariant 6, never
    forked) and substring-matches the question against every known alias,
    the same pattern chat.py's own match_background_topics() already uses
    for background-topic aliases. Uses a bare substring test, not a regex
    word-boundary match, since alias_key rows are themselves normalized
    (lowercase, whitespace-collapsed) multi-word names/phrases (minimum
    length 6 chars, e.g. "derek prince", "zac poonen") — the same
    false-positive risk profile already accepted for background topics.

    Fails CLOSED, not open: if source_aliases can't be loaded
    (_teacher_aliases_load_failed), returns True unconditionally — every
    question is treated as if it might name a teacher, so
    match_position_paper defers to the normal teacher-citation path rather
    than risk answering a genuinely teacher-named question in uncited
    house voice with the teacher erased (CLAUDE.md ranked failure mode 2 —
    worse than the minor cost of one request not getting the faster
    house-voice answer).
    """
    _ensure_teacher_aliases()
    if _teacher_aliases_load_failed:
        return True
    q = normalize_alias_key(question)
    return any(alias in q for alias in _teacher_aliases_cache)


_RETRIEVAL_INTENT_RE = re.compile(
    r"\bwhich\s+teachers?\b"
    r"|\bwhat\s+(?:do|does)\s+.{0,40}?\bteachers?\b"
    r"|\bwho\s+teaches?\b"
    r"|\bteachers?\s+(?:say|teach|believe|think)\b",
    re.IGNORECASE,
)


def _is_retrieval_intent(question: str) -> bool:
    """Return True if `question` is asking FOR teacher citations/attribution
    ("which teachers...", "what do teachers say...", "who teaches...")
    rather than a topical question a house-voice paper could answer. A
    position paper names no teachers by design (see the voice system
    prompt below) — intercepting a retrieval-intent question would silently
    answer a citation request with zero citations. Phase 1 items 1.6/1.7 —
    the T4 ("Which teachers in the library teach on speaking in tongues?")
    and H3 ("What do charismatic teachers say about...") symptoms.

    Deliberately phrase-general (any pillar, any topic), not keyed to
    "tongues" or "healing" specifically — a structural fix, not a
    per-topic exclusion.
    """
    return bool(_RETRIEVAL_INTENT_RE.search(question))


def match_position_paper(question: str) -> Optional[str]:
    """Return the pillar_key of whichever registered pillar `question`
    semantically matches, or None if it matches none or is gated out.

    Priority order (Alex's ruling, 2026-08-01, Phase 1 items 1.5-1.7 — the
    fix for Phase 0's confirmed, deterministic over-matching):

      0. HIGHEST PRIORITY, evaluated first, before any embedding call: if
         `question` names a specific corpus teacher
         (_mentions_named_teacher) or is shaped as a request for teacher
         citations (_is_retrieval_intent), return None immediately. No
         pillar's embedding similarity can override this — a position
         paper names no teachers, so either case would silently strip the
         citations/attribution the question asked for.

      1. Embed the question ONCE regardless of how many pillars are
         registered (N+1 discipline) and reuse that single vector against
         every pillar's cached anchors.

      2. Per-pillar qualification: a pillar qualifies if BOTH
           (a) pos_sim (max similarity across its positive anchors) clears
               its own match_threshold, AND
           (b) pos_sim clears contrast_sim (max similarity across this
               pillar's OWN contrast anchors AND the shared
               STANDING_DEBATE_CONTRASTS — healing mechanics, prophetic
               accountability, apostolic authority, eschatological timing,
               per Alex's ruling that these stay debates on every pillar,
               present and future) by
               at least MIN_QUALIFY_MARGIN — not a bare `>`. A razor-thin
               margin (found live: under 0.002 between two phrasings of the
               same salvation question) no longer qualifies; on genuinely
               ambiguous ground, this defaults to NOT intercepting rather
               than confidently committing to an uncited house-voice
               answer.
         This stays fully semantic per pillar: no phrase blocklist, no
         hardcoded topic-name string matching anywhere in this scoring step
         (the two gates in step 0 are the only phrase/name-based logic in
         this whole function, and they gate ALL pillars uniformly, not one
         pillar's topic).

      3. Cross-pillar arbitration (Alex's decision, 2026-07-30 — see
         TIE_BREAK_EPSILON above for the full justification): among all
         qualifying pillars, the one with the HIGHEST pos_sim wins — UNLESS
         the top-scoring pillars are within TIE_BREAK_EPSILON of the
         leader's pos_sim, in which case the tie is broken by
         tie_break_priority instead (lowest number wins; baptism_holy_spirit
         is priority 0). This never falls back to dict/list iteration order
         — every path through this function's decision is keyed on pos_sim,
         MIN_QUALIFY_MARGIN, or an explicit, data-driven tie_break_priority
         field.
    """
    if _mentions_named_teacher(question) or _is_retrieval_intent(question):
        return None

    q_vec = embed_text(question)

    qualifying = []  # type: List[Tuple[dict, float]]
    for pillar in PILLARS:
        scores = _pillar_scores(pillar, q_vec)
        if scores is None:
            continue
        pos_sim, contrast_sim = scores
        if pos_sim >= pillar["match_threshold"] and (pos_sim - contrast_sim) >= MIN_QUALIFY_MARGIN:
            qualifying.append((pillar, pos_sim))

    if not qualifying:
        return None
    if len(qualifying) == 1:
        return qualifying[0][0]["pillar_key"]

    qualifying.sort(key=lambda item: item[1], reverse=True)
    top_score = qualifying[0][1]
    tied_pool = [p for p, score in qualifying if (top_score - score) < TIE_BREAK_EPSILON]
    if len(tied_pool) > 1:
        tied_pool.sort(key=lambda p: p["tie_break_priority"])
        return tied_pool[0]["pillar_key"]
    return qualifying[0][0]["pillar_key"]


# ── Position-paper voice system prompt (shared template, one per pillar
# via substitution — not a duplicated hardcoded string per pillar) ────────
# Deliberately NOT ANSWER_SYSTEM_BLOCKS (chat.py's normal prompt) — that
# prompt is built around numbered [Source N]/[Background] citation labels,
# an <answer>/<reference_mentions> XML wrapper, and a "Rhemata can make
# mistakes" machine-fallback disclaimer posture that all belong to the
# cited-retrieval path, not this one. This path answers directly in
# Rhemata's own voice with no citation and no XML wrapper at all — output
# is streamed as plain prose.
#
# {voice_topic_name} and {heading_list} are the only two pillar-specific
# substitutions. heading_list is derived dynamically, per pillar, from that
# pillar's OWN loaded body (see _ensure_body below) — never a hardcoded
# per-pillar list — so a shared template can never leak one pillar's own
# section headings into a different pillar's "don't reuse these" rule, and
# a future pillar gets a correct avoid-list automatically, with no new code.
_VOICE_SYSTEM_TEMPLATE = """You are Rhemata, speaking on {voice_topic_name} in your own confident, pastorally warm teaching voice. This is settled Rhemata teaching, stated directly as your own conviction — not a survey of outside sources, not a report of what someone else believes.

You will be given the full substance of what Rhemata teaches on this topic in a second block below. Ground every claim in that material and in the Scripture it references. Do not draw on outside knowledge, other theological traditions, or training data beyond what is given there.

Hard rules for this answer:
- Never cite, name, or attribute this teaching to any author, source, title, or document. Never use the phrase "position paper," "this document," "this material," or any variant that reveals a written document lies behind your answer. Speak it as your own settled understanding.
- Never add a disclaimer such as "Rhemata can make mistakes" or "please let us know if you see any errors" or any similar wording — that belongs to a different, unrelated part of the product and has no place in this answer.
- Do not dump the material's section headers or bullet points verbatim, and do not reproduce its structure mechanically. Read the whole body of material, then write fresh, natural, conversational prose that answers the specific question actually asked, drawing together whichever parts of the material are relevant to it, in your own words and your own structure.
- This applies even to broad questions like "what is {voice_topic_name}" that could touch most of the material below. A broad question is not an invitation to summarize the whole document section-by-section in its own order. Instead, pick the 2-4 ideas most relevant to what was actually asked and build your own arc through them — you do not need to cover every section of the material in one answer, and you should not walk through it start to finish the way it's laid out below.
- If you use a heading or a bolded label standing in for one, it must be worded differently from every heading in the material below — never reuse one of the material's own section headings verbatim, whether as a "##" heading, a **bolded** label, or any other formatting. This material's own section headings are: {heading_list}. Do not reuse any of them, in any formatting, even inside a longer answer. When in doubt, prefer no heading at all and let short paragraphs carry the structure instead.
- You may name and quote specific Bible verses directly and confidently — Scripture is not a source attribution, it is the Word itself, and the material below cites it throughout.
- Write with the same conviction, warmth, and first-person confidence as Rhemata's normal voice: open with a direct answer to the question (no hedged preamble, no "some believe..." framing), build the biblical case, and land on a clear, settled takeaway.
- Scale length to the question: a narrow question deserves a focused answer (roughly 150-250 words); a broad "what is..." style question can run longer (roughly 250-400 words). Do not pad a simple answer and do not truncate a broad one.
- Short paragraphs. A light heading or two is fine if it helps a longer answer breathe, but never copy the material's own headings word-for-word as if transcribing a document."""


def _build_voice_system_prompt(pillar: dict, headings: List[str]) -> str:
    heading_list = "; ".join('"%s"' % h for h in headings) if headings else "(none detected)"
    return _VOICE_SYSTEM_TEMPLATE.format(
        voice_topic_name=pillar["voice_topic_name"],
        heading_list=heading_list,
    )


# ── Paper body loader — keyed PER PILLAR ──────────────────────────────────
# Reads from the `chunks` table (document_id=pillar["document_id"]), ordered
# by chunk_index and joined with "\n\n" — the exact pattern chat.py's own
# `_ensure_background_topics` / topics_to_inject loop already uses for the
# other background topics. Read-only SELECT only; no write of any kind.
_HEADER_LINE_RE = re.compile(r"^(TITLE|AUTHOR|SOURCE_TYPE):", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

_body_cache = {}  # type: Dict[str, dict]


def _strip_frontmatter(raw_text: str) -> str:
    """Defensively strip any leading TITLE:/AUTHOR:/SOURCE_TYPE: header
    lines (and blank lines interspersed at the top), returning clean body
    text starting at the first real content line. A no-op against today's
    ingested chunk content for either pillar (confirmed clean by direct
    query for both document_ids), kept in case a future re-ingest
    reintroduces these lines."""
    lines = raw_text.splitlines()
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or _HEADER_LINE_RE.match(stripped):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip()


def _ensure_body(pillar: dict) -> None:
    """Lazy-load and cache one pillar's body text AND its own derived
    heading list, loaded once per process from the `chunks` table
    (read-only SELECT) for pillar["document_id"], ordered by chunk_index
    and joined with "\\n\\n".

    Fails soft: if the query errors or returns no rows, logs and leaves the
    cache empty rather than raising, so match_position_paper() /
    generate_position_paper_answer() callers degrade to "feature
    unavailable for this request" instead of crashing /chat.
    """
    key = pillar["pillar_key"]
    cached = _body_cache.get(key)
    if cached and cached.get("loaded"):
        return
    try:
        db = get_supabase()
        result = (
            db.table("chunks")
            .select("content")
            .eq("document_id", pillar["document_id"])
            .order("chunk_index")
            .execute()
        )
        rows = result.data or []
        if not rows:
            logger.error(
                "No chunks found for pillar=%s document_id=%s — position-paper serving disabled for this call",
                key, pillar["document_id"],
            )
            return
        raw = "\n\n".join(r["content"] for r in rows)
        body = _strip_frontmatter(raw)
        headings = list(dict.fromkeys(h.strip() for h in _HEADING_RE.findall(body)))
        _body_cache[key] = {"loaded": True, "body": body, "headings": headings}
        logger.info(
            "Loaded position paper body from chunks table (pillar=%s, document_id=%s, %d chunks, %d chars, %d headings)",
            key, pillar["document_id"], len(rows), len(body), len(headings),
        )
    except Exception:
        logger.exception(
            "Failed to load position paper chunks for pillar=%s document_id=%s — position-paper serving disabled for this call",
            key, pillar["document_id"],
        )


def get_paper_body(pillar_key: str) -> Optional[str]:
    """Return the cached, frontmatter-stripped body for `pillar_key`, or
    None if it's not a registered pillar or could not be loaded."""
    pillar = _PILLARS_BY_KEY.get(pillar_key)
    if not pillar:
        return None
    _ensure_body(pillar)
    cached = _body_cache.get(pillar_key)
    if not cached or not cached.get("loaded"):
        return None
    return cached["body"]


def _sse(data: str) -> str:
    """Same SSE framing as chat.py's _sse() — duplicated here (not
    imported) to keep this module import-independent of chat.py, since
    chat.py imports FROM this module."""
    return f"data: {data}\n\n"


def generate_position_paper_answer(
    pillar_key: str, question: str, messages: Optional[List[object]] = None
) -> Iterator[str]:
    """Stream an SSE token event per output chunk for a position-paper-
    grounded answer to `question`, for whichever pillar `pillar_key`
    identifies — using that pillar's assembled voice system prompt (shared
    template + that pillar's own loaded body and its own derived heading
    list) as system context, and the real conversation history (if any) as
    prior turns.

    `pillar_key` must be one already returned by match_position_paper() —
    the caller (chat.py) is responsible for knowing which pillar matched;
    this function does not re-run the matcher.

    `messages` accepts the same shape as chat.py's ChatRequest.messages
    (a list of objects/dicts with .role/.content or ["role"]/["content"]) —
    duck-typed here rather than importing chat.py's ChatMessage, to avoid a
    circular import (chat.py imports from this module).

    No <answer> tag parsing is needed or performed: this dedicated prompt
    does not wrap its output in XML tags, so every content_block_delta is
    streamed directly as a token event.
    """
    pillar = _PILLARS_BY_KEY.get(pillar_key)
    if not pillar:
        logger.error("Unknown pillar_key=%s — cannot generate position-paper answer", pillar_key)
        yield _sse(json.dumps({"error": "position_paper_unavailable"}))
        return

    _ensure_body(pillar)
    cached = _body_cache.get(pillar_key)
    if not cached or not cached.get("loaded"):
        logger.error("Position paper body unavailable for pillar=%s — cannot generate answer", pillar_key)
        yield _sse(json.dumps({"error": "position_paper_unavailable"}))
        return

    paper_body = cached["body"]
    voice_system = _build_voice_system_prompt(pillar, cached["headings"])

    system_blocks = [
        {
            "type": "text",
            "text": voice_system,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                "Here is the full body of what Rhemata teaches on this topic — "
                "treat this as your own settled understanding, not as an "
                "external source to cite:\n\n" + paper_body
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    history = []  # type: List[Dict[str, str]]
    msgs = messages or []
    recent = msgs[-6:] if len(msgs) > 6 else msgs
    for msg in recent:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    history.append({"role": "user", "content": question})

    try:
        client = get_anthropic_client()
        stream = client.messages.create(
            model=get_generation_model(),
            max_tokens=2048,
            thinking={"type": "disabled"},
            system=system_blocks,
            messages=history,
            stream=True,
        )
        for event in stream:
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                text = event.delta.text
                if text:
                    yield _sse(json.dumps({"token": text}))
    except Exception:
        logger.exception("Position-paper LLM stream failed for pillar=%s", pillar_key)
        yield _sse(json.dumps({"error": "AI service temporarily unavailable"}))


# ── Sanctioned fallback: exclusion-emptied-the-answer only ────────────────
# Alex's ruling, 2026-08-06: if app.services.position_paper_exclusion
# removes every retrieved teacher for genuinely contradicting the matched
# house position, do not serve the empty state — fall back to the paper's
# own voice (a sanctioned form under the No-Oracle Rule) with the standard
# disclaimer. This is the ONLY sanctioned reason for this fallback — never
# thin retrieval, never a match failure, never an error; chat.py's/
# producer.py's own callers are responsible for only reaching this when
# that specific condition holds.
DISCLAIMER_TEXT = "Rhemata can make mistakes. Please let us know if you see any."


def render_paper_voice_with_disclaimer(pillar_key, question, messages=None):
    # type: (str, str, Optional[List[object]]) -> str
    """Buffer generate_position_paper_answer() into a complete string and
    append DISCLAIMER_TEXT, deterministically in code — never left to the
    model to phrase, so it can never be dropped, paraphrased, or mangled.
    Returns "" if the underlying generation produced nothing (caller decides
    how to handle that — this function does not itself supply a fallback
    fallback)."""
    parts = []  # type: List[str]
    for event in generate_position_paper_answer(pillar_key, question, messages):
        if not event.startswith("data: "):
            continue
        try:
            payload = json.loads(event[len("data: "):].rstrip("\n"))
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and "token" in payload:
            parts.append(payload["token"])
    answer = "".join(parts).strip()
    if not answer:
        return ""
    return answer + "\n\n" + DISCLAIMER_TEXT
