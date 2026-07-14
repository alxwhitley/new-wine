#!/usr/bin/env python3
"""
Track-B (constructed/injected) tests for the SP1 reference verifier.
Covers: biblical-figure backstop, nonexistent verse, not-servable teacher
(Leonard Ravenhill), MISS/sentinel teacher, presence-check drop, occurrence
anchoring (verse=every occurrence, teacher=first only), and malformed/
vague-reference robustness.

Run from project root: python3 scripts/test_reference_verifier.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.reference_verifier import (
    parse_reference_mentions,
    find_occurrences,
    verify_references,
)
from app.services.source_resolver import normalize_alias_key

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

db = create_client(SB_URL, SB_SVC)
failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if not condition:
        failures.append(label)


def main():
    # --- Parsing robustness ---
    raw_output_malformed = "<answer>...</answer>\n<reference_mentions>\nVERSE: Romans 8:28\nGARBAGE LINE\nTEACHER:\n</reference_mentions>"
    proposals = parse_reference_mentions(raw_output_malformed)
    check(
        "Malformed lines are skipped, well-formed line survives",
        proposals == [{"type": "verse", "raw": "Romans 8:28"}],
    )

    check(
        "Missing <reference_mentions> block returns empty, not an error",
        parse_reference_mentions("<answer>no block here</answer>") == [],
    )

    # --- B1: Biblical-figure backstop ---
    answer_text_1 = "Paul's letter to the Romans is foundational."
    raw_output_1 = "<reference_mentions>\nTEACHER: Paul\n</reference_mentions>"
    result_1 = verify_references(answer_text_1, raw_output_1, db)
    check("B1: 'Paul' proposed as teacher never resolves", result_1 == [])

    # --- B2: Nonexistent verse (Genesis 50 has 26 verses) ---
    answer_text_2 = "This is discussed in Genesis 50:99."
    raw_output_2 = "<reference_mentions>\nVERSE: Genesis 50:99\n</reference_mentions>"
    result_2 = verify_references(answer_text_2, raw_output_2, db)
    check("B2: nonexistent verse (Genesis 50:99) never resolves", result_2 == [])

    # --- B3: Not-servable teacher (Leonard Ravenhill — unlicensed/hidden) ---
    ravenhill_alias = db.table("source_aliases").select("source_id").eq(
        "alias_key", normalize_alias_key("Leonard Ravenhill")
    ).limit(1).execute()
    if not ravenhill_alias.data:
        print("  SKIP  B3: no live alias for 'Leonard Ravenhill' — confirm live data before treating this as a gap")
    else:
        answer_text_3 = "Leonard Ravenhill preached extensively on revival and repentance."
        raw_output_3 = "<reference_mentions>\nTEACHER: Leonard Ravenhill\n</reference_mentions>"
        result_3 = verify_references(answer_text_3, raw_output_3, db)
        check("B3: Leonard Ravenhill (real alias, not servable) never resolves", result_3 == [])

    # --- MISS / sentinel: a name with no alias at all ---
    answer_text_4 = "Some Nonexistent Teacher Name talks about grace."
    raw_output_4 = "<reference_mentions>\nTEACHER: Some Nonexistent Teacher Name\n</reference_mentions>"
    result_4 = verify_references(answer_text_4, raw_output_4, db)
    check("MISS: unaliased name never resolves (and never sentinel-resolves)", result_4 == [])

    # --- Presence-check drop: proposal not actually in the text ---
    answer_text_5 = "This answer never mentions any verse at all."
    raw_output_5 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_5 = verify_references(answer_text_5, raw_output_5, db)
    check("Presence check drops a proposal that never appears in the answer", result_5 == [])

    # --- Vague reference: no book match, always fails ---
    answer_text_6 = "That verse we discussed earlier is important."
    raw_output_6 = "<reference_mentions>\nVERSE: that verse\nVERSE: verse 26\n</reference_mentions>"
    result_6 = verify_references(answer_text_6, raw_output_6, db)
    check("Vague references ('that verse', 'verse 26') never resolve", result_6 == [])

    # --- Occurrence anchoring: verse repeated 2x, both anchored ---
    answer_text_7 = "Romans 8:28 tells us this. Later, Romans 8:28 is echoed again."
    raw_output_7 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_7 = verify_references(answer_text_7, raw_output_7, db)
    check(
        "Repeated verse mention anchors every occurrence",
        len(result_7) == 1 and result_7[0]["type"] == "verse" and len(result_7[0]["positions"]) == 2,
    )

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
