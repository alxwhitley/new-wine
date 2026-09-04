#!/usr/bin/env python3
"""Attended, approval-gated, resumable batch writer for the remaining TIPNR corpus.

Nothing here loads an OpenAI or write dependency until approval equality and a
fresh read-only preflight both pass. Each batch validates every vector before a
write connection opens, writes exactly three rows per item inside one
transaction, and stamps completion once.

A rollback-only structural probe mode stages the first remaining batch with
deterministic zero-vectors and can never commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import stat
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    SOURCE_SLUG,
)
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preflight_tipnr_full_batch import assert_source
from preview_biblical_context_tooling import (
    PreviewCollisionError,
    PreviewPathError,
    write_new_preview,
)
from preview_tipnr_full_batch import (
    DISCLOSED_PAYLOAD_CATEGORIES,
    EXCLUDED_PAYLOAD_CATEGORIES,
)
from tipnr_full_batch_contract import (
    BATCH_COUNT,
    EXPECTED_ROW_TOTAL,
    MAXIMUM_SPEND_USD,
    REMAINING_COUNT,
    ROWS_PER_ITEM,
    FullBatch,
    FullBatchPacket,
    build_full_batch_packet,
)


ROOT = Path(__file__).resolve().parent.parent
APPROVAL_SCHEMA_VERSION = "biblical_context_tipnr_full_batch_approval.v1"
MAX_APPROVAL_BYTES = 16384
EVIDENCE_DIRECTORY = ROOT / "local" / "2026-09"


class FullBatchApprovalError(ValueError):
    """The attended approval does not match the exact same-day operation."""


class FullBatchApplyError(RuntimeError):
    """A vector, cache, or atomic write boundary failed."""


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

def stale_fixture_chunk_id() -> str:
    """The chunk whose Phase 6 fixture policy must be demoted, not deleted."""

    from biblical_context_ingest_contract import build_aaron_projection

    return str(build_aaron_projection(ROOT).chunks[0]["id"])


def expected_approval(packet: FullBatchPacket, today: date) -> dict[str, object]:
    """The one approval shape that authorizes this exact operation, today."""

    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approved_by": "Alex Whitley",
        "operation_date": today.isoformat(),
        "source_slug": SOURCE_SLUG,
        "packet_sha256": packet.packet_sha256,
        "batch_sha256": [batch.batch_sha256 for batch in packet.batches],
        "item_count": REMAINING_COUNT,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "maximum_embedding_requests": REMAINING_COUNT,
        "maximum_spend_usd": MAXIMUM_SPEND_USD,
        "maximum_transactions": BATCH_COUNT,
        "maximum_rows": EXPECTED_ROW_TOTAL,
        "disclosed_payload_categories": list(DISCLOSED_PAYLOAD_CATEGORIES),
        "excluded_payload_categories": list(EXCLUDED_PAYLOAD_CATEGORIES),
        "fixture_policy_demotion_authorized": True,
        "fixture_policy_chunk_id": stale_fixture_chunk_id(),
        "rollback_probe_authorized": True,
        "embedding_requests_authorized": True,
        "batch_transactions_authorized": True,
        "final_reconciliation_required": True,
    }


def validate_approval(
    path: Path, packet: FullBatchPacket, today: date
) -> dict[str, object]:
    """Accept only a small regular one-link JSON file matching the whole packet."""

    try:
        details = path.lstat()
    except FileNotFoundError as exc:
        raise FullBatchApprovalError("approval_missing") from exc
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise FullBatchApprovalError("approval_not_regular")
    if details.st_size > MAX_APPROVAL_BYTES:
        raise FullBatchApprovalError("approval_too_large")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FullBatchApprovalError("approval_invalid_json") from exc
    if value != expected_approval(packet, today):
        raise FullBatchApprovalError("approval_scope_mismatch")
    return value


def _require_approval(approval: Mapping[str, object], packet: FullBatchPacket) -> None:
    if dict(approval) != expected_approval(packet, date.today()):
        raise FullBatchApprovalError("approval_scope_mismatch")


# ---------------------------------------------------------------------------
# Vectors and the content-addressed cache
# ---------------------------------------------------------------------------

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
        raise FullBatchApplyError("embedding_invalid")
    return [float(item) for item in value]


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def cache_identity(packet: FullBatchPacket, batch: FullBatch) -> dict[str, object]:
    """Bind a cache entry to model, dimensions, rendered hashes, and batch identity."""

    return {
        "schema_version": "biblical_context_tipnr_full_batch_vectors.v1",
        "packet_sha256": packet.packet_sha256,
        "batch_index": batch.index,
        "batch_sha256": batch.batch_sha256,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "rendered_sha256": [item.rendered_sha256 for item in batch.items],
    }


def cache_path(directory: Path, packet: FullBatchPacket, batch: FullBatch) -> Path:
    digest = canonical_sha256(cache_identity(packet, batch))
    return directory / f"tipnr_full_batch_vectors_{digest}.json"


def load_cached_vectors(
    directory: Path, packet: FullBatchPacket, batch: FullBatch
) -> list[list[float]] | None:
    """Return cached vectors only on an exact identity match; never substitute."""

    path = cache_path(directory, packet, batch)
    if not path.is_file():
        return None
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise FullBatchApplyError("vector_cache_not_regular")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FullBatchApplyError("vector_cache_unreadable") from exc
    if not isinstance(payload, dict):
        raise FullBatchApplyError("vector_cache_mismatch")
    identity = {key: value for key, value in payload.items() if key != "vectors"}
    if identity != cache_identity(packet, batch):
        raise FullBatchApplyError("vector_cache_mismatch")
    vectors = payload.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != batch.size:
        raise FullBatchApplyError("vector_cache_mismatch")
    return [_validate_vector(vector) for vector in vectors]


def store_cached_vectors(
    directory: Path,
    packet: FullBatchPacket,
    batch: FullBatch,
    vectors: Sequence[Sequence[float]],
) -> Path:
    """Persist validated vectors as immutable mode-0600 ignored local evidence."""

    if len(vectors) != batch.size:
        raise FullBatchApplyError("vector_cache_mismatch")
    payload = dict(cache_identity(packet, batch))
    payload["vectors"] = [list(vector) for vector in vectors]
    path = cache_path(directory, packet, batch)
    write_new_preview(path, canonical_json_bytes(payload))
    return path


def resolve_batch_vectors(
    batch: FullBatch,
    packet: FullBatchPacket,
    embed_fn: Callable[..., Sequence[float]] | None,
    directory: Path,
) -> tuple[list[list[float]], dict[str, object]]:
    """Reuse a validated cache when present; otherwise embed and validate all."""

    cached = load_cached_vectors(directory, packet, batch)
    if cached is not None:
        return cached, {
            "requests_attempted": 0,
            "requests_completed": 0,
            "requests_failed": 0,
            "source": "cache",
            "model": EMBEDDING_MODEL,
            "dimensions": EMBEDDING_DIMENSIONS,
        }
    if embed_fn is None:
        raise FullBatchApplyError("embedding_unavailable")

    vectors: list[list[float]] = []
    for position, item in enumerate(batch.items, start=1):
        try:
            raw = embed_fn(
                item.text, model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS
            )
            vectors.append(_validate_vector(raw))
        except Exception as exc:
            reason = (
                "embedding_invalid"
                if isinstance(exc, FullBatchApplyError)
                else "embedding_failed"
            )
            raise FullBatchApplyError(
                json.dumps({
                    "reason": reason,
                    "requests_attempted": position,
                    "requests_completed": len(vectors),
                    "requests_failed": 1,
                })
            ) from exc
    store_cached_vectors(directory, packet, batch, vectors)
    return vectors, {
        "requests_attempted": batch.size,
        "requests_completed": batch.size,
        "requests_failed": 0,
        "source": "provider",
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
    }


# ---------------------------------------------------------------------------
# Atomic per-batch write
# ---------------------------------------------------------------------------

_DOCUMENT_COLUMNS = (
    "id", "title", "original_title", "author", "source_name", "source_type",
    "source_kind", "citation_mode", "source", "topic_tags", "bible_references",
    "file_path", "is_copyrighted", "full_text", "source_id", "url",
)
_POLICY_COLUMNS = (
    "chunk_id", "policy_class", "protected_topic_keys", "issue_key",
    "viewpoint_key", "classifier_kind", "rule_version", "model",
    "prompt_fingerprint", "reason_codes", "is_current",
)


def _stage_batch(
    cursor,
    packet: FullBatchPacket,
    batch: FullBatch,
    vectors: Sequence[Sequence[float]],
) -> list[str]:
    """Insert exactly three rows per item using parameterized SQL only."""

    cursor.execute("SET LOCAL statement_timeout = '120s'")
    cursor.execute("SET LOCAL lock_timeout = '5s'")

    # Re-assert the hidden, licensed source on the WRITING session, inside this
    # transaction, before any row is staged. preflight_full_batch already runs
    # assert_source, but on a separate read-only connection that is opened and
    # closed before this one exists -- so it cannot see a visibility or license
    # flip that lands in between. This ingest's entire safety argument is that
    # the material is unretrievable because the source is hidden, and that has
    # to hold at COMMIT time, not merely at preflight time. This mirrors
    # _verify_source_alias in apply_tipnr_hidden_pilot.py, which ran the same
    # check as the first statement of its own write transaction.
    assert_source(cursor, packet)

    document_ids = [item.document["id"] for item in batch.items]
    chunk_ids = [item.chunk["id"] for item in batch.items]

    cursor.execute(
        """/* fullbatch:precheck_documents */
        SELECT count(*) FROM documents WHERE id = ANY(%s::uuid[])""",
        (document_ids,),
    )
    if int(cursor.fetchone()[0]) != 0:
        raise FullBatchApplyError("candidate_state_changed_after_preflight")
    cursor.execute(
        """/* fullbatch:precheck_chunks */
        SELECT count(*) FROM chunks WHERE id = ANY(%s::uuid[])""",
        (chunk_ids,),
    )
    if int(cursor.fetchone()[0]) != 0:
        raise FullBatchApplyError("candidate_state_changed_after_preflight")

    policy_ids: list[str] = []
    for item, vector in zip(batch.items, vectors, strict=True):
        cursor.execute(
            """/* fullbatch:insert_document */
            INSERT INTO documents
              (id, title, original_title, author, source_name, source_type,
               source_kind, citation_mode, source, topic_tags, bible_references,
               file_path, is_copyrighted, full_text, source_id, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            tuple(item.document[field] for field in _DOCUMENT_COLUMNS),
        )
        cursor.execute(
            """/* fullbatch:insert_chunk */
            INSERT INTO chunks
              (id, document_id, content, embedding, chunk_index, bible_references)
            VALUES (%s, %s, %s, %s::vector, %s, %s)""",
            (
                item.chunk["id"], item.chunk["document_id"], item.chunk["content"],
                _vector_literal(vector), item.chunk["chunk_index"],
                item.chunk["bible_references"],
            ),
        )
        cursor.execute(
            """/* fullbatch:insert_policy */
            INSERT INTO source_passage_policy_versions
              (chunk_id, policy_class, protected_topic_keys, issue_key,
               viewpoint_key, classifier_kind, rule_version, model,
               prompt_fingerprint, reason_codes, is_current)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id""",
            tuple(item.policy[field] for field in _POLICY_COLUMNS),
        )
        policy_ids.append(str(cursor.fetchone()[0]))

    # Staged exact-count checks before the completion stamp.
    cursor.execute(
        """/* fullbatch:staged_documents */
        SELECT count(*) FROM documents WHERE id = ANY(%s::uuid[])""",
        (document_ids,),
    )
    if int(cursor.fetchone()[0]) != batch.size:
        raise FullBatchApplyError("staged_document_count_mismatch")
    cursor.execute(
        """/* fullbatch:staged_chunks */
        SELECT count(*) FROM chunks
        WHERE id = ANY(%s::uuid[]) AND vector_dims(embedding) = %s""",
        (chunk_ids, EMBEDDING_DIMENSIONS),
    )
    if int(cursor.fetchone()[0]) != batch.size:
        raise FullBatchApplyError("staged_chunk_count_mismatch")
    cursor.execute(
        """/* fullbatch:staged_policies */
        SELECT count(*) FROM source_passage_policy_versions
        WHERE chunk_id = ANY(%s::uuid[]) AND is_current
          AND policy_class = 'general_context'""",
        (chunk_ids,),
    )
    if int(cursor.fetchone()[0]) != batch.size:
        raise FullBatchApplyError("staged_policy_count_mismatch")

    cursor.execute(
        """/* fullbatch:stamp_complete */
        UPDATE documents SET ingest_completed_at = now()
        WHERE id = ANY(%s::uuid[]) AND ingest_completed_at IS NULL""",
        (document_ids,),
    )
    cursor.execute(
        """/* fullbatch:staged_stamped */
        SELECT count(*) FROM documents
        WHERE id = ANY(%s::uuid[]) AND ingest_completed_at IS NOT NULL""",
        (document_ids,),
    )
    if int(cursor.fetchone()[0]) != batch.size:
        raise FullBatchApplyError("staged_stamp_count_mismatch")
    return policy_ids


def _counters(batch: FullBatch, *, stored: int, errored: int, skipped: int):
    return {
        "attempted": batch.size,
        "stored": stored,
        "errored": errored,
        "skipped": skipped,
        "rows": stored * ROWS_PER_ITEM,
    }


def apply_batch(
    connection_factory: Callable[[str], object],
    embed_fn: Callable[..., Sequence[float]] | None,
    packet: FullBatchPacket,
    batch: FullBatch,
    approval: Mapping[str, object],
    preflight_fn: Callable[[], Mapping[str, object]],
    *,
    evidence_directory: Path = EVIDENCE_DIRECTORY,
) -> dict[str, object]:
    """Validate approval and preflight, then commit exactly one batch atomically."""

    _require_approval(approval, packet)
    preflight = preflight_fn()
    if preflight.get("next_batch_index") != batch.index:
        raise FullBatchApplyError("preflight_batch_index_mismatch")
    if preflight.get("next_batch_sha256") != batch.batch_sha256:
        raise FullBatchApplyError("preflight_batch_identity_mismatch")
    if preflight.get("candidate_state") not in {"all_clean", "exact_complete_prefix"}:
        raise FullBatchApplyError("preflight_not_resumable")

    try:
        vectors, embedding = resolve_batch_vectors(
            batch, packet, embed_fn, evidence_directory
        )
    except (PreviewCollisionError, PreviewPathError) as exc:
        return {
            "status": "failed",
            "reason": "evidence_collision",
            "batch_index": batch.index,
            "batch_sha256": batch.batch_sha256,
            "error": {"kind": type(exc).__name__, "detail": str(exc)[:200]},
            "transactions": {"opened": 0, "committed": 0, "rolled_back": 0},
            "reconciliation": _counters(batch, stored=0, errored=batch.size, skipped=0),
        }
    except FullBatchApplyError as exc:
        try:
            detail = json.loads(str(exc))
        except json.JSONDecodeError:
            detail = {"reason": str(exc)}
        return {
            "status": "failed",
            "reason": detail.get("reason", "embedding_failed"),
            "batch_index": batch.index,
            "batch_sha256": batch.batch_sha256,
            "embedding": {**detail, "model": EMBEDDING_MODEL,
                          "dimensions": EMBEDDING_DIMENSIONS},
            "transactions": {"opened": 0, "committed": 0, "rolled_back": 0},
            "reconciliation": _counters(batch, stored=0, errored=batch.size, skipped=0),
        }

    try:
        connection = connection_factory("write")
        connection.autocommit = False
    except Exception as exc:
        return {
            "status": "failed",
            "reason": "write_connection_failed",
            "batch_index": batch.index,
            "batch_sha256": batch.batch_sha256,
            "embedding": embedding,
            "error": type(exc).__name__,
            "transactions": {"opened": 0, "committed": 0, "rolled_back": 0},
            "reconciliation": _counters(batch, stored=0, errored=batch.size, skipped=0),
        }

    try:
        with connection.cursor() as cursor:
            policy_ids = _stage_batch(cursor, packet, batch, vectors)
    except Exception as exc:
        try:
            connection.rollback()
        finally:
            connection.close()
        return {
            "status": "failed",
            "reason": "staging_failed",
            "batch_index": batch.index,
            "batch_sha256": batch.batch_sha256,
            "embedding": embedding,
            "error": {"kind": type(exc).__name__, "detail": str(exc)[:500]},
            "transactions": {"opened": 1, "committed": 0, "rolled_back": 1},
            "reconciliation": _counters(batch, stored=0, errored=batch.size, skipped=0),
        }

    try:
        connection.commit()
    except Exception as exc:
        try:
            connection.rollback()
        finally:
            connection.close()
        return {
            "status": "commit_uncertain",
            "reason": "commit_failed",
            "batch_index": batch.index,
            "batch_sha256": batch.batch_sha256,
            "embedding": embedding,
            "error": {"kind": type(exc).__name__, "detail": str(exc)[:500]},
            "transactions": {"opened": 1, "committed": 0, "rolled_back": 1},
            "reconciliation": {
                "attempted": batch.size,
                "stored": None,
                "errored": None,
                "skipped": None,
                "rows": None,
                "resolved_by": "fresh_reconciliation",
            },
        }
    connection.close()
    return {
        "status": "stored",
        "reason": None,
        "batch_index": batch.index,
        "batch_sha256": batch.batch_sha256,
        "policy_ids": policy_ids,
        "embedding": embedding,
        "transactions": {"opened": 1, "committed": 1, "rolled_back": 0},
        "reconciliation": _counters(batch, stored=batch.size, errored=0, skipped=0),
    }


# ---------------------------------------------------------------------------
# Rollback-only structural probe
# ---------------------------------------------------------------------------

def probe_batch(
    connection_factory: Callable[[str], object],
    packet: FullBatchPacket,
    batch: FullBatch,
    preflight_fn: Callable[[], Mapping[str, object]],
    postflight_fn: Callable[[], Mapping[str, object]],
) -> dict[str, object]:
    """Stage one batch with zero-vectors, always roll back, never commit.

    This function makes zero model requests and has no commit path at all;
    there is deliberately no option a caller could pass to make it commit.
    A fresh read-only preflight must classify live state before the write
    connection is opened.
    """

    preflight = preflight_fn()
    if preflight.get("candidate_state") != "all_clean":
        raise FullBatchApplyError("probe_preflight_not_clean")
    if preflight.get("next_batch_index") != batch.index:
        raise FullBatchApplyError("probe_preflight_batch_index_mismatch")
    if preflight.get("next_batch_sha256") != batch.batch_sha256:
        raise FullBatchApplyError("probe_preflight_batch_identity_mismatch")

    zero_vectors = [[0.0] * EMBEDDING_DIMENSIONS for _ in range(batch.size)]
    connection = connection_factory("write")
    connection.autocommit = False
    staged_rows = 0
    policy_ids: list[str] = []
    error: dict[str, object] | None = None
    try:
        with connection.cursor() as cursor:
            policy_ids = _stage_batch(cursor, packet, batch, zero_vectors)
            staged_rows = batch.size * ROWS_PER_ITEM
    except Exception as exc:
        error = {"kind": type(exc).__name__, "detail": str(exc)[:500]}
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()

    postflight = postflight_fn()
    verified = (
        error is None
        and staged_rows == batch.size * ROWS_PER_ITEM
        and len(policy_ids) == batch.size
        and postflight.get("candidate_state") == "all_clean"
        and postflight.get("counts", {}).get("exact_complete") == 0
    )
    return {
        "schema_version": "biblical_context_tipnr_full_batch_probe.v1",
        "status": "verified" if verified else "failed",
        "batch_index": batch.index,
        "batch_sha256": batch.batch_sha256,
        "packet_sha256": packet.packet_sha256,
        "staged_rows": staged_rows,
        "expected_rows": batch.size * ROWS_PER_ITEM,
        "staged_policy_rows": len(policy_ids),
        "embedding_requests": 0,
        "vectors": "deterministic_zero",
        "transactions": {"opened": 1, "committed": 0, "rolled_back": 1},
        "committed": False,
        "error": error,
        "preflight": {
            "candidate_state": preflight.get("candidate_state"),
            "next_batch_index": preflight.get("next_batch_index"),
        },
        "postflight": dict(postflight),
    }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def write_attempt_evidence(directory: Path, payload: bytes) -> Path:
    """Persist one immutable content-addressed mode-0600 attempt report."""

    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"tipnr_full_batch_attempt_{digest}.json"
    write_new_preview(path, payload)
    return path


def finalize_batch(
    apply_report: Mapping[str, object],
    reconcile_fn: Callable[[], Mapping[str, object]],
    evidence_directory: Path = EVIDENCE_DIRECTORY,
) -> tuple[dict[str, object], bytes]:
    """Resolve one batch through fresh reads and persist evidence before returning."""

    try:
        verification = dict(reconcile_fn())
    except Exception as exc:
        status = (
            "committed_reconciliation_failed"
            if apply_report.get("status") == "stored"
            else "commit_outcome_unknown_reconciliation_failed"
        )
        report = {
            "schema_version": "biblical_context_tipnr_full_batch_final.v1",
            "status": status,
            "apply": dict(apply_report),
            "verification": None,
            "verification_error": {"kind": type(exc).__name__, "reason": str(exc)[:500]},
        }
    else:
        if verification.get("status") == "verified":
            status = (
                "verified"
                if apply_report.get("status") == "stored"
                else "commit_outcome_ambiguous_but_verified"
            )
        else:
            status = "reconciliation_not_verified"
        report = {
            "schema_version": "biblical_context_tipnr_full_batch_final.v1",
            "status": status,
            "apply": dict(apply_report),
            "verification": verification,
        }
    payload = canonical_json_bytes(report)
    write_attempt_evidence(evidence_directory, payload)
    return report, payload


# ---------------------------------------------------------------------------
# Deferred dependency loading
# ---------------------------------------------------------------------------

def _load_write_dependencies():
    """Load write and embedding clients only after approval and preflight pass."""

    sys.path.insert(0, str(ROOT / "backend"))
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2
    from app.services.embeddings import embed_text

    database_url = os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        raise FullBatchApplyError("write_url_missing")

    def connection_factory(mode: str):
        if mode != "write":
            raise ValueError("apply_connection_mode_invalid")
        return psycopg2.connect(database_url)

    def embedding_adapter(text: str, *, model: str, dimensions: int):
        if model != EMBEDDING_MODEL or dimensions != EMBEDDING_DIMENSIONS:
            raise FullBatchApplyError("embedding_contract_changed")
        return embed_text(text)

    return connection_factory, embedding_adapter


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the attended remaining-TIPNR batches, one at a time."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--approval-file", required=True, type=Path)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args(argv)

    packet = build_full_batch_packet(ROOT, args.artifact)
    approval = validate_approval(args.approval_file, packet, date.today())
    if not approval:
        raise FullBatchApprovalError("approval_scope_mismatch")

    from preflight_tipnr_full_batch import _load_identity_factory, preflight_full_batch
    from tipnr_hidden_pilot_contract import build_pilot_packet

    identity_factory = _load_identity_factory()
    pilot = build_pilot_packet(ROOT, args.artifact)

    def preflight():
        return preflight_full_batch(identity_factory, packet, pilot_packet=pilot)

    # Classify live state BEFORE any write or embedding credential is loaded.
    state = preflight()
    index = state.get("next_batch_index")
    if index is None:
        sys.stdout.buffer.write(canonical_json_bytes(
            {"status": "complete", "reason": "all_batches_already_stored"}
        ))
        return 0
    batch = packet.batches[index - 1]

    connection_factory, embed_fn = _load_write_dependencies()

    if args.probe_only:
        report = probe_batch(
            connection_factory, packet, batch, preflight, preflight
        )
        payload = canonical_json_bytes(report)
        write_attempt_evidence(EVIDENCE_DIRECTORY, payload)
        sys.stdout.buffer.write(payload)
        return 0 if report["status"] == "verified" else 1

    from reconcile_tipnr_full_batch import _load_factories, reconcile_batch

    _, retrieval_factory = _load_factories()
    apply_report = apply_batch(
        connection_factory, embed_fn, packet, batch, approval, preflight
    )
    report, payload = finalize_batch(
        apply_report,
        lambda: reconcile_batch(identity_factory, retrieval_factory, packet, batch),
    )
    sys.stdout.buffer.write(payload)
    return 0 if report["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
