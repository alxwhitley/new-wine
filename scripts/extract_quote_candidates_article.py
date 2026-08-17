#!/usr/bin/env python3
"""
extract_quote_candidates_article.py — reusable, general (not
Prince-specific) article/document quote-candidate PROPOSAL tool.

Composes scripts/quote_candidates.py's deterministic generation layer
with the REAL, unmodified app.services.quote_verifier.verify_quote_candidate
and app.services.quotes._enforce_quote_cap. Candidate GENERATION and
candidate APPROVAL are two distinct calls in this file, never merged:
propose_candidates_for_chunk() only ever returns a verdict the real
verifier already reached; nothing in this module writes 'approved' (or
even 'pending') anywhere -- there is no INSERT statement anywhere in this
file. Existing commentary exclusion, sub-chunk/nested-quotation exclusion,
excluded-span handling, and speaker confirmation are exactly
verify_quote_candidate()'s own checks, reused unmodified; the per-work
cap is exactly app.services.quotes._enforce_quote_cap, also reused
unmodified.

REMAINING PRODUCT DECISION, deliberately not invented here (per this
build's own instruction: complete the deterministic layer, name the open
question, do not guess): extract_quote_candidates_derek_prince.py ranks
candidates with a hand-calibrated _score_candidate() (theological-
vocabulary hits, preferred length bands, oral-speech red-flag phrases
like "applause"/"turn to your Bible") tuned 2026-08-13 against Derek
Prince's own spoken-sermon corpus statistics (document-length
distribution, what "quotable" looks like in his transcripts). Reusing
those exact weights for arbitrary written article prose from an unknown
future author would itself be a quality-calibration decision with no
real content behind it yet -- exactly the kind of thing this build was
told not to invent. This module therefore proposes every STRUCTURALLY
eligible candidate (see quote_candidates.py) in document order and does
NOT rank or score them. Before this tool is run at any real volume, a
human needs to: (a) decide whether article prose needs its own scoring
model, calibrated against real sampled article content the way Prince's
was, and (b) decide whether/how proposed candidates should be written to
the database at all (pending, for later automatic verification the way
the Prince script does, or some other shape) -- neither is decided here,
and this file's CLI below deliberately only ever prints proposals; it has
no code path that writes anything, gated by a flag or otherwise.

Dry-run / local-fixture mode: propose_candidates_for_chunk() and
would_exceed_work_cap() take `db` as a plain parameter with no import-time
side effect -- pass any object exposing the same
.table(name).select(...).eq(...).in_(...).limit(...).execute().data shape
the real Supabase client does (see test_extract_quote_candidates_article.py's
FakeDb for a complete, DB-free, network-free example) to exercise the real
verifier/cap logic entirely offline. The CLI's own --dry-run is the only
mode this file implements at all -- there is no non-dry-run path.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, FrozenSet, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.quote_verifier import verify_quote_candidate  # noqa: E402
from app.services.quotes import _enforce_quote_cap  # noqa: E402

from quote_candidates import generate_candidate_spans  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateProposal:
    chunk_id: str
    text: str
    valid: bool
    rule: str
    reason: Optional[str]


def propose_candidates_for_chunk(
    db,
    chunk_id: str,
    chunk_content: str,
    teacher_source_id: str,
    *,
    verify_fn: Callable = verify_quote_candidate,
    existing_texts: FrozenSet[str] = frozenset(),
    min_len: int = 120,
    max_len: int = 500,
) -> List[CandidateProposal]:
    """Propose every structurally eligible candidate in one chunk and
    report the REAL verifier's verdict on each. Two visibly distinct
    steps: generate_candidate_spans() (never sees `db`) produces text
    spans; verify_fn (the real verifier, by default) makes every
    accept/refuse decision. Never raises on a refused candidate -- refusal
    is a normal CandidateProposal(valid=False, ...), not an exception."""
    spans = generate_candidate_spans(chunk_content, min_len=min_len, max_len=max_len)
    proposals: List[CandidateProposal] = []
    seen_this_call = set()
    for _start, _end, text in spans:
        if text in existing_texts or text in seen_this_call:
            continue
        seen_this_call.add(text)
        verification = verify_fn(db, chunk_id, text, teacher_source_id)
        proposals.append(
            CandidateProposal(
                chunk_id=chunk_id,
                text=text,
                valid=verification.valid,
                rule=verification.rule,
                reason=verification.reason,
            )
        )
    return proposals


def would_exceed_work_cap(
    db,
    document_id: str,
    candidate_text: str,
    *,
    enforce_cap_fn: Callable = _enforce_quote_cap,
) -> bool:
    """True if this candidate would push the document's cumulative
    approved-quote-text cap (Settled decision #16) over its limit, per the
    EXISTING, unchanged app.services.quotes._enforce_quote_cap -- this
    function never approves anything and never recomputes the cap itself;
    it only asks the real cap-enforcing code what it would decide."""
    try:
        enforce_cap_fn(db, document_id, candidate_text)
        return False
    except ValueError:
        return True


def _print_report(proposals: List[CandidateProposal]) -> None:
    accepted = [p for p in proposals if p.valid]
    refused = [p for p in proposals if not p.valid]
    for p in accepted:
        print("ACCEPT chunk=%s text=%r" % (p.chunk_id, p.text[:200]))
    for p in refused:
        print(
            "REFUSE chunk=%s rule=%s reason=%s text=%r"
            % (p.chunk_id, p.rule, p.reason, p.text[:200])
        )
    print(
        "Summary: %d accepted, %d refused, %d total"
        % (len(accepted), len(refused), len(proposals))
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Propose article/document quote candidates for one teacher's "
            "chunks. Dry-run only -- prints proposals; writes nothing."
        )
    )
    parser.add_argument("--teacher-source-id", required=True)
    parser.add_argument(
        "--doc-ids-file",
        required=True,
        help="Path to a file containing UUID document ids (one per line).",
    )
    args = parser.parse_args()

    # Imported lazily so this CLI path (never exercised by this build's own
    # tests, which use a fully offline FakeDb) is the only place a real
    # Supabase client is constructed.
    from app.db.supabase import get_supabase

    db = get_supabase()
    doc_ids = [line.strip() for line in Path(args.doc_ids_file).read_text().splitlines() if line.strip()]

    all_proposals: List[CandidateProposal] = []
    seen_texts: set = set()
    for doc_id in doc_ids:
        chunks = (
            db.table("chunks")
            .select("id, content, quote_ineligible_reason")
            .eq("document_id", doc_id)
            .order("chunk_index")
            .execute()
            .data
        )
        for chunk in chunks:
            if not chunk.get("content") or chunk.get("quote_ineligible_reason"):
                continue
            proposals = propose_candidates_for_chunk(
                db,
                chunk["id"],
                chunk["content"],
                args.teacher_source_id,
                existing_texts=frozenset(seen_texts),
            )
            for p in proposals:
                if p.valid:
                    seen_texts.add(p.text)
            all_proposals.extend(proposals)

    _print_report(all_proposals)


if __name__ == "__main__":
    main()
