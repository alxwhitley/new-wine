"""Adversarial tests for the pinned P5A worker-claim lifecycle."""

import json
import os

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
import harness_coordinator.v1.coordinator as coordinator_module
import harness_coordinator.v1.locks as locks_module
import harness_coordinator.v1.recovery as recovery_module
from harness_coordinator.v1.coordinator import claim_packet
from harness_coordinator.v1.locks import (
    create_claim_at,
    list_worker_claim_ids,
    read_claim_at,
    reclaim_lock_at,
)
from harness_coordinator.v1.seals_runtime import StateRootMoved, open_state_root
from harness_coordinator.v1.store import JournalHeadMoved, read_journal


def _claim(packet_id="packet-1", run_id="run-1"):
    record = {
        "schema_version": 1, "packet_id": packet_id,
        "intent_id": f"attempt-{packet_id}-1", "stage": "claim", "attempt": 1,
        "coordinator_id": "coord-1", "run_id": run_id, "hostname": "host-1",
        "boot_id": "boot-1", "pid": 1234,
        "acquired_at": "2026-08-11T12:30:00Z",
        "heartbeat_at": "2026-08-11T12:30:00Z", "lease_seconds": 60,
        "lane": "kimi_implementation", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(
        canonical_bytes(record, omit={"claim_sha256"}))
    return record


def _packet(packet_id="packet-1"):
    packet = {
        "schema_version": 1, "packet_id": packet_id, "objective": "claim fixture",
        "dependency_ids": [], "lane": "kimi_implementation",
        "assigned_worker": {"worker_id": "kimi-1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "starting_revision": "a" * 40,
        "worktree": {"path": "/tmp/p5a-worktree", "branch": "p5a-test"},
        "writable_paths": [f"scripts/{packet_id}.py"], "forbidden_surfaces": [],
        "required_context": [{"path": "HARNESS.md", "sha256": "b" * 64}],
        "premise_checks": [{"check_id": "ck-1", "command_id": "cmd-1", "expected": "present"}],
        "acceptance_criteria": [{"criterion_id": "ac-1", "statement": "works", "required_evidence_ids": ["ev-1"]}],
        "verification_commands": [{"command_id": "cmd-1", "argv": ["python3", "-m", "pytest"], "cwd": ".", "timeout_seconds": 60, "expected_exit_code": 0, "expected_evidence_ids": ["ev-1"]}],
        "budgets": {"max_turns": 10, "wall_clock_seconds": 300, "retry_limit": 2, "max_output_bytes": 1000000, "cost_class": "low", "allowance_limit": 100},
        "network_policy": "denied",
        "checkpoint_artifacts": [{"artifact_id": "art-1", "path": f"scripts/{packet_id}.py", "required_for_fallback": True}],
        "rollback": {"method": "git_reset", "allowed_commands": [{"argv": ["git", "status"], "cwd": "."}]},
        "human_stop_conditions": ["governed_doc_touched"], "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
    }
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


def _enrolled(root):
    from harness_coordinator.v1.enroll import enroll_packets

    packet = _packet()
    enroll_packets(str(root), "srid-1", "coord-1", "run-1",
                   "2026-08-11T12:30:00Z", [packet])
    events, torn = read_journal(str(root / "journal.ndjson"), state_root_id="srid-1")
    assert torn is None
    folded, _ = recovery_module._fold_journal(str(root), events)
    return events, folded["packet-1"]


def _trust_roots(root):
    trust = root / "trust"
    trust.mkdir()
    reviewer = {"schema_version": 1, "sessions": [], "registry_sha256": ""}
    reviewer["registry_sha256"] = compute_sha256(
        canonical_bytes(reviewer, omit={"registry_sha256"}))
    (trust / "reviewer_sessions.json").write_bytes(canonical_bytes(reviewer))
    provider = {"schema_version": 1, "registry_id": "empty", "providers": {}, "registry_sha256": ""}
    provider["registry_sha256"] = compute_sha256(
        canonical_bytes(provider, omit={"registry_sha256"}))
    (trust / "provider_signals.json").write_bytes(canonical_bytes(provider))


def test_pinned_claim_is_canonical_and_o_excl(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = _claim()
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", record)
        assert read_claim_at(handle, "packet-1") == record
        assert list_worker_claim_ids(handle) == ["packet-1"]
        with pytest.raises(FileExistsError):
            create_claim_at(handle, "packet-1", record)
    assert (root / "locks" / "packet-1.lock.json").read_bytes() == canonical_bytes(record)


def test_claim_symlink_is_refused(tmp_path):
    root = tmp_path / "state"
    (root / "locks").mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(canonical_bytes(_claim()))
    os.symlink(outside, root / "locks" / "packet-1.lock.json")
    with open_state_root(str(root)) as handle:
        with pytest.raises(OSError):
            read_claim_at(handle, "packet-1")
        with pytest.raises(ValueError):
            list_worker_claim_ids(handle)


def test_pinned_handle_does_not_follow_replacement_root(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    original = tmp_path / "original"
    with open_state_root(str(root)) as handle:
        root.rename(original)
        root.mkdir()
        create_claim_at(handle, "packet-1", _claim())
        assert (original / "locks" / "packet-1.lock.json").exists()
        assert not (root / "locks" / "packet-1.lock.json").exists()
        with pytest.raises(StateRootMoved):
            handle.verify_identity()


def test_claim_packet_halts_before_writing_replacement_root(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    original = tmp_path / "original"
    with open_state_root(str(root)) as handle:
        root.rename(original)
        root.mkdir()
        with pytest.raises(StateRootMoved):
            claim_packet(
                str(root), "packet-1", {"lane": "kimi_implementation", "attempts_started": 0},
                "coord-1", "run-1",
                {"hostname": "host-1", "boot_id": "boot-1", "pid": 1234},
                "2026-08-11T12:30:00Z", handle=handle)
    assert not (root / "locks").exists()
    assert not (original / "locks").exists()


def test_archive_is_exclusive_and_preserves_exact_bytes(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = _claim()
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", record)
        reclaim_lock_at(handle, "packet-1", "run-2", "STALE_PRIOR_BOOT",
                        record["claim_sha256"])
        with pytest.raises(FileNotFoundError):
            read_claim_at(handle, "packet-1")
    archived = root / "locks" / "reclaimed" / "run-2" / "packet-1.lock.json"
    assert archived.read_bytes() == canonical_bytes(record)


def test_archive_refuses_changed_claim_digest(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = _claim()
    changed = _claim()
    changed["heartbeat_at"] = "2026-08-11T12:31:00Z"
    changed["claim_sha256"] = compute_sha256(
        canonical_bytes(changed, omit={"claim_sha256"}))
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", changed)
        with pytest.raises(ValueError, match="changed"):
            reclaim_lock_at(handle, "packet-1", "run-2", "STALE_PRIOR_BOOT",
                            record["claim_sha256"])
        assert read_claim_at(handle, "packet-1") == changed


def test_archive_refuses_tampered_claim_with_stale_self_hash(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = _claim()
    tampered = dict(record)
    tampered["heartbeat_at"] = "2026-08-11T12:31:00Z"
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", tampered)
        with pytest.raises(ValueError, match="changed"):
            reclaim_lock_at(handle, "packet-1", "run-2", "STALE_PRIOR_BOOT",
                            record["claim_sha256"])
        assert read_claim_at(handle, "packet-1") == tampered


def test_archive_destination_is_exclusive(tmp_path):
    root = tmp_path / "state"
    (root / "locks" / "reclaimed" / "run-2").mkdir(parents=True)
    record = _claim()
    destination = root / "locks" / "reclaimed" / "run-2" / "packet-1.lock.json"
    destination.write_text("occupied")
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", record)
        with pytest.raises(FileExistsError):
            reclaim_lock_at(handle, "packet-1", "run-2", "STALE_SAME_BOOT",
                            record["claim_sha256"])
        assert read_claim_at(handle, "packet-1") == record
    assert destination.read_text() == "occupied"


def test_symlinked_locks_parent_is_refused_without_outside_write(tmp_path):
    root = tmp_path / "state"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    os.symlink(outside, root / "locks")
    with open_state_root(str(root)) as handle:
        with pytest.raises(OSError):
            create_claim_at(handle, "packet-1", _claim())
    assert list(outside.iterdir()) == []


def test_non_regular_claim_is_refused_by_enumeration(tmp_path):
    root = tmp_path / "state"
    (root / "locks" / "packet-1.lock.json").mkdir(parents=True)
    with open_state_root(str(root)) as handle:
        with pytest.raises(ValueError, match="not a regular file"):
            list_worker_claim_ids(handle)


def test_parent_swap_after_directory_pin_cannot_redirect_claim(tmp_path, monkeypatch):
    root = tmp_path / "state"
    locks = root / "locks"
    outside = tmp_path / "outside"
    locks.mkdir(parents=True)
    outside.mkdir()
    original_open = locks_module.os.open
    swapped = {"done": False}

    def swapping_open(path, flags, *args, **kwargs):
        if path == "packet-1.lock.json" and not swapped["done"]:
            swapped["done"] = True
            locks.rename(root / "locks-original")
            os.symlink(outside, locks)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(locks_module.os, "open", swapping_open)
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", _claim())
    assert (root / "locks-original" / "packet-1.lock.json").exists()
    assert list(outside.iterdir()) == []


def test_recovery_enumeration_ignores_replacement_root_claim(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    original = tmp_path / "original"
    with open_state_root(str(root)) as handle:
        root.rename(original)
        root.mkdir()
        with open_state_root(str(root)) as replacement:
            create_claim_at(replacement, "packet-1", _claim())
        assert recovery_module._reconcile_locks(
            str(original), str(original / "journal.ndjson"),
            str(original / "locks" / "journal.wlock"), [], "coord-1", "run-2",
            "srid-1", "2026-08-11T12:31:00Z",
            {"coordinator_id": "coord-1", "hostname": "host-1", "boot_id": "boot-2",
             "pid": 99, "live_coordinator_ids": set(), "now": "2026-08-11T12:31:00Z"},
            set(), handle=handle) == []
    assert (root / "locks" / "packet-1.lock.json").exists()


def test_pending_reclaim_journals_lock_then_abandon_then_archives(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    record = _claim()
    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", record)
        events = []
        abandoned, reclaimed = recovery_module._resolve_pending_intents(
            str(root), str(root / "journal.ndjson"),
            str(root / "locks" / "journal.wlock"), events, "coord-2", "run-2",
            "srid-1", "2026-08-11T12:31:00Z",
            {"coordinator_id": "coord-2", "hostname": "host-1", "boot_id": "boot-2",
             "pid": 99, "live_coordinator_ids": set(), "now": "2026-08-11T12:31:00Z"},
            [{"intent_id": record["intent_id"], "packet_id": "packet-1"}],
            handle=handle)
    assert [event["event_type"] for event in events] == ["LOCK_RECLAIMED", "INTENT_ABANDONED"]
    assert len(abandoned) == 1 and reclaimed == ["packet-1"]
    assert (root / "locks" / "reclaimed" / "run-2" / "packet-1.lock.json").read_bytes() == canonical_bytes(record)


def test_run_once_passes_its_single_handle_into_recovery(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    seen = {}

    class Report:
        state_root_id = None
        journal_events = []
        derived_states = {}
        released = False

        def release_singleton(self):
            self.released = True

    report = Report()

    def fake_recovery(*args, **kwargs):
        seen["handle"] = kwargs["handle"]
        return report

    monkeypatch.setattr(coordinator_module, "run_started_recovery", fake_recovery)
    result = coordinator_module.run_once(
        str(root), "coord-1", "run-1",
        {"hostname": "host-1", "boot_id": "boot-1", "pid": 1},
        "2026-08-11T12:30:00Z")
    assert result == {"status": "no_eligible_work", "packet_id": None}
    assert report.released is True
    with pytest.raises(ValueError, match="closed"):
        _ = seen["handle"].fd


def test_direct_recovery_fallback_closes_handle_on_failure(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    captured = {}
    real_open = recovery_module.open_state_root

    def capturing_open(path):
        handle = real_open(path)
        captured["handle"] = handle
        return handle

    monkeypatch.setattr(recovery_module, "open_state_root", capturing_open)
    with pytest.raises(recovery_module.IntegrityError):
        recovery_module.run_started_recovery(
            str(root), "coord-1", "run-1",
            {"coordinator_id": "coord-1", "hostname": "host-1", "boot_id": "boot-1",
             "pid": 1, "live_coordinator_ids": set(), "now": "2026-08-11T12:30:00Z"},
            "2026-08-11T12:30:00Z")
    with pytest.raises(ValueError, match="closed"):
        _ = captured["handle"].fd


def test_direct_recovery_fallback_closes_handle_on_success(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    _trust_roots(root)
    captured = {}
    real_open = recovery_module.open_state_root

    def capturing_open(path):
        handle = real_open(path)
        captured["handle"] = handle
        return handle

    monkeypatch.setattr(recovery_module, "open_state_root", capturing_open)
    report = recovery_module.run_started_recovery(
        str(root), "coord-1", "run-1",
        {"coordinator_id": "coord-1", "hostname": "host-1", "boot_id": "boot-1",
         "pid": 1, "live_coordinator_ids": set(), "now": "2026-08-11T12:30:00Z"},
        "2026-08-11T12:30:00Z")
    report.release_singleton()
    with pytest.raises(ValueError, match="closed"):
        _ = captured["handle"].fd


def test_direct_recovery_refuses_symlinked_final_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "state-link"
    os.symlink(outside, root)
    with pytest.raises(OSError):
        recovery_module.run_started_recovery(
            str(root), "coord-1", "run-1", {}, "2026-08-11T12:30:00Z")
    assert list(outside.iterdir()) == []


def test_direct_recovery_refuses_symlinked_parent_component(tmp_path):
    outside = tmp_path / "outside"
    target = outside / "state"
    outside.mkdir()
    parent = tmp_path / "parent-link"
    os.symlink(outside, parent)
    root = parent / "state"
    with pytest.raises(OSError):
        recovery_module.run_started_recovery(
            str(root), "coord-1", "run-1", {}, "2026-08-11T12:30:00Z")
    assert not target.exists()


def test_root_swap_after_claim_halts_before_pending_projection(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    events, folded = _enrolled(root)
    original = tmp_path / "original"
    real_create = coordinator_module.create_claim_at

    def create_then_swap(handle, packet_id, record):
        real_create(handle, packet_id, record)
        root.rename(original)
        root.mkdir()

    monkeypatch.setattr(coordinator_module, "create_claim_at", create_then_swap)
    with open_state_root(str(root)) as handle:
        with pytest.raises(StateRootMoved):
            coordinator_module.claim_and_start_attempt(
                str(root), "srid-1", events, "packet-1", folded, "coord-1", "run-2",
                {"hostname": "host-1", "boot_id": "boot-1", "pid": 1234},
                "2026-08-11T12:31:00Z", handle=handle)
    assert (original / "locks" / "packet-1.lock.json").exists()
    assert not (root / "queue.json").exists()
    assert not (root / "journal.ndjson").exists()


def test_cas_reread_halts_on_replacement_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    events, folded = _enrolled(root)
    original = tmp_path / "original"

    def move_then_conflict(*args, **kwargs):
        root.rename(original)
        root.mkdir()
        raise JournalHeadMoved("injected")

    monkeypatch.setattr(coordinator_module, "append_journal", move_then_conflict)
    with open_state_root(str(root)) as handle:
        with pytest.raises(StateRootMoved):
            coordinator_module.claim_and_start_attempt(
                str(root), "srid-1", events, "packet-1", folded, "coord-1", "run-2",
                {"hostname": "host-1", "boot_id": "boot-1", "pid": 1234},
                "2026-08-11T12:31:00Z", handle=handle)
    assert not (root / "journal.ndjson").exists()
    assert not (root / "locks" / "packet-1.lock.json").exists()


def test_swap_after_reclaim_evidence_stops_before_archive(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    original = tmp_path / "original"
    record = _claim()
    real_append = recovery_module.append_journal
    calls = {"count": 0}

    def append_then_swap(*args, **kwargs):
        real_append(*args, **kwargs)
        calls["count"] += 1
        if calls["count"] == 2:
            root.rename(original)
            root.mkdir()

    with open_state_root(str(root)) as handle:
        create_claim_at(handle, "packet-1", record)
        monkeypatch.setattr(recovery_module, "append_journal", append_then_swap)
        with pytest.raises(StateRootMoved):
            recovery_module._reconcile_locks(
                str(root), str(root / "journal.ndjson"),
                str(root / "locks" / "journal.wlock"), [], "coord-2", "run-2",
                "srid-1", "2026-08-11T12:31:00Z",
                {"coordinator_id": "coord-2", "hostname": "host-1", "boot_id": "boot-2",
                 "pid": 99, "live_coordinator_ids": set(), "now": "2026-08-11T12:31:00Z"},
                set(), handle=handle)
    assert (original / "locks" / "packet-1.lock.json").exists()
    assert not (original / "locks" / "reclaimed").exists()
    assert not (root / "locks").exists()
