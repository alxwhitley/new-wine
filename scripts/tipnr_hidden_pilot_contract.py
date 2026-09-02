#!/usr/bin/env python3
"""Pure contract for the unexecuted Phase 8 balanced TIPNR hidden pilot."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Mapping

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MAX_SPEND_USD,
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
from parse_tipnr_context import classify_tipnr_text, verify_tipnr_artifact


PACKET_ITEM_COUNT = 20
PERSON_COUNT = 10
PLACE_COUNT = 10
PHASE7_INVENTORY_SHA256 = "edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040"
PHASE7_ELIGIBLE_SHA256 = "1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2"
SELECTION_SHA256 = "398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b"
MAXIMUM_SPEND_USD = MAX_SPEND_USD
SAMPLE_IDS = ("G0010", "G0132", "G0223J", "G0009", "G0137", "G0494")
PRICE_PER_MILLION_INPUT_TOKENS_USD = Decimal("0.02")

EXPECTED_SELECTION = (
    ("person", "G0010", "5f791ad27a2902eb4422435b006cbb883899743b809f6786d7367d56183217b6"),
    ("person", "G0013", "f0b76e34a79d674af2d1362600b2b50bc63d7715e64a6c70e43dac4b35ff1565"),
    ("person", "G0078", "40c276c2fe9f9ee8fb54e9367953c3f3512be8218d56f143a8f82a446b16d4e5"),
    ("person", "G0107", "53988a7194f676b6b05db7f4fad96c9fd39d4e1821d3ac0087302c285b9cb2d7"),
    ("person", "G0132", "49c0e19a38133366a95c02ccaf036912c121692a98c5f9929a91aeb64f06e52d"),
    ("person", "G0207", "524273dd4cdb03f65a55eb1d05b5b4b84cacd46695058eb801005ec0362832fb"),
    ("person", "G0223G", "1037130044b799c3ac8e53248595278e2fc36210f54fb46873f218c6018ed5fa"),
    ("person", "G0223H", "1a8187197a906d2a7f2159b2d5a200ecaeb1cb068af85c2edc5d4aa0dd0a7255"),
    ("person", "G0223I", "71af8b3d2f8436c87836813f8b397051f7bbf15dba4461f637d4fdc4702927c1"),
    ("person", "G0223J", "3d965783438391d723cbaf1c3e4d52852f6fb45c8a6c0c6d3dbf41a54f8b1274"),
    ("place", "G0009", "b8db1dee76c7416fba5d45e3ad29f56951340cd4d23417c181364ed82b665614"),
    ("place", "G0098", "1ae34ab14cf2cda6ddf7928bcdf071cdcf4b4fbfe47862f44656cc6125fd6dd0"),
    ("place", "G0099", "4a034fd1f32510a0b56656ecd3c4b962de07dac64bb432073d624a43ea855698"),
    ("place", "G0116", "7b18e321b2ce1694ce2e5b08df32e4763f75626045cdebb184d310af30bfcb2d"),
    ("place", "G0137", "02c22cb23dfcd7855010bbc6478f9b82fc3516adfba4eb120c2215d917d906c3"),
    ("place", "G0222", "b5c77b572a3c906e9ab698f75a70892a5be0eb1734bf73733ea8397639a1c533"),
    ("place", "G0295", "bb0148822af539bab599009b7edcdbfc964f1907543971ddf22075e3ced2b326"),
    ("place", "G0490G", "379c668f35076ec02f97c9064088096d382a69f9bf74dbe86d1331e5c8c3d54f"),
    ("place", "G0490H", "2ed5af6fa2fe7126c2d992a3547255d28e8d231cc31f42abaf594532a1f39dd0"),
    ("place", "G0494", "28664288bc469b0f425f6855f909748296de5d1015821c5b99591acd107c9d24"),
)

_RECORD_FIELDS = {
    "dataset_id", "artifact_revision", "entity_id", "entity_type",
    "original_language_forms", "record_sha256",
}
_FORM_FIELDS = {"dstrong", "estrong", "source_script_form", "osis_references"}


class PilotContractError(ValueError):
    """The pinned inventory, selection, or projection drifted."""


@dataclass(frozen=True)
class PilotItem:
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
class PilotPacket:
    source: dict[str, object]
    alias: dict[str, object]
    items: tuple[PilotItem, ...]
    selection_checksum: str
    rendered_bytes: int
    estimated_tokens: int
    estimated_cost_usd: str
    maximum_spend_usd: str
    sample_ids: tuple[str, ...]
    packet_sha256: str


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING), "f")


def _validate_record(record: Mapping[str, object]) -> None:
    if set(record) != _RECORD_FIELDS:
        raise PilotContractError("pilot_record_fields_changed")
    forms = record.get("original_language_forms")
    if not isinstance(forms, list) or not forms:
        raise PilotContractError("pilot_record_forms_invalid")
    if any(not isinstance(form, dict) or set(form) != _FORM_FIELDS for form in forms):
        raise PilotContractError("pilot_record_fields_changed")
    checksum_input = dict(record)
    supplied = checksum_input.pop("record_sha256", None)
    if (
        record.get("dataset_id") != "stepbible_tipnr"
        or record.get("artifact_revision") != UPSTREAM_REVISION
        or record.get("entity_type") not in {"person", "place"}
        or supplied != canonical_sha256(checksum_input)
    ):
        raise PilotContractError("pilot_record_mismatch")


def render_pilot_text(record: Mapping[str, object]) -> str:
    """Render only the Phase 2 allowlisted structural fields."""

    _validate_record(record)
    lines = [
        f"Dataset: {SOURCE_NAME}",
        f"Revision: {UPSTREAM_REVISION}",
        f"Entity ID: {record['entity_id']}",
        f"Entity type: {record['entity_type']}",
    ]
    forms = record["original_language_forms"]
    assert isinstance(forms, list)
    for index, form in enumerate(forms, start=1):
        assert isinstance(form, dict)
        references = form["osis_references"]
        assert isinstance(references, list)
        lines.extend((
            f"Form {index} dStrong: {form['dstrong']}",
            f"Form {index} eStrong: {form['estrong']}",
            f"Form {index} source script: {form['source_script_form']}",
            f"Form {index} OSIS references: {'; '.join(references)}",
        ))
    return "\n".join(lines) + "\n"


def _item(record: dict[str, object], source: Mapping[str, object], registration) -> PilotItem:
    _validate_record(record)
    entity_id = str(record["entity_id"])
    entity_type = str(record["entity_type"])
    text = render_pilot_text(record)
    rendered_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record_sha256 = str(record["record_sha256"])
    identity = ":".join((SOURCE_SLUG, UPSTREAM_REVISION, entity_id, record_sha256, rendered_sha256))
    document_id = stable_uuid("document", identity)
    chunk_id = stable_uuid("chunk", f"{identity}:0")
    references = [
        reference
        for form in record["original_language_forms"]
        for reference in form["osis_references"]
    ]
    title = f"{SOURCE_NAME} {entity_type} {entity_id}"
    document = {
        "id": document_id, "title": title, "original_title": title, "author": None,
        "source_name": SOURCE_NAME, "source_type": "reference",
        "source_kind": registration.document["source_kind"],
        "citation_mode": registration.document["citation_mode"],
        "source": SOURCE_NAME, "topic_tags": [], "bible_references": references,
        "file_path": f"biblical-context/{SOURCE_SLUG}/{UPSTREAM_REVISION}/{entity_id}/{record_sha256}.json",
        "is_copyrighted": True, "full_text": text, "source_id": source["id"],
        "url": registration.document["url"],
    }
    chunk = {
        "id": chunk_id, "document_id": document_id, "content": text,
        "chunk_index": 0, "bible_references": references,
    }
    policy = {
        "chunk_id": chunk_id, "policy_class": "general_context",
        "protected_topic_keys": [], "issue_key": None, "viewpoint_key": None,
        "classifier_kind": "deterministic", "rule_version": POLICY_RULE_VERSION,
        "model": None, "prompt_fingerprint": None,
        "reason_codes": [POLICY_REASON], "is_current": True,
    }
    return PilotItem(entity_id, entity_type, copy.deepcopy(record), document, chunk, policy, text, rendered_sha256, identity)


def _report_without_hash(packet: PilotPacket) -> dict[str, object]:
    return {
        "schema_version": "biblical_context_tipnr_hidden_pilot.v1",
        "source": copy.deepcopy(packet.source),
        "alias": copy.deepcopy(packet.alias),
        "selection_checksum": packet.selection_checksum,
        "items": [{
            "entity_id": item.entity_id, "entity_type": item.entity_type,
            "record": copy.deepcopy(item.record), "document": copy.deepcopy(item.document),
            "chunk": copy.deepcopy(item.chunk), "policy": copy.deepcopy(item.policy),
            "text": item.text, "rendered_sha256": item.rendered_sha256,
            "identity": item.identity,
        } for item in packet.items],
        "rendered_bytes": packet.rendered_bytes,
        "estimated_tokens": packet.estimated_tokens,
        "estimated_cost_usd": packet.estimated_cost_usd,
        "maximum_spend_usd": packet.maximum_spend_usd,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "sample_ids": list(packet.sample_ids),
    }


def build_pilot_packet(root: Path, artifact_path: Path) -> PilotPacket:
    """Re-derive and freeze exactly ten people plus ten places."""

    inventory = build_tipnr_inventory(artifact_path)
    if (
        inventory.get("payload_sha256") != PHASE7_INVENTORY_SHA256
        or inventory.get("eligible_checksum") != PHASE7_ELIGIBLE_SHA256
        or inventory.get("outcome_counts") != {
            "duplicate": 0, "eligible": 3959, "malformed": 172,
            "prohibited": 16, "skipped": 115,
        }
        or inventory.get("eligible_by_type") != {"person": 3055, "place": 904}
    ):
        raise PilotContractError("phase7_inventory_mismatch")
    payload = verify_tipnr_artifact(artifact_path)
    outcomes = classify_tipnr_text(payload.decode("utf-8"), artifact_revision=UPSTREAM_REVISION)
    eligible = [
        copy.deepcopy(outcome.projection) for outcome in outcomes
        if outcome.status == "eligible" and outcome.projection is not None
        and outcome.projection["entity_id"] != "H0175"
    ]
    people = sorted((row for row in eligible if row["entity_type"] == "person"), key=lambda row: str(row["entity_id"]))[:PERSON_COUNT]
    places = sorted((row for row in eligible if row["entity_type"] == "place"), key=lambda row: str(row["entity_id"]))[:PLACE_COUNT]
    selected = people + places
    literal = tuple((str(row["entity_type"]), str(row["entity_id"]), str(row["record_sha256"])) for row in selected)
    if literal != EXPECTED_SELECTION or canonical_sha256(selected) != SELECTION_SHA256:
        raise PilotContractError("pilot_selection_mismatch")

    proof = build_aaron_projection(root)
    items = tuple(_item(record, proof.source, proof) for record in selected)
    rendered_bytes = sum(len(item.text.encode("utf-8")) for item in items)
    estimated_tokens = (rendered_bytes + 2) // 3
    estimated_cost = Decimal(estimated_tokens) * PRICE_PER_MILLION_INPUT_TOKENS_USD / Decimal(1_000_000)
    provisional = PilotPacket(
        copy.deepcopy(proof.source), copy.deepcopy(proof.alias), items,
        SELECTION_SHA256, rendered_bytes, estimated_tokens, _money(estimated_cost),
        MAXIMUM_SPEND_USD, SAMPLE_IDS, "",
    )
    packet_sha256 = canonical_sha256(_report_without_hash(provisional))
    return PilotPacket(
        provisional.source, provisional.alias, provisional.items,
        provisional.selection_checksum, provisional.rendered_bytes,
        provisional.estimated_tokens, provisional.estimated_cost_usd,
        provisional.maximum_spend_usd, provisional.sample_ids, packet_sha256,
    )


def pilot_packet_report(packet: PilotPacket) -> dict[str, object]:
    """Return a deep canonical report whose hash covers every projection."""

    report = _report_without_hash(packet)
    if canonical_sha256(report) != packet.packet_sha256:
        raise PilotContractError("pilot_packet_hash_mismatch")
    report["packet_sha256"] = packet.packet_sha256
    return report
