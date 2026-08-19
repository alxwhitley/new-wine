#!/usr/bin/env python3
"""
prove_stored_position_injection.py -- live, real-generation proof for the
Project 2 one-hop evidence-injection wiring
(backend/app/services/stored_position_evidence.py +
async_answers/producer.py's produce()).

Not a regression test (no _check()/pass-fail assertions) -- a side-by-side
comparison tool for a human to read: for each of the six V1 topics, prints
the OLD-path answer (real generation through normal _retrieve(), as if the
injection wiring did not exist) next to the NEW-path answer (real
generation through produce(), which now injects stored evidence for a
matched topic) next to the stored position's own rendered `content` text --
so a human can visually confirm the served answer reads as fresh generated,
cited prose and NOT as the stored position's own frozen phrasing. This is
this build's own stop-and-flag condition: if the stored position's exact
rendered text turns up verbatim in a served answer, evidence boundaries
leaked and this script says so explicitly.

Makes real Anthropic API calls -- one OLD + one NEW generation per topic,
plus one produce() call each for a debate-topic, a paper-fenced (tongues),
and an unrelated question (to confirm zero evidence-injection breadcrumbs
fire for any of them). ~15 real single-question answers total, small and
bounded, nowhere near corpus-scale spend. Three of the six topics currently
have zero surviving evidence (their sole contributor, Vlad Savchuk, is
presently unlicensed/hidden -- see stored_position_evidence.py's own
docstring) and will show identical OLD/NEW output by construction; that is
expected, not a failure of this script or the build.

Read-only against the DB; the only real side effect is the Anthropic spend.
produce() itself does not persist conversations or meter usage (that lives
in async_chat.py/jobs.py, not here) -- see producer.py's own module
docstring.

Run: python3 scripts/prove_stored_position_injection.py
"""
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

logging.basicConfig(level=logging.WARNING)  # keep noise down; this is a human-read tool

from app.db.supabase import get_supabase  # noqa: E402
from app.services.async_answers import producer  # noqa: E402
from app.services import stored_position_evidence as spe  # noqa: E402
from app.services import stored_position_topics as spt  # noqa: E402

REPRESENTATIVE_QUESTIONS = {
    "fasting": "How should I fast as a Christian?",
    "deliverance from demons and spiritual warfare": "What is deliverance from demons?",
    "how to pray effectively": "How do I pray effectively?",
    "the divine exchange at the cross": "What is the divine exchange at the cross?",
    "can a believer lose their salvation": "Can a believer lose their salvation?",
    "holiness and personal purity": "What does the Bible teach about holiness and personal purity?",
}

DEBATE_QUESTION = "Is healing guaranteed in the atonement for every believer?"
TONGUES_QUESTION = "What does it mean to speak in tongues?"
UNRELATED_QUESTION = "What does the Bible say about tithing?"


def _old_path_answer(db, question):
    """Real generation through the ORIGINAL retrieval path (_retrieve()),
    bypassing the new injection wiring entirely -- what produce() would
    have returned before this build."""
    chunks, citations, citable_count, _ = producer._retrieve(db, question, set(), None)
    if not chunks:
        return "[no material retrieved -- old path would return no_material]", []
    context = producer._build_context(chunks, citable_count, None)
    history = producer._build_history([], context, question)
    answer, _raw_output, _sr, _usage, _model = producer._generate_and_capture(history)
    return answer, citations


def _stored_position_text(db, topic_key):
    # Any current lineage for this topic_key, not filtered on
    # requested_teacher_id -- see stored_position_evidence.py's
    # _current_position_id() docstring for why (4 of the 6 seeded topics'
    # current row was built via a teacher-explicit ask and has
    # requested_teacher_id set, not NULL).
    result = (
        db.table("positions")
        .select("content")
        .eq("topic_key", topic_key)
        .eq("is_current", True)
        .neq("status", "retracted")
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]["content"]


def compare_topic(db, topic_key, question):
    print("\n" + "#" * 90)
    print(f"TOPIC: {topic_key!r}")
    print(f"QUESTION: {question!r}")
    print("#" * 90)

    matched = spt.match_stored_position(question)
    print(f"match_stored_position(question) = {matched!r} (expected {topic_key!r})")
    if matched != topic_key:
        print("  !!! FLAG: representative question did not match its own topic key. !!!")

    evidence = spe.fetch_stored_position_evidence(db, topic_key)
    print(f"fetch_stored_position_evidence -> {len(evidence) if evidence else 0} chunk(s)")
    if evidence:
        print("\n--- INJECTED EVIDENCE (raw propositions, what the writer sees) ---")
        for c in evidence:
            print(f"  [{c.get('author')}] {c['content']}")

    stored_text = _stored_position_text(db, topic_key)
    print("\n--- STORED POSITION'S OWN RENDERED TEXT (must NOT appear verbatim below) ---")
    print(f"  {stored_text!r}")

    print("\n--- OLD PATH (normal RAG, no injection) ---")
    old_answer, old_citations = _old_path_answer(db, question)
    print(old_answer)
    print(f"  ({len(old_citations)} citations)")

    print("\n--- NEW PATH (produce(), injection wired) ---")
    result = producer.produce(db, question)
    print(result.answer)
    print(f"  (outcome={result.outcome}, {len(result.citations)} citations)")

    if stored_text and stored_text.strip() and stored_text.strip() in result.answer:
        print(
            "\n  !!! FLAG: the stored position's own rendered text appears verbatim "
            "in the served answer -- evidence boundaries may have leaked. STOP for "
            "review. !!!"
        )


def compare_excluded(db, label, question):
    print("\n" + "#" * 90)
    print(f"EXCLUSION CHECK: {label}")
    print(f"QUESTION: {question!r}")
    print("#" * 90)
    matched = spt.match_stored_position(question)
    print(f"match_stored_position(question) = {matched!r} (expected None)")
    if matched is not None:
        print("  !!! FLAG: a topic matched when it should not have. STOP for review. !!!")
        return
    result = producer.produce(db, question)
    print(
        f"produce() outcome={result.outcome}, {len(result.citations)} citations -- "
        "normal RAG, no injection expected"
    )


def main():
    db = get_supabase()
    for topic_key, question in REPRESENTATIVE_QUESTIONS.items():
        compare_topic(db, topic_key, question)

    compare_excluded(db, "debate topic (healing mechanics)", DEBATE_QUESTION)
    compare_excluded(db, "paper-fenced (tongues)", TONGUES_QUESTION)
    compare_excluded(db, "unrelated (tithing)", UNRELATED_QUESTION)


if __name__ == "__main__":
    main()
