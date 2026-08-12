"""One bounded P5 coordinator iteration: review, seal, promote, select, claim."""

import errno
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.execution_plan import HUMAN_STOP_CATEGORIES
from harness_contracts.v1.journal import validate_journal_event
from harness_contracts.v1.packet import validate_packet
from harness_contracts.v1.replay import validate_replay_bundle
from harness_contracts.v1.seal import TERMINAL_STATES
from harness_coordinator.v1.budget_runtime import budget_event_payload, evaluate_preclaim
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
from harness_coordinator.v1.recovery import (
    IntegrityError,
    _build_derived_queue,
    _fold_journal,
    _make_event,
    bound_execution_plan_for_run,
    graceful_stop_state,
    make_graceful_stop_effective,
    request_graceful_stop,
    run_started_recovery,
    wall_clock_ceiling_reached,
)
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
    ensure_attempt_baseline, load_attempt_baseline,
    publish_workspace_artifact, validate_postflight_binding,
)


def attempt_session_id(run_id: str, packet_id: str, attempt: int) -> str:
    """Durable worker-session identity; P5B must consume this exact value."""
    return f"session-{run_id}-{packet_id}-{attempt}"


def _plan_budgets_for(plan: Optional[Dict[str, Any]], packet_id: str) -> Optional[Dict[str, Any]]:
    """The authenticated plan's budgets for one member packet, if bound.

    ``None`` means no plan is bound to this run, in which case the invocation
    keeps its own defaults.  A bound plan that does not contain the packet is
    a plan-scope problem owned by the pre-claim gate, not something to paper
    over with a permissive default here.
    """
    if plan is None:
        return None
    for row in plan.get("packets", []):
        if row.get("packet_id") == packet_id:
            return row.get("budgets")
    return None


def _plan_packet_row(plan: Dict[str, Any], packet_id: str) -> Optional[Dict[str, Any]]:
    """The authenticated plan's own row for one member packet, if any."""
    for row in plan.get("packets", []):
        if row.get("packet_id") == packet_id:
            return row
    return None


def _plan_is_complete(plan: Dict[str, Any], folded: Dict[str, Dict[str, Any]]) -> bool:
    """Every plan member packet has reached a packet-level TERMINAL state.

    ``TERMINAL_STATES`` (``harness_contracts.v1.seal``) is
    ``{ACCEPTED, QUARANTINED, HUMAN_REQUIRED}`` -- the fold's only terminal
    states. A packet merely paused for provider capacity, or blocked on
    this task's own human-authority gate, stays READY in the fold: neither
    condition has (or should have) a dedicated ``PACKET_STATES`` value --
    see ``PACKET_PAUSED``'s own from_state/to_state-null journal contract --
    so it is deliberately NOT treated as complete here. It remains
    genuinely resumable and must go on being offered to selection on a
    later iteration once its condition clears; only Task 5's reconciliation
    is responsible for partitioning a "paused"/"blocked" packet into the
    run's final accounting, which is a different question from whether
    ``run_once`` may still claim new work.
    """
    for row in plan.get("packets", []):
        packet = folded.get(row.get("packet_id"))
        if packet is None or packet.get("state") not in TERMINAL_STATES:
            return False
    return True


def _human_authority_decision(packet_body: Dict[str, Any], packet_id: str) -> Optional[Dict[str, Any]]:
    """A packet-declared human-stop condition that matches the plan's closed
    ``human_stop_categories`` vocabulary gates unconditionally, before claim.

    Reasoned design call (flagged for review, see the report): the PLAN's
    own ``human_stop_categories`` field is a required up-front declaration
    of which categories a plan is expected to encounter (useful for
    governance/audit, Task 5's job) -- it is never read here as a filter
    that could narrow or waive which packet-level conditions actually gate.
    Only the packet's own ``human_stop_conditions`` is the operative
    claim-time signal, checked against the full closed 14-value enum
    directly. A ``human_stop_conditions`` entry that is not itself one of
    the 14 closed values (e.g. legacy pre-O5 free-form text such as
    ``"governed_doc_touched"``) does not trigger this gate -- only an exact
    closed-vocabulary match does. The returned shape deliberately matches
    ``budget_runtime.BUDGET_DECISION_KEYS`` exactly, so the caller treats it
    identically to an ``evaluate_preclaim`` result -- one decision shape,
    one persistence path (``_persist_budget_decision``), regardless of
    which check produced it.
    """
    conditions = packet_body.get("human_stop_conditions") or []
    triggered = sorted(set(conditions) & HUMAN_STOP_CATEGORIES)
    if not triggered:
        return None
    return {
        "decision": "HUMAN_REQUIRED", "reason_code": "HUMAN_AUTHORITY_REQUIRED",
        "packet_id": packet_id, "route": None, "next_eligible_at": None,
        "evidence_ids": [],
    }


_STATUS_BY_BUDGET_DECISION = {
    "PAUSE": "no_capable_model",
    "BACKOFF": "awaiting_provider_reset",
    "HUMAN_REQUIRED": "plan_stopped",
    "STOP": "plan_stopped",
}


def _status_for_budget_decision(decision: Dict[str, Any]) -> str:
    """The coordinator status for a non-claimable ``BudgetDecision``.

    ``ALLOW``/``FALLBACK`` are claimable and never reach this function.
    """
    return _STATUS_BY_BUDGET_DECISION.get(decision["decision"], "plan_stopped")


def _assigned_worker_override(
    packet_body: Dict[str, Any], route: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The ``assigned_worker`` shape a chosen plan route implies.

    Only ``provider``/``model`` are overridden -- ``worker_id`` is a worker
    INSTANCE label, not part of the plan's capability-class routing model
    (``select_capable_route``'s route shape has no such field), so the
    packet's own declared instance id is deliberately preserved. For every
    plan whose primary route already matches a packet's own pre-plan
    ``assigned_worker`` (true of every existing O5 fixture that predates
    Task 4), this is a value-for-value no-op.
    """
    if route is None:
        return None
    overridden = dict(packet_body.get("assigned_worker") or {})
    overridden["provider"] = route["provider"]
    overridden["model"] = route["model_id"]
    return overridden


def _record_model_fallback(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    plan: Dict[str, Any], packet_id: str, capability_class: str, decision: Dict[str, Any],
    coordinator_id: str, run_id: str, now: str,
) -> List[Dict[str, Any]]:
    """Durably record a fallback route choice. Written fresh on every claim
    that uses one -- a crash before the claim that follows simply produces
    another truthful record on retry, which the crash matrix names as an
    expected boundary ("during fallback selection"), not a defect."""
    route = decision["route"]
    primary = plan["routes"][capability_class][0]
    body = {
        "capability_class": capability_class,
        "from_route_id": primary["route_id"],
        "to_route_id": route["route_id"],
        "provider": route["provider"],
        "model_id": route["model_id"],
        "reason_code": decision["reason_code"],
    }
    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        (previous["seq"] + 1) if previous else 1, "MODEL_FALLBACK_SELECTED",
        coordinator_id, run_id, state_root_id, previous, now, packet_id=packet_id,
        payload=budget_event_payload("MODEL_FALLBACK_SELECTED", body))
    # Defense-in-depth, matching ``recovery._append_stop_event``'s pattern
    # exactly: never durably write an event this codebase's own validator
    # would refuse to read back. Without this, a contract-invalid write
    # (e.g. a null ``capability_class`` when the selected packet is out of
    # the bound plan's scope) succeeds silently and corrupts the journal
    # for good -- ``read_journal`` refuses to load it on every future call.
    result = validate_journal_event(event, prev_event=previous, state_root_id=state_root_id)
    if not result["valid"]:
        raise IntegrityError(
            "MODEL_FALLBACK_INVALID",
            "refusing to journal an invalid model fallback event: %s"
            % result["errors"][0]["message"], packet_id)
    handle.verify_identity()
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=previous)
    handle.verify_identity()
    journal_events.append(event)
    return journal_events


def _record_packet_pause(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    packet_id: str, capability_class: str, decision: Dict[str, Any],
    coordinator_id: str, run_id: str, now: str,
) -> List[Dict[str, Any]]:
    """Durably record why one packet could not be claimed this iteration.

    Covers every non-claimable ``BudgetDecision`` -- ``PAUSE``, ``BACKOFF``,
    a pre-claim plan/budget ``STOP``, and this task's own
    ``HUMAN_REQUIRED`` -- under the single closed event the schema actually
    offers for a packet-scoped, non-transitioning refusal
    (``PACKET_PAUSED``'s ``reason_code`` accepts the full
    ``CAPACITY_EVENT_REASON_CODES`` set, which includes every one of these).
    Deduplicated against the latest identical record for this packet, so a
    repeatedly-polled, still-blocked packet does not grow the journal
    without bound while nothing about its evidence has changed.
    """
    body = {
        "reason_code": decision["reason_code"],
        "capability_class": capability_class,
        "next_eligible_at": decision.get("next_eligible_at"),
        "evidence_ids": sorted(decision.get("evidence_ids") or []),
    }
    latest = None
    for event in journal_events:
        if event.get("event_type") == "PACKET_PAUSED" and event.get("packet_id") == packet_id:
            latest = event
    if latest is not None and (latest.get("payload") or {}).get("packet_pause") == body:
        return journal_events
    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        (previous["seq"] + 1) if previous else 1, "PACKET_PAUSED",
        coordinator_id, run_id, state_root_id, previous, now, packet_id=packet_id,
        payload=budget_event_payload("PACKET_PAUSED", body))
    # Defense-in-depth, matching ``recovery._append_stop_event``'s pattern
    # exactly: never durably write an event this codebase's own validator
    # would refuse to read back. Without this, a contract-invalid write
    # (e.g. a null ``capability_class`` when the selected packet is out of
    # the bound plan's scope) succeeds silently and corrupts the journal
    # for good -- ``read_journal`` refuses to load it on every future call.
    # The root cause (a plan-scope-outside packet ever reaching this
    # function at all) is closed separately, at selection
    # (``scheduler.select_next``'s ``plan`` parameter) -- this check is the
    # backstop for every other way a caller could reach here, not a
    # substitute for that fix.
    result = validate_journal_event(event, prev_event=previous, state_root_id=state_root_id)
    if not result["valid"]:
        raise IntegrityError(
            "PACKET_PAUSE_INVALID",
            "refusing to journal an invalid packet pause event: %s"
            % result["errors"][0]["message"], packet_id)
    handle.verify_identity()
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=previous)
    handle.verify_identity()
    journal_events.append(event)
    return journal_events


def _persist_budget_decision(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    plan: Dict[str, Any], packet_id: str, capability_class: str, decision: Dict[str, Any],
    coordinator_id: str, run_id: str, now: str,
) -> List[Dict[str, Any]]:
    """Persist step 6 of the pre-claim gate ordering: fallback, or a
    pause/backoff/stop/human-required refusal. ``ALLOW`` persists nothing
    here -- the chosen (primary) route is recorded on ATTEMPT_STARTED
    itself, not as a separate budget event."""
    kind = decision["decision"]
    if kind == "FALLBACK":
        return _record_model_fallback(
            handle, state_root, state_root_id, journal_events, plan, packet_id,
            capability_class, decision, coordinator_id, run_id, now)
    if kind in ("PAUSE", "BACKOFF", "STOP", "HUMAN_REQUIRED"):
        return _record_packet_pause(
            handle, state_root, state_root_id, journal_events, packet_id,
            capability_class, decision, coordinator_id, run_id, now)
    return journal_events


def _ceiling_evidence_ids(journal_events: List[Dict[str, Any]], run_id: str) -> List[str]:
    """Bounded identifiers for the events that fix this run's elapsed time.

    The run start and the plan binding are what the backstop was computed
    from, so they are what a later reader needs to recheck it. Identifiers
    only -- never timings, output, or any part of a command.
    """
    evidence: List[str] = []
    for event in journal_events:
        if event.get("run_id") != run_id:
            continue
        if event.get("event_type") in ("RUN_STARTED", "EXECUTION_PLAN_BOUND"):
            event_id = event.get("event_id")
            if isinstance(event_id, str) and event_id:
                evidence.append(event_id)
    return evidence


def _assert_no_graceful_stop(journal_events: List[Dict[str, Any]], run_id: str) -> None:
    """Refuse a claim once this run's stop is effective or already pending.

    Every pre-claim path passes through here, not only the iteration loop, so
    a direct caller cannot add the one extra claim a graceful stop exists to
    prevent.  ``pending`` counts: the stop was requested, the active attempt
    may finish, but nothing new may start.
    """
    state = graceful_stop_state(journal_events, run_id)
    if state["stopped"] or state["pending"]:
        raise IntegrityError(
            "GRACEFUL_STOP_IN_EFFECT",
            "run %s has a graceful stop %s; no further packet may be claimed"
            % (run_id, "in effect" if state["stopped"] else "pending"))


def _record_workspace_baseline(
    handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
    folded: Dict[str, Dict[str, Any]], packet: Dict[str, Any], intent_id: str,
    coordinator_id: str, run_id: str, now: str, protected_worktree_path: Optional[str],
    *, revalidate: bool = True,
) -> None:
    """Durably bind the immutable O4 baseline before a worker is invoked."""
    repo_root = packet.get("repository_root")
    if not isinstance(repo_root, str) or not repo_root:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_REPOSITORY",
            "Packet lacks an operator-provided repository root",
        )
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
                            handle=None, assigned_worker: Optional[Dict[str, str]] = None) -> str:
    """Durably perform lock -> pending intent -> ATTEMPT_STARTED -> projection.

    ``assigned_worker``, when supplied, overrides the enrolled packet's own
    declared ``assigned_worker`` for exactly this attempt's ATTEMPT_STARTED
    ``worker`` fields -- the O5 pre-claim gate's chosen plan route, so the
    durable claim record names the route that was actually decided, not a
    stale pre-plan default. ``None`` (every caller that predates this
    parameter, and every ungoverned/no-plan claim) preserves the exact prior
    behavior: the enrolled packet's own ``assigned_worker`` is used as-is.
    """
    if handle is None:
        with open_state_root(state_root) as scoped:
            return claim_and_start_attempt(
                state_root, state_root_id, journal_events, packet_id, packet,
                coordinator_id, run_id, trusted_process_context, now, handle=scoped,
                assigned_worker=assigned_worker)
    # Checked before the lock, the pending intent, and ATTEMPT_STARTED, so a
    # stopped run creates no durable claim artifact at all.
    _assert_no_graceful_stop(journal_events, run_id)
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

    assigned = assigned_worker if assigned_worker is not None else packet_body["assigned_worker"]
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
             integration_context_by_packet: Optional[Mapping[str, Any]] = None,
             execution_plan: Optional[Dict[str, Any]] = None,
             provider_state: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Recover, resolve reviews, seal, promote, then claim at most one packet.

    Maintenance runs twice by design. The first pass completes work a previous
    interrupted run left behind (a verdict committed but never sealed, a sealed
    dependency whose dependents never promoted). The second pass seals and
    promotes whatever this iteration's own reviews just made terminal, so an
    ACCEPT and its dependents' promotion land in the same bounded iteration
    rather than waiting for the next one.

    ``execution_plan`` is the validated plan this run is bound to. When it is
    omitted, an already-bound plan is authenticated from the journal instead;
    when neither exists, the iteration behaves exactly as before, with no
    plan-derived limits, no wall-clock backstop, and no pre-claim budget/
    routing/human-authority gate.

    ``provider_state`` is an optional, caller-supplied capacity snapshot
    passed straight through to ``evaluate_preclaim``/``select_capable_route``
    (Task 2) alongside the authenticated journal. Nothing in this build
    populates it from a live provider -- real provider commissioning is an
    explicit O5 non-goal -- so every caller today either omits it or supplies
    synthetic evidence directly; it exists so a future live-provider
    integration has a call-time input to fill without another coordinator
    signature change. Omitting it is equivalent to an empty snapshot: the
    durable, authenticated ``PROVIDER_CAPACITY_RECORDED`` journal trail is
    always consulted regardless.
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
                                  integration_context_by_packet, execution_plan,
                                  provider_state)
        finally:
            report.release_singleton()


def _run_iteration(handle, state_root: str, report, coordinator_id: str, run_id: str,
                   trusted_process_context: Dict[str, Any], now: str,
                   disabled_lanes: List[str],
                   worker_adapters: Optional[Mapping[str, WorkerAdapter]],
                   protected_worktree_path: Optional[str],
                   integration_context_by_packet: Optional[Mapping[str, Any]],
                   execution_plan: Optional[Dict[str, Any]] = None,
                   provider_state: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """One bounded iteration, every P5C artifact operation sharing one handle."""
    journal_events = getattr(report, "journal_events", [])
    state_root_id = getattr(report, "state_root_id", None)
    folded = report.derived_states
    adapters = worker_adapters or {}
    review_outcomes: List[Dict[str, Any]] = []
    review_attention: List[Dict[str, Any]] = []
    first = second = {"sealed": [], "promotion_attention": [], "revise_budget_exhausted": []}
    journal_path = os.path.join(state_root, "journal.ndjson")
    journal_lock_path = os.path.join(state_root, "locks", "journal.wlock")

    # The plan is resolved once, before anything is claimed or invoked. An
    # explicit argument wins; otherwise a plan already bound to this run is
    # authenticated from the journal, so its limits and its wall-clock
    # backstop apply on a restart even when the caller did not re-supply it.
    # A caller-supplied ``execution_plan`` never silently overrides a plan
    # already durably bound to this run: if one is bound, its identity is
    # cross-checked against the caller's argument and any disagreement fails
    # closed, matching the existing ``PLAN_IDENTITY_CONFLICT`` pattern
    # ``_fold_journal`` already raises for two conflicting bindings of the
    # same run. An unbound run (the common test/ungoverned-caller shape,
    # where ``execution_plan`` is supplied but never durably bound) has
    # nothing to conflict with, so this is a no-op for it.
    plan = execution_plan
    if state_root_id is not None:
        bound_plan = bound_execution_plan_for_run(state_root, journal_events, run_id)
        if plan is None:
            plan = bound_plan
        elif bound_plan is not None and bound_plan.get("plan_sha256") != plan.get("plan_sha256"):
            raise IntegrityError(
                "PLAN_IDENTITY_CONFLICT",
                "caller-supplied execution_plan disagrees with the plan already "
                "bound to run %s" % run_id)

    # A stop condition observed BEFORE the attempt-resolution block below is
    # recorded before that work runs: the design lets the active attempt reach
    # a durable outcome, but the decision to stop is what must survive a crash
    # in the middle of it. Making the stop EFFECTIVE waits until afterwards.
    stop = graceful_stop_state(journal_events, run_id)
    if state_root_id is not None and plan is not None and not (
            stop["stopped"] or stop["pending"]):
        if wall_clock_ceiling_reached(
                journal_events, run_id, plan["wall_clock_safety_seconds"], now):
            journal_events = request_graceful_stop(
                journal_path, journal_lock_path, journal_events, plan,
                coordinator_id, run_id, state_root_id, now,
                "QUEUE_SAFETY_CEILING_REACHED",
                _ceiling_evidence_ids(journal_events, run_id), handle=handle)
            stop = graceful_stop_state(journal_events, run_id)

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
                # ATTEMPT_STARTED's own durably-recorded ``worker`` is the
                # ground truth for what this specific attempt was actually
                # assigned -- whatever a prior iteration's pre-claim gate
                # decided (a fallback route or the packet's own default),
                # never the enrolled packet's own (possibly stale) default.
                # Without this, a resumed invocation after a pre-invoke
                # crash checks the worker RESULT's identity against the
                # packet's original assignment instead of the one actually
                # recorded at claim time, and a genuine fallback fails
                # ``RESULT_IDENTITY_MISMATCH`` even though the correct
                # worker ran.
                started_worker = (((started.get("payload") or {}).get("attempt") or {})
                                  .get("worker") or {})
                session_id = started_worker.get("session_id")
                if {"worker_id", "provider", "model"} <= set(started_worker):
                    invocation_packet["assigned_worker"] = {
                        "worker_id": started_worker["worker_id"],
                        "provider": started_worker["provider"],
                        "model": started_worker["model"],
                    }
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
                        session_id, adapter, allowed_worktree=packet_body["worktree"]["path"],
                        plan_budgets=_plan_budgets_for(plan, packet_id))
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
        # Extended, never rebound: attempt-level attention gathered above is
        # part of what this iteration must report.  Rebinding the name here
        # silently discarded it, so a packet whose evidence contradicted
        # itself -- the exact case resolve_open_attempts isolates rather than
        # aborting on -- came back to the caller as an empty list.
        journal_events, review_outcomes, pending_attention = resolve_pending_reviews(
            state_root, state_root_id, journal_events, folded, coordinator_id, run_id,
            trusted_process_context, now, handle=handle)
        review_attention.extend(pending_attention)
        if len(journal_events) != before:
            folded, _ = _fold_journal(state_root, journal_events)

        journal_events, folded, second = _maintenance(
            handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id, now,
            integration_context_by_packet)

        # The active attempt has now reached a durable outcome and its O4
        # postflight is recorded, so a requested stop may become effective.
        # A restart that found the stop already requested lands here too: it
        # completes recovery first, exactly as a fresh observation would, and
        # never assumes the condition has passed.
        stop = graceful_stop_state(journal_events, run_id)
        if stop["pending"] and not _any_attempt_open(folded):
            # ``plan`` is passed as a cross-check, not as the source of the
            # stop's plan identity -- that comes from the recorded request, so
            # this closes cleanly even on a restart that resolved no plan.
            journal_events = make_graceful_stop_effective(
                journal_path, journal_lock_path, journal_events,
                coordinator_id, run_id, state_root_id, now, plan=plan,
                handle=handle)
            stop = graceful_stop_state(journal_events, run_id)

    if stop["stopped"] or stop["pending"]:
        # Selection is skipped entirely rather than filtered: a graceful stop
        # must produce ZERO further ATTEMPT_STARTED events, and the surest way
        # to guarantee that is never to reach the claim path at all.
        return _finish_iteration(
            handle, state_root, state_root_id, journal_events, coordinator_id, run_id, now,
            {
                "status": "graceful_stopped" if stop["stopped"] else "graceful_stop_pending",
                "packet_id": None,
                "stop_reason_code": stop["reason_code"],
                "reviews": review_outcomes, "review_attention": review_attention,
                "sealed": first["sealed"] + second["sealed"],
                "promotion_attention": (
                    first["promotion_attention"] + second["promotion_attention"]),
                "revise_budget_exhausted": (
                    first["revise_budget_exhausted"] + second["revise_budget_exhausted"]),
            })

    # Step 4 of the pre-claim gate ordering: verify plan membership and
    # terminal partition. Every plan member has reached a packet-level
    # terminal state, so remaining provider capacity or newly-discoverable
    # work must not permit a new claim or new enrollment -- checked before
    # ``select_next`` runs at all, so a completed plan never even asks the
    # scheduler for a candidate.
    if plan is not None and _plan_is_complete(plan, folded):
        return _finish_iteration(
            handle, state_root, state_root_id, journal_events, coordinator_id, run_id, now,
            {
                "status": "plan_complete", "packet_id": None,
                "reviews": review_outcomes, "review_attention": review_attention,
                "sealed": first["sealed"] + second["sealed"],
                "promotion_attention": (
                    first["promotion_attention"] + second["promotion_attention"]),
                "revise_budget_exhausted": (
                    first["revise_budget_exhausted"] + second["revise_budget_exhausted"]),
            })

    packet_id = select_next(folded, disabled_lanes or [], now, plan=plan)
    waiting_for_adapter = False
    if packet_id is not None:
        selected_adapter = adapters.get(packet_id) or adapters.get(folded[packet_id]["lane"])
        if selected_adapter is None and folded[packet_id].get("packet_sha256") is not None:
            selected_packet = _load_enrolled_packet(
                state_root, packet_id, folded[packet_id], journal_events, handle=handle)
            waiting_for_adapter = bool(selected_packet.get("writable_paths"))

    # Steps 5-6 of the pre-claim gate ordering: evaluate the stop/budget/
    # provider/model decision for the one packet selection actually picked,
    # then persist whatever it implies (fallback, or a pause/backoff/stop/
    # human-required refusal). No adapter lookup, provider catalog response,
    # worker result, or cache participates in this decision -- it is derived
    # solely from the authenticated plan and journal (plus this task's own
    # human-authority read of the packet's OWN declared conditions).
    #
    # Scope note (flagged in the report): this evaluates only the packet
    # ``select_next`` already chose. It does not walk past a blocked
    # candidate to try a different eligible packet with unrelated capacity --
    # a deliberate, narrower scope than a full multi-candidate scheduler,
    # explained in the report.
    budget_decision: Optional[Dict[str, Any]] = None
    assigned_worker_override: Optional[Dict[str, str]] = None
    if packet_id is not None and not waiting_for_adapter and plan is not None:
        plan_packet_row = _plan_packet_row(plan, packet_id)
        gate_packet_body = _load_enrolled_packet(
            state_root, packet_id, folded[packet_id], journal_events, handle=handle)
        capability_class = plan_packet_row["capability_class"] if plan_packet_row else None
        budget_decision = _human_authority_decision(gate_packet_body, packet_id)
        if budget_decision is None:
            budget_decision = evaluate_preclaim(
                plan, folded[packet_id], journal_events, provider_state or {}, now)
        journal_events = _persist_budget_decision(
            handle, state_root, state_root_id, journal_events, plan, packet_id,
            capability_class, budget_decision, coordinator_id, run_id, now)
        if budget_decision["decision"] in ("ALLOW", "FALLBACK"):
            assigned_worker_override = _assigned_worker_override(
                gate_packet_body, budget_decision.get("route"))

    if waiting_for_adapter:
        # A nonempty writable allowlist is the compatibility-independent
        # boundary for workspace preflight. Without an adapter there is no
        # authorized invocation to guard, so preserve READY rather than
        # creating a durable claim/RUNNING attempt.
        result = {
            "status": "awaiting_worker_adapter", "packet_id": packet_id,
            "reviews": review_outcomes, "review_attention": review_attention,
            "sealed": first["sealed"] + second["sealed"],
            "promotion_attention": (
                first["promotion_attention"] + second["promotion_attention"]),
            "revise_budget_exhausted": (
                first["revise_budget_exhausted"] + second["revise_budget_exhausted"]),
        }
    elif budget_decision is not None and budget_decision["decision"] not in ("ALLOW", "FALLBACK"):
        # Steps 4-6 of the pre-claim gate ordering refused this claim: the
        # decision (and, for PAUSE/BACKOFF/STOP/HUMAN_REQUIRED, its
        # PACKET_PAUSED record) is already durably persisted above. The one
        # thing left to guarantee is that steps 7-9 (O4 preflight,
        # ATTEMPT_STARTED, invocation) never run for this packet on this
        # iteration -- selection is reported, not acted on.
        result = {
            "status": _status_for_budget_decision(budget_decision),
            "packet_id": packet_id,
            "stop_reason_code": budget_decision["reason_code"],
            "reviews": review_outcomes, "review_attention": review_attention,
            "sealed": first["sealed"] + second["sealed"],
            "promotion_attention": (
                first["promotion_attention"] + second["promotion_attention"]),
            "revise_budget_exhausted": (
                first["revise_budget_exhausted"] + second["revise_budget_exhausted"]),
        }
    elif packet_id is None:
        result = {"status": "no_eligible_work", "packet_id": None}
    else:
        adapter = adapters.get(packet_id) or adapters.get(folded[packet_id]["lane"])
        packet_body = None
        preflight_intent_id = None
        attempt = None
        if adapter is not None:
            # The O4 baseline is intentionally durable while the packet still
            # folds to READY.  A crash or refusal here therefore cannot strand
            # a RUNNING attempt without its pre-invocation evidence.
            attempt = folded[packet_id].get("attempts_started", 0) + 1
            preflight_intent_id = f"attempt-{packet_id}-{attempt}"
            packet_body = _load_enrolled_packet(
                state_root, packet_id, folded[packet_id], journal_events, handle=handle)
            _record_workspace_baseline(
                handle, state_root, state_root_id, journal_events, folded, packet_body,
                preflight_intent_id, coordinator_id, run_id, now, protected_worktree_path)
        intent_id = claim_and_start_attempt(state_root=state_root, state_root_id=state_root_id,
                                            journal_events=journal_events, packet_id=packet_id,
                                            packet=folded[packet_id], coordinator_id=coordinator_id,
                                            run_id=run_id, trusted_process_context=trusted_process_context,
                                            now=now, handle=handle,
                                            assigned_worker=assigned_worker_override)
        if preflight_intent_id is not None and intent_id != preflight_intent_id:
            raise RuntimeError("attempt identity changed after workspace preflight")
        result = {"status": "claimed", "packet_id": packet_id, "intent_id": intent_id,
                  "reviews": review_outcomes, "review_attention": review_attention,
                  "sealed": first["sealed"] + second["sealed"],
                  "promotion_attention": first["promotion_attention"] + second["promotion_attention"],
                  "revise_budget_exhausted": first["revise_budget_exhausted"] + second["revise_budget_exhausted"]}
        if adapter is not None:
            assert attempt is not None
            assert packet_body is not None
            invocation_packet = dict(packet_body)
            invocation_packet["attempt"] = attempt
            # The pre-claim gate's chosen route (if any) was already applied
            # to the durable ATTEMPT_STARTED record via ``claim_and_start_
            # attempt``'s own ``assigned_worker`` parameter above; it must
            # also apply here, to the packet actually handed to the worker,
            # or the journal and the invocation disagree on who was assigned
            # and ``invoke_worker``'s own result-identity check rejects a
            # genuine fallback as ``RESULT_IDENTITY_MISMATCH``.
            if assigned_worker_override is not None:
                invocation_packet["assigned_worker"] = assigned_worker_override
            session_id = attempt_session_id(run_id, packet_id, attempt)
            handle.verify_identity()
            invocation = invoke_worker(
                state_root, state_root_id, invocation_packet, intent_id, session_id,
                adapter, allowed_worktree=packet_body["worktree"]["path"],
                plan_budgets=_plan_budgets_for(plan, packet_id))
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

    return _finish_iteration(handle, state_root, state_root_id, journal_events,
                             coordinator_id, run_id, now, result)


def _any_attempt_open(folded: Dict[str, Dict[str, Any]]) -> bool:
    """Whether any packet still holds an unresolved attempt."""
    return any(packet.get("state") == "RUNNING" and packet.get("open_attempt") is not None
               for packet in folded.values())


def _finish_iteration(handle, state_root: str, state_root_id: Optional[str],
                      journal_events: List[Dict[str, Any]], coordinator_id: str,
                      run_id: str, now: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Publish this iteration's reconciliation report and return the result.

    Shared by every exit from the iteration, including the graceful-stop one:
    a stopped run still owes an accurate report of where its packets landed.
    """
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
