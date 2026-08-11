"""P5D restart, immutable fallback, reconciliation, and status tests."""

import os
import copy
import shutil
import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.reassignment_runtime import (
    ReassignmentConflict,
    assert_preserved,
    build_reassignment_record,
    load_and_validate_attempt_evidence,
    publish_reassignment,
)
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.cli import run_status
from harness_coordinator.v1.reconcile import build_reconciliation_report, emit_reconciliation_report
from harness_coordinator.v1.store import read_journal
from harness_coordinator.v1.classify_runtime import _finish_attempt, _resolve_reassignment_cause
from harness_coordinator.v1.coordinator import run_once
from harness_coordinator.v1.recovery import IntegrityError
from harness_coordinator.v1.scheduler import select_next
from test_o3_reconciliation import _make_event, _new_state_root, _run_payload, _write_journal
from test_o3_p5_invocation import _packet as _invocation_packet, _worker_result


def _bound_evidence(tmp_path):
    packet = _invocation_packet(tmp_path)
    packet["assigned_worker"]["provider"] = "local"
    result = _worker_result(packet, "session-1")
    result["outcome"] = "CHECKPOINTED"
    result["evidence"][0]["criterion_ids"] = ["done"]
    result["criteria"] = [{"criterion_id": "done", "status": "SATISFIED", "evidence_ids": ["ev"]}]
    result["remaining_criterion_ids"] = ["ac"]
    result["fallback"] = {"reason": "confirmed_rate_limit_exhaustion",
                          "provider_evidence_id": "pe-1", "reassign_to": "sonnet_implementation"}
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    stdout = b""
    stderr = b"rate limit exceeded"
    invocation = {"argv": ["synthetic"], "cwd": ".", "started_at": "2026-08-11T13:00:00Z",
                  "finished_at": "2026-08-11T13:00:01Z", "exit_code": 1,
                  "signal": None, "timed_out": False, "wall_clock_seconds": 1}
    evidence = {
        "schema_version": 1, "evidence_id": "pe-1", "packet_id": packet["packet_id"],
        "attempt": 1, "provider": "local",
        "captured_by": {"role": "coordinator", "coordinator_id": "coord-1",
                        "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
        "invocation": {key: invocation[key] for key in
                       ("argv", "exit_code", "signal", "started_at", "finished_at", "timed_out")},
        "stdout_path": f"results/{packet['packet_id']}/1/stdout.bin",
        "stdout_sha256": compute_sha256(stdout),
        "stderr_path": f"results/{packet['packet_id']}/1/stderr.bin",
        "stderr_sha256": compute_sha256(stderr),
        "matched_signal": {"channel": "stderr", "rule_id": "rate", "registry_id": "reg-1",
                           "verbatim_excerpt": "rate limit exceeded", "byte_offset": 0,
                           "byte_length": len(stderr)},
        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION", "evidence_sha256": "",
    }
    evidence["evidence_sha256"] = compute_sha256(canonical_bytes(evidence, omit={"evidence_sha256"}))
    outcome = {
        "schema_version": 1, "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"], "attempt": 1,
        "coordinator_id": "coord-1", "run_id": "run-1", "lane": "kimi_implementation",
        "invocation": invocation,
        "stdout": {"path": evidence["stdout_path"], "sha256": evidence["stdout_sha256"],
                   "byte_length": len(stdout)},
        "stderr": {"path": evidence["stderr_path"], "sha256": evidence["stderr_sha256"],
                   "byte_length": len(stderr)},
        "raw_result": {"path": f"results/{packet['packet_id']}/1/worker_result.json",
                       "sha256": result["result_sha256"],
                       "byte_length": len(canonical_bytes(result))},
        "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
        "authority": {"guard_denials": [], "undeclared_changed_paths": [],
                      "governed_path_touches": [], "hard_stop_matches": []},
        "provider_evidence_sha256": evidence["evidence_sha256"], "outcome": "CHECKPOINTED",
        "fallback": result["fallback"], "outcome_sha256": "",
    }
    outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))
    started = {"event_type": "ATTEMPT_STARTED", "packet_id": packet["packet_id"],
               "coordinator_id": "coord-1", "run_id": "run-1",
               "payload": {"attempt": {"attempt": 1, "lane": "kimi_implementation",
                                         "worker": {**packet["assigned_worker"],
                                                    "session_id": "session-1",
                                                    "lane": "kimi_implementation"}}}}
    run_started = {"event_type": "RUN_STARTED", "coordinator_id": "coord-1", "run_id": "run-1",
                   "payload": {"run": {"coordinator": {"coordinator_id": "coord-1",
                                                         "boot_id": "boot-1", "hostname": "host-1",
                                                         "pid": 1}}}}
    root = tmp_path / "state-evidence"
    root.mkdir()
    with open_state_root(str(root)) as handle:
        base = ("results", packet["packet_id"], "1")
        handle.publish(base + ("stdout.bin",), stdout)
        handle.publish(base + ("stderr.bin",), stderr)
        handle.publish(base + ("worker_result.json",), canonical_bytes(result))
        handle.publish(base + ("provider_evidence.json",), canonical_bytes(evidence))
        handle.publish(base + ("attempt_outcome.json",), canonical_bytes(outcome))
    return root, packet, result, evidence, outcome, started, run_started


@pytest.mark.parametrize("mutation", ["packet_sha256", "worker", "fallback"])
def test_worker_result_must_bind_exact_attempt_identity_and_fallback(tmp_path, mutation):
    root, packet, result, evidence, outcome, started, run_started = _bound_evidence(tmp_path)
    altered = copy.deepcopy(result)
    if mutation == "packet_sha256":
        altered["packet_sha256"] = "f" * 64
    elif mutation == "worker":
        altered["worker"]["worker_id"] = "substituted-worker"
    else:
        altered["fallback"]["provider_evidence_id"] = "substituted-evidence"
    altered["result_sha256"] = compute_sha256(
        canonical_bytes(altered, omit={"result_sha256"}))
    altered_outcome = copy.deepcopy(outcome)
    altered_outcome["raw_result"]["sha256"] = altered["result_sha256"]
    altered_outcome["raw_result"]["byte_length"] = len(canonical_bytes(altered))
    if mutation == "packet_sha256":
        altered_outcome["packet_sha256"] = altered["packet_sha256"]
    if mutation == "fallback":
        altered_outcome["fallback"] = altered["fallback"]
    altered_outcome["outcome_sha256"] = compute_sha256(
        canonical_bytes(altered_outcome, omit={"outcome_sha256"}))
    with open_state_root(str(root)) as handle:
        with handle.directory(("results", packet["packet_id"], "1")) as directory_fd:
            os.unlink("worker_result.json", dir_fd=directory_fd)
            os.unlink("attempt_outcome.json", dir_fd=directory_fd)
        handle.publish(("results", packet["packet_id"], "1", "worker_result.json"),
                       canonical_bytes(altered))
        handle.publish(("results", packet["packet_id"], "1", "attempt_outcome.json"),
                       canonical_bytes(altered_outcome))
        with pytest.raises(ReassignmentConflict):
            load_and_validate_attempt_evidence(
                handle, packet["packet_id"], packet["packet_sha256"], 1,
                altered_outcome, started, run_started)


def _inputs():
    packet = {"packet_id": "packet-1", "packet_sha256": "a" * 64,
              "lane": "kimi_implementation"}
    result = {
        "result_id": "result-1", "result_sha256": "b" * 64,
        "changed_files": [{"path": "scripts/x.py", "status": "modified",
                           "before_sha256": "c" * 64, "after_sha256": "d" * 64}],
        "checkpoints": [{"artifact_id": "cp-1", "path": "scripts/x.py", "sha256": "d" * 64}],
        "verification_evidence": [{"evidence_id": "ev-1", "command_id": "cmd-1",
                                   "artifact_path": "evidence/ev-1.json", "artifact_sha256": "e" * 64}],
        "remaining_criterion_ids": ["criterion-1"],
    }
    evidence = {"evidence_id": "provider-1", "evidence_sha256": "f" * 64}
    outcome = {"outcome_sha256": "1" * 64}
    events = [{"seq": 1, "event_sha256": "2" * 64},
              {"seq": 4, "event_sha256": "3" * 64}]
    return packet, result, evidence, outcome, events


def _exhaustion_finish_fixture(tmp_path):
    root, packet, _, provider_evidence, outcome, _, _ = _bound_evidence(tmp_path)
    root = str(root)
    run_payload = _run_payload()
    run_payload["coordinator"] = {"coordinator_id": "coord-1", "boot_id": "boot-1",
                                  "hostname": "host-1", "pid": 1}
    run_event = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": run_payload, "report": None})
    attempt_payload = {"attempt": 1, "lane": "kimi_implementation",
                       "worker": {**packet["assigned_worker"], "session_id": "session-1",
                                  "lane": "kimi_implementation"},
                       "claim_sha256": None, "worktree_path": packet["worktree"]["path"]}
    started = _make_event(
        2, "ATTEMPT_STARTED", prev_event=run_event, packet_id=packet["packet_id"],
        intent_id="attempt-1", from_state="READY", to_state="RUNNING",
        cause="claim_committed", payload={"packet": None, "attempt": attempt_payload,
        "artifacts": [], "classification": None, "transition_detail": None,
        "recovery": None, "run": None, "report": None})
    events = [run_event, started]
    _write_journal(os.path.join(root, "journal.ndjson"), events)
    registry = {"schema_version": 1, "registry_id": "reg-1", "providers": {"local": [{
        "rule_id": "rate", "channel": "stderr", "match_kind": "substring",
        "pattern": "rate limit exceeded", "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        "captured_from": {"sample_path": "trust/sample.json", "sample_sha256": "0" * 64,
                          "captured_at": "2026-08-10T00:00:00Z"}}]}, "registry_sha256": ""}
    registry["registry_sha256"] = compute_sha256(
        canonical_bytes(registry, omit={"registry_sha256"}))
    folded = {"packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
              "lane": "kimi_implementation", "retry_limit": 3, "attempts_started": 1,
              "sonnet_reassignment_allowed": True, "reassignment_used": False}
    return root, packet, provider_evidence, outcome, events, attempt_payload, registry, folded


def test_reassignment_publish_is_canonical_exclusive_and_idempotent(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = build_reassignment_record(
        *_inputs(), next_event_seq=5, now="2026-08-11T13:00:00Z", attempt=1,
        paths={"worker_result": "results/packet-1/1/worker_result.json",
               "provider_evidence": "results/packet-1/1/provider_evidence.json",
               "attempt_outcome": "results/packet-1/1/attempt_outcome.json"})
    with open_state_root(str(root)) as handle:
        digest, created = publish_reassignment(handle, record)
        assert created is True
        assert publish_reassignment(handle, record) == (digest, False)
    path = root / "reassignments" / "packet-1.json"
    assert path.read_bytes() == canonical_bytes(record)
    assert digest == record["reassignment_sha256"]


def test_reassignment_conflict_never_overwrites(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = build_reassignment_record(
        *_inputs(), next_event_seq=5, now="2026-08-11T13:00:00Z", attempt=1,
        paths={"worker_result": "results/packet-1/1/worker_result.json",
               "provider_evidence": "results/packet-1/1/provider_evidence.json",
               "attempt_outcome": "results/packet-1/1/attempt_outcome.json"})
    with open_state_root(str(root)) as handle:
        handle.publish(("reassignments", "packet-1.json"), b"conflict")
        with pytest.raises(ReassignmentConflict):
            publish_reassignment(handle, record)


def test_assert_preserved_reports_changed_pointer(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = build_reassignment_record(
        *_inputs(), next_event_seq=5, now="2026-08-11T13:00:00Z", attempt=1,
        paths={"worker_result": "results/packet-1/1/worker_result.json",
               "provider_evidence": "results/packet-1/1/provider_evidence.json",
               "attempt_outcome": "results/packet-1/1/attempt_outcome.json"})
    with open_state_root(str(root)) as handle:
        handle.publish(("results", "packet-1", "1", "worker_result.json"), b"changed")
        mismatches = assert_preserved(handle, record)
    assert any(item["kind"] == "worker_result" for item in mismatches)


def test_pinned_reconciliation_publish_is_idempotent():
    root = os.path.realpath(_new_state_root())
    journal_path = os.path.join(root, "journal.ndjson")
    lock_path = os.path.join(root, "locks", "journal.wlock")
    started = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [started])
    report = build_reconciliation_report(
        root, "srid-1", "coord-1", "run-1", "reconciliation-run-1",
        "2026-08-11T13:00:00Z")
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    with open_state_root(root) as handle:
        events = emit_reconciliation_report(
            root, journal_path, lock_path, events, report, "coord-1", "run-1",
            "srid-1", "2026-08-11T13:00:01Z", handle=handle)
        rebuilt = build_reconciliation_report(
            root, "srid-1", "coord-1", "run-1", "reconciliation-run-1",
            "2026-08-11T13:00:02Z")
        events = emit_reconciliation_report(
            root, journal_path, lock_path, events, rebuilt, "coord-1", "run-1",
            "srid-1", "2026-08-11T13:00:01Z", handle=handle)
    assert len([event for event in events if event["event_type"] == "RECONCILIATION_EMITTED"]) == 1


def test_committed_reconciliation_artifact_mismatch_fails_closed():
    root = os.path.realpath(_new_state_root())
    journal_path = os.path.join(root, "journal.ndjson")
    lock_path = os.path.join(root, "locks", "journal.wlock")
    started = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(journal_path, [started])
    report = build_reconciliation_report(
        root, "srid-1", "coord-1", "run-1", "reconciliation-run-1",
        "2026-08-11T13:00:00Z")
    with open_state_root(root) as handle:
        events = emit_reconciliation_report(
            root, journal_path, lock_path, [started], report, "coord-1", "run-1",
            "srid-1", "2026-08-11T13:00:01Z", handle=handle)
        handle.unlink(("reports", "reconciliation-run-1.json"))
        handle.publish(("reports", "reconciliation-run-1.json"), b"substituted")
        with pytest.raises(IntegrityError):
            emit_reconciliation_report(
                root, journal_path, lock_path, events, report, "coord-1", "run-1",
                "srid-1", "2026-08-11T13:00:01Z", handle=handle)


def test_real_no_work_iteration_emits_reconciliation(tmp_path):
    from test_o3_p5_review import _write_manifest, _write_trust_roots, STATE_ROOT_ID

    root = os.path.realpath(str(tmp_path / "empty-state"))
    os.makedirs(os.path.join(root, "locks"))
    _write_manifest(root)
    _write_trust_roots(root)
    context = {"coordinator_id": "coord-empty", "hostname": "test-host", "boot_id": "boot-1",
               "pid": os.getpid(), "live_coordinator_ids": {"coord-empty"},
               "now": "2026-08-11T13:00:00Z"}
    result = run_once(root, "coord-empty", "run-empty", context, "2026-08-11T13:00:00Z")
    assert result["status"] == "no_eligible_work"
    assert result["reconciliation"]["report_id"].startswith("reconciliation-")
    events, torn = read_journal(os.path.join(root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    assert len([e for e in events if e["event_type"] == "RECONCILIATION_EMITTED"]) == 1


def test_preservation_mutations_flow_into_reconciliation(tmp_path, monkeypatch):
    import harness_coordinator.v1.reconcile as reconcile_module

    root = os.path.realpath(_new_state_root())
    started = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(os.path.join(root, "journal.ndjson"), [started])
    packet, result, evidence, outcome, journal_range = _inputs()
    result["evidence"] = [{"evidence_id": "ev-1", "command_id": "cmd-1",
                           "artifact_path": "evidence/ev-1.json",
                           "artifact_sha256": "e" * 64}]
    worktree = tmp_path / "preserved-worktree"
    (worktree / "scripts").mkdir(parents=True)
    (worktree / "evidence").mkdir()
    (worktree / "scripts" / "x.py").write_bytes(b"mutated")
    (worktree / "evidence" / "ev-1.json").write_bytes(b"mutated")
    packet_body = _invocation_packet(tmp_path)
    packet_body["packet_id"] = "packet-1"
    packet_body["worktree"]["path"] = str(worktree)
    packet_body["packet_sha256"] = compute_sha256(
        canonical_bytes(packet_body, omit={"packet_sha256"}))
    packet["packet_sha256"] = packet_body["packet_sha256"]
    record = build_reassignment_record(
        packet, result, evidence, outcome, journal_range, next_event_seq=5,
        now="2026-08-11T13:00:00Z", attempt=1,
        paths={"worker_result": "results/packet-1/1/worker_result.json",
               "provider_evidence": "results/packet-1/1/provider_evidence.json",
               "attempt_outcome": "results/packet-1/1/attempt_outcome.json"})
    with open_state_root(root) as handle:
        handle.publish(("packets", "packet-1.json"), canonical_bytes(packet_body))
        publish_reassignment(handle, record)
    folded_packet = {"packet_id": "packet-1", "state": "READY",
                     "lane": "sonnet_implementation", "enqueue_seq": 1,
                     "attempts_started": 1, "infra_retries_used": 0,
                     "revise_cycles_used": 0, "revise_verdicts": 0,
                     "reassignment_used": True, "open_attempt": None,
                     "last_event_seq": 1, "last_event_sha256": started["event_sha256"],
                     "dependency_ids": [], "retry_limit": 3}
    monkeypatch.setattr(reconcile_module, "_fold_journal",
                        lambda *args: ({"packet-1": folded_packet}, {}))
    report = build_reconciliation_report(
        root, "srid-1", "coord-1", "run-1", "reconciliation-run-1",
        "2026-08-11T13:00:00Z")
    mismatches = report["integrity"]["preserved_evidence_mismatches"]
    assert any(":changed_file:" in item for item in mismatches)
    assert any(":checkpoint:" in item for item in mismatches)
    assert any(":verification_evidence:" in item for item in mismatches)


def test_reconciliation_reads_one_pinned_root_during_transient_path_swap(tmp_path, monkeypatch):
    import harness_coordinator.v1.reconcile as reconcile_module

    root = tmp_path / "state"
    original = _new_state_root()
    shutil.copytree(original, root)
    original_event = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(str(root / "journal.ndjson"), [original_event])
    replacement = tmp_path / "replacement"
    shutil.copytree(root, replacement)
    replacement_event = copy.deepcopy(original_event)
    replacement_event["event_id"] = "replacement-event"
    replacement_event["event_sha256"] = compute_sha256(
        canonical_bytes(replacement_event, omit={"event_sha256"}))
    _write_journal(str(replacement / "journal.ndjson"), [replacement_event])
    parked = tmp_path / "parked"
    real_read = reconcile_module._read_journal_pinned

    def swap_around_pinned_read(handle, state_root_id):
        os.rename(root, parked)
        os.rename(replacement, root)
        try:
            return real_read(handle, state_root_id)
        finally:
            os.rename(root, replacement)
            os.rename(parked, root)

    monkeypatch.setattr(reconcile_module, "_read_journal_pinned", swap_around_pinned_read)
    with open_state_root(str(root)) as handle:
        report = build_reconciliation_report(
            str(root), "srid-1", "coord-1", "run-1", "reconciliation-run-1",
            "2026-08-11T13:00:00Z", handle=handle)
    assert report["journal_head"]["event_sha256"] == original_event["event_sha256"]
    assert not (root / "reports").exists()


def test_status_is_read_only():
    root = _new_state_root()
    started = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None})
    _write_journal(os.path.join(root, "journal.ndjson"), [started])
    before = sorted(
        (os.path.relpath(os.path.join(base, name), root), os.path.getsize(os.path.join(base, name)))
        for base, _, names in os.walk(root) for name in names)
    status = run_status(root, "srid-1")
    after = sorted(
        (os.path.relpath(os.path.join(base, name), root), os.path.getsize(os.path.join(base, name)))
        for base, _, names in os.walk(root) for name in names)
    assert status["error"] is False
    assert before == after


def test_attempt_evidence_is_bound_to_exact_origin(tmp_path):
    root, packet, result, evidence, outcome, started, run_started = _bound_evidence(tmp_path)
    with open_state_root(str(root)) as handle:
        loaded_result, loaded_evidence, stdout, stderr = load_and_validate_attempt_evidence(
            handle, packet["packet_id"], packet["packet_sha256"], 1,
            outcome, started, run_started)
    assert loaded_result == result
    assert loaded_evidence == evidence
    assert stdout == b"" and stderr == b"rate limit exceeded"


def test_prior_attempt_provider_evidence_cannot_authorize_fallback(tmp_path):
    root, packet, _, evidence, outcome, started, run_started = _bound_evidence(tmp_path)
    stale = copy.deepcopy(evidence)
    stale["attempt"] = 2
    stale["evidence_sha256"] = compute_sha256(canonical_bytes(stale, omit={"evidence_sha256"}))
    changed_outcome = copy.deepcopy(outcome)
    changed_outcome["provider_evidence_sha256"] = stale["evidence_sha256"]
    changed_outcome["outcome_sha256"] = compute_sha256(
        canonical_bytes(changed_outcome, omit={"outcome_sha256"}))
    with open_state_root(str(root)) as handle:
        handle.unlink(("results", packet["packet_id"], "1", "provider_evidence.json"))
        handle.publish(("results", packet["packet_id"], "1", "provider_evidence.json"), canonical_bytes(stale))
        handle.unlink(("results", packet["packet_id"], "1", "attempt_outcome.json"))
        handle.publish(("results", packet["packet_id"], "1", "attempt_outcome.json"), canonical_bytes(changed_outcome))
        with pytest.raises(ReassignmentConflict, match="another packet or attempt"):
            load_and_validate_attempt_evidence(
                handle, packet["packet_id"], packet["packet_sha256"], 1,
                changed_outcome, started, run_started)


def test_confirmed_exhaustion_publishes_before_digest_bound_transition(tmp_path):
    root, packet, _, provider_evidence, outcome, _, _ = _bound_evidence(tmp_path)
    root = str(root)
    run_payload = _run_payload()
    run_payload["coordinator"] = {"coordinator_id": "coord-1", "boot_id": "boot-1",
                                  "hostname": "host-1", "pid": 1}
    run_event = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": run_payload, "report": None})
    started_payload = {"attempt": 1, "lane": "kimi_implementation",
                       "worker": {**packet["assigned_worker"], "session_id": "session-1",
                                  "lane": "kimi_implementation"},
                       "claim_sha256": None, "worktree_path": packet["worktree"]["path"]}
    started_event = _make_event(
        2, "ATTEMPT_STARTED", prev_event=run_event, packet_id=packet["packet_id"],
        intent_id="attempt-1", from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": started_payload, "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None,
                 "run": None, "report": None})
    events = [run_event, started_event]
    _write_journal(os.path.join(root, "journal.ndjson"), events)
    registry = {
        "schema_version": 1, "registry_id": "reg-1",
        "providers": {"local": [{"rule_id": "rate", "channel": "stderr",
                                  "match_kind": "substring", "pattern": "rate limit exceeded",
                                  "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
                                  "captured_from": {"sample_path": "trust/sample.json",
                                                    "sample_sha256": "0" * 64,
                                                    "captured_at": "2026-08-10T00:00:00Z"}}]},
        "registry_sha256": "",
    }
    registry["registry_sha256"] = compute_sha256(canonical_bytes(registry, omit={"registry_sha256"}))
    folded = {"packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
              "lane": "kimi_implementation", "retry_limit": 3, "attempts_started": 1,
              "sonnet_reassignment_allowed": True, "reassignment_used": False}
    with open_state_root(root) as handle:
        updated = _finish_attempt(
            root, os.path.join(root, "journal.ndjson"), os.path.join(root, "locks", "journal.wlock"),
            events, packet["packet_id"], "attempt-1", 1, folded,
            started_payload["worker"], outcome, provider_evidence, registry, "coord-2", "run-2", "srid-1",
            "2026-08-11T13:01:00Z", handle=handle,
            available_lanes=["kimi_implementation", "sonnet_implementation"])
        artifact = handle.read(("reassignments", f"{packet['packet_id']}.json"))
    assert artifact is not None
    record = __import__("json").loads(artifact)
    finished = updated[-1]
    assert finished["cause"] == "provider_exhausted_reassignment"
    assert finished["payload"]["classification"]["reassignment_record_sha256"] == record["reassignment_sha256"]


@pytest.mark.parametrize(
    "change,available_lanes,expected",
    [("disallowed", ["kimi_implementation", "sonnet_implementation"], "fallback_not_permitted"),
     ("budget", ["kimi_implementation", "sonnet_implementation"], "attempt_budget_exhausted"),
     ("unavailable", ["kimi_implementation"], "fallback_not_permitted")],
)
def test_p5d_fallback_refusals_never_publish_reassignment(
        tmp_path, change, available_lanes, expected):
    root, packet, evidence, outcome, events, attempt_payload, registry, folded = (
        _exhaustion_finish_fixture(tmp_path))
    if change == "disallowed":
        folded["sonnet_reassignment_allowed"] = False
    elif change == "budget":
        folded["attempts_started"] = folded["retry_limit"] + 1
    with open_state_root(root) as handle:
        updated = _finish_attempt(
            root, os.path.join(root, "journal.ndjson"),
            os.path.join(root, "locks", "journal.wlock"), events, packet["packet_id"],
            "attempt-1", 1, folded, attempt_payload["worker"], outcome, evidence, registry,
            "coord-2", "run-2", "srid-1", "2026-08-11T13:01:00Z", handle=handle,
            available_lanes=available_lanes)
        assert handle.read(("reassignments", f"{packet['packet_id']}.json")) is None
    finished = updated[-1]
    assert finished["cause"] == expected
    assert finished["to_state"] == "QUARANTINED"


def test_quarantined_packet_does_not_block_independent_ready_selection():
    packets = {
        "bad": {"packet_id": "bad", "state": "QUARANTINED", "enqueue_seq": 1,
                "lane": "kimi_implementation", "attempts_started": 1, "retry_limit": 3},
        "good": {"packet_id": "good", "state": "READY", "enqueue_seq": 2,
                 "lane": "kimi_implementation", "attempts_started": 0, "retry_limit": 3,
                 "next_eligible_at": None},
    }
    assert select_next(packets, [], "2026-08-11T13:02:00Z") == "good"


def test_reassignment_artifact_before_event_resumes_identically(tmp_path, monkeypatch):
    import harness_coordinator.v1.classify_runtime as classify_module

    root, packet, _, provider_evidence, outcome, _, _ = _bound_evidence(tmp_path)
    root = str(root)
    run_payload = _run_payload()
    run_payload["coordinator"] = {"coordinator_id": "coord-1", "boot_id": "boot-1",
                                  "hostname": "host-1", "pid": 1}
    run_event = _make_event(1, "RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": run_payload, "report": None})
    attempt_payload = {"attempt": 1, "lane": "kimi_implementation",
                       "worker": {**packet["assigned_worker"], "session_id": "session-1",
                                  "lane": "kimi_implementation"},
                       "claim_sha256": None, "worktree_path": packet["worktree"]["path"]}
    started = _make_event(2, "ATTEMPT_STARTED", prev_event=run_event,
                          packet_id=packet["packet_id"], intent_id="attempt-1",
                          from_state="READY", to_state="RUNNING", cause="claim_committed",
                          payload={"packet": None, "attempt": attempt_payload, "artifacts": [],
                                   "classification": None, "transition_detail": None,
                                   "recovery": None, "run": None, "report": None})
    events = [run_event, started]
    _write_journal(os.path.join(root, "journal.ndjson"), events)
    registry = {"schema_version": 1, "registry_id": "reg-1", "providers": {"local": [{
        "rule_id": "rate", "channel": "stderr", "match_kind": "substring",
        "pattern": "rate limit exceeded", "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        "captured_from": {"sample_path": "trust/sample.json", "sample_sha256": "0" * 64,
                          "captured_at": "2026-08-10T00:00:00Z"}}]}, "registry_sha256": ""}
    registry["registry_sha256"] = compute_sha256(canonical_bytes(registry, omit={"registry_sha256"}))
    folded = {"packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
              "lane": "kimi_implementation", "retry_limit": 3, "attempts_started": 1,
              "sonnet_reassignment_allowed": True, "reassignment_used": False}
    real_append = classify_module.append_journal
    with open_state_root(root) as handle:
        monkeypatch.setattr(classify_module, "append_journal",
                            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash")))
        with pytest.raises(RuntimeError, match="crash"):
            _finish_attempt(
                root, os.path.join(root, "journal.ndjson"), os.path.join(root, "locks", "journal.wlock"),
                events, packet["packet_id"], "attempt-1", 1, folded, attempt_payload["worker"],
                outcome, provider_evidence, registry, "coord-2", "run-2", "srid-1",
                "2026-08-11T13:01:00Z", handle=handle,
                available_lanes=["kimi_implementation", "sonnet_implementation"])
        before = handle.read(("reassignments", f"{packet['packet_id']}.json"))
        monkeypatch.setattr(classify_module, "append_journal", real_append)
        updated = _finish_attempt(
            root, os.path.join(root, "journal.ndjson"), os.path.join(root, "locks", "journal.wlock"),
            events, packet["packet_id"], "attempt-1", 1, folded, attempt_payload["worker"],
            outcome, provider_evidence, registry, "coord-2", "run-2", "srid-1",
            "2026-08-11T13:01:00Z", handle=handle,
            available_lanes=["kimi_implementation", "sonnet_implementation"])
        after = handle.read(("reassignments", f"{packet['packet_id']}.json"))
    assert before == after
    assert len([event for event in updated if event["event_type"] == "ATTEMPT_FINISHED"]) == 1


def test_once_fails_closed_when_real_result_omits_reconciliation(tmp_path, monkeypatch):
    import harness_coordinator.v1.run_cli as run_cli

    (tmp_path / "MANIFEST.json").write_text("{}")
    monkeypatch.setattr(run_cli, "derive_local_process_context", lambda *args: {})
    monkeypatch.setattr(run_cli, "run_once",
                        lambda *args: {"status": "no_eligible_work", "packet_id": None})
    assert run_cli.main(["--once", "--state-root", str(tmp_path),
                         "--coordinator-id", "coord-1", "--run-id", "run-1",
                         "--now", "2026-08-11T13:00:00Z"]) == 1


def test_status_corrupt_root_is_machine_readable_and_write_free(tmp_path, capsys):
    import harness_coordinator.v1.cli as cli

    before = list(tmp_path.iterdir())
    code = cli.main(["status", "--state-root", str(tmp_path), "--state-root-id", "srid-1"])
    payload = __import__("json").loads(capsys.readouterr().out)
    assert code == 1 and payload["error"] is True
    assert list(tmp_path.iterdir()) == before
