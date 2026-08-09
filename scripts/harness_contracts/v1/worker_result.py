"""Worker result schema validation for harness contract v1."""

import datetime
import json
import re
from typing import Any, Dict, List, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import (
    LANES,
    RE_REVISION,
    RE_SHA256,
    _matches,
    _normalize_relative_path,
    _PacketValidator,
    is_repo_relative_path,
)


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
CRITERION_STATUSES = {"SATISFIED", "UNSATISFIED", "NOT_EVALUATED"}
FILE_STATUSES = {"added", "modified", "deleted", "renamed"}
FALLBACK_REASONS = {
    "confirmed_quota_exhaustion",
    "confirmed_rate_limit_exhaustion",
}
RE_RFC3339 = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def validate_worker_result(value: Any) -> Dict[str, Any]:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Worker result root is not an object")])

    v = _PacketValidator(value)
    _validate_worker_result_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_worker_result_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "result_id",
        "packet_id",
        "packet_sha256",
        "attempt",
        "worker",
        "started_at",
        "finished_at",
        "starting_revision",
        "ending_revision",
        "outcome",
        "changed_files",
        "commands",
        "evidence",
        "criteria",
        "checkpoints",
        "remaining_criterion_ids",
        "fallback",
        "human_required_reasons",
        "budgets",
        "result_sha256",
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
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1")

    for field in ("result_id", "packet_id"):
        v.check_non_empty_string(value[field], f"/{field}")

    if not _matches(value.get("packet_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/packet_sha256", "Must be 64-character lowercase SHA-256 hex")

    attempt = value.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        v.add("INVALID_TYPE", "/attempt", "Expected integer", phase="scalar")
    elif attempt < 1:
        v.add("INVALID_VALUE", "/attempt", "attempt must be a positive integer", phase="value")

    _validate_worker(v, value.get("worker"), "/worker")

    for field in ("started_at", "finished_at"):
        if not _matches(value.get(field), RE_RFC3339):
            v.add("INVALID_FORMAT", f"/{field}", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

    for field in ("starting_revision", "ending_revision"):
        if not _matches(value.get(field), RE_REVISION):
            v.add("INVALID_FORMAT", f"/{field}", "Must be 40-character lowercase SHA-1 hex", phase="format")

    v.check_enum(value.get("outcome"), WORKER_OUTCOMES, "/outcome")

    _validate_budgets(v, value.get("budgets"), "/budgets")

    _validate_time_order(v, value.get("started_at"), value.get("finished_at"), "/finished_at")

    _validate_changed_files(v, value.get("changed_files", []), "/changed_files")
    _validate_commands(v, value.get("commands", []), "/commands")
    _validate_evidence(v, value.get("evidence", []), "/evidence")
    _validate_criteria(v, value.get("criteria", []), "/criteria")
    _validate_checkpoints(v, value.get("checkpoints", []), "/checkpoints")

    rem = value.get("remaining_criterion_ids", [])
    if not isinstance(rem, list):
        v.add("INVALID_TYPE", "/remaining_criterion_ids", "Expected array")
    else:
        for i, cid in enumerate(rem):
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"/remaining_criterion_ids/{i}", "Criterion ID must be a non-empty string")

    if value.get("fallback") is not None:
        _validate_fallback(v, value["fallback"], "/fallback")

    hrr = value.get("human_required_reasons", [])
    if not isinstance(hrr, list):
        v.add("INVALID_TYPE", "/human_required_reasons", "Expected array")
    else:
        for i, reason in enumerate(hrr):
            if not isinstance(reason, str) or reason.strip() == "":
                v.add("INVALID_VALUE", f"/human_required_reasons/{i}", "Reason must be a non-empty string")

    if not _matches(value.get("result_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/result_sha256", "Must be 64-character lowercase SHA-256 hex")

    _cross_field_checks_worker_result(v)


def _validate_worker(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("worker_id", "session_id", "lane", "provider", "model"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        else:
            if key == "lane":
                v.check_enum(value[key], LANES, f"{path}/{key}")
            else:
                v.check_non_empty_string(value[key], f"{path}/{key}")
    for key in value:
        if key not in {"worker_id", "session_id", "lane", "provider", "model"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    # A worker may not judge its own result.
    if isinstance(value, dict) and value.get("lane") == "opus_judgment":
        v.add("FORBIDDEN_AUTHORITY", f"{path}/lane", "Worker lane cannot be opus_judgment", phase="path_authority")


def _parse_rfc3339(value: str) -> Optional[datetime.datetime]:
    """Parse a strict RFC3339 UTC timestamp ending in ``Z``."""
    if not _matches(value, RE_RFC3339):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _validate_time_order(v: _PacketValidator, started: Any, finished: Any, path: str) -> None:
    started_dt = _parse_rfc3339(started) if isinstance(started, str) else None
    finished_dt = _parse_rfc3339(finished) if isinstance(finished, str) else None
    if started_dt is not None and finished_dt is not None and finished_dt < started_dt:
        v.add("INVALID_VALUE", path, "finished_at must not be before started_at", phase="value")


def _validate_budgets(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    required = {"turns_used", "output_bytes", "retry_count", "allowance_used"}
    for key in required:
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in ("turns_used", "output_bytes", "retry_count"):
        if key not in value:
            continue
        val = value[key]
        if isinstance(val, bool):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected integer, not boolean", phase="scalar")
        elif not isinstance(val, int):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected integer", phase="scalar")
        elif val < 0:
            v.add("INVALID_VALUE", f"{path}/{key}", "Must be a non-negative integer", phase="value")
    if "allowance_used" in value:
        val = value["allowance_used"]
        if not isinstance(val, str) or val.strip() == "":
            v.add("INVALID_VALUE", f"{path}/allowance_used", "Must be a non-empty string", phase="value")


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


def _validate_changed_files(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    seen: Set[str] = set()
    for i, cf in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(cf, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("path", "status"):
            if key not in cf:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in cf:
            if key not in {"path", "status", "before_sha256", "after_sha256"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "path" in cf:
            normalized = _validate_repo_relative_path(v, cf["path"], f"{p}/path")
            if normalized is not None:
                if normalized in seen:
                    v.add("DUPLICATE_PATH", f"{p}/path", "Duplicate changed file path")
                else:
                    seen.add(normalized)
        if "status" in cf:
            v.check_enum(cf["status"], FILE_STATUSES, f"{p}/status")
        for key in ("before_sha256", "after_sha256"):
            if key in cf and cf[key] is not None and not _matches(cf[key], RE_SHA256):
                v.add("INVALID_FORMAT", f"{p}/{key}", "Must be 64-character lowercase SHA-256 hex or null")


def _validate_commands(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    seen: Set[str] = set()
    for i, cmd in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(cmd, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        required = {"command_id", "argv", "cwd", "timestamps", "exit_code", "outcome", "stdout_sha256", "stderr_sha256"}
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
        if "timestamps" in cmd:
            ts = cmd["timestamps"]
            if not isinstance(ts, dict):
                v.add("INVALID_TYPE", f"{p}/timestamps", "Expected object")
            else:
                for key in ("started_at", "finished_at"):
                    if key not in ts:
                        v.add("MISSING_FIELD", f"{p}/timestamps/{key}", f"Missing required field '{key}'")
                    elif not _matches(ts[key], RE_RFC3339):
                        v.add("INVALID_FORMAT", f"{p}/timestamps/{key}", "Must be RFC3339 UTC timestamp ending in Z", phase="format")
                _validate_time_order(
                    v,
                    ts.get("started_at"),
                    ts.get("finished_at"),
                    f"{p}/timestamps/finished_at",
                )
                for key in ts:
                    if key not in {"started_at", "finished_at"}:
                        v.add("UNKNOWN_FIELD", f"{p}/timestamps/{key}", f"Unknown field '{key}'")
        if "exit_code" in cmd and cmd["exit_code"] is not None:
            ec = cmd["exit_code"]
            if isinstance(ec, bool) or not isinstance(ec, int):
                v.add("INVALID_TYPE", f"{p}/exit_code", "Expected integer or null", phase="scalar")
        if "outcome" in cmd:
            v.check_enum(cmd["outcome"], COMMAND_OUTCOMES, f"{p}/outcome")
        for key in ("stdout_sha256", "stderr_sha256"):
            if key in cmd and cmd[key] is not None and not _matches(cmd[key], RE_SHA256):
                v.add("INVALID_FORMAT", f"{p}/{key}", "Must be 64-character lowercase SHA-256 hex or null")


def _validate_evidence(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    seen: Set[str] = set()
    for i, ev in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(ev, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        required = {"evidence_id", "kind", "criterion_ids", "command_id", "artifact_path", "artifact_sha256", "summary"}
        for key in required:
            if key not in ev:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in ev:
            if key not in required:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "evidence_id" in ev:
            eid = ev["evidence_id"]
            if not isinstance(eid, str) or eid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/evidence_id", "Evidence ID must be a non-empty string")
            elif eid in seen:
                v.add("DUPLICATE_ID", f"{p}/evidence_id", "Duplicate evidence_id")
            else:
                seen.add(eid)
        if "kind" in ev:
            v.check_enum(ev["kind"], EVIDENCE_KINDS, f"{p}/kind")
        if "criterion_ids" in ev:
            ids = ev["criterion_ids"]
            if not isinstance(ids, list):
                v.add("INVALID_TYPE", f"{p}/criterion_ids", "Expected array")
            else:
                for j, cid in enumerate(ids):
                    if not isinstance(cid, str) or cid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/criterion_ids/{j}", "Criterion ID must be a non-empty string")
        if "artifact_path" in ev and ev["artifact_path"] is not None:
            _validate_repo_relative_path(v, ev["artifact_path"], f"{p}/artifact_path")
        if "artifact_sha256" in ev and ev["artifact_sha256"] is not None and not _matches(ev["artifact_sha256"], RE_SHA256):
            v.add("INVALID_FORMAT", f"{p}/artifact_sha256", "Must be 64-character lowercase SHA-256 hex or null")
        if "summary" in ev:
            v.check_non_empty_string(ev["summary"], f"{p}/summary")


def _validate_criteria(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one criterion result")
    seen: Set[str] = set()
    for i, crit in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(crit, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("criterion_id", "status", "evidence_ids"):
            if key not in crit:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in crit:
            if key not in {"criterion_id", "status", "evidence_ids"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "criterion_id" in crit:
            cid = crit["criterion_id"]
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/criterion_id", "Criterion ID must be a non-empty string")
            elif cid in seen:
                v.add("DUPLICATE_ID", f"{p}/criterion_id", "Duplicate criterion_id")
            else:
                seen.add(cid)
        if "status" in crit:
            v.check_enum(crit["status"], CRITERION_STATUSES, f"{p}/status")
        if "evidence_ids" in crit:
            ids = crit["evidence_ids"]
            if not isinstance(ids, list):
                v.add("INVALID_TYPE", f"{p}/evidence_ids", "Expected array")
            else:
                if crit.get("status") == "SATISFIED" and len(ids) == 0:
                    v.add("EVIDENCE_MISSING", f"{p}/evidence_ids", "SATISFIED criterion must cite evidence")
                for j, eid in enumerate(ids):
                    if not isinstance(eid, str) or eid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/evidence_ids/{j}", "Evidence ID must be a non-empty string")


def _validate_checkpoints(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one checkpoint")
    seen: Set[str] = set()
    for i, cp in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(cp, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("artifact_id", "path", "sha256"):
            if key not in cp:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in cp:
            if key not in {"artifact_id", "path", "sha256"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "artifact_id" in cp:
            aid = cp["artifact_id"]
            if not isinstance(aid, str) or aid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/artifact_id", "Artifact ID must be a non-empty string")
            elif aid in seen:
                v.add("DUPLICATE_ID", f"{p}/artifact_id", "Duplicate artifact_id")
            else:
                seen.add(aid)
        if "path" in cp:
            _validate_repo_relative_path(v, cp["path"], f"{p}/path")
        if "sha256" in cp and not _matches(cp["sha256"], RE_SHA256):
            v.add("INVALID_FORMAT", f"{p}/sha256", "Must be 64-character lowercase SHA-256 hex")


def _validate_fallback(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("reason", "provider_evidence_id", "reassign_to"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in {"reason", "provider_evidence_id", "reassign_to"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    if "reason" in value:
        v.check_enum(value["reason"], FALLBACK_REASONS, f"{path}/reason")
    if "provider_evidence_id" in value:
        v.check_non_empty_string(value["provider_evidence_id"], f"{path}/provider_evidence_id")
    if "reassign_to" in value and value["reassign_to"] != "sonnet_implementation":
        v.add("INVALID_VALUE", f"{path}/reassign_to", "reassign_to must be 'sonnet_implementation'")


def _cross_field_checks_worker_result(v: _PacketValidator) -> None:
    value = v.value

    # Self-hash.
    declared = value.get("result_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"result_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/result_sha256", "result_sha256 does not match canonical self-hash")

    # COMPLETED requires all commands passed and no remaining criteria.
    outcome = value.get("outcome")
    rem = value.get("remaining_criterion_ids", [])
    commands = value.get("commands", [])
    if outcome == "COMPLETED":
        if rem:
            v.add("INVALID_VALUE", "/remaining_criterion_ids", "COMPLETED result must have no remaining criteria")
        for cmd in commands:
            if cmd.get("outcome") != "PASSED":
                v.add("COMMAND_FAILED", f"/commands/{commands.index(cmd)}/outcome", "COMPLETED result requires all commands PASSED")
                break

    # CHECKPOINTED requires fallback, checkpoints, changed files, remaining criteria.
    if outcome == "CHECKPOINTED":
        if value.get("fallback") is None:
            v.add("CHECKPOINT_INCOMPLETE", "/fallback", "CHECKPOINTED result requires a fallback")
        if not value.get("changed_files"):
            v.add("CHECKPOINT_INCOMPLETE", "/changed_files", "CHECKPOINTED result requires changed files")
        if not rem:
            v.add("CHECKPOINT_INCOMPLETE", "/remaining_criterion_ids", "CHECKPOINTED result requires remaining criteria")

    # Every criterion in criteria must be represented exactly once across criteria + remaining.
    crit_ids = {c.get("criterion_id") for c in value.get("criteria", []) if isinstance(c, dict)}
    rem_ids = set(rem) if isinstance(rem, list) else set()
    if crit_ids & rem_ids:
        v.add("INVALID_VALUE", "/remaining_criterion_ids", "Criterion appears both as satisfied and remaining")

    # Evidence references must exist.
    evidence_ids = {e.get("evidence_id") for e in value.get("evidence", []) if isinstance(e, dict)}
    for i, crit in enumerate(value.get("criteria", [])):
        if isinstance(crit, dict):
            for j, eid in enumerate(crit.get("evidence_ids", [])):
                if eid not in evidence_ids:
                    v.add("EVIDENCE_MISSING", f"/criteria/{i}/evidence_ids/{j}", "Referenced evidence not found")

    for i, cmd in enumerate(commands):
        if isinstance(cmd, dict):
            for j, eid in enumerate(cmd.get("expected_evidence_ids", [])):
                if eid not in evidence_ids:
                    v.add("EVIDENCE_MISSING", f"/commands/{i}/expected_evidence_ids/{j}", "Referenced evidence not found")
