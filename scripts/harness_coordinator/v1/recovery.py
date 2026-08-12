"""Coordinator RUN_STARTED recovery for harness v1.

Implements design section 3.5 steps 1 through 9 only.  Steps 10-13
(open-attempt resolution, dependency/revision promotion, cache write-back)
are left to packet O3-P3; this module returns a report describing the fold
state so the caller can continue.
"""

import datetime
import fcntl
import json
import os
import stat
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.claim import classify_claim, validate_claim
from harness_contracts.v1.execution_plan import (
    ExecutionPlanContractError,
    authenticate_execution_plan_bytes,
)
from harness_contracts.v1.journal import (
    CAUSE_EDGES,
    GRACEFUL_STOP_EVENT_TYPES,
    GRACEFUL_STOP_REASON_CODES,
    ZERO_SHA256,
    validate_journal_event,
)
from harness_contracts.v1.worker_result import RE_RFC3339
from harness_contracts.v1.provider_evidence import validate_provider_signals_registry
from harness_contracts.v1.packet import RE_SHA256, _matches, is_harness_id, validate_packet
from harness_contracts.v1.queue_state import validate_queue
from harness_contracts.v1.seal import TERMINAL_STATES, validate_terminal_seal
from harness_contracts.v1.transition import validate_transition

from harness_coordinator.v1.locks import (
    list_worker_claim_ids,
    read_claim_at,
    reclaim_lock_at,
)
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id
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
        # ``str(exc)`` carries the code for every code uniformly, so a bare
        # ``pytest.raises(match=...)`` or a logged traceback names the failure
        # class.  ``self.message`` stays the RAW message: consumers such as
        # ``reconcile``'s attention records and ``replay_schedule``'s
        # divergences format ``code`` themselves and would otherwise double it.
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.packet_id = packet_id


# ``PACKET_PAUSED`` is schema-forbidden from transitioning packet state (its
# ``from_state``/``to_state`` must both be null), so it cannot mark a paused
# packet ineligible the way an ordinary state transition would. Reusing the
# already-required ``earliest_next_attempt_at`` packet-state field --
# already consulted by ``scheduler._is_eligible`` -- is how the fold makes a
# paused/blocked packet genuinely ineligible for reselection without
# inventing new schema. A real BACKOFF's own ``next_eligible_at`` is used
# verbatim (see ``_fold_journal``'s ``PACKET_PAUSED`` branch); a pause with
# no natural expiry (``PAUSE``/``STOP``/``HUMAN_REQUIRED``, e.g.
# ``NO_CAPABLE_MODEL_AVAILABLE`` or the human-authority gate) gets this
# sentinel instead. It is a timestamp safely beyond any plan's
# ``wall_clock_safety_seconds`` ceiling (``execution_plan.
# MAX_WALL_CLOCK_SAFETY_SECONDS`` is 86400 seconds, one day), so it reads as
# "not eligible again within this run" without inventing a second,
# never-clears sentinel value that could be confused with a real timestamp.
_INDEFINITE_PAUSE_SENTINEL = "9999-12-31T23:59:59Z"


WORKSPACE_STAGE_SPECS = {
    "WORKSPACE_BASELINE_RECORDED": {
        "event_kind": "workspace_baseline", "artifact_kind": "workspace_baseline",
        "suffix": ".baseline.json",
        "fields": {"schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
                   "worktree_identity", "packet_snapshot", "protected_snapshot", "writable_paths",
                   "forbidden_surfaces", "content_sha256", "artifact_sha256"},
    },
    "WORKSPACE_POSTFLIGHT_RECORDED": {
        "event_kind": "workspace_postflight", "artifact_kind": "workspace_postflight",
        "suffix": ".postflight.json",
        "fields": {"schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
                   "worktree_identity", "packet_snapshot", "protected_snapshot", "writable_paths",
                   "forbidden_surfaces", "derived_changes", "scope_findings", "worker_manifest_findings",
                   "protected_findings", "secret_findings", "acceptance_allowed", "content_sha256",
                   "artifact_sha256"},
    },
    "INTEGRATION_MANIFEST_RECORDED": {
        "event_kind": "workspace_integration", "artifact_kind": "integration_manifest",
        "suffix": ".integration.json",
        "fields": {"schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
                   "starting_revision", "integration_base", "integration_target_path",
                   "integration_target_status", "worktree_identity", "derived_changes",
                   "verification_evidence_ids", "protected_tree_result", "secret_result", "decision",
                   "reason_codes", "postflight", "accepted_replay", "required_human_action",
                   "content_sha256", "artifact_sha256"},
    },
}


def _workspace_fold_error(message: str, packet_id: Optional[str],
                          packets: Dict[str, Dict[str, Any]]) -> IntegrityError:
    """Return an attributable O4 fold failure without dropping packet rows."""
    error = IntegrityError("WORKSPACE_EVIDENCE_MISMATCH", message, packet_id)
    error.partial_packets = dict(packets)
    return error


def validate_workspace_stage_artifact(raw: bytes, packet: Dict[str, Any], intent_id: str,
                                      event_type: str, binding: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one O4 artifact and its journal binding without fallbacks."""
    spec = WORKSPACE_STAGE_SPECS[event_type]
    packet_id = packet["packet_id"]
    expected_path = "workspace/%s/%s%s" % (packet_id, intent_id, spec["suffix"])
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("WORKSPACE_EVIDENCE_MISMATCH", "workspace evidence artifact is unreadable", packet_id) from exc
    if not isinstance(artifact, dict):
        raise IntegrityError(
            "WORKSPACE_EVIDENCE_MISMATCH",
            "workspace evidence artifact root is not an object",
            packet_id,
        )
    content_sha256 = compute_sha256(canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"}))
    with_content = dict(artifact)
    with_content["content_sha256"] = content_sha256
    artifact_sha256 = compute_sha256(canonical_bytes(with_content, omit={"artifact_sha256"}))
    if (raw != canonical_bytes(artifact)
            or set(artifact) != spec["fields"]
            or artifact.get("schema_version") != 1
            or artifact.get("artifact_kind") != spec["artifact_kind"]
            or artifact.get("packet_id") != packet_id
            or artifact.get("packet_sha256") != packet.get("packet_sha256")
            or artifact.get("intent_id") != intent_id
            or artifact.get("content_sha256") != content_sha256
            or artifact.get("artifact_sha256") != artifact_sha256
            or binding.get("kind") != spec["event_kind"]
            or binding.get("artifact_id") != spec["event_kind"]
            or binding.get("path") != expected_path
            or binding.get("content_sha256") != content_sha256
            or binding.get("sha256") != artifact_sha256
            or binding.get("byte_length") != len(raw)
            or set(binding) != {
                "kind", "artifact_id", "path", "sha256", "content_sha256", "byte_length",
            }):
        raise IntegrityError("WORKSPACE_EVIDENCE_MISMATCH", "workspace evidence artifact disagrees", packet_id)
    return artifact


def _direct_state_root_path(state_root: str) -> str:
    """Normalize only macOS's fixed /var -> /private/var system alias.

    ``realpath`` is deliberately forbidden here: it would also follow a
    caller-controlled final or parent symlink before the no-follow handle had
    a chance to reject it. The suffix is copied lexically and every component
    beneath ``/private/var`` is still opened by ``open_state_root`` with
    ``O_NOFOLLOW``.
    """
    if state_root == "/var" or state_root.startswith("/var/"):
        try:
            if os.path.islink("/var") and os.readlink("/var") == "private/var":
                return "/private/var" + state_root[len("/var"):]
        except OSError:
            pass
    return state_root


def _ensure_state_root_nofollow(state_root: str) -> None:
    """Create a missing direct-call root without following any component."""
    if not os.path.isabs(state_root):
        raise ValueError(f"state root must be an absolute path: {state_root!r}")
    fd = os.open("/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in state_root.split("/"):
            if component == "":
                continue
            if component in (".", ".."):
                raise ValueError(
                    f"state root must be lexically canonical: {state_root!r}")
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                    getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=fd,
                )
            except FileNotFoundError:
                os.mkdir(component, 0o700, dir_fd=fd)
                child = os.open(
                    component,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                    getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=fd,
                )
            os.close(fd)
            fd = child
    finally:
        os.close(fd)


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
    handle=None,
) -> RecoveryReport:
    """Execute RUN_STARTED recovery steps 1-9 and return a report.

    Raises:
        CoordinatorAlreadyRunning: if the singleton flock is already held.
        IntegrityError: on fatal integrity problems.
        JournalChainBroken: propagated from ``read_journal`` for non-final
            corruption (caller should exit non-zero).
    """
    if handle is None:
        # Legacy direct callers on macOS commonly receive /var/... from
        # tempfile even though the kernel canonical directory is
        # /private/var/....  Normalize only this compatibility entry. The
        # live run_once path supplies its already-strict pinned handle and
        # never reaches this branch.
        canonical_root = _direct_state_root_path(state_root)
        _ensure_state_root_nofollow(canonical_root)
        with open_state_root(canonical_root) as scoped:
            return run_started_recovery(
                canonical_root, coordinator_id, run_id, trusted_process_context, now,
                handle=scoped)
    handle.verify_identity()

    # Step 1: acquire singleton coordinator flock non-blocking.
    handle.verify_identity()
    singleton_path = os.path.join(state_root, "locks", "coordinator.singleton")
    os.makedirs(os.path.dirname(singleton_path), exist_ok=True)
    singleton_fd = os.open(singleton_path, os.O_CREAT | os.O_RDWR, 0o600)
    handle.verify_identity()
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
        handle.verify_identity()
        manifest = _read_or_init_manifest(state_root, now)
        handle.verify_identity()
        state_root_id = manifest["state_root_id"]

        # Step 3: validate trust registries and record digests.
        handle.verify_identity()
        trust_digests = _validate_trust_roots(state_root)
        handle.verify_identity()

        # Step 4: validate the journal; handle torn tail.
        journal_path = os.path.join(state_root, "journal.ndjson")
        lock_path = os.path.join(state_root, "locks", "journal.wlock")
        handle.verify_identity()
        journal_events, torn_tail = read_journal(journal_path, state_root_id=state_root_id)
        handle.verify_identity()

        torn_tail_handled = False
        if torn_tail is not None:
            handle.verify_identity()
            _handle_torn_tail(state_root, journal_path, lock_path, journal_events, torn_tail, coordinator_id, run_id, state_root_id, now)
            handle.verify_identity()
            journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)
            handle.verify_identity()
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
        handle.verify_identity()
        append_journal(
            journal_path,
            run_started_event,
            lock_path,
            expected_head=journal_events[-1] if journal_events else None,
        )
        handle.verify_identity()
        journal_events.append(run_started_event)

        # Step 7: sweep orphan tmp files.
        handle.verify_identity()
        sweep_orphans(state_root, run_id)
        handle.verify_identity()

        # Step 8: reconcile locks.
        handle.verify_identity()
        pending_intents_at_step8 = _read_pending_intents(state_root, state_root_id)
        handle.verify_identity()
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
            handle,
        )
        handle.verify_identity()
        journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)
        handle.verify_identity()

        # Step 9: resolve pending intents. Re-read tolerantly (defect 3) --
        # queue.json is a rebuildable cache and step 8 may have changed
        # what's committed since it was first read.
        handle.verify_identity()
        pending_intents_at_step9 = _read_pending_intents(state_root, state_root_id)
        handle.verify_identity()
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
            handle,
        )
        reclaimed_locks = reclaimed_locks + reclaimed_at_step9
        handle.verify_identity()
        journal_events, _ = read_journal(journal_path, state_root_id=state_root_id)
        handle.verify_identity()

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
    validate_harness_id(run_id, "/run_id")
    torn_dir = os.path.join(state_root, "journal.torn")
    os.makedirs(torn_dir, exist_ok=True)
    tail_path = safe_state_path(
        state_root,
        "journal.torn",
        identifier=run_id,
        identifier_suffix=".bytes",
    )
    tail_rel = os.path.relpath(tail_path, os.path.realpath(state_root))
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
    bound_plans_by_run: Dict[str, Dict[str, Any]] = {}
    # Graceful-stop state is journal-only: no artifact is read to decide it,
    # so unlike plan authentication below it holds under the phantom-root
    # folds that reconcile and replay perform.
    stop_requested_runs: Set[str] = set()
    stop_effective_runs: Set[str] = set()
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

    for event_index, event in enumerate(journal_events):
        event_type = event.get("event_type")
        cause = event.get("cause")
        packet_id = event.get("packet_id")
        if packet_id is not None:
            try:
                validate_harness_id(packet_id, "/packet_id")
            except ValueError as exc:
                raise IntegrityError("INVALID_FORMAT", str(exc)) from exc
        from_state = event.get("from_state")
        to_state = event.get("to_state")

        if event_type in GRACEFUL_STOP_EVENT_TYPES:
            stop_run_id = event.get("run_id")
            if not isinstance(stop_run_id, str) or not stop_run_id:
                raise IntegrityError(
                    "GRACEFUL_STOP_INVALID", "graceful stop event has an invalid run_id")
            if event_type == "GRACEFUL_STOP_REQUESTED":
                if stop_run_id in stop_effective_runs:
                    raise IntegrityError(
                        "GRACEFUL_STOP_REQUEST_AFTER_EFFECTIVE",
                        "run requested a graceful stop after one already took effect")
                if stop_run_id in stop_requested_runs:
                    raise IntegrityError(
                        "GRACEFUL_STOP_DUPLICATE_REQUEST",
                        "run has more than one graceful stop request")
                stop_requested_runs.add(stop_run_id)
            else:
                if stop_run_id not in stop_requested_runs:
                    # An effective stop with no request is not reconstructable:
                    # nothing records what the run was stopping for.
                    raise IntegrityError(
                        "GRACEFUL_STOP_EFFECTIVE_WITHOUT_REQUEST",
                        "graceful stop took effect without a recorded request")
                if stop_run_id in stop_effective_runs:
                    raise IntegrityError(
                        "GRACEFUL_STOP_DUPLICATE_EFFECTIVE",
                        "run has more than one effective graceful stop")
                stop_effective_runs.add(stop_run_id)

        if event_type == "ATTEMPT_STARTED" and event.get("run_id") in stop_effective_runs:
            # The one-extra-claim failure, caught durably rather than only at
            # the pre-claim gate: once a run's stop is effective, a later
            # ATTEMPT_STARTED in the same run cannot be replayed as legitimate.
            raise IntegrityError(
                "GRACEFUL_STOP_CLAIM_AFTER_STOP",
                "packet claimed after the run's graceful stop took effect",
                packet_id)

        if event_type == "EXECUTION_PLAN_BOUND":
            run_id = event.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise IntegrityError("PLAN_IDENTITY_INVALID", "execution plan binding has an invalid run_id")
            if any(
                prior.get("event_type") == "ATTEMPT_STARTED" and prior.get("run_id") == run_id
                for prior in journal_events[:event_index]
            ):
                raise IntegrityError("PLAN_IDENTITY_LATE_BIND", "execution plan binding occurred after an attempt claim")
            # Recovery has a concrete state root, unlike reconciliation's
            # phantom inventory fold and replay's phantom prefix-fold root.
            # Plan authentication and plan-scope membership both read
            # immutable artifacts from that root, so a phantom-root fold is
            # an inventory pass, not an authentication pass -- exactly how
            # the workspace-evidence branch below already treats it.
            if os.path.isdir(state_root):
                plan = _authenticate_bound_execution_plan(state_root, event)
                existing_plan = bound_plans_by_run.get(run_id)
                if existing_plan is not None and existing_plan != plan:
                    raise IntegrityError("PLAN_IDENTITY_CONFLICT", "run has conflicting execution plan bindings")
                bound_plans_by_run[run_id] = plan
                for known_packet in packets.values():
                    if known_packet.get("run_id") == run_id:
                        _validate_plan_packet_binding(state_root, plan, known_packet)

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
            for index, dependency_id in enumerate(
                packet_payload.get("dependency_ids") or []
            ):
                try:
                    validate_harness_id(
                        dependency_id,
                        f"/payload/packet/dependency_ids/{index}",
                    )
                except ValueError as exc:
                    raise IntegrityError("INVALID_FORMAT", str(exc)) from exc
            if packet_id in packets:
                raise IntegrityError("DUPLICATE_ID", f"Packet {packet_id} already enrolled")
            plan = bound_plans_by_run.get(event.get("run_id"))
            # Same phantom-root convention as the plan-binding branch above:
            # ``_validate_plan_packet_binding`` reads the enrolled packet's
            # immutable artifact, which only a concrete state root has.
            if plan is not None and os.path.isdir(state_root):
                _validate_plan_packet_binding(
                    state_root,
                    plan,
                    {
                        "packet_id": packet_id,
                        "packet_sha256": packet_payload.get("packet_sha256"),
                        "dependency_ids": list(packet_payload.get("dependency_ids") or []),
                        "packet_path": packet_payload.get("packet_path"),
                    },
                )
            lane = packet_payload.get("lane")
            packets[packet_id] = {
                "packet_id": packet_id,
                "run_id": event.get("run_id"),
                "enqueue_seq": event["seq"],
                "state": to_state,
                "lane": lane,
                "dependency_ids": list(packet_payload.get("dependency_ids") or []),
                "packet_sha256": packet_payload.get("packet_sha256"),
                # Persisted so the retro plan-scope check performed when a
                # binding event arrives AFTER enrollment passes the same
                # record shape this branch's own enrollment-time call builds.
                "packet_path": packet_payload.get("packet_path"),
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
                "attempt_intents": {},
                "workspace_evidence": {},
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
            attempt = attempt_payload.get("attempt")
            intent_id = event.get("intent_id")
            if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1:
                preflight_intent = pkt["attempt_intents"].get(attempt)
                if preflight_intent is not None and preflight_intent != intent_id:
                    raise _workspace_fold_error(
                        "workspace baseline intent disagrees with ATTEMPT_STARTED", packet_id, packets)
                pkt["attempt_intents"][attempt] = intent_id
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]
            counters["attempts_started_total"] += 1

        elif event_type == "WORKER_RESULT_RECORDED":
            counters["results_recorded_total"] += 1

        elif event_type in WORKSPACE_STAGE_SPECS:
            pkt = packets.get(packet_id)
            if pkt is None:
                raise _workspace_fold_error(
                    "workspace evidence for unknown packet", packet_id, packets)
            spec = WORKSPACE_STAGE_SPECS[event_type]
            artifact_kind, suffix = spec["event_kind"], spec["suffix"]
            intent_id = event.get("intent_id")
            matching_attempts = [attempt for attempt, known_intent in pkt["attempt_intents"].items()
                                 if known_intent == intent_id]
            # O4 writes the immutable baseline while the packet is still
            # READY.  Bind it to the deterministic next attempt before
            # ATTEMPT_STARTED so a crash before that transition folds back to
            # READY, while a later start must use that exact intent.
            if (event_type == "WORKSPACE_BASELINE_RECORDED"
                    and pkt.get("state") == "READY" and not matching_attempts):
                attempt = pkt["attempts_started"] + 1
                expected_intent = "attempt-%s-%s" % (packet_id, attempt)
                if intent_id != expected_intent:
                    raise _workspace_fold_error(
                        "workspace preflight intent disagrees", packet_id, packets)
                pkt["attempt_intents"][attempt] = intent_id
                matching_attempts = [attempt]
            if len(matching_attempts) != 1:
                raise _workspace_fold_error(
                    "workspace evidence intent disagrees", packet_id, packets)
            attempt = matching_attempts[0]
            expected_path = "workspace/%s/%s%s" % (packet_id, intent_id, suffix)
            artifacts = (event.get("payload") or {}).get("artifacts") or []
            if len(artifacts) != 1:
                raise _workspace_fold_error(
                    "workspace evidence requires one artifact", packet_id, packets)
            artifact = artifacts[0]
            if not isinstance(artifact, dict):
                raise _workspace_fold_error(
                    "workspace evidence binding disagrees", packet_id, packets)
            # Recovery has a concrete state root, unlike reconciliation's
            # phantom inventory fold. Bind the journal hash to the immutable
            # canonical artifact before permitting this stage to count.
            if os.path.isdir(state_root):
                try:
                    with open(os.path.join(state_root, expected_path), "rb") as source:
                        raw = source.read()
                    persisted = validate_workspace_stage_artifact(raw, pkt, intent_id, event_type, artifact)
                except IntegrityError as exc:
                    exc.partial_packets = packets
                    raise
                except (OSError, TypeError, ValueError) as exc:
                    raise _workspace_fold_error(
                        "workspace evidence artifact is unreadable", packet_id, packets) from exc
            stage = artifact_kind
            stages = pkt["workspace_evidence"].setdefault(attempt, {})
            if stage in stages:
                if stages[stage] != artifact:
                    raise _workspace_fold_error(
                        "workspace evidence duplicate disagrees", packet_id, packets)
                continue
            required_prior = {
                "workspace_postflight": "workspace_baseline",
                "workspace_integration": "workspace_postflight",
            }.get(stage)
            if required_prior is not None and required_prior not in stages:
                raise _workspace_fold_error(
                    "workspace evidence stage order disagrees", packet_id, packets)
            stages[stage] = artifact
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]

        elif event_type == "PACKET_PAUSED":
            pkt = packets.get(packet_id)
            if pkt is None:
                # Unlike ATTEMPT_STARTED/ATTEMPT_FINISHED/STATE_TRANSITION,
                # PACKET_PAUSED is not itself proof of a real prior
                # enrollment the fold must have seen -- it is a pure
                # capacity-event record, and reconcile's inventory fold and
                # replay's prefix fold both run over phantom/partial slices
                # that legitimately omit the PACKET_ENROLLED an event like
                # this references (see
                # ``test_phantom_root_folds_tolerate_the_new_budget_events``).
                # A live coordinator run never actually reaches this branch
                # for an unenrolled packet: ``_persist_budget_decision`` is
                # only ever called with a packet ``select_next`` already drew
                # from this SAME fold, so it is always present there.
                continue
            body = (event.get("payload") or {}).get("packet_pause") or {}
            next_eligible = body.get("next_eligible_at")
            # A real BACKOFF window is used verbatim; every other pause
            # reason (PAUSE/STOP/HUMAN_REQUIRED, no natural expiry) gets the
            # indefinite sentinel -- see the constant's own docstring above.
            # This is a last-write-wins update, same convention as every
            # other packet-scoped fold field: the most recent journal record
            # for this packet is authoritative, whichever direction it moves.
            pkt["earliest_next_attempt_at"] = (
                next_eligible if isinstance(next_eligible, str) and next_eligible
                else _INDEFINITE_PAUSE_SENTINEL)
            pkt["last_event_seq"] = event["seq"]
            pkt["last_event_sha256"] = event["event_sha256"]

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
            try:
                seal_path = safe_state_path(
                    state_root,
                    "state",
                    "terminal",
                    identifier=pid,
                    identifier_suffix=".seal.json",
                )
            except ValueError as exc:
                raise IntegrityError(
                    "TERMINAL_SEAL_MISMATCH",
                    f"Seal path for {pid} escapes state root: {exc}",
                    packet_id=pid,
                ) from exc
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


def _authenticate_bound_execution_plan(state_root: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """Authenticate the immutable plan artifact named by one binding event."""
    binding = ((event.get("payload") or {}).get("execution_plan"))
    required = {"plan_id", "plan_sha256", "plan_path", "packet_count"}
    if not isinstance(binding, dict) or set(binding) != required:
        raise IntegrityError("PLAN_IDENTITY_INVALID", "execution plan binding payload is not closed")
    plan_id = binding.get("plan_id")
    try:
        validate_harness_id(plan_id, "/payload/execution_plan/plan_id")
        expected_path = safe_state_path(
            state_root, "plans", identifier=plan_id, identifier_suffix=".json"
        )
    except ValueError as exc:
        raise IntegrityError("PLAN_IDENTITY_INVALID", str(exc)) from exc
    if binding.get("plan_path") != "plans/%s.json" % plan_id:
        raise IntegrityError("PLAN_IDENTITY_INVALID", "execution plan binding path is not canonical")
    try:
        raw = _read_regular_nofollow(expected_path)
    except FileNotFoundError as exc:
        raise IntegrityError("PLAN_IDENTITY_ARTIFACT_MISSING", "bound execution plan artifact is missing") from exc
    except OSError as exc:
        raise IntegrityError("PLAN_IDENTITY_INVALID", "bound execution plan artifact cannot be safely read") from exc
    try:
        plan = authenticate_execution_plan_bytes(raw)
    except ExecutionPlanContractError as exc:
        raise IntegrityError(exc.code, exc.message) from exc
    if plan.get("plan_id") != plan_id:
        raise IntegrityError("PLAN_IDENTITY_CONFLICT", "bound plan artifact plan_id disagrees with journal")
    if plan.get("plan_sha256") != binding.get("plan_sha256"):
        raise IntegrityError("PLAN_IDENTITY_CONFLICT", "bound plan artifact digest disagrees with journal")
    if len(plan.get("packets", [])) != binding.get("packet_count"):
        raise IntegrityError("PLAN_IDENTITY_CONFLICT", "bound plan packet count disagrees with journal")
    return plan


def bound_execution_plan_for_run(
    state_root: str, journal_events: List[Dict[str, Any]], run_id: str
) -> Optional[Dict[str, Any]]:
    """Return the authenticated plan this run is bound to, if any.

    Same phantom-root convention as the fold: authentication reads the
    immutable plan artifact, which only a concrete state root has, so an
    inventory or prefix fold root yields ``None`` rather than a failure.
    """
    if not os.path.isdir(state_root):
        return None
    binding_event = None
    for event in journal_events:
        if (event.get("event_type") == "EXECUTION_PLAN_BOUND"
                and event.get("run_id") == run_id):
            binding_event = event
    if binding_event is None:
        return None
    return _authenticate_bound_execution_plan(state_root, binding_event)


# ---------------------------------------------------------------------------
# Durable graceful-stop state
#
# A graceful stop lets the active attempt reach a durable outcome and complete
# mandatory O4 postflight, then stops the run before the next claim.  It is a
# different thing from an immediate process-safety limit, which terminates a
# process group; the reason vocabularies are disjoint so the two can never be
# confused in the journal.
# ---------------------------------------------------------------------------


def graceful_stop_state(
    journal_events: List[Dict[str, Any]], run_id: str
) -> Dict[str, Any]:
    """Fold one run's durable graceful-stop state. Pure; reads no artifact.

    ``pending`` is the conservative state a restart must honour: the stop was
    requested and has not yet taken effect, so recovery completes first and
    the stop is made effective afterwards -- never dropped because a new
    process did not observe the original condition.
    """
    requested = None
    effective = None
    for event in journal_events or []:
        if event.get("run_id") != run_id:
            continue
        event_type = event.get("event_type")
        if event_type == "GRACEFUL_STOP_REQUESTED":
            requested = event
        elif event_type == "GRACEFUL_STOP_EFFECTIVE":
            effective = event
    reason_code = None
    for event in (effective, requested):
        if event is None:
            continue
        body = ((event.get("payload") or {}).get(_stop_payload_key(event["event_type"]))
                or {})
        if isinstance(body.get("reason_code"), str):
            reason_code = body["reason_code"]
            break
    return {
        "requested": requested,
        "effective": effective,
        "pending": requested is not None and effective is None,
        "stopped": effective is not None,
        "reason_code": reason_code,
    }


def _stop_payload_key(event_type: str) -> str:
    return ("graceful_stop_effective" if event_type == "GRACEFUL_STOP_EFFECTIVE"
            else "graceful_stop_request")


def _run_started_at(journal_events: List[Dict[str, Any]], run_id: str) -> Optional[str]:
    """The authenticated start instant of ``run_id``, or None if unrecorded.

    The EARLIEST RUN_STARTED wins: a restart appends another one for the same
    run, and measuring elapsed time from the restart would let a run that
    keeps crashing outlive its own backstop forever.

    Earliest by VALUE, never by position in the list -- taking the first match
    in list order would make a safety backstop depend on how the caller
    happened to order its events, and every accepted instant here is
    normalised fixed-width Z-terminated UTC, so ``min`` over the strings is
    exactly ``min`` over the instants.
    """
    started = [
        event.get("event_at") for event in journal_events or []
        if event.get("event_type") == "RUN_STARTED"
        and event.get("run_id") == run_id
        and _matches_rfc3339(event.get("event_at"))
    ]
    return min(started) if started else None


def _matches_rfc3339(value: Any) -> bool:
    """Normalised, fixed-width, Z-terminated UTC, so string order is time order."""
    return _matches(value, RE_RFC3339)


def _parse_utc(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def wall_clock_ceiling_reached(
    journal_events: List[Dict[str, Any]],
    run_id: str,
    wall_clock_safety_seconds: Any,
    now: Any,
) -> bool:
    """Has the plan's run-level wall-clock backstop elapsed?

    This is a backstop against an abandoned run, NOT the definition of a
    successful one: plan completion is.  It is evaluated against durable UTC
    with explicit ordering validation, per the design -- a ``now`` earlier
    than the authenticated run start is clock regression and fails closed
    rather than being read as "time remains".
    """
    if isinstance(wall_clock_safety_seconds, bool) or not isinstance(
            wall_clock_safety_seconds, int) or wall_clock_safety_seconds < 1:
        raise IntegrityError(
            "BUDGET_EVIDENCE_INVALID",
            "wall_clock_safety_seconds must be a positive integer")
    started_at = _run_started_at(journal_events, run_id)
    if started_at is None:
        # Nothing authenticates when this run began, so no elapsed time can be
        # claimed against it.  The run is bounded by its other limits instead.
        return False
    if not _matches_rfc3339(now):
        raise IntegrityError(
            "CLOCK_EVIDENCE_INVALID", "now must be a normalised RFC3339 UTC instant")
    if now < started_at:
        raise IntegrityError(
            "CLOCK_REGRESSION",
            "now precedes the authenticated run start")
    elapsed = (_parse_utc(now) - _parse_utc(started_at)).total_seconds()
    return elapsed >= wall_clock_safety_seconds


def _graceful_stop_binding(source: Dict[str, Any]) -> Dict[str, str]:
    """The plan identity every graceful stop event is bound to.

    ``source`` is anything carrying ``plan_id``/``plan_sha256`` -- a validated
    execution plan, or a recorded ``graceful_stop_request`` payload, which
    names the same two fields precisely so a stop's plan identity can be read
    back off the journal instead of being supplied again.
    """
    if not isinstance(source, dict):
        raise ValueError("a graceful stop must name the plan it stops")
    plan_id, plan_sha256 = source.get("plan_id"), source.get("plan_sha256")
    if not is_harness_id(plan_id) or not _matches(plan_sha256, RE_SHA256):
        raise ValueError("a graceful stop must name an authenticated plan identity")
    return {"plan_id": plan_id, "plan_sha256": plan_sha256}


def _append_stop_event(
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    event_type: str,
    body: Dict[str, Any],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    handle=None,
) -> List[Dict[str, Any]]:
    from harness_coordinator.v1.budget_runtime import budget_event_payload

    previous = journal_events[-1] if journal_events else None
    event = _make_event(
        seq=(_last_seq(journal_events) + 1),
        event_type=event_type,
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=previous,
        event_at=now,
        payload=budget_event_payload(event_type, body),
    )
    result = validate_journal_event(event, previous, state_root_id)
    if not result["valid"]:
        raise IntegrityError(
            "GRACEFUL_STOP_INVALID",
            "refusing to journal an invalid graceful stop event: %s"
            % result["errors"][0]["message"])
    if handle is not None:
        handle.verify_identity()
    append_journal(journal_path, event, lock_path, expected_head=previous)
    if handle is not None:
        handle.verify_identity()
    journal_events.append(event)
    return journal_events


def request_graceful_stop(
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    plan: Dict[str, Any],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    reason_code: str,
    evidence_ids: List[str],
    handle=None,
) -> List[Dict[str, Any]]:
    """Record that this run must stop after its active attempt resolves.

    Requesting is idempotent: a request already on record is returned as-is
    rather than duplicated, so a retry or a restart cannot manufacture a
    second stop for one run.
    """
    if reason_code not in GRACEFUL_STOP_REASON_CODES:
        # An immediate process-safety code lands here: refused, not recorded.
        # Terminating a runaway process group is not an orderly plan stop, and
        # relabelling one as the other is exactly the confusion this vocabulary
        # split exists to prevent.
        raise ValueError(
            "%s is not a graceful stop reason code" % (reason_code,))
    binding = _graceful_stop_binding(plan)
    state = graceful_stop_state(journal_events, run_id)
    if state["stopped"]:
        raise IntegrityError(
            "GRACEFUL_STOP_REQUEST_AFTER_EFFECTIVE",
            "run already has an effective graceful stop")
    if state["pending"]:
        return journal_events
    body = dict(binding, reason_code=reason_code,
                evidence_ids=sorted(set(evidence_ids or [])))
    return _append_stop_event(
        journal_path, lock_path, journal_events, "GRACEFUL_STOP_REQUESTED", body,
        coordinator_id, run_id, state_root_id, now, handle=handle)


def make_graceful_stop_effective(
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    plan: Optional[Dict[str, Any]] = None,
    handle=None,
) -> List[Dict[str, Any]]:
    """Close a requested stop, after recovery and postflight have completed.

    Reason code, evidence ids AND PLAN IDENTITY are all read back off the
    recorded request rather than supplied again, so an effective stop can
    never claim a different reason -- or a different plan -- from the request
    it completes.  Taking the binding from the journal is also what lets a
    restart close a pending stop at all: the plan that produced the request is
    on record even when this process was handed no plan argument and none was
    ever bound into the journal.

    ``plan`` is therefore optional, and when supplied it is CHECKED against
    the recorded identity rather than preferred over it.  A disagreement is
    ambiguity about which plan is being stopped, so it fails closed with
    ``PLAN_IDENTITY_CONFLICT`` instead of silently writing the argument's
    identity over the request's.
    """
    state = graceful_stop_state(journal_events, run_id)
    request = state["requested"]
    binding = None
    if request is not None:
        requested_body = (
            (request.get("payload") or {}).get("graceful_stop_request") or {})
        binding = _graceful_stop_binding(requested_body)
        if plan is not None and _graceful_stop_binding(plan) != binding:
            raise IntegrityError(
                "PLAN_IDENTITY_CONFLICT",
                "an effective graceful stop must name the same plan as the "
                "request it completes")
    if state["stopped"]:
        return journal_events
    if not state["pending"]:
        raise ValueError(
            "a graceful stop cannot take effect without a recorded request")
    body = dict(
        binding,
        reason_code=requested_body.get("reason_code"),
        requested_event_id=request.get("event_id"),
        evidence_ids=sorted(set(requested_body.get("evidence_ids") or [])),
    )
    return _append_stop_event(
        journal_path, lock_path, journal_events, "GRACEFUL_STOP_EFFECTIVE", body,
        coordinator_id, run_id, state_root_id, now, handle=handle)


def _validate_plan_packet_binding(
    state_root: str, plan: Dict[str, Any], enrolled: Dict[str, Any]
) -> None:
    """Prove an enrolled packet is one authenticated member of ``plan``."""
    packet_id = enrolled.get("packet_id")
    expected = None
    for packet in plan.get("packets", []):
        if packet.get("packet_id") == packet_id:
            expected = packet
            break
    if expected is None:
        raise IntegrityError("PLAN_SCOPE_PACKET_OUTSIDE_PLAN", "enrolled packet is outside bound execution plan", packet_id)
    if enrolled.get("packet_sha256") != expected.get("packet_sha256"):
        raise IntegrityError("PLAN_SCOPE_PACKET_DIGEST_MISMATCH", "enrolled packet digest disagrees with bound execution plan", packet_id)
    # Ordered, not set, comparison on purpose: the plan authenticates a
    # deterministic enrollment order, so dependency ORDER is part of plan
    # identity and a reordering is a different plan, not the same one.
    if enrolled.get("dependency_ids") != expected.get("dependencies"):
        raise IntegrityError("PLAN_SCOPE_PACKET_DEPENDENCY_MISMATCH", "enrolled packet dependencies disagree with bound execution plan", packet_id)
    if enrolled.get("packet_path") != "packets/%s.json" % packet_id:
        raise IntegrityError("PLAN_SCOPE_PACKET_ARTIFACT_PATH", "enrolled packet artifact path is not canonical", packet_id)

    try:
        packet_path = safe_state_path(
            state_root, "packets", identifier=packet_id, identifier_suffix=".json"
        )
        raw = _read_regular_nofollow(packet_path)
    except FileNotFoundError as exc:
        raise IntegrityError("PLAN_SCOPE_PACKET_ARTIFACT_MISSING", "enrolled packet artifact is missing", packet_id) from exc
    except (OSError, ValueError) as exc:
        raise IntegrityError("PLAN_SCOPE_PACKET_ARTIFACT_INVALID", "enrolled packet artifact cannot be safely read", packet_id) from exc
    try:
        packet = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("PLAN_SCOPE_PACKET_ARTIFACT_INVALID", "enrolled packet artifact is invalid JSON", packet_id) from exc
    result = validate_packet(packet)
    if not result["valid"] or raw != canonical_bytes(packet):
        raise IntegrityError("PLAN_SCOPE_PACKET_ARTIFACT_INVALID", "enrolled packet artifact is not canonical and authenticated", packet_id)
    if packet.get("packet_id") != packet_id:
        raise IntegrityError("PLAN_SCOPE_PACKET_DIGEST_MISMATCH", "packet artifact identity disagrees with enrollment", packet_id)
    if packet.get("packet_sha256") != expected.get("packet_sha256"):
        raise IntegrityError("PLAN_SCOPE_PACKET_DIGEST_MISMATCH", "packet artifact digest disagrees with bound execution plan", packet_id)


def _read_regular_nofollow(path: str) -> bytes:
    """Read one artifact without accepting a symlinked terminal path."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("artifact is not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


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
                    "workspace_evidence": 1,
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
    handle=None,
) -> List[str]:
    if handle is None:
        with open_state_root(state_root) as scoped:
            return _reconcile_locks(
                state_root, journal_path, lock_path, journal_events,
                coordinator_id, run_id, state_root_id, now,
                trusted_process_context, pending_intent_ids, scoped)
    reclaimed: List[str] = []
    for packet_id_from_name in list_worker_claim_ids(handle):
        record = read_claim_at(handle, packet_id_from_name)
        lock_file = f"locks/{packet_id_from_name}.lock.json"
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
                "path": lock_file,
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
            handle.verify_identity()
            append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
            handle.verify_identity()
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
            handle.verify_identity()
            append_journal(journal_path, abandon_event, lock_path, expected_head=journal_events[-1] if journal_events else None)
            handle.verify_identity()
            journal_events.append(abandon_event)

            handle.verify_identity()
            reclaim_lock_at(
                handle, packet_id, run_id, status, record["claim_sha256"])
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
    handle=None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if handle is None:
        with open_state_root(state_root) as scoped:
            return _resolve_pending_intents(
                state_root, journal_path, lock_path, journal_events,
                coordinator_id, run_id, state_root_id, now,
                trusted_process_context, pending_intents, scoped)
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
        lock_file = f"locks/{validate_harness_id(packet_id)}.lock.json"
        try:
            lock_record = read_claim_at(handle, packet_id)
        except FileNotFoundError:
            lock_record = None
        reclaim_record = None
        reclaim_status = None
        if lock_record is not None:
            lock_validation = validate_claim(lock_record)
            if lock_validation["valid"] and lock_record.get("intent_id") == intent_id:
                classification = classify_claim(lock_record, trusted_process_context)
                if classification["status"] in {"STALE_PRIOR_BOOT", "STALE_SAME_BOOT"}:
                    reclaim_record = lock_record
                    reclaim_status = classification["status"]

        # Audit order is load-bearing: record the exact claim to be reclaimed,
        # then record abandonment of its intent, and only then move the bytes.
        if reclaim_record is not None:
            prior_claim = {
                "claim_sha256": reclaim_record["claim_sha256"],
                "path": lock_file,
                "classification": reclaim_status,
                "coordinator_id": reclaim_record["coordinator_id"],
                "pid": reclaim_record["pid"],
                "boot_id": reclaim_record["boot_id"],
                "hostname": reclaim_record["hostname"],
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
                    "packet": None, "attempt": None, "artifacts": [],
                    "classification": None, "transition_detail": None,
                    "recovery": {
                        "abandoned_intent_id": None, "abandoned_at_stage": None,
                        "consecutive_abandonments": None, "prior_claim": prior_claim,
                        "truncation": None, "review_failure": None,
                    },
                    "run": None, "report": None,
                },
            )
            handle.verify_identity()
            append_journal(
                journal_path, reclaim_event, lock_path,
                expected_head=journal_events[-1] if journal_events else None)
            handle.verify_identity()
            journal_events.append(reclaim_event)

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
        handle.verify_identity()
        append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
        handle.verify_identity()
        journal_events.append(event)
        abandoned.append(intent)
        if reclaim_record is not None:
            handle.verify_identity()
            reclaim_lock_at(
                handle, packet_id, run_id, reclaim_status,
                reclaim_record["claim_sha256"])
            reclaimed.append(packet_id)

    return abandoned, reclaimed


def _build_derived_queue(
    derived_states: Dict[str, Dict[str, Any]],
    state_root_id: str,
    last_event: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    entries = []
    ordered_packet_ids = sorted(
        derived_states,
        key=lambda packet_id: (derived_states[packet_id]["enqueue_seq"], packet_id),
    )
    for packet_id in ordered_packet_ids:
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
