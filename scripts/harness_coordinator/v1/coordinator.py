"""One bounded P5 coordinator iteration: review, seal, promote, select, claim."""

import errno
import json
import os
from typing import Any, Dict, List, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet
from harness_coordinator.v1.classify_runtime import promote_dependencies, requeue_revise
from harness_coordinator.v1.locks import create_claim, read_claim
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id
from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal, _make_event, run_started_recovery
from harness_coordinator.v1.review import resolve_pending_reviews
from harness_coordinator.v1.scheduler import select_next
from harness_coordinator.v1.seals_runtime import complete_terminal_seals, open_state_root
from harness_coordinator.v1.store import JournalHeadMoved, atomic_replace, append_journal, read_journal


def attempt_session_id(run_id: str, packet_id: str, attempt: int) -> str:
    """Durable worker-session identity; P5B must consume this exact value."""
    return f"session-{run_id}-{packet_id}-{attempt}"


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
                 run_id: str, trusted_process_context: Dict[str, Any], now: str) -> Dict[str, Any]:
    """Create the intent-scoped O_EXCL claim for one selected packet."""
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
    lock_path = safe_state_path(state_root, "locks", identifier=packet_id, identifier_suffix=".lock.json")
    create_claim(lock_path, record)
    return record


def claim_and_start_attempt(state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                            packet_id: str, packet: Dict[str, Any], coordinator_id: str,
                            run_id: str, trusted_process_context: Dict[str, Any], now: str) -> str:
    """Durably perform lock -> pending intent -> ATTEMPT_STARTED -> projection."""
    packet_body = _load_enrolled_packet(state_root, packet_id, packet, journal_events)
    claim = claim_packet(state_root, packet_id, packet, coordinator_id, run_id, trusted_process_context, now)
    intent_id = claim["intent_id"]
    queue = _build_derived_queue(_fold_journal(state_root, journal_events)[0], state_root_id,
                                 journal_events[-1] if journal_events else None)
    queue["pending_intents"] = [{
        "intent_id": intent_id, "packet_id": packet_id, "stage": "claim", "created_at": now,
        "coordinator_id": coordinator_id, "run_id": run_id,
        "boot_id": trusted_process_context["boot_id"], "pid": trusted_process_context["pid"],
    }]
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(queue), coordinator_id,
                   f"pending-{run_id}-{claim['attempt']}")

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
            append_journal(journal_path, event, os.path.join(state_root, "locks", "journal.wlock"), expected_head=prev)
            break
        except JournalHeadMoved:
            moves += 1
            if moves >= 8:
                raise RuntimeError("ATTEMPT_STARTED journal head kept moving; pending intent preserved for recovery")
            fresh, torn = read_journal(journal_path, state_root_id=state_root_id)
            if torn is not None:
                raise RuntimeError("torn journal during ATTEMPT_STARTED; pending intent preserved for recovery")
            folded, _ = _fold_journal(state_root, fresh)
            current = folded.get(packet_id)
            lock_path = safe_state_path(state_root, "locks", identifier=packet_id, identifier_suffix=".lock.json")
            lock = read_claim(lock_path)
            if current is None or current.get("state") != "READY" or current.get("open_attempt") is not None:
                raise RuntimeError("packet no longer READY; pending intent preserved for recovery")
            if lock.get("intent_id") != intent_id or lock.get("claim_sha256") != claim["claim_sha256"]:
                raise RuntimeError("claim changed during ATTEMPT_STARTED; pending intent preserved for recovery")
            journal_events[:] = fresh
            prev = fresh[-1] if fresh else None
    journal_events.append(event)
    folded, _ = _fold_journal(state_root, journal_events)
    cleared = _build_derived_queue(folded, state_root_id, event)
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(cleared), coordinator_id,
                   f"committed-{run_id}-{claim['attempt']}")
    return intent_id


def _maintenance(handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                 folded: Dict[str, Dict[str, Any]], coordinator_id: str, run_id: str,
                 now: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Any]]:
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
             disabled_lanes: List[str] = None) -> Dict[str, Any]:
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
                                      run_id=run_id, trusted_process_context=trusted_process_context, now=now)
        try:
            handle.verify_identity()
            return _run_iteration(handle, state_root, report, coordinator_id, run_id,
                                  trusted_process_context, now, disabled_lanes)
        finally:
            report.release_singleton()


def _run_iteration(handle, state_root: str, report, coordinator_id: str, run_id: str,
                   trusted_process_context: Dict[str, Any], now: str,
                   disabled_lanes: List[str]) -> Dict[str, Any]:
    """One bounded iteration, every P5C artifact operation sharing one handle."""
    journal_events = getattr(report, "journal_events", [])
    state_root_id = getattr(report, "state_root_id", None)
    folded = report.derived_states
    review_outcomes: List[Dict[str, Any]] = []
    review_attention: List[Dict[str, Any]] = []
    first = second = {"sealed": [], "promotion_attention": [], "revise_budget_exhausted": []}

    # Every durable phase is skipped without an identified state root. A
    # real RecoveryReport always carries one; a caller-supplied minimal
    # report models no durable state, and journaling an event stamped with
    # a null state_root_id would write a contract-invalid record that
    # read_journal would later refuse to load.
    if state_root_id is not None:
        journal_events, folded, first = _maintenance(
            handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id, now)

        before = len(journal_events)
        journal_events, review_outcomes, review_attention = resolve_pending_reviews(
            state_root, state_root_id, journal_events, folded, coordinator_id, run_id,
            trusted_process_context, now, handle=handle)
        if len(journal_events) != before:
            folded, _ = _fold_journal(state_root, journal_events)

        journal_events, folded, second = _maintenance(
            handle, state_root, state_root_id, journal_events, folded, coordinator_id, run_id, now)

    packet_id = select_next(folded, disabled_lanes or [], now)
    if packet_id is None:
        return {"status": "no_eligible_work", "packet_id": None}
    intent_id = claim_and_start_attempt(state_root=state_root, state_root_id=state_root_id,
                                        journal_events=journal_events, packet_id=packet_id,
                                        packet=folded[packet_id], coordinator_id=coordinator_id,
                                        run_id=run_id, trusted_process_context=trusted_process_context, now=now)
    return {"status": "claimed", "packet_id": packet_id, "intent_id": intent_id,
            "reviews": review_outcomes, "review_attention": review_attention,
            "sealed": first["sealed"] + second["sealed"],
            "promotion_attention": first["promotion_attention"] + second["promotion_attention"],
            "revise_budget_exhausted": first["revise_budget_exhausted"] + second["revise_budget_exhausted"]}


__all__ = ["attempt_session_id", "claim_and_start_attempt", "claim_packet", "run_once"]
