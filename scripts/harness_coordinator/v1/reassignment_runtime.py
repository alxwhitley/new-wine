"""Pinned immutable evidence for the one permitted Kimi-to-Sonnet fallback."""

import json
import os
import stat
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.reassignment import validate_reassignment
from harness_contracts.v1.classification import validate_attempt_outcome
from harness_contracts.v1.provider_evidence import validate_provider_evidence
from harness_contracts.v1.worker_result import validate_worker_result
from harness_coordinator.v1.paths import validate_harness_id
from harness_coordinator.v1.seals_runtime import ArtifactConflict


class ReassignmentConflict(ValueError):
    """An immutable reassignment slot or its preserved evidence disagrees."""


def _canonical_object(raw: bytes, validator, kind: str) -> Dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReassignmentConflict(f"{kind} is invalid JSON") from exc
    if raw != canonical_bytes(body):
        raise ReassignmentConflict(f"{kind} is not canonically encoded")
    result = validator(body)
    if not result["valid"]:
        raise ReassignmentConflict(
            f"{kind} is contract-invalid: {result['errors'][0]['message']}")
    return body


def load_and_validate_attempt_evidence(
    handle, packet_id: str, packet_sha256: str, attempt: int,
    outcome_record: Dict[str, Any],
    started_event: Dict[str, Any], run_started_event: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], bytes, bytes]:
    """Load pinned evidence and bind it to this exact originating attempt."""
    outcome_raw = handle.read(("results", packet_id, str(attempt), "attempt_outcome.json"))
    if outcome_raw is None:
        raise ReassignmentConflict("attempt outcome is missing")
    pinned_outcome = _canonical_object(outcome_raw, validate_attempt_outcome, "attempt outcome")
    if pinned_outcome != outcome_record:
        raise ReassignmentConflict("attempt outcome changed during resolution")
    if outcome_record.get("packet_id") != packet_id or outcome_record.get("attempt") != attempt:
        raise ReassignmentConflict("attempt outcome belongs to another packet or attempt")
    if outcome_record.get("packet_sha256") != packet_sha256:
        raise ReassignmentConflict("attempt outcome packet digest mismatch")
    attempt_payload = ((started_event.get("payload") or {}).get("attempt") or {})
    worker = attempt_payload.get("worker") or {}
    if started_event.get("packet_id") != packet_id or attempt_payload.get("attempt") != attempt:
        raise ReassignmentConflict("ATTEMPT_STARTED identity mismatch")
    if outcome_record.get("lane") != attempt_payload.get("lane"):
        raise ReassignmentConflict("attempt outcome lane mismatch")
    if (outcome_record.get("coordinator_id") != started_event.get("coordinator_id")
            or outcome_record.get("run_id") != started_event.get("run_id")):
        raise ReassignmentConflict("attempt outcome origin mismatch")
    if run_started_event.get("run_id") != started_event.get("run_id"):
        raise ReassignmentConflict("originating RUN_STARTED mismatch")
    run_coordinator = (((run_started_event.get("payload") or {}).get("run") or {})
                       .get("coordinator") or {})

    evidence_parts = ("results", packet_id, str(attempt), "provider_evidence.json")
    evidence_raw = handle.read(evidence_parts)
    if evidence_raw is None:
        raise ReassignmentConflict("provider evidence is missing")
    evidence = _canonical_object(evidence_raw, validate_provider_evidence, "provider evidence")
    if evidence.get("evidence_sha256") != outcome_record.get("provider_evidence_sha256"):
        raise ReassignmentConflict("provider evidence digest mismatch")
    if evidence.get("packet_id") != packet_id or evidence.get("attempt") != attempt:
        raise ReassignmentConflict("provider evidence belongs to another packet or attempt")
    captured = evidence.get("captured_by") or {}
    if (captured.get("coordinator_id") != outcome_record.get("coordinator_id")
            or captured.get("run_id") != outcome_record.get("run_id")):
        raise ReassignmentConflict("provider evidence origin mismatch")
    if (captured.get("coordinator_id") != started_event.get("coordinator_id")
            or captured.get("coordinator_id") != run_started_event.get("coordinator_id")
            or captured.get("boot_id") != run_coordinator.get("boot_id")
            or captured.get("hostname") != run_coordinator.get("hostname")):
        raise ReassignmentConflict("provider evidence capture identity mismatch")
    if evidence.get("provider") != worker.get("provider"):
        raise ReassignmentConflict("provider evidence worker mismatch")
    invocation = outcome_record.get("invocation") or {}
    evidence_invocation = evidence.get("invocation") or {}
    for key in ("argv", "started_at", "finished_at", "exit_code", "signal", "timed_out"):
        if evidence_invocation.get(key) != invocation.get(key):
            raise ReassignmentConflict(f"provider evidence invocation mismatch: {key}")

    channel_bytes = []
    for channel in ("stdout", "stderr"):
        pointer = outcome_record.get(channel) or {}
        if evidence.get(f"{channel}_path") != pointer.get("path"):
            raise ReassignmentConflict(f"provider evidence {channel} path mismatch")
        raw = handle.read(tuple(pointer["path"].split("/")))
        if raw is None or len(raw) != pointer.get("byte_length"):
            raise ReassignmentConflict(f"captured {channel} is missing or truncated")
        digest = compute_sha256(raw)
        if digest != pointer.get("sha256") or digest != evidence.get(f"{channel}_sha256"):
            raise ReassignmentConflict(f"captured {channel} digest mismatch")
        channel_bytes.append(raw)

    result_path = (outcome_record.get("raw_result") or {}).get("path")
    result_raw = handle.read(tuple(result_path.split("/"))) if result_path else None
    if result_raw is None:
        raise ReassignmentConflict("worker result is missing")
    worker_result = _canonical_object(result_raw, validate_worker_result, "worker result")
    if (worker_result.get("packet_id") != packet_id
            or worker_result.get("attempt") != attempt
            or worker_result.get("result_sha256") != (outcome_record.get("raw_result") or {}).get("sha256")):
        raise ReassignmentConflict("worker result identity or digest mismatch")
    if worker_result.get("packet_sha256") != outcome_record.get("packet_sha256"):
        raise ReassignmentConflict("worker result packet digest mismatch")
    result_worker = worker_result.get("worker") or {}
    if ({key: result_worker.get(key) for key in ("worker_id", "session_id", "provider", "model")}
            != worker
            or result_worker.get("lane") != attempt_payload.get("lane")):
        raise ReassignmentConflict("worker result worker identity mismatch")
    result_fallback = worker_result.get("fallback")
    outcome_fallback = outcome_record.get("fallback")
    if result_fallback != outcome_fallback:
        raise ReassignmentConflict("worker result fallback mismatch")
    expected_reason = {
        "CONFIRMED_RATE_LIMIT_EXHAUSTION": "confirmed_rate_limit_exhaustion",
        "CONFIRMED_QUOTA_EXHAUSTION": "confirmed_quota_exhaustion",
    }.get(evidence.get("classification"))
    if (not isinstance(result_fallback, dict)
            or result_fallback.get("provider_evidence_id") != evidence.get("evidence_id")
            or result_fallback.get("reason") != expected_reason):
        raise ReassignmentConflict("worker result fallback evidence mismatch")
    return worker_result, evidence, channel_bytes[0], channel_bytes[1]


def build_reassignment_record(
    packet: Dict[str, Any], worker_result: Dict[str, Any],
    provider_evidence: Dict[str, Any], outcome_record: Dict[str, Any],
    packet_events: Sequence[Dict[str, Any]], *, next_event_seq: int,
    now: str, attempt: int, paths: Mapping[str, str],
) -> Dict[str, Any]:
    """Assemble and contract-validate the record for the reserved event seq."""
    if not packet_events:
        raise ReassignmentConflict("reassignment requires a non-empty packet journal range")
    record = {
        "schema_version": 1,
        "packet_id": validate_harness_id(packet["packet_id"]),
        "packet_sha256": packet["packet_sha256"],
        "from_lane": "kimi_implementation", "to_lane": "sonnet_implementation",
        "reassigned_at": now, "at_event_seq": next_event_seq, "kimi_attempt": attempt,
        "preserved": {
            "changed_files": worker_result.get("changed_files", []),
            "worker_result": {"result_id": worker_result["result_id"],
                              "result_sha256": worker_result["result_sha256"],
                              "path": paths["worker_result"]},
            "provider_evidence": {"evidence_id": provider_evidence["evidence_id"],
                                  "evidence_sha256": provider_evidence["evidence_sha256"],
                                  "path": paths["provider_evidence"]},
            "attempt_outcome": {"outcome_sha256": outcome_record["outcome_sha256"],
                                "path": paths["attempt_outcome"]},
            "checkpoints": worker_result.get("checkpoints", []),
            "verification_evidence": [
                {"evidence_id": item["evidence_id"], "command_id": item.get("command_id"),
                 "artifact_path": item.get("artifact_path"),
                 "artifact_sha256": item.get("artifact_sha256")}
                for item in worker_result.get("evidence", [])
            ],
            "remaining_criterion_ids": worker_result.get("remaining_criterion_ids", []),
            "journal_range": {
                "first_seq": packet_events[0]["seq"], "last_seq": packet_events[-1]["seq"],
                "first_event_sha256": packet_events[0]["event_sha256"],
                "last_event_sha256": packet_events[-1]["event_sha256"],
            },
        },
        "reassignment_sha256": "",
    }
    record["reassignment_sha256"] = compute_sha256(
        canonical_bytes(record, omit={"reassignment_sha256"}))
    result = validate_reassignment(record)
    if not result["valid"]:
        raise ReassignmentConflict(
            f"reassignment record is invalid: {result['errors'][0]['message']}")
    return record


def publish_reassignment(handle, record: Dict[str, Any]) -> Tuple[str, bool]:
    """Publish once through the pinned root; identical replay is a no-op."""
    result = validate_reassignment(record)
    if not result["valid"]:
        raise ReassignmentConflict(result["errors"][0]["message"])
    parts = ("reassignments", f"{validate_harness_id(record['packet_id'])}.json")
    try:
        created = handle.publish(parts, canonical_bytes(record))
    except ArtifactConflict as exc:
        raise ReassignmentConflict(str(exc)) from exc
    return record["reassignment_sha256"], created


def _pointer_digest(pointer: Dict[str, Any]) -> str:
    for key in ("result_sha256", "evidence_sha256", "outcome_sha256"):
        if key in pointer:
            return pointer[key]
    raise ReassignmentConflict("preserved pointer has no digest")


def _read_worktree_file(worktree: str, relative_path: str):
    if not os.path.isabs(worktree) or relative_path.startswith("/"):
        raise ReassignmentConflict("preserved worktree path is not absolute/relative as required")
    root_fd = os.open(worktree, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                      getattr(os, "O_NOFOLLOW", 0))
    opened = [root_fd]
    try:
        parts = relative_path.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ReassignmentConflict("preserved path is not canonical")
        parent = root_fd
        for component in parts[:-1]:
            parent = os.open(component, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                             getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
            opened.append(parent)
        try:
            fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
        except FileNotFoundError:
            return None
        opened.append(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ReassignmentConflict("preserved artifact is not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        for fd in reversed(opened):
            os.close(fd)


def _worktree_digest_matches(worktree: str, path: str, expected) -> bool:
    try:
        raw = _read_worktree_file(worktree, path)
    except (OSError, ReassignmentConflict, TypeError):
        return False
    if expected is None:
        return raw is None
    return raw is not None and compute_sha256(raw) == expected


def assert_preserved(handle, record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return deterministic evidence mismatches; absence is never success."""
    mismatches: List[Dict[str, Any]] = []
    validation = validate_reassignment(record)
    if not validation["valid"]:
        return [{"kind": "reassignment", "code": "INVALID_VALUE"}]
    preserved = record["preserved"]
    for kind in ("worker_result", "provider_evidence", "attempt_outcome"):
        pointer = preserved[kind]
        raw = handle.read(tuple(pointer["path"].split("/")))
        if raw is None:
            mismatches.append({"kind": kind, "code": "EVIDENCE_MISSING"})
            continue
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            mismatches.append({"kind": kind, "code": "INVALID_JSON"})
            continue
        declared = _pointer_digest(pointer)
        digest_key = {"worker_result": "result_sha256", "provider_evidence": "evidence_sha256",
                      "attempt_outcome": "outcome_sha256"}[kind]
        computed = compute_sha256(canonical_bytes(body, omit={digest_key}))
        if body.get(digest_key) != declared or computed != declared or raw != canonical_bytes(body):
            mismatches.append({"kind": kind, "code": "EVIDENCE_HASH_MISMATCH"})
    packet_raw = handle.read(("packets", f"{validate_harness_id(record['packet_id'])}.json"))
    if packet_raw is None:
        mismatches.append({"kind": "packet", "code": "EVIDENCE_MISSING"})
    else:
        try:
            packet = json.loads(packet_raw.decode("utf-8"))
            packet_digest = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
            if (packet_raw != canonical_bytes(packet)
                    or packet.get("packet_sha256") != record.get("packet_sha256")
                    or packet_digest != record.get("packet_sha256")):
                mismatches.append({"kind": "packet", "code": "EVIDENCE_HASH_MISMATCH"})
        except (UnicodeDecodeError, json.JSONDecodeError):
            mismatches.append({"kind": "packet", "code": "INVALID_JSON"})
            packet = None

    if packet_raw is not None and 'packet' in locals() and isinstance(packet, dict):
        worktree = (packet.get("worktree") or {}).get("path")
        for changed in preserved["changed_files"]:
            expected = changed.get("after_sha256")
            if not _worktree_digest_matches(worktree, changed["path"], expected):
                mismatches.append({"kind": "changed_file", "code": "EVIDENCE_HASH_MISMATCH"})
        for checkpoint in preserved["checkpoints"]:
            if not _worktree_digest_matches(worktree, checkpoint["path"], checkpoint["sha256"]):
                mismatches.append({"kind": "checkpoint", "code": "EVIDENCE_HASH_MISMATCH"})
        for evidence in preserved["verification_evidence"]:
            path = evidence.get("artifact_path")
            digest = evidence.get("artifact_sha256")
            if path is None:
                continue
            if not _worktree_digest_matches(worktree, path, digest):
                mismatches.append({"kind": "verification_evidence", "code": "EVIDENCE_HASH_MISMATCH"})

    journal_raw = handle.read(("journal.ndjson",))
    journal_range = preserved["journal_range"]
    if journal_raw is None:
        mismatches.append({"kind": "journal_range", "code": "EVIDENCE_MISSING"})
    else:
        try:
            events = [json.loads(line) for line in journal_raw.decode("utf-8").splitlines() if line]
            by_seq = {event.get("seq"): event for event in events}
            first = by_seq.get(journal_range["first_seq"])
            last = by_seq.get(journal_range["last_seq"])
            if (first is None or last is None
                    or first.get("event_sha256") != journal_range["first_event_sha256"]
                    or last.get("event_sha256") != journal_range["last_event_sha256"]):
                mismatches.append({"kind": "journal_range", "code": "EVIDENCE_HASH_MISMATCH"})
        except (UnicodeDecodeError, json.JSONDecodeError):
            mismatches.append({"kind": "journal_range", "code": "INVALID_JSON"})
    return mismatches


__all__ = ["ReassignmentConflict", "assert_preserved", "build_reassignment_record",
           "load_and_validate_attempt_evidence", "publish_reassignment"]
