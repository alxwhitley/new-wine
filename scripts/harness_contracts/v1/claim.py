"""Claim record validation and classification for harness contract v1 O3."""

import json
from typing import Any, Dict, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import LANES, RE_SHA256, _matches, _PacketValidator
from harness_contracts.v1.worker_result import RE_RFC3339


STAGES = {
    "enrollment",
    "claim",
    "result_record",
    "attempt_finish",
    "review_claim",
    "verdict_record",
    "promotion",
}

CLAIM_CLASSIFICATIONS = {
    "FOREIGN_HOST",
    "STALE_PRIOR_BOOT",
    "SELF_OWNED",
    "FOREIGN_LIVE",
    "STALE_SAME_BOOT",
}


def validate_claim(value: Any) -> Dict[str, Any]:
    """Validate a claim record."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Claim root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_claim_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_claim_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "intent_id",
        "stage",
        "attempt",
        "coordinator_id",
        "run_id",
        "hostname",
        "boot_id",
        "pid",
        "acquired_at",
        "heartbeat_at",
        "lease_seconds",
        "lane",
        "worktree_path",
        "claim_sha256",
    }
    value = v.value
    for key in value:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in value:
            v.add("MISSING_FIELD", f"/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    if value.get("schema_version") != 1:
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1", phase="value")

    for field in ("packet_id", "intent_id", "coordinator_id", "run_id", "hostname", "boot_id"):
        val = value.get(field)
        if not isinstance(val, str) or val.strip() == "":
            v.add("INVALID_VALUE", f"/{field}", f"{field} must be a non-empty string", phase="value")

    v.check_enum(value.get("stage"), STAGES, "/stage")

    attempt = value.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        v.add("INVALID_TYPE", "/attempt", "Expected integer", phase="scalar")
    elif attempt < 1:
        v.add("INVALID_VALUE", "/attempt", "attempt must be a positive integer", phase="value")

    pid = value.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int):
        v.add("INVALID_TYPE", "/pid", "Expected integer", phase="scalar")
    elif pid < 1:
        v.add("INVALID_VALUE", "/pid", "pid must be a positive integer", phase="value")

    for field in ("acquired_at", "heartbeat_at"):
        if not _matches(value.get(field), RE_RFC3339):
            v.add("INVALID_FORMAT", f"/{field}", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

    lease_seconds = value.get("lease_seconds")
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
        v.add("INVALID_TYPE", "/lease_seconds", "Expected integer", phase="scalar")
    elif lease_seconds <= 0:
        v.add("INVALID_VALUE", "/lease_seconds", "lease_seconds must be a positive integer", phase="value")

    v.check_enum(value.get("lane"), LANES, "/lane")

    worktree_path = value.get("worktree_path")
    if worktree_path is not None:
        if not isinstance(worktree_path, str) or worktree_path.strip() == "":
            v.add("INVALID_VALUE", "/worktree_path", "worktree_path must be a non-empty string when non-null", phase="value")
        elif not worktree_path.startswith("/"):
            v.add("INVALID_VALUE", "/worktree_path", "worktree_path must be absolute when non-null", phase="value")

    if not _matches(value.get("claim_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/claim_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    declared = value.get("claim_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"claim_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/claim_sha256", "claim_sha256 does not match canonical self-hash", phase="cross_field")


def classify_claim(
    record: Dict[str, Any],
    trusted_process_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify a claim record against trusted process context.

    Required trusted context keys:
      - coordinator_id
      - hostname
      - boot_id
      - pid
      - live_coordinator_ids (Set[str])
      - now

    Returns a dict with ``status`` and ``errors``.  The function never performs
    OS lookups itself.
    """
    required_keys = {"coordinator_id", "hostname", "boot_id", "pid", "live_coordinator_ids", "now"}
    missing = required_keys - set(trusted_process_context.keys())
    if missing:
        return {
            "status": "TRUST_CONTEXT_MISSING",
            "errors": [
                error(
                    "TRUST_CONTEXT_MISSING",
                    "",
                    f"Missing trusted process context keys: {sorted(missing)}",
                    phase="path_authority",
                )
            ],
        }

    live_ids = trusted_process_context["live_coordinator_ids"]
    if not isinstance(live_ids, set):
        return {
            "status": "TRUST_CONTEXT_MISSING",
            "errors": [
                error(
                    "TRUST_CONTEXT_MISSING",
                    "",
                    "live_coordinator_ids must be a set",
                    phase="path_authority",
                )
            ],
        }

    if record.get("hostname") != trusted_process_context["hostname"]:
        return {
            "status": "FOREIGN_HOST",
            "errors": [
                error(
                    "CLAIM_CONFLICT",
                    "/hostname",
                    "Claim belongs to a different host; refusing to reclaim",
                    phase="path_authority",
                )
            ],
        }

    if record.get("boot_id") != trusted_process_context["boot_id"]:
        return {"status": "STALE_PRIOR_BOOT", "errors": []}

    if record.get("coordinator_id") == trusted_process_context["coordinator_id"] and record.get("pid") == trusted_process_context["pid"]:
        return {"status": "SELF_OWNED", "errors": []}

    if record.get("coordinator_id") in live_ids:
        return {
            "status": "FOREIGN_LIVE",
            "errors": [
                error(
                    "CLAIM_CONFLICT",
                    "/coordinator_id",
                    "Claim owner is a live coordinator; refusing to steal",
                    phase="path_authority",
                )
            ],
        }

    return {"status": "STALE_SAME_BOOT", "errors": []}
