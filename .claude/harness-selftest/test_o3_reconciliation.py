"""O3-P4 TDD: reconciliation report assembly and scheduling replay."""

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_coordinator.v1.cli import main as cli_main
from harness_coordinator.v1.cli import run_reconcile, run_replay
from harness_coordinator.v1.reconcile import build_reconciliation_report, emit_reconciliation_report
from harness_coordinator.v1.recovery import IntegrityError
from harness_coordinator.v1.replay_schedule import replay_schedule
from harness_coordinator.v1.store import JournalChainBroken, append_journal, atomic_replace, read_journal


def _hash_event(event: Dict[str, Any]) -> str:
    return compute_sha256(canonical_bytes(event, omit={"event_sha256"}))


def _make_event(
    seq, event_type, coordinator_id="coord-1", run_id="run-1", state_root_id="srid-1",
    prev_event=None, event_id=None, event_at="2026-08-10T00:00:00Z", packet_id=None,
    intent_id=None, from_state=None, to_state=None, cause="none", payload=None,
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
    os.makedirs(os.path.join(os.path.dirname(journal_path), "locks"), exist_ok=True)
    with open(journal_path, "wb") as f:
        for event in events:
            f.write(canonical_bytes(event) + b"\n")


def _run_payload() -> Dict[str, Any]:
    return {
        "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1},
        "trust_roots": {"reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0" * 64, "provider_signals_path": "y", "provider_signals_sha256": "0" * 64},
        "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
        "end_reason": None, "end_detail": None, "disabled_lanes": [],
    }


def _packet_payload(packet_id: str, enqueue_seq: int, lane: str = "kimi_implementation", retry_limit: int = 2) -> Dict[str, Any]:
    return {
        "packet_sha256": compute_sha256(canonical_bytes({"packet_id": packet_id})),
        "packet_path": f"packets/{packet_id}.json",
        "lane": lane,
        "dependency_ids": [],
        "sonnet_reassignment_allowed": False,
        "retry_limit": retry_limit,
        "enqueue_seq": enqueue_seq,
    }


def _attempt_payload(attempt: int = 1) -> Dict[str, Any]:
    return {
        "attempt": attempt, "lane": "kimi_implementation",
        "worker": {"worker_id": "w1", "session_id": "s1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "claim_sha256": None, "worktree_path": None,
    }


def _write_manifest(state_root: str, state_root_id: str = "srid-1") -> None:
    manifest = {
        "schema_version": 1,
        "state_root_id": state_root_id,
        "created_at": "2026-08-10T00:00:00Z",
        "contract_versions": {
            "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
            "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
            "reassignment": 1, "reconciliation": 1,
        },
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"}))
    with open(os.path.join(state_root, "MANIFEST.json"), "wb") as f:
        f.write(canonical_bytes(manifest))


def _new_state_root(state_root_id: str = "srid-1") -> str:
    """A fresh tempdir with a valid MANIFEST.json already in place --
    build_reconciliation_report now requires this to exist and agree
    with the caller's expected state_root_id before reading anything
    else (H2's fix: a missing/wrong-id MANIFEST is a real finding, not
    silently treated as an empty-and-healthy state root)."""
    state_root = tempfile.mkdtemp()
    _write_manifest(state_root, state_root_id)
    return state_root


def _write_terminal_seal(state_root: str, packet_id: str, terminal_state: str, seq: int) -> None:
    seal = {
        "schema_version": 1, "packet_id": packet_id, "packet_sha256": "0" * 64,
        "terminal_state": terminal_state, "sealing_event_seq": seq,
        "sealing_event_sha256": "0" * 64, "sealed_at": "2026-08-10T00:00:00Z",
        "quarantine_reason": "contract_invalid" if terminal_state == "QUARANTINED" else None,
        "human_required_reasons": ["worker_human_required"] if terminal_state == "HUMAN_REQUIRED" else [],
        "upstream_digests": {"packet_sha256": "0" * 64, "result_sha256": "0" * 64, "verdict_sha256": "0" * 64, "bundle_sha256": "0" * 64} if terminal_state == "ACCEPTED" else None,
    }
    seal["seal_sha256"] = compute_sha256(canonical_bytes(seal, omit={"seal_sha256"}))
    seal_dir = os.path.join(state_root, "state", "terminal")
    os.makedirs(seal_dir, exist_ok=True)
    with open(os.path.join(seal_dir, f"{packet_id}.seal.json"), "wb") as f:
        f.write(canonical_bytes(seal))


def _accepted_packet_journal(packet_id: str, enqueue_seq: int, start_seq: int, prev_event) -> List[Dict[str, Any]]:
    """A full, legitimate enroll -> attempt -> finish -> verdict -> ACCEPTED sequence."""
    events = []
    e = _make_event(start_seq, "PACKET_ENROLLED", prev_event=prev_event, packet_id=packet_id,
                     intent_id=f"enroll-{packet_id}", to_state="READY", cause="enrollment",
                     payload={"packet": _packet_payload(packet_id, enqueue_seq), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e); prev_event = e
    e = _make_event(start_seq + 1, "ATTEMPT_STARTED", prev_event=prev_event, packet_id=packet_id,
                     intent_id=f"attempt-{packet_id}-1", from_state="READY", to_state="RUNNING", cause="claim_committed",
                     payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e); prev_event = e
    e = _make_event(start_seq + 2, "ATTEMPT_FINISHED", prev_event=prev_event, packet_id=packet_id,
                     intent_id=f"attempt-{packet_id}-1", from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
                     payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [],
                              "classification": {"attempt_class": "COMPLETED_PENDING_REVIEW", "quarantine_reason": None, "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": 0, "signal": None, "timed_out": False, "result_present": True, "result_valid": True, "error_codes": []}},
                              "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e); prev_event = e
    e = _make_event(start_seq + 3, "VERDICT_RECORDED", prev_event=prev_event, packet_id=packet_id,
                     intent_id=f"attempt-{packet_id}-1", from_state="REVIEW", to_state="ACCEPTED", cause="verdict_accept",
                     payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e)
    return events


def test_build_reconciliation_report_end_to_end_healthy_state():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")

    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "ACCEPTED", 6)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")

    assert report["inventory_total"] == 1
    assert report["by_state"]["ACCEPTED"] == 1
    assert report["by_state"]["READY"] == 0
    assert sum(report["by_state"].values()) == report["inventory_total"]
    assert report["reconciliation"]["all_invariants_passed"] is True
    assert report["integrity"]["journal_chain_valid"] is True
    assert report["integrity"]["seal_mismatches"] == []
    assert report["packets"][0]["packet_id"] == "pkt-1"

    from harness_contracts.v1.reconciliation import validate_reconciliation_report
    result = validate_reconciliation_report(report)
    assert result["valid"], result["errors"]


def test_report_is_deterministic_content_hash_stable_identity_fields_free():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "ACCEPTED", 6)

    r1 = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-A", "2026-08-10T00:10:00Z")
    r2 = build_reconciliation_report(state_root, "srid-1", "coord-2", "run-2", "report-B", "2026-08-10T00:20:00Z")

    assert r1["content_sha256"] == r2["content_sha256"]
    assert r1["report_sha256"] != r2["report_sha256"]


def test_every_state_represented_even_at_zero():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    _write_journal(journal_path, [])
    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:00:00Z")
    from harness_contracts.v1.packet import PACKET_STATES
    assert set(report["by_state"].keys()) == PACKET_STATES
    assert report["inventory_total"] == 0


def test_seal_disagreeing_with_fold_surfaces_via_seal_mismatches():
    """A terminal seal that disagrees with the real fold-derived state
    is caught by reconcile.py's own _check_seal_consistency -- run
    non-fatally, over a phantom-root fold's inventory, deliberately NOT
    inside _fold_journal's own step-5 check this time (see N3: that
    check aborts the whole fold, which used to erase every OTHER
    packet's inventory too). Surfaces as integrity.seal_mismatches + an
    attention item carrying code="TERMINAL_SEAL_MISMATCH" -- NOT a
    generic "fold_failed" catch-all -- and journal_chain_valid stays
    True (the chain itself IS intact; the seal is the actual
    contradiction, and seal_mismatches is what flips
    all_invariants_passed to False, correctly attributing the failure)."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    # Seal disagrees with the real fold-derived ACCEPTED state.
    _write_terminal_seal(state_root, "pkt-1", "QUARANTINED", 6)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is True
    assert report["integrity"]["seal_mismatches"] == ["pkt-1"]
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert any(a["packet_id"] == "pkt-1" and a["code"] == "TERMINAL_SEAL_MISMATCH" for a in report["attention_required"])


def test_orphan_terminal_seal_for_never_enrolled_packet_surfaces_via_seal_mismatches():
    """Same mechanism as above: a seal for a packet the fold never
    enrolled is exactly design 2.6's "contradictory terminal state"
    case, caught inside _fold_journal itself and correctly attributed
    to the ghost packet_id."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    _write_terminal_seal(state_root, "ghost-packet", "ACCEPTED", 1)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is True
    assert report["integrity"]["seal_mismatches"] == ["ghost-packet"]
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert any(a["packet_id"] == "ghost-packet" and a["code"] == "TERMINAL_SEAL_MISMATCH" for a in report["attention_required"])


def test_healthy_terminal_seal_agreeing_with_fold_reports_zero_mismatches():
    """The complement of the two tests above: when a terminal seal DOES
    agree with the fold (the normal case), the fold succeeds and
    seal_mismatches is genuinely empty -- confirms the field means
    something on the healthy path, not just always-empty by construction."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "ACCEPTED", 6)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["seal_mismatches"] == []
    assert report["integrity"]["journal_chain_valid"] is True
    assert report["reconciliation"]["all_invariants_passed"] is True


def test_unenrolled_dependency_surfaces_in_attention_and_integrity():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e1 = _make_event(2, "PACKET_ENROLLED", prev_event=e0, packet_id="dependent-1", intent_id="enroll-dependent-1",
                      to_state="BLOCKED", cause="enrollment",
                      payload={"packet": {**_packet_payload("dependent-1", 2), "dependency_ids": ["never-enrolled"]}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e0, e1])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert "never-enrolled" in report["integrity"]["unenrolled_dependencies"]
    assert any(a["code"] == "dependency_not_enrolled" for a in report["attention_required"])
    assert "dependency_not_enrolled" in report["packets"][0]["attention_codes"]


def test_corrupt_queue_json_does_not_abort_report_generation():
    """A corrupt queue.json must never abort reconciliation -- it's a
    rebuildable cache (D0.2); the report reflects the journal fold, which
    doesn't even read queue.json."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    with open(os.path.join(state_root, "queue.json"), "wb") as f:
        f.write(b"{not valid json at all")

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["inventory_total"] == 0
    assert report["reconciliation"]["all_invariants_passed"] is True


def test_truncated_journal_tail_reported_not_fatal_to_report_generation():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    with open(journal_path, "ab") as f:
        f.write(b'{"schema_version": 1, "seq": 2')  # torn tail, no valid prefix loss

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    # read_journal treats a torn final line as recoverable (returns the
    # valid prefix + torn tail bytes, not an exception) -- so the report
    # still reflects the one valid RUN_STARTED event, but is marked as
    # having seen a non-clean chain.
    assert report["integrity"]["journal_chain_valid"] is False


def test_mid_file_journal_corruption_raises_not_silently_empty_report():
    """A genuinely broken (mid-file, non-final-line) journal must not
    produce a report that silently looks like a healthy empty state
    root. Position (only the final line may be torn), not damage shape,
    is store.py's own discriminator (design 3.3) -- corruption on a
    non-final line is never torn-tail-eligible, so read_journal raises
    JournalChainBroken directly, and build_reconciliation_report lets it
    propagate raw (matching recovery.run_started_recovery's own
    documented precedent for the same call)."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e1 = _make_event(2, "RUN_ENDED", prev_event=e0, payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": {**_run_payload(), "end_reason": "normal"}, "report": None})
    _write_journal(journal_path, [e0, e1])
    with open(journal_path, "rb") as f:
        raw = f.read()
    lines = raw.splitlines(keepends=True)
    corrupted = lines[0].replace(b"RUN_STARTED", b"BAD_TYPE")
    with open(journal_path, "wb") as f:
        f.write(corrupted + lines[1])

    with pytest.raises(JournalChainBroken):
        build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")


def test_unknown_schema_version_journal_raises_when_not_the_final_line():
    """An unknown schema_version on a non-final line is unambiguous
    corruption (not a plausible torn write) -- read_journal raises
    JournalChainBroken. (A bad final line is deliberately handled
    differently -- see test_unknown_schema_version_on_final_line_is_
    treated_as_a_possible_torn_write below; that leniency is design 3.5's
    own accepted carve-out, not a gap in this test.)"""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e1 = _make_event(2, "RUN_ENDED", prev_event=e0, payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": {**_run_payload(), "end_reason": "normal"}, "report": None})
    e1["schema_version"] = 2
    e1["event_sha256"] = _hash_event(e1)
    e2 = _make_event(3, "RUN_STARTED", prev_event=e1, payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0, e1, e2])

    with pytest.raises(JournalChainBroken):
        build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")


def test_unknown_schema_version_on_final_line_is_treated_as_a_possible_torn_write():
    """Design 3.5's position-based torn-tail discriminator (already
    accepted in O3-P2) treats ANY malformed final line as possibly a
    crash-interrupted write, not a hard failure -- content-based
    heuristics ("is this specifically a schema_version problem?") are
    deliberately not trusted; only foreign state_root_id is exempted
    from this leniency. This is the one place a corrupt final line does
    NOT raise -- confirms build_reconciliation_report doesn't fight that
    established design by, e.g., trying to hard-validate the tail itself."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e0["schema_version"] = 2
    e0["event_sha256"] = _hash_event(e0)
    _write_journal(journal_path, [e0])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is False
    assert report["inventory_total"] == 0


def test_emit_reconciliation_report_writes_and_journals():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events = emit_reconciliation_report(state_root, journal_path, lock_path, events, report, "coord-1", "run-1", "srid-1", "2026-08-10T00:11:00Z")

    assert os.path.exists(os.path.join(state_root, "reports", "report-1.json"))
    emitted = [e for e in events if e["event_type"] == "RECONCILIATION_EMITTED"]
    assert len(emitted) == 1
    assert emitted[0]["payload"]["report"]["report_id"] == "report-1"

    reread, torn = read_journal(journal_path, state_root_id="srid-1")
    assert torn is None
    assert len([e for e in reread if e["event_type"] == "RECONCILIATION_EMITTED"]) == 1


def test_emit_reconciliation_report_refuses_invalid_report():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    _write_journal(journal_path, [])
    events, _ = read_journal(journal_path, state_root_id="srid-1")

    bad_report = {"schema_version": 1, "bogus": True}
    with pytest.raises(IntegrityError):
        emit_reconciliation_report(state_root, journal_path, lock_path, events, bad_report, "coord-1", "run-1", "srid-1", "2026-08-10T00:11:00Z")
    assert not os.path.exists(os.path.join(state_root, "reports"))


def test_cli_reconcile_read_only_no_files_written():
    """Read-only guarantee: the CLI's reconcile command must never write
    anything to the state root."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])

    def _snapshot():
        listing = []
        for root, _dirs, files in os.walk(state_root):
            for name in files:
                listing.append(os.path.relpath(os.path.join(root, name), state_root))
        return sorted(listing)

    before = _snapshot()
    report = run_reconcile(state_root, "srid-1", "coord-1", "run-1")
    after = _snapshot()
    assert before == after
    assert report["reconciliation"]["all_invariants_passed"] is True


def test_cli_main_exit_code_nonzero_for_unreconciled_state():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "QUARANTINED", 6)  # disagrees -> unreconciled

    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1


def test_cli_main_exit_code_zero_for_healthy_state():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 0


def test_run_replay_direct_call_matches_replay_schedule():
    """M4 regression: run_replay (cli.py's own wrapper) was imported by
    this test module but never actually called -- confirm it's a real,
    correct pass-through to replay_schedule, not untested dead code."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])

    direct = replay_schedule(state_root, "srid-1")
    via_wrapper = run_replay(state_root, "srid-1")
    assert direct == via_wrapper


def test_cli_main_replay_subcommand_end_to_end_exit_0():
    """M4 regression: the "replay" subcommand was never exercised
    through the real cli_main() entry point in any test -- only
    "reconcile" was."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    exit_code = cli_main(["replay", "--state-root", state_root, "--state-root-id", "srid-1"])
    assert exit_code == 0


def test_missing_manifest_is_a_real_finding_not_a_healthy_empty_report():
    """H2 regression: a state root with no MANIFEST.json at all (never
    initialized by a real coordinator run, or a plain typo'd path) must
    not report as an empty-and-healthy reconciliation -- it must raise,
    loudly, before anything else is read."""
    state_root = tempfile.mkdtemp()  # deliberately no MANIFEST.json
    with pytest.raises(IntegrityError):
        build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")


def test_manifest_state_root_id_mismatch_raises():
    """H2 regression: MANIFEST.json declares a DIFFERENT state_root_id
    than the caller expected -- wrong path, or a stale/foreign state
    root reused by mistake. Must raise, not silently proceed."""
    state_root = _new_state_root(state_root_id="srid-actual")
    with pytest.raises(IntegrityError):
        build_reconciliation_report(state_root, "srid-expected", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")


def test_cli_reconcile_missing_manifest_is_clean_json_error_exit_1():
    """Same as above, through the real CLI subprocess-equivalent path
    (cli_main) -- confirms main()'s broad exception handling actually
    covers this, not just the direct function call."""
    state_root = tempfile.mkdtemp()  # no MANIFEST.json
    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1


def test_cli_replay_missing_manifest_is_clean_exit_1_not_a_vacuous_pass():
    """replay_schedule also validates MANIFEST.json (same fix as
    build_reconciliation_report) -- a missing/wrong state root must not
    replay as a vacuously "passing," zero-event report."""
    state_root = tempfile.mkdtemp()  # no MANIFEST.json
    exit_code = cli_main(["replay", "--state-root", state_root, "--state-root-id", "srid-1"])
    assert exit_code == 1


def test_cli_reconcile_corrupt_seal_json_is_clean_json_error_not_raw_traceback():
    """H1 regression: a truncated/corrupt seal file (the canonical
    crash-mid-write artifact) must never escape as a raw Python
    traceback -- confirmed via the real cli_main() entry point, the
    actual boundary a corrupt overnight state root would hit."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    seal_dir = os.path.join(state_root, "state", "terminal")
    os.makedirs(seal_dir, exist_ok=True)
    with open(os.path.join(seal_dir, "pkt-1.seal.json"), "wb") as f:
        f.write(b'{"schema_version": 1, "packet_id": "pkt-1"')  # truncated, not valid JSON

    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1


def test_cli_reconcile_seal_directory_where_file_expected_is_clean_json_error():
    """H1 regression: a directory sitting where a seal FILE is expected
    (e.g. a botched atomic_replace or a hostile state root) raises
    IsADirectoryError deep inside _fold_journal -- must still degrade to
    clean JSON + exit 1 at the CLI boundary, not crash raw."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    seal_dir = os.path.join(state_root, "state", "terminal")
    os.makedirs(os.path.join(seal_dir, "pkt-1.seal.json"))  # a directory, not a file

    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1


def test_dependency_terminal_not_accepted_reaches_top_level_attention_required():
    """M2 regression: a BLOCKED packet whose dependency is terminal but
    NOT ACCEPTED (QUARANTINED/HUMAN_REQUIRED) must surface in the
    human-facing attention_required list, not just the per-packet
    attention_codes array -- previously asymmetric with its sibling
    dependency_not_enrolled, which already reached the top level."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e1 = _make_event(2, "PACKET_ENROLLED", prev_event=e0, packet_id="blocker-1", intent_id="enroll-blocker-1",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("blocker-1", 2), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    e2 = _make_event(3, "PACKET_ENROLLED", prev_event=e1, packet_id="dependent-1", intent_id="enroll-dependent-1",
                      to_state="BLOCKED", cause="enrollment",
                      payload={"packet": {**_packet_payload("dependent-1", 3), "dependency_ids": ["blocker-1"]}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    e3 = _make_event(4, "ATTEMPT_STARTED", prev_event=e2, packet_id="blocker-1", intent_id="attempt-blocker-1-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    e4 = _make_event(5, "ATTEMPT_FINISHED", prev_event=e3, packet_id="blocker-1", intent_id="attempt-blocker-1-1",
                      from_state="RUNNING", to_state="QUARANTINED", cause="contract_invalid",
                      payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [],
                               "classification": {"attempt_class": "CONTRACT_INVALID", "quarantine_reason": "contract_invalid", "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": 1, "signal": None, "timed_out": False, "result_present": False, "result_valid": False, "error_codes": ["SCHEMA_INVALID"]}},
                               "transition_detail": None,
                               "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e0, e1, e2, e3, e4])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert any(p["packet_id"] == "dependent-1" and "dependency_terminal_not_accepted" in p["attention_codes"] for p in report["packets"])
    assert any(a["packet_id"] == "dependent-1" and a["code"] == "dependency_terminal_not_accepted" for a in report["attention_required"])


def test_attempt_budget_exhausted_flagged_for_revise_resting_packet_at_cap():
    """H5 regression (design 2.3 / fixture G9): a packet resting in
    REVISE with attempts_started == retry_limit + 1 has legitimately
    used its whole budget and is stuck until a human decides -- distinct
    from retry_budget_exceeded (attempts_started > retry_limit + 1,
    a structural violation that should never happen). Must not be
    invisible in attention_required just because nothing is "wrong.\""""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    prev = e0
    seq = 2
    pid = "pkt-1"
    enroll = _make_event(seq, "PACKET_ENROLLED", prev_event=prev, packet_id=pid, intent_id=f"enroll-{pid}",
                          to_state="READY", cause="enrollment",
                          payload={"packet": {**_packet_payload(pid, seq), "retry_limit": 1}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(enroll); prev = enroll; seq += 1
    for attempt in (1, 2):
        if attempt > 1:
            requeued = _make_event(seq, "STATE_TRANSITION", prev_event=prev, packet_id=pid, intent_id=f"revision-{pid}-{attempt - 1}",
                                    from_state="REVISE", to_state="READY", cause="revision_requeued",
                                    payload={"packet": None, "attempt": None, "artifacts": [], "classification": None,
                                             "transition_detail": {"satisfied_by": [], "source_verdict": None, "revise_cycle": attempt - 1},
                                             "recovery": None, "run": None, "report": None})
            events.append(requeued); prev = requeued; seq += 1
        started = _make_event(seq, "ATTEMPT_STARTED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                               from_state="READY", to_state="RUNNING", cause="claim_committed",
                               payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
        events.append(started); prev = started; seq += 1
        finished = _make_event(seq, "ATTEMPT_FINISHED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                                from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
                                payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                                         "classification": {"attempt_class": "COMPLETED_PENDING_REVIEW", "quarantine_reason": None, "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": 0, "signal": None, "timed_out": False, "result_present": True, "result_valid": True, "error_codes": []}},
                                         "transition_detail": None, "recovery": None, "run": None, "report": None})
        events.append(finished); prev = finished; seq += 1
        revised = _make_event(seq, "VERDICT_RECORDED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                               from_state="REVIEW", to_state="REVISE", cause="verdict_revise",
                               payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
        events.append(revised); prev = revised; seq += 1
    _write_journal(journal_path, events)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    pkt_row = next(p for p in report["packets"] if p["packet_id"] == pid)
    assert pkt_row["state"] == "REVISE"
    assert pkt_row["attempts_started"] == 2
    assert pkt_row["retry_limit"] == 1
    assert "attempt_budget_exhausted" in pkt_row["attention_codes"]
    assert "retry_budget_exceeded" not in pkt_row["attention_codes"]
    assert any(a["packet_id"] == pid and a["code"] == "attempt_budget_exhausted" for a in report["attention_required"])


def test_replay_schedule_healthy_multi_packet_journal_zero_divergence():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    # pkt-1 has the lower enqueue_seq -- must be selected first.
    e1 = _make_event(2, "PACKET_ENROLLED", prev_event=events[-1], packet_id="pkt-1", intent_id="enroll-pkt-1",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("pkt-1", 2), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e1)
    e2 = _make_event(3, "PACKET_ENROLLED", prev_event=events[-1], packet_id="pkt-2", intent_id="enroll-pkt-2",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("pkt-2", 3), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e2)
    # Correctly claims pkt-1 first (lower enqueue_seq).
    e3 = _make_event(4, "ATTEMPT_STARTED", prev_event=events[-1], packet_id="pkt-1", intent_id="attempt-pkt-1-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e3)
    _write_journal(journal_path, events)

    result = replay_schedule(state_root, "srid-1")
    assert result["replay_passed"] is True
    assert result["divergences"] == []
    assert result["attempt_started_events_checked"] == 1


def test_replay_schedule_detects_out_of_priority_scheduling_divergence():
    """A tampered journal where ATTEMPT_STARTED claims pkt-2 while pkt-1
    (lower enqueue_seq, equally eligible) was actually the deterministic
    choice -- must be flagged as a divergence."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    e1 = _make_event(2, "PACKET_ENROLLED", prev_event=events[-1], packet_id="pkt-1", intent_id="enroll-pkt-1",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("pkt-1", 2), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e1)
    e2 = _make_event(3, "PACKET_ENROLLED", prev_event=events[-1], packet_id="pkt-2", intent_id="enroll-pkt-2",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("pkt-2", 3), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e2)
    # WRONG: claims pkt-2 while pkt-1 (lower enqueue_seq) was still eligible.
    e3 = _make_event(4, "ATTEMPT_STARTED", prev_event=events[-1], packet_id="pkt-2", intent_id="attempt-pkt-2-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e3)
    _write_journal(journal_path, events)

    result = replay_schedule(state_root, "srid-1")
    assert result["replay_passed"] is False
    assert len(result["divergences"]) == 1
    assert result["divergences"][0]["code"] == "SCHEDULING_DIVERGENCE"


def test_replay_schedule_healthy_accepted_and_sealed_packet_does_not_spuriously_diverge():
    """Regression: a real seal file (written for the packet's eventual
    ACCEPTED state) must not make an EARLIER prefix fold (where the
    packet was still READY/RUNNING) look like a seal mismatch. Caught
    via manual CLI smoke-testing -- the unit tests above never exercised
    a terminal/sealed packet's replay, only non-terminal ones."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "ACCEPTED", 6)

    result = replay_schedule(state_root, "srid-1")
    assert result["replay_passed"] is True
    assert result["divergences"] == []
    assert result["fold_ok"] is True


def test_replay_schedule_tampered_journal_event_hash_reported_not_silently_passed():
    """N7: this tampers a JOURNAL EVENT's own event_sha256 (chain
    integrity), not an artifact digest (design 10.2 check 7, which this
    module doesn't implement -- see the module docstring)."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])
    with open(journal_path, "rb") as f:
        raw = f.read()
    tampered = raw.replace(e0["event_sha256"].encode(), ("1" * 64).encode())
    with open(journal_path, "wb") as f:
        f.write(tampered)

    result = replay_schedule(state_root, "srid-1")
    assert result["replay_passed"] is False
    assert result["journal_chain_valid"] is False


def test_missing_journal_with_valid_manifest_is_not_reported_as_healthy():
    """N1 regression: a state root with a real, valid MANIFEST.json but
    NO journal.ndjson at all must not report as empty-and-healthy --
    either the coordinator crashed before ever writing RUN_STARTED, or
    the journal (design D0.1's sole commit point) was lost. Both are
    attention-worthy; neither is silently "nothing to reconcile"."""
    state_root = _new_state_root()  # MANIFEST.json written, journal.ndjson never created

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert any(a["code"] == "journal_missing" for a in report["attention_required"])


def test_cli_reconcile_missing_journal_exit_1_not_healthy_zero():
    state_root = _new_state_root()
    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1


def test_seal_attributable_fold_failure_preserves_inventory_of_other_packets():
    """N3 regression: a bad seal on ONE packet must not erase the
    report's visibility into every OTHER healthy packet -- the whole
    point of a reconciliation report is to itemize problems, not go
    blind the moment it finds the first one. pkt-1's seal disagrees;
    pkt-2 is untouched and fully healthy; pkt-2 must still show up,
    fully described, in the report."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("pkt-1", 2, 2, events[-1])
    events += _accepted_packet_journal("pkt-2", 3, 6, events[-1])
    _write_journal(journal_path, events)
    _write_terminal_seal(state_root, "pkt-1", "QUARANTINED", 6)  # disagrees -- real state is ACCEPTED
    _write_terminal_seal(state_root, "pkt-2", "ACCEPTED", 10)  # agrees

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["inventory_total"] == 2
    assert report["integrity"]["seal_mismatches"] == ["pkt-1"]
    # Both packets' rows correctly show ACCEPTED -- that's the real,
    # fold-derived state for each. The seal MISMATCH is a separate
    # signal (integrity.seal_mismatches), not something that changes
    # what state the report attributes to pkt-1.
    assert report["by_state"]["ACCEPTED"] == 2
    pkt2_row = next(p for p in report["packets"] if p["packet_id"] == "pkt-2")
    assert pkt2_row["state"] == "ACCEPTED"
    assert pkt2_row["attention_codes"] == []
    assert report["reconciliation"]["all_invariants_passed"] is False  # pkt-1's mismatch still fails the run


def test_emit_reconciliation_report_requires_valid_manifest():
    """N2 regression: emit_reconciliation_report must not write a report
    into a state root with a missing/wrong MANIFEST.json -- writing into
    the wrong or uninitialized root is exactly as bad as reading from it."""
    state_root = tempfile.mkdtemp()  # deliberately no MANIFEST.json
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    fake_report = {"schema_version": 1, "report_id": "report-1"}  # never even reaches validation

    with pytest.raises(IntegrityError):
        emit_reconciliation_report(state_root, journal_path, lock_path, [], fake_report, "coord-1", "run-1", "srid-1", "2026-08-10T00:10:00Z")
    assert not os.path.exists(os.path.join(state_root, "reports"))


def test_report_always_carries_unverified_invariants_disclosure():
    """H3/H4 regression: the report artifact itself (not just the module
    docstring) must name state_cache_in_sync/preserved_evidence_mismatches
    as unverified placeholders -- visible to whoever reads a report, not
    only whoever reads the source. Purely informational: does not affect
    all_invariants_passed on an otherwise-healthy report."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [e0])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert any(a["code"] == "unverified_invariants" for a in report["attention_required"])
    assert report["reconciliation"]["all_invariants_passed"] is True


def test_empty_but_present_journal_treated_same_as_missing():
    """N9 regression: a 0-byte journal.ndjson is reachable only by a
    crash between O_CREAT and the first fsync'd write, or tampering --
    never a legitimate "nothing happened yet" state (the only creation
    point anywhere is append_journal's O_CREAT). Must get the identical
    journal_missing treatment as a genuinely absent file, not report
    healthy."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    with open(journal_path, "wb") as f:
        pass  # 0 bytes, but the file exists

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert any(a["code"] == "journal_missing" for a in report["attention_required"])


def test_accounting_identity_violation_not_falsely_stamped_on_retry_budget_exceeded_packet():
    """N8 regression: compute_reconciliation's integrity.accounting_violations
    bucket is shared between I9 (identity) and I10 (retry budget) --
    keying the per-packet attention_codes back-fill on that shared bucket
    previously stamped a FALSE accounting_identity_violation onto every
    retry-budget-exceeded packet even when its identity holds exactly.
    Construct exactly that: retry_limit=1, 3 attempts (exceeds budget --
    I10 fires), 2 revise_cycles + 0 infra + 0 reassign == 3-1 (identity
    holds exactly -- I9 must NOT fire)."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    prev = e0
    seq = 2
    pid = "pkt-1"
    enroll = _make_event(seq, "PACKET_ENROLLED", prev_event=prev, packet_id=pid, intent_id=f"enroll-{pid}",
                          to_state="READY", cause="enrollment",
                          payload={"packet": {**_packet_payload(pid, seq), "retry_limit": 1}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(enroll); prev = enroll; seq += 1
    for attempt in (1, 2, 3):
        if attempt > 1:
            requeued = _make_event(seq, "STATE_TRANSITION", prev_event=prev, packet_id=pid, intent_id=f"revision-{pid}-{attempt - 1}",
                                    from_state="REVISE", to_state="READY", cause="revision_requeued",
                                    payload={"packet": None, "attempt": None, "artifacts": [], "classification": None,
                                             "transition_detail": {"satisfied_by": [], "source_verdict": None, "revise_cycle": attempt - 1},
                                             "recovery": None, "run": None, "report": None})
            events.append(requeued); prev = requeued; seq += 1
        started = _make_event(seq, "ATTEMPT_STARTED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                               from_state="READY", to_state="RUNNING", cause="claim_committed",
                               payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
        events.append(started); prev = started; seq += 1
        if attempt < 3:
            finished = _make_event(seq, "ATTEMPT_FINISHED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                                    from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
                                    payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                                             "classification": {"attempt_class": "COMPLETED_PENDING_REVIEW", "quarantine_reason": None, "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": 0, "signal": None, "timed_out": False, "result_present": True, "result_valid": True, "error_codes": []}},
                                             "transition_detail": None, "recovery": None, "run": None, "report": None})
            events.append(finished); prev = finished; seq += 1
            revised = _make_event(seq, "VERDICT_RECORDED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                                   from_state="REVIEW", to_state="REVISE", cause="verdict_revise",
                                   payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
            events.append(revised); prev = revised; seq += 1
    _write_journal(journal_path, events)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    pkt_row = next(p for p in report["packets"] if p["packet_id"] == pid)
    assert pkt_row["attempts_started"] == 3
    assert pkt_row["revise_cycles_used"] == 2
    assert pkt_row["retry_limit"] == 1
    assert "retry_budget_exceeded" in pkt_row["attention_codes"]
    assert "accounting_identity_violation" not in pkt_row["attention_codes"]
    assert not any(a["packet_id"] == pid and a["code"] == "accounting_identity_violation" for a in report["attention_required"])


def test_accounting_identity_violation_is_genuinely_stamped_when_it_should_be():
    """N14: the complement of the negative test above -- a real I9
    violation must still reach the row's attention_codes. Deleting the
    whole back-fill loop must not leave this passing.

    reassignment_used is a BOOLEAN (recovery.py sets it True on
    provider_exhausted_reassignment, never counts occurrences), while
    attempts_started increments on every ATTEMPT_STARTED -- so a packet
    that goes through provider_exhausted_reassignment TWICE (legal per
    CAUSE_EDGES at the fold level; a real coordinator's business logic
    elsewhere is what actually limits this to once, not the fold) ends
    up with attempts_started=3 but reassignment_used counting as only 1,
    breaking the identity: 0+0+1 != 3-1. retry_limit is set high enough
    that I10 does not also fire, isolating this to a pure I9 case."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    pid = "pkt-1"
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    prev = e0
    seq = 2
    enroll = _make_event(seq, "PACKET_ENROLLED", prev_event=prev, packet_id=pid, intent_id=f"enroll-{pid}",
                          to_state="READY", cause="enrollment",
                          payload={"packet": {**_packet_payload(pid, seq), "retry_limit": 5, "sonnet_reassignment_allowed": True}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(enroll); prev = enroll; seq += 1
    for attempt in (1, 2, 3):
        started = _make_event(seq, "ATTEMPT_STARTED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                               from_state="READY", to_state="RUNNING", cause="claim_committed",
                               payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
        events.append(started); prev = started; seq += 1
        if attempt < 3:
            finished = _make_event(seq, "ATTEMPT_FINISHED", prev_event=prev, packet_id=pid, intent_id=f"attempt-{pid}-{attempt}",
                                    from_state="RUNNING", to_state="READY", cause="provider_exhausted_reassignment",
                                    payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                                             "classification": {"attempt_class": "PROVIDER_EXHAUSTED", "quarantine_reason": None, "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": 1, "signal": None, "timed_out": False, "result_present": False, "result_valid": False, "error_codes": []}},
                                             "transition_detail": None, "recovery": None, "run": None, "report": None})
            events.append(finished); prev = finished; seq += 1
    _write_journal(journal_path, events)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    pkt_row = next(p for p in report["packets"] if p["packet_id"] == pid)
    assert pkt_row["attempts_started"] == 3
    assert pkt_row["reassignment_used"] is True
    assert pkt_row["infra_retries_used"] == 0
    assert pkt_row["revise_cycles_used"] == 0
    assert "retry_budget_exceeded" not in pkt_row["attention_codes"]  # isolate to I9 only
    assert "accounting_identity_violation" in pkt_row["attention_codes"]
    assert any(a["packet_id"] == pid and a["code"] == "accounting_identity_violation" for a in report["attention_required"])


def test_seals_not_checked_flagged_only_when_fold_genuinely_fails():
    """N15: seals_not_checked must fire when the fold itself fails
    (before any packet inventory exists to check seals against), and
    must NOT fire on the healthy path or on a seal-attributable-only
    failure (where the fold succeeds and seals ARE checked)."""
    # Genuine fold failure: a second ATTEMPT_STARTED for a packet
    # already RUNNING -- schema-valid shape, rejected by _fold_journal's
    # actual-state check (see the from_state/actual-state mismatch this
    # produces below).
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    e1 = _make_event(2, "PACKET_ENROLLED", prev_event=e0, packet_id="pkt-1", intent_id="enroll-pkt-1",
                      to_state="READY", cause="enrollment",
                      payload={"packet": _packet_payload("pkt-1", 2), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    e2 = _make_event(3, "ATTEMPT_STARTED", prev_event=e1, packet_id="pkt-1", intent_id="attempt-pkt-1-1",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    # ATTEMPT_STARTED for an already-RUNNING packet: schema-valid shape,
    # illegal transition (a second open attempt) -- _fold_journal's
    # terminal-safety/transition check must reject this.
    e3 = _make_event(4, "ATTEMPT_STARTED", prev_event=e2, packet_id="pkt-1", intent_id="attempt-pkt-1-2",
                      from_state="READY", to_state="RUNNING", cause="claim_committed",
                      payload={"packet": None, "attempt": _attempt_payload(2), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e0, e1, e2, e3])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert any(a["code"] == "fold_failed" for a in report["attention_required"])
    assert any(a["code"] == "seals_not_checked" for a in report["attention_required"])

    # Healthy path: must NOT fire.
    healthy_root = _new_state_root()
    healthy_journal = os.path.join(healthy_root, "journal.ndjson")
    e0h = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(healthy_journal, [e0h])
    healthy_report = build_reconciliation_report(healthy_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert not any(a["code"] == "seals_not_checked" for a in healthy_report["attention_required"])

    # Seal-attributable-only failure: fold SUCCEEDS, seals get checked --
    # seals_not_checked must not fire here either.
    seal_root = _new_state_root()
    seal_journal = os.path.join(seal_root, "journal.ndjson")
    e0s = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events_s = [e0s]
    events_s += _accepted_packet_journal("pkt-1", 2, 2, events_s[-1])
    _write_journal(seal_journal, events_s)
    _write_terminal_seal(seal_root, "pkt-1", "QUARANTINED", 6)  # disagrees
    seal_report = build_reconciliation_report(seal_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert not any(a["code"] == "seals_not_checked" for a in seal_report["attention_required"])
    assert seal_report["integrity"]["seal_mismatches"] == ["pkt-1"]


def test_whitespace_only_journal_treated_same_as_missing():
    """N9 follow-up regression: a journal.ndjson containing only
    whitespace/newlines (e.g. `echo > journal.ndjson`) is byte-nonempty
    but produces the exact same (valid_events=[], torn_tail=None) from
    read_journal as a genuinely absent or 0-byte file -- os.path.getsize()
    > 0 alone missed this. Must get the identical journal_missing
    treatment, not report healthy."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    with open(journal_path, "wb") as f:
        f.write(b"\n\n   \n\t\n")

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["integrity"]["journal_chain_valid"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert any(a["code"] == "journal_missing" for a in report["attention_required"])


def test_promotion_stalled_flagged_when_all_dependencies_accepted_but_still_blocked():
    """Final O3 integration gate, defect D1: no code anywhere in this
    build writes a terminal seal, and classify_runtime.promote_dependencies
    requires one to exist for every dependency before it will promote a
    BLOCKED packet -- deferring quietly (zero events) when absent. Without
    this flag, a packet stuck in exactly this state has blocked_on==[]
    (every dependency IS fold-ACCEPTED) and gets zero attention codes --
    the report would read fully healthy while real work is permanently
    stuck. Must surface as promotion_stalled, not silently pass."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("blocker-1", 2, 2, events[-1])
    e_dep = _make_event(6, "PACKET_ENROLLED", prev_event=events[-1], packet_id="dependent-1", intent_id="enroll-dependent-1",
                         to_state="BLOCKED", cause="enrollment",
                         payload={"packet": {**_packet_payload("dependent-1", 6), "dependency_ids": ["blocker-1"]}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e_dep)
    _write_journal(journal_path, events)
    # blocker-1's dependency is ACCEPTED per the fold, but deliberately
    # NO terminal seal is written for it -- reproducing the permanent
    # stuck state, not a transient one-pass-behind race.

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    dependent_row = next(p for p in report["packets"] if p["packet_id"] == "dependent-1")
    assert dependent_row["state"] == "BLOCKED"
    assert dependent_row["blocked_on"] == []
    assert "promotion_stalled" in dependent_row["attention_codes"]
    assert any(a["packet_id"] == "dependent-1" and a["code"] == "promotion_stalled" for a in report["attention_required"])


def test_possible_benign_retry_window_disclosed_for_i9_violation_on_resting_packet():
    """Final O3 integration gate, defect D5: classify_runtime.py's own
    "Known, disclosed gap (design 9.2 / O3-P4)" docstring names this
    exact mechanism and hands P4 the obligation to surface it -- a
    packet resting in READY immediately after a single infra_retry has
    attempts_started=1, infra_retries_used=1, so I9 evaluates 1 == 0 and
    fires, even though nothing is actually wrong. The real
    accounting_identity_violation must still be reported (not
    suppressed -- compute_reconciliation is not second-guessed), but
    accompanied by context a human needs to judge it correctly."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    pid = "pkt-1"
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    enroll = _make_event(2, "PACKET_ENROLLED", prev_event=e0, packet_id=pid, intent_id=f"enroll-{pid}",
                          to_state="READY", cause="enrollment",
                          payload={"packet": _packet_payload(pid, 2), "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    started = _make_event(3, "ATTEMPT_STARTED", prev_event=enroll, packet_id=pid, intent_id=f"attempt-{pid}-1",
                           from_state="READY", to_state="RUNNING", cause="claim_committed",
                           payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    finished = _make_event(4, "ATTEMPT_FINISHED", prev_event=started, packet_id=pid, intent_id=f"attempt-{pid}-1",
                            from_state="RUNNING", to_state="READY", cause="infra_retry",
                            payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [],
                                     "classification": {"attempt_class": "INFRA_RETRYABLE", "quarantine_reason": None, "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None, "reassignment_record_sha256": None, "outcome_summary": {"exit_code": None, "signal": 9, "timed_out": False, "result_present": False, "result_valid": False, "error_codes": []}},
                                     "transition_detail": None, "recovery": None, "run": None, "report": None})
    _write_journal(journal_path, [e0, enroll, started, finished])

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    pkt_row = next(p for p in report["packets"] if p["packet_id"] == pid)
    assert pkt_row["state"] == "READY"
    assert pkt_row["attempts_started"] == 1
    assert pkt_row["infra_retries_used"] == 1
    assert "accounting_identity_violation" in pkt_row["attention_codes"]
    assert "possible_benign_retry_window" in pkt_row["attention_codes"]
    assert any(a["packet_id"] == pid and a["code"] == "accounting_identity_violation" for a in report["attention_required"])
    assert any(a["packet_id"] == pid and a["code"] == "possible_benign_retry_window" for a in report["attention_required"])


def test_cli_exit_code_nonzero_on_promotion_stalled_despite_all_invariants_passed():
    """Final O3 integration gate follow-up: a permanently-stalled
    promotion is internally CONSISTENT durable state (all_invariants_passed
    stays True -- I1-I12 genuinely all pass, correctly, per the review
    that flagged this), so the CLI must not rely on that field alone for
    its exit code. An automated morning check reading only the exit code
    (not the JSON body) must still see nonzero on a stuck run."""
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    e0 = _make_event(1, "RUN_STARTED", payload={"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    events = [e0]
    events += _accepted_packet_journal("blocker-1", 2, 2, events[-1])
    e_dep = _make_event(6, "PACKET_ENROLLED", prev_event=events[-1], packet_id="dependent-1", intent_id="enroll-dependent-1",
                         to_state="BLOCKED", cause="enrollment",
                         payload={"packet": {**_packet_payload("dependent-1", 6), "dependency_ids": ["blocker-1"]}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None})
    events.append(e_dep)
    _write_journal(journal_path, events)

    report = build_reconciliation_report(state_root, "srid-1", "coord-1", "run-1", "report-1", "2026-08-10T00:10:00Z")
    assert report["reconciliation"]["all_invariants_passed"] is True  # internally consistent -- confirms this is the exact case
    assert any(a["code"] == "promotion_stalled" for a in report["attention_required"])

    exit_code = cli_main(["reconcile", "--state-root", state_root, "--state-root-id", "srid-1", "--coordinator-id", "coord-1", "--run-id", "run-1"])
    assert exit_code == 1
