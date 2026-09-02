#!/usr/bin/env python3
"""Manifest contracts for zero-write biblical-context Phase 2 tooling."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

import yaml


EXPECTED_DATASET_IDS = frozenset(
    {
        "openbible_structured_data",
        "stepbible_data",
        "stepbible_tipnr",
        "tyndale_open_resources",
    }
)
DENIED_AUTHORIZATIONS = {
    "source_registration_authorized": False,
    "database_write_authorized": False,
    "ingestion_authorized": False,
    "visibility_change_authorized": False,
    "passage_classification_authorized": False,
    "retrieval_change_authorized": False,
    "answer_path_change_authorized": False,
    "deployment_authorized": False,
}


class ContractError(ValueError):
    """Raised when a governing Phase 0 manifest contract drifts."""


def canonical_json_bytes(value: object) -> bytes:
    """Return stable UTF-8 canonical JSON with exactly one trailing newline."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractError(reason)
    return value


def _normalize_alias(value: str) -> str:
    return " ".join(value.lower().split())


def _validate_manifests(
    manifests: Mapping[str, Mapping[str, object]],
) -> None:
    if set(manifests) != EXPECTED_DATASET_IDS:
        raise ContractError("unsupported_dataset")

    for dataset_id, manifest in manifests.items():
        if manifest.get("dataset_id") != dataset_id:
            raise ContractError("dataset_identity_mismatch")
        if manifest.get("schema_version") != 1:
            raise ContractError("unsupported_schema_version")

        decision = _require_mapping(
            manifest.get("decision"), "decision_contract_invalid"
        )
        if decision.get("status") != "approved":
            raise ContractError("decision_not_approved")
        if decision.get("approved_by") != "Alex Whitley":
            raise ContractError("decision_approver_changed")
        if decision.get("approved_at") != "2026-09-01":
            raise ContractError("decision_date_changed")

        authorization = _require_mapping(
            manifest.get("authorization"), "authorization_contract_invalid"
        )
        if dict(authorization) != DENIED_AUTHORIZATIONS:
            raise ContractError("authorization_boundary_changed")


def load_approved_manifests(
    manifest_dir: Path,
) -> dict[str, dict[str, object]]:
    """Load only the four approved Phase 0 manifest files."""

    manifests: dict[str, dict[str, object]] = {}
    for path in sorted(manifest_dir.glob("*.yaml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ContractError("manifest_not_mapping")
        dataset_id = value.get("dataset_id")
        if not isinstance(dataset_id, str):
            raise ContractError("dataset_identity_missing")
        if dataset_id in manifests:
            raise ContractError("duplicate_dataset_identity")
        manifests[dataset_id] = value
    _validate_manifests(manifests)
    return manifests


def compile_registration_preview(
    manifests: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Project the five approved future hidden source rows without UUIDs."""

    _validate_manifests(manifests)
    rows: list[dict[str, object]] = []
    slugs: set[str] = set()
    aliases: set[str] = set()

    for dataset_id in sorted(manifests):
        manifest = manifests[dataset_id]
        registration = _require_mapping(
            manifest.get("proposed_registration"),
            "registration_contract_invalid",
        )
        source_rows = registration.get("source_rows", ())
        if not isinstance(source_rows, (list, tuple)):
            raise ContractError("registration_rows_invalid")

        license_data = _require_mapping(manifest.get("license"), "license_invalid")
        license_status = registration.get("license_status")
        if license_status != "licensed":
            raise ContractError("registration_license_not_licensed")

        for raw_row in source_rows:
            source_row = _require_mapping(raw_row, "registration_row_invalid")
            if source_row.get("visibility") != "hidden":
                raise ContractError("registration_not_hidden")
            name = source_row.get("name")
            slug = source_row.get("slug")
            if not isinstance(name, str) or not name.strip():
                raise ContractError("registration_name_invalid")
            if not isinstance(slug, str) or not slug.strip():
                raise ContractError("registration_slug_invalid")
            if slug in slugs:
                raise ContractError("duplicate_registration_slug")
            slugs.add(slug)

            raw_aliases = source_row.get("aliases", ())
            if not isinstance(raw_aliases, (list, tuple)):
                raise ContractError("registration_aliases_invalid")
            normalized_aliases: list[str] = []
            for alias in raw_aliases:
                if not isinstance(alias, str) or not alias.strip():
                    raise ContractError("registration_alias_invalid")
                normalized = _normalize_alias(alias)
                if normalized in aliases:
                    raise ContractError("duplicate_registration_alias")
                aliases.add(normalized)
                normalized_aliases.append(alias)

            rows.append(
                {
                    "dataset_id": dataset_id,
                    "name": name,
                    "slug": slug,
                    "license_status": license_status,
                    "license": dict(license_data),
                    "visibility": "hidden",
                    "source_kind": source_row.get("source_kind"),
                    "citation_mode": source_row.get("citation_mode"),
                    "aliases": sorted(normalized_aliases),
                    "ingestion_policy": source_row.get(
                        "ingestion_policy", "eligible_for_phase_2_preview"
                    ),
                }
            )

    return tuple(sorted(rows, key=lambda row: str(row["slug"])))


def compile_ingestion_policies(
    manifests: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Compile the two eligible and three prohibited Phase 2 dataset policies."""

    _validate_manifests(manifests)
    tipnr = manifests["stepbible_tipnr"]
    tipnr_policy = _require_mapping(tipnr.get("v1_policy"), "tipnr_policy_invalid")

    openbible = manifests["openbible_structured_data"]
    openbible_policy = _require_mapping(
        openbible.get("v1_policy"), "openbible_policy_invalid"
    )
    openbible_datasets = _require_mapping(
        openbible_policy.get("datasets"), "openbible_datasets_invalid"
    )
    geocoding = _require_mapping(
        openbible_datasets.get("bible_geocoding"), "openbible_geocoding_invalid"
    )
    cross_references = _require_mapping(
        openbible_datasets.get("cross_references"),
        "openbible_cross_references_invalid",
    )

    return {
        "stepbible_tipnr": {
            "dataset_id": "stepbible_tipnr",
            "ingestion_policy": "eligible_for_phase_2_preview",
            "input_file": tipnr_policy.get("input_file"),
            "allowed_raw_fields": tipnr_policy.get("allowed_raw_fields"),
            "allowed_output_fields": tipnr_policy.get("allowed_output_fields"),
            "unknown_field_policy": tipnr_policy.get("unknown_field_policy"),
        },
        "openbible_structured_data:bible_geocoding": {
            "dataset_id": "openbible_structured_data:bible_geocoding",
            "ingestion_policy": "eligible_for_phase_2_preview",
            "input_file": geocoding.get("input_file"),
            "allowed_raw_fields": geocoding.get("allowed_raw_fields"),
            "allowed_output_fields": geocoding.get("allowed_output_fields"),
            "unknown_field_policy": geocoding.get("unknown_field_policy"),
        },
        "openbible_structured_data:cross_references": {
            "dataset_id": "openbible_structured_data:cross_references",
            "ingestion_policy": "prohibited_in_v1",
            "eligible": cross_references.get("eligible"),
        },
        "tyndale_open_resources:open_bible_dictionary": {
            "dataset_id": "tyndale_open_resources:open_bible_dictionary",
            "ingestion_policy": "prohibited_in_v1",
            "eligible": False,
        },
        "tyndale_open_resources:open_study_notes": {
            "dataset_id": "tyndale_open_resources:open_study_notes",
            "ingestion_policy": "prohibited_in_v1",
            "eligible": False,
        },
    }
