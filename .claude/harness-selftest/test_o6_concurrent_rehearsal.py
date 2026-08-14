"""O6 — pre-overnight rehearsal.

Concurrent multi-packet rehearsal plus the five individually-fixtured
failure paths (quota fallback, recoverable worker failure, quarantine,
human-stop, crash/resume) that a real overnight run must survive, and one
combined morning report merging two disjoint lanes into a single
human-readable summary. Repo-only: no production DB writes, no network, no
provider SDKs. Every fixture here is a real, disposable, on-disk state root
driven through the real coordinator entry points (``run_once``/``run_night``)
-- nothing here mocks the safety mechanisms themselves, only the synthetic
worker/provider evidence they read.
"""

import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest

import harness_coordinator.v1.night_loop as night_loop_module
from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.coordinator import attempt_session_id, run_once
from harness_coordinator.v1.enroll import enroll_packets
from harness_coordinator.v1.invoke import WorkerAdapter
from harness_coordinator.v1.night_loop import combine_morning_reports, run_night
from harness_coordinator.v1.recovery import _fold_journal
from harness_coordinator.v1.review import resolve_review
from harness_coordinator.v1.seals_runtime import open_state_root

from test_night_loop import _adapters, _plan_for
from test_o3_p5_commissioning import (
    _commission_result,
    _registered_packet,
    _registered_worktrees,
    _review,
)
from test_o3_p5_review import TRUSTED_REVIEWER, _deposit, _verdict, _write_manifest, _write_trust_roots
from test_o5_budget_runtime import _default_routes
from test_o5_commissioning import (
    _child_grandchild_worker_code,
    _commission_scenario1,
    _enroll_real_packet_with_retry_limit,
    _process_group_probe_adapter,
)
from test_o5_coordinator_budgets import (
    COORDINATOR_ID,
    RUN_ID,
    STATE_ROOT_ID,
    T_AFTER,
    T_CLAIM,
    T_ENROLL,
    T_FINAL,
    _adapter_for,
    _attempt_outcome,
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


PYTHON_EXECUTABLE = os.path.realpath(sys.executable)
WORKER_O6 = str(Path(__file__).with_name("synthetic_o6_worker.py").resolve())


# ---------------------------------------------------------------------------
# Step 2.1 -- quota fallback (Kimi -> Sonnet-equivalent) reaches ACCEPTED
# ---------------------------------------------------------------------------


def test_o6_quota_fallback_kimi_to_sonnet_reaches_accepted(tmp_path):
    """Reuses O5 scenario 1's own commissioned setup verbatim
    (``_commission_scenario1``): a real bound plan pins a two-hop
    implementation route table, the primary hop (``opencode``/
    ``kimi-k2.7-code`` -- this codebase's synthetic stand-in for "Kimi via
    OpenCode Go") is durably recorded exhausted before the claim, and the
    real pre-claim gate (``budget_runtime.evaluate_preclaim``/
    ``select_capable_route``) genuinely selects the plan-pinned fallback hop
    (``openai``/``gpt-5.6-terra`` -- the same fallback identity O5's own
    fixtures already use as their canonical "Sonnet fallback" stand-in).
    This test drives the routing half through to a real terminal ACCEPTED,
    the way O6's rehearsal needs (O5's own ``test_fallback_routed_attempt_
    reaches_accepted`` proves the identical shape; this is the O6-scoped
    rehearsal instance of it).
    """
    base, state_root, packet, plan = _commission_scenario1(tmp_path, "o6-quota-fallback")

    started_event = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_STARTED")
    started_worker = started_event["payload"]["attempt"]["worker"]
    assert started_worker["provider"] == "openai"
    assert started_worker["model"] == "gpt-5.6-terra"
    # The accepted attempt's recorded identity is the fallback, never the
    # exhausted primary it was routed away from.
    assert (started_worker["provider"], started_worker["model"]) != ("opencode", "kimi-k2.7-code")
    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"

    session = attempt_session_id(RUN_ID, packet["packet_id"], 1)
    result = _commission_result(packet, session, attempt=1)
    result["worker"]["provider"] = "openai"
    result["worker"]["model"] = "gpt-5.6-terra"
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    _deposit(state_root, packet["packet_id"], 1, _review(_verdict(packet, result)))

    events = _events(state_root)
    folded, _ = _fold_journal(state_root, events)
    with open_state_root(state_root) as handle:
        outcome = resolve_review(
            state_root, STATE_ROOT_ID, events, folded, packet["packet_id"],
            COORDINATOR_ID, RUN_ID, _context(), T_AFTER, handle=handle)
    assert outcome["status"] == "recorded"
    assert outcome["verdict"] == "ACCEPT"
    assert outcome["next_state"] == "ACCEPTED"

    folded_after = _folded(state_root)
    assert folded_after[packet["packet_id"]]["state"] == "ACCEPTED"
    # The recorded accepted worker identity stays the fallback's, confirmed
    # against the durably folded attempt evidence, not merely the journal
    # event checked above.
    accepted_started = next(
        e for e in _events(state_root)
        if e["event_type"] == "ATTEMPT_STARTED" and e["packet_id"] == packet["packet_id"])
    accepted_worker = accepted_started["payload"]["attempt"]["worker"]
    assert (accepted_worker["provider"], accepted_worker["model"]) == ("openai", "gpt-5.6-terra")


# ---------------------------------------------------------------------------
# Step 2.2 -- a recoverable worker failure, then a successful retry
# ---------------------------------------------------------------------------


def test_o6_worker_failure_then_retry_succeeds(tmp_path):
    """One real enrolled packet. The first bounded attempt's worker is a
    minimal real failing command (a plain non-zero exit, no result ever
    written) -- classify_attempt's own INFRA_RETRYABLE rule 5 fires on
    exactly this shape (no raw_result bytes, a non-(0,None) exit code), the
    same real classification path O5's timeout/output-flood fixtures
    exercise, just from a different immediate cause. The second attempt uses
    a normal, ``_adapter_for``-style succeeding adapter. Two separate
    ``run_once`` calls with two different ``worker_adapters`` entries for
    the SAME packet_id, matching O5's own established two-call pattern for
    this shape (e.g. ``test_command_timeout_kills_process_group_on_both_
    bounded_attempts_then_quarantines``) rather than a single ``run_night``
    call, since a fixed ``worker_adapters`` mapping cannot vary by attempt
    number within one such call.

    This must read as RECOVERABLE failure -- exactly 2 ATTEMPT_STARTED
    events and a non-quarantined terminal/REVIEW state -- distinct from
    quarantine (Step 2.3), which needs the retry budget genuinely exhausted.
    """
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "o6-retry-then-succeed", ["p-retry"])
    packet = packets[0]
    plan = _build_plan(
        "plan-o6-retry", [_plan_row(packet, "implementation", attempt_limit=2, retry_limit=2)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    failing_adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c", "import sys; sys.exit(1)"), env={})
    first = run_once(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
        execution_plan=plan, worker_adapters={packet["packet_id"]: failing_adapter})
    assert first["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    finished1 = next(
        e for e in _events(state_root) if e["event_type"] == "ATTEMPT_FINISHED"
        and e["packet_id"] == packet["packet_id"]
        and e["payload"]["attempt"]["attempt"] == 1)
    assert finished1["cause"] == "infra_retry"
    assert finished1["to_state"] == "READY"

    marker = base / "markers.txt"
    succeeding_adapter = _adapter_for(packet, marker, attempt=2)
    second = run_once(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
        execution_plan=plan, worker_adapters={packet["packet_id"]: succeeding_adapter})
    assert second["status"] == "completed_attempt"

    assert _attempt_started_count(state_root, packet["packet_id"]) == 2
    final_state = _folded(state_root)[packet["packet_id"]]["state"]
    assert final_state == "REVIEW"
    assert final_state != "QUARANTINED"


# ---------------------------------------------------------------------------
# Step 2.3 -- bounded retries exhausted reaches QUARANTINED
# ---------------------------------------------------------------------------


def test_o6_bounded_retries_exhausted_reaches_quarantined(tmp_path):
    """Reuses O5 scenario 4's exact process-group-kill quarantine pattern
    (``_enroll_real_packet_with_retry_limit``, ``_child_grandchild_worker_
    code``, ``_process_group_probe_adapter``) verbatim, scoped to an
    O6-named packet: both bounded attempts time out and are killed at the
    process-group level, the retry budget is exhausted on the second, and
    the packet reaches terminal QUARANTINED.
    """
    base, state_root, packet = _enroll_real_packet_with_retry_limit(
        tmp_path, "o6-quarantine", "o6-p-quarantine", retry_limit=1)
    plan = _build_plan(
        "plan-o6-quarantine",
        [_plan_row(packet, "implementation", attempt_limit=2, retry_limit=1,
                   command_timeout_seconds=2, output_bytes=65536)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    code = _child_grandchild_worker_code()

    marker1 = base / "pg-marker-1.txt"
    first = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                     execution_plan=plan,
                     worker_adapters={packet["packet_id"]: _process_group_probe_adapter(code, marker1)})
    assert first["status"] == "completed_attempt"
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    marker2 = base / "pg-marker-2.txt"
    second = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan,
                      worker_adapters={packet["packet_id"]: _process_group_probe_adapter(code, marker2)})
    assert second["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 2
    assert _folded(state_root)[packet["packet_id"]]["state"] == "QUARANTINED"


# ---------------------------------------------------------------------------
# Step 2.4 -- a human-authority packet blocked before claim
# ---------------------------------------------------------------------------


def test_o6_human_authority_packet_blocked_before_claim(tmp_path):
    """Reuses O5 scenario 6's exact human-stop-category shape: a packet
    whose own ``human_stop_conditions`` intersect the bound plan's closed
    ``human_stop_categories`` vocabulary is blocked at the real pre-claim
    gate, before any claim -- zero ATTEMPT_STARTED events, ever, for this
    packet.
    """
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "o6-human-block", ["o6-p-blocked"],
        human_stop_conditions_by_id={"o6-p-blocked": ["deployment"]})
    packet = packets[0]
    plan = _build_plan(
        "plan-o6-human-block", [_plan_row(packet, "implementation")],
        {"implementation": _default_routes()["implementation"]},
        human_stop_categories=["deployment"])
    _bind(state_root, plan)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})

    assert result["status"] == "plan_stopped"
    assert result.get("stop_reason_code") == "HUMAN_AUTHORITY_REQUIRED"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    assert not any(e["event_type"] == "ATTEMPT_STARTED" for e in _events(state_root))
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "HUMAN_AUTHORITY_REQUIRED"


# ---------------------------------------------------------------------------
# Step 2.5 -- night_loop crash then resume, no duplicate claim
# ---------------------------------------------------------------------------


def test_o6_night_loop_crash_then_resume_no_duplicate_claim(tmp_path, monkeypatch):
    """Reuses ``test_night_loop.py``'s exact crash/resume monkeypatch
    pattern (``test_night_loop_crash_resume_does_not_reclaim_the_finished_
    packet``), scoped to two O6-named packets in one lane: the coordinator
    process dies immediately after the first packet's attempt durably
    completes; a fresh ``run_night`` call resumes and must claim the
    survivor exactly once, never reclaiming or duplicating the packet whose
    attempt already finished before the simulated crash.
    """
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "o6-crash-resume", ["o6-crash-a", "o6-crash-b"])
    plan = _plan_for("o6-crash", packets)
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

    assert _attempt_started_count(state_root, "o6-crash-a") == 1
    assert _attempt_started_count(state_root, "o6-crash-b") == 0

    monkeypatch.setattr(
        "harness_coordinator.v1.night_loop.run_once", real_run_once)
    resumed = run_night(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM, plan,
        worker_adapters=adapters,
    )

    assert resumed["status"] == "queue_drained"
    # Exactly one ATTEMPT_STARTED per packet after resume -- no duplicates.
    assert _attempt_started_count(state_root, "o6-crash-a") == 1
    assert _attempt_started_count(state_root, "o6-crash-b") == 1
    folded = _folded(state_root)
    assert folded["o6-crash-a"]["state"] == "REVIEW"
    assert folded["o6-crash-b"]["state"] == "REVIEW"


# ---------------------------------------------------------------------------
# Step 3 -- combine_morning_reports: pure merge, no coordinator run needed
# ---------------------------------------------------------------------------


def _fake_run_night_report(*, end_reason, packets, attention=(), all_invariants_passed=True,
                           iteration_count=2):
    """A small hand-built dict shaped exactly like a real ``run_night()``
    return value -- just enough of the real shape for ``combine_morning_
    reports`` to operate on, no coordinator run needed for this unit test.
    """
    return {
        "status": "queue_drained",
        "end_reason": end_reason,
        "now": "2026-08-13T00:00:00Z",
        "iterations": [],
        "iteration_count": iteration_count,
        "morning_report": {
            "generated_at": "2026-08-13T00:00:00Z",
            "end_reason": end_reason,
            "iterations": iteration_count,
            "what_happened": {"end_reason": end_reason, "iteration_count": iteration_count,
                              "iteration_statuses": []},
            "what_changed": {"attempted_packet_ids": [p["packet_id"] for p in packets],
                             "by_state": {}},
            "what_passed": {"all_invariants_passed": all_invariants_passed, "plan_totals": {}},
            "what_needs_attention": list(attention),
            "packets": packets,
            "reconciliation_report_id": "report-fake",
            "reconciliation_sha256": "f" * 64,
            "all_invariants_passed": all_invariants_passed,
        },
    }


def test_o6_combine_morning_reports_merges_two_lanes_into_one_report():
    lane_a = _fake_run_night_report(
        end_reason="queue_drained",
        packets=[{"packet_id": "ingest-1", "state": "ACCEPTED", "disposition": "accepted"}],
        attention=[{"packet_id": None, "code": "unverified_invariants", "detail": "note"}],
        all_invariants_passed=True,
    )
    lane_b = _fake_run_night_report(
        end_reason="queue_drained",
        packets=[
            {"packet_id": "appbuild-quarantine", "state": "QUARANTINED", "disposition": "quarantined"},
            {"packet_id": "appbuild-blocked", "state": "READY", "disposition": "blocked_human"},
        ],
        attention=[],
        all_invariants_passed=True,
    )

    combined = combine_morning_reports({"ingestion": lane_a, "app_build": lane_b})

    assert set(combined["lanes"]) == {"ingestion", "app_build"}
    assert combined["lanes"]["ingestion"] is lane_a
    assert combined["lanes"]["app_build"] is lane_b
    assert combined["all_invariants_passed"] is True

    attention = combined["what_needs_attention"]
    assert {"packet_id": None, "code": "unverified_invariants", "detail": "note",
            "lane": "ingestion"} in attention
    assert {"packet_id": "appbuild-quarantine", "code": "packet_quarantined",
            "detail": "appbuild-quarantine reached disposition 'quarantined'",
            "lane": "app_build"} in attention
    assert {"packet_id": "appbuild-blocked", "code": "packet_blocked_human",
            "detail": "appbuild-blocked reached disposition 'blocked_human'",
            "lane": "app_build"} in attention
    # Nothing invented for the cleanly accepted packet.
    assert not any(item.get("packet_id") == "ingest-1" for item in attention
                  if item.get("code") in {"packet_quarantined", "packet_blocked_human"})


def test_o6_combine_morning_reports_all_invariants_passed_is_and_across_lanes():
    clean = _fake_run_night_report(
        end_reason="queue_drained", packets=[], all_invariants_passed=True)
    dirty = _fake_run_night_report(
        end_reason="queue_drained", packets=[], all_invariants_passed=False)

    assert combine_morning_reports({"a": clean, "b": clean})["all_invariants_passed"] is True
    assert combine_morning_reports({"a": clean, "b": dirty})["all_invariants_passed"] is False


def test_o6_combine_morning_reports_rejects_empty_input():
    with pytest.raises(ValueError):
        combine_morning_reports({})


# ---------------------------------------------------------------------------
# Step 4 -- genuine OS-level concurrency proof
# ---------------------------------------------------------------------------


def _sleepy_o6_adapter(packet, run_id, sleep_seconds, attempt=1):
    """A WorkerAdapter pointed at synthetic_o6_worker.py with a real,
    controllable pre-completion sleep -- see synthetic_o6_worker.py's own
    module docstring for why the sleep duration travels inside the
    SYNTHETIC_RESULT payload (popped before the worker's own result is
    validated) rather than as a bare adapter env key.
    """
    session = attempt_session_id(run_id, packet["packet_id"], attempt)
    result = _commission_result(packet, session, attempt=attempt)
    result["sleep_seconds"] = sleep_seconds
    return WorkerAdapter(
        argv=(WORKER_O6,),
        env={"SYNTHETIC_RESULT": json.dumps(result, sort_keys=True, separators=(",", ":"))})


def _run_lane_in_process(state_root, coordinator_id, run_id, plan, adapter, now, barrier, queue):
    """Module-level (spawn-picklable -- macOS multiprocessing uses spawn,
    which requires a real importable top-level function, never a closure or
    lambda) target: one real claim+invoke cycle, synchronized on
    ``barrier`` so two independent OS processes call ``run_once`` at the
    same real instant.

    Real wall-clock timestamps (``time.time()``) are recorded immediately
    around the call -- these are what prove genuine process-level overlap.
    The RFC3339 ``now`` argument is the coordinator's own simulated clock
    and proves nothing about real concurrency by itself.
    """
    packet_id = plan["packets"][0]["packet_id"]
    context = {
        "coordinator_id": coordinator_id, "hostname": "synthetic-host",
        "boot_id": "synthetic-boot-%s" % coordinator_id, "pid": os.getpid(),
        "live_coordinator_ids": {coordinator_id}, "now": now,
    }
    barrier.wait()
    t_start = time.time()
    result = run_once(
        state_root, coordinator_id, run_id, context, now,
        execution_plan=plan, worker_adapters={packet_id: adapter},
    )
    t_end = time.time()
    queue.put({"lane": coordinator_id, "result": result, "t_start": t_start, "t_end": t_end})


def test_o6_two_lanes_run_concurrently_without_file_collision(tmp_path):
    """Two fully disjoint fixtures -- own git repo, branch, worktree, state
    root, MANIFEST, trust roots, one enrolled packet each -- driven through
    a single real claim+invoke cycle apiece in two genuinely separate OS
    processes, synchronized to fire at the same real instant. Proves the
    two lanes do not collide on any shared file or journal.
    """
    _base_a, state_root_a, packets_a = _enroll_real_packets(
        tmp_path, "concurrency-a", ["concurrency-lane-a"])
    _base_b, state_root_b, packets_b = _enroll_real_packets(
        tmp_path, "concurrency-b", ["concurrency-lane-b"])
    packet_a, packet_b = packets_a[0], packets_b[0]

    plan_a = _build_plan(
        "plan-concurrency-a", [_plan_row(packet_a, "implementation")],
        {"implementation": _default_routes()["implementation"]})
    plan_b = _build_plan(
        "plan-concurrency-b", [_plan_row(packet_b, "implementation")],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root_a, plan_a)
    _bind(state_root_b, plan_b)

    run_id_a, run_id_b = "run-concurrency-a", "run-concurrency-b"
    coordinator_a, coordinator_b = "coord-concurrency-a", "coord-concurrency-b"

    # 0.4s: comfortably larger than process-spawn jitter, small enough to
    # keep the test fast.
    adapter_a = _sleepy_o6_adapter(packet_a, run_id_a, 0.4)
    adapter_b = _sleepy_o6_adapter(packet_b, run_id_b, 0.4)

    barrier = multiprocessing.Barrier(2)
    queue: "multiprocessing.Queue[Dict[str, Any]]" = multiprocessing.Queue()
    proc_a = multiprocessing.Process(
        target=_run_lane_in_process,
        args=(state_root_a, coordinator_a, run_id_a, plan_a, adapter_a, T_CLAIM, barrier, queue))
    proc_b = multiprocessing.Process(
        target=_run_lane_in_process,
        args=(state_root_b, coordinator_b, run_id_b, plan_b, adapter_b, T_CLAIM, barrier, queue))
    proc_a.start()
    proc_b.start()
    proc_a.join(15)
    proc_b.join(15)
    assert not proc_a.is_alive()
    assert not proc_b.is_alive()

    outcomes = {}
    for _ in range(2):
        item = queue.get(timeout=5)
        outcomes[item["lane"]] = item
    outcome_a, outcome_b = outcomes[coordinator_a], outcomes[coordinator_b]

    assert outcome_a["result"]["status"] == "completed_attempt"
    assert outcome_b["result"]["status"] == "completed_attempt"

    # (b) Real wall-clock overlap -- actual OS processes, actual time.time()
    # readings, never the simulated RFC3339 clock.
    assert max(outcome_a["t_start"], outcome_b["t_start"]) < min(outcome_a["t_end"], outcome_b["t_end"])

    # (c) Each lane's worktree contains only its own expected new file.
    worktree_a = packet_a["worktree"]["path"]
    worktree_b = packet_b["worktree"]["path"]
    assert os.path.exists(os.path.join(worktree_a, "scripts", "concurrency-lane-a.py"))
    assert not os.path.exists(os.path.join(worktree_a, "scripts", "concurrency-lane-b.py"))
    assert os.path.exists(os.path.join(worktree_b, "scripts", "concurrency-lane-b.py"))
    assert not os.path.exists(os.path.join(worktree_b, "scripts", "concurrency-lane-a.py"))

    # (d) Each lane's own journal shows exactly one ATTEMPT_STARTED, for its
    # own packet only.
    assert _attempt_started_count(state_root_a, "concurrency-lane-a") == 1
    assert _attempt_started_count(state_root_b, "concurrency-lane-b") == 1
    assert not any(e["packet_id"] == "concurrency-lane-b" for e in _events(state_root_a))
    assert not any(e["packet_id"] == "concurrency-lane-a" for e in _events(state_root_b))


# ---------------------------------------------------------------------------
# Step 5 -- combined rehearsal: two lanes, five failure paths, one report
# ---------------------------------------------------------------------------


def _enroll_lane_b_packets(tmp_path, name):
    """Three packets, one state root, heterogeneous per-packet overrides:
    ``appbuild-quarantine`` needs a packet-level ``budgets.retry_limit``
    tight enough that two bounded timeout attempts exhaust it (this must be
    the PACKET's own O3-level retry_limit -- see ``_enroll_real_packet_
    with_retry_limit``'s own docstring for why the O5 plan row's retry_limit
    is a different field the budget-exhaustion check does not read);
    ``appbuild-blocked`` needs a ``human_stop_conditions`` override that
    intersects the plan's own ``human_stop_categories``. Same real,
    disposable, on-disk multi-packet enrollment shape as
    ``_enroll_real_packets``, just with per-packet overrides it does not
    support.
    """
    base = tmp_path / name
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    packet_ids = ["appbuild-retry", "appbuild-quarantine", "appbuild-blocked"]
    worktrees = _registered_worktrees(base, *packet_ids)
    packets = []
    for packet_id, worktree in zip(packet_ids, worktrees):
        packet = _registered_packet(packet_id, worktree)
        if packet_id == "appbuild-quarantine":
            packet["budgets"]["retry_limit"] = 1
            packet["sonnet_reassignment_allowed"] = False
        elif packet_id == "appbuild-blocked":
            packet["human_stop_conditions"] = ["deployment"]
        packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
        packets.append(packet)

    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, T_ENROLL, packets)
    return base, state_root, {p["packet_id"]: p for p in packets}


def _lane_context(coordinator_id, now):
    return {
        "coordinator_id": coordinator_id, "hostname": "synthetic-host",
        "boot_id": "synthetic-boot-%s" % coordinator_id, "pid": os.getpid(),
        "live_coordinator_ids": {coordinator_id}, "now": now,
    }


def _lane_a_ingestion_target(state_root, coordinator_id, run_id, packets, plan, adapters, now,
                             barrier, queue):
    """Lane A ('ingestion'): ``ingest-happy`` exercises crash/resume
    (Step 2.5's pattern -- pytest's ``monkeypatch`` fixture cannot cross
    into this child process, so the module attribute is patched by hand,
    same effect); ``ingest-fallback`` exercises the quota-fallback route
    (Step 2.1's pattern). Both packets share one plan/route table, so the
    durably-recorded primary-route exhaustion the caller records before
    this process starts routes BOTH packets through the plan-pinned
    fallback when claimed -- harmless for ``ingest-happy``, whose own
    distinguishing feature (crash/resume) is orthogonal to which route its
    single attempt used.

    Puts the FINAL ``run_night()`` return dict on ``queue``, tagged
    ``"ingestion"`` -- after resuming past the simulated crash AND
    resolving both packets to a real terminal ACCEPTED, so this lane's own
    ``all_invariants_passed`` can be True (a packet left resting in REVIEW
    is, correctly, an indeterminate disposition).
    """
    context = _lane_context(coordinator_id, now)
    barrier.wait()

    seen = {"completed": 0}

    def crash_after_first_attempt(*args, **kwargs):
        outcome = run_once(*args, **kwargs)
        if outcome.get("status") == "completed_attempt":
            seen["completed"] += 1
            if seen["completed"] == 1:
                raise RuntimeError("simulated coordinator crash")
        return outcome

    night_loop_module.run_once = crash_after_first_attempt
    try:
        night_loop_module.run_night(
            state_root, coordinator_id, run_id, context, now, plan, worker_adapters=adapters)
    except RuntimeError:
        pass
    finally:
        night_loop_module.run_once = run_once

    resumed = night_loop_module.run_night(
        state_root, coordinator_id, run_id, context, now, plan, worker_adapters=adapters)
    assert resumed["status"] == "queue_drained"

    for packet in packets:
        packet_id = packet["packet_id"]
        events = _events(state_root)
        started = next(
            e for e in events if e["event_type"] == "ATTEMPT_STARTED" and e["packet_id"] == packet_id)
        attempt = started["payload"]["attempt"]["attempt"]
        worker_identity = started["payload"]["attempt"]["worker"]
        session = attempt_session_id(run_id, packet_id, attempt)
        result = _commission_result(packet, session, attempt=attempt)
        result["worker"]["provider"] = worker_identity["provider"]
        result["worker"]["model"] = worker_identity["model"]
        result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
        _deposit(state_root, packet_id, attempt, _review(_verdict(packet, result)))

        events = _events(state_root)
        folded, _ = _fold_journal(state_root, events)
        with open_state_root(state_root) as handle:
            outcome = resolve_review(
                state_root, STATE_ROOT_ID, events, folded, packet_id,
                coordinator_id, run_id, context, now, handle=handle)
        assert outcome["status"] == "recorded"
        assert outcome["next_state"] == "ACCEPTED"

    final = night_loop_module.run_night(
        state_root, coordinator_id, run_id, context, now, plan, worker_adapters=adapters)
    queue.put({"lane": "ingestion", "report": final})


_RETRY_ATTEMPT_BRANCH_CODE = (
    "import json, os, sys\n"
    "if os.environ.get('HARNESS_ATTEMPT') == '1':\n"
    "    sys.exit(1)\n"
    "result = json.loads(os.environ['SYNTHETIC_RESULT'])\n"
    # Attempt 2 must physically write the file its own result claims to
    # have added (matching synthetic_p5_worker.py/synthetic_o6_worker.py's
    # own contract) -- omitting this leaves the worker's changed_files claim
    # unbacked by any real change, which O4 postflight correctly treats as
    # an authority violation (HUMAN_REQUIRED), not a harmless no-op.
    "for changed in result.get('changed_files', []):\n"
    "    path = changed['path']\n"
    "    os.makedirs(os.path.dirname(path), exist_ok=True)\n"
    "    with open(path, 'wb') as stream:\n"
    "        stream.write(('synthetic %s %s\\n' % (result['packet_id'], result['attempt'])).encode('utf-8'))\n"
    "marker = os.environ.get('SYNTHETIC_MARKER_PATH')\n"
    "if marker:\n"
    "    with open(marker, 'a') as handle:\n"
    "        handle.write(result['packet_id'] + ':' + str(result['attempt']) + chr(10))\n"
    "with os.fdopen(os.dup(int(os.environ['HARNESS_RESULT_FD'])), 'w') as stream:\n"
    "    json.dump(result, stream, sort_keys=True, separators=(',', ':'))\n"
)


def _lane_b_appbuild_target(state_root, coordinator_id, run_id, packets, plan, adapters, now,
                            barrier, queue):
    """Lane B ('app_build'): ``appbuild-retry`` exercises a recoverable
    worker failure then a successful retry (Step 2.2's pattern -- via the
    HARNESS_ATTEMPT-branching inline worker ``adapters["appbuild-retry"]``
    already carries, since one ``run_night`` call keeps ONE fixed adapter
    per packet_id for every attempt, unlike Step 2.2's own standalone test,
    which drives two separate ``run_once`` calls with two different
    adapters); ``appbuild-quarantine`` exercises bounded-retries-exhausted
    quarantine (Step 2.3's pattern); ``appbuild-blocked`` exercises
    human-authority block before claim (Step 2.4's pattern). No crash
    injection in this lane.

    Puts the FINAL ``run_night()`` return dict on ``queue``, tagged
    ``"app_build"`` -- after resolving ``appbuild-retry`` to a real terminal
    ACCEPTED (quarantined/blocked_human are already closed dispositions
    with no review step needed).
    """
    context = _lane_context(coordinator_id, now)
    barrier.wait()

    first = night_loop_module.run_night(
        state_root, coordinator_id, run_id, context, now, plan, worker_adapters=adapters)
    assert first["status"] in ("queue_drained", "plan_complete")

    retry_packet = next(p for p in packets if p["packet_id"] == "appbuild-retry")
    events = _events(state_root)
    started = next(
        e for e in events if e["event_type"] == "ATTEMPT_STARTED"
        and e["packet_id"] == "appbuild-retry" and e["payload"]["attempt"]["attempt"] == 2)
    worker_identity = started["payload"]["attempt"]["worker"]
    session = attempt_session_id(run_id, "appbuild-retry", 2)
    result = _commission_result(retry_packet, session, attempt=2)
    result["worker"]["provider"] = worker_identity["provider"]
    result["worker"]["model"] = worker_identity["model"]
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    _deposit(state_root, "appbuild-retry", 2, _review(_verdict(retry_packet, result)))

    events = _events(state_root)
    folded, _ = _fold_journal(state_root, events)
    with open_state_root(state_root) as handle:
        outcome = resolve_review(
            state_root, STATE_ROOT_ID, events, folded, "appbuild-retry",
            coordinator_id, run_id, context, now, handle=handle)
    assert outcome["status"] == "recorded"
    assert outcome["next_state"] == "ACCEPTED"

    final = night_loop_module.run_night(
        state_root, coordinator_id, run_id, context, now, plan, worker_adapters=adapters)
    queue.put({"lane": "app_build", "report": final})


def test_o6_combined_two_lane_night_reconciles_to_one_morning_report(tmp_path):
    """Lane A (ingestion): ``ingest-happy`` (crash/resume) + ``ingest-
    fallback`` (quota fallback). Lane B (app_build): ``appbuild-retry``
    (recoverable failure then success), ``appbuild-quarantine`` (bounded
    retries exhausted), ``appbuild-blocked`` (human-authority block). Both
    lanes run their own ``run_night`` in a genuinely separate OS process,
    synchronized on one ``Barrier(2)``, each in its own disjoint state
    root/plan. The parent combines both FINAL reports into one via
    ``night_loop.combine_morning_reports`` and asserts real expected values.
    """
    # ---- Lane A: ingestion ----
    base_a, state_root_a, packets_a = _enroll_real_packets(
        tmp_path, "o6-combined-ingestion", ["ingest-happy", "ingest-fallback"])
    plan_a = _build_plan(
        "plan-o6-combined-ingestion",
        [_plan_row(p, "implementation") for p in packets_a],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root_a, plan_a)
    _record_capacity(state_root_a, "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED")
    marker_a = base_a / "markers.txt"
    adapters_a = {
        p["packet_id"]: _adapter_for(p, marker_a, provider="openai", model="gpt-5.6-terra")
        for p in packets_a
    }

    # ---- Lane B: app_build ----
    base_b, state_root_b, packets_by_id_b = _enroll_lane_b_packets(tmp_path, "o6-combined-appbuild")
    packets_b = list(packets_by_id_b.values())
    plan_b = _build_plan(
        "plan-o6-combined-appbuild",
        [
            _plan_row(packets_by_id_b["appbuild-retry"], "implementation",
                     attempt_limit=2, retry_limit=2),
            _plan_row(packets_by_id_b["appbuild-quarantine"], "implementation",
                     attempt_limit=2, retry_limit=1, command_timeout_seconds=2, output_bytes=65536),
            _plan_row(packets_by_id_b["appbuild-blocked"], "implementation"),
        ],
        {"implementation": _default_routes()["implementation"]},
        human_stop_categories=["deployment"],
    )
    _bind(state_root_b, plan_b)
    marker_b = base_b / "markers.txt"
    retry_result_attempt2 = _commission_result(
        packets_by_id_b["appbuild-retry"], attempt_session_id(RUN_ID, "appbuild-retry", 2), attempt=2)
    adapters_b = {
        "appbuild-retry": WorkerAdapter(
            argv=(PYTHON_EXECUTABLE, "-c", _RETRY_ATTEMPT_BRANCH_CODE),
            env={"SYNTHETIC_RESULT": json.dumps(
                    retry_result_attempt2, sort_keys=True, separators=(",", ":")),
                 "SYNTHETIC_MARKER_PATH": str(marker_b)}),
        "appbuild-quarantine": _process_group_probe_adapter(
            _child_grandchild_worker_code(), marker_b),
        "appbuild-blocked": _adapter_for(packets_by_id_b["appbuild-blocked"], marker_b),
    }

    barrier = multiprocessing.Barrier(2)
    queue: "multiprocessing.Queue[Dict[str, Any]]" = multiprocessing.Queue()
    proc_a = multiprocessing.Process(
        target=_lane_a_ingestion_target,
        args=(state_root_a, COORDINATOR_ID, RUN_ID, packets_a, plan_a, adapters_a, T_CLAIM,
              barrier, queue))
    proc_b = multiprocessing.Process(
        target=_lane_b_appbuild_target,
        args=(state_root_b, COORDINATOR_ID, RUN_ID, packets_b, plan_b, adapters_b, T_CLAIM,
              barrier, queue))
    proc_a.start()
    proc_b.start()
    proc_a.join(60)
    proc_b.join(60)
    assert not proc_a.is_alive()
    assert not proc_b.is_alive()

    reports = {}
    for _ in range(2):
        item = queue.get(timeout=10)
        reports[item["lane"]] = item["report"]
    assert set(reports) == {"ingestion", "app_build"}

    # Real expected values, per lane, before combining.
    assert reports["ingestion"]["morning_report"]["all_invariants_passed"] is True
    assert reports["app_build"]["morning_report"]["all_invariants_passed"] is True

    combined = combine_morning_reports(reports)
    # Quarantine and blocked_human are correct, expected dispositions here,
    # not integrity violations -- both lanes, and the combined report,
    # genuinely pass.
    assert combined["all_invariants_passed"] is True

    dispositions = {
        row["packet_id"]: row["disposition"]
        for lane_report in reports.values()
        for row in lane_report["morning_report"]["packets"]
    }
    assert dispositions["ingest-happy"] == "accepted"
    assert dispositions["ingest-fallback"] == "accepted"
    assert dispositions["appbuild-retry"] == "accepted"
    assert dispositions["appbuild-quarantine"] == "quarantined"
    assert dispositions["appbuild-blocked"] == "blocked_human"

    attention_by_packet = {item.get("packet_id"): item for item in combined["what_needs_attention"]}
    assert attention_by_packet["appbuild-quarantine"]["lane"] == "app_build"
    assert attention_by_packet["appbuild-quarantine"]["code"] == "packet_quarantined"
    assert attention_by_packet["appbuild-blocked"]["lane"] == "app_build"
    assert attention_by_packet["appbuild-blocked"]["code"] == "packet_blocked_human"

    # No duplicate ATTEMPT_STARTED anywhere after the crash/resume.
    assert _attempt_started_count(state_root_a, "ingest-happy") == 1
    assert _attempt_started_count(state_root_a, "ingest-fallback") == 1
    assert _attempt_started_count(state_root_b, "appbuild-retry") == 2
    assert _attempt_started_count(state_root_b, "appbuild-quarantine") == 2
    assert _attempt_started_count(state_root_b, "appbuild-blocked") == 0
