"""One bounded P5 coordinator iteration: review, seal, promote, select, claim."""

import errno
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet
from harness_contracts.v1.replay import validate_replay_bundle
from harness_coordinator.v1.classify_runtime import (
    promote_dependencies,
    requeue_revise,
    resolve_open_attempts,
)
from harness_coordinator.v1.locks import create_claim_at, read_claim_at
from harness_coordinator.v1.invoke import (
    WorkerAdapter, invoke_worker, load_completed_invocation, persist_invocation_outcome,
)
from harness_coordinator.v1.integration_analysis import (
    analyze_integration, build_integration_manifest,
)
from harness_coordinator.v1.paths import validate_harness_id
from harness_coordinator.v1.process_sidecar import terminate_sidecar_process
from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal, _make_event, run_started_recovery
from harness_coordinator.v1.review import (
    _dependency_context, load_trusted_reviewer_sessions, resolve_pending_reviews,
)
from harness_coordinator.v1.reconcile import build_reconciliation_report, emit_reconciliation_report
from harness_coordinator.v1.scheduler import select_next
from harness_coordinator.v1.seals_runtime import (
    SealContradiction, _bundle_from_event, authenticate_seal, build_terminal_seal,
    committing_terminal_event, complete_terminal_seals, open_state_root, seal_binding,
    terminal_seal_parts,
)
from harness_coordinator.v1.store import JournalHeadMoved, atomic_replace, append_journal, read_journal
from harness_coordinator.v1.workspace_evidence import (
    WorkspaceEvidenceError, build_postflight, build_postflight_failure,
    discover_repo_root, ensure_attempt_baseline, load_attempt_baseline,
    publish_workspace_artifact, validate_postflight_binding,
)


def attempt_session_id(run_id: str, packet_id: str, attempt: int) -> str:
    """Durable worker-session identity; P5B must consume this exact value."""
    return f"session-{run_id}-{packet_id}-{attempt}"


def _record_workspace_baseline(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    folded: Dict[str, Dict[str, Any]], packet: Dict[str, Any], intent_id: str,
    coordinator_id: str, run_id: str, now: str, protected_worktree_path: Optional[str],
    *, revalidate: bool = True,
) -> None:
    """Durably bind the immutable O4 baseline before a worker is invoked."""
    repo_root = discover_repo_root(packet["worktree"]["path"])
    packet_id = packet["packet_id"]
    active_packets = []
    for active_id, active_state in folded.items():
        if active_state.get("state") not in {"READY", "RUNNING", "REVIEW", "REVISE"}:
            continue
        active_body = _load_enrolled_packet(
            state_root, active_id, active_state, journal_events, handle=handle)
        active_body["state"] = active_state["state"]
        active_packets.append(active_body)
    binding = ensure_attempt_baseline(
        handle, packet, intent_id, repo_root, protected_worktree_path, active_packets,
        revalidate=revalidate)
    matching = [
        event for event in journal_events
        if event.get("event_type") == "WORKSPACE_BASELINE_RECORDED"
        and event.get("packet_id") == packet_id
        and event.get("intent_id") == intent_id
    ]
    if matching:
        artifact = (matching[-1].get("payload") or {}).get("artifacts") or []
        expected = {
            "kind": "workspace_baseline", "artifact_id": "workspace_baseline",
            "path": binding["artifact_path"], "sha256": binding["artifact_sha256"],
            "content_sha256": binding["content_sha256"],
        }
        if len(artifact) != 1 or any(artifact[0].get(key) != value for key, value in expected.items()):
            from harness_coordinator.v1.recovery import IntegrityError
            raise IntegrityError("WORKSPACE_BASELINE_MISMATCH", "Workspace baseline journal binding disagrees", packet_id)
        return
    raw = handle.read(tuple(binding["artifact_path"].split("/")))
    if raw is None:
        from harness_coordinator.v1.recovery import IntegrityError
        raise IntegrityError("WORKSPACE_BASELINE_MISSING", "Published workspace baseline disappeared", packet_id)
    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        (previous["seq"] + 1) if previous else 1, "WORKSPACE_BASELINE_RECORDED",
        coordinator_id, run_id, state_root_id, previous, now, packet_id=packet_id,
        intent_id=intent_id, from_state=None, to_state=None, cause="none",
        payload={
            "packet": None, "attempt": None,
            "artifacts": [{
                "kind": "workspace_baseline", "artifact_id": "workspace_baseline",
                "path": binding["artifact_path"], "sha256": binding["artifact_sha256"],
                "content_sha256": binding["content_sha256"], "byte_length": len(raw),
            }],
            "classification": None, "transition_detail": None, "recovery": None,
            "run": None, "report": None,
        },
    )
    handle.verify_identity()
    append_journal(
        os.path.join(state_root, "journal.ndjson"), event,
        os.path.join(state_root, "locks", "journal.wlock"), expected_head=previous,
    )
    handle.verify_identity()
    journal_events.append(event)


def _record_workspace_postflight(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    packet: Dict[str, Any], intent_id: str, worker_result: Optional[Dict[str, Any]],
    coordinator_id: str, run_id: str, now: str,
) -> Dict[str, Any]:
    """Publish and journal the authoritative postflight before review can begin."""
    packet_id = packet["packet_id"]
    parts = ("workspace", packet_id, f"{intent_id}.postflight.json")
    existing = handle.read(parts)
    if existing is not None:
        try:
            artifact = json.loads(existing.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_INVALID", "Postflight is not valid JSON") from exc
        if (existing != canonical_bytes(artifact)
                or set(artifact) != {
                    "schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
                    "worktree_identity", "packet_snapshot", "protected_snapshot", "writable_paths",
                    "forbidden_surfaces", "derived_changes", "scope_findings", "worker_manifest_findings",
                    "protected_findings", "secret_findings", "acceptance_allowed", "content_sha256", "artifact_sha256",
                }
                or artifact.get("artifact_kind") != "workspace_postflight"
                or artifact.get("packet_id") != packet_id or artifact.get("intent_id") != intent_id):
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_INVALID", "Postflight artifact is invalid")
        content_sha256 = compute_sha256(canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"}))
        copy = dict(artifact)
        copy["content_sha256"] = content_sha256
        artifact_sha256 = compute_sha256(canonical_bytes(copy, omit={"artifact_sha256"}))
        if artifact.get("content_sha256") != content_sha256 or artifact.get("artifact_sha256") != artifact_sha256:
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_INVALID", "Postflight hashes disagree")
        binding = {"artifact_path": "/".join(parts), "content_sha256": content_sha256,
                   "artifact_sha256": artifact_sha256}
    else:
        baseline = load_attempt_baseline(handle, packet, intent_id)
        try:
            artifact = build_postflight(packet, intent_id, baseline, worker_result)
        except Exception:
            # Evidence uncertainty must fail closed as HUMAN_REQUIRED; never
            # reinterpret postflight failure as an ordinary retryable worker
            # outcome or expose a low-level filesystem/Git error in the artifact.
            artifact = build_postflight_failure(packet, intent_id, baseline)
        binding = publish_workspace_artifact(handle, parts, artifact)
        raw = handle.read(parts)
        if raw is None:
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_MISSING", "Published postflight disappeared")
        artifact = json.loads(raw.decode("utf-8"))
    matching = [
        event for event in journal_events
        if event.get("event_type") == "WORKSPACE_POSTFLIGHT_RECORDED"
        and event.get("packet_id") == packet_id and event.get("intent_id") == intent_id
    ]
    validated_postflight = validate_postflight_binding(handle, packet, intent_id, artifact)
    artifact = validated_postflight["artifact"]
    binding = {
        "artifact_path": validated_postflight["binding"]["path"],
        "artifact_sha256": validated_postflight["binding"]["artifact_sha256"],
        "content_sha256": validated_postflight["binding"]["content_sha256"],
    }
    expected = {"kind": "workspace_postflight", "artifact_id": "workspace_postflight",
                "path": binding["artifact_path"], "sha256": binding["artifact_sha256"],
                "content_sha256": binding["content_sha256"]}
    if matching:
        artifacts = (matching[-1].get("payload") or {}).get("artifacts") or []
        if len(artifacts) != 1 or any(artifacts[0].get(key) != value for key, value in expected.items()):
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_MISMATCH", "Postflight journal binding disagrees")
        return artifact
    raw = handle.read(parts)
    if raw is None:
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_MISSING", "Published postflight disappeared")
    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        (previous["seq"] + 1) if previous else 1, "WORKSPACE_POSTFLIGHT_RECORDED",
        coordinator_id, run_id, state_root_id, previous, now, packet_id=packet_id, intent_id=intent_id,
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [{
            "kind": "workspace_postflight", "artifact_id": "workspace_postflight",
            "path": binding["artifact_path"], "sha256": binding["artifact_sha256"],
            "content_sha256": binding["content_sha256"], "byte_length": len(raw),
        }], "classification": None, "transition_detail": None, "recovery": None,
                 "run": None, "report": None},
    )
    handle.verify_identity()
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=previous)
    handle.verify_identity()
    journal_events.append(event)
    return artifact


def _record_workspace_integration(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    packet: Dict[str, Any], postflight: Dict[str, Any], analysis: Dict[str, Any],
    coordinator_id: str, run_id: str, now: str,
) -> None:
    """Publish and journal one accepted, postflight-bound integration artifact."""
    artifact = build_integration_manifest(packet, postflight, analysis)
    parts = ("workspace", packet["packet_id"], f"{postflight['intent_id']}.integration.json")
    existing = handle.read(parts)
    if existing is not None:
        try:
            persisted = json.loads(existing.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INVALID", "Integration manifest is not valid JSON") from exc
        if existing != canonical_bytes(persisted) or persisted != artifact:
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_MISMATCH", "Integration manifest disagrees")
    else:
        publish_workspace_artifact(handle, parts, artifact)
        existing = handle.read(parts)
    if existing is None:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_MISSING", "Published integration manifest disappeared")
    binding = {
        "kind": "workspace_integration", "artifact_id": "workspace_integration",
        "path": "/".join(parts), "sha256": artifact["artifact_sha256"],
        "content_sha256": artifact["content_sha256"], "byte_length": len(existing),
    }
    matching = [
        event for event in journal_events
        if event.get("event_type") == "INTEGRATION_MANIFEST_RECORDED"
        and event.get("packet_id") == packet["packet_id"]
        and event.get("intent_id") == postflight["intent_id"]
    ]
    if matching:
        recorded = (matching[-1].get("payload") or {}).get("artifacts") or []
        if len(matching) != 1 or len(recorded) != 1 or any(
                recorded[0].get(key) != value for key, value in binding.items()):
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_MISMATCH", "Integration manifest journal binding disagrees")
        return
    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        (previous["seq"] + 1) if previous else 1, "INTEGRATION_MANIFEST_RECORDED",
        coordinator_id, run_id, state_root_id, previous, now,
        packet_id=packet["packet_id"], intent_id=postflight["intent_id"],
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [binding],
                 "classification": None, "transition_detail": None, "recovery": None,
                 "run": None, "report": None},
    )
    handle.verify_identity()
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=previous)
    handle.verify_identity()
    journal_events.append(event)


def _accepted_replay_evidence(handle, packet_id: str, packet: Dict[str, Any],
                              packet_state: Dict[str, Any], journal_events: List[Dict[str, Any]],
                              folded: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Authenticate the exact accepted replay bundle and its terminal seal."""
    if packet_state.get("state") != "ACCEPTED":
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Packet is not accepted")
    parts = terminal_seal_parts(packet_id)
    raw = handle.read(parts)
    if raw is None:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted packet has no terminal seal")
    try:
        seal = authenticate_seal(raw, packet_id, "/".join(parts))
        expected_seal = build_terminal_seal(handle, journal_events, packet_id, packet_state, seal["sealed_at"])
    except (SealContradiction, KeyError) as exc:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted terminal seal is not trustworthy") from exc
    if (seal.get("terminal_state") != "ACCEPTED" or seal_binding(seal) != seal_binding(expected_seal)
            or seal.get("packet_sha256") != packet.get("packet_sha256")):
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted terminal seal disagrees")
    try:
        committing = committing_terminal_event(journal_events, packet_id, "ACCEPTED")
        if (seal.get("sealing_event_seq") != committing.get("seq")
                or seal.get("sealing_event_sha256") != committing.get("event_sha256")):
            raise SealContradiction("seal does not bind the accepted verdict event")
        bundle = _bundle_from_event(handle, committing, packet_id)
    except SealContradiction as exc:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay evidence is unavailable") from exc
    bundle_packet = bundle.get("packet")
    worker_result = bundle.get("worker_result")
    verdict = bundle.get("opus_verdict")
    upstream = seal.get("upstream_digests") or {}
    if (bundle_packet != packet or not isinstance(worker_result, dict) or not isinstance(verdict, dict)
            or verdict.get("verdict") != "ACCEPT" or verdict.get("next_state") != "ACCEPTED"
            or bundle.get("bundle_sha256") != upstream.get("bundle_sha256")
            or worker_result.get("result_sha256") != upstream.get("result_sha256")
            or verdict.get("verdict_sha256") != upstream.get("verdict_sha256")):
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay evidence disagrees")
    try:
        _dependency_states, provenance = _dependency_context(handle, packet, journal_events, folded)
        replay_validation = validate_replay_bundle(
            bundle, provenance, load_trusted_reviewer_sessions(handle))
    except Exception as exc:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay context is unavailable") from exc
    if not replay_validation["valid"]:
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay evidence is invalid")
    evidence_ids = sorted({item.get("evidence_id") for item in worker_result.get("evidence", [])
                           if isinstance(item, dict) and item.get("kind") == "verification"
                           and isinstance(item.get("evidence_id"), str) and item.get("evidence_id")})
    return {
        "attempt": worker_result.get("attempt"),
        "verification_evidence_ids": evidence_ids,
        "accepted_replay": {
            "replay_bundle_sha256": bundle["bundle_sha256"],
            "verdict_sha256": verdict["verdict_sha256"],
            "terminal_seal_sha256": seal["seal_sha256"],
        },
    }


def _integration_analysis_for_context(packet: Dict[str, Any], postflight: Dict[str, Any],
                                      context: Any, replay: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Require operator-supplied integration context; never invent a base."""
    identity = postflight.get("worktree_identity")
    if not isinstance(identity, dict) or not isinstance(identity.get("repo_root"), str):
        raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INVALID", "Postflight identity is invalid")
    base = context.get("integration_base") if isinstance(context, dict) else None
    target = context.get("integration_target_path") if isinstance(context, dict) else None
    if not isinstance(base, str) or not base:
        return None
    elif target is not None and not isinstance(target, str):
        analysis = {
            "schema_version": 1, "starting_revision": packet["starting_revision"],
            "integration_base": base, "packet_changed_paths": [item["path"] for item in postflight["derived_changes"]],
            "integration_base_changed_paths": [], "integration_target_path": None,
            "integration_target_status": "UNVERIFIABLE", "decision": "HUMAN_REQUIRED",
            "reason_codes": ["INTEGRATION_CONTEXT_INVALID"], "required_human_action": True,
        }
    else:
        analysis = analyze_integration(identity["repo_root"], packet["starting_revision"], base,
                                       postflight["derived_changes"], target)
    if not postflight.get("acceptance_allowed"):
        analysis["reason_codes"] = sorted(set(analysis["reason_codes"]) | {"INTEGRATION_POSTFLIGHT_INELIGIBLE"})
        analysis["decision"] = "HUMAN_REQUIRED"
        analysis["required_human_action"] = True
    analysis.update(replay)
    return analysis


def _publish_accepted_integrations(handle, state_root: str, state_root_id: str,
                                   journal_events: List[Dict[str, Any]],
                                   folded: Dict[str, Dict[str, Any]], coordinator_id: str,
                                   run_id: str, now: str,
                                   integration_context_by_packet: Optional[Mapping[str, Any]]) -> None:
    """Publish only accepted/sealed packet integration evidence, including recovery."""
    contexts = integration_context_by_packet or {}
    for packet_id, packet_state in sorted(folded.items()):
        if packet_state.get("state") != "ACCEPTED":
            continue
        # O3 packets predate O4 workspace evidence. Only a packet whose
        # attempt actually crossed the durable postflight gate participates in
        # integration-candidate publication.
        if not any(event.get("event_type") == "WORKSPACE_POSTFLIGHT_RECORDED"
                   and event.get("packet_id") == packet_id for event in journal_events):
            continue
        packet = _load_enrolled_packet(state_root, packet_id, packet_state, journal_events, handle=handle)
        replay = _accepted_replay_evidence(handle, packet_id, packet, packet_state, journal_events, folded)
        attempt = replay.get("attempt")
        if not isinstance(attempt, int) or attempt < 1:
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay has invalid attempt")
        intent_id = f"attempt-{packet_id}-{attempt}"
        postflight_path = ("workspace", packet_id, f"{intent_id}.postflight.json")
        raw = handle.read(postflight_path)
        if raw is None:
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted replay has no postflight")
        try:
            candidate = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted postflight is invalid") from exc
        postflight = validate_postflight_binding(handle, packet, intent_id, candidate)["artifact"]
        recorded = [event for event in journal_events
                    if event.get("event_type") == "WORKSPACE_POSTFLIGHT_RECORDED"
                    and event.get("packet_id") == packet_id and event.get("intent_id") == intent_id]
        expected = {
            "kind": "workspace_postflight", "artifact_id": "workspace_postflight",
            "path": "/".join(postflight_path), "sha256": postflight["artifact_sha256"],
            "content_sha256": postflight["content_sha256"],
        }
        recorded_artifacts = ((recorded[-1].get("payload") or {}).get("artifacts") or []) if recorded else []
        if (len(recorded) != 1 or len(recorded_artifacts) != 1
                or any(recorded_artifacts[0].get(key) != value for key, value in expected.items())):
            raise WorkspaceEvidenceError(
                "WORKSPACE_INTEGRATION_INELIGIBLE", "Accepted postflight journal binding disagrees")
        integration_parts = ("workspace", packet_id, f"{intent_id}.integration.json")
        existing = handle.read(integration_parts)
        if existing is not None:
            try:
                persisted = json.loads(existing.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkspaceEvidenceError("WORKSPACE_INTEGRATION_INVALID", "Integration manifest is not valid JSON") from exc
            persisted_analysis = {
                "starting_revision": persisted.get("starting_revision"),
                "integration_base": persisted.get("integration_base"),
                "integration_target_path": persisted.get("integration_target_path"),
                "integration_target_status": persisted.get("integration_target_status"),
                "packet_changed_paths": [item.get("path") for item in postflight["derived_changes"]],
                "decision": persisted.get("decision"), "reason_codes": persisted.get("reason_codes"),
                "required_human_action": persisted.get("required_human_action"),
                "verification_evidence_ids": persisted.get("verification_evidence_ids"),
                "accepted_replay": persisted.get("accepted_replay"),
            }
            if (persisted_analysis["accepted_replay"] != replay["accepted_replay"]
                    or persisted_analysis["verification_evidence_ids"]
                    != replay["verification_evidence_ids"]):
                raise WorkspaceEvidenceError(
                    "WORKSPACE_INTEGRATION_MISMATCH", "Integration manifest replay binding disagrees")
            _record_workspace_integration(
                handle, state_root, state_root_id, journal_events, packet, postflight,
                persisted_analysis, coordinator_id, run_id, now)
            continue
        analysis = _integration_analysis_for_context(packet, postflight, contexts.get(packet_id), replay)
        if analysis is None:
            continue
        _record_workspace_integration(
            handle, state_root, state_root_id, journal_events, packet, postflight,
            analysis, coordinator_id, run_id, now)


def _load_enrolled_packet(state_root: str, packet_id: str, packet: Dict[str, Any],
                          journal_events: List[Dict[str, Any]], handle=None) -> Dict[str, Any]:
    if handle is None:
        with open_state_root(state_root) as scoped:
            return _load_enrolled_packet(state_root, packet_id, packet, journal_events, handle=scoped)
    enroll_event = next(e for e in journal_events if e.get("event_type") == "PACKET_ENROLLED" and e.get("packet_id") == packet_id)
    recorded = enroll_event["payload"]["packet"]
    parts = ("packets", f"{validate_harness_id(packet_id)}.json")
    if recorded.get("packet_path") != "/".join(parts):
        raise ValueError("enrolled packet path does not match canonical packet artifact")
    try:
        raw = handle.read(parts)
    except OSError as exc:
        # The pinned no-follow read refuses a symlinked artifact or a
        # non-directory parent at the OS level; the caller contract for this
        # function is a ValueError naming the refusal, so translate rather
        # than leak an errno.
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError("enrolled packet artifact is a symlink or escapes its directory") from exc
        raise
    if raw is None:
        raise ValueError("enrolled packet artifact is missing")
    body = json.loads(raw.decode("utf-8"))
    if raw != canonical_bytes(body):
        raise ValueError("enrolled packet artifact is not canonical")
    result = validate_packet(body, dependency_states=None)
    if not result["valid"]:
        raise ValueError("enrolled packet artifact fails packet contract")
    digest = compute_sha256(canonical_bytes(body, omit={"packet_sha256"}))
    if digest != recorded.get("packet_sha256") or digest != packet.get("packet_sha256"):
        raise ValueError("enrolled packet artifact digest disagrees with journal/fold")
    if body.get("packet_id") != packet_id or body.get("lane") != recorded.get("lane") or body.get("lane") != packet.get("lane"):
        raise ValueError("enrolled packet identity or lane disagrees with journal/fold")
    if not isinstance(body.get("assigned_worker"), dict) or not isinstance(body.get("worktree"), dict):
        raise ValueError("enrolled packet worker/worktree identity missing")
    return body


def claim_packet(state_root: str, packet_id: str, packet: Dict[str, Any], coordinator_id: str,
                 run_id: str, trusted_process_context: Dict[str, Any], now: str,
                 handle=None) -> Dict[str, Any]:
    """Create the intent-scoped O_EXCL claim for one selected packet."""
    if handle is None:
        os.makedirs(state_root, exist_ok=True)
        with open_state_root(state_root) as scoped:
            return claim_packet(state_root, packet_id, packet, coordinator_id, run_id,
                                trusted_process_context, now, handle=scoped)
    attempt = packet.get("attempts_started", 0) + 1
    intent_id = f"attempt-{packet_id}-{attempt}"
    record = {
        "schema_version": 1, "packet_id": packet_id, "intent_id": intent_id,
        "stage": "claim", "attempt": attempt, "coordinator_id": coordinator_id,
        "run_id": run_id, "hostname": trusted_process_context["hostname"],
        "boot_id": trusted_process_context["boot_id"], "pid": trusted_process_context["pid"],
        "acquired_at": now, "heartbeat_at": now, "lease_seconds": 60,
        "lane": packet["lane"], "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    handle.verify_identity()
    create_claim_at(handle, packet_id, record)
    handle.verify_identity()
    return record


def claim_and_start_attempt(state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                            packet_id: str, packet: Dict[str, Any], coordinator_id: str,
                            run_id: str, trusted_process_context: Dict[str, Any], now: str,
                            handle=None) -> str:
    """Durably perform lock -> pending intent -> ATTEMPT_STARTED -> projection."""
    if handle is None:
        with open_state_root(state_root) as scoped:
            return claim_and_start_attempt(
                state_root, state_root_id, journal_events, packet_id, packet,
                coordinator_id, run_id, trusted_process_context, now, handle=scoped)
    packet_body = _load_enrolled_packet(
        state_root, packet_id, packet, journal_events, handle=handle)
    claim = claim_packet(
        state_root, packet_id, packet, coordinator_id, run_id,
        trusted_process_context, now, handle=handle)
    intent_id = claim["intent_id"]
    queue = _build_derived_queue(_fold_journal(state_root, journal_events)[0], state_root_id,
                                 journal_events[-1] if journal_events else None)
    queue["pending_intents"] = [{
        "intent_id": intent_id, "packet_id": packet_id, "stage": "claim", "created_at": now,
        "coordinator_id": coordinator_id, "run_id": run_id,
        "boot_id": trusted_process_context["boot_id"], "pid": trusted_process_context["pid"],
    }]
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    handle.verify_identity()
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(queue), coordinator_id,
                   f"pending-{run_id}-{claim['attempt']}")
    handle.verify_identity()

    assigned = packet_body["assigned_worker"]
    attempt_payload = {
        "attempt": claim["attempt"], "lane": packet["lane"],
        "worker": {"worker_id": assigned["worker_id"], "session_id": attempt_session_id(run_id, packet_id, claim["attempt"]),
                   "provider": assigned["provider"], "model": assigned["model"]},
        "claim_sha256": claim["claim_sha256"], "worktree_path": packet_body["worktree"]["path"],
    }
    prev = journal_events[-1] if journal_events else None
    journal_path = os.path.join(state_root, "journal.ndjson")
    moves = 0
    while True:
        event = _make_event((prev["seq"] + 1) if prev else 1, "ATTEMPT_STARTED", coordinator_id,
                            run_id, state_root_id, prev, now, packet_id=packet_id, intent_id=intent_id,
                            from_state="READY", to_state="RUNNING", cause="claim_committed",
                            payload={"packet": None, "attempt": attempt_payload, "artifacts": [],
                                     "classification": None, "transition_detail": None, "recovery": None,
                                     "run": None, "report": None})
        try:
            handle.verify_identity()
            append_journal(journal_path, event, os.path.join(state_root, "locks", "journal.wlock"), expected_head=prev)
            handle.verify_identity()
            break
        except JournalHeadMoved:
            moves += 1
            if moves >= 8:
                raise RuntimeError("ATTEMPT_STARTED journal head kept moving; pending intent preserved for recovery")
            handle.verify_identity()
            fresh, torn = read_journal(journal_path, state_root_id=state_root_id)
            handle.verify_identity()
            if torn is not None:
                raise RuntimeError("torn journal during ATTEMPT_STARTED; pending intent preserved for recovery")
            folded, _ = _fold_journal(state_root, fresh)
            current = folded.get(packet_id)
            lock = read_claim_at(handle, packet_id)
            if current is None or current.get("state") != "READY" or current.get("open_attempt") is not None:
                raise RuntimeError("packet no longer READY; pending intent preserved for recovery")
            if lock.get("intent_id") != intent_id or lock.get("claim_sha256") != claim["claim_sha256"]:
                raise RuntimeError("claim changed during ATTEMPT_STARTED; pending intent preserved for recovery")
            journal_events[:] = fresh
            prev = fresh[-1] if fresh else None
    journal_events.append(event)
    folded, _ = _fold_journal(state_root, journal_events)
    cleared = _build_derived_queue(folded, state_root_id, event)
    handle.verify_identity()
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(cleared), coordinator_id,
                   f"committed-{run_id}-{claim['attempt']}")
    handle.verify_identity()
    return intent_id


def _maintenance(handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                 folded: Dict[str, Dict[str, Any]], coordinator_id: str, run_id: str,
                 now: str, integration_context_by_packet: Optional[Mapping[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Seal terminal packets, then promote dependents, then requeue REVISE.

    The order is load-bearing, not stylistic: ``promote_dependencies`` reads
    each dependency's terminal seal to build its ``satisfied_by`` citation and
    defers silently when one is absent, so promotion before sealing is a
    guaranteed no-op -- the exact condition the accepted build reports as
    ``promotion_stalled``.

    The fold is only recomputed when something actually changed. A caller may
    legitimately supply state that no phase touches, and re-deriving it from an
    empty journal would silently discard it.
    """
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    sealed = complete_terminal_seals(state_root, journal_events, folded, now, handle=handle)
    if sealed:
        folded, _ = _fold_journal(state_root, journal_events)
    _publish_accepted_integrations(
        handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id,
        now, integration_context_by_packet)

    before = len(journal_events)
    # ``promote_dependencies`` is an accepted O3 primitive that operates by
    # pathname and is deliberately not duplicated. Root identity is verified
    # immediately before and after it, so a swap around the call halts the
    # iteration instead of being silently followed.
    handle.verify_identity()
    journal_events, promotion_attention = promote_dependencies(
        state_root, journal_path, lock_path, journal_events, folded,
        coordinator_id, run_id, state_root_id, now)
    handle.verify_identity()
    if len(journal_events) != before:
        folded, _ = _fold_journal(state_root, journal_events)

    before = len(journal_events)
    # ``requeue_revise`` is an accepted O3 primitive that writes the journal by
    # pathname, exactly like ``promote_dependencies`` above, and gets the same
    # immediate before/after identity guards.
    handle.verify_identity()
    journal_events, budget_exhausted = requeue_revise(
        journal_path, lock_path, journal_events, folded,
        coordinator_id, run_id, state_root_id, now)
    handle.verify_identity()
    if len(journal_events) != before:
        folded, _ = _fold_journal(state_root, journal_events)

    return journal_events, folded, {"sealed": sealed, "promotion_attention": promotion_attention,
                                    "revise_budget_exhausted": budget_exhausted}


def run_once(state_root: str, coordinator_id: str, run_id: str,
             trusted_process_context: Dict[str, Any], now: str,
             disabled_lanes: List[str] = None,
             worker_adapters: Optional[Mapping[str, WorkerAdapter]] = None,
             protected_worktree_path: Optional[str] = None,
             integration_context_by_packet: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Recover, resolve reviews, seal, promote, then claim at most one packet.

    Maintenance runs twice by design. The first pass completes work a previous
    interrupted run left behind (a verdict committed but never sealed, a sealed
    dependency whose dependents never promoted). The second pass seals and
    promotes whatever this iteration's own reviews just made terminal, so an
    ACCEPT and its dependents' promotion land in the same bounded iteration
    rather than waiting for the next one.
    """
    # One pinned state-root identity for the whole iteration. It is opened
    # BEFORE recovery -- which is accepted code operating by pathname -- and
    # re-verified immediately after, so a root renamed or replaced during
    # recovery halts before any P5C write rather than being written through.
    with open_state_root(state_root) as handle:
        report = run_started_recovery(state_root=state_root, coordinator_id=coordinator_id,
                                      run_id=run_id, trusted_process_context=trusted_process_context,
                                      now=now, handle=handle)
        try:
            handle.verify_identity()
            return _run_iteration(handle, state_root, report, coordinator_id, run_id,
                                  trusted_process_context, now, disabled_lanes,
                                  worker_adapters, protected_worktree_path,
                                  integration_context_by_packet)
        finally:
            report.release_singleton()


def _run_iteration(handle, state_root: str, report, coordinator_id: str, run_id: str,
                   trusted_process_context: Dict[str, Any], now: str,
                   disabled_lanes: List[str],
                   worker_adapters: Optional[Mapping[str, WorkerAdapter]],
                   protected_worktree_path: Optional[str],
                   integration_context_by_packet: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """One bounded iteration, every P5C artifact operation sharing one handle."""
    journal_events = getattr(report, "journal_events", [])
    state_root_id = getattr(report, "state_root_id", None)
    folded = report.derived_states
    adapters = worker_adapters or {}
    review_outcomes: List[Dict[str, Any]] = []
    review_attention: List[Dict[str, Any]] = []
    first = second = {"sealed": [], "promotion_attention": [], "revise_budget_exhausted": []}

    # Every durable phase is skipped without an identified state root. A
    # real RecoveryReport always carries one; a caller-supplied minimal
    # report models no durable state, and journaling an event stamped with
    # a null state_root_id would write a contract-invalid record that
    # read_journal would later refuse to load.
    if state_root_id is not None:
        provider_evidence = {}
        for packet_id, packet in folded.items():
            attempt = packet.get("open_attempt")
            if packet.get("state") != "RUNNING" or attempt is None:
                continue
            raw = handle.read(("results", packet_id, str(attempt), "provider_evidence.json"))
            if raw is not None:
                try:
                    provider_evidence[packet_id] = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # Per-packet classification will quarantine the claimed
                    # fallback as unconfirmed; malformed evidence must not
                    # abort independent work in the iteration.
                    continue
        registry_raw = handle.read(("trust", "provider_signals.json"))
        signal_registry = json.loads(registry_raw.decode("utf-8")) if registry_raw else None
        available_lanes = [lane for lane in ("kimi_implementation", "sonnet_implementation")
                           if lane not in (disabled_lanes or [])]
        for packet_id, packet in sorted(folded.items()):
            attempt = packet.get("open_attempt")
            if packet.get("state") != "RUNNING" or attempt is None:
                continue
            if handle.read(("results", packet_id, str(attempt), "attempt_outcome.json")) is not None:
                continue
            started = next((
                event for event in reversed(journal_events)
                if event.get("event_type") == "ATTEMPT_STARTED"
                and event.get("packet_id") == packet_id
                and (((event.get("payload") or {}).get("attempt") or {}).get("attempt") == attempt)
            ), None)
            if started is None:
                continue
            invocation_parts = ("invocations", started["intent_id"])
            receipt_present = (
                handle.read(invocation_parts + ("completion.json",)) is not None
                or handle.read(invocation_parts + ("completion.pending",)) is not None)
            sidecar_present = handle.read(invocation_parts + ("process.json",)) is not None
            adapter = adapters.get(packet_id) or adapters.get(packet.get("lane"))
            if receipt_present and adapter is None:
                raise RuntimeError(
                    f"completed invocation for {packet_id} requires its operator adapter to resume")
            if adapter is not None:
                packet_body = _load_enrolled_packet(
                    state_root, packet_id, packet, journal_events, handle=handle)
                invocation_packet = dict(packet_body)
                invocation_packet["attempt"] = attempt
                session_id = (((started.get("payload") or {}).get("attempt") or {})
                              .get("worker", {}).get("session_id"))
                baseline_was_journaled = any(
                    event.get("event_type") == "WORKSPACE_BASELINE_RECORDED"
                    and event.get("packet_id") == packet_id
                    and event.get("intent_id") == started["intent_id"]
                    for event in journal_events
                )
                _record_workspace_baseline(
                    handle, state_root, state_root_id, journal_events, folded,
                    packet_body, started["intent_id"], coordinator_id, run_id, now,
                    protected_worktree_path,
                    revalidate=not (baseline_was_journaled and (receipt_present or sidecar_present)))
                baseline_exists = True
                completed = load_completed_invocation(
                    handle, state_root_id, invocation_packet, started["intent_id"],
                    session_id, adapter)
                if completed is not None:
                    postflight = _record_workspace_postflight(
                        handle, state_root, state_root_id, journal_events, invocation_packet,
                        started["intent_id"], completed.result, started["coordinator_id"],
                        started["run_id"], now)
                    persist_invocation_outcome(
                        handle, invocation_packet, started["intent_id"], completed,
                        adapter, started["coordinator_id"], started["run_id"], now, postflight)
                elif (not baseline_was_journaled
                      and baseline_exists
                      and not receipt_present
                      and not sidecar_present):
                    invocation = invoke_worker(
                        state_root, state_root_id, invocation_packet, started["intent_id"],
                        session_id, adapter, allowed_worktree=packet_body["worktree"]["path"])
                    postflight = _record_workspace_postflight(
                        handle, state_root, state_root_id, journal_events, invocation_packet,
                        started["intent_id"], invocation.result, started["coordinator_id"],
                        started["run_id"], now)
                    persist_invocation_outcome(
                        handle, invocation_packet, started["intent_id"], invocation,
                        adapter, started["coordinator_id"], started["run_id"], now, postflight)
            # A pre-worker crash resumes through this loop and may invoke the
            # worker here.  Re-read the durable receipt after that invocation;
            # the value captured before invocation is intentionally stale.
            # Treating it as current would try to terminate the already-dead,
            # successfully receipted process and strand the attempt.
            receipt_present_now = (
                handle.read(invocation_parts + ("completion.json",)) is not None
                or handle.read(invocation_parts + ("completion.pending",)) is not None)
            if (not receipt_present_now
                    and handle.read(invocation_parts + ("process.json",)) is not None):
                with handle.directory(("invocations", started["intent_id"])) as intent_fd:
                    dead = terminate_sidecar_process(
                        intent_fd, "process.json", state_root_id, packet_id, attempt,
                        started["intent_id"])
                if not dead:
                    raise RuntimeError(
                        f"cannot prove prior worker dead for {packet_id} attempt {attempt}")
        # A receipt/outcome recovered from a prior coordinator process may be
        # encountered before an operator adapter is available. Postflight is
        # still mandatory before the generic O3 resolver can journal a worker
        # result or transition the packet, so seal it from the durable result
        # artifact rather than depending on a reinvocation.
        for packet_id, packet in sorted(folded.items()):
            attempt = packet.get("open_attempt")
            if packet.get("state") != "RUNNING" or attempt is None:
                continue
            outcome_raw = handle.read(("results", packet_id, str(attempt), "attempt_outcome.json"))
            if outcome_raw is None:
                continue
            started = next((
                event for event in reversed(journal_events)
                if event.get("event_type") == "ATTEMPT_STARTED" and event.get("packet_id") == packet_id
                and (((event.get("payload") or {}).get("attempt") or {}).get("attempt") == attempt)
            ), None)
            if started is None:
                continue
            already_recorded = any(
                event.get("event_type") == "WORKSPACE_POSTFLIGHT_RECORDED"
                and event.get("packet_id") == packet_id and event.get("intent_id") == started["intent_id"]
                for event in journal_events)
            if already_recorded:
                continue
            packet_body = _load_enrolled_packet(
                state_root, packet_id, packet, journal_events, handle=handle)
            worker_result = None
            result_raw = handle.read(("results", packet_id, str(attempt), "worker-result.json"))
            if result_raw is not None:
                try:
                    candidate = json.loads(result_raw.decode("utf-8"))
                    if result_raw == canonical_bytes(candidate):
                        worker_result = candidate
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            _record_workspace_postflight(
                handle, state_root, state_root_id, journal_events, packet_body,
                started["intent_id"], worker_result, coordinator_id, run_id, now)
        before = len(journal_events)
        handle.verify_identity()
        journal_events, attempt_attention = resolve_open_attempts(
            state_root, os.path.join(state_root, "journal.ndjson"),
            os.path.join(state_root, "locks", "journal.wlock"), journal_events,
            folded, provider_evidence, signal_registry, coordinator_id, run_id,
            state_root_id, now, available_lanes=available_lanes, handle=handle)
        handle.verify_identity()
        review_attention.extend(attempt_attention)
        if len(journal_events) != before:
            folded, _ = _fold_journal(state_root, journal_events)

        journal_events, folded, first = _maintenance(
            handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id, now,
            integration_context_by_packet)

        before = len(journal_events)
        journal_events, review_outcomes, review_attention = resolve_pending_reviews(
            state_root, state_root_id, journal_events, folded, coordinator_id, run_id,
            trusted_process_context, now, handle=handle)
        if len(journal_events) != before:
            folded, _ = _fold_journal(state_root, journal_events)

        journal_events, folded, second = _maintenance(
            handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id, now,
            integration_context_by_packet)

    packet_id = select_next(folded, disabled_lanes or [], now)
    if packet_id is None:
        result = {"status": "no_eligible_work", "packet_id": None}
    else:
        intent_id = claim_and_start_attempt(state_root=state_root, state_root_id=state_root_id,
                                            journal_events=journal_events, packet_id=packet_id,
                                            packet=folded[packet_id], coordinator_id=coordinator_id,
                                            run_id=run_id, trusted_process_context=trusted_process_context,
                                            now=now, handle=handle)
        result = {"status": "claimed", "packet_id": packet_id, "intent_id": intent_id,
                  "reviews": review_outcomes, "review_attention": review_attention,
                  "sealed": first["sealed"] + second["sealed"],
                  "promotion_attention": first["promotion_attention"] + second["promotion_attention"],
                  "revise_budget_exhausted": first["revise_budget_exhausted"] + second["revise_budget_exhausted"]}
        adapter = adapters.get(packet_id) or adapters.get(folded[packet_id]["lane"])
        if adapter is not None:
            attempt = folded[packet_id].get("attempts_started", 0) + 1
            packet_body = _load_enrolled_packet(
                state_root, packet_id, folded[packet_id], journal_events, handle=handle)
            invocation_packet = dict(packet_body)
            invocation_packet["attempt"] = attempt
            session_id = attempt_session_id(run_id, packet_id, attempt)
            _record_workspace_baseline(
                handle, state_root, state_root_id, journal_events, folded, packet_body,
                intent_id, coordinator_id, run_id, now, protected_worktree_path)
            handle.verify_identity()
            invocation = invoke_worker(
                state_root, state_root_id, invocation_packet, intent_id, session_id,
                adapter, allowed_worktree=packet_body["worktree"]["path"])
            handle.verify_identity()
            postflight = _record_workspace_postflight(
                handle, state_root, state_root_id, journal_events, invocation_packet,
                intent_id, invocation.result, coordinator_id, run_id, now)
            persist_invocation_outcome(
                handle, invocation_packet, intent_id, invocation, adapter,
                coordinator_id, run_id, now, postflight)
            folded, _ = _fold_journal(state_root, journal_events)
            journal_events, attempt_attention = resolve_open_attempts(
                state_root, os.path.join(state_root, "journal.ndjson"),
                os.path.join(state_root, "locks", "journal.wlock"), journal_events,
                folded, {}, signal_registry, coordinator_id, run_id, state_root_id, now,
                available_lanes=available_lanes, handle=handle)
            review_attention.extend(attempt_attention)
            folded, _ = _fold_journal(state_root, journal_events)
            journal_events, folded, after_worker = _maintenance(
                handle, state_root, state_root_id, journal_events, folded,
                coordinator_id, run_id, now, integration_context_by_packet)
            result.update({
                "status": "completed_attempt",
                "reviews": review_outcomes,
                "review_attention": review_attention,
                "sealed": result["sealed"] + after_worker["sealed"],
                "promotion_attention": (result["promotion_attention"]
                                        + after_worker["promotion_attention"]),
                "revise_budget_exhausted": (result["revise_budget_exhausted"]
                                            + after_worker["revise_budget_exhausted"]),
            })

    if state_root_id is None or not os.path.exists(os.path.join(state_root, "MANIFEST.json")):
        return result
    report_id = f"reconciliation-{compute_sha256(run_id.encode('utf-8'))[:32]}"
    handle.verify_identity()
    report = build_reconciliation_report(
        state_root, state_root_id, coordinator_id, run_id, report_id, now,
        handle=handle)
    handle.verify_identity()
    journal_events = emit_reconciliation_report(
        state_root, os.path.join(state_root, "journal.ndjson"),
        os.path.join(state_root, "locks", "journal.wlock"), journal_events,
        report, coordinator_id, run_id, state_root_id, now, handle=handle)
    result["reconciliation"] = {
        "report_id": report_id, "report_sha256": report["report_sha256"],
        "content_sha256": report["content_sha256"],
        "all_invariants_passed": report["reconciliation"]["all_invariants_passed"],
        "attention_codes": sorted({item["code"] for item in report["attention_required"]}),
    }
    return result


__all__ = ["attempt_session_id", "claim_and_start_attempt", "claim_packet", "run_once"]
