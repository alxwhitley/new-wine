"""One bounded P5 coordinator selection/claim iteration (no invocation)."""

import json
import os
from typing import Any, Dict, List

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet
from harness_coordinator.v1.locks import create_claim, read_claim
from harness_coordinator.v1.paths import safe_state_path
from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal, _make_event, run_started_recovery
from harness_coordinator.v1.scheduler import select_next
from harness_coordinator.v1.store import JournalHeadMoved, atomic_replace, append_journal, read_journal


def attempt_session_id(run_id: str, packet_id: str, attempt: int) -> str:
    """Durable worker-session identity; P5B must consume this exact value."""
    return f"session-{run_id}-{packet_id}-{attempt}"


def _load_enrolled_packet(state_root: str, packet_id: str, packet: Dict[str, Any],
                          journal_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    enroll_event = next(e for e in journal_events if e.get("event_type") == "PACKET_ENROLLED" and e.get("packet_id") == packet_id)
    recorded = enroll_event["payload"]["packet"]
    expected_rel = f"packets/{packet_id}.json"
    if recorded.get("packet_path") != expected_rel:
        raise ValueError("enrolled packet path does not match canonical packet artifact")
    lexical_path = os.path.join(os.path.realpath(state_root), "packets", f"{packet_id}.json")
    if os.path.islink(lexical_path):
        raise ValueError("enrolled packet artifact is a symlink")
    path = safe_state_path(state_root, "packets", identifier=packet_id, identifier_suffix=".json")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        raw = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(fd)
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


def run_once(state_root: str, coordinator_id: str, run_id: str,
             trusted_process_context: Dict[str, Any], now: str,
             disabled_lanes: List[str] = None) -> Dict[str, Any]:
    """Recover, deterministically select, claim at most one packet, return."""
    report = run_started_recovery(state_root=state_root, coordinator_id=coordinator_id,
                                  run_id=run_id, trusted_process_context=trusted_process_context, now=now)
    try:
        packet_id = select_next(report.derived_states, disabled_lanes or [], now)
        if packet_id is None:
            return {"status": "no_eligible_work", "packet_id": None}
        intent_id = claim_and_start_attempt(state_root=state_root, state_root_id=report.state_root_id,
                                            journal_events=report.journal_events, packet_id=packet_id,
                                            packet=report.derived_states[packet_id], coordinator_id=coordinator_id,
                                            run_id=run_id, trusted_process_context=trusted_process_context, now=now)
        return {"status": "claimed", "packet_id": packet_id, "intent_id": intent_id}
    finally:
        report.release_singleton()


__all__ = ["attempt_session_id", "claim_and_start_attempt", "claim_packet", "run_once"]
