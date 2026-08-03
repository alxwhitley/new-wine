#!/usr/bin/env python3
"""Deterministic proof of the JSON-escaping-defect fix (2026-08-02) in
propositions._repair_unescaped_quotes. Each case below is a faithful reproduction
of a REAL failing Groq output captured this session from the 3 failing sermons
(Prince "Mary: The Pattern Mother", Prince "Seven Ways To Keep Your Deliverance",
Savchuk "God Decides When") -- the model wrote a nested scripture/phrase quotation
inside a `content` value with the inner quotes unescaped, breaking json.loads with
"Expecting ',' delimiter".

For each: (1) the raw fails bare json.loads (proving the defect is real), and
(2) after the repair it parses to the correct number of propositions with the
inner quotation preserved verbatim in the content. Well-formed and already-escaped
outputs must pass through unchanged. No network, no DB, no cost.

Run: python3 scripts/test_proposition_json_repair.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propositions

failures = []
def check(label, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(label)

def _fails_raw(raw):
    try:
        json.loads(raw)
        return False
    except json.JSONDecodeError:
        return True

def _repairs_to(raw, n_expected, must_contain):
    parsed = json.loads(propositions._repair_unescaped_quotes(raw))
    ok = isinstance(parsed, list) and len(parsed) == n_expected
    ok = ok and all(isinstance(p.get("content"), str) and p.get("content") for p in parsed)
    ok = ok and all(sub in " ".join(p["content"] for p in parsed) for sub in must_contain)
    return ok, parsed

# ── Case A — Savchuk: scripture quote with an internal comma, then " and " ──
A = ('[{"proposition_index": 1, "content": "God controls time, as seen in Psalm '
     '31:15, which says, "My times are in your hands," and Ecclesiastes 3:1, which '
     'states everything has a season."}]')
check("A (Savchuk pattern) fails bare json.loads (defect reproduced)", _fails_raw(A))
okA, pA = _repairs_to(A, 1, ['My times are in your hands'])
check("A repairs -> 1 prop, inner scripture quote preserved", okA)

# ── Case B — Prince "Mary": quote ends the content, producing `.""}` ──
B = ('[{"proposition_index": 3, "content": "Mary responded in Luke 1:31, where she '
     'says, "Behold, I am the maidservant of the Lord; let it be to me according to '
     'your word.""}, {"proposition_index": 4, "content": "Faith requires obedience."}]')
check("B (Prince-Mary pattern) fails bare json.loads", _fails_raw(B))
okB, pB = _repairs_to(B, 2, ['Behold, I am the maidservant', 'Faith requires obedience'])
check("B repairs -> 2 props, terminal quote + next object intact", okB
      and pB[0]["proposition_index"] == 3 and pB[1]["proposition_index"] == 4)

# ── Case C — Prince "Seven Ways": inner quote then `."}` ──
C = ('[{"proposition_index": 1, "content": "The unclean spirit intends to return, '
     'referring to that person as "my house"."}, {"proposition_index": 2, "content": '
     '"Derek Prince states he does not know for sure."}]')
check("C (Prince-SevenWays pattern) fails bare json.loads", _fails_raw(C))
okC, pC = _repairs_to(C, 2, ['as "my house".', 'does not know for sure'])
check("C repairs -> 2 props, inner phrase quote preserved", okC)

# ── Well-formed output must be returned unchanged (repair is a fallback only) ──
GOOD = '[{"proposition_index": 1, "content": "A plain proposition, no quotes."}]'
check("Well-formed JSON already parses (repair not needed)", not _fails_raw(GOOD))
check("Repair is a no-op on well-formed JSON",
      json.loads(propositions._repair_unescaped_quotes(GOOD)) == json.loads(GOOD))

# ── Already-escaped inner quotes must survive the repair intact ──
ESC = '[{"proposition_index": 1, "content": "He said \\"hello\\" to them."}]'
check("Already-escaped quotes parse and survive repair",
      json.loads(ESC)[0]["content"] == 'He said "hello" to them.'
      and json.loads(propositions._repair_unescaped_quotes(ESC))[0]["content"] == 'He said "hello" to them.')

print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
