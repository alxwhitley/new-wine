#!/usr/bin/env python3
"""
Regression tests for app.services.quote_verifier (Project 3 quote rail).

Part 1 (unchanged): four required cases for verify_quote_exact_match,
built from real live chunk content (sliced programmatically, never
hand-transcribed, so the fixtures are guaranteed byte-exact against what
the verifier itself will read):
  1. a correct quote (exact substring) -> valid
  2. an off-by-one wording error -> invalid
  3. a quote that actually spans two chunks -> invalid (checked against
     either chunk individually, since a candidate assembled from both
     chunks' unique regions cannot be a substring of either chunk alone)
  4. a quote attributed to the wrong document -> invalid

Part 2 (added 2026-08-08, human-approval removal): verify_quote_candidate,
the tightened orchestrating verifier -- boundary proximity, sentence-
completeness, exclusion zone, and speaker confirmation, plus a live
re-check that both quotes already approved in production still pass every
tightened rule (they must, or the tightening would have silently
invalidated real served content).

Run from project root: python3 scripts/test_quote_verifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.db.supabase import get_supabase
from app.services.quote_verifier import verify_quote_exact_match, verify_quote_candidate

db = get_supabase()
failures = []


def check(label, condition, detail=None):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


# Real chunk IDs, Andrew Murray "The New Life", chunk_index 6 and 7 -- both
# genuinely Murray's own Preface text (outside the excluded 0-5 zone).
MURRAY_CHUNK_6 = "00b5623f-12a7-43bb-9bb7-af72d898ec73"
MURRAY_CHUNK_7 = "2ce7de25-1cbf-460e-a04d-405e6f07c1b7"

# A real Derek Prince chunk, a different document entirely.
PRINCE_CHUNK = "71e88d36-b959-4e8d-a500-0839dd3fc6ba"

chunk6_content = db.table("chunks").select("content").eq("id", MURRAY_CHUNK_6).limit(1).execute().data[0]["content"]
chunk7_content = db.table("chunks").select("content").eq("id", MURRAY_CHUNK_7).limit(1).execute().data[0]["content"]
prince_content = db.table("chunks").select("content").eq("id", PRINCE_CHUNK).limit(1).execute().data[0]["content"]

print("\nquote_verifier regression suite")
print("=" * 60)

# ── Case 1: a correct quote ──────────────────────────────────────────────────
correct_quote = "While writing this book I have had a second wish abiding with me."
assert correct_quote in chunk6_content, "fixture error: correct_quote not actually in chunk 6"
result = verify_quote_exact_match(db, MURRAY_CHUNK_6, correct_quote)
print("\n1. Correct quote:")
check("valid == True", result.valid is True)
check("reason is None", result.reason is None)

# ── Case 2: off-by-one wording error ─────────────────────────────────────────
wrong_word_quote = "While writing this book I have had a second thought abiding with me."
assert wrong_word_quote not in chunk6_content, "fixture error: mutated quote unexpectedly present"
result = verify_quote_exact_match(db, MURRAY_CHUNK_6, wrong_word_quote)
print("\n2. Off-by-one wording error ('wish' -> 'thought'):")
check("valid == False", result.valid is False)
check("reason is not None", result.reason is not None)

# ── Case 3: a quote that actually spans two chunks ───────────────────────────
# head_unique_to_6 appears only in chunk 6 (before the overlap zone);
# tail_unique_to_7 appears only in chunk 7 (after the overlap zone). Neither
# substring alone crosses the boundary; concatenating them simulates a
# candidate wrongly assembled across two retrievable units.
head_unique_to_6 = "received every day of our life as a gift from above"
tail_unique_to_7 = "I hope that no one will think it strange."
assert head_unique_to_6 in chunk6_content and head_unique_to_6 not in chunk7_content
assert tail_unique_to_7 in chunk7_content and tail_unique_to_7 not in chunk6_content
spanning_quote = head_unique_to_6 + " " + tail_unique_to_7
print("\n3. Quote spanning two chunks:")
result_vs_6 = verify_quote_exact_match(db, MURRAY_CHUNK_6, spanning_quote)
check("invalid when checked against chunk 6", result_vs_6.valid is False)
result_vs_7 = verify_quote_exact_match(db, MURRAY_CHUNK_7, spanning_quote)
check("invalid when checked against chunk 7", result_vs_7.valid is False)

# ── Case 4: a quote attributed to the wrong document ─────────────────────────
# A genuine exact substring of the Prince chunk, checked against the Murray
# chunk instead -- must be rejected as a wrong-document attribution.
prince_quote = prince_content[40:110].strip()
assert prince_quote in prince_content, "fixture error"
assert prince_quote not in chunk6_content, "fixture error: unexpectedly present in Murray chunk"
result = verify_quote_exact_match(db, MURRAY_CHUNK_6, prince_quote)
print("\n4. Quote attributed to the wrong document (real Prince text, checked against a Murray chunk):")
check("valid == False", result.valid is False)

# Sanity: the same Prince quote against its OWN chunk must pass, confirming
# case 4's failure is genuinely about mismatched attribution, not a broken fixture.
result_correct_doc = verify_quote_exact_match(db, PRINCE_CHUNK, prince_quote)
check("valid == True against its real source chunk", result_correct_doc.valid is True)


# ── Part 2: verify_quote_candidate (tightened orchestrator) ─────────────────

print()
print("\nverify_quote_candidate regression suite (2026-08-08 tightening)")
print("=" * 60)

MURRAY_SOURCE_ID = "d26f77e7-6ce0-4311-991b-03d9900a6045"
PRINCE_SOURCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"

# 5. Candidate flush against the chunk's own start (position 0) -> refused,
#    boundary_proximity -- cannot verify it isn't a continuation of whatever
#    the previous chunk ended with.
start0_candidate = chunk6_content[:18]
assert chunk6_content.find(start0_candidate) == 0, "fixture error: expected start index 0"
result = verify_quote_candidate(db, MURRAY_CHUNK_6, start0_candidate, MURRAY_SOURCE_ID)
print("\n5. Candidate starts at chunk position 0:")
check("valid == False", result.valid is False)
check("rule == boundary_proximity", result.rule == "boundary_proximity")

# 6. Candidate flush against the chunk's own end -> refused, boundary_proximity.
endflush_candidate = chunk6_content[-25:]
assert chunk6_content.find(endflush_candidate) + len(endflush_candidate) == len(chunk6_content)
result = verify_quote_candidate(db, MURRAY_CHUNK_6, endflush_candidate, MURRAY_SOURCE_ID)
print("\n6. Candidate ends at the chunk's own end:")
check("valid == False", result.valid is False)
check("rule == boundary_proximity", result.rule == "boundary_proximity")

# 7. Interior candidate, but the text immediately preceding it does not end
#    on sentence-terminal punctuation ("...must the young" -> not a fresh
#    sentence) -> refused, boundary_proximity. The candidate's OWN ending
#    ("...power and truth.") is clean, isolating this as the preceding-text
#    failure specifically, not a fixture error.
preceding_not_terminal_candidate = (
    "Christian make acquaintance, as the Person through whom the word and Jesus, "
    "with all His\nwork, and faith in Him, can become power and truth."
)
assert preceding_not_terminal_candidate in chunk6_content, "fixture error"
result = verify_quote_candidate(db, MURRAY_CHUNK_6, preceding_not_terminal_candidate, MURRAY_SOURCE_ID)
print("\n7. Candidate does not open on a clean sentence boundary:")
check("valid == False", result.valid is False)
check("rule == boundary_proximity", result.rule == "boundary_proximity")

# 8. Interior candidate preceded by clean terminal punctuation, but the
#    candidate's OWN text does not end on terminal punctuation -> refused,
#    boundary_proximity.
candidate_not_terminal_candidate = "With the Holy Spiritalso must the young"
assert candidate_not_terminal_candidate in chunk6_content, "fixture error"
result = verify_quote_candidate(db, MURRAY_CHUNK_6, candidate_not_terminal_candidate, MURRAY_SOURCE_ID)
print("\n8. Candidate does not close on a clean sentence boundary:")
check("valid == False", result.valid is False)
check("rule == boundary_proximity", result.rule == "boundary_proximity")

# 9. Exclusion zone -- any exact-substring candidate from a chunk flagged
#    quote_ineligible_reason must be refused regardless of how clean its
#    boundaries look. Real seeded chunk (migration 082): CCEL editorial
#    description on "The New Life", chunk_index 0.
EXCLUDED_CHUNK = "722b3730-e047-4f4d-b380-c752f95bac42"
excluded_content = db.table("chunks").select("content").eq("id", EXCLUDED_CHUNK).limit(1).execute().data[0]["content"]
excluded_candidate = excluded_content[:40]
result = verify_quote_candidate(db, EXCLUDED_CHUNK, excluded_candidate, MURRAY_SOURCE_ID)
print("\n9. Candidate from a known exclusion-zone chunk:")
check("valid == False", result.valid is False)
check("rule == exclusion_zone", result.rule == "exclusion_zone")

# 10. Speaker confirmation -- a real, cleanly-bounded, exact-substring
#     candidate from Murray's document, attributed to Prince instead ->
#     refused. A strong content match is not confirmation; only the
#     document's own source_id counts.
clean_candidate = (
    "It was often very unwillingly that I took leave of\nthe young converts who had "
    "to go back to lonely places, where they could have little counsel\nor help, "
    "and seldom mingle in the preaching of the word."
)
assert clean_candidate in chunk6_content, "fixture error"
result = verify_quote_candidate(db, MURRAY_CHUNK_6, clean_candidate, PRINCE_SOURCE_ID)
print("\n10. Correctly-bounded candidate attributed to the wrong teacher:")
check("valid == False", result.valid is False)
check("rule == speaker_unconfirmed", result.rule == "speaker_unconfirmed")

# 11. The same candidate, correctly attributed to Murray -> accepted. Proves
#     case 10's failure was genuinely about attribution, not the boundary
#     rule silently rejecting a good fixture.
result = verify_quote_candidate(db, MURRAY_CHUNK_6, clean_candidate, MURRAY_SOURCE_ID)
print("\n11. Same candidate, correctly attributed:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# 12/13. Live re-check: both quotes already approved in production must
#    still pass the full tightened verifier end to end -- the tightening
#    must not silently invalidate real served content.
print("\n12/13. Live re-check of the two currently-approved production quotes:")
murray_waiting_result = verify_quote_candidate(
    db,
    "ef3c7593-7d39-4633-b198-7623942f05eb",
    "Oh for the eyes of our heart to be opened to see God working in ourselves and in others,\n"
    "and to see how blessed it is to worship and just to wait for His salvation!",
    MURRAY_SOURCE_ID,
)
check("Murray 'waiting on God' (approved, live) still passes", murray_waiting_result.valid is True,
      murray_waiting_result.reason)
prince_fasting_result = verify_quote_candidate(
    db,
    "6e31038e-257b-4666-9fa3-a2719017d1f6",
    "Apparently, fasting, even for Jesus, was necessary for him to get the victory over the devil.",
    PRINCE_SOURCE_ID,
)
check("Prince 'fasting' (approved, live) still passes", prince_fasting_result.valid is True,
      prince_fasting_result.reason)

print()
print("=" * 60)
if failures:
    print("%d check(s) FAILED:" % len(failures))
    for f in failures:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks passed.")
