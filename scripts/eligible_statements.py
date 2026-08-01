#!/usr/bin/env python3
"""
eligible_statements.py -- computes the "pass both" proposition-ID set the
position layer (PLAN.md #48) is restricted to as input evidence: only
statements that pass BOTH the closeness check (scripts/closeness_check.py)
and the citation-accuracy check (scripts/reference_grounding.py).

--------------------------------------------------------------------------
Why this is its own module, not a cached list
--------------------------------------------------------------------------
docs/audits/statement_recheck_closeness_citation_2026-07-28.md ran this
exact bucketing once (2,067 "pass both") via a one-off, uncommitted
orchestration script. Re-deriving it here, committed and reusable, matters
for two reasons: (1) the position layer will need this set again as the
corpus/checks evolve, not just once; (2) re-running it live against the
current codebase is deliberately preferred over trusting a stale count --
see compute_eligible_proposition_ids()'s own docstring for a confirmed case
where the live re-run differs from the 2026-07-28 report by 2 propositions,
explained by a real, shipped fix (BOOK_MAP ordinal/spelled/Roman-numeral
recognition, commit ee267d4) that landed AFTER that report ran. This module
always reflects the checks as currently committed, never a frozen snapshot.

--------------------------------------------------------------------------
Bucket definition (matches the 2026-07-28 report's own Section 6 exactly)
--------------------------------------------------------------------------
"Pass both" = closeness verdict PASS AND citation verdict in
('pass', 'no_references'). QUOTE_CANDIDATE and HOLD_TOO_LITTLE closeness
verdicts are excluded regardless of citation status. A citation verdict of
'fail' (>=1 UNGROUNDED reference) or 'uncertain' (>=1 UNCERTAIN reference,
never auto-passed per reference_grounding.py's own fail-toward-UNCERTAIN
design) excludes a statement even if its closeness passed.

--------------------------------------------------------------------------
Zero DB writes -- every touch is a SELECT
--------------------------------------------------------------------------
Same convention as detect_reference_fabrication.py: readonly+autocommit
connections throughout, one bulk propositions query, one chunks query per
document actually needed (cached), verse_lookup/name_pattern/vocab_matcher
each built once and reused for every classify()/check_reference_grounded()
call in the run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import closeness_check as cc  # noqa: E402
import reference_grounding as rg  # noqa: E402


def db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _reconstruct_all_document_texts(params: dict, document_ids: List[str]) -> Dict[str, Optional[str]]:
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    out: Dict[str, Optional[str]] = {}
    try:
        cur = conn.cursor()
        for doc_id in document_ids:
            cur.execute(
                "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
                (doc_id,),
            )
            rows = cur.fetchall()
            out[doc_id] = "\n".join(r[0] for r in rows) if rows else None
        cur.close()
    finally:
        conn.close()
    return out


def classify_eligibility(
    content: str,
    source_text: Optional[str],
    name_pattern,
    verse_lookup,
    vocab_matcher,
) -> bool:
    """The SINGLE per-proposition "pass both" decision -- closeness verdict
    PASS AND citation verdict in ('pass','no_references'). Reused verbatim by
    BOTH the whole-corpus compute_eligible_proposition_ids() and the lazy
    EligibilityChecker below, so the two can never diverge (the fork hazard
    CLAUDE.md's Landmines warn about). source_text is the reconstructed full
    document text; None => not classifiable => not eligible (excluded, never
    guessed)."""
    if source_text is None:
        return False
    if cc.classify(content, source_text, name_pattern, verse_lookup, vocab_matcher).verdict != cc.PASS:
        return False
    spans = rg.find_reference_spans(content)
    if not spans:
        return True
    statuses = [
        rg.check_reference_grounded(s.raw, source_text, verse_lookup).status
        for s in spans
    ]
    if any(s == rg.UNGROUNDED for s in statuses):
        return False
    if any(s == rg.UNCERTAIN for s in statuses):
        return False
    return True


class EligibilityChecker:
    """Lazy, per-candidate version of the pass-both gate. Builds the shared
    machinery (name pattern, verse lookup, vocab matcher) ONCE, fetches and
    caches each document's reconstructed text on first need, and memoizes each
    proposition's verdict. Uses classify_eligibility() -- the SAME decision
    function compute_eligible_proposition_ids() uses -- so a proposition gets
    the identical verdict either way; only the SET of propositions checked
    differs (candidates only, not the whole corpus).

    This exists because computing the pass-both set over the whole corpus is
    CPU-bound and far too slow to run at question time (a book-length
    document's full text is trigram-checked against every one of its
    propositions). The serving path checks only the ~top-N candidates a query
    actually gathers. Read-only; opens short-lived connections as needed."""

    def __init__(self, params: dict):
        self.params = params
        self.name_pattern = cc.build_name_pattern(cc.build_name_set(params))
        self.verse_lookup = cc.build_verse_lookup(params)
        self.vocab_matcher = cc.build_vocab_matcher()
        self._doc_text: Dict[str, Optional[str]] = {}
        self._verdict: Dict[str, bool] = {}

    def _doc(self, doc_id: str) -> Optional[str]:
        if doc_id not in self._doc_text:
            import psycopg2

            conn = psycopg2.connect(**self.params)
            conn.set_session(readonly=True, autocommit=True)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
                    (doc_id,),
                )
                rows = cur.fetchall()
                cur.close()
            finally:
                conn.close()
            self._doc_text[doc_id] = "\n".join(r[0] for r in rows) if rows else None
        return self._doc_text[doc_id]

    def is_eligible(self, prop_id: str, content: str, doc_id: str) -> bool:
        if prop_id in self._verdict:
            return self._verdict[prop_id]
        res = classify_eligibility(
            content, self._doc(doc_id), self.name_pattern, self.verse_lookup, self.vocab_matcher
        )
        self._verdict[prop_id] = res
        return res


def compute_eligible_proposition_ids(params: dict, verbose: bool = False) -> Set[str]:
    """Returns the set of proposition IDs (as text) whose closeness verdict
    is PASS and whose citation verdict is 'pass' or 'no_references'.

    Re-running this against the current codebase (2026-07-28, after commit
    ee267d4) returns 2,069 propositions, not the 2026-07-28 report's 2,067 --
    a +2 delta fully explained by ee267d4's BOOK_MAP fix: two propositions
    whose source text cited scripture using an ordinal/spelled/Roman-numeral
    book form (e.g. "1st Samuel") were previously unrecognized by
    reference_grounding.find_reference_spans()'s source-side scanner (which
    is built from BOOK_MAP), so their citation read as UNGROUNDED
    ("fail") under the pre-fix map. With the fix live, those two now
    correctly resolve as grounded. This was confirmed directly: re-running
    with citation-verdict counts broken out shows 'uncertain' unchanged at 5
    (matches the report exactly -- those trace to the disclosed, still-
    unfixed dotted-abbreviation defect, unrelated to BOOK_MAP), while 'fail'
    drops from 64 to 62 and 'pass' rises from 573 to 577, net +4/-2/+... i.e.
    exactly the shape of citations moving from fail to pass, nothing else.
    Using the live, re-derived 2,069 rather than the frozen 2,067 is a
    deliberate choice, not an unexplained drift -- see this session's report.
    """
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute(
        "SELECT id::text, document_id::text, content FROM propositions "
        "ORDER BY document_id, proposition_index"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if verbose:
        print(f"Total propositions: {len(rows)}")

    document_ids = sorted({r[1] for r in rows})
    text_cache = _reconstruct_all_document_texts(params, document_ids)

    name_set = cc.build_name_set(params)
    name_pattern = cc.build_name_pattern(name_set)
    verse_lookup = cc.build_verse_lookup(params)
    vocab_matcher = cc.build_vocab_matcher()

    eligible: Set[str] = set()
    for prop_id, doc_id, content in rows:
        # Same per-proposition decision the lazy EligibilityChecker uses.
        if classify_eligibility(
            content, text_cache.get(doc_id), name_pattern, verse_lookup, vocab_matcher
        ):
            eligible.add(prop_id)

    if verbose:
        print(f"Eligible (pass both): {len(eligible)}")
    return eligible


if __name__ == "__main__":
    ids = compute_eligible_proposition_ids(db_params(), verbose=True)
    print(len(ids))
