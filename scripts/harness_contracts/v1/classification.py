"""Attempt classification for harness contract v1 O3."""

from typing import Any, Dict, List, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import (
    LANES,
    RE_SHA256,
    _matches,
    _normalize_relative_path,
    _PacketValidator,
    is_repo_relative_path,
)
from harness_contracts.v1.worker_result import FALLBACK_REASONS, RE_RFC3339, WORKER_OUTCOMES


ATTEMPT_CLASSES = {
    "COMPLETED_PENDING_REVIEW",
    "INFRA_RETRYABLE",
    "WORKER_QUALITY",
    "CONTRACT_INVALID",
    "PROVIDER_EXHAUSTED",
    "AUTHORITY_VIOLATION",
    "HUMAN_DECISION",
}

RETRYABLE_CLASSES = {"INFRA_RETRYABLE"}
FALLBACK_ELIGIBLE_CLASSES = {"PROVIDER_EXHAUSTED"}

CLASS_ACTIONS: Dict[str, Dict[str, Any]] = {
    "COMPLETED_PENDING_REVIEW": {
        "auto_retry": False,
        "fallback": False,
        "edge": ("RUNNING", "REVIEW"),
        "cause": "result_recorded",
    },
    "WORKER_QUALITY": {
        "auto_retry": False,
        "fallback": False,
        "edge": ("RUNNING", "REVIEW"),
        "cause": "result_recorded",
    },
    "INFRA_RETRYABLE": {
        "auto_retry": True,
        "fallback": False,
        "edge": ("RUNNING", "READY"),
        "cause": "infra_retry",
    },
    "CONTRACT_INVALID": {
        "auto_retry": False,
        "fallback": False,
        "edge": ("RUNNING", "QUARANTINED"),
        "cause": "contract_invalid",
    },
    "PROVIDER_EXHAUSTED": {
        "auto_retry": False,
        "fallback": True,
        "edge": None,
        "cause": None,
    },
    "AUTHORITY_VIOLATION": {
        "auto_retry": False,
        "fallback": False,
        "edge": ("RUNNING", "QUARANTINED"),
        "cause": "authority_violation",
    },
    "HUMAN_DECISION": {
        "auto_retry": False,
        "fallback": False,
        "edge": ("RUNNING", "HUMAN_REQUIRED"),
        "cause": "worker_human_required",
    },
}


def validate_attempt_outcome(value: Any) -> Dict[str, Any]:
    """Validate an attempt-outcome record."""
    import json

    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Attempt outcome root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_attempt_outcome_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_attempt_outcome_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "packet_sha256",
        "attempt",
        "coordinator_id",
        "run_id",
        "lane",
        "invocation",
        "stdout",
        "stderr",
        "raw_result",
        "result_validation",
        "authority",
        "provider_evidence_sha256",
        "outcome",
        "fallback",
        "outcome_sha256",
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

    for field in ("packet_id", "coordinator_id", "run_id"):
        if not _check_non_empty_string(v, value.get(field), f"/{field}"):
            pass

    if not _matches(value.get("packet_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/packet_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    attempt = value.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        v.add("INVALID_TYPE", "/attempt", "Expected integer", phase="scalar")
    elif attempt < 1:
        v.add("INVALID_VALUE", "/attempt", "attempt must be a positive integer", phase="value")

    v.check_enum(value.get("lane"), LANES, "/lane")

    _validate_invocation(v, value.get("invocation"), "/invocation")
    _validate_stream_capture(v, value.get("stdout"), "/stdout")
    _validate_stream_capture(v, value.get("stderr"), "/stderr")
    _validate_raw_result(v, value.get("raw_result"), "/raw_result")
    _validate_result_validation(v, value.get("result_validation"), "/result_validation")
    _validate_authority(v, value.get("authority"), "/authority")

    pes = value.get("provider_evidence_sha256")
    if pes is not None and not _matches(pes, RE_SHA256):
        v.add("INVALID_FORMAT", "/provider_evidence_sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    v.check_enum(value.get("outcome"), WORKER_OUTCOMES, "/outcome")

    fallback = value.get("fallback")
    if fallback is not None:
        _validate_fallback(v, fallback, "/fallback")

    declared = value.get("outcome_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"outcome_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/outcome_sha256", "outcome_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/outcome_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")


def _validate_invocation(v: _PacketValidator, invocation: Any, path: str) -> None:
    if not isinstance(invocation, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {"argv", "cwd", "started_at", "finished_at", "exit_code", "signal", "timed_out", "wall_clock_seconds"}
    for key in invocation:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in invocation:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    argv = invocation.get("argv")
    if not isinstance(argv, list) or len(argv) == 0:
        v.add("INVALID_VALUE", f"{path}/argv", "argv must be a non-empty array", phase="value")
    else:
        for i, arg in enumerate(argv):
            if not isinstance(arg, str):
                v.add("INVALID_TYPE", f"{path}/argv/{i}", "argv elements must be strings", phase="scalar")

    _check_repo_relative_path(v, invocation.get("cwd"), f"{path}/cwd")
    _check_rfc3339(v, invocation.get("started_at"), f"{path}/started_at")
    _check_rfc3339(v, invocation.get("finished_at"), f"{path}/finished_at")

    ec = invocation.get("exit_code")
    if ec is not None and (isinstance(ec, bool) or not isinstance(ec, int)):
        v.add("INVALID_TYPE", f"{path}/exit_code", "Expected integer or null", phase="scalar")

    sig = invocation.get("signal")
    if sig is not None and (isinstance(sig, bool) or not isinstance(sig, int)):
        v.add("INVALID_TYPE", f"{path}/signal", "Expected integer or null", phase="scalar")

    timed_out = invocation.get("timed_out")
    if not isinstance(timed_out, bool):
        v.add("INVALID_TYPE", f"{path}/timed_out", "Expected boolean", phase="scalar")

    wall = invocation.get("wall_clock_seconds")
    if isinstance(wall, bool) or not isinstance(wall, int):
        v.add("INVALID_TYPE", f"{path}/wall_clock_seconds", "Expected integer", phase="scalar")
    elif wall < 0:
        v.add("INVALID_VALUE", f"{path}/wall_clock_seconds", "Must be a non-negative integer", phase="value")


def _validate_stream_capture(v: _PacketValidator, capture: Any, path: str) -> None:
    if not isinstance(capture, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {"path", "sha256", "byte_length"}
    for key in capture:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in capture:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if "path" in capture:
        _check_repo_relative_path(v, capture["path"], f"{path}/path")
    if "sha256" in capture:
        _check_sha256(v, capture["sha256"], f"{path}/sha256")
    if "byte_length" in capture:
        _check_int(v, capture["byte_length"], f"{path}/byte_length", nonneg=True)


def _validate_raw_result(v: _PacketValidator, raw: Any, path: str) -> None:
    if not isinstance(raw, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {"path", "sha256", "byte_length"}
    for key in raw:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in raw:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if "path" in raw:
        p = raw["path"]
        if p is not None:
            _check_repo_relative_path(v, p, f"{path}/path")
    if "sha256" in raw:
        s = raw["sha256"]
        if s is not None and not _matches(s, RE_SHA256):
            v.add("INVALID_FORMAT", f"{path}/sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")
    if "byte_length" in raw:
        _check_int(v, raw["byte_length"], f"{path}/byte_length", nonneg=True)


def _validate_result_validation(v: _PacketValidator, rv: Any, path: str) -> None:
    if not isinstance(rv, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {"present", "valid", "error_codes", "error_count"}
    for key in rv:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in rv:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if "present" in rv and not isinstance(rv["present"], bool):
        v.add("INVALID_TYPE", f"{path}/present", "Expected boolean", phase="scalar")
    if "valid" in rv and not isinstance(rv["valid"], bool):
        v.add("INVALID_TYPE", f"{path}/valid", "Expected boolean", phase="scalar")
    if "error_count" in rv:
        _check_int(v, rv["error_count"], f"{path}/error_count", nonneg=True)
    if "error_codes" in rv:
        codes = rv["error_codes"]
        if not isinstance(codes, list):
            v.add("INVALID_TYPE", f"{path}/error_codes", "Expected array", phase="scalar")
        else:
            for i, code in enumerate(codes):
                if not isinstance(code, str) or code.strip() == "":
                    v.add("INVALID_VALUE", f"{path}/error_codes/{i}", "Error code must be a non-empty string", phase="value")


def _validate_authority(v: _PacketValidator, authority: Any, path: str) -> None:
    if not isinstance(authority, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {"guard_denials", "undeclared_changed_paths", "governed_path_touches", "hard_stop_matches"}
    for key in authority:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in authority:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    guard_denials = authority.get("guard_denials")
    if not isinstance(guard_denials, list):
        v.add("INVALID_TYPE", f"{path}/guard_denials", "Expected array", phase="scalar")
    else:
        for i, gd in enumerate(guard_denials):
            p = f"{path}/guard_denials/{i}"
            if not isinstance(gd, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("tool", "target_path", "rule_id"):
                if key not in gd:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
                elif key == "target_path":
                    tp = gd[key]
                    if tp is not None:
                        _check_repo_relative_path(v, tp, f"{p}/{key}")
                else:
                    _check_non_empty_string(v, gd[key], f"{p}/{key}")
            for key in gd:
                if key not in {"tool", "target_path", "rule_id"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    for key in ("undeclared_changed_paths", "governed_path_touches", "hard_stop_matches"):
        arr = authority.get(key)
        if not isinstance(arr, list):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected array", phase="scalar")
        else:
            for i, pth in enumerate(arr):
                _check_repo_relative_path(v, pth, f"{path}/{key}/{i}")


def _validate_fallback(v: _PacketValidator, fallback: Any, path: str) -> None:
    if not isinstance(fallback, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    for key in ("reason", "provider_evidence_id", "reassign_to"):
        if key not in fallback:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in fallback:
        if key not in {"reason", "provider_evidence_id", "reassign_to"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    if "reason" in fallback:
        v.check_enum(fallback["reason"], FALLBACK_REASONS, f"{path}/reason")
    if "provider_evidence_id" in fallback:
        _check_non_empty_string(v, fallback["provider_evidence_id"], f"{path}/provider_evidence_id")
    if "reassign_to" in fallback and fallback["reassign_to"] != "sonnet_implementation":
        v.add("INVALID_VALUE", f"{path}/reassign_to", "reassign_to must be 'sonnet_implementation'", phase="value")


def classify_attempt(
    outcome_record: Dict[str, Any],
    packet: Dict[str, Any],
    provider_evidence: Optional[Dict[str, Any]],
    signal_registry: Optional[Dict[str, Any]],
    stdout_bytes: Optional[bytes] = None,
    stderr_bytes: Optional[bytes] = None,
    worker_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify an attempt outcome into one of ATTEMPT_CLASSES.

    ``packet`` is the original packet object.  ``provider_evidence`` and
    ``signal_registry`` are required when evaluating provider-exhaustion
    claims.  ``stdout_bytes``/``stderr_bytes`` are required for Guard 1's
    verbatim excerpt verification.  ``worker_result`` is required for Guard 3's
    chronology check and supplies the fallback binding when present.
    """
    from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion

    result_validation = outcome_record.get("result_validation") or {}
    authority = outcome_record.get("authority") or {}
    outcome = outcome_record.get("outcome")
    raw_result = outcome_record.get("raw_result") or {}
    invocation = outcome_record.get("invocation") or {}
    fallback = (worker_result or outcome_record).get("fallback")

    # 1. AUTHORITY_VIOLATION
    if (
        authority.get("guard_denials")
        or authority.get("undeclared_changed_paths")
        or authority.get("governed_path_touches")
        or authority.get("hard_stop_matches")
    ):
        cause = "authority_hard_stop" if (authority.get("hard_stop_matches") or authority.get("governed_path_touches")) else "authority_violation"
        return _classification("AUTHORITY_VIOLATION", matched_rule="authority_violation", cause=cause)

    # 2. HUMAN_DECISION
    if result_validation.get("valid") is True and outcome == "HUMAN_REQUIRED":
        return _classification("HUMAN_DECISION", matched_rule="human_decision", cause="worker_human_required")

    # 3. PROVIDER_EXHAUSTED
    if result_validation.get("valid") is True and outcome == "CHECKPOINTED":
        confirmation = confirm_provider_exhaustion(
            worker_result if worker_result is not None else outcome_record,
            provider_evidence,
            signal_registry,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            outcome_record=outcome_record,
        )
        if confirmation.get("classification") in {
            "CONFIRMED_QUOTA_EXHAUSTION",
            "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        } and not confirmation.get("errors"):
            return _classification("PROVIDER_EXHAUSTED", matched_rule="provider_exhausted", cause="provider_exhausted_reassignment")

    # 4. CONTRACT_INVALID
    if raw_result.get("byte_length", 0) > 0 and result_validation.get("valid") is False:
        return _classification("CONTRACT_INVALID", matched_rule="contract_invalid", cause="contract_invalid")

    # 5. INFRA_RETRYABLE
    if (
        (raw_result.get("path") is None or raw_result.get("byte_length", 0) == 0)
        and (invocation.get("timed_out") is True or invocation.get("signal") is not None or invocation.get("exit_code") not in (0, None))
    ):
        return _classification("INFRA_RETRYABLE", matched_rule="infra_retryable", cause="infra_retry")

    # 6. WORKER_QUALITY
    if result_validation.get("valid") is True and outcome == "FAILED":
        return _classification("WORKER_QUALITY", matched_rule="worker_quality", cause="result_recorded")

    # 7. COMPLETED_PENDING_REVIEW
    if result_validation.get("valid") is True and outcome == "COMPLETED":
        return _classification("COMPLETED_PENDING_REVIEW", matched_rule="completed_pending_review", cause="result_recorded")

    # Catch-all
    return _classification("CONTRACT_INVALID", matched_rule="catch_all", cause="contract_invalid", error_codes=["EVIDENCE_MISSING"])


def _classification(
    attempt_class: str,
    matched_rule: str,
    cause: str,
    error_codes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "attempt_class": attempt_class,
        "matched_rule": matched_rule,
        "cause": cause,
        "error_codes": error_codes or [],
    }


def _check_non_empty_string(v: _PacketValidator, value: Any, path: str) -> bool:
    if not isinstance(value, str):
        v.add("INVALID_TYPE", path, "Expected string", phase="scalar")
        return False
    if value.strip() == "":
        v.add("INVALID_VALUE", path, "Empty or whitespace-only string", phase="value")
        return False
    return True


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
        return False
    return True


def _check_rfc3339(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_RFC3339):
        v.add("INVALID_FORMAT", path, "Must be RFC3339 UTC timestamp ending in Z", phase="format")
        return False
    return True


def _check_int(v: _PacketValidator, value: Any, path: str, min_value: Optional[int] = None, positive: bool = False, nonneg: bool = False) -> bool:
    if isinstance(value, bool):
        v.add("INVALID_TYPE", path, "Expected integer, not boolean", phase="scalar")
        return False
    if not isinstance(value, int):
        v.add("INVALID_TYPE", path, "Expected integer", phase="scalar")
        return False
    if positive and value <= 0:
        v.add("INVALID_VALUE", path, "Must be a positive integer", phase="value")
        return False
    if nonneg and value < 0:
        v.add("INVALID_VALUE", path, "Must be a non-negative integer", phase="value")
        return False
    if min_value is not None and value < min_value:
        v.add("INVALID_VALUE", path, f"Must be >= {min_value}", phase="value")
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
