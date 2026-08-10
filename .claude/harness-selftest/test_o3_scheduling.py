"""Deterministic scheduling TDD for O3-P3's scheduler.select_next."""

from typing import Any, Dict

from harness_coordinator.v1.scheduler import eligible_packets, select_next


def _pkt(
    enqueue_seq: int,
    state: str = "READY",
    lane: str = "kimi_implementation",
    dependency_ids=None,
    retry_limit: int = 2,
    attempts_started: int = 0,
    open_attempt=None,
    earliest_next_attempt_at=None,
    terminal_seal_sha256=None,
) -> Dict[str, Any]:
    return {
        "enqueue_seq": enqueue_seq,
        "state": state,
        "lane": lane,
        "dependency_ids": dependency_ids or [],
        "retry_limit": retry_limit,
        "attempts_started": attempts_started,
        "open_attempt": open_attempt,
        "earliest_next_attempt_at": earliest_next_attempt_at,
        "terminal_seal_sha256": terminal_seal_sha256,
    }


def test_select_next_empty_returns_none():
    assert select_next({}, [], "2026-08-10T00:00:00Z") is None


def test_select_next_no_eligible_packets_returns_none():
    packets = {"p1": _pkt(1, state="BLOCKED")}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None


def test_f6_selection_follows_enqueue_seq_not_packet_id():
    """Five packets enrolled in reverse alphabetical order -- selection
    must follow enqueue_seq, not packet_id string order."""
    packets = {
        "p5": _pkt(1),
        "p4": _pkt(2),
        "p3": _pkt(3),
        "p2": _pkt(4),
        "p1": _pkt(5),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") == "p5"


def test_f7_identical_fold_replayed_twice_selects_identically():
    packets = {
        "p1": _pkt(1),
        "p2": _pkt(2),
    }
    first = select_next(packets, [], "2026-08-10T00:00:00Z")
    second = select_next(packets, [], "2026-08-10T00:00:00Z")
    assert first == second == "p1"


def test_f9_packet_at_retry_budget_never_selected():
    """retry_limit=2 means attempts_started <= 3 is eligible; at 3 it's
    exhausted and must never be selected again."""
    packets = {"p1": _pkt(1, retry_limit=2, attempts_started=3)}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None

    packets2 = {"p1": _pkt(1, retry_limit=2, attempts_started=2)}
    assert select_next(packets2, [], "2026-08-10T00:00:00Z") == "p1"


def test_f3_one_quarantined_packet_does_not_block_independent_ready_packet():
    packets = {
        "p1": _pkt(1, state="QUARANTINED", terminal_seal_sha256="0" * 64),
        "p2": _pkt(2, state="READY"),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") == "p2"


def test_blocked_packet_never_selected_even_with_lowest_enqueue_seq():
    packets = {
        "p1": _pkt(1, state="BLOCKED"),
        "p2": _pkt(2, state="READY"),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") == "p2"


def test_human_required_packet_does_not_block_independent_ready_packet():
    packets = {
        "p1": _pkt(1, state="HUMAN_REQUIRED", terminal_seal_sha256="0" * 64),
        "p2": _pkt(2, state="READY"),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") == "p2"


def test_f10_disabled_lane_packet_not_selected_others_still_run():
    packets = {
        "p1": _pkt(1, lane="kimi_implementation"),
        "p2": _pkt(2, lane="grok_verification"),
    }
    assert select_next(packets, ["kimi_implementation"], "2026-08-10T00:00:00Z") == "p2"


def test_all_lanes_disabled_returns_none():
    packets = {"p1": _pkt(1, lane="kimi_implementation")}
    assert select_next(packets, ["kimi_implementation"], "2026-08-10T00:00:00Z") is None


def test_dependency_not_accepted_excludes_even_if_state_says_ready():
    """Defense in depth: even if a packet's fold state were somehow READY
    with an unaccepted dependency, select_next must still exclude it --
    this is the requirement design section 4 states explicitly, distinct
    from the BLOCKED->READY promotion gate itself."""
    packets = {
        "dep": _pkt(1, state="RUNNING"),
        "p2": _pkt(2, state="READY", dependency_ids=["dep"]),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None


def test_dependency_accepted_allows_selection():
    packets = {
        "dep": _pkt(1, state="ACCEPTED", terminal_seal_sha256="0" * 64),
        "p2": _pkt(2, state="READY", dependency_ids=["dep"]),
    }
    assert select_next(packets, [], "2026-08-10T00:00:00Z") == "p2"


def test_open_attempt_excludes_packet():
    packets = {"p1": _pkt(1, open_attempt=1)}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None


def test_terminal_seal_excludes_packet_even_if_state_says_ready():
    """Defense in depth: a sealed-terminal packet must never be selected
    again, regardless of what its (stale/corrupt) state field says."""
    packets = {"p1": _pkt(1, state="READY", terminal_seal_sha256="0" * 64)}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None


def test_backoff_gate_excludes_until_earliest_next_attempt_at():
    packets = {"p1": _pkt(1, earliest_next_attempt_at="2026-08-10T00:05:00Z")}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None
    assert select_next(packets, [], "2026-08-10T00:05:00Z") == "p1"
    assert select_next(packets, [], "2026-08-10T00:10:00Z") == "p1"


def test_eligible_packets_and_select_next_share_the_same_filter():
    """Both entry points must apply the identical predicate -- exercise
    every filter condition in one fold and confirm eligible_packets'
    output and select_next's head agree exactly (guards against the two
    functions silently diverging into separately-maintained copies)."""
    packets = {
        "terminal": _pkt(1, terminal_seal_sha256="0" * 64),
        "open_attempt": _pkt(2, open_attempt=1),
        "wrong_lane": _pkt(3, lane="grok_verification"),
        "budget_exhausted": _pkt(4, retry_limit=1, attempts_started=2),
        "blocked_dep": _pkt(5, dependency_ids=["never-enrolled"]),
        "not_yet_due": _pkt(6, earliest_next_attempt_at="2099-01-01T00:00:00Z"),
        "blocked": _pkt(7, state="BLOCKED"),
        "eligible-a": _pkt(8),
        "eligible-b": _pkt(9),
    }
    result = eligible_packets(packets, ["grok_verification"], "2026-08-10T00:00:00Z")
    assert result == ["eligible-a", "eligible-b"]
    assert select_next(packets, ["grok_verification"], "2026-08-10T00:00:00Z") == "eligible-a"


def test_eligible_packets_returns_full_ordered_set():
    packets = {
        "p3": _pkt(3),
        "p1": _pkt(1),
        "p2": _pkt(2, state="BLOCKED"),
    }
    assert eligible_packets(packets, [], "2026-08-10T00:00:00Z") == ["p1", "p3"]

    packets2 = {"p1": _pkt(1), "p2": _pkt(2), "p3": _pkt(3)}
    assert eligible_packets(packets2, [], "2026-08-10T00:00:00Z") == ["p1", "p2", "p3"]


def test_retry_limit_boolean_fails_closed_not_treated_as_budget_1():
    """H6-equivalent for this module: a boolean retry_limit must not be
    silently treated as an integer budget of 1 (isinstance(x, bool) is a
    subclass of int in Python) -- but a malformed/unreadable budget must
    fail CLOSED (ineligible), never fail open into unbounded retries."""
    packets = {"p1": _pkt(1, retry_limit=True, attempts_started=0)}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None


def test_retry_limit_none_or_missing_fails_closed_not_unbounded():
    """An absent/unknown retry_limit must make a packet ineligible, not
    unboundedly retryable -- the exact failure mode ('the harness must
    never loop against depleted provider allowance') this packet exists
    to prevent."""
    packets = {"p1": _pkt(1, retry_limit=None, attempts_started=999)}
    assert select_next(packets, [], "2026-08-10T00:00:00Z") is None

    packets2 = {"p1": {"enqueue_seq": 1, "state": "READY", "attempts_started": 999}}
    assert select_next(packets2, [], "2026-08-10T00:00:00Z") is None
