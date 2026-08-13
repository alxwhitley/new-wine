"""O5 Task 5 Step 2, Scenario 1 -- single-item commissioning checkpoint.

Real end-to-end proof for the first of Task 5 Step 2's seven disposable
multi-scenario commissioning cases (the written plan,
``docs/superpowers/plans/2026-08-11-o5-budgets-hard-stops.md``, Task 5 Step
2, item 1): "an implementation packet whose primary synthetic provider
exhausts and whose plan-pinned fallback succeeds."

This is deliberately a genuine INTEGRATION proof, not a mocked one: the real
coordinator (``run_once`` / ``coordinator._run_iteration``) is driven against
a real, disposable, on-disk state root with a real bound execution plan and
real, durably-journaled synthetic ``PROVIDER_CAPACITY_RECORDED`` evidence
showing the primary implementation route (``opencode``/``kimi-k2.7-code``)
exhausted at claim time. Task 2/4's real pre-claim gate
(``budget_runtime.evaluate_preclaim`` / ``select_capable_route``, reached
through ``coordinator.py``'s real pre-claim ordering, never called directly
here) makes the fallback decision itself -- nothing in this file hand-writes
a ``MODEL_FALLBACK_SELECTED`` event or a ``route_history`` entry. The plan's
own pinned fallback hop (``openai``/``gpt-5.6-terra``) is the exact
implementation-fallback pair Task 2's own fixtures
(``test_o5_budget_runtime.py::_default_routes``) and Task 4's own coordinator
fixtures (``test_o5_coordinator_budgets.py``, e.g.
``test_implementation_fallback_routes_to_terra_and_matches_the_invoked_worker``)
already use as their canonical implementation-fallback example -- reused here
for consistency with the rest of the O5 suite, not invented fresh.

**Checkpoint finding, load-bearing for this file's shape (see this
dispatch's own report for the full write-up): the routing half of Scenario 1
was real, live-tested, and passing from the start. The "reaches a real
terminal ACCEPTED disposition" half of Scenario 1, as literally specified,
was found genuinely UNREACHABLE through the coordinator + review code as it
stood -- not a fixture problem, a real, deterministically-reproduced defect
-- and is now FIXED.**

Once ``evaluate_preclaim``/``select_capable_route`` choose the plan-pinned
fallback route, ``coordinator.py`` applies that route's provider/model to the
durable ``ATTEMPT_STARTED`` event and to the actual worker invocation
(``_assigned_worker_override``, applied explicitly at the two call sites that
need it -- see coordinator.py's own comment at the invocation-resume call
site, "...or invoke_worker's own result-identity check rejects a genuine
fallback as RESULT_IDENTITY_MISMATCH"). This is never written back into the
packet's own durable enrolled artifact (``packets/<packet_id>.json``,
``assigned_worker`` stays the packet's original pre-plan default forever --
and must, since that artifact's own ``packet_sha256`` self-hash and its
downstream terminal-seal binding both depend on it staying byte-identical to
what was enrolled). The defect was that ``review.py``'s ``_decide()`` -- the
ONLY function that resolves a REVIEW packet to a terminal verdict -- loaded
that same stale, un-overridden packet via
``coordinator._load_enrolled_packet`` and handed it to
``assemble_replay_bundle``/``validate_replay_bundle``
(``harness_contracts.v1.replay._cross_object_replay_checks``), which compared
``packet.assigned_worker.{provider,model}`` against the ACTUAL worker result
recorded for the attempt. For a genuinely fallback-routed packet these always
disagreed, so this check ALWAYS failed with two ``REVISION_MISMATCH`` errors
("worker.model/provider does not match packet.assigned_worker"), and
``resolve_review`` ALWAYS raised ``ReviewRefused``. This was the exact same
stale-identity failure mode coordinator.py's own comments already name and
guard against for the invocation-resume path -- it had never been propagated
to the review path.

**The fix**, kept off the bundle's own hashed/schema content on purpose:
``review.py``'s ``_decide`` (and, symmetrically, ``coordinator.py``'s
``_accepted_replay_evidence``, used when an ACCEPTED packet's dependents are
promoted) now looks up the ATTEMPT_STARTED-recorded ``worker`` for the
specific attempt under review -- the actually-invoked identity -- and passes
it to ``validate_replay_bundle`` as a new, optional
``trusted_attempt_worker`` parameter, alongside the bundle rather than
folded into it (the same shape ``trusted_dependency_provenance``/
``trusted_reviewer_sessions`` already use). ``_cross_object_replay_checks``
prefers this trusted, attempt-scoped identity when present and falls back to
``packet.assigned_worker`` exactly as before when it is not -- so the
non-fallback case (a worker result whose identity genuinely disagrees with
what was assigned, for any illegitimate reason) is checked exactly as
strictly as before.

This file therefore has two tests:

1. ``test_implementation_primary_exhausted_fallback_succeeds_reaches_review``
   -- the full, real, passing proof of the routing half of Scenario 1: the
   real pre-claim gate genuinely selects FALLBACK from durable exhaustion
   evidence, the real invocation genuinely runs under the fallback route, and
   the attempt genuinely reaches REVIEW with a clean, valid result.

2. ``test_fallback_routed_attempt_reaches_accepted`` -- the full, real proof
   of the fix: depositing a real, exactly-matching ACCEPT-worthy verdict for
   the fallback-invoked attempt and driving a real ``resolve_review`` call
   genuinely moves the packet to terminal ACCEPTED (no longer
   ``ReviewRefused``); a further real ``run_once`` call is a clean,
   idempotent no-op on the now-terminal packet; and the real
   ``build_reconciliation_report`` (Task 5's own subject) correctly reports
   the packet as accepted -- ``all_invariants_passed`` is ``True``, the
   packet's disposition is ``"accepted"``, and ``plan_totals["accepted"]``
   is ``1`` with every other disposition bucket at ``0``.

Neither test hand-fabricates the fallback event, the invocation, the
verdict's authorization, or the terminal acceptance -- every one of those is
produced by the real code this dispatch was scoped to exercise (unmodified
for the routing/invocation half, genuinely fixed for the review half), not
by this file.
"""

import os
import sys
import time

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.coordinator import attempt_session_id, run_once
from harness_coordinator.v1.invoke import WorkerAdapter
from harness_coordinator.v1.reconcile import build_reconciliation_report
from harness_coordinator.v1.recovery import _fold_journal
from harness_coordinator.v1.review import resolve_review
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import read_journal

from test_o3_p5_commissioning import _commission_result, _review
from test_o3_p5_review import _deposit, _verdict
from test_o5_budget_runtime import _default_routes
from test_o5_coordinator_budgets import (
    COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, T_AFTER, T_CLAIM, T_ENROLL, T_FINAL,
    _adapter_for, _attempt_outcome, _attempt_started_count, _bind,
    _build_plan, _context, _enroll_real_packets, _events, _folded,
    _packet_paused_events, _plan_row, _record_capacity,
)


def _commission_scenario1(tmp_path, name):
    """Commission scenario 1's shared setup: one plan, one implementation
    packet, its primary hop durably exhausted, driven through a real
    ``run_once`` claim so the real pre-claim gate genuinely selects the
    plan-pinned fallback and genuinely invokes it. Returns everything both
    tests in this file need, so neither duplicates this ~20-line sequence.
    """
    base, state_root, packets = _enroll_real_packets(tmp_path, name, ["p1"])
    packet = packets[0]
    plan = _build_plan(
        "plan-o5-scenario1-%s" % name, [_plan_row(packet, "implementation")],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    # Synthetic provider evidence: the primary hop is durably recorded
    # exhausted BEFORE the claim -- real authenticated evidence the real
    # pre-claim gate reads, not a hand-fabricated fallback decision.
    _record_capacity(state_root, "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker, provider="openai", model="gpt-5.6-terra")
    claim_result = run_once(
        state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
        execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})
    assert claim_result["status"] == "completed_attempt"
    return base, state_root, packet, plan


def test_implementation_primary_exhausted_fallback_succeeds_reaches_review(tmp_path):
    base, state_root, packet, plan = _commission_scenario1(tmp_path, "scenario1-routing")

    events = _events(state_root)
    fallback_events = [e for e in events if e["event_type"] == "MODEL_FALLBACK_SELECTED"]
    assert len(fallback_events) == 1
    fallback_body = fallback_events[0]["payload"]["model_fallback"]
    assert fallback_body["capability_class"] == "implementation"
    assert fallback_body["from_route_id"] == "implementation-primary"
    assert fallback_body["to_route_id"] == "implementation-terra"
    assert fallback_body["provider"] == "openai"
    assert fallback_body["model_id"] == "gpt-5.6-terra"
    # budget_runtime.select_capable_route's FALLBACK decision always carries
    # the fixed reason code "MODEL_ROUTE_FALLBACK_SELECTED" -- NOT the
    # underlying provider-capacity reason ("PROVIDER_ALLOWANCE_EXHAUSTED")
    # that caused the primary to be skipped. That capacity-specific reason
    # is not part of this event's payload at all; it is only independently
    # recoverable via a reconciliation row's own ``provider_backoff_state``
    # (the durable PROVIDER_CAPACITY_RECORDED evidence), checked below.
    assert fallback_body["reason_code"] == "MODEL_ROUTE_FALLBACK_SELECTED"

    started_event = next(e for e in events if e["event_type"] == "ATTEMPT_STARTED")
    started_worker = started_event["payload"]["attempt"]["worker"]
    assert started_worker["provider"] == "openai"
    assert started_worker["model"] == "gpt-5.6-terra"
    # The routing decision was recorded before the claim it produced.
    assert fallback_events[0]["seq"] < started_event["seq"]

    assert _folded(state_root)[packet["packet_id"]]["state"] == "REVIEW"

    # The reconciliation report already reflects real route_history/
    # provider_backoff_state extension for this packet, even resting in
    # REVIEW (not yet terminal) -- Task 5's own row extension does not wait
    # for a terminal disposition to report real routing evidence.
    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario1-routing", T_CLAIM)
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["plan_id"] == plan["plan_id"]
    assert row["capability_class"] == "implementation"
    route_history = row["route_history"]
    assert [entry["event_type"] for entry in route_history] == [
        "MODEL_FALLBACK_SELECTED", "ATTEMPT_STARTED",
    ]
    for entry in route_history:
        assert entry["provider"] == "openai"
        assert entry["model_id"] == "gpt-5.6-terra"
    assert route_history[0]["seq"] < route_history[1]["seq"]

    backoff = row["provider_backoff_state"]
    assert backoff["provider"] == "opencode"
    assert backoff["model_id"] == "kimi-k2.7-code"
    assert backoff["state"] == "ALLOWANCE_EXHAUSTED"

    # Not yet terminal: disposition genuinely cannot resolve to any of the
    # six closed buckets yet, and reconcile.py's own docstring says exactly
    # this must be left unresolved (None) rather than guessed -- proven for
    # real here, not merely asserted from reading the source.
    assert row["disposition"] is None
    assert report["all_invariants_passed"] is False


def test_fallback_routed_attempt_reaches_accepted(tmp_path):
    """Proves the fix: a genuinely ACCEPT-worthy, exactly-matching verdict
    for a fallback-invoked attempt now reaches terminal ACCEPTED -- the real
    end-to-end chain Task 5's commissioning scenario 1 specifies: claim ->
    primary exhausted -> plan-pinned fallback selected -> real invocation
    under the fallback identity (all inside ``_commission_scenario1``) ->
    real deposited ACCEPT verdict -> a real ``resolve_review`` call ->
    terminal ACCEPTED.

    Before the fix, this exact call sequence raised
    ``ReviewRefused(codes=("REVISION_MISMATCH",))`` every time, because
    ``review.py``'s replay-bundle assembly checked the packet's STALE,
    un-overridden ``assigned_worker`` against the actually-invoked worker
    identity -- the same override ``coordinator.py`` already applied for the
    invocation itself, never propagated to the review path. The fix compares
    against the ATTEMPT_STARTED-recorded assigned worker for this attempt
    instead (supplied to the validator alongside the bundle, not folded into
    it -- the bundle's own embedded ``packet`` stays byte-identical to the
    enrolled artifact throughout, so its self-hash and downstream
    terminal-seal binding never change).
    """
    base, state_root, packet, plan = _commission_scenario1(tmp_path, "scenario1-accepted")

    # A real ACCEPT-worthy result, built and hashed exactly the way the
    # actually-invoked fallback worker's own result was (same technique
    # ``_adapter_for`` itself uses internally) -- this is not a contrived
    # match, it is precisely what a genuinely successful fallback attempt's
    # own worker-result.json contains.
    session = attempt_session_id(RUN_ID, packet["packet_id"], 1)
    result = _commission_result(packet, session, attempt=1)
    result["worker"]["provider"] = "openai"
    result["worker"]["model"] = "gpt-5.6-terra"
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    _deposit(state_root, packet["packet_id"], 1, _review(_verdict(packet, result)))

    # A direct resolve_review call -- the exact call that, before the fix,
    # always raised ReviewRefused(REVISION_MISMATCH) for a fallback-routed
    # packet -- now genuinely authorizes and commits the verdict.
    events = _events(state_root)
    folded, _ = _fold_journal(state_root, events)
    with open_state_root(state_root) as handle:
        outcome = resolve_review(
            state_root, STATE_ROOT_ID, events, folded, packet["packet_id"],
            COORDINATOR_ID, RUN_ID, _context(), T_AFTER, handle=handle)
    assert outcome["status"] == "recorded"
    assert outcome["verdict"] == "ACCEPT"
    assert outcome["next_state"] == "ACCEPTED"
    assert _folded(state_root)[packet["packet_id"]]["state"] == "ACCEPTED"

    # A further real run_once call -- the normal coordinator path a
    # controller would rely on -- is a clean, idempotent no-op on the
    # now-terminal packet, not a second resolution.
    run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_FINAL, execution_plan=plan)
    assert _folded(state_root)[packet["packet_id"]]["state"] == "ACCEPTED"

    # Task 5's own reconciliation layer reflects the real terminal outcome:
    # correctly accepted, not silently misreported either direction.
    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario1-accepted", T_FINAL)
    assert report["all_invariants_passed"] is True
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["disposition"] == "accepted"
    totals = report["plan_totals"]
    assert totals["planned"] == 1
    assert totals["accepted"] == 1
    # No other closed disposition bucket may claim this packet.
    assert sum(totals[key] for key in (
        "resting_revise", "quarantined",
        "paused_provider", "blocked_human", "never_started",
    )) == 0


# ---------------------------------------------------------------------------
# Scenario 2 -- "a design packet whose Fable signal exhausts and whose
# disabled Sol candidate causes a pause without invocation."
#
# Real, end-to-end proof, same discipline as scenario 1: a real bound plan
# (``design_judgment`` route table pinning Fable primary and the
# disabled-by-plan ``gpt-5.6-sol`` as the only other candidate -- exactly
# ``test_o5_budget_runtime.py::_default_routes()["design_judgment"]``, the
# same fixture Task 2/4's own tests already use for this exact pairing, not
# invented fresh here), real durable ``PROVIDER_CAPACITY_RECORDED`` evidence
# showing Fable exhausted, and a real ``run_once`` claim. The real pre-claim
# gate (``budget_runtime.select_capable_route``, reached through
# ``coordinator.py``, never called directly) is what decides PAUSE here --
# this reuses the exact scenario ``test_o5_coordinator_budgets.py::
# test_fable_exhaustion_pauses_design_without_claim`` already proves at the
# coordinator layer; this file adds Task 5's reconciliation-disposition
# proof on top of it.
# ---------------------------------------------------------------------------


def test_design_fable_exhausted_disabled_sol_pauses_without_claim(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "scenario2-design-pause", ["design-1"])
    packet = packets[0]
    plan = _build_plan(
        "plan-o5-scenario2", [_plan_row(packet, "design_judgment")],
        {"design_judgment": _default_routes()["design_judgment"]})
    _bind(state_root, plan)

    # Real authenticated evidence: Fable's primary route is durably recorded
    # exhausted BEFORE the claim.
    _record_capacity(state_root, "anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED")

    marker = base / "markers.txt"
    adapter = _adapter_for(packet, marker)
    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                      execution_plan=plan, worker_adapters={packet["packet_id"]: adapter})

    assert result["status"] == "no_capable_model"
    assert result.get("stop_reason_code") == "NO_CAPABLE_MODEL_AVAILABLE"

    # The disabled Sol candidate never causes an invocation: no
    # MODEL_FALLBACK_SELECTED, no ATTEMPT_STARTED, ever, for this packet.
    events = _events(state_root)
    assert not any(e["event_type"] == "MODEL_FALLBACK_SELECTED" for e in events)
    assert not any(e["event_type"] == "ATTEMPT_STARTED" and e["packet_id"] == packet["packet_id"]
                  for e in events)
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    paused = _packet_paused_events(state_root, packet["packet_id"])
    assert len(paused) == 1
    assert paused[0]["payload"]["packet_pause"]["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"
    assert paused[0]["payload"]["packet_pause"]["capability_class"] == "design_judgment"

    # Task 5's own reconciliation classifies this as paused_provider, per
    # reconcile.py's _o5_disposition: NO_CAPABLE_MODEL_AVAILABLE is a member
    # of _O5_PROVIDER_REASON_CODES.
    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario2", T_CLAIM)
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["disposition"] == "paused_provider"
    assert row["capability_class"] == "design_judgment"
    assert row["stop_reasons"] == ["NO_CAPABLE_MODEL_AVAILABLE"]
    totals = report["plan_totals"]
    assert totals["planned"] == 1
    assert totals["paused_provider"] == 1
    assert sum(totals[key] for key in (
        "accepted", "resting_revise", "quarantined", "blocked_human", "never_started",
    )) == 0
    assert report["all_invariants_passed"] is True


# ---------------------------------------------------------------------------
# Scenario 6 -- "a human-authority packet blocked before claim."
#
# Real mechanism (Task 4 Step 4, coordinator.py): a packet's own
# ``human_stop_conditions`` are cross-checked against the bound plan's closed
# ``human_stop_categories`` vocabulary at the pre-claim gate, BEFORE any
# claim -- reached here through a real ``run_once`` call, not asserted from
# reading the source. Reuses the exact category ("deployment") and packet
# shape ``test_o5_coordinator_budgets.py::
# test_human_stop_condition_in_plan_category_blocks_claim_before_attempt``
# already proves at the coordinator layer; this file adds Task 5's
# reconciliation-disposition proof on top of it.
# ---------------------------------------------------------------------------


def test_human_authority_packet_blocked_before_claim(tmp_path):
    base, state_root, packets = _enroll_real_packets(
        tmp_path, "scenario6-human-block", ["p1"],
        human_stop_conditions_by_id={"p1": ["deployment"]})
    packet = packets[0]
    plan = _build_plan(
        "plan-o5-scenario6", [_plan_row(packet, "implementation")],
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

    # Task 5's own reconciliation classifies this as blocked_human, per
    # reconcile.py's _o5_disposition's reasoned default: HUMAN_AUTHORITY_
    # REQUIRED is NOT a member of _O5_PROVIDER_REASON_CODES, so it falls to
    # the blocked_human branch (a human needs to look), never paused_provider.
    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario6", T_CLAIM)
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["disposition"] == "blocked_human"
    assert row["stop_reasons"] == ["HUMAN_AUTHORITY_REQUIRED"]
    totals = report["plan_totals"]
    assert totals["planned"] == 1
    assert totals["blocked_human"] == 1
    assert sum(totals[key] for key in (
        "accepted", "resting_revise", "quarantined", "paused_provider", "never_started",
    )) == 0
    assert report["all_invariants_passed"] is True


# ---------------------------------------------------------------------------
# Scenario 3 -- "an active packet that finishes after the queue safety
# ceiling while the next packet remains never started."
#
# Real mechanism (Task 3, coordinator.py's ceiling check at the top of
# ``_run_iteration``, before the attempt-resolution block; see
# ``wall_clock_ceiling_reached``/``request_graceful_stop``/
# ``make_graceful_stop_effective`` in recovery.py). Reuses
# ``test_o5_hard_stops.py``'s own proven two-packet ceiling fixture
# (``_two_packet_plan_state``) and its own
# ``test_queue_ceiling_during_attempt_finishes_then_blocks_next_claim`` shape
# for the "ceiling crosses mid-attempt, the open attempt still finishes, the
# next packet is never claimed" half -- not reinvented here. This file adds
# the second half Task 5's commissioning scenario needs beyond what that
# test proves: driving packet A's already-finished REVIEW attempt on to a
# REAL terminal ACCEPTED (a real deposited verdict, resolved through a
# further real ``run_once`` call -- proving that a graceful stop blocks the
# NEXT CLAIM, not the resolution of work already in flight, per the plan's
# own Global Constraints: "Graceful limits finish the active attempt and
# stop before the next claim") -- and Task 5's reconciliation proof that the
# two packets land in exactly the two dispositions this scenario names:
# accepted (A) and never_started (B).
#
# Uses test_o5_hard_stops.py's own module-level identities (COORDINATOR_ID=
# "coord-o5-stop", RUN_ID="run-o5-stop", STATE_ROOT_ID="srid-o5-stop"), not
# this file's own scenario-1/2/6 identities -- aliased locally to avoid
# colliding with those already-bound names.
# ---------------------------------------------------------------------------


def test_active_packet_finishes_after_ceiling_next_packet_never_started(tmp_path):
    from test_o5_hard_stops import (
        COORDINATOR_ID as HS_COORDINATOR_ID,
        RUN_ID as HS_RUN_ID,
        STATE_ROOT_ID as HS_STATE_ROOT_ID,
        _context as _hs_context,
        _stop_events,
        _two_packet_plan_state,
    )
    from harness_coordinator.v1.coordinator import claim_and_start_attempt

    # ``bind=True``: Task 5's reconciliation reads the DURABLY BOUND plan
    # from the journal (``bound_execution_plan_for_run``), not merely the
    # caller-supplied ``execution_plan`` argument each ``run_once`` call
    # below also passes -- without a real ``EXECUTION_PLAN_BOUND`` event,
    # ``build_reconciliation_report`` finds no bound plan and every row's
    # ``plan_id``/``capability_class``/``disposition`` stays ``None``, even
    # though the coordinator's own gating (which reads the caller-supplied
    # plan directly) behaves identically either way.
    state = _two_packet_plan_state(tmp_path, "scenario3", bind=True)
    first, second = state["packet_ids"]
    state_root = state["state_root"]

    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"),
                                state_root_id=HS_STATE_ROOT_ID)
    assert torn is None
    folded, _ = _fold_journal(state_root, events)
    # Packet A already has an open attempt BEFORE the fake clock crosses the
    # plan's wall-clock safety ceiling -- a direct claim, matching
    # test_o5_hard_stops.py's own established technique for constructing
    # this exact precondition.
    claim_and_start_attempt(
        state_root=state_root, state_root_id=HS_STATE_ROOT_ID,
        journal_events=events, packet_id=first, packet=folded[first],
        coordinator_id=HS_COORDINATOR_ID, run_id=HS_RUN_ID,
        trusted_process_context=_hs_context(), now=state["before_ceiling"])

    # The real coordinator: the ceiling is crossed, the stop is requested,
    # packet A's open attempt is still driven to a durable outcome (REVIEW)
    # in the SAME call, and only THEN does the stop become effective --
    # before packet B is ever selected.
    result = run_once(state_root, HS_COORDINATOR_ID, HS_RUN_ID, _hs_context(),
                      state["past_ceiling"], execution_plan=state["plan"],
                      worker_adapters={"kimi_implementation": state["adapters"][first]})

    assert result["status"] == "graceful_stopped"
    assert _stop_events(state_root) == ["GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]

    mid, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                          state_root_id=HS_STATE_ROOT_ID)
    folded_mid, _ = _fold_journal(state_root, mid)
    assert folded_mid[first]["state"] == "REVIEW"
    assert folded_mid[first]["open_attempt"] is None
    assert folded_mid[second]["state"] == "READY"
    started_second = [e for e in mid if e["event_type"] == "ATTEMPT_STARTED"
                      and e["packet_id"] == second]
    assert started_second == []

    # Packet A's attempt genuinely finished (not merely abandoned) before the
    # stop took effect -- the exact ordering test_o5_hard_stops.py's own
    # ceiling test already proves; re-confirmed here as this scenario's own
    # precondition for what follows.
    types = [event["event_type"] for event in mid]
    assert types.index("GRACEFUL_STOP_REQUESTED") < types.index("ATTEMPT_FINISHED")
    assert types.index("ATTEMPT_FINISHED") < types.index("GRACEFUL_STOP_EFFECTIVE")

    # A real ACCEPT-worthy verdict for packet A's already-finished attempt,
    # deposited and resolved through a FURTHER real run_once call -- proving
    # the graceful stop blocks the next CLAIM (packet B), never the
    # resolution of an already-open review for work already in flight.
    session = attempt_session_id(HS_RUN_ID, first, 1)
    packet_a = next(p for p in state["packets"] if p["packet_id"] == first)
    worker_result = _commission_result(packet_a, session, attempt=1)
    _deposit(state_root, first, 1, _review(_verdict(packet_a, worker_result)))

    resolved = run_once(state_root, HS_COORDINATOR_ID, HS_RUN_ID, _hs_context(),
                        state["past_ceiling"], execution_plan=state["plan"])
    assert resolved["status"] == "graceful_stopped"
    assert any(r.get("packet_id") == first and r.get("verdict") == "ACCEPT"
              for r in resolved.get("reviews", []))

    final, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                            state_root_id=HS_STATE_ROOT_ID)
    folded_final, _ = _fold_journal(state_root, final)
    assert folded_final[first]["state"] == "ACCEPTED"
    assert folded_final[second]["state"] == "READY"
    started_second_final = [e for e in final if e["event_type"] == "ATTEMPT_STARTED"
                            and e["packet_id"] == second]
    assert started_second_final == []

    # Task 5's own reconciliation reflects exactly the two dispositions this
    # scenario is meant to contribute to the eventual 7-packet total: one
    # accepted, one never_started.
    report = build_reconciliation_report(
        state_root, HS_STATE_ROOT_ID, HS_COORDINATOR_ID, HS_RUN_ID,
        "report-o5-scenario3", state["past_ceiling"])
    row_a = next(r for r in report["packets"] if r["packet_id"] == first)
    row_b = next(r for r in report["packets"] if r["packet_id"] == second)
    assert row_a["disposition"] == "accepted"
    assert row_b["disposition"] == "never_started"
    totals = report["plan_totals"]
    assert totals["planned"] == 2
    assert totals["accepted"] == 1
    assert totals["never_started"] == 1
    assert sum(totals[key] for key in (
        "resting_revise", "quarantined", "paused_provider", "blocked_human",
    )) == 0
    assert report["all_invariants_passed"] is True


# ---------------------------------------------------------------------------
# Scenarios 4 and 5 -- "a packet with retry_limit=1 whose command timeout /
# output flood kills a child/grandchild process group on both bounded
# attempts and then deterministically quarantines the packet."
#
# Real process-group-kill mechanics, reused (not reinvented) from
# ``test_o3_p5_invocation.py``'s own ``test_timeout_kills_entire_process_
# group``/``test_output_cap_terminates_worker`` -- the exact nested
# child-spawns-grandchild code shape those tests already prove closes the
# whole group, not just the direct child. The only thing new here is
# driving that same shape through the REAL coordinator claim path
# (``run_once``/``claim_and_start_attempt``/``invoke_worker``, via a plan
# whose packet ``budgets.command_timeout_seconds``/``budgets.output_bytes``
# are the plan-derived ceiling Task 3 wires into every invocation) across
# TWO bounded attempts (``retry_limit=1`` -> ``attempt_limit=2``), so the
# first attempt's real INFRA_RETRYABLE classification requeues the packet
# and the second attempt's real budget-exhausted classification quarantines
# it -- both durably observed, not asserted from reading the source.
# ---------------------------------------------------------------------------

PYTHON_EXECUTABLE = os.path.realpath(sys.executable)


def _child_grandchild_worker_code(extra_body=""):
    """The exact nested process-group shape
    ``test_o3_p5_invocation.py::test_timeout_kills_entire_process_group``
    already proves closes cleanly: a worker spawns a child, which spawns a
    grandchild and reports both pids to a marker file, so containment is
    checked two levels down, not just at the direct child. ``extra_body`` is
    injected between the marker write and the final sleep, for scenario 5's
    output flood."""
    grandchild = "import time; time.sleep(60)"
    child = (
        "import subprocess, sys, time\n"
        "g = subprocess.Popen([sys.executable, '-c', %r])\n"
        "sys.stdout.write(str(g.pid) + chr(10)); sys.stdout.flush()\n"
        "time.sleep(60)\n"
    ) % grandchild
    return """import os, subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', %r], stdout=subprocess.PIPE, text=True)
grandchild = p.stdout.readline().strip()
open(os.environ['SYNTHETIC_MARKER_PATH'], 'a').write('%%d\\n%%s\\n' %% (p.pid, grandchild))
%s
time.sleep(60)
""" % (child, extra_body)


def _process_group_probe_adapter(code, marker_path):
    return WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code),
                         env={"SYNTHETIC_MARKER_PATH": str(marker_path)})


def _assert_pid_gone(pid, timeout=5.0):
    """Same bounded poll-and-check technique as
    ``test_o3_p5_invocation.py::test_timeout_kills_entire_process_group``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(.01)
    raise AssertionError("descendant %d survived the kill" % pid)


def _read_marker_pids(marker_path):
    child_pid, grandchild_pid = [int(line) for line in marker_path.read_text().split()]
    return child_pid, grandchild_pid


def _enroll_real_packet_with_retry_limit(tmp_path, name, packet_id, retry_limit):
    """Same real, on-disk single-packet enrollment ``_enroll_real_packets``
    performs, with the packet's own O3-level ``budgets.retry_limit``
    overridden.

    Load-bearing distinction, found while building scenarios 4/5: the O5
    PLAN row's own ``budgets.retry_limit`` field (set via ``_plan_row``) is
    NOT what ``classify_runtime._finish_attempt`` reads to decide
    requeue-vs-quarantine for an INFRA_RETRYABLE attempt -- that reads the
    PACKET's own O3-level ``budgets.retry_limit`` (``pkt.get("retry_limit")``
    on the folded packet), which ``_registered_packet``'s shared fixture
    defaults to 2 (``test_o3_p5_review.py::_packet``). Passing
    ``retry_limit=1`` only to ``_plan_row`` (as scenario 1-3/6's fixtures do,
    where it is immaterial) genuinely produces THREE requeue-eligible
    attempts before quarantine, not the two this scenario's own docstring
    requires -- confirmed by first reproducing that exact wrong disposition
    live before adding this override, not assumed from reading the source.
    """
    from harness_coordinator.v1.enroll import enroll_packets

    from test_o3_p5_commissioning import _registered_packet, _registered_worktrees
    from test_o3_p5_review import TRUSTED_REVIEWER, _write_manifest, _write_trust_roots

    base = tmp_path / name
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    worktree = _registered_worktrees(base, packet_id)[0]
    packet = _registered_packet(packet_id, worktree)
    packet["budgets"]["retry_limit"] = retry_limit
    # validate_journal_event's own enrollment-payload check requires
    # retry_limit >= 2 whenever sonnet_reassignment_allowed is true (one
    # retry is structurally spent on the kimi->sonnet lane switch itself) --
    # confirmed live, not assumed, after this exact retry_limit=1 override
    # first failed enrollment with INVALID_VALUE on
    # /payload/packet/retry_limit. This scenario exercises INFRA_RETRYABLE
    # command-timeout classification, not lane reassignment, so disabling it
    # is the clean fix, not a workaround.
    packet["sonnet_reassignment_allowed"] = False
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))

    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, T_ENROLL, [packet])
    return base, state_root, packet


def test_command_timeout_kills_process_group_on_both_bounded_attempts_then_quarantines(tmp_path):
    base, state_root, packet = _enroll_real_packet_with_retry_limit(
        tmp_path, "scenario4-timeout", "p1", retry_limit=1)
    plan = _build_plan(
        "plan-o5-scenario4",
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
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    outcome1 = _attempt_outcome(state_root, packet["packet_id"], 1)
    assert outcome1["invocation"]["timed_out"] is True

    finished1 = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_FINISHED"
                     and e["packet_id"] == packet["packet_id"]
                     and e["payload"]["attempt"]["attempt"] == 1)
    assert finished1["cause"] == "infra_retry"
    assert finished1["to_state"] == "READY"

    child1, grandchild1 = _read_marker_pids(marker1)
    _assert_pid_gone(child1)
    _assert_pid_gone(grandchild1)

    marker2 = base / "pg-marker-2.txt"
    second = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan,
                      worker_adapters={packet["packet_id"]: _process_group_probe_adapter(code, marker2)})
    assert second["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 2
    assert _folded(state_root)[packet["packet_id"]]["state"] == "QUARANTINED"

    outcome2 = _attempt_outcome(state_root, packet["packet_id"], 2)
    assert outcome2["invocation"]["timed_out"] is True

    finished2 = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_FINISHED"
                     and e["packet_id"] == packet["packet_id"]
                     and e["payload"]["attempt"]["attempt"] == 2)
    assert finished2["cause"] == "attempt_budget_exhausted"
    assert finished2["to_state"] == "QUARANTINED"
    assert finished2["payload"]["classification"]["quarantine_reason"] == "attempt_budget_exhausted"

    child2, grandchild2 = _read_marker_pids(marker2)
    _assert_pid_gone(child2)
    _assert_pid_gone(grandchild2)

    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario4", T_AFTER)
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["disposition"] == "quarantined"
    totals = report["plan_totals"]
    assert totals["planned"] == 1
    assert totals["quarantined"] == 1
    assert sum(totals[key] for key in (
        "accepted", "resting_revise", "paused_provider", "blocked_human", "never_started",
    )) == 0
    assert report["all_invariants_passed"] is True


def test_output_flood_capped_and_killed_on_both_bounded_attempts_then_quarantines(tmp_path):
    base, state_root, packet = _enroll_real_packet_with_retry_limit(
        tmp_path, "scenario5-output", "p1", retry_limit=1)
    plan = _build_plan(
        "plan-o5-scenario5",
        [_plan_row(packet, "implementation", attempt_limit=2, retry_limit=1,
                   command_timeout_seconds=15, output_bytes=1024)],
        {"implementation": _default_routes()["implementation"]})
    _bind(state_root, plan)

    # Same nested child/grandchild containment shape as scenario 4, plus an
    # output flood the killed worker writes before sleeping -- the exact
    # additional line ``test_o3_p5_invocation.py::test_output_cap_
    # terminates_worker`` already proves triggers OUTPUT_LIMIT_EXCEEDED, not
    # invented fresh here.
    code = _child_grandchild_worker_code(
        extra_body="sys.stdout.write('x' * 200000)\nsys.stdout.flush()")

    marker1 = base / "pg-marker-1.txt"
    first = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_CLAIM,
                     execution_plan=plan,
                     worker_adapters={packet["packet_id"]: _process_group_probe_adapter(code, marker1)})
    assert first["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 1
    assert _folded(state_root)[packet["packet_id"]]["state"] == "READY"

    outcome1 = _attempt_outcome(state_root, packet["packet_id"], 1)
    # Distinguishes this from scenario 4's COMMAND_TIMEOUT durable evidence:
    # an output-capped kill is NOT a timeout (invoke.py's read loop breaks on
    # output_exceeded before the deadline check), and the captured channel
    # bytes are genuinely bounded by the plan's tiny output_bytes ceiling.
    assert outcome1["invocation"]["timed_out"] is False
    assert outcome1["stdout"]["byte_length"] + outcome1["stderr"]["byte_length"] <= 1024

    finished1 = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_FINISHED"
                     and e["packet_id"] == packet["packet_id"]
                     and e["payload"]["attempt"]["attempt"] == 1)
    assert finished1["cause"] == "infra_retry"
    assert finished1["to_state"] == "READY"

    child1, grandchild1 = _read_marker_pids(marker1)
    _assert_pid_gone(child1)
    _assert_pid_gone(grandchild1)

    marker2 = base / "pg-marker-2.txt"
    second = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), T_AFTER,
                      execution_plan=plan,
                      worker_adapters={packet["packet_id"]: _process_group_probe_adapter(code, marker2)})
    assert second["status"] == "completed_attempt"
    assert _attempt_started_count(state_root, packet["packet_id"]) == 2
    assert _folded(state_root)[packet["packet_id"]]["state"] == "QUARANTINED"

    outcome2 = _attempt_outcome(state_root, packet["packet_id"], 2)
    assert outcome2["invocation"]["timed_out"] is False
    assert outcome2["stdout"]["byte_length"] + outcome2["stderr"]["byte_length"] <= 1024

    finished2 = next(e for e in _events(state_root) if e["event_type"] == "ATTEMPT_FINISHED"
                     and e["packet_id"] == packet["packet_id"]
                     and e["payload"]["attempt"]["attempt"] == 2)
    assert finished2["cause"] == "attempt_budget_exhausted"
    assert finished2["to_state"] == "QUARANTINED"
    assert finished2["payload"]["classification"]["quarantine_reason"] == "attempt_budget_exhausted"

    child2, grandchild2 = _read_marker_pids(marker2)
    _assert_pid_gone(child2)
    _assert_pid_gone(grandchild2)

    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5-scenario5", T_AFTER)
    row = next(r for r in report["packets"] if r["packet_id"] == packet["packet_id"])
    assert row["disposition"] == "quarantined"
    totals = report["plan_totals"]
    assert totals["planned"] == 1
    assert totals["quarantined"] == 1
    assert sum(totals[key] for key in (
        "accepted", "resting_revise", "paused_provider", "blocked_human", "never_started",
    )) == 0
    assert report["all_invariants_passed"] is True


# ---------------------------------------------------------------------------
# Task 5 Step 2, item 7 -- "restart at every durable crash boundary followed
# by identical final accounting."
#
# NOT an eighth scenario: a testing methodology applied across ONE combined
# execution plan containing all seven packets scenarios 1-6 already proved
# individually above (the two "accepted" packets -- scenario 1's own fallback
# packet and scenario 3's finisher -- plus scenario 2's paused_provider
# packet, scenario 3's own never_started second packet, scenarios 4/5's two
# quarantined packets, and scenario 6's blocked_human packet). Every
# packet-building technique below is reused unmodified from the scenarios
# above (``_child_grandchild_worker_code``/``_process_group_probe_adapter``
# for 4/5, ``_adapter_for``/``_commission_result`` for 1/2/3,
# ``claim_and_start_attempt`` for 3's direct pre-ceiling claim) -- nothing
# here reinvents a proven building block.
#
# **Checked and corrected during review, recorded here so it is not
# rediscovered:** an earlier draft of this file suspected scenarios 2 and 6
# (both "paused/blocked before claim", leaving the packet's fold ``state``
# at ``READY``) could starve one another under ``scheduler.select_next``'s
# single-candidate-per-call, ``(enqueue_seq, packet_id)``-ordered selection
# -- reasoning from ``_is_eligible``'s field checks alone, without also
# checking how ``PACKET_PAUSED`` folds. That reasoning was WRONG and has
# been corrected, not merely reverted: ``recovery.py`` folds every
# ``PACKET_PAUSED`` event with no natural expiry (``PAUSE``/``STOP``/
# ``HUMAN_REQUIRED`` -- exactly scenarios 2 and 6's own reason codes) by
# setting the packet's ``earliest_next_attempt_at`` to
# ``_INDEFINITE_PAUSE_SENTINEL`` (``"9999-12-31T23:59:59Z"``, comment above
# the constant, ``recovery.py``), which ``_is_eligible`` (``scheduler.py``)
# then correctly excludes from every later ``now``. This is precisely
# designed to prevent the starvation the earlier draft suspected -- and a
# live, isolated two-packet reproduction (design-pause then, on a genuinely
# SECOND real ``run_once`` call, human-block) confirms it works exactly as
# designed: the second call correctly selects and blocks the human-authority
# packet, not the already-paused design packet. Both scenarios 2 and 6
# below are therefore driven through the SAME real, ordinary, automatic
# ``run_once`` claim path, in enrollment order, exactly like every other
# select_next-driven packet here -- no direct/bypass construction needed for
# either. The packet-to-bucket MAPPING matches the plan doc's Step 2
# exactly, and so, once corrected, does the MECHANISM reaching every one of
# the seven dispositions.
#
# Dependencies between all seven packets are empty (``dependency_ids=[]``,
# the ``_registered_packet`` fixture's own default, never overridden below)
# -- confirmed structurally, not merely asserted, by never touching that
# field for any of the seven.
# ---------------------------------------------------------------------------

TC_ENROLL = "2026-08-12T00:00:00Z"
TC_BIND = "2026-08-12T00:00:30Z"
TC_S4_A1 = "2026-08-12T00:01:00Z"          # RUN_STARTED anchors here (first run_once call)
TC_S4_A2 = "2026-08-12T00:02:00Z"
TC_S5_A1 = "2026-08-12T00:03:00Z"
TC_S5_A2 = "2026-08-12T00:04:00Z"
TC_OBS_PRIMARY = "2026-08-12T00:04:30Z"
TC_S1_CLAIM = "2026-08-12T00:05:00Z"
TC_S1_RESOLVE = "2026-08-12T00:06:00Z"
TC_OBS_FABLE = "2026-08-12T00:06:30Z"
TC_S2_CLAIM = "2026-08-12T00:07:00Z"
TC_S6_BLOCK = "2026-08-12T00:07:30Z"
TC_S3_BEFORE_CEILING = "2026-08-12T00:10:00Z"   # well under RUN_STARTED + 3600s
TC_S3_PAST_CEILING = "2026-08-12T02:00:00Z"     # past RUN_STARTED + 3600s (01:01:00Z)

TC_PACKET_ORDER = (
    "p-timeout", "p-output", "p-fallback", "p-design", "p-human",
    "p-ceiling-a", "p-ceiling-b",
)


def _enroll_combined_packets(tmp_path, name):
    """All seven packets, enrolled in ONE ``enroll_packets`` call, in the
    exact order this combined scenario's own real claim sequence needs:
    ``select_next`` always returns the minimum ``(enqueue_seq, packet_id)``
    among currently-eligible packets, so every packet whose own turn is
    reached through the normal ``run_once`` claim path must already be
    terminal, paused-with-the-indefinite-sentinel-set (see the module-level
    note above), or not yet enrolled by the time an earlier-enqueued
    packet's own turn comes. ``p-design`` (scenario 2) is enrolled
    immediately before ``p-human`` (scenario 6): once scenario 2's pause is
    folded, ``recovery.py``'s indefinite-sentinel mechanism correctly
    excludes it from every later ``select_next`` call, so scenario 6's own
    packet is reached next, in ordinary enrollment order, exactly like
    every other packet here.
    """
    from harness_coordinator.v1.enroll import enroll_packets
    from test_o3_p5_commissioning import _registered_packet, _registered_worktrees
    from test_o3_p5_review import TRUSTED_REVIEWER, _write_manifest, _write_trust_roots

    base = tmp_path / name
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,))

    worktrees = _registered_worktrees(base, *TC_PACKET_ORDER)
    packets = {}
    for packet_id, worktree in zip(TC_PACKET_ORDER, worktrees):
        packet = _registered_packet(packet_id, worktree)
        changed = False
        if packet_id in ("p-timeout", "p-output"):
            # Same override, same reason, as scenario 4/5's own
            # ``_enroll_real_packet_with_retry_limit`` above: the O3-level
            # packet ``budgets.retry_limit`` (not the O5 plan row's) is what
            # ``classify_runtime._finish_attempt`` reads to decide
            # requeue-vs-quarantine, and sonnet reassignment needs
            # disabling once retry_limit drops below 2.
            packet["budgets"]["retry_limit"] = 1
            packet["sonnet_reassignment_allowed"] = False
            changed = True
        elif packet_id == "p-human":
            packet["human_stop_conditions"] = ["deployment"]
            changed = True
        if changed:
            packet["packet_sha256"] = compute_sha256(
                canonical_bytes(packet, omit={"packet_sha256"}))
        packets[packet_id] = packet

    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, TC_ENROLL,
                   [packets[pid] for pid in TC_PACKET_ORDER])
    return base, state_root, packets


def _combined_plan(packets):
    rows = [
        _plan_row(packets["p-timeout"], "implementation", attempt_limit=2,
                 retry_limit=1, command_timeout_seconds=2, output_bytes=65536),
        _plan_row(packets["p-output"], "implementation", attempt_limit=2,
                 retry_limit=1, command_timeout_seconds=15, output_bytes=1024),
        _plan_row(packets["p-fallback"], "implementation"),
        _plan_row(packets["p-design"], "design_judgment"),
        _plan_row(packets["p-human"], "implementation"),
        _plan_row(packets["p-ceiling-a"], "implementation"),
        _plan_row(packets["p-ceiling-b"], "implementation"),
    ]
    # dependencies are empty for every row (_plan_row reads them straight off
    # each packet's own dependency_ids, never set for any of these seven).
    assert all(row["dependencies"] == [] for row in rows)
    return _build_plan("plan-o5-commissioning-combined", rows, _default_routes())


def _inject_restart(state_root, plan, now, worker_adapters=None):
    """A restart at a durable boundary, per this dispatch's own instruction:
    drop every in-memory reference to prior state, reopen the state root
    fresh (nothing here reuses a previously-fetched ``events``/``folded``
    object -- ``run_once`` itself always re-reads the journal from disk),
    and call ``run_once`` again with a freshly-built ``trusted_process_
    context`` (``_context()`` returns a new dict every call, never a stored
    one) -- relying only on durably persisted journal state. This is the
    exact mechanism this codebase's own restart tests already establish
    (``test_o5_hard_stops.py``'s ``test_a_restart_after_an_effective_stop_
    is_deterministic_and_claims_nothing`` and neighbors): there is no
    coordinator object held across calls to drop in the first place, so an
    extra, independently-constructed ``run_once`` call IS what "a fresh
    process resuming from durable state alone" looks like in this design.

    ``worker_adapters``, when supplied, mirrors
    ``test_a_restart_after_a_pending_stop_completes_recovery_before_effect``'s
    own established convention: an adapter is the CALLER's own worker-
    launching configuration, not journal-derived state, so a resuming
    process re-supplies it exactly as a live coordinator daemon would
    reload its own configuration on restart -- re-supplying it is not
    reusing in-memory coordinator state, only a caller-side input, same as
    ``execution_plan`` itself already is on every restart call in this
    suite.
    """
    return run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), now,
                    execution_plan=plan, worker_adapters=worker_adapters)


# Every packet still eligible for automatic ``select_next`` selection at any
# of these boundaries declares non-empty ``writable_paths`` (``_packet``'s
# own fixture default), so an adapter-free injected call is always either a
# genuine, safe no-op ("awaiting_worker_adapter" -- the budget/human-
# authority gate is skipped entirely without an adapter, so nothing new is
# ever persisted) or, at the one boundary already past the graceful stop,
# "graceful_stopped" -- confirmed per-boundary below, not assumed uniform.
#
# **One boundary is a genuine, real-behavior exception, found live (not
# assumed): "post_attempt_started_ceiling".** At that point p-ceiling-a has
# an OPEN, durably-claimed attempt with no captured outcome yet. An
# adapter-free restart call there is NOT a no-op: ``resolve_open_attempts``
# (``classify_runtime.py``) runs unconditionally on every ``run_once`` call
# and treats "RUNNING with no ``attempt_outcome.json``" as case (c) of its
# own documented three-case contract -- "the worker was still running or the
# coordinator died before capture" -- and infra-retries the packet back to
# READY, consuming one of its two bounded attempts for nothing (confirmed
# live: a first draft of this boundary without an adapter reproducibly left
# p-ceiling-a at ``READY`` with ``attempts_started == 1`` instead of
# ``REVIEW``, silently changing the rest of the run). This is CORRECT,
# documented coordinator behavior for a genuine crash-before-invocation
# (``test_an_attempt_whose_worker_never_ran_still_resolves_before_the_stop``
# proves the identical mechanism deliberately), not a defect -- it simply
# means an adapter-free call is the wrong way to model "the SAME worker
# invocation resumes" for this one boundary. The fix, matching
# ``test_a_restart_after_a_pending_stop_completes_recovery_before_effect``'s
# own established convention exactly: re-supply the SAME adapter on the
# injected call, so the resumed attempt is genuinely (and correctly)
# invoked and finished, rather than infra-retried away. Even WITH the
# adapter supplied, the OVERALL returned status for this one boundary is
# still "awaiting_worker_adapter", not "completed_attempt": resuming an
# already-open RUNNING attempt happens in ``_run_iteration``'s own
# top-of-function resume section, which never sets the returned ``status``
# itself -- the call falls through afterward to its own fresh
# ``select_next`` pick (p-design, still forever eligible, no adapter
# supplied for IT in this call), and THAT decides the final status. The
# genuine resumption is confirmed via a direct, fresh read of p-ceiling-a's
# own folded state instead (asserted right after the injected call below),
# exactly like "post_verdict_deposit_fallback"'s own side-effect-not-status
# pattern.
_EXPECTED_RESTART_STATUS = {
    "post_quarantine_timeout": "awaiting_worker_adapter",
    "post_attempt_finished_fallback": "awaiting_worker_adapter",
    "post_verdict_deposit_fallback": "awaiting_worker_adapter",
    "post_resolve_accepted": "awaiting_worker_adapter",
    "post_packet_paused_provider": "awaiting_worker_adapter",
    "post_attempt_started_ceiling": "awaiting_worker_adapter",
    "post_graceful_stop": "graceful_stopped",
}

BOUNDARY_LABELS = tuple(_EXPECTED_RESTART_STATUS)


def _drive_combined_scenario(tmp_path, name, restart_after=None):
    """Drive all seven scenario-1-6 packets through ONE combined execution
    plan/run to Task 5 Step 2 item 7's own six-way disposition split.

    ``restart_after`` is ``None`` (the clean baseline) or one of
    ``BOUNDARY_LABELS``: immediately after that boundary's event becomes
    durable (confirmed via a fresh read, never a held Python reference), one
    extra ``run_once`` restart call (``_inject_restart``) is driven before
    the real sequence continues, proving the rest of the run needs nothing
    but the journal to finish identically.

    Returns ``(state_root, plan, packets, report)``.
    """
    from harness_coordinator.v1.coordinator import claim_and_start_attempt

    base, state_root, packets = _enroll_combined_packets(tmp_path, name)
    plan = _combined_plan(packets)
    _bind(state_root, plan, at=TC_BIND)

    injected = {}

    def _maybe_restart(label, now, worker_adapters=None):
        if label != restart_after:
            return
        result = _inject_restart(state_root, plan, now, worker_adapters=worker_adapters)
        assert result["status"] == _EXPECTED_RESTART_STATUS[label], (label, result["status"])
        injected[label] = result

    # -- Scenario 4: p-timeout, retry_limit=1, two bounded command-timeout
    # kills -> QUARANTINED. --------------------------------------------------
    code_timeout = _child_grandchild_worker_code()
    marker_t1 = base / "pg-marker-timeout-1.txt"
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S4_A1,
                execution_plan=plan,
                worker_adapters={packets["p-timeout"]["packet_id"]:
                                 _process_group_probe_adapter(code_timeout, marker_t1)})
    assert r["status"] == "completed_attempt"
    assert _folded(state_root)[packets["p-timeout"]["packet_id"]]["state"] == "READY"
    child1, grandchild1 = _read_marker_pids(marker_t1)
    _assert_pid_gone(child1)
    _assert_pid_gone(grandchild1)

    marker_t2 = base / "pg-marker-timeout-2.txt"
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S4_A2,
                execution_plan=plan,
                worker_adapters={packets["p-timeout"]["packet_id"]:
                                 _process_group_probe_adapter(code_timeout, marker_t2)})
    assert r["status"] == "completed_attempt"
    assert _folded(state_root)[packets["p-timeout"]["packet_id"]]["state"] == "QUARANTINED"
    child2, grandchild2 = _read_marker_pids(marker_t2)
    _assert_pid_gone(child2)
    _assert_pid_gone(grandchild2)

    _maybe_restart("post_quarantine_timeout", TC_S4_A2)

    # -- Scenario 5: p-output, retry_limit=1, two bounded output-cap kills
    # -> QUARANTINED. ---------------------------------------------------------
    code_output = _child_grandchild_worker_code(
        extra_body="sys.stdout.write('x' * 200000)\nsys.stdout.flush()")
    marker_o1 = base / "pg-marker-output-1.txt"
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S5_A1,
                execution_plan=plan,
                worker_adapters={packets["p-output"]["packet_id"]:
                                 _process_group_probe_adapter(code_output, marker_o1)})
    assert r["status"] == "completed_attempt"
    assert _folded(state_root)[packets["p-output"]["packet_id"]]["state"] == "READY"
    child3, grandchild3 = _read_marker_pids(marker_o1)
    _assert_pid_gone(child3)
    _assert_pid_gone(grandchild3)

    marker_o2 = base / "pg-marker-output-2.txt"
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S5_A2,
                execution_plan=plan,
                worker_adapters={packets["p-output"]["packet_id"]:
                                 _process_group_probe_adapter(code_output, marker_o2)})
    assert r["status"] == "completed_attempt"
    assert _folded(state_root)[packets["p-output"]["packet_id"]]["state"] == "QUARANTINED"
    child4, grandchild4 = _read_marker_pids(marker_o2)
    _assert_pid_gone(child4)
    _assert_pid_gone(grandchild4)

    # -- Scenario 1: p-fallback, primary exhausted -> fallback -> ACCEPTED. --
    _record_capacity(state_root, "opencode", "kimi-k2.7-code",
                     "ALLOWANCE_EXHAUSTED", observed_at=TC_OBS_PRIMARY)

    marker_fb = base / "marker-fallback.txt"
    adapter_fb = _adapter_for(packets["p-fallback"], marker_fb,
                              provider="openai", model="gpt-5.6-terra")
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S1_CLAIM,
                execution_plan=plan,
                worker_adapters={packets["p-fallback"]["packet_id"]: adapter_fb})
    assert r["status"] == "completed_attempt"
    assert _folded(state_root)[packets["p-fallback"]["packet_id"]]["state"] == "REVIEW"

    _maybe_restart("post_attempt_finished_fallback", TC_S1_CLAIM)

    session_fb = attempt_session_id(RUN_ID, packets["p-fallback"]["packet_id"], 1)
    result_fb = _commission_result(packets["p-fallback"], session_fb, attempt=1)
    result_fb["worker"]["provider"] = "openai"
    result_fb["worker"]["model"] = "gpt-5.6-terra"
    result_fb["result_sha256"] = compute_sha256(canonical_bytes(result_fb, omit={"result_sha256"}))
    _deposit(state_root, packets["p-fallback"]["packet_id"], 1,
            _review(_verdict(packets["p-fallback"], result_fb)))

    _maybe_restart("post_verdict_deposit_fallback", TC_S1_CLAIM)

    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S1_RESOLVE,
                execution_plan=plan)
    # The verdict may already have been resolved by a "post_verdict_deposit_
    # fallback" restart injection above (resolve_pending_reviews is
    # unconditional on every run_once call) -- an idempotent, correct
    # outcome, not a bug, so the ACCEPT is looked for across BOTH calls
    # rather than assumed to land on this specific one.
    reviews_seen = list(r.get("reviews", []))
    if "post_verdict_deposit_fallback" in injected:
        reviews_seen += injected["post_verdict_deposit_fallback"].get("reviews", [])
    assert any(rv.get("packet_id") == packets["p-fallback"]["packet_id"]
              and rv.get("verdict") == "ACCEPT" for rv in reviews_seen)
    assert _folded(state_root)[packets["p-fallback"]["packet_id"]]["state"] == "ACCEPTED"

    _maybe_restart("post_resolve_accepted", TC_S1_RESOLVE)

    # -- Scenario 2: p-design, Fable exhausted + Sol disabled -> paused. ------
    _record_capacity(state_root, "anthropic", "claude-fable-5",
                     "ALLOWANCE_EXHAUSTED", observed_at=TC_OBS_FABLE)
    marker_ds = base / "marker-design.txt"
    adapter_ds = _adapter_for(packets["p-design"], marker_ds)
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S2_CLAIM,
                execution_plan=plan,
                worker_adapters={packets["p-design"]["packet_id"]: adapter_ds})
    assert r["status"] == "no_capable_model"
    assert _folded(state_root)[packets["p-design"]["packet_id"]]["state"] == "READY"
    paused_design = [e for e in _events(state_root) if e["event_type"] == "PACKET_PAUSED"
                     and e["packet_id"] == packets["p-design"]["packet_id"]]
    assert len(paused_design) == 1
    assert paused_design[0]["payload"]["packet_pause"]["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"

    _maybe_restart("post_packet_paused_provider", TC_S2_CLAIM)

    # -- Scenario 6: p-human, blocked before claim. A genuinely SECOND real
    # run_once call: scenario 2's own pause (just above) already set
    # p-design's earliest_next_attempt_at to recovery.py's indefinite-pause
    # sentinel, which _is_eligible excludes for any real "now" -- so
    # select_next correctly reaches p-human here, in ordinary enrollment
    # order, through the ordinary automatic claim path (see the module-level
    # note above). ---------------------------------------------------------
    marker_hu = base / "marker-human.txt"
    adapter_hu = _adapter_for(packets["p-human"], marker_hu)
    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S6_BLOCK,
                execution_plan=plan,
                worker_adapters={packets["p-human"]["packet_id"]: adapter_hu})
    assert r["status"] == "plan_stopped"
    assert r.get("packet_id") == packets["p-human"]["packet_id"]
    assert r.get("stop_reason_code") == "HUMAN_AUTHORITY_REQUIRED"
    paused_human = [e for e in _events(state_root) if e["event_type"] == "PACKET_PAUSED"
                    and e["packet_id"] == packets["p-human"]["packet_id"]]
    assert len(paused_human) == 1
    assert paused_human[0]["payload"]["packet_pause"]["reason_code"] == "HUMAN_AUTHORITY_REQUIRED"
    assert _folded(state_root)[packets["p-human"]["packet_id"]]["state"] == "READY"
    # Confirms the sentinel mechanism itself, not just its effect: p-design
    # stays excluded from this and every later call, never re-paused.
    assert len([e for e in _events(state_root) if e["event_type"] == "PACKET_PAUSED"
               and e["packet_id"] == packets["p-design"]["packet_id"]]) == 1

    # -- Scenario 3: p-ceiling-a / p-ceiling-b, queue safety ceiling. ---------
    events = _events(state_root)
    folded = _folded(state_root)
    claim_and_start_attempt(
        state_root=state_root, state_root_id=STATE_ROOT_ID, journal_events=events,
        packet_id=packets["p-ceiling-a"]["packet_id"],
        packet=folded[packets["p-ceiling-a"]["packet_id"]],
        coordinator_id=COORDINATOR_ID, run_id=RUN_ID, trusted_process_context=_context(),
        now=TC_S3_BEFORE_CEILING)
    assert _folded(state_root)[packets["p-ceiling-a"]["packet_id"]]["open_attempt"] == 1

    marker_ca = base / "marker-ceiling-a.txt"
    adapter_ca = _adapter_for(packets["p-ceiling-a"], marker_ca)

    # See _EXPECTED_RESTART_STATUS's own note above: this one boundary needs
    # the same adapter re-supplied, or resolve_open_attempts legitimately
    # (and correctly) infra-retries the open, not-yet-invoked attempt away
    # instead of resuming it.
    _maybe_restart("post_attempt_started_ceiling", TC_S3_BEFORE_CEILING,
                   worker_adapters={packets["p-ceiling-a"]["packet_id"]: adapter_ca})
    if "post_attempt_started_ceiling" in injected:
        # The genuine side effect this boundary's whole point is to prove:
        # the resumed attempt reached a real durable outcome (REVIEW), not
        # an infra-retry back to READY -- confirmed via a fresh read, not
        # inferred from the injected call's own "status" field (see
        # _EXPECTED_RESTART_STATUS's note on why that field reflects the
        # LATER select_next pick instead).
        assert _folded(state_root)[packets["p-ceiling-a"]["packet_id"]]["state"] == "REVIEW"
        assert _folded(state_root)[packets["p-ceiling-a"]["packet_id"]]["open_attempt"] is None

    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S3_PAST_CEILING,
                execution_plan=plan,
                worker_adapters={packets["p-ceiling-a"]["packet_id"]: adapter_ca})
    assert r["status"] == "graceful_stopped"
    stop_types = [e["event_type"] for e in _events(state_root)
                 if e["event_type"] in ("GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE")]
    assert stop_types == ["GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    assert _folded(state_root)[packets["p-ceiling-a"]["packet_id"]]["state"] == "REVIEW"
    assert _folded(state_root)[packets["p-ceiling-b"]["packet_id"]]["state"] == "READY"
    assert not any(e["event_type"] == "ATTEMPT_STARTED"
                  and e["packet_id"] == packets["p-ceiling-b"]["packet_id"]
                  for e in _events(state_root))

    _maybe_restart("post_graceful_stop", TC_S3_PAST_CEILING)

    session_ca = attempt_session_id(RUN_ID, packets["p-ceiling-a"]["packet_id"], 1)
    result_ca = _commission_result(packets["p-ceiling-a"], session_ca, attempt=1)
    _deposit(state_root, packets["p-ceiling-a"]["packet_id"], 1,
            _review(_verdict(packets["p-ceiling-a"], result_ca)))

    r = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(), TC_S3_PAST_CEILING,
                execution_plan=plan)
    assert r["status"] == "graceful_stopped"
    reviews_seen_ca = list(r.get("reviews", []))
    if "post_graceful_stop" in injected:
        reviews_seen_ca += injected["post_graceful_stop"].get("reviews", [])
    assert any(rv.get("packet_id") == packets["p-ceiling-a"]["packet_id"]
              and rv.get("verdict") == "ACCEPT" for rv in reviews_seen_ca)
    assert _folded(state_root)[packets["p-ceiling-a"]["packet_id"]]["state"] == "ACCEPTED"
    assert _folded(state_root)[packets["p-ceiling-b"]["packet_id"]]["state"] == "READY"
    assert not any(e["event_type"] == "ATTEMPT_STARTED"
                  and e["packet_id"] == packets["p-ceiling-b"]["packet_id"]
                  for e in _events(state_root))

    if restart_after is not None:
        assert restart_after in injected, (
            "restart_after=%r named a boundary this driver never reaches" % restart_after)

    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID,
        "report-o5-commissioning-combined-%s" % name, TC_S3_PAST_CEILING)
    return state_root, plan, packets, report


_EXPECTED_COMBINED_TOTALS = {
    "planned": 7, "attempted": 4,
    "accepted": 2, "resting_revise": 0, "quarantined": 2,
    "paused_provider": 1, "blocked_human": 1, "never_started": 1,
}


@pytest.fixture(scope="module")
def _combined_baseline(tmp_path_factory):
    """The clean, no-restart-injected baseline (Step 1 of this dispatch's
    own instructions), built once and reused as the comparison target for
    every restart-boundary variant below -- so each variant is checked
    against the ACTUAL baseline report this session produced, not merely a
    literal expected-value copy of it."""
    tmp_path = tmp_path_factory.mktemp("o5-combined-baseline")
    _, _, packets, report = _drive_combined_scenario(
        tmp_path, "combined-baseline", restart_after=None)
    return packets, report


def test_combined_seven_packet_plan_baseline_reaches_documented_totals(_combined_baseline):
    """Step 1: the combined 7-packet plan, run once with NO restart
    injected, reaches exactly the plan doc's own Task 5 Step 2 item 7
    totals -- the exact ``assert totals == {...}`` block from
    ``docs/superpowers/plans/2026-08-11-o5-budgets-hard-stops.md`` (plus
    the ``attempted`` key, per this dispatch's own note, matching how
    ``test_o5_reconciliation.py``'s own six-way fixture already reports
    it) -- confirming the plan doc's packet-to-bucket mapping holds
    unchanged once all seven scenarios share one plan and one run.
    """
    packets, report = _combined_baseline
    totals = report["plan_totals"]
    assert totals == _EXPECTED_COMBINED_TOTALS
    assert report["all_invariants_passed"] is True

    by_id = {row["packet_id"]: row for row in report["packets"]}
    assert by_id[packets["p-timeout"]["packet_id"]]["disposition"] == "quarantined"
    assert by_id[packets["p-output"]["packet_id"]]["disposition"] == "quarantined"
    assert by_id[packets["p-fallback"]["packet_id"]]["disposition"] == "accepted"
    assert by_id[packets["p-design"]["packet_id"]]["disposition"] == "paused_provider"
    assert by_id[packets["p-human"]["packet_id"]]["disposition"] == "blocked_human"
    assert by_id[packets["p-ceiling-a"]["packet_id"]]["disposition"] == "accepted"
    assert by_id[packets["p-ceiling-b"]["packet_id"]]["disposition"] == "never_started"

    assert sorted(report["attempted_packet_ids"]) == sorted([
        packets["p-timeout"]["packet_id"], packets["p-output"]["packet_id"],
        packets["p-fallback"]["packet_id"], packets["p-ceiling-a"]["packet_id"],
    ])


@pytest.mark.parametrize("boundary", BOUNDARY_LABELS)
def test_combined_seven_packet_plan_restart_matrix_matches_baseline(
    tmp_path, _combined_baseline, boundary,
):
    """Step 2: a restart injected at each of seven structurally distinct
    durable boundaries -- post-ATTEMPT_FINISHED (scenario 1's claim),
    post-verdict-deposit and post-resolve for scenario 1's ACCEPT,
    post-PACKET_PAUSED for scenario 2's provider pause,
    post-ATTEMPT_STARTED (scenario 3's pre-ceiling open claim),
    post-GRACEFUL_STOP (scenario 3's ceiling crossing), and
    post-ATTEMPT_FINISHED for scenario 4's quarantine -- each reruns the
    WHOLE combined scenario from a fresh state root/run, with one extra,
    independently-constructed ``run_once`` restart call inserted right
    after that boundary's event is confirmed durable. The FINAL
    reconciliation totals, dispositions, ``all_invariants_passed``, and
    attempted-packet membership must be byte-identical to the real
    no-restart baseline every time.
    """
    _, baseline_report = _combined_baseline
    _, _, packets, report = _drive_combined_scenario(
        tmp_path, "combined-restart-%s" % boundary, restart_after=boundary)

    assert report["all_invariants_passed"] is True
    assert report["plan_totals"] == baseline_report["plan_totals"]
    assert sorted(report["attempted_packet_ids"]) == sorted(baseline_report["attempted_packet_ids"])

    baseline_pairs = sorted((row["packet_id"], row["disposition"])
                            for row in baseline_report["packets"])
    variant_pairs = sorted((row["packet_id"], row["disposition"])
                           for row in report["packets"])
    assert variant_pairs == baseline_pairs
