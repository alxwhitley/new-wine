#!/usr/bin/env python3
"""
Regression coverage for the 2026-08-18 book-name ordinal-normalization
consolidation: app.routers.study.parse_ref and app.services.reference_
verifier._parse_verse_or_range each used to hand-maintain an identical
copy of the "strip ordinal suffix, normalize spacing, look up BOOK_MAP
with a trailing-s fallback" sequence -- confirmed byte-identical before
this fix. Both now call the single shared app.constants.resolve_book_
abbrev() instead.

Part 1: both consumers resolve every recognized form identically.
Part 2: structural proof that neither consumer still hand-types the
ordinal-strip regex -- the actual thing that drifted silently before
(reference_verifier.py's own docstring said "kept independently in sync
... a future edit to one must be mirrored here").

Run from project root:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/test_resolve_book_abbrev_consolidation.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

from app.constants import resolve_book_abbrev
from app.routers.study import parse_ref
from app.services.reference_verifier import _parse_verse_or_range

failures = []


def check(label, condition, detail=None):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


FORMS = [
    ("1 Samuel 3:13", "1SA"),
    ("1st Samuel 3:13", "1SA"),
    ("First Samuel 3:13", "1SA"),
    ("I Samuel 3:13", "1SA"),
    ("2nd Corinthians 5:21", "2CO"),
    ("Second Corinthians 5:21", "2CO"),
    ("II Corinthians 5:21", "2CO"),
    ("3rd John 1:4", "3JN"),
    ("Third John 1:4", "3JN"),
    ("III John 1:4", "3JN"),
    ("John 3:16", "JHN"),
    ("Psalms 23:1", "PSA"),
]

ORDINAL_STRIP_PATTERN = r"re\.sub\(r'\^\(\\d\)\(\?:st\|nd\|rd\|th\)\\b'"


def test_both_consumers_resolve_every_form_identically():
    for ref, expected in FORMS:
        study_result = parse_ref(ref)
        verifier_result = _parse_verse_or_range(ref)
        check(
            "study.parse_ref(%r) resolves to %s" % (ref, expected),
            study_result is not None and study_result[0] == expected,
            detail=repr(study_result),
        )
        check(
            "reference_verifier._parse_verse_or_range(%r) resolves to %s" % (ref, expected),
            verifier_result is not None and verifier_result[0] == expected,
            detail=repr(verifier_result),
        )
        check(
            "both consumers agree on %r" % ref,
            study_result is not None and verifier_result is not None
            and study_result[0] == verifier_result[0],
            detail="study=%r verifier=%r" % (study_result, verifier_result),
        )


def test_no_consumer_still_hand_types_the_ordinal_strip():
    """The actual regression this consolidation guards against: a future
    edit landing in only one of the two files, silently drifting the two
    apart again, the way reference_verifier.py's own retired comment
    ("kept independently in sync... must be mirrored here") describes."""
    study_src = (ROOT / "backend" / "app" / "routers" / "study.py").read_text()
    verifier_src = (ROOT / "backend" / "app" / "services" / "reference_verifier.py").read_text()
    constants_src = (ROOT / "backend" / "app" / "constants.py").read_text()

    check(
        "constants.py defines the ordinal-strip pattern exactly once (the shared implementation)",
        len(re.findall(ORDINAL_STRIP_PATTERN, constants_src)) == 1,
        detail="found %d occurrences" % len(re.findall(ORDINAL_STRIP_PATTERN, constants_src)),
    )
    check(
        "study.py no longer hand-types the ordinal-strip regex",
        not re.search(ORDINAL_STRIP_PATTERN, study_src),
    )
    check(
        "reference_verifier.py no longer hand-types the ordinal-strip regex",
        not re.search(ORDINAL_STRIP_PATTERN, verifier_src),
    )
    check(
        "study.py calls the shared resolve_book_abbrev()",
        "resolve_book_abbrev(" in study_src,
    )
    check(
        "reference_verifier.py calls the shared resolve_book_abbrev()",
        "resolve_book_abbrev(" in verifier_src,
    )


def main():
    print("resolve_book_abbrev consolidation regression suite")
    print("=" * 60)
    test_both_consumers_resolve_every_form_identically()
    test_no_consumer_still_hand_types_the_ordinal_strip()
    print("=" * 60)
    if failures:
        print("FAILED: %d check(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
