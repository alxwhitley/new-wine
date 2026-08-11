"""O4 baseline gate tests with disposable Git worktrees only."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.coordinator import run_once
from harness_coordinator.v1.enroll import enroll_packets
from harness_coordinator.v1.invoke import WorkerAdapter
from harness_coordinator.v1.recovery import _fold_journal
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import read_journal
from test_o3_p5_review import (
    COORD_ID, RUN_ID, STATE_ROOT_ID, T_ENROLL, T_NOW, _packet, _worker_result, _write_manifest,
    _deposit, _verdict, _write_trust_roots,
)
from test_o3_p5_commissioning import _commission_result


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True,
        env={"PATH": os.environ["PATH"], "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1"},
    ).stdout.strip()


def _state_with_registered_worktree(tmp_path: Path, packet_id: str):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "O4 Test")
    _git(repo, "config", "user.email", "o4@example.test")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "branch", "codex/o4-packet")
    worktree = tmp_path / "packet-worktree"
    _git(repo, "worktree", "add", str(worktree), "codex/o4-packet")
    packet = _packet(packet_id, worktree=os.path.realpath(worktree))
    packet["starting_revision"] = _git(worktree, "rev-parse", "HEAD")
    packet["worktree"]["branch"] = "codex/o4-packet"
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    state_root = os.path.realpath(tmp_path / "state")
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, [packet])
    return state_root, repo, worktree, packet


def _context():
    return {
        "coordinator_id": COORD_ID, "hostname": "o4-host", "boot_id": "o4-boot",
        "pid": os.getpid(), "live_coordinator_ids": {COORD_ID}, "now": T_NOW,
    }


def test_ensure_attempt_baseline_publishes_exact_canonical_artifact(tmp_path: Path) -> None:
    from harness_coordinator.v1.workspace_evidence import ensure_attempt_baseline

    state_root, repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-baseline")
    with open_state_root(state_root) as handle:
        binding = ensure_attempt_baseline(
            handle, packet, "attempt-o4-baseline-1", str(repo), None, []
        )
        raw = handle.read(tuple(binding["artifact_path"].split("/")))
    artifact = json.loads(raw.decode("utf-8"))
    assert raw == canonical_bytes(artifact)
    assert set(artifact) == {
        "schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
        "worktree_identity", "packet_snapshot", "protected_snapshot", "writable_paths",
        "forbidden_surfaces", "content_sha256", "artifact_sha256",
    }
    assert artifact["packet_snapshot"]["entries"] == []
    assert artifact["packet_id"] == packet["packet_id"]
    assert artifact["packet_sha256"] == packet["packet_sha256"]
    assert artifact["intent_id"] == "attempt-o4-baseline-1"
    assert artifact["content_sha256"] == compute_sha256(
        canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"})
    )
    assert artifact["artifact_sha256"] == compute_sha256(
        canonical_bytes(artifact, omit={"artifact_sha256"})
    )


def test_worker_is_never_called_until_baseline_event_is_durable(tmp_path: Path, monkeypatch) -> None:
    import harness_coordinator.v1.coordinator as coordinator

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-gate")
    invoked = {"value": False}

    def assert_gate(*_args, **_kwargs):
        invoked["value"] = True
        path = Path(state_root, "workspace", packet["packet_id"], f"attempt-{packet['packet_id']}-1.baseline.json")
        assert path.exists()
        events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
        assert torn is None
        event = next(event for event in events if event["event_type"] == "WORKSPACE_BASELINE_RECORDED")
        assert event["packet_id"] == packet["packet_id"]
        assert event["payload"]["artifacts"][0]["path"] == f"workspace/{packet['packet_id']}/attempt-{packet['packet_id']}-1.baseline.json"
        raise RuntimeError("stop after gate assertion")

    monkeypatch.setattr(coordinator, "invoke_worker", assert_gate)
    with pytest.raises(RuntimeError, match="stop after gate assertion"):
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW, worker_adapters={packet["packet_id"]: object()})
    assert invoked["value"]


def test_postflight_does_not_publish_integration_before_accepted_terminal_seal(tmp_path: Path) -> None:
    """Fails if rejected or unreviewed work is labelled an integration candidate."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-integration")
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(
        argv=(str(worker),), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                                 "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt")},
    )
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    path = Path(state_root, "workspace", packet["packet_id"],
                f"attempt-{packet['packet_id']}-1.integration.json")
    assert not path.exists()


def test_accepted_packet_without_operator_context_stays_pending_until_context_arrives(tmp_path: Path) -> None:
    """Fails if missing context permanently consumes an accepted integration slot."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-integration-context")
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(
        argv=(str(worker),), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                                 "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt")},
    )
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    run_once(state_root, COORD_ID, "o4-context-review", _context(), "2026-08-10T01:12:00Z",
             integration_context_by_packet={})
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "ACCEPTED", [event["event_type"] for event in events]
    path = Path(state_root, "workspace", packet["packet_id"],
                f"attempt-{packet['packet_id']}-1.integration.json")
    assert not path.exists()
    run_once(
        state_root, COORD_ID, "o4-context-supplied", _context(), "2026-08-10T01:13:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": packet["starting_revision"],
        }},
    )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["decision"] == "CLEAN_CANDIDATE"
    assert artifact["integration_base"] == packet["starting_revision"]


def test_accepted_packet_uses_explicit_operator_base_not_starting_revision(tmp_path: Path) -> None:
    """Fails if recovery publication silently replaces the supplied operator base."""
    state_root, repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-integration-base")
    (repo / "allowed").mkdir()
    (repo / "allowed" / "b.py").write_text("integration\n", encoding="utf-8")
    _git(repo, "add", "allowed/b.py")
    _git(repo, "commit", "-m", "integration base")
    integration_base = _git(repo, "rev-parse", "HEAD")
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(
        argv=(str(worker),), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                                 "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt")},
    )
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    run_once(
        state_root, COORD_ID, "o4-base-review", _context(), "2026-08-10T01:12:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": integration_base, "integration_target_path": str(repo),
        }},
    )
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "ACCEPTED", [event["event_type"] for event in events]
    path = Path(state_root, "workspace", packet["packet_id"],
                f"attempt-{packet['packet_id']}-1.integration.json")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["integration_base"] == integration_base
    assert artifact["integration_base"] != packet["starting_revision"]
    assert artifact["decision"] == "CLEAN_CANDIDATE"
    assert artifact["verification_evidence_ids"] == ["ev-1"]
    assert artifact["worktree_identity"]["worktree_path"] == packet["worktree"]["path"]
    assert artifact["worktree_identity"]["branch"] == "refs/heads/" + packet["worktree"]["branch"]
    assert artifact["integration_target_path"] == os.path.realpath(str(repo))
    assert artifact["integration_target_status"] == "CLEAN"
    before_recovery = path.read_bytes()
    run_once(state_root, COORD_ID, "o4-base-recovery", _context(), "2026-08-10T01:13:00Z",
             integration_context_by_packet={})
    assert path.read_bytes() == before_recovery


@pytest.mark.parametrize("target", ["", 17])
def test_accepted_packet_with_malformed_target_context_stays_human_required(
        tmp_path: Path, target) -> None:
    """Fails if a bad optional target aborts maintenance or becomes a clean candidate."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-bad-target")
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(
        argv=(str(worker),), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                                 "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt")},
    )
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    run_once(
        state_root, COORD_ID, "o4-bad-target-review", _context(), "2026-08-10T01:12:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": packet["starting_revision"], "integration_target_path": target,
        }},
    )
    artifact = json.loads(Path(state_root, "workspace", packet["packet_id"],
                               f"attempt-{packet['packet_id']}-1.integration.json").read_text())
    assert artifact["decision"] == "HUMAN_REQUIRED"
    assert artifact["integration_target_path"] is None
    assert artifact["integration_target_status"] == "UNVERIFIABLE"


def test_accepted_packet_rejects_rehashed_postflight_that_disagrees_with_journal(tmp_path: Path) -> None:
    """Fails if postflight facts can be replaced after their durable binding."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-integration-ineligible")
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(
        argv=(str(worker),), env={"SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                                 "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt")},
    )
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    postflight_path = Path(state_root, "workspace", packet["packet_id"],
                           f"attempt-{packet['packet_id']}-1.postflight.json")
    postflight = json.loads(postflight_path.read_text(encoding="utf-8"))
    postflight["acceptance_allowed"] = False
    postflight["content_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"content_sha256", "artifact_sha256"})
    )
    postflight["artifact_sha256"] = compute_sha256(canonical_bytes(postflight, omit={"artifact_sha256"}))
    postflight_path.write_bytes(canonical_bytes(postflight))
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError
    with pytest.raises(WorkspaceEvidenceError, match="postflight journal binding"):
        run_once(
            state_root, COORD_ID, "o4-ineligible-review", _context(), "2026-08-10T01:12:00Z",
            integration_context_by_packet={packet["packet_id"]: {
                "integration_base": packet["starting_revision"],
            }},
        )
    assert not Path(state_root, "workspace", packet["packet_id"],
                    f"attempt-{packet['packet_id']}-1.integration.json").exists()


@pytest.mark.parametrize("shape", ["completed", "failed", "malformed", "interrupted", "timed_out"])
def test_postflight_is_durable_before_each_worker_outcome_can_advance(
        tmp_path: Path, monkeypatch, shape: str) -> None:
    """Every terminal invocation shape crosses the durable postflight gate first."""
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.invoke import InvocationOutcome

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-postflight-gate")
    result = _worker_result(packet, f"session-{shape}", attempt=1) if shape == "completed" else None
    errors = {"malformed": ("INVALID_JSON",), "interrupted": ("INTERRUPTED",),
              "timed_out": ("TIMED_OUT",)}.get(shape, ())
    invocation = InvocationOutcome(
        result=result, error_codes=errors, exit_code=1 if shape == "failed" else None, timed_out=shape == "timed_out",
        output_exceeded=False, interrupted=shape == "interrupted", process_group_dead=True, pid=None,
        stdout_path="", stderr_path="", result_path="", sidecar_path="", environment_keys=(),
    )
    monkeypatch.setattr(coordinator, "invoke_worker", lambda *_args, **_kwargs: invocation)

    def assert_postflight(*_args, **_kwargs):
        events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
        assert torn is None
        postflight = next(event for event in events if event["event_type"] == "WORKSPACE_POSTFLIGHT_RECORDED")
        artifact = postflight["payload"]["artifacts"][0]
        assert artifact["kind"] == "workspace_postflight"
        assert Path(state_root, artifact["path"]).exists()
        raise RuntimeError(f"postflight recorded for {shape}")

    monkeypatch.setattr(coordinator, "persist_invocation_outcome", assert_postflight)
    with pytest.raises(RuntimeError, match=f"postflight recorded for {shape}"):
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
                 worker_adapters={packet["packet_id"]: object()})


def test_baseline_publication_failure_never_invokes_worker(tmp_path: Path, monkeypatch) -> None:
    import harness_coordinator.v1.coordinator as coordinator

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-publication-failure")
    monkeypatch.setattr(
        coordinator, "ensure_attempt_baseline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("baseline publication failed")),
    )
    monkeypatch.setattr(
        coordinator, "invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not run")),
    )
    with pytest.raises(RuntimeError, match="baseline publication failed"):
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW, worker_adapters={packet["packet_id"]: object()})


def test_unverifiable_worktree_fails_closed_before_worker_invocation(tmp_path: Path, monkeypatch) -> None:
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError

    state_root = os.path.realpath(tmp_path / "non-git-state")
    worktree = os.path.realpath(tmp_path / "non-git-worktree")
    os.makedirs(os.path.join(state_root, "locks"))
    os.makedirs(worktree)
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    packet = _packet("o4-non-git", worktree=worktree)
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, [packet])
    monkeypatch.setattr(
        coordinator, "invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not run")),
    )
    with pytest.raises(WorkspaceEvidenceError) as caught:
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
                 worker_adapters={packet["packet_id"]: object()})
    assert caught.value.code == "WORKTREE_IDENTITY_REPOSITORY"


def test_crash_after_baseline_artifact_before_journal_reuses_same_attempt(tmp_path: Path, monkeypatch) -> None:
    """A published-but-unjournaled baseline resumes before the same invocation."""
    import harness_coordinator.v1.coordinator as coordinator

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-crash")
    real_append = coordinator.append_journal

    def crash_baseline_append(*args, **kwargs):
        event = args[1]
        if event["event_type"] == "WORKSPACE_BASELINE_RECORDED":
            raise RuntimeError("after baseline artifact")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(coordinator, "append_journal", crash_baseline_append)
    monkeypatch.setattr(
        coordinator, "invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not run before journal")),
    )
    with pytest.raises(RuntimeError, match="after baseline artifact"):
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW, worker_adapters={packet["packet_id"]: object()})
    baseline_dir = Path(state_root, "workspace", packet["packet_id"])
    assert [path.name for path in baseline_dir.iterdir()] == [f"attempt-{packet['packet_id']}-1.baseline.json"]

    monkeypatch.setattr(coordinator, "append_journal", real_append)
    resumed = {"intent_id": None}

    def assert_same_attempt(*args, **_kwargs):
        resumed["intent_id"] = args[3]
        raise RuntimeError("same attempt invoked")

    monkeypatch.setattr(
        coordinator, "invoke_worker",
        assert_same_attempt,
    )
    with pytest.raises(RuntimeError, match="same attempt invoked"):
        run_once(state_root, COORD_ID, "resumed-run", _context(), "2026-08-10T01:12:00Z",
                 worker_adapters={packet["packet_id"]: object()})
    assert resumed["intent_id"] == f"attempt-{packet['packet_id']}-1"
    assert [path.name for path in baseline_dir.iterdir()] == [f"attempt-{packet['packet_id']}-1.baseline.json"]
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    assert len([event for event in events if event["event_type"] == "WORKSPACE_BASELINE_RECORDED"]) == 1


def test_reused_baseline_rejects_packet_worktree_drift(tmp_path: Path) -> None:
    from harness_coordinator.v1.recovery import IntegrityError
    from harness_coordinator.v1.workspace_evidence import ensure_attempt_baseline

    state_root, repo, worktree, packet = _state_with_registered_worktree(tmp_path, "o4-worktree-drift")
    with open_state_root(state_root) as handle:
        ensure_attempt_baseline(handle, packet, "attempt-o4-worktree-drift-1", str(repo), None, [])
        (worktree / "tracked.txt").write_text("drift\n", encoding="utf-8")
        with pytest.raises(IntegrityError, match="baseline"):
            ensure_attempt_baseline(handle, packet, "attempt-o4-worktree-drift-1", str(repo), None, [])


def test_reused_baseline_rejects_extra_top_level_field(tmp_path: Path) -> None:
    from harness_coordinator.v1.recovery import IntegrityError
    from harness_coordinator.v1.workspace_evidence import ensure_attempt_baseline

    state_root, repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-extra-field")
    intent = "attempt-o4-extra-field-1"
    with open_state_root(state_root) as handle:
        binding = ensure_attempt_baseline(handle, packet, intent, str(repo), None, [])
    path = Path(state_root, binding["artifact_path"])
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["unexpected"] = "tampered"
    artifact["content_sha256"] = compute_sha256(
        canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"})
    )
    artifact["artifact_sha256"] = compute_sha256(canonical_bytes(artifact, omit={"artifact_sha256"}))
    path.write_bytes(canonical_bytes(artifact))
    with open_state_root(state_root) as handle:
        with pytest.raises(IntegrityError, match="field set"):
            ensure_attempt_baseline(handle, packet, intent, str(repo), None, [])


def test_reused_baseline_rejects_protected_worktree_drift(tmp_path: Path) -> None:
    from harness_coordinator.v1.recovery import IntegrityError
    from harness_coordinator.v1.workspace_evidence import ensure_attempt_baseline

    state_root, repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-protected-drift")
    protected = tmp_path / "protected"
    _git(repo, "branch", "codex/o4-protected")
    _git(repo, "worktree", "add", str(protected), "codex/o4-protected")
    with open_state_root(state_root) as handle:
        ensure_attempt_baseline(handle, packet, "attempt-o4-protected-drift-1", str(repo), str(protected), [])
        (protected / "tracked.txt").write_text("protected drift\n", encoding="utf-8")
        with pytest.raises(IntegrityError, match="baseline"):
            ensure_attempt_baseline(handle, packet, "attempt-o4-protected-drift-1", str(repo), str(protected), [])


def test_authenticated_receipt_recovers_dirty_allowed_worktree_without_reinvocation(
        tmp_path: Path, monkeypatch) -> None:
    """Post-worker receipt recovery must not compare dirty output to the clean baseline."""
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.coordinator import attempt_session_id

    state_root, _repo, worktree, packet = _state_with_registered_worktree(tmp_path, "o4-dirty-receipt")
    worker = tmp_path / "dirty-worker.py"
    marker = tmp_path / "dirty-worker-marker.txt"
    worker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "os.makedirs('scripts', exist_ok=True)\n"
        "open('scripts/o4-dirty-receipt.py', 'w').write('changed\\n')\n"
        "open(os.environ['SYNTHETIC_MARKER_PATH'], 'a').write('invoked\\n')\n"
        "with os.fdopen(int(os.environ['HARNESS_RESULT_FD']), 'w') as output:\n"
        "    json.dump(json.loads(os.environ['SYNTHETIC_RESULT']), output, sort_keys=True, separators=(',', ':'))\n",
        encoding="utf-8",
    )
    worker.chmod(0o755)
    session = attempt_session_id("dirty-receipt-run-1", packet["packet_id"], 1)
    result = _worker_result(packet, session, attempt=1)
    result["changed_files"] = [{
        "path": "scripts/o4-dirty-receipt.py", "status": "added",
        "before_sha256": None, "after_sha256": compute_sha256(b"changed\n"),
    }]
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    adapter = WorkerAdapter(
        argv=(str(worker),),
        env={"SYNTHETIC_MARKER_PATH": str(marker), "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":"))},
    )
    real_persist = coordinator.persist_invocation_outcome
    monkeypatch.setattr(
        coordinator, "persist_invocation_outcome",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("after receipt")),
    )
    with pytest.raises(RuntimeError, match="after receipt"):
        run_once(state_root, COORD_ID, "dirty-receipt-run-1", _context(), T_NOW,
                 worker_adapters={packet["packet_id"]: adapter})
    assert (worktree / "scripts/o4-dirty-receipt.py").exists()
    monkeypatch.setattr(coordinator, "persist_invocation_outcome", real_persist)

    recovered = run_once(
        state_root, COORD_ID, "dirty-receipt-run-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={packet["packet_id"]: adapter})
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert recovered["status"] == "no_eligible_work"
    assert folded[packet["packet_id"]]["state"] == "REVIEW"
    assert marker.read_text(encoding="utf-8").splitlines() == ["invoked"]
    outcome = json.loads(Path(state_root, "results", packet["packet_id"], "1", "attempt_outcome.json").read_text())
    binding = outcome["workspace_postflight"]
    assert binding["path"] == f"workspace/{packet['packet_id']}/attempt-{packet['packet_id']}-1.postflight.json"
    assert binding["artifact_sha256"] == compute_sha256(
        canonical_bytes(json.loads(Path(state_root, binding["path"]).read_text()), omit={"artifact_sha256"})
    )
    from harness_contracts.v1.classification import validate_attempt_outcome
    assert validate_attempt_outcome(outcome)["valid"]
    forged = dict(outcome)
    forged["workspace_postflight"] = dict(binding, path="workspace/other/wrong.postflight.json")
    forged["outcome_sha256"] = compute_sha256(canonical_bytes(forged, omit={"outcome_sha256"}))
    assert any(item["code"] == "EVIDENCE_HASH_MISMATCH"
               for item in validate_attempt_outcome(forged)["errors"])


def test_path_independent_postflight_hard_stop_is_human_required() -> None:
    """Capture failure cannot lose its stop condition when a packet owns no paths."""
    from harness_contracts.v1.classification import classify_attempt

    classification = classify_attempt({
        "authority": {"guard_denials": [], "undeclared_changed_paths": [],
                      "governed_path_touches": [], "hard_stop_matches": [],
                      "hard_stop_reasons": ["workspace_postflight_capture_failed"]},
        "result_validation": {"valid": False}, "outcome": "FAILED",
        "raw_result": {"byte_length": 0, "path": None},
        "invocation": {"timed_out": True, "signal": None, "exit_code": None},
    }, {}, None, None)
    assert classification["cause"] == "authority_hard_stop"


def test_persisted_capture_failure_controls_empty_allowlist_resolution(tmp_path: Path) -> None:
    """Persistence ignores a caller's forged acceptance and resolves the stored hard stop."""
    from harness_contracts.v1.classification import classify_attempt
    from harness_coordinator.v1.invoke import InvocationOutcome, persist_invocation_outcome
    from harness_coordinator.v1.workspace_evidence import (
        build_postflight_failure, ensure_attempt_baseline, load_attempt_baseline,
        publish_workspace_artifact,
    )

    state_root, repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-empty-capture")
    intent_id = "attempt-o4-empty-capture-1"
    packet_empty = dict(packet)
    packet_empty["writable_paths"] = []
    packet_empty["attempt"] = 1
    with open_state_root(state_root) as handle:
        ensure_attempt_baseline(handle, packet, intent_id, str(repo), None, [])
        baseline = load_attempt_baseline(handle, packet, intent_id)
        failure = build_postflight_failure(packet_empty, intent_id, baseline)
        binding = publish_workspace_artifact(
            handle, ("workspace", packet["packet_id"], f"{intent_id}.postflight.json"), failure)
        handle.publish(("invocations", intent_id, "stdout.bin"), b"")
        handle.publish(("invocations", intent_id, "stderr.bin"), b"")
        # These fields are deliberately caller-controlled noise.  The persisted
        # canonical artifact remains fail-closed and is the only authority.
        forged_caller_artifact = {
            "content_sha256": binding["content_sha256"],
            "artifact_sha256": binding["artifact_sha256"],
            "acceptance_allowed": True,
            "protected_findings": [],
        }
        outcome = persist_invocation_outcome(
            handle, packet_empty, intent_id,
            InvocationOutcome(
                result=None, error_codes=("TIMED_OUT",), exit_code=None, timed_out=True,
                output_exceeded=False, interrupted=False, process_group_dead=True, pid=None,
                stdout_path="", stderr_path="", result_path="", sidecar_path="", environment_keys=(),
            ),
            WorkerAdapter(argv=("/bin/true",), env={}), COORD_ID, RUN_ID, T_NOW,
            forged_caller_artifact,
        )
    assert outcome["workspace_postflight"] == {
        "packet_id": packet["packet_id"], "intent_id": intent_id,
        "path": f"workspace/{packet['packet_id']}/{intent_id}.postflight.json",
        "artifact_sha256": binding["artifact_sha256"], "content_sha256": binding["content_sha256"],
    }
    assert outcome["authority"]["hard_stop_reasons"] == ["workspace_postflight_capture_failed"]
    assert classify_attempt(outcome, {}, None, None)["cause"] == "authority_hard_stop"


@pytest.mark.parametrize("shape", ["two_baselines", "nonbaseline_content_hash"])
def test_workspace_baseline_journal_contract_rejects_wrong_artifact_shapes(shape: str) -> None:
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.recovery import _make_event

    artifact = {
        "kind": "workspace_baseline", "artifact_id": "workspace_baseline",
        "path": "workspace/o4-parity/attempt-o4-parity-1.baseline.json",
        "sha256": "a" * 64, "content_sha256": "b" * 64, "byte_length": 1,
    }
    event = _make_event(
        1, "WORKSPACE_BASELINE_RECORDED", "coord-o4", "run-o4", "state-o4", None,
        "2026-08-11T00:00:00Z", packet_id="o4-parity", intent_id="attempt-o4-parity-1",
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [artifact], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    if shape == "two_baselines":
        event["payload"]["artifacts"].append(dict(artifact, artifact_id="workspace_baseline_2"))
    else:
        event["event_type"] = "RUN_STARTED"
        event["packet_id"] = None
        event["intent_id"] = None
        event["payload"]["run"] = {
            "coordinator": {"coordinator_id": "coord-o4", "boot_id": "boot", "hostname": "host", "pid": 1},
            "trust_roots": {}, "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1,
                "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1,
                "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
            "end_reason": None, "end_detail": None, "disabled_lanes": [],
        }
        event["payload"]["artifacts"] = [dict(artifact, kind="stdout")]
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    schema = json.loads((Path(__file__).parents[2] / "schemas/harness/v1/journal-event.schema.json").read_text())
    assert not validate_journal_event(event)["valid"]
    assert len(schema["allOf"]) == 3
    assert schema["allOf"][0]["then"]["properties"]["payload"]["properties"]["artifacts"]["items"]["properties"]["kind"] == {"const": "workspace_baseline"}


def test_workspace_postflight_journal_contract_requires_one_hashed_artifact() -> None:
    """The review gate cannot advance without a durable, self-identifying postflight."""
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.recovery import _make_event

    artifact = {
        "kind": "workspace_postflight", "artifact_id": "workspace_postflight",
        "path": "workspace/o4-postflight/attempt-o4-postflight-1.postflight.json",
        "sha256": "a" * 64, "content_sha256": "b" * 64, "byte_length": 1,
    }
    event = _make_event(
        1, "WORKSPACE_POSTFLIGHT_RECORDED", "coord-o4", "run-o4", "state-o4", None,
        "2026-08-11T00:00:00Z", packet_id="o4-postflight", intent_id="attempt-o4-postflight-1",
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [artifact], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    assert validate_journal_event(event)["valid"]
    event["payload"]["artifacts"].append(dict(artifact, artifact_id="duplicate"))
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert not validate_journal_event(event)["valid"]
