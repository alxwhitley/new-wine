"""P5A0 safe harness identifier and state-path tests."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import validate_journal_event
from harness_contracts.v1.packet import validate_packet
from harness_coordinator.v1.reconcile import (
    _check_seal_consistency,
    build_reconciliation_report,
    emit_reconciliation_report,
)
from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, _handle_torn_tail
from harness_coordinator.v1.locks import reclaim_lock
from harness_coordinator.v1.store import atomic_replace, read_journal, sweep_orphans
from test_o2_packet_contract import _minimal_valid_packet
from test_o3_crash_recovery import _make_event, _make_packet_payload
from test_o3_reconciliation import _make_event as _make_reconcile_event
from test_o3_reconciliation import _new_state_root, _run_payload, _write_journal


UNSAFE_IDS = (
    "../../evil",
    "/absolute",
    "has/slash",
    r"has\backslash",
    "",
    "a" * 129,
    "Uppercase",
    ".leading-dot",
)


def _rehash(packet):
    packet["packet_sha256"] = compute_sha256(
        canonical_bytes(packet, omit={"packet_sha256"})
    )
    return packet


@pytest.mark.parametrize("packet_id", UNSAFE_IDS)
def test_packet_id_rejects_unsafe_filesystem_identifiers(packet_id):
    packet = _minimal_valid_packet()
    packet["packet_id"] = packet_id
    result = validate_packet(_rehash(packet), dependency_states=None)
    assert not result["valid"]
    assert any(error["path"] == "/packet_id" for error in result["errors"])


@pytest.mark.parametrize("dependency_id", UNSAFE_IDS)
def test_dependency_id_uses_the_same_identifier_contract(dependency_id):
    packet = _minimal_valid_packet()
    packet["dependency_ids"] = [dependency_id]
    result = validate_packet(_rehash(packet), dependency_states=None)
    assert not result["valid"]
    assert any(error["path"] == "/dependency_ids/0" for error in result["errors"])


@pytest.mark.parametrize("safe_id", ("a", "pkt-1", "packet.v1_test", "0" * 128))
def test_safe_identifier_grammar_is_accepted(safe_id):
    packet = _minimal_valid_packet()
    packet["packet_id"] = safe_id
    assert validate_packet(_rehash(packet), dependency_states=None)["valid"]


def test_packet_json_schema_uses_the_same_identifier_pattern():
    schema = json.loads((REPO / "schemas/harness/v1/packet.schema.json").read_text())
    expected = "^[a-z0-9][a-z0-9._-]{0,127}$"
    assert schema["properties"]["packet_id"]["pattern"] == expected
    assert schema["properties"]["dependency_ids"]["items"]["pattern"] == expected


def test_journal_json_schema_uses_the_same_identifier_pattern():
    schema = json.loads(
        (REPO / "schemas/harness/v1/journal-event.schema.json").read_text()
    )
    expected = "^[a-z0-9][a-z0-9._-]{0,127}$"
    assert schema["properties"]["packet_id"]["pattern"] == expected
    deps = schema["properties"]["payload"]["properties"]["packet"]["properties"]["dependency_ids"]
    assert deps["items"]["pattern"] == expected


def test_safe_state_path_module_exists_before_filesystem_use():
    assert importlib.util.find_spec("harness_coordinator.v1.paths") is not None


def test_safe_state_path_builds_identifier_derived_path_beneath_root(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path

    assert safe_state_path(
        str(tmp_path), "results", identifier="packet-1", suffix="attempt.json"
    ) == str(tmp_path / "results" / "packet-1" / "attempt.json")


@pytest.mark.parametrize("unsafe_id", UNSAFE_IDS)
def test_safe_state_path_rejects_unsafe_identifier_before_join(tmp_path, unsafe_id):
    from harness_coordinator.v1.paths import safe_state_path

    with pytest.raises(ValueError, match="unsafe harness identifier"):
        safe_state_path(str(tmp_path), "locks", identifier=unsafe_id, suffix="claim.json")


def test_safe_state_path_rejects_literal_segment_escape(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path

    with pytest.raises(ValueError, match="escapes state root"):
        safe_state_path(str(tmp_path), "..", identifier="packet-1", suffix="claim.json")


def test_safe_state_path_checks_the_complete_artifact_filename_symlink(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path

    terminal = tmp_path / "state" / "terminal"
    terminal.mkdir(parents=True)
    outside = tmp_path.parent / "outside-seal.json"
    outside.write_text("outside")
    (terminal / "dep-1.seal.json").symlink_to(outside)

    with pytest.raises(ValueError, match="escapes state root"):
        safe_state_path(
            str(tmp_path),
            "state",
            "terminal",
            identifier="dep-1",
            identifier_suffix=".seal.json",
        )


def _enrollment_event(packet_id, dependency_ids):
    payload = _make_packet_payload(packet_id=packet_id, enqueue_seq=1)
    payload["dependency_ids"] = dependency_ids
    return _make_event(
        seq=1,
        event_type="PACKET_ENROLLED",
        coordinator_id="coord-1",
        run_id="run-1",
        state_root_id="srid-1",
        prev_event=None,
        packet_id=packet_id,
        intent_id="enroll-1",
        to_state="BLOCKED" if dependency_ids else "READY",
        cause="enrollment",
        payload={
            "packet": payload,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": None,
        },
    )


def test_legacy_journal_rejects_unsafe_packet_id_before_fold():
    result = validate_journal_event(_enrollment_event("../../evil", []))
    assert not result["valid"]
    assert any(error["path"] == "/packet_id" for error in result["errors"])


def test_legacy_journal_rejects_unsafe_dependency_id_before_fold():
    result = validate_journal_event(_enrollment_event("packet-1", ["../../dep"]))
    assert not result["valid"]
    assert any(
        error["path"] == "/payload/packet/dependency_ids/0"
        for error in result["errors"]
    )


def test_direct_fold_rejects_unsafe_packet_id_even_without_read_journal(tmp_path):
    with pytest.raises(IntegrityError, match="unsafe harness identifier"):
        _fold_journal(str(tmp_path), [_enrollment_event("../../evil", [])])


def test_fold_refuses_exact_seal_symlink_outside_state_root(tmp_path):
    terminal = tmp_path / "state" / "terminal"
    terminal.mkdir(parents=True)
    outside = tmp_path.parent / "outside-fold-seal.json"
    outside.write_text("{}")
    (terminal / "packet-1.seal.json").symlink_to(outside)

    with pytest.raises(IntegrityError, match="escapes state root"):
        _fold_journal(str(tmp_path), [])


def test_reconciliation_reports_exact_seal_symlink_without_following_it(tmp_path):
    terminal = tmp_path / "state" / "terminal"
    terminal.mkdir(parents=True)
    outside = tmp_path.parent / "outside-reconcile-seal.json"
    outside.write_text("{}")
    (terminal / "packet-1.seal.json").symlink_to(outside)

    findings = _check_seal_consistency(str(tmp_path), {})
    assert findings == [
        {
            "packet_id": "packet-1",
            "code": "TERMINAL_SEAL_MISMATCH",
            "detail": "Seal path for packet-1 escapes state root",
        }
    ]


def test_sweep_run_id_cannot_escape_state_root(tmp_path):
    with pytest.raises(ValueError, match="unsafe harness identifier"):
        sweep_orphans(str(tmp_path), "../../../outside")


def test_reclaimed_lock_run_id_cannot_escape_state_root(tmp_path):
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    lock_path = lock_dir / "packet-1.lock.json"
    lock_path.write_text(json.dumps({"packet_id": "packet-1"}))
    with pytest.raises(ValueError, match="unsafe harness identifier"):
        reclaim_lock(str(lock_path), "../../../outside", "STALE_PRIOR_BOOT")
    assert lock_path.exists()


def test_torn_journal_run_id_cannot_escape_state_root(tmp_path):
    journal_path = tmp_path / "journal.ndjson"
    journal_path.write_bytes(b"broken")
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    with pytest.raises(ValueError, match="unsafe harness identifier"):
        _handle_torn_tail(
            str(tmp_path),
            str(journal_path),
            str(lock_dir / "journal.wlock"),
            [],
            b"broken",
            "coord-1",
            "../../../outside",
            "srid-1",
            "2026-08-10T00:00:00Z",
        )


def test_reconciliation_report_id_cannot_escape_state_root():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    event = _make_reconcile_event(
        1,
        "RUN_STARTED",
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": _run_payload(),
            "report": None,
        },
    )
    _write_journal(journal_path, [event])
    report = build_reconciliation_report(
        state_root,
        "srid-1",
        "coord-1",
        "run-1",
        "../../../outside",
        "2026-08-10T00:10:00Z",
    )
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    with pytest.raises(ValueError, match="unsafe harness identifier"):
        emit_reconciliation_report(
            state_root,
            journal_path,
            lock_path,
            events,
            report,
            "coord-1",
            "run-1",
            "srid-1",
            "2026-08-10T00:11:00Z",
        )


def test_reconciliation_artifact_path_is_relative_to_canonical_state_root():
    state_root = _new_state_root()
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    event = _make_reconcile_event(
        1,
        "RUN_STARTED",
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": _run_payload(),
            "report": None,
        },
    )
    _write_journal(journal_path, [event])
    report = build_reconciliation_report(
        state_root,
        "srid-1",
        "coord-1",
        "run-1",
        "report-1",
        "2026-08-10T00:10:00Z",
    )
    events, _ = read_journal(journal_path, state_root_id="srid-1")
    events = emit_reconciliation_report(
        state_root,
        journal_path,
        lock_path,
        events,
        report,
        "coord-1",
        "run-1",
        "srid-1",
        "2026-08-10T00:11:00Z",
    )
    emitted = [e for e in events if e["event_type"] == "RECONCILIATION_EMITTED"][-1]
    assert emitted["payload"]["report"]["report_path"] == "reports/report-1.json"


def test_atomic_replace_rejects_untrusted_temp_filename_components(tmp_path):
    target = tmp_path / "target.json"
    with pytest.raises(ValueError, match="unsafe harness identifier"):
        atomic_replace(
            str(target),
            b"safe",
            coordinator_id="../../../coordinator",
            nonce="../../../nonce",
        )
    assert not target.exists()
