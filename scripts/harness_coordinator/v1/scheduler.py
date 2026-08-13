"""Deterministic packet scheduling for the harness coordinator v1.

Implements design section 4's ``select_next`` exactly: a pure function over
the journal-derived fold (as produced by
``harness_coordinator.v1.recovery._fold_journal``) plus an explicit ``now``
(D0.4 -- no implicit clock). No filesystem I/O, no process state, no lock
files consulted. This is what makes scheduling reproducible from durable
state alone (fixtures F6, F7, F8) and what guarantees a quarantined,
blocked, or human-required packet never aborts a scheduling pass (fixture
F3) -- such packets are simply filtered out of ``eligible`` and the pass
continues.

``now`` and every ``earliest_next_attempt_at`` must be in the harness's
canonical RFC3339 UTC form, ``^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$``
(``harness_contracts.v1.worker_result.RE_RFC3339``) -- the backoff gate
compares them as plain strings, which is only lexicographically correct for
that exact fixed-width, no-fractional-seconds, ``Z``-suffixed form. A
caller supplying any other valid ISO-8601 variant (fractional seconds, an
explicit ``+00:00`` offset, etc.) gets a silently wrong -- not a raised --
answer. No caller exists yet to enforce this; a future caller must produce
``now`` via the same canonical formatting the rest of the harness already
uses for every other timestamp field, never invent its own.
"""

from typing import Any, Dict, List, Optional, Set


def _is_eligible(
    packet_id: str,
    pkt: Dict[str, Any],
    packets: Dict[str, Dict[str, Any]],
    disabled: Set[str],
    now: str,
    plan_members: Optional[Set[str]] = None,
) -> bool:
    """The single filter both ``select_next`` and ``eligible_packets``
    apply -- one predicate, not two independently-maintained copies, so a
    future edit cannot silently guard one entry point and not the other.

    ``plan_members`` is ``None`` for an ungoverned (no-plan) selection,
    which preserves every prior caller's behavior exactly.  When a plan IS
    bound, it is the closed set of that plan's own member packet_ids: a
    packet the fold still knows about (e.g. enrolled under an earlier run,
    before this run's plan ever bound) but that is not itself a member of
    THIS plan must never be selected -- not because it is ineligible for
    some ordinary scheduling reason, but because it is out of scope for
    this run entirely.  Selecting it would hand it to the pre-claim gate,
    which has no plan row to evaluate it against; excluding it here, at the
    one shared predicate, is the root-cause fix rather than a reactive
    check further down the pipeline.
    """
    if plan_members is not None and packet_id not in plan_members:
        return False
    if pkt.get("state") != "READY":
        return False
    if pkt.get("terminal_seal_sha256") is not None:
        return False
    if pkt.get("open_attempt") is not None:
        return False
    if pkt.get("lane") in disabled:
        return False

    retry_limit = pkt.get("retry_limit")
    attempts_started = pkt.get("attempts_started", 0)
    if isinstance(retry_limit, int) and not isinstance(retry_limit, bool):
        if attempts_started >= retry_limit + 1:
            return False
    else:
        # An absent/None/malformed retry_limit means the budget is
        # unknown -- fail CLOSED (ineligible), not open. Unbounded
        # retries on a packet with no legible budget is exactly the
        # "harness must never loop against depleted allowance" failure
        # mode this whole packet exists to prevent. Contract validation
        # of retry_limit's type/presence is P1's job at enrollment; this
        # is a second, independent line of defense at the scheduling
        # boundary, not a substitute for it.
        return False

    deps = pkt.get("dependency_ids") or []
    if not all(packets.get(dep, {}).get("state") == "ACCEPTED" for dep in deps):
        return False

    earliest = pkt.get("earliest_next_attempt_at")
    if earliest is not None and earliest > now:
        return False

    return True


def _plan_member_ids(plan: Optional[Dict[str, Any]]) -> Optional[Set[str]]:
    """The closed set of a bound plan's own member packet_ids, or ``None``.

    ``None`` (no plan supplied) means "no plan-scope restriction" -- the
    exact prior, ungoverned behavior -- rather than an empty, universally-
    excluding set.
    """
    if plan is None:
        return None
    return {row.get("packet_id") for row in plan.get("packets", [])}


def select_next(
    packets: Dict[str, Dict[str, Any]],
    disabled_lanes: List[str],
    now: str,
    plan: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return the packet_id of the next packet to run, or ``None``.

    ``packets`` is the fold's packet-state mapping (as returned by
    ``recovery._fold_journal``'s first element). Selection rule (design
    section 4): minimum ``(enqueue_seq, packet_id)`` among packets passing
    ``_is_eligible``.

    ``enqueue_seq`` is provably unique (it is the packet's own
    ``PACKET_ENROLLED`` event ``seq``, and ``store.append_journal``'s
    compare-and-swap makes a duplicate ``seq`` impossible), so the
    ``packet_id`` tiebreak can never actually fire -- it exists only to
    make the ordering total by construction, per design section 4.

    Every packet considered must carry ``enqueue_seq`` (a bare, not
    ``.get()``, lookup on the min key) -- a fold-produced packet missing it
    is a structural impossibility upstream, and raising loudly here beats
    silently mis-ordering the schedule.

    ``plan``, when supplied, scopes selection to that plan's own member
    packets (see ``_is_eligible``'s ``plan_members`` docstring). Omitting it
    preserves the exact ungoverned behavior every existing caller relies on.
    """
    disabled = set(disabled_lanes or [])
    plan_members = _plan_member_ids(plan)
    eligible = [pid for pid, pkt in packets.items()
               if _is_eligible(pid, pkt, packets, disabled, now, plan_members)]
    if not eligible:
        return None
    return min(eligible, key=lambda pid: (packets[pid]["enqueue_seq"], pid))


def eligible_packets(
    packets: Dict[str, Dict[str, Any]],
    disabled_lanes: List[str],
    now: str,
    plan: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Return every eligible packet_id, in selection order.

    A genuine wrapper around ``_is_eligible`` -- the same predicate
    ``select_next`` uses, not a second hand-maintained copy -- useful for
    the morning report and for tests that need to see the full eligible
    set rather than just the head. ``plan`` has the same meaning as in
    ``select_next``.
    """
    disabled = set(disabled_lanes or [])
    plan_members = _plan_member_ids(plan)
    eligible = [pid for pid, pkt in packets.items()
               if _is_eligible(pid, pkt, packets, disabled, now, plan_members)]
    return sorted(eligible, key=lambda pid: (packets[pid]["enqueue_seq"], pid))
