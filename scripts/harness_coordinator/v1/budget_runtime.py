"""Pure O5 budget-accounting and capability-routing decisions.

Every function here is a pure decision over authenticated inputs.  Nothing in
this module writes a file, appends to the journal, invokes a provider, reads
an environment variable, or reads the wall clock.  Time enters only through
the caller-supplied ``now_utc``, and the only time arithmetic performed is
``strptime``/``timedelta``/``strftime`` over already-normalised UTC strings.

Consequences that callers may rely on:

* **Determinism.** Journal events are consumed in authenticated ``seq`` order,
  never list order, so a shuffled input list yields an identical decision.
  Every reason and evidence list is sorted.
* **No mutation.** No argument is written to.  The ``route`` a decision
  carries is a deep copy, so a caller mutating a decision cannot reach into
  the plan.
* **Fail closed.** A malformed plan, packet row, event, or provider snapshot
  produces ``STOP``/``BUDGET_EVIDENCE_INVALID`` rather than an exception, so
  ambiguity can never be mistaken for permission.  This holds even for input
  that makes the plan validator itself raise -- see ``_plan_is_valid``.
* **Nothing untrusted can grant budget.** Journal-derived usage and the folded
  row are reconciled by taking the LARGER usage; a folded row that reports
  less usage than the authenticated journal is an integrity finding, not a
  refund.  Worker-reported usage is never read for accounting at all.

Deliberately out of scope, and owned elsewhere in the plan: the run-level
wall-clock ceiling and graceful-stop state (Task 3), packet-state eligibility
and the human-authority category mapping (Task 4), and writing any of the
events whose payloads this module builds (Tasks 3 and 4).
"""

import copy
import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.execution_plan import CAPABILITY_CLASSES, validate_execution_plan
from harness_contracts.v1.journal import (
    BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE,
    BUDGET_PAYLOAD_SPECS,
    BUDGET_REASON_CODES,
)
from harness_contracts.v1.packet import RE_SHA256, _matches, is_harness_id
from harness_contracts.v1.provider_evidence import validate_provider_capacity_observation
from harness_contracts.v1.worker_result import RE_RFC3339


DECISIONS = frozenset({"ALLOW", "BACKOFF", "FALLBACK", "PAUSE", "STOP", "HUMAN_REQUIRED"})

BUDGET_DECISION_KEYS = (
    "decision", "reason_code", "packet_id", "route", "next_eligible_at", "evidence_ids",
)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Review classes may never reuse the invocation that implemented the work, and
# prefer a different model family for the review itself.
_REVIEW_CAPABILITY_CLASSES = frozenset({"independent_review", "adversarial_audit"})

# Lanes whose ATTEMPT_STARTED events identify an implementer invocation.
_IMPLEMENTATION_LANES = frozenset({"kimi_implementation", "sonnet_implementation"})

# Capacity severity: a snapshot may only move a pair to a MORE restrictive
# state than the authenticated journal already proves.  Mutable cache state
# can restrict work; it can never authorise it.
_CAPACITY_SEVERITY = {
    "AVAILABLE": 0,
    "RATE_LIMITED": 1,
    "ALLOWANCE_EXHAUSTED": 2,
    "UNAVAILABLE": 3,
}

_HARD_CAPACITY_REASONS = {
    "ALLOWANCE_EXHAUSTED": "PROVIDER_ALLOWANCE_EXHAUSTED",
    "UNAVAILABLE": "PROVIDER_ALLOWANCE_UNAVAILABLE",
}


# ---------------------------------------------------------------------------
# Decision construction
# ---------------------------------------------------------------------------


def _decision(
    decision: str,
    reason_code: str,
    packet_id: Optional[str] = None,
    route: Optional[Dict[str, Any]] = None,
    next_eligible_at: Optional[str] = None,
    evidence_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build one closed, immutable-by-convention BudgetDecision."""
    if decision not in DECISIONS:
        raise ValueError("unknown decision %r" % (decision,))
    if reason_code not in BUDGET_REASON_CODES:
        raise ValueError("unknown reason code %r" % (reason_code,))
    return {
        "decision": decision,
        "reason_code": reason_code,
        "packet_id": packet_id,
        "route": copy.deepcopy(route) if route is not None else None,
        "next_eligible_at": next_eligible_at,
        "evidence_ids": sorted(set(evidence_ids or [])),
    }


def _with_packet_id(decision: Dict[str, Any], packet_id: Optional[str]) -> Dict[str, Any]:
    carried = dict(decision)
    carried["packet_id"] = packet_id
    return carried


def budget_event_payload(event_type: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Build the closed journal payload for one O5 budget event.

    Task 3 and Task 4 append these events; building the envelope here keeps
    exactly one place that knows which payload key belongs to which event
    type, instead of four hand-spelled copies at the call sites.
    """
    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE.get(event_type)
    if key is None:
        raise ValueError("%r is not an O5 budget event type" % (event_type,))
    unknown = sorted(set(body) - set(BUDGET_PAYLOAD_SPECS[key]))
    if unknown:
        raise ValueError("%s payload has unknown fields: %s" % (event_type, unknown))
    payload = {
        "packet": None,
        "attempt": None,
        "artifacts": [],
        "classification": None,
        "transition_detail": None,
        "recovery": None,
        "run": None,
        "report": None,
    }
    payload[key] = copy.deepcopy(body)
    return payload


# ---------------------------------------------------------------------------
# Normalised time
# ---------------------------------------------------------------------------


def _normalized_utc(value: Any) -> Optional[str]:
    """Return ``value`` when it is a normalised RFC3339 UTC instant.

    The accepted form is fixed width and always ``Z``-terminated, so string
    comparison over two accepted values is exact chronological comparison --
    no parsing, no timezone handling, no locale.
    """
    if _matches(value, RE_RFC3339):
        return value
    return None


def _shift(timestamp: str, seconds: int) -> Optional[str]:
    """Return ``timestamp`` advanced by ``seconds``, in the same normal form."""
    try:
        moment = datetime.datetime.strptime(timestamp, _TIMESTAMP_FORMAT)
        return (moment + datetime.timedelta(seconds=seconds)).strftime(_TIMESTAMP_FORMAT)
    except (ValueError, OverflowError):
        return None


def _is_exact_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _plan_is_valid(plan: Dict[str, Any]) -> bool:
    """Validate a plan without ever raising out of a decision.

    ``validate_execution_plan`` still raises a raw ``TypeError`` on some legal
    but hostile JSON -- ``"dependencies": null``, ``"capability_class": []``,
    ``"human_stop_categories": [[]]`` -- all plausible hand-authoring slips.
    That defect lives in the contract module and is recorded there for repair;
    this module's unqualified "never raises, always fails closed" promise is
    honoured here regardless of what the validator does.
    """
    try:
        return bool(validate_execution_plan(plan)["valid"])
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Authenticated journal reading
# ---------------------------------------------------------------------------


class _EvidenceError(Exception):
    """An input contradicts authenticated evidence; the decision fails closed."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _ordered_events(journal_events: Any, now: str) -> List[Dict[str, Any]]:
    """Return de-duplicated events in authenticated sequence order.

    Input list order is discarded: ``seq`` is the authenticated order, so a
    caller may hand these events over in any order and get the same decision.
    Duplicates -- byte-identical replays of one event -- collapse to one.
    """
    if not isinstance(journal_events, list):
        raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
    by_identity: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
    for event in journal_events:
        if not isinstance(event, dict):
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        seq = event.get("seq")
        digest = event.get("event_sha256")
        if not _is_exact_int(seq) or seq < 1 or not _matches(digest, RE_SHA256):
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        event_at = _normalized_utc(event.get("event_at"))
        if event_at is None or event_at > now:
            # An event stamped after the caller's clock is a clock regression:
            # the run cannot have observed the future.
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        identity = (seq, digest)
        existing = by_identity.get(identity)
        if existing is not None and existing != event:
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        by_identity[identity] = event

    ordered = [by_identity[key] for key in sorted(by_identity)]
    seen_seqs: Set[int] = set()
    previous_at = None
    for event in ordered:
        seq = event["seq"]
        if seq in seen_seqs:
            # Two different events claiming one sequence number.
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        seen_seqs.add(seq)
        event_at = event["event_at"]
        if previous_at is not None and event_at < previous_at:
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        previous_at = event_at
    return ordered


def _evidence_id(event: Dict[str, Any]) -> str:
    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return event_id
    return event["event_sha256"]


def _journal_usage(events: List[Dict[str, Any]], packet_id: str) -> Dict[str, Any]:
    """Derive one packet's budget usage from authenticated events only.

    Worker-reported usage is deliberately not read: ``WORKER_RESULT_RECORDED``
    contributes nothing to any counter here, so no worker claim -- honest or
    forged -- can move a budget in either direction.
    """
    usage = {"attempts_started": 0, "infra_retries_used": 0, "revise_cycles_used": 0}
    evidence_ids: List[str] = []
    for event in events:
        if event.get("packet_id") != packet_id:
            continue
        event_type = event.get("event_type")
        cause = event.get("cause")
        if event_type == "ATTEMPT_STARTED":
            usage["attempts_started"] += 1
        elif event_type == "ATTEMPT_FINISHED" and cause == "infra_retry":
            usage["infra_retries_used"] += 1
        elif event_type == "STATE_TRANSITION" and cause == "revision_requeued":
            usage["revise_cycles_used"] += 1
        else:
            continue
        evidence_ids.append(_evidence_id(event))
    usage["evidence_ids"] = evidence_ids
    return usage


def _implementer_invocations(events: List[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    """Return the ``(provider, model)`` pairs that have implemented work."""
    invocations: Set[Tuple[str, str]] = set()
    for event in events:
        if event.get("event_type") != "ATTEMPT_STARTED":
            continue
        attempt = (event.get("payload") or {}).get("attempt") or {}
        if attempt.get("lane") not in _IMPLEMENTATION_LANES:
            continue
        worker = attempt.get("worker") or {}
        provider, model = worker.get("provider"), worker.get("model")
        if isinstance(provider, str) and isinstance(model, str):
            invocations.add((provider, model))
    return invocations


# ---------------------------------------------------------------------------
# Provider capacity
# ---------------------------------------------------------------------------


def _pair_key(provider: Any, model_id: Any) -> str:
    return "%s/%s" % (provider, model_id)


def _observation_key(observation: Dict[str, Any]) -> str:
    return _pair_key(observation.get("provider"), observation.get("model_id"))


def _validated_observation(candidate: Any) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
    if not validate_provider_capacity_observation(candidate)["valid"]:
        raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
    return candidate


def _restriction_rank(observation: Dict[str, Any]) -> Tuple[int, int, str]:
    """Order two observations of one pair from least to most restrictive."""
    severity = _CAPACITY_SEVERITY[observation["state"]]
    reset_at = observation.get("reset_at")
    # A hard state with no authenticated reset time is the most restrictive
    # thing an observation can say: nothing proves the window ever reopens.
    unbounded = 1 if severity > 0 and reset_at is None else 0
    return (severity, unbounded, reset_at or "")


def _capacity_from_journal(events: List[Dict[str, Any]], now: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Fold authenticated capacity observations, last authenticated one wins."""
    latest: Dict[str, Dict[str, Any]] = {}
    evidence_ids: List[str] = []
    for event in events:
        if event.get("event_type") != "PROVIDER_CAPACITY_RECORDED":
            continue
        observation = _validated_observation(
            (event.get("payload") or {}).get("provider_capacity"))
        observed_at = observation["observed_at"]
        if observed_at > now:
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        key = _observation_key(observation)
        previous = latest.get(key)
        if previous is not None and observed_at < previous["observed_at"]:
            # Appended later but observed earlier: stale evidence being
            # replayed to clear a newer exhaustion.  Refuse rather than let
            # ordering decide whether a model is spendable.
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        latest[key] = observation
        evidence_ids.append(_evidence_id(event))
    return latest, evidence_ids


def _backoff_history(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Count and bound the backoff already scheduled for each provider pair."""
    history: Dict[str, Dict[str, Any]] = {}
    for event in events:
        if event.get("event_type") != "PROVIDER_BACKOFF_SCHEDULED":
            continue
        body = (event.get("payload") or {}).get("provider_backoff")
        if not isinstance(body, dict):
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        next_eligible_at = _normalized_utc(body.get("next_eligible_at"))
        if next_eligible_at is None:
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        key = _pair_key(body.get("provider"), body.get("model_id"))
        record = history.setdefault(key, {"count": 0, "next_eligible_at": None})
        record["count"] += 1
        if record["next_eligible_at"] is None or next_eligible_at > record["next_eligible_at"]:
            record["next_eligible_at"] = next_eligible_at
    return history


def _capacity_snapshot(provider_state: Any) -> Dict[str, Dict[str, Any]]:
    """Validate the caller's capacity snapshot without trusting its keys."""
    if provider_state is None:
        return {}
    if not isinstance(provider_state, dict):
        raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
    snapshot: Dict[str, Dict[str, Any]] = {}
    for key in sorted(provider_state):
        observation = _validated_observation(provider_state[key])
        if key != _observation_key(observation):
            # A key that disagrees with its own observation could mask a
            # different model's state; refuse instead of picking one.
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        snapshot[key] = observation
    return snapshot


def _effective_capacity(
    journal_capacity: Dict[str, Dict[str, Any]],
    snapshot: Dict[str, Dict[str, Any]],
    key: str,
) -> Optional[Dict[str, Any]]:
    """Return the more restrictive of the journal and snapshot observations."""
    from_journal = journal_capacity.get(key)
    from_snapshot = snapshot.get(key)
    if from_journal is None:
        return from_snapshot
    if from_snapshot is None:
        return from_journal
    if _restriction_rank(from_snapshot) > _restriction_rank(from_journal):
        return from_snapshot
    return from_journal


def _capacity_eligibility(
    observation: Optional[Dict[str, Any]],
    backoff: Dict[str, Any],
    plan_backoff: Dict[str, Any],
    now: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Return ``(eligible, reason_code, next_eligible_at)`` for one pair.

    An allowance that is exhausted with no authenticated reset time yields no
    window at all: the design forbids guessing when a subscription reopens, so
    the packet pauses instead of waiting on an invented deadline.  A rate limit
    is different -- the plan's own bounded schedule, not a guess about the
    provider, supplies its finite window.
    """
    if observation is None:
        return True, None, None
    state = observation["state"]
    if state == "AVAILABLE":
        return True, None, None

    reset_at = _normalized_utc(observation.get("reset_at"))
    retries_used = backoff.get("count", 0)
    max_retries = plan_backoff.get("max_retries")
    if not _is_exact_int(max_retries) or max_retries < 0:
        raise _EvidenceError("BUDGET_EVIDENCE_INVALID")

    if state == "RATE_LIMITED":
        if retries_used >= max_retries:
            return False, "PROVIDER_BACKOFF_RETRIES_EXHAUSTED", None
        window = reset_at
        if window is None:
            base = plan_backoff.get("base_delay_seconds")
            ceiling = plan_backoff.get("max_delay_seconds")
            if not _is_exact_int(base) or not _is_exact_int(ceiling):
                raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
            delay = min(base * (2 ** min(retries_used, 30)), ceiling)
            window = _shift(observation["observed_at"], delay)
            recorded = backoff.get("next_eligible_at")
            if recorded is not None and (window is None or recorded > window):
                # A durably recorded schedule is honoured over a recomputed
                # one: a restart must not shorten a backoff already promised.
                window = recorded
        if window is None:
            raise _EvidenceError("BUDGET_EVIDENCE_INVALID")
        if now >= window:
            return True, None, None
        return False, "PROVIDER_BACKOFF_PENDING", window

    # ALLOWANCE_EXHAUSTED / UNAVAILABLE.
    if reset_at is None:
        return False, _HARD_CAPACITY_REASONS[state], None
    if now >= reset_at:
        return True, None, None
    return False, "PROVIDER_ALLOWANCE_RESET_PENDING", reset_at


# ---------------------------------------------------------------------------
# Plan-pinned route ordering
# ---------------------------------------------------------------------------


def _ordered_hops(plan: Dict[str, Any], capability_class: str) -> List[Dict[str, Any]]:
    """Walk the plan's pinned fallback chain for one capability class.

    The chain starts at the class's first declared hop and follows each hop's
    explicit ``fallback_to``; where none is declared, the next declared hop is
    the next hop.  Nothing is discovered at runtime, so a provider catalog
    change, an alias, or a registry edit cannot reorder or extend this list.
    Cycles are re-detected here even though ``validate_execution_plan``
    already refuses them, because this is the last gate before a route is
    handed to an invocation.
    """
    hops = plan["routes"][capability_class]
    by_id = {}
    for hop in hops:
        by_id[hop["route_id"]] = hop
    index_of = dict((hop["route_id"], index) for index, hop in enumerate(hops))
    same_class_ids = set(by_id)

    ordered: List[Dict[str, Any]] = []
    visited: Set[str] = set()
    current = hops[0]
    while current is not None:
        route_id = current["route_id"]
        if route_id in visited:
            raise _EvidenceError("MODEL_ROUTE_FALLBACK_CYCLE")
        visited.add(route_id)
        ordered.append(current)

        fallback_to = current.get("fallback_to")
        if fallback_to is None:
            position = index_of[route_id] + 1
            current = hops[position] if position < len(hops) else None
            continue
        if fallback_to not in same_class_ids:
            raise _EvidenceError("MODEL_ROUTE_CROSS_CLASS_FALLBACK")
        current = by_id[fallback_to]
    return ordered


# ---------------------------------------------------------------------------
# Public decisions
# ---------------------------------------------------------------------------


def select_capable_route(
    plan: Any,
    capability_class: Any,
    journal_events: Any,
    provider_state: Any,
    now_utc: Any,
) -> Dict[str, Any]:
    """Choose the plan-pinned route for one capability class.

    Fallback stays inside the class, follows the plan's own acyclic chain, and
    never changes packet authority.  Availability alone never authorises a
    downgrade: a disabled or unqualified hop is skipped, never used, and when
    no hop is usable the caller is told to pause rather than to substitute.
    """
    now = _normalized_utc(now_utc)
    if now is None:
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")

    if not isinstance(plan, dict) or not _plan_is_valid(plan):
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")

    if (not isinstance(capability_class, str)
            or capability_class not in CAPABILITY_CLASSES
            or capability_class not in plan["routes"]):
        return _decision("STOP", "MODEL_ROUTE_NOT_IN_PLAN")

    try:
        events = _ordered_events(journal_events, now)
        hops = _ordered_hops(plan, capability_class)
        journal_capacity, capacity_evidence = _capacity_from_journal(events, now)
        backoff_history = _backoff_history(events)
        snapshot = _capacity_snapshot(provider_state)
    except _EvidenceError as exc:
        return _decision("STOP", exc.reason_code)

    evidence_ids = list(capacity_evidence)
    for key in sorted(snapshot):
        evidence_ids.append(snapshot[key]["evidence_sha256"])

    implementers = (_implementer_invocations(events)
                    if capability_class in _REVIEW_CAPABILITY_CLASSES else set())
    implementer_providers = set(provider for provider, _model in implementers)

    eligible: List[Tuple[int, Dict[str, Any]]] = []
    windows: List[Tuple[str, str]] = []
    try:
        for index, hop in enumerate(hops):
            if hop.get("enabled") is not True:
                continue
            qualification_id = hop.get("qualification_id")
            if not is_harness_id(qualification_id):
                continue
            pair = (hop["provider"], hop["model_id"])
            if pair in implementers:
                # The same invocation cannot implement and then review itself.
                continue
            key = _pair_key(hop["provider"], hop["model_id"])
            observation = _effective_capacity(journal_capacity, snapshot, key)
            is_eligible, reason_code, window = _capacity_eligibility(
                observation, backoff_history.get(key, {}), plan["provider_backoff"], now)
            if is_eligible:
                eligible.append((index, hop))
            elif window is not None and reason_code is not None:
                windows.append((window, reason_code))
    except _EvidenceError as exc:
        return _decision("STOP", exc.reason_code)

    if not eligible:
        if windows:
            window, reason_code = min(windows)
            return _decision("BACKOFF", reason_code, next_eligible_at=window,
                             evidence_ids=evidence_ids)
        return _decision("PAUSE", "NO_CAPABLE_MODEL_AVAILABLE", evidence_ids=evidence_ids)

    chosen = eligible[0]
    if implementer_providers:
        diverse = [entry for entry in eligible
                   if entry[1]["provider"] not in implementer_providers]
        if not diverse:
            # Every remaining reviewer shares the implementer's family.  Say so
            # rather than quietly running a weaker review -- and say it with the
            # SPECIFIC code, not the generic human-authority one the deployment
            # and governed-content gates also emit, so a paused row records
            # which of the two actually happened.
            return _decision("HUMAN_REQUIRED", "MODEL_ROUTE_REVIEWER_IDENTITY_CONFLICT",
                             evidence_ids=evidence_ids)
        chosen = diverse[0]

    index, route = chosen
    if index == 0:
        return _decision("ALLOW", "MODEL_ROUTE_SELECTED", route=route,
                         evidence_ids=evidence_ids)
    return _decision("FALLBACK", "MODEL_ROUTE_FALLBACK_SELECTED", route=route,
                     evidence_ids=evidence_ids)


def evaluate_preclaim(
    plan: Any,
    packet: Any,
    journal_events: Any,
    provider_state: Any,
    now_utc: Any,
) -> Dict[str, Any]:
    """Decide whether one plan member may be claimed, and on which route.

    Budget is settled before routing: a packet that has spent its plan limits
    stops on its own budget, whatever the providers happen to be doing.
    """
    now = _normalized_utc(now_utc)
    if now is None:
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")

    if not isinstance(plan, dict) or not _plan_is_valid(plan):
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")

    if not isinstance(packet, dict):
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")
    packet_id = packet.get("packet_id")
    if not is_harness_id(packet_id):
        return _decision("STOP", "BUDGET_EVIDENCE_INVALID")

    plan_packet = None
    for row in plan["packets"]:
        if row["packet_id"] == packet_id:
            plan_packet = row
            break
    if plan_packet is None:
        return _decision("STOP", "PLAN_SCOPE_PACKET_OUTSIDE_PLAN", packet_id=packet_id)
    if packet.get("packet_sha256") != plan_packet["packet_sha256"]:
        return _decision("STOP", "PLAN_SCOPE_PACKET_DIGEST_MISMATCH", packet_id=packet_id)

    try:
        events = _ordered_events(journal_events, now)
    except _EvidenceError as exc:
        return _decision("STOP", exc.reason_code, packet_id=packet_id)

    usage = _journal_usage(events, packet_id)
    evidence_ids = list(usage["evidence_ids"])
    budgets = plan_packet["budgets"]

    # (used, limit, reason_code, boundary).  Attempts count claims, so the last
    # permitted claim is the one that reaches the limit.  Retries and revision
    # cycles count re-entries the coordinator has ALREADY granted, so the claim
    # that follows the final granted retry is itself that retry -- the two
    # boundaries genuinely differ by one, by construction rather than by
    # accident.
    checks = (
        ("attempts_started", "attempt_limit", "PACKET_BUDGET_ATTEMPTS_EXHAUSTED", 0),
        ("infra_retries_used", "retry_limit", "PACKET_BUDGET_RETRIES_EXHAUSTED", 1),
        ("revise_cycles_used", "revision_limit", "PACKET_BUDGET_REVISIONS_EXHAUSTED", 1),
    )
    for counter, limit_key, reason_code, slack in checks:
        limit = budgets[limit_key]
        if not _is_exact_int(limit) or limit < 0:
            return _decision("STOP", "BUDGET_EVIDENCE_INVALID", packet_id=packet_id)
        row_used = packet.get(counter)
        if not _is_exact_int(row_used) or row_used < 0:
            return _decision("STOP", "BUDGET_EVIDENCE_INVALID", packet_id=packet_id)
        journal_used = usage[counter]
        if journal_used > row_used:
            # The authenticated journal proves more usage than the folded row
            # reports.  A cache may never be the reason a budget looks larger.
            return _decision("STOP", "BUDGET_EVIDENCE_INVALID", packet_id=packet_id)
        used = max(row_used, journal_used)
        if used >= limit + slack:
            return _decision("STOP", reason_code, packet_id=packet_id,
                             evidence_ids=evidence_ids)

    routed = select_capable_route(
        plan, plan_packet["capability_class"], journal_events, provider_state, now)
    routed = _with_packet_id(routed, packet_id)
    routed["evidence_ids"] = sorted(set(routed["evidence_ids"]) | set(evidence_ids))
    return routed


__all__ = [
    "BUDGET_DECISION_KEYS",
    "DECISIONS",
    "budget_event_payload",
    "evaluate_preclaim",
    "select_capable_route",
]
