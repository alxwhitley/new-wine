#!/usr/bin/env python3
"""Generate frontend/lib/generated/book-maps.ts from the single canonical
source, backend/app/constants.py's BOOK_MAP and ABBREV_TO_NAME.

Closes the CLAUDE.md Landmines item "The book-name map exists as five
independent hand-maintained copies" for the three copies that were
byte-for-byte identical to constants.py (frontend/app/study/page.tsx's own
BOOK_MAP/ABBREV_TO_NAME, and frontend/app/library/page.tsx's
VERSE_BOOK_NAMES — confirmed identical by direct comparison before this
script was written, not assumed). Those three files now import the
generated output below instead of hand-typing their own copy.

frontend/lib/study-reference.ts is NOT fully generated from this file — it
deliberately recognizes a narrower, hand-curated set of forms (its own
"deliberately conservative" fail-quiet design, scanning free-form generated
prose rather than an isolated search-box string) plus historically
load-bearing ordinal-literal forms ("1st Samuel") that constants.py does
not carry as map keys at all. Only its (code, full name) identity pairs are
sourced from this generated file; its curated abbrevs list stays
hand-maintained in that file, on purpose. See that file's own comment.

Run directly to (re)write the generated file:
    python3.12 scripts/generate_book_maps_ts.py

Run with --check to verify the committed file is not stale (drift gate;
exits 1 and prints a diff-free notice if the committed file would change):
    python3.12 scripts/generate_book_maps_ts.py --check
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSTANTS_PATH = REPO_ROOT / "backend" / "app" / "constants.py"
OUTPUT_PATH = REPO_ROOT / "frontend" / "lib" / "generated" / "book-maps.ts"

HEADER = """\
// GENERATED FILE — DO NOT EDIT BY HAND.
//
// Source of truth: backend/app/constants.py's BOOK_MAP and ABBREV_TO_NAME.
// Regenerate with: python3.12 scripts/generate_book_maps_ts.py
// Verify no drift with: python3.12 scripts/generate_book_maps_ts.py --check
//
// Every consumer that needs the canonical book-name-form -> 3-letter-code
// map, or its reverse, imports from this file instead of hand-typing its
// own copy. See CLAUDE.md Landmines, "The book-name map exists as five
// independent hand-maintained copies."
"""


def _load_constants():
    spec = importlib.util.spec_from_file_location("rhemata_constants", CONSTANTS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render_dict(name: str, data: dict) -> str:
    lines = [f"export const {name}: Record<string, string> = {{"]
    for key, value in data.items():
        lines.append(f'  {_ts_key(key)}: "{value}",')
    lines.append("};")
    return "\n".join(lines)


def _ts_key(key: str) -> str:
    """Match the quoting style already used by hand in the files this
    replaces: a bare identifier-safe key is unquoted, anything else
    (spaces, a leading digit) is quoted."""
    if key.isidentifier() and not key[0].isdigit():
        return key
    return f'"{key}"'


def render(constants_module) -> str:
    book_map = _render_dict("BOOK_MAP", constants_module.BOOK_MAP)
    abbrev_to_name = _render_dict("ABBREV_TO_NAME", constants_module.ABBREV_TO_NAME)
    return HEADER + "\n" + book_map + "\n\n" + abbrev_to_name + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the committed file would differ from a fresh render, without writing.",
    )
    args = parser.parse_args()

    constants_module = _load_constants()
    rendered = render(constants_module)

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"DRIFT: {OUTPUT_PATH} does not exist — run without --check to generate it.")
            return 1
        current = OUTPUT_PATH.read_text()
        if current != rendered:
            print(f"DRIFT: {OUTPUT_PATH} is stale relative to {CONSTANTS_PATH}.")
            print("Run: python3.12 scripts/generate_book_maps_ts.py")
            return 1
        print(f"OK: {OUTPUT_PATH} matches the canonical source.")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered)
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
