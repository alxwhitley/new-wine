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

Part 3 (added 2026-08-08 build): sub-chunk exclusion regression tests on
real mixed chunks.

Part 4 (added same session): close documented gaps -- inline Müller
quotations without explicit markers, and catechism answer continuation.

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
# ── Part 3: sub-chunk exclusion (2026-08-08 build) ──────────────────────────

print()
print("\nsub-chunk exclusion regression suite (2026-08-08 build)")
print("=" * 60)

# Real chunk IDs for the known mixed chunks flagged in the audit.
LT_CHUNK_54 = "6633550a-694c-4a12-8274-5384c54a6210"  # translator footnote
SOP_CHUNK_228 = "77b7aadb-98a4-4354-a61f-e6ac3d413787"  # Müller block quote at tail
NL_CHUNK_181 = "431a215f-458d-4fa3-b73f-6d6cd6d30fd6"  # Heidelberg Catechism Q&A

lt54_content = db.table("chunks").select("content").eq("id", LT_CHUNK_54).limit(1).execute().data[0]["content"]
sop228_content = db.table("chunks").select("content").eq("id", SOP_CHUNK_228).limit(1).execute().data[0]["content"]
nl181_content = db.table("chunks").select("content").eq("id", NL_CHUNK_181).limit(1).execute().data[0]["content"]

# 14. Translator footnote candidate is refused.
translator_footnote_candidate = "1 The Dutch version has: The cup of thanksgiving which we bless with thanksgiving. -- Translator"
assert translator_footnote_candidate in lt54_content, "fixture error"
result = verify_quote_candidate(db, LT_CHUNK_54, translator_footnote_candidate, MURRAY_SOURCE_ID)
print("\n14. Candidate from a translator footnote:")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 15. Teacher text next to the translator footnote is still allowed.
teacher_after_footnote = "At the Supper, Jesus points us not only backward, but also forward."
assert teacher_after_footnote in lt54_content, "fixture error"
result = verify_quote_candidate(db, LT_CHUNK_54, teacher_after_footnote, MURRAY_SOURCE_ID)
print("\n15. Teacher text after the translator footnote:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# 16. Müller block-quotation candidate is refused.
muller_quote_candidate = "He is the Teacher of His people."
assert muller_quote_candidate in sop228_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_228, muller_quote_candidate, MURRAY_SOURCE_ID)
print("\n16. Candidate from a Müller block quotation:")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 17. Murray framing next to the Müller quote is still allowed.
murray_framing_candidate = (
    "The connection was dissolved in 1830 by\n"
    "mutual consent, and he became the pastor of a small congregation at Teignmouth."
)
assert murray_framing_candidate in sop228_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_228, murray_framing_candidate, MURRAY_SOURCE_ID)
print("\n17. Murray framing before the Müller quotation:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# 18. Heidelberg Catechism Q&A candidate is refused.
catechism_candidate = "What is it to eat the glorified body of Christ and to drink His shed blood?"
assert catechism_candidate in nl181_content, "fixture error"
result = verify_quote_candidate(db, NL_CHUNK_181, catechism_candidate, MURRAY_SOURCE_ID)
print("\n18. Candidate from a Heidelberg Catechism Q&A insert:")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 19. Murray commentary next to the catechism insert is still allowed.
murray_commentary_candidate = (
    "The\nbread is a participation in the body: the cup is a participation in the blood."
)
assert murray_commentary_candidate in nl181_content, "fixture error"
result = verify_quote_candidate(db, NL_CHUNK_181, murray_commentary_candidate, MURRAY_SOURCE_ID)
print("\n19. Murray commentary before the catechism insert:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# ── Part 4: closing the two documented gaps ────────────────────────────────

print()
print("\nsub-chunk exclusion gap-closing suite (2026-08-08 build)")
print("=" * 60)

SOP_CHUNK_231 = "6c1fca7c-528e-40bd-8322-3b0e865e61ee"  # inline Müller, no marker
SOP_CHUNK_233 = "1a604b76-2dc0-4f6b-a330-fa3556eecea4"  # inline Müller, no marker
NL_CHUNK_182 = "51e8bc5c-f95c-426d-9d92-2d9f2c93c1c0"   # catechism answer continuation

sop231_content = db.table("chunks").select("content").eq("id", SOP_CHUNK_231).limit(1).execute().data[0]["content"]
sop233_content = db.table("chunks").select("content").eq("id", SOP_CHUNK_233).limit(1).execute().data[0]["content"]
nl182_content = db.table("chunks").select("content").eq("id", NL_CHUNK_182).limit(1).execute().data[0]["content"]

# 20. Inline Müller quotation in ch231 is refused.
inline_muller_231 = (
    "For it will not do, it is not possible, to live in sin, and at the same time, by\n"
    "communion with God, to draw down from heaven everything one needs for the life that now\n"
    "is."
)
assert inline_muller_231 in sop231_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_231, inline_muller_231, MURRAY_SOURCE_ID)
print("\n20. Inline Müller quotation (School of Prayer ch231):")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 21. Murray's own prose next to that inline quote is still allowed.
murray_next_to_inline_231 = "This mode of living was not easy at first."
assert murray_next_to_inline_231 in sop231_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_231, murray_next_to_inline_231, MURRAY_SOURCE_ID)
print("\n21. Murray prose next to the inline Müller quotation:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# 22. Inline Müller/Scripture quotation in ch233 is refused.
inline_muller_233 = "Thou hast been faithful over few things; I will set thee over many things."
assert inline_muller_233 in sop233_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_233, inline_muller_233, MURRAY_SOURCE_ID)
print("\n22. Inline Müller/Scripture quotation (School of Prayer ch233):")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 23. Murray prose after that inline quote is still allowed.
murray_after_inline_233 = "And these things have happened for an ensample to us."
assert murray_after_inline_233 in sop233_content, "fixture error"
result = verify_quote_candidate(db, SOP_CHUNK_233, murray_after_inline_233, MURRAY_SOURCE_ID)
print("\n23. Murray prose after the inline quotation:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

# 24. Catechism answer continuation in ch182 is refused.
catechism_answer_182 = (
    "It is not only to receive with a believing heart the whole suffering and dying of Christ,\n"
    "and thereby to obtain forgiveness of sins and eternal life"
)
assert catechism_answer_182 in nl182_content, "fixture error"
result = verify_quote_candidate(db, NL_CHUNK_182, catechism_answer_182, MURRAY_SOURCE_ID)
print("\n24. Heidelberg Catechism answer continuation (New Life ch182):")
check("valid == False", result.valid is False)
check("rule == subchunk_exclusion", result.rule == "subchunk_exclusion")

# 25. Murray commentary after the catechism answer is still allowed.
murray_after_catechism_182 = (
    "This deeply inward union with Jesus, even with His body and blood, is the great aim\n"
    "of the Lord’s Supper."
)
assert murray_after_catechism_182 in nl182_content, "fixture error"
result = verify_quote_candidate(db, NL_CHUNK_182, murray_after_catechism_182, MURRAY_SOURCE_ID)
print("\n25. Murray commentary after the catechism answer:")
check("valid == True", result.valid is True)
check("rule == accepted", result.rule == "accepted")

print()
print("=" * 60)
if failures:
    print("%d check(s) FAILED:" % len(failures))
    for f in failures:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks passed.")
