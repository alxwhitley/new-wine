#!/usr/bin/env python3
"""
test_stored_position_topics.py -- regression tests for the Project 2 one-hop
stored-position matcher (backend/app/services/stored_position_topics.py,
PLAN.md Open Decision #16 V1 list).

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest, hand-
built `_check(label, condition)` assertions, a `main()` that runs everything,
`if __name__ == "__main__": main()` (see test_debate_topics.py, whose shape
this file was built to mirror).

Tier A (deterministic, no live calls): imports stored_position_topics.py
directly and asserts match_stored_position() against real questions covering
all six V1 topics, plus the two fail-safe gates (debate wins, tongues
paper-fence), off-topic questions, and a constructed multi-match refusal. Also
enforces the migration-077 key contract: STORED_POSITION_TOPIC_KEYS must be
byte-identical to scripts/positions.py::normalize_topic_key() of each key --
this is where that contract is checked, deliberately NOT at the module's own
import time (see the module's registry comment).

Tier B (1 behavior, live, read-only DB, ZERO writes): confirms every
STORED_POSITION_TOPIC_KEYS value has a live `positions` row with
is_current=true, so the matcher's outputs will actually resolve to a stored
position when the one-hop injection slice lands later. Guarded behind DB creds
like test_debate_topics.py's Tier B; skips cleanly if creds absent.

Run: python3 scripts/test_stored_position_topics.py
"""
import logging
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from app.services import stored_position_topics as spt  # noqa: E402
from app.services import debate_topics as dt  # noqa: E402
from positions import normalize_topic_key  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- match_stored_position(): each V1 topic fires on its own anchors
# ═══════════════════════════════════════════════════════════════════════════

# Realistic phrasings a real user would type, per V1 topic. Each MUST return
# exactly that topic's stored key.
TOPIC_QUESTIONS = {
    "fasting": [
        "What does the Bible say about fasting?",
        "How to fast as a Christian?",
        "Why fast and pray before a big decision?",
        "Is there a biblical fast I should follow?",
    ],
    "deliverance from demons and spiritual warfare": [
        "What is deliverance?",
        "How do you engage in spiritual warfare?",
        "Can Christians cast out demons?",
        "What does casting out demons look like today?",
        "Is demonic oppression real for believers?",
    ],
    "how to pray effectively": [
        "How to pray so that God hears me?",
        "How should i pray when I don't know what to say?",
        "What makes for effective prayer?",
        "How do I build a stronger prayer life?",
        "What is intercession?",
    ],
    "the divine exchange at the cross": [
        "What is the divine exchange?",
        "Explain the great exchange in the gospel.",
        "What happened at the cross for me?",
        "The exchange at the cross -- what did Jesus take?",
    ],
    "can a believer lose their salvation": [
        "Can a believer lose their salvation?",
        "Is once saved always saved biblical?",
        "What is eternal security?",
        "Can a christian fall away and be lost?",
        "What is the perseverance of the saints?",
    ],
    "holiness and personal purity": [
        "What does the Bible teach about holiness?",
        "How do I pursue personal purity?",
        "What is sanctification?",
        "How can I walk in holiness day to day?",
    ],
}


def test_each_topic_matches_its_key():
    print("\n" + "=" * 78)
    print("Tier A: match_stored_position() -- each V1 topic -> its stored key")
    print("=" * 78)
    for topic_key, questions in TOPIC_QUESTIONS.items():
        for q in questions:
            _check(
                f"[{topic_key}] {q!r} -> {topic_key!r}",
                spt.match_stored_position(q) == topic_key,
            )


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- fail-safe gate 1: debate topics win (return None)
# ═══════════════════════════════════════════════════════════════════════════

# Real debate-topic questions from test_debate_topics.py's own set -- every one
# must return None here (a stored position must never be injected on a
# decision-#11 debate topic). Includes the phrase anchors named in the plan.
DEBATE_QUESTIONS = [
    "Will the rapture happen before or after the tribulation?",
    "Is healing guaranteed in the atonement for every believer?",
    "Are there apostles today, or did that office end with the twelve?",
    "What is the office of an apostle?",
    "How do you test a prophetic word given in church?",
    "What does the Bible teach about the millennium?",
]


def test_debate_topics_win():
    print("\n" + "=" * 78)
    print("Tier A: debate topics win -> match_stored_position() is None")
    print("=" * 78)
    for q in DEBATE_QUESTIONS:
        # Sanity: these really are debate-classified upstream.
        _check(f"{q!r} is a debate topic (upstream)", dt.matched_debate_topic(q) is not None)
        _check(f"{q!r} -> None (debate wins)", spt.match_stored_position(q) is None)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- fail-safe gate 2: paper-fenced topics (tongues/baptism) out
# ═══════════════════════════════════════════════════════════════════════════

PAPER_FENCED_QUESTIONS = [
    "What does it mean to speak in tongues?",
    "Is speaking in tongues the initial evidence of the baptism of the Holy Spirit?",
    "What is a private prayer language?",
    "How does interpretation of tongues work in a service?",
    "What is the baptism in the Holy Spirit?",
]


def test_paper_fenced_topics_out():
    print("\n" + "=" * 78)
    print("Tier A: paper-fenced topics (tongues/baptism) -> None")
    print("=" * 78)
    for q in PAPER_FENCED_QUESTIONS:
        _check(f"{q!r} -> None (paper-fenced, out of V1)", spt.match_stored_position(q) is None)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- ordinary/off-topic questions match nothing
# ═══════════════════════════════════════════════════════════════════════════

OFF_TOPIC_QUESTIONS = [
    "Who was Moses?",
    "What time is the service on Sunday?",
    "What does the Bible say about tithing?",
    "How do I study the book of Romans?",
    "What is the fruit of the Spirit?",
    "Tell me about the life of the apostle Paul.",
]


def test_off_topic_none():
    print("\n" + "=" * 78)
    print("Tier A: ordinary/off-topic questions -> None (normal RAG)")
    print("=" * 78)
    for q in OFF_TOPIC_QUESTIONS:
        _check(f"{q!r} -> None", spt.match_stored_position(q) is None)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- multi-match refusal (near-tie -> None, and it logs)
# ═══════════════════════════════════════════════════════════════════════════

def test_multi_match_refuses_and_logs():
    print("\n" + "=" * 78)
    print("Tier A: multi-match refusal -> None (and logs)")
    print("=" * 78)

    # Hits BOTH "fasting" and "holiness and personal purity" phrase lists.
    q = "How does fasting relate to holiness in the Christian life?"

    # Precondition: it really does hit two topic lists (so this exercises the
    # >=2 branch, not the 0/1 branch).
    hits = spt._matched_topic_keys(q)
    _check(f"{q!r} hits >=2 topic lists (actually {hits})", len(hits) >= 2)

    # It must refuse to None...
    _check(f"{q!r} -> None (multi-match refusal)", spt.match_stored_position(q) is None)

    # ...and it must have logged the refusal at INFO on the module's logger.
    import logging as _logging

    class _Capture(_logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    cap = _Capture()
    spt_logger = _logging.getLogger("app.services.stored_position_topics")
    spt_logger.addHandler(cap)
    try:
        spt.match_stored_position(q)
    finally:
        spt_logger.removeHandler(cap)
    _check(
        "multi-match refusal emitted an INFO log breadcrumb",
        any("multi-match refusal" in r.getMessage() for r in cap.records),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- key contract: STORED_POSITION_TOPIC_KEYS are normalize_topic_key-
# canonical (migration-077 byte-identity), checked here not at import time
# ═══════════════════════════════════════════════════════════════════════════

# The six V1 topic_keys, exactly as recorded in
# docs/audits/position_topic_list_v1_2026-08-07.md. Independent literal copy so
# the assertion is against the source of truth, not the module echoing itself.
V1_TOPIC_KEYS = (
    "fasting",
    "deliverance from demons and spiritual warfare",
    "how to pray effectively",
    "the divine exchange at the cross",
    "can a believer lose their salvation",
    "holiness and personal purity",
)


def test_key_contract():
    print("\n" + "=" * 78)
    print("Tier A: STORED_POSITION_TOPIC_KEYS byte-identity vs normalize_topic_key")
    print("=" * 78)
    _check(
        "module keys == V1 doc keys (same set, same order)",
        spt.STORED_POSITION_TOPIC_KEYS == V1_TOPIC_KEYS,
    )
    for k in spt.STORED_POSITION_TOPIC_KEYS:
        _check(
            f"{k!r} is normalize_topic_key-canonical (== normalize_topic_key(k))",
            k == normalize_topic_key(k),
        )


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- every V1 key resolves to a live is_current=true positions row
# (read-only, ZERO writes)
# ═══════════════════════════════════════════════════════════════════════════

def _run_tier_b():
    print("\n" + "=" * 78)
    print("Tier B: every V1 key has a live is_current=true positions row (read-only)")
    print("=" * 78)

    if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY")):
        print("  Skipping Tier B -- SUPABASE_URL / SUPABASE_SERVICE_KEY not set.")
        return

    from app.db.supabase import get_supabase
    db = get_supabase()
    result = (
        db.table("positions")
        .select("topic_key, is_current")
        .eq("is_current", True)
        .execute()
    )
    live_keys = {row["topic_key"] for row in (result.data or [])}
    for k in spt.STORED_POSITION_TOPIC_KEYS:
        _check(f"{k!r} has a live is_current position row", k in live_keys)


def main():
    print("#" * 78)
    print("test_stored_position_topics.py")
    print("#" * 78)

    test_each_topic_matches_its_key()
    test_debate_topics_win()
    test_paper_fenced_topics_out()
    test_off_topic_none()
    test_multi_match_refuses_and_logs()
    test_key_contract()

    print("\n" + "#" * 78)
    if failures:
        print(f"Tier A: {len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("Tier A: all assertions passed.")
    print("#" * 78)

    print(
        "\nTier B below opens a real (read-only) DB connection against the live "
        "positions table -- no writes. Skips cleanly if creds are absent."
    )
    _run_tier_b()

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S) TOTAL: " + ", ".join(failures))
    else:
        print("All assertions passed (Tier A + Tier B).")
    print("#" * 78)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
