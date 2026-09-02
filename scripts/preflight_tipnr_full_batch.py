#!/usr/bin/env python3
"""Prefix-resumable read-only preflight for the remaining TIPNR corpus.

Loads no write or embedding dependency. Classifies live state through an
asserted read-only role and accepts only three shapes: all-clean, all-exact-
complete, or an exact-complete prefix ending on a whole batch boundary
followed by an all-clean suffix.
"""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    SOURCE_ALIAS,
    SOURCE_NAME,
    build_aaron_projection,
)
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from tipnr_full_batch_contract import (
    BATCH_COUNT,
    REMAINING_COUNT,
    ROWS_PER_ITEM,
    FullBatchPacket,
    build_full_batch_packet,
)
from tipnr_hidden_pilot_contract import build_pilot_packet


ROOT = Path(__file__).resolve().parent.parent
READONLY_ROLE = "newwine_readonly_analysis"

_EXPECTED_CONSTRAINTS = (
    "source_passage_policy_versions_classifier_kind_check",
    "source_passage_policy_versions_classifier_metadata_check",
    "source_passage_policy_versions_issue_key_check",
    "source_passage_policy_versions_policy_class_check",
    "source_passage_policy_versions_policy_metadata_check",
    "source_passage_policy_versions_protected_topics_check",
    "source_passage_policy_versions_reason_codes_check",
    "source_passage_policy_versions_rule_version_check",
    "source_passage_policy_versions_viewpoint_key_check",
)
_EXPECTED_INDEXES = (
    "source_passage_policy_versions_chunk_id_idx",
    "source_passage_policy_versions_one_current_idx",
    "source_passage_policy_versions_pkey",
)
_EXPECTED_TRIGGERS = ("source_passage_policy_versions_append_only",)


class FullBatchPreflightError(RuntimeError):
    """Live state is unsafe, mixed, out of order, or outside the contract."""


@dataclass(frozen=True)
class CandidateState:
    entity_id: str
    kind: str
    problem: str | None = None


def _rows(cursor, sql: str, params: tuple = ()):
    cursor.execute(sql, params)
    return cursor.fetchall()


def _require_readonly(cursor) -> None:
    cursor.execute("/* fullbatch:transaction_read_only */ SHOW transaction_read_only")
    row = cursor.fetchone()
    if not row or row[0] != "on":
        raise FullBatchPreflightError("identity_session_not_readonly")
    cursor.execute("/* fullbatch:current_user */ SELECT current_user")
    row = cursor.fetchone()
    if not row or row[0] != READONLY_ROLE:
        raise FullBatchPreflightError("readonly_role_mismatch")


def assert_migration_097(cursor) -> dict[str, object]:
    """Reject any drift in the policy table's structural safety guarantees."""

    table = _rows(
        cursor,
        """/* fullbatch:097_table */
        SELECT c.relrowsecurity FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'source_passage_policy_versions'""",
    )
    if len(table) != 1:
        raise FullBatchPreflightError("migration_097_table_missing")
    if table[0][0] is not True:
        raise FullBatchPreflightError("migration_097_rls_disabled")

    constraints = tuple(sorted(row[0] for row in _rows(
        cursor,
        """/* fullbatch:097_constraints */
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'public.source_passage_policy_versions'::regclass
          AND contype = 'c'""",
    )))
    indexes = tuple(sorted(row[0] for row in _rows(
        cursor,
        """/* fullbatch:097_indexes */
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'source_passage_policy_versions'""",
    )))
    triggers = tuple(sorted(row[0] for row in _rows(
        cursor,
        """/* fullbatch:097_triggers */
        SELECT tgname FROM pg_trigger
        WHERE tgrelid = 'public.source_passage_policy_versions'::regclass
          AND NOT tgisinternal""",
    )))
    if constraints != _EXPECTED_CONSTRAINTS:
        raise FullBatchPreflightError("migration_097_constraint_drift")
    if indexes != _EXPECTED_INDEXES:
        raise FullBatchPreflightError("migration_097_index_drift")
    if triggers != _EXPECTED_TRIGGERS:
        raise FullBatchPreflightError("migration_097_trigger_drift")
    return {
        "row_level_security_enabled": True,
        "check_constraints": list(constraints),
        "indexes": list(indexes),
        "triggers": list(triggers),
    }


def assert_source(cursor, packet: FullBatchPacket) -> dict[str, object]:
    """Require the exact hidden, licensed source and its single alias."""

    source_id = str(packet.source["id"])
    rows = _rows(
        cursor,
        """/* fullbatch:source */
        SELECT id, name, license_status, visibility
        FROM sources WHERE id = %s OR name = %s""",
        (source_id, SOURCE_NAME),
    )
    if len(rows) != 1:
        raise FullBatchPreflightError("source_identity_conflict")
    row = rows[0]
    if str(row[0]) != source_id or row[1] != SOURCE_NAME:
        raise FullBatchPreflightError("source_identity_mismatch")
    if row[2] != "licensed":
        raise FullBatchPreflightError("source_license_drift")
    if row[3] != "hidden":
        raise FullBatchPreflightError("source_visibility_drift")

    aliases = _rows(
        cursor,
        """/* fullbatch:alias */
        SELECT id, alias_key FROM source_aliases WHERE source_id = %s""",
        (source_id,),
    )
    if len(aliases) != 1 or aliases[0][1] != SOURCE_ALIAS:
        raise FullBatchPreflightError("source_alias_drift")
    if str(aliases[0][0]) != str(packet.alias["id"]):
        raise FullBatchPreflightError("source_alias_identity_mismatch")
    return {
        "source_id": source_id,
        "license_status": row[2],
        "visibility": row[3],
        "alias_key": SOURCE_ALIAS,
    }


def _load_live_rows(cursor, items, source_id: str):
    """Bulk-load stored documents, chunks, current policies, and propositions."""

    document_ids = [item.document["id"] for item in items]
    chunk_ids = [item.chunk["id"] for item in items]
    file_paths = [item.document["file_path"] for item in items]

    documents = {}
    for r in _rows(
        cursor,
        """/* fullbatch:documents */
        SELECT id, title, original_title, author, source_name, source_type,
               source_kind, citation_mode, source, topic_tags, bible_references,
               file_path, is_copyrighted, full_text, source_id, url,
               ingest_completed_at
        FROM documents
        WHERE id = ANY(%s::uuid[]) OR file_path = ANY(%s::text[])
           OR source_id = %s::uuid""",
        (document_ids, file_paths, source_id),
    ):
        documents[str(r[0])] = {
            "id": str(r[0]), "title": r[1], "original_title": r[2], "author": r[3],
            "source_name": r[4], "source_type": r[5], "source_kind": r[6],
            "citation_mode": r[7], "source": r[8], "topic_tags": r[9],
            "bible_references": r[10], "file_path": r[11], "is_copyrighted": r[12],
            "full_text": r[13], "source_id": str(r[14]) if r[14] else None,
            "url": r[15], "ingest_completed_at": r[16],
        }

    chunks: dict[str, list] = {}
    for r in _rows(
        cursor,
        """/* fullbatch:chunks */
        SELECT id, document_id, content, chunk_index, bible_references,
               vector_dims(embedding)
        FROM chunks
        WHERE id = ANY(%s::uuid[]) OR document_id = ANY(%s::uuid[])""",
        (chunk_ids, document_ids),
    ):
        chunks.setdefault(str(r[1]), []).append({
            "id": str(r[0]), "document_id": str(r[1]), "content": r[2],
            "chunk_index": r[3], "bible_references": r[4],
            "embedding_dimensions": r[5],
        })

    policies: dict[str, list] = {}
    for r in _rows(
        cursor,
        """/* fullbatch:policies */
        SELECT id, chunk_id, policy_class, protected_topic_keys, issue_key,
               viewpoint_key, classifier_kind, rule_version, model,
               prompt_fingerprint, reason_codes, is_current
        FROM source_passage_policy_versions
        WHERE chunk_id = ANY(%s::uuid[]) AND is_current""",
        (chunk_ids,),
    ):
        policies.setdefault(str(r[1]), []).append({
            "id": str(r[0]), "chunk_id": str(r[1]), "policy_class": r[2],
            "protected_topic_keys": r[3], "issue_key": r[4], "viewpoint_key": r[5],
            "classifier_kind": r[6], "rule_version": r[7], "model": r[8],
            "prompt_fingerprint": r[9], "reason_codes": r[10], "is_current": r[11],
        })

    propositions = {
        str(r[0]): int(r[1])
        for r in _rows(
            cursor,
            """/* fullbatch:propositions */
            SELECT document_id, count(*) FROM propositions
            WHERE document_id = ANY(%s::uuid[]) GROUP BY document_id""",
            (document_ids,),
        )
    }
    return documents, chunks, policies, propositions


def classify_item(item, documents, chunks, policies, propositions) -> CandidateState:
    """Classify one identity as clean or exact-complete; never as partial."""

    document_id = item.document["id"]
    chunk_id = item.chunk["id"]
    stored_document = documents.get(document_id)
    stored_chunks = chunks.get(document_id, [])
    stored_policies = policies.get(chunk_id, [])
    count = propositions.get(document_id, 0)

    if stored_document is None and not stored_chunks and not stored_policies and count == 0:
        return CandidateState(item.entity_id, "clean")
    if stored_document is None:
        return CandidateState(item.entity_id, "conflict", "chunk_or_policy_without_document")
    if count != 0:
        return CandidateState(item.entity_id, "conflict", "proposition_present")
    if len(stored_chunks) != 1:
        return CandidateState(item.entity_id, "conflict", "chunk_cardinality")
    if len(stored_policies) != 1:
        return CandidateState(item.entity_id, "conflict", "policy_cardinality")

    observed = dict(stored_document)
    completed = observed.pop("ingest_completed_at")
    if completed is None:
        return CandidateState(item.entity_id, "conflict", "ingest_not_stamped")
    if observed != item.document:
        return CandidateState(item.entity_id, "conflict", "document_projection_drift")
    expected_chunk = {
        **copy.deepcopy(item.chunk), "embedding_dimensions": EMBEDDING_DIMENSIONS,
    }
    if stored_chunks[0] != expected_chunk:
        return CandidateState(item.entity_id, "conflict", "chunk_projection_drift")
    observed_policy = dict(stored_policies[0])
    observed_policy.pop("id")
    if observed_policy != item.policy:
        return CandidateState(item.entity_id, "conflict", "policy_projection_drift")
    return CandidateState(item.entity_id, "exact_complete")


def _resolve_prefix(packet: FullBatchPacket, states: Sequence[CandidateState]):
    """Require an exact-complete prefix ending on a whole batch boundary."""

    conflicts = [state for state in states if state.kind == "conflict"]
    if conflicts:
        raise FullBatchPreflightError(
            f"candidate_state_conflict:{conflicts[0].entity_id}:{conflicts[0].problem}"
        )

    kinds = [state.kind for state in states]
    complete_total = kinds.count("exact_complete")
    if kinds[:complete_total] != ["exact_complete"] * complete_total:
        raise FullBatchPreflightError("candidate_state_out_of_order")
    if kinds[complete_total:] != ["clean"] * (len(kinds) - complete_total):
        raise FullBatchPreflightError("candidate_state_out_of_order")

    boundary = 0
    completed_batches = 0
    for batch in packet.batches:
        if complete_total >= boundary + batch.size:
            boundary += batch.size
            completed_batches += 1
        else:
            break
    if boundary != complete_total:
        raise FullBatchPreflightError("candidate_state_partial_batch")
    return complete_total, completed_batches


def preflight_full_batch(
    identity_factory: Callable[[str], object],
    packet: FullBatchPacket,
    *,
    pilot_packet=None,
    invariant_checker: Callable[[], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Classify live state and report the exact next safe batch."""

    invariants = invariant_checker() if invariant_checker else _repository_invariants()

    connection = identity_factory("identity")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            _require_readonly(cursor)
            migration = assert_migration_097(cursor)
            source = assert_source(cursor, packet)
            source_id = source["source_id"]

            documents, chunks, policies, propositions = _load_live_rows(
                cursor, packet.items, source_id
            )
            states = [
                classify_item(item, documents, chunks, policies, propositions)
                for item in packet.items
            ]

            pilot_states = []
            if pilot_packet is not None:
                pilot_documents, pilot_chunks, pilot_policies, pilot_props = (
                    _load_live_rows(cursor, pilot_packet.items, source_id)
                )
                pilot_states = [
                    classify_item(item, pilot_documents, pilot_chunks,
                                  pilot_policies, pilot_props)
                    for item in pilot_packet.items
                ]

            cursor.execute(
                """/* fullbatch:source_totals */
                SELECT count(*) FROM documents WHERE source_id = %s::uuid""",
                (source_id,),
            )
            source_documents = int(cursor.fetchone()[0])
            cursor.execute(
                """/* fullbatch:source_propositions */
                SELECT count(*) FROM propositions p
                JOIN documents d ON d.id = p.document_id
                WHERE d.source_id = %s::uuid""",
                (source_id,),
            )
            source_propositions = int(cursor.fetchone()[0])
    finally:
        connection.close()

    if source_propositions != 0:
        raise FullBatchPreflightError("tipnr_propositions_present")
    if pilot_packet is not None and any(s.kind != "exact_complete" for s in pilot_states):
        raise FullBatchPreflightError("pilot_not_exact_complete")

    complete_total, completed_batches = _resolve_prefix(packet, states)
    remaining_items = REMAINING_COUNT - complete_total

    # The stale Phase 6 fixture document is a known pre-existing row until its
    # policy is demoted under separate attended authorization.
    known_documents = {item.document["id"] for item in packet.items}
    if pilot_packet is not None:
        known_documents |= {item.document["id"] for item in pilot_packet.items}
    fixture_document_id = str(build_aaron_projection(ROOT).document["id"])
    unknown = sorted(
        document_id for document_id in documents
        if document_id not in known_documents and document_id != fixture_document_id
    )
    if unknown:
        raise FullBatchPreflightError("unknown_source_documents")

    if complete_total == 0:
        candidate_state = "all_clean"
    elif complete_total == REMAINING_COUNT:
        candidate_state = "all_exact_complete"
    else:
        candidate_state = "exact_complete_prefix"

    report = {
        "schema_version": "biblical_context_tipnr_full_batch_preflight.v1",
        "status": "ready",
        "database_write_authorized": False,
        "external_model_call_authorized": False,
        "connection_role": READONLY_ROLE,
        "packet_sha256": packet.packet_sha256,
        "migration_097": migration,
        "source": source,
        "repository_invariants": invariants,
        "candidate_state": candidate_state,
        "counts": {
            "eligible_remaining_total": REMAINING_COUNT,
            "exact_complete": complete_total,
            "clean": remaining_items,
            "completed_batches": completed_batches,
            "source_documents": source_documents,
            "tipnr_propositions": source_propositions,
        },
        "next_batch_index": (
            None if completed_batches >= BATCH_COUNT else completed_batches + 1
        ),
        "next_batch_sha256": (
            None if completed_batches >= BATCH_COUNT
            else packet.batches[completed_batches].batch_sha256
        ),
        "remaining_ceilings": {
            "embedding_requests": remaining_items,
            "rows": remaining_items * ROWS_PER_ITEM,
            "transactions": BATCH_COUNT - completed_batches,
        },
        "pilot_exact_complete": len(pilot_states) if pilot_packet is not None else None,
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def _repository_invariants() -> dict[str, object]:
    backend = ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from app.services import answer_toolbox
    from app.services.source_use_policy import (
        ISSUE_REGISTRY,
        PROTECTED_TOPIC_KEYS,
        ApprovedProtectedSourceRegistry,
    )

    if answer_toolbox.BIBLICAL_CONTEXT_ANSWER_ENABLED:
        raise FullBatchPreflightError("biblical_context_answer_default_enabled")
    empty = ApprovedProtectedSourceRegistry({})
    if any(empty.allowed_source_ids((key,)) for key in PROTECTED_TOPIC_KEYS):
        raise FullBatchPreflightError("protected_source_registry_populated")
    if any(entry.registered_source_ids_by_slot for entry in ISSUE_REGISTRY.entries):
        raise FullBatchPreflightError("plural_source_registry_populated")
    return {
        "biblical_context_answer_enabled": False,
        "protected_source_registry": "empty",
        "plural_viewpoint_registry": "empty",
    }


def _load_identity_factory():
    """Return only a read-only identity factory; never a write or model client."""

    sys.path.insert(0, str(ROOT / "backend"))
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env.readonly-analysis", override=True)
    import psycopg2

    url = os.environ.get("READONLY_ANALYSIS_DB_URL")
    if not url:
        raise FullBatchPreflightError("readonly_analysis_url_missing")

    def identity_factory(mode: str):
        if mode != "identity":
            raise ValueError("identity_connection_mode_invalid")
        return psycopg2.connect(url)

    return identity_factory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for the remaining TIPNR corpus."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("--verify is required")

    packet = build_full_batch_packet(ROOT, args.artifact)
    pilot = build_pilot_packet(ROOT, args.artifact)
    report = preflight_full_batch(
        _load_identity_factory(), packet, pilot_packet=pilot
    )
    payload = canonical_json_bytes(report)
    if args.output is not None:
        from preview_biblical_context_tooling import write_new_preview

        write_new_preview(args.output, payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
