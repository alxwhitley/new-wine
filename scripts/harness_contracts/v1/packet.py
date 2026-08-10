"""Packet schema validation for harness contract v1."""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result


LANES = {
    "kimi_implementation",
    "sonnet_implementation",
    "grok_verification",
    "opus_judgment",
}

PACKET_STATES = {
    "BLOCKED",
    "READY",
    "RUNNING",
    "REVIEW",
    "REVISE",
    "ACCEPTED",
    "QUARANTINED",
    "HUMAN_REQUIRED",
}

WORKER_OUTCOMES = {"COMPLETED", "FAILED", "CHECKPOINTED", "HUMAN_REQUIRED"}

COMMAND_OUTCOMES = {"PASSED", "FAILED", "TIMED_OUT", "NOT_RUN"}

EVIDENCE_KINDS = {
    "premise",
    "acceptance",
    "verification",
    "changed_files",
    "checkpoint",
    "reconciliation",
    "quota_exhaustion",
}

VERDICTS = {"ACCEPT", "REVISE", "QUARANTINE", "HUMAN_REQUIRED"}

COST_CLASSES = {"none", "low", "medium", "high"}

NETWORK_POLICIES = {"denied", "allowed"}

FALLBACK_REASONS = {
    "confirmed_quota_exhaustion",
    "confirmed_rate_limit_exhaustion",
}

GOVERNED_PATHS = {
    "CLAUDE.md",
    "PLAN.md",
    "POSITIONING.md",
    "DESIGN.md",
    "rhemata-status.md",
}

RE_SHA256 = r"^[0-9a-f]{64}$"
RE_REVISION = r"^[0-9a-f]{40}$"
RE_HARNESS_ID = r"^[a-z0-9][a-z0-9._-]{0,127}$"
HARNESS_ID_PATTERN = re.compile(RE_HARNESS_ID)


def is_harness_id(value: Any) -> bool:
    """Return whether value is safe for identity and filesystem use."""
    return isinstance(value, str) and HARNESS_ID_PATTERN.fullmatch(value) is not None


def is_repo_relative_path(path: str) -> bool:
    """Return True if ``path`` is repo-relative before normalization.

    Rejects POSIX absolute paths (``/...``), drive-qualified Windows paths
    (``C:\\...``, ``C:/...``, ``C:...``), and UNC paths (``\\\\server\\share``,
    ``//server/share``) before any ``..`` normalization happens.
    """
    if path.startswith("/"):
        return False
    if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
        return False
    if path.startswith("\\") or path.startswith("//"):
        return False
    return True


class _PacketValidator:
    """Stateful validator collecting errors for one packet value."""

    def __init__(self, value: Any) -> None:
        self.errors: List[Dict[str, str]] = []
        self.value: Dict[str, Any] = value if isinstance(value, dict) else {}

    def add(self, code: str, path: str, message: str, phase: str = "unknown_missing") -> None:
        self.errors.append(error(code, path, message, phase=phase))

    def require(self, key: str, expected_type: str, path: str = "") -> Any:
        if key not in self.value:
            self.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
            return None
        return self.value[key]

    def check_type(self, value: Any, expected: str, path: str) -> bool:
        type_map = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "number": (int, float),
        }
        if expected not in type_map:
            return True
        ok = isinstance(value, type_map[expected])
        if not ok:
            self.add("INVALID_TYPE", path, f"Expected {expected}, got {type(value).__name__}")
        return ok

    def check_enum(self, value: Any, allowed: Set[str], path: str) -> bool:
        if value not in allowed:
            self.add("INVALID_ENUM", path, f"Value must be one of {sorted(allowed)}")
            return False
        return True

    def check_non_empty_string(self, value: Any, path: str) -> bool:
        if not isinstance(value, str):
            self.add("INVALID_TYPE", path, "Expected string")
            return False
        if value.strip() == "":
            self.add("INVALID_VALUE", path, "Empty or whitespace-only string")
            return False
        return True


def validate_packet(value: Any, dependency_states: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Validate a packet object against the v1 contract.

    ``dependency_states`` is an optional mapping of packet_id -> state. When
    provided, every dependency must be known and ``ACCEPTED``.

    Returns ``{"valid": bool, "errors": [...]}``.
    """
    if value is None:
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Packet root is not an object")])

    if isinstance(value, (str, bytes, bytearray)):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}")])
        value = parsed

    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Packet root is not an object")])

    validator = _PacketValidator(value)
    validator.dependency_states = dependency_states
    _validate_packet_object(validator)
    if not validator.errors:
        return valid_result()
    return invalid_result(sort_errors(validator.errors))


def _validate_packet_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet_id",
        "objective",
        "dependency_ids",
        "lane",
        "assigned_worker",
        "starting_revision",
        "worktree",
        "writable_paths",
        "forbidden_surfaces",
        "required_context",
        "premise_checks",
        "acceptance_criteria",
        "verification_commands",
        "budgets",
        "network_policy",
        "checkpoint_artifacts",
        "rollback",
        "human_stop_conditions",
        "sonnet_reassignment_allowed",
        "created_by",
        "packet_sha256",
    }

    value = v.value

    # Phase: unknown / missing (collected together).
    for key in value:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"/{key}", f"Unknown field '{key}'")

    for key in allowed:
        if key not in value:
            v.add("MISSING_FIELD", f"/{key}", f"Missing required field '{key}'")

    if v.errors:
        return

    # Schema version
    if value.get("schema_version") != 1:
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1")

    # Strings
    v.check_non_empty_string(value["objective"], "/objective")
    if not is_harness_id(value["packet_id"]):
        v.add(
            "INVALID_FORMAT",
            "/packet_id",
            "Must match ^[a-z0-9][a-z0-9._-]{0,127}$",
            phase="format",
        )

    # dependency_ids: array of non-empty strings, may be empty
    deps = value["dependency_ids"]
    packet_id = value.get("packet_id")
    if not isinstance(deps, list):
        v.add("INVALID_TYPE", "/dependency_ids", "Expected array")
    else:
        for i, dep in enumerate(deps):
            if not is_harness_id(dep):
                v.add(
                    "INVALID_FORMAT",
                    f"/dependency_ids/{i}",
                    "Must match ^[a-z0-9][a-z0-9._-]{0,127}$",
                    phase="format",
                )
            elif isinstance(packet_id, str) and dep == packet_id:
                v.add("SELF_DEPENDENCY", f"/dependency_ids/{i}", "Packet cannot depend on itself")

    # Cross-object dependency state checks (only when context is supplied).
    if v.dependency_states is not None and isinstance(deps, list):
        for i, dep in enumerate(deps):
            if not isinstance(dep, str) or dep.strip() == "":
                continue
            if dep == packet_id:
                continue
            if dep not in v.dependency_states:
                v.add("UNKNOWN_DEPENDENCY", f"/dependency_ids/{i}", f"Dependency '{dep}' state is unknown")
            elif v.dependency_states.get(dep) != "ACCEPTED":
                v.add("DEPENDENCY_NOT_ACCEPTED", f"/dependency_ids/{i}", f"Dependency '{dep}' is not ACCEPTED")

    # lane
    v.check_enum(value["lane"], LANES, "/lane")
    # Implementation packets may not be assigned to the judgment lane.
    if value.get("lane") == "opus_judgment":
        v.add("FORBIDDEN_AUTHORITY", "/lane", "Implementation packet cannot use opus_judgment lane")

    # assigned_worker
    _validate_assigned_worker(v, value["assigned_worker"], "/assigned_worker")

    # starting_revision
    if not _matches(value["starting_revision"], RE_REVISION):
        v.add("INVALID_FORMAT", "/starting_revision", "Must be 40-character lowercase SHA-1 hex")

    # worktree
    _validate_worktree(v, value["worktree"], "/worktree")

    # writable_paths: non-empty array
    _validate_path_array(v, value["writable_paths"], "/writable_paths", nonempty=True)

    # forbidden_surfaces: array (may be empty)
    _validate_path_array(v, value["forbidden_surfaces"], "/forbidden_surfaces", nonempty=False)

    # required_context
    _validate_required_context(v, value["required_context"], "/required_context")

    # premise_checks
    _validate_premise_checks(v, value["premise_checks"], "/premise_checks")

    # acceptance_criteria
    _validate_acceptance_criteria(v, value["acceptance_criteria"], "/acceptance_criteria")

    # verification_commands
    _validate_verification_commands(v, value["verification_commands"], "/verification_commands")

    # budgets
    _validate_budgets(v, value["budgets"], "/budgets")

    # network_policy
    v.check_enum(value["network_policy"], NETWORK_POLICIES, "/network_policy")

    # checkpoint_artifacts
    _validate_checkpoint_artifacts(v, value["checkpoint_artifacts"], "/checkpoint_artifacts")

    # rollback
    _validate_rollback(v, value["rollback"], "/rollback")

    # human_stop_conditions
    hsc = value["human_stop_conditions"]
    if not isinstance(hsc, list):
        v.add("INVALID_TYPE", "/human_stop_conditions", "Expected array")
    else:
        for i, cond in enumerate(hsc):
            if not isinstance(cond, str) or cond.strip() == "":
                v.add("INVALID_VALUE", f"/human_stop_conditions/{i}", "Stop condition must be a non-empty string")

    # sonnet_reassignment_allowed
    if not isinstance(value["sonnet_reassignment_allowed"], bool):
        v.add("INVALID_TYPE", "/sonnet_reassignment_allowed", "Expected boolean")

    # created_by
    _validate_created_by(v, value["created_by"], "/created_by")

    # packet_sha256
    if not _matches(value["packet_sha256"], RE_SHA256):
        v.add("INVALID_FORMAT", "/packet_sha256", "Must be 64-character lowercase SHA-256 hex")

    # Cross-field checks (only when base fields are present and well-typed).
    _cross_field_checks(v)


def _validate_assigned_worker(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("worker_id", "provider", "model"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        else:
            v.check_non_empty_string(value[key], f"{path}/{key}")
    for key in value:
        if key not in {"worker_id", "provider", "model"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")


def _validate_worktree(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("path", "branch"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        elif key == "path":
            if not isinstance(value[key], str) or value[key].strip() == "":
                v.add("INVALID_VALUE", f"{path}/{key}", "Worktree path must be a non-empty string")
            elif not value[key].startswith("/"):
                v.add("INVALID_VALUE", f"{path}/{key}", "Worktree path must be absolute")
        else:
            v.check_non_empty_string(value[key], f"{path}/{key}")
    for key in value:
        if key not in {"path", "branch"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")


def _validate_path_array(v: _PacketValidator, value: Any, path: str, nonempty: bool) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if nonempty and len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one path")
    seen: Set[str] = set()
    normalized_paths: List[str] = []
    for i, p in enumerate(value):
        ppath = f"{path}/{i}"
        if not isinstance(p, str) or p.strip() == "":
            v.add("INVALID_VALUE", ppath, "Path must be a non-empty string")
            continue
        if not is_repo_relative_path(p):
            v.add("PATH_NOT_RELATIVE", ppath, "Path must be relative to the repo root")
            continue
        normalized = _normalize_relative_path(p)
        if normalized is None:
            v.add("PATH_ESCAPE", ppath, "Path escapes the repository root")
            continue
        if normalized in seen:
            v.add("DUPLICATE_PATH", ppath, "Duplicate path in list")
        seen.add(normalized)
        normalized_paths.append(normalized)
        if normalized in GOVERNED_PATHS:
            v.add("GOVERNED_PATH", ppath, f"Path '{normalized}' is governed and cannot appear here")

    # Detect ancestor/descendant overlap (including equality, already caught above).
    for i, a in enumerate(normalized_paths):
        for j, b in enumerate(normalized_paths):
            if i >= j:
                continue
            if _path_overlaps(a, b):
                v.add("PATH_OVERLAP", path, f"Paths '{a}' and '{b}' overlap")


def _validate_repo_relative_path(v: _PacketValidator, value: Any, path: str) -> Optional[str]:
    """Validate a repo-relative path: non-empty, not absolute, no escape.

    Returns the normalized path on success, or None and records errors.
    """
    if not isinstance(value, str) or value.strip() == "":
        v.add("INVALID_VALUE", path, "Path must be a non-empty string")
        return None
    if not is_repo_relative_path(value):
        v.add("PATH_NOT_RELATIVE", path, "Path must be relative to the repo root")
        return None
    normalized = _normalize_relative_path(value)
    if normalized is None:
        v.add("PATH_ESCAPE", path, "Path escapes the repository root")
        return None
    return normalized


def _validate_required_context(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one context entry")
    seen: Set[str] = set()
    for i, ctx in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(ctx, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("path", "sha256"):
            if key not in ctx:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in ctx:
            if key not in {"path", "sha256"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "path" in ctx:
            normalized = _validate_repo_relative_path(v, ctx["path"], f"{p}/path")
            if normalized is not None:
                if normalized in seen:
                    v.add("DUPLICATE_PATH", f"{p}/path", "Duplicate context path")
                else:
                    seen.add(normalized)
        if "sha256" in ctx and not _matches(ctx["sha256"], RE_SHA256):
            v.add("INVALID_FORMAT", f"{p}/sha256", "Must be 64-character lowercase SHA-256 hex")


def _validate_premise_checks(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one premise check")
    seen: Set[str] = set()
    for i, check in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(check, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("check_id", "command_id", "expected"):
            if key not in check:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
            else:
                v.check_non_empty_string(check[key], f"{p}/{key}")
        for key in check:
            if key not in {"check_id", "command_id", "expected"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if check.get("check_id") in seen:
            v.add("DUPLICATE_ID", f"{p}/check_id", "Duplicate check_id")
        seen.add(check.get("check_id"))


def _validate_acceptance_criteria(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one acceptance criterion")
    seen: Set[str] = set()
    for i, crit in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(crit, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("criterion_id", "statement", "required_evidence_ids"):
            if key not in crit:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in crit:
            if key not in {"criterion_id", "statement", "required_evidence_ids"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "criterion_id" in crit:
            cid = crit["criterion_id"]
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/criterion_id", "Criterion ID must be a non-empty string")
            elif cid in seen:
                v.add("DUPLICATE_ID", f"{p}/criterion_id", "Duplicate criterion_id")
            else:
                seen.add(cid)
        if "statement" in crit:
            v.check_non_empty_string(crit["statement"], f"{p}/statement")
        if "required_evidence_ids" in crit:
            ids = crit["required_evidence_ids"]
            if not isinstance(ids, list) or len(ids) == 0:
                v.add("INVALID_VALUE", f"{p}/required_evidence_ids", "Must be a non-empty array")
            else:
                for j, eid in enumerate(ids):
                    if not isinstance(eid, str) or eid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/required_evidence_ids/{j}", "Evidence ID must be a non-empty string")


def _validate_verification_commands(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one verification command")
    seen: Set[str] = set()
    for i, cmd in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(cmd, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        required = {"command_id", "argv", "cwd", "timeout_seconds", "expected_exit_code", "expected_evidence_ids"}
        for key in required:
            if key not in cmd:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in cmd:
            if key not in required:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "command_id" in cmd:
            cid = cmd["command_id"]
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/command_id", "Command ID must be a non-empty string")
            elif cid in seen:
                v.add("DUPLICATE_ID", f"{p}/command_id", "Duplicate command_id")
            else:
                seen.add(cid)
        if "argv" in cmd:
            argv = cmd["argv"]
            if not isinstance(argv, list) or len(argv) == 0:
                v.add("INVALID_VALUE", f"{p}/argv", "argv must be a non-empty array")
            else:
                for j, arg in enumerate(argv):
                    if not isinstance(arg, str):
                        v.add("INVALID_TYPE", f"{p}/argv/{j}", "argv elements must be strings")
        if "cwd" in cmd:
            _validate_repo_relative_path(v, cmd["cwd"], f"{p}/cwd")
        if "timeout_seconds" in cmd:
            ts = cmd["timeout_seconds"]
            if isinstance(ts, bool) or not isinstance(ts, int):
                v.add("INVALID_TYPE", f"{p}/timeout_seconds", "Expected integer", phase="scalar")
            elif ts <= 0:
                v.add("INVALID_VALUE", f"{p}/timeout_seconds", "Must be a positive integer", phase="value")
        if "expected_exit_code" in cmd:
            ec = cmd["expected_exit_code"]
            if isinstance(ec, bool) or not isinstance(ec, int):
                v.add("INVALID_TYPE", f"{p}/expected_exit_code", "Expected integer", phase="scalar")
        if "expected_evidence_ids" in cmd:
            ids = cmd["expected_evidence_ids"]
            if not isinstance(ids, list):
                v.add("INVALID_TYPE", f"{p}/expected_evidence_ids", "Expected array")
            else:
                for j, eid in enumerate(ids):
                    if not isinstance(eid, str) or eid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/expected_evidence_ids/{j}", "Evidence ID must be a non-empty string")


def _validate_budgets(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    required = {"max_turns", "wall_clock_seconds", "retry_limit", "max_output_bytes", "cost_class", "allowance_limit"}
    for key in required:
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    positive_int_fields = {"max_turns", "wall_clock_seconds", "retry_limit", "max_output_bytes", "allowance_limit"}
    for key in positive_int_fields:
        if key not in value:
            continue
        val = value[key]
        if isinstance(val, bool):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected integer, not boolean", phase="scalar")
        elif not isinstance(val, int):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected integer", phase="scalar")
        elif val <= 0:
            v.add("INVALID_VALUE", f"{path}/{key}", "Must be a positive integer", phase="value")
    if "cost_class" in value:
        v.check_enum(value["cost_class"], COST_CLASSES, f"{path}/cost_class")


def _validate_checkpoint_artifacts(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one checkpoint artifact")
    seen: Set[str] = set()
    for i, art in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(art, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("artifact_id", "path", "required_for_fallback"):
            if key not in art:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in art:
            if key not in {"artifact_id", "path", "required_for_fallback"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "artifact_id" in art:
            aid = art["artifact_id"]
            if not isinstance(aid, str) or aid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/artifact_id", "Artifact ID must be a non-empty string")
            elif aid in seen:
                v.add("DUPLICATE_ID", f"{p}/artifact_id", "Duplicate artifact_id")
            else:
                seen.add(aid)
        if "path" in art:
            _validate_repo_relative_path(v, art["path"], f"{p}/path")
        if "required_for_fallback" in art and not isinstance(art["required_for_fallback"], bool):
            v.add("INVALID_TYPE", f"{p}/required_for_fallback", "Expected boolean")


def _validate_rollback(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("method", "allowed_commands"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in {"method", "allowed_commands"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    if "method" in value:
        v.check_non_empty_string(value["method"], f"{path}/method")
    if "allowed_commands" in value:
        cmds = value["allowed_commands"]
        if not isinstance(cmds, list) or len(cmds) == 0:
            v.add("INVALID_VALUE", f"{path}/allowed_commands", "Must be a non-empty array")
        else:
            for i, cmd in enumerate(cmds):
                cp = f"{path}/allowed_commands/{i}"
                if not isinstance(cmd, dict):
                    v.add("INVALID_TYPE", cp, "Expected object")
                    continue
                for key in ("argv", "cwd"):
                    if key not in cmd:
                        v.add("MISSING_FIELD", f"{cp}/{key}", f"Missing required field '{key}'")
                for key in cmd:
                    if key not in {"argv", "cwd"}:
                        v.add("UNKNOWN_FIELD", f"{cp}/{key}", f"Unknown field '{key}'")
                if "argv" in cmd:
                    argv = cmd["argv"]
                    if not isinstance(argv, list) or len(argv) == 0:
                        v.add("INVALID_VALUE", f"{cp}/argv", "argv must be a non-empty array")
                    else:
                        for j, arg in enumerate(argv):
                            if not isinstance(arg, str):
                                v.add("INVALID_TYPE", f"{cp}/argv/{j}", "argv elements must be strings")
                if "cwd" in cmd:
                    _validate_repo_relative_path(v, cmd["cwd"], f"{cp}/cwd")


def _validate_created_by(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("role", "session_id", "model"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in {"role", "session_id", "model"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    if "role" in value and value["role"] != "opus_judgment":
        v.add("INVALID_VALUE", f"{path}/role", "role must be 'opus_judgment'")
    for key in ("session_id", "model"):
        if key in value:
            v.check_non_empty_string(value[key], f"{path}/{key}")


def _cross_field_checks(v: _PacketValidator) -> None:
    value = v.value
    # Forbidden overlap: writable_paths must not intersect forbidden_surfaces,
    # including ancestor/descendant overlaps.
    writable_raw = [p for p in value.get("writable_paths", []) if isinstance(p, str)]
    forbidden_raw = [p for p in value.get("forbidden_surfaces", []) if isinstance(p, str)]
    writable = set()
    forbidden = set()
    for p in writable_raw:
        normalized = _normalize_relative_path(p)
        if normalized is not None:
            writable.add(normalized)
    for p in forbidden_raw:
        normalized = _normalize_relative_path(p)
        if normalized is not None:
            forbidden.add(normalized)
    for wp in writable:
        for fp in forbidden:
            if _path_overlaps(wp, fp):
                v.add(
                    "PATH_OVERLAP",
                    "/writable_paths",
                    f"Writable path '{wp}' overlaps forbidden surface '{fp}'",
                    phase="path_authority",
                )

    # Verify packet_sha256 is consistent with canonical bytes (self omitted).
    declared = value.get("packet_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"packet_sha256"}))
        if computed != declared:
            v.add(
                "EVIDENCE_HASH_MISMATCH",
                "/packet_sha256",
                "packet_sha256 does not match canonical self-hash",
                phase="cross_field",
            )


def _matches(value: Any, pattern: str) -> bool:
    import re
    return isinstance(value, str) and bool(re.match(pattern, value))


def _path_overlaps(a: str, b: str) -> bool:
    """Return True if one repo-relative path is an ancestor/descendant of the other."""
    a_parts = a.split("/") if a else []
    b_parts = b.split("/") if b else []
    min_len = min(len(a_parts), len(b_parts))
    return a_parts[:min_len] == b_parts[:min_len]


def _normalize_relative_path(path: str) -> Optional[str]:
    """Normalize a repo-relative path and reject escapes above root.

    Returns ``None`` if the path escapes the repository root.
    """
    import os.path
    parts = path.replace("\\", "/").split("/")
    stack: List[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                return None
            stack.pop()
        else:
            stack.append(part)
    if not stack:
        return ""
    return "/".join(stack)
