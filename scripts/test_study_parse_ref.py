#!/usr/bin/env python3
"""
Live test suite for app.routers.study.parse_ref (Site B in the 2026-07-28
ordinal/spelled-word/Roman-numeral scripture-book-name recognition fix).

No existing live test file touched study.py or BOOK_MAP before this session
(confirmed by grep across scripts/test_*.py) -- this file closes that gap.
parse_ref itself does no DB I/O, so no live Supabase connection is required,
unlike scripts/test_reference_verifier.py's sibling tests for Site C.

Run from project root: python3 scripts/test_study_parse_ref.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.routers.study import parse_ref

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if not condition:
        failures.append(label)


def main():
    # --- Digit-form baseline (must never regress) ---
    check(
        "Digit form '1 Samuel 3:13' resolves to ('1SA', 3, 13)",
        parse_ref("1 Samuel 3:13") == ("1SA", 3, 13),
    )
    check(
        "Abbreviation form '1Cor 13:4' resolves to ('1CO', 13, 4)",
        parse_ref("1Cor 13:4") == ("1CO", 13, 4),
    )
    check(
        "Unnumbered book 'John 3:16' resolves to ('JHN', 3, 16)",
        parse_ref("John 3:16") == ("JHN", 3, 16),
    )

    # --- Ordinal-digit form: the primary normalization bug ---
    # Before the fix: "1st samuel" normalized to "1 st samuel" (space
    # inserted after the bare digit, "st" left stuck to "samuel") and never
    # matched any BOOK_MAP key regardless of how the map was widened.
    check(
        "Ordinal form '1st Samuel 3:13' resolves to ('1SA', 3, 13)",
        parse_ref("1st Samuel 3:13") == ("1SA", 3, 13),
    )
    check(
        "Ordinal form '2nd Corinthians 5:21' resolves to ('2CO', 5, 21)",
        parse_ref("2nd Corinthians 5:21") == ("2CO", 5, 21),
    )
    check(
        "Ordinal form '3rd John 1:4' resolves to ('3JN', 1, 4)",
        parse_ref("3rd John 1:4") == ("3JN", 1, 4),
    )

    # --- Spelled-word form ---
    check(
        "Spelled form 'First Samuel 3:13' resolves to ('1SA', 3, 13)",
        parse_ref("First Samuel 3:13") == ("1SA", 3, 13),
    )
    check(
        "Spelled form 'Second Corinthians 5:21' resolves to ('2CO', 5, 21)",
        parse_ref("Second Corinthians 5:21") == ("2CO", 5, 21),
    )
    check(
        "Spelled form 'Third John 1:4' resolves to ('3JN', 1, 4)",
        parse_ref("Third John 1:4") == ("3JN", 1, 4),
    )

    # --- Roman-numeral form ---
    check(
        "Roman form 'I Samuel 3:13' resolves to ('1SA', 3, 13)",
        parse_ref("I Samuel 3:13") == ("1SA", 3, 13),
    )
    check(
        "Roman form 'II Corinthians 5:21' resolves to ('2CO', 5, 21)",
        parse_ref("II Corinthians 5:21") == ("2CO", 5, 21),
    )
    check(
        "Roman form 'III John 1:4' resolves to ('3JN', 1, 4)",
        parse_ref("III John 1:4") == ("3JN", 1, 4),
    )

    # --- Wrong-book boundary tests (mandatory) ---
    result_b1 = parse_ref("1st John 3:16")
    check(
        "Boundary: '1st John' resolves to 1JN, never JHN (Gospel of John)",
        result_b1 is not None and result_b1[0] == "1JN" and result_b1[0] != "JHN",
    )

    result_b2 = parse_ref("First Corinthians 13:4")
    check(
        "Boundary: 'First Corinthians' resolves to 1CO, never 2CO",
        result_b2 is not None and result_b2[0] == "1CO" and result_b2[0] != "2CO",
    )

    result_b3 = parse_ref("II Samuel 5:1")
    check(
        "Boundary: 'II Samuel' resolves to 2SA, never 1SA",
        result_b3 is not None and result_b3[0] == "2SA" and result_b3[0] != "1SA",
    )

    result_b4 = parse_ref("I Genesis 1:1")
    check(
        "Boundary: adversarial 'I Genesis' (numbered prefix on a book that "
        "never takes one) never produces a false match",
        result_b4 is None,
    )

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
