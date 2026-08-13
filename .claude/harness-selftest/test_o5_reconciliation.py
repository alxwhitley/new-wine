"""O5 Task 5 Step 1: reconciliation identity RED/GREEN tests.

Proves two things about Task 5's O5 reconciliation extension
(``build_reconciliation_report``'s new ``plan_totals``/row-extension/
``all_invariants_passed`` fields, wired through ``reconcile.py`` and
``harness_contracts.v1.reconciliation.compute_reconciliation``):

(1) the terminal-disposition partition is a real identity over authenticated
    plan membership -- ``planned == accepted+resting_revise+quarantined+
    paused_provider+blocked_human+never_started`` -- proven on a genuinely
    commissioned, hand-built multi-packet run exercising all six buckets;
    and

(2) reconciliation fails closed (``all_invariants_passed is False``) under
    thirteen independent tamper scenarios -- both the top-level and nested
    ``all_invariants_passed`` fields are asserted, and asserted to agree
    (O5 review round 3 finding D1). Several of these ride on pre-existing
    O2/O3/O5 safety machinery this step deliberately does not duplicate
    (documented per-case below); the rest exercise this step's own new O5
    checks (plan-scope membership, plan-level attempt-budget overrun,
    forged evidence references, and the ``attempt_route_not_in_plan``
    detection backstop -- which checks EVERY plan-member packet's recorded
    attempt identities against the plan's route table, not only ones that
    went through the legacy reassignment lane, requires a matched hop to be
    both ``enabled`` and validly qualified, and requires the hop be
    actually REACHABLE via the plan's fallback_to chain, not merely present
    in the raw declared list -- mirroring the live route selector's own
    eligibility gate exactly). No test in this file weakens or bypasses any
    existing check to make its own case pass.

No mocking of the mechanism under test: every fixture is a real, disposable
on-disk state root with a real journal (and, where relevant, a real bound
execution plan), read back through the real ``build_reconciliation_report``.
The one exception (``duplicate_disposition``) monkeypatches
``harness_coordinator.v1.reconcile.compute_reconciliation`` to inject a
duplicated packet row directly into the invariant engine's own input -- the
only way to observe that shape at all, since ``_fold_journal`` returns
packets keyed by a dict (structurally incapable of holding two entries for
one packet_id) and a real duplicate ``PACKET_ENROLLED`` is refused before it
ever reaches the fold (already covered by
``test_o3_json_schemas.py::TestReconciliationIntegrityFixtures``).
"""

import copy
import os

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.reconcile import build_reconciliation_report
from harness_coordinator.v1.recovery import make_graceful_stop_effective, request_graceful_stop
from harness_coordinator.v1.recovery import _direct_state_root_path
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import append_journal, read_journal

from test_o3_reconciliation import (
    _make_event,
    _new_state_root,
    _packet_payload as _o3_packet_payload,
    _run_payload,
    _write_journal,
)
from test_o5_budget_runtime import _default_routes as _o5_canonical_default_routes


STATE_ROOT_ID = "srid-1"
COORDINATOR_ID = "coord-1"
RUN_ID = "run-1"
T0 = "2026-08-12T00:00:00Z"
T_EARLIER = "2026-08-11T00:00:00Z"


# ---------------------------------------------------------------------------
# Shared fixture-construction helpers
# ---------------------------------------------------------------------------


def _route(route_id, provider, model_id, enabled=True, fallback_to=None, reasoning="high"):
    return {
        "route_id": route_id, "provider": provider, "model_id": model_id,
        "minimum_reasoning": reasoning, "enabled": enabled,
        "qualification_id": "qual-" + route_id, "fallback_to": fallback_to,
    }


def _routes():
    """Deliberately NO anthropic-provider hop anywhere -- the
    ``route_not_in_plan`` case depends on this route table never
    authorizing a Sonnet-family implementer."""
    return {
        "implementation": [
            _route("impl-primary", "opencode", "kimi-k2.7-code", fallback_to="impl-terra"),
            _route("impl-terra", "openai", "gpt-5.6-terra"),
        ],
    }


def _plan_row(packet_id, packet_sha256, capability_class="implementation",
              attempt_limit=3, retry_limit=2, revision_limit=2, dependencies=None):
    return {
        "packet_id": packet_id, "packet_sha256": packet_sha256,
        "dependencies": list(dependencies or []), "capability_class": capability_class,
        "budgets": {
            "attempt_limit": attempt_limit, "retry_limit": retry_limit,
            "revision_limit": revision_limit, "turn_limit": 12,
            "command_timeout_seconds": 60, "output_bytes": 4096,
        },
    }


def _plan(plan_id, rows, routes=None, human_stop_categories=None, wall_clock=3600):
    plan = {
        "schema_version": 1, "plan_id": plan_id, "plan_sha256": "",
        "packets": rows, "routes": routes if routes is not None else _routes(),
        "provider_backoff": {"max_retries": 3, "base_delay_seconds": 30, "max_delay_seconds": 300},
        "wall_clock_safety_seconds": wall_clock,
        "human_stop_categories": human_stop_categories or ["deployment"],
    }
    plan["plan_sha256"] = compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))
    return plan


def _packet_sha256(packet_id):
    return compute_sha256(canonical_bytes({"packet_id": packet_id}))


def _publish_plan(state_root, plan):
    # ``_new_state_root`` (test_o3_reconciliation.py) uses ``tempfile.mkdtemp()``
    # directly, which on macOS returns the unresolved ``/var/...`` alias --
    # fine for the raw ``open()`` calls that module uses throughout, but
    # ``open_state_root`` requires the exact same lexical form
    # ``build_reconciliation_report`` itself normalizes internally via
    # ``_direct_state_root_path`` (see that function's own docstring: it
    # substitutes ONLY the macOS ``/var`` -> ``/private/var`` system alias,
    # deliberately not a full ``realpath``).
    with open_state_root(_direct_state_root_path(state_root)) as handle:
        handle.publish(("plans", "%s.json" % plan["plan_id"]), canonical_bytes(plan))


class _Journal:
    """Bookkeeping wrapper: tracks seq/prev_event so each fixture builder
    doesn't hand-thread them through every call."""

    def __init__(self):
        self.events = []

    @property
    def prev(self):
        return self.events[-1] if self.events else None

    def add(self, event_type, **kwargs):
        kwargs.setdefault("event_at", T0)
        seq = (self.prev["seq"] + 1) if self.prev else 1
        event = _make_event(seq, event_type, prev_event=self.prev, **kwargs)
        self.events.append(event)
        return event


def _run_started(builder):
    return builder.add("RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None,
    })


def _bind_plan(builder, plan):
    return builder.add("EXECUTION_PLAN_BOUND", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": None, "report": None,
        "execution_plan": {
            "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"],
            "plan_path": "plans/%s.json" % plan["plan_id"], "packet_count": len(plan["packets"]),
        },
    })


def _enroll(builder, packet_id, enqueue_seq, lane="kimi_implementation", retry_limit=2,
            dependency_ids=None, sonnet_reassignment_allowed=False):
    body = _o3_packet_payload(packet_id, enqueue_seq, lane=lane, retry_limit=retry_limit)
    body["sonnet_reassignment_allowed"] = sonnet_reassignment_allowed
    if dependency_ids:
        body["dependency_ids"] = list(dependency_ids)
    to_state = "BLOCKED" if body["dependency_ids"] else "READY"
    return builder.add(
        "PACKET_ENROLLED", packet_id=packet_id, intent_id="enroll-%s" % packet_id,
        to_state=to_state, cause="enrollment",
        payload={"packet": body, "attempt": None, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _attempt_payload(attempt=1, provider="opencode", model="kimi-k2.7-code", lane="kimi_implementation"):
    return {
        "attempt": attempt, "lane": lane,
        "worker": {"worker_id": "w1", "session_id": "s1", "provider": provider, "model": model},
        "claim_sha256": None, "worktree_path": None,
    }


def _start(builder, packet_id, attempt=1, **worker_kwargs):
    return builder.add(
        "ATTEMPT_STARTED", packet_id=packet_id, intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _attempt_payload(attempt, **worker_kwargs), "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _classification_completed():
    return {
        "attempt_class": "COMPLETED_PENDING_REVIEW", "quarantine_reason": None,
        "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {"exit_code": 0, "signal": None, "timed_out": False,
                             "result_present": True, "result_valid": True, "error_codes": []},
    }


def _classification_quarantine():
    return {
        "attempt_class": "CONTRACT_INVALID", "quarantine_reason": "contract_invalid",
        "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {"exit_code": 1, "signal": None, "timed_out": False,
                             "result_present": False, "result_valid": False, "error_codes": ["SCHEMA_INVALID"]},
    }


def _classification_infra_retry():
    return {
        "attempt_class": "INFRA_RETRYABLE", "quarantine_reason": None,
        "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {"exit_code": 1, "signal": None, "timed_out": False,
                             "result_present": False, "result_valid": False, "error_codes": ["INFRA"]},
    }


def _classification_reassignment():
    return {
        "attempt_class": "PROVIDER_EXHAUSTED", "quarantine_reason": None,
        "human_required_reasons": [], "result_sha256": None, "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {"exit_code": 1, "signal": None, "timed_out": False,
                             "result_present": False, "result_valid": False, "error_codes": []},
    }


def _finish(builder, packet_id, attempt, from_state, to_state, cause, classification):
    return builder.add(
        "ATTEMPT_FINISHED", packet_id=packet_id, intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state=from_state, to_state=to_state, cause=cause,
        payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                 "classification": classification, "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )


def _verdict(builder, packet_id, attempt, to_state, cause):
    return builder.add(
        "VERDICT_RECORDED", packet_id=packet_id, intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state="REVIEW", to_state=to_state, cause=cause,
        payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _requeue(builder, packet_id, revise_cycle):
    return builder.add(
        "STATE_TRANSITION", packet_id=packet_id, intent_id="revision-%s-%d" % (packet_id, revise_cycle),
        from_state="REVISE", to_state="READY", cause="revision_requeued",
        payload={"packet": None, "attempt": None, "artifacts": [], "classification": None,
                 "transition_detail": {"satisfied_by": [], "source_verdict": None, "revise_cycle": revise_cycle},
                 "recovery": None, "run": None, "report": None},
    )


def _packet_pause(builder, packet_id, reason_code, capability_class="implementation",
                   evidence_ids=None, next_eligible_at=None):
    from harness_coordinator.v1.budget_runtime import budget_event_payload
    payload = budget_event_payload("PACKET_PAUSED", {
        "reason_code": reason_code, "capability_class": capability_class,
        "next_eligible_at": next_eligible_at, "evidence_ids": sorted(evidence_ids or []),
    })
    return builder.add("PACKET_PAUSED", packet_id=packet_id, payload=payload)


def _accept_packet(builder, packet_id, enqueue_seq, attempt=1):
    _enroll(builder, packet_id, enqueue_seq)
    _start(builder, packet_id, attempt)
    _finish(builder, packet_id, attempt, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(builder, packet_id, attempt, "ACCEPTED", "verdict_accept")


def _quarantine_packet(builder, packet_id, enqueue_seq, attempt=1):
    _enroll(builder, packet_id, enqueue_seq)
    _start(builder, packet_id, attempt)
    _finish(builder, packet_id, attempt, "RUNNING", "QUARANTINED", "contract_invalid", _classification_quarantine())


def _rest_in_revise(builder, packet_id, enqueue_seq, retry_limit=1):
    """Two attempts, both revised, resting in REVISE exactly at its O3
    retry_limit cap -- same shape as test_o3_reconciliation.py's own
    ``test_attempt_budget_exhausted_flagged_for_revise_resting_packet_at_cap``."""
    _enroll(builder, packet_id, enqueue_seq, retry_limit=retry_limit)
    for attempt in (1, 2):
        if attempt > 1:
            _requeue(builder, packet_id, attempt - 1)
        _start(builder, packet_id, attempt)
        _finish(builder, packet_id, attempt, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
        _verdict(builder, packet_id, attempt, "REVISE", "verdict_revise")


def _report(state_root, report_id="report-1", now=T0):
    return build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, report_id, now,
    )


# ---------------------------------------------------------------------------
# (1) Terminal-partition identity, on a genuinely commissioned six-way run.
# ---------------------------------------------------------------------------


def _commissioned_events(tmp_path):
    """A single real, disposable state root exercising all six terminal
    dispositions plus a healthy ``attempted`` cross-check: one packet per
    bucket, all plan members, zero foreign packets, zero violations."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [
        _plan_row("pkt-accepted", _packet_sha256("pkt-accepted")),
        _plan_row("pkt-revise", _packet_sha256("pkt-revise")),
        _plan_row("pkt-quarantined", _packet_sha256("pkt-quarantined")),
        _plan_row("pkt-paused-provider", _packet_sha256("pkt-paused-provider")),
        _plan_row("pkt-blocked-human", _packet_sha256("pkt-blocked-human")),
        _plan_row("pkt-never-started", _packet_sha256("pkt-never-started")),
    ]
    plan = _plan("plan-commissioned", rows)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _accept_packet(b, "pkt-accepted", 2)
    _rest_in_revise(b, "pkt-revise", 3)
    _quarantine_packet(b, "pkt-quarantined", 4)
    _enroll(b, "pkt-paused-provider", 5)
    _packet_pause(b, "pkt-paused-provider", "NO_CAPABLE_MODEL_AVAILABLE")
    _enroll(b, "pkt-blocked-human", 6)
    _packet_pause(b, "pkt-blocked-human", "HUMAN_AUTHORITY_REQUIRED")
    _enroll(b, "pkt-never-started", 7)

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return state_root


def test_terminal_partition_equals_authenticated_plan_membership(tmp_path):
    state_root = _commissioned_events(tmp_path)
    report = _report(state_root)
    totals = report["plan_totals"]

    assert totals["planned"] == sum(totals[key] for key in (
        "accepted", "resting_revise", "quarantined", "paused_provider",
        "blocked_human", "never_started"))

    # Strengthen beyond the bare sum identity -- confirm every bucket this
    # fixture was built to exercise actually landed exactly where expected,
    # not merely that the six counts happen to add up (which a report that
    # is broken for an unrelated reason could still satisfy vacuously with
    # every bucket at zero).
    assert totals == {
        "planned": 6, "attempted": 3,
        "accepted": 1, "resting_revise": 1, "quarantined": 1,
        "paused_provider": 1, "blocked_human": 1, "never_started": 1,
    }
    assert sorted(report["attempted_packet_ids"]) == [
        "pkt-accepted", "pkt-quarantined", "pkt-revise",
    ]
    assert report["all_invariants_passed"] is True
    assert report["reconciliation"]["all_invariants_passed"] is True
    assert report["all_invariants_passed"] == report["reconciliation"]["all_invariants_passed"]

    from harness_contracts.v1.reconciliation import validate_reconciliation_report
    result = validate_reconciliation_report(report)
    assert result["valid"], result["errors"]

    # Per-row disposition/extension sanity, spot-checked on two rows.
    by_id = {row["packet_id"]: row for row in report["packets"]}
    assert by_id["pkt-accepted"]["disposition"] == "accepted"
    assert by_id["pkt-paused-provider"]["disposition"] == "paused_provider"
    assert by_id["pkt-paused-provider"]["stop_reasons"] == ["NO_CAPABLE_MODEL_AVAILABLE"]
    assert by_id["pkt-blocked-human"]["disposition"] == "blocked_human"
    assert by_id["pkt-never-started"]["disposition"] == "never_started"
    assert by_id["pkt-accepted"]["plan_id"] == "plan-commissioned"
    assert by_id["pkt-accepted"]["capability_class"] == "implementation"


# ---------------------------------------------------------------------------
# (1b) Regression: a stale PACKET_PAUSED record must never outrank a live
# re-claim -- reviewer-identified defect in ``_o5_disposition``'s check
# ordering.
# ---------------------------------------------------------------------------


def test_backoff_paused_then_reclaimed_packet_is_indeterminate_not_paused(tmp_path):
    """A packet backoff-paused with a REAL (non-indefinite) ``next_eligible_at``
    window, then successfully re-claimed and carried on to a live/pending
    attempt (RUNNING or REVIEW), must never report ``paused_provider``.

    ``recovery.py``'s ``PACKET_PAUSED`` fold branch is schema-forbidden from
    transitioning packet state, so the OLD pause event is still in the
    journal even though the packet has since been claimed -- and its
    ``next_eligible_at`` is a real backoff window here, not the indefinite
    sentinel a natural-expiry-less pause would get, so this is exactly the
    "paused, then the window passed, then re-claimed" shape a real run
    produces. The correct disposition is the genuine indeterminate
    ``None`` -- with ``all_invariants_passed`` correctly reporting False
    and ``plan_disposition_indeterminate`` present -- never a stale pause
    outranking the live claim."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [
        _plan_row("pkt-review", _packet_sha256("pkt-review")),
        _plan_row("pkt-running", _packet_sha256("pkt-running")),
    ]
    plan = _plan("plan-backoff-reclaimed", rows)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)

    # pkt-review: paused with a real backoff window, then reclaimed and
    # carried all the way to a pending review verdict (REVIEW).
    _enroll(b, "pkt-review", 2)
    _packet_pause(b, "pkt-review", "PROVIDER_BACKOFF_PENDING",
                   next_eligible_at="2026-08-12T00:30:00Z")
    _start(b, "pkt-review", 1)
    _finish(b, "pkt-review", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed())

    # pkt-running: same shape, but the packet is still mid-attempt (RUNNING)
    # at report time.
    _enroll(b, "pkt-running", 3)
    _packet_pause(b, "pkt-running", "PROVIDER_BACKOFF_PENDING",
                   next_eligible_at="2026-08-12T00:30:00Z")
    _start(b, "pkt-running", 1)

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    by_id = {row["packet_id"]: row for row in report["packets"]}
    assert by_id["pkt-review"]["state"] == "REVIEW"
    assert by_id["pkt-review"]["disposition"] is None
    assert by_id["pkt-running"]["state"] == "RUNNING"
    assert by_id["pkt-running"]["disposition"] is None

    assert report["all_invariants_passed"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert report["all_invariants_passed"] == report["reconciliation"]["all_invariants_passed"]
    indeterminate_pids = {
        item["packet_id"] for item in report["attention_required"]
        if item["code"] == "plan_disposition_indeterminate"
    }
    assert indeterminate_pids == {"pkt-review", "pkt-running"}


# ---------------------------------------------------------------------------
# (1c) Regression: the top-level all_invariants_passed mirror must never
# disagree with reconciliation.all_invariants_passed -- O5 review round 3
# finding D1.
# ---------------------------------------------------------------------------


def test_all_invariants_passed_top_level_field_agrees_with_nested_on_workspace_isolation_violation(tmp_path):
    """Reproduces the reviewer's own live probe byte-for-byte in shape: an
    O4-declaring ``RUN_STARTED`` (``contract_versions.workspace_evidence ==
    1``) whose one packet is claimed, completed, and reaches ACCEPTED with
    NO ``WORKSPACE_BASELINE_RECORDED`` or ``WORKSPACE_POSTFLIGHT_RECORDED``
    evidence anywhere in the journal -- a genuine O4 workspace-isolation
    violation (``reconcile.py``'s own pre-existing
    ``_workspace_evidence_attention``, not something this step invented).

    Before this fix, ``reconciliation.all_invariants_passed`` was already
    correctly overridden to False for exactly this case (a non-empty
    ``workspace_attention`` list), but the TOP-LEVEL ``all_invariants_passed``
    mirror was computed BEFORE that override, in a separate expression, and
    was never re-synced to it -- so the two fields disagreed: a schema-valid
    report could read ``all_invariants_passed: True`` at the top level while
    its own nested ``reconciliation.all_invariants_passed`` said False. The
    fix (``harness_contracts.v1.reconciliation.compute_reconciliation``) now
    folds workspace_attention into the SAME single computation that feeds
    BOTH fields, so they cannot diverge by construction -- proven here on
    the exact violation class that exposed the drift, not merely asserted
    in the abstract."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-o4-baseline-missing", rows)
    _publish_plan(state_root, plan)

    b = _Journal()
    o4_run_payload = dict(_run_payload())
    o4_run_payload["contract_versions"] = dict(o4_run_payload["contract_versions"], workspace_evidence=1)
    b.add("RUN_STARTED", payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": o4_run_payload, "report": None,
    })
    _bind_plan(b, plan)
    # Claimed, completed, ACCEPTED -- via the ordinary _accept_packet
    # helper, which never records any WORKSPACE_* evidence itself. Combined
    # with the O4-declaring RUN_STARTED above, this is a real, detected
    # violation, not a synthetic one.
    _accept_packet(b, "pkt-a", 2)
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)

    report = _report(state_root)

    attention_codes = {item["code"] for item in report["attention_required"]}
    assert attention_codes == {
        "integration_human_required", "unverified_invariants",
        "workspace_baseline_missing", "workspace_postflight_missing",
    }

    assert report["reconciliation"]["all_invariants_passed"] is False
    # THE regression under test: before the fix, this stayed True even
    # though every finding above, and the nested field right below it,
    # correctly said the run was NOT clean.
    assert report["all_invariants_passed"] is False
    assert report["all_invariants_passed"] == report["reconciliation"]["all_invariants_passed"]

    from harness_contracts.v1.reconciliation import validate_reconciliation_report
    result = validate_reconciliation_report(report)
    assert result["valid"], result["errors"]


# ---------------------------------------------------------------------------
# (2) Fail-closed under tamper -- twelve independent scenarios.
# ---------------------------------------------------------------------------


def _tamper_missing_member(tmp_path):
    """A plan declares two members; only one is ever enrolled. Exercises
    this step's OWN new check (``plan_member_never_enrolled``) -- the
    phantom-root fold this report is built from never runs recovery.py's
    real plan-scope retro-check, so nothing else would catch this."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [
        _plan_row("pkt-a", _packet_sha256("pkt-a")),
        _plan_row("pkt-b", _packet_sha256("pkt-b")),
    ]
    plan = _plan("plan-missing-member", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _accept_packet(b, "pkt-a", 2)
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_duplicate_disposition(tmp_path, monkeypatch):
    """Injects a duplicated packet row directly into
    ``compute_reconciliation``'s own input -- the only way to observe this
    shape at all (see the module docstring). Exercises the PRE-EXISTING
    I4 duplicate_packet_ids invariant (harness_contracts.v1.reconciliation),
    proving this step's new O5 totals math coexists with it correctly
    rather than masking it."""
    import harness_coordinator.v1.reconcile as reconcile_module

    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-duplicate", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _accept_packet(b, "pkt-a", 2)
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)

    real_compute = reconcile_module.compute_reconciliation

    def _duplicating_compute(fold_data):
        tampered = dict(fold_data)
        packets = list(fold_data.get("packets") or [])
        if packets:
            packets = packets + [copy.deepcopy(packets[0])]
        tampered["packets"] = packets
        return real_compute(tampered)

    monkeypatch.setattr(reconcile_module, "compute_reconciliation", _duplicating_compute)
    return _report(state_root)


def _tamper_foreign_packet(tmp_path):
    """A packet enrolled under this run's journal that is not a member of
    the bound plan at all. DETECTION BACKSTOP: build_reconciliation_report's
    own fold runs against a phantom seal directory, never a real state
    root, so recovery.py's live plan-scope retro-check never fires on this
    exact fold -- this step's own new check closes that gap here."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-foreign", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _accept_packet(b, "pkt-a", 2)
    _enroll(b, "pkt-foreign", 3)
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_route_not_in_plan(tmp_path):
    """A packet reassigned kimi_implementation -> sonnet_implementation via
    the legacy lane mechanism (ATTEMPT_FINISHED, cause=
    provider_exhausted_reassignment), then ACTUALLY INVOKED under
    anthropic/claude-sonnet-4-5 for its next attempt (the real target
    identity, read straight from that attempt's own durable
    ATTEMPT_STARTED event, like any other entry in ``row["route_history"]``
    -- the legacy reassignment lane is no longer treated specially by
    ``attempt_route_not_in_plan``, see ``_o5_hop_authorized``), then
    completes normally to ACCEPTED -- while the plan's own route table for
    its capability_class authorizes no anthropic-provider hop at all, real
    target included. Without this step's new check, this packet would land
    cleanly in ``accepted`` with all_invariants_passed True -- proving the
    failure below is attributable to THIS check, not an accident of an
    otherwise-broken fixture. (Prior to the target-granular fix, this
    fixture's reassigned attempt used a non-anthropic provider/model that
    happened to already be a real plan-authorized hop for a different
    purpose -- which the OLD provider-only check never even looked at, so
    it passed for the wrong reason. The reassigned attempt now genuinely
    invokes anthropic/claude-sonnet-4-5, so this remains a real positive
    case under the corrected, target-granular check too -- see the
    ``route_not_in_plan_realistic_route_table`` parametrized case below for
    the case this fixture alone no longer covers: a REAL anthropic hop
    present in the route table, for a DIFFERENT model than the one
    actually invoked; and see ``attempt_route_not_in_plan_no_reassignment``
    for the case this fixture ALSO doesn't cover: an out-of-plan identity
    reached with no legacy reassignment involved at all.)"""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-route-violation", rows)  # _routes() has no anthropic hop
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2, sonnet_reassignment_allowed=True)
    _start(b, "pkt-a", 1, provider="opencode", model="kimi-k2.7-code", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "READY", "provider_exhausted_reassignment", _classification_reassignment())
    _start(b, "pkt-a", 2, provider="anthropic", model="claude-sonnet-4-5", lane="sonnet_implementation")
    _finish(b, "pkt-a", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 2, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_fallback_cycle(tmp_path):
    """A plan whose route table contains a genuine fallback cycle,
    published and bound WITHOUT going through
    ``execution_plan.bind_execution_plan`` (which would refuse it at write
    time) -- simulating a corrupted/tampered plan artifact reaching a real
    state root. ``validate_execution_plan``'s own pre-existing cycle
    detection is what catches this, surfaced through this step's new
    plan-authentication error path (``plan_scope["authentication_error"]``)
    rather than a second, parallel cycle detector."""
    state_root = _new_state_root(STATE_ROOT_ID)
    plan = _plan("plan-cycle", [])
    plan["routes"]["implementation"][0]["fallback_to"] = "impl-terra"
    plan["routes"]["implementation"][1]["fallback_to"] = "impl-primary"
    plan["plan_sha256"] = compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_attempt_over_limit(tmp_path):
    """The plan's own O5 attempt_limit is 1; the folded packet has 2 real
    ATTEMPT_STARTED events (an infra retry, then a completion) -- legal
    under the packet's O3-level retry_limit (2), so nothing pre-existing
    (I9/I10, both O3-level) flags this. Only this step's new plan-level
    budget check does."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"), attempt_limit=1)]
    plan = _plan("plan-attempt-over-limit", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2, retry_limit=2)
    _start(b, "pkt-a", 1)
    _finish(b, "pkt-a", 1, "RUNNING", "READY", "infra_retry", _classification_infra_retry())
    _start(b, "pkt-a", 2)
    _finish(b, "pkt-a", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 2, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_stop_then_claim(tmp_path):
    """One more claim recorded after a run's graceful stop is already
    effective -- the one-extra-claim failure Task 3's hard-stop machinery
    exists to prevent. PRE-EXISTING check:
    ``recovery._fold_journal``'s own ``GRACEFUL_STOP_CLAIM_AFTER_STOP``
    guard (not duplicated here) is what catches this; this fixture only
    proves ``build_reconciliation_report`` still surfaces that as a failed
    report (via its existing ``fold_failed`` attention path) rather than
    letting the exception escape or silently reporting a healthy run."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("p1", _packet_sha256("p1")), _plan_row("p2", _packet_sha256("p2"))]
    plan = _plan("plan-stop-then-claim", rows)
    _publish_plan(state_root, plan)
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "p1", 2)
    _enroll(b, "p2", 3)
    _write_journal(journal_path, b.events)

    events, torn = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    assert torn is None
    events = request_graceful_stop(
        journal_path, lock_path, events, plan, COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
        T0, "QUEUE_SAFETY_CEILING_REACHED", [])
    events = make_graceful_stop_effective(
        journal_path, lock_path, events, COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, T0, plan=plan)

    # One more claim, appended directly to the journal file -- bypassing
    # every live pre-claim gate (coordinator.py's
    # ``_assert_no_graceful_stop`` is never invoked by this fixture at
    # all), simulating the exact corrupted-journal shape the fold-level
    # guard must catch independent of whether the live gate ran.
    illegal_claim = _make_event(
        events[-1]["seq"] + 1, "ATTEMPT_STARTED", prev_event=events[-1], packet_id="p2",
        intent_id="attempt-p2-1", from_state="READY", to_state="RUNNING", cause="claim_committed",
        event_at=T0,
        payload={"packet": None, "attempt": _attempt_payload(1), "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    with open(journal_path, "ab") as f:
        f.write(canonical_bytes(illegal_claim) + b"\n")

    return _report(state_root)


def _tamper_forged_provider_evidence(tmp_path):
    """A PACKET_PAUSED record cites an evidence_id that does not
    correspond to any real event anywhere in the journal -- fabricated
    provenance for a capacity refusal. Only this step's new check
    (nothing pre-existing cross-references PACKET_PAUSED.evidence_ids
    against real journal event identities) catches this."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-forged-evidence", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    _packet_pause(b, "pkt-a", "NO_CAPABLE_MODEL_AVAILABLE", evidence_ids=["evt-does-not-exist"])
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_clock_regression(tmp_path):
    """A journal whose final event's ``event_at`` precedes the previous
    event's -- a chronology violation. PRE-EXISTING check:
    ``read_journal``'s own final-line torn-tail leniency (design 3.3,
    already covered by test_o3_reconciliation.py's own truncated-tail
    tests) drops it and marks ``journal_chain_valid`` False; this fixture
    proves that behaviour composes correctly with a bound O5 plan rather
    than being bypassed by it."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-clock-regression", rows)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    journal_path = os.path.join(state_root, "journal.ndjson")
    _write_journal(journal_path, b.events)

    regressed = _make_event(
        b.events[-1]["seq"] + 1, "PACKET_ENROLLED", prev_event=b.events[-1], packet_id="pkt-b",
        intent_id="enroll-pkt-b", to_state="READY", cause="enrollment", event_at=T_EARLIER,
        payload={"packet": _o3_packet_payload("pkt-b", 3), "attempt": None, "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    with open(journal_path, "ab") as f:
        f.write(canonical_bytes(regressed) + b"\n")

    return _report(state_root)


def _tamper_route_not_in_plan_realistic_route_table(tmp_path):
    """Regression: the ORIGINAL O5 check (``any(hop.provider ==
    "anthropic" ...)``) was provider-granular, not target-granular, and was
    provably inert under the O5 test suite's OWN canonical multi-hop route
    table -- ``test_o5_budget_runtime.py``'s ``_default_routes()``, reused
    verbatim here (not a hand-rolled copy), whose ``implementation`` route
    table already includes a real anthropic hop
    (``anthropic/claude-sonnet-4-5``). Under that original check, ANY
    anthropic model reached by a legacy reassignment would satisfy
    ``any(provider == "anthropic")`` and sail through undetected -- even
    one the plan never actually authorized. This packet's reassigned
    attempt actually invokes ``anthropic/claude-fable-9``, a model this
    route table never lists for ``implementation`` at all (only
    ``claude-sonnet-4-5`` is listed there). The fixed, target-granular
    check (exact ``(provider, model_id)`` hop match -- see
    ``_o5_hop_authorized``, which now reads the identity straight off
    ``row["route_history"]`` rather than through the removed,
    reassignment-only ``_o5_reassignment_target_identity`` helper) must
    still fire here; the original provider-granular check could not have,
    proving this is a real strengthening, not just a fixture-specific
    artifact of ``test_o5_reconciliation.py``'s own deliberately-
    anthropic-free ``_routes()``."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-route-violation-realistic", rows, routes=_o5_canonical_default_routes())
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2, sonnet_reassignment_allowed=True)
    _start(b, "pkt-a", 1, provider="opencode", model="kimi-k2.7-code", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "READY", "provider_exhausted_reassignment", _classification_reassignment())
    _start(b, "pkt-a", 2, provider="anthropic", model="claude-fable-9", lane="sonnet_implementation")
    _finish(b, "pkt-a", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 2, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_attempt_route_not_in_plan_no_reassignment(tmp_path):
    """O5 review round 2 finding NEW-1's exact reviewer-demonstrated gap
    (PROBE4): a plan-member packet whose durable ``ATTEMPT_STARTED``
    records a ``(provider, model_id)`` the bound plan's route table for
    that capability class never lists at all -- with NO legacy
    ``kimi_implementation`` -> ``sonnet_implementation`` reassignment
    involved anywhere (``sonnet_reassignment_allowed`` stays at its default
    ``False``, the attempt's own ``lane`` stays ``kimi_implementation``
    throughout, and no ``provider_exhausted_reassignment`` cause ever
    fires). Before this step's general ``attempt_route_not_in_plan`` check,
    the check living here was gated behind
    ``reassignment_used and lane == "sonnet_implementation"`` and produced
    ZERO violations for exactly this shape -- the packet reached ACCEPTED
    with a clean report, matching the reviewer's own live probe
    (``codes=set() invariants=True``) byte-for-byte: same provider
    (``anthropic``), same model (``claude-opus-9``), same
    ``route_history`` shape. The fixed, general check must now flag this."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-attempt-route-no-reassignment", rows)  # _routes() has no anthropic hop
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    _start(b, "pkt-a", 1, provider="anthropic", model="claude-opus-9", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 1, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_attempt_route_disabled_hop(tmp_path):
    """O5 review round 2 finding NEW-2: the plan's route table for this
    packet's capability class DOES list a hop with the exact ``(provider,
    model_id)`` the real ``ATTEMPT_STARTED`` invoked -- but that hop is
    ``enabled: False``. ``budget_runtime.select_capable_route`` (the live
    route selector) would never actually choose a disabled hop
    (``if hop.get("enabled") is not True: continue``), so an attempt that
    reached this identity anyway must not read as plan-authorized just
    because the identity happens to appear SOMEWHERE in the route table --
    ``_o5_hop_authorized`` must require ``enabled is True`` exactly like
    the live selector does, not merely a listed provider/model_id pair."""
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = _routes()
    routes["implementation"] = routes["implementation"] + [
        _route("impl-disabled", "deepseek", "deepseek-v4", enabled=False),
    ]
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-attempt-route-disabled-hop", rows, routes=routes)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    _start(b, "pkt-a", 1, provider="deepseek", model="deepseek-v4", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 1, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


def _tamper_attempt_route_unreachable_via_fallback_chain(tmp_path):
    """O5 review round 3 finding D3: ``_o5_hop_authorized`` iterated the
    RAW declared route list, not the live selector's actual reachable set.
    ``budget_runtime.select_capable_route`` walks
    ``budget_runtime._ordered_hops`` -- starting at the capability class's
    first DECLARED hop, following each hop's explicit ``fallback_to`` (or,
    where none is declared, the next hop by array position). A hop the
    chain never actually reaches is never selectable by the live
    coordinator, however ``enabled`` and validly qualified it looks in
    isolation.

    Route table: ``[primary(fallback_to=terra), skipped(deepseek), terra]``.
    The reachability chain from ``primary`` is ``[primary, terra]`` --
    ``primary``'s own ``fallback_to`` jumps straight past ``skipped`` to
    ``terra``, and nothing else in the table ever points at ``skipped``, so
    it is declared but genuinely unreachable. An attempt that actually
    invoked ``deepseek/deepseek-v4`` (exactly ``skipped``'s identity) must
    still be flagged ``attempt_route_not_in_plan`` -- before this fix, it
    would have read as authorized purely because ``skipped`` is ``enabled``
    and carries a valid ``qualification_id``, with no reachability check at
    all."""
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "implementation": [
            _route("impl-primary", "opencode", "kimi-k2.7-code", fallback_to="impl-terra"),
            _route("impl-skipped", "deepseek", "deepseek-v4"),
            _route("impl-terra", "openai", "gpt-5.6-terra"),
        ],
    }
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-attempt-route-unreachable-hop", rows, routes=routes)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    _start(b, "pkt-a", 1, provider="deepseek", model="deepseek-v4", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 1, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    return _report(state_root)


_TAMPER_BUILDERS = {
    "missing_member": lambda tmp_path, monkeypatch: _tamper_missing_member(tmp_path),
    "duplicate_disposition": _tamper_duplicate_disposition,
    "foreign_packet": lambda tmp_path, monkeypatch: _tamper_foreign_packet(tmp_path),
    "route_not_in_plan": lambda tmp_path, monkeypatch: _tamper_route_not_in_plan(tmp_path),
    "route_not_in_plan_realistic_route_table":
        lambda tmp_path, monkeypatch: _tamper_route_not_in_plan_realistic_route_table(tmp_path),
    "attempt_route_not_in_plan_no_reassignment":
        lambda tmp_path, monkeypatch: _tamper_attempt_route_not_in_plan_no_reassignment(tmp_path),
    "attempt_route_disabled_hop":
        lambda tmp_path, monkeypatch: _tamper_attempt_route_disabled_hop(tmp_path),
    "attempt_route_unreachable_via_fallback_chain":
        lambda tmp_path, monkeypatch: _tamper_attempt_route_unreachable_via_fallback_chain(tmp_path),
    "fallback_cycle": lambda tmp_path, monkeypatch: _tamper_fallback_cycle(tmp_path),
    "attempt_over_limit": lambda tmp_path, monkeypatch: _tamper_attempt_over_limit(tmp_path),
    "stop_then_claim": lambda tmp_path, monkeypatch: _tamper_stop_then_claim(tmp_path),
    "forged_provider_evidence": lambda tmp_path, monkeypatch: _tamper_forged_provider_evidence(tmp_path),
    "clock_regression": lambda tmp_path, monkeypatch: _tamper_clock_regression(tmp_path),
}


def _report_for_tamper(tmp_path, tamper, monkeypatch):
    return _TAMPER_BUILDERS[tamper](tmp_path, monkeypatch)


@pytest.mark.parametrize("tamper", [
    "missing_member", "duplicate_disposition", "foreign_packet",
    "route_not_in_plan", "route_not_in_plan_realistic_route_table",
    "attempt_route_not_in_plan_no_reassignment", "attempt_route_disabled_hop",
    "attempt_route_unreachable_via_fallback_chain",
    "fallback_cycle", "attempt_over_limit",
    "stop_then_claim", "forged_provider_evidence", "clock_regression",
])
def test_reconciliation_fails_closed_on_o5_tamper(tmp_path, tamper, monkeypatch):
    report = _report_for_tamper(tmp_path, tamper, monkeypatch)
    # O5 review round 3 finding D1: asserting the top-level field ALONE is
    # not sufficient -- it is not authoritative for every real violation
    # class (see the workspace-isolation regression test above, where the
    # top-level mirror stayed True while this nested field correctly said
    # False). Assert both, and that they agree, on every tamper scenario in
    # this matrix -- per the reviewer's own recommendation, a real
    # strengthening of this existing coverage, not new scope.
    assert report["reconciliation"]["all_invariants_passed"] is False
    assert report["all_invariants_passed"] is False
    assert report["all_invariants_passed"] == report["reconciliation"]["all_invariants_passed"]


def test_attempt_route_not_in_plan_is_target_granular_not_provider_granular(tmp_path):
    """Companion positive control for the regression above: an EXACT hop
    match (the reassigned attempt's real invoked identity matches a real
    plan-authorized, ENABLED, validly-qualified hop's (provider, model_id)
    precisely) must NOT flag ``attempt_route_not_in_plan`` -- proving the
    strengthened, generalized check isn't simply flagging every
    anthropic-lane reassignment (or every attempt at all) regardless of
    which model was actually used, only ones the plan didn't authorize.
    Scoped narrowly to THIS check: this fixture never publishes a real
    ``reassignments/pkt-a.json`` artifact through
    ``reassignment_runtime.publish_reassignment`` (it fabricates the
    journal directly, like every other fixture in this file), so it
    separately, and correctly, also trips the PRE-EXISTING
    ``preserved_evidence_mismatches`` check -- unrelated to this test's
    subject and not weakened or suppressed here; this test asserts only
    that ``attempt_route_not_in_plan`` specifically is absent, not that
    the whole report is clean."""
    state_root = _new_state_root(STATE_ROOT_ID)
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-route-authorized-realistic", rows, routes=_o5_canonical_default_routes())
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2, sonnet_reassignment_allowed=True)
    _start(b, "pkt-a", 1, provider="opencode", model="kimi-k2.7-code", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "READY", "provider_exhausted_reassignment", _classification_reassignment())
    _start(b, "pkt-a", 2, provider="anthropic", model="claude-sonnet-4-5", lane="sonnet_implementation")
    _finish(b, "pkt-a", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 2, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    violation_codes = {
        item["code"] for item in report["attention_required"]
        if item.get("packet_id") == "pkt-a"
    }
    assert "attempt_route_not_in_plan" not in violation_codes


def test_attempt_route_reachable_via_fallback_chain_is_still_authorized(tmp_path):
    """Companion positive control for the regression above
    (``attempt_route_unreachable_via_fallback_chain``): a hop that IS
    reachable via the plan's ``fallback_to`` chain -- not the capability
    class's first declared hop, but the one it explicitly points to --
    must still read as authorized. Proves the D3 reachability fix does not
    over-restrict authorization to only ``hops[0]``; it excludes only hops
    the chain genuinely never reaches, not every non-primary hop."""
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "implementation": [
            _route("impl-primary", "opencode", "kimi-k2.7-code", fallback_to="impl-terra"),
            _route("impl-skipped", "deepseek", "deepseek-v4"),
            _route("impl-terra", "openai", "gpt-5.6-terra"),
        ],
    }
    rows = [_plan_row("pkt-a", _packet_sha256("pkt-a"))]
    plan = _plan("plan-reachable-fallback-hop", rows, routes=routes)
    _publish_plan(state_root, plan)
    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-a", 2)
    _start(b, "pkt-a", 1, provider="openai", model="gpt-5.6-terra", lane="kimi_implementation")
    _finish(b, "pkt-a", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed())
    _verdict(b, "pkt-a", 1, "ACCEPTED", "verdict_accept")
    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    violation_codes = {
        item["code"] for item in report["attention_required"]
        if item.get("packet_id") == "pkt-a"
    }
    assert "attempt_route_not_in_plan" not in violation_codes


# ---------------------------------------------------------------------------
# (3) Route authorization is run-scoped (O5 review round 3 finding D2): each
# ATTEMPT_STARTED must be checked against the plan that was ACTUALLY BOUND
# for THAT event's own run_id -- never against whichever plan happens to be
# bound for the run currently being reconciled. Plan authorization is
# inherently run-scoped (``bound_execution_plan_for_run`` selects by
# run_id), and a state root can legitimately see several runs, each with
# its own bound plan (a plan amendment mid-project) -- ``test_o3_p5_resume.py``
# already exercises multiple runs against one state root as a real,
# supported pattern.
# ---------------------------------------------------------------------------


def _run_started_as(builder, run_id):
    return builder.add("RUN_STARTED", run_id=run_id, payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": _run_payload(), "report": None,
    })


def _bind_plan_as(builder, plan, run_id):
    return builder.add("EXECUTION_PLAN_BOUND", run_id=run_id, payload={
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": None, "report": None,
        "execution_plan": {
            "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"],
            "plan_path": "plans/%s.json" % plan["plan_id"], "packet_count": len(plan["packets"]),
        },
    })


def _enroll_as(builder, packet_id, enqueue_seq, run_id, retry_limit=2):
    body = _o3_packet_payload(packet_id, enqueue_seq, lane="kimi_implementation", retry_limit=retry_limit)
    body["sonnet_reassignment_allowed"] = False
    return builder.add(
        "PACKET_ENROLLED", run_id=run_id, packet_id=packet_id, intent_id="enroll-%s" % packet_id,
        to_state="READY", cause="enrollment",
        payload={"packet": body, "attempt": None, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _start_as(builder, packet_id, attempt, run_id, provider, model):
    return builder.add(
        "ATTEMPT_STARTED", run_id=run_id, packet_id=packet_id,
        intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": _attempt_payload(attempt, provider=provider, model=model),
                 "artifacts": [], "classification": None, "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )


def _finish_as(builder, packet_id, attempt, from_state, to_state, cause, classification, run_id):
    return builder.add(
        "ATTEMPT_FINISHED", run_id=run_id, packet_id=packet_id,
        intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state=from_state, to_state=to_state, cause=cause,
        payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                 "classification": classification, "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )


def _verdict_as(builder, packet_id, attempt, to_state, cause, run_id):
    return builder.add(
        "VERDICT_RECORDED", run_id=run_id, packet_id=packet_id,
        intent_id="attempt-%s-%d" % (packet_id, attempt),
        from_state="REVIEW", to_state=to_state, cause=cause,
        payload={"packet": None, "attempt": _attempt_payload(attempt), "artifacts": [],
                 "classification": None, "transition_detail": None, "recovery": None, "run": None, "report": None},
    )


def _report_for_run(state_root, run_id, report_id="report-1", now=T0):
    return build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, run_id, report_id, now,
    )


def test_route_authorization_is_scoped_to_each_attempts_own_run_not_the_reconciled_run(tmp_path):
    """O5 review round 3 finding D2, reproducing the reviewer's own live
    probe shape: a state root with TWO runs, each binding a DIFFERENT plan
    for the same capability class -- a realistic mid-project plan
    amendment, not a corrupted/hostile shape.

    Plan A (bound under run-1) authorizes opencode/kimi-k2.7-code (``X``)
    for the ``implementation`` capability class. Plan B (bound under
    run-2, the amendment) does NOT authorize ``X`` at all (it lists only a
    different provider/model). Both packets below are members of BOTH
    plans (an amendment, not a removal of either).

    ``pkt-a`` is enrolled and attempted ONLY under run-1, using ``X`` --
    fully legitimate under run-1's OWN bound plan (Plan A).
    ``pkt-b`` is enrolled and attempted ONLY under run-2, using the SAME
    ``X`` -- genuinely NOT authorized under run-2's OWN bound plan (Plan
    B); this is the drift a real amendment can produce.

    Before the fix: reconciling run-2 checked ``pkt-a``'s run-1 attempt
    against Plan B (whichever plan is bound for the CURRENT run being
    reconciled) and would wrongly flag it -- a false positive against a
    fully legitimate attempt. Reconciling run-1 checked ``pkt-b``'s run-2
    attempt against Plan A and would wrongly clear it (``X`` IS authorized
    under Plan A) -- a false negative against a genuinely unauthorized
    attempt. After the fix, each attempt is judged only by the plan that
    was actually bound for ITS OWN run, so both reports agree and are both
    correct, regardless of which run is being reconciled.
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    plan_a_routes = _routes()  # authorizes opencode/kimi-k2.7-code (X)
    plan_b_routes = {
        "implementation": [
            _route("impl-b-primary", "anthropic", "claude-sonnet-4-5"),
        ],
    }
    plan_a = _plan("plan-amend-a", [_plan_row("pkt-a", _packet_sha256("pkt-a")),
                                     _plan_row("pkt-b", _packet_sha256("pkt-b"))],
                    routes=plan_a_routes)
    plan_b = _plan("plan-amend-b", [_plan_row("pkt-a", _packet_sha256("pkt-a")),
                                     _plan_row("pkt-b", _packet_sha256("pkt-b"))],
                    routes=plan_b_routes)
    _publish_plan(state_root, plan_a)
    _publish_plan(state_root, plan_b)

    b = _Journal()
    _run_started_as(b, "run-1")
    _bind_plan_as(b, plan_a, "run-1")
    _enroll_as(b, "pkt-a", 2, "run-1")
    _start_as(b, "pkt-a", 1, "run-1", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-a", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed(), "run-1")
    _verdict_as(b, "pkt-a", 1, "ACCEPTED", "verdict_accept", "run-1")

    _run_started_as(b, "run-2")
    _bind_plan_as(b, plan_b, "run-2")
    _enroll_as(b, "pkt-b", 3, "run-2")
    _start_as(b, "pkt-b", 1, "run-2", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-b", 1, "RUNNING", "REVIEW", "result_recorded", _classification_completed(), "run-2")
    _verdict_as(b, "pkt-b", 1, "ACCEPTED", "verdict_accept", "run-2")

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)

    report_run1 = _report_for_run(state_root, "run-1", report_id="report-run-1")
    report_run2 = _report_for_run(state_root, "run-2", report_id="report-run-2")

    def _codes_for(report, packet_id):
        return {
            item["code"] for item in report["attention_required"]
            if item.get("packet_id") == packet_id
        }

    # pkt-a's run-1 attempt is legitimate under ITS OWN run's plan (A) --
    # never flagged, whichever run is being reconciled. The run-2 case is
    # the false-positive fix under direct test: before the fix, this
    # would have been (wrongly) flagged when reconciling run-2, since old
    # code checked it against Plan B (run-2's plan) instead of Plan A
    # (run-1's own plan, the one it actually ran under).
    assert "attempt_route_not_in_plan" not in _codes_for(report_run1, "pkt-a")
    assert "attempt_route_not_in_plan" not in _codes_for(report_run2, "pkt-a")

    # pkt-b's run-2 attempt is genuinely NOT authorized under ITS OWN run's
    # plan (B) -- correctly flagged in run-2's own report, and (the
    # false-negative fix under direct test) also correctly flagged when
    # reconciling run-1, since pkt-b is a plan-A member too and the check
    # must resolve run-2's OWN plan for that entry rather than silently
    # passing it under Plan A (which DOES authorize the same identity).
    assert "attempt_route_not_in_plan" in _codes_for(report_run1, "pkt-b")
    assert "attempt_route_not_in_plan" in _codes_for(report_run2, "pkt-b")

    # Attribution sanity: the flagged violation genuinely names pkt-b's own
    # run and identity, not a garbled/aggregated message.
    pkt_b_detail = next(
        item["detail"] for item in report_run2["attention_required"]
        if item.get("packet_id") == "pkt-b" and item["code"] == "attempt_route_not_in_plan"
    )
    assert "run-2" in pkt_b_detail
    assert "opencode/kimi-k2.7-code" in pkt_b_detail


# ---------------------------------------------------------------------------
# (4) Plan-level attempt-budget checking is also run-scoped (O5 review round
# 4 finding A): each real ATTEMPT_STARTED counts toward the packet's
# GLOBAL, cumulative attempts_started total (never reset per run -- the same
# convention budget_runtime._journal_usage/evaluate_preclaim use), but
# whether a GIVEN attempt was within budget is judged against the
# attempt_limit of the plan that was ACTUALLY BOUND for THAT attempt's own
# run_id -- never against whichever plan happens to be bound for the run
# currently being reconciled. Same false-positive shape as D2 (finding #7
# above), same fix approach.
# ---------------------------------------------------------------------------


def test_plan_attempt_budget_is_scoped_to_each_attempts_own_run_not_the_reconciled_run(tmp_path):
    """O5 review round 4 finding A, reproducing the reviewer's own scenario:
    a packet (``pkt-a``) legitimately uses 2 of the 3 attempts allowed by
    the plan bound to the run it actually ran under (run-1, ``attempt_limit
    =3``). A LATER run (run-2) amends the plan for the same packet down to
    ``attempt_limit=1`` -- a real, legitimate, forward-looking policy
    tightening -- but grants ``pkt-a`` no further attempts under run-2 at
    all (exactly what a live coordinator would do: ``evaluate_preclaim``
    would refuse a THIRD claim under the new plan, but it does not, and
    must not, retroactively judge the first two).

    Before the fix: reconciling run-2 compared ``pkt-a``'s cumulative
    ``attempts_started`` (2, unchanged since run-1 -- the fold accumulates
    across the WHOLE journal regardless of run_id) against run-2's
    stricter ``attempt_limit`` (1) and wrongly flagged
    ``plan_attempt_budget_exceeded`` -- a false positive against attempts
    that were fully legitimate under the plan they actually happened
    under. After the fix, each individual attempt is judged only against
    the plan bound to the run it actually happened under (run-1's own
    Plan A, ``attempt_limit=3``), so neither run's report flags ``pkt-a``.

    ``pkt-b`` is the companion positive control (same pairing pattern as
    D2's own test above), proving detection genuinely still fires under
    run-scoping, not merely stopped firing altogether: it is enrolled AND
    attempted twice, entirely under run-2's own stricter plan (Plan B,
    ``attempt_limit=1``) -- its second attempt genuinely exceeds the
    budget its OWN governing run's plan allowed, at the time it happened,
    and must still be flagged in BOTH runs' reports (reconciling run-1
    must not silently clear it just because Plan A -- which never
    governed these attempts -- would have allowed 3).
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    plan_a = _plan("plan-budget-a", [
        _plan_row("pkt-a", _packet_sha256("pkt-a"), attempt_limit=3),
        _plan_row("pkt-b", _packet_sha256("pkt-b"), attempt_limit=3),
    ])
    plan_b = _plan("plan-budget-b", [
        _plan_row("pkt-a", _packet_sha256("pkt-a"), attempt_limit=1),
        _plan_row("pkt-b", _packet_sha256("pkt-b"), attempt_limit=1),
    ])
    _publish_plan(state_root, plan_a)
    _publish_plan(state_root, plan_b)

    b = _Journal()
    _run_started_as(b, "run-1")
    _bind_plan_as(b, plan_a, "run-1")
    _enroll_as(b, "pkt-a", 2, "run-1", retry_limit=2)
    _start_as(b, "pkt-a", 1, "run-1", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-a", 1, "RUNNING", "READY", "infra_retry", _classification_infra_retry(), "run-1")
    _start_as(b, "pkt-a", 2, "run-1", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-a", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed(), "run-1")
    _verdict_as(b, "pkt-a", 2, "ACCEPTED", "verdict_accept", "run-1")

    _run_started_as(b, "run-2")
    _bind_plan_as(b, plan_b, "run-2")
    _enroll_as(b, "pkt-b", 3, "run-2", retry_limit=2)
    _start_as(b, "pkt-b", 1, "run-2", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-b", 1, "RUNNING", "READY", "infra_retry", _classification_infra_retry(), "run-2")
    _start_as(b, "pkt-b", 2, "run-2", provider="opencode", model="kimi-k2.7-code")
    _finish_as(b, "pkt-b", 2, "RUNNING", "REVIEW", "result_recorded", _classification_completed(), "run-2")
    _verdict_as(b, "pkt-b", 2, "ACCEPTED", "verdict_accept", "run-2")

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)

    report_run1 = _report_for_run(state_root, "run-1", report_id="report-budget-run-1")
    report_run2 = _report_for_run(state_root, "run-2", report_id="report-budget-run-2")

    def _codes_for(report, packet_id):
        return {
            item["code"] for item in report["attention_required"]
            if item.get("packet_id") == packet_id
        }

    # pkt-a's 2 attempts were fully legitimate under run-1's OWN bound plan
    # (attempt_limit=3) -- never flagged, whichever run is being
    # reconciled. Reconciling run-2 is the false-positive fix under direct
    # test: before the fix, this would have been wrongly flagged, since
    # the old code checked pkt-a's cumulative 2 attempts against run-2's
    # plan (attempt_limit=1) instead of run-1's own plan (the one it
    # actually ran under).
    assert "plan_attempt_budget_exceeded" not in _codes_for(report_run1, "pkt-a")
    assert "plan_attempt_budget_exceeded" not in _codes_for(report_run2, "pkt-a")

    # pkt-b's 2nd attempt genuinely exceeds the attempt_limit of the ONE
    # plan it ever ran under (run-2's own Plan B, attempt_limit=1) --
    # detection must still fire, in both runs' reports (reconciling run-1
    # must not silently clear it just because Plan A -- which never
    # governed these attempts -- would have allowed 3).
    assert "plan_attempt_budget_exceeded" in _codes_for(report_run1, "pkt-b")
    assert "plan_attempt_budget_exceeded" in _codes_for(report_run2, "pkt-b")
    assert report_run1["all_invariants_passed"] is False
    assert report_run1["reconciliation"]["all_invariants_passed"] is False
    assert report_run1["all_invariants_passed"] == report_run1["reconciliation"]["all_invariants_passed"]
    assert report_run2["all_invariants_passed"] is False
    assert report_run2["reconciliation"]["all_invariants_passed"] is False
    assert report_run2["all_invariants_passed"] == report_run2["reconciliation"]["all_invariants_passed"]

    # Attribution sanity: the flagged violation genuinely names pkt-b's own
    # attempt ordinal, run, and limit -- not a garbled/aggregated message.
    pkt_b_budget_detail = next(
        item["detail"] for item in report_run2["attention_required"]
        if item.get("packet_id") == "pkt-b" and item["code"] == "plan_attempt_budget_exceeded"
    )
    assert "attempt #2" in pkt_b_budget_detail
    assert "run-2" in pkt_b_budget_detail
    assert "attempt_limit of 1" in pkt_b_budget_detail


# ---------------------------------------------------------------------------
# (5) Review capability classes exclude a hop matching the packet's own
# recorded implementer identity, exact-pair form (O5 review round 4 finding
# B, closed this pass, not merely documented) -- mirrors
# budget_runtime.select_capable_route's ``if pair in implementers: continue``
# for _REVIEW_CAPABILITY_CLASSES.
# ---------------------------------------------------------------------------


def test_review_capability_class_excludes_hop_matching_recorded_implementer_identity(tmp_path):
    """O5 review round 4 finding B: ``budget_runtime.select_capable_route``'s
    live eligibility gate excludes any candidate hop whose EXACT
    ``(provider, model_id)`` pair already appears as an ``ATTEMPT_STARTED``
    implementer identity (lane in ``kimi_implementation``/
    ``sonnet_implementation``) ANYWHERE in the journal, for review
    capability classes (``independent_review``/``adversarial_audit``) --
    "the same invocation cannot implement and then review itself," computed
    project-wide, never scoped to one packet (``budget_runtime.
    _implementer_invocations`` takes no ``packet_id`` parameter at all).
    Before this pass, ``_o5_hop_authorized`` did not replicate this at all:
    a plan-member ``independent_review`` packet whose durable
    ``ATTEMPT_STARTED`` recorded an identity that had already implemented
    other work read as "authorized" here even though the live selector
    would have refused to ever select it for review (nothing else eligible
    -> ``PAUSE``/``NO_CAPABLE_MODEL_AVAILABLE``).

    ``pkt-impl`` legitimately implements using ``opencode/kimi-k2.7-code``
    under the ordinary ``implementation`` capability class -- never
    flagged; the exclusion is review-class-only, by design (matching the
    live gate, which only computes ``implementers`` at all when
    ``capability_class in _REVIEW_CAPABILITY_CLASSES``). ``pkt-review``'s
    plan-pinned ``independent_review`` route table has EXACTLY ONE hop:
    that SAME identity. Its durable ``ATTEMPT_STARTED`` records using it
    anyway -- a self-review the live selector would never have granted --
    and reconciliation must now say so.
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "implementation": [_route("impl-primary", "opencode", "kimi-k2.7-code")],
        "independent_review": [_route("review-primary", "opencode", "kimi-k2.7-code")],
    }
    rows = [
        _plan_row("pkt-impl", _packet_sha256("pkt-impl"), capability_class="implementation"),
        _plan_row("pkt-review", _packet_sha256("pkt-review"), capability_class="independent_review"),
    ]
    plan = _plan("plan-reviewer-diversity", rows, routes=routes)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _accept_packet(b, "pkt-impl", 2)  # default lane="kimi_implementation", opencode/kimi-k2.7-code
    _enroll(b, "pkt-review", 3)
    review_attempt = _attempt_payload(1, provider="opencode", model="kimi-k2.7-code", lane="grok_verification")
    b.add(
        "ATTEMPT_STARTED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": review_attempt, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    b.add(
        "ATTEMPT_FINISHED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": review_attempt, "artifacts": [],
                 "classification": _classification_completed(), "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )
    _verdict(b, "pkt-review", 1, "ACCEPTED", "verdict_accept")

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    def _codes_for(packet_id):
        return {item["code"] for item in report["attention_required"] if item.get("packet_id") == packet_id}

    assert "attempt_route_not_in_plan" in _codes_for("pkt-review")
    assert "attempt_route_not_in_plan" not in _codes_for("pkt-impl")
    assert report["all_invariants_passed"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False

    detail = next(
        item["detail"] for item in report["attention_required"]
        if item.get("packet_id") == "pkt-review" and item["code"] == "attempt_route_not_in_plan"
    )
    assert "opencode/kimi-k2.7-code" in detail
    assert "independent_review" in detail


# ---------------------------------------------------------------------------
# (5) The reviewer-diversity implementer set (defect #10 above) must be
# scoped to each attempt's OWN seq, not the whole journal (O5 review round 5,
# finding N1) -- the live gate (``select_capable_route`` inside
# ``evaluate_preclaim``, called BEFORE that claim's own ``ATTEMPT_STARTED``
# is appended) only ever sees implementer identities that already existed
# strictly BEFORE the moment of that specific claim decision.
# ---------------------------------------------------------------------------


def test_implementer_identity_scoped_before_review_attempt_not_flagged(tmp_path):
    """O5 review round 5, finding N1, shape 1 (temporal): a review-class
    attempt on identity X made strictly BEFORE any implementation-lane
    attempt on X anywhere in the journal must NOT be retroactively flagged
    once a LATER implementation attempt on X appears. Before this fix,
    ``implementer_identities`` was computed ONCE over the WHOLE journal and
    reused, unscoped, for every attempt -- so a later implementation attempt
    on the same identity would poison an earlier, already-decided, correctly
    authorized review attempt. The round-4 test immediately above this one
    (``test_review_capability_class_excludes_hop_matching_recorded_implementer_identity``)
    proves the mirror-image case -- an implementer attempt BEFORE the review
    attempt, in seq order -- still correctly gets flagged; this test proves
    the fix does not overcorrect into never flagging anything.
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "implementation": [_route("impl-primary", "opencode", "kimi-k2.7-code")],
        "independent_review": [_route("review-primary", "opencode", "kimi-k2.7-code")],
    }
    rows = [
        _plan_row("pkt-review", _packet_sha256("pkt-review"), capability_class="independent_review"),
        _plan_row("pkt-impl", _packet_sha256("pkt-impl"), capability_class="implementation"),
    ]
    plan = _plan("plan-implementer-scoping-temporal", rows, routes=routes)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    # The review attempt happens FIRST, at an earlier seq than any
    # implementation-lane attempt on this same identity anywhere in the
    # journal -- exactly what the live gate would have seen at decision
    # time: no implementer yet.
    _enroll(b, "pkt-review", 2)
    review_attempt = _attempt_payload(1, provider="opencode", model="kimi-k2.7-code", lane="grok_verification")
    b.add(
        "ATTEMPT_STARTED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": review_attempt, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    b.add(
        "ATTEMPT_FINISHED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": review_attempt, "artifacts": [],
                 "classification": _classification_completed(), "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )
    _verdict(b, "pkt-review", 1, "ACCEPTED", "verdict_accept")
    # THEN, at a later seq, a genuine implementation-lane attempt on the
    # SAME identity -- this is what previously retroactively poisoned the
    # earlier review attempt above.
    _accept_packet(b, "pkt-impl", 6)

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    def _codes_for(packet_id):
        return {item["code"] for item in report["attention_required"] if item.get("packet_id") == packet_id}

    assert "attempt_route_not_in_plan" not in _codes_for("pkt-review")
    assert "attempt_route_not_in_plan" not in _codes_for("pkt-impl")


def test_implementer_identity_self_inclusion_not_flagged_on_first_attempt(tmp_path):
    """O5 review round 5, finding N1, shape 2 (self-inclusion): a
    review-capability-class packet whose own enrolled ``lane`` happens to be
    an IMPLEMENTATION lane (``kimi_implementation``/``sonnet_implementation``)
    must not have its OWN not-yet-recorded ``ATTEMPT_STARTED`` counted into
    the implementer set used to judge itself. No cross-packet identity
    overlap is needed to reproduce this shape -- there is exactly ONE
    attempt in this whole journal, and it is this packet's own. Before this
    fix, the whole-journal ``implementer_identities`` set included this
    attempt's own recorded identity (lane in ``_IMPLEMENTATION_LANES``,
    irrespective of the packet's own ``capability_class``), so the
    exact-pair reviewer-diversity exclusion in ``_o5_hop_authorized`` fired
    against itself even though the plan's own review route table
    legitimately lists this identity and the live gate allowed it.
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "independent_review": [_route("review-primary", "opencode", "kimi-k2.7-code")],
    }
    rows = [_plan_row("pkt-review-self", _packet_sha256("pkt-review-self"), capability_class="independent_review")]
    plan = _plan("plan-implementer-self-inclusion", rows, routes=routes)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)
    _enroll(b, "pkt-review-self", 2)
    self_attempt = _attempt_payload(1, provider="opencode", model="kimi-k2.7-code", lane="kimi_implementation")
    b.add(
        "ATTEMPT_STARTED", packet_id="pkt-review-self", intent_id="attempt-pkt-review-self-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": self_attempt, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    b.add(
        "ATTEMPT_FINISHED", packet_id="pkt-review-self", intent_id="attempt-pkt-review-self-1",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": self_attempt, "artifacts": [],
                 "classification": _classification_completed(), "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )
    _verdict(b, "pkt-review-self", 1, "ACCEPTED", "verdict_accept")

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    violation_codes = {
        item["code"] for item in report["attention_required"]
        if item.get("packet_id") == "pkt-review-self"
    }
    assert "attempt_route_not_in_plan" not in violation_codes


# ---------------------------------------------------------------------------
# (6) The route-authorization dedup key itself must be scoped by each
# attempt's own implementer status, not just (identity, run_id) -- O5 review
# round 6, finding N3, a fail-open regression introduced by round 5's N1 fix
# above. Before N1, ``_o5_hop_authorized``'s verdict for a given
# ATTEMPT_STARTED was a pure function of (plan-for-that-run, capability_class,
# identity), so any two entries sharing (identity, run_id) were guaranteed to
# produce the same verdict and (identity, run_id) was a safe dedup key. N1
# made the verdict also depend on the attempt's own seq (via a per-attempt-
# scoped implementer set that only grows as seq advances), but the dedup key
# was never extended to match -- so two entries sharing (identity, run_id)
# could now legitimately disagree, and dedup silently kept only the EARLIEST
# (and therefore most permissive) one, never even reaching
# ``_o5_hop_authorized`` for any later, genuinely-illegitimate attempt on
# that same identity.
# ---------------------------------------------------------------------------


def test_second_attempt_on_same_identity_after_intervening_implementer_is_flagged_despite_dedup(tmp_path):
    """O5 review round 6, finding N3: reproduces the reviewer's exact
    scenario. ``pkt-review`` (``independent_review`` capability class) makes
    a FIRST attempt on identity X while X is not yet an implementer identity
    anywhere in the journal -- legitimate, correctly NOT flagged, exactly
    like ``test_implementer_identity_scoped_before_review_attempt_not_flagged``
    above. It is then sent to REVISE and requeued. Before it runs again, a
    DIFFERENT packet (``pkt-impl``) implements on that SAME identity X. When
    ``pkt-review`` then makes its SECOND attempt -- still on the SAME
    identity X, still within the SAME run -- this is now exactly the
    self-review the live gate's reviewer-diversity exclusion exists to
    refuse: X has implemented other work in this journal by the time this
    claim is decided.

    Before this fix, (identity, run_id) alone deduped these two
    ATTEMPT_STARTED entries to a single dedup slot. Because iteration is in
    seq order, the FIRST (legitimate) attempt filled that slot and the
    SECOND (illegitimate) attempt was skipped outright -- never checked, never
    flagged, report reads all-clear. This is the fail-open shape the reviewer
    demonstrated live through ``build_reconciliation_report``: ``codes:
    set()``, ``all_invariants_passed: True``, for a journal that should have
    refused the second attempt.

    The control case -- a single ATTEMPT_STARTED made entirely AFTER the
    identity already implemented elsewhere, with no earlier legitimate
    attempt on that identity to collide with in dedup -- is
    ``test_review_capability_class_excludes_hop_matching_recorded_implementer_identity``
    above; it already passes both before and after this fix, confirming the
    miss this test reproduces is specifically caused by the dedup collision,
    not a broader break in the underlying check.
    """
    state_root = _new_state_root(STATE_ROOT_ID)
    routes = {
        "implementation": [_route("impl-primary", "opencode", "kimi-k2.7-code")],
        "independent_review": [_route("review-primary", "opencode", "kimi-k2.7-code")],
    }
    rows = [
        _plan_row("pkt-review", _packet_sha256("pkt-review"), capability_class="independent_review"),
        _plan_row("pkt-impl", _packet_sha256("pkt-impl"), capability_class="implementation"),
    ]
    plan = _plan("plan-dedup-key-implementer-scoping", rows, routes=routes)
    _publish_plan(state_root, plan)

    b = _Journal()
    _run_started(b)
    _bind_plan(b, plan)

    _enroll(b, "pkt-review", 2)
    review_attempt_1 = _attempt_payload(1, provider="opencode", model="kimi-k2.7-code", lane="grok_verification")
    b.add(
        "ATTEMPT_STARTED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": review_attempt_1, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    b.add(
        "ATTEMPT_FINISHED", packet_id="pkt-review", intent_id="attempt-pkt-review-1",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": review_attempt_1, "artifacts": [],
                 "classification": _classification_completed(), "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )
    _verdict(b, "pkt-review", 1, "REVISE", "verdict_revise")
    _requeue(b, "pkt-review", 1)

    # Intervening implementer attempt, on a DIFFERENT packet, lands between
    # pkt-review's two attempts -- this is what must now be picked up by
    # pkt-review's SECOND attempt and must NOT retroactively poison its
    # FIRST (already-decided, correctly-authorized) attempt above.
    _accept_packet(b, "pkt-impl", 6)  # default lane="kimi_implementation", opencode/kimi-k2.7-code

    review_attempt_2 = _attempt_payload(2, provider="opencode", model="kimi-k2.7-code", lane="grok_verification")
    b.add(
        "ATTEMPT_STARTED", packet_id="pkt-review", intent_id="attempt-pkt-review-2",
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload={"packet": None, "attempt": review_attempt_2, "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None, "report": None},
    )
    b.add(
        "ATTEMPT_FINISHED", packet_id="pkt-review", intent_id="attempt-pkt-review-2",
        from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
        payload={"packet": None, "attempt": review_attempt_2, "artifacts": [],
                 "classification": _classification_completed(), "transition_detail": None,
                 "recovery": None, "run": None, "report": None},
    )
    _verdict(b, "pkt-review", 2, "ACCEPTED", "verdict_accept")

    _write_journal(os.path.join(state_root, "journal.ndjson"), b.events)
    report = _report(state_root)

    def _violations_for(packet_id, code):
        return [
            item for item in report["attention_required"]
            if item.get("packet_id") == packet_id and item["code"] == code
        ]

    review_route_violations = _violations_for("pkt-review", "attempt_route_not_in_plan")
    # Exactly one violation: the SECOND attempt, not the first (the fix must
    # not overcorrect into flagging the earlier, legitimately-authorized
    # attempt too) and not two (a broken fix that stopped deduping legitimate
    # repeats entirely would double-count).
    assert len(review_route_violations) == 1
    assert "opencode/kimi-k2.7-code" in review_route_violations[0]["detail"]
    assert "independent_review" in review_route_violations[0]["detail"]

    assert _violations_for("pkt-impl", "attempt_route_not_in_plan") == []

    assert report["all_invariants_passed"] is False
    assert report["reconciliation"]["all_invariants_passed"] is False
