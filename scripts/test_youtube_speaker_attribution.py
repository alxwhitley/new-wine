#!/usr/bin/env python3.12
"""
test_youtube_speaker_attribution.py — regression test for the speaker →
documents.author guard in youtube_ingest.py (built 2026-08-31).

Why this exists: `_extract_speaker()` matches any run of two-or-more
Title-Case words after a '|' or '-'. YouTube titles produce those constantly,
so title fragments reached `documents.author` as CITABLE rows — five of them
under the Vlad Savchuk source ("Do This Instead", "Your Porn Battle Plan",
"Watch Message", "Day Abortion", "This Is How You Should Fight Your
Battles"). A citable author enters the permitted-name set that
reference_verifier builds, i.e. the set of names the answer writer is told it
may attribute claims to.

The signal that would have prevented it was already being computed and then
discarded: when the extracted string fails alias lookup, resolution falls back
to the channel name and records that in `via` — but the speaker was written as
author regardless.

Locked-in property: a title-extracted speaker becomes documents.author ONLY
when that string itself matched a source alias.

Fully offline: no network, no database, no LLM calls, no cost.

Usage:
    python3.12 scripts/test_youtube_speaker_attribution.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_ingest as yi  # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print("  OK: {}".format(label))
    else:
        print("  FAIL: {}{}".format(label, "  -- " + detail if detail else ""))
        FAILURES.append(label)


# The five strings actually found live as citable authors (audit 2026-08-31).
REAL_DEFECTS = [
    "Do This Instead",
    "Your Porn Battle Plan",
    "Watch Message",
    "Day Abortion",
    "This Is How You Should Fight Your Battles",
]

# Every `via` value the resolution chain can produce.
VERIFIED_VIA = ["title_speaker", "author"]
UNVERIFIED_VIA = ["channel_name", "source_name", "MISS"]


def test_verified_paths_keep_the_speaker():
    print("\n1. A speaker that matched an alias is KEPT")
    for via in VERIFIED_VIA:
        got = yi._verified_speaker("Derek Prince", via)
        check("via={!r} keeps a resolved name".format(via),
              got == "Derek Prince",
              "got {!r}".format(got))


def test_unverified_paths_drop_the_speaker():
    print("\n2. A speaker that did NOT match an alias is DROPPED")
    for via in UNVERIFIED_VIA:
        got = yi._verified_speaker("Derek Prince", via)
        check("via={!r} drops even a real-looking name".format(via),
              got == "",
              "got {!r}".format(got))


def test_real_defects_are_dropped():
    print("\n3. The five live defect strings are dropped on channel fallback")
    for junk in REAL_DEFECTS:
        got = yi._verified_speaker(junk, "channel_name")
        check("{!r} does not become an author".format(junk[:34]),
              got == "",
              "got {!r}".format(got))


def test_empty_extraction_stays_empty():
    print("\n4. No extraction stays empty on every path")
    for via in VERIFIED_VIA + UNVERIFIED_VIA:
        check("via={!r} with no speaker -> ''".format(via),
              yi._verified_speaker("", via) == "")


def test_extractor_really_does_produce_junk():
    print("\n5. Root cause: the extractor cannot tell a fragment from a name")
    # If these ever stop matching, the guard is still correct but this test's
    # premise has changed -- so assert the premise explicitly.
    title = "3 Signs of a Porn Addiction | Your Porn Battle Plan"
    extracted = yi._extract_speaker(title)
    check("extractor returns a title fragment as a 'speaker'",
          extracted != "",
          "extracted {!r} from {!r}".format(extracted, title))
    check("and the guard refuses it under channel fallback",
          yi._verified_speaker(extracted, "channel_name") == "")


def test_mutation_the_guard_is_load_bearing():
    print("\n6. Mutation proof: the guard is what does the work")
    original = yi._SPEAKER_VERIFIED_VIA
    try:
        # Simulate the pre-fix behavior: trust every resolution path.
        yi._SPEAKER_VERIFIED_VIA = frozenset(VERIFIED_VIA + UNVERIFIED_VIA)
        leaked = yi._verified_speaker("Your Porn Battle Plan", "channel_name")
        check("widening _SPEAKER_VERIFIED_VIA reintroduces the defect",
              leaked == "Your Porn Battle Plan",
              "got {!r} -- if this is '' the guard is not the mechanism".format(leaked))
    finally:
        yi._SPEAKER_VERIFIED_VIA = original

    check("guard restored after mutation",
          yi._verified_speaker("Your Porn Battle Plan", "channel_name") == "")
    check("channel_name is not a trusted path",
          "channel_name" not in yi._SPEAKER_VERIFIED_VIA)


def main():
    print("=" * 68)
    print("speaker -> documents.author attribution guard")
    print("=" * 68)

    test_verified_paths_keep_the_speaker()
    test_unverified_paths_drop_the_speaker()
    test_real_defects_are_dropped()
    test_empty_extraction_stays_empty()
    test_extractor_really_does_produce_junk()
    test_mutation_the_guard_is_load_bearing()

    print("\n" + "=" * 68)
    if FAILURES:
        print("FAILED: {} check(s)".format(len(FAILURES)))
        for f in FAILURES:
            print("  - {}".format(f))
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
