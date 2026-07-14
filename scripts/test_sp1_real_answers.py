#!/usr/bin/env python3
"""
Track-A (real-generation) test harness for SP1. Runs real questions through
the actual retrieval + Claude answer-writing path via generate_real_answer()
(same system prompt, same model, same retrieval fusion as production) — NOT
the live /chat HTTP endpoint, so no weekly-query-limit / guest-limit
metering and no conversations/messages rows are touched (per Alex's
confirmed harness choice).

IMPORTANT — per Alex's explicit instruction: a case where the model's
answer does not actually contain the targeted mention is NOT a pass by
default. If a run doesn't produce the expected mention, reword the
question and rerun until it does, THEN evaluate the verifier's output.
Do not silently count a non-materialized case as green.

Servability confirmed live before pinning this question set (2026-07-14):
    john bevere    -> John Bevere, unlicensed/shown  (safe_mode=off)  -> servable
    derek prince   -> Derek Prince, unlicensed/shown (safe_mode=off)  -> servable
    kenneth copeland -> no alias found                                -> absent from corpus
All three match what this case set assumes; no substitutions were needed.

Run from project root: python3 scripts/test_sp1_real_answers.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from sp1_answer_harness import generate_real_answer
from app.services.reference_verifier import verify_references

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

db = create_client(SB_URL, SB_SVC)

# Pinned test cases. "expect_mention" is the exact substring that must
# appear in the real generated answer for the case to be evaluable at all —
# if it doesn't appear, rerun with a reworded question, do not score it.
CASES = [
    {
        "id": "A1_biblical_figure_narrative",
        "question": "Walk me through the story of Paul's conversion on the road to Damascus and what it teaches about God's sovereignty in salvation.",
        "expect_mention": "Paul",
        "bar": "Zero TEACHER pointers for 'Paul'. Verse citations (e.g. Acts references), if any, may resolve as verses.",
    },
    {
        "id": "A2_ambiguous_shared_name",
        "question": "What does John Bevere teach about the fear of the Lord, and how does that connect to what the Apostle John writes about love and fear in his first epistle?",
        "expect_mention": "John Bevere",
        "bar": "Exactly one TEACHER pointer for 'John Bevere' (first full-name mention). Any bare 'John' / 'the Apostle John' biblical mention never resolves as TEACHER, even if mismarked by the writer.",
    },
    {
        "id": "A3_teacher_not_in_corpus",
        "question": "What does Kenneth Copeland teach about faith, and how does that compare to what's in this library?",
        "expect_mention": "Kenneth Copeland",
        "bar": "No TEACHER pointer, and no verified_references entry ever carries the sentinel source id (267a09ac-76f3-43fb-901f-3015aef88e22).",
    },
    {
        "id": "A4_verse_range",
        "question": "What does Romans 8:26-28 teach about the Spirit's help in our weakness?",
        "expect_mention": "Romans 8:2",  # loose match — model may write 8:26-28 or 8:26–28
        "bar": "Exactly one verified verse reference spanning the whole range (both endpoints must independently resolve).",
    },
    {
        "id": "A5_repeated_teacher_mention",
        "question": "What does Derek Prince teach about spiritual authority, and can you also summarize his overall approach to intercession?",
        "expect_mention": "Derek Prince",
        "bar": "Exactly one TEACHER pointer, anchored at the first full-name occurrence. A later short-form mention (e.g. bare 'Prince') produces no second pointer.",
    },
    {
        "id": "A6_vague_reference",
        "question": "Can you unpack what that verse about being transformed by the renewing of your mind is about?",
        "expect_mention": "renewing",
        "bar": "The model's own answer should name the real reference (Romans 12:2) explicitly rather than staying vague — if it does, that resolves normally. This case primarily checks the writer follows instructions; the verifier's robustness against genuinely vague strings is separately proven in Track B.",
    },
    {
        "id": "A7_user_mentioned_verse_named_back",
        "question": "What does Romans 8:28 mean, and how should it shape the way I process a hard season?",
        "expect_mention": "Romans 8:28",
        "bar": "The answer must explicitly name 'Romans 8:28' back in its own text — not just discuss the passage thematically without ever citing the reference (this is the writer-instruction added in Task 10, tested directly here). Once named, it must also appear in verified_references as a resolved verse pointer — this is the exact case the spec's own rationale is about: if the answer never names the verse the user asked about, there is nothing for the panel to ever trigger on.",
    },
]


def extract_reference_mentions_block(raw_output):
    """Return the raw substring between <reference_mentions> tags, if
    present, so a reader can see what the writer actually proposed versus
    what survived verification. Returns None if the block is absent
    (e.g. generation was truncated before reaching it)."""
    start = raw_output.find("<reference_mentions>")
    end = raw_output.find("</reference_mentions>")
    if start != -1 and end != -1:
        return raw_output[start + len("<reference_mentions>"):end].strip()
    return None


def run_case(case):
    print("=" * 70)
    print(f"CASE: {case['id']}")
    print(f"Question: {case['question']}")
    print(f"Bar: {case['bar']}")
    print("-" * 70)

    answer, raw_output = generate_real_answer(case["question"], db)

    # Fix 2: an empty/absent verifier result is only meaningful evidence if
    # generation actually completed. Without a real </answer> closing tag,
    # the model was truncated (max_tokens) before finishing — possibly
    # before it ever reached the <reference_mentions> block — so there is
    # nothing to score. Treat this the same as DID NOT MATERIALIZE rather
    # than letting a vacuous empty result be reported as a clean pass.
    generation_complete = "</answer>" in raw_output
    if not generation_complete:
        print("*** GENERATION TRUNCATED — no closing </answer> tag found in raw output. ***")
        print("*** The model's response was cut off (max_tokens) before finishing. This case CANNOT be scored — an empty verifier result here would be meaningless, not a pass. ***")
        print(f"Raw output for review:\n{raw_output}\n")
        return {"id": case["id"], "materialized": False, "truncated": True}

    materialized = case["expect_mention"] in answer
    print(f"Target mention present in answer: {materialized}")
    if not materialized:
        print("*** NOT MATERIALIZED — reword the question and rerun. Do not score this case. ***")
        print(f"Full answer for review:\n{answer}\n")
        return {"id": case["id"], "materialized": False}

    verified = verify_references(answer, raw_output, db)
    mentions_block = extract_reference_mentions_block(raw_output)
    print(f"Answer:\n{answer}\n")
    print(f"Raw <reference_mentions> block (what the writer actually proposed):\n{mentions_block}\n")
    print(f"Verifier output:\n{json.dumps(verified, indent=2)}\n")

    return {"id": case["id"], "materialized": True, "answer": answer, "verified": verified}


def main():
    results = []
    for case in CASES:
        results.append(run_case(case))

    print("=" * 70)
    print("SUMMARY — review each result against its stated bar by hand.")
    for r in results:
        if r["materialized"]:
            status = "MATERIALIZED — inspect above against the bar"
        elif r.get("truncated"):
            status = "TRUNCATED — generation cut off before </answer>, rerun before scoring"
        else:
            status = "DID NOT MATERIALIZE — rerun with reworded question"
        print(f"  {r['id']}: {status}")


if __name__ == "__main__":
    main()
