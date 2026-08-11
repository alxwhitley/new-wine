"""Crash-recovery TDD for O3-P2 durable store."""

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_coordinator.v1.recovery import (
    CoordinatorAlreadyRunning,
    IntegrityError,
    run_started_recovery,
)
from harness_coordinator.v1.store import (
    JournalChainBroken,
    JournalHeadMoved,
    atomic_replace,
    append_journal,
    read_journal,
    sweep_orphans,
)


def _hash_event(event: Dict[str, Any]) -> str:
    return compute_sha256(canonical_bytes(event, omit={"event_sha256"}))


def _make_run_payload(
    coordinator_id: str = "coord-1",
    run_id: str = "run-1",
    boot_id: str = "boot-1",
    hostname: str = "host-1",
    pid: int = 1,
    end_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "coordinator": {
            "coordinator_id": coordinator_id,
            "boot_id": boot_id,
            "hostname": hostname,
            "pid": pid,
        },
        "trust_roots": {
            "reviewer_sessions_path": "trust/reviewer_sessions.json",
            "reviewer_sessions_sha256": ZERO_SHA256,
            "provider_signals_path": "trust/provider_signals.json",
            "provider_signals_sha256": ZERO_SHA256,
        },
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
        "end_reason": end_reason,
        "end_detail": None,
        "disabled_lanes": [],
    }


def _make_packet_payload(
    packet_id: str = "pkt-1",
    lane: str = "kimi_implementation",
    dependency_ids: Optional[List[str]] = None,
    retry_limit: int = 2,
    sonnet_reassignment_allowed: bool = False,
    packet_path: str = "packets/pkt-1.json",
    enqueue_seq: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "packet_sha256": compute_sha256(canonical_bytes({"packet_id": packet_id})),
        "packet_path": packet_path,
        "lane": lane,
        "dependency_ids": dependency_ids or [],
        "sonnet_reassignment_allowed": sonnet_reassignment_allowed,
        "retry_limit": retry_limit,
        "enqueue_seq": enqueue_seq,
    }


def _make_attempt_payload(
    attempt: int = 1,
    lane: str = "kimi_implementation",
    worker_id: str = "worker-1",
    session_id: str = "session-1",
    provider: str = "kimi",
    model: str = "kimi-latest",
    claim_sha256: Optional[str] = None,
    worktree_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "attempt": attempt,
        "lane": lane,
        "worker": {
            "worker_id": worker_id,
            "session_id": session_id,
            "provider": provider,
            "model": model,
        },
        "claim_sha256": claim_sha256,
        "worktree_path": worktree_path,
    }


def _make_classification_payload(
    attempt_class: str = "INFRA_RETRYABLE",
    cause: str = "infra_retry",
    exit_code: Optional[int] = None,
    signal: Optional[int] = None,
    timed_out: bool = False,
) -> Dict[str, Any]:
    return {
        "attempt_class": attempt_class,
        "quarantine_reason": None,
        "human_required_reasons": [],
        "result_sha256": None,
        "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {
            "exit_code": exit_code,
            "signal": signal,
            "timed_out": timed_out,
            "result_present": False,
            "result_valid": False,
            "error_codes": [],
        },
    }


def _write_journal(journal_path: str, events: List[Dict[str, Any]]) -> None:
    with open(journal_path, "wb") as f:
        for event in events:
            f.write(canonical_bytes(event) + b"\n")


def _make_event(
    seq: int,
    event_type: str,
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    prev_event: Optional[Dict[str, Any]],
    event_id: Optional[str] = None,
    event_at: str = "2026-08-10T00:00:00Z",
    packet_id: Optional[str] = None,
    intent_id: Optional[str] = None,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    cause: str = "none",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event_id = event_id or f"evt-{seq}"
    payload = payload or {
        "packet": None,
        "attempt": None,
        "artifacts": [],
        "classification": None,
        "transition_detail": None,
        "recovery": None,
        "run": None,
        "report": None,
    }
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
        "payload": payload,
        "prev_event_sha256": prev_event["event_sha256"] if prev_event else ZERO_SHA256,
        "event_sha256": "",  # filled below
    }
    event["event_sha256"] = _hash_event(event)
    return event


def test_atomic_replace_writes_file_atomically():
    state_root = tempfile.mkdtemp()
    path = os.path.join(state_root, "queue.json")
    data = b'{"schema_version": 1}'
    atomic_replace(path, data, coordinator_id="coord-1", nonce="nonce-1")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == data
    # No tmp residue.
    assert not any(".tmp." in name for name in os.listdir(state_root))


def test_derived_queue_writer_orders_entries_by_enqueue_sequence():
    from harness_contracts.v1.queue_state import validate_queue
    from harness_coordinator.v1.recovery import _build_derived_queue

    def packet_state(enqueue_seq: int) -> Dict[str, Any]:
        return {
            "enqueue_seq": enqueue_seq,
            "state": "READY",
            "lane": "kimi_implementation",
            "dependency_ids": [],
            "packet_sha256": "a" * 64,
            "attempts_started": 0,
            "infra_retries_used": 0,
            "revise_cycles_used": 0,
            "revise_verdicts": 0,
            "reassignment_used": False,
            "open_attempt": None,
            "earliest_next_attempt_at": None,
            "last_event_seq": enqueue_seq,
            "terminal_seal_sha256": None,
        }

    queue = _build_derived_queue(
        {
            "a-later": packet_state(2),
            "z-first": packet_state(1),
        },
        "srid-1",
        None,
    )

    assert [entry["packet_id"] for entry in queue["entries"]] == [
        "z-first",
        "a-later",
    ]
    assert validate_queue(queue, state_root_id="srid-1")["valid"]


def test_folded_enrollment_order_produces_contract_valid_queue(tmp_path):
    from harness_contracts.v1.queue_state import validate_queue
    from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal

    events = []
    for seq, packet_id in ((1, "z-first"), (2, "a-later")):
        packet_payload = _make_packet_payload(
            packet_id=packet_id,
            packet_path=f"packets/{packet_id}.json",
            enqueue_seq=seq,
        )
        event = _make_event(
            seq,
            "PACKET_ENROLLED",
            "coord-1",
            "run-1",
            "srid-1",
            events[-1] if events else None,
            packet_id=packet_id,
            intent_id=f"enroll-{packet_id}-{seq}",
            to_state="READY",
            cause="enrollment",
            payload={
                "packet": packet_payload,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
            },
        )
        events.append(event)

    folded, _ = _fold_journal(str(tmp_path), events)
    queue = _build_derived_queue(folded, "srid-1", events[-1])

    assert [entry["packet_id"] for entry in queue["entries"]] == [
        "z-first",
        "a-later",
    ]
    assert validate_queue(queue, state_root_id="srid-1")["valid"]


def test_append_journal_appends_and_enforces_cas():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "journal.wlock")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    append_journal(journal_path, event1, lock_path, expected_head=None)

    events, torn = read_journal(journal_path)
    assert len(events) == 1
    assert torn is None
    assert events[0]["seq"] == 1

    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=events[0],
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    append_journal(journal_path, event2, lock_path, expected_head=events[0])

    events, torn = read_journal(journal_path)
    assert len(events) == 2
    assert events[1]["seq"] == 2


def test_append_journal_raises_when_head_moved():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "journal.wlock")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    append_journal(journal_path, event1, lock_path, expected_head=None)

    # Attempt to append seq=1 again with expected_head=None should fail because head is now event1.
    with pytest.raises(JournalHeadMoved):
        append_journal(journal_path, event1, lock_path, expected_head=None)


def test_read_journal_empty():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    events, torn = read_journal(journal_path)
    assert events == []
    assert torn is None


def test_read_journal_torn_tail_truncated():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "journal.wlock")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    append_journal(journal_path, event1, lock_path, expected_head=None)

    with open(journal_path, "ab") as f:
        f.write(b'{"schema_version": 1, "seq": 2')  # truncated mid-JSON, no newline

    events, torn = read_journal(journal_path)
    assert len(events) == 1
    assert torn is not None
    assert torn.startswith(b'{"schema_version": 1, "seq": 2')


def test_read_journal_torn_tail_nul_padded():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "journal.wlock")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    append_journal(journal_path, event1, lock_path, expected_head=None)

    # NUL-padded final line, newline-terminated.
    with open(journal_path, "ab") as f:
        f.write(b'{"schema_version": 1, "seq": 2, \x00\x00\x00}\n')

    events, torn = read_journal(journal_path)
    assert len(events) == 1
    assert torn is not None


def test_read_journal_mid_file_corruption_raises():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "journal.wlock")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    append_journal(journal_path, event1, lock_path, expected_head=None)
    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    append_journal(journal_path, event2, lock_path, expected_head=event1)

    # Corrupt the first event's payload (mid-file).
    with open(journal_path, "rb") as f:
        raw = f.read()
    lines = raw.splitlines(keepends=True)
    corrupted = lines[0].replace(b"RUN_STARTED", b"BAD_TYPE")
    with open(journal_path, "wb") as f:
        f.write(corrupted + lines[1])

    with pytest.raises(JournalChainBroken):
        read_journal(journal_path)


def test_read_journal_deleted_mid_line_raises():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    event3 = _make_event(
        seq=3,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-2",
        state_root_id="srid-1",
        prev_event=event2,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event4 = _make_event(
        seq=4,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-2",
        state_root_id="srid-1",
        prev_event=event3,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event1) + b"\n" + canonical_bytes(event2) + b"\n" + canonical_bytes(event3) + b"\n" + canonical_bytes(event4) + b"\n")

    # Delete the middle event: event3's prev hash will no longer match event1.
    with open(journal_path, "rb") as f:
        raw = f.read()
    lines = raw.splitlines(keepends=True)
    with open(journal_path, "wb") as f:
        f.write(lines[0] + lines[2] + lines[3])

    with pytest.raises(JournalChainBroken):
        read_journal(journal_path)


def test_read_journal_duplicate_seq_raises():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    # Forge an event with duplicate seq but valid chain hash.
    event3 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event2,
        event_id="evt-3",
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    event4 = _make_event(
        seq=3,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-2",
        state_root_id="srid-1",
        prev_event=event3,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event1) + b"\n" + canonical_bytes(event2) + b"\n" + canonical_bytes(event3) + b"\n" + canonical_bytes(event4) + b"\n")

    with pytest.raises(JournalChainBroken):
        read_journal(journal_path)


def test_read_journal_bad_genesis_hash_on_final_line_is_torn_tail():
    """Defect 6: position, not the shape of the damage, is the sole
    discriminator (design 3.3) -- a validation failure on the ONLY/final
    line is a recoverable torn tail even with no valid prefix, whether
    caused by truncation, NUL-fill, or (as here) a malformed genesis
    hash. Only a MID-file failure is a hard, unrepairable
    JournalChainBroken -- see test_read_journal_mid_file_corruption_raises
    and test_read_journal_deleted_mid_line_raises, both unchanged."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event["prev_event_sha256"] = "1" * 64
    event["event_sha256"] = _hash_event(event)

    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event) + b"\n")

    events, torn = read_journal(journal_path)
    assert events == []
    assert torn is not None


def test_read_journal_wrong_event_sha256_on_final_line_is_torn_tail():
    """Same discriminator as above, for a tampered event_sha256."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event["event_sha256"] = "1" * 64

    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event) + b"\n")

    events, torn = read_journal(journal_path)
    assert events == []
    assert torn is not None


def test_read_journal_mid_file_failure_still_hard_fails_even_as_only_content():
    """The position discriminator cuts both ways: a MID-file failure is
    never torn-tail-recoverable, even when it's the only real content
    (i.e., failing at index 0 of a 2-line file where index 0 is not the
    last non-empty line)."""
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event1["event_sha256"] = "1" * 64  # mid-file (not final) corruption
    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )

    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event1) + b"\n" + canonical_bytes(event2) + b"\n")

    with pytest.raises(JournalChainBroken):
        read_journal(journal_path)


def test_read_journal_chronology_violation_raises():
    state_root = tempfile.mkdtemp()
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        event_at="2026-08-10T00:00:01Z",
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    event2 = _make_event(
        seq=2,
        event_type="RUN_ENDED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        event_at="2026-08-10T00:00:00Z",
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(end_reason="normal"), "report": None},
    )
    event3 = _make_event(
        seq=3,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-2",
        state_root_id="srid-1",
        prev_event=event2,
        event_at="2026-08-10T00:00:02Z",
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    with open(journal_path, "wb") as f:
        f.write(canonical_bytes(event1) + b"\n" + canonical_bytes(event2) + b"\n" + canonical_bytes(event3) + b"\n")

    with pytest.raises(JournalChainBroken):
        read_journal(journal_path)


def _make_ctx(
    coordinator_id: str = "coord-1",
    boot_id: str = "boot-1",
    hostname: str = "host-1",
    pid: int = 1,
    live_coordinator_ids=None,
):
    return {
        "coordinator_id": coordinator_id,
        "hostname": hostname,
        "boot_id": boot_id,
        "pid": pid,
        "live_coordinator_ids": live_coordinator_ids or set(),
        "now": "2026-08-10T00:00:00Z",
    }


def test_recovery_singleton_flock_refuses_second_start():
    import fcntl

    state_root = tempfile.mkdtemp()
    singleton_path = os.path.join(state_root, "locks", "coordinator.singleton")
    os.makedirs(os.path.dirname(singleton_path), exist_ok=True)
    fd = os.open(singleton_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        ctx = _make_ctx(pid=1)
        with pytest.raises(CoordinatorAlreadyRunning):
            run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")
        # No files should have been written.
        assert not os.path.exists(os.path.join(state_root, "MANIFEST.json"))
        assert not os.path.exists(os.path.join(state_root, "journal.ndjson"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_sweep_orphans_moves_tmp_files_preserving_structure():
    state_root = tempfile.mkdtemp()
    nested = os.path.join(state_root, "state")
    os.makedirs(nested)
    tmp_path = os.path.join(nested, "queue.json.tmp.coord-1.1234.nonce-1")
    with open(tmp_path, "wb") as f:
        f.write(b"orphan")

    moved = sweep_orphans(state_root, "run-1")
    assert moved == ["state/queue.json.tmp.coord-1.1234.nonce-1"]
    assert not os.path.exists(tmp_path)
    swept = os.path.join(state_root, "sweep", "run-1", "state", "queue.json.tmp.coord-1.1234.nonce-1")
    assert os.path.exists(swept)
    with open(swept, "rb") as f:
        assert f.read() == b"orphan"


def _write_trust_roots(state_root: str) -> None:
    """Provision the two operator-owned trust registries.

    Defect 8: recovery now fails closed if these are missing (they are
    never fabricated by the coordinator), so any test exercising a real
    ``run_started_recovery`` call must provision them first, exactly as a
    real operator would before ever starting a coordinator.
    """
    trust_dir = os.path.join(state_root, "trust")
    os.makedirs(trust_dir, exist_ok=True)

    reviewer = {"schema_version": 1, "sessions": [], "registry_sha256": ""}
    reviewer["registry_sha256"] = compute_sha256(canonical_bytes(reviewer, omit={"registry_sha256"}))
    with open(os.path.join(trust_dir, "reviewer_sessions.json"), "wb") as f:
        f.write(canonical_bytes(reviewer))

    provider = {"schema_version": 1, "registry_id": "empty", "providers": {}, "registry_sha256": ""}
    provider["registry_sha256"] = compute_sha256(canonical_bytes(provider, omit={"registry_sha256"}))
    with open(os.path.join(trust_dir, "provider_signals.json"), "wb") as f:
        f.write(canonical_bytes(provider))


def _write_manifest(state_root: str, state_root_id: str, now: str = "2026-08-10T00:00:00Z") -> None:
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
    manifest_path = os.path.join(state_root, "MANIFEST.json")
    atomic_replace(manifest_path, canonical_bytes(manifest), coordinator_id="coord-1", nonce="init")


def _write_queue_with_intent(
    state_root: str,
    state_root_id: str,
    intent_id: str,
    packet_id: str,
    stage: str = "claim",
    journal_last_seq: int = 0,
) -> None:
    queue = {
        "schema_version": 1,
        "state_root_id": state_root_id,
        "derived_from": {
            "journal_last_seq": journal_last_seq,
            "journal_last_event_sha256": ZERO_SHA256,
        },
        "entries": [],
        "pending_intents": [
            {
                "intent_id": intent_id,
                "packet_id": packet_id,
                "stage": stage,
                "created_at": "2026-08-10T00:00:00Z",
                "coordinator_id": "coord-1",
                "run_id": "run-1",
                "boot_id": "boot-1",
                "pid": 1234,
            }
        ],
        "queue_sha256": "",
    }
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    queue_path = os.path.join(state_root, "queue.json")
    atomic_replace(queue_path, canonical_bytes(queue), coordinator_id="coord-1", nonce="init")


def test_recovery_b1_lock_created_queue_not_written_reclaimed():
    """Crash 1a: lock exists, no queue.json, no journal event."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    from harness_coordinator.v1.locks import create_claim
    from harness_contracts.v1.canonical import canonical_bytes, compute_sha256

    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1,
        "packet_id": "pkt-1",
        "intent_id": "intent-pkt-1",
        "stage": "claim",
        "attempt": 1,
        "coordinator_id": "coord-1",
        "run_id": "run-1",
        "hostname": "host-1",
        "boot_id": "old-boot",
        "pid": 1234,
        "acquired_at": "2026-08-10T00:00:00Z",
        "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60,
        "lane": "kimi_implementation",
        "worktree_path": None,
        "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)

    ctx = _make_ctx(pid=1)
    run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")

    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"))
    types = [e["event_type"] for e in events]
    assert "LOCK_RECLAIMED" in types
    assert "INTENT_ABANDONED" in types
    abandoned = [e for e in events if e["event_type"] == "INTENT_ABANDONED"][0]
    assert abandoned["payload"]["recovery"]["abandoned_at_stage"] == "lock_acquired"
    assert not os.path.exists(lock_path)
    assert os.path.exists(os.path.join(state_root, "locks", "reclaimed", "run-2", "pkt-1.lock.json"))


def test_recovery_b2_pending_intent_no_journal_event_rolled_back():
    """Crash 2: pending_intent in queue.json but never committed to journal."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    # Enroll a packet so the fold has something to protect.
    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    packet_payload["enqueue_seq"] = 2
    event2 = _make_event(
        seq=2,
        event_type="PACKET_ENROLLED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        packet_id="pkt-1",
        intent_id="enroll-pkt-1",
        to_state="READY",
        cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2])

    # Write a queue.json with a pending intent that never reached the journal.
    _write_queue_with_intent(state_root, "srid-1", intent_id="intent-pkt-1", packet_id="pkt-1", stage="claim", journal_last_seq=2)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")

    events, _ = read_journal(journal_path)
    abandon_events = [e for e in events if e["event_type"] == "INTENT_ABANDONED"]
    assert len(abandon_events) == 1
    assert abandon_events[0]["payload"]["recovery"]["abandoned_at_stage"] == "queue_intent_written"
    # Packet state unchanged; attempts_started unchanged.
    assert report.derived_states["pkt-1"]["state"] == "READY"
    assert report.derived_states["pkt-1"]["attempts_started"] == 0


def test_recovery_b3_attempt_started_journaled_projections_stale():
    """Crash 3: journal has ATTEMPT_STARTED; queue/state caches stale/missing."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    packet_payload["enqueue_seq"] = 2
    event2 = _make_event(
        seq=2,
        event_type="PACKET_ENROLLED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event1,
        packet_id="pkt-1",
        intent_id="enroll-pkt-1",
        to_state="READY",
        cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    attempt_payload = _make_attempt_payload(attempt=1, lane="kimi_implementation")
    event3 = _make_event(
        seq=3,
        event_type="ATTEMPT_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=event2,
        packet_id="pkt-1",
        intent_id="attempt-pkt-1-1",
        from_state="READY",
        to_state="RUNNING",
        cause="claim_committed",
        payload={"packet": None, "attempt": attempt_payload, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2, event3])

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")

    assert report.derived_states["pkt-1"]["state"] == "RUNNING"
    assert report.derived_states["pkt-1"]["attempts_started"] == 1
    assert report.derived_states["pkt-1"]["open_attempt"] == 1
    entry = report.derived_queue["entries"][0]
    assert entry["packet_id"] == "pkt-1"
    assert entry["attempts_started"] == 1
    assert entry["state"] == "RUNNING"


def test_recovery_b7_orphan_tmp_swept_during_recovery():
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    nested = os.path.join(state_root, "state")
    os.makedirs(nested)
    tmp_path = os.path.join(nested, "queue.json.tmp.coord-1.1234.nonce-1")
    with open(tmp_path, "wb") as f:
        f.write(b"orphan")

    ctx = _make_ctx(pid=1)
    run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")

    assert not os.path.exists(tmp_path)
    swept = os.path.join(state_root, "sweep", "run-1", "state", "queue.json.tmp.coord-1.1234.nonce-1")
    assert os.path.exists(swept)


def test_recovery_a1_torn_tail_truncated_recovered():
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    _write_journal(journal_path, [event1])
    with open(journal_path, "ab") as f:
        f.write(b'{"schema_version": 1, "seq": 2')  # truncated mid-JSON

    ctx = _make_ctx(pid=1)
    run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")

    events, _ = read_journal(journal_path)
    types = [e["event_type"] for e in events]
    assert "JOURNAL_TAIL_TRUNCATED" in types
    torn = [e for e in events if e["event_type"] == "JOURNAL_TAIL_TRUNCATED"][0]
    assert torn["payload"]["recovery"]["truncation"]["valid_prefix_last_seq"] == 1
    assert os.path.exists(os.path.join(state_root, "journal.torn", "run-2.bytes"))


def test_recovery_defect1_fold_rejects_reopening_accepted_packet():
    """Defect 1: the fold must compare an event's declared from_state to
    the packet's ACTUAL current fold state, not just check the edge is
    abstractly legal. A packet that reaches ACCEPTED and then gets a
    forged ATTEMPT_STARTED(READY->RUNNING) must not silently re-run."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    event3 = _make_event(
        seq=3, event_type="ATTEMPT_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event2, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    event4 = _make_event(
        seq=4, event_type="ATTEMPT_FINISHED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event3, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=1), "artifacts": [], "classification": _make_classification_payload(attempt_class="COMPLETED_PENDING_REVIEW", cause="result_recorded"), "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    event5 = _make_event(
        seq=5, event_type="VERDICT_RECORDED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event4, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
        from_state="REVIEW", to_state="ACCEPTED", cause="verdict_accept",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    # Forged: re-opens the now-ACCEPTED packet with a second ATTEMPT_STARTED
    # claiming to come from READY (an abstractly-legal edge in isolation,
    # but the packet is not actually in READY).
    event6 = _make_event(
        seq=6, event_type="ATTEMPT_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event5, packet_id="pkt-1", intent_id="attempt-pkt-1-2",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=2), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2, event3, event4, event5, event6])

    ctx = _make_ctx(pid=1)
    with pytest.raises(IntegrityError):
        run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")


def test_recovery_defect2_singleton_flock_persists_past_successful_return():
    """Defect 2: design 3.5 holds the singleton flock from step 1 through
    step 14 (entering the scheduling loop). P2's own scope stops at step
    9, but a successful recovery must NOT release the lock on return --
    the caller (report.release_singleton()) becomes responsible. Proven
    by attempting a second full recovery against the same state root
    before releasing the first's report."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")
    try:
        with pytest.raises(CoordinatorAlreadyRunning):
            run_started_recovery(state_root, "coord-2", "run-2", ctx, "2026-08-10T00:00:01Z")
    finally:
        report.release_singleton()

    # Once released, a fresh recovery succeeds.
    report2 = run_started_recovery(state_root, "coord-2", "run-2", ctx, "2026-08-10T00:00:02Z")
    report2.release_singleton()


def test_recovery_b10_corrupt_queue_json_does_not_abort_run():
    """Defect 3 / fixture B10: queue.json is a rebuildable cache (D0.2) --
    corruption must never abort the run."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")

    # Unparseable.
    with open(os.path.join(state_root, "queue.json"), "wb") as f:
        f.write(b'{"schema_version": 1, "entries": [')  # truncated

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")
    report.release_singleton()
    assert report.derived_queue["entries"] == []

    # Parseable but schema-invalid.
    with open(os.path.join(state_root, "queue.json"), "wb") as f:
        f.write(b'{"schema_version": 1, "bogus_field": true}')

    report2 = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    report2.release_singleton()
    assert report2.derived_queue["entries"] == []


def test_recovery_defect4_crash2_with_lock_present_correctly_staged():
    """Defect 4: design 3.4's write order means every real claim-stage
    crash-2 ALSO has a lock file present. The stage must come from
    whether queue.json's pending_intents contains the intent, not from
    lock presence alone."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2])

    # Lock file present (per design 3.4's write order) AND a matching
    # queue.json pending_intent -- the true crash-2 signature.
    from harness_coordinator.v1.locks import create_claim
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1, "packet_id": "pkt-1", "intent_id": "attempt-pkt-1-1",
        "stage": "claim", "attempt": 1, "coordinator_id": "coord-1", "run_id": "run-1",
        "hostname": "host-1", "boot_id": "old-boot", "pid": 1234,
        "acquired_at": "2026-08-10T00:00:00Z", "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60, "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)
    _write_queue_with_intent(state_root, "srid-1", intent_id="attempt-pkt-1-1", packet_id="pkt-1", stage="claim", journal_last_seq=2)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    try:
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id="srid-1")
        abandon_events = [e for e in events if e["event_type"] == "INTENT_ABANDONED"]
        assert len(abandon_events) == 1
        assert abandon_events[0]["payload"]["recovery"]["abandoned_at_stage"] == "queue_intent_written"
        assert report.abandoned_intents or report.reclaimed_locks  # some resolution occurred
    finally:
        report.release_singleton()


def test_recovery_defect5_committed_intent_lock_not_abandoned():
    """Defect 5: a lock backing an ALREADY-COMMITTED intent (crash point
    3 -- a genuinely open, in-progress attempt) must be left entirely
    alone, never abandoned/reclaimed. Resolving it is O3-P3's scope."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    event3 = _make_event(
        seq=3, event_type="ATTEMPT_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event2, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2, event3])

    from harness_coordinator.v1.locks import create_claim
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1, "packet_id": "pkt-1", "intent_id": "attempt-pkt-1-1",
        "stage": "claim", "attempt": 1, "coordinator_id": "coord-1", "run_id": "run-1",
        "hostname": "host-1", "boot_id": "old-boot", "pid": 1234,
        "acquired_at": "2026-08-10T00:00:00Z", "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60, "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    try:
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id="srid-1")
        types = [e["event_type"] for e in events]
        assert "INTENT_ABANDONED" not in types
        assert "LOCK_RECLAIMED" not in types
        assert os.path.exists(lock_path)  # untouched, still in place for P3
        assert report.derived_states["pkt-1"]["state"] == "RUNNING"
    finally:
        report.release_singleton()


def test_recovery_defect7_self_owned_lock_not_force_reclaimed_via_pending_intent():
    """Defect 7: step 9's pending-intent lock cleanup must call
    classify_claim for real, never a hardcoded classification -- a lock
    that genuinely classifies SELF_OWNED must not be reclaimed."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2])

    # A lock whose coordinator_id/pid match the CURRENT coordinator's own
    # trusted_process_context exactly -> classify_claim returns SELF_OWNED.
    ctx = _make_ctx(coordinator_id="coord-1", boot_id="boot-1", hostname="host-1", pid=1)
    from harness_coordinator.v1.locks import create_claim
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1, "packet_id": "pkt-1", "intent_id": "attempt-pkt-1-1",
        "stage": "claim", "attempt": 1, "coordinator_id": "coord-1", "run_id": "run-1",
        "hostname": "host-1", "boot_id": "boot-1", "pid": 1,
        "acquired_at": "2026-08-10T00:00:00Z", "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60, "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)

    # A pending intent for the SAME packet AND the SAME intent_id as the
    # lock -- so step 9's intent_id-matching guard does not itself skip
    # this lock, and classify_claim's SELF_OWNED verdict is genuinely the
    # thing preventing the reclaim (not a non-matching intent_id doing it
    # vacuously).
    _write_queue_with_intent(state_root, "srid-1", intent_id="attempt-pkt-1-1", packet_id="pkt-1", stage="claim", journal_last_seq=2)

    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    try:
        # SELF_OWNED means step 8 must also leave it alone (raises nothing,
        # reclaims nothing) -- the lock survives untouched throughout.
        assert os.path.exists(lock_path)
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id="srid-1")
        assert "LOCK_RECLAIMED" not in [e["event_type"] for e in events]
    finally:
        report.release_singleton()


def test_recovery_round2_step9_never_reclaims_unrelated_committed_intents_lock():
    """Opus round-2 finding 1: _resolve_pending_intents must select the
    lock to reclaim by the ABANDONED intent's own intent_id, never by
    packet_id alone -- a packet can have a genuinely live lock (backing a
    committed, still-open ATTEMPT_STARTED) at the same canonical path
    while an UNRELATED pending intent for that same packet is what's
    actually being abandoned. Reproduces the exact scenario: a RUNNING
    packet with a committed attempt, plus an unrelated uncommitted
    'attempt_finish'-stage pending intent for the same packet."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    # The committed, genuinely open attempt -- intent_id "attempt-pkt-1-1".
    event3 = _make_event(
        seq=3, event_type="ATTEMPT_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event2, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _make_attempt_payload(attempt=1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2, event3])

    # The lock on disk backs the COMMITTED intent (genuinely live).
    from harness_coordinator.v1.locks import create_claim
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1, "packet_id": "pkt-1", "intent_id": "attempt-pkt-1-1",
        "stage": "claim", "attempt": 1, "coordinator_id": "coord-1", "run_id": "run-1",
        "hostname": "host-1", "boot_id": "old-boot", "pid": 1234,
        "acquired_at": "2026-08-10T00:00:00Z", "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60, "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)

    # An UNRELATED pending intent for the SAME packet -- a different
    # intent_id, from queue.json's "attempt_finish" stage, which never
    # creates a lock of its own.
    _write_queue_with_intent(state_root, "srid-1", intent_id="finish-pkt-1-1", packet_id="pkt-1", stage="attempt_finish", journal_last_seq=3)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    try:
        events, _ = read_journal(journal_path, state_root_id="srid-1")
        assert "LOCK_RECLAIMED" not in [e["event_type"] for e in events]
        assert "finish-pkt-1-1" in [e.get("intent_id") for e in events if e["event_type"] == "INTENT_ABANDONED"]
        assert report.reclaimed_locks == []
        # The committed attempt's claim lock is untouched -- still at its
        # canonical path, still the evidence P3 needs for open-attempt
        # resolution.
        assert os.path.exists(lock_path)
        with open(lock_path, "rb") as f:
            on_disk = json.loads(f.read().decode("utf-8"))
        assert on_disk["intent_id"] == "attempt-pkt-1-1"
        assert report.derived_states["pkt-1"]["state"] == "RUNNING"
        assert report.derived_states["pkt-1"]["open_attempt"] == 1
    finally:
        report.release_singleton()


def test_recovery_matching_stale_lock_reclaimed_with_journal_record():
    """NOTE: step 8 (_reconcile_locks) exhaustively scans every lock file
    on disk for STALE_* classifications before step 9 ever runs, and
    nothing creates new locks in between -- so this scenario (a stale
    lock whose intent_id matches an also-pending intent) is actually
    resolved by step 8, and step 9's own reclaim block never fires here
    (verified: step 9 returns ([], []) in this exact case). This is a
    regression test for the reclaim-with-journal-record guarantee in
    general (LOCK_RECLAIMED before the move, reclaimed_locks populated),
    not specifically a step-9 test -- see
    test_recovery_round2_step9_never_reclaims_unrelated_committed_intents_lock
    for the test that actually isolates step 9's own guard."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    packet_payload = _make_packet_payload(packet_id="pkt-1", enqueue_seq=2)
    event2 = _make_event(
        seq=2, event_type="PACKET_ENROLLED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-1", prev_event=event1, packet_id="pkt-1", intent_id="enroll-pkt-1",
        to_state="READY", cause="enrollment",
        payload={"packet": packet_payload, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    _write_journal(journal_path, [event1, event2])

    # A stale (prior-boot) lock whose intent_id matches the pending intent
    # exactly, and which was never committed to the journal.
    from harness_coordinator.v1.locks import create_claim
    lock_path = os.path.join(state_root, "locks", "pkt-1.lock.json")
    record = {
        "schema_version": 1, "packet_id": "pkt-1", "intent_id": "attempt-pkt-1-1",
        "stage": "claim", "attempt": 1, "coordinator_id": "coord-1", "run_id": "run-1",
        "hostname": "host-1", "boot_id": "old-boot", "pid": 1234,
        "acquired_at": "2026-08-10T00:00:00Z", "heartbeat_at": "2026-08-10T00:00:00Z",
        "lease_seconds": 60, "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    create_claim(lock_path, record)
    _write_queue_with_intent(state_root, "srid-1", intent_id="attempt-pkt-1-1", packet_id="pkt-1", stage="claim", journal_last_seq=2)

    ctx = _make_ctx(pid=1)
    report = run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")
    try:
        events, _ = read_journal(journal_path, state_root_id="srid-1")
        reclaim_events = [e for e in events if e["event_type"] == "LOCK_RECLAIMED"]
        assert len(reclaim_events) == 1
        assert reclaim_events[0]["payload"]["recovery"]["prior_claim"]["classification"] == "STALE_PRIOR_BOOT"
        assert "pkt-1" in report.reclaimed_locks
        assert not os.path.exists(lock_path)
        assert os.path.exists(os.path.join(state_root, "locks", "reclaimed", "run-2", "pkt-1.lock.json"))
    finally:
        report.release_singleton()


def test_recovery_defect8_missing_trust_registry_fails_closed_no_fabrication():
    """Defect 8: trust registries are operator-owned; recovery must
    refuse to start on a fresh state root rather than fabricating
    defaults and attesting to them."""
    state_root = tempfile.mkdtemp()
    # Deliberately do NOT call _write_trust_roots.
    ctx = _make_ctx(pid=1)
    with pytest.raises(IntegrityError):
        run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")
    assert not os.path.exists(os.path.join(state_root, "trust", "reviewer_sessions.json"))
    assert not os.path.exists(os.path.join(state_root, "trust", "provider_signals.json"))


def test_recovery_defect9_tampered_manifest_self_hash_rejected():
    """Defect 9: MANIFEST.json's own canonical self-hash must be verified
    before trusting its contents."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")

    manifest_path = os.path.join(state_root, "MANIFEST.json")
    with open(manifest_path, "rb") as f:
        manifest = json.loads(f.read().decode("utf-8"))
    manifest["state_root_id"] = "srid-TAMPERED"  # self-hash now stale
    with open(manifest_path, "wb") as f:
        f.write(canonical_bytes(manifest))

    ctx = _make_ctx(pid=1)
    with pytest.raises(IntegrityError):
        run_started_recovery(state_root, "coord-1", "run-1", ctx, "2026-08-10T00:00:00Z")


def test_recovery_defect9_journal_state_root_id_mismatch_rejected():
    """Defect 9: a journal whose events carry a different state_root_id
    than the MANIFEST's must be rejected, not folded cleanly."""
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-MINE")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1, event_type="RUN_STARTED", coordinator_id="coord-1", run_id="run-1",
        state_root_id="srid-SOMEONE-ELSE", prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    _write_journal(journal_path, [event1])

    ctx = _make_ctx(pid=1)
    with pytest.raises(JournalChainBroken):
        run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")


def test_atomic_replace_does_not_delete_foreign_in_flight_tmp_file():
    """Defect 10: an EEXIST from another writer's in-flight tmp file must
    never be deleted by the call that failed to create it."""
    state_root = tempfile.mkdtemp()
    path = os.path.join(state_root, "queue.json")
    tmp = f"{path}.tmp.coord-1.{os.getpid()}.nonce-1"
    with open(tmp, "wb") as f:
        f.write(b"someone-elses-in-flight-bytes")

    with pytest.raises(FileExistsError):
        atomic_replace(path, b'{"schema_version": 1}', coordinator_id="coord-1", nonce="nonce-1")

    assert os.path.exists(tmp)
    with open(tmp, "rb") as f:
        assert f.read() == b"someone-elses-in-flight-bytes"


def test_recovery_a2_torn_tail_nul_padded_recovered():
    state_root = tempfile.mkdtemp()
    _write_trust_roots(state_root)
    _write_manifest(state_root, "srid-1")
    journal_path = os.path.join(state_root, "journal.ndjson")

    event1 = _make_event(
        seq=1,
        event_type="RUN_STARTED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _make_run_payload(), "report": None},
    )
    _write_journal(journal_path, [event1])
    with open(journal_path, "ab") as f:
        f.write(b'{"schema_version": 1, "seq": 2, \x00\x00\x00}\n')  # NUL-padded, newline-terminated

    ctx = _make_ctx(pid=1)
    run_started_recovery(state_root, "coord-1", "run-2", ctx, "2026-08-10T00:00:01Z")

    events, _ = read_journal(journal_path)
    types = [e["event_type"] for e in events]
    assert "JOURNAL_TAIL_TRUNCATED" in types
    assert os.path.exists(os.path.join(state_root, "journal.torn", "run-2.bytes"))
