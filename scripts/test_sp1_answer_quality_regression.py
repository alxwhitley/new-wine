#!/usr/bin/env python3
"""
SP1 answer-quality regression check. Run AFTER Task 10's system_prompt.txt
edit and Task 11's chat.py wiring have both landed. Re-runs the exact same
questions from Task 9's baseline capture, through the NEW prompt, and
prints both answers side by side for manual comparison of length, tone,
and structure. This is an explicit Phase B acceptance criterion — not
optional, not a "looks fine, moving on."

Run from project root: python3 scripts/test_sp1_answer_quality_regression.py
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


def main():
    if not BASELINE_FILE.exists():
        print(f"No baseline file at {BASELINE_FILE} — run Task 9's capture script "
              f"BEFORE this comparison, or this check proves nothing.")
        sys.exit(1)

    baseline = json.loads(BASELINE_FILE.read_text())
    db = create_client(SB_URL, SB_SVC)

    for question, before_answer in baseline.items():
        after_answer, raw_output = generate_real_answer(question, db)
        assert "<reference_mentions>" not in after_answer, (
            "The <reference_mentions> block leaked into the visible answer text — "
            "this is a hard failure, stop and fix the prompt/parsing before proceeding."
        )
        print("=" * 70)
        print(f"QUESTION: {question}")
        print(f"BEFORE ({len(before_answer)} chars):\n{before_answer}\n")
        print(f"AFTER  ({len(after_answer)} chars):\n{after_answer}\n")
        print("Compare by hand: same length ballpark? same tone, structure, headings? "
              "same level of conviction and citation style?")

    print("\nReview every pair above. This check passes only when a human confirms "
          "no case reads meaningfully different in length, tone, or quality.")


if __name__ == "__main__":
    main()
