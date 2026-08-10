"""Reassignment record validation for harness contract v1 O3."""

import json
from typing import Any, Dict, Optional

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import LANES, RE_SHA256, _matches, _normalize_relative_path, _PacketValidator, is_repo_relative_path
from harness_contracts.v1.worker_result import RE_RFC3339


LANE_TRANSITIONS = {("kimi_implementation", "sonnet_implementation")}


def validate_reassignment(value: Any) -> Dict[str, Any]:
    """Validate a reassignment record."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Reassignment root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_reassignment_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_reassignment_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "packet_sha256",
        "from_lane",
        "to_lane",
        "reassigned_at",
        "at_event_seq",
        "kimi_attempt",
        "preserved",
        "reassignment_sha256",
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

    from_lane = value.get("from_lane")
    to_lane = value.get("to_lane")
    v.check_enum(from_lane, LANES, "/from_lane")
    v.check_enum(to_lane, LANES, "/to_lane")
    if (from_lane, to_lane) not in LANE_TRANSITIONS:
        v.add("INVALID_TRANSITION", "/to_lane", "Lane transition is not permitted", phase="transition")

    if not _matches(value.get("reassigned_at"), RE_RFC3339):
        v.add("INVALID_FORMAT", "/reassigned_at", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

    at_event_seq = value.get("at_event_seq")
    if isinstance(at_event_seq, bool) or not isinstance(at_event_seq, int):
        v.add("INVALID_TYPE", "/at_event_seq", "Expected integer", phase="scalar")
    elif at_event_seq < 1:
        v.add("INVALID_VALUE", "/at_event_seq", "at_event_seq must be a positive integer", phase="value")

    kimi_attempt = value.get("kimi_attempt")
    if isinstance(kimi_attempt, bool) or not isinstance(kimi_attempt, int):
        v.add("INVALID_TYPE", "/kimi_attempt", "Expected integer", phase="scalar")
    elif kimi_attempt < 1:
        v.add("INVALID_VALUE", "/kimi_attempt", "kimi_attempt must be a positive integer", phase="value")

    preserved = value.get("preserved")
    if isinstance(preserved, dict):
        _validate_preserved(v, preserved, "/preserved")
    else:
        v.add("INVALID_TYPE", "/preserved", "Expected object", phase="scalar")

    declared = value.get("reassignment_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"reassignment_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/reassignment_sha256", "reassignment_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/reassignment_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")


def _validate_preserved(v: _PacketValidator, preserved: Dict[str, Any], path: str) -> None:
    required = {
        "changed_files",
        "worker_result",
        "provider_evidence",
        "attempt_outcome",
        "checkpoints",
        "verification_evidence",
        "remaining_criterion_ids",
        "journal_range",
    }
    for key in preserved:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in preserved:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    changed_files = preserved.get("changed_files")
    if not isinstance(changed_files, list):
        v.add("INVALID_TYPE", f"{path}/changed_files", "Expected array", phase="scalar")
    else:
        seen: set = set()
        for i, cf in enumerate(changed_files):
            p = f"{path}/changed_files/{i}"
            if not isinstance(cf, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("path", "status", "before_sha256", "after_sha256"):
                if key not in cf:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
            if "path" in cf:
                normalized = _check_repo_relative_path(v, cf["path"], f"{p}/path")
                if normalized is not None:
                    if normalized in seen:
                        v.add("DUPLICATE_PATH", f"{p}/path", "Duplicate changed file path", phase="uniqueness")
                    else:
                        seen.add(normalized)
            if "status" in cf:
                v.check_enum(cf["status"], {"added", "modified", "deleted", "renamed"}, f"{p}/status")
            for key in ("before_sha256", "after_sha256"):
                if key in cf and cf[key] is not None and not _matches(cf[key], RE_SHA256):
                    v.add("INVALID_FORMAT", f"{p}/{key}", "Must be 64-character lowercase SHA-256 hex or null", phase="format")
            for key in cf:
                if key not in {"path", "status", "before_sha256", "after_sha256"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    _validate_digest_pointer(v, preserved.get("worker_result"), f"{path}/worker_result", required={"result_id", "result_sha256", "path"})
    _validate_digest_pointer(v, preserved.get("provider_evidence"), f"{path}/provider_evidence", required={"evidence_id", "evidence_sha256", "path"})
    _validate_digest_pointer(v, preserved.get("attempt_outcome"), f"{path}/attempt_outcome", required={"outcome_sha256", "path"})

    checkpoints = preserved.get("checkpoints")
    if not isinstance(checkpoints, list):
        v.add("INVALID_TYPE", f"{path}/checkpoints", "Expected array", phase="scalar")
    else:
        seen: set = set()
        for i, cp in enumerate(checkpoints):
            p = f"{path}/checkpoints/{i}"
            if not isinstance(cp, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("artifact_id", "path", "sha256"):
                if key not in cp:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
            if "artifact_id" in cp:
                aid = cp["artifact_id"]
                if not isinstance(aid, str) or aid.strip() == "":
                    v.add("INVALID_VALUE", f"{p}/artifact_id", "artifact_id must be a non-empty string", phase="value")
                elif aid in seen:
                    v.add("DUPLICATE_ID", f"{p}/artifact_id", "Duplicate artifact_id", phase="uniqueness")
                else:
                    seen.add(aid)
            if "path" in cp:
                _check_repo_relative_path(v, cp["path"], f"{p}/path")
            if "sha256" in cp:
                _check_sha256(v, cp["sha256"], f"{p}/sha256")
            for key in cp:
                if key not in {"artifact_id", "path", "sha256"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    verification_evidence = preserved.get("verification_evidence")
    if not isinstance(verification_evidence, list):
        v.add("INVALID_TYPE", f"{path}/verification_evidence", "Expected array", phase="scalar")
    else:
        seen: set = set()
        for i, ev in enumerate(verification_evidence):
            p = f"{path}/verification_evidence/{i}"
            if not isinstance(ev, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("evidence_id", "command_id", "artifact_path", "artifact_sha256"):
                if key not in ev:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
            if "evidence_id" in ev:
                eid = ev["evidence_id"]
                if not isinstance(eid, str) or eid.strip() == "":
                    v.add("INVALID_VALUE", f"{p}/evidence_id", "evidence_id must be a non-empty string", phase="value")
                elif eid in seen:
                    v.add("DUPLICATE_ID", f"{p}/evidence_id", "Duplicate evidence_id", phase="uniqueness")
                else:
                    seen.add(eid)
            if "command_id" in ev and ev["command_id"] is not None:
                if not isinstance(ev["command_id"], str) or ev["command_id"].strip() == "":
                    v.add("INVALID_VALUE", f"{p}/command_id", "command_id must be a non-empty string or null", phase="value")
            if "artifact_path" in ev and ev["artifact_path"] is not None:
                _check_repo_relative_path(v, ev["artifact_path"], f"{p}/artifact_path")
            if "artifact_sha256" in ev and ev["artifact_sha256"] is not None:
                _check_sha256(v, ev["artifact_sha256"], f"{p}/artifact_sha256")
            for key in ev:
                if key not in {"evidence_id", "command_id", "artifact_path", "artifact_sha256"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    remaining = preserved.get("remaining_criterion_ids")
    if not isinstance(remaining, list) or len(remaining) == 0:
        v.add("INVALID_VALUE", f"{path}/remaining_criterion_ids", "Must be a non-empty array", phase="value")
    else:
        for i, cid in enumerate(remaining):
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"{path}/remaining_criterion_ids/{i}", "Criterion ID must be a non-empty string", phase="value")

    journal_range = preserved.get("journal_range")
    if not isinstance(journal_range, dict):
        v.add("INVALID_TYPE", f"{path}/journal_range", "Expected object", phase="scalar")
    else:
        for key in ("first_seq", "last_seq", "first_event_sha256", "last_event_sha256"):
            if key not in journal_range:
                v.add("MISSING_FIELD", f"{path}/journal_range/{key}", f"Missing required field '{key}'")
            elif key.endswith("_seq"):
                val = journal_range[key]
                if isinstance(val, bool) or not isinstance(val, int):
                    v.add("INVALID_TYPE", f"{path}/journal_range/{key}", "Expected integer", phase="scalar")
                elif val < 1:
                    v.add("INVALID_VALUE", f"{path}/journal_range/{key}", "Must be a positive integer", phase="value")
            else:
                _check_sha256(v, journal_range[key], f"{path}/journal_range/{key}")
        for key in journal_range:
            if key not in {"first_seq", "last_seq", "first_event_sha256", "last_event_sha256"}:
                v.add("UNKNOWN_FIELD", f"{path}/journal_range/{key}", f"Unknown field '{key}'")


def _validate_digest_pointer(
    v: _PacketValidator,
    pointer: Any,
    path: str,
    required: set,
) -> None:
    if not isinstance(pointer, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    for key in pointer:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in pointer:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if "sha256" in pointer and pointer["sha256"] is not None:
        _check_sha256(v, pointer["sha256"], f"{path}/sha256")
    if "path" in pointer and pointer["path"] is not None:
        _check_repo_relative_path(v, pointer["path"], f"{path}/path")
    for key in ("result_id", "evidence_id"):
        if key in pointer and pointer[key] is not None:
            val = pointer[key]
            if not isinstance(val, str) or val.strip() == "":
                v.add("INVALID_VALUE", f"{path}/{key}", f"{key} must be a non-empty string", phase="value")


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
        return False
    return True


def _check_repo_relative_path(v: _PacketValidator, value: Any, path: str) -> Optional[str]:
    if not isinstance(value, str) or value.strip() == "":
        v.add("INVALID_VALUE", path, "Path must be a non-empty string", phase="value")
        return None
    if not is_repo_relative_path(value):
        v.add("PATH_NOT_RELATIVE", path, "Path must be relative to the repo root", phase="path_authority")
        return None
    normalized = _normalize_relative_path(value)
    if normalized is None:
        v.add("PATH_ESCAPE", path, "Path escapes the repository root", phase="path_authority")
        return None
    return normalized
