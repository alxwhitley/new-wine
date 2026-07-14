#!/usr/bin/env python3
"""
SP1 answer-quality baseline capture. Run this BEFORE Task 10's
system_prompt.txt edit lands. Saves real answers to a fixed set of
ordinary questions using the CURRENT (pre-SP1) prompt, for later
side-by-side comparison in Task 12. This is an explicit Phase B
acceptance criterion, not optional: the writer-instruction change touches
every answer, so proving ordinary answers are unchanged matters as much as
proving references resolve correctly.

Run from project root: python3 scripts/test_sp1_answer_quality_baseline.py
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

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

BASELINE_FILE = Path(__file__).resolve().parent / "sp1_answer_quality_baseline.json"

# A fixed set of ordinary questions, deliberately unrelated to any SP1 hard
# case — this checks general answer quality (length, tone, structure), not
# reference resolution.
QUESTIONS = [
    "What does it mean to be baptized in the Holy Spirit?",
    "How should a believer respond when a prayer for healing isn't answered?",
    "What is the charismatic understanding of prophetic ministry today?",
    "Why do Spirit-filled Christians believe tongues is still active?",
    "What does it look like to walk in the fruit of the Spirit day to day?",
]


def main():
    db = create_client(SB_URL, SB_SVC)
    baseline = {}
    for question in QUESTIONS:
        answer, _ = generate_real_answer(question, db)
        baseline[question] = answer
        print(f"Captured baseline for: {question!r} ({len(answer)} chars)")

    BASELINE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"\nSaved {len(baseline)} baseline answers to {BASELINE_FILE}")


if __name__ == "__main__":
    main()
