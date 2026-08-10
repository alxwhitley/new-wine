"""Coordinator RUN_STARTED recovery for harness v1.

Implements design section 3.5 steps 1 through 9 only.  Steps 10-13
(open-attempt resolution, dependency/revision promotion, cache write-back)
are left to packet O3-P3; this module returns a report describing the fold
state so the caller can continue.
"""

import fcntl
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.claim import classify_claim, validate_claim
from harness_contracts.v1.journal import (
    CAUSE_EDGES,
    ZERO_SHA256,
    validate_journal_event,
)
from harness_contracts.v1.provider_evidence import validate_provider_signals_registry
from harness_contracts.v1.queue_state import validate_queue
from harness_contracts.v1.seal import TERMINAL_STATES, validate_terminal_seal
from harness_contracts.v1.transition import validate_transition

from harness_coordinator.v1.locks import read_claim, reclaim_lock
from harness_coordinator.v1.store import (
    JournalChainBroken,
    atomic_replace,
    append_journal,
    read_journal,
    sweep_orphans,
)


class CoordinatorAlreadyRunning(Exception):
    """Another coordinator process already holds the singleton flock."""


class IntegrityError(Exception):
    """Fatal integrity error during recovery.

    ``packet_id`` is optional and additive (existing 2-arg call sites are
    unaffected) -- set by raise sites that know which single packet an
    error concerns (e.g. a terminal-seal disagreement), so a caller like
    ``reconcile.build_reconciliation_report`` can attribute the failure
    to a specific packet instead of only reporting "the fold broke."
    """

    def __init__(self, code: str, message: str, packet_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.packet_id = packet_id


class RecoveryReport:
    """Result of ``run_started_recovery`` for the caller (O3-P3).

    Defect 2: design 3.5 holds the singleton coordinator flock from step 1
    through step 14 (entering the scheduling loop) -- P2's own scope stops
    at step 9, but the lock itself must still be held past this function's
    return so the caller (P3's coordinator loop) can continue holding it.
    ``singleton_fd`` is the open, still-locked file descriptor; the caller
    becomes responsible for releasing it via ``release_singleton()`` when
    the coordinator run actually ends.
    """

    def __init__(
        self,
        state_root_id: str,
        run_id: str,
        coordinator_id: str,
        journal_events: List[Dict[str, Any]],
        derived_states: Dict[str, Dict[str, Any]],
        derived_queue: Dict[str, Any],
        reclaimed_locks: List[str],
        abandoned_intents: List[Dict[str, Any]],
        torn_tail_handled: bool,
        singleton_fd: int,
    ) -> None:
        self.state_root_id = state_root_id
        self.run_id = run_id
        self.coordinator_id = coordinator_id
        self.journal_events = journal_events
        self.derived_states = derived_states
        self.derived_queue = derived_queue
        self.reclaimed_locks = reclaimed_locks
        self.abandoned_intents = abandoned_intents
        self.torn_tail_handled = torn_tail_handled
        self._singleton_fd = singleton_fd
        self._singleton_released = False

    def release_singleton(self) -> None:
        """Release the singleton coordinator flock. Idempotent."""
        if self._singleton_released:
            return
        fcntl.flock(self._singleton_fd, fcntl.LOCK_UN)
        os.close(self._singleton_fd)
        self._singleton_released = True


def run_started_recovery(
    state_root: str,
    coordinator_id: str,
    run_id: str,
    trusted_process_context: Dict[str, Any],
    now: str,
) -> RecoveryReport:
    """Execute RUN_STARTED recovery steps 1-9 and return a report.

    Raises:
        CoordinatorAlreadyRunning: if the singleton flock is already held.
        IntegrityError: on fatal integrity problems.
        JournalChainBroken: propagated from ``read_journal`` for non-final
            corruption (caller should exit non-zero).
    """
    os.makedirs(state_root, exist_ok=True)

    # Step 1: acquire singleton coordinator flock non-blocking.
    singleton_path = os.path.join(state_root, "locks", "coordinator.singleton")
    os.makedirs(os.path.dirname(singleton_path), exist_ok=True)
    singleton_fd = os.open(singleton_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(singleton_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(singleton_fd)
        raise CoordinatorAlreadyRunning("Singleton coordinator flock already held")
    except OSError:
        # A genuine lock conflict raises BlockingIOError specifically; any
        # other OSError (permission denied, disk full, etc) is a distinct
        # failure and must not be misreported as "another coordinator is
        # running."
        os.close(singleton_fd)
        raise

    try:
        # Step 2: read/validate MANIFEST.json (initialize if absent).
        manifest = _read_or_init_manifest(state_root, now)
        state_root_id = manifest["state_root_id"]

        # Step 3: validate trust registries and record digests.
        trust_digests = _validate_trust_roots(state_root)

        # Step 4: validate the journal; handle torn tail.
        journal_path = os.path.join(state_root, "journal.ndjson")
        lock_path = os.path.join(state_root, "locks", "journal.wlock")
        journal_events, torn_tail = read_journal(journal_path, state_root_id=state_root_id)

        torn_tail_handled = False
        if torn_tail is not None:
            _handle_torn_tail(state_root, journal_path, lock_path, journal_events, torn_tail, coordinator_id, run_id, state_root_id, now)
            journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)
            torn_tail_handled = True

        # Step 5: fold the journal.
        derived_states, counters = _fold_journal(state_root, journal_events)

        # Step 6: append RUN_STARTED.
        run_started_event = _build_run_started_event(
            journal_events,
            coordinator_id,
            run_id,
            state_root_id,
            now,
            trusted_process_context,
            trust_digests,
            counters.get("disabled_lanes", []),
        )
        append_journal(
            journal_path,
            run_started_event,
            lock_path,
            expected_head=journal_events[-1] if journal_events else None,
        )
        journal_events.append(run_started_event)

        # Step 7: sweep orphan tmp files.
        sweep_orphans(state_root, run_id)

        # Step 8: reconcile locks.
        pending_intents_at_step8 = _read_pending_intents(state_root, state_root_id)
        pending_intent_ids = {
            i.get("intent_id") for i in pending_intents_at_step8 if isinstance(i, dict) and i.get("intent_id")
        }
        reclaimed_locks = _reconcile_locks(
            state_root,
            journal_path,
            lock_path,
            journal_events,
            coordinator_id,
            run_id,
            state_root_id,
            now,
            trusted_process_context,
            pending_intent_ids,
        )
        journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)

        # Step 9: resolve pending intents. Re-read tolerantly (defect 3) --
        # queue.json is a rebuildable cache and step 8 may have changed
        # what's committed since it was first read.
        pending_intents_at_step9 = _read_pending_intents(state_root, state_root_id)
        abandoned_intents, reclaimed_at_step9 = _resolve_pending_intents(
            state_root,
            journal_path,
            lock_path,
            journal_events,
            coordinator_id,
            run_id,
            state_root_id,
            now,
            trusted_process_context,
            pending_intents_at_step9,
        )
        reclaimed_locks = reclaimed_locks + reclaimed_at_step9
        journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)

        # Build derived queue projection from the fold.
        derived_queue = _build_derived_queue(
            derived_states, state_root_id, journal_events[-1] if journal_events else None
        )

        return RecoveryReport(
            state_root_id=state_root_id,
            run_id=run_id,
            coordinator_id=coordinator_id,
            journal_events=journal_events,
            derived_states=derived_states,
            derived_queue=derived_queue,
            reclaimed_locks=reclaimed_locks,
            abandoned_intents=abandoned_intents,
            torn_tail_handled=torn_tail_handled,
            singleton_fd=singleton_fd,
        )
    except Exception:
        # Defect 2: only release on a FAILED recovery -- on success the
        # flock must keep spanning past this return (see RecoveryReport).
        fcntl.flock(singleton_fd, fcntl.LOCK_UN)
        os.close(singleton_fd)
        raise


def _read_or_init_manifest(state_root: str, now: str) -> Dict[str, Any]:
    manifest_path = os.path.join(state_root, "MANIFEST.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "rb") as f:
            manifest = json.loads(f.read().decode("utf-8"))
        if manifest.get("schema_version") != 1:
            raise IntegrityError("INVALID_VALUE", "MANIFEST schema_version must be 1")
        if not isinstance(manifest.get("state_root_id"), str) or not manifest["state_root_id"]:
            raise IntegrityError("INVALID_VALUE", "MANIFEST state_root_id must be a non-empty string")
        # Defect 9: verify the manifest's own canonical self-hash before
        # trusting anything it declares (state_root_id in particular).
        declared = manifest.get("manifest_sha256")
        computed = compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"}))
        if declared != computed:
            raise IntegrityError("EVIDENCE_HASH_MISMATCH", "MANIFEST.json manifest_sha256 does not match canonical self-hash")
        return manifest

    state_root_id = str(uuid.uuid4())
    manifest = {
        "schema_version": 1,
        "state_root_id": state_root_id,
        "created_at": now,
        "contract_versions": {
            "packet": 1,
            "worker_result": 1,
            "verdict": 1,
            "replay": 1,
            "journal": 1,
            "queue": 1,
            "claim": 1,
            "attempt_outcome": 1,
            "provider_evidence": 1,
            "reassignment": 1,
            "reconciliation": 1,
        },
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"}))
    data = canonical_bytes(manifest)
    atomic_replace(manifest_path, data, coordinator_id="init", nonce=str(uuid.uuid4()))
    return manifest


def _validate_trust_roots(state_root: str) -> Dict[str, str]:
    """Validate the two operator-owned trust registries.

    Defect 8: these files are operator-owned (design section 1.0) and the
    coordinator has no write path to them.  D0.5 is explicit that trusted
    context absent means the operation refuses, never a default -- so a
    missing registry fails closed here rather than being fabricated.
    """
    trust_dir = os.path.join(state_root, "trust")

    reviewer_path = os.path.join(trust_dir, "reviewer_sessions.json")
    provider_path = os.path.join(trust_dir, "provider_signals.json")

    if not os.path.exists(reviewer_path):
        raise IntegrityError("TRUST_CONTEXT_MISSING", "trust/reviewer_sessions.json is missing (operator-owned; the coordinator never creates it)")
    if not os.path.exists(provider_path):
        raise IntegrityError("TRUST_CONTEXT_MISSING", "trust/provider_signals.json is missing (operator-owned; the coordinator never creates it)")

    with open(reviewer_path, "rb") as f:
        reviewer_raw = f.read()
    reviewer = json.loads(reviewer_raw.decode("utf-8"))
    if not isinstance(reviewer, dict) or reviewer.get("schema_version") != 1:
        raise IntegrityError("INVALID_VALUE", "trust/reviewer_sessions.json schema_version must be 1")
    if not isinstance(reviewer.get("sessions"), list):
        raise IntegrityError("INVALID_VALUE", "trust/reviewer_sessions.json sessions must be an array")
    for i, s in enumerate(reviewer["sessions"]):
        if not isinstance(s, str) or not s.strip():
            raise IntegrityError("INVALID_VALUE", f"trust/reviewer_sessions.json sessions/{i} must be a non-empty string")
    declared = reviewer.get("registry_sha256")
    computed = compute_sha256(canonical_bytes(reviewer, omit={"registry_sha256"}))
    if declared != computed:
        raise IntegrityError("EVIDENCE_HASH_MISMATCH", "trust/reviewer_sessions.json registry_sha256 mismatch")

    with open(provider_path, "rb") as f:
        provider_raw = f.read()
    provider_result = validate_provider_signals_registry(provider_raw)
    if not provider_result["valid"]:
        raise IntegrityError("INVALID_VALUE", f"trust/provider_signals.json invalid: {provider_result['errors'][0]['message']}")

    return {
        "reviewer_sessions_path": "trust/reviewer_sessions.json",
        "reviewer_sessions_sha256": compute_sha256(reviewer_raw),
        "provider_signals_path": "trust/provider_signals.json",
        "provider_signals_sha256": compute_sha256(provider_raw),
    }


def _handle_torn_tail(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    torn_tail: bytes,
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
) -> None:
    torn_dir = os.path.join(state_root, "journal.torn")
    os.makedirs(torn_dir, exist_ok=True)
    tail_path = os.path.join(torn_dir, f"{run_id}.bytes")
    tail_rel = os.path.relpath(tail_path, state_root)
    atomic_replace(tail_path, torn_tail, coordinator_id=coordinator_id, nonce=str(uuid.uuid4()))

    # Truncate journal to valid prefix.
    with open(journal_path, "rb") as f:
        raw = f.read()
    valid_prefix_length = len(raw) - len(torn_tail)
    with open(journal_path, "r+b") as f:
        f.truncate(valid_prefix_length)
        os.fsync(f.fileno())

    last_event = journal_events[-1] if journal_events else None
    event = _make_event(
        seq=(last_event["seq"] + 1) if last_event else 1,
        event_type="JOURNAL_TAIL_TRUNCATED",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=last_event,
        event_at=now,
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [
                {
                    "kind": "journal_tail",
                    "artifact_id": "torn_tail",
                    "path": tail_rel,
                    "sha256": compute_sha256(torn_tail),
                    "byte_length": len(torn_tail),
                }
            ],
            "classification": None,
            "transition_detail": None,
            "recovery": {
                "abandoned_intent_id": None,
                "abandoned_at_stage": None,
                "consecutive_abandonments": None,
                "prior_claim": None,
                "truncation": {
                    "byte_length": len(torn_tail),
                    "tail_path": tail_rel,
                    "tail_sha256": compute_sha256(torn_tail),
                    "valid_prefix_last_seq": last_event["seq"] if last_event else 0,
                },
                "review_failure": None,
            },
            "run": None,
            "report": None,
        },
    )
    append_journal(journal_path, event, lock_path, expected_head=last_event)


def _fold_journal(
    state_root: str,
    journal_events: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    packets: Dict[str, Dict[str, Any]] = {}
    counters = {
        "attempts_started_total": 0,
        "infra_retries_total": 0,
        "revise_verdicts_total": 0,
        "revise_cycles_total": 0,
        "reassignments_total": 0,
        "results_recorded_total": 0,
        "verdicts_recorded_total": 0,
        "intents_abandoned_total": 0,
        "locks_reclaimed_total": 0,
        "disabled_lanes": [],
    }

    state_changing_types = {"PACKET_ENROLLED", "STATE_TRANSITION", "ATTEMPT_STARTED", "ATTEMPT_FINISHED", "VERDICT_RECORDED"}

    for event in journal_events:
        event_type = event.get("event_type")
        cause = event.get("cause")
        packet_id = event.get("packet_id")
        from_state = event.get("from_state")
        to_state = event.get("to_state")

        if event_type in state_changing_types:
            if event_type == "PACKET_ENROLLED":
                if from_state is not None:
                    raise IntegrityError("INVALID_TRANSITION", "PACKET_ENROLLED must have from_state null")
            else:
                t_result = validate_transition(from_state, to_state)
                if not t_result["valid"]:
                    raise IntegrityError("INVALID_TRANSITION", t_result["errors"][0]["message"])
            allowed_edges = CAUSE_EDGES.get(cause, set()) if isinstance(cause, str) else set()
            if (from_state, to_state) not in allowed_edges:
                raise IntegrityError(
                    "INVALID_TRANSITION",
                    f"Cause '{cause}' does not permit transition ({from_state}, {to_state})",
                )
            # Defect 1: the checks above validate the event's OWN declared
            # (from_state, to_state) pair in isolation -- they never compare
            # it to the packet state the fold has actually accumulated so
            # far.  Without this, a forged/duplicated event can claim any
            # abstractly-legal edge regardless of where the packet really
            # is, including re-opening a packet that is already terminal.
            # This is the terminal-safety guarantee (design 3.5 step 5,
            # fixtures C1/C2): re-derive it from TERMINAL_STATES + the
            # packet's actual current fold state, not just the edge tables.
            if event_type != "PACKET_ENROLLED":
                pkt_check = packets.get(packet_id)
                if pkt_check is None:
                    raise IntegrityError("INVALID_TRANSITION", f"{event_type} for unknown packet {packet_id}")
                if pkt_check["state"] in TERMINAL_STATES:
                    raise IntegrityError(
                        "INVALID_TRANSITION",
                        f"Packet {packet_id} is already terminal ({pkt_check['state']}); cannot accept {event_type}",
                    )
                if pkt_check["state"] != from_state:
                    raise IntegrityError(
                        "INVALID_TRANSITION",
                        f"{event_type} declares from_state '{from_state}' but packet {packet_id} is actually in state '{pkt_check['state']}'",
                    )

        if event_type == "PACKET_ENROLLED":
            payload = event.get("payload") or {}
            packet_payload = payload.get("packet") or {}
            packet_id = event.get("packet_id")
            if packet_id in packets:
                raise IntegrityError("DUPLICATE_ID", f"Packet {packet_id} already enrolled")
            lane = packet_payload.get("lane")
            packets[packet_id] = {
                "packet_id": packet_id,
                "enqueue_seq": event["seq"],
                "state": to_state,
                "lane": lane,
                "dependency_ids": list(packet_payload.get("dependency_ids") or []),
                "packet_sha256": packet_payload.get("packet_sha256"),
                "retry_limit": packet_payload.get("retry_limit"),
                "sonnet_reassignment_allowed": packet_payload.get("sonnet_reassignment_allowed"),
                "attempts_started": 0,
                "infra_retries_used": 0,
                "revise_cycles_used": 0,
                "revise_verdicts": 0,
                "reassignment_used": False,
                "open_attempt": None,
                "earliest_next_attempt_at": None,
                "last_event_seq": event["seq"],
                "last_event_sha256": event["event_sha256"],
                "terminal_seal_sha256": None,
                "quarantine_reason": None,
                "human_required_reasons": [],
                "lane_history": [{"lane": lane, "since_event_seq": event["seq"]}],
            }

        elif event_type == "ATTEMPT_STARTED":
            pkt = packets.get(packet_id)
            if pkt is None:
                raise IntegrityError("INVALID_TRANSITION", f"ATTEMPT_STARTED for unknown packet {packet_id}")
            payload = event.get("payload") or {}
            attempt_payload = payload.get("attempt") or {}
            attempt_lane = attempt_payload.get("lane")
            if attempt_lane and attempt_lane != pkt["lane"]:
                pkt["lane"] = attempt_lane
                pkt["lane_history"].append({"lane": attempt_lane, "since_event_seq": event["seq"]})
            pkt["state"] = "RUNNING"
            pkt["attempts_started"] += 1
            pkt["open_attempt"] = attempt_payload.get("attempt")
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]
            counters["attempts_started_total"] += 1

        elif event_type == "WORKER_RESULT_RECORDED":
            counters["results_recorded_total"] += 1

        elif event_type == "ATTEMPT_FINISHED":
            pkt = packets.get(packet_id)
            if pkt is None:
                raise IntegrityError("INVALID_TRANSITION", f"ATTEMPT_FINISHED for unknown packet {packet_id}")
            payload = event.get("payload") or {}
            classification = payload.get("classification") or {}
            pkt["state"] = to_state
            pkt["open_attempt"] = None
            cause = event.get("cause")
            if cause == "infra_retry":
                pkt["infra_retries_used"] += 1
                counters["infra_retries_total"] += 1
            elif cause == "provider_exhausted_reassignment":
                pkt["reassignment_used"] = True
                pkt["lane"] = "sonnet_implementation"
                pkt["lane_history"].append({"lane": "sonnet_implementation", "since_event_seq": event["seq"]})
                counters["reassignments_total"] += 1
            elif to_state == "QUARANTINED":
                pkt["quarantine_reason"] = classification.get("quarantine_reason") or cause
            elif to_state == "HUMAN_REQUIRED":
                pkt["human_required_reasons"] = classification.get("human_required_reasons") or [cause]
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]

        elif event_type == "VERDICT_RECORDED":
            pkt = packets.get(packet_id)
            if pkt is None:
                raise IntegrityError("INVALID_TRANSITION", f"VERDICT_RECORDED for unknown packet {packet_id}")
            pkt["state"] = to_state
            if to_state == "REVISE":
                pkt["revise_verdicts"] += 1
                counters["revise_verdicts_total"] += 1
            elif to_state == "QUARANTINED":
                payload = event.get("payload") or {}
                attempt = payload.get("attempt") or {}
                pkt["quarantine_reason"] = "verdict_quarantine"
            elif to_state == "HUMAN_REQUIRED":
                pkt["human_required_reasons"] = ["verdict_human_required"]
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]
            counters["verdicts_recorded_total"] += 1

        elif event_type == "STATE_TRANSITION":
            pkt = packets.get(packet_id)
            if pkt is None:
                raise IntegrityError("INVALID_TRANSITION", f"STATE_TRANSITION for unknown packet {packet_id}")
            pkt["state"] = to_state
            if cause == "revision_requeued":
                pkt["revise_cycles_used"] += 1
                counters["revise_cycles_total"] += 1
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]

        elif event_type == "INTENT_ABANDONED":
            counters["intents_abandoned_total"] += 1

        elif event_type == "LOCK_RECLAIMED":
            counters["locks_reclaimed_total"] += 1

        elif event_type == "RUN_STARTED":
            payload = event.get("payload") or {}
            run_payload = payload.get("run") or {}
            counters["disabled_lanes"] = list(run_payload.get("disabled_lanes") or [])

    # Terminal-seal consistency check.
    seal_dir = os.path.join(state_root, "state", "terminal")
    sealed_packets: Set[str] = set()
    if os.path.isdir(seal_dir):
        for name in os.listdir(seal_dir):
            if not name.endswith(".seal.json"):
                continue
            pid = name[:-len(".seal.json")]
            seal_path = os.path.join(seal_dir, name)
            try:
                with open(seal_path, "rb") as f:
                    seal = json.loads(f.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise IntegrityError("TERMINAL_SEAL_MISMATCH", f"Seal for {pid} is not valid JSON: {exc}", packet_id=pid)
            seal_result = validate_terminal_seal(seal)
            if not seal_result["valid"]:
                raise IntegrityError("TERMINAL_SEAL_MISMATCH", f"Seal for {pid} is invalid: {seal_result['errors'][0]['message']}", packet_id=pid)
            pkt = packets.get(pid)
            if pkt is None:
                raise IntegrityError("TERMINAL_SEAL_MISMATCH", f"Seal exists for unenrolled packet {pid}", packet_id=pid)
            if pkt["state"] != seal.get("terminal_state"):
                raise IntegrityError(
                    "TERMINAL_SEAL_MISMATCH",
                    f"Seal state {seal.get('terminal_state')} does not match fold state {pkt['state']} for {pid}",
                    packet_id=pid,
                )
            pkt["terminal_seal_sha256"] = seal.get("seal_sha256")
            sealed_packets.add(pid)

    # Step 5 only checks existing seals for consistency; missing terminal seals
    # are created later by step 13 (owned by O3-P3).
    return packets, counters


def _build_run_started_event(
    journal_events: List[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    trusted_process_context: Dict[str, Any],
    trust_digests: Dict[str, str],
    disabled_lanes: List[str],
) -> Dict[str, Any]:
    prev_event = journal_events[-1] if journal_events else None
    return _make_event(
        seq=(prev_event["seq"] + 1) if prev_event else 1,
        event_type="RUN_STARTED",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=prev_event,
        event_at=now,
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": {
                "coordinator": {
                    "coordinator_id": coordinator_id,
                    "boot_id": trusted_process_context["boot_id"],
                    "hostname": trusted_process_context["hostname"],
                    "pid": trusted_process_context["pid"],
                },
                "trust_roots": trust_digests,
                "contract_versions": {
                    "packet": 1,
                    "worker_result": 1,
                    "verdict": 1,
                    "replay": 1,
                    "journal": 1,
                    "queue": 1,
                    "claim": 1,
                    "attempt_outcome": 1,
                    "provider_evidence": 1,
                    "reassignment": 1,
                    "reconciliation": 1,
                },
                "end_reason": None,
                "end_detail": None,
                "disabled_lanes": list(disabled_lanes),
            },
            "report": None,
        },
    )


def _read_pending_intents(state_root: str, state_root_id: str) -> List[Dict[str, Any]]:
    """Tolerantly read queue.json's ``pending_intents`` list.

    Defect 3: queue.json is a rebuildable cache (D0.2) -- a corrupt or
    schema-invalid file must never abort the run.  Any real committed work
    is safe regardless (the journal is the sole source of truth); a lock
    whose intent never reached the journal is still caught independently
    by lock reconciliation no matter what queue.json says.
    """
    queue_path = os.path.join(state_root, "queue.json")
    if not os.path.exists(queue_path):
        return []
    try:
        with open(queue_path, "rb") as f:
            queue = json.loads(f.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    q_result = validate_queue(queue, state_root_id=state_root_id)
    if not q_result["valid"]:
        return []
    pending = queue.get("pending_intents")
    if not isinstance(pending, list):
        return []
    return pending


def _reconcile_locks(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    trusted_process_context: Dict[str, Any],
    pending_intent_ids: Any,
) -> List[str]:
    locks_dir = os.path.join(state_root, "locks")
    if not os.path.isdir(locks_dir):
        return []

    reclaimed: List[str] = []
    lock_files = []
    for name in os.listdir(locks_dir):
        if not name.endswith(".lock.json"):
            continue
        full = os.path.join(locks_dir, name)
        if os.path.isfile(full):
            lock_files.append(full)

    for lock_file in lock_files:
        record = read_claim(lock_file)
        validation = validate_claim(record)
        if not validation["valid"]:
            raise IntegrityError("INVALID_VALUE", f"Lock {lock_file} invalid: {validation['errors'][0]['message']}")
        classification = classify_claim(record, trusted_process_context)
        status = classification["status"]
        if status in {"FOREIGN_HOST", "FOREIGN_LIVE"}:
            raise IntegrityError(
                "CLAIM_CONFLICT",
                f"Lock {lock_file} is {status}; refusing to start",
            )
        if status in {"STALE_PRIOR_BOOT", "STALE_SAME_BOOT"}:
            intent_id_check = record.get("intent_id")
            # Defect 5: an intent already committed to the journal is a
            # genuinely open, in-progress attempt (crash point 3) -- not an
            # abandonment. Resolving it is O3-P3's scope (open-attempt
            # resolution); this lock must be left entirely alone, never
            # reclaimed, so the journal never contradicts itself about
            # whether the intent is durable.
            committed_ids_here = {
                e.get("intent_id") for e in journal_events if e.get("intent_id") is not None
            }
            if intent_id_check is not None and intent_id_check in committed_ids_here:
                continue
            packet_id = record["packet_id"]
            prior_claim = {
                "claim_sha256": record["claim_sha256"],
                "path": os.path.relpath(lock_file, state_root),
                "classification": status,
                "coordinator_id": record["coordinator_id"],
                "pid": record["pid"],
                "boot_id": record["boot_id"],
                "hostname": record["hostname"],
            }
            event = _make_event(
                seq=(_last_seq(journal_events) + 1),
                event_type="LOCK_RECLAIMED",
                coordinator_id=coordinator_id,
                run_id=run_id,
                state_root_id=state_root_id,
                prev_event=journal_events[-1] if journal_events else None,
                event_at=now,
                packet_id=packet_id,
                payload={
                    "packet": None,
                    "attempt": None,
                    "artifacts": [],
                    "classification": None,
                    "transition_detail": None,
                    "recovery": {
                        "abandoned_intent_id": None,
                        "abandoned_at_stage": None,
                        "consecutive_abandonments": None,
                        "prior_claim": prior_claim,
                        "truncation": None,
                        "review_failure": None,
                    },
                    "run": None,
                    "report": None,
                },
            )
            append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
            journal_events.append(event)

            intent_id = record.get("intent_id")
            # Defect 4: design 3.4's write order creates the lock BEFORE
            # the queue.json pending-intent entry, so every real claim-
            # stage crash-2 (queue has the intent, journal lacks the
            # committing event) ALSO has a lock present -- lock presence
            # alone does not distinguish crash-1a from crash-2. The real
            # discriminator is whether this intent also has a pending_intents
            # entry in queue.json.
            stage = "queue_intent_written" if (intent_id is not None and intent_id in pending_intent_ids) else "lock_acquired"
            abandon_event = _make_event(
                seq=(_last_seq(journal_events) + 1),
                event_type="INTENT_ABANDONED",
                coordinator_id=coordinator_id,
                run_id=run_id,
                state_root_id=state_root_id,
                prev_event=journal_events[-1] if journal_events else None,
                event_at=now,
                packet_id=packet_id,
                intent_id=intent_id,
                payload={
                    "packet": None,
                    "attempt": None,
                    "artifacts": [],
                    "classification": None,
                    "transition_detail": None,
                    "recovery": {
                        "abandoned_intent_id": intent_id,
                        "abandoned_at_stage": stage,
                        "consecutive_abandonments": None,
                        "prior_claim": prior_claim,
                        "truncation": None,
                        "review_failure": None,
                    },
                    "run": None,
                    "report": None,
                },
            )
            append_journal(journal_path, abandon_event, lock_path, expected_head=journal_events[-1] if journal_events else None)
            journal_events.append(abandon_event)

            reclaim_lock(lock_file, run_id, status)
            reclaimed.append(packet_id)

    return reclaimed


def _resolve_pending_intents(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    trusted_process_context: Dict[str, Any],
    pending_intents: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    committed_intent_ids = {
        e.get("intent_id")
        for e in journal_events
        if e.get("intent_id") is not None
    }

    abandoned: List[Dict[str, Any]] = []
    reclaimed: List[str] = []
    for intent in pending_intents:
        intent_id = intent.get("intent_id")
        if intent_id in committed_intent_ids:
            continue

        packet_id = intent.get("packet_id")
        event = _make_event(
            seq=(_last_seq(journal_events) + 1),
            event_type="INTENT_ABANDONED",
            coordinator_id=coordinator_id,
            run_id=run_id,
            state_root_id=state_root_id,
            prev_event=journal_events[-1] if journal_events else None,
            event_at=now,
            packet_id=packet_id,
            intent_id=intent_id,
            payload={
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": {
                    "abandoned_intent_id": intent_id,
                    "abandoned_at_stage": "queue_intent_written",
                    "consecutive_abandonments": None,
                    "prior_claim": None,
                    "truncation": None,
                    "review_failure": None,
                },
                "run": None,
                "report": None,
            },
        )
        append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
        journal_events.append(event)
        abandoned.append(intent)

        # Defect 7 + Opus round-2 finding 1: never bypass classify_claim
        # with a hardcoded classification, AND never select the lock to
        # reclaim by packet_id alone -- a packet can have an unrelated,
        # genuinely-live lock (e.g. a committed open attempt) at the same
        # canonical path while THIS specific intent_id is the one being
        # abandoned. Only reclaim if the on-disk lock's own intent_id
        # actually matches the abandoned intent; otherwise this lock
        # belongs to different, still-live work and must be left alone
        # entirely (exactly defect 5's rule, enforced here too). A
        # reclaim, when it does apply, must journal LOCK_RECLAIMED with
        # prior_claim BEFORE moving the file, identically to step 8 --
        # mutating the state root with no journal record is itself the
        # auditability violation D0.1 exists to prevent.
        lock_file = os.path.join(state_root, "locks", f"{packet_id}.lock.json")
        if os.path.exists(lock_file):
            lock_record = read_claim(lock_file)
            lock_validation = validate_claim(lock_record)
            if lock_validation["valid"] and lock_record.get("intent_id") == intent_id:
                lock_classification = classify_claim(lock_record, trusted_process_context)
                lock_status = lock_classification["status"]
                if lock_status in {"STALE_PRIOR_BOOT", "STALE_SAME_BOOT"}:
                    prior_claim = {
                        "claim_sha256": lock_record["claim_sha256"],
                        "path": os.path.relpath(lock_file, state_root),
                        "classification": lock_status,
                        "coordinator_id": lock_record["coordinator_id"],
                        "pid": lock_record["pid"],
                        "boot_id": lock_record["boot_id"],
                        "hostname": lock_record["hostname"],
                    }
                    reclaim_event = _make_event(
                        seq=(_last_seq(journal_events) + 1),
                        event_type="LOCK_RECLAIMED",
                        coordinator_id=coordinator_id,
                        run_id=run_id,
                        state_root_id=state_root_id,
                        prev_event=journal_events[-1] if journal_events else None,
                        event_at=now,
                        packet_id=packet_id,
                        payload={
                            "packet": None,
                            "attempt": None,
                            "artifacts": [],
                            "classification": None,
                            "transition_detail": None,
                            "recovery": {
                                "abandoned_intent_id": None,
                                "abandoned_at_stage": None,
                                "consecutive_abandonments": None,
                                "prior_claim": prior_claim,
                                "truncation": None,
                                "review_failure": None,
                            },
                            "run": None,
                            "report": None,
                        },
                    )
                    append_journal(journal_path, reclaim_event, lock_path, expected_head=journal_events[-1] if journal_events else None)
                    journal_events.append(reclaim_event)
                    reclaim_lock(lock_file, run_id, lock_status)
                    reclaimed.append(packet_id)

    return abandoned, reclaimed


def _build_derived_queue(
    derived_states: Dict[str, Dict[str, Any]],
    state_root_id: str,
    last_event: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    entries = []
    for packet_id in sorted(derived_states.keys()):
        pkt = derived_states[packet_id]
        entries.append({
            "packet_id": packet_id,
            "enqueue_seq": pkt["enqueue_seq"],
            "state": pkt["state"],
            "lane": pkt["lane"],
            "dependency_ids": pkt["dependency_ids"],
            "packet_sha256": pkt["packet_sha256"],
            "attempts_started": pkt["attempts_started"],
            "infra_retries_used": pkt["infra_retries_used"],
            "revise_cycles_used": pkt["revise_cycles_used"],
            "revise_verdicts": pkt["revise_verdicts"],
            "reassignment_used": pkt["reassignment_used"],
            "open_attempt": pkt["open_attempt"],
            "earliest_next_attempt_at": pkt["earliest_next_attempt_at"],
            "last_event_seq": pkt["last_event_seq"],
            "terminal_seal_sha256": pkt["terminal_seal_sha256"],
        })

    queue = {
        "schema_version": 1,
        "state_root_id": state_root_id,
        "derived_from": {
            "journal_last_seq": last_event["seq"] if last_event else 0,
            "journal_last_event_sha256": last_event["event_sha256"] if last_event else ZERO_SHA256,
        },
        "entries": entries,
        "pending_intents": [],
        "queue_sha256": "",
    }
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    return queue


def _last_seq(journal_events: List[Dict[str, Any]]) -> int:
    return journal_events[-1]["seq"] if journal_events else 0


def _make_event(
    seq: int,
    event_type: str,
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    prev_event: Optional[Dict[str, Any]],
    event_at: str,
    packet_id: Optional[str] = None,
    intent_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    cause: str = "none",
) -> Dict[str, Any]:
    """Build a canonically-hashed journal event envelope.

    ``from_state``/``to_state``/``cause`` default to the no-transition shape
    every O3-P2 call site uses (RUN_STARTED, LOCK_RECLAIMED,
    INTENT_ABANDONED, JOURNAL_TAIL_TRUNCATED never carry a real edge) --
    adding them as optional, defaulted parameters here is additive and
    changes no existing call site's behavior. O3-P3R's real STATE_TRANSITION/
    ATTEMPT_FINISHED events are the first callers to supply them.
    """
    event_id = f"{run_id}-{seq}"
    event: Dict[str, Any] = {
        "schema_version": 1,
        "seq": seq,
        "event_id": event_id,
        "event_type": event_type,
        "event_at": event_at,
        "coordinator_id": coordinator_id,
        "run_id": run_id,
        "state_root_id": state_root_id,
        "packet_id": packet_id,
        "intent_id": intent_id,
        "from_state": from_state,
        "to_state": to_state,
        "cause": cause,
        "payload": payload or {
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": None,
        },
        "prev_event_sha256": prev_event["event_sha256"] if prev_event else ZERO_SHA256,
        "event_sha256": "",
    }
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    return event
