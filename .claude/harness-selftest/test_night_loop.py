"""Coordinator night driver — synthetic path only.

Proves the loop over the commissioned ``run_once`` runner: a full simulated
night, crash/resume without duplicate claims, provider outage without
spinning, and a clean operator/morning stop. Real providers are out of
scope.
"""

import os

import pytest

from harness_coordinator.v1.coordinator import run_once
from harness_coordinator.v1.night_loop import run_night
from test_o5_budget_runtime import _default_routes
from test_o5_coordinator_budgets import (
    COORDINATOR_ID,
    RUN_ID,
    T_CLAIM,
    _adapter_for,
    _attempt_started_count,
    _bind,
    _build_plan,
    _context,
    _enroll_real_packets,
    _events,
    _folded,
    _packet_paused_events,
    _plan_row,
    _record_capacity,
)


def _plan_for(name, packets, capability="implementation", wall_clock=3600):
    rows = [_plan_row(packet, capability) for packet in packets]
    return _build_plan(
        "plan-night-%s" % name,
        rows,
        {capability: _default_routes()[capability]},
        wall_clock=wall_clock,
    )


def _adapters(packets, marker):
    return {
        packet["packet_id"]: _adapter_for(packet, marker)
        for packet in packets
    }


def test_night_loop_drives_simulated_workers_and_emits_a_morning_report(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "night-happy", ["p1", "p2"])
    plan = _plan_for("happy", packets)
    _bind(state_root, plan)
    marker = base / "markers.txt"
    result = run_night(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
        worker_adapters=_adapters(packets, marker),
    )

    assert result["status"] == "queue_drained"
    assert result["iteration_count"] >= 2
    assert {item["packet_id"] for item in result["iterations"]
            if item["status"] == "completed_attempt"} == {"p1", "p2"}
    assert _attempt_started_count(state_root, "p1") == 1
    assert _attempt_started_count(state_root, "p2") == 1
    folded = _folded(state_root)
    assert folded["p1"]["state"] == "REVIEW"
    assert folded["p2"]["state"] == "REVIEW"

    report = result["morning_report"]
    assert report["what_happened"]["end_reason"] == "queue_drained"
    assert report["what_happened"]["iteration_count"] == result["iteration_count"]
    assert set(report["what_changed"]["attempted_packet_ids"]) == {"p1", "p2"}
    assert report["what_changed"]["by_state"]["REVIEW"] == 2
    # Synthetic workers stop at REVIEW. No verdict was deposited, so the
    # commissioned reconciliation correctly leaves disposition open and
    # flags the pending reviews as attention -- that is the morning report
    # doing its job, not a driver defect.
    attention_codes = {item["code"] for item in report["what_needs_attention"]}
    assert "plan_disposition_indeterminate" in attention_codes
    assert report["what_passed"]["plan_totals"]["attempted"] == 2
    assert report["what_passed"]["plan_totals"]["accepted"] == 0
    assert marker.exists()


def test_night_loop_crash_resume_does_not_reclaim_the_finished_packet(tmp_path, monkeypatch):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "night-crash", ["p1", "p2"])
    plan = _plan_for("crash", packets)
    _bind(state_root, plan)
    marker = base / "markers.txt"
    adapters = _adapters(packets, marker)

    real_run_once = run_once
    seen = {"completed": 0}

    def crash_after_first_attempt(*args, **kwargs):
        outcome = real_run_once(*args, **kwargs)
        if outcome.get("status") == "completed_attempt":
            seen["completed"] += 1
            if seen["completed"] == 1:
                raise RuntimeError("simulated coordinator crash")
        return outcome

    monkeypatch.setattr(
        "harness_coordinator.v1.night_loop.run_once", crash_after_first_attempt)

    with pytest.raises(RuntimeError, match="simulated coordinator crash"):
        run_night(
            state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
            worker_adapters=adapters,
        )

    assert _attempt_started_count(state_root, "p1") == 1
    assert _attempt_started_count(state_root, "p2") == 0

    monkeypatch.setattr(
        "harness_coordinator.v1.night_loop.run_once", real_run_once)
    resumed = run_night(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
        worker_adapters=adapters,
    )

    assert resumed["status"] == "queue_drained"
    assert _attempt_started_count(state_root, "p1") == 1
    assert _attempt_started_count(state_root, "p2") == 1
    folded = _folded(state_root)
    assert folded["p1"]["open_attempt"] is None
    assert folded["p2"]["open_attempt"] is None
    assert folded["p1"]["state"] == "REVIEW"
    assert folded["p2"]["state"] == "REVIEW"


def test_night_loop_provider_outage_does_not_spin(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "night-outage", ["design-1"])
    packet = packets[0]
    plan = _plan_for("outage", packets, capability="design_judgment")
    _bind(state_root, plan)
    _record_capacity(state_root, "anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    result = run_night(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
        worker_adapters={packet["packet_id"]: _adapter_for(packet, marker)},
        max_iterations=8,
    )

    assert result["status"] in {"provider_unavailable", "graceful_stopped"}
    assert result["iteration_count"] <= 3
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    assert len(_packet_paused_events(state_root, packet["packet_id"])) == 1
    assert not any(
        event["event_type"] == "ATTEMPT_STARTED"
        for event in _events(state_root)
    )
    report = result["morning_report"]
    assert report["what_changed"]["by_state"]["READY"] == 1
    assert report["what_passed"]["all_invariants_passed"] is True


def test_night_loop_clean_stop_finishes_open_work_and_claims_nothing_more(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "night-stop", ["p1", "p2"])
    plan = _plan_for("stop", packets)
    _bind(state_root, plan)
    marker = base / "markers.txt"
    claimed = {"count": 0}

    def stop_after_first_claim():
        return claimed["count"] >= 1

    real_run_once = run_once

    def count_claims(*args, **kwargs):
        outcome = real_run_once(*args, **kwargs)
        if outcome.get("status") == "completed_attempt":
            claimed["count"] += 1
        return outcome

    # Patch inside night_loop so the driver sees the same wrapper it calls.
    import harness_coordinator.v1.night_loop as night_loop
    original = night_loop.run_once
    night_loop.run_once = count_claims
    try:
        result = run_night(
            state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
            worker_adapters=_adapters(packets, marker),
            stop_check=stop_after_first_claim,
        )
    finally:
        night_loop.run_once = original

    assert result["status"] == "graceful_stopped"
    assert result["end_reason"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert _attempt_started_count(state_root, "p1") == 1
    assert _attempt_started_count(state_root, "p2") == 0
    folded = _folded(state_root)
    assert folded["p1"]["state"] == "REVIEW"
    assert folded["p2"]["state"] == "READY"
    types = [event["event_type"] for event in _events(state_root)]
    assert "GRACEFUL_STOP_REQUESTED" in types
    assert "GRACEFUL_STOP_EFFECTIVE" in types
    assert types.index("GRACEFUL_STOP_REQUESTED") < types.index("GRACEFUL_STOP_EFFECTIVE")
    report = result["morning_report"]
    assert report["what_happened"]["end_reason"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert report["what_changed"]["by_state"]["READY"] == 1
    assert report["what_changed"]["by_state"]["REVIEW"] == 1


def test_night_loop_morning_cutoff_requests_stop_before_any_claim(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "night-morning", ["p1", "p2"])
    plan = _plan_for("morning", packets)
    _bind(state_root, plan)
    marker = base / "markers.txt"
    result = run_night(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
        worker_adapters=_adapters(packets, marker),
        morning_at=T_CLAIM,
    )

    assert result["status"] == "graceful_stopped"
    assert result["end_reason"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert _attempt_started_count(state_root, "p1") == 0
    assert _attempt_started_count(state_root, "p2") == 0
    report = result["morning_report"]
    assert "what_happened" in report
    assert "what_changed" in report
    assert "what_passed" in report
    assert "what_needs_attention" in report
    assert _folded(state_root)["p1"]["state"] == "READY"
    assert _folded(state_root)["p2"]["state"] == "READY"
