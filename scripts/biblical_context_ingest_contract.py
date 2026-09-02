#!/usr/bin/env python3
"""Pure Phase 6 contract for the single hidden TIPNR ingestion proof."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from biblical_context_tooling import (
    canonical_sha256,
    compile_registration_preview,
    load_approved_manifests,
)
from parse_tipnr_context import parse_tipnr_file


ENTITY_ID = "H0175"
ENTITY_TYPE = "person"
UPSTREAM_REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"
RECORD_SHA256 = "78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6"
SOURCE_NAME = "STEPBible TIPNR"
SOURCE_SLUG = "stepbible-tipnr"
SOURCE_ALIAS = "stepbible tipnr"
SOURCE_URL = (
    "https://github.com/STEPBible/STEPBible-Data/tree/"
    + UPSTREAM_REVISION
)
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode.en"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_SPEND_USD = "0.01"
POLICY_RULE_VERSION = "biblical_context_structural_v1"
POLICY_REASON = "phase0_allowlisted_structural_fields"
PHASE6_NAMESPACE = uuid.UUID("35bf010d-89d2-4f0b-8e50-f12a89cd688f")

_RECORD_FIELDS = {
    "dataset_id",
    "artifact_revision",
    "entity_id",
    "entity_type",
    "original_language_forms",
    "record_sha256",
}
_FORM_FIELDS = {
    "dstrong",
    "estrong",
    "source_script_form",
    "osis_references",
}


class ProofContractError(ValueError):
    """The pinned proof input or its deterministic projection drifted."""


@dataclass(frozen=True)
class ProofProjection:
    entity_id: str
    record: dict[str, object]
    source: dict[str, object]
    alias: dict[str, object]
    document: dict[str, object]
    chunks: tuple[dict[str, object], ...]
    policy: dict[str, object]
    text: str
    rendered_sha256: str
    identity: str


def stable_uuid(kind: str, identity: str) -> str:
    """Derive a stable UUID for one immutable Phase 6 identity."""

    return str(uuid.uuid5(PHASE6_NAMESPACE, f"{kind}:{identity}"))


def validate_aaron_record(record: Mapping[str, object]) -> None:
    """Require the exact Phase 2 Aaron projection and no additional fields."""

    if set(record) != _RECORD_FIELDS:
        raise ProofContractError("proof_record_fields_changed")
    forms = record.get("original_language_forms")
    if not isinstance(forms, list) or len(forms) != 2:
        raise ProofContractError("proof_record_mismatch")
    if any(not isinstance(form, dict) or set(form) != _FORM_FIELDS for form in forms):
        raise ProofContractError("proof_record_fields_changed")

    checksum_input = dict(record)
    supplied_checksum = checksum_input.pop("record_sha256", None)
    if (
        record.get("dataset_id") != "stepbible_tipnr"
        or record.get("artifact_revision") != UPSTREAM_REVISION
        or record.get("entity_id") != ENTITY_ID
        or record.get("entity_type") != ENTITY_TYPE
        or supplied_checksum != RECORD_SHA256
        or canonical_sha256(checksum_input) != RECORD_SHA256
    ):
        raise ProofContractError("proof_record_mismatch")


def canonical_proof_text(record: Mapping[str, object]) -> str:
    """Render only the fields retained by the approved Phase 2 parser."""

    validate_aaron_record(record)
    lines = [
        f"Dataset: {SOURCE_NAME}",
        f"Revision: {UPSTREAM_REVISION}",
        f"Entity ID: {ENTITY_ID}",
        f"Entity type: {ENTITY_TYPE}",
    ]
    forms = record["original_language_forms"]
    assert isinstance(forms, list)
    for index, form in enumerate(forms, start=1):
        assert isinstance(form, dict)
        references = form["osis_references"]
        assert isinstance(references, list)
        lines.extend(
            (
                f"Form {index} dStrong: {form['dstrong']}",
                f"Form {index} eStrong: {form['estrong']}",
                f"Form {index} source script: {form['source_script_form']}",
                f"Form {index} OSIS references: {'; '.join(references)}",
            )
        )
    return "\n".join(lines) + "\n"


def _registration(root: Path) -> dict[str, object]:
    manifests = load_approved_manifests(
        root / "docs" / "ingestion" / "source_manifests"
    )
    matches = [
        row
        for row in compile_registration_preview(manifests)
        if row["slug"] == SOURCE_SLUG
    ]
    if len(matches) != 1:
        raise ProofContractError("proof_registration_mismatch")
    registration = dict(matches[0])
    if (
        registration["name"] != SOURCE_NAME
        or registration["license_status"] != "licensed"
        or registration["visibility"] != "hidden"
        or registration["source_kind"] != "biblical_context"
        or registration["citation_mode"] != "citable"
        or registration["aliases"] != [SOURCE_ALIAS]
    ):
        raise ProofContractError("proof_registration_mismatch")
    return registration


def _record(root: Path) -> dict[str, object]:
    fixture_dir = root / "scripts" / "fixtures" / "biblical_context"
    metadata = json.loads(
        (fixture_dir / "tipnr_minimal.meta.json").read_text(encoding="utf-8")
    )
    if metadata.get("revision") != UPSTREAM_REVISION:
        raise ProofContractError("proof_artifact_revision_mismatch")
    result = parse_tipnr_file(
        fixture_dir / "tipnr_minimal.txt",
        artifact_revision=UPSTREAM_REVISION,
    )
    matches = [row for row in result["records"] if row.get("entity_id") == ENTITY_ID]
    if len(matches) != 1:
        raise ProofContractError("proof_record_mismatch")
    record = copy.deepcopy(matches[0])
    validate_aaron_record(record)
    return record


def build_aaron_projection(root: Path) -> ProofProjection:
    """Build the immutable one-source/one-document/one-chunk proof projection."""

    registration = _registration(root)
    record = _record(root)
    text = canonical_proof_text(record)
    rendered_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = ":".join(
        (SOURCE_SLUG, UPSTREAM_REVISION, ENTITY_ID, RECORD_SHA256, rendered_sha256)
    )
    source_id = stable_uuid("source", SOURCE_SLUG)
    alias_id = stable_uuid("alias", SOURCE_ALIAS)
    document_id = stable_uuid("document", identity)
    chunk_id = stable_uuid("chunk", f"{identity}:0")
    references = [
        reference
        for form in record["original_language_forms"]
        for reference in form["osis_references"]
    ]
    file_path = (
        f"biblical-context/{SOURCE_SLUG}/{UPSTREAM_REVISION}/"
        f"{ENTITY_ID}/{RECORD_SHA256}.json"
    )
    source = {
        "id": source_id,
        "name": SOURCE_NAME,
        "slug": SOURCE_SLUG,
        "license_status": "licensed",
        "visibility": "hidden",
        "permission_terms": (
            f"CC BY 4.0 ({LICENSE_URL}); credit STEP Bible and link "
            "www.stepbible.org; identify New Wine's selected-field "
            f"transformation; source revision {UPSTREAM_REVISION}."
        ),
        "notes": (
            "Dedicated hidden Phase 6 TIPNR dataset proof. Dataset-level "
            "allowlists govern eligibility; no change to the existing "
            "STEPBible lexicon source."
        ),
    }
    alias = {
        "id": alias_id,
        "alias_key": SOURCE_ALIAS,
        "alias_display": SOURCE_NAME,
        "source_id": source_id,
        "note": "Phase 6 hidden TIPNR proof alias.",
    }
    document = {
        "id": document_id,
        "title": f"{SOURCE_NAME} {ENTITY_TYPE} {ENTITY_ID}",
        "original_title": f"{SOURCE_NAME} {ENTITY_TYPE} {ENTITY_ID}",
        "author": None,
        "source_name": SOURCE_NAME,
        "source_type": "reference",
        "source_kind": registration["source_kind"],
        "citation_mode": registration["citation_mode"],
        "source": SOURCE_NAME,
        "topic_tags": [],
        "bible_references": references,
        "file_path": file_path,
        "is_copyrighted": True,
        "full_text": text,
        "source_id": source_id,
        "url": SOURCE_URL,
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
    return ProofProjection(
        entity_id=ENTITY_ID,
        record=record,
        source=source,
        alias=alias,
        document=document,
        chunks=(chunk,),
        policy=policy,
        text=text,
        rendered_sha256=rendered_sha256,
        identity=identity,
    )


def projection_report(projection: ProofProjection) -> dict[str, object]:
    """Return a deep, JSON-safe report of the deterministic projection."""

    return {
        "entity_id": projection.entity_id,
        "record": copy.deepcopy(projection.record),
        "record_sha256": RECORD_SHA256,
        "rendered_sha256": projection.rendered_sha256,
        "identity": projection.identity,
        "source": copy.deepcopy(projection.source),
        "alias": copy.deepcopy(projection.alias),
        "document": copy.deepcopy(projection.document),
        "chunks": [copy.deepcopy(row) for row in projection.chunks],
        "policy": copy.deepcopy(projection.policy),
    }
