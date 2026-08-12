"""O5 Task 4: coordinator plan scope, fallback, pause, and human gates.

Wires ``budget_runtime.evaluate_preclaim``/``select_capable_route`` (Task 2,
already independently tested against pure inputs in
``test_o5_budget_runtime.py``) into the coordinator's real pre-claim path,
and closes the plan-scope enrollment gap left open by Task 1's own tests
(which exercise the reactive ``_fold_journal`` check by hand-building
journal events, never through ``enroll_packets`` itself).

Every fixture here is a real, disposable, on-disk state root -- enrolled
packets, a real bound plan, a real journal -- driven through the real
``run_once``/``enroll_packets`` entry points, per this suite's own
no-mocking-the-safety-mechanism discipline: nothing here mocks
``evaluate_preclaim``/``select_capable_route`` themselves, only the
provider/capacity EVIDENCE they read is synthetic.
"""

import json
import os

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.execution_plan import bind_execution_plan
from harness_coordinator.v1.budget_runtime import budget_event_payload
from harness_coordinator.v1.coordinator import attempt_session_id, claim_and_start_attempt, run_once
from harness_coordinator.v1.enroll import enroll_packets
from harness_coordinator.v1.invoke import WorkerAdapter
from harness_coordinator.v1.recovery import (
    IntegrityError, _fold_journal, _make_event,
    graceful_stop_state, make_graceful_stop_effective, request_graceful_stop,
)
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import append_journal, read_journal

from test_o3_p5_commissioning import (
    _commission_result, _registered_packet, _registered_worktrees, _review,
)
from test_o3_p5_review import TRUSTED_REVIEWER, _deposit, _verdict, _write_manifest, _write_trust_roots
from test_o5_budget_runtime import _default_routes, _route
from test_o5_hard_stops import WORKER


COORDINATOR_ID = "coord-o5-t4"
RUN_ID = "run-o5-t4"
STATE_ROOT_ID = "srid-o5-t4"

T_ENROLL = "2026-08-12T00:00:00Z"
T_BIND = "2026-08-12T00:05:00Z"
T_OBSERVE = "2026-08-12T00:10:00Z"
T_CLAIM = "2026-08-12T00:15:00Z"
T_AFTER = "2026-08-12T00:20:00Z"
T_FINAL = "2026-08-12T00:25:00Z"
T_MUCH_LATER = "2026-08-12T00:30:00Z"

EVIDENCE_SHA = "e" * 64


# --------------------------------------------------------------------------
# Shared fixtures
# --------------------------------------------------------------------------


def _context(coordinator_id=COORDINATOR_ID):
    return {"coordinator_id": coordinator_id, "hostname": "synthetic-host",
            "boot_id": "synthetic-boot", "pid": os.getpid(),
            "live_coordinator_ids": {coordinator_id}, "now": T_CLAIM}


def _plan_row(packet, capability_class, attempt_limit=2, retry_limit=1,
              revision_limit=1, command_timeout_seconds=45, output_bytes=65536,
              turn_limit=12):
    return {
        "packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
        "dependencies": list(packet.get("dependency_ids") or []),
        "capability_class": capability_class,
        "budgets": {
            "attempt_limit": attempt_limit, "retry_limit": retry_limit,
            "revision_limit": revision_limit, "turn_limit": turn_limit,
            "command_timeout_seconds": command_timeout_seconds, "output_bytes": output_bytes,
        },
    }


def _build_plan(plan_id, rows, routes, human_stop_categories=None, wall_clock=3600):
    plan = {
        "schema_version": 1, "plan_id": plan_id, "plan_sha256": "",
        "packets": rows, "routes": routes,
        "provider_backoff": {"max_retries": 3, "base_delay_seconds": 30, "max_delay_seconds": 300},
        "wall_clock_safety_seconds": wall_clock,
        "human_stop_categories": human_stop_categories or ["deployment"],
    }
    plan["plan_sha256"] = compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))
    return plan


def _enroll_real_packets(tmp_path, name, packet_ids, human_stop_conditions_by_id=None,
                         at=T_ENROLL):
    """Real registered packets in real disposable Git worktrees, enrolled."""
    base = tmp_path / name
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    worktrees = _registered_worktrees(base, *packet_ids)
    packets = []
    for packet_id, worktree in zip(packet_ids, worktrees):
        packet = _registered_packet(packet_id, worktree)
        override = (human_stop_conditions_by_id or {}).get(packet_id)
        if override is not None:
            packet["human_stop_conditions"] = list(override)
            packet["packet_sha256"] = compute_sha256(
                canonical_bytes(packet, omit={"packet_sha256"}))
        packets.append(packet)

    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, at, packets)
    return base, state_root, packets


def _bind(state_root, plan, at=T_BIND):
    with open_state_root(state_root) as handle:
        return bind_execution_plan(handle, canonical_bytes(plan), COORDINATOR_ID, RUN_ID, at)


def _adapter_for(packet, marker, provider=None, model=None, attempt=1):
    session = attempt_session_id(RUN_ID, packet["packet_id"], attempt)
    result = _commission_result(packet, session, attempt=attempt)
    if provider is not None:
        result["worker"]["provider"] = provider
    if model is not None:
        result["worker"]["model"] = model
    if provider is not None or model is not None:
        result["result_sha256"] = compute_sha256(
            canonical_bytes(result, omit={"result_sha256"}))
    return WorkerAdapter(
        argv=(WORKER,),
        env={"SYNTHETIC_RESULT": json.dumps(result, sort_keys=True, separators=(",", ":")),
             "SYNTHETIC_MARKER_PATH": str(marker)})


def _record_capacity(state_root, provider, model_id, state, observed_at=T_OBSERVE,
                     reset_at=None, evidence_sha256=EVIDENCE_SHA):
    """Durably append a real ``PROVIDER_CAPACITY_RECORDED`` event.

    Simulates capacity already having been authenticated and journaled by
    the (not-yet-built, out of Task 4's scope) live provider-observation
    path -- Task 4 only CONSUMES this evidence via ``evaluate_preclaim``/
    ``select_capable_route``, it does not produce it. See the report's
    escalated-ambiguity note on why Task 4 itself never constructs a
    ``PROVIDER_CAPACITY_RECORDED``/``PROVIDER_BACKOFF_SCHEDULED`` event.
    """
    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=STATE_ROOT_ID)
    assert torn is None
    payload = budget_event_payload("PROVIDER_CAPACITY_RECORDED", {
        "provider": provider, "model_id": model_id, "state": state,
        "observed_at": observed_at, "reset_at": reset_at,
        "evidence_sha256": evidence_sha256,
    })
    previous = events[-1] if events else None
    event = _make_event((previous["seq"] + 1) if previous else 1,
                        "PROVIDER_CAPACITY_RECORDED", COORDINATOR_ID, RUN_ID,
                        STATE_ROOT_ID, previous, observed_at, payload=payload)
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"),
                   expected_head=previous)
    return event


def _events(state_root):
    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=STATE_ROOT_ID)
    assert torn is None
    return events


def _folded(state_root):
    events = _events(state_root)
    folded, _ = _fold_journal(state_root, events)
    return folded


def _attempt_started_count(state_root, packet_id):
    return len([e for e in _events(state_root)
               if e["event_type"] == "ATTEMPT_STARTED" and e["packet_id"] == packet_id])


def _packet_paused_events(state_root, packet_id):
    return [e for e in _events(state_root)
           if e["event_type"] == "PACKET_PAUSED" and e["packet_id"] == packet_id]


def _attempt_outcome(state_root, packet_id, attempt):
    """The durable ``attempt_outcome.json`` record for one attempt."""
    path = os.path.join(state_root, "results", packet_id, str(attempt), "attempt_outcome.json")
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _worker_result(state_root, packet_id, attempt):
    """The actual synthetic worker's own self-reported result -- proof of
    what the invocation genuinely used, independent of what the journal's
    ATTEMPT_STARTED merely decided beforehand."""
    path = os.path.join(state_root, "results", packet_id, str(attempt), "worker-result.json")
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Step 1 -- plan scope at enrollment, plan completion, last-budget contention
# --------------------------------------------------------------------------


def test_packet_outside_bound_plan_cannot_enroll(tmp_path):
    base, state_root, packets = _enroll_real_packets(tmp_path, "outside", ["p1"])
    plan = _build_plan("plan-outside", [_plan_row(packets[0], "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    foreign_base = tmp_path / "outside_foreign"
    foreign_base.mkdir()
    foreign_worktree = _registered_worktrees(foreign_base, "p2")[0]
    foreign = _registered_packet("p2", foreign_worktree)

    with pytest.raises(IntegrityError) as caught:
        enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, T_OBSERVE, [foreign])
    assert caught.value.code == "PLAN_SCOPE_PACKET_OUTSIDE_PLAN"

    # The rejected attempt must never have reached the durable journal.
    events = _events(state_root)
    assert not any(e["event_type"] == "PACKET_ENROLLED" and e["packet_id"] == "p2"
                  for e in events)
    folded, _ = _fold_journal(state_root, events)
    assert "p2" not in folded


def test_in_plan_packet_still_enrolls_normally_around_the_new_gate(tmp_path):
    """The new preflight gate must not block the ordinary, legitimate case,
    in either the enroll-then-bind or bind-then-enroll order Task 1 already
    guarantees are both legal."""
    base = tmp_path / "inside"
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    worktree = _registered_worktrees(base, "p1")[0]
    packet = _registered_packet("p1", worktree)
    plan = _build_plan("plan-inside", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, T_ENROLL, [packet])
    _bind(state_root, plan)
    assert _folded(state_root)["p1"]["state"] == "READY"

    base2 = tmp_path / "inside2"
    base2.mkdir()
    state_root2 = os.path.realpath(str(base2 / "state"))
    os.makedirs(os.path.join(state_root2, "locks"))
    _write_manifest(state_root2, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root2, sessions=(TRUSTED_REVIEWER,))
    worktree2 = _registered_worktrees(base2, "p1")[0]
    packet2 = _registered_packet("p1", worktree2)
    plan2 = _build_plan("plan-inside2", [_plan_row(packet2, "implementation")],
                        {"implementation": _default_routes()["implementation"]})
    _bind(state_root2, plan2)
    enroll_packets(state_root2, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, T_OBSERVE, [packet2])
    assert _folded(state_root2)["p1"]["state"] == "READY"


OLDER_RUN_ID = "run-o5-t4-older"


def test_packet_from_an_earlier_unbound_run_is_never_selected_under_a_later_plan(tmp_path):
    """Root-cause regression for the ``PACKET_PAUSED capability_class: null``
    corruption bug.

    ``_fold_journal``'s ``EXECUTION_PLAN_BOUND`` retro-check only
    cross-checks packets whose OWN ``run_id`` matches the binding event's
    ``run_id`` (see ``_fold_journal``, the ``for known_packet in
    packets.values(): if known_packet.get("run_id") == run_id`` loop). A
    packet enrolled under an EARLIER run -- before any plan was ever bound,
    so ``enroll.py``'s own preflight plan-scope gate was exempt at
    enrollment time too -- is invisible to that retro-check when a
    DIFFERENT, later run's plan binds and does not include it. Before this
    fix, ``select_next`` would still offer the old packet (it is READY,
    unclaimed, and otherwise perfectly ordinary), ``_plan_packet_row`` would
    return ``None`` for it, and ``_persist_budget_decision`` would durably
    write a ``PACKET_PAUSED`` event with ``capability_class: null`` --
    contract-invalid, and ``read_journal`` refuses to load it ever again.
    The fix closes this at selection itself
    (``scheduler.select_next``'s new ``plan`` parameter): the old packet is
    never selected, so it never even reaches a budget decision.
    """
    base, state_root, packets = _enroll_real_packets(tmp_path, "older-run", ["old-p1"])
    old_packet = packets[0]
    from harness_coordinator.v1.recovery import bound_execution_plan_for_run
    assert bound_execution_plan_for_run(state_root, _events(state_root), RUN_ID) is None

    # A second packet, enrolled under a DIFFERENT run -- the run whose plan
    # will actually bind and be exercised by this test. A separate base
    # directory, matching ``test_packet_outside_bound_plan_cannot_enroll``'s
    # own ``foreign_base`` pattern: ``_registered_worktrees`` creates one
    # shared git repo per call, and one already exists under ``base`` from
    # ``_enroll_real_packets`` above.
    new_base = tmp_path / "older-run-new"
    new_base.mkdir()
    new_worktree = _registered_worktrees(new_base, "new-p1")[0]
    new_packet = _registered_packet("new-p1", new_worktree)
    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, OLDER_RUN_ID, T_OBSERVE, [new_packet])

    plan = _build_plan("plan-older-run-scope", [_plan_row(new_packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    with open_state_root(state_root) as handle:
        # Bound strictly after the new packet's own enrollment (T_OBSERVE)
        # -- chronology requires it, since the old packet's earlier
        # enrollment (T_ENROLL) and this new one now share one journal.
        bind_execution_plan(handle, canonical_bytes(plan), COORDINATOR_ID, OLDER_RUN_ID, T_CLAIM)

    folded_before = _folded(state_root)
    assert folded_before[old_packet["packet_id"]]["state"] == "READY"
    assert folded_before[new_packet["packet_id"]]["state"] == "READY"
    # The old packet enrolled first, so it has the lower enqueue_seq --
    # without the plan-membership filter, ordinary selection order would
    # pick IT first.
    assert (folded_before[old_packet["packet_id"]]["enqueue_seq"]
           < folded_before[new_packet["packet_id"]]["enqueue_seq"])

    marker = base / "markers.txt"
    adapter = _adapter_for(new_packet, marker)
    result = run_once(state_root, COORDINATOR_ID, OLDER_RUN_ID, _context(), T_AFTER,
                      execution_plan=plan,
                      worker_adapters={new_packet["packet_id"]: adapter})

    # The plan's own (in-scope) packet is claimed normally.
    assert result["status"] == "completed_attempt"
    assert result["packet_id"] == new_packet["packet_id"]
    assert _attempt_started_count(state_root, new_packet["packet_id"]) == 1

    # The out-of-plan packet from the earlier run is NEVER selected, NEVER
    # reaches a budget decision, and NEVER gets a (contract-invalid)
    # PACKET_PAUSED durably written for it.
    assert _attempt_started_count(state_root, old_packet["packet_id"]) == 0
    assert len(_packet_paused_events(state_root, old_packet["packet_id"])) == 0
    assert not any(e["event_type"] == "MODEL_FALLBACK_SELECTED"
                   and e.get("packet_id") == old_packet["packet_id"]
                   for e in _events(state_root))

    # The journal is fully intact and readable -- the corruption this fix
    # closes would have made this same call raise ``JournalChainBroken``.
    reread, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=STATE_ROOT_ID)
    assert torn is None
    assert reread


def test_replay_schedule_does_not_falsely_diverge_on_a_plan_scoped_selection(tmp_path):
    """Regression for a ``replay_schedule.py`` false positive introduced by
    ``select_next`` becoming plan-aware above.

    ``replay_schedule.py``'s own re-derivation of "what ``select_next``
    would have chosen" at each ``ATTEMPT_STARTED`` used to call
    ``select_next`` WITHOUT resolving the run's bound plan -- so replaying
    the exact scenario built by
    ``test_packet_from_an_earlier_unbound_run_is_never_selected_under_a_later_plan``
    above used to report a false ``SCHEDULING_DIVERGENCE``: the unscoped
    re-derivation picked the older, out-of-plan packet (the lower
    ``enqueue_seq``, ordinarily first), diverging from what was actually,
    correctly, recorded (the in-plan packet, the only one ``select_next``
    would have offered a real plan-bound coordinator). Fixed by resolving
    the plan actually bound to each event's own ``run_id`` (via
    ``recovery.bound_execution_plan_for_run``, reused not reimplemented)
    and passing it into ``select_next``, exactly as the real coordinator
    does. This is design 10.2 check #4 (the scheduling-choice replay,
    ``replay_schedule.py``'s own module docstring) -- a false divergence
    here is a false report on a perfectly correct journal, which is the
    one thing this module exists not to produce.
    """
    from harness_coordinator.v1.replay_schedule import replay_schedule

    base, state_root, packets = _enroll_real_packets(tmp_path, "replay-older-run", ["old-p1"])
    old_packet = packets[0]

    new_base = tmp_path / "replay-older-run-new"
    new_base.mkdir()
    new_worktree = _registered_worktrees(new_base, "new-p1")[0]
    new_packet = _registered_packet("new-p1", new_worktree)
    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, OLDER_RUN_ID, T_OBSERVE, [new_packet])

    plan = _build_plan("plan-replay-older-run-scope", [_plan_row(new_packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    with open_state_root(state_root) as handle:
        bind_execution_plan(handle, canonical_bytes(plan), COORDINATOR_ID, OLDER_RUN_ID, T_CLAIM)

    marker = base / "markers.txt"
    adapter = _adapter_for(new_packet, marker)
    result = run_once(state_root, COORDINATOR_ID, OLDER_RUN_ID, _context(), T_AFTER,
                      execution_plan=plan,
                      worker_adapters={new_packet["packet_id"]: adapter})
    assert result["status"] == "completed_attempt"
    assert result["packet_id"] == new_packet["packet_id"]

    replay = replay_schedule(state_root, STATE_ROOT_ID)
    assert replay["divergences"] == [], replay["divergences"]
    assert replay["replay_passed"] is True
    # Sanity: this journal genuinely does have the one ATTEMPT_STARTED that
    # a broken replay would have flagged -- an empty ``divergences`` list is
    # not vacuously true because nothing was ever checked.
    assert replay["attempt_started_events_checked"] == 1


def test_a_null_capability_class_pause_is_refused_before_it_can_corrupt_the_journal(tmp_path):
    """Part 1 of the same fix, exercised directly at the write boundary.

    Even if some future caller reached ``_record_packet_pause`` with
    ``capability_class=None`` -- exactly the shape the root-cause bug above
    used to produce -- ``validate_journal_event`` now refuses the write
    before it reaches the journal, matching ``recovery._append_stop_event``'s
    existing defense-in-depth pattern for exactly this kind of durable
    write. Before this fix, no validation call existed here at all and the
    contract-invalid event was written straight to disk, permanently.
    """
    from harness_coordinator.v1.coordinator import _record_packet_pause

    base, state_root, packets = _enroll_real_packets(tmp_path, "corrupt-guard", ["p1"])
    packet = packets[0]
    events_before = _events(state_root)
    journal_path = os.path.join(state_root, "journal.ndjson")
    before_bytes = open(journal_path, "rb").read()

    decision = {
        "decision": "STOP", "reason_code": "PLAN_SCOPE_PACKET_OUTSIDE_PLAN",
        "packet_id": packet["packet_id"], "route": None, "next_eligible_at": None,
        "evidence_ids": [],
    }
    with open_state_root(state_root) as handle:
        with pytest.raises(IntegrityError) as caught:
            _record_packet_pause(
                handle, state_root, STATE_ROOT_ID, list(events_before),
                packet["packet_id"], None, decision, COORDINATOR_ID, RUN_ID, T_CLAIM)
    assert caught.value.code == "PACKET_PAUSE_INVALID"

    # Nothing durable changed: the journal is byte-identical to before the
    # refused write attempt, and it remains fully readable -- the exact
    # property the old, unvalidated write would have destroyed forever.
    after_bytes = open(journal_path, "rb").read()
    assert after_bytes == before_bytes
    reread, torn = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    assert torn is None
    assert reread == events_before


def test_completed_plan_never_discovers_or_claims_more_work(tmp_path):
    base, state_root, packets = _enroll_real_packets(tmp_path, "complete", ["p1"])
    packet = packets[0]
    plan = _build_plan("plan-complete", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    claimed = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                       execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert claimed["status"] == "completed_attempt"

    result = _commission_result(
        packet, attempt_session_id(RUN_ID, packet["packet_id"], 1), attempt=1)
    _deposit(state_root, packet["packet_id"], 1, _review(_verdict(packet, result)))

    run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER, execution_plan=plan)
    assert _folded(state_root)[packet["packet_id"]]["state"] == "ACCEPTED"

    complete = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_FINAL,
                        execution_plan=plan)
    assert complete["status"] == "plan_complete"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    # A repeat call must still make zero further ATTEMPT_STARTED events.
    again = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_FINAL,
                     execution_plan=plan)
    assert again["status"] == "plan_complete"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1


def test_a_bound_plan_still_refuses_a_claim_after_a_graceful_stop(tmp_path):
    """The new pre-claim gate is unreachable once a stop is in effect.

    ``_run_iteration`` returns before this task's new code even runs once a
    graceful stop is stopped/pending -- structurally, not just by test
    convention -- so this proves that placement holds under a real plan.
    """
    base, state_root, packets = _enroll_real_packets(tmp_path, "stopped", ["p1", "p2"])
    rows = [_plan_row(p, "implementation") for p in packets]
    plan = _build_plan("plan-stopped", rows,
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    events = _events(state_root)
    events = request_graceful_stop(
        journal_path, lock_path, events, plan, COORDINATOR_ID, RUN_ID,
        STATE_ROOT_ID, T_OBSERVE, "QUEUE_SAFETY_CEILING_REACHED", [])
    events = make_graceful_stop_effective(
        journal_path, lock_path, events, COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
        T_OBSERVE, plan=plan)
    assert graceful_stop_state(events, RUN_ID)["stopped"] is True

    marker = base / "markers.txt"
    adapters = {p["packet_id"]: _adapter_for(p, marker) for p in packets}
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters=adapters)
    assert result["status"] == "graceful_stopped"
    assert _attempt_started_count(state_root, "p1") == 0
    assert _attempt_started_count(state_root, "p2") == 0


def test_two_sequential_claims_cannot_both_consume_the_last_budget_unit(tmp_path, monkeypatch):
    """A single coordinator's own budget survives a crash-and-resume.

    Despite the docstring this test originally carried, this is ONE process,
    one ``coordinator_id``, one ``run_id`` -- not two coordinators contending
    -- and it proves a real, worth-keeping property of its own: a crashed,
    unresolved attempt does not let the SAME coordinator, on a later call,
    spend a second unit of an already-exhausted plan budget. See
    ``test_two_distinct_coordinator_identities_cannot_both_win_the_journal_cas_for_the_same_claim``
    below for the genuinely-two-coordinators CAS property, and
    ``test_a_genuinely_distinct_second_coordinator_is_refused_by_the_budget_gate_not_the_cas``
    for the genuinely-two-coordinators BUDGET property -- this test's own
    single-coordinator crash-and-resume fixture pattern is what that one
    reuses to reach it.

    The packet's own O3 ``retry_limit`` (2, from the shared registered-packet
    fixture) would ordinarily allow ``resolve_open_attempts`` to hand out a
    further attempt after a stalled/crashed one -- that machinery predates
    O5 and is deliberately left untouched here. The plan's O5 ``attempt_limit``
    is set to 1, one unit stricter, so this proves the NEW thing: even though
    the underlying O3 retry mechanism is willing to return the packet to
    READY and would grant it another attempt, this run must still be refused
    a second unit of an already-exhausted plan budget -- refused by the
    pre-claim gate itself (``PACKET_BUDGET_ATTEMPTS_EXHAUSTED``), not merely
    by an unrelated already-claimed/already-running check.

    (An earlier version of this test drove the packet through one full
    completed attempt into O3's REVIEW state and called a second ``run_once``
    immediately after -- that scenario never reached the O5 budget gate at
    all: REVIEW is not READY, so ``select_next`` returned ``None`` for a
    reason with nothing to do with budgets, and the test passed for the
    wrong reason. This version drives an open, unresolved attempt back to
    READY via the same crash-and-resume path already proven in
    ``test_resume_after_a_pre_invoke_crash_still_applies_the_same_fallback_decision``,
    so the second claim attempt is genuinely otherwise-eligible and the O5
    budget check is what has to do the refusing.)
    """
    import harness_coordinator.v1.coordinator as coordinator_module

    base, state_root, packets = _enroll_real_packets(tmp_path, "contend", ["p1"])
    packet = packets[0]
    plan = _build_plan(
        "plan-contend",
        [_plan_row(packet, "implementation", attempt_limit=1)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    marker = base / "markers.txt"
    real_invoke = coordinator_module.invoke_worker
    monkeypatch.setattr(
        coordinator_module, "invoke_worker",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("coordinator-1 crash")))
    adapter = _adapter_for(packet, marker)
    try:
        run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    except RuntimeError as exc:
        assert str(exc) == "coordinator-1 crash"
    else:
        raise AssertionError("injected pre-invoke crash did not occur")
    monkeypatch.setattr(coordinator_module, "invoke_worker", real_invoke)
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    # A second coordinator racing for the same durable state root: the first
    # coordinator's crash is invisible to it, it simply observes the same
    # journal. ``resolve_open_attempts`` reaps the stalled attempt as an
    # infra_retry (the packet's own retry_limit=2 permits it) and returns the
    # packet to READY within this SAME call -- otherwise eligible again --
    # but the plan's attempt_limit=1 has already been spent by the one
    # ATTEMPT_STARTED above, so the pre-claim gate must refuse a second unit.
    second = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert second["status"] == "plan_stopped"
    assert second.get("stop_reason_code") == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"

    # A third, identical call must not duplicate the PACKET_PAUSED record.
    run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_FINAL,
            execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert len(_packet_paused_events(state_root, packet["packet_id"])) == 1


def test_two_distinct_coordinator_identities_cannot_both_win_the_journal_cas_for_the_same_claim(tmp_path):
    """Two DISTINCT coordinator identities -- different ``coordinator_id``,
    different ``trusted_process_context`` (hostname/boot_id/pid) -- both
    contending for the SAME durable state root's last remaining budget unit
    on one packet (``attempt_limit=1``, zero attempts started).

    **What this test actually proves, precisely named (renamed from
    "...cannot_both_consume_the_last_budget_unit" in review -- that name
    implied an O5-budget property, and this test does not prove one):**
    the PRE-EXISTING O3 journal compare-and-swap
    (``append_journal``'s ``expected_head``/``JournalHeadMoved``, plus
    ``claim_and_start_attempt``'s "packet no longer READY" re-fold-and-
    recheck) refuses a second, distinct coordinator identity once a first
    has durably won the claim -- this is a CAS-level double-claim-
    prevention property, not an O5-budget-determined one. Confirmed by
    review: re-running this exact test body with ``attempt_limit`` raised
    from 1 to 5 produces byte-identical behavior, because coordinator B
    never reaches ``evaluate_preclaim``/the O5 budget gate at all -- B is
    refused by the CAS (see below for why B calls
    ``claim_and_start_attempt`` directly, bypassing the pre-claim gate
    entirely) before the O5 budget gate is ever consulted, so the plan's
    budget is causally inert in this test. No test in this file covers a
    genuinely budget-DETERMINED refusal for a distinct second coordinator
    identity -- see
    ``test_a_genuinely_distinct_second_coordinator_is_refused_by_the_budget_gate_not_the_cas``
    below for that property.

    Both independently read the SAME pre-claim journal snapshot and both
    genuinely compute ``evaluate_preclaim(...) == ALLOW`` against it -- this
    is not a fabricated setup, both coordinators really do believe they may
    claim. Coordinator A's claim is durably recorded first. Coordinator B's
    own call then reuses exactly the durable journal compare-and-swap
    machinery ``append_journal``'s ``expected_head``/``JournalHeadMoved``
    already provides (the same mechanism O3's existing single-claim-wins
    tests exercise for an ordinary, non-budget claim, e.g.
    ``test_root_swap_after_claim_halts_before_pending_projection`` and
    ``test_cas_reread_halts_on_replacement_root`` in
    test_o3_p5_claim_root_identity.py): coordinator B's in-memory
    ``journal_events`` is the stale, pre-A snapshot -- exactly what a truly
    independent second coordinator process would have last read -- so its
    own ``append_journal`` call finds the on-disk head has moved, raises
    ``JournalHeadMoved``, and B's OWN retry loop (``claim_and_start_
    attempt``'s already-existing re-fold-and-recheck logic) discovers the
    packet is no longer READY and refuses with a clean ``RuntimeError``,
    never a corrupt double-claim.

    Coordinator A's own claim is durably recorded directly (rather than
    driven through a real ``claim_and_start_attempt`` call, which would
    also create the packet's O_EXCL claim-lock file and block B there
    instead) -- constructed with ``_make_event`` from the exact same
    payload shape ``claim_and_start_attempt`` itself builds, the same
    technique ``test_o3_p5_enrollment.py``'s
    ``test_cas_refresh_revalidates_chronology_against_new_head`` already
    uses to simulate "another coordinator already wrote this". This is
    deliberate: it is what isolates the JOURNAL CAS as the mechanism under
    test, rather than the claim-lock file, which a real second attempt
    would hit first and which is already proven elsewhere by
    ``test_two_sequential_claims_cannot_both_consume_the_last_budget_unit``
    and O3's own claim-root-identity suite.
    """
    from harness_coordinator.v1.coordinator import _load_enrolled_packet

    base, state_root, packets = _enroll_real_packets(tmp_path, "two-coord", ["p1"])
    packet = packets[0]
    plan = _build_plan(
        "plan-two-coord",
        [_plan_row(packet, "implementation", attempt_limit=1)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    events_before = _events(state_root)
    folded_before, _ = _fold_journal(state_root, events_before)
    packet_row_before = folded_before[packet["packet_id"]]
    assert packet_row_before["state"] == "READY"
    assert packet_row_before["attempts_started"] == 0

    # Both coordinators independently look at this SAME pre-claim snapshot
    # and both genuinely conclude they may claim.
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim
    decision_a = evaluate_preclaim(plan, packet_row_before, events_before, {}, T_CLAIM)
    decision_b = evaluate_preclaim(plan, packet_row_before, events_before, {}, T_AFTER)
    assert decision_a["decision"] == "ALLOW"
    assert decision_b["decision"] == "ALLOW"

    with open_state_root(state_root) as handle:
        packet_body = _load_enrolled_packet(
            state_root, packet["packet_id"], packet_row_before, events_before, handle=handle)

    # Coordinator A's claim, durably recorded first -- the same event shape
    # ``claim_and_start_attempt`` itself would produce.
    assigned = packet_body["assigned_worker"]
    intent_a = "attempt-%s-1" % packet["packet_id"]
    attempt_payload = {
        "attempt": 1, "lane": packet_row_before["lane"],
        "worker": {"worker_id": assigned["worker_id"],
                   "session_id": attempt_session_id(RUN_ID, packet["packet_id"], 1),
                   "provider": assigned["provider"], "model": assigned["model"]},
        "claim_sha256": "a" * 64, "worktree_path": packet_body["worktree"]["path"],
    }
    prev = events_before[-1] if events_before else None
    event_a = _make_event(
        (prev["seq"] + 1) if prev else 1, "ATTEMPT_STARTED", "coord-a", RUN_ID,
        STATE_ROOT_ID, prev, T_CLAIM, packet_id=packet["packet_id"], intent_id=intent_a,
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": attempt_payload, "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None,
                 "run": None, "report": None})
    append_journal(os.path.join(state_root, "journal.ndjson"), event_a,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=prev)

    # Coordinator B's own call: a distinct coordinator_id and a distinct
    # trusted_process_context (hostname/boot_id/pid), operating on its OWN
    # stale, pre-A in-memory journal_events snapshot -- exactly what a
    # genuinely independent second process would have last read.
    context_b = {"hostname": "host-b", "boot_id": "boot-b", "pid": 424242}
    with open_state_root(state_root) as handle:
        with pytest.raises(RuntimeError, match="packet no longer READY"):
            claim_and_start_attempt(
                state_root, STATE_ROOT_ID, list(events_before), packet["packet_id"],
                packet_row_before, "coord-b", RUN_ID, context_b, T_AFTER, handle=handle)

    # Exactly one of the two coordinators won: exactly one ATTEMPT_STARTED,
    # attempts_started spent exactly once -- not a corrupt double-claim, and
    # not by luck of call order (B's refusal was forced by a real, durably
    # earlier write, not a race).
    final_events = _events(state_root)
    started = [e for e in final_events if e["event_type"] == "ATTEMPT_STARTED"
              and e["packet_id"] == packet["packet_id"]]
    assert len(started) == 1
    assert started[0]["coordinator_id"] == "coord-a"
    final_folded, _ = _fold_journal(state_root, final_events)
    assert final_folded[packet["packet_id"]]["attempts_started"] == 1


def test_a_genuinely_distinct_second_coordinator_is_refused_by_the_budget_gate_not_the_cas(
        tmp_path, monkeypatch):
    """The O5 budget layer itself -- not the pre-existing O3 journal CAS --
    refuses a genuinely distinct second coordinator identity once a
    packet's plan budget is spent.

    Companion to
    ``test_two_distinct_coordinator_identities_cannot_both_win_the_journal_cas_for_the_same_claim``
    above, which proves the CAS property but never reaches the O5 budget
    gate at all (confirmed there by re-running with ``attempt_limit``
    raised from 1 to 5 and observing byte-identical behavior -- the plan's
    budget is causally inert in that test). This test proves the property
    that one does not: reuses
    ``test_two_sequential_claims_cannot_both_consume_the_last_budget_unit``'s
    own crash-and-resume fixture pattern for "attempt limit reached, packet
    still genuinely READY" (an already-completed/REVIEW packet would exit
    READY and make ``select_next`` return ``None`` for a reason unrelated
    to budgets -- the exact wrong-reason failure that pattern's own
    docstring already documents avoiding), but drives the SECOND call
    through a genuinely distinct coordinator identity ("coord-b", its own
    ``trusted_process_context``) instead of the same coordinator calling
    again.

    Coordinator A ("coord-a") durably starts the packet's one and only
    permitted attempt (plan ``attempt_limit=1``), then crashes before the
    attempt resolves (``invoke_worker`` monkeypatched to raise).
    Coordinator B's own ``run_once`` call reaps A's stalled attempt during
    its OWN recovery pass via ``resolve_open_attempts`` -- a purely
    journal-evidence-based mechanism (no ``attempt_outcome.json`` was ever
    written, so it resolves as ``infra_retry``, RUNNING -> READY) that is
    independent of coordinator/host identity, UNLIKE the other,
    identity-checked lock-reclaim path (``_reconcile_locks`` /
    ``classify_claim``). That is why A and B deliberately share the same
    ``hostname`` here: a genuinely foreign hostname against an
    already-journal-committed claim is refused with ``CLAIM_CONFLICT`` by
    that OTHER path before recovery gets anywhere near the property under
    test -- not a bypass of the distinct-identity requirement, since
    ``boot_id``/``pid``/``coordinator_id`` (the fields ``classify_claim``
    actually keys "is this genuinely a different coordinator" on) all
    differ between A and B regardless.

    Once the packet is genuinely READY again, B reaches ``select_next`` and
    its OWN independent ``evaluate_preclaim`` call over the durable journal
    (attempts_started=1 already spent against attempt_limit=1) is what
    refuses the claim -- ``PACKET_BUDGET_ATTEMPTS_EXHAUSTED``, not a
    CAS/journal-head error -- proving the O5 budget gate itself, not just
    the pre-existing claim-lock, refuses a second distinct coordinator once
    the last unit is spent.
    """
    import harness_coordinator.v1.coordinator as coordinator_module

    base, state_root, packets = _enroll_real_packets(tmp_path, "distinct-budget", ["p1"])
    packet = packets[0]
    plan = _build_plan(
        "plan-distinct-budget",
        [_plan_row(packet, "implementation", attempt_limit=1)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    context_a = {"coordinator_id": "coord-a", "hostname": "shared-host",
                "boot_id": "boot-a", "pid": 111111,
                "live_coordinator_ids": {"coord-a"}, "now": T_CLAIM}
    context_b = {"coordinator_id": "coord-b", "hostname": "shared-host",
                "boot_id": "boot-b", "pid": 424242,
                "live_coordinator_ids": {"coord-b"}, "now": T_AFTER}

    marker = base / "markers.txt"
    real_invoke = coordinator_module.invoke_worker
    monkeypatch.setattr(
        coordinator_module, "invoke_worker",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("coordinator-a crash")))
    adapter = _adapter_for(packet, marker)
    try:
        run_once(state_root, "coord-a", RUN_ID, context_a, T_CLAIM,
                execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    except RuntimeError as exc:
        assert str(exc) == "coordinator-a crash"
    else:
        raise AssertionError("injected pre-invoke crash did not occur")
    monkeypatch.setattr(coordinator_module, "invoke_worker", real_invoke)
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    started_events = [e for e in _events(state_root)
                      if e["event_type"] == "ATTEMPT_STARTED"
                      and e["packet_id"] == packet["packet_id"]]
    assert started_events[0]["coordinator_id"] == "coord-a"

    # Coordinator B: a genuinely distinct identity (coordinator_id, boot_id,
    # pid all differ from A), independently reaping A's stalled attempt
    # during its own recovery pass and then independently hitting the O5
    # budget gate.
    second = run_once(state_root, "coord-b", RUN_ID, context_b, T_AFTER,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert second["status"] == "plan_stopped"
    assert second.get("stop_reason_code") == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"
    # Recorded BY coordinator B specifically -- the refusal is genuinely B's
    # own independent decision, not attributable to A.
    assert paused[0]["coordinator_id"] == "coord-b"


def test_a_caller_supplied_plan_disagreeing_with_the_bound_plan_fails_closed(tmp_path):
    """``run_once``'s plan resolution never lets a caller-supplied
    ``execution_plan`` silently override a plan already durably bound to
    this run: when a disagreeing plan is already bound, the mismatch fails
    closed with ``PLAN_IDENTITY_CONFLICT`` (matching the existing pattern
    ``_fold_journal`` already raises for two conflicting bindings of the
    same run) rather than proceeding under the caller's plan."""
    base, state_root, packets = _enroll_real_packets(tmp_path, "plan-conflict", ["p1"])
    packet = packets[0]
    bound_plan = _build_plan("plan-conflict-bound", [_plan_row(packet, "implementation")],
                             {"implementation": _default_routes()["implementation"]})
    _bind(state_root, bound_plan)

    conflicting_plan = _build_plan("plan-conflict-other", [_plan_row(packet, "implementation")],
                                   {"implementation": _default_routes()["implementation"]},
                                   wall_clock=7200)
    assert conflicting_plan["plan_sha256"] != bound_plan["plan_sha256"]

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    with pytest.raises(IntegrityError) as caught:
        run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                execution_plan=conflicting_plan, worker_adapters={packet["packet_id"]: adapter})
    assert caught.value.code == "PLAN_IDENTITY_CONFLICT"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0

    # The SAME (matching) plan is still accepted normally -- this is a
    # cross-check against disagreement, not a blanket refusal of the
    # execution_plan argument.
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=bound_plan, worker_adapters={packet["packet_id"]: adapter})
    assert result["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1


# --------------------------------------------------------------------------
# Step 2 -- provider fallback and pause
# --------------------------------------------------------------------------


def test_implementation_fallback_routes_to_terra_and_matches_the_invoked_worker(tmp_path):
    """Not just that ``run_once`` returns ``completed_attempt`` -- that
    string is returned whether or not the invocation actually succeeded, so
    on its own it does not prove the fallback route was genuinely applied
    to the invocation (see the ``RESULT_IDENTITY_MISMATCH`` regression this
    guards). The attempt must genuinely reach REVIEW with a clean, valid
    result, and the worker-result artifact -- the synthetic worker's OWN
    self-reported identity, produced by the real invocation, not merely
    decided beforehand by the journal -- must show the fallback
    provider/model actually ran."""
    base, state_root, packets = _enroll_real_packets(tmp_path, "fallback", ["p1"])
    packet = packets[0]
    plan = _build_plan("plan-fallback", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)
    _record_capacity(state_root, "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker, provider="openai", model="gpt-5.6-terra")
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert result["status"] == "completed_attempt"

    events = _events(state_root)
    fallback = [e for e in events if e["event_type"] == "MODEL_FALLBACK_SELECTED"]
    assert len(fallback) == 1
    body = fallback[0]["payload"]["model_fallback"]
    assert body["capability_class"] == "implementation"
    assert body["from_route_id"] == "implementation-primary"
    assert body["to_route_id"] == "implementation-terra"
    assert body["provider"] == "openai"
    assert body["model_id"] == "gpt-5.6-terra"

    started = next(e for e in events if e["event_type"] == "ATTEMPT_STARTED")
    worker = started["payload"]["attempt"]["worker"]
    assert worker["provider"] == "openai"
    assert worker["model"] == "gpt-5.6-terra"
    # The worker's own instance identity, unlike provider/model, is not part
    # of the plan's routing decision, so it is deliberately preserved.
    assert worker["worker_id"] == packet["assigned_worker"]["worker_id"]

    # The attempt genuinely reached REVIEW -- not QUARANTINED, which is
    # where a RESULT_IDENTITY_MISMATCH lands the packet -- with a clean
    # result_validation carrying no error codes at all.
    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"
    outcome = _attempt_outcome(state_root, packet["packet_id"], 1)
    assert outcome["result_validation"]["valid"] is True
    assert outcome["result_validation"]["error_codes"] == []
    assert "RESULT_IDENTITY_MISMATCH" not in outcome["result_validation"]["error_codes"]
    assert outcome["outcome"] != "FAILED"

    # The actually-invoked synthetic worker's OWN self-reported identity
    # (not merely what the journal decided beforehand) genuinely used the
    # fallback route.
    invoked_worker = _worker_result(state_root, packet["packet_id"], 1)["worker"]
    assert invoked_worker["provider"] == "openai"
    assert invoked_worker["model"] == "gpt-5.6-terra"


def test_fable_exhaustion_pauses_design_without_claim(tmp_path):
    base, state_root, packets = _enroll_real_packets(tmp_path, "pause", ["design-1"])
    packet = packets[0]
    plan = _build_plan("plan-pause", [_plan_row(packet, "design_judgment")],
                       {"design_judgment": _default_routes()["design_judgment"]})
    _bind(state_root, plan)
    _record_capacity(state_root, "anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})

    assert result["status"] == "no_capable_model"
    assert result.get("stop_reason_code") == "NO_CAPABLE_MODEL_AVAILABLE"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"
    assert paused[0]["payload"]["packet_pause"]["capability_class"] == "design_judgment"

    # gpt-5.6-sol stays disabled in this plan -- Task 4 must not invent an
    # enabled fallback where none is authorized.
    assert not any(e["event_type"] == "MODEL_FALLBACK_SELECTED" for e in _events(state_root))
    assert not any(e["event_type"] == "ATTEMPT_STARTED" for e in _events(state_root))


def test_provider_backoff_pending_reports_awaiting_provider_reset_without_claim(tmp_path):
    base, state_root, packets = _enroll_real_packets(tmp_path, "backoff", ["p1"])
    packet = packets[0]
    routes = {"implementation": [
        _route("implementation-only", "opencode", "kimi-k2.7-code", "high", True, None),
    ]}
    plan = _build_plan("plan-backoff", [_plan_row(packet, "implementation")], routes)
    _bind(state_root, plan)
    _record_capacity(state_root, "opencode", "kimi-k2.7-code", "RATE_LIMITED",
                     reset_at=T_FINAL)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})

    assert result["status"] == "awaiting_provider_reset"
    assert result.get("stop_reason_code") == "PROVIDER_BACKOFF_PENDING"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["next_eligible_at"] == T_FINAL


# --------------------------------------------------------------------------
# Step 3 -- a fresh claim after a stalled resume still applies the SAME
# durable fallback decision (not a stale pre-plan default)
# --------------------------------------------------------------------------


def test_resume_after_a_pre_invoke_crash_still_applies_the_same_fallback_decision(tmp_path, monkeypatch):
    """A crash between ATTEMPT_STARTED and the actual invoke leaves that
    attempt with no captured outcome; the ALREADY-BUILT O3 resolution path
    (``resolve_open_attempts`` case (c), infra_retry -- not a Task 4
    mechanism) returns the packet to READY within the SAME later call, and a
    fresh second attempt is claimed.  This proves the fresh claim
    re-evaluates and re-applies the SAME durable fallback decision
    consistently -- exactly what Step 3 requires -- not a stale one."""
    import harness_coordinator.v1.coordinator as coordinator_module

    base, state_root, packets = _enroll_real_packets(tmp_path, "resume", ["p1"])
    packet = packets[0]
    plan = _build_plan("plan-resume", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)
    _record_capacity(state_root, "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    real_invoke = coordinator_module.invoke_worker
    monkeypatch.setattr(
        coordinator_module, "invoke_worker",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pre-invoke crash")))
    adapter_1 = _adapter_for(packet, marker, provider="openai", model="gpt-5.6-terra")
    try:
        run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                execution_plan=plan, worker_adapters={packet["packet_id"]: adapter_1})
    except RuntimeError as exc:
        assert str(exc) == "pre-invoke crash"
    else:
        raise AssertionError("injected pre-invoke crash did not occur")
    monkeypatch.setattr(coordinator_module, "invoke_worker", real_invoke)
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1

    adapter_2 = _adapter_for(packet, marker, provider="openai", model="gpt-5.6-terra", attempt=2)
    resumed = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                       execution_plan=plan, worker_adapters={packet["packet_id"]: adapter_2})
    assert resumed["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 2
    started_events = [e for e in _events(state_root) if e["event_type"] == "ATTEMPT_STARTED"]
    assert started_events[-1]["payload"]["attempt"]["worker"]["provider"] == "openai"
    assert started_events[-1]["payload"]["attempt"]["worker"]["model"] == "gpt-5.6-terra"

    # The fresh (second) attempt genuinely reached REVIEW with a clean
    # result -- not QUARANTINED via RESULT_IDENTITY_MISMATCH, which is what
    # happens when the re-applied fallback decision is journaled but never
    # actually handed to the invocation.
    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"
    outcome = _attempt_outcome(state_root, packet["packet_id"], 2)
    assert outcome["result_validation"]["valid"] is True
    assert outcome["result_validation"]["error_codes"] == []
    assert "RESULT_IDENTITY_MISMATCH" not in outcome["result_validation"]["error_codes"]
    assert outcome["outcome"] != "FAILED"

    # The actually-invoked synthetic worker's OWN self-reported identity for
    # the fresh attempt used the fallback route for real.
    invoked_worker = _worker_result(state_root, packet["packet_id"], 2)["worker"]
    assert invoked_worker["provider"] == "openai"
    assert invoked_worker["model"] == "gpt-5.6-terra"


def test_a_fallback_claim_resumed_via_the_other_invoke_worker_call_site_also_matches(tmp_path):
    """The SECOND ``invoke_worker`` call site -- the one inside
    ``_run_iteration``'s initial recovery loop, for a packet that folds to
    RUNNING with its baseline not yet journaled -- needs the identical
    ``assigned_worker`` fix as the fresh-claim call site, and this test
    reaches it for real, not just by code review.

    Neither existing fallback test actually exercises this call site (its
    OWN precondition -- ATTEMPT_STARTED already durably recorded, but this
    exact attempt's workspace baseline never journaled -- cannot arise from
    a fresh ``run_once`` claim, since the coordinator always records
    baseline immediately before claiming). It genuinely arises exactly the
    way O5's own graceful-stop resume tests already construct it
    (``test_queue_ceiling_during_attempt_finishes_then_blocks_next_claim``/
    ``test_a_restart_after_a_pending_stop_completes_recovery_before_effect``
    in test_o5_hard_stops.py): ``claim_and_start_attempt`` called directly
    (bypassing the coordinator's own baseline-then-claim orchestration, so
    no baseline is ever journaled for the attempt it creates), then a LATER
    ``run_once`` call supplies a real adapter for the first time. This test
    additionally supplies a FALLBACK ``assigned_worker`` to that direct
    claim -- the exact shape the O5 pre-claim gate produces in a real
    fallback -- and proves the resumed invocation matches it, not the
    packet's own default.
    """
    from harness_coordinator.v1.coordinator import claim_and_start_attempt

    base, state_root, packets = _enroll_real_packets(tmp_path, "resume-site2", ["p1"])
    packet = packets[0]
    plan = _build_plan("plan-resume-site2", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    events = _events(state_root)
    folded, _ = _fold_journal(state_root, events)
    fallback_worker = dict(packet["assigned_worker"])
    fallback_worker["provider"] = "openai"
    fallback_worker["model"] = "gpt-5.6-terra"
    assert fallback_worker != packet["assigned_worker"]
    with open_state_root(state_root) as handle:
        claim_and_start_attempt(
            state_root=state_root, state_root_id=STATE_ROOT_ID, journal_events=events,
            packet_id=packet["packet_id"], packet=folded[packet["packet_id"]],
            coordinator_id=COORDINATOR_ID, run_id=RUN_ID,
            trusted_process_context=_context(), now=T_CLAIM, handle=handle,
            assigned_worker=fallback_worker)
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
    started = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_STARTED")
    assert started["payload"]["attempt"]["worker"]["provider"] == "openai"
    assert started["payload"]["attempt"]["worker"]["model"] == "gpt-5.6-terra"
    # No baseline was journaled for this attempt -- the direct claim never
    # went through the coordinator's own preflight step, matching the exact
    # precondition the resume call site requires.
    assert not any(e["event_type"] == "WORKSPACE_BASELINE_RECORDED" for e in _events(state_root))

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker, provider="openai", model="gpt-5.6-terra")
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})

    # This resume happens entirely inside the initial recovery loop, BEFORE
    # selection runs -- "completed_attempt" is a status string only the
    # fresh-claim branch produces, so it is deliberately NOT asserted here,
    # and the iteration's own aggregate ``result["status"]`` is not asserted
    # either: it is a downstream consequence of how the attempt resolved
    # (confirmed empirically to read "no_eligible_work" when this fix is
    # applied and "plan_complete" -- via a terminal HUMAN_REQUIRED, NOT
    # REVIEW -- when it is reverted), not itself the property under test.
    # What matters, and what is actually asserted, is that the attempt
    # genuinely resolved to REVIEW with a clean, matching result -- not
    # QUARANTINED/HUMAN_REQUIRED via a RESULT_IDENTITY_MISMATCH.
    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"
    outcome = _attempt_outcome(state_root, packet["packet_id"], 1)
    assert outcome["result_validation"]["valid"] is True
    assert outcome["result_validation"]["error_codes"] == []
    assert "RESULT_IDENTITY_MISMATCH" not in outcome["result_validation"]["error_codes"]
    assert outcome["outcome"] != "FAILED"

    invoked_worker = _worker_result(state_root, packet["packet_id"], 1)["worker"]
    assert invoked_worker["provider"] == "openai"
    assert invoked_worker["model"] == "gpt-5.6-terra"


# --------------------------------------------------------------------------
# Step 4 -- human authority gate
# --------------------------------------------------------------------------


def test_human_stop_condition_in_plan_category_blocks_claim_before_attempt(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "human", ["p1"], human_stop_conditions_by_id={"p1": ["deployment"]})
    packet = packets[0]
    plan = _build_plan("plan-human", [_plan_row(packet, "implementation")],
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
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"
    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "HUMAN_AUTHORITY_REQUIRED"

    # A second call must not fabricate an approval: still blocked, still no
    # claim, and the duplicate-record dedupe still holds. The status is now
    # "no_eligible_work", not a repeated "plan_stopped": a HUMAN_REQUIRED
    # pause has no natural expiry, so the fold's own starvation fix (the
    # first PACKET_PAUSED durably sets this packet's
    # ``earliest_next_attempt_at`` to the indefinite sentinel) makes it
    # genuinely ineligible for the rest of this run -- ``select_next``
    # correctly has nothing left to offer, rather than re-selecting and
    # re-refusing the same blocked packet forever (the starvation bug this
    # fix closes; see the head-of-line-starvation regression tests below).
    again = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                     execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert again["status"] == "no_eligible_work"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    assert len(_packet_paused_events(state_root, packet["packet_id"])) == 1


def test_human_stop_condition_outside_the_closed_vocabulary_does_not_gate(tmp_path):
    """Legacy free-form ``human_stop_conditions`` text (pre-O5 fixtures use
    values like ``governed_doc_touched``) is not itself a closed-category
    match, so it must not gate under this reading -- a flagged, documented
    edge case, not an oversight (see the report)."""
    base, state_root, packets = _enroll_real_packets(tmp_path, "legacy", ["p1"])
    packet = packets[0]
    assert packet["human_stop_conditions"] == ["governed_doc_touched"]
    plan = _build_plan("plan-legacy", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert result["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1


def test_plan_human_stop_categories_do_not_narrow_the_packet_level_gate(tmp_path):
    """The plan's own ``human_stop_categories`` is a declared-scope
    inventory, never a waiver: a category absent from it must still gate if
    the packet declares it -- pre-waiving a category is exactly the
    inferred-approval hole this design forbids."""
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "notnarrow", ["p1"],
        human_stop_conditions_by_id={"p1": ["licensing_determination"]})
    packet = packets[0]
    plan = _build_plan("plan-notnarrow", [_plan_row(packet, "implementation")],
                       {"implementation": _default_routes()["implementation"]},
                       human_stop_categories=["deployment"])  # excludes licensing_determination
    _bind(state_root, plan)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert result["status"] == "plan_stopped"
    assert result.get("stop_reason_code") == "HUMAN_AUTHORITY_REQUIRED"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0


# --------------------------------------------------------------------------
# Step 5 -- head-of-line starvation: a paused/blocked packet must not
# re-select forever and starve the rest of the plan
# --------------------------------------------------------------------------


def test_a_blocked_packet_does_not_starve_a_second_eligible_packet_in_the_same_plan(tmp_path):
    """The starvation bug, reproduced and closed: before the fix,
    ``select_next`` re-picked the same lowest-``enqueue_seq`` READY packet
    on every iteration even after a ``PACKET_PAUSED`` refusal, because
    ``PACKET_PAUSED`` never changes packet state and nothing else marked it
    ineligible -- so a second, otherwise-eligible packet in the same plan
    could never be claimed and ``plan_complete`` became unreachable. p1
    (enrolled first, so it has the LOWER ``enqueue_seq`` and would ordinarily
    win selection) is blocked by a human-authority gate with no natural
    expiry; p2 is ordinary. This proves p2 gets selected and claimed on a
    SUBSEQUENT iteration once p1's first refusal durably marks it ineligible
    -- p1 is never required to become claimable in this test, that is
    expected to stay blocked for the run."""
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "starve", ["p1", "p2"], human_stop_conditions_by_id={"p1": ["deployment"]})
    p1, p2 = packets
    plan = _build_plan(
        "plan-starve",
        [_plan_row(p1, "implementation"), _plan_row(p2, "implementation")],
        {"implementation": _default_routes()["implementation"]},
        human_stop_categories=["deployment"])
    _bind(state_root, plan)

    marker = base / "markers.txt"
    adapters = {p["packet_id"]: _adapter_for(p, marker) for p in packets}

    # First iteration: p1 (the lower enqueue_seq) is selected, blocked, and
    # durably paused -- p2 is untouched this same iteration (the pre-claim
    # gate's own documented scope: it evaluates only the packet select_next
    # already chose, it does not walk past a blocked candidate).
    first = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                     execution_plan=plan, worker_adapters=adapters)
    assert first["status"] == "plan_stopped"
    assert first["packet_id"] == p1["packet_id"]
    assert first.get("stop_reason_code") == "HUMAN_AUTHORITY_REQUIRED"
    assert _attempt_started_count(state_root, p1["packet_id"]) == 0
    assert _attempt_started_count(state_root, p2["packet_id"]) == 0

    # Second iteration: p1 is now ineligible (its PACKET_PAUSED durably set
    # earliest_next_attempt_at to the indefinite sentinel) -- p2 is
    # genuinely selected and claimed, not starved behind p1 forever.
    second = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan, worker_adapters=adapters)
    assert second["status"] == "completed_attempt"
    assert second["packet_id"] == p2["packet_id"]
    assert _attempt_started_count(state_root, p2["packet_id"]) == 1
    assert _folded(state_root)[p2["packet_id"]]["state"] == "REVIEW"

    # p1 remains blocked -- never claimed, exactly one PACKET_PAUSED record
    # (the dedupe still holds across both iterations that considered it).
    assert _attempt_started_count(state_root, p1["packet_id"]) == 0
    assert _folded(state_root)[p1["packet_id"]]["state"] == "READY"
    assert len(_packet_paused_events(state_root, p1["packet_id"])) == 1

    # The run correctly proceeds to a sane terminal status once p2 completes
    # and p1 remains blocked -- no further claimable work (p1 permanently
    # blocked, p2 already past READY) -- never an infinite re-selection of
    # the blocked packet.
    third = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_FINAL,
                     execution_plan=plan, worker_adapters=adapters)
    assert third["status"] == "no_eligible_work"
    assert _attempt_started_count(state_root, p1["packet_id"]) == 0
    assert _attempt_started_count(state_root, p2["packet_id"]) == 1


def test_a_real_backoff_window_becomes_eligible_again_once_now_passes_it(tmp_path):
    """A BACKOFF-type pause with a real ``next_eligible_at`` composes
    correctly with the new fold-side ``earliest_next_attempt_at`` wiring:
    the packet stays genuinely ineligible while ``now`` is still before the
    recorded window, and becomes eligible again -- and gets claimed for
    real -- once ``now`` passes it. This is existing scheduler behavior
    (``scheduler._is_eligible``'s own ``earliest_next_attempt_at`` check);
    this test proves it still composes correctly now that ``PACKET_PAUSED``
    actually populates that field."""
    base, state_root, packets = _enroll_real_packets(tmp_path, "backoff-clears", ["p1"])
    packet = packets[0]
    routes = {"implementation": [
        _route("implementation-only", "opencode", "kimi-k2.7-code", "high", True, None),
    ]}
    plan = _build_plan("plan-backoff-clears", [_plan_row(packet, "implementation")], routes)
    _bind(state_root, plan)
    _record_capacity(state_root, "opencode", "kimi-k2.7-code", "RATE_LIMITED", reset_at=T_FINAL)

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    first = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                     execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert first["status"] == "awaiting_provider_reset"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0
    assert _folded(state_root)[packet["packet_id"]]["earliest_next_attempt_at"] == T_FINAL

    # Still before the window: re-polling must not re-select it either --
    # this is the same starvation-prevention property, just via a real,
    # finite window instead of the indefinite sentinel.
    still_blocked = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                             execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert still_blocked["status"] == "no_eligible_work"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 0

    # Once ``now`` passes the recorded window, the packet is genuinely
    # eligible again and gets claimed for real.
    after_window = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_MUCH_LATER,
                            execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert after_window["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"


# --------------------------------------------------------------------------
# Ungoverned (plan=None) runs are unaffected
# --------------------------------------------------------------------------


def test_ungoverned_run_without_a_plan_is_unaffected_by_the_gate(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "ungoverned", ["p1"], human_stop_conditions_by_id={"p1": ["deployment"]})
    packet = packets[0]
    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      worker_adapters={packet["packet_id"]: adapter})
    assert result["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
