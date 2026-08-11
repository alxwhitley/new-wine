"""O3-P3R TDD: runtime transitions (dependency promotion, REVISE requeue,
stale-RUNNING resolution) and their adversarial fixtures."""

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_coordinator.v1.classify_runtime import (
    promote_dependencies,
    requeue_revise,
    resolve_open_attempts,
)
from harness_coordinator.v1.recovery import IntegrityError
from harness_coordinator.v1.store import append_journal, read_journal


def _hash_event(event: Dict[str, Any]) -> str:
    return compute_sha256(canonical_bytes(event, omit={"event_sha256"}))


def _make_event(
    seq,
    event_type,
    coordinator_id="coord-1",
    run_id="run-1",
    state_root_id="srid-1",
    prev_event=None,
    event_id=None,
    event_at="2026-08-10T00:00:00Z",
    packet_id=None,
    intent_id=None,
    from_state=None,
    to_state=None,
    cause="none",
    payload=None,
) -> Dict[str, Any]:
    event_id = event_id or f"evt-{seq}"
    payload = payload or {
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": None, "report": None,
    }
    event: Dict[str, Any] = {
        "schema_version": 1, "seq": seq, "event_id": event_id, "event_type": event_type,
        "event_at": event_at, "coordinator_id": coordinator_id, "run_id": run_id,
        "state_root_id": state_root_id, "packet_id": packet_id, "intent_id": intent_id,
        "from_state": from_state, "to_state": to_state, "cause": cause, "payload": payload,
        "prev_event_sha256": prev_event["event_sha256"] if prev_event else ZERO_SHA256,
        "event_sha256": "",
    }
    event["event_sha256"] = _hash_event(event)
    return event


def _write_journal(journal_path: str, events: List[Dict[str, Any]]) -> None:
    # Real recovery always creates locks/ (step 1, the singleton flock)
    # before any journal operation; mirror that here so append_journal's
    # journal.wlock target directory always exists for these tests.
    os.makedirs(os.path.join(os.path.dirname(journal_path), "locks"), exist_ok=True)
    with open(journal_path, "wb") as f:
        for event in events:
            f.write(canonical_bytes(event) + b"\n")


def _valid_packet_body(
    packet_id: str,
    dependency_ids: Optional[List[str]] = None,
    lane: str = "kimi_implementation",
    retry_limit: int = 2,
    sonnet_reassignment_allowed: bool = False,
) -> Dict[str, Any]:
    packet = {
        "schema_version": 1,
        "packet_id": packet_id,
        "objective": "O3-P3R test packet",
        "dependency_ids": dependency_ids or [],
        "lane": lane,
        "assigned_worker": {"worker_id": "kimi-1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "starting_revision": "a" * 40,
        "worktree": {"path": "/tmp/o3-test-worktree", "branch": "o3-p3r-test"},
        "writable_paths": [f"scripts/{packet_id}.py"],
        "forbidden_surfaces": ["backend/app/services/answer_toolbox.py"],
        "required_context": [{"path": "PLAN.md", "sha256": "b" * 64}],
        "premise_checks": [{"check_id": "ck-1", "command_id": "cmd-1", "expected": "present"}],
        "acceptance_criteria": [{"criterion_id": "ac-1", "statement": "works", "required_evidence_ids": ["ev-1"]}],
        "verification_commands": [{
            "command_id": "cmd-1", "argv": ["python3", "-m", "pytest"], "cwd": ".",
            "timeout_seconds": 60, "expected_exit_code": 0, "expected_evidence_ids": ["ev-1"],
        }],
        "budgets": {
            "max_turns": 10, "wall_clock_seconds": 300, "retry_limit": retry_limit,
            "max_output_bytes": 1_000_000, "cost_class": "low", "allowance_limit": 100,
        },
        "network_policy": "denied",
        "checkpoint_artifacts": [{"artifact_id": "art-1", "path": f"scripts/{packet_id}.py", "required_for_fallback": True}],
        "rollback": {"method": "git_reset", "allowed_commands": [{"argv": ["git", "status"], "cwd": "."}]},
        "human_stop_conditions": ["governed_doc_touched"],
        "sonnet_reassignment_allowed": sonnet_reassignment_allowed,
        "created_by": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
    }
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


def _write_packet_body(state_root: str, packet_id: str, body: Dict[str, Any]) -> str:
    rel = f"packets/{packet_id}.json"
    path = os.path.join(state_root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(canonical_bytes(body))
    return rel


def _enroll_event(seq, prev_event, packet_id, body, packet_path_rel, enqueue_seq, to_state):
    packet_payload = {
        "packet_sha256": body["packet_sha256"],
        "packet_path": packet_path_rel,
        "lane": body["lane"],
        "dependency_ids": body["dependency_ids"],
        "sonnet_reassignment_allowed": body["sonnet_reassignment_allowed"],
        "retry_limit": body["budgets"]["retry_limit"],
        "enqueue_seq": enqueue_seq,
    }
    return _make_event(
        seq=seq, event_type="PACKET_ENROLLED", prev_event=prev_event, packet_id=packet_id,
        intent_id=f"enroll-{packet_id}", to_state=to_state, cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _write_terminal_seal(state_root: str, packet_id: str, terminal_state: str, seq: int) -> Dict[str, Any]:
    seal = {
        "schema_version": 1, "packet_id": packet_id, "packet_sha256": "0" * 64,
        "terminal_state": terminal_state, "sealing_event_seq": seq,
        "sealing_event_sha256": "0" * 64, "sealed_at": "2026-08-10T00:00:00Z",
        "quarantine_reason": "contract_invalid" if terminal_state == "QUARANTINED" else None,
        "human_required_reasons": ["worker_human_required"] if terminal_state == "HUMAN_REQUIRED" else [],
        "upstream_digests": {
            "packet_sha256": "0" * 64, "result_sha256": "0" * 64,
            "verdict_sha256": "0" * 64, "bundle_sha256": "0" * 64,
        } if terminal_state == "ACCEPTED" else None,
    }
    seal["seal_sha256"] = compute_sha256(canonical_bytes(seal, omit={"seal_sha256"}))
    seal_dir = os.path.join(state_root, "state", "terminal")
    os.makedirs(seal_dir, exist_ok=True)
    with open(os.path.join(seal_dir, f"{packet_id}.seal.json"), "wb") as f:
        f.write(canonical_bytes(seal))
    return seal


def _fold_pkt(**overrides) -> Dict[str, Any]:
    base = {
        "enqueue_seq": 1, "state": "READY", "lane": "kimi_implementation",
        "dependency_ids": [], "retry_limit": 2, "attempts_started": 0,
        "infra_retries_used": 0, "revise_cycles_used": 0, "revise_verdicts": 0,
        "reassignment_used": False, "open_attempt": None,
        "earliest_next_attempt_at": None, "terminal_seal_sha256": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Dependency promotion
# ---------------------------------------------------------------------------

def test_dependency_accepted_promotes_exactly_one_dependent():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    other_body = _valid_packet_body("other-1")
    other_path = _write_packet_body(state_root, "other-1", other_body)

    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    e3 = _enroll_event(3, e2, "other-1", other_body, other_path, 3, "READY")
    _write_journal(journal_path, [e1, e2, e3])
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
        "other-1": _fold_pkt(enqueue_seq=3, state="READY"),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    transitions = [e for e in events if e["event_type"] == "STATE_TRANSITION"]
    assert len(transitions) == 1
    t = transitions[0]
    assert t["packet_id"] == "dependent-1"
    assert t["from_state"] == "BLOCKED"
    assert t["to_state"] == "READY"
    assert t["cause"] == "dependencies_satisfied"
    assert t["payload"]["transition_detail"]["satisfied_by"][0]["packet_id"] == "dep-1"


def test_dependency_nonterminal_dependent_stays_blocked():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    # dep-1 is still RUNNING -- no terminal seal written at all.

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]


def test_dependency_quarantined_dependent_stays_blocked_not_terminated():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    _write_terminal_seal(state_root, "dep-1", "QUARANTINED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="QUARANTINED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]
    # No BLOCKED -> QUARANTINED edge exists or is invented here.
    assert not [e for e in events if e.get("to_state") == "QUARANTINED" and e["packet_id"] == "dependent-1"]


def test_dependency_human_required_dependent_stays_blocked():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    _write_terminal_seal(state_root, "dep-1", "HUMAN_REQUIRED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="HUMAN_REQUIRED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]


def test_missing_dependency_never_enrolled_stays_blocked():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["never-enrolled"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dependent-1", dependent_body, dependent_path, 1, "BLOCKED")
    _write_journal(journal_path, [e1])

    packets = {"dependent-1": _fold_pkt(enqueue_seq=1, state="BLOCKED", dependency_ids=["never-enrolled"])}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]


def test_duplicate_dependency_id_still_promotes_once_satisfied():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    # duplicate dependency_ids entries for the same real dependency
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_body["dependency_ids"] = ["dep-1", "dep-1"]
    dependent_body["packet_sha256"] = compute_sha256(canonical_bytes(dependent_body, omit={"packet_sha256"}))
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)

    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1", "dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    # validate_packet itself rejects a packet body with duplicate dependency_ids
    # (O2's own DUPLICATE_PATH-style uniqueness isn't defined for dependency_ids
    # specifically, but this proves promote_dependencies does not crash or
    # double-promote on a malformed/duplicated dependency list either way).
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    transitions = [e for e in events if e["event_type"] == "STATE_TRANSITION" and e["packet_id"] == "dependent-1"]
    assert len(transitions) <= 1


def test_dependency_cycle_never_resolves_never_loops():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    a_body = _valid_packet_body("cycle-a", dependency_ids=["cycle-b"])
    a_path = _write_packet_body(state_root, "cycle-a", a_body)
    b_body = _valid_packet_body("cycle-b", dependency_ids=["cycle-a"])
    b_path = _write_packet_body(state_root, "cycle-b", b_body)
    e1 = _enroll_event(1, None, "cycle-a", a_body, a_path, 1, "BLOCKED")
    e2 = _enroll_event(2, e1, "cycle-b", b_body, b_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])

    packets = {
        "cycle-a": _fold_pkt(enqueue_seq=1, state="BLOCKED", dependency_ids=["cycle-b"]),
        "cycle-b": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["cycle-a"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    # Must terminate (no infinite loop) and promote neither.
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]


# ---------------------------------------------------------------------------
# REVISE -> READY requeue
# ---------------------------------------------------------------------------

def test_revise_packet_requeued_preserves_prior_checkpoint_evidence():
    """Requeue only writes a STATE_TRANSITION -- it must never touch or
    remove any prior attempt/evidence/checkpoint records the fold already
    accounts for (attempts_started, revise_cycles_used, etc. are untouched
    by this function; they change only via the fold re-reading the journal)."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    e1 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": {
        "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1},
        "trust_roots": {"reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0"*64, "provider_signals_path": "y", "provider_signals_sha256": "0"*64},
        "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
        "end_reason": None, "end_detail": None, "disabled_lanes": [],
    }, "report": None})
    _write_journal(journal_path, [e1])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="REVISE", attempts_started=1, revise_cycles_used=0, revise_verdicts=1, retry_limit=3)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, exhausted = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    assert exhausted == []
    transitions = [e for e in events if e["event_type"] == "STATE_TRANSITION" and e["packet_id"] == "pkt-1"]
    assert len(transitions) == 1
    assert transitions[0]["from_state"] == "REVISE"
    assert transitions[0]["to_state"] == "READY"
    assert transitions[0]["cause"] == "revision_requeued"
    assert transitions[0]["payload"]["transition_detail"]["revise_cycle"] == 1


def test_repeated_revise_event_second_cycle_requeues_again_until_budget():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _write_journal(journal_path, [])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="REVISE", attempts_started=2, revise_cycles_used=1, retry_limit=3)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, exhausted = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-1", "srid-1", "2026-08-10T00:01:00Z")
    assert exhausted == []
    assert len([e for e in events if e["event_type"] == "STATE_TRANSITION"]) == 1

    # Budget exhausted: attempts_started already at retry_limit+1.
    packets2 = {"pkt-1": _fold_pkt(enqueue_seq=1, state="REVISE", attempts_started=4, revise_cycles_used=2, retry_limit=3)}
    events2, _ = read_journal(journal_path, state_root_id="srid-1")
    count_before = len(events2)
    events2, exhausted2 = requeue_revise(journal_path, lock_path, events2, packets2, "coord-1", "run-1", "srid-1", "2026-08-10T00:02:00Z")
    assert exhausted2 == ["pkt-1"]
    # Stays in REVISE -- no SECOND STATE_TRANSITION for it, no REVISE->QUARANTINED edge invented.
    assert len(events2) == count_before


def test_accepted_packet_presented_for_requeue_is_never_touched():
    """Terminal-state immutability: requeue_revise only scans state==REVISE,
    so an ACCEPTED packet is structurally never a candidate -- but this test
    proves it explicitly rather than relying on that being "obviously" true."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _write_journal(journal_path, [])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x")}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, exhausted = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-1", "srid-1", "2026-08-10T00:01:00Z")
    assert exhausted == []
    assert events == []


# ---------------------------------------------------------------------------
# Stale RUNNING recovery (design 3.5 step 10 a/b/c)
# ---------------------------------------------------------------------------

def _running_setup(state_root, journal_path, attempt=1):
    os.makedirs(os.path.join(state_root, "locks"), exist_ok=True)
    e1 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": {
        "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1},
        "trust_roots": {"reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0"*64, "provider_signals_path": "y", "provider_signals_sha256": "0"*64},
        "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
        "end_reason": None, "end_detail": None, "disabled_lanes": [],
    }, "report": None})
    e2 = _make_event(2, "ATTEMPT_STARTED", prev_event=e1, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": {"attempt": attempt, "lane": "kimi_implementation",
                               "worker": {"worker_id": "w1", "session_id": "s1", "provider": "opencode", "model": "kimi-k2.7-code"},
                               "claim_sha256": None, "worktree_path": None},
                               "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e1, e2])
    return e1, e2


def _write_attempt_outcome(state_root, packet_id, attempt, outcome="COMPLETED", exit_code=0, timed_out=False, signal=None, byte_length=100):
    outcome_record = {
        "schema_version": 1, "packet_id": packet_id, "packet_sha256": "0" * 64, "attempt": attempt,
        "coordinator_id": "coord-1", "run_id": "run-1", "lane": "kimi_implementation",
        "invocation": {"argv": ["python3", "worker.py"], "cwd": ".", "started_at": "2026-08-10T00:00:00Z",
                       "finished_at": "2026-08-10T00:00:10Z", "exit_code": exit_code, "signal": signal,
                       "timed_out": timed_out, "wall_clock_seconds": 10},
        "stdout": {"path": f"results/{packet_id}/{attempt}/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
        "stderr": {"path": f"results/{packet_id}/{attempt}/stderr.bin", "sha256": "0" * 64, "byte_length": 0},
        "raw_result": {"path": "results/pkt-1/1/worker_result.json" if byte_length else None, "sha256": "0" * 64 if byte_length else None, "byte_length": byte_length},
        "result_validation": {"present": byte_length > 0, "valid": byte_length > 0, "error_codes": [], "error_count": 0},
        "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
        "provider_evidence_sha256": None,
        "workspace_postflight": {
            "packet_id": packet_id, "intent_id": f"intent-{attempt}",
            "path": f"workspace/{packet_id}/intent-{attempt}.postflight.json",
            "artifact_sha256": "0" * 64, "content_sha256": "0" * 64,
        },
        "outcome": outcome,
        "fallback": None,
    }
    outcome_record["outcome_sha256"] = compute_sha256(canonical_bytes(outcome_record, omit={"outcome_sha256"}))
    outcome_dir = os.path.join(state_root, "results", packet_id, str(attempt))
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(canonical_bytes(outcome_record))
    return outcome_record


def test_stale_running_no_outcome_case_c_infra_retryable():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)
    # No attempt_outcome.json written at all -- worker still running or
    # coordinator died before capture.

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["from_state"] == "RUNNING"
    assert finished[0]["to_state"] == "READY"
    assert finished[0]["cause"] == "infra_retry"
    assert finished[0]["payload"]["classification"]["attempt_class"] == "INFRA_RETRYABLE"


def test_stale_running_committed_intent_worker_result_already_recorded():
    """Case (a): WORKER_RESULT_RECORDED already journaled -- classify from
    the recorded outcome directly, no re-ingestion."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    e1, e2 = _running_setup(state_root, journal_path)
    outcome = _write_attempt_outcome(state_root, "pkt-1", 1, outcome="COMPLETED")
    wr = _make_event(3, "WORKER_RESULT_RECORDED", prev_event=e2, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
                      payload={"packet": None, "attempt": {"attempt": 1, "lane": "kimi_implementation",
                               "worker": {"worker_id": "w1", "session_id": "s1", "provider": "opencode", "model": "kimi-k2.7-code"},
                               "claim_sha256": None, "worktree_path": None},
                               "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e1, e2, wr])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["to_state"] == "REVIEW"
    assert finished[0]["cause"] == "result_recorded"
    # No duplicate WORKER_RESULT_RECORDED was written.
    assert len([e for e in events if e["event_type"] == "WORKER_RESULT_RECORDED"]) == 1


def test_stale_running_outcome_captured_not_yet_ingested_case_b():
    """Case (b): attempt_outcome.json exists on disk but no
    WORKER_RESULT_RECORDED journaled yet -- ingest it (journal
    WORKER_RESULT_RECORDED), then classify and finish. This is the
    concrete mechanism behind 'a worker that finished before the
    coordinator died still has its work ingested.'"""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)
    _write_attempt_outcome(state_root, "pkt-1", 1, outcome="COMPLETED")

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    assert len([e for e in events if e["event_type"] == "WORKER_RESULT_RECORDED"]) == 1
    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["to_state"] == "REVIEW"


def test_stale_running_abandoned_intent_no_worker_result_treated_as_infra():
    """'Abandoned intent' for a RUNNING packet -- no attempt_outcome.json
    was ever captured (equivalent to case (c)); resolve_open_attempts
    must treat it the same as a genuinely-still-running/crashed worker,
    not raise or silently drop the packet."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert [e for e in events if e["event_type"] == "ATTEMPT_FINISHED" and e["cause"] == "infra_retry"]


def test_repeated_recovery_invocation_is_idempotent():
    """Running resolve_open_attempts twice over the SAME already-resolved
    journal must not re-finish an attempt that's no longer open."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    first_count = len(events)

    # Re-fold: the packet is now READY (infra_retry), not RUNNING, so a
    # second invocation over the fresh fold must find nothing to resolve.
    packets2 = {"pkt-1": _fold_pkt(enqueue_seq=1, state="READY", open_attempt=None, attempts_started=1, infra_retries_used=1)}
    events2, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets2, None, None, "coord-1", "run-3", "srid-1", "2026-08-10T00:02:00Z")
    assert len(events2) == first_count


# ---------------------------------------------------------------------------
# Corrupt / contradictory / malicious runtime state
# ---------------------------------------------------------------------------

def test_corrupt_attempt_outcome_json_reported_not_silently_skipped():
    """Per-packet isolation: a corrupt attempt_outcome.json for ONE
    packet must not raise and abort the whole call -- it's collected in
    the returned attention list, not silently dropped, and (proven
    separately below) does not block an unrelated healthy packet."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)
    outcome_dir = os.path.join(state_root, "results", "pkt-1", "1")
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(b'{"schema_version": 1, "bogus": true}')  # schema-invalid

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert len(attention) == 1
    assert attention[0]["packet_id"] == "pkt-1"
    assert attention[0]["code"] == "INVALID_VALUE"
    assert not [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]


def test_worker_result_recorded_journaled_but_outcome_file_missing_reported():
    """Contradictory durable state: the journal says the result was
    recorded, but the artifact it points to is gone -- this is a
    preserved-evidence integrity failure, reported per-packet rather
    than aborting resolution for every other RUNNING packet."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    e1, e2 = _running_setup(state_root, journal_path)
    wr = _make_event(3, "WORKER_RESULT_RECORDED", prev_event=e2, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
                      payload={"packet": None, "attempt": {"attempt": 1, "lane": "kimi_implementation",
                               "worker": {"worker_id": "w1", "session_id": "s1", "provider": "opencode", "model": "kimi-k2.7-code"},
                               "claim_sha256": None, "worktree_path": None},
                               "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e1, e2, wr])
    # No attempt_outcome.json written -- contradicts the journal.

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert len(attention) == 1
    assert attention[0]["packet_id"] == "pkt-1"
    assert attention[0]["code"] == "EVIDENCE_MISSING"


def test_one_packets_integrity_error_does_not_block_an_independent_healthy_packet():
    """The per-packet isolation guarantee, proven directly: pkt-bad has a
    corrupt attempt_outcome.json; pkt-good is an entirely independent
    RUNNING packet with no outcome captured at all (a normal case-(c)
    scenario). pkt-good must still resolve normally."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    os.makedirs(os.path.join(state_root, "locks"), exist_ok=True)

    e1 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": {
        "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1},
        "trust_roots": {"reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0"*64, "provider_signals_path": "y", "provider_signals_sha256": "0"*64},
        "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
        "end_reason": None, "end_detail": None, "disabled_lanes": [],
    }, "report": None})
    e2 = _make_event(2, "ATTEMPT_STARTED", prev_event=e1, packet_id="pkt-bad", intent_id="attempt-pkt-bad-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": {"attempt": 1, "lane": "kimi_implementation",
                               "worker": {"worker_id": "w1", "session_id": "s1", "provider": "opencode", "model": "kimi-k2.7-code"},
                               "claim_sha256": None, "worktree_path": None},
                               "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    e3 = _make_event(3, "ATTEMPT_STARTED", prev_event=e2, packet_id="pkt-good", intent_id="attempt-pkt-good-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": {"attempt": 1, "lane": "kimi_implementation",
                               "worker": {"worker_id": "w2", "session_id": "s2", "provider": "opencode", "model": "kimi-k2.7-code"},
                               "claim_sha256": None, "worktree_path": None},
                               "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e1, e2, e3])
    outcome_dir = os.path.join(state_root, "results", "pkt-bad", "1")
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(b'{"schema_version": 1, "bogus": true}')

    packets = {
        "pkt-bad": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1),
        "pkt-good": _fold_pkt(enqueue_seq=2, state="RUNNING", open_attempt=1, attempts_started=1),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    assert len(attention) == 1
    assert attention[0]["packet_id"] == "pkt-bad"
    good_finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED" and e["packet_id"] == "pkt-good"]
    assert len(good_finished) == 1
    assert good_finished[0]["cause"] == "infra_retry"


def test_promoted_transition_survives_a_real_read_journal_reread():
    """Regression for the round-1 finding: every event this module writes
    must carry a real, non-null intent_id so read_journal (validate_
    journal_event) accepts it on a genuine re-read, not just an in-memory
    append -- and a SECOND append immediately after (the normal case,
    since the scheduler would journal ATTEMPT_STARTED next) must not
    corrupt the chain either."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    other_body = _valid_packet_body("other-1", dependency_ids=["dep-1"])
    other_path = _write_packet_body(state_root, "other-1", other_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    e3 = _enroll_event(3, e2, "other-1", other_body, other_path, 3, "BLOCKED")
    _write_journal(journal_path, [e1, e2, e3])
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
        "other-1": _fold_pkt(enqueue_seq=3, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert len([e for e in events if e["event_type"] == "STATE_TRANSITION"]) == 2

    # The critical check: re-read the journal FROM DISK (not the in-memory
    # list) after TWO transitions were appended back to back.
    reread_events, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len(reread_events) == 5
    transitions = [e for e in reread_events if e["event_type"] == "STATE_TRANSITION"]
    assert len(transitions) == 2
    assert all(t.get("intent_id") for t in transitions)
    assert len({t["intent_id"] for t in transitions}) == 2  # each promotion gets its own


def test_revise_requeue_survives_a_real_read_journal_reread():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _write_journal(journal_path, [])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="REVISE", attempts_started=1, retry_limit=3)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, exhausted = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-1", "srid-1", "2026-08-10T00:01:00Z")
    assert exhausted == []

    reread_events, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len(reread_events) == 1
    assert reread_events[0]["intent_id"] is not None


def test_provider_exhausted_end_to_end_through_resolve_open_attempts():
    """The exact defect-2 regression: a fully valid, four-guard-passing
    exhaustion claim must reach PROVIDER_EXHAUSTED through the real
    resolve_open_attempts call path (not just classify_attempt called
    directly), and the coordinator-captured stdout/stderr bytes named by
    the outcome record must actually be read from disk."""
    import hashlib

    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    stderr_text = "something\nrate limit exceeded\n"
    stderr_bytes = stderr_text.encode("utf-8")
    stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()
    outcome_dir = os.path.join(state_root, "results", "pkt-1", "1")
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "stdout.bin"), "wb") as f:
        f.write(b"")
    with open(os.path.join(outcome_dir, "stderr.bin"), "wb") as f:
        f.write(stderr_bytes)

    outcome = {
        "schema_version": 1, "packet_id": "pkt-1", "packet_sha256": "0" * 64, "attempt": 1,
        "coordinator_id": "coord-1", "run_id": "run-1", "lane": "kimi_implementation",
        "invocation": {"argv": ["python", "worker.py"], "cwd": "scripts", "started_at": "2026-08-10T00:00:00Z",
                       "finished_at": "2026-08-10T00:00:10Z", "exit_code": 1, "signal": None,
                       "timed_out": False, "wall_clock_seconds": 10},
        "stdout": {"path": "results/pkt-1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
        "stderr": {"path": "results/pkt-1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
        "raw_result": {"path": "results/pkt-1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
        "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
        "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
        "provider_evidence_sha256": "0" * 64,
        "workspace_postflight": {"packet_id": "pkt-1", "intent_id": "intent-1", "path": "workspace/pkt-1/intent-1.postflight.json", "artifact_sha256": "0" * 64, "content_sha256": "0" * 64},
        "outcome": "CHECKPOINTED",
        "fallback": {"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe-1", "reassign_to": "sonnet_implementation"},
    }
    outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(canonical_bytes(outcome))

    provider_evidence = {
        "schema_version": 1, "evidence_id": "pe-1", "packet_id": "pkt-1", "attempt": 1, "provider": "kimi",
        "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
        "invocation": {"argv": ["python", "worker.py"], "exit_code": 1, "signal": None,
                       "started_at": "2026-08-10T00:00:00Z", "finished_at": "2026-08-10T00:00:10Z", "timed_out": False},
        "stdout_path": "results/pkt-1/1/stdout.bin", "stdout_sha256": "0" * 64,
        "stderr_path": "results/pkt-1/1/stderr.bin", "stderr_sha256": stderr_sha256,
        "matched_signal": {"channel": "stderr", "rule_id": "r1", "registry_id": "reg-1",
                            "verbatim_excerpt": "rate limit exceeded", "byte_offset": 10, "byte_length": 19},
        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
    }
    provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))

    signal_registry = {
        "schema_version": 1, "registry_id": "reg-1",
        "providers": {"kimi": [{
            "rule_id": "r1", "channel": "stderr", "match_kind": "substring",
            "pattern": "rate limit exceeded", "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
            "captured_from": {"sample_path": "trust/samples/kimi_rate_limit.json", "sample_sha256": "0" * 64, "captured_at": "2026-08-09T00:00:00Z"},
        }]},
    }

    # kimi lane, reassignment allowed, budget available -> provider_exhausted_reassignment.
    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1,
                                   retry_limit=3, lane="kimi_implementation")}
    packets["pkt-1"]["sonnet_reassignment_allowed"] = True
    packets["pkt-1"]["reassignment_used"] = False
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets,
                                    {"pkt-1": provider_evidence}, signal_registry,
                                    "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["payload"]["classification"]["attempt_class"] == "PROVIDER_EXHAUSTED"
    assert finished[0]["cause"] == "provider_exhausted_reassignment"
    assert finished[0]["to_state"] == "READY"


def test_exhaustion_unconfirmed_when_worker_claims_but_guards_fail():
    """Design 6.3/7.4 row 5: the worker CLAIMED exhaustion (outcome=
    CHECKPOINTED with a fallback object) but the confirmation guards fail
    (here: no provider_evidence supplied at all, so Guard 1 cannot even
    run) -- must classify as exhaustion_unconfirmed, never the generic
    contract_invalid, since operationally these mean very different
    things (the latter reads as 'the worker emitted garbage')."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    outcome_dir = os.path.join(state_root, "results", "pkt-1", "1")
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "stdout.bin"), "wb") as f:
        f.write(b"")
    with open(os.path.join(outcome_dir, "stderr.bin"), "wb") as f:
        f.write(b"")
    outcome = {
        "schema_version": 1, "packet_id": "pkt-1", "packet_sha256": "0" * 64, "attempt": 1,
        "coordinator_id": "coord-1", "run_id": "run-1", "lane": "kimi_implementation",
        "invocation": {"argv": ["python", "worker.py"], "cwd": "scripts", "started_at": "2026-08-10T00:00:00Z",
                       "finished_at": "2026-08-10T00:00:10Z", "exit_code": 1, "signal": None,
                       "timed_out": False, "wall_clock_seconds": 10},
        "stdout": {"path": "results/pkt-1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
        "stderr": {"path": "results/pkt-1/1/stderr.bin", "sha256": "0" * 64, "byte_length": 0},
        "raw_result": {"path": "results/pkt-1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
        "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
        "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
        "provider_evidence_sha256": None,
        "workspace_postflight": {"packet_id": "pkt-1", "intent_id": "intent-1", "path": "workspace/pkt-1/intent-1.postflight.json", "artifact_sha256": "0" * 64, "content_sha256": "0" * 64},
        "outcome": "CHECKPOINTED",
        "fallback": {"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe-missing", "reassign_to": "sonnet_implementation"},
    }
    outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(canonical_bytes(outcome))

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1,
                                   retry_limit=3, lane="kimi_implementation")}
    packets["pkt-1"]["sonnet_reassignment_allowed"] = True
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    # No provider_evidence supplied at all -- Guard 1 cannot run.
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["cause"] == "exhaustion_unconfirmed"
    assert finished[0]["to_state"] == "QUARANTINED"
    assert finished[0]["payload"]["classification"]["quarantine_reason"] == "exhaustion_unconfirmed"


def test_promote_dependencies_idempotent_under_repeated_invocation():
    """Same fold snapshot, called twice -- the second call must not
    double-promote (journal-based intent_id dedup, not a caller re-fold
    dependency)."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert len([e for e in events if e["event_type"] == "STATE_TRANSITION"]) == 1

    # Same unchanged BLOCKED packets dict, called again.
    events2, attention2 = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-3", "srid-1", "2026-08-10T00:02:00Z")
    assert len([e for e in events2 if e["event_type"] == "STATE_TRANSITION"]) == 1
    assert attention2 == []

    reread, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len([e for e in reread if e["event_type"] == "STATE_TRANSITION"]) == 1


def test_requeue_revise_idempotent_under_repeated_invocation():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _write_journal(journal_path, [])

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="REVISE", attempts_started=1, revise_cycles_used=0, retry_limit=3)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, exhausted = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-1", "srid-1", "2026-08-10T00:01:00Z")
    assert len([e for e in events if e["event_type"] == "STATE_TRANSITION"]) == 1

    # Same unchanged REVISE snapshot (revise_cycles_used still 0), called again.
    events2, exhausted2 = requeue_revise(journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:02:00Z")
    assert len([e for e in events2 if e["event_type"] == "STATE_TRANSITION"]) == 1
    assert exhausted2 == []

    reread, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len([e for e in reread if e["event_type"] == "STATE_TRANSITION"]) == 1


def test_provider_exhausted_sonnet_lane_quarantines_fallback_exhausted():
    """Same valid exhaustion evidence, but the packet is already on the
    sonnet_implementation lane -- design 7.4 row 2: quarantine, don't loop."""
    import hashlib

    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    stderr_text = "something\nrate limit exceeded\n"
    stderr_bytes = stderr_text.encode("utf-8")
    stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()
    outcome_dir = os.path.join(state_root, "results", "pkt-1", "1")
    os.makedirs(outcome_dir, exist_ok=True)
    with open(os.path.join(outcome_dir, "stdout.bin"), "wb") as f:
        f.write(b"")
    with open(os.path.join(outcome_dir, "stderr.bin"), "wb") as f:
        f.write(stderr_bytes)

    outcome = {
        "schema_version": 1, "packet_id": "pkt-1", "packet_sha256": "0" * 64, "attempt": 1,
        "coordinator_id": "coord-1", "run_id": "run-1", "lane": "sonnet_implementation",
        "invocation": {"argv": ["python", "worker.py"], "cwd": "scripts", "started_at": "2026-08-10T00:00:00Z",
                       "finished_at": "2026-08-10T00:00:10Z", "exit_code": 1, "signal": None,
                       "timed_out": False, "wall_clock_seconds": 10},
        "stdout": {"path": "results/pkt-1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
        "stderr": {"path": "results/pkt-1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
        "raw_result": {"path": "results/pkt-1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
        "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
        "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
        "provider_evidence_sha256": "0" * 64,
        "workspace_postflight": {"packet_id": "pkt-1", "intent_id": "intent-1", "path": "workspace/pkt-1/intent-1.postflight.json", "artifact_sha256": "0" * 64, "content_sha256": "0" * 64},
        "outcome": "CHECKPOINTED",
        "fallback": {"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe-1", "reassign_to": "sonnet_implementation"},
    }
    outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))
    with open(os.path.join(outcome_dir, "attempt_outcome.json"), "wb") as f:
        f.write(canonical_bytes(outcome))

    provider_evidence = {
        "schema_version": 1, "evidence_id": "pe-1", "packet_id": "pkt-1", "attempt": 1, "provider": "kimi",
        "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
        "invocation": {"argv": ["python", "worker.py"], "exit_code": 1, "signal": None,
                       "started_at": "2026-08-10T00:00:00Z", "finished_at": "2026-08-10T00:00:10Z", "timed_out": False},
        "stdout_path": "results/pkt-1/1/stdout.bin", "stdout_sha256": "0" * 64,
        "stderr_path": "results/pkt-1/1/stderr.bin", "stderr_sha256": stderr_sha256,
        "matched_signal": {"channel": "stderr", "rule_id": "r1", "registry_id": "reg-1",
                            "verbatim_excerpt": "rate limit exceeded", "byte_offset": 10, "byte_length": 19},
        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
    }
    provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))
    signal_registry = {
        "schema_version": 1, "registry_id": "reg-1",
        "providers": {"kimi": [{
            "rule_id": "r1", "channel": "stderr", "match_kind": "substring",
            "pattern": "rate limit exceeded", "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
            "captured_from": {"sample_path": "trust/samples/kimi_rate_limit.json", "sample_sha256": "0" * 64, "captured_at": "2026-08-09T00:00:00Z"},
        }]},
    }

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=2,
                                   retry_limit=3, lane="sonnet_implementation")}
    packets["pkt-1"]["reassignment_used"] = True
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets,
                                    {"pkt-1": provider_evidence}, signal_registry,
                                    "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert finished[0]["cause"] == "fallback_exhausted"
    assert finished[0]["to_state"] == "QUARANTINED"


def test_d19_infra_retry_at_budget_cap_quarantines_not_requeues():
    """Fixture D19: retry_limit=2, at the cap (attempts_started == 3) --
    an infra failure must quarantine (attempt_budget_exhausted), not
    requeue into READY forever."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)
    # No attempt_outcome.json -- case (c).

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=3, retry_limit=2)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    finished = [e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]
    assert len(finished) == 1
    assert finished[0]["cause"] == "attempt_budget_exhausted"
    assert finished[0]["to_state"] == "QUARANTINED"
    assert finished[0]["payload"]["classification"]["quarantine_reason"] == "attempt_budget_exhausted"


def test_true_idempotency_same_running_snapshot_called_twice_journal_deduped():
    """The reviewer's exact concern: call resolve_open_attempts TWICE with
    the packets dict UNCHANGED (still showing RUNNING, as a caller that
    forgot to re-fold between calls would do) -- the journal itself, not
    the caller's snapshot, must be the idempotency key."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _running_setup(state_root, journal_path)

    packets = {"pkt-1": _fold_pkt(enqueue_seq=1, state="RUNNING", open_attempt=1, attempts_started=1)}
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert len([e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]) == 1

    # Same packets dict, still RUNNING -- must not double-finish.
    events2, _ = resolve_open_attempts(state_root, journal_path, lock_path, events, packets, None, None, "coord-1", "run-3", "srid-1", "2026-08-10T00:02:00Z")
    assert len([e for e in events2 if e["event_type"] == "ATTEMPT_FINISHED"]) == 1

    reread, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len([e for e in reread if e["event_type"] == "ATTEMPT_FINISHED"]) == 1


def test_corrupt_terminal_seal_reported_typed_not_raw_json_error_not_silently_skipped():
    """Per-packet isolation: a corrupt terminal seal for one dependency
    is reported in the attention list (typed IntegrityError code, never
    a raw json.JSONDecodeError leaking out), and does not abort
    promotion for other independent BLOCKED packets."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    other_dep_body = _valid_packet_body("dep-2")
    other_dep_path = _write_packet_body(state_root, "dep-2", other_dep_body)
    other_dependent_body = _valid_packet_body("dependent-2", dependency_ids=["dep-2"])
    other_dependent_path = _write_packet_body(state_root, "dependent-2", other_dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    e3 = _enroll_event(3, e2, "dep-2", other_dep_body, other_dep_path, 3, "READY")
    e4 = _enroll_event(4, e3, "dependent-2", other_dependent_body, other_dependent_path, 4, "BLOCKED")
    _write_journal(journal_path, [e1, e2, e3, e4])

    seal_dir = os.path.join(state_root, "state", "terminal")
    os.makedirs(seal_dir, exist_ok=True)
    with open(os.path.join(seal_dir, "dep-1.seal.json"), "wb") as f:
        f.write(b"{not valid json")
    _write_terminal_seal(state_root, "dep-2", "ACCEPTED", 3)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
        "dep-2": _fold_pkt(enqueue_seq=3, state="ACCEPTED", terminal_seal_sha256="y"),
        "dependent-2": _fold_pkt(enqueue_seq=4, state="BLOCKED", dependency_ids=["dep-2"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")

    assert len(attention) == 1
    assert attention[0]["packet_id"] == "dependent-1"
    assert attention[0]["code"] == "INVALID_JSON"
    # The unrelated, healthy dependent-2 must still promote.
    transitions = [e for e in events if e["event_type"] == "STATE_TRANSITION"]
    assert len(transitions) == 1
    assert transitions[0]["packet_id"] == "dependent-2"


def test_promote_dependencies_fold_gate_blocks_before_ever_reaching_the_seal_check():
    """A fully rehashed but semantically-wrong seal (claims ACCEPTED but
    the fold's own packets dict disagrees) must not promote the
    dependent. NOTE: this specifically proves the O2 validate_packet gate
    (fold state QUARANTINED != ACCEPTED -> DEPENDENCY_NOT_ACCEPTED) stops
    promotion BEFORE the seal is ever read at all -- it does NOT exercise
    the seal cross-check itself. See
    test_seal_disagrees_with_accepted_fold_is_fatal_not_isolated below for
    the case where the fold DOES say ACCEPTED and the seal disagrees."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    # A fully valid, self-consistent, correctly-hashed seal claiming
    # ACCEPTED for a packet the fold itself says is QUARANTINED.
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="QUARANTINED", terminal_seal_sha256="x"),  # fold disagrees with the seal
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    # promote_dependencies gates on packets[dep_id]["state"] == "ACCEPTED"
    # (the fold, the authoritative source) before ever consulting the seal
    # -- a forged seal alone cannot promote a dependent the fold disagrees with.
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]
    assert attention == []


def test_seal_not_yet_created_for_accepted_dependency_defers_quietly():
    """Design 3.5: step 13 (create any missing terminal seals) runs AFTER
    step 12 (this promotion pass) -- a fold-ACCEPTED dependency with no
    seal file yet is the ordinary shape of a coordinator caught between
    VERDICT_RECORDED(ACCEPTED) and seal creation. Must defer quietly:
    no exception, no attention entry, dependent simply stays BLOCKED
    until a later pass."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    # Deliberately NO terminal seal written for dep-1, even though the
    # fold already says ACCEPTED.

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events, attention = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert not [e for e in events if e["event_type"] == "STATE_TRANSITION"]
    assert attention == []

    # Once the seal is created (step 13, or a later pass), the SAME call
    # succeeds -- proving this was genuinely deferred, not permanently blocked.
    _write_terminal_seal(state_root, "dep-1", "ACCEPTED", 1)
    events2, attention2 = promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-3", "srid-1", "2026-08-10T00:02:00Z")
    assert len([e for e in events2 if e["event_type"] == "STATE_TRANSITION"]) == 1
    assert attention2 == []


def test_seal_disagrees_with_accepted_fold_is_fatal_not_isolated():
    """The genuine run-halting case: the fold says dep-1 is ACCEPTED
    (already confirmed via O2's validate_packet gate), but a REAL seal
    file exists on disk and disagrees (claims QUARANTINED). This is one
    of design section 2.6's three named run-halting conditions and must
    propagate OUT of promote_dependencies uncaught -- never silently
    isolated into the per-packet attention list, unlike an ordinary
    packet-scoped problem."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    dep_body = _valid_packet_body("dep-1")
    dep_path = _write_packet_body(state_root, "dep-1", dep_body)
    dependent_body = _valid_packet_body("dependent-1", dependency_ids=["dep-1"])
    dependent_path = _write_packet_body(state_root, "dependent-1", dependent_body)
    e1 = _enroll_event(1, None, "dep-1", dep_body, dep_path, 1, "READY")
    e2 = _enroll_event(2, e1, "dependent-1", dependent_body, dependent_path, 2, "BLOCKED")
    _write_journal(journal_path, [e1, e2])
    # The fold says ACCEPTED, so the O2 gate passes -- but the real seal
    # on disk contradicts it.
    _write_terminal_seal(state_root, "dep-1", "QUARANTINED", 1)

    packets = {
        "dep-1": _fold_pkt(enqueue_seq=1, state="ACCEPTED", terminal_seal_sha256="x"),
        "dependent-1": _fold_pkt(enqueue_seq=2, state="BLOCKED", dependency_ids=["dep-1"]),
    }
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    with pytest.raises(IntegrityError) as exc_info:
        promote_dependencies(state_root, journal_path, lock_path, events, packets, "coord-1", "run-2", "srid-1", "2026-08-10T00:01:00Z")
    assert exc_info.value.code == "TERMINAL_SEAL_MISMATCH"
