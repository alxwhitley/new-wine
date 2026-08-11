"""P5A: enrollment, deterministic selection, and distinct lock proofs."""

import copy
import multiprocessing
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256


def _packet(packet_id, dependencies=None):
    packet = {
        "schema_version": 1, "packet_id": packet_id, "objective": "P5A fixture",
        "dependency_ids": dependencies or [], "lane": "kimi_implementation",
        "assigned_worker": {"worker_id": "kimi-1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "starting_revision": "a" * 40,
        "worktree": {"path": "/tmp/p5a-worktree", "branch": "p5a-test"},
        "writable_paths": [f"scripts/{packet_id}.py"],
        "forbidden_surfaces": ["backend/app/services/answer_toolbox.py"],
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


def test_invalid_item_preflights_entire_batch_before_any_write(tmp_path):
    from harness_coordinator.v1.enroll import PacketPreflightError, enroll_packets
    invalid = _packet("bad")
    invalid["objective"] = ""
    with pytest.raises(PacketPreflightError):
        enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [_packet("good"), invalid])
    assert not (tmp_path / "journal.ndjson").exists()
    assert not (tmp_path / "packets").exists()


def test_stale_enrollment_time_is_rejected_before_any_publication(tmp_path):
    from harness_coordinator.v1.enroll import PacketPreflightError, enroll_packets
    from harness_coordinator.v1.store import read_journal

    args = (str(tmp_path), "srid-1", "coord-1", "run-1")
    enroll_packets(*args, "2026-08-10T00:00:02Z", [_packet("packet-1")])
    journal_before = (tmp_path / "journal.ndjson").read_bytes()
    queue_before = (tmp_path / "queue.json").read_bytes()

    with pytest.raises(PacketPreflightError) as exc_info:
        enroll_packets(*args, "2026-08-10T00:00:01Z", [_packet("packet-2")])

    assert any(error["code"] == "CHRONOLOGY_VIOLATION" for error in exc_info.value.errors)
    assert (tmp_path / "journal.ndjson").read_bytes() == journal_before
    assert (tmp_path / "queue.json").read_bytes() == queue_before
    assert not (tmp_path / "packets" / "packet-2.json").exists()
    events, torn = read_journal(str(tmp_path / "journal.ndjson"), state_root_id="srid-1")
    assert torn is None
    assert [event.get("packet_id") for event in events] == ["packet-1"]


def test_stale_time_precedes_mixed_batch_rejection_evidence(tmp_path):
    from harness_coordinator.v1.enroll import PacketPreflightError, enroll_packets

    args = (str(tmp_path), "srid-1", "coord-1", "run-1")
    enroll_packets(*args, "2026-08-10T00:00:02Z", [_packet("packet-1")])
    journal_before = (tmp_path / "journal.ndjson").read_bytes()
    queue_before = (tmp_path / "queue.json").read_bytes()
    (tmp_path / "packets" / "packet-3.json").write_bytes(b"conflicting bytes")

    with pytest.raises(PacketPreflightError) as exc_info:
        enroll_packets(
            *args,
            "2026-08-10T00:00:01Z",
            [_packet("packet-2"), _packet("packet-3")],
        )

    assert any(error["code"] == "CHRONOLOGY_VIOLATION" for error in exc_info.value.errors)
    assert (tmp_path / "journal.ndjson").read_bytes() == journal_before
    assert (tmp_path / "queue.json").read_bytes() == queue_before
    assert not (tmp_path / "packets" / "packet-2.json").exists()
    assert not (tmp_path / "rejected").exists()


def test_equal_enrollment_time_is_allowed(tmp_path):
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.store import read_journal

    args = (str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z")
    assert enroll_packets(*args, [_packet("packet-1")]) == {
        "enrolled": ["packet-1"],
        "skipped": [],
    }
    assert enroll_packets(*args, [_packet("packet-2")]) == {
        "enrolled": ["packet-2"],
        "skipped": [],
    }
    events, torn = read_journal(str(tmp_path / "journal.ndjson"), state_root_id="srid-1")
    assert torn is None
    assert [event.get("packet_id") for event in events] == ["packet-1", "packet-2"]


def test_two_packet_batch_with_one_timestamp_remains_valid(tmp_path):
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.store import read_journal

    result = enroll_packets(
        str(tmp_path),
        "srid-1",
        "coord-1",
        "run-1",
        "2026-08-10T00:00:00Z",
        [_packet("packet-1"), _packet("packet-2")],
    )

    assert result == {"enrolled": ["packet-1", "packet-2"], "skipped": []}
    events, torn = read_journal(str(tmp_path / "journal.ndjson"), state_root_id="srid-1")
    assert torn is None
    assert [event.get("packet_id") for event in events] == ["packet-1", "packet-2"]


def test_cas_refresh_revalidates_chronology_against_new_head(tmp_path, monkeypatch):
    import harness_coordinator.v1.enroll as enroll
    from harness_coordinator.v1.recovery import _make_event
    from harness_coordinator.v1.store import JournalHeadMoved, read_journal

    args = (str(tmp_path), "srid-1", "coord-1", "run-1")
    enroll.enroll_packets(*args, "2026-08-10T00:00:00Z", [_packet("packet-1")])
    original_events, torn = read_journal(
        str(tmp_path / "journal.ndjson"), state_root_id="srid-1"
    )
    assert torn is None
    packet = _packet("packet-3")
    intervening = _make_event(
        2,
        "PACKET_ENROLLED",
        "coord-other",
        "run-other",
        "srid-1",
        original_events[-1],
        "2026-08-10T00:00:02Z",
        packet_id="packet-3",
        intent_id="enroll-packet-3-2",
        to_state="READY",
        cause="enrollment",
        payload={
            "packet": {
                "packet_sha256": packet["packet_sha256"],
                "packet_path": "packets/packet-3.json",
                "lane": packet["lane"],
                "dependency_ids": [],
                "sonnet_reassignment_allowed": True,
                "retry_limit": 2,
                "enqueue_seq": 2,
            },
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": None,
        },
    )
    real_append = enroll.append_journal

    def move_once(*call_args, **call_kwargs):
        monkeypatch.setattr(enroll, "append_journal", real_append)
        raise JournalHeadMoved(intervening)

    real_read = enroll.read_journal

    def read_with_intervening(path, state_root_id=None):
        if path == str(tmp_path / "journal.ndjson"):
            return original_events + [intervening], None
        return real_read(path, state_root_id=state_root_id)

    monkeypatch.setattr(enroll, "append_journal", move_once)
    monkeypatch.setattr(enroll, "read_journal", read_with_intervening)

    with pytest.raises(enroll.PacketPreflightError) as exc_info:
        enroll.enroll_packets(*args, "2026-08-10T00:00:01Z", [_packet("packet-2")])

    assert any(error["code"] == "CHRONOLOGY_VIOLATION" for error in exc_info.value.errors)
    actual_events, actual_torn = real_read(
        str(tmp_path / "journal.ndjson"), state_root_id="srid-1"
    )
    assert actual_torn is None
    assert [event.get("packet_id") for event in actual_events] == ["packet-1"]


def test_identical_duplicate_is_noop_and_conflicting_duplicate_is_rejected(tmp_path):
    from harness_coordinator.v1.enroll import ConflictingEnrollment, enroll_packets
    args = (str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z")
    packet = _packet("packet-1")
    assert enroll_packets(*args, [packet]) == {"enrolled": ["packet-1"], "skipped": []}
    journal_before = (tmp_path / "journal.ndjson").read_bytes()
    assert enroll_packets(*args, [packet]) == {"enrolled": [], "skipped": ["packet-1"]}
    assert (tmp_path / "journal.ndjson").read_bytes() == journal_before
    changed = copy.deepcopy(packet)
    changed["objective"] = "different"
    changed["packet_sha256"] = compute_sha256(canonical_bytes(changed, omit={"packet_sha256"}))
    with pytest.raises(ConflictingEnrollment):
        enroll_packets(*args, [changed])
    assert (tmp_path / "journal.ndjson").read_bytes() == journal_before


def test_retry_after_partial_batch_skips_prefix_and_finishes_suffix(tmp_path, monkeypatch):
    import harness_coordinator.v1.enroll as enroll
    args = (str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z")
    packets = [_packet("packet-1"), _packet("packet-2")]
    real = enroll.append_journal
    calls = 0
    def crash_second(*a, **kw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("crash")
        return real(*a, **kw)
    monkeypatch.setattr(enroll, "append_journal", crash_second)
    with pytest.raises(RuntimeError, match="crash"):
        enroll.enroll_packets(*args, packets)
    monkeypatch.setattr(enroll, "append_journal", real)
    assert enroll.enroll_packets(*args, packets) == {"enrolled": ["packet-2"], "skipped": ["packet-1"]}


def test_later_conflicting_artifact_preflight_leaves_entire_batch_untouched(tmp_path):
    from harness_coordinator.v1.enroll import ConflictingEnrollment, enroll_packets
    packets_dir = tmp_path / "packets"
    packets_dir.mkdir()
    (packets_dir / "packet-2.json").write_bytes(b"conflicting bytes")
    with pytest.raises(ConflictingEnrollment):
        enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [_packet("packet-1"), _packet("packet-2")])
    assert not (tmp_path / "journal.ndjson").exists()
    assert not (packets_dir / "packet-1.json").exists()
    evidence = list((tmp_path / "rejected" / "enrollment").glob("packet-2.*.json"))
    assert len(evidence) == 1


def test_journal_head_move_reloads_fold_and_never_duplicates_enrollment(tmp_path, monkeypatch):
    import harness_coordinator.v1.enroll as enroll
    from harness_coordinator.v1.store import JournalHeadMoved
    real = enroll.append_journal
    calls = 0
    def move_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise JournalHeadMoved({"simulated": "new head"})
        return real(*args, **kwargs)
    monkeypatch.setattr(enroll, "append_journal", move_once)
    result = enroll.enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [_packet("packet-1")])
    assert result == {"enrolled": ["packet-1"], "skipped": []}
    lines = (tmp_path / "journal.ndjson").read_text().splitlines()
    assert len(lines) == 1
    assert calls == 2


def test_conflicting_duplicate_preserves_idempotent_rejection_evidence(tmp_path):
    from harness_coordinator.v1.enroll import ConflictingEnrollment, enroll_packets
    args = (str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z")
    original = _packet("packet-1")
    enroll_packets(*args, [original])
    changed = copy.deepcopy(original)
    changed["objective"] = "conflict"
    changed["packet_sha256"] = compute_sha256(canonical_bytes(changed, omit={"packet_sha256"}))
    for _ in range(2):
        with pytest.raises(ConflictingEnrollment):
            enroll_packets(*args, [changed])
    evidence = list((tmp_path / "rejected" / "enrollment").glob("packet-1.*.json"))
    assert len(evidence) == 1


def test_artifact_conflict_injected_after_preflight_preserves_rejection_without_journal(tmp_path, monkeypatch):
    import harness_coordinator.v1.enroll as enroll
    packet = _packet("packet-1")
    real = enroll._preserve_packet
    def inject_then_preserve(path, body):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as artifact:
            artifact.write(b"racing conflicting artifact")
        return real(path, body)
    monkeypatch.setattr(enroll, "_preserve_packet", inject_then_preserve)
    with pytest.raises(enroll.ConflictingEnrollment):
        enroll.enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [packet])
    assert not (tmp_path / "journal.ndjson").exists()
    evidence_paths = list((tmp_path / "rejected" / "enrollment").glob("packet-1.*.json"))
    assert len(evidence_paths) == 1
    evidence = __import__("json").loads(evidence_paths[0].read_text())
    assert evidence["reason"] == "artifact_race_conflict"
    assert evidence["offered_packet_sha256"] == packet["packet_sha256"]
    assert evidence["existing_bytes_sha256"] == compute_sha256(b"racing conflicting artifact")


def test_post_preflight_symlink_race_never_follows_outside_target(tmp_path, monkeypatch):
    import harness_coordinator.v1.enroll as enroll
    packet = _packet("packet-1")
    artifact_path = tmp_path / "packets" / "packet-1.json"
    outside = tmp_path.parent / "outside-secret-packet.json"
    outside.write_bytes(b"outside secret bytes")
    real_open = enroll.os.open
    injected = False
    def inject_symlink(path, flags, *args):
        nonlocal injected
        if path == str(artifact_path) and flags & os.O_CREAT and not injected:
            injected = True
            artifact_path.symlink_to(outside)
        return real_open(path, flags, *args)
    monkeypatch.setattr(enroll.os, "open", inject_symlink)
    with pytest.raises(enroll.ConflictingEnrollment):
        enroll.enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [packet])
    assert outside.read_bytes() == b"outside secret bytes"
    assert not (tmp_path / "journal.ndjson").exists()
    evidence_path = next((tmp_path / "rejected" / "enrollment").glob("packet-1.*.json"))
    evidence = __import__("json").loads(evidence_path.read_text())
    assert evidence["reason"] == "artifact_race_conflict"
    assert evidence["existing_bytes_sha256"] is None


def test_preexisting_contained_identical_symlink_is_rejected_without_retargeting(tmp_path):
    import harness_coordinator.v1.enroll as enroll
    packet = _packet("packet-1")
    packets = tmp_path / "packets"
    packets.mkdir()
    shared = packets / "shared.json"
    shared.write_bytes(canonical_bytes(packet))
    artifact = packets / "packet-1.json"
    artifact.symlink_to(shared.name)
    with pytest.raises(enroll.ConflictingEnrollment):
        enroll.enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [packet])
    assert artifact.is_symlink()
    assert os.readlink(artifact) == "shared.json"
    assert not (tmp_path / "journal.ndjson").exists()
    evidence_path = next((tmp_path / "rejected" / "enrollment").glob("packet-1.*.json"))
    evidence = __import__("json").loads(evidence_path.read_text())
    assert evidence["reason"] == "artifact_symlink_conflict"


def test_outside_packets_parent_alias_becomes_deterministic_rejection(tmp_path):
    import harness_coordinator.v1.enroll as enroll
    outside = tmp_path.parent / "outside-packets-dir"
    outside.mkdir(exist_ok=True)
    (tmp_path / "packets").symlink_to(outside, target_is_directory=True)
    packet = _packet("packet-1")
    with pytest.raises(enroll.ConflictingEnrollment):
        enroll.enroll_packets(str(tmp_path), "srid-1", "coord-1", "run-1", "2026-08-10T00:00:00Z", [packet])
    assert not (tmp_path / "journal.ndjson").exists()
    evidence_path = next((tmp_path / "rejected" / "enrollment").glob("packet-1.*.json"))
    evidence = __import__("json").loads(evidence_path.read_text())
    assert evidence["reason"] == "artifact_path_escape_conflict"
    assert evidence["offered_packet_sha256"] == packet["packet_sha256"]


def test_run_once_selects_lowest_enqueue_sequence(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    report = type("Report", (), {"state_root_id": "srid-1", "journal_events": [], "derived_states": {
        "later": {"state": "READY", "enqueue_seq": 9, "lane": "kimi_implementation", "dependency_ids": [], "retry_limit": 2, "attempts_started": 0, "open_attempt": None, "terminal_seal_sha256": None, "earliest_next_attempt_at": None},
        "first": {"state": "READY", "enqueue_seq": 2, "lane": "kimi_implementation", "dependency_ids": [], "retry_limit": 2, "attempts_started": 0, "open_attempt": None, "terminal_seal_sha256": None, "earliest_next_attempt_at": None},
    }, "release_singleton": lambda self: None})()
    monkeypatch.setattr(coordinator, "run_started_recovery", lambda **kw: report)
    monkeypatch.setattr(coordinator, "claim_and_start_attempt", lambda **kw: "attempt-first-1")
    assert coordinator.run_once(str(tmp_path), "coord-1", "run-1", {}, "2026-08-10T00:00:00Z")["packet_id"] == "first"


def test_claim_sequence_commits_pending_intent_then_attempt_started(tmp_path):
    from harness_coordinator.v1.coordinator import claim_and_start_attempt
    from harness_coordinator.v1.recovery import _fold_journal, _make_event
    packet = _packet("packet-1")
    packet_path = tmp_path / "packets" / "packet-1.json"
    packet_path.parent.mkdir()
    packet_path.write_bytes(canonical_bytes(packet))
    payload = {"packet": {"packet_sha256": packet["packet_sha256"], "packet_path": "packets/packet-1.json", "lane": packet["lane"], "dependency_ids": [], "sonnet_reassignment_allowed": True, "retry_limit": 2, "enqueue_seq": 1}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None}
    enrolled = _make_event(1, "PACKET_ENROLLED", "coord-1", "run-1", "srid-1", None, "2026-08-10T00:00:00Z", packet_id="packet-1", intent_id="enroll-1", to_state="READY", cause="enrollment", payload=payload)
    (tmp_path / "locks").mkdir()
    (tmp_path / "journal.ndjson").write_bytes(canonical_bytes(enrolled) + b"\n")
    folded, _ = _fold_journal(str(tmp_path), [enrolled])
    context = {"hostname": "host-1", "boot_id": "boot-1", "pid": os.getpid(), "coordinator_id": "coord-1", "live_coordinator_ids": set(), "now": "2026-08-10T00:00:00Z"}
    intent = claim_and_start_attempt(str(tmp_path), "srid-1", [enrolled], "packet-1", folded["packet-1"], "coord-1", "run-1", context, "2026-08-10T00:00:00Z")
    lines = [__import__("json").loads(line) for line in (tmp_path / "journal.ndjson").read_text().splitlines()]
    assert intent == "attempt-packet-1-1"
    assert lines[-1]["event_type"] == "ATTEMPT_STARTED"
    assert _fold_journal(str(tmp_path), lines)[0]["packet-1"]["open_attempt"] == 1
    queue = __import__("json").loads((tmp_path / "queue.json").read_text())
    assert queue["pending_intents"] == []
    assert lines[-1]["payload"]["attempt"]["worker"]["session_id"] == "session-run-1-packet-1-1"


def test_attempt_started_retries_bounded_journal_head_move(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.store import JournalHeadMoved
    enrolled, state, context = _ready_attempt_fixture(tmp_path)
    real = coordinator.append_journal
    calls = 0
    def move_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise JournalHeadMoved({"moved": True})
        return real(*args, **kwargs)
    monkeypatch.setattr(coordinator, "append_journal", move_once)
    coordinator.claim_and_start_attempt(str(tmp_path), "srid-1", [enrolled], "packet-1", state, "coord-1", "run-1", context, "2026-08-10T00:00:00Z")
    assert calls == 2


def test_packet_artifact_symlink_escape_rejected_before_attempt(tmp_path):
    import harness_coordinator.v1.coordinator as coordinator
    enrolled, state, context = _ready_attempt_fixture(tmp_path)
    artifact = tmp_path / "packets" / "packet-1.json"
    outside = tmp_path.parent / "outside-packet.json"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink|escape"):
        coordinator.claim_and_start_attempt(str(tmp_path), "srid-1", [enrolled], "packet-1", state, "coord-1", "run-1", context, "2026-08-10T00:00:00Z")
    assert not (tmp_path / "locks" / "packet-1.lock.json").exists()


def _ready_attempt_fixture(tmp_path):
    from harness_coordinator.v1.recovery import _fold_journal, _make_event
    packet = _packet("packet-1")
    packet_path = tmp_path / "packets" / "packet-1.json"
    packet_path.parent.mkdir()
    packet_path.write_bytes(canonical_bytes(packet))
    payload = {"packet": {"packet_sha256": packet["packet_sha256"], "packet_path": "packets/packet-1.json", "lane": packet["lane"], "dependency_ids": [], "sonnet_reassignment_allowed": True, "retry_limit": 2, "enqueue_seq": 1}, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None}
    enrolled = _make_event(1, "PACKET_ENROLLED", "coord-1", "run-1", "srid-1", None, "2026-08-10T00:00:00Z", packet_id="packet-1", intent_id="enroll-1", to_state="READY", cause="enrollment", payload=payload)
    (tmp_path / "locks").mkdir()
    (tmp_path / "journal.ndjson").write_bytes(canonical_bytes(enrolled) + b"\n")
    folded, _ = _fold_journal(str(tmp_path), [enrolled])
    context = {"hostname": "host-1", "boot_id": "boot-1", "pid": os.getpid(), "coordinator_id": "coord-1", "live_coordinator_ids": set(), "now": "2026-08-10T00:00:00Z"}
    return enrolled, folded["packet-1"], context


def test_crash_after_claim_and_pending_before_journal_is_recoverably_abandoned(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.recovery import _resolve_pending_intents
    enrolled, state, context = _ready_attempt_fixture(tmp_path)
    monkeypatch.setattr(coordinator, "append_journal", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash-before-journal")))
    with pytest.raises(RuntimeError, match="crash-before-journal"):
        coordinator.claim_and_start_attempt(str(tmp_path), "srid-1", [enrolled], "packet-1", state, "coord-1", "run-1", context, "2026-08-10T00:00:00Z")
    queue = __import__("json").loads((tmp_path / "queue.json").read_text())
    assert queue["pending_intents"][0]["intent_id"] == "attempt-packet-1-1"
    stale = {**context, "coordinator_id": "coord-2", "boot_id": "boot-2", "pid": os.getpid() + 1}
    abandoned, reclaimed = _resolve_pending_intents(str(tmp_path), str(tmp_path / "journal.ndjson"), str(tmp_path / "locks" / "journal.wlock"), [enrolled], "coord-2", "run-2", "srid-1", "2026-08-10T00:00:01Z", stale, queue["pending_intents"])
    assert len(abandoned) == 1
    assert reclaimed == ["packet-1"]


def test_crash_after_attempt_journal_before_projection_is_recognized_committed(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.recovery import _resolve_pending_intents
    from harness_coordinator.v1.store import read_journal
    enrolled, state, context = _ready_attempt_fixture(tmp_path)
    real = coordinator.atomic_replace
    writes = 0
    def crash_second_projection(*args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise RuntimeError("crash-after-journal")
        return real(*args, **kwargs)
    monkeypatch.setattr(coordinator, "atomic_replace", crash_second_projection)
    with pytest.raises(RuntimeError, match="crash-after-journal"):
        coordinator.claim_and_start_attempt(str(tmp_path), "srid-1", [enrolled], "packet-1", state, "coord-1", "run-1", context, "2026-08-10T00:00:00Z")
    events, _ = read_journal(str(tmp_path / "journal.ndjson"), state_root_id="srid-1")
    assert events[-1]["event_type"] == "ATTEMPT_STARTED"
    queue = __import__("json").loads((tmp_path / "queue.json").read_text())
    stale = {**context, "coordinator_id": "coord-2", "boot_id": "boot-2", "pid": os.getpid() + 1}
    abandoned, reclaimed = _resolve_pending_intents(str(tmp_path), str(tmp_path / "journal.ndjson"), str(tmp_path / "locks" / "journal.wlock"), events, "coord-2", "run-2", "srid-1", "2026-08-10T00:00:01Z", stale, queue["pending_intents"])
    assert abandoned == []
    assert reclaimed == []
    assert (tmp_path / "locks" / "packet-1.lock.json").exists()


def _claim_worker(path, record, barrier, results):
    from harness_coordinator.v1.locks import create_claim
    barrier.wait()
    try:
        create_claim(path, record)
        results.put("won")
    except FileExistsError:
        results.put("lost")


def _coordinator_worker(state_root, coordinator_id, start, release, results):
    from harness_coordinator.v1.recovery import CoordinatorAlreadyRunning, run_started_recovery
    start.wait()
    context = {"coordinator_id": coordinator_id, "hostname": "host-1", "boot_id": "boot-1", "pid": os.getpid(), "live_coordinator_ids": set(), "now": "2026-08-10T00:00:00Z"}
    try:
        report = run_started_recovery(state_root, coordinator_id, f"run-{coordinator_id}", context, "2026-08-10T00:00:00Z")
    except CoordinatorAlreadyRunning:
        results.put("lost")
        return
    results.put("won")
    release.wait(5)
    report.release_singleton()


def test_two_top_level_coordinators_admit_one_singleton_winner(tmp_path):
    trust = tmp_path / "trust"
    trust.mkdir()
    reviewer = {"schema_version": 1, "sessions": [], "registry_sha256": ""}
    reviewer["registry_sha256"] = compute_sha256(canonical_bytes(reviewer, omit={"registry_sha256"}))
    (trust / "reviewer_sessions.json").write_bytes(canonical_bytes(reviewer))
    provider = {"schema_version": 1, "registry_id": "empty", "providers": {}, "registry_sha256": ""}
    provider["registry_sha256"] = compute_sha256(canonical_bytes(provider, omit={"registry_sha256"}))
    (trust / "provider_signals.json").write_bytes(canonical_bytes(provider))
    start = multiprocessing.Event()
    release = multiprocessing.Event()
    results = multiprocessing.Queue()
    procs = [multiprocessing.Process(target=_coordinator_worker, args=(str(tmp_path), f"coord-{i}", start, release, results)) for i in range(2)]
    for proc in procs: proc.start()
    start.set()
    outcomes = [results.get(timeout=5) for _ in range(2)]
    release.set()
    for proc in procs: proc.join(5)
    assert sorted(outcomes) == ["lost", "won"]


def test_lower_level_claim_contention_has_exactly_one_winner(tmp_path):
    path = str(tmp_path / "locks" / "packet-1.lock.json")
    record = {"packet_id": "packet-1"}
    barrier = multiprocessing.Barrier(2)
    results = multiprocessing.Queue()
    procs = [multiprocessing.Process(target=_claim_worker, args=(path, record, barrier, results)) for _ in range(2)]
    for proc in procs: proc.start()
    for proc in procs: proc.join(5)
    assert sorted(results.get(timeout=1) for _ in range(2)) == ["lost", "won"]


def test_run_once_releases_singleton_when_selection_finishes(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    released = []
    report = type("Report", (), {"derived_states": {}, "release_singleton": lambda self: released.append(True)})()
    monkeypatch.setattr(coordinator, "run_started_recovery", lambda **kw: report)
    assert coordinator.run_once(str(tmp_path), "coord-1", "run-1", {}, "2026-08-10T00:00:00Z") == {"status": "no_eligible_work", "packet_id": None}
    assert released == [True]


def test_run_cli_requires_explicit_once():
    from harness_coordinator.v1.run_cli import main
    with pytest.raises(SystemExit):
        main([])


def test_run_cli_derives_trusted_context_locally_not_from_argv(tmp_path, monkeypatch):
    import harness_coordinator.v1.run_cli as cli
    captured = {}
    local = {"hostname": "local-host", "boot_id": "local-boot", "pid": 42, "coordinator_id": "coord-1", "live_coordinator_ids": {"coord-1"}, "now": "2026-08-10T00:00:00Z"}
    monkeypatch.setattr(cli, "derive_local_process_context", lambda coordinator_id, now: local)
    def fake_run_once(*args):
        captured["context"] = args[3]
        return {"status": "no_eligible_work", "packet_id": None}
    monkeypatch.setattr(cli, "run_once", fake_run_once)
    assert cli.main(["--once", "--state-root", str(tmp_path), "--coordinator-id", "coord-1", "--run-id", "run-1", "--now", "2026-08-10T00:00:00Z"]) == 0
    assert captured["context"] is local


def test_local_context_reads_linux_boot_id(monkeypatch):
    import harness_coordinator.v1.run_cli as cli
    monkeypatch.setattr(cli.os.path, "exists", lambda path: path == "/proc/sys/kernel/random/boot_id")
    monkeypatch.setattr("builtins.open", lambda *a, **k: __import__("io").StringIO("linux-boot\n"))
    context = cli.derive_local_process_context("coord-1", "2026-08-10T00:00:00Z")
    assert context["boot_id"] == "linux-boot"


def test_local_context_uses_macos_sysctl_fallback(monkeypatch):
    import harness_coordinator.v1.run_cli as cli
    monkeypatch.setattr(cli.os.path, "exists", lambda path: False)
    result = type("Result", (), {"stdout": "{ sec = 123 }\n"})()
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: result)
    assert cli.derive_local_process_context("coord-1", "2026-08-10T00:00:00Z")["boot_id"] == "{ sec = 123 }"


def test_local_context_fails_when_boot_identity_unavailable(monkeypatch):
    import harness_coordinator.v1.run_cli as cli
    monkeypatch.setattr(cli.os.path, "exists", lambda path: False)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: type("Result", (), {"stdout": ""})())
    with pytest.raises(RuntimeError, match="boot identity unavailable"):
        cli.derive_local_process_context("coord-1", "2026-08-10T00:00:00Z")
