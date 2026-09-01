#!/usr/bin/env python3
"""Attended Phase 6 writer, permanently limited to the one Aaron proof."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    ENTITY_ID,
    MAX_SPEND_USD,
    RECORD_SHA256,
    SOURCE_SLUG,
    ProofProjection,
    build_aaron_projection,
)
from biblical_context_tooling import canonical_json_bytes
from preview_biblical_context_tooling import write_new_preview


ROOT = Path(__file__).resolve().parent.parent
APPROVAL_SCHEMA_VERSION = "biblical_context_phase6_approval.v1"
MAX_APPROVAL_BYTES = 4096
_APPROVAL_KEYS = {
    "schema_version",
    "approved_by",
    "operation_date",
    "source_slug",
    "entity_id",
    "record_sha256",
    "maximum_spend_usd",
    "source_registration_authorized",
    "embedding_request_authorized",
    "single_database_transaction_authorized",
}


class ApprovalError(ValueError):
    """The attended approval artifact does not authorize this exact proof."""


def validate_approval(
    path: Path,
    proof: ProofProjection,
    today: date,
) -> dict[str, object]:
    """Validate a small regular JSON file against the immutable proof identity."""

    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise ApprovalError("approval_missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ApprovalError("approval_not_regular")
    if details.st_size > MAX_APPROVAL_BYTES:
        raise ApprovalError("approval_too_large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ApprovalError("approval_invalid_json") from exc
    if not isinstance(value, dict) or set(value) != _APPROVAL_KEYS:
        raise ApprovalError("approval_fields_invalid")

    expected = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approved_by": "Alex Whitley",
        "operation_date": today.isoformat(),
        "source_slug": SOURCE_SLUG,
        "entity_id": ENTITY_ID,
        "record_sha256": RECORD_SHA256,
        "maximum_spend_usd": MAX_SPEND_USD,
        "source_registration_authorized": True,
        "embedding_request_authorized": True,
        "single_database_transaction_authorized": True,
    }
    if value != expected or proof.entity_id != ENTITY_ID:
        raise ApprovalError("approval_scope_mismatch")
    return value


class StateConflictError(RuntimeError):
    """Live rows are partial, conflicting, or not the exact completed proof."""


class ProofApplyError(RuntimeError):
    """The external embedding boundary failed or returned invalid data."""


@dataclass(frozen=True)
class StateVerdict:
    kind: str
    policy_id: str | None = None


_SOURCE_FIELDS = (
    "id",
    "name",
    "slug",
    "license_status",
    "visibility",
    "permission_terms",
    "notes",
)
_ALIAS_FIELDS = ("id", "alias_key", "alias_display", "source_id", "note")
_DOCUMENT_FIELDS = (
    "id",
    "title",
    "original_title",
    "author",
    "source_name",
    "source_type",
    "source_kind",
    "citation_mode",
    "source",
    "topic_tags",
    "bible_references",
    "file_path",
    "is_copyrighted",
    "full_text",
    "source_id",
    "url",
    "ingest_completed_at",
)
_CHUNK_FIELDS = (
    "id",
    "document_id",
    "content",
    "chunk_index",
    "bible_references",
    "embedding_dimensions",
)
_POLICY_FIELDS = (
    "id",
    "chunk_id",
    "policy_class",
    "protected_topic_keys",
    "issue_key",
    "viewpoint_key",
    "classifier_kind",
    "rule_version",
    "model",
    "prompt_fingerprint",
    "reason_codes",
    "is_current",
)
_POLICY_INSERT_FIELDS = _POLICY_FIELDS[1:]


def _as_mapping(row, fields: tuple[str, ...]) -> dict[str, object] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        value = {field: row.get(field) for field in fields}
    else:
        if len(row) != len(fields):
            raise StateConflictError("proof_state_shape_changed")
        value = dict(zip(fields, row))
    for field in ("id", "source_id", "document_id", "chunk_id"):
        if field in value and value[field] is not None:
            value[field] = str(value[field])
    return value


def _fetch_unique(cursor, sql: str, params: tuple, fields: tuple[str, ...]):
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    if len(rows) > 1:
        raise StateConflictError("proof_state_conflict")
    return _as_mapping(rows[0], fields) if rows else None


def inspect_state(
    cursor,
    proof: ProofProjection,
    *,
    allow_unstamped: bool = False,
) -> StateVerdict:
    """Classify live state as entirely absent or the exact completed proof."""

    source = _fetch_unique(
        cursor,
        """/* phase6:source */
        SELECT id, name, slug, license_status, visibility, permission_terms, notes
        FROM sources WHERE id = %s OR name = %s OR slug = %s
        ORDER BY (id = %s) DESC
        """,
        (
            proof.source["id"],
            proof.source["name"],
            proof.source["slug"],
            proof.source["id"],
        ),
        _SOURCE_FIELDS,
    )
    alias = _fetch_unique(
        cursor,
        """/* phase6:alias */
        SELECT id, alias_key, alias_display, source_id, note
        FROM source_aliases WHERE id = %s OR alias_key = %s
        ORDER BY (id = %s) DESC
        """,
        (proof.alias["id"], proof.alias["alias_key"], proof.alias["id"]),
        _ALIAS_FIELDS,
    )
    document = _fetch_unique(
        cursor,
        """/* phase6:document */
        SELECT id, title, original_title, author, source_name, source_type,
               source_kind, citation_mode, source, topic_tags, bible_references,
               file_path, is_copyrighted, full_text, source_id, url,
               ingest_completed_at
        FROM documents WHERE id = %s OR file_path = %s
        ORDER BY (id = %s) DESC
        """,
        (
            proof.document["id"],
            proof.document["file_path"],
            proof.document["id"],
        ),
        _DOCUMENT_FIELDS,
    )
    chunk = _fetch_unique(
        cursor,
        """/* phase6:chunk */
        SELECT id, document_id, content, chunk_index, bible_references,
               vector_dims(embedding)
        FROM chunks WHERE id = %s OR document_id = %s
        ORDER BY (id = %s) DESC
        """,
        (
            proof.chunks[0]["id"],
            proof.document["id"],
            proof.chunks[0]["id"],
        ),
        _CHUNK_FIELDS,
    )
    cursor.execute(
        """/* phase6:policies */
        SELECT id, chunk_id, policy_class, protected_topic_keys, issue_key,
               viewpoint_key, classifier_kind, rule_version, model,
               prompt_fingerprint, reason_codes, is_current
        FROM source_passage_policy_versions
        WHERE chunk_id = %s AND is_current
        ORDER BY created_at, id
        """,
        (proof.chunks[0]["id"],),
    )
    policies = [_as_mapping(row, _POLICY_FIELDS) for row in cursor.fetchall()]
    cursor.execute(
        """/* phase6:propositions */
        SELECT count(*) FROM propositions WHERE document_id = %s
        """,
        (proof.document["id"],),
    )
    proposition_row = cursor.fetchone()
    proposition_count = int(proposition_row[0]) if proposition_row else 0

    if (
        source is None
        and alias is None
        and document is None
        and chunk is None
        and not policies
        and proposition_count == 0
    ):
        return StateVerdict("clean")

    expected_document = dict(proof.document)
    if document is not None:
        completed = document.pop("ingest_completed_at")
    else:
        completed = None
    expected_chunk = {**dict(proof.chunks[0]), "embedding_dimensions": EMBEDDING_DIMENSIONS}
    expected_policy = dict(proof.policy)
    exact_policy = policies[0] if len(policies) == 1 else None
    policy_id = exact_policy.pop("id") if exact_policy is not None else None
    if (
        source == proof.source
        and alias == proof.alias
        and document == expected_document
        and (completed is not None or allow_unstamped)
        and chunk == expected_chunk
        and exact_policy == expected_policy
        and proposition_count == 0
    ):
        return StateVerdict("exact_complete", str(policy_id))
    raise StateConflictError("proof_state_conflict")


def _approval_matches_proof(
    approval: Mapping[str, object], proof: ProofProjection
) -> bool:
    return (
        approval.get("schema_version") == APPROVAL_SCHEMA_VERSION
        and approval.get("approved_by") == "Alex Whitley"
        and approval.get("source_slug") == SOURCE_SLUG
        and approval.get("entity_id") == proof.entity_id == ENTITY_ID
        and approval.get("record_sha256") == RECORD_SHA256
        and approval.get("maximum_spend_usd") == MAX_SPEND_USD
        and approval.get("source_registration_authorized") is True
        and approval.get("embedding_request_authorized") is True
        and approval.get("single_database_transaction_authorized") is True
    )


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(value) for value in embedding) + "]"


def apply_single_proof(
    connection_factory: Callable[[str], object],
    embed_fn: Callable[..., list[float]],
    proof: ProofProjection,
    approval: Mapping[str, object],
) -> dict[str, object]:
    """Apply one exact proof after preflight; never supports another item."""

    if not _approval_matches_proof(approval, proof):
        raise ApprovalError("approval_scope_mismatch")

    preflight = connection_factory("preflight")
    try:
        if hasattr(preflight, "set_session"):
            preflight.set_session(readonly=True, autocommit=True)
        with preflight.cursor() as cursor:
            verdict = inspect_state(cursor, proof)
    finally:
        preflight.close()
    if verdict.kind == "exact_complete":
        return {
            "status": "skipped",
            "reason": "exact_proof_already_complete",
            "policy_id": verdict.policy_id,
            "reconciliation": {
                "attempted": 1,
                "stored": 0,
                "errored": 0,
                "skipped": 1,
            },
        }

    try:
        raw_embedding = embed_fn(
            proof.text,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
        )
    except Exception as exc:
        raise ProofApplyError("embedding_failed") from exc
    if (
        not isinstance(raw_embedding, list)
        or len(raw_embedding) != EMBEDDING_DIMENSIONS
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in raw_embedding
        )
    ):
        raise ProofApplyError("embedding_invalid")
    embedding = [float(value) for value in raw_embedding]

    try:
        connection = connection_factory("write")
        connection.autocommit = False
    except Exception:
        return {
            "status": "failed",
            "reason": "write_connection_failed",
            "policy_id": None,
            "embedding": {
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "maximum_spend_usd": MAX_SPEND_USD,
            },
            "reconciliation": {
                "attempted": 1,
                "stored": 0,
                "errored": 1,
                "skipped": 0,
            },
        }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            if inspect_state(cursor, proof).kind != "clean":
                raise StateConflictError("proof_state_changed_after_preflight")
            cursor.execute(
                """/* phase6:insert_source */
                INSERT INTO sources
                  (id, name, slug, license_status, visibility,
                   permission_terms, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                tuple(proof.source[field] for field in _SOURCE_FIELDS),
            )
            cursor.execute(
                """/* phase6:insert_alias */
                INSERT INTO source_aliases
                  (id, alias_key, alias_display, source_id, note)
                VALUES (%s, %s, %s, %s, %s)
                """,
                tuple(proof.alias[field] for field in _ALIAS_FIELDS),
            )
            document_fields = _DOCUMENT_FIELDS[:-1]
            cursor.execute(
                """/* phase6:insert_document */
                INSERT INTO documents
                  (id, title, original_title, author, source_name, source_type,
                   source_kind, citation_mode, source, topic_tags,
                   bible_references, file_path, is_copyrighted, full_text,
                   source_id, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                tuple(proof.document[field] for field in document_fields),
            )
            cursor.execute(
                """/* phase6:insert_chunk */
                INSERT INTO chunks
                  (id, document_id, content, embedding, chunk_index,
                   bible_references)
                VALUES (%s, %s, %s, %s::vector, %s, %s)
                """,
                (
                    proof.chunks[0]["id"],
                    proof.chunks[0]["document_id"],
                    proof.chunks[0]["content"],
                    _vector_literal(embedding),
                    proof.chunks[0]["chunk_index"],
                    proof.chunks[0]["bible_references"],
                ),
            )
            cursor.execute(
                """/* phase6:insert_policy */
                INSERT INTO source_passage_policy_versions
                  (chunk_id, policy_class, protected_topic_keys, issue_key,
                   viewpoint_key, classifier_kind, rule_version, model,
                   prompt_fingerprint, reason_codes, is_current)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                tuple(proof.policy[field] for field in _POLICY_INSERT_FIELDS),
            )
            policy_id = str(cursor.fetchone()[0])
            staged = inspect_state(cursor, proof, allow_unstamped=True)
            if staged.policy_id != policy_id:
                raise StateConflictError("staged_policy_identity_mismatch")
            cursor.execute(
                """/* phase6:stamp_complete */
                UPDATE documents SET ingest_completed_at = now() WHERE id = %s
                """,
                (proof.document["id"],),
            )
            inspect_state(cursor, proof)
        connection.commit()
    except Exception as exc:
        connection.rollback()
        connection.close()
        return {
            "status": "failed",
            "reason": type(exc).__name__,
            "policy_id": None,
            "embedding": {
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
                "maximum_spend_usd": MAX_SPEND_USD,
            },
            "reconciliation": {
                "attempted": 1,
                "stored": 0,
                "errored": 1,
                "skipped": 0,
            },
        }
    connection.close()
    return {
        "status": "stored",
        "reason": None,
        "policy_id": policy_id,
        "embedding": {
            "model": EMBEDDING_MODEL,
            "dimensions": EMBEDDING_DIMENSIONS,
            "maximum_spend_usd": MAX_SPEND_USD,
        },
        "reconciliation": {
            "attempted": 1,
            "stored": 1,
            "errored": 0,
            "skipped": 0,
        },
    }


def _load_apply_dependencies():
    """Load the write credential and embedding client only after approval."""

    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2
    from app.services.embeddings import embed_text

    database_url = os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not set")

    def connection_factory(mode: str):
        if mode not in {"preflight", "write"}:
            raise ValueError("apply_connection_mode_invalid")
        return psycopg2.connect(database_url)

    def embedding_adapter(text: str, *, model: str, dimensions: int):
        if model != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
            raise ProofApplyError("embedding_contract_changed")
        return embed_text(text)

    return connection_factory, embedding_adapter


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the attended, single-item Phase 6 Aaron proof."
    )
    parser.add_argument("--approval-file", type=Path, required=True)
    args = parser.parse_args(argv)

    proof = build_aaron_projection(ROOT)
    approval = validate_approval(args.approval_file, proof, date.today())
    connection_factory, embed_fn = _load_apply_dependencies()
    apply_report = apply_single_proof(
        connection_factory, embed_fn, proof, approval
    )

    from reconcile_biblical_context_batch import (
        _load_reconcile_dependencies,
        reconcile_attempt,
    )

    reconciliation = reconcile_attempt(
        _load_reconcile_dependencies(), proof
    )
    if apply_report["status"] == "failed":
        operation_status = (
            "commit_outcome_ambiguous_but_verified"
            if reconciliation["status"] == "verified"
            else "failed_clean"
        )
    elif reconciliation["status"] == "verified":
        operation_status = "verified"
    else:
        raise StateConflictError("apply_reported_success_but_proof_is_absent")
    final_report = {
        "schema_version": "biblical_context_phase6_proof.v1",
        "status": operation_status,
        "approval": approval,
        "apply": apply_report,
        "verification": reconciliation,
    }
    payload = canonical_json_bytes(final_report)
    if reconciliation["status"] == "verified":
        write_new_preview(
            ROOT / "local" / "2026-09" / "biblical_context_v1_proof.json",
            payload,
        )
    sys.stdout.write(payload.decode("utf-8"))
    return 0 if operation_status == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
