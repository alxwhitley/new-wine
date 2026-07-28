#!/usr/bin/env python3
"""
detect_reference_fabrication.py -- corpus-wide, READ-ONLY scripture-reference
grounding audit (PLAN.md #45, 2026-07-28 root-cause fabrication fix, Part 2).

Runs `reference_grounding.check_reference_grounded()` (imported, never
forked -- see that module's own docstring) against every parseable
chapter:verse reference in every stored `propositions.content` row, checked
against that proposition's own document's FULL reconstructed source text
(all chunks, concatenated, chunk_index order), with a live `verse_lookup`
supplied so BOTH grounding arms (citation-string AND WEB verse-wording) run
for every reference. This is the corpus-detection counterpart to Part 1's
prevention wiring in propositions.py -- that call site never supplies
verse_lookup (extract_propositions() has no DB connection of its own); this
script does, because it IS the DB-connected caller reference_grounding.py's
own docstring anticipated when it said "a LATER, SEPARATE step (Part 2,
corpus-wide detection) can feed this exact same function chunk-reconstructed
document text with zero change to the predicate itself."

--------------------------------------------------------------------------
Zero DB writes -- every touch is a SELECT
--------------------------------------------------------------------------
`verses`, `propositions`, `chunks`, `documents`, `sources` are all read via
plain SELECT, each connection opened readonly+autocommit (see db helpers
below, same convention as build_verse_lookup/test_reference_grounding_unit_
proof.py). No INSERT/UPDATE/DELETE anywhere in this file. The only output
artifact besides stdout is a local, gitignored JSONL review file -- never a
DB table, never a flag persisted anywhere in the corpus itself.

--------------------------------------------------------------------------
N+1 discipline
--------------------------------------------------------------------------
verse_lookup: ONE query for the whole run (build_verse_lookup). Propositions:
ONE bulk query for the whole run (or, for a restricted/dry run, one query
scoped by document_id list). Each document's chunks: ONE query PER DOCUMENT
NEEDED (never per proposition, never per reference), fetched only for
documents that actually have >=1 reference-bearing proposition, cached in a
dict, and reused for every proposition/reference belonging to that document.
Document/teacher metadata (title, source name): ONE bulk query for every
document actually needed.

--------------------------------------------------------------------------
Two disclosed limitations (see also the printed report at the end of a run)
--------------------------------------------------------------------------
(i) GROUNDED-but-misattributed-elsewhere-in-document: check_reference_
    grounded() only checks whether a citation string or verse wording
    exists ANYWHERE in source_text, not whether it is the CORRECT support
    for the specific claim the proposition attaches it to. A real
    fabrication -- a real citation attached to the wrong claim -- can and
    does resolve GROUNDED if the same verse's own wording or citation
    string exists anywhere else in a long source document, for a
    completely unrelated reason. Proven case: Leonard Ravenhill, "Paul's
    Passion, Preaching, and Praying" (document_id
    c19ad18c-ea97-4841-8fa0-e60afc273521), citing "Philippians 4:8-9" --
    Alex has explicitly scoped detection to WHOLE-DOCUMENT presence only,
    and this is an accepted, disclosed miss under that scoping, not a bug.
(ii) WEB-only-translation on UNGROUNDED: the wording arm's ground truth is
    the WEB translation only (~31,098 rows, `verses` table). A genuinely
    quoted verse in a divergent non-WEB translation, with no citation
    string printed nearby, could still read UNGROUNDED even though the
    teacher really did quote scripture. UNGROUNDED findings in the review
    file are HIGH-CONFIDENCE CANDIDATES FOR HUMAN REVIEW, never certain
    fabrications to auto-act on.

--------------------------------------------------------------------------
Out of scope by construction (not a gap to fix here)
--------------------------------------------------------------------------
Bare scripture-attribution phrases with no parseable chapter:verse (e.g.
"as stated in the scripture," Vlad Savchuk "How to Spot the Devil's Voice
in Your Head," document_id 6c55bec3-a8ff-45ee-8ccf-5afb862a91a8,
proposition_index 3) are invisible to find_reference_spans() by
construction -- it only ever returns spans that _parse_verse_or_range()
successfully parsed. This script does not and cannot detect that
fabrication class; it produces zero findings for that proposition, and
this is expected, not an error.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
Python 3.9 syntax (Optional[str], never str | None -- Invariant 1). Reuses
reference_grounding.check_reference_grounded()/find_reference_spans() and
closeness_check.build_verse_lookup() exactly as they are -- no fork, no
modification, no reimplementation of the reference-finding regex or the
grounding logic. Does not touch propositions.py or reference_grounding.py.

Run:
  python3 scripts/detect_reference_fabrication.py --dry-run
  python3 scripts/detect_reference_fabrication.py --full
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_grounding as rg  # noqa: E402
import closeness_check as cc  # noqa: E402

REVIEW_DIR = PROJECT_ROOT / "reference_fabrication_review"
REVIEW_PATH = REVIEW_DIR / "corpus_findings.jsonl"

# The 5 documents named in the session's investigation -- used by --dry-run.
# See module docstring / task report for the expected outcome of each.
DRY_RUN_DOCUMENT_IDS = [
    "c19ad18c-ea97-4841-8fa0-e60afc273521",  # Ravenhill, "Paul's Passion..." -- Phil 4:8-9 -> expect GROUNDED (disclosed miss)
    "0f198d4c-7592-47b0-9cea-383f25d24701",  # Savchuk, "...The One God Sent You" -- Genesis 24 -> expect GROUNDED (proof case)
    "6c55bec3-a8ff-45ee-8ccf-5afb862a91a8",  # Savchuk, "...Devil's Voice..." -- prop[3] has zero parseable references
    "e2c25797-4e70-460e-accd-1f61acdc5816",  # Prince, "Deliverance And Demonology" -- unresolved, to be classified
    "199e0871-4197-4f7e-8405-c50fab320103",  # Savchuk, "...Falling for This Trap" -- unresolved, to be classified
]


# ── DB plumbing (mirrors test_reference_grounding_unit_proof.py's convention) ──

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


def fetch_all_propositions(
    params: dict, restrict_document_ids: Optional[List[str]] = None
) -> List[Tuple[str, str, int, str]]:
    """ONE bulk SELECT -- (id, document_id, proposition_index, content) --
    for every proposition in the corpus, or (if restrict_document_ids is
    given -- the --dry-run/--document-ids path) only those belonging to
    that document set. Never a per-row or per-document query."""
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        if restrict_document_ids:
            cur.execute(
                "SELECT id::text, document_id::text, proposition_index, content "
                "FROM propositions WHERE document_id::text = ANY(%s) "
                "ORDER BY document_id, proposition_index",
                (restrict_document_ids,),
            )
        else:
            cur.execute(
                "SELECT id::text, document_id::text, proposition_index, content "
                "FROM propositions ORDER BY document_id, proposition_index"
            )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return rows


def reconstruct_document_text(params: dict, document_id: str) -> Optional[str]:
    """ONE bulk SELECT of every chunk for document_id, ordered by
    chunk_index, joined -- same convention as
    test_reference_grounding_unit_proof.py. Returns None (distinct from an
    empty string) if the document has zero chunk rows at all, so the caller
    can treat that as the genuine ambiguity it is (see main()) rather than
    silently treating "no chunks" the same as "empty document"."""
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    if not rows:
        return None
    return "\n".join(r[0] for r in rows)


def fetch_document_metadata(params: dict, document_ids: List[str]) -> Dict[str, dict]:
    """ONE bulk SELECT -- document_id -> {"title", "teacher"}.

    `teacher` prefers sources.name (joined through documents.source_id) --
    confirmed live (2026-07-28) to be the more reliable field: Derek
    Prince's "Deliverance And Demonology" has documents.source_name = NULL
    but sources.name = 'Derek Prince' via a populated source_id. Falls back
    to documents.author, then documents.source_name, then the literal
    string 'Unknown' if none resolve (never raises for a metadata gap --
    this is a review-file label, not a gate)."""
    if not document_ids:
        return {}
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.id::text, d.original_title, d.title, d.author, d.source_name, s.name
            FROM documents d
            LEFT JOIN sources s ON s.id = d.source_id
            WHERE d.id::text = ANY(%s)
            """,
            (document_ids,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    out: Dict[str, dict] = {}
    for doc_id, original_title, title, author, source_name, source_display_name in rows:
        out[doc_id] = {
            "title": original_title or title or "(untitled)",
            "teacher": source_display_name or author or source_name or "Unknown",
        }
    return out


# ── Core run ─────────────────────────────────────────────────────────────

def run(
    params: dict,
    restrict_document_ids: Optional[List[str]] = None,
    write_review: bool = False,
    verbose: bool = False,
) -> dict:
    """Executes the full detection pass (or, if restrict_document_ids is
    given, a scoped pass over just those documents' propositions) and
    returns a summary dict with every reconciliation number. write_review
    controls whether UNGROUNDED/UNCERTAIN findings are appended to
    REVIEW_PATH -- False for the --dry-run exploration pass (so re-running
    it never pollutes the review file with duplicate lines), True for the
    --full corpus pass, which OVERWRITES REVIEW_PATH (mode "w", not "a")
    at the start of the run -- this script produces one full-corpus
    snapshot per invocation, not an incrementally-appended production log
    like propositions.py's own stripped-references review file."""
    t0 = time.time()

    verse_lookup = cc.build_verse_lookup(params)
    proposition_rows = fetch_all_propositions(params, restrict_document_ids)

    total_propositions = len(proposition_rows)
    zero_ref_propositions = 0
    prop_refs: List[Tuple[str, str, int, str, list]] = []

    for prop_id, doc_id, idx, content in proposition_rows:
        spans = rg.find_reference_spans(content)
        if not spans:
            zero_ref_propositions += 1
            continue
        prop_refs.append((prop_id, doc_id, idx, content, spans))

    doc_ids_needed = sorted({doc_id for _, doc_id, _, _, _ in prop_refs})

    source_text_cache: Dict[str, Optional[str]] = {}
    docs_with_no_chunks: List[str] = []
    for doc_id in doc_ids_needed:
        text = reconstruct_document_text(params, doc_id)
        source_text_cache[doc_id] = text
        if text is None:
            docs_with_no_chunks.append(doc_id)

    if docs_with_no_chunks:
        raise SystemExit(
            "AMBIGUITY -- stopping, not guessing: {0} document(s) have "
            ">=1 reference-bearing proposition but ZERO chunk rows, so "
            "source text cannot be reconstructed: {1}".format(
                len(docs_with_no_chunks), docs_with_no_chunks
            )
        )

    doc_meta = fetch_document_metadata(params, doc_ids_needed)

    findings: List[dict] = []
    total_refs = 0
    grounded_refs = 0
    ungrounded_refs = 0
    uncertain_refs = 0
    errored_refs = 0

    clean_propositions = 0
    props_with_ungrounded = 0
    props_with_uncertain = 0
    props_with_both = 0

    per_reference_log: List[dict] = []  # populated always, printed in verbose/dry-run mode

    for prop_id, doc_id, idx, content, spans in prop_refs:
        source_text = source_text_cache[doc_id]
        meta = doc_meta.get(doc_id, {"title": "(unknown)", "teacher": "Unknown"})
        prop_has_ungrounded = False
        prop_has_uncertain = False

        for span in spans:
            total_refs += 1
            try:
                result = rg.check_reference_grounded(span.raw, source_text, verse_lookup)
            except Exception as exc:  # defensive -- predicate is not expected to raise
                errored_refs += 1
                findings.append(
                    {
                        "document_id": doc_id,
                        "document_title": meta["title"],
                        "teacher": meta["teacher"],
                        "proposition_id": prop_id,
                        "proposition_index": idx,
                        "proposition_content": content,
                        "reference": span.raw,
                        "status": "ERROR",
                        "reason": "exception:{0}:{1}".format(type(exc).__name__, exc),
                    }
                )
                per_reference_log.append(
                    {"document_id": doc_id, "proposition_index": idx, "reference": span.raw, "status": "ERROR"}
                )
                continue

            per_reference_log.append(
                {
                    "document_id": doc_id,
                    "proposition_index": idx,
                    "reference": span.raw,
                    "status": result.status,
                    "reason": result.reason,
                }
            )

            if result.status == rg.GROUNDED:
                grounded_refs += 1
            elif result.status == rg.UNGROUNDED:
                ungrounded_refs += 1
                prop_has_ungrounded = True
                findings.append(
                    {
                        "document_id": doc_id,
                        "document_title": meta["title"],
                        "teacher": meta["teacher"],
                        "proposition_id": prop_id,
                        "proposition_index": idx,
                        "proposition_content": content,
                        "reference": span.raw,
                        "status": rg.UNGROUNDED,
                        "reason": result.reason,
                    }
                )
            elif result.status == rg.UNCERTAIN:
                uncertain_refs += 1
                prop_has_uncertain = True
                findings.append(
                    {
                        "document_id": doc_id,
                        "document_title": meta["title"],
                        "teacher": meta["teacher"],
                        "proposition_id": prop_id,
                        "proposition_index": idx,
                        "proposition_content": content,
                        "reference": span.raw,
                        "status": rg.UNCERTAIN,
                        "reason": result.reason,
                    }
                )
            else:
                raise AssertionError("unreachable status: {0!r}".format(result.status))

        if prop_has_ungrounded and prop_has_uncertain:
            props_with_both += 1
        if prop_has_ungrounded:
            props_with_ungrounded += 1
        if prop_has_uncertain:
            props_with_uncertain += 1
        if not prop_has_ungrounded and not prop_has_uncertain:
            clean_propositions += 1

    in_scope_propositions = total_propositions - zero_ref_propositions
    ungrounded_only = props_with_ungrounded - props_with_both
    uncertain_only = props_with_uncertain - props_with_both
    reconciled_propositions = (
        zero_ref_propositions + clean_propositions + ungrounded_only + uncertain_only + props_with_both
    )

    if write_review:
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_PATH, "w", encoding="utf-8") as f:
            for record in findings:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0

    summary = {
        "elapsed_seconds": round(elapsed, 1),
        "documents_needed": len(doc_ids_needed),
        "verse_lookup_rows": len(verse_lookup),
        "total_propositions": total_propositions,
        "zero_ref_propositions": zero_ref_propositions,
        "in_scope_propositions": in_scope_propositions,
        "clean_propositions": clean_propositions,
        "props_with_ungrounded": props_with_ungrounded,
        "props_with_uncertain": props_with_uncertain,
        "props_with_both": props_with_both,
        "ungrounded_only_propositions": ungrounded_only,
        "uncertain_only_propositions": uncertain_only,
        "reconciled_propositions": reconciled_propositions,
        "total_refs": total_refs,
        "grounded_refs": grounded_refs,
        "ungrounded_refs": ungrounded_refs,
        "uncertain_refs": uncertain_refs,
        "errored_refs": errored_refs,
        "findings": findings,
        "per_reference_log": per_reference_log,
        "review_written": write_review,
    }
    return summary


def print_summary(summary: dict, label: str) -> None:
    print("\n" + "=" * 78)
    print(f"SUMMARY -- {label}")
    print("=" * 78)
    print(f"elapsed: {summary['elapsed_seconds']}s | documents needing chunk fetch: "
          f"{summary['documents_needed']} | verse_lookup rows: {summary['verse_lookup_rows']}")

    print("\n-- Reference-level --")
    print(f"  total references found : {summary['total_refs']}")
    print(f"  GROUNDED               : {summary['grounded_refs']}")
    print(f"  UNGROUNDED             : {summary['ungrounded_refs']}")
    print(f"  UNCERTAIN              : {summary['uncertain_refs']}")
    print(f"  ERRORED                : {summary['errored_refs']}")
    reconciled = (
        summary["grounded_refs"] + summary["ungrounded_refs"]
        + summary["uncertain_refs"] + summary["errored_refs"]
    )
    print(f"  reconciles: grounded+ungrounded+uncertain+errored = {reconciled} "
          f"{'== ' if reconciled == summary['total_refs'] else '!= '}"
          f"total found ({summary['total_refs']})")

    print("\n-- Proposition-level --")
    print(f"  total propositions                         : {summary['total_propositions']}")
    print(f"  zero references (out of scope)              : {summary['zero_ref_propositions']}")
    print(f"  in-scope (>=1 reference)                    : {summary['in_scope_propositions']}")
    print(f"  clean (all references GROUNDED)             : {summary['clean_propositions']}")
    print(f"  >=1 UNGROUNDED reference (total, may overlap): {summary['props_with_ungrounded']}")
    print(f"  >=1 UNCERTAIN reference (total, may overlap) : {summary['props_with_uncertain']}")
    print(f"    of which BOTH ungrounded AND uncertain     : {summary['props_with_both']}")
    print(f"    ungrounded-only (exclusive)                : {summary['ungrounded_only_propositions']}")
    print(f"    uncertain-only (exclusive)                 : {summary['uncertain_only_propositions']}")
    print(f"  reconciled (zero_ref+clean+ungrounded_only+uncertain_only+both) "
          f"= {summary['reconciled_propositions']} "
          f"{'== ' if summary['reconciled_propositions'] == summary['total_propositions'] else '!= '}"
          f"total ({summary['total_propositions']})")

    if summary["review_written"]:
        print(f"\nReview file written: {REVIEW_PATH} ({len(summary['findings'])} findings)")
    else:
        print("\n(dry run -- review file NOT written; findings shown above only)")

    print("\n-- Disclosed limitations (read before treating any number as certainty) --")
    print("  (i)  GROUNDED-but-misattributed-elsewhere-in-document: a real")
    print("       fabrication can still resolve GROUNDED if the same verse's")
    print("       citation/wording exists anywhere else in a long document,")
    print("       unrelated to the specific claim. Proven case: Ravenhill")
    print("       'Paul's Passion...' citing Philippians 4:8-9 -- an accepted,")
    print("       disclosed miss under whole-document-presence scoping.")
    print("  (ii) WEB-only-translation on UNGROUNDED: ground truth for the")
    print("       wording arm is WEB only. A genuinely quoted non-WEB verse")
    print("       with no citation string could read UNGROUNDED. UNGROUNDED")
    print("       findings are high-confidence REVIEW CANDIDATES, never")
    print("       certain fabrications to auto-act on.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Run against the 5 named investigation documents only. No review file write.")
    parser.add_argument("--document-ids", type=str, default=None,
                         help="Comma-separated document_id list to restrict to (alternative to --dry-run).")
    parser.add_argument("--full", action="store_true",
                         help="Run against the entire corpus. Writes the review file.")
    parser.add_argument("--show-per-reference", action="store_true",
                         help="Print every individual reference classification (verbose).")
    args = parser.parse_args()

    if not args.dry_run and not args.document_ids and not args.full:
        parser.error("specify one of --dry-run, --document-ids, or --full")

    params = db_params()

    if args.dry_run or args.document_ids:
        restrict = args.document_ids.split(",") if args.document_ids else DRY_RUN_DOCUMENT_IDS
        print(f"Running SCOPED pass over {len(restrict)} document(s): {restrict}")
        summary = run(params, restrict_document_ids=restrict, write_review=False, verbose=True)
        if args.show_per_reference or args.dry_run:
            print("\n-- Per-reference classification (scoped pass) --")
            for rec in summary["per_reference_log"]:
                print(f"  doc={rec['document_id']} prop_idx={rec['proposition_index']} "
                      f"ref={rec['reference']!r} -> {rec['status']}"
                      + (f" ({rec.get('reason')})" if rec.get("reason") else ""))
        print_summary(summary, label="scoped/dry-run pass (review file NOT written)")

    if args.full:
        print("\nRunning FULL CORPUS pass (writes review file)...")
        summary = run(params, restrict_document_ids=None, write_review=True, verbose=False)
        print_summary(summary, label="full corpus pass")


if __name__ == "__main__":
    main()
