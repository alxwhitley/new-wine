#!/usr/bin/env python3
"""Pure contract freezing the remaining TIPNR corpus and its 20 atomic batches.

This module has no network, database, model, or write capability. It re-derives
every remaining eligible identity from the pinned artifact, excludes the exact
Phase 8 pilot identities that are already exact-complete in production, and
freezes the canonical batch sequence.

Aaron (`H0175`) is deliberately IN the remaining set. Phase 6 ingested Aaron
from the reduced parser fixture (4 of 352 OSIS references), so the pinned
artifact's Aaron projection has never been stored. Its stale fixture-derived
policy is demoted under separate attended authorization; this contract only
freezes what must still be written.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Mapping, Sequence

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    POLICY_REASON,
    POLICY_RULE_VERSION,
    SOURCE_NAME,
    SOURCE_SLUG,
    UPSTREAM_REVISION,
    build_aaron_projection,
    stable_uuid,
)
from biblical_context_tooling import canonical_sha256
from inventory_tipnr_context import build_tipnr_inventory
from parse_tipnr_context import (
    TIPNR_ARTIFACT_BYTES,
    TIPNR_ARTIFACT_SHA256,
    classify_tipnr_text,
    verify_tipnr_artifact,
)
from tipnr_hidden_pilot_contract import (
    EXPECTED_SELECTION,
    PHASE7_ELIGIBLE_SHA256,
    PHASE7_INVENTORY_SHA256,
    render_pilot_text,
)


BATCH_SIZE = 200
FINAL_BATCH_SIZE = 139
BATCH_COUNT = 20
REMAINING_COUNT = 3939
COMPLETED_COUNT = 20
ELIGIBLE_COUNT = 3959
ROWS_PER_ITEM = 3
EXPECTED_ROW_TOTAL = REMAINING_COUNT * ROWS_PER_ITEM

EXPECTED_OUTCOME_COUNTS = {
    "duplicate": 0,
    "eligible": 3959,
    "malformed": 172,
    "prohibited": 16,
    "skipped": 115,
}
EXPECTED_ELIGIBLE_BY_TYPE = {"person": 3055, "place": 904}
REMAINING_BY_TYPE = {"person": 3045, "place": 894}

# The conservative full-inventory ceiling frozen by the Phase 7 inventory. A
# lower computed estimate never widens this ceiling.
MAXIMUM_SPEND_USD = "0.02441808"
PRICE_PER_MILLION_INPUT_TOKENS_USD = Decimal("0.02")

# Post-ingest global totals under the approved "Correct Aaron" resolution.
GLOBAL_CURRENT_POLICIES = 3959
GLOBAL_DOCUMENTS = 3960
GLOBAL_CHUNKS = 3960
GLOBAL_INERT_DOCUMENTS = 1
GLOBAL_PROPOSITIONS = 0

_RECORD_FIELDS = {
    "dataset_id", "artifact_revision", "entity_id", "entity_type",
    "original_language_forms", "record_sha256",
}
_ENTITY_TYPE_ORDER = ("person", "place")


class FullBatchContractError(ValueError):
    """The pinned inventory, exclusion set, ordering, or projection drifted."""


@dataclass(frozen=True)
class FullBatchItem:
    entity_id: str
    entity_type: str
    record: dict[str, object]
    document: dict[str, object]
    chunk: dict[str, object]
    policy: dict[str, object]
    text: str
    rendered_sha256: str
    identity: str


@dataclass(frozen=True)
class FullBatch:
    index: int
    size: int
    first_entity_id: str
    last_entity_id: str
    items: tuple[FullBatchItem, ...]
    rendered_bytes: int
    estimated_tokens: int
    batch_sha256: str


@dataclass(frozen=True)
class FullBatchPacket:
    source: dict[str, object]
    alias: dict[str, object]
    batches: tuple[FullBatch, ...]
    excluded: tuple[tuple[str, str, str], ...]
    remaining_by_type: dict[str, int]
    rendered_bytes: int
    estimated_tokens: int
    estimated_cost_usd: str
    maximum_spend_usd: str
    embedding_request_ceiling: int
    row_total: int
    sample_ids: tuple[str, ...]
    packet_sha256: str

    @property
    def items(self) -> tuple[FullBatchItem, ...]:
        return tuple(item for batch in self.batches for item in batch.items)


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING), "f")


def _validate_record(record: Mapping[str, object]) -> None:
    """Refuse any unrecognized field or drifted record checksum."""

    if set(record) != _RECORD_FIELDS:
        raise FullBatchContractError("full_batch_record_fields_changed")
    checksum_input = dict(record)
    supplied = checksum_input.pop("record_sha256", None)
    if (
        record.get("dataset_id") != "stepbible_tipnr"
        or record.get("artifact_revision") != UPSTREAM_REVISION
        or record.get("entity_type") not in set(_ENTITY_TYPE_ORDER)
        or supplied != canonical_sha256(checksum_input)
    ):
        raise FullBatchContractError("full_batch_record_mismatch")


def build_item(
    record: Mapping[str, object],
    registration: Mapping[str, object],
    source_id: str,
) -> FullBatchItem:
    """Project one eligible record through the canonical Phase 6/8 shape."""

    _validate_record(record)
    entity_id = str(record["entity_id"])
    entity_type = str(record["entity_type"])
    text = render_pilot_text(record)
    rendered_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record_sha256 = str(record["record_sha256"])
    identity = ":".join(
        (SOURCE_SLUG, UPSTREAM_REVISION, entity_id, record_sha256, rendered_sha256)
    )
    document_id = stable_uuid("document", identity)
    chunk_id = stable_uuid("chunk", f"{identity}:0")
    references = [
        reference
        for form in record["original_language_forms"]
        for reference in form["osis_references"]
    ]
    title = f"{SOURCE_NAME} {entity_type} {entity_id}"
    document = {
        "id": document_id,
        "title": title,
        "original_title": title,
        "author": None,
        "source_name": SOURCE_NAME,
        "source_type": "reference",
        "source_kind": registration["source_kind"],
        "citation_mode": registration["citation_mode"],
        "source": SOURCE_NAME,
        "topic_tags": [],
        "bible_references": references,
        "file_path": (
            f"biblical-context/{SOURCE_SLUG}/{UPSTREAM_REVISION}/"
            f"{entity_id}/{record_sha256}.json"
        ),
        "is_copyrighted": True,
        "full_text": text,
        "source_id": source_id,
        "url": registration["url"],
    }
    chunk = {
        "id": chunk_id,
        "document_id": document_id,
        "content": text,
        "chunk_index": 0,
        "bible_references": references,
    }
    policy = {
        "chunk_id": chunk_id,
        "policy_class": "general_context",
        "protected_topic_keys": [],
        "issue_key": None,
        "viewpoint_key": None,
        "classifier_kind": "deterministic",
        "rule_version": POLICY_RULE_VERSION,
        "model": None,
        "prompt_fingerprint": None,
        "reason_codes": [POLICY_REASON],
        "is_current": True,
    }
    return FullBatchItem(
        entity_id, entity_type, copy.deepcopy(dict(record)), document, chunk,
        policy, text, rendered_sha256, identity,
    )


def _item_report(item: FullBatchItem) -> dict[str, object]:
    return {
        "entity_id": item.entity_id,
        "entity_type": item.entity_type,
        "record": copy.deepcopy(item.record),
        "document": copy.deepcopy(item.document),
        "chunk": copy.deepcopy(item.chunk),
        "policy": copy.deepcopy(item.policy),
        "text": item.text,
        "rendered_sha256": item.rendered_sha256,
        "identity": item.identity,
    }


def _batch_report(batch: FullBatch) -> dict[str, object]:
    return {
        "index": batch.index,
        "size": batch.size,
        "first_entity_id": batch.first_entity_id,
        "last_entity_id": batch.last_entity_id,
        "rendered_bytes": batch.rendered_bytes,
        "estimated_tokens": batch.estimated_tokens,
        "items": [_item_report(item) for item in batch.items],
    }


def _deterministic_sample(items: Sequence[FullBatchItem]) -> tuple[str, ...]:
    """First, lower quartile, median, upper quartile, and last per entity type."""

    sample: list[str] = []
    for entity_type in _ENTITY_TYPE_ORDER:
        subset = [item for item in items if item.entity_type == entity_type]
        if not subset:
            raise FullBatchContractError("full_batch_sample_empty")
        last = len(subset) - 1
        for index in (0, last // 4, last // 2, (3 * last) // 4, last):
            sample.append(subset[index].entity_id)
    if len(sample) != 10:
        raise FullBatchContractError("full_batch_sample_shape_changed")
    return tuple(sample)


def _report_without_hash(packet: FullBatchPacket) -> dict[str, object]:
    return {
        "schema_version": "biblical_context_tipnr_full_batch.v1",
        "source": copy.deepcopy(packet.source),
        "alias": copy.deepcopy(packet.alias),
        "excluded_completed_identities": [list(row) for row in packet.excluded],
        "remaining_by_type": dict(packet.remaining_by_type),
        "batches": [_batch_report(batch) for batch in packet.batches],
        "batch_sha256": [batch.batch_sha256 for batch in packet.batches],
        "rendered_bytes": packet.rendered_bytes,
        "estimated_tokens": packet.estimated_tokens,
        "estimated_cost_usd": packet.estimated_cost_usd,
        "maximum_spend_usd": packet.maximum_spend_usd,
        "embedding_request_ceiling": packet.embedding_request_ceiling,
        "row_total": packet.row_total,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "sample_ids": list(packet.sample_ids),
    }


def build_full_batch_packet(root: Path, artifact_path: Path) -> FullBatchPacket:
    """Freeze the exact remaining corpus and its canonical 20-batch sequence.

    Accepts only the pinned artifact. There is deliberately no selection,
    limit, offset, entity, or alternate-source parameter.
    """

    inventory = build_tipnr_inventory(artifact_path)
    if (
        inventory.get("payload_sha256") != PHASE7_INVENTORY_SHA256
        or inventory.get("eligible_checksum") != PHASE7_ELIGIBLE_SHA256
        or inventory.get("outcome_counts") != EXPECTED_OUTCOME_COUNTS
        or inventory.get("eligible_by_type") != EXPECTED_ELIGIBLE_BY_TYPE
    ):
        raise FullBatchContractError("phase7_inventory_mismatch")

    payload = verify_tipnr_artifact(artifact_path)
    outcomes = classify_tipnr_text(
        payload.decode("utf-8"), artifact_revision=UPSTREAM_REVISION
    )
    eligible = [
        copy.deepcopy(outcome.projection)
        for outcome in outcomes
        if outcome.status == "eligible" and outcome.projection is not None
    ]
    if len(eligible) != ELIGIBLE_COUNT:
        raise FullBatchContractError("eligible_count_mismatch")

    proof = build_aaron_projection(root)
    registration = {
        "source_kind": proof.document["source_kind"],
        "citation_mode": proof.document["citation_mode"],
        "url": proof.document["url"],
    }
    source_id = str(proof.source["id"])

    # Exclude the completed Phase 8 pilot identities by literal expected ID AND
    # projection checksum. Aaron is not excluded: production holds only the
    # reduced fixture projection, never this artifact projection.
    excluded_index = {
        (entity_type, entity_id): record_sha256
        for entity_type, entity_id, record_sha256 in EXPECTED_SELECTION
    }
    if len(excluded_index) != COMPLETED_COUNT:
        raise FullBatchContractError("completed_selection_shape_changed")

    remaining: list[dict[str, object]] = []
    matched = 0
    for record in eligible:
        key = (str(record["entity_type"]), str(record["entity_id"]))
        expected_checksum = excluded_index.get(key)
        if expected_checksum is None:
            remaining.append(record)
            continue
        if str(record["record_sha256"]) != expected_checksum:
            raise FullBatchContractError("completed_projection_drift")
        matched += 1
    if matched != COMPLETED_COUNT:
        raise FullBatchContractError("completed_selection_not_found")
    if len(remaining) != REMAINING_COUNT:
        raise FullBatchContractError("remaining_count_mismatch")

    # Canonical order: people by entity ID, then places by entity ID.
    ordered: list[dict[str, object]] = []
    for entity_type in _ENTITY_TYPE_ORDER:
        subset = sorted(
            (row for row in remaining if row["entity_type"] == entity_type),
            key=lambda row: str(row["entity_id"]),
        )
        if len(subset) != REMAINING_BY_TYPE[entity_type]:
            raise FullBatchContractError("remaining_type_count_mismatch")
        ordered.extend(subset)

    items = tuple(build_item(record, registration, source_id) for record in ordered)
    if len({item.entity_id for item in items}) != REMAINING_COUNT:
        raise FullBatchContractError("duplicate_remaining_identity")

    batches: list[FullBatch] = []
    for index in range(BATCH_COUNT):
        start = index * BATCH_SIZE
        window = items[start:start + BATCH_SIZE]
        expected_size = FINAL_BATCH_SIZE if index == BATCH_COUNT - 1 else BATCH_SIZE
        if len(window) != expected_size:
            raise FullBatchContractError("batch_size_mismatch")
        rendered_bytes = sum(len(item.text.encode("utf-8")) for item in window)
        estimated_tokens = (rendered_bytes + 2) // 3
        provisional = FullBatch(
            index + 1, len(window), window[0].entity_id, window[-1].entity_id,
            window, rendered_bytes, estimated_tokens, "",
        )
        batch_sha256 = canonical_sha256(_batch_report(provisional))
        batches.append(FullBatch(
            provisional.index, provisional.size, provisional.first_entity_id,
            provisional.last_entity_id, provisional.items,
            provisional.rendered_bytes, provisional.estimated_tokens, batch_sha256,
        ))
    if sum(batch.size for batch in batches) != REMAINING_COUNT:
        raise FullBatchContractError("batch_total_mismatch")

    rendered_bytes = sum(batch.rendered_bytes for batch in batches)
    estimated_tokens = (rendered_bytes + 2) // 3
    estimated_cost = (
        Decimal(estimated_tokens) * PRICE_PER_MILLION_INPUT_TOKENS_USD
        / Decimal(1_000_000)
    )
    if estimated_cost > Decimal(MAXIMUM_SPEND_USD):
        raise FullBatchContractError("estimated_cost_exceeds_ceiling")

    provisional_packet = FullBatchPacket(
        copy.deepcopy(proof.source), copy.deepcopy(proof.alias), tuple(batches),
        EXPECTED_SELECTION, dict(REMAINING_BY_TYPE), rendered_bytes,
        estimated_tokens, _money(estimated_cost), MAXIMUM_SPEND_USD,
        REMAINING_COUNT, EXPECTED_ROW_TOTAL, _deterministic_sample(items), "",
    )
    packet_sha256 = canonical_sha256(_report_without_hash(provisional_packet))
    return FullBatchPacket(
        provisional_packet.source, provisional_packet.alias,
        provisional_packet.batches, provisional_packet.excluded,
        provisional_packet.remaining_by_type, provisional_packet.rendered_bytes,
        provisional_packet.estimated_tokens, provisional_packet.estimated_cost_usd,
        provisional_packet.maximum_spend_usd,
        provisional_packet.embedding_request_ceiling, provisional_packet.row_total,
        provisional_packet.sample_ids, packet_sha256,
    )


def full_batch_packet_report(packet: FullBatchPacket) -> dict[str, object]:
    """Return the deep canonical report whose hash covers every projection."""

    report = _report_without_hash(packet)
    if canonical_sha256(report) != packet.packet_sha256:
        raise FullBatchContractError("full_batch_packet_hash_mismatch")
    report["packet_sha256"] = packet.packet_sha256
    return report


def full_batch_summary(packet: FullBatchPacket) -> dict[str, object]:
    """Return the compact, projection-free summary used by fixtures and previews."""

    return {
        "schema_version": "biblical_context_tipnr_full_batch_summary.v1",
        "artifact_sha256": TIPNR_ARTIFACT_SHA256,
        "artifact_bytes": TIPNR_ARTIFACT_BYTES,
        "artifact_revision": UPSTREAM_REVISION,
        "packet_sha256": packet.packet_sha256,
        "remaining_count": sum(batch.size for batch in packet.batches),
        "remaining_by_type": dict(packet.remaining_by_type),
        "excluded_completed_count": len(packet.excluded),
        "batch_count": len(packet.batches),
        "batches": [
            {
                "index": batch.index,
                "size": batch.size,
                "first_entity_id": batch.first_entity_id,
                "last_entity_id": batch.last_entity_id,
                "rendered_bytes": batch.rendered_bytes,
                "estimated_tokens": batch.estimated_tokens,
                "batch_sha256": batch.batch_sha256,
            }
            for batch in packet.batches
        ],
        "rendered_bytes": packet.rendered_bytes,
        "estimated_tokens": packet.estimated_tokens,
        "estimated_cost_usd": packet.estimated_cost_usd,
        "maximum_spend_usd": packet.maximum_spend_usd,
        "embedding_request_ceiling": packet.embedding_request_ceiling,
        "row_total": packet.row_total,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "sample_ids": list(packet.sample_ids),
        "global_totals_after_ingest": {
            "current_policies": GLOBAL_CURRENT_POLICIES,
            "documents": GLOBAL_DOCUMENTS,
            "chunks": GLOBAL_CHUNKS,
            "inert_superseded_documents": GLOBAL_INERT_DOCUMENTS,
            "propositions": GLOBAL_PROPOSITIONS,
        },
    }
