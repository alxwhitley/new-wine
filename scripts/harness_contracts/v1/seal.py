"""Terminal seal validation for harness contract v1 O3."""

import json
from typing import Any, Dict

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import RE_SHA256, _matches, _PacketValidator
from harness_contracts.v1.worker_result import RE_RFC3339


TERMINAL_STATES = {"ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED"}


def validate_terminal_seal(value: Any) -> Dict[str, Any]:
    """Validate a terminal seal record."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Terminal seal root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_terminal_seal_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_terminal_seal_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "packet_sha256",
        "terminal_state",
        "sealing_event_seq",
        "sealing_event_sha256",
        "sealed_at",
        "quarantine_reason",
        "human_required_reasons",
        "upstream_digests",
        "seal_sha256",
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

    for field in ("packet_id",):
        val = value.get(field)
        if not isinstance(val, str) or val.strip() == "":
            v.add("INVALID_VALUE", f"/{field}", f"{field} must be a non-empty string", phase="value")

    if not _matches(value.get("packet_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/packet_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    terminal_state = value.get("terminal_state")
    v.check_enum(terminal_state, TERMINAL_STATES, "/terminal_state")

    sealing_event_seq = value.get("sealing_event_seq")
    if isinstance(sealing_event_seq, bool) or not isinstance(sealing_event_seq, int):
        v.add("INVALID_TYPE", "/sealing_event_seq", "Expected integer", phase="scalar")
    elif sealing_event_seq < 1:
        v.add("INVALID_VALUE", "/sealing_event_seq", "sealing_event_seq must be a positive integer", phase="value")

    if not _matches(value.get("sealing_event_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/sealing_event_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    sealed_at = value.get("sealed_at")
    if not _matches(sealed_at, RE_RFC3339):
        v.add("INVALID_FORMAT", "/sealed_at", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

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

    upstream_digests = value.get("upstream_digests")
    if terminal_state == "ACCEPTED":
        if not isinstance(upstream_digests, dict):
            v.add("INVALID_TYPE", "/upstream_digests", "Expected object for ACCEPTED seal", phase="scalar")
        else:
            for key in ("packet_sha256", "result_sha256", "verdict_sha256", "bundle_sha256"):
                if key not in upstream_digests:
                    v.add("MISSING_FIELD", f"/upstream_digests/{key}", f"Missing required field '{key}'")
                elif not _matches(upstream_digests[key], RE_SHA256):
                    v.add("INVALID_FORMAT", f"/upstream_digests/{key}", "Must be 64-character lowercase SHA-256 hex", phase="format")
            for key in upstream_digests:
                if key not in {"packet_sha256", "result_sha256", "verdict_sha256", "bundle_sha256"}:
                    v.add("UNKNOWN_FIELD", f"/upstream_digests/{key}", f"Unknown field '{key}'")
    else:
        if upstream_digests is not None:
            v.add("INVALID_VALUE", "/upstream_digests", "upstream_digests must be null when terminal_state is not ACCEPTED", phase="value")

    declared = value.get("seal_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"seal_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/seal_sha256", "seal_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/seal_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")
