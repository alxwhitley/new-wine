"""Packet state projection validation for harness contract v1 O3."""

import json
from typing import Any, Dict, List, Optional

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.classification import ATTEMPT_CLASSES
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import LANES, PACKET_STATES, RE_SHA256, _matches, _PacketValidator
from harness_contracts.v1.worker_result import RE_RFC3339

ZERO_SHA256 = "0" * 64


def _check_int(v: _PacketValidator, value: Any, path: str, min_value: Optional[int] = None, nonneg: bool = False) -> bool:
    if isinstance(value, bool):
        v.add("INVALID_TYPE", path, "Expected integer, not boolean", phase="scalar")
        return False
    if not isinstance(value, int):
        v.add("INVALID_TYPE", path, "Expected integer", phase="scalar")
        return False
    if nonneg and value < 0:
        v.add("INVALID_VALUE", path, "Must be a non-negative integer", phase="value")
        return False
    if min_value is not None and value < min_value:
        v.add("INVALID_VALUE", path, f"Must be >= {min_value}", phase="value")
        return False
    return True


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
        return False
    return True


def _check_rfc3339_or_null(v: _PacketValidator, value: Any, path: str) -> bool:
    if value is None:
        return True
    if not _matches(value, RE_RFC3339):
        v.add("INVALID_FORMAT", path, "Must be RFC3339 UTC timestamp ending in Z or null", phase="format")
        return False
    return True


def validate_packet_state(value: Any) -> Dict[str, Any]:
    """Validate a per-packet state projection."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Packet state root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_packet_state_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_packet_state_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "enqueue_seq",
        "state",
        "lane",
        "dependency_ids",
        "packet_sha256",
        "attempts_started",
        "infra_retries_used",
        "revise_cycles_used",
        "revise_verdicts",
        "reassignment_used",
        "open_attempt",
        "earliest_next_attempt_at",
        "last_event_seq",
        "terminal_seal_sha256",
        "lane_history",
        "attempts",
        "quarantine_reason",
        "human_required_reasons",
        "last_applied_seq",
        "last_applied_event_sha256",
        "state_sha256",
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

    val = value.get("packet_id")
    if not isinstance(val, str) or val.strip() == "":
        v.add("INVALID_VALUE", "/packet_id", "packet_id must be a non-empty string", phase="value")

    _check_int(v, value.get("enqueue_seq"), "/enqueue_seq", min_value=1)
    v.check_enum(value.get("state"), PACKET_STATES, "/state")
    v.check_enum(value.get("lane"), LANES, "/lane")

    deps = value.get("dependency_ids")
    if not isinstance(deps, list):
        v.add("INVALID_TYPE", "/dependency_ids", "Expected array", phase="scalar")
    else:
        for i, dep in enumerate(deps):
            if not isinstance(dep, str) or dep.strip() == "":
                v.add("INVALID_VALUE", f"/dependency_ids/{i}", "Dependency ID must be a non-empty string", phase="value")

    _check_sha256(v, value.get("packet_sha256"), "/packet_sha256")
    _check_int(v, value.get("attempts_started"), "/attempts_started", nonneg=True)
    _check_int(v, value.get("infra_retries_used"), "/infra_retries_used", nonneg=True)
    _check_int(v, value.get("revise_cycles_used"), "/revise_cycles_used", nonneg=True)
    _check_int(v, value.get("revise_verdicts"), "/revise_verdicts", nonneg=True)

    if not isinstance(value.get("reassignment_used"), bool):
        v.add("INVALID_TYPE", "/reassignment_used", "Expected boolean", phase="scalar")

    open_attempt = value.get("open_attempt")
    if open_attempt is not None and not _check_int(v, open_attempt, "/open_attempt", min_value=1):
        pass

    _check_rfc3339_or_null(v, value.get("earliest_next_attempt_at"), "/earliest_next_attempt_at")
    _check_int(v, value.get("last_event_seq"), "/last_event_seq", min_value=1)

    tss = value.get("terminal_seal_sha256")
    if tss is not None and not _matches(tss, RE_SHA256):
        v.add("INVALID_FORMAT", "/terminal_seal_sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    lane_history = value.get("lane_history")
    if not isinstance(lane_history, list) or len(lane_history) < 1 or len(lane_history) > 2:
        v.add("INVALID_VALUE", "/lane_history", "lane_history must contain 1 or 2 entries", phase="value")
    else:
        for i, lh in enumerate(lane_history):
            p = f"/lane_history/{i}"
            if not isinstance(lh, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("lane", "since_event_seq"):
                if key not in lh:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
                elif key == "lane":
                    v.check_enum(lh[key], LANES, f"{p}/{key}")
                else:
                    _check_int(v, lh[key], f"{p}/{key}", min_value=1)
            for key in lh:
                if key not in {"lane", "since_event_seq"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    attempts = value.get("attempts")
    if not isinstance(attempts, list):
        v.add("INVALID_TYPE", "/attempts", "Expected array", phase="scalar")
    else:
        seen: set = set()
        for i, att in enumerate(attempts):
            p = f"/attempts/{i}"
            if not isinstance(att, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            required = {"attempt", "lane", "started_event_seq", "finished_event_seq", "attempt_class", "result_sha256", "verdict_sha256", "provider_evidence_sha256", "bundle_sha256"}
            for key in att:
                if key not in required:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
            for key in required:
                if key not in att:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
            attempt = att.get("attempt")
            if isinstance(attempt, int) and not isinstance(attempt, bool):
                if attempt in seen:
                    v.add("DUPLICATE_ID", f"{p}/attempt", "Duplicate attempt number", phase="uniqueness")
                else:
                    seen.add(attempt)
            _check_int(v, attempt, f"{p}/attempt", min_value=1)
            v.check_enum(att.get("lane"), LANES, f"{p}/lane")
            _check_int(v, att.get("started_event_seq"), f"{p}/started_event_seq", min_value=1)
            finished = att.get("finished_event_seq")
            if finished is not None and not _check_int(v, finished, f"{p}/finished_event_seq", min_value=1):
                pass
            ac = att.get("attempt_class")
            if ac is not None:
                v.check_enum(ac, ATTEMPT_CLASSES, f"{p}/attempt_class")
            for key in ("result_sha256", "verdict_sha256", "provider_evidence_sha256", "bundle_sha256"):
                val = att.get(key)
                if val is not None and not _matches(val, RE_SHA256):
                    v.add("INVALID_FORMAT", f"{p}/{key}", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    qr = value.get("quarantine_reason")
    if qr is not None and (not isinstance(qr, str) or qr.strip() == ""):
        v.add("INVALID_VALUE", "/quarantine_reason", "quarantine_reason must be a non-empty string or null", phase="value")

    hrr = value.get("human_required_reasons")
    if not isinstance(hrr, list):
        v.add("INVALID_TYPE", "/human_required_reasons", "Expected array", phase="scalar")
    else:
        for i, reason in enumerate(hrr):
            if not isinstance(reason, str) or reason.strip() == "":
                v.add("INVALID_VALUE", f"/human_required_reasons/{i}", "Reason must be a non-empty string", phase="value")

    _check_int(v, value.get("last_applied_seq"), "/last_applied_seq", nonneg=True)

    laeh = value.get("last_applied_event_sha256")
    if laeh != ZERO_SHA256 and not _matches(laeh, RE_SHA256):
        v.add("INVALID_FORMAT", "/last_applied_event_sha256", "Must be 64-character lowercase SHA-256 hex or 64 zeros", phase="format")

    declared = value.get("state_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"state_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/state_sha256", "state_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/state_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")
