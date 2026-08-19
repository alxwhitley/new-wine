#!/usr/bin/env python3
"""Gold-set quote write path for the quality pipeline (Task 5).

Flow per candidate: LLM propose → assess_quote_quality → verify_quote_candidate
→ (optional) create_and_approve_quote with quality_pipeline_version + topic_ids.

Defaults to dry-run (ZERO quote writes). Pass --apply only after Alex approves
the doc list + cost. First gold inserts as status=pending by default.

Examples (repo root):
  python3 scripts/extract_quotes_quality_pipeline.py --limit 3
  python3 scripts/extract_quotes_quality_pipeline.py --limit 3 --estimate-only
  python3 scripts/extract_quotes_quality_pipeline.py --doc-ids UUID1,UUID2 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
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
from app.services.quote_verifier import verify_quote_candidate
from app.services.quotes import (
    QUALITY_PIPELINE_VERSION_V1,
    create_and_approve_quote,
    _log_quote_decision,
)
from propose_quotes_dry_run import (
    COST_CEILING_USD,
    PRINCE_SOURCE_ID,
    connect_readonly,
    load_cleared_prince_chunks,
    print_cost_header,
)

REVIEW_DIR = Path(__file__).resolve().parent.parent / "quote_propose_review"


def _db_params() -> dict:
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("ERROR: SUPABASE_DB_URL is not set")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def _admin_user_id(conn: PgConnection) -> str:
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM user_roles WHERE role = 'admin' ORDER BY created_at LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("no admin user found in user_roles")
    return str(row[0])


def _reviewer_note(restated_point: str, why_quotable: str) -> str:
    return (
        "%s\n\n[why_quotable: %s | prompt=%s | pipeline=%s]"
        % (restated_point.strip(), why_quotable.strip(), PROMPT_VERSION, QUALITY_PIPELINE_VERSION_V1)
    )


def process_chunk(
    chunk: dict[str, Any],
    *,
    supabase_db: Any,
    user_id: str,
    model: str,
    apply: bool,
    status: str,
    model_fn=None,
    seen_texts: Optional[set[str]] = None,
) -> dict[str, int]:
    """Propose → quality → verify → optional insert. Returns reconciliation deltas."""
    counts = {
        "windows": 1,
        "proposals": 0,
        "refused_quality": 0,
        "refused_verify": 0,
        "skipped_dup": 0,
        "would_store": 0,
        "stored": 0,
        "errors": 0,
    }
    if seen_texts is None:
        seen_texts = set()

    try:
        batch = propose_from_window(chunk["content"], model_fn=model_fn, model=model)
    except Exception as exc:
        counts["errors"] += 1
        print(
            "  ERROR propose failed chunk=%s: %s" % (chunk["chunk_index"], exc),
            flush=True,
        )
        return counts

    for cand in batch.candidates:
        counts["proposals"] += 1
        quality = assess_quote_quality(
            cand.quote_text,
            restated_point=cand.restated_point,
            why_quotable=cand.why_quotable,
            standalone_ok=cand.standalone_ok,
        )
        if not quality.ok:
            counts["refused_quality"] += 1
            print(
                "  refuse_quality rule=%s len=%d" % (quality.rule, len(cand.quote_text)),
                flush=True,
            )
            continue

        if cand.quote_text in seen_texts:
            counts["skipped_dup"] += 1
            print("  skip_dup", flush=True)
            continue

        verification = verify_quote_candidate(
            supabase_db,
            chunk["chunk_id"],
            cand.quote_text,
            chunk["teacher_source_id"],
        )
        if not verification.valid:
            counts["refused_verify"] += 1
            print(
                "  refuse_verify rule=%s reason=%s"
                % (verification.rule, verification.reason),
                flush=True,
            )
            if apply:
                _log_quote_decision(
                    supabase_db,
                    chunk_id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    teacher_source_id=chunk["teacher_source_id"],
                    quote_text=cand.quote_text,
                    decision="refused",
                    rule=verification.rule,
                    reason=verification.reason,
                    submitted_by=user_id,
                )
            continue

        primary_topic = cand.topic_ids[0]
        note = _reviewer_note(cand.restated_point, cand.why_quotable)

        if not apply:
            counts["would_store"] += 1
            seen_texts.add(cand.quote_text)
            print(
                "  [DRY] would_store status=%s topic=%r topics=%s text=%r"
                % (status, primary_topic, cand.topic_ids, cand.quote_text[:120]),
                flush=True,
            )
            continue

        try:
            row = create_and_approve_quote(
                supabase_db,
                chunk["chunk_id"],
                cand.quote_text,
                chunk["teacher_source_id"],
                primary_topic,
                note,
                user_id,
                topic_ids=list(cand.topic_ids),
                quality_pipeline_version=QUALITY_PIPELINE_VERSION_V1,
                selection_eligible=True,
                status=status,
            )
            counts["stored"] += 1
            seen_texts.add(cand.quote_text)
            print(
                "  STORED id=%s status=%s topic=%r"
                % (row.get("id"), row.get("status"), primary_topic),
                flush=True,
            )
        except Exception as exc:
            counts["errors"] += 1
            print("  ERROR store failed: %s" % exc, flush=True)

    return counts


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quality-pipeline quote extract (dry-run default; --apply writes)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Max cleared Prince docs")
    parser.add_argument("--doc-ids", type=str, default=None, help="Comma-separated doc UUIDs")
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="Print cost projection and exit (no model calls)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write pending/approved quote rows (OFF by default)",
    )
    parser.add_argument(
        "--status",
        choices=("pending", "approved"),
        default="pending",
        help="Insert status when --apply (default pending)",
    )
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Stub model (empty candidates) — plumbing only",
    )
    parser.add_argument(
        "--force-over-ceiling",
        action="store_true",
        help="Allow projected cost above $%.0f" % COST_CEILING_USD,
    )
    args = parser.parse_args(argv)

    if args.apply and args.mock:
        print("ERROR: --apply and --mock together refuse (would write empty junk)")
        return 2

    doc_ids = None
    if args.doc_ids:
        doc_ids = [x.strip() for x in args.doc_ids.split(",") if x.strip()]
    if args.limit is None and not doc_ids:
        args.limit = 3

    ro = connect_readonly()
    try:
        chunks = load_cleared_prince_chunks(
            ro, limit_docs=None if doc_ids else args.limit, doc_ids=doc_ids
        )
        admin_user_id = _admin_user_id(ro)
    finally:
        ro.close()

    if not chunks:
        print("No cleared Prince non-book chunks matched.")
        return 1

    doc_titles = {}
    for ch in chunks:
        doc_titles.setdefault(ch["document_id"], ch["title"])
    avg_chars = int(sum(len(c["content"]) for c in chunks) / max(1, len(chunks)))
    est = estimate_propose_cost_usd(
        n_windows=len(chunks), avg_window_chars=avg_chars, model=args.model
    )
    print_cost_header(est, n_docs=len(doc_titles), ceiling=COST_CEILING_USD)
    print("mode: %s  insert_status: %s  pipeline: %s" % (
        "APPLY" if args.apply else "DRY-RUN",
        args.status,
        QUALITY_PIPELINE_VERSION_V1,
    ))
    for i, (did, title) in enumerate(doc_titles.items(), 1):
        n_ch = sum(1 for c in chunks if c["document_id"] == did)
        print("  %d. %s (%d chunks) id=%s" % (i, title, n_ch, did))
    print()

    if float(est["est_cost_usd"]) > COST_CEILING_USD and not args.force_over_ceiling:
        print("ABORT: projected cost exceeds ceiling")
        return 2

    if args.estimate_only:
        print("Estimate-only complete.")
        return 0

    if args.apply:
        print(
            "WARNING: --apply will write quote rows as status=%s. "
            "Ctrl-C now if unintended." % args.status,
            flush=True,
        )

    from app.db.supabase import get_supabase

    supabase_db = get_supabase()
    model_fn = None
    if args.mock:
        model_fn = lambda system, user: json.dumps({"candidates": []})

    totals = {
        "windows": 0,
        "proposals": 0,
        "refused_quality": 0,
        "refused_verify": 0,
        "skipped_dup": 0,
        "would_store": 0,
        "stored": 0,
        "errors": 0,
    }
    seen: set[str] = set()
    for i, chunk in enumerate(chunks, 1):
        print(
            "[%d/%d] %s chunk %s"
            % (i, len(chunks), chunk["title"], chunk["chunk_index"]),
            flush=True,
        )
        delta = process_chunk(
            chunk,
            supabase_db=supabase_db,
            user_id=admin_user_id,
            model=args.model,
            apply=args.apply,
            status=args.status,
            model_fn=model_fn,
            seen_texts=seen,
        )
        for k, v in delta.items():
            totals[k] += v

    print()
    print("RECONCILIATION")
    print("  windows_attempted:  %d" % totals["windows"])
    print("  proposals_parsed:   %d" % totals["proposals"])
    print("  refused_quality:    %d" % totals["refused_quality"])
    print("  refused_verify:     %d" % totals["refused_verify"])
    print("  skipped_dup:        %d" % totals["skipped_dup"])
    print("  would_store:        %d" % totals["would_store"])
    print("  stored:             %d" % totals["stored"])
    print("  errors:             %d" % totals["errors"])
    if not args.apply and totals["stored"] != 0:
        print("FATAL: dry-run stored rows")
        return 1
    if args.apply:
        print(
            "HARD CHECK: stored=%d windows=%d (attempted docs=%d)"
            % (totals["stored"], totals["windows"], len(doc_titles))
        )

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out = REVIEW_DIR / (
        "gold_pipeline_%s_%s.json"
        % (
            "apply" if args.apply else "dry",
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        )
    )
    out.write_text(
        json.dumps(
            {
                "apply": args.apply,
                "status": args.status,
                "prompt_version": PROMPT_VERSION,
                "pipeline_version": QUALITY_PIPELINE_VERSION_V1,
                "model": args.model,
                "estimate": est,
                "doc_ids": list(doc_titles.keys()),
                "reconciliation": totals,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Report: %s" % out)
    return 0 if totals["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
