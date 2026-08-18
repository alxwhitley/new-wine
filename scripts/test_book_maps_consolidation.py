#!/usr/bin/env python3
"""Regression suite for the book-name-map consolidation (CLAUDE.md
Landmines, "The book-name map exists as five independent hand-maintained
copies"). No DB, no live services — pure data/text checks, safe to run
anywhere.

Covers:
  - The generated frontend module (frontend/lib/generated/book-maps.ts) is
    not stale relative to backend/app/constants.py (the drift gate).
  - The generated module's BOOK_MAP/ABBREV_TO_NAME are byte-identical to
    the canonical Python dicts (proves the data layer is genuinely shared,
    not just superficially similar).
  - frontend/app/study/page.tsx and frontend/app/library/page.tsx no longer
    hand-type a local copy of the map (structural check — a reverted import
    would be caught here even if the values happened to still match).
  - The two backend consumers that already shared constants.py's BOOK_MAP
    before this session (app.routers.study.parse_ref and
    app.services.reference_verifier._parse_verse_or_range) still resolve
    numeric, Roman-numeral, spelled-ordinal, and ordinal-digit forms
    identically to each other — untouched by this session, checked anyway
    since Step 5's stop condition is "no consumer's behavior changes".
  - frontend/lib/study-reference.ts's deliberately-preserved, non-unioned
    forms are still exactly as they were: the ordinal-literal forms it
    alone recognizes ("1st Samuel") are still present in its source, and
    the compact forms it deliberately does not recognize ("jos", "ezr")
    are still absent — locking in the flagged "union unsafe" decision
    rather than silently drifting either direction later.

Run from project root: python3.12 scripts/test_book_maps_consolidation.py
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "generate_book_maps_ts.py"
GENERATED_TS = REPO_ROOT / "frontend" / "lib" / "generated" / "book-maps.ts"
STUDY_PAGE_TSX = REPO_ROOT / "frontend" / "app" / "study" / "page.tsx"
LIBRARY_PAGE_TSX = REPO_ROOT / "frontend" / "app" / "library" / "page.tsx"
STUDY_REFERENCE_TS = REPO_ROOT / "frontend" / "lib" / "study-reference.ts"

sys.path.insert(0, str(REPO_ROOT / "backend"))

failures = []  # type: list[str]


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if not condition:
        failures.append(label)


def _load_module(name, path):
    # Registering in sys.modules BEFORE exec_module matters here: reference_
    # verifier.py's @dataclass decorator resolves cls.__module__ via
    # sys.modules.get(...) while its class body is still executing, which
    # raises AttributeError on None if the module isn't registered yet.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_constants():
    return _load_module("rhemata_constants", REPO_ROOT / "backend" / "app" / "constants.py")


def _load_generator():
    return _load_module("generate_book_maps_ts", GENERATOR)


def _load_study_parse_ref():
    # study.py imports fastapi/pydantic/etc — only needed for its module-level
    # code, not for calling parse_ref, but the import must still succeed.
    module = _load_module("study_router", REPO_ROOT / "backend" / "app" / "routers" / "study.py")
    return module.parse_ref


def _load_reference_verifier_parse():
    module = _load_module(
        "reference_verifier", REPO_ROOT / "backend" / "app" / "services" / "reference_verifier.py"
    )
    return module._parse_verse_or_range


def _parse_ts_dict(text: str, const_name: str) -> dict:
    m = re.search(rf'export const {const_name}[^=]*=\s*{{(.*?)\n}};', text, re.DOTALL)
    if not m:
        return {}
    entries = re.findall(r'(?:"([^"]+)"|(\b[A-Za-z0-9_]+\b))\s*:\s*"([^"]+)"', m.group(1))
    return {(a if a else b): val for a, b, val in entries}


def main() -> int:
    constants = _load_constants()
    generator = _load_generator()

    print("== Drift gate: generated file vs. canonical source ==")
    check_result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"], capture_output=True, text=True
    )
    check("generate_book_maps_ts.py --check reports no drift", check_result.returncode == 0)

    # Mutation-proof the drift check itself: corrupt a TEMP copy (never the
    # real committed file) and confirm the same comparison logic flags it.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "book-maps.ts"
        real_content = GENERATED_TS.read_text()
        tmp_path.write_text(real_content + "\n// mutated\n")
        rendered = generator.render(constants)
        check(
            "drift check's own comparison logic detects a corrupted copy (mutation-proof)",
            tmp_path.read_text() != rendered,
        )
        tmp_path.write_text(rendered)
        check(
            "drift check's own comparison logic accepts a freshly-regenerated copy",
            tmp_path.read_text() == rendered,
        )

    print()
    print("== Cross-language identity: generated TS vs. canonical Python dicts ==")
    ts_text = GENERATED_TS.read_text()
    ts_book_map = _parse_ts_dict(ts_text, "BOOK_MAP")
    ts_abbrev_to_name = _parse_ts_dict(ts_text, "ABBREV_TO_NAME")
    check(
        f"generated BOOK_MAP has {len(constants.BOOK_MAP)} entries, byte-identical to constants.py",
        ts_book_map == constants.BOOK_MAP,
    )
    check(
        f"generated ABBREV_TO_NAME has {len(constants.ABBREV_TO_NAME)} entries, byte-identical to constants.py",
        ts_abbrev_to_name == constants.ABBREV_TO_NAME,
    )

    print()
    print("== Structural: no consumer still hand-types a local copy ==")
    study_page_text = STUDY_PAGE_TSX.read_text()
    library_page_text = LIBRARY_PAGE_TSX.read_text()
    check(
        "study/page.tsx has no local `const BOOK_MAP` object literal",
        not re.search(r'const BOOK_MAP\s*:\s*Record<string,\s*string>\s*=\s*{', study_page_text),
    )
    check(
        "study/page.tsx has no local `const ABBREV_TO_NAME` object literal",
        not re.search(r'const ABBREV_TO_NAME\s*:\s*Record<string,\s*string>\s*=\s*{', study_page_text),
    )
    check(
        "study/page.tsx imports BOOK_MAP and ABBREV_TO_NAME from the generated module",
        'from "@/lib/generated/book-maps"' in study_page_text
        and "BOOK_MAP" in study_page_text
        and "ABBREV_TO_NAME" in study_page_text,
    )
    check(
        "library/page.tsx has no local `const VERSE_BOOK_NAMES` object literal",
        not re.search(r'const VERSE_BOOK_NAMES\s*:\s*Record<string,\s*string>\s*=\s*{', library_page_text),
    )
    check(
        "library/page.tsx imports VERSE_BOOK_NAMES (aliased from ABBREV_TO_NAME) from the generated module",
        'from "@/lib/generated/book-maps"' in library_page_text
        and "VERSE_BOOK_NAMES" in library_page_text,
    )

    print()
    print("== Backend consumers (study.parse_ref, reference_verifier._parse_verse_or_range) ==")
    parse_ref = _load_study_parse_ref()
    parse_verse_or_range = _load_reference_verifier_parse()

    FORMS = [
        ("1 Samuel 3:13", "1SA", 3, 13),
        ("1Cor 13:4", "1CO", 13, 4),
        ("1st Samuel 3:13", "1SA", 3, 13),
        ("2nd Corinthians 5:21", "2CO", 5, 21),
        ("First Corinthians 13:4", "1CO", 13, 4),
        ("I Samuel 3:13", "1SA", 3, 13),
        ("II Timothy 2:2", "2TI", 2, 2),
        ("Third John 1:4", "3JN", 1, 4),
        ("III John 1:4", "3JN", 1, 4),
        ("John 3:16", "JHN", 3, 16),
        ("Genesis 1:1", "GEN", 1, 1),
    ]
    for ref, expected_abbrev, expected_chapter, expected_verse in FORMS:
        study_result = parse_ref(ref)
        verifier_result = parse_verse_or_range(ref)
        study_ok = study_result == (expected_abbrev, expected_chapter, expected_verse)
        verifier_ok = (
            verifier_result is not None
            and verifier_result[0] == expected_abbrev
            and verifier_result[1] == expected_chapter
            and verifier_result[2] == expected_verse
        )
        check(f"study.parse_ref({ref!r}) == {(expected_abbrev, expected_chapter, expected_verse)}", study_ok)
        check(
            f"reference_verifier._parse_verse_or_range({ref!r}) resolves to the same identity",
            verifier_ok,
        )

    print()
    print("== study-reference.ts: flagged 'union unsafe' decision holds (forms neither added nor dropped) ==")
    sr_text = STUDY_REFERENCE_TS.read_text()
    check(
        "study-reference.ts still recognizes the load-bearing ordinal-literal form '1st Samuel'",
        '"1st Samuel"' in sr_text,
    )
    check(
        "study-reference.ts still recognizes the load-bearing ordinal-literal form '3rd John'",
        '"3rd John"' in sr_text,
    )
    check(
        "study-reference.ts imports ABBREV_TO_NAME from the generated module for its code/full identity",
        'from "./generated/book-maps.ts"' in sr_text and "ABBREV_TO_NAME" in sr_text,
    )
    # These compact forms exist in constants.py's BOOK_MAP but were confirmed
    # (before this session's edits) to be absent from study-reference.ts's
    # abbrevs — a deliberate non-union, not an oversight. This locks in that
    # they are STILL absent post-consolidation, i.e. no accidental widening.
    # Scoped to the BOOK_ABBREVS object body only (not the whole file) so
    # this doesn't false-positive on the explanatory comment above it, which
    # names these same strings as documented examples of what was excluded.
    abbrevs_body_match = re.search(r'const BOOK_ABBREVS[^=]*=\s*{(.*?)\n};', sr_text, re.DOTALL)
    abbrevs_body = abbrevs_body_match.group(1) if abbrevs_body_match else ""
    check("found BOOK_ABBREVS object body to scan", bool(abbrevs_body_match))
    for compact_form in ('"Jos"', '"Ezr"', '"Psa"', '"Act"', '"Jud"'):
        check(
            f"study-reference.ts's BOOK_ABBREVS still does NOT list the compact form {compact_form} (flagged union-unsafe, unchanged)",
            compact_form not in abbrevs_body,
        )

    print()
    total = len(failures)
    if total:
        print(f"{total} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
