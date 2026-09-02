#!/usr/bin/env python3
"""Fresh read-only reconciliation for each committed TIPNR batch and the whole corpus.

Every check runs on connections opened after the writer closed, never on the
writer's own session. Hidden-retrieval probes require zero matches while the
answer feature remains off.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_ingest_contract import build_aaron_projection
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preflight_tipnr_full_batch import (
    READONLY_ROLE,
    _load_live_rows,
    _require_readonly,
    assert_source,
    classify_item,
)
from tipnr_full_batch_contract import (
    ELIGIBLE_COUNT,
    GLOBAL_CURRENT_POLICIES,
    GLOBAL_DOCUMENTS,
    REMAINING_COUNT,
    ROWS_PER_ITEM,
    FullBatch,
    FullBatchPacket,
    build_full_batch_packet,
)
from tipnr_hidden_pilot_contract import build_pilot_packet


ROOT = Path(__file__).resolve().parent.parent


class FullBatchReconciliationError(RuntimeError):
    """Fresh read-only evidence does not prove the committed contract."""


def _classify_all(cursor, items, source_id: str):
    documents, chunks, policies, propositions = _load_live_rows(
        cursor, items, source_id
    )
    return [
        classify_item(item, documents, chunks, policies, propositions)
        for item in items
    ]


def reconcile_batch(
    identity_factory: Callable[[str], object],
    packet: FullBatchPacket,
    batch: FullBatch,
    *,
    retrieval_factory: Callable[[str], object] | None = None,
) -> dict[str, object]:
    """Require the committed prefix exact, the suffix clean, and zero propositions."""

    completed_through = batch.index * 0
    for candidate in packet.batches:
        if candidate.index <= batch.index:
            completed_through += candidate.size

    connection = identity_factory("identity")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            _require_readonly(cursor)
            source = assert_source(cursor, packet)
            source_id = source["source_id"]
            states = _classify_all(cursor, packet.items, source_id)
            cursor.execute(
                """/* fullbatch:reconcile_propositions */
                SELECT count(*) FROM propositions p
                JOIN documents d ON d.id = p.document_id
                WHERE d.source_id = %s::uuid""",
                (source_id,),
            )
            propositions = int(cursor.fetchone()[0])
    finally:
        connection.close()

    conflicts = [state for state in states if state.kind == "conflict"]
    if conflicts:
        raise FullBatchReconciliationError(
            f"candidate_state_conflict:{conflicts[0].entity_id}:{conflicts[0].problem}"
        )
    prefix = [state.kind for state in states[:completed_through]]
    suffix = [state.kind for state in states[completed_through:]]
    if prefix != ["exact_complete"] * completed_through:
        raise FullBatchReconciliationError("committed_prefix_not_exact")
    if suffix != ["clean"] * len(suffix):
        raise FullBatchReconciliationError("suffix_not_clean")
    if propositions != 0:
        raise FullBatchReconciliationError("tipnr_propositions_present")

    retrieval = None
    if retrieval_factory is not None:
        retrieval = probe_hidden_retrieval(retrieval_factory, batch)

    stored = batch.size
    report = {
        "schema_version": "biblical_context_tipnr_full_batch_reconciliation.v1",
        "status": "verified",
        "connection_role": READONLY_ROLE,
        "batch_index": batch.index,
        "batch_sha256": batch.batch_sha256,
        "packet_sha256": packet.packet_sha256,
        "counts": {
            "completed_through": completed_through,
            "exact_complete": len([s for s in states if s.kind == "exact_complete"]),
            "clean": len([s for s in states if s.kind == "clean"]),
            "tipnr_propositions": propositions,
        },
        "reconciliation": {
            "attempted": batch.size,
            "stored": stored,
            "errored": 0,
            "skipped": 0,
            "rows": stored * ROWS_PER_ITEM,
        },
        "hidden_retrieval": retrieval,
    }
    attempted = report["reconciliation"]["attempted"]
    resolved = (
        report["reconciliation"]["stored"]
        + report["reconciliation"]["errored"]
        + report["reconciliation"]["skipped"]
    )
    if attempted != resolved:
        raise FullBatchReconciliationError("reconciliation_counters_do_not_balance")
    report["payload_sha256"] = canonical_sha256(report)
    return report


def probe_hidden_retrieval(
    retrieval_factory: Callable[[str], object], batch: FullBatch
) -> dict[str, object]:
    """Require zero vector and zero FTS matches for every newly completed item."""

    connection = retrieval_factory("retrieval")
    vector_matches = 0
    fts_matches = 0
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            cursor.execute(
                "/* fullbatch:retrieval_readonly */ SHOW transaction_read_only"
            )
            row = cursor.fetchone()
            if not row or row[0] != "on":
                raise FullBatchReconciliationError("retrieval_session_not_readonly")
            for item in batch.items:
                cursor.execute(
                    """/* fullbatch:retrieval_vector */
                    SELECT count(*) FROM match_chunks(
                      (SELECT embedding FROM chunks WHERE id = %s), 20, true
                    ) WHERE document_id = %s""",
                    (item.chunk["id"], item.document["id"]),
                )
                vector_matches += int(cursor.fetchone()[0])
                cursor.execute(
                    """/* fullbatch:retrieval_fts */
                    SELECT count(*) FROM search_chunks_fts(%s, 100, true)
                    WHERE document_id = %s""",
                    (item.entity_id, item.document["id"]),
                )
                fts_matches += int(cursor.fetchone()[0])
    finally:
        connection.close()

    if vector_matches != 0 or fts_matches != 0:
        raise FullBatchReconciliationError("hidden_retrieval_leak")
    return {
        "items_probed": batch.size,
        "vector_matches": vector_matches,
        "fts_matches": fts_matches,
    }


def reconcile_global(
    identity_factory: Callable[[str], object],
    packet: FullBatchPacket,
    pilot_packet,
    *,
    noneligible_document_ids: Sequence[str] = (),
) -> dict[str, object]:
    """Require every eligible identity exact-complete and all exclusions absent."""

    fixture_document_id = str(build_aaron_projection(ROOT).document["id"])

    connection = identity_factory("identity")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            _require_readonly(cursor)
            source = assert_source(cursor, packet)
            source_id = source["source_id"]

            remaining_states = _classify_all(cursor, packet.items, source_id)
            pilot_states = _classify_all(cursor, pilot_packet.items, source_id)

            cursor.execute(
                """/* fullbatch:global_documents */
                SELECT count(*) FROM documents WHERE source_id = %s::uuid""",
                (source_id,),
            )
            documents = int(cursor.fetchone()[0])
            cursor.execute(
                """/* fullbatch:global_chunks */
                SELECT count(*) FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.source_id = %s::uuid""",
                (source_id,),
            )
            chunks = int(cursor.fetchone()[0])
            cursor.execute(
                """/* fullbatch:global_policies */
                SELECT count(*) FROM source_passage_policy_versions v
                JOIN chunks c ON c.id = v.chunk_id
                JOIN documents d ON d.id = c.document_id
                WHERE d.source_id = %s::uuid AND v.is_current""",
                (source_id,),
            )
            current_policies = int(cursor.fetchone()[0])
            cursor.execute(
                """/* fullbatch:global_propositions */
                SELECT count(*) FROM propositions p
                JOIN documents d ON d.id = p.document_id
                WHERE d.source_id = %s::uuid""",
                (source_id,),
            )
            propositions = int(cursor.fetchone()[0])
            cursor.execute(
                """/* fullbatch:fixture_policy */
                SELECT count(*) FROM source_passage_policy_versions v
                JOIN chunks c ON c.id = v.chunk_id
                WHERE c.document_id = %s::uuid AND v.is_current""",
                (fixture_document_id,),
            )
            fixture_current_policies = int(cursor.fetchone()[0])

            excluded_present = 0
            if noneligible_document_ids:
                cursor.execute(
                    """/* fullbatch:excluded_absent */
                    SELECT count(*) FROM documents WHERE id = ANY(%s::uuid[])""",
                    (list(noneligible_document_ids),),
                )
                excluded_present = int(cursor.fetchone()[0])
    finally:
        connection.close()

    problems: list[str] = []
    if any(state.kind != "exact_complete" for state in remaining_states):
        problems.append("remaining_not_exact_complete")
    if any(state.kind != "exact_complete" for state in pilot_states):
        problems.append("pilot_not_exact_complete")
    if propositions != 0:
        problems.append("tipnr_propositions_present")
    if current_policies != GLOBAL_CURRENT_POLICIES:
        problems.append("current_policy_total_mismatch")
    if documents != GLOBAL_DOCUMENTS:
        problems.append("document_total_mismatch")
    if chunks != GLOBAL_DOCUMENTS:
        problems.append("chunk_total_mismatch")
    if fixture_current_policies != 0:
        problems.append("stale_fixture_policy_still_current")
    if excluded_present:
        problems.append("excluded_identity_present")

    exact_total = (
        len([s for s in remaining_states if s.kind == "exact_complete"])
        + len([s for s in pilot_states if s.kind == "exact_complete"])
    )
    if exact_total != ELIGIBLE_COUNT:
        problems.append("eligible_exact_total_mismatch")

    report = {
        "schema_version": "biblical_context_tipnr_full_batch_global.v1",
        "status": "verified" if not problems else "blocked",
        "connection_role": READONLY_ROLE,
        "packet_sha256": packet.packet_sha256,
        "source": source,
        "counts": {
            "eligible_exact_complete": exact_total,
            "eligible_expected": ELIGIBLE_COUNT,
            "this_run_stored": REMAINING_COUNT,
            "pre_existing_pilot": len(pilot_packet.items),
            "documents": documents,
            "chunks": chunks,
            "current_policies": current_policies,
            "tipnr_propositions": propositions,
            "stale_fixture_current_policies": fixture_current_policies,
            "excluded_identities_present": excluded_present,
        },
        "inventory_accounting": {
            "attempted": ELIGIBLE_COUNT,
            "stored": exact_total,
            "errored": ELIGIBLE_COUNT - exact_total,
            "skipped": 0,
        },
        "sample_ids": list(packet.sample_ids),
        "problems": problems,
    }
    report["payload_sha256"] = canonical_sha256(report)
    if problems:
        raise FullBatchReconciliationError(
            "global_reconciliation_failed:" + ",".join(problems)
        )
    return report


def _load_factories():
    """Return separate read-only identity and retrieval factories."""

    sys.path.insert(0, str(ROOT / "backend"))
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env.readonly-analysis", override=True)
    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2

    identity_url = os.environ.get("READONLY_ANALYSIS_DB_URL")
    retrieval_url = os.environ.get("SUPABASE_DB_URL")
    if not identity_url:
        raise FullBatchReconciliationError("readonly_analysis_url_missing")
    if not retrieval_url:
        raise FullBatchReconciliationError("retrieval_url_missing")

    def identity_factory(mode: str):
        if mode != "identity":
            raise ValueError("identity_connection_mode_invalid")
        return psycopg2.connect(identity_url)

    def retrieval_factory(mode: str):
        if mode != "retrieval":
            raise ValueError("retrieval_connection_mode_invalid")
        return psycopg2.connect(retrieval_url)

    return identity_factory, retrieval_factory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile committed TIPNR batches through fresh read-only sessions."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--global", dest="run_global", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    packet = build_full_batch_packet(ROOT, args.artifact)
    pilot = build_pilot_packet(ROOT, args.artifact)
    identity_factory, _ = _load_factories()
    if not args.run_global:
        parser.error("--global is required for a standalone run")
    report = reconcile_global(identity_factory, packet, pilot)
    payload = canonical_json_bytes(report)
    if args.output is not None:
        from preview_biblical_context_tooling import write_new_preview

        write_new_preview(args.output, payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
