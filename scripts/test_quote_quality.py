#!/usr/bin/env python3
"""Unit tests for app.services.quote_quality (deterministic serveability gate).

Run from project root: python3 scripts/test_quote_quality.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.quote_quality import assess_quote_quality

failures = []


def check(label: str, cond: bool, detail: str | None = None) -> None:
    print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
    if not cond:
        failures.append(label)
        if detail:
            print("         %s" % detail)


def main() -> int:
    print("\nquote_quality deterministic rubric")
    print("=" * 60)

    strong = (
        "We’re all going to answer to God personally for the lives we’ve led. "
        "I think it’s important to bear that in mind. The scripture says that "
        "the doctrine of eternal judgment is one of the six basic doctrines of "
        "the Christian faith."
    )
    v = assess_quote_quality(strong)
    print("\n1. Strong standalone claim:")
    check("ok", v.ok is True, v.reason)
    check("rule == accepted", v.rule == "accepted")

    weak_deixis = "Verse 17, this is a wonderful verse."
    v = assess_quote_quality(weak_deixis)
    print("\n2. Deictic verse pointer (quality sample class):")
    check("ok == False", v.ok is False)
    check("rule == deixis_opener", v.rule == "deixis_opener")

    multi = (
        "When you get to the point of hanging everything on a precise form of words, "
        "you are no longer moving in the liberty of the Holy Spirit.\n\n"
        "We come to the seventh unity, one God and Father."
    )
    v = assess_quote_quality(multi)
    print("\n3. Multi-paragraph / section swallow:")
    check("ok == False", v.ok is False)
    check("rule == internal_paragraph_break", v.rule == "internal_paragraph_break")

    v = assess_quote_quality("Too short.")
    print("\n4. Too short:")
    check("ok == False", v.ok is False)
    check("rule == length_band", v.rule == "length_band")

    v = assess_quote_quality(strong, standalone_ok=False)
    print("\n5. Propose marked standalone_ok=False:")
    check("ok == False", v.ok is False)
    check("rule == not_standalone", v.rule == "not_standalone")

    connective = (
        "Now I am not seeking to make a big issue out of that. On the other hand, "
        "I think it is very important as we try to discern the nature and the "
        "ministry of the Holy Spirit."
    )
    v = assess_quote_quality(connective)
    print("\n6. Mid-argument connective (weak sample class):")
    check("ok == False", v.ok is False)
    check("rule == connective_prose", v.rule == "connective_prose")

    print()
    if failures:
        print("%d check(s) failed" % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
