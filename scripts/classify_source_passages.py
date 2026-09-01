#!/usr/bin/env python3
"""Deterministic Phase 3 passage-policy classification.

This module is a repository-only policy contract. It does not import database,
model, retrieval, or answer-generation code and it never writes classification
rows. V1 recognizes only the structural fields Alex approved in Phase 0.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Optional, Sequence


RULE_VERSION = "biblical_context_structural_fields.v1"
ELIGIBLE_POLICY_CLASSES = frozenset(
    {"general_context", "orthodox_viewpoint", "protected_spirit_filled"}
)

APPROVED_FIELDS = {
    "stepbible_tipnr": frozenset(
        {
            "entity_type",
            "entity_id",
            "original_language.dstrong",
            "original_language.estrong",
            "original_language.source_script_form",
            "osis_references",
        }
    ),
    "openbible_structured_data:bible_geocoding": frozenset(
        {
            "place_id",
            "place_name",
            "place_types",
            "osis_references",
            "candidate_identifications[].modern_id",
            "candidate_identifications[].name",
            "candidate_identifications[].confidence_score",
        }
    ),
}

PROHIBITED_DATASETS = frozenset(
    {
        "openbible_structured_data:cross_references",
        "tyndale_open_resources:open_bible_dictionary",
        "tyndale_open_resources:open_study_notes",
    }
)


class ClassificationRefused(ValueError):
    """The caller requested a classification mode V1 cannot safely perform."""


@dataclass(frozen=True)
class PassageClassification:
    policy_class: str
    protected_topic_keys: tuple[str, ...] = ()
    issue_key: Optional[str] = None
    viewpoint_key: Optional[str] = None
    classifier_kind: str = "deterministic"
    rule_version: str = RULE_VERSION
    model: Optional[str] = None
    prompt_fingerprint: Optional[str] = None
    reason_codes: tuple[str, ...] = ()


def _require_identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ClassificationRefused(f"{label}_invalid")
    return value


def is_answer_eligible(policy_class: object) -> bool:
    """Return the class-level gate only; Phase 4 must still enforce routing."""

    return isinstance(policy_class, str) and policy_class in ELIGIBLE_POLICY_CLASSES


def classify_source_field(
    dataset_id: str,
    field_path: str,
    *,
    classifier_kind: str = "deterministic",
) -> PassageClassification:
    """Classify one canonical output field, failing closed on every unknown."""

    dataset_id = _require_identity(dataset_id, "dataset_id")
    field_path = _require_identity(field_path, "field_path")
    if classifier_kind != "deterministic":
        raise ClassificationRefused("model_classification_prohibited_in_v1")

    if field_path in APPROVED_FIELDS.get(dataset_id, frozenset()):
        return PassageClassification(
            policy_class="general_context",
            reason_codes=("approved_structural_field",),
        )

    reason = (
        "dataset_prohibited_in_v1"
        if dataset_id in PROHIBITED_DATASETS
        else "field_not_approved"
    )
    return PassageClassification(
        policy_class="uncertain",
        reason_codes=(reason,),
    )


def _json_payload(result: PassageClassification) -> dict[str, object]:
    payload = asdict(result)
    payload["answer_eligible"] = is_answer_eligible(result.policy_class)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify one approved structural field without database or model access."
    )
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--field-path", required=True)
    parser.add_argument(
        "--classifier-kind",
        default="deterministic",
        choices=("deterministic", "model"),
    )
    args = parser.parse_args(argv)
    try:
        result = classify_source_field(
            args.dataset_id,
            args.field_path,
            classifier_kind=args.classifier_kind,
        )
    except ClassificationRefused as exc:
        parser.exit(2, f"classification_refused={exc}\n")
    print(json.dumps(_json_payload(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
