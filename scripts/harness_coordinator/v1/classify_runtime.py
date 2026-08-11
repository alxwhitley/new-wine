"""Runtime transition behaviors for the harness coordinator v1.

Implements the three pieces design section 3.5 explicitly deferred past
O3-P2's scope (steps 10-13), plus sections 2.3/2.4:

- ``resolve_open_attempts``    -- design 3.5 step 10 (a/b/c): every packet
  whose fold state is RUNNING gets its open attempt resolved from durable
  evidence alone.
- ``promote_dependencies``     -- design 2.4: dependency-driven
  BLOCKED -> READY promotion, evaluated from terminal seals, never state
  caches, reusing O2's ``validate_packet(packet, dependency_states=...)``
  as the sole decision-maker for whether dependencies are satisfied.
- ``requeue_revise``           -- design 2.3: REVISE -> READY is a separate,
  budget-checked STATE_TRANSITION, not an automatic same-commit promotion.

All three are pure over durable inputs plus an explicit ``now`` (D0.4) and
write through the same ``append_journal``/atomic-replace primitives O3-P2
built -- no parallel persistence path.

Known, disclosed gap: neither ``promote_dependencies`` nor
``requeue_revise`` implements design 3.4's full two-phase crash-safe write
order (a ``queue.json`` ``pending_intents`` entry with
``stage="promotion"``/``"revision_requeue"`` written BEFORE the journal
append, so a crash between the two is distinguishable and resolvable on
restart). Each STATE_TRANSITION this module writes DOES carry a real,
non-null, deterministic ``intent_id`` (so the write is contract-valid and
survives a normal read), but a crash strictly between generating that
intent_id and the journal append would currently leave no queue-side
record to recover from -- unlike every other intent-bearing write in this
build. This is a real, narrower gap than the "no intent_id at all" defect
it replaces, not a substitute for the full two-phase write; flagged for a
follow-up round, not silently treated as complete.

Known, disclosed gap (design 9.2 / O3-P4): ``resolve_open_attempts``'s
``infra_retry`` cause and ``requeue_revise``'s ``revision_requeued`` cause
are the actual producers of a reconciliation-invariant-I9 false positive
-- NOT ``promote_dependencies``'s ``dependencies_satisfied`` (a promoted
packet always has ``attempts_started == 0``, since the only edge into
``BLOCKED`` is enrollment, and I9 only applies at ``attempts_started >=
1``). A packet resting at rest in READY (after ``infra_retry``) or REVISE
(before ``revision_requeued`` fires) has consumed a retry/cycle the fold
already counts, but has not yet been re-claimed, so ``attempts_started``
has not yet incremented for that re-entry -- making I9's ``infra_retries_
used + revise_cycles_used + reassignment == attempts_started - 1`` read
false on an otherwise healthy night. Confirmed empirically: after a single
``infra_retry``, the fold shows ``attempts_started=1, infra_retries_
used=1``, so I9 evaluates ``1 == 0``. This is a design-9.2 semantics
question belonging to ``reconciliation.py`` (an already-ACCEPTED O3-P1
module this packet does not own) or to O3-P4 (which owns building the
reconciliation report that would actually surface it) -- not fixed here.
Confirmed non-corrupting: no data loss, no double-execution, and
``classify_runtime`` has no production caller yet.

Known, disclosed caller obligation: ``promote_dependencies`` defers
(rather than errors) when a fold-ACCEPTED dependency has no terminal seal
yet (design 3.5 step 13 creates missing seals AFTER step 12's promotion
pass runs). Because design 2.4's in-loop promotion trigger is
``VERDICT_RECORDED(ACCEPTED)`` -- already journaled before the crash this
defers around -- nothing else re-evaluates promotion for the rest of a
run once step 12 has passed once. A future O3-P4 coordinator loop MUST
either create seals before step 12 runs, or re-run ``promote_dependencies``
again after step 13 creates them, or a dependent can stay silently BLOCKED
for an entire otherwise-healthy night with no attention entry to explain
why.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from harness_contracts.v1.canonical import compute_sha256
from harness_contracts.v1.classification import classify_attempt, validate_attempt_outcome
from harness_contracts.v1.journal import CAUSE_EDGES
from harness_contracts.v1.packet import validate_packet
from harness_contracts.v1.seal import validate_terminal_seal

from harness_coordinator.v1.recovery import IntegrityError, _last_seq, _make_event
from harness_coordinator.v1.locks import complete_claim_at
from harness_coordinator.v1.paths import safe_state_path
from harness_coordinator.v1.reassignment_runtime import (
    ReassignmentConflict,
    build_reassignment_record,
    load_and_validate_attempt_evidence,
    publish_reassignment,
)
from harness_coordinator.v1.store import append_journal


def _edge_for_running_cause(cause: str) -> Tuple[str, str]:
    """Resolve (from_state, to_state) for a RUNNING-origin cause via the
    authoritative CAUSE_EDGES table (O3-P1) -- never a parallel mapping.
    Every cause this module ever produces for an open-RUNNING-attempt
    resolution has exactly one edge whose from_state is RUNNING."""
    for from_state, to_state in CAUSE_EDGES.get(cause, set()):
        if from_state == "RUNNING":
            return from_state, to_state
    raise IntegrityError("INVALID_TRANSITION", f"No RUNNING-origin edge for cause '{cause}'")


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    """Read and parse a JSON file. Raises IntegrityError (never a raw
    json.JSONDecodeError) on unparseable content, so callers that need to
    distinguish 'absent' from 'corrupt' can do so and every caller that
    treats corruption as fatal gets a typed, catchable exception."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrityError("INVALID_JSON", f"{path} is not valid JSON: {exc}")


def _read_channel_bytes(state_root: str, outcome_record: Dict[str, Any]) -> Tuple[Optional[bytes], Optional[bytes]]:
    """Read the coordinator-captured stdout/stderr bytes an attempt_outcome
    record names, for classify_attempt's Guard 1 verbatim-excerpt check.
    Design 6.1: the coordinator captures these itself; classify_attempt
    must never be asked to trust a worker's own claim without them."""
    def _read(rel_path: Optional[str]) -> Optional[bytes]:
        if not rel_path:
            return None
        full = os.path.join(state_root, rel_path)
        if not os.path.exists(full):
            return None
        with open(full, "rb") as f:
            return f.read()

    stdout_bytes = _read((outcome_record.get("stdout") or {}).get("path"))
    stderr_bytes = _read((outcome_record.get("stderr") or {}).get("path"))
    return stdout_bytes, stderr_bytes


def _resolve_reassignment_cause(pkt: Dict[str, Any]) -> str:
    """Design section 7.4's action table, minus the artifact-preservation
    barriers (reassignment record creation / assert_preserved) -- those
    are a genuinely separate, not-yet-built piece of section 7 and are
    flagged as remaining work, not silently approximated here. This
    resolves only which STATE the packet moves to and why; it does not
    write a reassignments/<packet_id>.json record. This is a bounded gap
    because the fold (recovery.py) already sets reassignment_used=True and
    flips the lane on provider_exhausted_reassignment from the journal
    alone, so a second reassignment attempt is still structurally refused
    by this same function's own `reassignment_used` check on replay --
    barrier 2 (the acyclic lane edge) holds independent of the record.
    """
    lane = pkt.get("lane")
    if lane == "sonnet_implementation":
        return "fallback_exhausted"
    if lane != "kimi_implementation":
        return "fallback_not_permitted"
    if not pkt.get("sonnet_reassignment_allowed") or pkt.get("reassignment_used"):
        return "fallback_not_permitted"
    retry_limit = pkt.get("retry_limit")
    attempts_started = pkt.get("attempts_started", 0)
    if not (isinstance(retry_limit, int) and not isinstance(retry_limit, bool)):
        # Unknown/malformed budget -- fail CLOSED, consistent with every
        # other budget guard in this build (scheduler.py's _is_eligible).
        return "fallback_not_permitted"
    if attempts_started >= retry_limit + 1:
        return "attempt_budget_exhausted"
    return "provider_exhausted_reassignment"


def _finish_attempt(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packet_id: str,
    intent_id: str,
    attempt: int,
    pkt: Dict[str, Any],
    started_worker: Dict[str, Any],
    outcome_record: Dict[str, Any],
    provider_evidence: Optional[Dict[str, Any]],
    signal_registry: Optional[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    handle=None,
    available_lanes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Classify (via O3-P1's classify_attempt, never reimplemented) and
    journal ATTEMPT_FINISHED with the correct edge/cause.

    Budget-checked before classification is even attempted: an INFRA
    class at the retry cap must quarantine, not requeue -- checked here
    so both the (a)/(b) durable-evidence path and case (c)'s synthetic
    "no evidence at all" path share one enforcement point (mirrors
    design 2.3's rationale for REVISE's single budget-check location).
    """
    retry_limit = pkt.get("retry_limit")
    attempts_started = pkt.get("attempts_started", 0)
    budget_known = isinstance(retry_limit, int) and not isinstance(retry_limit, bool)
    budget_exhausted = (not budget_known) or attempts_started >= retry_limit + 1

    stdout_bytes, stderr_bytes = _read_channel_bytes(state_root, outcome_record)
    classification = classify_attempt(
        outcome_record, {}, provider_evidence, signal_registry,
        stdout_bytes=stdout_bytes, stderr_bytes=stderr_bytes,
    )
    attempt_class = classification["attempt_class"]
    cause = classification["cause"]
    validated_worker_result = None
    if attempt_class == "PROVIDER_EXHAUSTED" and handle is not None:
        started_event = next(
            (event for event in reversed(journal_events)
             if event.get("event_type") == "ATTEMPT_STARTED"
             and event.get("packet_id") == packet_id
             and (((event.get("payload") or {}).get("attempt") or {}).get("attempt") == attempt)),
            None)
        origin_run = next(
            (event for event in reversed(journal_events)
             if event.get("event_type") == "RUN_STARTED"
             and started_event is not None
             and event.get("run_id") == started_event.get("run_id")),
            None)
        try:
            if started_event is None or origin_run is None:
                raise ReassignmentConflict("originating attempt/run evidence is missing")
            validated_worker_result, provider_evidence, stdout_bytes, stderr_bytes = (
                load_and_validate_attempt_evidence(
                    handle, packet_id, pkt["packet_sha256"], attempt,
                    outcome_record, started_event, origin_run))
            classification = classify_attempt(
                outcome_record, {}, provider_evidence, signal_registry,
                stdout_bytes=stdout_bytes, stderr_bytes=stderr_bytes)
            attempt_class = classification["attempt_class"]
            cause = classification["cause"]
        except ReassignmentConflict:
            attempt_class = "CONTRACT_INVALID"
            cause = "exhaustion_unconfirmed"

    if attempt_class == "INFRA_RETRYABLE" and budget_exhausted:
        cause = "attempt_budget_exhausted"
    elif attempt_class == "PROVIDER_EXHAUSTED":
        cause = _resolve_reassignment_cause(pkt)
        if cause == "provider_exhausted_reassignment" and available_lanes is not None:
            if "sonnet_implementation" not in available_lanes:
                cause = "fallback_not_permitted"
    elif (
        attempt_class == "CONTRACT_INVALID"
        and outcome_record.get("outcome") == "CHECKPOINTED"
        and outcome_record.get("fallback") is not None
    ):
        # Design 6.3: the worker CLAIMED exhaustion (outcome=CHECKPOINTED
        # with a fallback object) but one of the four confirmation guards
        # failed -- classify_attempt's catch-all correctly falls through
        # to CONTRACT_INVALID, but design section 6.3/7.4 row 5 require
        # the more specific `exhaustion_unconfirmed` cause here, not a
        # generic contract-invalid label. This is the only place that
        # distinction can be made, since only this module sees both the
        # classification AND the raw claim.
        cause = "exhaustion_unconfirmed"
    from_state, to_state = _edge_for_running_cause(cause)

    quarantine_reason = None
    human_required_reasons: List[str] = []
    if to_state == "QUARANTINED":
        quarantine_reason = cause
    elif to_state == "HUMAN_REQUIRED":
        human_required_reasons = [cause]

    result_sha256 = None
    raw_result = outcome_record.get("raw_result") or {}
    if raw_result.get("path"):
        result_sha256 = raw_result.get("sha256")

    reassignment_sha256 = None
    if cause == "provider_exhausted_reassignment" and handle is not None:
        if provider_evidence is None:
            raise ReassignmentConflict("confirmed fallback requires pinned provider evidence")
        raw_path = (outcome_record.get("raw_result") or {}).get("path")
        if not raw_path:
            raise ReassignmentConflict("confirmed fallback requires a worker result")
        worker_result = validated_worker_result
        if worker_result is None:
            raise ReassignmentConflict("fallback worker result was not authenticated")
        # The range's last digest binds the global journal head immediately
        # before ATTEMPT_FINISHED; filtering to packet-local events would
        # permit intervening durable work to be omitted from preservation.
        packet_events = journal_events
        evidence_path = f"results/{packet_id}/{attempt}/provider_evidence.json"
        outcome_path = f"results/{packet_id}/{attempt}/attempt_outcome.json"
        record = build_reassignment_record(
            pkt, worker_result, provider_evidence, outcome_record, packet_events,
            next_event_seq=_last_seq(journal_events) + 1, now=now, attempt=attempt,
            paths={"worker_result": raw_path, "provider_evidence": evidence_path,
                   "attempt_outcome": outcome_path},
        )
        reassignment_sha256, _ = publish_reassignment(handle, record)

    event = _make_event(
        seq=(_last_seq(journal_events) + 1),
        event_type="ATTEMPT_FINISHED",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=journal_events[-1] if journal_events else None,
        event_at=now,
        packet_id=packet_id,
        intent_id=intent_id,
        from_state=from_state,
        to_state=to_state,
        cause=cause,
        payload={
            "packet": None,
            "attempt": {
                "attempt": attempt,
                "lane": pkt.get("lane"),
                "worker": started_worker,
                "claim_sha256": None,
                "worktree_path": None,
            },
            "artifacts": [],
            "classification": {
                "attempt_class": attempt_class,
                "quarantine_reason": quarantine_reason,
                "human_required_reasons": human_required_reasons,
                "result_sha256": result_sha256,
                "provider_evidence_sha256": outcome_record.get("provider_evidence_sha256"),
                "reassignment_record_sha256": reassignment_sha256,
                "outcome_summary": {
                    "exit_code": (outcome_record.get("invocation") or {}).get("exit_code"),
                    "signal": (outcome_record.get("invocation") or {}).get("signal"),
                    "timed_out": bool((outcome_record.get("invocation") or {}).get("timed_out")),
                    "result_present": bool((outcome_record.get("result_validation") or {}).get("present")),
                    "result_valid": bool((outcome_record.get("result_validation") or {}).get("valid")),
                    "error_codes": classification.get("error_codes") or [],
                },
            },
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": None,
        },
    )
    append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
    journal_events.append(event)
    return journal_events


_UNKNOWN_WORKER = {"worker_id": "unknown", "session_id": "unknown", "provider": "unknown", "model": "unknown"}


def resolve_open_attempts(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packets: Dict[str, Dict[str, Any]],
    provider_evidence_by_packet: Optional[Dict[str, Dict[str, Any]]],
    signal_registry: Optional[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    available_lanes: Optional[List[str]] = None,
    handle=None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Design 3.5 step 10: resolve every packet whose fold state is
    RUNNING, using exactly the durable evidence the design names.

    - (a) WORKER_RESULT_RECORDED already journaled for the open attempt ->
      classify from the recorded outcome, journal ATTEMPT_FINISHED.
    - (b) No WORKER_RESULT_RECORDED, but attempt_outcome.json exists and
      validates -> journal WORKER_RESULT_RECORDED (ingesting the result
      the worker/coordinator captured before a crash), then classify and
      journal ATTEMPT_FINISHED. This is the concrete mechanism behind "a
      worker that finished before the coordinator died still has its
      work ingested."
    - (c) No attempt_outcome.json at all -> the worker was still running
      or the coordinator died before capture -> INFRA_RETRYABLE (or
      QUARANTINED if the retry budget is already exhausted),
      RUNNING -> READY/QUARANTINED.

    Idempotent under repeated invocation: before doing anything for a
    RUNNING packet, checks whether an ATTEMPT_FINISHED already exists in
    the journal for this exact intent_id and skips if so -- the journal
    itself is the idempotency key, not the caller-supplied ``packets``
    dict, matching design 3.5's "every one is keyed by an
    intent_id/attempt/seq that is checked against the journal first."

    Iterates packet_ids in sorted order so behavior is deterministic
    across repeated invocations over the same durable state.

    Per-packet isolation: a genuine evidence/integrity contradiction for
    ONE packet (missing artifact behind a journaled claim, a
    contract-invalid attempt_outcome.json) is not one of design section
    2.6's three named run-halting conditions, so it must not abort
    resolution for every OTHER RUNNING packet. Each packet's resolution
    is attempted independently; a raised IntegrityError is caught,
    recorded in the returned ``attention`` list (packet_id, code,
    message), and the loop continues. The run-halting conditions
    themselves (broken chain, seal mismatch, state-root mismatch) are
    detected upstream by read_journal/the fold, never by this function.

    Returns ``(journal_events, attention)``.
    """
    provider_evidence_by_packet = provider_evidence_by_packet or {}
    attention: List[Dict[str, Any]] = []
    for packet_id in sorted(packets.keys()):
        try:
            journal_events = _resolve_one_open_attempt(
                state_root, journal_path, lock_path, journal_events, packet_id, packets,
                provider_evidence_by_packet, signal_registry, coordinator_id, run_id, state_root_id, now,
                available_lanes, handle,
            )
            if handle is not None:
                finished = next((
                    event for event in reversed(journal_events)
                    if event.get("event_type") == "ATTEMPT_FINISHED"
                    and event.get("packet_id") == packet_id
                ), None)
                if finished is not None:
                    complete_claim_at(
                        handle, packet_id, finished.get("intent_id"), run_id)
        except IntegrityError as exc:
            attention.append({"packet_id": packet_id, "code": exc.code, "message": exc.message})
    return journal_events, attention


def _resolve_one_open_attempt(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packet_id: str,
    packets: Dict[str, Dict[str, Any]],
    provider_evidence_by_packet: Dict[str, Dict[str, Any]],
    signal_registry: Optional[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    available_lanes: Optional[List[str]] = None,
    handle=None,
) -> List[Dict[str, Any]]:
    pkt = packets[packet_id]
    if pkt.get("state") != "RUNNING":
        return journal_events
    attempt = pkt.get("open_attempt")
    if attempt is None:
        return journal_events

    intent_id = None
    started_worker = _UNKNOWN_WORKER
    for e in journal_events:
        if (
            e.get("event_type") == "ATTEMPT_STARTED"
            and e.get("packet_id") == packet_id
            and ((e.get("payload") or {}).get("attempt") or {}).get("attempt") == attempt
        ):
            intent_id = e.get("intent_id")
            started_worker = ((e.get("payload") or {}).get("attempt") or {}).get("worker") or _UNKNOWN_WORKER
    if intent_id is None:
        # Structurally shouldn't happen against a fold-validated
        # journal; nothing durable identifies this attempt to resolve.
        return journal_events

    already_finished = any(
        e.get("event_type") == "ATTEMPT_FINISHED" and e.get("intent_id") == intent_id
        for e in journal_events
    )
    if already_finished:
        # Idempotency: a prior invocation (in this pass or an earlier
        # one) already resolved this exact attempt. The caller's
        # `packets` snapshot may be stale relative to journal_events
        # (e.g. two calls in the same process without an intervening
        # re-fold) -- the journal, not the snapshot, is authoritative.
        return journal_events

    has_result_recorded = any(
        e.get("event_type") == "WORKER_RESULT_RECORDED" and e.get("intent_id") == intent_id
        for e in journal_events
    )
    outcome_path = safe_state_path(
        state_root,
        "results",
        identifier=packet_id,
        suffix=os.path.join(str(attempt), "attempt_outcome.json"),
    )
    provider_evidence = provider_evidence_by_packet.get(packet_id)

    if has_result_recorded:
        outcome_record = _read_json(outcome_path)
        if outcome_record is None:
            # Journaled as recorded but the on-disk artifact is gone --
            # a preserved-evidence integrity problem, not this
            # function's to silently paper over.
            raise IntegrityError("EVIDENCE_MISSING", f"WORKER_RESULT_RECORDED journaled for {packet_id} attempt {attempt} but attempt_outcome.json is missing")
        journal_events = _finish_attempt(
            state_root, journal_path, lock_path, journal_events, packet_id, intent_id, attempt, pkt, started_worker,
            outcome_record, provider_evidence, signal_registry, coordinator_id, run_id, state_root_id, now,
            handle, available_lanes,
        )
        return journal_events

    outcome_record = _read_json(outcome_path)
    if outcome_record is not None:
        outcome_validation = validate_attempt_outcome(outcome_record)
        if not outcome_validation["valid"]:
            raise IntegrityError("INVALID_VALUE", f"attempt_outcome.json for {packet_id} attempt {attempt} is contract-invalid: {outcome_validation['errors'][0]['message']}")
        # Design 3.5(b): journal WORKER_RESULT_RECORDED only "if
        # valid" -- the attempt_outcome.json record itself parsing
        # and matching its own schema (outcome_validation, above) is
        # a DIFFERENT check from whether the raw worker result it
        # describes was itself contract-valid
        # (outcome_record.result_validation.valid). Only the second
        # is what "if valid" refers to; recording WORKER_RESULT_RECORDED
        # for a result the contract rejected would durably assert a
        # result was recorded that never actually was.
        raw_result_valid = bool((outcome_record.get("result_validation") or {}).get("valid"))
        if raw_result_valid:
            artifacts = []
            canonical_result_path = f"results/{packet_id}/{attempt}/worker-result.json"
            if (outcome_record.get("raw_result") or {}).get("path") == canonical_result_path:
                raw_worker_result = (handle.read(tuple(canonical_result_path.split("/")))
                                     if handle is not None else None)
                if raw_worker_result is None:
                    raise IntegrityError(
                        "EVIDENCE_MISSING",
                        f"valid result for {packet_id} attempt {attempt} is missing")
                artifacts = [{
                    "kind": "worker_result",
                    "artifact_id": f"worker-result-{packet_id}-{attempt}",
                    "path": canonical_result_path,
                    "sha256": compute_sha256(raw_worker_result),
                    "byte_length": len(raw_worker_result),
                }]
            wr_event = _make_event(
                seq=(_last_seq(journal_events) + 1),
                event_type="WORKER_RESULT_RECORDED",
                coordinator_id=coordinator_id,
                run_id=run_id,
                state_root_id=state_root_id,
                prev_event=journal_events[-1] if journal_events else None,
                event_at=now,
                packet_id=packet_id,
                intent_id=intent_id,
                payload={
                    "packet": None,
                    "attempt": {
                        "attempt": attempt,
                        "lane": pkt.get("lane"),
                        "worker": started_worker,
                        "claim_sha256": None,
                        "worktree_path": None,
                    },
                    "artifacts": artifacts,
                    "classification": None,
                    "transition_detail": None,
                    "recovery": None,
                    "run": None,
                    "report": None,
                },
            )
            append_journal(journal_path, wr_event, lock_path, expected_head=journal_events[-1] if journal_events else None)
            journal_events.append(wr_event)

        journal_events = _finish_attempt(
            state_root, journal_path, lock_path, journal_events, packet_id, intent_id, attempt, pkt, started_worker,
            outcome_record, provider_evidence, signal_registry, coordinator_id, run_id, state_root_id, now,
            handle, available_lanes,
        )
        return journal_events

    # Case (c): no outcome captured at all. Still budget-checked --
    # design 5.3/5.4/fixture D19: at the retry cap, a re-entry
    # attempt quarantines rather than requeuing indefinitely.
    retry_limit = pkt.get("retry_limit")
    attempts_started = pkt.get("attempts_started", 0)
    budget_known = isinstance(retry_limit, int) and not isinstance(retry_limit, bool)
    budget_exhausted = (not budget_known) or attempts_started >= retry_limit + 1
    cause = "attempt_budget_exhausted" if budget_exhausted else "infra_retry"
    from_state, to_state = _edge_for_running_cause(cause)
    quarantine_reason = cause if to_state == "QUARANTINED" else None

    event = _make_event(
        seq=(_last_seq(journal_events) + 1),
        event_type="ATTEMPT_FINISHED",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=journal_events[-1] if journal_events else None,
        event_at=now,
        packet_id=packet_id,
        intent_id=intent_id,
        from_state=from_state,
        to_state=to_state,
        cause=cause,
        payload={
            "packet": None,
            "attempt": {
                "attempt": attempt,
                "lane": pkt.get("lane"),
                "worker": started_worker,
                "claim_sha256": None,
                "worktree_path": None,
            },
            "artifacts": [],
            "classification": {
                "attempt_class": "INFRA_RETRYABLE",
                "quarantine_reason": quarantine_reason,
                "human_required_reasons": [],
                "result_sha256": None,
                "provider_evidence_sha256": None,
                "reassignment_record_sha256": None,
                "outcome_summary": {
                    "exit_code": None,
                    "signal": None,
                    "timed_out": False,
                    "result_present": False,
                    "result_valid": False,
                    "error_codes": [],
                },
            },
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": None,
        },
    )
    append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
    journal_events.append(event)
    return journal_events


def promote_dependencies(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packets: Dict[str, Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Design 2.4: promote every BLOCKED packet whose dependencies are ALL
    ACCEPTED.

    O2's ``validate_packet(packet, dependency_states=...)`` is the SOLE
    decision-maker for whether dependencies are satisfied (D0.6: never a
    parallel filter that pre-decides the answer and calls validate_packet
    only when it must already succeed). ``dependency_states`` is built
    from the fold's own state for every dependency the packet names (a
    dependency absent from the fold entirely -- never enrolled -- is
    correctly omitted, so O2 itself returns UNKNOWN_DEPENDENCY for it);
    ``validate_packet`` is called exactly once per candidate packet and
    its result is the entire gate.

    Only once validate_packet has confirmed every dependency is ACCEPTED
    does this function separately read each dependency's terminal seal
    file to build the auditable ``satisfied_by`` citation. Design 3.5
    orders step 12 (dependency promotion, this function) BEFORE step 13
    ("create any missing terminal seals") -- so a fold-ACCEPTED
    dependency with NO seal file yet is the ordinary, benign shape of a
    coordinator caught between VERDICT_RECORDED(ACCEPTED) and seal
    creation (crash point 3's own recovery note: "re-create the terminal
    seal if the committing event was terminal"). That case is NOT an
    error: promotion is simply deferred to a later pass, quietly, with no
    attention entry -- it will succeed once the seal exists. A seal that
    DOES exist but disagrees with the fold-ACCEPTED state it was just
    confirmed against, however, is exactly one of design section 2.6's
    three named run-halting conditions ("terminal-seal mismatch") and is
    deliberately NOT caught by this function's per-packet isolation --
    see below.

    Packet bodies are read from ``<state_root>/<packet_path>``, where
    ``packet_path`` is the repo-relative path recorded in the packet's own
    PACKET_ENROLLED payload (interpreted relative to the state root for
    this repo-only harness, consistent with every other artifact path
    design section 1.0 defines -- e.g. ``results/<id>/...`` -- which are
    all state-root-relative; a future enrollment writer that places
    packet bodies elsewhere must keep this interpretation in sync). A
    missing enroll event or unreadable/absent packet body is a genuine
    integrity contradiction for a packet the fold already knows about,
    and raises rather than silently stalling.

    Iterates BLOCKED packet_ids in sorted order for deterministic
    evaluation order across repeated invocations (design's "deterministic
    dependency evaluation").

    Idempotent under repeated invocation: each promotion's intent_id is
    deterministic (``f"promotion-{packet_id}"``, unique per packet
    lifetime -- a packet enters BLOCKED at most once, at enrollment, and
    never returns to it), so a prior promotion for this packet already in
    the journal is detected and skipped, exactly like
    ``resolve_open_attempts``'s idempotency key.

    Per-packet isolation: a genuine integrity contradiction confined to
    ONE BLOCKED packet (missing enroll event, unreadable packet body) is
    not one of design section 2.6's three named run-halting conditions,
    so it must not block promotion for every OTHER independent BLOCKED
    packet -- caught and collected into the returned ``attention`` list
    (``[{packet_id, code, message}, ...]``). A genuine terminal-seal
    DISAGREEMENT (as opposed to a not-yet-created seal, the benign case
    above) IS one of those three named conditions and is deliberately
    NOT caught here -- it propagates uncaught, exactly like
    ``_fold_journal``'s own equivalent check in ``recovery.py``, since a
    tampered/contradictory seal is a whole-state-root integrity failure,
    not a single packet's problem.

    Known, disclosed gap: writes a STATE_TRANSITION with a deterministic,
    non-null ``intent_id`` (``f"promotion-{packet_id}"``), but does not
    implement design 3.4's full two-phase queue.json pending-intent write
    before the journal append -- see the module docstring.

    Known, disclosed gap (design 9.2 / O3-P4): see the module docstring
    -- ``resolve_open_attempts``'s ``infra_retry`` and this module's own
    ``requeue_revise``'s ``revision_requeued`` are the actual producers
    of a reconciliation-I9 false positive, not ``dependencies_satisfied``
    (a promoted packet always has ``attempts_started == 0``, so it can
    never trip I9, which only applies at ``attempts_started >= 1``).
    """
    attention: List[Dict[str, Any]] = []
    for packet_id in sorted(packets.keys()):
        try:
            journal_events = _promote_one_dependency(
                state_root, journal_path, lock_path, journal_events, packet_id, packets,
                coordinator_id, run_id, state_root_id, now,
            )
        except IntegrityError as exc:
            if exc.code == "TERMINAL_SEAL_MISMATCH":
                # A genuine seal disagreement is a run-halting condition
                # (design 2.6), never packet-scoped -- propagate, do not
                # isolate. Only reachable for an EXISTING seal that
                # disagrees; a not-yet-created seal never raises (below).
                raise
            attention.append({"packet_id": packet_id, "code": exc.code, "message": exc.message})
    return journal_events, attention


def _promote_one_dependency(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packet_id: str,
    packets: Dict[str, Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
) -> List[Dict[str, Any]]:
    pkt = packets[packet_id]
    if pkt.get("state") != "BLOCKED":
        return journal_events
    deps = pkt.get("dependency_ids") or []
    if not deps:
        return journal_events

    intent_id = f"promotion-{packet_id}"
    already_promoted = any(
        e.get("event_type") == "STATE_TRANSITION" and e.get("intent_id") == intent_id
        for e in journal_events
    )
    if already_promoted:
        return journal_events

    dependency_states: Dict[str, str] = {}
    for dep_id in deps:
        dep_pkt = packets.get(dep_id)
        if dep_pkt is not None:
            dependency_states[dep_id] = dep_pkt.get("state")

    enroll_event = next(
        (e for e in journal_events if e.get("event_type") == "PACKET_ENROLLED" and e.get("packet_id") == packet_id),
        None,
    )
    if enroll_event is None:
        raise IntegrityError("INVALID_TRANSITION", f"Packet {packet_id} is BLOCKED in the fold but has no PACKET_ENROLLED event")
    packet_path_rel = ((enroll_event.get("payload") or {}).get("packet") or {}).get("packet_path")
    if not packet_path_rel:
        raise IntegrityError("MISSING_FIELD", f"Packet {packet_id}'s PACKET_ENROLLED payload has no packet_path")
    packet_body = _read_json(os.path.join(state_root, packet_path_rel))
    if packet_body is None:
        raise IntegrityError("EVIDENCE_MISSING", f"Packet body for {packet_id} not found at {packet_path_rel}")

    packet_result = validate_packet(packet_body, dependency_states=dependency_states)
    if not packet_result["valid"]:
        # O2's own decision: some dependency is UNKNOWN_DEPENDENCY or
        # DEPENDENCY_NOT_ACCEPTED (or the body fails independently) --
        # stays BLOCKED either way, no parallel judgment made here.
        return journal_events

    # validate_packet confirmed every dependency is ACCEPTED per the
    # fold; now read each dependency's real terminal seal for the
    # auditable satisfied_by citation.
    satisfied_by: List[Dict[str, Any]] = []
    for dep_id in deps:
        seal_path = safe_state_path(
            state_root,
            "state",
            "terminal",
            identifier=dep_id,
            identifier_suffix=".seal.json",
        )
        seal = _read_json(seal_path)
        if seal is None:
            # Benign: design 3.5 step 13 ("create any missing terminal
            # seals") runs AFTER step 12 (this promotion pass) -- a
            # fold-ACCEPTED dependency legitimately has no seal yet on a
            # normal pass. Defer this promotion quietly; it succeeds on
            # a later pass once the seal exists. NOT an integrity error.
            return journal_events
        seal_result = validate_terminal_seal(seal)
        if not seal_result["valid"] or seal.get("terminal_state") != "ACCEPTED":
            # A seal that EXISTS but disagrees with the fold it was just
            # confirmed ACCEPTED against is a genuine, whole-state-root
            # integrity contradiction -- one of design 2.6's three named
            # run-halting conditions. Deliberately NOT packet-isolated;
            # the caller (promote_dependencies) re-raises this specific
            # code rather than catching it into the attention list.
            raise IntegrityError("TERMINAL_SEAL_MISMATCH", f"Dependency {dep_id} of {packet_id}: terminal seal disagrees with fold-ACCEPTED state")
        upstream = seal.get("upstream_digests") or {}
        satisfied_by.append({
            "packet_id": dep_id,
            "verdict_sha256": upstream.get("verdict_sha256"),
            "seal_sha256": seal.get("seal_sha256"),
        })

    event = _make_event(
        seq=(_last_seq(journal_events) + 1),
        event_type="STATE_TRANSITION",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=journal_events[-1] if journal_events else None,
        event_at=now,
        packet_id=packet_id,
        intent_id=intent_id,
        from_state="BLOCKED",
        to_state="READY",
        cause="dependencies_satisfied",
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": {
                "satisfied_by": satisfied_by,
                "source_verdict": None,
                "revise_cycle": None,
            },
            "recovery": None,
            "run": None,
            "report": None,
        },
    )
    append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
    journal_events.append(event)
    return journal_events


def requeue_revise(
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    packets: Dict[str, Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Design 2.3: REVISE -> READY is a separate STATE_TRANSITION, not an
    automatic same-commit promotion, so REVISE stays observable at rest
    (the morning report's ``revise`` bucket) and the attempt-budget check
    happens in exactly one place.

    Returns ``(journal_events, budget_exhausted_packet_ids)`` -- the
    second list is every packet left resting in REVISE because its
    budget is gone (design: "there is no REVISE -> QUARANTINED edge... a
    packet whose budget is exhausted stays in REVISE and is flagged
    attempt_budget_exhausted", never auto-quarantined). An unknown/
    malformed retry_limit fails CLOSED (treated as exhausted), matching
    every other budget guard in this build (scheduler.py's _is_eligible).

    Idempotent under repeated invocation: the intent_id for a given
    packet's Nth requeue is deterministic (``f"revision-{packet_id}-N"``,
    derived from ``revise_cycles_used``), so a prior requeue for this
    exact cycle already in the journal is detected and skipped -- a
    caller invoking this twice against the same stale REVISE snapshot
    (revise_cycles_used unchanged between calls) cannot double-write.

    Known, disclosed gap: writes a STATE_TRANSITION with a deterministic,
    non-null ``intent_id`` (``f"revision-{packet_id}-{cycle}"``), but does
    not implement design 3.4's full two-phase queue.json pending-intent
    write before the journal append -- see the module docstring.
    """
    budget_exhausted: List[str] = []
    for packet_id in sorted(packets.keys()):
        pkt = packets[packet_id]
        if pkt.get("state") != "REVISE":
            continue

        retry_limit = pkt.get("retry_limit")
        attempts_started = pkt.get("attempts_started", 0)
        budget_known = isinstance(retry_limit, int) and not isinstance(retry_limit, bool)
        if (not budget_known) or attempts_started >= retry_limit + 1:
            budget_exhausted.append(packet_id)
            continue

        next_cycle = pkt.get("revise_cycles_used", 0) + 1
        intent_id = f"revision-{packet_id}-{next_cycle}"
        already_requeued = any(
            e.get("event_type") == "STATE_TRANSITION" and e.get("intent_id") == intent_id
            for e in journal_events
        )
        if already_requeued:
            continue

        event = _make_event(
            seq=(_last_seq(journal_events) + 1),
            event_type="STATE_TRANSITION",
            coordinator_id=coordinator_id,
            run_id=run_id,
            state_root_id=state_root_id,
            prev_event=journal_events[-1] if journal_events else None,
            event_at=now,
            packet_id=packet_id,
            intent_id=f"revision-{packet_id}-{next_cycle}",
            from_state="REVISE",
            to_state="READY",
            cause="revision_requeued",
            payload={
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": {
                    "satisfied_by": [],
                    "source_verdict": None,
                    "revise_cycle": next_cycle,
                },
                "recovery": None,
                "run": None,
                "report": None,
            },
        )
        append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
        journal_events.append(event)

    return journal_events, budget_exhausted
