"""Scheduling/transition replay for the harness coordinator v1.

**Implements 3 of design section 10.2's 9 replay checks -- NOT the full
determinism proof; do not read this module as design 10.2 complete.**
What IS implemented: (1) journal chain/sequence/chronology validity, via
``read_journal``; (2) transition legality against ``CAUSE_EDGES``, via a
full fold of the whole journal (``_fold_journal`` already validates every
``(from_state, to_state)`` edge and raises on any illegal one -- a clean
fold over the whole journal genuinely IS this check, not a stand-in for
it); (4) the scheduling CHOICE at every ``ATTEMPT_STARTED`` -- walks the
journal from seq 1 and, at each one, independently re-derives what
``scheduler.select_next`` would have chosen given the fold state
immediately BEFORE that event, and compares it to what was actually
recorded. Plan-aware (O5 Task 4): the plan actually bound to that event's
own ``run_id`` as of that point in the journal is resolved via
``recovery.bound_execution_plan_for_run`` and passed to ``select_next``,
so a plan's scope restriction is part of the re-derivation, not just the
original decision -- otherwise a correctly plan-scoped choice would
falsely diverge from an unscoped re-derivation. **NOT implemented, and
not silently claimed:** (3) re-running
``classify_attempt`` over the stored ``attempt_outcome.json``/
``provider_evidence.json`` to prove the CLASSIFICATION decision (not
just its legality) was reproducible; (5) backoff timing (moot today --
``INFRA_BACKOFF_SECONDS`` from design 5.4 is itself unbuilt, see the
integration-gate note in P3R's ``classify_runtime.py``); (6)
promotion-vs-dependency-states cross-check; (7) recorded artifact digests
vs. what's actually on disk; (8) ``VERDICT_RECORDED`` bundle replay via
``validate_replay_bundle``; (9) all nine design 9.2 reconciliation
invariants re-checked at the final journal head -- this module never
calls ``compute_reconciliation`` at all, that is ``reconcile.py``'s job
on a SEPARATE artifact, not this one's. These six are real, named future
work, not oversights -- flagged for whoever picks up the final O3
integration gate.

Reuses O3-P2's ``recovery._fold_journal`` (never reimplemented) by
re-folding each journal prefix -- O(n^2) in the number of events, an
accepted cost for a read-only diagnostic CLI, not a hot coordinator path.
Reuses O3-P3's ``scheduler.select_next`` directly for the same reason.

Pure over durable inputs: no process state, no wall clock, no lock files
-- exactly design 10.2's stated input list.

Prefix folds (one per ATTEMPT_STARTED) are deliberately folded against a
non-existent seal directory, not the real one -- see the comment at
``_prefix_fold_root`` below for why: the real state_root's terminal
seals are the run's FINAL ones, and checking an early prefix's
in-progress packet state against a seal written for its eventual
terminal state spuriously fails on every journal that has any
terminal packet at all. Only the final, whole-journal fold uses the
real ``state_root``.
"""

import os
from typing import Any, Dict, List

from harness_coordinator.v1.reconcile import _read_manifest_read_only
from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, bound_execution_plan_for_run
from harness_coordinator.v1.scheduler import select_next
from harness_coordinator.v1.store import JournalChainBroken, JournalHeadMoved, read_journal


def replay_schedule(state_root: str, state_root_id: str) -> Dict[str, Any]:
    """Replay every ATTEMPT_STARTED's scheduling decision and every
    event's transition legality (implicitly, via re-folding). Returns a
    report with ``replay_passed`` and an itemized ``divergences`` list --
    never raises for an ordinary divergence, only for a broken journal
    (which is itself the most important thing to report, not swallow).

    Validates MANIFEST.json first (same check ``build_reconciliation_report``
    uses -- see its docstring): a missing or wrong-id state root must not
    replay as a vacuously "passing," zero-event report.
    """
    _read_manifest_read_only(state_root, state_root_id)

    journal_path = os.path.join(state_root, "journal.ndjson")
    try:
        journal_events, torn_tail = read_journal(journal_path, state_root_id=state_root_id)
    except (JournalChainBroken, JournalHeadMoved) as exc:
        return {
            "journal_chain_valid": False,
            "journal_head": {"seq": 0},
            "events_replayed": 0,
            "divergences": [{"seq": None, "code": type(exc).__name__, "message": str(exc)}],
            "replay_passed": False,
        }

    divergences: List[Dict[str, Any]] = []
    disabled_lanes: List[str] = []

    # _fold_journal's terminal-seal consistency check (design 3.5 step 5)
    # reads state/terminal/*.seal.json under whatever ``state_root`` it's
    # given. A PREFIX fold represents a hypothetical earlier point in the
    # run -- but the real state_root's seal files are the FINAL, current
    # ones (e.g. a packet that later became ACCEPTED already has its real
    # seal on disk). Folding an early prefix against those real seals
    # spuriously fails: the prefix's packet state (still READY/RUNNING)
    # will never match a seal written for its eventual terminal state.
    # Point prefix folds at a path whose state/terminal/ subdirectory is
    # guaranteed not to exist (nothing is created there -- _fold_journal
    # only checks os.path.isdir), so the seal check is a no-op for
    # prefixes; the FINAL full-journal fold below uses the real
    # ``state_root`` and legitimately gets the real seal check.
    _prefix_fold_root = os.path.join(state_root, ".o3-replay-prefix-fold-root")

    for i, event in enumerate(journal_events):
        if event.get("event_type") != "ATTEMPT_STARTED":
            continue
        try:
            prior_packets, prior_counters = _fold_journal(_prefix_fold_root, journal_events[:i])
        except IntegrityError as exc:
            divergences.append({"seq": event.get("seq"), "code": "FOLD_FAILED_AT_PREFIX", "message": exc.message})
            continue
        disabled = prior_counters.get("disabled_lanes", disabled_lanes)
        # ``select_next`` became plan-aware (O5 Task 4): a bound plan scopes
        # selection to its own member packets, so re-deriving "what would
        # have been chosen" must resolve the SAME plan the real coordinator
        # would have seen at this point -- the plan bound to this event's
        # own run_id, as of the journal prefix strictly before this event.
        # Reuses ``recovery.bound_execution_plan_for_run`` (never
        # reimplemented) against the REAL ``state_root`` -- unlike the
        # packet/counters fold above, plan authentication reads an immutable
        # artifact from disk that only the real state root has (see the
        # ``_prefix_fold_root`` comment above), and an ungoverned/pre-O5 run
        # with no bound plan correctly resolves to ``None`` here, preserving
        # ``select_next``'s exact prior (unscoped) behavior for it.
        plan = bound_execution_plan_for_run(state_root, journal_events[:i], event.get("run_id"))
        expected = select_next(prior_packets, disabled, event.get("event_at"), plan)
        actual = event.get("packet_id")
        if expected != actual:
            divergences.append({
                "seq": event.get("seq"),
                "code": "SCHEDULING_DIVERGENCE",
                "message": f"select_next over the prior-event fold chose {expected!r}, journal recorded {actual!r}",
            })

    # A full fold of the entire journal is itself a transition-legality
    # replay -- _fold_journal already validates every (from_state,to_state)
    # against CAUSE_EDGES and validate_transition, raising on any illegal
    # edge, so a clean fold over the whole journal IS the transition-replay
    # proof; no parallel check is written here.
    try:
        final_packets, final_counters = _fold_journal(state_root, journal_events)
        fold_ok = True
    except IntegrityError as exc:
        final_packets, final_counters = {}, {}
        fold_ok = False
        divergences.append({"seq": None, "code": "FOLD_FAILED", "message": exc.message})

    return {
        "journal_chain_valid": torn_tail is None,
        "journal_head": {
            "seq": journal_events[-1]["seq"] if journal_events else 0,
            "event_sha256": journal_events[-1]["event_sha256"] if journal_events else None,
        },
        "events_replayed": len(journal_events),
        "attempt_started_events_checked": len([e for e in journal_events if e.get("event_type") == "ATTEMPT_STARTED"]),
        "fold_ok": fold_ok,
        "divergences": divergences,
        "replay_passed": (torn_tail is None) and fold_ok and not divergences,
    }
