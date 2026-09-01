#!/usr/bin/env python3
"""Attended, approval-gated atomic writer for the exact Phase 8 TIPNR pilot."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_ingest_contract import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, SOURCE_SLUG
from biblical_context_tooling import canonical_json_bytes
from preflight_tipnr_hidden_pilot import inspect_pilot_item
from tipnr_hidden_pilot_contract import PilotPacket, build_pilot_packet


ROOT = Path(__file__).resolve().parent.parent
APPROVAL_SCHEMA_VERSION = "biblical_context_tipnr_hidden_pilot_approval.v1"
MAX_APPROVAL_BYTES = 8192


class PilotApprovalError(ValueError):
    """The attended approval does not match the exact same-day packet."""


class PilotApplyError(RuntimeError):
    """The vector or atomic write boundary failed."""


def _expected_approval(packet: PilotPacket, today: date) -> dict[str, object]:
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approved_by": "Alex Whitley",
        "operation_date": today.isoformat(),
        "source_slug": SOURCE_SLUG,
        "packet_sha256": packet.packet_sha256,
        "selection_checksum": packet.selection_checksum,
        "item_count": 20,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "maximum_embedding_requests": 20,
        "maximum_spend_usd": packet.maximum_spend_usd,
        "embedding_requests_authorized": True,
        "single_database_transaction_authorized": True,
    }


def validate_pilot_approval(path: Path, packet: PilotPacket, today: date) -> dict[str, object]:
    """Accept only a small regular one-link JSON file matching the whole packet."""

    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise PilotApprovalError("approval_missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise PilotApprovalError("approval_not_regular")
    if details.st_size > MAX_APPROVAL_BYTES:
        raise PilotApprovalError("approval_too_large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotApprovalError("approval_invalid_json") from exc
    if value != _expected_approval(packet, today):
        raise PilotApprovalError("approval_scope_mismatch")
    return value


def _validate_approval_mapping(approval: Mapping[str, object], packet: PilotPacket) -> None:
    if dict(approval) != _expected_approval(packet, date.today()):
        raise PilotApprovalError("approval_scope_mismatch")


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(value) for value in vector) + "]"


def _validate_vector(value: object) -> list[float]:
    if (
        not isinstance(value, list)
        or len(value) != EMBEDDING_DIMENSIONS
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in value
        )
    ):
        raise PilotApplyError("embedding_invalid")
    return [float(item) for item in value]


def _verify_source_alias(cursor, packet: PilotPacket) -> None:
    cursor.execute(
        """/* phase8:source */
        SELECT id, name, slug, license_status, visibility, permission_terms, notes
        FROM sources WHERE id = %s OR name = %s OR slug = %s""",
        (packet.source["id"], packet.source["name"], packet.source["slug"]),
    )
    sources = cursor.fetchall()
    cursor.execute(
        """/* phase8:alias */
        SELECT id, alias_key, alias_display, source_id, note
        FROM source_aliases WHERE id = %s OR alias_key = %s""",
        (packet.alias["id"], packet.alias["alias_key"]),
    )
    aliases = cursor.fetchall()

    def normalized(row, fields):
        if isinstance(row, Mapping):
            result = {field: row.get(field) for field in fields}
        else:
            result = dict(zip(fields, row))
        for key in ("id", "source_id"):
            if result.get(key) is not None:
                result[key] = str(result[key])
        return result

    source_fields = ("id", "name", "slug", "license_status", "visibility", "permission_terms", "notes")
    alias_fields = ("id", "alias_key", "alias_display", "source_id", "note")
    if (
        len(sources) != 1 or normalized(sources[0], source_fields) != packet.source
        or len(aliases) != 1 or normalized(aliases[0], alias_fields) != packet.alias
    ):
        raise PilotApplyError("source_alias_state_conflict")


def _write_packet(connection, packet: PilotPacket, vectors: list[list[float]]) -> list[str]:
    policy_ids: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '30s'")
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        _verify_source_alias(cursor, packet)
        if any(inspect_pilot_item(cursor, item).kind != "clean" for item in packet.items):
            raise PilotApplyError("candidate_state_changed_after_preflight")
        for item, vector in zip(packet.items, vectors, strict=True):
            document = item.document
            cursor.execute(
                """/* phase8:insert_document */
                INSERT INTO documents
                  (id, title, original_title, author, source_name, source_type,
                   source_kind, citation_mode, source, topic_tags, bible_references,
                   file_path, is_copyrighted, full_text, source_id, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                tuple(document[field] for field in (
                    "id", "title", "original_title", "author", "source_name", "source_type",
                    "source_kind", "citation_mode", "source", "topic_tags", "bible_references",
                    "file_path", "is_copyrighted", "full_text", "source_id", "url",
                )),
            )
            chunk = item.chunk
            cursor.execute(
                """/* phase8:insert_chunk */
                INSERT INTO chunks
                  (id, document_id, content, embedding, chunk_index, bible_references)
                VALUES (%s, %s, %s, %s::vector, %s, %s)""",
                (chunk["id"], chunk["document_id"], chunk["content"], _vector_literal(vector), chunk["chunk_index"], chunk["bible_references"]),
            )
            policy = item.policy
            cursor.execute(
                """/* phase8:insert_policy */
                INSERT INTO source_passage_policy_versions
                  (chunk_id, policy_class, protected_topic_keys, issue_key,
                   viewpoint_key, classifier_kind, rule_version, model,
                   prompt_fingerprint, reason_codes, is_current)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id""",
                tuple(policy[field] for field in (
                    "chunk_id", "policy_class", "protected_topic_keys", "issue_key",
                    "viewpoint_key", "classifier_kind", "rule_version", "model",
                    "prompt_fingerprint", "reason_codes", "is_current",
                )),
            )
            policy_ids.append(str(cursor.fetchone()[0]))
        staged = [inspect_pilot_item(cursor, item, allow_unstamped=True) for item in packet.items]
        if [state.policy_id for state in staged] != policy_ids:
            raise PilotApplyError("staged_policy_identity_mismatch")
        cursor.execute(
            """/* phase8:stamp_complete */
            UPDATE documents SET ingest_completed_at = now() WHERE id = ANY(%s)""",
            ([item.document["id"] for item in packet.items],),
        )
        if any(inspect_pilot_item(cursor, item).kind != "exact_complete" for item in packet.items):
            raise PilotApplyError("staged_state_verification_failed")
    return policy_ids


def apply_pilot(
    connection_factory: Callable[[str], object],
    embed_fn: Callable[..., list[float]],
    packet: PilotPacket,
    approval: Mapping[str, object],
    preflight_fn: Callable[[], Mapping[str, object]],
) -> dict[str, object]:
    """Validate all vectors before opening one atomic 60-row transaction."""

    _validate_approval_mapping(approval, packet)
    preflight = preflight_fn()
    state = preflight.get("candidate_state")
    if state == "all_exact_complete":
        return {
            "status": "skipped", "reason": "exact_pilot_already_complete",
            "reconciliation": {"attempted": 20, "stored": 0, "errored": 0, "skipped": 20},
        }
    if state != "all_clean":
        raise PilotApplyError("preflight_not_clean")

    vectors: list[list[float]] = []
    for item in packet.items:
        try:
            raw = embed_fn(item.text, model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS)
        except Exception as exc:
            raise PilotApplyError("embedding_failed") from exc
        vectors.append(_validate_vector(raw))

    try:
        connection = connection_factory("write")
        connection.autocommit = False
    except Exception:
        return {
            "status": "failed", "reason": "write_connection_failed",
            "embedding": {"requests_attempted": 20, "requests_completed": 20, "model": EMBEDDING_MODEL, "dimensions": EMBEDDING_DIMENSIONS, "maximum_spend_usd": packet.maximum_spend_usd},
            "reconciliation": {"attempted": 20, "stored": 0, "errored": 20, "skipped": 0},
        }
    try:
        policy_ids = _write_packet(connection, packet, vectors)
        connection.commit()
    except Exception as exc:
        connection.rollback()
        connection.close()
        return {
            "status": "failed", "reason": type(exc).__name__,
            "embedding": {"requests_attempted": 20, "requests_completed": 20, "model": EMBEDDING_MODEL, "dimensions": EMBEDDING_DIMENSIONS, "maximum_spend_usd": packet.maximum_spend_usd},
            "reconciliation": {"attempted": 20, "stored": 0, "errored": 20, "skipped": 0},
        }
    connection.close()
    return {
        "status": "stored", "reason": None, "policy_ids": policy_ids,
        "embedding": {"requests_attempted": 20, "requests_completed": 20, "model": EMBEDDING_MODEL, "dimensions": EMBEDDING_DIMENSIONS, "maximum_spend_usd": packet.maximum_spend_usd},
        "reconciliation": {"attempted": 20, "stored": 20, "errored": 0, "skipped": 0},
    }


def _load_apply_dependencies():
    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2
    from app.services.embeddings import embed_text
    database_url = os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_DB_URL is not set")

    def connection_factory(mode: str):
        if mode != "write":
            raise ValueError("apply_connection_mode_invalid")
        return psycopg2.connect(database_url)

    def embedding_adapter(text: str, *, model: str, dimensions: int):
        if model != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
            raise PilotApplyError("embedding_contract_changed")
        return embed_text(text)
    return connection_factory, embedding_adapter


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the exact attended Phase 8 hidden pilot.")
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--approval-file", required=True, type=Path)
    args = parser.parse_args(argv)
    packet = build_pilot_packet(ROOT, args.artifact)
    approval = validate_pilot_approval(args.approval_file, packet, date.today())

    from biblical_context_ingest_contract import build_aaron_projection
    from preflight_tipnr_hidden_pilot import preflight_pilot
    from reconcile_biblical_context_batch import _load_reconcile_dependencies
    identity_factory, retrieval_factory = _load_reconcile_dependencies()
    preflight = preflight_pilot(
        identity_factory, retrieval_factory, packet, build_aaron_projection(ROOT)
    )
    connection_factory, embed_fn = _load_apply_dependencies()
    report = apply_pilot(connection_factory, embed_fn, packet, approval, lambda: preflight)
    sys.stdout.buffer.write(canonical_json_bytes(report))
    return 0 if report["status"] in {"stored", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
