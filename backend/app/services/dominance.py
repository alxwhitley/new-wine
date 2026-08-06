"""
dominance.py -- the single-teacher-dominance decision rule, shared between
scripts/positions.py (the position layer's teacher-vs-corpus scope
determination, PLAN.md #48) and app.services.single_teacher_lock (Project 2
phase 1 step 2's retrieval-time lock, PLAN.md v5.24, CLAUDE.md Settled
decision #15). Originally lived only in scripts/positions.py; moved here
2026-08-06 so both consumers share ONE reasoned threshold and ONE Counter
implementation instead of two independently-maintained copies -- the same
class of drift CLAUDE.md's Landmines already documents for the book-name map
(five hand-maintained copies that silently went out of sync).

scripts/positions.py re-exports DOMINANCE_THRESHOLD and determine_scope from
here (`from app.services.dominance import DOMINANCE_THRESHOLD,
determine_scope`) rather than defining its own -- existing callers
(scripts/serve_position.py, scripts/test_serve_position.py) that reference
`positions.DOMINANCE_THRESHOLD` / `positions.determine_scope` are unaffected,
since Python module attributes reached via a re-export resolve identically to
ones defined locally.

app.services.single_teacher_lock could NOT reuse scripts/positions.py's
determine_scope() by importing scripts/positions.py directly -- see that
module's own docstring for why (scripts/ is not on the backend Railway
service's deploy root, and positions.py's OTHER functions open their own
psycopg2 connection against the propositions table, an offline-script shape
unsuited to the live per-question chunks retrieval path). This module holds
only the one piece that generalizes cleanly: a pure, I/O-free function keyed
on a "source_id" per evidence item.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Scope determination (originally PLAN.md #48 serving-path session,
# 2026-08-01; relocated here 2026-08-06)
# --------------------------------------------------------------------------
# DOMINANCE_THRESHOLD is the single, documented boundary between teacher and
# corpus scope for a TOPIC question (one that does not name a teacher). After
# gathering evidence corpus-wide, compute each teacher's share of that
# gathered evidence. If the single largest teacher supplies >= this fraction,
# the honest answer is "this is mostly that teacher's position" -> teacher
# scope, attributed to him. Below it, no single voice dominates -> corpus
# scope, naming the real contributors with their evidence counts.
#
# 0.60 is a reasoned starting point, NOT a calibrated constant (no real
# question traffic exists yet -- the position layer does not serve users).
# Rationale: at >=60% one teacher supplies the clear majority of the material
# that actually answers the question, so dressing it up as a multi-teacher
# "corpus consensus" would misrepresent it (exactly the failure the corpus
# contributor rules exist to refuse). Below 60% the evidence is genuinely
# distributed across two or more materially-contributing teachers. Recorded
# in PLAN.md as overrulable once Alex sees it work. Known limitation, stated
# not hidden: share is measured over the gathered top-N by similarity, so a
# prolific teacher (Derek Prince, ~5k propositions) has more shots at the
# top-N and can dominate share partly by volume, not only by topical
# authority -- an accepted first-cut bias, flagged for the calibration pass.
DOMINANCE_THRESHOLD = 0.60


def determine_scope(evidence):
    # type: (List[Dict]) -> Tuple[str, Optional[str]]
    """Given a list of evidence items each carrying 'source_id', decide scope
    by single-teacher dominance. If the largest-contributing teacher supplies
    >= DOMINANCE_THRESHOLD of the gathered evidence, this topic is dominated
    by one voice -> ("teacher", that source_id); dressing it up as a
    multi-teacher consensus would misrepresent it. Otherwise the evidence is
    genuinely distributed -> ("corpus", None). Pure, no I/O. Empty evidence
    returns ("corpus", None) -- scripts/positions.py's caller refuses on the
    honest-empty floor before scope is ever consulted; app.services.
    single_teacher_lock's caller treats it as "no lock" instead, since there
    is no honest-empty refusal concept on the live chat retrieval path."""
    if not evidence:
        return "corpus", None
    counts = Counter(e["source_id"] for e in evidence)
    total = sum(counts.values())
    top_source, top_n = counts.most_common(1)[0]
    if top_n / total >= DOMINANCE_THRESHOLD:
        return "teacher", top_source
    return "corpus", None
