#!/usr/bin/env python3
"""
Unit tests for is_biblical_figure() — no DB required.

Run from project root: python3 scripts/test_biblical_figures.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.biblical_figures import is_biblical_figure

CASES = [
    ("Paul", True),
    ("paul", True),
    ("  PAUL  ", True),
    ("Paul Washer", False),   # distinct full name — must NOT be caught
    ("Moses", True),
    ("John", True),
    ("John Bevere", False),   # distinct full name — must NOT be caught
    ("Derek Prince", False),
    ("Peter", True),
    ("Peter Parker", False),
    ("", False),
    (None, False),
]


def main():
    failures = []
    for name, expected in CASES:
        actual = is_biblical_figure(name)
        status = "OK" if actual == expected else "FAIL"
        print(f"  {status}  is_biblical_figure({name!r}) = {actual} (expected {expected})")
        if actual != expected:
            failures.append((name, expected, actual))

    if failures:
        print(f"\nFAILED — {len(failures)} case(s) wrong")
        sys.exit(1)
    print("\nALL PASSED")


if __name__ == "__main__":
    main()
