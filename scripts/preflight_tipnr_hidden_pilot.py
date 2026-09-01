#!/usr/bin/env python3
"""Read-only Phase 8 preflight for the exact balanced TIPNR hidden pilot."""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_ingest_contract import EMBEDDING_DIMENSIONS, ProofProjection, build_aaron_projection
from biblical_context_tooling import canonical_json_bytes
from reconcile_biblical_context_batch import READONLY_ROLE, reconcile_single_proof
from tipnr_hidden_pilot_contract import PilotItem, PilotPacket, build_pilot_packet


ROOT = Path(__file__).resolve().parent.parent


class PilotPreflightError(RuntimeError):
    """Live state is unsafe, ambiguous, or outside the Phase 8 contract."""


@dataclass(frozen=True)
class CandidateState:
    kind: str
    policy_id: str | None = None


_DOCUMENT_FIELDS = tuple((
    "id", "title", "original_title", "author", "source_name", "source_type",
    "source_kind", "citation_mode", "source", "topic_tags", "bible_references",
    "file_path", "is_copyrighted", "full_text", "source_id", "url",
    "ingest_completed_at",
))
_CHUNK_FIELDS = ("id", "document_id", "content", "chunk_index", "bible_references", "embedding_dimensions")
_POLICY_FIELDS = (
    "id", "chunk_id", "policy_class", "protected_topic_keys", "issue_key",
    "viewpoint_key", "classifier_kind", "rule_version", "model",
    "prompt_fingerprint", "reason_codes", "is_current",
)


def _mapping(row, fields: tuple[str, ...]) -> dict[str, object] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        value = {field: row.get(field) for field in fields}
    else:
        if len(row) != len(fields):
            raise PilotPreflightError("candidate_state_shape_changed")
        value = dict(zip(fields, row))
    for field in ("id", "source_id", "document_id", "chunk_id"):
        if field in value and value[field] is not None:
            value[field] = str(value[field])
    return value


def _unique(cursor, sql: str, params: tuple, fields: tuple[str, ...]):
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    if len(rows) > 1:
        raise PilotPreflightError("candidate_state_conflict")
    return _mapping(rows[0], fields) if rows else None


def inspect_pilot_item(cursor, item: PilotItem) -> CandidateState:
    """Classify one candidate as absent or exact-complete; reject all partial state."""

    document = _unique(
        cursor,
        """/* phase8:document */
        SELECT id, title, original_title, author, source_name, source_type,
               source_kind, citation_mode, source, topic_tags, bible_references,
               file_path, is_copyrighted, full_text, source_id, url,
               ingest_completed_at
        FROM documents WHERE id = %s OR file_path = %s
        ORDER BY (id = %s) DESC""",
        (item.document["id"], item.document["file_path"], item.document["id"]),
        _DOCUMENT_FIELDS,
    )
    chunk = _unique(
        cursor,
        """/* phase8:chunk */
        SELECT id, document_id, content, chunk_index, bible_references,
               vector_dims(embedding)
        FROM chunks WHERE id = %s OR document_id = %s
        ORDER BY (id = %s) DESC""",
        (item.chunk["id"], item.document["id"], item.chunk["id"]),
        _CHUNK_FIELDS,
    )
    cursor.execute(
        """/* phase8:policies */
        SELECT id, chunk_id, policy_class, protected_topic_keys, issue_key,
               viewpoint_key, classifier_kind, rule_version, model,
               prompt_fingerprint, reason_codes, is_current
        FROM source_passage_policy_versions
        WHERE chunk_id = %s AND is_current ORDER BY created_at, id""",
        (item.chunk["id"],),
    )
    policies = [_mapping(row, _POLICY_FIELDS) for row in cursor.fetchall()]
    cursor.execute(
        """/* phase8:propositions */
        SELECT count(*) FROM propositions WHERE document_id = %s""",
        (item.document["id"],),
    )
    row = cursor.fetchone()
    propositions = int(row[0]) if row else 0

    if document is None and chunk is None and not policies and propositions == 0:
        return CandidateState("clean")

    expected_document = copy.deepcopy(item.document)
    completed = document.pop("ingest_completed_at") if document is not None else None
    expected_chunk = {**copy.deepcopy(item.chunk), "embedding_dimensions": EMBEDDING_DIMENSIONS}
    policy = policies[0] if len(policies) == 1 else None
    policy_id = policy.pop("id") if policy is not None else None
    if (
        document == expected_document
        and completed is not None
        and chunk == expected_chunk
        and policy == item.policy
        and propositions == 0
    ):
        return CandidateState("exact_complete", str(policy_id))
    raise PilotPreflightError("candidate_state_conflict")


def _require_readonly(cursor) -> None:
    cursor.execute("/* phase8:transaction_read_only */ SHOW transaction_read_only")
    row = cursor.fetchone()
    if not row or row[0] != "on":
        raise PilotPreflightError("identity_session_not_readonly")
    cursor.execute("/* phase8:current_user */ SELECT current_user")
    row = cursor.fetchone()
    if not row or row[0] != READONLY_ROLE:
        raise PilotPreflightError("readonly_role_mismatch")


def _repository_invariants() -> None:
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
        raise PilotPreflightError("biblical_context_answer_default_enabled")
    empty = ApprovedProtectedSourceRegistry({})
    if any(empty.allowed_source_ids((key,)) for key in PROTECTED_TOPIC_KEYS):
        raise PilotPreflightError("protected_source_registry_populated")
    if any(entry.registered_source_ids_by_slot for entry in ISSUE_REGISTRY.entries):
        raise PilotPreflightError("plural_source_registry_populated")


def preflight_pilot(
    identity_factory: Callable[[str], object],
    retrieval_factory: Callable[[str], object],
    packet: PilotPacket,
    proof: ProofProjection,
    *,
    proof_verifier: Callable[..., dict[str, object]] = reconcile_single_proof,
    invariant_checker: Callable[[], None] = _repository_invariants,
) -> dict[str, object]:
    """Require exact H0175 plus a unanimous clean or complete 20-item state."""

    invariant_checker()
    single = proof_verifier(identity_factory, retrieval_factory, proof)
    if single.get("status") != "verified":
        raise PilotPreflightError("single_item_verification_failed")

    connection = identity_factory("identity")
    try:
        connection.set_session(readonly=True, autocommit=True)
        with connection.cursor() as cursor:
            _require_readonly(cursor)
            states = [inspect_pilot_item(cursor, item) for item in packet.items]
    finally:
        connection.close()
    counts = {
        "clean": sum(state.kind == "clean" for state in states),
        "exact_complete": sum(state.kind == "exact_complete" for state in states),
    }
    if counts == {"clean": 20, "exact_complete": 0}:
        candidate_state = "all_clean"
    elif counts == {"clean": 0, "exact_complete": 20}:
        candidate_state = "all_exact_complete"
    else:
        raise PilotPreflightError("candidate_state_mixed")
    return {
        "schema_version": "biblical_context_tipnr_hidden_pilot_preflight.v1",
        "status": "verified",
        "packet_sha256": packet.packet_sha256,
        "single_item_verification": single,
        "candidate_state": candidate_state,
        "counts": counts,
        "policy_ids": [state.policy_id for state in states if state.policy_id],
        "database_write_authorized": False,
        "external_model_call_authorized": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight for the exact Phase 8 pilot.")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if not args.verify:
        parser.error("--verify is required")

    packet = build_pilot_packet(ROOT, args.artifact)
    proof = build_aaron_projection(ROOT)
    from reconcile_biblical_context_batch import _load_reconcile_dependencies
    identity_factory, retrieval_factory = _load_reconcile_dependencies()
    sys.stdout.buffer.write(canonical_json_bytes(
        preflight_pilot(identity_factory, retrieval_factory, packet, proof)
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
