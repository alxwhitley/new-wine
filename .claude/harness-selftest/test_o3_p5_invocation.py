"""P5B bounded synthetic worker invocation tests."""

import json
import os
import signal
import sys
import time
import uuid
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
PYTHON_EXECUTABLE = os.path.realpath(sys.executable)
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.coordinator import attempt_session_id
from harness_coordinator.v1.invoke import WorkerAdapter, invoke_worker
from harness_coordinator.v1.process_sidecar import (
    _linux_stat_starttime,
    process_start_identity,
    read_sidecar,
    terminate_sidecar_process,
    write_sidecar,
)


def _packet(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir(exist_ok=True)
    return {
        "packet_id": "pkt-p5b",
        "packet_sha256": "a" * 64,
        "attempt": 1,
        "lane": "kimi_implementation",
        "assigned_worker": {"worker_id": "synthetic", "provider": "local", "model": "fixture"},
        "starting_revision": "b" * 40,
        "worktree": {"path": str(worktree), "branch": "fixture"},
        "writable_paths": ["allowed.txt"],
        "forbidden_surfaces": ["forbidden.txt"],
    }


def _worker_result(packet, session_id, changed_path="allowed.txt"):
    result = {
        "schema_version": 1,
        "result_id": "res-p5b",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "attempt": packet["attempt"],
        "worker": {**packet["assigned_worker"], "session_id": session_id, "lane": packet["lane"]},
        "started_at": "2026-08-10T12:00:00Z",
        "finished_at": "2026-08-10T12:00:01Z",
        "starting_revision": packet["starting_revision"],
        "ending_revision": packet["starting_revision"],
        "outcome": "COMPLETED",
        "changed_files": [{"path": changed_path, "status": "modified", "before_sha256": "c" * 64, "after_sha256": "d" * 64}],
        "commands": [],
        "evidence": [{"evidence_id": "ev", "kind": "verification", "criterion_ids": ["ac"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "synthetic proof"}],
        "criteria": [{"criterion_id": "ac", "status": "SATISFIED", "evidence_ids": ["ev"]}],
        "checkpoints": [{"artifact_id": "cp", "path": "allowed.txt", "sha256": "e" * 64}],
        "remaining_criterion_ids": [], "fallback": None, "human_required_reasons": [],
        "budgets": {"turns_used": 1, "output_bytes": 1, "retry_count": 0, "allowance_used": "synthetic"},
    }
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    return result


WRITE_RESULT = """import json, os
value = json.loads(os.environ['SYNTHETIC_RESULT'])
with os.fdopen(os.dup(int(os.environ['HARNESS_RESULT_FD'])), 'w', encoding='utf-8') as f:
    json.dump(value, f, sort_keys=True, separators=(',', ':'))
"""


def _terminate_from_parent(path, *identity, grace_seconds=.1):
    directory_fd = os.open(str(path.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        return terminate_sidecar_process(directory_fd, path.name, *identity, grace_seconds=grace_seconds)
    finally:
        os.close(directory_fd)


def _invoke(tmp_path, code, result=None, **kwargs):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], packet["attempt"])
    env = {"SYNTHETIC_RESULT": json.dumps(result or _worker_result(packet, session), separators=(",", ":"))}
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code), env=env)
    nonce = uuid.uuid4().hex
    outcome = invoke_worker(str(tmp_path / ("state-" + nonce)), "root-id", packet, "attempt-" + nonce, session, adapter, allowed_worktree=packet["worktree"]["path"], **kwargs)
    return packet, session, outcome


def test_exit_before_result_is_reported(tmp_path):
    _, _, outcome = _invoke(tmp_path, "raise SystemExit(0)")
    assert outcome.result is None
    assert "RESULT_MISSING" in outcome.error_codes


def test_malformed_and_schema_invalid_results_are_rejected(tmp_path):
    _, _, malformed = _invoke(tmp_path, "import os; os.write(int(os.environ['HARNESS_RESULT_FD']), b'{')")
    assert "INVALID_JSON" in malformed.error_codes
    _, _, invalid = _invoke(tmp_path, "import os; os.write(int(os.environ['HARNESS_RESULT_FD']), b'{}')")
    assert "MISSING_FIELD" in invalid.error_codes


def test_timeout_kills_entire_process_group(tmp_path):
    code = """import os, subprocess, sys, time
p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
open(os.environ['SYNTHETIC_MARKER_PATH'],'w').write(str(p.pid))
time.sleep(60)
"""
    marker = tmp_path / "child.pid"
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code), env={"SYNTHETIC_MARKER_PATH": str(marker)})
    outcome = invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-pkt-p5b-1", session, adapter, allowed_worktree=packet["worktree"]["path"], timeout_seconds=.5, terminate_grace_seconds=.1)
    assert outcome.timed_out and outcome.process_group_dead
    child_pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_output_cap_terminates_worker(tmp_path):
    _, _, outcome = _invoke(tmp_path, "import sys,time; print('x'*100000); sys.stdout.flush(); time.sleep(60)", output_limit_bytes=1024, timeout_seconds=3)
    assert outcome.output_exceeded and outcome.process_group_dead
    assert os.path.getsize(outcome.stdout_path) <= 1024


def test_output_cap_is_aggregate_across_stdout_and_stderr(tmp_path):
    code = "import os,time; os.write(1,b'x'*700); os.write(2,b'y'*700); time.sleep(60)"
    _, _, outcome = _invoke(tmp_path, code, output_limit_bytes=1024, timeout_seconds=3)
    assert outcome.output_exceeded and outcome.process_group_dead
    assert os.path.getsize(outcome.stdout_path) + os.path.getsize(outcome.stderr_path) <= 1024


def test_interruption_before_and_during_invocation(tmp_path):
    _, _, before = _invoke(tmp_path, WRITE_RESULT, stop_requested=lambda: True)
    assert before.interrupted and before.pid is None
    started = time.monotonic()
    _, _, during = _invoke(tmp_path, "import time; time.sleep(60)", stop_requested=lambda: time.monotonic() - started > .1, timeout_seconds=3)
    assert during.interrupted and during.process_group_dead


def test_secret_environment_is_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    code = """import json, os
os.write(int(os.environ['HARNESS_RESULT_FD']), os.environ.get('ANTHROPIC_API_KEY','{}').encode())
"""
    _, _, outcome = _invoke(tmp_path, code)
    assert "ANTHROPIC_API_KEY" not in outcome.environment_keys
    assert "MISSING_FIELD" in outcome.error_codes


def test_result_identity_and_forbidden_path_are_rejected(tmp_path):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    wrong = _worker_result(packet, "wrong-session")
    _, _, identity = _invoke(tmp_path, WRITE_RESULT, result=wrong)
    assert "RESULT_IDENTITY_MISMATCH" in identity.error_codes
    forbidden = _worker_result(packet, session, "forbidden.txt")
    _, _, path = _invoke(tmp_path, WRITE_RESULT, result=forbidden)
    assert "FORBIDDEN_PATH" in path.error_codes
    wrong_worker = _worker_result(packet, session)
    wrong_worker["worker"]["provider"] = "substituted"
    wrong_worker["result_sha256"] = compute_sha256(canonical_bytes(wrong_worker, omit={"result_sha256"}))
    _, _, worker = _invoke(tmp_path, WRITE_RESULT, result=wrong_worker)
    assert "RESULT_IDENTITY_MISMATCH" in worker.error_codes


def test_result_path_symlink_substitution_is_rejected(tmp_path):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    result = _worker_result(packet, session)
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "import time; time.sleep(.2)\n" + WRITE_RESULT), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":"))})
    result_path = tmp_path / "state" / "invocations" / "attempt-result-link" / "worker-result.json"
    def replace():
        for _ in range(200):
            if result_path.exists(): break
            time.sleep(.005)
        result_path.unlink(); result_path.symlink_to("/tmp")
    thread = threading.Thread(target=replace); thread.start()
    outcome = invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-result-link", session, adapter, allowed_worktree=packet["worktree"]["path"])
    thread.join()
    assert "RESULT_PATH_UNSAFE" in outcome.error_codes


def test_sidecar_is_self_hashed_and_tamper_detected(tmp_path):
    path = tmp_path / "sidecar.json"
    sidecar = write_sidecar(str(path), "root-id", "pkt-p5b", 1, "intent", os.getpid(), os.getpgrp())
    assert read_sidecar(str(path)) == sidecar
    body = json.loads(path.read_text()); body["pid"] += 1; path.write_bytes(canonical_bytes(body))
    with pytest.raises(ValueError, match="hash"):
        read_sidecar(str(path))


def test_orphan_recovery_requires_matching_process_and_attempt_identity(tmp_path):
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        path = tmp_path / "sidecar.json"
        write_sidecar(str(path), "root-id", "pkt-p5b", 1, "intent", process.pid, process.pid)
        assert _terminate_from_parent(path, "root-id", "pkt-p5b", 1, "intent")
        process.wait(timeout=2)
        path.unlink()
        stale = write_sidecar(str(path), "root-id", "pkt-p5b", 1, "intent", os.getpid(), os.getpgrp())
        stale["process_start_identity"] = "wrong"
        stale["sidecar_sha256"] = compute_sha256(canonical_bytes(stale, omit={"sidecar_sha256"}))
        path.write_bytes(canonical_bytes(stale))
        assert _terminate_from_parent(path, "root-id", "pkt-p5b", 1, "intent") is False
        assert process_start_identity(os.getpid()) is not None
    finally:
        if process.poll() is None:
            process.kill()


def test_sidecar_refuses_wrong_expected_identity_without_killing(tmp_path):
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        path = tmp_path / "sidecar.json"
        write_sidecar(str(path), "root-id", "pkt-p5b", 1, "intent", process.pid, process.pid)
        with pytest.raises(ValueError, match="identity"):
            _terminate_from_parent(path, "other-root", "pkt-p5b", 1, "intent")
        assert process.poll() is None
    finally:
        process.kill(); process.wait()


def test_sidecar_refuses_rehashed_wrong_process_group(tmp_path):
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        path = tmp_path / "sidecar.json"
        value = write_sidecar(str(path), "root-id", "pkt-p5b", 1, "intent", process.pid, process.pid)
        value["pgid"] = os.getpgrp()
        value["sidecar_sha256"] = compute_sha256(canonical_bytes(value, omit={"sidecar_sha256"}))
        path.write_bytes(canonical_bytes(value))
        assert _terminate_from_parent(path, "root-id", "pkt-p5b", 1, "intent") is False
        assert process.poll() is None
    finally:
        process.kill(); process.wait()


def test_sidecar_termination_uses_retained_intent_dir_fd_after_alias_replacement(tmp_path):
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    intent = tmp_path / "intent"; intent.mkdir()
    moved = tmp_path / "moved"; replacement = tmp_path / "replacement"; replacement.mkdir()
    original_fd = os.open(str(intent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        write_sidecar(str(intent / "process.json"), "root-id", "pkt-p5b", 1, "intent", process.pid, process.pid)
        fake = write_sidecar(str(replacement / "process.json"), "root-id", "pkt-p5b", 1, "intent", os.getpid(), os.getpgrp())
        intent.rename(moved); intent.symlink_to(replacement, target_is_directory=True)
        with pytest.raises(ValueError, match="basename"):
            terminate_sidecar_process(original_fd, "../process.json", "root-id", "pkt-p5b", 1, "intent", grace_seconds=.1)
        assert process.poll() is None
        assert terminate_sidecar_process(original_fd, "process.json", "root-id", "pkt-p5b", 1, "intent", grace_seconds=.1)
        process.wait(timeout=2)
        assert json.loads((replacement / "process.json").read_text()) == fake
    finally:
        os.close(original_fd)
        if process.poll() is None:
            process.kill(); process.wait()


def test_exception_after_popen_kills_child(monkeypatch, tmp_path):
    import harness_coordinator.v1.invoke as invoke_module
    marker = tmp_path / "pid"
    code = "import os,time; open(os.environ['SYNTHETIC_MARKER_PATH'],'w').write(str(os.getpid())); time.sleep(60)"
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code), env={"SYNTHETIC_MARKER_PATH": str(marker)})
    def fail_sidecar(*args, **kwargs):
        for _ in range(100):
            if marker.exists(): break
            time.sleep(.01)
        raise RuntimeError("sidecar failed")
    monkeypatch.setattr(invoke_module, "write_sidecar", fail_sidecar)
    with pytest.raises(RuntimeError, match="sidecar failed"):
        invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-pkt-p5b-1", session, adapter, allowed_worktree=packet["worktree"]["path"])
    assert marker.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


@pytest.mark.parametrize("key", ["LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONPATH", "ARBITRARY"])
def test_adapter_rejects_non_allowlisted_environment(key):
    with pytest.raises(ValueError, match="environment"):
        WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={key: "x"})


def test_adapter_cannot_override_harness_environment():
    with pytest.raises(ValueError, match="environment"):
        WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={"HARNESS_RESULT_PATH": "/tmp/evil"})


def test_adapter_rejects_relative_worktree_or_path_runner(tmp_path):
    runner = tmp_path / "runner"
    runner.write_text("#!/bin/sh\nexit 0\n"); runner.chmod(0o755)
    with pytest.raises(ValueError, match="absolute"):
        WorkerAdapter(argv=("runner",), env={})


def test_invocation_rejects_symlink_executable_but_absolute_executable_runs(tmp_path):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    link = tmp_path / "python-link"; link.symlink_to(sys.executable)
    adapter = WorkerAdapter(argv=(str(link), "-c", "pass"), env={})
    with pytest.raises(ValueError, match="executable"):
        invoke_worker(str(tmp_path / "state-link"), "root-id", packet, "attempt-link", session, adapter, allowed_worktree=packet["worktree"]["path"])
    outcome = invoke_worker(str(tmp_path / "state-absolute"), "root-id", packet, "attempt-absolute", session,
                            WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", WRITE_RESULT), env={"SYNTHETIC_RESULT": json.dumps(_worker_result(packet, session), separators=(",", ":"))}),
                            allowed_worktree=packet["worktree"]["path"])
    assert outcome.result is not None


def test_worktree_requires_explicit_operator_match_and_is_not_symlink(tmp_path):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={})
    with pytest.raises(ValueError, match="worktree"):
        invoke_worker(str(tmp_path / "state-a"), "root-id", packet, "attempt-a", session, adapter, allowed_worktree=str(tmp_path))
    real = Path(packet["worktree"]["path"]); real.rmdir(); real.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="worktree"):
        invoke_worker(str(tmp_path / "state-b"), "root-id", packet, "attempt-b", session, adapter, allowed_worktree=str(real))


def test_linux_stat_parser_handles_spaces_in_comm():
    tail = ["S"] + [str(i) for i in range(4, 23)]
    stat_line = "123 (worker name with spaces) " + " ".join(tail)
    assert _linux_stat_starttime(stat_line) == "22"


def test_worktree_fd_binds_child_to_original_inode_after_path_replacement(monkeypatch, tmp_path):
    import harness_coordinator.v1.invoke as invoke_module
    packet = _packet(tmp_path)
    original = Path(packet["worktree"]["path"])
    moved = tmp_path / "worktree-original"
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    result = _worker_result(packet, session)
    code = WRITE_RESULT + "\nimport time; time.sleep(.2); open('cwd-proof','w').write('original')\n"
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":"))})
    real_popen = invoke_module.subprocess.Popen
    def replacing_popen(*args, **kwargs):
        original.rename(moved)
        original.mkdir()
        return real_popen(*args, **kwargs)
    monkeypatch.setattr(invoke_module.subprocess, "Popen", replacing_popen)
    outcome = invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-cwd", session, adapter, allowed_worktree=str(original))
    assert (moved / "cwd-proof").read_text() == "original"
    assert not (original / "cwd-proof").exists()
    assert outcome.result is not None


def test_artifact_dir_fd_prevents_canonical_alias_redirection(tmp_path):
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    result = _worker_result(packet, session)
    outside = tmp_path / "outside"; outside.mkdir()
    moved = tmp_path / "state" / "invocations" / "moved"
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "import time; time.sleep(.2)\n" + WRITE_RESULT), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":"))})
    def replace():
        intent = tmp_path / "state" / "invocations" / "attempt-artifact"
        for _ in range(200):
            if (intent / "process.json").exists(): break
            time.sleep(.005)
        intent.rename(moved)
        intent.symlink_to(outside, target_is_directory=True)
    thread = threading.Thread(target=replace); thread.start()
    outcome = invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-artifact", session, adapter, allowed_worktree=packet["worktree"]["path"])
    thread.join()
    assert list(outside.iterdir()) == []
    assert (moved / "worker-result.json").exists()
    assert "ARTIFACT_PATH_UNSAFE" in outcome.error_codes
    assert outcome.result is None
    assert outcome.stdout_path == outcome.stderr_path == outcome.result_path == outcome.sidecar_path == ""


def test_partial_artifact_open_failure_closes_all_descriptors(monkeypatch, tmp_path):
    import harness_coordinator.v1.invoke as invoke_module
    packet = _packet(tmp_path)
    session = attempt_session_id("run-p5b", packet["packet_id"], 1)
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={})
    baseline = len(os.listdir("/dev/fd"))
    real_open = invoke_module.os.open
    def fail_stderr(path, flags, mode=0o777, *, dir_fd=None):
        if path == "stderr.bin" and dir_fd is not None:
            raise OSError("injected staged open failure")
        return real_open(path, flags, mode, dir_fd=dir_fd)
    monkeypatch.setattr(invoke_module.os, "open", fail_stderr)
    with pytest.raises(OSError, match="injected"):
        invoke_worker(str(tmp_path / "state"), "root-id", packet, "attempt-fd", session, adapter, allowed_worktree=packet["worktree"]["path"])
    assert len(os.listdir("/dev/fd")) == baseline
