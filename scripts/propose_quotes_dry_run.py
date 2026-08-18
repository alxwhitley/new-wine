#!/usr/bin/env python3
"""Dry-run LLM quote propose + quality + (optional) verify — ZERO quote writes.

Task 4 of docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md.

Prints a cost projection up front and aborts if projected spend exceeds $50
without --force-over-ceiling (Alex must approve that explicitly).

Default mode is --estimate-only (no Anthropic calls). Pass --run to call the
model after the estimate is printed. Never inserts quotes.

Examples (repo root):
  python3 scripts/propose_quotes_dry_run.py --limit 3
  python3 scripts/propose_quotes_dry_run.py --limit 3 --estimate-only
  python3 scripts/propose_quotes_dry_run.py --doc-ids UUID1,UUID2 --run
  python3 scripts/propose_quotes_dry_run.py --limit 3 --run --mock   # no API

Reports land under quote_propose_review/ (gitignored) when --run writes them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

warnings.simplefilter("ignore")

import psycopg2
from psycopg2.extensions import connection as PgConnection

from app.services.quote_propose import (
    DEFAULT_MODEL,
    PROMPT_VERSION,
    estimate_propose_cost_usd,
    propose_from_window,
)
from app.services.quote_quality import assess_quote_quality

# Symbols present so unit tests can patch them and prove dry-run never writes.
# The dry-run path must never call these.
create_and_approve_quote = None  # type: ignore
raw_insert_quote = None  # type: ignore

PRINCE_SOURCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"
COST_CEILING_USD = 50.0
REVIEW_DIR = Path(__file__).resolve().parent.parent / "quote_propose_review"


def _db_params() -> dict:
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def connect_readonly() -> PgConnection:
    conn = psycopg2.connect(**_db_params())
    conn.set_session(readonly=True, autocommit=True)
    return conn


def load_cleared_prince_chunks(
    conn: PgConnection,
    *,
    limit_docs: Optional[int] = None,
    doc_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Cleared Derek Prince non-book chunks (quote_ineligible_reason IS NULL)."""
    cur = conn.cursor()
    sql = """
        SELECT d.id, d.title, d.source_type, d.source_kind,
               c.id, c.chunk_index, c.content
        FROM documents d
        JOIN document_quote_clearance qc ON qc.document_id = d.id
        JOIN chunks c ON c.document_id = d.id
        WHERE d.source_id = %s
          AND d.source_type != 'book'
          AND d.source_kind != 'commentary'
          AND c.quote_ineligible_reason IS NULL
          AND c.content IS NOT NULL
          AND length(c.content) >= 80
    """
    params: list[Any] = [PRINCE_SOURCE_ID]
    if doc_ids:
        sql += " AND d.id = ANY(%s)"
        params.append(doc_ids)
    sql += " ORDER BY d.title, c.chunk_index"
    cur.execute(sql, params)
    rows = cur.fetchall()

    # Optionally limit to first N distinct documents (title order).
    if limit_docs is not None:
        keep_ids: list[str] = []
        seen: set[str] = set()
        for doc_id, *_rest in rows:
            sid = str(doc_id)
            if sid not in seen:
                seen.add(sid)
                keep_ids.append(sid)
                if len(keep_ids) >= limit_docs:
                    break
        keep = set(keep_ids)
        rows = [r for r in rows if str(r[0]) in keep]

    out = []
    for doc_id, title, source_type, source_kind, chunk_id, chunk_index, content in rows:
        out.append(
            {
                "document_id": str(doc_id),
                "title": title,
                "source_type": source_type,
                "source_kind": source_kind,
                "chunk_id": str(chunk_id),
                "chunk_index": chunk_index,
                "content": content,
                "teacher_source_id": PRINCE_SOURCE_ID,
            }
        )
    return out


def evaluate_proposals_for_chunk(
    chunk: dict[str, Any],
    *,
    model_fn: Optional[Callable[[str, str], str]] = None,
    model: str = DEFAULT_MODEL,
    run_verify: bool = False,
    db_for_verify: Any = None,
) -> list[dict[str, Any]]:
    """Propose + quality (+ optional verify). Never writes quotes.

    ``create_and_approve_quote`` / ``raw_insert_quote`` exist as module
    attributes for mutation tests; this function must not call them.
    """
    batch = propose_from_window(
        chunk["content"],
        model_fn=model_fn,
        model=model,
    )
    results: list[dict[str, Any]] = []
    for cand in batch.candidates:
        quality = assess_quote_quality(
            cand.quote_text,
            restated_point=cand.restated_point,
            why_quotable=cand.why_quotable,
            standalone_ok=cand.standalone_ok,
        )
        verify_payload: Optional[dict[str, Any]] = None
        if run_verify and db_for_verify is not None and quality.ok:
            from app.services.quote_verifier import verify_quote_candidate

            verification = verify_quote_candidate(
                db_for_verify,
                chunk["chunk_id"],
                cand.quote_text,
                chunk["teacher_source_id"],
            )
            verify_payload = {
                "valid": verification.valid,
                "rule": verification.rule,
                "reason": verification.reason,
            }

        results.append(
            {
                "document_id": chunk["document_id"],
                "title": chunk["title"],
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "prompt_version": batch.prompt_version,
                "model": batch.model,
                "quote_text": cand.quote_text,
                "char_start": cand.char_start,
                "char_end": cand.char_end,
                "restated_point": cand.restated_point,
                "topic_ids": list(cand.topic_ids),
                "why_quotable": cand.why_quotable,
                "standalone_ok": cand.standalone_ok,
                "quality_ok": quality.ok,
                "quality_rule": quality.rule,
                "quality_reason": quality.reason,
                "verify": verify_payload,
                "wrote": False,
                "parse_errors": list(batch.parse_errors),
            }
        )

    if not batch.candidates:
        results.append(
            {
                "document_id": chunk["document_id"],
                "title": chunk["title"],
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "prompt_version": batch.prompt_version,
                "model": batch.model,
                "quote_text": None,
                "quality_ok": False,
                "quality_rule": "no_candidates",
                "quality_reason": "model returned no usable candidates",
                "parse_errors": list(batch.parse_errors),
                # Keep raw so offset/parse failures are diagnosable without a re-spend.
                "raw_response": batch.raw_response,
                "wrote": False,
            }
        )
    return results


def print_cost_header(est: dict[str, Any], *, n_docs: int, ceiling: float) -> None:
    print()
    print("=" * 60)
    print("QUOTE PROPOSE DRY-RUN — COST PROJECTION")
    print("=" * 60)
    print("prompt_version:     %s" % PROMPT_VERSION)
    print("model:              %s" % est["model"])
    print("documents in scope: %d" % n_docs)
    print("windows (chunks):   %d" % est["n_windows"])
    print("avg window chars:   %d" % est["avg_window_chars"])
    print("est input tokens:   %d" % est["est_input_tokens"])
    print("est output tokens:  %d" % est["est_output_tokens"])
    print(
        "pricing assumption: $%.2f/MTok in + $%.2f/MTok out"
        % (est["usd_per_mtok_input"], est["usd_per_mtok_output"])
    )
    print("ESTIMATED COST:     $%.4f" % est["est_cost_usd"])
    print("HARD CEILING:       $%.2f" % ceiling)
    print("=" * 60)
    print()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run quote propose (zero quote DB writes)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max cleared Prince non-book documents (title order)",
    )
    parser.add_argument(
        "--doc-ids",
        type=str,
        default=None,
        help="Comma-separated document UUIDs (overrides --limit filter set)",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        default=False,
        help="Print cost projection only (default when --run is absent)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        default=False,
        help="After printing the estimate, call the model (or --mock)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use a local stub model_fn instead of Anthropic (still --run)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="Also run verify_quote_candidate (read-only) on quality-pass candidates",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Anthropic model id (default %s)" % DEFAULT_MODEL,
    )
    parser.add_argument(
        "--force-over-ceiling",
        action="store_true",
        default=False,
        help="Allow projected cost above $%.0f (requires Alex approval)" % COST_CEILING_USD,
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="JSONL report path (default quote_propose_review/<timestamp>.jsonl)",
    )
    args = parser.parse_args(argv)

    if not args.run:
        args.estimate_only = True

    doc_ids = None
    if args.doc_ids:
        doc_ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]

    if args.limit is None and not doc_ids:
        # Calibration default from the plan: 3 docs.
        args.limit = 3

    conn = connect_readonly()
    try:
        chunks = load_cleared_prince_chunks(
            conn, limit_docs=None if doc_ids else args.limit, doc_ids=doc_ids
        )
    finally:
        conn.close()

    if not chunks:
        print("No cleared Prince non-book chunks matched the scope.")
        return 1

    doc_titles = {}
    for ch in chunks:
        doc_titles.setdefault(ch["document_id"], ch["title"])
    n_docs = len(doc_titles)
    avg_chars = int(sum(len(c["content"]) for c in chunks) / max(1, len(chunks)))
    est = estimate_propose_cost_usd(
        n_windows=len(chunks),
        avg_window_chars=avg_chars,
        model=args.model,
    )
    print_cost_header(est, n_docs=n_docs, ceiling=COST_CEILING_USD)
    print("Documents:")
    for i, (did, title) in enumerate(doc_titles.items(), 1):
        n_ch = sum(1 for c in chunks if c["document_id"] == did)
        print("  %d. %s  (%d chunks)  id=%s" % (i, title, n_ch, did))
    print()

    if float(est["est_cost_usd"]) > COST_CEILING_USD and not args.force_over_ceiling:
        print(
            "ABORT: projected $%.4f exceeds $%.2f ceiling. "
            "Re-run with a smaller --limit or explicit --force-over-ceiling after Alex OK."
            % (est["est_cost_usd"], COST_CEILING_USD)
        )
        return 2

    if args.estimate_only and not args.run:
        print(
            "Estimate-only complete. Re-run with --run to call the model "
            "(add --mock for a free stub pass)."
        )
        return 0

    # ── Paid or mock propose ───────────────────────────────────────────────
    model_fn = None
    if args.mock:

        def model_fn(system: str, user: str) -> str:  # noqa: F811
            # Deterministic empty proposal — proves plumbing without inventing spans.
            return json.dumps({"candidates": []})

    db_for_verify = None
    if args.verify:
        from app.db.supabase import get_supabase

        db_for_verify = get_supabase()

    all_rows: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks, 1):
        print(
            "[%d/%d] %s chunk %s"
            % (i, len(chunks), chunk["title"], chunk["chunk_index"]),
            flush=True,
        )
        rows = evaluate_proposals_for_chunk(
            chunk,
            model_fn=model_fn,
            model=args.model,
            run_verify=args.verify,
            db_for_verify=db_for_verify,
        )
        all_rows.extend(rows)
        for r in rows:
            if r.get("quote_text"):
                print(
                    "  -> quality=%s/%s topics=%s"
                    % (r["quality_ok"], r["quality_rule"], r.get("topic_ids")),
                    flush=True,
                )
            elif r.get("parse_errors"):
                print(
                    "  -> no usable candidates; parse_errors=%s"
                    % (r.get("parse_errors"),),
                    flush=True,
                )

    # Hard reconciliation counts (attempted windows / proposals / quality / verify).
    attempted = len(chunks)
    proposed = sum(1 for r in all_rows if r.get("quote_text"))
    quality_pass = sum(1 for r in all_rows if r.get("quality_ok"))
    quality_fail = proposed - quality_pass
    verify_pass = sum(
        1 for r in all_rows if (r.get("verify") or {}).get("valid") is True
    )
    wrote = sum(1 for r in all_rows if r.get("wrote"))

    print()
    print("RECONCILIATION")
    print("  windows_attempted: %d" % attempted)
    print("  proposals_parsed:  %d" % proposed)
    print("  quality_pass:      %d" % quality_pass)
    print("  quality_fail:      %d" % quality_fail)
    if args.verify:
        print("  verify_pass:       %d" % verify_pass)
    print("  quote_rows_written:%d  (must be 0)" % wrote)
    if wrote != 0:
        print("FATAL: dry-run wrote quote rows")
        return 1

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else (
        REVIEW_DIR
        / ("propose_dry_run_%s.jsonl" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    )
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "meta": True,
                    "prompt_version": PROMPT_VERSION,
                    "model": args.model,
                    "mock": args.mock,
                    "estimate": est,
                    "n_docs": n_docs,
                    "doc_ids": list(doc_titles.keys()),
                    "reconciliation": {
                        "windows_attempted": attempted,
                        "proposals_parsed": proposed,
                        "quality_pass": quality_pass,
                        "quality_fail": quality_fail,
                        "verify_pass": verify_pass if args.verify else None,
                        "quote_rows_written": wrote,
                    },
                }
            )
            + "\n"
        )
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("Report: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
