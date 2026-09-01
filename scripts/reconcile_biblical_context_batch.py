#!/usr/bin/env python3
"""Fresh read-only reconciliation for the Phase 6 Aaron proof."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from biblical_context_ingest_contract import (
    ProofProjection,
    build_aaron_projection,
    projection_report,
)
from biblical_context_tooling import canonical_json_bytes
from ingest_biblical_context_batch import inspect_state


ROOT = Path(__file__).resolve().parent.parent
READONLY_ROLE = "newwine_readonly_analysis"


class ReconciliationError(RuntimeError):
    """Fresh read-only evidence does not prove the hidden proof contract."""


def reconcile_attempt(
    connection_factory: Callable[[str], object],
    proof: ProofProjection,
) -> dict[str, object]:
    """Classify a write attempt as cleanly absent or exactly committed."""

    connection = connection_factory("reconcile")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute("/* phase6:current_user */ SELECT current_user")
            role_row = cursor.fetchone()
            role = role_row[0] if role_row else None
            if role != READONLY_ROLE:
                raise ReconciliationError("readonly_role_mismatch")

            verdict = inspect_state(cursor, proof)
            if verdict.kind == "clean":
                return {
                    "schema_version": "biblical_context_phase6_reconciliation.v1",
                    "status": "absent",
                    "database_connection": READONLY_ROLE,
                    "proof": projection_report(proof),
                    "policy_id": None,
                    "retrieval_matches": None,
                    "reconciliation": {
                        "attempted": 1,
                        "stored": 0,
                        "errored": 1,
                        "skipped": 0,
                    },
                }

            cursor.execute(
                """/* phase6:retrieval_vector */
                SELECT count(*)
                FROM match_chunks(
                  (SELECT embedding FROM chunks WHERE id = %s), 20, true
                )
                WHERE document_id = %s
                """,
                (proof.chunks[0]["id"], proof.document["id"]),
            )
            vector_row = cursor.fetchone()
            vector_count = int(vector_row[0]) if vector_row else 0
            cursor.execute(
                """/* phase6:retrieval_fts */
                SELECT count(*)
                FROM search_chunks_fts(%s, 100, true)
                WHERE document_id = %s
                """,
                (proof.entity_id, proof.document["id"]),
            )
            fts_row = cursor.fetchone()
            fts_count = int(fts_row[0]) if fts_row else 0
            if vector_count != 0 or fts_count != 0:
                raise ReconciliationError("hidden_retrieval_leak")
    finally:
        connection.close()

    return {
        "schema_version": "biblical_context_phase6_reconciliation.v1",
        "status": "verified",
        "database_connection": READONLY_ROLE,
        "proof": projection_report(proof),
        "policy_id": verdict.policy_id,
        "retrieval_matches": {"vector": vector_count, "fts": fts_count},
        "reconciliation": {
            "attempted": 1,
            "stored": 1,
            "errored": 0,
            "skipped": 0,
        },
    }


def reconcile_single_proof(
    connection_factory: Callable[[str], object],
    proof: ProofProjection,
) -> dict[str, object]:
    """Require an exactly committed, hidden proof on a fresh read-only session."""

    report = reconcile_attempt(connection_factory, proof)
    if report["status"] != "verified":
        raise ReconciliationError("proof_not_complete")
    return report


def _load_reconcile_dependencies():
    """Return a factory backed only by the dedicated read-only credential."""

    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv

    load_dotenv(
        ROOT / "backend" / "app" / ".env.readonly-analysis",
        override=True,
    )
    import psycopg2

    database_url = os.environ.get("READONLY_ANALYSIS_DB_URL")
    if not database_url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL is not set")

    def connection_factory(mode: str):
        if mode != "reconcile":
            raise ValueError("reconcile_connection_mode_invalid")
        return psycopg2.connect(database_url)

    return connection_factory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 6 proof through a fresh read-only session."
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("--verify is required")
    report = reconcile_single_proof(
        _load_reconcile_dependencies(),
        build_aaron_projection(ROOT),
    )
    sys.stdout.write(canonical_json_bytes(report).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
