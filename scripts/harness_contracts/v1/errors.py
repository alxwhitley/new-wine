"""Validation result and error-code helpers for contract v1."""

from typing import Any, Dict, List


ERROR_CODES = [
    "INVALID_JSON",
    "ROOT_NOT_OBJECT",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "INVALID_TYPE",
    "INVALID_ENUM",
    "INVALID_FORMAT",
    "INVALID_VALUE",
    "DUPLICATE_ID",
    "DUPLICATE_PATH",
    "PATH_NOT_RELATIVE",
    "PATH_ESCAPE",
    "PATH_OVERLAP",
    "GOVERNED_PATH",
    "FORBIDDEN_AUTHORITY",
    "SELF_DEPENDENCY",
    "UNKNOWN_DEPENDENCY",
    "DEPENDENCY_NOT_ACCEPTED",
    "REVISION_MISMATCH",
    "BUDGET_EXCEEDED",
    "COMMAND_MISMATCH",
    "COMMAND_NOT_RUN",
    "COMMAND_FAILED",
    "EVIDENCE_MISSING",
    "EVIDENCE_HASH_MISMATCH",
    "ACCEPTANCE_UNSATISFIED",
    "CHANGED_FILE_UNDECLARED",
    "CHECKPOINT_INCOMPLETE",
    "INVALID_TRANSITION",
    "INVALID_FALLBACK",
    "WORKER_SELF_ACCEPT",
    "VERDICT_CONFLICT",
    "TRUST_CONTEXT_MISSING",
    "UNAUTHORIZED_REVIEWER",
    "PROVENANCE_MISMATCH",
    "CHRONOLOGY_VIOLATION",
]

_ERROR_CODE_ORDER = {code: i for i, code in enumerate(ERROR_CODES)}


# Phase ranks for deterministic error ordering. Lower ranks are reported first.
# Validation stops after phase 1 (JSON decode / root-type) errors, so these
# ranks are only meaningful once structural collection begins.
PHASE_RANK = {
    "json_decode": 0,
    "root_type": 0,
    "unknown_missing": 1,
    "scalar": 2,
    "enum": 2,
    "format": 2,
    "value": 2,
    "uniqueness": 3,
    "path_authority": 4,
    "cross_field": 5,
    "cross_object": 6,
    "transition": 7,
    "evidence_accept": 8,
}


def error(
    code: str,
    path: str,
    message: str,
    phase: str = "unknown_missing",
) -> Dict[str, Any]:
    if code not in _ERROR_CODE_ORDER:
        raise ValueError(f"Unknown error code: {code}")
    return {
        "code": code,
        "path": path,
        "message": message,
        "_phase": PHASE_RANK.get(phase, 99),
    }


def _strip_internal(err: Dict[str, Any]) -> Dict[str, str]:
    return {"code": err["code"], "path": err["path"], "message": err["message"]}


def invalid_result(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    sorted_errors = sort_errors(errors)
    return {"valid": False, "errors": [_strip_internal(e) for e in sorted_errors]}


def valid_result() -> Dict[str, Any]:
    return {"valid": True, "errors": []}


def sort_errors(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort errors by phase rank, JSON Pointer path, error-code enum order, then message."""
    return sorted(
        errors,
        key=lambda e: (
            e.get("_phase", 99),
            e["path"],
            _ERROR_CODE_ORDER[e["code"]],
            e["message"],
        ),
    )
