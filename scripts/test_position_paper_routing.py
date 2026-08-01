#!/usr/bin/env python3
"""
Regression test for position-paper routing gates (Phase 1 items 1.5-1.7,
2026-08-01). Confirms:
  - a question naming a corpus teacher is NEVER intercepted (highest
    priority gate)
  - a retrieval-intent question ("which teachers...") is NEVER intercepted
  - the three standing debate topics (healing mechanics, prophetic
    accountability, apostolic authority) never qualify either shipped
    pillar, per Alex's 1 Aug ruling
  - the specific hijacked questions from
    docs/audits/phase0_measurement_2026-08-01.md section 7b (H3, G2, T4) no
    longer route to a position paper
  - currently-correct routing (T1-T3) still works

Hits real OpenAI embeddings (a few cents, ~20 calls) -- not free, not a CI
test, run on demand: python3 scripts/test_position_paper_routing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.services.position_papers import (
    match_position_paper,
    PILLARS,
    STANDING_DEBATE_CONTRASTS,
    _pillar_scores,
    _cosine,
    embed_text,
)

CASES = [
    # (question, expected_pillar_or_None, reason)
    ("What do charismatic teachers say about the relationship between faith and healing?", None, "H3 -- reported hijacked into tongues, retrieval-intent + wrong-topic"),
    ("How do I hear God's voice in daily life?", None, "G2 -- reported hijacked into tongues, general topic, not tongues"),
    ("Which teachers in the library teach on speaking in tongues?", None, "T4 -- reported hijacked into tongues, retrieval-intent"),
    ("What does Derek Prince teach about speaking in tongues?", None, "teacher-named -- must never intercept regardless of topic match"),
    ("What does Zac Poonen teach about speaking in tongues?", None, "teacher-named (2nd teacher) -- must never intercept"),
    ("What does Derek Prince teach about the baptism of the Holy Spirit?", None, "teacher-named -- must never intercept, baptism pillar too"),
    ("Can a believer lose their salvation?", None, "salvation wording A -- must not route to baptism"),
    ("Is it possible for a Christian to lose their salvation once they are saved?", None, "salvation wording B -- must not route to baptism"),
    ("Why are some people healed when they pray and others are not?", None, "healing mechanics -- standing debate, must never qualify either pillar"),
    ("How should a prophetic word be tested and held accountable in the church?", None, "prophetic accountability -- standing debate"),
    ("Do apostles still have authority over the church today?", None, "apostolic authority -- standing debate"),
    ("Is speaking in tongues for today?", "speaking_in_tongues", "T1 regression -- must still route correctly"),
    ("What is the baptism of the Holy Spirit?", "baptism_holy_spirit", "T2 regression -- must still route correctly"),
    ("What is the initial evidence of the baptism of the Holy Spirit?", "baptism_holy_spirit", "T3 regression -- must still route correctly"),
    ("How can I be filled with God's power for ministry?", "baptism_holy_spirit", "P1 historical -- baptism's own thinnest documented legitimate margin (+0.0113 at 2026-07-31 calibration) -- must still qualify after MIN_QUALIFY_MARGIN=0.008 and the new contrast anchors were added"),
]

failures = []
for question, expected, reason in CASES:
    result = match_position_paper(question)
    status = "PASS" if result == expected else "FAIL"
    if status == "FAIL":
        failures.append((question, expected, result, reason))
    print(f"[{status}] {reason}\n    Q: {question}\n    expected={expected!r} got={result!r}\n")

# Mechanism check (independent reviewer's flag, 2026-08-01): the three
# debate-probe cases above already fail to qualify on raw pos_sim alone, so
# passing them proves nothing about whether STANDING_DEBATE_CONTRASTS is
# actually wired into scoring. Prove it directly: for at least one debate
# probe, one of the STANDING_DEBATE_CONTRASTS anchors must be the anchor
# that WINS the contrast_sim max (i.e. it must beat every one of the
# pillar's own pre-existing contrast anchors) -- otherwise the shared list
# is dead code that happens to never bind.
print("--- mechanism check: is STANDING_DEBATE_CONTRASTS actually load-bearing? ---")
mechanism_proven = False
healing_q = "Why are some people healed when they pray and others are not?"
q_vec = embed_text(healing_q)
debate_vecs = [embed_text(c) for c in STANDING_DEBATE_CONTRASTS]
for pillar in PILLARS:
    pos_sim, contrast_sim = _pillar_scores(pillar, q_vec)
    own_contrast_only = max(
        _cosine(q_vec, embed_text(c)) for c in pillar["contrast_anchors"]
    )
    debate_only = max(_cosine(q_vec, v) for v in debate_vecs)
    print(
        f"    {pillar['pillar_key']}: contrast_sim={contrast_sim:.4f} "
        f"own_contrast_anchors_alone={own_contrast_only:.4f} "
        f"standing_debate_anchors_alone={debate_only:.4f}"
    )
    if debate_only > own_contrast_only:
        mechanism_proven = True

if not mechanism_proven:
    failures.append((healing_q, "N/A", "N/A", "MECHANISM CHECK FAILED: STANDING_DEBATE_CONTRASTS never wins contrast_sim for either pillar on this probe -- the shared list may be dead code"))
    print("[FAIL] mechanism check: STANDING_DEBATE_CONTRASTS is not the binding contrast for either pillar on this probe")
else:
    print("[PASS] mechanism check: STANDING_DEBATE_CONTRASTS is the binding (highest-scoring) contrast for at least one pillar on this probe -- confirmed load-bearing, not dead code")
print()

print("=" * 70)
if failures:
    print(f"{len(failures)} of {len(CASES)} cases FAILED:")
    for q, expected, got, reason in failures:
        print(f"  - {reason}: expected {expected!r}, got {got!r} -- {q}")
    sys.exit(1)
else:
    print(f"All {len(CASES)} cases passed.")
