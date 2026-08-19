#!/usr/bin/env python3
"""
generate_teacher_positions.py -- CLI driver for the position layer
foundation (PLAN.md #48, Phase 4 opening session, 2026-07-28).

For one teacher, gathers evidence per topic from the pass-both eligible
proposition set (eligible_statements.py) and writes teacher-specific
positions (positions.py). Reports a hard reconciliation count: attempted /
written / refused_floor / errored -- per Standing Session Rule 3.

Usage:
  python3 scripts/generate_teacher_positions.py --teacher "Vlad Savchuk" \\
      --topic "deliverance from demons and spiritual warfare" \\
      --topic "how to pray effectively" \\
      --topic "fasting" \\
      --topic "infant baptism and the sacraments"

Zero DB writes beyond `positions`/`position_evidence` INSERTs for topics
that clear the evidence floor -- no existing row anywhere is read for
write, only for SELECT.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "backend" / "app" / ".env")

import eligible_statements as es  # noqa: E402
import positions as pos  # noqa: E402


def resolve_teacher_source_id(params: dict, teacher_name: str) -> str:
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT id::text FROM sources WHERE name = %s", (teacher_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise SystemExit(f"No sources row named {teacher_name!r}")
    return row[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher", required=True)
    parser.add_argument("--topic", action="append", required=True, dest="topics")
    parser.add_argument("--min-evidence-count", type=int, default=pos.MIN_EVIDENCE_COUNT)
    parser.add_argument("--similarity-floor", type=float, default=pos.SIMILARITY_FLOOR)
    args = parser.parse_args()

    params = pos.db_params()

    print("Deriving eligible (pass-both) proposition ID set...")
    eligible_ids = es.compute_eligible_proposition_ids(params, verbose=True)

    source_id = resolve_teacher_source_id(params, args.teacher)
    print(f"Teacher: {args.teacher}  source_id={source_id}")

    attempted = 0
    written = []
    refused = []
    errored = []

    for topic in args.topics:
        attempted += 1
        print(f"\n--- topic: {topic!r} ---")
        evidence = pos.gather_evidence(
            params, source_id, topic, eligible_ids,
            floor=args.similarity_floor,
        )
        print(f"  evidence gathered: {len(evidence)} (floor={args.similarity_floor})")

        result = pos.write_position(
            params, source_id, topic, evidence,
            kind="teacher",
            min_evidence_count=args.min_evidence_count,
            teacher_name=args.teacher,
        )
        print(f"  status: {result['status']}")

        if result["status"] == "written":
            written.append(result)
            print(f"  position_id: {result['position_id']}")
            print(f"  content:\n{result['content']}\n")
        elif result["status"] == "refused_floor":
            refused.append(result)
            print(f"  refused: evidence_count={result['evidence_count']} < min={result['min_evidence_count']}")
        else:
            errored.append(result)
            print(f"  error: {result.get('error')}")

    print("\n=== RECONCILIATION ===")
    print(f"attempted={attempted} written={len(written)} refused_floor={len(refused)} errored={len(errored)}")
    assert attempted == len(written) + len(refused) + len(errored), "reconciliation mismatch"
    print("Reconciles.")

    out = {
        "teacher": args.teacher,
        "source_id": source_id,
        "attempted": attempted,
        "written": written,
        "refused": refused,
        "errored": errored,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
