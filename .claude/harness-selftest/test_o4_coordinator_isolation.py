"""O4 baseline gate tests with disposable Git worktrees only."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.coordinator import claim_and_start_attempt, run_once
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


def _state_with_registered_worktree(tmp_path: Path, packet_id: str,
                                    repository_root: str = None,
                                    include_repository_root: bool = True):
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
    if include_repository_root:
        packet["repository_root"] = repository_root or os.path.realpath(repo)
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
        started = next(event for event in events if event["event_type"] == "ATTEMPT_STARTED")
        assert event["packet_id"] == packet["packet_id"]
        assert event["seq"] < started["seq"]
        assert event["payload"]["artifacts"][0]["path"] == f"workspace/{packet['packet_id']}/attempt-{packet['packet_id']}-1.baseline.json"
        raise RuntimeError("stop after gate assertion")

    monkeypatch.setattr(coordinator, "invoke_worker", assert_gate)
    with pytest.raises(RuntimeError, match="stop after gate assertion"):
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW, worker_adapters={packet["packet_id"]: object()})
    assert invoked["value"]


def test_coordinator_rejects_foreign_operator_repository_before_worker(tmp_path: Path,
                                                                        monkeypatch) -> None:
    """The root bound into a packet must be operator-provided, not worktree-derived."""
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError

    foreign = tmp_path / "foreign-repository"
    foreign.mkdir()
    _git(foreign, "init")
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(
        tmp_path, "o4-foreign-root", repository_root=os.path.realpath(foreign))
    monkeypatch.setattr(
        "harness_coordinator.v1.coordinator.invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not run")),
    )

    with pytest.raises(WorkspaceEvidenceError) as caught:
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
                 worker_adapters={packet["packet_id"]: object()})

    assert caught.value.code == "WORKTREE_IDENTITY_COMMON_DIR"
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    assert not any(event["event_type"] == "ATTEMPT_STARTED" for event in events)


def test_write_packet_waits_for_adapter_before_foreign_root_preflight_refusal(
        tmp_path: Path, monkeypatch) -> None:
    """An O4 write packet remains READY until its adapter can execute preflight."""
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError

    foreign = tmp_path / "foreign-repository"
    foreign.mkdir()
    _git(foreign, "init")
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(
        tmp_path, "o4-await-adapter", repository_root=os.path.realpath(foreign))
    invoked = {"value": False}
    monkeypatch.setattr(
        "harness_coordinator.v1.coordinator.invoke_worker",
        lambda *_args, **_kwargs: invoked.update(value=True),
    )

    waiting = run_once(
        state_root, COORD_ID, "o4-await-adapter-1", _context(), T_NOW,
        worker_adapters={})
    assert waiting["status"] == "awaiting_worker_adapter"
    assert waiting["packet_id"] == packet["packet_id"]
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "READY"
    assert folded[packet["packet_id"]]["open_attempt"] is None
    assert folded[packet["packet_id"]]["attempts_started"] == 0
    assert not any(event["event_type"] in {
        "ATTEMPT_STARTED", "WORKSPACE_BASELINE_RECORDED",
    } for event in events)

    with pytest.raises(WorkspaceEvidenceError) as caught:
        run_once(
            state_root, COORD_ID, "o4-await-adapter-2", _context(),
            "2026-08-10T01:12:00Z", worker_adapters={packet["packet_id"]: object()})

    assert caught.value.code == "WORKTREE_IDENTITY_COMMON_DIR"
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "READY"
    assert folded[packet["packet_id"]]["open_attempt"] is None
    assert folded[packet["packet_id"]]["attempts_started"] == 0
    assert not any(event["event_type"] in {
        "ATTEMPT_STARTED", "WORKSPACE_BASELINE_RECORDED",
    } for event in events)
    assert invoked["value"] is False


def test_legacy_write_packet_waits_for_adapter_before_missing_root_refusal(
        tmp_path: Path, monkeypatch) -> None:
    """Rootless legacy compatibility never permits a new write attempt."""
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(
        tmp_path, "o4-legacy-await-adapter", include_repository_root=False)
    monkeypatch.setattr(
        "harness_coordinator.v1.coordinator.invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("worker must not run")),
    )

    waiting = run_once(
        state_root, COORD_ID, "o4-legacy-await-1", _context(), T_NOW,
        worker_adapters={})
    assert waiting["status"] == "awaiting_worker_adapter"
    assert waiting["packet_id"] == packet["packet_id"]

    with pytest.raises(WorkspaceEvidenceError) as caught:
        run_once(
            state_root, COORD_ID, "o4-legacy-await-2", _context(),
            "2026-08-10T01:12:00Z",
            worker_adapters={packet["packet_id"]: object()})
    assert caught.value.code == "WORKTREE_IDENTITY_REPOSITORY"

    events, torn = read_journal(
        Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "READY"
    assert folded[packet["packet_id"]]["open_attempt"] is None
    assert folded[packet["packet_id"]]["attempts_started"] == 0
    assert not any(event["event_type"] in {
        "ATTEMPT_STARTED", "WORKSPACE_BASELINE_RECORDED",
    } for event in events)


def test_preflight_refusal_keeps_packet_ready_without_durable_running_attempt(
        tmp_path: Path, monkeypatch) -> None:
    """A preflight refusal is a stable READY state, never a stranded RUNNING attempt."""
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.workspace_evidence import WorkspaceEvidenceError

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-preflight-ready")
    monkeypatch.setattr(
        coordinator, "ensure_attempt_baseline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            WorkspaceEvidenceError("WORKTREE_IDENTITY_COMMON_DIR", "foreign root")),
    )
    monkeypatch.setattr(
        coordinator, "invoke_worker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("worker must not run")),
    )

    with pytest.raises(WorkspaceEvidenceError) as caught:
        run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
                 worker_adapters={packet["packet_id"]: object()})

    assert caught.value.code == "WORKTREE_IDENTITY_COMMON_DIR"
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "READY"
    assert folded[packet["packet_id"]]["open_attempt"] is None
    assert folded[packet["packet_id"]]["attempts_started"] == 0
    assert not any(event["event_type"] == "ATTEMPT_STARTED" for event in events)


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
    from harness_coordinator.v1.recovery import IntegrityError
    with pytest.raises(IntegrityError, match="workspace evidence artifact"):
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
    assert len(schema["allOf"]) == 4
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


@pytest.mark.parametrize("event_type, kind", [
    ("WORKSPACE_BASELINE_RECORDED", "workspace_baseline"),
    ("WORKSPACE_POSTFLIGHT_RECORDED", "workspace_postflight"),
    ("INTEGRATION_MANIFEST_RECORDED", "workspace_integration"),
])
def test_every_workspace_event_kind_has_runtime_and_json_schema_parity(
        event_type: str, kind: str) -> None:
    """Each O4 journal event accepts exactly the matching workspace artifact kind."""
    from harness_contracts.v1.journal import ARTIFACT_KINDS, validate_journal_event
    from harness_coordinator.v1.recovery import _make_event

    packet_id = "o4-schema-" + kind.rsplit("_", 1)[-1]
    intent_id = "attempt-" + packet_id + "-1"
    artifact = {
        "kind": kind, "artifact_id": kind,
        "path": "workspace/%s/%s.evidence.json" % (packet_id, intent_id),
        "sha256": "a" * 64, "content_sha256": "b" * 64, "byte_length": 1,
    }
    event = _make_event(
        1, event_type, "coord-o4", "run-o4", "state-o4", None,
        "2026-08-11T00:00:00Z", packet_id=packet_id, intent_id=intent_id,
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [artifact],
                 "classification": None, "transition_detail": None, "recovery": None,
                 "run": None, "report": None},
    )
    assert validate_journal_event(event)["valid"]

    schema = json.loads(
        (Path(__file__).parents[2] / "schemas/harness/v1/journal-event.schema.json").read_text())
    schema_kinds = set(schema["properties"]["payload"]["properties"]["artifacts"]
                       ["items"]["properties"]["kind"]["enum"])
    assert schema_kinds == ARTIFACT_KINDS
    conditional = next(
        rule for rule in schema["allOf"]
        if rule["if"]["properties"]["event_type"].get("const") == event_type
    )
    assert (conditional["then"]["properties"]["payload"]["properties"]["artifacts"]
            ["items"]["properties"]["kind"]) == {"const": kind}


def test_staged_packet_change_is_retained_and_human_required(tmp_path: Path) -> None:
    """Any Git-index mutation is a coordinator-enforced hard stop, even in allowlist scope."""
    state_root, _repo, worktree, packet = _state_with_registered_worktree(tmp_path, "o4-staged-index")
    marker = tmp_path / "staged-marker.txt"
    worker = tmp_path / "stage-worker.py"
    worker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, subprocess\n"
        "os.makedirs('scripts', exist_ok=True)\n"
        "open('scripts/o4-staged-index.py', 'w').write('staged\\n')\n"
        "subprocess.run(['git', 'add', 'scripts/o4-staged-index.py'], check=True)\n"
        "open(os.environ['SYNTHETIC_MARKER_PATH'], 'w').write('invoked\\n')\n"
        "with os.fdopen(int(os.environ['HARNESS_RESULT_FD']), 'w') as output:\n"
        "    json.dump(json.loads(os.environ['SYNTHETIC_RESULT']), output, sort_keys=True, separators=(',', ':'))\n",
        encoding="utf-8",
    )
    worker.chmod(0o755)
    session = "session-%s-%s-1" % (RUN_ID, packet["packet_id"])
    result = _worker_result(packet, session, attempt=1)
    result["changed_files"] = [{
        "path": "scripts/o4-staged-index.py", "status": "added",
        "before_sha256": None, "after_sha256": compute_sha256(b"staged\n"),
    }]
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    adapter = WorkerAdapter(
        argv=(str(worker),),
        env={"SYNTHETIC_MARKER_PATH": str(marker),
             "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":"))},
    )

    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})

    postflight = json.loads(Path(
        state_root, "workspace", packet["packet_id"],
        "attempt-%s-1.postflight.json" % packet["packet_id"],
    ).read_text(encoding="utf-8"))
    assert postflight["acceptance_allowed"] is False
    assert postflight["scope_findings"] == [{
        "code": "ALLOWLIST_VIOLATION_INDEX", "path": "scripts/o4-staged-index.py",
    }]
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "HUMAN_REQUIRED"
    assert marker.read_text(encoding="utf-8") == "invoked\n"
    assert (worktree / "scripts/o4-staged-index.py").read_text(encoding="utf-8") == "staged\n"


def test_integration_manifest_journal_contract_requires_one_hashed_artifact() -> None:
    """The integration candidate is durable evidence, not an unjournaled file."""
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.recovery import _make_event

    artifact = {
        "kind": "workspace_integration", "artifact_id": "workspace_integration",
        "path": "workspace/o4-integration/attempt-o4-integration-1.integration.json",
        "sha256": "a" * 64, "content_sha256": "b" * 64, "byte_length": 1,
    }
    event = _make_event(
        1, "INTEGRATION_MANIFEST_RECORDED", "coord-o4", "run-o4", "state-o4", None,
        "2026-08-11T00:00:00Z", packet_id="o4-integration", intent_id="attempt-o4-integration-1",
        from_state=None, to_state=None, cause="none",
        payload={"packet": None, "attempt": None, "artifacts": [artifact], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    assert validate_journal_event(event)["valid"]
    event["payload"]["artifacts"].append(dict(artifact, artifact_id="duplicate"))
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert not validate_journal_event(event)["valid"]


def test_accepted_integration_is_journaled_once_and_tampered_binding_fails_fold(
        tmp_path: Path) -> None:
    """A changed integration hash must never be treated as a completed O4 stage."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-fold-integration")
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
        state_root, COORD_ID, "o4-fold-integration-review", _context(), "2026-08-10T01:12:00Z",
        integration_context_by_packet={packet["packet_id"]: {"integration_base": packet["starting_revision"]}},
    )
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    integration = [event for event in events if event["event_type"] == "INTEGRATION_MANIFEST_RECORDED"]
    assert len(integration) == 1
    assert integration[0]["payload"]["artifacts"][0]["path"] == (
        f"workspace/{packet['packet_id']}/attempt-{packet['packet_id']}-1.integration.json")
    forged = json.loads(json.dumps(integration[0]))
    forged["payload"]["artifacts"][0]["sha256"] = "f" * 64
    forged["event_sha256"] = compute_sha256(canonical_bytes(forged, omit={"event_sha256"}))
    from harness_coordinator.v1.recovery import IntegrityError
    with pytest.raises(IntegrityError, match="workspace evidence"):
        _fold_journal(state_root, events[:-1] + [forged])


def test_reconciliation_surfaces_missing_workspace_baseline(tmp_path: Path) -> None:
    """A malformed claimed O4 attempt cannot disappear without preflight evidence."""
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.reconcile import (
        _declares_workspace_evidence_v1,
        build_reconciliation_report,
    )

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-reconcile-baseline")
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW)
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded[packet["packet_id"]]["state"] == "READY"
    with open_state_root(state_root) as handle:
        claim_and_start_attempt(
            state_root, STATE_ROOT_ID, events, packet["packet_id"],
            folded[packet["packet_id"]], COORD_ID, RUN_ID,
            _context(), "2026-08-10T01:12:00Z", handle=handle)
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    run_started = next(event for event in events if event["event_type"] == "RUN_STARTED")
    assert run_started["payload"]["run"]["contract_versions"]["workspace_evidence"] == 1
    run_index = events.index(run_started)
    assert validate_journal_event(
        run_started, prev_event=events[run_index - 1], state_root_id=STATE_ROOT_ID)["valid"]
    assert _declares_workspace_evidence_v1(run_started)
    schema = json.loads(
        (Path(__file__).parents[2] / "schemas/harness/v1/journal-event.schema.json").read_text())
    contract_schema = schema["properties"]["payload"]["properties"]["run"]["properties"][
        "contract_versions"]
    assert contract_schema["properties"]["workspace_evidence"] == {
        "type": "integer", "enum": [1],
    }
    assert "workspace_evidence" not in contract_schema["required"]
    with open_state_root(state_root) as handle:
        report = build_reconciliation_report(
            state_root, STATE_ROOT_ID, COORD_ID, "o4-reconcile-read",
            "reconciliation-o4-reconcile-baseline", "2026-08-10T01:13:00Z", handle=handle,
        )
    assert any(item["code"] == "workspace_baseline_missing"
               for item in report["attention_required"])
    assert not report["reconciliation"]["all_invariants_passed"]


def test_reconciliation_does_not_infer_o4_from_legacy_packet_artifact(tmp_path: Path) -> None:
    """A packet file cannot silently upgrade an authenticated pre-O4 run contract."""
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.reconcile import build_reconciliation_report

    state_root, _repo, _worktree, packet = _state_with_registered_worktree(
        tmp_path, "o4-legacy-boundary")
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW)
    assert Path(state_root, "packets", f"{packet['packet_id']}.json").exists()
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    for event in events:
        if event["event_type"] == "RUN_STARTED":
            del event["payload"]["run"]["contract_versions"]["workspace_evidence"]
    previous_sha = "0" * 64
    for event in events:
        event["prev_event_sha256"] = previous_sha
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        previous_sha = event["event_sha256"]
    Path(state_root, "journal.ndjson").write_bytes(
        b"".join(canonical_bytes(event) + b"\n" for event in events))
    legacy_run = next(event for event in events if event["event_type"] == "RUN_STARTED")
    run_index = events.index(legacy_run)
    assert validate_journal_event(
        legacy_run, prev_event=events[run_index - 1], state_root_id=STATE_ROOT_ID)["valid"]

    with open_state_root(state_root) as handle:
        report = build_reconciliation_report(
            state_root, STATE_ROOT_ID, COORD_ID, "legacy-reconcile-read",
            "reconciliation-o4-legacy-boundary", "2026-08-10T01:13:00Z", handle=handle,
        )
    codes = {item["code"] for item in report["attention_required"]
             if item["packet_id"] == packet["packet_id"]}
    assert "workspace_baseline_missing" not in codes
    assert "workspace_postflight_missing" not in codes


@pytest.mark.parametrize("bad_value", [0, 2, "1", None, True])
def test_workspace_evidence_contract_version_rejects_non_v1_values(
        tmp_path: Path, bad_value) -> None:
    """The optional legacy discriminator is strict whenever an O4 run declares it."""
    from harness_contracts.v1.journal import validate_journal_event
    from harness_coordinator.v1.reconcile import _declares_workspace_evidence_v1

    state_root, _repo, _worktree, _packet = _state_with_registered_worktree(
        tmp_path, "o4-version-negative")
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW)
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    run_started = next(event for event in events if event["event_type"] == "RUN_STARTED")
    run_started["payload"]["run"]["contract_versions"]["workspace_evidence"] = bad_value
    run_started["event_sha256"] = compute_sha256(
        canonical_bytes(run_started, omit={"event_sha256"}))
    run_index = events.index(run_started)
    result = validate_journal_event(
        run_started, prev_event=events[run_index - 1], state_root_id=STATE_ROOT_ID)
    assert not result["valid"]
    assert not _declares_workspace_evidence_v1(run_started)
    assert any(error["path"].endswith("/contract_versions/workspace_evidence")
               for error in result["errors"])


@pytest.mark.parametrize("root", ["workspace", ["workspace"], 7])
def test_workspace_stage_artifact_rejects_non_object_json(root) -> None:
    """Valid JSON scalars and arrays fail deterministically before canonical hashing."""
    from harness_coordinator.v1.recovery import IntegrityError, validate_workspace_stage_artifact

    packet = {"packet_id": "o4-non-object", "packet_sha256": "a" * 64}
    with pytest.raises(IntegrityError) as caught:
        validate_workspace_stage_artifact(
            canonical_bytes(root), packet, "attempt-o4-non-object-1",
            "WORKSPACE_BASELINE_RECORDED", {},
        )
    assert caught.value.code == "WORKSPACE_EVIDENCE_MISMATCH"
    assert caught.value.packet_id == packet["packet_id"]
    assert caught.value.message == "workspace evidence artifact root is not an object"


@pytest.mark.parametrize("suffix", ["baseline", "postflight", "integration"])
def test_fold_rejects_each_rehashed_workspace_artifact_shape(tmp_path: Path, suffix: str) -> None:
    """Each O4 stage validates its own exact artifact schema, not shared fields alone."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, "o4-stage-" + suffix)
    result = _commission_result(packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(argv=(str(worker),), env={
        "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
        "SYNTHETIC_MARKER_PATH": str(tmp_path / "marker.txt"),
    })
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    run_once(state_root, COORD_ID, "o4-stage-review", _context(), "2026-08-10T01:12:00Z",
             integration_context_by_packet={packet["packet_id"]: {"integration_base": packet["starting_revision"]}})
    intent = f"attempt-{packet['packet_id']}-1"
    path = Path(state_root, "workspace", packet["packet_id"], f"{intent}.{suffix}.json")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["unexpected"] = True
    artifact["content_sha256"] = compute_sha256(canonical_bytes(
        artifact, omit={"content_sha256", "artifact_sha256"}))
    artifact["artifact_sha256"] = compute_sha256(canonical_bytes(artifact, omit={"artifact_sha256"}))
    path.write_bytes(canonical_bytes(artifact))
    events, _ = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    from harness_coordinator.v1.recovery import IntegrityError
    with pytest.raises(IntegrityError, match="workspace evidence"):
        _fold_journal(state_root, events)


@pytest.mark.parametrize("crash_point", [
    "before_baseline_artifact",
    "after_baseline_artifact_before_event",
    "after_worker_receipt_before_postflight",
    "after_postflight_artifact_before_event",
    "after_postflight_event_before_integration",
])
def test_five_point_workspace_crash_resume_matrix(
        tmp_path: Path, monkeypatch, crash_point: str) -> None:
    """Every O4 publication boundary resumes once without reinvoking a worker."""
    import harness_coordinator.v1.coordinator as coordinator

    packet_id = "o4-crash-%d" % ({
        "before_baseline_artifact": 1,
        "after_baseline_artifact_before_event": 2,
        "after_worker_receipt_before_postflight": 3,
        "after_postflight_artifact_before_event": 4,
        "after_postflight_event_before_integration": 5,
    }[crash_point])
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(
        tmp_path, packet_id)
    marker = tmp_path / "worker-markers.txt"
    result = _commission_result(
        packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(argv=(str(worker),), env={
        "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
        "SYNTHETIC_MARKER_PATH": str(marker),
    })
    real_baseline = coordinator.ensure_attempt_baseline
    real_postflight = coordinator._record_workspace_postflight
    real_integration = coordinator._record_workspace_integration
    real_append = coordinator.append_journal
    crashed = {"value": False}

    if crash_point == "before_baseline_artifact":
        def crash_before_baseline(*args, **kwargs):
            if not crashed["value"]:
                crashed["value"] = True
                raise RuntimeError(crash_point)
            return real_baseline(*args, **kwargs)
        monkeypatch.setattr(coordinator, "ensure_attempt_baseline", crash_before_baseline)
    elif crash_point == "after_baseline_artifact_before_event":
        def crash_baseline_event(*args, **kwargs):
            if args[1]["event_type"] == "WORKSPACE_BASELINE_RECORDED" and not crashed["value"]:
                crashed["value"] = True
                raise RuntimeError(crash_point)
            return real_append(*args, **kwargs)
        monkeypatch.setattr(coordinator, "append_journal", crash_baseline_event)
    elif crash_point == "after_worker_receipt_before_postflight":
        def crash_before_postflight(*args, **kwargs):
            if not crashed["value"]:
                crashed["value"] = True
                raise RuntimeError(crash_point)
            return real_postflight(*args, **kwargs)
        monkeypatch.setattr(coordinator, "_record_workspace_postflight", crash_before_postflight)
    elif crash_point == "after_postflight_artifact_before_event":
        def crash_postflight_event(*args, **kwargs):
            if args[1]["event_type"] == "WORKSPACE_POSTFLIGHT_RECORDED" and not crashed["value"]:
                crashed["value"] = True
                raise RuntimeError(crash_point)
            return real_append(*args, **kwargs)
        monkeypatch.setattr(coordinator, "append_journal", crash_postflight_event)

    if crash_point != "after_postflight_event_before_integration":
        with pytest.raises(RuntimeError, match=crash_point):
            run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
                     worker_adapters={packet["packet_id"]: adapter})
        if crash_point in {"before_baseline_artifact", "after_baseline_artifact_before_event"}:
            assert not marker.exists()
        else:
            assert marker.read_text(encoding="utf-8").splitlines() == [f"{packet_id}:1"]

        monkeypatch.setattr(coordinator, "ensure_attempt_baseline", real_baseline)
        monkeypatch.setattr(coordinator, "_record_workspace_postflight", real_postflight)
        monkeypatch.setattr(coordinator, "append_journal", real_append)
        resume_adapter = adapter
        if crash_point in {"before_baseline_artifact", "after_baseline_artifact_before_event"}:
            # No attempt had started, so the resumed run owns the first
            # session identity and needs a result bound to that identity.
            result = _commission_result(
                packet, f"session-o4-crash-resume-{packet['packet_id']}-1", attempt=1)
            resume_adapter = WorkerAdapter(argv=(str(worker),), env={
                "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
                "SYNTHETIC_MARKER_PATH": str(marker),
            })
        resumed = run_once(
            state_root, COORD_ID, "o4-crash-resume", _context(), "2026-08-10T01:12:00Z",
            worker_adapters={packet["packet_id"]: resume_adapter})
        if crash_point in {"before_baseline_artifact", "after_baseline_artifact_before_event"}:
            # O4 preflight now precedes the durable RUNNING transition, so a
            # crash at either baseline boundary leaves the packet READY and
            # the resumed coordinator performs its first invocation.
            assert resumed["status"] == "completed_attempt"
        else:
            assert resumed["status"] == "no_eligible_work"

    if crash_point == "after_postflight_event_before_integration":
        first = run_once(
            state_root, COORD_ID, RUN_ID, _context(), T_NOW,
            worker_adapters={packet["packet_id"]: adapter})
        assert first["status"] == "completed_attempt"
    assert marker.read_text(encoding="utf-8").splitlines() == [f"{packet_id}:1"]
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))

    if crash_point == "after_postflight_event_before_integration":
        def crash_before_integration(*args, **kwargs):
            if not crashed["value"]:
                crashed["value"] = True
                raise RuntimeError(crash_point)
            return real_integration(*args, **kwargs)
        monkeypatch.setattr(coordinator, "_record_workspace_integration", crash_before_integration)
        with pytest.raises(RuntimeError, match=crash_point):
            run_once(
                state_root, COORD_ID, "o4-integration-crash", _context(),
                "2026-08-10T01:13:00Z",
                integration_context_by_packet={packet["packet_id"]: {
                    "integration_base": packet["starting_revision"],
                }})
        monkeypatch.setattr(coordinator, "_record_workspace_integration", real_integration)

    run_once(
        state_root, COORD_ID, "o4-integration-resume", _context(),
        "2026-08-10T01:14:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": packet["starting_revision"],
        }})
    run_once(
        state_root, COORD_ID, "o4-integration-repeat", _context(),
        "2026-08-10T01:15:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": packet["starting_revision"],
        }})

    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    intent = f"attempt-{packet_id}-1"
    for event_type, suffix in (
        ("WORKSPACE_BASELINE_RECORDED", "baseline"),
        ("WORKSPACE_POSTFLIGHT_RECORDED", "postflight"),
        ("INTEGRATION_MANIFEST_RECORDED", "integration"),
    ):
        matching = [event for event in events if event["event_type"] == event_type
                    and event.get("packet_id") == packet_id]
        assert len(matching) == 1
        paths = list(Path(state_root, "workspace", packet_id).glob(f"{intent}.{suffix}.json"))
        assert [path.name for path in paths] == [f"{intent}.{suffix}.json"]


def _accepted_o4_state(tmp_path: Path, packet_id: str):
    """Commission one accepted packet with all three O4 artifacts."""
    state_root, _repo, _worktree, packet = _state_with_registered_worktree(tmp_path, packet_id)
    result = _commission_result(
        packet, f"session-{RUN_ID}-{packet['packet_id']}-1", attempt=1)
    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    adapter = WorkerAdapter(argv=(str(worker),), env={
        "SYNTHETIC_RESULT": json.dumps(result, separators=(",", ":")),
        "SYNTHETIC_MARKER_PATH": str(tmp_path / "tamper-marker.txt"),
    })
    run_once(state_root, COORD_ID, RUN_ID, _context(), T_NOW,
             worker_adapters={packet["packet_id"]: adapter})
    _deposit(state_root, packet["packet_id"], 1, _verdict(packet, result))
    run_once(
        state_root, COORD_ID, "o4-tamper-accept", _context(), "2026-08-10T01:12:00Z",
        integration_context_by_packet={packet["packet_id"]: {
            "integration_base": packet["starting_revision"],
        }})
    return state_root, packet


@pytest.mark.parametrize("stage", ["baseline", "postflight", "integration"])
@pytest.mark.parametrize("tamper", [
    "missing_file", "altered_bytes", "cross_packet", "wrong_intent",
    "wrong_content_hash", "wrong_artifact_hash", "contradictory_acceptance_allowed",
])
def test_reconciliation_attributes_every_workspace_artifact_tamper(
        tmp_path: Path, stage: str, tamper: str) -> None:
    """Every O4 artifact failure remains attributed to its enrolled packet."""
    from harness_coordinator.v1.reconcile import build_reconciliation_report

    packet_id = "o4-tamper-%s-%d" % (stage[0], {
        "missing_file": 1,
        "altered_bytes": 2,
        "cross_packet": 3,
        "wrong_intent": 4,
        "wrong_content_hash": 5,
        "wrong_artifact_hash": 6,
        "contradictory_acceptance_allowed": 7,
    }[tamper])
    state_root, packet = _accepted_o4_state(tmp_path, packet_id)
    intent = f"attempt-{packet_id}-1"
    path = Path(state_root, "workspace", packet_id, f"{intent}.{stage}.json")

    if tamper == "missing_file":
        path.unlink()
    elif tamper == "altered_bytes":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        if tamper == "cross_packet":
            artifact["packet_id"] = "different-packet"
        elif tamper == "wrong_intent":
            artifact["intent_id"] = "attempt-different-packet-9"
        elif tamper == "wrong_content_hash":
            artifact["content_sha256"] = "f" * 64
            path.write_bytes(canonical_bytes(artifact))
        elif tamper == "wrong_artifact_hash":
            artifact["artifact_sha256"] = "f" * 64
            path.write_bytes(canonical_bytes(artifact))
        elif tamper == "contradictory_acceptance_allowed":
            artifact["acceptance_allowed"] = not bool(artifact.get("acceptance_allowed", False))
        if tamper not in {"wrong_content_hash", "wrong_artifact_hash"}:
            artifact["content_sha256"] = compute_sha256(canonical_bytes(
                artifact, omit={"content_sha256", "artifact_sha256"}))
            artifact["artifact_sha256"] = compute_sha256(canonical_bytes(
                artifact, omit={"artifact_sha256"}))
            path.write_bytes(canonical_bytes(artifact))

    with open_state_root(state_root) as handle:
        report = build_reconciliation_report(
            state_root, STATE_ROOT_ID, COORD_ID, "o4-tamper-report",
            "reconciliation-" + packet_id, "2026-08-10T01:13:00Z", handle=handle)
    row = next(item for item in report["packets"] if item["packet_id"] == packet_id)
    assert not report["reconciliation"]["all_invariants_passed"]
    assert "workspace_evidence_mismatch" in row["attention_codes"]
    assert any(item["packet_id"] == packet_id and item["code"] == "workspace_evidence_mismatch"
               for item in report["attention_required"])


@pytest.mark.parametrize("tamper", [
    "cross_packet_event", "wrong_event_intent", "wrong_binding_path", "wrong_byte_length",
])
def test_workspace_fold_failures_preserve_partial_packet_inventory(
        tmp_path: Path, tamper: str) -> None:
    """Journal-binding failures cannot make an enrolled packet disappear."""
    from harness_coordinator.v1.recovery import IntegrityError

    packet_id = "o4-fold-partial"
    state_root, _packet_body = _accepted_o4_state(tmp_path, packet_id)
    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    forged = json.loads(json.dumps(events))
    event = next(item for item in forged
                 if item["event_type"] == "INTEGRATION_MANIFEST_RECORDED")
    if tamper == "cross_packet_event":
        event["packet_id"] = "different-packet"
    elif tamper == "wrong_event_intent":
        event["intent_id"] = "attempt-different-packet-1"
    elif tamper == "wrong_binding_path":
        event["payload"]["artifacts"][0]["path"] = (
            "workspace/different-packet/wrong.integration.json")
    else:
        event["payload"]["artifacts"][0]["byte_length"] += 1
    event["event_sha256"] = compute_sha256(canonical_bytes(
        event, omit={"event_sha256"}))
    with pytest.raises(IntegrityError) as caught:
        _fold_journal(state_root, forged)
    assert packet_id in caught.value.partial_packets


def test_disposable_two_packet_o4_commissioning_reconciles_exactly(tmp_path: Path) -> None:
    """Commission disjoint work while preserving and refusing, never cleaning, dirt."""
    from harness_coordinator.v1.integration_analysis import analyze_integration
    from harness_coordinator.v1.reconcile import build_reconciliation_report
    from harness_coordinator.v1.workspace_evidence import capture_snapshot

    repo = tmp_path / "protected-repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "O4 Commission")
    _git(repo, "config", "user.email", "o4-commission@example.test")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "base")
    starting_revision = _git(repo, "rev-parse", "HEAD")

    worktrees = {}
    for packet_id in ("o4-clean", "o4-refused"):
        branch = "codex/" + packet_id
        _git(repo, "branch", branch)
        worktree = tmp_path / (packet_id + "-worktree")
        _git(repo, "worktree", "add", str(worktree), branch)
        worktrees[packet_id] = (worktree, branch)

    _git(repo, "branch", "codex/o4-overlap")
    overlap_worktree = tmp_path / "overlap-worktree"
    _git(repo, "worktree", "add", str(overlap_worktree), "codex/o4-overlap")
    (overlap_worktree / "scripts").mkdir()
    (overlap_worktree / "scripts" / "o4-refused.py").write_text(
        "integration base\n", encoding="utf-8")
    _git(overlap_worktree, "add", "scripts/o4-refused.py")
    _git(overlap_worktree, "commit", "-m", "overlapping integration base")
    overlap_revision = _git(overlap_worktree, "rev-parse", "HEAD")

    # The protected checkout begins dirty and must remain byte-for-byte dirty.
    (repo / "tracked.txt").write_text("protected tracked dirt\n", encoding="utf-8")
    (repo / "protected-untracked.txt").write_text(
        "protected untracked dirt\n", encoding="utf-8")
    protected_before = capture_snapshot(str(repo))
    assert len(protected_before["entries"]) == 2

    packets = []
    for packet_id in ("o4-clean", "o4-refused"):
        worktree, branch = worktrees[packet_id]
        packet = _packet(packet_id, worktree=os.path.realpath(worktree))
        packet["starting_revision"] = starting_revision
        packet["worktree"]["branch"] = branch
        packet["repository_root"] = os.path.realpath(repo)
        packet["packet_sha256"] = compute_sha256(canonical_bytes(
            packet, omit={"packet_sha256"}))
        packets.append(packet)
    clean_packet, refused_packet = packets
    assert clean_packet["writable_paths"] == ["scripts/o4-clean.py"]
    assert refused_packet["writable_paths"] == ["scripts/o4-refused.py"]

    state_root = os.path.realpath(tmp_path / "state")
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root)
    _write_trust_roots(state_root)
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, packets)

    worker = Path(__file__).with_name("synthetic_p5_worker.py").resolve()
    clean_result = _commission_result(
        clean_packet, "session-o4-commission-1-o4-clean-1", attempt=1)
    clean_marker = tmp_path / "clean-marker.txt"
    clean_adapter = WorkerAdapter(argv=(str(worker),), env={
        "SYNTHETIC_RESULT": json.dumps(clean_result, separators=(",", ":")),
        "SYNTHETIC_MARKER_PATH": str(clean_marker),
    })
    first = run_once(
        state_root, COORD_ID, "o4-commission-1", _context(), T_NOW,
        worker_adapters={clean_packet["packet_id"]: clean_adapter},
        protected_worktree_path=str(repo))
    assert first["status"] == "completed_attempt"
    _deposit(state_root, clean_packet["packet_id"], 1,
             _verdict(clean_packet, clean_result))

    refused_result = _commission_result(
        refused_packet, "session-o4-commission-2-o4-refused-1", attempt=1)
    refused_worker = tmp_path / "refused-worker.py"
    refused_worker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "os.makedirs('scripts', exist_ok=True)\n"
        "open('scripts/o4-refused.py', 'w').write('synthetic o4-refused 1\\n')\n"
        "open('forbidden-untracked.txt', 'w').write('retain for inspection\\n')\n"
        "open(os.environ['SYNTHETIC_MARKER_PATH'], 'a').write('o4-refused:1\\n')\n"
        "with os.fdopen(int(os.environ['HARNESS_RESULT_FD']), 'w') as output:\n"
        "    json.dump(json.loads(os.environ['SYNTHETIC_RESULT']), output, sort_keys=True, separators=(',', ':'))\n",
        encoding="utf-8")
    refused_worker.chmod(0o755)
    refused_marker = tmp_path / "refused-marker.txt"
    refused_adapter = WorkerAdapter(argv=(str(refused_worker),), env={
        "SYNTHETIC_RESULT": json.dumps(refused_result, separators=(",", ":")),
        "SYNTHETIC_MARKER_PATH": str(refused_marker),
    })
    second = run_once(
        state_root, COORD_ID, "o4-commission-2", _context(), "2026-08-10T01:12:00Z",
        worker_adapters={refused_packet["packet_id"]: refused_adapter},
        protected_worktree_path=str(repo),
        integration_context_by_packet={clean_packet["packet_id"]: {
            "integration_base": starting_revision,
        }})
    assert second["status"] == "completed_attempt"

    assert capture_snapshot(str(repo)) == protected_before
    assert (worktrees["o4-clean"][0] / "scripts" / "o4-clean.py").read_text() == (
        "synthetic o4-clean 1\n")
    assert (worktrees["o4-refused"][0] / "scripts" / "o4-refused.py").read_text() == (
        "synthetic o4-refused 1\n")
    forbidden_path = worktrees["o4-refused"][0] / "forbidden-untracked.txt"
    assert forbidden_path.read_text(encoding="utf-8") == "retain for inspection\n"

    events, torn = read_journal(Path(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    assert folded["o4-clean"]["state"] == "ACCEPTED"
    assert folded["o4-refused"]["state"] == "HUMAN_REQUIRED"
    clean_integration = json.loads(Path(
        state_root, "workspace", "o4-clean", "attempt-o4-clean-1.integration.json"
    ).read_text(encoding="utf-8"))
    assert clean_integration["decision"] == "CLEAN_CANDIDATE"
    assert not Path(
        state_root, "workspace", "o4-refused", "attempt-o4-refused-1.integration.json"
    ).exists()

    refused_postflight = json.loads(Path(
        state_root, "workspace", "o4-refused", "attempt-o4-refused-1.postflight.json"
    ).read_text(encoding="utf-8"))
    assert not refused_postflight["acceptance_allowed"]
    assert any(item["path"] == "forbidden-untracked.txt"
               for item in refused_postflight["scope_findings"])
    overlap = analyze_integration(
        str(repo), starting_revision, overlap_revision,
        refused_postflight["derived_changes"])
    assert overlap["decision"] == "HUMAN_REQUIRED"
    assert overlap["reason_codes"] == ["INTEGRATION_CONFLICT_PATH_OVERLAP"]

    with open_state_root(state_root) as handle:
        report = build_reconciliation_report(
            state_root, STATE_ROOT_ID, COORD_ID, "o4-commission-report",
            "reconciliation-o4-commission", "2026-08-10T01:13:00Z", handle=handle)
    assert report["inventory_total"] == 2
    assert report["by_state"] == {
        "BLOCKED": 0, "READY": 0, "RUNNING": 0, "REVIEW": 0,
        "ACCEPTED": 1, "REVISE": 0, "QUARANTINED": 0, "HUMAN_REQUIRED": 1,
    }
    assert report["activity"] == {
        "attempts_started_total": 2,
        "infra_retries_total": 0,
        "revise_verdicts_total": 0,
        "revise_cycles_total": 0,
        "reassignments_total": 0,
        "results_recorded_total": 2,
        "verdicts_recorded_total": 1,
        "intents_abandoned_total": 0,
        "locks_reclaimed_total": 0,
    }
    assert report["reconciliation"] == {
        "sum_of_by_state": 2,
        "packets_array_length": 2,
        "distinct_packet_ids": 2,
        "equals_inventory_total": True,
        "all_invariants_passed": False,
    }
    refused_row = next(row for row in report["packets"]
                       if row["packet_id"] == "o4-refused")
    assert "allowlist_violation" in refused_row["attention_codes"]
