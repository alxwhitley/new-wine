#!/usr/bin/env python3
"""Fresh read-only reconciliation for the exact Phase 8 TIPNR hidden pilot."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Callable, Sequence

from apply_tipnr_hidden_pilot import _verify_source_alias
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preflight_tipnr_hidden_pilot import READONLY_ROLE, inspect_pilot_item
from tipnr_hidden_pilot_contract import SAMPLE_IDS, PilotPacket, build_pilot_packet


ROOT = Path(__file__).resolve().parent.parent


class PilotReconciliationError(RuntimeError):
    """Fresh evidence does not prove exact hidden pilot state."""


def _require_session(cursor, *, identity: bool) -> str:
    cursor.execute("/* phase8:transaction_read_only */ SHOW transaction_read_only")
    row = cursor.fetchone()
    if not row or row[0] != "on":
        raise PilotReconciliationError("session_not_readonly")
    cursor.execute("/* phase8:current_user */ SELECT current_user")
    row = cursor.fetchone()
    role = str(row[0]) if row else ""
    if identity and role != READONLY_ROLE:
        raise PilotReconciliationError("readonly_role_mismatch")
    if not identity and (not role or role == READONLY_ROLE):
        raise PilotReconciliationError("retrieval_role_invalid")
    return role


def build_sample_report(packet: PilotPacket) -> dict[str, object]:
    """Return exact first/middle/last samples using only approved structural fields."""

    by_id = {item.entity_id: item for item in packet.items}
    if set(SAMPLE_IDS).difference(by_id):
        raise PilotReconciliationError("sample_identity_missing")
    items = []
    for entity_id in SAMPLE_IDS:
        item = by_id[entity_id]
        items.append({
            "entity_id": item.entity_id,
            "entity_type": item.entity_type,
            "record_sha256": item.record["record_sha256"],
            "rendered_sha256": item.rendered_sha256,
            "source": {
                "id": packet.source["id"],
                "name": packet.source["name"],
                "slug": packet.source["slug"],
                "visibility": packet.source["visibility"],
            },
            "original_language_forms": copy.deepcopy(item.record["original_language_forms"]),
            "policy_class": item.policy["policy_class"],
        })
    report: dict[str, object] = {
        "schema_version": "biblical_context_tipnr_hidden_pilot_sample.v1",
        "packet_sha256": packet.packet_sha256,
        "items": items,
    }
    report["sample_sha256"] = canonical_sha256(report)
    return report


def reconcile_pilot(
    identity_factory: Callable[[str], object],
    retrieval_factory: Callable[[str], object],
    packet: PilotPacket,
) -> dict[str, object]:
    """Require all 20 exact rows and zero matches from all 40 retrieval probes."""

    identity = identity_factory("identity")
    policy_ids: list[str] = []
    try:
        identity.set_session(readonly=True, autocommit=True)
        with identity.cursor() as cursor:
            role = _require_session(cursor, identity=True)
            try:
                _verify_source_alias(cursor, packet)
            except Exception as exc:
                raise PilotReconciliationError("source_alias_state_conflict") from exc
            for item in packet.items:
                state = inspect_pilot_item(cursor, item)
                if state.kind != "exact_complete" or state.policy_id is None:
                    raise PilotReconciliationError("candidate_not_complete")
                policy_ids.append(state.policy_id)
    finally:
        identity.close()

    vector_matches = 0
    fts_matches = 0
    retrieval = retrieval_factory("retrieval")
    try:
        retrieval.set_session(readonly=True, autocommit=True)
        with retrieval.cursor() as cursor:
            retrieval_role = _require_session(cursor, identity=False)
            for item in packet.items:
                cursor.execute(
                    """/* phase8:retrieval_vector */
                    SELECT count(*) FROM match_chunks(
                      (SELECT embedding FROM chunks WHERE id = %s), 20, true
                    ) WHERE document_id = %s""",
                    (item.chunk["id"], item.document["id"]),
                )
                row = cursor.fetchone()
                vector_matches += int(row[0]) if row else 0
                cursor.execute(
                    """/* phase8:retrieval_fts */
                    SELECT count(*) FROM search_chunks_fts(%s, 100, true)
                    WHERE document_id = %s""",
                    (item.entity_id, item.document["id"]),
                )
                row = cursor.fetchone()
                fts_matches += int(row[0]) if row else 0
    finally:
        retrieval.close()
    if vector_matches or fts_matches:
        raise PilotReconciliationError("hidden_retrieval_leak")

    sample = build_sample_report(packet)
    report: dict[str, object] = {
        "schema_version": "biblical_context_tipnr_hidden_pilot_reconciliation.v1",
        "status": "verified",
        "packet_sha256": packet.packet_sha256,
        "database_connections": {
            "identity": role,
            "retrieval": f"{retrieval_role} (read-only session)",
        },
        "policy_ids": policy_ids,
        "retrieval_probes": {
            "vector_attempted": 20, "vector_matches": 0,
            "fts_attempted": 20, "fts_matches": 0,
        },
        "reconciliation": {
            "attempted": 20, "stored": 20, "errored": 0, "skipped": 0,
        },
        "sample": sample,
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fresh read-only verification of the Phase 8 pilot.")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("--verify is required")
    packet = build_pilot_packet(ROOT, args.artifact)
    from reconcile_biblical_context_batch import _load_reconcile_dependencies
    identity_factory, retrieval_factory = _load_reconcile_dependencies()
    sys.stdout.buffer.write(canonical_json_bytes(
        reconcile_pilot(identity_factory, retrieval_factory, packet)
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
