"""Disposable synthetic commissioning of the real P5 coordinator path."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from harness_coordinator.v1.coordinator import attempt_session_id, run_once
from harness_coordinator.v1.enroll import enroll_packets
from harness_coordinator.v1.invoke import WorkerAdapter
from harness_coordinator.v1.recovery import _fold_journal
from harness_coordinator.v1.store import read_journal
from test_o3_p5_review import (
    COORD_ID, RUN_ID, STATE_ROOT_ID, T_ENROLL, T_NOW,
    _deposit, _packet, _verdict, _worker_result, _write_manifest, _write_trust_roots,
)


WORKER = str(Path(__file__).with_name("synthetic_p5_worker.py").resolve())
REVIEWER = str(Path(__file__).with_name("synthetic_p5_reviewer.py").resolve())


def _context(coordinator_id=COORD_ID):
    return {"coordinator_id": coordinator_id, "hostname": "synthetic-host",
            "boot_id": "synthetic-boot", "pid": os.getpid(),
            "live_coordinator_ids": {coordinator_id}, "now": T_NOW}


def _git(path, *args):
    return subprocess.run(
        ["git", *args], cwd=str(path), check=True, text=True, capture_output=True,
        env={"PATH": os.environ["PATH"], "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1"},
    ).stdout.strip()


def _registered_worktrees(tmp_path, *names):
    """Create disposable registered packet worktrees without changing assertions."""
    repo = tmp_path / "packet-repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "O3 Test")
    _git(repo, "config", "user.email", "o3@example.test")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")
    worktrees = []
    for name in names:
        branch = "codex/%s" % name
        path = tmp_path / ("worktree-" + name)
        _git(repo, "branch", branch)
        _git(repo, "worktree", "add", str(path), branch)
        worktrees.append((os.path.realpath(str(path)), branch, _git(path, "rev-parse", "HEAD")))
    return worktrees


def _registered_packet(packet_id, worktree):
    path, branch, revision = worktree
    packet = _packet(packet_id, worktree=path)
    packet["worktree"]["branch"] = branch
    packet["starting_revision"] = revision
    from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


def _adapter(packet, run_id, marker, attempt=1):
    session = attempt_session_id(run_id, packet["packet_id"], attempt)
    result = _worker_result(
        packet, session, attempt=attempt,
        dependency_evidence=tuple(packet.get("dependency_ids") or ()))
    return WorkerAdapter(
        argv=(WORKER,),
        env={"SYNTHETIC_RESULT": json.dumps(result, sort_keys=True, separators=(",", ":")),
             "SYNTHETIC_MARKER_PATH": marker})


def _review(verdict):
    completed = subprocess.run(
        [REVIEWER], input=json.dumps(verdict), capture_output=True, text=True,
        check=True, timeout=5, env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    return json.loads(completed.stdout)


def test_real_run_once_invokes_synthetic_worker_and_reaches_review(tmp_path):
    state_root = os.path.realpath(str(tmp_path / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    packet = _registered_packet("commission-root", _registered_worktrees(tmp_path, "root")[0])
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, [packet])
    session = attempt_session_id(RUN_ID, packet["packet_id"], 1)
    result = _worker_result(packet, session, attempt=1)
    marker = str(tmp_path / "worker-markers.txt")
    adapter = WorkerAdapter(
        argv=(WORKER,),
        env={"SYNTHETIC_RESULT": json.dumps(result, sort_keys=True, separators=(",", ":")),
             "SYNTHETIC_MARKER_PATH": marker},
    )

    outcome = run_once(
        state_root, COORD_ID, RUN_ID, _context(), T_NOW,
        worker_adapters={"kimi_implementation": adapter})

    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert torn is None
    assert outcome["status"] == "completed_attempt"
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == ["commission-root:1"]
    assert len([e for e in events if e["event_type"] == "ATTEMPT_STARTED"]) == 1
    assert len([e for e in events if e["event_type"] == "WORKER_RESULT_RECORDED"]) == 1
    assert len([e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]) == 1


def test_dependency_chain_reaches_terminal_through_synthetic_runtime(tmp_path):
    state_root = os.path.realpath(str(tmp_path / "state-chain"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    root_worktree, child_worktree = _registered_worktrees(tmp_path, "parent", "child")
    root_packet = _registered_packet("commission-parent", root_worktree)
    child_packet = _registered_packet("commission-child", child_worktree)
    child_packet["dependency_ids"] = ["commission-parent"]
    from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
    child_packet["packet_sha256"] = compute_sha256(canonical_bytes(child_packet, omit={"packet_sha256"}))
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL,
                   [root_packet, child_packet])
    marker = str(tmp_path / "chain-markers.txt")

    first = run_once(
        state_root, COORD_ID, "commission-run-1", _context(), T_NOW,
        worker_adapters={"commission-parent": _adapter(root_packet, "commission-run-1", marker)})
    assert first["packet_id"] == "commission-parent"
    parent_result = _worker_result(
        root_packet, attempt_session_id("commission-run-1", "commission-parent", 1), attempt=1)
    _deposit(state_root, "commission-parent", 1, _review(_verdict(root_packet, parent_result)))

    second = run_once(
        state_root, COORD_ID, "commission-run-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={"commission-child": _adapter(child_packet, "commission-run-2", marker)})
    interim_events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                     state_root_id=STATE_ROOT_ID)
    interim_folded, _ = _fold_journal(state_root, interim_events)
    assert second["packet_id"] == "commission-child", (second, interim_folded)
    child_result = _worker_result(
        child_packet, attempt_session_id("commission-run-2", "commission-child", 1), attempt=1,
        dependency_evidence=("commission-parent",))
    _deposit(state_root, "commission-child", 1, _review(_verdict(child_packet, child_result)))

    third = run_once(
        state_root, COORD_ID, "commission-run-3", _context(), "2026-08-10T01:13:00Z",
        worker_adapters={})
    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert torn is None
    assert third["status"] == "no_eligible_work"
    assert folded["commission-parent"]["state"] == "ACCEPTED"
    assert folded["commission-child"]["state"] == "ACCEPTED"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == [
        "commission-parent:1", "commission-child:1"]
    assert len([e for e in events if e["event_type"] == "VERDICT_RECORDED"]) == 2
    assert len([e for e in events if e["event_type"] == "RECONCILIATION_EMITTED"]) == 3
    guarded_types = {"ATTEMPT_STARTED", "WORKER_RESULT_RECORDED", "ATTEMPT_FINISHED",
                     "VERDICT_RECORDED", "STATE_TRANSITION", "RECONCILIATION_EMITTED"}
    before_counts = {kind: len([e for e in events if e["event_type"] == kind])
                     for kind in guarded_types}
    repeat = run_once(
        state_root, COORD_ID, "commission-run-3", _context(), "2026-08-10T01:13:00Z",
        worker_adapters={})
    assert repeat["status"] == "no_eligible_work"
    repeated_events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                      state_root_id=STATE_ROOT_ID)
    assert {kind: len([e for e in repeated_events if e["event_type"] == kind])
            for kind in guarded_types} == before_counts
    assert Path(marker).read_text(encoding="utf-8").splitlines() == [
        "commission-parent:1", "commission-child:1"]


def _single_packet_state(tmp_path, packet_id):
    state_root = os.path.realpath(str(tmp_path / f"state-{packet_id}"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    packet = _registered_packet(packet_id, _registered_worktrees(tmp_path, packet_id)[0])
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, [packet])
    return state_root, packet


def test_crash_before_invoke_requeues_then_executes_only_new_attempt(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator_module

    state_root, packet = _single_packet_state(tmp_path, "commission-preinvoke")
    marker = str(tmp_path / "preinvoke-markers.txt")
    real_invoke = coordinator_module.invoke_worker
    monkeypatch.setattr(
        coordinator_module, "invoke_worker",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("pre-invoke crash")))
    try:
        run_once(
            state_root, COORD_ID, "preinvoke-run-1", _context(), T_NOW,
            worker_adapters={packet["packet_id"]: _adapter(packet, "preinvoke-run-1", marker)})
    except RuntimeError as exc:
        assert str(exc) == "pre-invoke crash"
    else:
        raise AssertionError("injected pre-invoke crash did not occur")
    monkeypatch.setattr(coordinator_module, "invoke_worker", real_invoke)

    resumed = run_once(
        state_root, COORD_ID, "preinvoke-run-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={packet["packet_id"]: _adapter(
            packet, "preinvoke-run-2", marker, attempt=2)})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert resumed["status"] == "completed_attempt"
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == [
        "commission-preinvoke:2"]
    assert len([e for e in events if e["event_type"] == "ATTEMPT_STARTED"]) == 2


def test_crash_after_durable_outcome_resumes_without_reinvocation(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator_module

    state_root, packet = _single_packet_state(tmp_path, "commission-postoutcome")
    marker = str(tmp_path / "postoutcome-markers.txt")
    real_resolve = coordinator_module.resolve_open_attempts
    calls = {"count": 0}

    def crash_second_resolution(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("post-outcome crash")
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(coordinator_module, "resolve_open_attempts", crash_second_resolution)
    try:
        run_once(
            state_root, COORD_ID, "postoutcome-run-1", _context(), T_NOW,
            worker_adapters={packet["packet_id"]: _adapter(
                packet, "postoutcome-run-1", marker)})
    except RuntimeError as exc:
        assert str(exc) == "post-outcome crash"
    else:
        raise AssertionError("injected post-outcome crash did not occur")
    monkeypatch.setattr(coordinator_module, "resolve_open_attempts", real_resolve)

    resumed = run_once(
        state_root, COORD_ID, "postoutcome-run-2", _context(),
        "2026-08-10T01:12:00Z", worker_adapters={})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert resumed["status"] == "no_eligible_work"
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == [
        "commission-postoutcome:1"]
    assert len([e for e in events if e["event_type"] == "WORKER_RESULT_RECORDED"]) == 1
    assert len([e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]) == 1


def test_crash_after_worker_before_outcome_consumes_receipt_without_reinvocation(
        tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator_module

    state_root, packet = _single_packet_state(tmp_path, "commission-receipt")
    marker = str(tmp_path / "receipt-markers.txt")
    adapter = _adapter(packet, "receipt-run-1", marker)
    real_persist = coordinator_module.persist_invocation_outcome
    monkeypatch.setattr(
        coordinator_module, "persist_invocation_outcome",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("receipt-only crash")))
    with pytest.raises(RuntimeError, match="receipt-only crash"):
        run_once(
            state_root, COORD_ID, "receipt-run-1", _context(), T_NOW,
            worker_adapters={packet["packet_id"]: adapter})
    monkeypatch.setattr(coordinator_module, "persist_invocation_outcome", real_persist)

    with pytest.raises(RuntimeError, match="requires its operator adapter"):
        run_once(
            state_root, COORD_ID, "receipt-run-missing-adapter", _context(),
            "2026-08-10T01:11:00Z", worker_adapters={})
    barrier_events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                     state_root_id=STATE_ROOT_ID)
    assert len([e for e in barrier_events if e["event_type"] == "ATTEMPT_STARTED"]) == 1
    assert Path(marker).read_text(encoding="utf-8").splitlines() == ["commission-receipt:1"]

    resumed = run_once(
        state_root, COORD_ID, "receipt-run-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={packet["packet_id"]: adapter})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert resumed["status"] == "no_eligible_work"
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == ["commission-receipt:1"]
    assert len([e for e in events if e["event_type"] == "ATTEMPT_STARTED"]) == 1
    assert len([e for e in events if e["event_type"] == "WORKER_RESULT_RECORDED"]) == 1
    assert len([e for e in events if e["event_type"] == "ATTEMPT_FINISHED"]) == 1


def test_partial_result_publication_resumes_idempotently_from_receipt(tmp_path, monkeypatch):
    import harness_coordinator.v1.invoke as invoke_module

    state_root, packet = _single_packet_state(tmp_path, "commission-partial")
    marker = str(tmp_path / "partial-markers.txt")
    adapter = _adapter(packet, "partial-run-1", marker)
    real_validate = invoke_module.validate_attempt_outcome
    monkeypatch.setattr(
        invoke_module, "validate_attempt_outcome",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("partial persist crash")))
    with pytest.raises(RuntimeError, match="partial persist crash"):
        run_once(
            state_root, COORD_ID, "partial-run-1", _context(), T_NOW,
            worker_adapters={packet["packet_id"]: adapter})
    assert Path(state_root, "results", packet["packet_id"], "1", "worker-result.json").exists()
    assert not Path(state_root, "results", packet["packet_id"], "1", "attempt_outcome.json").exists()
    monkeypatch.setattr(invoke_module, "validate_attempt_outcome", real_validate)

    run_once(
        state_root, COORD_ID, "partial-run-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={packet["packet_id"]: adapter})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == ["commission-partial:1"]
    assert len([e for e in events if e["event_type"] == "ATTEMPT_STARTED"]) == 1


def test_fsynced_pending_receipt_recovers_after_atomic_publish_failure(tmp_path, monkeypatch):
    import harness_coordinator.v1.invoke as invoke_module

    state_root, packet = _single_packet_state(tmp_path, "commission-pending-receipt")
    marker = str(tmp_path / "pending-receipt-markers.txt")
    adapter = _adapter(packet, "pending-receipt-run-1", marker)
    real_link = invoke_module.os.link
    failed = {"done": False}

    def fail_completion_link(source, destination, *args, **kwargs):
        if source == "completion.pending" and destination == "completion.json" and not failed["done"]:
            failed["done"] = True
            raise OSError("injected completion publication failure")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(invoke_module.os, "link", fail_completion_link)
    with pytest.raises(OSError, match="injected completion publication failure"):
        run_once(
            state_root, COORD_ID, "pending-receipt-run-1", _context(), T_NOW,
            worker_adapters={packet["packet_id"]: adapter})
    intent = f"attempt-{packet['packet_id']}-1"
    assert Path(state_root, "invocations", intent, "completion.pending").exists()
    assert not Path(state_root, "invocations", intent, "completion.json").exists()
    monkeypatch.setattr(invoke_module.os, "link", real_link)

    run_once(
        state_root, COORD_ID, "pending-receipt-run-2", _context(),
        "2026-08-10T01:12:00Z", worker_adapters={packet["packet_id"]: adapter})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert Path(marker).read_text(encoding="utf-8").splitlines() == [
        "commission-pending-receipt:1"]
    assert len([e for e in events if e["event_type"] == "ATTEMPT_STARTED"]) == 1


def test_crash_after_verdict_resumes_sealing_without_duplicate_verdict(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator_module
    from harness_coordinator.v1.seals_runtime import terminal_seal_path

    state_root, packet = _single_packet_state(tmp_path, "commission-postverdict")
    marker = str(tmp_path / "postverdict-markers.txt")
    run_once(
        state_root, COORD_ID, "postverdict-run-1", _context(), T_NOW,
        worker_adapters={packet["packet_id"]: _adapter(
            packet, "postverdict-run-1", marker)})
    result = _worker_result(
        packet, attempt_session_id("postverdict-run-1", packet["packet_id"], 1), attempt=1)
    _deposit(state_root, packet["packet_id"], 1, _review(_verdict(packet, result)))
    real_complete = coordinator_module.complete_terminal_seals
    calls = {"count": 0}

    def crash_second_seal_pass(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("post-verdict crash")
        return real_complete(*args, **kwargs)

    monkeypatch.setattr(coordinator_module, "complete_terminal_seals", crash_second_seal_pass)
    try:
        run_once(
            state_root, COORD_ID, "postverdict-run-2", _context(),
            "2026-08-10T01:12:00Z", worker_adapters={})
    except RuntimeError as exc:
        assert str(exc) == "post-verdict crash"
    else:
        raise AssertionError("injected post-verdict crash did not occur")
    assert not os.path.exists(terminal_seal_path(state_root, packet["packet_id"]))
    monkeypatch.setattr(coordinator_module, "complete_terminal_seals", real_complete)

    run_once(
        state_root, COORD_ID, "postverdict-run-3", _context(),
        "2026-08-10T01:13:00Z", worker_adapters={})
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "ACCEPTED"
    assert os.path.exists(terminal_seal_path(state_root, packet["packet_id"]))
    assert len([e for e in events if e["event_type"] == "VERDICT_RECORDED"]) == 1


def test_commissioning_proves_top_level_singleton_separately(tmp_path):
    from test_o3_p5_enrollment import test_two_top_level_coordinators_admit_one_singleton_winner
    test_two_top_level_coordinators_admit_one_singleton_winner(tmp_path)


def test_commissioning_proves_lower_level_claim_contention_separately(tmp_path):
    from test_o3_p5_enrollment import test_lower_level_claim_contention_has_exactly_one_winner
    test_lower_level_claim_contention_has_exactly_one_winner(tmp_path)


def test_write_cli_once_returns_deterministic_success_for_empty_roots(
        tmp_path, monkeypatch, capsys):
    import harness_coordinator.v1.run_cli as run_cli_module

    outputs = []
    for index in range(2):
        root = os.path.realpath(str(tmp_path / f"empty-cli-{index}"))
        os.makedirs(os.path.join(root, "locks"))
        _write_manifest(root)
        _write_trust_roots(root)
        monkeypatch.setattr(
            run_cli_module, "derive_local_process_context",
            lambda coordinator_id, now: _context(coordinator_id))
        exit_code = run_cli_module.main([
            "--once", "--state-root", root, "--coordinator-id", "coord-cli",
            "--run-id", "run-cli", "--now", T_NOW])
        assert exit_code == 0
        outputs.append(json.loads(capsys.readouterr().out))
    assert outputs[0] == outputs[1]
    assert outputs[0]["status"] == "no_eligible_work"
    assert outputs[0]["reconciliation"]["all_invariants_passed"] is True
