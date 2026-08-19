#!/usr/bin/env python3
"""
test_debate_topics.py -- regression tests for Project 2 phase 1's debate-
vs-settled classifier (backend/app/services/debate_topics.py) and its
get_teacher_card() integration (backend/app/routers/study.py).

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions, a `main()` that runs
everything, `if __name__ == "__main__": main()` (see test_positions.py,
the Calvinism/predestination tension-mode matcher's own test file, which
this classifier's shape was built to mirror).

Tier A (deterministic, no live calls): imports debate_topics.py and
study.py directly and asserts against classify_topic() / matched_debate_
topic() / _select_teacher_position_prompt() -- real questions covering all
four debate topics (apostolic authority, eschatological timing, healing
mechanics, prophetic accountability), the one settled topic (tongues), and
several genuinely ambiguous/off-topic questions to confirm the default-to-
debate behavior actually fires (and is never SETTLED by accident).

Tier B (1 behavior, live, real cost): a real GET /study/teacher/{source_id}
call (the get_teacher_card() route function itself, called directly --
Depends() defaults are simply overridden by passing user_id explicitly, no
FastAPI server needed) against Derek Prince (the corpus's largest, richest
teacher -- see scripts/test_teacher_card.py's own curated-teacher list),
once with a debate-topic question and once with an ordinary question, to
confirm the fix works end to end: the endpoint does not crash and returns
a real, non-empty `position` either way. Requires SUPABASE_URL/
SUPABASE_SERVICE_KEY + the Anthropic key to be set (backend/app/.env),
same as scripts/test_teacher_card.py.

get_teacher_card() now meters every call via enforce_query_limit() (2026-08-19
fix for the previously-unmetered teacher-card cost/abuse gap), which writes to
the real `user_usage` table and requires a user_id that is an actual
auth.users row (a placeholder string 400s on the RPC's uuid param, and a
syntactically-valid-but-nonexistent UUID FK-violates). Tier B therefore
resolves a real test user (TEST_EMAIL, same account scripts/test_metering.py
uses) via the admin API rather than a fake id, and each of the 2 calls below
consumes one real slot against that account's weekly query limit -- a live
side effect, not just an Anthropic cost, disclosed here so it isn't a
surprise when this script is next run.

Run: python3 scripts/test_debate_topics.py
"""
import asyncio
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from app.services import debate_topics as dt  # noqa: E402
from app.routers import study  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- classify_topic() / matched_debate_topic()
# ═══════════════════════════════════════════════════════════════════════════

# Realistic phrasings a real user would type, per topic (CLAUDE.md Settled
# decision #11's four-topic anchor set).
DEBATE_QUESTIONS = {
    "apostolic_authority": [
        "Is there such a thing as apostolic authority in the church today?",
        "Are there apostles today, or did that office end with the original twelve?",
        "What is the five-fold ministry and does it still apply now?",
        "How should apostolic ministry be held accountable?",
    ],
    "eschatological_timing": [
        "Will the rapture happen before or after the tribulation?",
        "What does the Bible teach about the millennium?",
        "Is a pre-tribulation rapture biblical?",
        "What's the difference between premillennial and amillennial views?",
    ],
    "healing_mechanics": [
        "Is healing guaranteed in the atonement for every believer?",
        "Why am I not healed even though I have faith?",
        "Does God always heal if we have enough faith?",
        "What are the gifts of healing and how do they operate?",
    ],
    "prophetic_accountability": [
        "How do you test a prophetic word given in church?",
        "What makes a prophecy false, and how should it be corrected?",
        "Are there prophets today, and how is their authority held accountable?",
    ],
}

TONGUES_QUESTIONS = [
    "What does it mean to speak in tongues?",
    "Is speaking in tongues required as the initial evidence of the baptism of the Holy Spirit?",
    "What is a private prayer language?",
    "How does interpretation of tongues work in a church service?",
]

# Genuinely ambiguous/off-topic questions -- none of these should match any
# phrase list, so all must fall through to the DEBATE default.
DEFAULT_QUESTIONS = [
    "What is deliverance?",
    "How can I hear God's voice more clearly?",
    "What does the Bible say about tithing?",
    "How do I study the book of Romans?",
    "What is the fruit of the Spirit?",
    "Should Christians fast, and how often?",
]


def test_debate_topics_match():
    print("\n" + "=" * 78)
    print("Tier A: classify_topic() -- the four debate topics -> DEBATE")
    print("=" * 78)
    for topic_key, questions in DEBATE_QUESTIONS.items():
        for q in questions:
            _check(f"[{topic_key}] {q!r} -> DEBATE", dt.classify_topic(q) == dt.DEBATE)
            _check(f"[{topic_key}] {q!r} -> matched_debate_topic == {topic_key!r}",
                   dt.matched_debate_topic(q) == topic_key)


def test_tongues_matches_settled():
    print("\n" + "=" * 78)
    print("Tier A: classify_topic() -- tongues -> SETTLED")
    print("=" * 78)
    for q in TONGUES_QUESTIONS:
        _check(f"{q!r} -> SETTLED", dt.classify_topic(q) == dt.SETTLED)
        _check(f"{q!r} -> matched_debate_topic is None", dt.matched_debate_topic(q) is None)


def test_default_is_debate_never_settled():
    print("\n" + "=" * 78)
    print("Tier A: classify_topic() -- unmatched questions default to DEBATE")
    print("=" * 78)
    for q in DEFAULT_QUESTIONS:
        result = dt.classify_topic(q)
        _check(f"{q!r} -> DEBATE (default)", result == dt.DEBATE)
        _check(f"{q!r} -> never SETTLED", result != dt.SETTLED)
        _check(f"{q!r} -> matched_debate_topic is None (no real match)",
               dt.matched_debate_topic(q) is None)


def test_two_value_output_only():
    print("\n" + "=" * 78)
    print("Tier A: classify_topic() only ever returns DEBATE or SETTLED")
    print("=" * 78)
    all_questions = (
        [q for qs in DEBATE_QUESTIONS.values() for q in qs]
        + TONGUES_QUESTIONS
        + DEFAULT_QUESTIONS
    )
    for q in all_questions:
        _check(f"{q!r} result in (DEBATE, SETTLED)", dt.classify_topic(q) in (dt.DEBATE, dt.SETTLED))


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- study.py's _select_teacher_position_prompt() routing
# ═══════════════════════════════════════════════════════════════════════════

def test_teacher_card_prompt_routing():
    print("\n" + "=" * 78)
    print("Tier A: study._select_teacher_position_prompt()")
    print("=" * 78)

    debate_q = "What does this teacher believe about the timing of the rapture?"
    _check(
        "debate-topic question -> TEACHER_POSITION_DEBATE_PROMPT",
        study._select_teacher_position_prompt(debate_q) is study.TEACHER_POSITION_DEBATE_PROMPT,
    )

    ordinary_q = "What does this teacher say about tithing and generosity?"
    _check(
        "ordinary question -> TEACHER_POSITION_PROMPT (unchanged)",
        study._select_teacher_position_prompt(ordinary_q) is study.TEACHER_POSITION_PROMPT,
    )

    tongues_q = "Does this teacher believe tongues is the initial evidence of the baptism?"
    _check(
        "settled (tongues) question -> TEACHER_POSITION_PROMPT (unchanged)",
        study._select_teacher_position_prompt(tongues_q) is study.TEACHER_POSITION_PROMPT,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- live get_teacher_card() end-to-end (real Anthropic + DB calls)
# ═══════════════════════════════════════════════════════════════════════════

DEREK_PRINCE_SOURCE_ID = None  # resolved live below, not hardcoded

# Real, existing auth.users account -- get_teacher_card()'s metering call
# (enforce_query_limit) FK-references auth.users, so this can no longer be a
# placeholder string. Same account scripts/test_metering.py uses.
TEST_EMAIL = "creative@clf-church.com"


async def _resolve_derek_prince_source_id():
    from app.db.supabase import get_supabase
    db = get_supabase()
    result = (
        db.table("teacher_profiles")
        .select("source_id, sources(name)")
        .execute()
    )
    for row in result.data or []:
        if row.get("sources", {}).get("name") == "Derek Prince":
            return row["source_id"]
    return None


def _resolve_test_user_id():
    from app.db.supabase import get_supabase
    db = get_supabase()
    link = db.auth.admin.generate_link({"type": "magiclink", "email": TEST_EMAIL})
    return link.user.id


async def _run_tier_b():
    print("\n" + "=" * 78)
    print("Tier B: get_teacher_card() end-to-end (live Anthropic + DB calls)")
    print("=" * 78)

    source_id = await _resolve_derek_prince_source_id()
    _check("Derek Prince source_id resolved", source_id is not None)
    if not source_id:
        print("  Skipping Tier B -- could not resolve Derek Prince's source_id.")
        return

    test_user_id = _resolve_test_user_id()
    print(f"  Metering against real test account: {TEST_EMAIL} ({test_user_id})")

    debate_question = "What does Derek Prince teach about the timing of the rapture and the tribulation?"
    _check("debate question classifies as DEBATE", dt.classify_topic(debate_question) == dt.DEBATE)
    debate_card = await study.get_teacher_card(source_id, debate_question, user_id=test_user_id)
    _check("debate-topic card returns a non-empty position", bool((debate_card or {}).get("position")))
    print(f"\n  -- debate-topic position (first 200 chars) --\n  {(debate_card.get('position') or '')[:200]}\n")

    ordinary_question = "What does Derek Prince teach about tithing and financial stewardship?"
    _check("ordinary question classifies as DEBATE default (not settled)", dt.classify_topic(ordinary_question) == dt.DEBATE)
    ordinary_card = await study.get_teacher_card(source_id, ordinary_question, user_id=test_user_id)
    _check("ordinary-topic card returns a non-empty position", bool((ordinary_card or {}).get("position")))
    print(f"\n  -- ordinary-topic position (first 200 chars) --\n  {(ordinary_card.get('position') or '')[:200]}\n")


def main():
    print("#" * 78)
    print("test_debate_topics.py")
    print("#" * 78)

    test_debate_topics_match()
    test_tongues_matches_settled()
    test_default_is_debate_never_settled()
    test_two_value_output_only()
    test_teacher_card_prompt_routing()

    print("\n" + "#" * 78)
    if failures:
        print(f"Tier A: {len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("Tier A: all assertions passed.")
    print("#" * 78)

    print(
        "\nTier B below makes live Anthropic API calls (real, small cost) and "
        "opens a real DB connection against Derek Prince's real corpus data. "
        "See scripts/test_teacher_card.py for the same disclosure pattern."
    )
    asyncio.run(_run_tier_b())

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S) TOTAL: " + ", ".join(failures))
    else:
        print("All assertions passed (Tier A + Tier B).")
    print("#" * 78)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
