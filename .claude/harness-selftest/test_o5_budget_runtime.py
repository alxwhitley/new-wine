"""O5 pure budget-accounting and capability-routing decision tests.

Every decision in this suite is produced by a pure function: no filesystem,
no journal append, no provider call, no environment read, and no wall-clock
read.  Time enters only through the caller-supplied ``now_utc``.
"""

import ast
import copy
import itertools
import json
import re
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import validate_journal_event
from harness_coordinator.v1.recovery import _make_event


T_NOW = "2026-08-11T12:00:00Z"
T_EARLY = "2026-08-11T00:00:00Z"
T_MID = "2026-08-11T06:00:00Z"
T_LATE = "2026-08-11T18:00:00Z"

COORDINATOR_ID = "coord-o5"
RUN_ID = "run-o5"
STATE_ROOT_ID = "state-root-o5"

PACKET_DIGESTS = {
    "packet-1": "a" * 64,
    "packet-2": "b" * 64,
    "packet-3": "c" * 64,
    "packet-4": "d" * 64,
}

EVIDENCE_SHA = "e" * 64

SCHEMA_PATH = (
    Path(__file__).parents[2] / "schemas" / "harness" / "v1" / "journal-event.schema.json"
)
PROVIDER_EVIDENCE_SCHEMA_PATH = (
    Path(__file__).parents[2] / "schemas" / "harness" / "v1" / "provider-evidence.schema.json"
)
BUDGET_RUNTIME_PATH = (
    Path(__file__).parents[2]
    / "scripts" / "harness_coordinator" / "v1" / "budget_runtime.py"
)


# --------------------------------------------------------------------------
# Plan / packet-row / journal fixtures
# --------------------------------------------------------------------------


def _rehash(plan):
    plan["plan_sha256"] = compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))
    return plan


def _route(route_id, provider, model_id, reasoning="high", enabled=True, fallback_to=None):
    return {
        "route_id": route_id,
        "provider": provider,
        "model_id": model_id,
        "minimum_reasoning": reasoning,
        "enabled": enabled,
        "qualification_id": "qual-" + route_id,
        "fallback_to": fallback_to,
    }


def _default_routes():
    return {
        "design_judgment": [
            _route("design-fable", "anthropic", "claude-fable-5", "max",
                   True, "design-sol"),
            _route("design-sol", "openai", "gpt-5.6-sol", "max", False, None),
        ],
        "implementation": [
            _route("implementation-primary", "opencode", "kimi-k2.7-code", "high",
                   True, "implementation-terra"),
            _route("implementation-terra", "openai", "gpt-5.6-terra", "high",
                   True, "implementation-sonnet"),
            _route("implementation-sonnet", "anthropic", "claude-sonnet-4-5", "high",
                   True, None),
        ],
        "independent_review": [
            _route("review-sol", "openai", "gpt-5.6-sol", "xhigh", True, "review-fable"),
            _route("review-fable", "anthropic", "claude-fable-5", "max", True, "review-grok"),
            _route("review-grok", "xai", "grok-4.2", "high", True, None),
        ],
        "adversarial_audit": [
            _route("audit-grok", "xai", "grok-4.2", "high", True, "audit-sol"),
            _route("audit-sol", "openai", "gpt-5.6-sol", "xhigh", True, "audit-fable"),
            _route("audit-fable", "anthropic", "claude-fable-5", "max", True, None),
        ],
    }


def _packet_row_in_plan(packet_id, capability_class, dependencies,
                        attempt_limit, retry_limit, revision_limit):
    return {
        "packet_id": packet_id,
        "packet_sha256": PACKET_DIGESTS[packet_id],
        "dependencies": list(dependencies),
        "capability_class": capability_class,
        "budgets": {
            "attempt_limit": attempt_limit,
            "retry_limit": retry_limit,
            "revision_limit": revision_limit,
            "turn_limit": 12,
            "command_timeout_seconds": 60,
            "output_bytes": 4096,
        },
    }


def _plan(attempt_limit=2, retry_limit=1, revision_limit=1, routes=None,
          max_retries=3, base_delay_seconds=30, max_delay_seconds=300,
          plan_id="plan-o5"):
    plan = {
        "schema_version": 1,
        "plan_id": plan_id,
        "plan_sha256": "",
        "packets": [
            _packet_row_in_plan("packet-1", "implementation", [],
                                attempt_limit, retry_limit, revision_limit),
            _packet_row_in_plan("packet-2", "independent_review", ["packet-1"],
                                attempt_limit, retry_limit, revision_limit),
            _packet_row_in_plan("packet-3", "design_judgment", [],
                                attempt_limit, retry_limit, revision_limit),
            _packet_row_in_plan("packet-4", "adversarial_audit", [],
                                attempt_limit, retry_limit, revision_limit),
        ],
        "routes": routes if routes is not None else _default_routes(),
        "provider_backoff": {
            "max_retries": max_retries,
            "base_delay_seconds": base_delay_seconds,
            "max_delay_seconds": max_delay_seconds,
        },
        "wall_clock_safety_seconds": 3600,
        "human_stop_categories": [
            "production_database_write",
            "deployment",
            "destructive_filesystem_git",
            "governed_content",
            "licensing_determination",
            "real_provider_commissioning",
            "material_plan_expansion",
        ],
    }
    return _rehash(plan)


def _packet(attempts_started=0, packet_id="packet-1", infra_retries_used=0,
            revise_cycles_used=0, packet_sha256=None, state="READY"):
    """A folded packet row, in the exact shape ``_fold_journal`` produces."""
    return {
        "packet_id": packet_id,
        "run_id": RUN_ID,
        "state": state,
        "packet_sha256": (PACKET_DIGESTS.get(packet_id, "a" * 64)
                          if packet_sha256 is None else packet_sha256),
        "attempts_started": attempts_started,
        "infra_retries_used": infra_retries_used,
        "revise_cycles_used": revise_cycles_used,
        "revise_verdicts": 0,
        "reassignment_used": False,
        "open_attempt": None,
    }


def _base_payload():
    return {
        "packet": None,
        "attempt": None,
        "artifacts": [],
        "classification": None,
        "transition_detail": None,
        "recovery": None,
        "run": None,
        "report": None,
    }


def _journal(*builders):
    """Build a hash-chained journal from ``(seq, prev) -> event`` builders."""
    events = []
    prev = None
    for index, builder in enumerate(builders, start=1):
        event = builder(index, prev)
        events.append(event)
        prev = event
    return events


def _attempt_started(packet_id="packet-1", attempt=1, at=T_EARLY,
                     lane="kimi_implementation", provider="opencode",
                     model="kimi-k2.7-code"):
    def build(seq, prev):
        payload = _base_payload()
        payload["attempt"] = {
            "attempt": attempt,
            "lane": lane,
            "worker": {
                "worker_id": "worker-%s-%d" % (packet_id, attempt),
                "session_id": "session-%s-%d" % (packet_id, attempt),
                "provider": provider,
                "model": model,
            },
            "claim_sha256": "1" * 64,
            "worktree_path": None,
        }
        return _make_event(
            seq, "ATTEMPT_STARTED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, prev, at,
            packet_id=packet_id, intent_id="attempt-%s-%d" % (packet_id, attempt),
            payload=payload, from_state="READY", to_state="RUNNING",
            cause="claim_committed",
        )
    return build


def _worker_result_recorded(packet_id="packet-1", attempt=1, at=T_EARLY):
    """An untrusted worker report.  Its content can never grant budget."""
    def build(seq, prev):
        payload = _base_payload()
        payload["attempt"] = {
            "attempt": attempt,
            "lane": "kimi_implementation",
            "worker": {
                "worker_id": "worker-%s-%d" % (packet_id, attempt),
                "session_id": "session-%s-%d" % (packet_id, attempt),
                "provider": "opencode",
                "model": "kimi-k2.7-code",
            },
            "claim_sha256": "1" * 64,
            "worktree_path": None,
        }
        return _make_event(
            seq, "WORKER_RESULT_RECORDED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, prev, at,
            packet_id=packet_id, intent_id="attempt-%s-%d" % (packet_id, attempt),
            payload=payload,
        )
    return build


def _capacity(provider, model_id, state, observed_at=T_EARLY, reset_at=None,
              evidence_sha256=EVIDENCE_SHA, at=None):
    def build(seq, prev):
        from harness_coordinator.v1.budget_runtime import budget_event_payload

        payload = budget_event_payload("PROVIDER_CAPACITY_RECORDED", {
            "provider": provider,
            "model_id": model_id,
            "state": state,
            "observed_at": observed_at,
            "reset_at": reset_at,
            "evidence_sha256": evidence_sha256,
        })
        return _make_event(
            seq, "PROVIDER_CAPACITY_RECORDED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            prev, at or observed_at, payload=payload,
        )
    return build


def _backoff(provider, model_id, next_eligible_at, retry_index=0,
             reason_code="PROVIDER_BACKOFF_PENDING", at=T_EARLY,
             evidence_sha256=EVIDENCE_SHA):
    def build(seq, prev):
        from harness_coordinator.v1.budget_runtime import budget_event_payload

        payload = budget_event_payload("PROVIDER_BACKOFF_SCHEDULED", {
            "provider": provider,
            "model_id": model_id,
            "reason_code": reason_code,
            "next_eligible_at": next_eligible_at,
            "retry_index": retry_index,
            "evidence_sha256": evidence_sha256,
        })
        return _make_event(
            seq, "PROVIDER_BACKOFF_SCHEDULED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            prev, at, payload=payload,
        )
    return build


def _observation(provider, model_id, state, observed_at=T_EARLY, reset_at=None):
    return {
        "provider": provider,
        "model_id": model_id,
        "state": state,
        "observed_at": observed_at,
        "reset_at": reset_at,
        "evidence_sha256": EVIDENCE_SHA,
    }


def _snapshot(*observations):
    return dict(
        ("%s/%s" % (obs["provider"], obs["model_id"]), obs) for obs in observations
    )


# --------------------------------------------------------------------------
# Step 1 -- accounting
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("attempts", "limit", "decision"), [
    (0, 0, "STOP"),
    (0, 1, "ALLOW"),
    (1, 1, "STOP"),
    (1, 2, "ALLOW"),
    (2, 2, "STOP"),
])
def test_attempt_limit_is_checked_before_claim(attempts, limit, decision):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(*[
        _attempt_started(attempt=index + 1) for index in range(attempts)
    ])
    result = evaluate_preclaim(
        _plan(attempt_limit=limit), _packet(attempts_started=attempts),
        events, {}, T_NOW)
    assert result["decision"] == decision


def test_exhausted_attempt_budget_names_its_own_reason_code():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=1),
        _journal(_attempt_started()), {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"
    assert result["packet_id"] == "packet-1"
    assert result["route"] is None


def test_worker_report_cannot_increase_remaining_budget():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started(), _worker_result_recorded())
    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=1), events, {}, T_NOW)
    assert result["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"


def test_worker_report_claiming_no_attempts_cannot_reopen_budget():
    """A folded row under-reporting authenticated journal usage fails closed."""
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started(), _worker_result_recorded())
    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=0), events, {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


@pytest.mark.parametrize("field", [
    "attempts_started", "infra_retries_used", "revise_cycles_used",
])
def test_boolean_masquerading_as_integer_in_packet_row_is_refused(field):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    packet = _packet()
    packet[field] = True
    result = evaluate_preclaim(_plan(), packet, [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


@pytest.mark.parametrize("field", ["attempt_limit", "retry_limit", "revision_limit"])
def test_boolean_masquerading_as_integer_in_plan_budget_is_refused(field):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    plan = _plan()
    plan["packets"][0]["budgets"][field] = True
    _rehash(plan)
    result = evaluate_preclaim(plan, _packet(), [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_duplicate_attempt_events_are_counted_once():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started())
    duplicated = events + [copy.deepcopy(events[0])]
    result = evaluate_preclaim(
        _plan(attempt_limit=2), _packet(attempts_started=1), duplicated, {}, T_NOW)
    assert result["decision"] == "ALLOW"


def test_missing_events_never_grant_budget_the_row_already_spent():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=1), [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"


def test_attempts_for_another_packet_do_not_consume_this_packets_budget():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started(packet_id="packet-4"))
    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=0), events, {}, T_NOW)
    assert result["decision"] == "ALLOW"


@pytest.mark.parametrize(("event_at", "expected"), [
    (T_EARLY, "ALLOW"),
    (T_LATE, "STOP"),
])
def test_clock_regression_against_now_utc_fails_closed(event_at, expected):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started(at=event_at))
    result = evaluate_preclaim(
        _plan(attempt_limit=2), _packet(attempts_started=1), events, {}, T_NOW)
    assert result["decision"] == expected
    if expected == "STOP":
        assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_event_timestamps_going_backwards_in_sequence_order_fail_closed():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(
        _attempt_started(attempt=1, at=T_MID),
        _worker_result_recorded(attempt=1, at=T_EARLY),
    )
    result = evaluate_preclaim(
        _plan(attempt_limit=3), _packet(attempts_started=1), events, {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


@pytest.mark.parametrize("bad_now", ["", "2026-08-11", "2026-08-11T12:00:00+00:00", None, 17])
def test_unnormalized_now_utc_is_refused(bad_now):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(_plan(), _packet(), [], {}, bad_now)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_packet_outside_plan_membership_is_refused():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(), _packet(packet_id="packet-not-in-plan"), [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "PLAN_SCOPE_PACKET_OUTSIDE_PLAN"


def test_packet_digest_disagreeing_with_plan_is_refused():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(), _packet(packet_sha256="9" * 64), [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "PLAN_SCOPE_PACKET_DIGEST_MISMATCH"


@pytest.mark.parametrize(("retries_used", "retry_limit", "decision"), [
    (0, 0, "ALLOW"),
    (1, 0, "STOP"),
    (1, 1, "ALLOW"),
    (2, 1, "STOP"),
])
def test_infra_retry_budget_is_checked_before_claim(retries_used, retry_limit, decision):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(attempt_limit=9, retry_limit=retry_limit),
        _packet(infra_retries_used=retries_used), [], {}, T_NOW)
    assert result["decision"] == decision
    if decision == "STOP":
        assert result["reason_code"] == "PACKET_BUDGET_RETRIES_EXHAUSTED"


@pytest.mark.parametrize(("cycles_used", "revision_limit", "decision"), [
    (0, 0, "ALLOW"),
    (1, 0, "STOP"),
    (1, 1, "ALLOW"),
    (2, 1, "STOP"),
])
def test_revision_budget_is_checked_before_claim(cycles_used, revision_limit, decision):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(attempt_limit=9, revision_limit=revision_limit),
        _packet(revise_cycles_used=cycles_used), [], {}, T_NOW)
    assert result["decision"] == decision
    if decision == "STOP":
        assert result["reason_code"] == "PACKET_BUDGET_REVISIONS_EXHAUSTED"


def test_attempt_budget_is_checked_before_provider_routing():
    """An exhausted packet stops on its own budget, not on provider capacity."""
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(attempt_limit=1), _packet(attempts_started=1), [],
        _snapshot(_observation("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED")),
        T_NOW)
    assert result["reason_code"] == "PACKET_BUDGET_ATTEMPTS_EXHAUSTED"


# --------------------------------------------------------------------------
# Step 2 -- routing, exhaustion, backoff
# --------------------------------------------------------------------------


def test_design_route_pauses_instead_of_using_disabled_sol():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(
        _plan(), "design_judgment", [],
        _snapshot(_observation("anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED")),
        T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"
    assert result["route"] is None
    assert result["next_eligible_at"] is None


def test_design_route_selects_fable_when_available():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "design_judgment", [], {}, T_NOW)
    assert result["decision"] == "ALLOW"
    assert result["reason_code"] == "MODEL_ROUTE_SELECTED"
    assert result["route"]["model_id"] == "claude-fable-5"


def test_implementation_fallback_is_same_class_and_acyclic():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(_capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED"))
    result = select_capable_route(
        _plan(), "implementation", events,
        _snapshot(_observation("openai", "gpt-5.6-terra", "AVAILABLE")), T_NOW)
    assert result["decision"] == "FALLBACK"
    assert result["reason_code"] == "MODEL_ROUTE_FALLBACK_SELECTED"
    assert result["route"]["model_id"] == "gpt-5.6-terra"
    assert result["route"]["provider"] == "openai"


def test_selected_route_is_the_exact_plan_pinned_opencode_model_id():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    plan = _plan()
    result = select_capable_route(plan, "implementation", [], {}, T_NOW)
    assert result["route"]["model_id"] == "kimi-k2.7-code"
    assert result["route"]["qualification_id"] == "qual-implementation-primary"
    assert result["route"] == plan["routes"]["implementation"][0]


def test_runtime_catalog_drift_cannot_introduce_a_model_outside_the_plan():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    drift = _snapshot(
        _observation("opencode", "kimi-k9-preview", "AVAILABLE"),
        _observation("opencode", "kimi-k2.7-code", "AVAILABLE"),
        _observation("anthropic", "claude-fable-9", "AVAILABLE"),
    )
    result = select_capable_route(_plan(), "implementation", [], drift, T_NOW)
    assert result["route"]["model_id"] == "kimi-k2.7-code"


def test_snapshot_cannot_re_enable_a_journal_exhausted_pair():
    """Mutable cache state can restrict, never authorize."""
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(_capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED"))
    result = select_capable_route(
        _plan(), "implementation", events,
        _snapshot(_observation("opencode", "kimi-k2.7-code", "AVAILABLE")), T_NOW)
    assert result["route"]["model_id"] == "gpt-5.6-terra"


def test_snapshot_may_restrict_a_route_the_journal_has_not_seen():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(
        _plan(), "implementation", [],
        _snapshot(_observation("opencode", "kimi-k2.7-code", "UNAVAILABLE")), T_NOW)
    assert result["decision"] == "FALLBACK"
    assert result["route"]["model_id"] == "gpt-5.6-terra"


def test_disabled_route_is_never_selected_even_when_available():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"][0]["enabled"] = False
    result = select_capable_route(_plan(routes=routes), "implementation", [], {}, T_NOW)
    assert result["decision"] == "FALLBACK"
    assert result["route"]["model_id"] == "gpt-5.6-terra"


def test_adversarial_audit_routes_to_the_plan_pinned_grok_model():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "adversarial_audit", [], {}, T_NOW)
    assert result["decision"] == "ALLOW"
    assert result["route"]["provider"] == "xai"
    assert result["route"]["model_id"] == "grok-4.2"


def test_review_route_falls_through_sol_then_fable_to_grok():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(
        _capacity("openai", "gpt-5.6-sol", "ALLOWANCE_EXHAUSTED"),
        _capacity("anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED",
                  observed_at=T_MID),
    )
    result = select_capable_route(_plan(), "independent_review", events, {}, T_NOW)
    assert result["decision"] == "FALLBACK"
    assert result["route"]["model_id"] == "grok-4.2"


def test_reviewer_cannot_be_the_same_invocation_that_implemented():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(_attempt_started(
        packet_id="packet-1", lane="kimi_implementation",
        provider="openai", model="gpt-5.6-sol"))
    result = select_capable_route(_plan(), "independent_review", events, {}, T_NOW)
    assert result["route"]["model_id"] != "gpt-5.6-sol"
    assert result["route"]["model_id"] == "claude-fable-5"


def test_unavoidable_loss_of_reviewer_family_diversity_is_human_required():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["independent_review"] = [
        _route("review-sol", "openai", "gpt-5.6-sol", "xhigh", True, "review-terra"),
        _route("review-terra", "openai", "gpt-5.6-terra", "xhigh", True, None),
    ]
    events = _journal(_attempt_started(
        packet_id="packet-1", lane="kimi_implementation",
        provider="openai", model="gpt-5.6-sol"))
    result = select_capable_route(
        _plan(routes=routes), "independent_review", events, {}, T_NOW)
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_code"] == "HUMAN_AUTHORITY_REQUIRED"
    assert result["route"] is None


def test_reviewer_family_diversity_is_preferred_over_plan_order():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["independent_review"] = [
        _route("review-terra", "openai", "gpt-5.6-terra", "xhigh", True, "review-fable"),
        _route("review-fable", "anthropic", "claude-fable-5", "max", True, None),
    ]
    events = _journal(_attempt_started(
        packet_id="packet-1", lane="kimi_implementation",
        provider="openai", model="gpt-5.6-sol"))
    result = select_capable_route(
        _plan(routes=routes), "independent_review", events, {}, T_NOW)
    assert result["route"]["model_id"] == "claude-fable-5"
    assert result["decision"] == "FALLBACK"


@pytest.mark.parametrize("mutation", ["cross_class", "cycle"])
def test_a_plan_whose_fallback_graph_is_unsound_never_routes(mutation):
    """The public boundary refuses the whole plan before any hop is picked."""
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    if mutation == "cross_class":
        routes["implementation"][0]["fallback_to"] = "review-grok"
    else:
        routes["implementation"][2]["fallback_to"] = "implementation-primary"
    result = select_capable_route(_plan(routes=routes), "implementation", [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


@pytest.mark.parametrize(("mutation", "reason_code"), [
    ("cross_class", "MODEL_ROUTE_CROSS_CLASS_FALLBACK"),
    ("cycle", "MODEL_ROUTE_FALLBACK_CYCLE"),
])
def test_route_walk_detects_an_unsound_graph_defensively(mutation, reason_code):
    """Defence in depth: the last gate before an invocation re-checks the graph.

    ``validate_execution_plan`` already refuses both shapes, so this exercises
    the walk directly -- the layer that would still hold if a future caller
    ever handed over routes that skipped plan validation.
    """
    from harness_coordinator.v1.budget_runtime import _EvidenceError, _ordered_hops

    routes = _default_routes()
    if mutation == "cross_class":
        routes["implementation"][0]["fallback_to"] = "review-grok"
    else:
        routes["implementation"][2]["fallback_to"] = "implementation-primary"
    with pytest.raises(_EvidenceError) as caught:
        _ordered_hops({"routes": routes}, "implementation")
    assert caught.value.reason_code == reason_code


def test_route_walk_follows_the_plans_explicit_fallback_pin():
    from harness_coordinator.v1.budget_runtime import _ordered_hops

    routes = _default_routes()
    ordered = _ordered_hops({"routes": routes}, "implementation")
    assert [hop["route_id"] for hop in ordered] == [
        "implementation-primary", "implementation-terra", "implementation-sonnet",
    ]

    routes["implementation"][0]["fallback_to"] = "implementation-sonnet"
    pinned = _ordered_hops({"routes": routes}, "implementation")
    assert [hop["route_id"] for hop in pinned] == [
        "implementation-primary", "implementation-sonnet",
    ]


def test_capability_class_absent_from_the_plan_is_refused():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "mechanical_check", [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "MODEL_ROUTE_NOT_IN_PLAN"


def test_unknown_capability_class_is_refused():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "vibes", [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "MODEL_ROUTE_NOT_IN_PLAN"


def test_rate_limited_sole_route_backs_off_until_its_bounded_window():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "RATE_LIMITED", observed_at=T_NOW))
    result = select_capable_route(
        _plan(routes=routes, base_delay_seconds=60), "implementation", events, {}, T_NOW)
    assert result["decision"] == "BACKOFF"
    assert result["reason_code"] == "PROVIDER_BACKOFF_PENDING"
    assert result["next_eligible_at"] == "2026-08-11T12:01:00Z"


def test_elapsed_bounded_backoff_window_makes_the_route_eligible_again():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "RATE_LIMITED", observed_at=T_EARLY))
    result = select_capable_route(
        _plan(routes=routes, base_delay_seconds=60), "implementation", events, {}, T_NOW)
    assert result["decision"] == "ALLOW"


def test_backoff_delay_is_bounded_by_the_plan_maximum():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "RATE_LIMITED", observed_at=T_NOW),
        _backoff("opencode", "kimi-k2.7-code", "2026-08-11T12:01:00Z",
                 retry_index=0, at=T_NOW),
        _backoff("opencode", "kimi-k2.7-code", "2026-08-11T12:02:00Z",
                 retry_index=1, at=T_NOW),
    )
    result = select_capable_route(
        _plan(routes=routes, base_delay_seconds=60, max_delay_seconds=120),
        "implementation", events, {}, T_NOW)
    assert result["decision"] == "BACKOFF"
    assert result["next_eligible_at"] == "2026-08-11T12:02:00Z"


def test_backoff_retry_budget_exhaustion_pauses_rather_than_waiting_forever():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "RATE_LIMITED", observed_at=T_NOW),
        _backoff("opencode", "kimi-k2.7-code", "2026-08-11T12:01:00Z",
                 retry_index=0, at=T_NOW),
    )
    result = select_capable_route(
        _plan(routes=routes, max_retries=1), "implementation", events, {}, T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"


def test_allowance_exhaustion_without_authenticated_reset_never_guesses_a_window():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED", observed_at=T_EARLY))
    result = select_capable_route(
        _plan(routes=routes), "implementation", events, {}, T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["next_eligible_at"] is None


def test_authenticated_reset_time_reopens_an_exhausted_allowance():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
        observed_at=T_EARLY, reset_at=T_MID))
    result = select_capable_route(
        _plan(routes=routes), "implementation", events, {}, T_NOW)
    assert result["decision"] == "ALLOW"


def test_pending_authenticated_reset_is_a_backoff_not_a_pause():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    routes = _default_routes()
    routes["implementation"] = [
        _route("implementation-primary", "opencode", "kimi-k2.7-code", "high", True, None),
    ]
    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
        observed_at=T_EARLY, reset_at=T_LATE))
    result = select_capable_route(
        _plan(routes=routes), "implementation", events, {}, T_NOW)
    assert result["decision"] == "BACKOFF"
    assert result["reason_code"] == "PROVIDER_ALLOWANCE_RESET_PENDING"
    assert result["next_eligible_at"] == T_LATE


def test_stale_reset_evidence_cannot_clear_a_later_exhaustion():
    """An AVAILABLE observation appended later but observed earlier is refused."""
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
                  observed_at=T_MID),
        _capacity("opencode", "kimi-k2.7-code", "AVAILABLE",
                  observed_at=T_EARLY, at=T_MID),
    )
    result = select_capable_route(_plan(), "implementation", events, {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_capacity_observation_from_the_future_fails_closed():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "AVAILABLE", observed_at=T_LATE, at=T_EARLY))
    result = select_capable_route(_plan(), "implementation", events, {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_exhausted_hop_stays_exhausted_across_a_full_journal_replay():
    """Restarting and refolding must not restore an exhausted hop."""
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
                  observed_at=T_EARLY),
        _attempt_started(packet_id="packet-1", attempt=1, at=T_MID,
                         provider="openai", model="gpt-5.6-terra"),
    )
    first = select_capable_route(_plan(), "implementation", events, {}, T_NOW)
    replayed = select_capable_route(
        _plan(), "implementation", copy.deepcopy(events), {}, T_LATE)
    assert first["route"]["model_id"] == "gpt-5.6-terra"
    assert replayed["route"]["model_id"] == "gpt-5.6-terra"


def test_every_hop_exhausted_pauses_the_lane():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
                  observed_at=T_EARLY),
        _capacity("openai", "gpt-5.6-terra", "ALLOWANCE_EXHAUSTED", observed_at=T_EARLY),
        _capacity("anthropic", "claude-sonnet-4-5", "UNAVAILABLE", observed_at=T_EARLY),
    )
    result = select_capable_route(_plan(), "implementation", events, {}, T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"


@pytest.mark.parametrize("bad", [
    {"opencode/kimi-k2.7-code": "EXHAUSTED"},
    {"opencode/kimi-k2.7-code": {"state": "AVAILABLE"}},
    {"wrong-key": _observation("opencode", "kimi-k2.7-code", "AVAILABLE")},
    {"opencode/kimi-k2.7-code": _observation(
        "opencode", "kimi-k2.7-code", "SOMETHING_ELSE")},
])
def test_malformed_provider_snapshot_fails_closed(bad):
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "implementation", [], bad, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_capacity_event_with_an_invalid_observation_fails_closed():
    from harness_coordinator.v1.budget_runtime import select_capable_route

    events = _journal(_capacity(
        "opencode", "kimi-k2.7-code", "AVAILABLE", evidence_sha256="not-a-digest"))
    result = select_capable_route(_plan(), "implementation", events, {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_preclaim_propagates_the_routing_decision_with_the_packet_id():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(
        _plan(), _packet(packet_id="packet-3"), [],
        _snapshot(_observation("anthropic", "claude-fable-5", "ALLOWANCE_EXHAUSTED")),
        T_NOW)
    assert result["decision"] == "PAUSE"
    assert result["reason_code"] == "NO_CAPABLE_MODEL_AVAILABLE"
    assert result["packet_id"] == "packet-3"


# --------------------------------------------------------------------------
# Step 3 -- purity, determinism, closed decision shape
# --------------------------------------------------------------------------


def test_budget_decision_is_a_closed_dict():
    from harness_coordinator.v1.budget_runtime import (
        BUDGET_DECISION_KEYS, DECISIONS, evaluate_preclaim, select_capable_route)
    from harness_contracts.v1.journal import BUDGET_REASON_CODES

    decisions = [
        evaluate_preclaim(_plan(), _packet(), [], {}, T_NOW),
        evaluate_preclaim(_plan(attempt_limit=0), _packet(), [], {}, T_NOW),
        select_capable_route(_plan(), "implementation", [], {}, T_NOW),
        select_capable_route(_plan(), "vibes", [], {}, T_NOW),
    ]
    for decision in decisions:
        assert set(decision) == set(BUDGET_DECISION_KEYS)
        assert decision["decision"] in DECISIONS
        assert decision["reason_code"] in BUDGET_REASON_CODES
        assert isinstance(decision["evidence_ids"], list)
        assert decision["evidence_ids"] == sorted(set(decision["evidence_ids"]))


def test_decisions_are_identical_under_shuffled_event_order():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED",
                  observed_at=T_EARLY),
        _attempt_started(packet_id="packet-1", attempt=1, at=T_MID,
                         provider="openai", model="gpt-5.6-terra"),
        _worker_result_recorded(packet_id="packet-1", attempt=1, at=T_MID),
        _backoff("opencode", "kimi-k2.7-code", T_LATE, retry_index=0, at=T_MID),
    )
    baseline = evaluate_preclaim(
        _plan(attempt_limit=3), _packet(attempts_started=1), events, {}, T_NOW)
    for permutation in itertools.permutations(events):
        shuffled = evaluate_preclaim(
            _plan(attempt_limit=3), _packet(attempts_started=1),
            list(permutation), {}, T_NOW)
        assert shuffled == baseline


def test_no_argument_is_mutated():
    from harness_coordinator.v1.budget_runtime import (
        evaluate_preclaim, select_capable_route)

    plan = _plan()
    packet = _packet(attempts_started=1)
    events = _journal(
        _capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED"),
        _attempt_started(attempt=1, at=T_MID),
    )
    snapshot = _snapshot(_observation("openai", "gpt-5.6-terra", "AVAILABLE"))
    before = copy.deepcopy((plan, packet, events, snapshot))

    decision = evaluate_preclaim(plan, packet, events, snapshot, T_NOW)
    select_capable_route(plan, "independent_review", events, snapshot, T_NOW)
    assert (plan, packet, events, snapshot) == before

    # The returned route must be a copy: mutating it cannot reach the plan.
    decision["route"]["model_id"] = "tampered"
    assert plan["routes"]["implementation"][1]["model_id"] == "gpt-5.6-terra"


def test_budget_runtime_module_is_structurally_pure():
    source = BUDGET_RUNTIME_PATH.read_text()
    # Word-boundary matching, so legitimate pure calls are not mistaken for
    # impure ones (``datetime.timedelta`` literally contains "time.time").
    forbidden = (
        r"\bopen\s*\(", r"\bos\.environ\b", r"\bgetenv\b", r"\butcnow\b",
        r"\bdatetime\.now\b", r"\btime\.time\b", r"\btime\.monotonic\b",
        r"\bsubprocess\b", r"\bsocket\b", r"\burllib\b", r"\brequests\b",
        r"\bappend_journal\b", r"\bread_journal\b", r"\.publish\s*\(",
        r"\bmakedirs\b", r"\bwrite_text\b", r"\bos\.path\b", r"\bshutil\b",
        r"\brandom\b", r"\bPath\b",
    )
    for pattern in forbidden:
        assert re.search(pattern, source) is None, (
            "budget_runtime.py must not reference %r" % pattern)

    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {
        "copy",
        "datetime",
        "typing",
        "harness_contracts.v1.execution_plan",
        "harness_contracts.v1.journal",
        "harness_contracts.v1.packet",
        "harness_contracts.v1.provider_evidence",
        "harness_contracts.v1.worker_result",
    }, sorted(imported)


@pytest.mark.parametrize("hostile", [
    None, [], "plan", 17, {"routes": {}}, {"packets": []},
])
def test_a_hostile_plan_never_raises_out_of_a_decision(hostile):
    from harness_coordinator.v1.budget_runtime import (
        evaluate_preclaim, select_capable_route)

    assert evaluate_preclaim(hostile, _packet(), [], {}, T_NOW)["decision"] == "STOP"
    assert select_capable_route(
        hostile, "implementation", [], {}, T_NOW)["decision"] == "STOP"


@pytest.mark.parametrize("hostile", [
    None, [], "packet-1", 17, {}, {"packet_id": ["not", "a", "string"]},
])
def test_a_hostile_packet_row_never_raises_out_of_a_decision(hostile):
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    result = evaluate_preclaim(_plan(), hostile, [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


@pytest.mark.parametrize("hostile", [
    None, "events", 17, [None], [{}], [{"seq": 1}],
    [{"seq": True, "event_sha256": "0" * 64, "event_at": T_EARLY}],
])
def test_a_hostile_event_list_never_raises_out_of_a_decision(hostile):
    from harness_coordinator.v1.budget_runtime import (
        evaluate_preclaim, select_capable_route)

    assert evaluate_preclaim(
        _plan(), _packet(), hostile, {}, T_NOW)["decision"] == "STOP"
    assert select_capable_route(
        _plan(), "implementation", hostile, {}, T_NOW)["decision"] == "STOP"


@pytest.mark.parametrize("hostile", [None, [], "state", 17, {"k": None}])
def test_a_hostile_capability_class_never_raises(hostile):
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), hostile, [], {}, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "MODEL_ROUTE_NOT_IN_PLAN"


@pytest.mark.parametrize("hostile", [[], "state", 17, {"k": None}, {"k": []}])
def test_a_hostile_provider_snapshot_never_raises(hostile):
    from harness_coordinator.v1.budget_runtime import select_capable_route

    result = select_capable_route(_plan(), "implementation", [], hostile, T_NOW)
    assert result["decision"] == "STOP"
    assert result["reason_code"] == "BUDGET_EVIDENCE_INVALID"


def test_an_absent_provider_snapshot_restricts_nothing():
    """``None`` means "no snapshot supplied", never "everything is available":
    the authenticated journal still decides, and a snapshot can only ever
    narrow what the journal already permits."""
    from harness_coordinator.v1.budget_runtime import select_capable_route

    assert (select_capable_route(_plan(), "implementation", [], None, T_NOW)
            == select_capable_route(_plan(), "implementation", [], {}, T_NOW))

    events = _journal(_capacity("opencode", "kimi-k2.7-code", "ALLOWANCE_EXHAUSTED"))
    absent = select_capable_route(_plan(), "implementation", events, None, T_NOW)
    assert absent["route"]["model_id"] == "gpt-5.6-terra"


def test_repeated_evaluation_is_stable():
    from harness_coordinator.v1.budget_runtime import evaluate_preclaim

    events = _journal(_attempt_started())
    first = evaluate_preclaim(
        _plan(), _packet(attempts_started=1), events, {}, T_NOW)
    second = evaluate_preclaim(
        _plan(), _packet(attempts_started=1), events, {}, T_NOW)
    assert first == second


# --------------------------------------------------------------------------
# Step 4 -- authenticated provider capacity evidence
# --------------------------------------------------------------------------


def test_capacity_observation_accepts_the_closed_shape():
    from harness_contracts.v1.provider_evidence import (
        validate_provider_capacity_observation)

    result = validate_provider_capacity_observation(
        _observation("openai", "gpt-5.6-sol", "RATE_LIMITED",
                     observed_at=T_EARLY, reset_at=T_MID))
    assert result["valid"] is True, result["errors"]


@pytest.mark.parametrize("secret_key", [
    "headers", "authorization", "response_body", "subscription_id",
    "prompt", "api_key", "stdout",
])
def test_capacity_observation_refuses_secret_bearing_fields(secret_key):
    from harness_contracts.v1.provider_evidence import (
        validate_provider_capacity_observation)

    observation = _observation("openai", "gpt-5.6-sol", "RATE_LIMITED")
    observation[secret_key] = "sk-live-should-never-persist"
    result = validate_provider_capacity_observation(observation)
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "UNKNOWN_FIELD"


@pytest.mark.parametrize("mutation", [
    ("state", "EXHAUSTED"),
    ("state", None),
    ("provider", ""),
    ("model_id", "GPT-5.6-Sol"),
    ("model_id", 5),
    ("observed_at", "2026-08-11"),
    ("observed_at", None),
    ("reset_at", "yesterday"),
    ("evidence_sha256", "abc"),
    ("evidence_sha256", None),
])
def test_capacity_observation_rejects_unusable_values(mutation):
    from harness_contracts.v1.provider_evidence import (
        validate_provider_capacity_observation)

    key, value = mutation
    observation = _observation("openai", "gpt-5.6-sol", "RATE_LIMITED")
    observation[key] = value
    assert validate_provider_capacity_observation(observation)["valid"] is False


def test_capacity_observation_rejects_a_reset_before_its_observation():
    from harness_contracts.v1.provider_evidence import (
        validate_provider_capacity_observation)

    observation = _observation("openai", "gpt-5.6-sol", "ALLOWANCE_EXHAUSTED",
                               observed_at=T_MID, reset_at=T_EARLY)
    assert validate_provider_capacity_observation(observation)["valid"] is False


@pytest.mark.parametrize("missing", [
    "provider", "model_id", "state", "observed_at", "reset_at", "evidence_sha256",
])
def test_capacity_observation_requires_every_closed_field(missing):
    from harness_contracts.v1.provider_evidence import (
        validate_provider_capacity_observation)

    observation = _observation("openai", "gpt-5.6-sol", "RATE_LIMITED")
    del observation[missing]
    result = validate_provider_capacity_observation(observation)
    assert result["valid"] is False
    assert result["errors"][0]["code"] == "MISSING_FIELD"


def test_provider_evidence_record_may_carry_a_capacity_observation():
    from harness_contracts.v1.provider_evidence import validate_provider_evidence

    record = _provider_evidence_record()
    assert validate_provider_evidence(record)["valid"] is True

    with_capacity = _provider_evidence_record(
        capacity=_observation("openai", "gpt-5.6-sol", "ALLOWANCE_EXHAUSTED"))
    assert validate_provider_evidence(with_capacity)["valid"] is True

    tampered = _provider_evidence_record(capacity={"state": "AVAILABLE"})
    assert validate_provider_evidence(tampered)["valid"] is False


def _provider_evidence_record(capacity=None):
    record = {
        "schema_version": 1,
        "evidence_id": "evidence-1",
        "packet_id": "packet-1",
        "attempt": 1,
        "provider": "openai",
        "captured_by": {
            "role": "coordinator",
            "coordinator_id": COORDINATOR_ID,
            "boot_id": "boot-1",
            "hostname": "host-1",
            "run_id": RUN_ID,
        },
        "invocation": {
            "argv": ["synthetic"],
            "exit_code": 1,
            "signal": None,
            "started_at": T_EARLY,
            "finished_at": T_MID,
            "timed_out": False,
        },
        "stdout_path": "artifacts/stdout.txt",
        "stdout_sha256": "0" * 64,
        "stderr_path": "artifacts/stderr.txt",
        "stderr_sha256": "0" * 64,
        "matched_signal": None,
        "classification": "NOT_EXHAUSTION",
        "evidence_sha256": "",
    }
    if capacity is not None:
        record["capacity"] = capacity
    record["evidence_sha256"] = compute_sha256(
        canonical_bytes(record, omit={"evidence_sha256"}))
    return record


def test_provider_evidence_schema_declares_the_closed_capacity_observation():
    schema = json.loads(PROVIDER_EVIDENCE_SCHEMA_PATH.read_text())
    from harness_contracts.v1.provider_evidence import (
        CAPACITY_OBSERVATION_FIELDS, CAPACITY_STATES)

    capacity = schema["properties"]["capacity"]
    assert capacity["additionalProperties"] is False
    assert set(capacity["required"]) == CAPACITY_OBSERVATION_FIELDS
    assert set(capacity["properties"]) == CAPACITY_OBSERVATION_FIELDS
    assert set(capacity["properties"]["state"]["enum"]) == CAPACITY_STATES
    assert "capacity" not in schema["required"]


# --------------------------------------------------------------------------
# Durable O5 budget events -- runtime and JSON Schema parity
# --------------------------------------------------------------------------


def _budget_event(event_type, body, packet_id=None, seq=1, prev=None, at=T_NOW):
    from harness_coordinator.v1.budget_runtime import budget_event_payload

    return _make_event(
        seq, event_type, COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, prev, at,
        packet_id=packet_id, payload=budget_event_payload(event_type, body),
    )


def _capacity_body():
    return {
        "provider": "openai",
        "model_id": "gpt-5.6-sol",
        "state": "ALLOWANCE_EXHAUSTED",
        "observed_at": T_EARLY,
        "reset_at": T_LATE,
        "evidence_sha256": EVIDENCE_SHA,
    }


def _backoff_body():
    return {
        "provider": "openai",
        "model_id": "gpt-5.6-sol",
        "reason_code": "PROVIDER_BACKOFF_PENDING",
        "next_eligible_at": T_LATE,
        "retry_index": 0,
        "evidence_sha256": EVIDENCE_SHA,
    }


def _fallback_body():
    return {
        "capability_class": "implementation",
        "from_route_id": "implementation-primary",
        "to_route_id": "implementation-terra",
        "provider": "openai",
        "model_id": "gpt-5.6-terra",
        "reason_code": "MODEL_ROUTE_FALLBACK_SELECTED",
    }


def _pause_body():
    return {
        "reason_code": "NO_CAPABLE_MODEL_AVAILABLE",
        "capability_class": "design_judgment",
        "next_eligible_at": None,
        "evidence_ids": ["evidence-a", "evidence-b"],
    }


O5_BUDGET_EVENTS = {
    "PROVIDER_CAPACITY_RECORDED": (_capacity_body, None),
    "PROVIDER_BACKOFF_SCHEDULED": (_backoff_body, None),
    "MODEL_FALLBACK_SELECTED": (_fallback_body, "packet-1"),
    "PACKET_PAUSED": (_pause_body, "packet-3"),
}


@pytest.mark.parametrize("event_type", sorted(O5_BUDGET_EVENTS))
def test_o5_budget_event_validates(event_type):
    body_fn, packet_id = O5_BUDGET_EVENTS[event_type]
    event = _budget_event(event_type, body_fn(), packet_id=packet_id)
    result = validate_journal_event(event, None, STATE_ROOT_ID)
    assert result["valid"] is True, result["errors"]


@pytest.mark.parametrize("event_type", sorted(O5_BUDGET_EVENTS))
def test_o5_budget_event_payload_is_closed(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    body_fn, packet_id = O5_BUDGET_EVENTS[event_type]
    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]

    event = _budget_event(event_type, body_fn(), packet_id=packet_id)
    event["payload"][key]["unexpected"] = True
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False

    event = _budget_event(event_type, body_fn(), packet_id=packet_id)
    del event["payload"][key][sorted(event["payload"][key])[0]]
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(O5_BUDGET_EVENTS))
def test_o5_budget_event_body_is_required_for_its_own_type(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    body_fn, packet_id = O5_BUDGET_EVENTS[event_type]
    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    event = _budget_event(event_type, body_fn(), packet_id=packet_id)
    event["payload"][key] = None
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(O5_BUDGET_EVENTS))
def test_o5_budget_body_cannot_ride_on_an_unrelated_event(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    body_fn, _packet_id = O5_BUDGET_EVENTS[event_type]
    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    payload = _base_payload()
    payload[key] = body_fn()
    event = _make_event(
        1, "RUN_ENDED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, None, T_NOW,
        payload=payload,
    )
    result = validate_journal_event(event, None, STATE_ROOT_ID)
    assert result["valid"] is False
    assert any(err["path"] == "/payload/%s" % key for err in result["errors"]), (
        result["errors"])


@pytest.mark.parametrize("event_type", sorted(O5_BUDGET_EVENTS))
def test_o5_budget_event_rejects_an_unknown_reason_code(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    body_fn, packet_id = O5_BUDGET_EVENTS[event_type]
    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    body = body_fn()
    if "reason_code" not in body:
        pytest.skip("%s carries no reason code" % event_type)
    event = _budget_event(event_type, body, packet_id=packet_id)
    event["payload"][key]["reason_code"] = "MADE_UP_REASON"
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


def test_provider_scoped_budget_events_carry_no_packet_id():
    for event_type in ("PROVIDER_CAPACITY_RECORDED", "PROVIDER_BACKOFF_SCHEDULED"):
        body_fn, _ = O5_BUDGET_EVENTS[event_type]
        event = _budget_event(event_type, body_fn(), packet_id="packet-1")
        assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


def test_packet_scoped_budget_events_require_a_packet_id():
    for event_type in ("MODEL_FALLBACK_SELECTED", "PACKET_PAUSED"):
        body_fn, _ = O5_BUDGET_EVENTS[event_type]
        event = _budget_event(event_type, body_fn(), packet_id=None)
        assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


def test_budget_events_never_drive_a_state_transition():
    body_fn, packet_id = O5_BUDGET_EVENTS["PACKET_PAUSED"]
    event = _budget_event("PACKET_PAUSED", body_fn(), packet_id=packet_id)
    event["from_state"] = "READY"
    event["to_state"] = "READY"
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


def test_runtime_and_json_schema_agree_on_the_o5_budget_vocabulary():
    from harness_contracts.v1.execution_plan import CAPABILITY_CLASSES
    from harness_contracts.v1.journal import (
        BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE, BUDGET_REASON_CODES, JOURNAL_EVENT_TYPES)
    from harness_contracts.v1.provider_evidence import CAPACITY_STATES

    schema = json.loads(SCHEMA_PATH.read_text())
    assert set(schema["properties"]["event_type"]["enum"]) == JOURNAL_EVENT_TYPES

    payload_properties = schema["properties"]["payload"]["properties"]
    for key in BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE.values():
        assert payload_properties[key]["additionalProperties"] is False
        assert key not in schema["properties"]["payload"]["required"]

    capacity = payload_properties["provider_capacity"]
    assert set(capacity["properties"]["state"]["enum"]) == CAPACITY_STATES
    backoff = payload_properties["provider_backoff"]
    assert set(backoff["properties"]["reason_code"]["enum"]) == BUDGET_REASON_CODES
    fallback = payload_properties["model_fallback"]
    assert set(fallback["properties"]["capability_class"]["enum"]) == CAPABILITY_CLASSES
    pause = payload_properties["packet_pause"]
    assert set(pause["properties"]["reason_code"]["enum"]) == BUDGET_REASON_CODES


def test_new_schema_branches_are_appended_after_the_workspace_baseline_branch():
    """Task 1's regression: allOf[0] is pinned by test_o4_coordinator_isolation."""
    schema = json.loads(SCHEMA_PATH.read_text())
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    assert (schema["allOf"][0]["then"]["properties"]["payload"]["properties"]
            ["artifacts"]["items"]["properties"]["kind"]) == {"const": "workspace_baseline"}
    branch_types = [
        rule["if"]["properties"]["event_type"].get("const") for rule in schema["allOf"]
    ]
    for event_type in BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE:
        assert event_type in branch_types
        assert branch_types.index(event_type) > branch_types.index(
            "WORKSPACE_BASELINE_RECORDED")


def test_phantom_root_folds_tolerate_the_new_budget_events():
    """reconcile's inventory fold and replay's prefix fold have no state root."""
    from harness_coordinator.v1.recovery import _fold_journal

    events = []
    prev = None
    seq = 1
    for event_type in sorted(O5_BUDGET_EVENTS):
        body_fn, packet_id = O5_BUDGET_EVENTS[event_type]
        event = _budget_event(event_type, body_fn(), packet_id=packet_id,
                              seq=seq, prev=prev)
        events.append(event)
        prev = event
        seq += 1

    packets, counters = _fold_journal("/dev/null", events)
    assert packets == {}
    assert counters["attempts_started_total"] == 0
    for index in range(1, len(events) + 1):
        _fold_journal("/dev/null", events[:index])
