#!/usr/bin/env python3
"""Attended: promote quote_quality_v1 pending gold rows to approved.

Alex-authorized 2026-08-19. Targets ONLY:
  quality_pipeline_version = 'quote_quality_v1'
  status = 'pending'
  selection_eligible = true

Sets approved_by = created_by (existing admin UUID on these rows) and
approved_at = now(). Does NOT flip QUOTE_SELECTION_ENABLED.

Usage:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/approve_gold_quotes_2026-08-19.py
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/approve_gold_quotes_2026-08-19.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = 28
PIPELINE = "quote_quality_v1"


def _load_db_url() -> str:
    env: dict[str, str] = {}
    for line in (ROOT / "backend/app/.env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    url = env.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL missing from backend/app/.env")
    return url


def _counts(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT status, count(*)::int AS n
        FROM quotes
        WHERE quality_pipeline_version = %s
        GROUP BY status
        ORDER BY status
        """,
        (PIPELINE,),
    )
    return {r["status"]: r["n"] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Perform the UPDATE (default is dry-run / report only)",
    )
    args = ap.parse_args()

    conn = psycopg2.connect(_load_db_url())
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    before = _counts(cur)
    cur.execute(
        """
        SELECT id::text
        FROM quotes
        WHERE quality_pipeline_version = %s
          AND status = 'pending'
          AND selection_eligible = true
        ORDER BY id
        """,
        (PIPELINE,),
    )
    ids = [r["id"] for r in cur.fetchall()]
    print("before:", before)
    print("targeted pending+eligible:", len(ids))
    if len(ids) != EXPECTED:
        print(
            f"REFUSE: expected {EXPECTED} targeted rows, found {len(ids)}",
            file=sys.stderr,
        )
        conn.rollback()
        conn.close()
        return 2

    cur.execute(
        """
        SELECT count(*)::int AS speaker_bad
        FROM quotes q
        JOIN quote_source_revisions r ON r.id = q.source_revision_id
        JOIN chunks c ON c.id = r.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE q.id = ANY(%s::uuid[])
          AND q.teacher_source_id IS DISTINCT FROM d.source_id
        """,
        (ids,),
    )
    speaker_bad = cur.fetchone()["speaker_bad"]
    if speaker_bad:
        print(f"REFUSE: speaker mismatch on {speaker_bad} rows", file=sys.stderr)
        conn.rollback()
        conn.close()
        return 2

    if not args.apply:
        print("DRY RUN — no write. Re-run with --apply to promote.")
        conn.rollback()
        conn.close()
        return 0

    cur.execute(
        """
        UPDATE quotes
        SET status = 'approved',
            approved_by = created_by,
            approved_at = now()
        WHERE id = ANY(%s::uuid[])
          AND quality_pipeline_version = %s
          AND status = 'pending'
          AND selection_eligible = true
        RETURNING id::text
        """,
        (ids, PIPELINE),
    )
    updated = [r["id"] for r in cur.fetchall()]
    if len(updated) != EXPECTED:
        print(
            f"ROLLBACK: updated={len(updated)} expected={EXPECTED}",
            file=sys.stderr,
        )
        conn.rollback()
        conn.close()
        return 3

    after = _counts(cur)
    cur.execute(
        """
        SELECT count(*)::int AS still_pending
        FROM quotes
        WHERE quality_pipeline_version = %s AND status = 'pending'
        """,
        (PIPELINE,),
    )
    still_pending = cur.fetchone()["still_pending"]
    cur.execute(
        """
        SELECT count(*)::int AS approved_eligible
        FROM quotes
        WHERE quality_pipeline_version = %s
          AND status = 'approved'
          AND selection_eligible = true
        """,
        (PIPELINE,),
    )
    approved_eligible = cur.fetchone()["approved_eligible"]

    print("updated:", len(updated))
    print("after:", after)
    print("still_pending_v1:", still_pending)
    print("approved_eligible_v1:", approved_eligible)

    if still_pending != 0 or approved_eligible != EXPECTED:
        print("ROLLBACK: reconciliation failed", file=sys.stderr)
        conn.rollback()
        conn.close()
        return 4

    conn.commit()
    print(
        f"OK reconciled: attempted={EXPECTED} stored_approved={len(updated)} "
        f"errored=0 skipped=0 still_pending=0"
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
