#!/usr/bin/env python3
"""
Dry-run for the sub-chunk quote exclusion mechanism.

Reads the known mixed chunks flagged in docs/audits/non_teacher_material_audit_2026-08-06.md
and the plan-archive, runs the deterministic detector, and reports:
  - what sub-spans would be excluded
  - whether sample quote candidates from the excluded span are caught
  - whether sample candidates from adjacent teacher text are NOT caught

No INSERT/UPDATE/DELETE. No schema changes. Read-only against live chunks.
Run from project root: python3 scripts/dry_run_subchunk_exclusion.py
"""
from __future__ import annotations

import psycopg2
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.quote_subchunk_exclusion import (
    detect_excluded_subspans,
    candidate_overlaps_excluded_subspan,
)

url = [l.split("=", 1)[1].strip().strip('"').strip("'") for l in open("backend/app/.env") if l.startswith("SUPABASE_DB_URL")][0]

# Document IDs from the audit.
LT = "6345f2ad-e9ec-4807-9fc1-489f7c828c4a"   # The Lord's Table
SOP = "a8e2ead2-7bdf-4f90-9b49-22835800f72a"  # With Christ in the School of Prayer
NL = None  # resolved below by title


def connect():
    return psycopg2.connect(url, connect_timeout=25)


def get_doc_id_by_title(cur, title_fragment: str) -> str:
    cur.execute("SELECT id::text FROM documents WHERE title ILIKE %s LIMIT 1", (f"%{title_fragment}%",))
    row = cur.fetchone()
    return row[0] if row else None


def get_chunk(cur, document_id: str, chunk_index: int):
    cur.execute(
        "SELECT id::text, content FROM chunks WHERE document_id = %s::uuid AND chunk_index = %s",
        (document_id, chunk_index),
    )
    return cur.fetchone()


def report_chunk(title: str, document_id: str, chunk_index: int, expected_kind: str):
    conn = connect()
    cur = conn.cursor()
    row = get_chunk(cur, document_id, chunk_index)
    cur.close()
    conn.close()
    if not row:
        print(f"\n[!] {title} chunk_index {chunk_index} NOT FOUND")
        return
    chunk_id, content = row
    spans = detect_excluded_subspans(content)
    print(f"\n{'='*80}")
    print(f"{title} | chunk_index={chunk_index} | {chunk_id}")
    print(f"expected issue: {expected_kind}")
    print(f"chunk length: {len(content)}")
    print(f"excluded sub-spans found: {len(spans)}")
    for start, end, reason in spans:
        snippet = content[start:end].replace("\n", " ")[:200]
        print(f"  [{start}:{end}] reason={reason!r} | {snippet!r}{'...' if end - start > 200 else ''}")

    # Build positive and negative candidate tests.
    tests: List[Tuple[str, str, bool]] = []
    if spans:
        # Positive: a clean exact substring fully inside the first excluded span.
        start, end, reason = spans[0]
        span_text = content[start:end]
        # Find the first sentence inside the span (look for terminal punctuation).
        pos_candidate = None
        for term in (".", "!", "?"):
            t = span_text.find(term)
            if t > 30:
                pos_candidate = span_text[: t + 1].strip()
                break
        if pos_candidate:
            tests.append(("excluded-span sentence", pos_candidate, True))
        # Negative: first clean sentence before the first excluded span.
        before = content[:start]
        neg_before = None
        for term in (".", "!", "?"):
            # last occurrence
            t = before.rfind(term)
            if t != -1:
                snippet = before[:t].rsplit(term, 1)[-1] if term in before[:t] else before[:t]
                cand = snippet.strip() + term
                if len(cand) > 30:
                    neg_before = cand
                    break
        if neg_before:
            tests.append(("teacher text before exclusion", neg_before, False))
        # Negative: first clean sentence after the last excluded span.
        last_end = spans[-1][1]
        after = content[last_end:]
        neg_after = None
        for term in (".", "!", "?"):
            t = after.find(term)
            if t > 30:
                neg_after = after[: t + 1].strip()
                break
        if neg_after:
            tests.append(("teacher text after exclusion", neg_after, False))
    else:
        print("  (no spans to test)")

    for label, candidate, should_refuse in tests:
        overlaps, reason = candidate_overlaps_excluded_subspan(content, candidate, spans)
        status = "REFUSED" if overlaps else "ALLOWED"
        expected = "REFUSED" if should_refuse else "ALLOWED"
        ok = overlaps == should_refuse
        print(f"  [{('OK' if ok else 'MISMATCH')}] {label}: {status} (expected {expected}) reason={reason!r}")
        if not ok:
            print(f"       candidate={candidate[:120]!r}")


def main():
    conn = connect()
    cur = conn.cursor()
    global NL
    NL = get_doc_id_by_title(cur, "The New Life")
    print("New Life document_id:", NL)
    cur.close()
    conn.close()

    # Müller boundary chunks in School of Prayer.
    report_chunk("SOP Müller boundary", SOP, 228, "Müller block quote at tail")
    report_chunk("SOP Müller boundary", SOP, 229, "Müller block quotes throughout")
    report_chunk("SOP Müller boundary", SOP, 231, "Müller block quotes mixed with Murray")
    report_chunk("SOP Müller boundary", SOP, 232, "Müller block quote mixed with Murray")
    report_chunk("SOP Müller boundary", SOP, 233, "Müller block quote mixed with Murray")
    report_chunk("SOP Müller boundary", SOP, 245, "Müller block quote starts mid-chunk")

    # Translator footnote in Lord's Table.
    report_chunk("LT translator footnote", LT, 54, "one-line translator footnote at head")

    if NL:
        # Translator footnotes in New Life body.
        for idx in [83, 96, 100, 145, 193]:
            report_chunk("NL translator footnote", NL, idx, "translator footnote at tail/head")
        # Heidelberg Catechism in New Life body.
        for idx in [181, 182, 183, 184]:
            report_chunk("NL Heidelberg Catechism", NL, idx, "catechism Q&A insert")


if __name__ == "__main__":
    main()
