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


def _require_readonly_session(cursor, boundary: str) -> None:
    cursor.execute("/* phase6:transaction_read_only */ SHOW transaction_read_only")
    row = cursor.fetchone()
    if not row or row[0] != "on":
        raise ReconciliationError(f"{boundary}_session_not_readonly")


def reconcile_attempt(
    identity_connection_factory: Callable[[str], object],
    retrieval_connection_factory: Callable[[str], object],
    proof: ProofProjection,
) -> dict[str, object]:
    """Reconcile exact rows and retrieval exclusion in separate read-only sessions."""

    connection = identity_connection_factory("identity")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            _require_readonly_session(cursor, "identity")
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
                    "database_connections": {
                        "identity": READONLY_ROLE,
                        "retrieval": None,
                    },
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

    finally:
        connection.close()

    retrieval_connection = retrieval_connection_factory("retrieval")
    try:
        retrieval_connection.set_session(readonly=True, autocommit=True)
        with retrieval_connection.cursor() as cursor:
            _require_readonly_session(cursor, "retrieval")
            cursor.execute("/* phase6:current_user */ SELECT current_user")
            retrieval_role_row = cursor.fetchone()
            retrieval_role = retrieval_role_row[0] if retrieval_role_row else None
            if not retrieval_role or retrieval_role == READONLY_ROLE:
                raise ReconciliationError("retrieval_role_invalid")

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
        retrieval_connection.close()

    return {
        "schema_version": "biblical_context_phase6_reconciliation.v1",
        "status": "verified",
        "database_connections": {
            "identity": READONLY_ROLE,
            "retrieval": f"{retrieval_role} (read-only session)",
        },
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
    identity_connection_factory: Callable[[str], object],
    retrieval_connection_factory: Callable[[str], object],
    proof: ProofProjection,
) -> dict[str, object]:
    """Require an exactly committed, hidden proof on a fresh read-only session."""

    report = reconcile_attempt(
        identity_connection_factory, retrieval_connection_factory, proof
    )
    if report["status"] != "verified":
        raise ReconciliationError("proof_not_complete")
    return report


def _load_reconcile_dependencies():
    """Return separate identity and retrieval factories for read-only sessions."""

    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv

    load_dotenv(
        ROOT / "backend" / "app" / ".env.readonly-analysis",
        override=True,
    )
    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2

    identity_database_url = os.environ.get("READONLY_ANALYSIS_DB_URL")
    retrieval_database_url = os.environ.get("SUPABASE_DB_URL")
    if not identity_database_url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL is not set")
    if not retrieval_database_url:
        raise RuntimeError("SUPABASE_DB_URL is not set")

    def identity_connection_factory(mode: str):
        if mode != "identity":
            raise ValueError("identity_connection_mode_invalid")
        return psycopg2.connect(identity_database_url)

    def retrieval_connection_factory(mode: str):
        if mode != "retrieval":
            raise ValueError("retrieval_connection_mode_invalid")
        return psycopg2.connect(retrieval_database_url)

    return identity_connection_factory, retrieval_connection_factory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 6 proof through a fresh read-only session."
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("--verify is required")
    identity_factory, retrieval_factory = _load_reconcile_dependencies()
    report = reconcile_single_proof(
        identity_factory, retrieval_factory, build_aaron_projection(ROOT)
    )
    sys.stdout.write(canonical_json_bytes(report).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
