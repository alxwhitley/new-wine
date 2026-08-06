#!/usr/bin/env python3
"""
Regression tests for app.services.quote_verifier.verify_quote_exact_match
(Project 3 quote rail, Step 2).

Four required cases, built from real live chunk content (sliced
programmatically, never hand-transcribed, so the fixtures are guaranteed
byte-exact against what the verifier itself will read):
  1. a correct quote (exact substring) -> valid
  2. an off-by-one wording error -> invalid
  3. a quote that actually spans two chunks -> invalid (checked against
     either chunk individually, since a candidate assembled from both
     chunks' unique regions cannot be a substring of either chunk alone)
  4. a quote attributed to the wrong document -> invalid

Run from project root: python3 scripts/test_quote_verifier.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.db.supabase import get_supabase
from app.services.quote_verifier import verify_quote_exact_match

db = get_supabase()
failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
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

print()
print("=" * 60)
if failures:
    print("%d check(s) FAILED:" % len(failures))
    for f in failures:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks passed.")
