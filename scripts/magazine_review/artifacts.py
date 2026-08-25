"""Durable direct-write storage for immutable review artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Type

from .schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArtifactValidationError,
    IssueDecision,
    OCRManifest,
    PropositionReview,
    StageIdentity,
)


_ARTIFACT_TYPES: Mapping[str, Type[Any]] = {
    "OCRManifest": OCRManifest,
    "ArticleManifest": ArticleManifest,
    "PropositionReview": PropositionReview,
    "IssueDecision": IssueDecision,
    "ApprovedPropositionSet": ApprovedPropositionSet,
}


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("artifact_not_canonical_json") from exc


def _artifact_identity(value: Any) -> StageIdentity:
    identity = getattr(value, "identity", None)
    if not isinstance(identity, StageIdentity):
        raise ArtifactValidationError("artifact_identity_required")
    identity.validate()
    return identity


def _base_envelope(value: Any) -> dict[str, object]:
    artifact_type = type(value).__name__
    if artifact_type not in _ARTIFACT_TYPES or not hasattr(value, "to_dict"):
        raise ArtifactValidationError("artifact_type_unsupported")
    validator = getattr(value, "validate", None)
    if not callable(validator):
        raise ArtifactValidationError("artifact_validate_required")
    validator()
    identity = _artifact_identity(value)
    return {
        "artifact_type": artifact_type,
        "identity": identity.to_dict(),
        "payload": value.to_dict(),
    }


def write_artifact(path: Path, value: Any) -> str:
    """Write canonical JSON directly, fsync it, and verify the exact bytes.

    This deliberately uses no temp file and no rename/replace operation: paths
    are neither moved nor deleted as part of artifact persistence.
    """
    artifact_path = Path(path)
    base = _base_envelope(value)
    payload_sha256 = hashlib.sha256(_canonical_json(base)).hexdigest()
    envelope = dict(base)
    envelope["payload_sha256"] = payload_sha256
    encoded = _canonical_json(envelope)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    with artifact_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(encoded.decode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())

    with artifact_path.open("rb") as handle:
        persisted = handle.read()
    if hashlib.sha256(persisted).digest() != hashlib.sha256(encoded).digest():
        raise ArtifactValidationError("artifact_reopen_sha256_mismatch")
    return hashlib.sha256(persisted).hexdigest()


def load_valid_artifact_bytes(
    raw_bytes: bytes, expected_identity: StageIdentity
) -> Any:
    """Validate one immutable artifact byte snapshot for these exact inputs."""
    expected_identity.validate()
    if not isinstance(raw_bytes, bytes):
        raise ArtifactValidationError("artifact_bytes_required")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError("artifact_invalid_json") from exc
    if not isinstance(raw, Mapping) or set(raw) != {
        "artifact_type", "identity", "payload", "payload_sha256"
    }:
        raise ArtifactValidationError("artifact_envelope_invalid")
    artifact_type = raw.get("artifact_type")
    identity_raw = raw.get("identity")
    payload = raw.get("payload")
    recorded_sha256 = raw.get("payload_sha256")
    if (
        not isinstance(artifact_type, str)
        or not isinstance(identity_raw, Mapping)
        or not isinstance(payload, Mapping)
        or not isinstance(recorded_sha256, str)
    ):
        raise ArtifactValidationError("artifact_payload_sha256_mismatch")
    base = {
        "artifact_type": artifact_type,
        "identity": dict(identity_raw),
        "payload": dict(payload),
    }
    actual_sha256 = hashlib.sha256(_canonical_json(base)).hexdigest()
    if actual_sha256 != recorded_sha256:
        raise ArtifactValidationError("artifact_payload_sha256_mismatch")
    identity = StageIdentity.from_dict(identity_raw)
    if identity != expected_identity:
        raise ArtifactValidationError("artifact_identity_mismatch")
    artifact_class = _ARTIFACT_TYPES.get(artifact_type)
    if artifact_class is None:
        raise ArtifactValidationError("artifact_type_unsupported")
    try:
        value = artifact_class.from_dict(payload)
    except ArtifactValidationError:
        raise
    except Exception as exc:
        raise ArtifactValidationError("artifact_payload_invalid") from exc
    if _artifact_identity(value) != identity:
        raise ArtifactValidationError("artifact_identity_mismatch")
    value.validate()
    return value


def load_valid_artifact(path: Path, expected_identity: StageIdentity) -> Any:
    """Compatibility path wrapper around immutable snapshot validation."""
    artifact_path = Path(path)
    try:
        raw_bytes = artifact_path.read_bytes()
    except FileNotFoundError as exc:
        raise ArtifactValidationError("artifact_not_found") from exc
    return load_valid_artifact_bytes(raw_bytes, expected_identity)
