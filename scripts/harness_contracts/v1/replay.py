"""Replay bundle validation for harness contract v1."""

import datetime
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import (
    GOVERNED_PATHS,
    RE_SHA256,
    _matches,
    _normalize_relative_path,
    _PacketValidator,
    validate_packet,
)
from harness_contracts.v1.transition import validate_transition
from harness_contracts.v1.verdict import validate_verdict
from harness_contracts.v1.worker_result import RE_RFC3339, validate_worker_result


def _parse_rfc3339(value: str) -> Optional[datetime.datetime]:
    if not _matches(value, RE_RFC3339):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _path_is_under_or_equal(path: str, roots: Set[str]) -> bool:
    """Return True if ``path`` is equal to or a descendant of at least one root."""
    path_parts = path.split("/") if path else []
    for root in roots:
        root_parts = root.split("/") if root else []
        if len(path_parts) >= len(root_parts):
            if path_parts[: len(root_parts)] == root_parts:
                return True
    return False


def _path_overlaps_any(path: str, others: Set[str]) -> bool:
    """Return True if ``path`` shares any ancestor/descendant/equality overlap."""
    path_parts = path.split("/") if path else []
    for other in others:
        other_parts = other.split("/") if other else []
        min_len = min(len(path_parts), len(other_parts))
        if path_parts[:min_len] == other_parts[:min_len]:
            return True
    return False


def validate_replay_bundle(
    value: Any,
    trusted_dependency_provenance: Optional[Dict[str, Dict[str, str]]] = None,
    trusted_reviewer_sessions: Optional[Set[str]] = None,
    trusted_attempt_worker: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Validate a coordinator-assembled replay bundle.

    ``trusted_attempt_worker``, when supplied, is the ATTEMPT_STARTED-
    recorded ``worker`` identity for the specific attempt under review --
    ground truth for a plan-pinned fallback route, which the bundle's own
    ``packet.assigned_worker`` (the packet's static, enrollment-time default)
    does not reflect and must never be mutated to reflect: ``packet`` inside
    the bundle has to stay byte-identical to the enrolled packet artifact for
    its own self-hash (``packet_sha256``) and downstream terminal-seal
    binding to keep holding. Passing it here, alongside the bundle rather
    than inside it, is the same shape ``trusted_dependency_provenance`` and
    ``trusted_reviewer_sessions`` already use for coordinator-owned context a
    self-consistent bundle cannot forge on its own. Omitting it (every caller
    that predates this parameter) preserves the exact prior behavior: the
    worker-identity cross-check falls back to ``packet.assigned_worker``.
    """
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Replay bundle root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    v.trusted_dependency_provenance = trusted_dependency_provenance
    v.trusted_reviewer_sessions = trusted_reviewer_sessions
    v.trusted_attempt_worker = trusted_attempt_worker
    _validate_bundle_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(v.errors)


def _validate_bundle_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "packet",
        "prior_state_event",
        "dependency_states",
        "worker_result",
        "opus_verdict",
        "validator_version",
        "bundle_sha256",
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

    if value.get("validator_version") != "1":
        v.add("INVALID_VALUE", "/validator_version", "validator_version must be '1'", phase="value")

    if not _matches(value.get("bundle_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/bundle_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    # Self-hash.
    declared = value.get("bundle_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"bundle_sha256"}))
        if computed != declared:
            v.add(
                "EVIDENCE_HASH_MISMATCH",
                "/bundle_sha256",
                "bundle_sha256 does not match canonical self-hash",
                phase="cross_object",
            )

    # Validate sub-objects.
    packet = value.get("packet")
    packet_result = validate_packet(packet)
    if not packet_result["valid"]:
        for e in packet_result["errors"]:
            v.errors.append({**e, "path": f"/packet{e['path']}", "_phase": 1})

    worker_result = value.get("worker_result")
    wr_result = validate_worker_result(worker_result)
    if not wr_result["valid"]:
        for e in wr_result["errors"]:
            v.errors.append({**e, "path": f"/worker_result{e['path']}", "_phase": 1})

    verdict = value.get("opus_verdict")
    verdict_result = validate_verdict(verdict)
    if not verdict_result["valid"]:
        for e in verdict_result["errors"]:
            v.errors.append({**e, "path": f"/opus_verdict{e['path']}", "_phase": 1})

    # Validate prior_state_event.
    pse = value.get("prior_state_event")
    if isinstance(pse, dict):
        for key in ("from_state", "to_state", "event_at"):
            if key not in pse:
                v.add("MISSING_FIELD", f"/prior_state_event/{key}", f"Missing required field '{key}'")
        for key in pse:
            if key not in {"from_state", "to_state", "event_at"}:
                v.add("UNKNOWN_FIELD", f"/prior_state_event/{key}", f"Unknown field '{key}'")
        if "from_state" in pse and "to_state" in pse:
            t_result = validate_transition(pse["from_state"], pse["to_state"])
            if not t_result["valid"]:
                for e in t_result["errors"]:
                    v.errors.append({**e, "path": "/prior_state_event", "_phase": 7})
        if "event_at" in pse and not _matches(pse["event_at"], RE_RFC3339):
            v.add("INVALID_FORMAT", "/prior_state_event/event_at", "Must be RFC3339 UTC timestamp ending in Z", phase="format")
    else:
        v.add("INVALID_TYPE", "/prior_state_event", "Expected object", phase="scalar")

    # Validate dependency_states.
    _validate_dependency_states(v, value.get("dependency_states"), packet)

    _cross_object_replay_checks(v, packet, worker_result, verdict, pse)


def _validate_dependency_states(v: _PacketValidator, value: Any, packet: Any) -> None:
    if not isinstance(packet, dict):
        return
    deps = packet.get("dependency_ids", [])
    if not isinstance(deps, list):
        deps = []

    if not isinstance(value, list):
        v.add("INVALID_TYPE", "/dependency_states", "Expected array", phase="scalar")
        return

    if len(value) == 0 and len(deps) > 0:
        v.add(
            "EVIDENCE_MISSING",
            "/dependency_states",
            "dependency_states must record one ACCEPTED entry per packet dependency",
            phase="evidence_accept",
        )
        return

    if len(value) > 0 and len(deps) == 0:
        v.add(
            "INVALID_VALUE",
            "/dependency_states",
            "dependency_states must be empty when packet has no dependencies",
            phase="value",
        )

    # Fail closed: external trusted provenance is required whenever dependencies exist.
    trusted = getattr(v, "trusted_dependency_provenance", None)
    if deps and trusted is None:
        v.add(
            "TRUST_CONTEXT_MISSING",
            "/dependency_states",
            "Trusted dependency provenance context is required to validate dependencies",
            phase="path_authority",
        )

    upstream_digest_fields = (
        "upstream_packet_sha256",
        "upstream_result_sha256",
        "upstream_verdict_sha256",
        "upstream_bundle_sha256",
    )
    allowed_dep_state_keys = {"packet_id", "state", "evidence_id"} | set(upstream_digest_fields)

    seen: Set[str] = set()
    for i, rec in enumerate(value):
        p = f"/dependency_states/{i}"
        if not isinstance(rec, dict):
            v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
            continue
        for key in allowed_dep_state_keys:
            if key not in rec:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in rec:
            if key not in allowed_dep_state_keys:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        for key in upstream_digest_fields:
            if key in rec and not _matches(rec[key], RE_SHA256):
                v.add("INVALID_FORMAT", f"{p}/{key}", "Must be 64-character lowercase SHA-256 hex", phase="format")
        pid = rec.get("packet_id")
        if not isinstance(pid, str) or pid.strip() == "":
            v.add("INVALID_VALUE", f"{p}/packet_id", "packet_id must be a non-empty string", phase="value")
        else:
            if pid in seen:
                v.add("DUPLICATE_ID", f"{p}/packet_id", "Duplicate packet_id in dependency_states", phase="uniqueness")
            seen.add(pid)
            if pid not in deps:
                v.add(
                    "UNKNOWN_DEPENDENCY",
                    f"{p}/packet_id",
                    f"'{pid}' is not listed in packet dependency_ids",
                    phase="path_authority",
                )
            elif isinstance(trusted, dict):
                if pid not in trusted:
                    v.add(
                        "TRUST_CONTEXT_MISSING",
                        f"{p}/packet_id",
                        f"Trusted provenance for dependency '{pid}' is missing",
                        phase="path_authority",
                    )
                else:
                    expected = trusted[pid]
                    for key in upstream_digest_fields:
                        upstream_key = key.replace("upstream_", "")
                        recorded = rec.get(key)
                        expected_value = expected.get(upstream_key) if isinstance(expected, dict) else None
                        if recorded != expected_value:
                            v.add(
                                "PROVENANCE_MISMATCH",
                                f"{p}/{key}",
                                f"Dependency '{pid}' {key} does not match trusted provenance",
                                phase="path_authority",
                            )
        state = rec.get("state")
        if state != "ACCEPTED":
            v.add(
                "DEPENDENCY_NOT_ACCEPTED",
                f"{p}/state",
                "Dependency state in replay must be ACCEPTED",
                phase="path_authority",
            )
        eid = rec.get("evidence_id")
        if not isinstance(eid, str) or eid.strip() == "":
            v.add("INVALID_VALUE", f"{p}/evidence_id", "evidence_id must be a non-empty string", phase="value")

    # Exact coverage of packet dependencies.
    covered = {rec.get("packet_id") for rec in value if isinstance(rec, dict) and isinstance(rec.get("packet_id"), str)}
    for dep in deps:
        if isinstance(dep, str) and dep not in covered:
            v.add(
                "EVIDENCE_MISSING",
                "/dependency_states",
                f"Missing dependency_state record for '{dep}'",
                phase="evidence_accept",
            )

    # Evidence existence is checked in cross-object checks once evidence is indexed.


def _cross_object_replay_checks(v: _PacketValidator, packet: Any, worker_result: Any, verdict: Any, pse: Any) -> None:
    """Enforce cross-object contract rules between packet, result, verdict and transition."""
    if not isinstance(packet, dict) or not isinstance(worker_result, dict):
        return

    # Worker identity must match the worker actually assigned to this
    # attempt. ``trusted_attempt_worker`` (the ATTEMPT_STARTED-recorded
    # identity for the reviewed attempt, supplied by the coordinator
    # assembling this bundle -- see ``validate_replay_bundle``'s docstring)
    # is the ground truth when present, because it reflects a plan-pinned
    # fallback route the packet's own static ``assigned_worker`` default
    # cannot. Falling back to ``packet.get("assigned_worker")`` when it is
    # absent preserves the exact prior check for every caller that predates
    # this parameter, including the non-fallback case this check exists to
    # catch: a worker result whose identity disagrees with what was actually
    # assigned, for any reason other than a legitimate recorded fallback.
    trusted_worker = getattr(v, "trusted_attempt_worker", None)
    assigned = trusted_worker if isinstance(trusted_worker, dict) else (packet.get("assigned_worker") or {})
    worker = worker_result.get("worker") or {}
    for field in ("worker_id", "provider", "model"):
        if assigned.get(field) != worker.get(field):
            v.add(
                "REVISION_MISMATCH",
                f"/worker_result/worker/{field}",
                f"worker.{field} does not match packet.assigned_worker",
                phase="cross_object",
            )
    if packet.get("lane") != worker.get("lane"):
        v.add("REVISION_MISMATCH", "/worker_result/worker/lane", "worker.lane does not match packet.lane", phase="cross_object")

    # Starting revision must match.
    if packet.get("starting_revision") != worker_result.get("starting_revision"):
        v.add(
            "REVISION_MISMATCH",
            "/worker_result/starting_revision",
            "worker_result starting_revision does not match packet",
            phase="cross_object",
        )

    # Identity and hash checks.
    if packet.get("packet_id") != worker_result.get("packet_id"):
        v.add("REVISION_MISMATCH", "/worker_result/packet_id", "worker_result packet_id does not match packet", phase="cross_object")
    if packet.get("packet_sha256") != worker_result.get("packet_sha256"):
        v.add(
            "EVIDENCE_HASH_MISMATCH",
            "/worker_result/packet_sha256",
            "worker_result packet_sha256 does not match packet",
            phase="cross_object",
        )

    if isinstance(verdict, dict):
        if worker_result.get("result_id") != verdict.get("result_id"):
            v.add("REVISION_MISMATCH", "/opus_verdict/result_id", "verdict result_id does not match worker_result", phase="cross_object")
        if worker_result.get("result_sha256") != verdict.get("result_sha256"):
            v.add(
                "EVIDENCE_HASH_MISMATCH",
                "/opus_verdict/result_sha256",
                "verdict result_sha256 does not match worker_result",
                phase="cross_object",
            )
        if packet.get("packet_id") != verdict.get("packet_id"):
            v.add("REVISION_MISMATCH", "/opus_verdict/packet_id", "verdict packet_id does not match packet", phase="cross_object")
        if packet.get("packet_sha256") != verdict.get("packet_sha256"):
            v.add(
                "EVIDENCE_HASH_MISMATCH",
                "/opus_verdict/packet_sha256",
                "verdict packet_sha256 does not match packet",
                phase="cross_object",
            )

    # Budget / attempt.
    pb = packet.get("budgets") or {}
    rb = worker_result.get("budgets") or {}
    retry_limit = pb.get("retry_limit")
    attempt = worker_result.get("attempt")
    if isinstance(retry_limit, int) and isinstance(attempt, int) and attempt > retry_limit + 1:
        v.add("BUDGET_EXCEEDED", "/worker_result/attempt", "attempt exceeds packet retry_limit + 1", phase="evidence_accept")
    if isinstance(pb.get("max_turns"), int) and isinstance(rb.get("turns_used"), int) and rb["turns_used"] > pb["max_turns"]:
        v.add("BUDGET_EXCEEDED", "/worker_result/budgets/turns_used", "turns_used exceeds packet max_turns", phase="evidence_accept")
    if isinstance(pb.get("max_output_bytes"), int) and isinstance(rb.get("output_bytes"), int) and rb["output_bytes"] > pb["max_output_bytes"]:
        v.add("BUDGET_EXCEEDED", "/worker_result/budgets/output_bytes", "output_bytes exceeds packet max_output_bytes", phase="evidence_accept")
    if isinstance(retry_limit, int) and isinstance(rb.get("retry_count"), int) and rb["retry_count"] > retry_limit:
        v.add("BUDGET_EXCEEDED", "/worker_result/budgets/retry_count", "retry_count exceeds packet retry_limit", phase="evidence_accept")

    # Timing.
    _validate_timing(v, packet, worker_result)

    # Path semantics for changed files.
    writable_raw = packet.get("writable_paths") or []
    forbidden_raw = packet.get("forbidden_surfaces") or []
    writable = {_normalize_relative_path(p) for p in writable_raw if isinstance(p, str)}
    forbidden = {_normalize_relative_path(p) for p in forbidden_raw if isinstance(p, str)}
    for i, cf in enumerate(worker_result.get("changed_files") or []):
        if not isinstance(cf, dict):
            continue
        cp = cf.get("path")
        if not isinstance(cp, str):
            continue
        normalized = _normalize_relative_path(cp)
        if normalized is None:
            v.add("PATH_ESCAPE", f"/worker_result/changed_files/{i}/path", "Path escapes the repository root", phase="path_authority")
            continue
        if normalized in GOVERNED_PATHS:
            v.add("GOVERNED_PATH", f"/worker_result/changed_files/{i}/path", f"Changed path '{normalized}' is governed", phase="path_authority")
        if not _path_is_under_or_equal(normalized, writable):
            v.add(
                "CHANGED_FILE_UNDECLARED",
                f"/worker_result/changed_files/{i}/path",
                f"Changed file '{normalized}' is not within writable_paths",
                phase="path_authority",
            )
        if _path_overlaps_any(normalized, forbidden):
            v.add(
                "PATH_OVERLAP",
                f"/worker_result/changed_files/{i}/path",
                f"Changed file '{normalized}' overlaps a forbidden surface",
                phase="path_authority",
            )

    # Verification commands: exact set, argv/cwd/exit/outcome/timing.
    packet_commands = {c.get("command_id"): c for c in (packet.get("verification_commands") or []) if isinstance(c, dict)}
    result_commands = {c.get("command_id"): c for c in (worker_result.get("commands") or []) if isinstance(c, dict)}
    result_command_list = worker_result.get("commands") or []

    # No extra result commands.
    for i, rc in enumerate(result_command_list):
        if isinstance(rc, dict):
            cid = rc.get("command_id")
            if cid not in packet_commands:
                v.add(
                    "COMMAND_MISMATCH",
                    f"/worker_result/commands/{i}/command_id",
                    f"Unexpected result command '{cid}' not declared in packet",
                    phase="cross_object",
                )

    for cid, pc in packet_commands.items():
        if cid not in result_commands:
            v.add("COMMAND_NOT_RUN", "/worker_result/commands", f"Verification command '{cid}' was not run", phase="evidence_accept")
            continue
        rc = result_commands[cid]
        rc_index = next(
            (i for i, c in enumerate(result_command_list) if isinstance(c, dict) and c.get("command_id") == cid),
            None,
        )
        path_prefix = f"/worker_result/commands/{rc_index}" if rc_index is not None else "/worker_result/commands"
        if rc.get("argv") != pc.get("argv"):
            v.add("COMMAND_MISMATCH", f"{path_prefix}/argv", f"Command '{cid}' argv does not match packet", phase="cross_object")
        if rc.get("cwd") != pc.get("cwd"):
            v.add("COMMAND_MISMATCH", f"{path_prefix}/cwd", f"Command '{cid}' cwd does not match packet", phase="cross_object")
        if rc.get("exit_code") != pc.get("expected_exit_code"):
            v.add("COMMAND_MISMATCH", f"{path_prefix}/exit_code", f"Command '{cid}' exit_code does not match packet expected_exit_code", phase="cross_object")
        if isinstance(verdict, dict) and verdict.get("verdict") == "ACCEPT" and rc.get("outcome") != "PASSED":
            v.add("COMMAND_FAILED", f"{path_prefix}/outcome", f"Command '{cid}' outcome is not PASSED", phase="evidence_accept")

        # Command elapsed time may not exceed packet timeout.
        pc_timeout = pc.get("timeout_seconds")
        ts = rc.get("timestamps") or {}
        cmd_started = ts.get("started_at")
        cmd_finished = ts.get("finished_at")
        if isinstance(pc_timeout, int):
            cmd_started_dt = _parse_rfc3339(cmd_started) if isinstance(cmd_started, str) else None
            cmd_finished_dt = _parse_rfc3339(cmd_finished) if isinstance(cmd_finished, str) else None
            if cmd_started_dt is not None and cmd_finished_dt is not None:
                elapsed = (cmd_finished_dt - cmd_started_dt).total_seconds()
                if elapsed > pc_timeout:
                    v.add(
                        "BUDGET_EXCEEDED",
                        f"{path_prefix}/timestamps/finished_at",
                        f"Command '{cid}' elapsed time exceeds timeout_seconds",
                        phase="evidence_accept",
                    )

    # Evidence indexing.
    evidence_list = [e for e in (worker_result.get("evidence") or []) if isinstance(e, dict)]
    evidence_by_id = {e.get("evidence_id"): e for e in evidence_list if isinstance(e.get("evidence_id"), str)}

    # Validate dependency_state evidence existence now that evidence is indexed.
    dep_states = v.value.get("dependency_states")
    if isinstance(dep_states, list):
        for i, rec in enumerate(dep_states):
            if not isinstance(rec, dict):
                continue
            eid = rec.get("evidence_id")
            if isinstance(eid, str) and eid not in evidence_by_id:
                v.add(
                    "EVIDENCE_MISSING",
                    f"/dependency_states/{i}/evidence_id",
                    f"Dependency evidence '{eid}' not found in worker_result evidence",
                    phase="evidence_accept",
                )

    # Packet acceptance criteria.
    packet_criteria = {c.get("criterion_id"): c for c in (packet.get("acceptance_criteria") or []) if isinstance(c, dict)}
    packet_crit_ids = set(packet_criteria.keys())

    # Criteria in the result must exactly match packet criteria.
    result_crit_ids = {c.get("criterion_id") for c in (worker_result.get("criteria") or []) if isinstance(c, dict)}
    missing_in_result = packet_crit_ids - result_crit_ids
    extra_in_result = result_crit_ids - packet_crit_ids
    for cid in sorted(missing_in_result):
        v.add("ACCEPTANCE_UNSATISFIED", "/worker_result/criteria", f"Criterion '{cid}' from packet is missing in worker_result", phase="evidence_accept")
    for cid in sorted(extra_in_result):
        v.add("ACCEPTANCE_UNSATISFIED", "/worker_result/criteria", f"Criterion '{cid}' in worker_result is not declared in packet", phase="evidence_accept")

    # Remaining criteria must be packet criteria and disjoint from satisfied.
    remaining = worker_result.get("remaining_criterion_ids") or []
    if isinstance(remaining, list):
        rem_ids = set(remaining)
        for cid in remaining:
            if cid not in packet_crit_ids:
                v.add(
                    "ACCEPTANCE_UNSATISFIED",
                    "/worker_result/remaining_criterion_ids",
                    f"Remaining criterion '{cid}' is not declared in packet",
                    phase="evidence_accept",
                )
        overlap = result_crit_ids & rem_ids
        for cid in sorted(overlap):
            v.add(
                "INVALID_VALUE",
                "/worker_result/remaining_criterion_ids",
                f"Criterion '{cid}' appears both as satisfied and remaining",
                phase="value",
            )

    # Verdict criterion findings must exactly cover packet criteria.
    if isinstance(verdict, dict):
        verdict_crit_ids = {f.get("criterion_id") for f in (verdict.get("criterion_findings") or []) if isinstance(f, dict)}
        missing_in_verdict = packet_crit_ids - verdict_crit_ids
        extra_in_verdict = verdict_crit_ids - packet_crit_ids
        for cid in sorted(missing_in_verdict):
            v.add(
                "ACCEPTANCE_UNSATISFIED",
                "/opus_verdict/criterion_findings",
                f"Verdict missing finding for criterion '{cid}'",
                phase="evidence_accept",
            )
        for cid in sorted(extra_in_verdict):
            v.add(
                "ACCEPTANCE_UNSATISFIED",
                "/opus_verdict/criterion_findings",
                f"Verdict finding for criterion '{cid}' is not declared in packet",
                phase="evidence_accept",
            )

    # Evidence reference integrity and bidirectional linkage.
    for i, ev in enumerate(evidence_list):
        p = f"/worker_result/evidence/{i}"
        eid = ev.get("evidence_id")
        # criterion_ids must reference packet criteria.
        for j, cid in enumerate(ev.get("criterion_ids") or []):
            if cid not in packet_crit_ids:
                v.add(
                    "ACCEPTANCE_UNSATISFIED",
                    f"{p}/criterion_ids/{j}",
                    f"Evidence criterion_id '{cid}' is not a packet acceptance criterion",
                    phase="evidence_accept",
                )
        cmd_id = ev.get("command_id")
        if cmd_id is not None:
            if cmd_id not in packet_commands:
                v.add(
                    "COMMAND_MISMATCH",
                    f"{p}/command_id",
                    f"Evidence command_id '{cmd_id}' is not a packet verification command",
                    phase="cross_object",
                )
            elif cmd_id not in result_commands:
                v.add(
                    "COMMAND_NOT_RUN",
                    f"{p}/command_id",
                    f"Evidence command_id '{cmd_id}' was not executed",
                    phase="evidence_accept",
                )
            else:
                # Evidence must be listed in the packet command's expected_evidence_ids.
                expected = packet_commands[cmd_id].get("expected_evidence_ids") or []
                if eid not in expected:
                    v.add(
                        "EVIDENCE_MISSING",
                        f"{p}/evidence_id",
                        f"Evidence '{eid}' is not expected by command '{cmd_id}'",
                        phase="evidence_accept",
                    )

    # Each packet verification command's expected_evidence_ids must exist and cite the command.
    for cid, pc in packet_commands.items():
        for j, eid in enumerate(pc.get("expected_evidence_ids") or []):
            if eid not in evidence_by_id:
                v.add(
                    "EVIDENCE_MISSING",
                    f"/packet/verification_commands/{cid}/expected_evidence_ids/{j}",
                    f"Expected evidence '{eid}' for command '{cid}' not found in worker_result",
                    phase="evidence_accept",
                )
            else:
                ev_cmd_id = evidence_by_id[eid].get("command_id")
                if ev_cmd_id != cid:
                    v.add(
                        "EVIDENCE_HASH_MISMATCH",
                        f"/worker_result/evidence",
                        f"Evidence '{eid}' expected by command '{cid}' does not cite that command_id",
                        phase="evidence_accept",
                    )

    # Required evidence from packet acceptance criteria must be a subset of both
    # worker criterion evidence and verdict finding evidence.
    result_criteria_by_id = {c.get("criterion_id"): c for c in (worker_result.get("criteria") or []) if isinstance(c, dict)}
    verdict_findings_by_id = {}
    if isinstance(verdict, dict):
        verdict_findings_by_id = {f.get("criterion_id"): f for f in (verdict.get("criterion_findings") or []) if isinstance(f, dict)}
    for cid, crit in packet_criteria.items():
        required = set(crit.get("required_evidence_ids") or [])
        worker_ev_ids = set(result_criteria_by_id.get(cid, {}).get("evidence_ids") or [])
        verdict_ev_ids = set(verdict_findings_by_id.get(cid, {}).get("evidence_ids") or [])
        for eid in sorted(required):
            if eid not in evidence_by_id:
                v.add(
                    "EVIDENCE_MISSING",
                    "/worker_result/evidence",
                    f"Required evidence '{eid}' for criterion '{cid}' is missing",
                    phase="evidence_accept",
                )
                continue
            if eid not in worker_ev_ids:
                v.add(
                    "EVIDENCE_MISSING",
                    f"/worker_result/criteria/{cid}/evidence_ids",
                    f"Required evidence '{eid}' must be cited by worker criterion '{cid}'",
                    phase="evidence_accept",
                )
            if eid not in verdict_ev_ids:
                v.add(
                    "EVIDENCE_MISSING",
                    f"/opus_verdict/criterion_findings/{cid}/evidence_ids",
                    f"Required evidence '{eid}' must be cited by verdict finding for '{cid}'",
                    phase="evidence_accept",
                )

    # Verdict evidence citations must exist in the result.
    if isinstance(verdict, dict):
        for i, finding in enumerate(verdict.get("criterion_findings") or []):
            if isinstance(finding, dict):
                for j, eid in enumerate(finding.get("evidence_ids") or []):
                    if eid not in evidence_by_id:
                        v.add(
                            "EVIDENCE_MISSING",
                            f"/opus_verdict/criterion_findings/{i}/evidence_ids/{j}",
                            f"Verdict evidence '{eid}' not found in worker_result",
                            phase="evidence_accept",
                        )
        for i, finding in enumerate(verdict.get("global_findings") or []):
            if isinstance(finding, dict):
                for j, eid in enumerate(finding.get("evidence_ids") or []):
                    if eid not in evidence_by_id:
                        v.add(
                            "EVIDENCE_MISSING",
                            f"/opus_verdict/global_findings/{i}/evidence_ids/{j}",
                            f"Verdict evidence '{eid}' not found in worker_result",
                            phase="evidence_accept",
                        )

    # Global findings applicability for ACCEPT.
    if isinstance(verdict, dict) and verdict.get("verdict") == "ACCEPT":
        _validate_accept_global_findings(v, verdict, evidence_by_id)

    # Fallback / remaining criteria checks around ACCEPT.
    if isinstance(verdict, dict) and verdict.get("verdict") == "ACCEPT":
        if worker_result.get("fallback") is not None:
            v.add("INVALID_FALLBACK", "/worker_result/fallback", "ACCEPT verdict cannot follow a fallback", phase="evidence_accept")
        remaining = worker_result.get("remaining_criterion_ids") or []
        if remaining:
            v.add("ACCEPTANCE_UNSATISFIED", "/worker_result/remaining_criterion_ids", "ACCEPT verdict cannot have remaining criteria", phase="evidence_accept")

    # Reviewer independence: explicit trusted reviewer session context is required;
    # bundle string inequality is not sufficient to establish trust.
    if isinstance(verdict, dict):
        reviewer = verdict.get("reviewer") or {}
        reviewer_session = reviewer.get("session_id")
        trusted_reviewer_sessions = getattr(v, "trusted_reviewer_sessions", None)
        if trusted_reviewer_sessions is None:
            v.add(
                "TRUST_CONTEXT_MISSING",
                "/opus_verdict/reviewer/session_id",
                "Trusted reviewer session context is required",
                phase="cross_object",
            )
        elif reviewer_session not in trusted_reviewer_sessions:
            v.add(
                "UNAUTHORIZED_REVIEWER",
                "/opus_verdict/reviewer/session_id",
                "Reviewer session_id is not in the trusted reviewer session set",
                phase="cross_object",
            )
        if reviewer_session == worker.get("session_id"):
            v.add(
                "WORKER_SELF_ACCEPT",
                "/opus_verdict/reviewer/session_id",
                "Reviewer session_id must differ from worker session_id",
                phase="cross_object",
            )

    # Cross-object chronology: worker work precedes review; state events cannot predate work/review.
    _validate_chronology(v, worker_result, verdict, pse)

    # Prior state event destination must match the verdict's next state.
    if isinstance(pse, dict) and isinstance(verdict, dict):
        if pse.get("to_state") != verdict.get("next_state"):
            v.add(
                "INVALID_TRANSITION",
                "/prior_state_event/to_state",
                "prior_state_event.to_state must equal verdict.next_state",
                phase="transition",
            )


def _validate_chronology(v: _PacketValidator, worker_result: Any, verdict: Any, pse: Any) -> None:
    """Enforce temporal ordering across worker, commands, verdict, and state event."""
    worker_started = worker_result.get("started_at")
    worker_finished = worker_result.get("finished_at")
    worker_started_dt = _parse_rfc3339(worker_started) if isinstance(worker_started, str) else None
    worker_finished_dt = _parse_rfc3339(worker_finished) if isinstance(worker_finished, str) else None

    if worker_started_dt is not None and worker_finished_dt is not None:
        if worker_finished_dt < worker_started_dt:
            v.add(
                "CHRONOLOGY_VIOLATION",
                "/worker_result/finished_at",
                "Worker finished_at must not be before started_at",
                phase="cross_object",
            )

        for i, cmd in enumerate(worker_result.get("commands") or []):
            if not isinstance(cmd, dict):
                continue
            ts = cmd.get("timestamps") or {}
            cmd_started = ts.get("started_at")
            cmd_finished = ts.get("finished_at")
            cmd_started_dt = _parse_rfc3339(cmd_started) if isinstance(cmd_started, str) else None
            cmd_finished_dt = _parse_rfc3339(cmd_finished) if isinstance(cmd_finished, str) else None
            if cmd_started_dt is not None and (cmd_started_dt < worker_started_dt or cmd_started_dt > worker_finished_dt):
                v.add(
                    "CHRONOLOGY_VIOLATION",
                    f"/worker_result/commands/{i}/timestamps/started_at",
                    "Command started_at must be within the worker interval",
                    phase="cross_object",
                )
            if cmd_finished_dt is not None and (cmd_finished_dt < worker_started_dt or cmd_finished_dt > worker_finished_dt):
                v.add(
                    "CHRONOLOGY_VIOLATION",
                    f"/worker_result/commands/{i}/timestamps/finished_at",
                    "Command finished_at must be within the worker interval",
                    phase="cross_object",
                )
            if cmd_started_dt is not None and cmd_finished_dt is not None and cmd_finished_dt < cmd_started_dt:
                v.add(
                    "CHRONOLOGY_VIOLATION",
                    f"/worker_result/commands/{i}/timestamps/finished_at",
                    "Command finished_at must not be before started_at",
                    phase="cross_object",
                )

    if isinstance(verdict, dict):
        reviewed_at = verdict.get("reviewed_at")
        reviewed_dt = _parse_rfc3339(reviewed_at) if isinstance(reviewed_at, str) else None
        if reviewed_dt is not None and worker_finished_dt is not None and reviewed_dt < worker_finished_dt:
            v.add(
                "CHRONOLOGY_VIOLATION",
                "/opus_verdict/reviewed_at",
                "Verdict reviewed_at must not be before worker_result finished_at",
                phase="cross_object",
            )

    if isinstance(pse, dict):
        event_at = pse.get("event_at")
        event_dt = _parse_rfc3339(event_at) if isinstance(event_at, str) else None
        if event_dt is not None and worker_finished_dt is not None and event_dt < worker_finished_dt:
            v.add(
                "CHRONOLOGY_VIOLATION",
                "/prior_state_event/event_at",
                "State event_at must not be before worker_result finished_at",
                phase="cross_object",
            )
        if event_dt is not None and pse.get("to_state") == "ACCEPTED":
            reviewed_at = verdict.get("reviewed_at") if isinstance(verdict, dict) else None
            reviewed_dt = _parse_rfc3339(reviewed_at) if isinstance(reviewed_at, str) else None
            if reviewed_dt is not None and event_dt < reviewed_dt:
                v.add(
                    "CHRONOLOGY_VIOLATION",
                    "/prior_state_event/event_at",
                    "ACCEPTED state event_at must not be before verdict reviewed_at",
                    phase="cross_object",
                )


def _validate_timing(v: _PacketValidator, packet: Any, worker_result: Any) -> None:
    """Check worker and command timing against packet budgets."""
    worker_started = worker_result.get("started_at")
    worker_finished = worker_result.get("finished_at")
    started_dt = _parse_rfc3339(worker_started) if isinstance(worker_started, str) else None
    finished_dt = _parse_rfc3339(worker_finished) if isinstance(worker_finished, str) else None
    if started_dt is not None and finished_dt is not None:
        elapsed = (finished_dt - started_dt).total_seconds()
        wall_clock = packet.get("budgets", {}).get("wall_clock_seconds")
        if isinstance(wall_clock, int) and elapsed > wall_clock:
            v.add(
                "BUDGET_EXCEEDED",
                "/worker_result/finished_at",
                "Worker elapsed time exceeds packet wall_clock_seconds",
                phase="evidence_accept",
            )


def _validate_accept_global_findings(v: _PacketValidator, verdict: Dict[str, Any], evidence_by_id: Dict[str, Any]) -> None:
    """For ACCEPT, enforce global-finding applicability and evidence rules."""
    from harness_contracts.v1.verdict import ALWAYS_APPLICABLE_RULES, CONDITIONAL_RULES

    present_rules = {}
    for f in verdict.get("global_findings", []):
        if isinstance(f, dict):
            rid = f.get("rule_id")
            if rid:
                present_rules[rid] = f

    for rule in ALWAYS_APPLICABLE_RULES:
        if rule not in present_rules:
            v.add(
                "EVIDENCE_MISSING",
                "/opus_verdict/global_findings",
                f"ACCEPT requires global finding for rule '{rule}'",
                phase="evidence_accept",
            )
            continue
        finding = present_rules[rule]
        if finding.get("finding") != "PASS":
            idx = verdict.get("global_findings", []).index(finding)
            v.add(
                "ACCEPTANCE_UNSATISFIED",
                f"/opus_verdict/global_findings/{idx}/finding",
                f"ACCEPT requires always-applicable rule '{rule}' to be PASS",
                phase="evidence_accept",
            )

    findings_list = verdict.get("global_findings", [])
    index_by_rule = {}
    for i, f in enumerate(findings_list):
        if isinstance(f, dict) and f.get("rule_id"):
            index_by_rule[f["rule_id"]] = i

    for rid, finding in present_rules.items():
        state = finding.get("finding")
        idx = index_by_rule.get(rid)
        path_prefix = f"/opus_verdict/global_findings/{idx}" if idx is not None else "/opus_verdict/global_findings"
        if state == "FAIL":
            v.add(
                "ACCEPTANCE_UNSATISFIED",
                path_prefix,
                f"ACCEPT cannot have a FAIL global finding for rule '{rid}'",
                phase="evidence_accept",
            )
        elif state == "NOT_APPLICABLE":
            if rid not in CONDITIONAL_RULES:
                v.add(
                    "ACCEPTANCE_UNSATISFIED",
                    path_prefix,
                    f"Rule '{rid}' is always applicable and cannot be NOT_APPLICABLE",
                    phase="evidence_accept",
                )
        elif state == "PASS":
            ev_ids = finding.get("evidence_ids") or []
            if not ev_ids:
                v.add(
                    "EVIDENCE_MISSING",
                    f"{path_prefix}/evidence_ids",
                    f"PASS global finding for rule '{rid}' must cite evidence",
                    phase="evidence_accept",
                )
            for eid in ev_ids:
                if eid not in evidence_by_id:
                    v.add(
                        "EVIDENCE_MISSING",
                        f"{path_prefix}/evidence_ids",
                        f"Global finding for rule '{rid}' cites missing evidence '{eid}'",
                        phase="evidence_accept",
                    )
