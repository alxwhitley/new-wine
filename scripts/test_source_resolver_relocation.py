#!/usr/bin/env python3
"""
Proves backend/app/services/source_resolver.py's normalize_alias_key() is
byte-identical to the original scripts/source_resolver.py version, across
every live alias_key plus synthetic edge cases. Run BEFORE Task 3 repoints
scripts/source_resolver.py at the relocated function — this is the evidence
that repointing is safe, not an assumption.

Run from project root: python3 scripts/test_source_resolver_relocation.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client

from source_resolver import normalize_alias_key as old_normalize
from app.services.source_resolver import normalize_alias_key as new_normalize

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

EDGE_CASES = [
    None,
    "",
    "   ",
    "Derek Prince",
    "  Derek   Prince  ",
    "DEREK PRINCE",
    "John\tBevere",
    "John\n\nBevere",
    "1 Corinthians",
    "F.F. Bosworth",
    "An Unknown Christian",
]


def main():
    db = create_client(SB_URL, SB_SVC)

    mismatches = []

    print("Checking synthetic edge cases...")
    for s in EDGE_CASES:
        old_result = old_normalize(s)
        new_result = new_normalize(s)
        status = "OK" if old_result == new_result else "MISMATCH"
        print(f"  {status}  {s!r:30} -> old={old_result!r} new={new_result!r}")
        if old_result != new_result:
            mismatches.append((s, old_result, new_result))

    print("\nChecking every live alias_key...")
    result = db.table("source_aliases").select("alias_key").execute()
    rows = result.data or []
    for row in rows:
        key = row["alias_key"]
        old_result = old_normalize(key)
        new_result = new_normalize(key)
        if old_result != new_result:
            mismatches.append((key, old_result, new_result))

    print(f"Checked {len(rows)} live alias_key rows + {len(EDGE_CASES)} edge cases.")

    if mismatches:
        print(f"\nFAILED — {len(mismatches)} mismatch(es):")
        for s, old_result, new_result in mismatches:
            print(f"  input={s!r} old={old_result!r} new={new_result!r}")
        sys.exit(1)

    print("\nPASSED — relocated normalize_alias_key is byte-identical to the original "
          "on every live alias_key and every synthetic edge case.")


if __name__ == "__main__":
    main()
