#!/usr/bin/env python3
"""Validate the Phase 0 biblical-context source manifests.

Read-only. No network or database access.

Run: python3.12 scripts/test_biblical_source_manifests.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ROOT / "docs" / "ingestion" / "source_manifests"
EXPECTED = (
    "tyndale_open_resources.yaml",
    "stepbible_data.yaml",
    "tipnr.yaml",
    "openbible.yaml",
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
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

TIPNR_RAW_FIELDS = {
    "entity marker `$========== {PERSON(s)|PLACE|OTHER}`",
    "primary row column 1 `UnifiedName=uStrong`, substring after final `=`",
    "non-Total form row column 3 `dStrong«eStrong=Heb/Grk`",
    "non-Total form row column 5 `All Refs`",
}
TIPNR_OUTPUT_FIELDS = {
    "entity_type",
    "entity_id",
    "original_language.dstrong",
    "original_language.estrong",
    "original_language.source_script_form",
    "osis_references",
}
OPENBIBLE_GEO_RAW_FIELDS = {
    "$.id",
    "$.friendly_id",
    "$.types[]",
    "$.verses[].osis",
    "$.modern_associations.<key>",
    "$.modern_associations.*.name",
    "$.modern_associations.*.score",
}
OPENBIBLE_GEO_OUTPUT_FIELDS = {
    "place_id",
    "place_name",
    "place_types",
    "osis_references",
    "candidate_identifications[].modern_id",
    "candidate_identifications[].name",
    "candidate_identifications[].confidence_score",
}
TIPNR_FIELD_RECORDS = [
    {
        "raw_path": "entity marker `$========== {PERSON(s)|PLACE|OTHER}`",
        "output_field": "entity_type",
        "transform": "closed mapping PERSON(s)->person, PLACE->place, OTHER->other; reject every other marker",
        "provenance": "TIPNR structural record marker",
    },
    {
        "raw_path": "primary row column 1 `UnifiedName=uStrong`, substring after final `=`",
        "output_field": "entity_id",
        "transform": "retain only the source uStrong token; discard the translated-name and reference prefix",
        "provenance": "TIPNR uStrong identifier",
    },
    {
        "raw_path": "non-Total form row column 3 `dStrong«eStrong=Heb/Grk`",
        "output_field": "original_language",
        "transform": "split exactly into dstrong, estrong, and source_script_form; reject a row that does not parse all three components",
        "provenance": "TIPNR disambiguated/electronic Strong identifiers and Hebrew/Greek form",
    },
    {
        "raw_path": "non-Total form row column 5 `All Refs`",
        "output_field": "osis_references",
        "transform": "split source reference list; preserve subverse suffixes; reject abbreviations such as `ff` rather than expanding them",
        "provenance": "TIPNR exhaustive occurrence field",
    },
]
OPENBIBLE_GEO_FIELD_RECORDS = [
    {
        "raw_path": "$.id",
        "output_field": "place_id",
        "transform": "copy exact string",
        "provenance": "OpenBible ancient-place dataset identifier",
    },
    {
        "raw_path": "$.friendly_id",
        "output_field": "place_name",
        "transform": "copy exact dataset label; do not consult translation_name_counts, verses[].readable, linked_data, or extra",
        "provenance": "OpenBible ancient-place dataset label under the repository-level CC BY 4.0 grant; source-level scholarly provenance is not asserted",
    },
    {
        "raw_path": "$.types[]",
        "output_field": "place_types",
        "transform": "copy exact strings from the documented closed type vocabulary",
        "provenance": "OpenBible ancient-place classification under the repository-level CC BY 4.0 grant",
    },
    {
        "raw_path": "$.verses[].osis",
        "output_field": "osis_references",
        "transform": "copy only OSIS identifiers; discard every sibling key",
        "provenance": "OpenBible catalog of where the Bible text mentions the place",
    },
    {
        "raw_path": "$.modern_associations.<key>",
        "output_field": "candidate_identifications[].modern_id",
        "transform": "copy the exact modern_associations mapping key; do not infer it from nested or excluded fields",
        "provenance": "OpenBible aggregate scholarly identification key; underlying sources are cataloged in data/source.jsonl",
    },
    {
        "raw_path": "$.modern_associations.*.name",
        "output_field": "candidate_identifications[].name",
        "transform": "copy exact dataset label",
        "provenance": "OpenBible aggregate scholarly identification label under the repository-level CC BY 4.0 grant",
    },
    {
        "raw_path": "$.modern_associations.*.score",
        "output_field": "candidate_identifications[].confidence_score",
        "transform": "copy integer without converting it to a probability or categorical fact",
        "provenance": "OpenBible aggregate confidence score computed from its cited-source voting model",
    },
]
TYNDALE_ROWS = [
    {
        "name": "Tyndale Open Study Notes",
        "slug": "tyndale-open-study-notes",
        "visibility": "hidden",
        "ingestion_policy": "prohibited_in_v1",
    },
    {
        "name": "Tyndale Open Bible Dictionary",
        "slug": "tyndale-open-bible-dictionary",
        "visibility": "hidden",
        "ingestion_policy": "prohibited_in_v1",
    },
]
TIPNR_ROWS = [
    {
        "name": "STEPBible TIPNR",
        "slug": "stepbible-tipnr",
        "visibility": "hidden",
        "source_kind": "biblical_context",
        "citation_mode": "citable",
        "aliases": ["stepbible tipnr"],
    }
]
OPENBIBLE_ROWS = [
    {
        "name": "OpenBible.info Bible Geocoding Data",
        "slug": "openbible-bible-geocoding",
        "visibility": "hidden",
        "source_kind": "biblical_context",
        "citation_mode": "citable",
        "aliases": ["openbible geocoding"],
    },
    {
        "name": "OpenBible.info Cross References",
        "slug": "openbible-cross-references",
        "visibility": "hidden",
        "ingestion_policy": "prohibited_in_v1",
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_manifest(path: Path) -> None:
    require(path.is_file(), f"missing manifest: {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{path.name}: top level must be a mapping")
    require(data.get("schema_version") == 1, f"{path.name}: schema_version must be 1")

    for field in (
        "dataset_id",
        "official_name",
        "official_url",
        "rights_holder",
        "reviewed_at",
        "license",
        "reviewed_artifacts",
        "nested_rights",
        "v1_policy",
        "proposed_registration",
        "decision",
        "authorization",
    ):
        require(field in data, f"{path.name}: missing {field}")

    require(data["reviewed_at"] == "2026-09-01", f"{path.name}: wrong review date")
    require(str(data["official_url"]).startswith("https://"), f"{path.name}: official_url must be HTTPS")

    license_data = data["license"]
    require(isinstance(license_data, dict), f"{path.name}: license must be a mapping")
    require(license_data.get("spdx") in {"CC-BY-4.0", "CC-BY-SA-4.0"}, f"{path.name}: unexpected SPDX license")
    require(str(license_data.get("url", "")).startswith("https://creativecommons.org/"), f"{path.name}: canonical CC URL required")

    artifacts = data["reviewed_artifacts"]
    require(isinstance(artifacts, list) and artifacts, f"{path.name}: at least one reviewed artifact required")
    for artifact in artifacts:
        require(isinstance(artifact, dict), f"{path.name}: artifact must be a mapping")
        require(SHA256_RE.fullmatch(str(artifact.get("sha256", ""))) is not None, f"{path.name}: artifact sha256 invalid")
        require(int(artifact.get("bytes", 0)) > 0, f"{path.name}: artifact bytes must be positive")

    registration = data["proposed_registration"]
    require(isinstance(registration, dict), f"{path.name}: proposed_registration must be a mapping")
    require(registration.get("license_status") == "licensed", f"{path.name}: CC material must not be labeled public_domain")
    require(registration.get("visibility") in {"hidden", "shown"}, f"{path.name}: explicit visibility required")

    decision = data["decision"]
    require(isinstance(decision, dict), f"{path.name}: decision must be a mapping")
    require(decision.get("status") == "approved", f"{path.name}: Phase 0 disposition must be approved")
    require(decision.get("approved_by") == "Alex Whitley", f"{path.name}: approval owner missing")
    require(decision.get("approved_at") == "2026-09-01", f"{path.name}: approval date missing")
    require(bool(decision.get("disposition")), f"{path.name}: approved disposition required")
    require("question" not in decision, f"{path.name}: approved decision must not retain an open question")

    authorization = data["authorization"]
    require(
        authorization == DENIED_AUTHORIZATIONS,
        f"{path.name}: Phase 0 approval must preserve the exact no-write/no-release boundary",
    )


def values(rows: list[dict], key: str) -> set[str]:
    return {str(row.get(key)) for row in rows}


def validate_policy_contracts(manifests: dict[str, dict]) -> None:
    tyndale = manifests["tyndale_open_resources.yaml"]
    require(tyndale["v1_policy"]["ordinary_answer_eligible"] is False, "Tyndale prose must be ordinary-answer ineligible")
    require(tyndale["v1_policy"]["study_mode_eligible"] is False, "Tyndale must not be enabled in Study Mode by Phase 0")
    require(tyndale["v1_policy"]["allowed_fields"] == [], "Tyndale V1 allowlist must be empty")
    require(tyndale["v1_policy"]["unknown_field_policy"] == "reject", "Tyndale unknown fields must fail closed")
    tyndale_notices = {item["name"]: item.get("reviewed_notice", {}) for item in tyndale["reviewed_artifacts"]}
    require(
        tyndale_notices["Tyndale Open Study Notes archive"].get("copyright")
        == "Copyright (C) 2022 by Tyndale House Publishers.",
        "Tyndale Study Notes exact notice missing",
    )
    require(
        tyndale_notices["Tyndale Open Study Notes archive"].get("adaptation_credit")
        == "Adapted from Tyndale Open Study Notes. The original work by Tyndale House Publishers is available for free at http://www.tyndaleopenresources.com.",
        "Tyndale Study Notes adaptation credit missing",
    )
    require(
        tyndale_notices["Tyndale Open Bible Dictionary archive"].get("copyright")
        == "Copyright (C) 2023 by Tyndale House Publishers.",
        "Tyndale Dictionary exact notice missing",
    )
    require(
        tyndale_notices["Tyndale Open Bible Dictionary archive"].get("adaptation_credit")
        == "Adapted from Tyndale Open Bible Dictionary. The original work by Tyndale House Publishers is available for free at http://www.tyndaleopenresources.com.",
        "Tyndale Dictionary adaptation credit missing",
    )
    require(tyndale["proposed_registration"]["source_rows"] == TYNDALE_ROWS, "Tyndale proposed rows changed")
    require(
        tyndale["decision"]["disposition"]
        == "Approve the future hidden per-work registration proposal for provenance only; no registration, ingestion, or exposure is authorized now.",
        "Tyndale approval disposition widened",
    )

    repository = manifests["stepbible_data.yaml"]
    require(repository["v1_policy"]["ordinary_answer_eligible"] is False, "repository-wide STEPBible ingestion must be ineligible")
    require(repository["v1_policy"]["allowed_fields"] == [], "repository-wide STEPBible allowlist must be empty")
    require(repository["proposed_registration"]["existing_source"]["proposed_license_status"] == "licensed", "STEPBible metadata correction must be licensed")
    require(
        repository["decision"]["disposition"]
        == "Approve the correction proposal in principle; the database write remains deferred until a separate attended retrieval-impact authorization.",
        "STEPBible deferred-write disposition widened",
    )

    tipnr = manifests["tipnr.yaml"]
    tipnr_policy = tipnr["v1_policy"]
    require(tipnr_policy["ordinary_answer_eligible"] is True, "TIPNR approved field subset must be eligible")
    require(tipnr_policy["unknown_field_policy"] == "reject", "TIPNR unknown fields must fail closed")
    require(values(tipnr_policy["allowed_raw_fields"], "raw_path") == TIPNR_RAW_FIELDS, "TIPNR raw-field allowlist changed")
    require(tipnr_policy["allowed_raw_fields"] == TIPNR_FIELD_RECORDS, "TIPNR field transforms or provenance changed")
    require(set(tipnr_policy["allowed_output_fields"]) == TIPNR_OUTPUT_FIELDS, "TIPNR output allowlist changed")
    require(len(tipnr_policy["allowed_raw_fields"]) == len(TIPNR_RAW_FIELDS), "TIPNR raw-field allowlist contains duplicates")
    require(len(tipnr_policy["allowed_output_fields"]) == len(TIPNR_OUTPUT_FIELDS), "TIPNR output allowlist contains duplicates")
    require(tipnr["proposed_registration"]["source_rows"] == TIPNR_ROWS, "TIPNR proposed rows changed")
    require(
        tipnr["decision"]["disposition"]
        == "Approve the V1 field allowlist and future hidden dataset-registration proposal; no registration, parser execution, or ingestion is authorized now.",
        "TIPNR approval disposition widened",
    )

    openbible = manifests["openbible.yaml"]
    geo = openbible["v1_policy"]["datasets"]["bible_geocoding"]
    crossrefs = openbible["v1_policy"]["datasets"]["cross_references"]
    require(geo["eligible"] is True, "OpenBible geocoding approved subset must be eligible")
    require(geo["input_file"] == "data/ancient.jsonl", "OpenBible V1 input must remain ancient.jsonl only")
    require(geo["unknown_field_policy"] == "reject", "OpenBible geocoding unknown fields must fail closed")
    require(values(geo["allowed_raw_fields"], "raw_path") == OPENBIBLE_GEO_RAW_FIELDS, "OpenBible raw-field allowlist changed")
    require(geo["allowed_raw_fields"] == OPENBIBLE_GEO_FIELD_RECORDS, "OpenBible field transforms or provenance changed")
    require(set(geo["allowed_output_fields"]) == OPENBIBLE_GEO_OUTPUT_FIELDS, "OpenBible output allowlist changed")
    require(len(geo["allowed_raw_fields"]) == len(OPENBIBLE_GEO_RAW_FIELDS), "OpenBible raw-field allowlist contains duplicates")
    require(len(geo["allowed_output_fields"]) == len(OPENBIBLE_GEO_OUTPUT_FIELDS), "OpenBible output allowlist contains duplicates")
    require(crossrefs["eligible"] is False, "OpenBible cross references must remain ineligible")
    require(crossrefs["allowed_fields"] == [], "OpenBible cross-reference allowlist must be empty")
    require(crossrefs["unknown_field_policy"] == "reject", "OpenBible cross-reference fields must fail closed")
    require(openbible["proposed_registration"]["source_rows"] == OPENBIBLE_ROWS, "OpenBible proposed rows changed")
    require(
        openbible["decision"]["disposition"]
        == "Approve the geocoding-only V1 boundary and future hidden per-dataset registration proposal; cross references remain prohibited and no registration or ingestion is authorized now.",
        "OpenBible approval disposition widened",
    )


def main() -> int:
    manifests = {}
    for name in EXPECTED:
        path = MANIFEST_DIR / name
        validate_manifest(path)
        manifests[name] = yaml.safe_load(path.read_text(encoding="utf-8"))
        print(f"PASS {name}")
    validate_policy_contracts(manifests)
    print("PASS manifest-specific safety contracts")
    print(f"PASS {len(EXPECTED)} manifests; 0 failures")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
