"""Drive the existing one-step coordinator through a simulated night.

This is a loop over ``run_once``, not a second coordinator. Queue, journal,
crash recovery, quarantine, one-time fallback, budgets, and graceful stop
stay exactly as commissioned. The driver:

- keeps calling ``run_once`` until morning, an operator stop, a drained
  queue, a completed plan, or a provider outage that would otherwise spin;
- requests a graceful stop through the existing journal helpers, then lets
  ``run_once`` finish the open attempt and make the stop effective;
- never tight-loops at the same instant against a pause, backoff, or empty
  selection;
- emits one morning report assembled from the already-commissioned
  reconciliation report plus a short loop summary.

Real-provider invocation is out of scope. Callers supply the same synthetic
``worker_adapters`` the O3/O5 path already uses.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Callable, Dict, List, Mapping, Optional

from harness_coordinator.v1.coordinator import run_once
from harness_coordinator.v1.reconcile import build_reconciliation_report
from harness_coordinator.v1.recovery import (
    IntegrityError,
    request_graceful_stop,
)
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import read_journal

# Existing graceful-stop vocabulary. Do not invent a new reason code.
_STOP_REASON_MORNING = "QUEUE_SAFETY_CEILING_REACHED"
_STOP_REASON_PROVIDER = "PROVIDER_ALLOWANCE_UNAVAILABLE"

_TERMINAL_STATUSES = frozenset({
    "graceful_stopped",
    "plan_complete",
})

_NO_PROGRESS_STATUSES = frozenset({
    "no_eligible_work",
    "no_capable_model",
    "awaiting_provider_reset",
    "awaiting_worker_adapter",
    "plan_stopped",
})

_PROVIDER_BLOCKED_STATUSES = frozenset({
    "no_capable_model",
    "awaiting_provider_reset",
})

_DEFAULT_MAX_ITERATIONS = 64

_RFC3339 = "%Y-%m-%dT%H:%M:%SZ"


def _parse_utc(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, _RFC3339)


def _format_utc(value: datetime.datetime) -> str:
    return value.strftime(_RFC3339)


def _advance(now: str, tick_seconds: int) -> str:
    return _format_utc(_parse_utc(now) + datetime.timedelta(seconds=tick_seconds))


def _read_state_root_id(state_root: str) -> str:
    path = os.path.join(state_root, "MANIFEST.json")
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    state_root_id = manifest.get("state_root_id")
    if not isinstance(state_root_id, str) or not state_root_id:
        raise ValueError("MANIFEST.json is missing state_root_id")
    return state_root_id


def _request_stop(
    state_root: str,
    state_root_id: str,
    plan: Dict[str, Any],
    coordinator_id: str,
    run_id: str,
    now: str,
    reason_code: str,
) -> None:
    """Record a graceful stop through the commissioned helper. Idempotent."""
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    with open_state_root(state_root) as handle:
        events, torn = read_journal(journal_path, state_root_id=state_root_id)
        if torn is not None:
            raise IntegrityError(
                "JOURNAL_TORN",
                "refusing to request a stop against a torn journal",
            )
        try:
            request_graceful_stop(
                journal_path, lock_path, events, plan,
                coordinator_id, run_id, state_root_id, now,
                reason_code, [], handle=handle,
            )
        except IntegrityError as exc:
            if getattr(exc, "code", None) == "GRACEFUL_STOP_REQUEST_AFTER_EFFECTIVE":
                return
            raise


def _summarize_iteration(result: Dict[str, Any], now: str) -> Dict[str, Any]:
    summary = {
        "now": now,
        "status": result.get("status"),
        "packet_id": result.get("packet_id"),
    }
    if result.get("stop_reason_code"):
        summary["stop_reason_code"] = result["stop_reason_code"]
    return summary


def _morning_report(
    state_root: str,
    state_root_id: str,
    coordinator_id: str,
    run_id: str,
    now: str,
    end_reason: str,
    iterations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """One report: what happened, what changed, what passed, what needs attention."""
    report_id = "morning-%s" % run_id
    reconciliation = build_reconciliation_report(
        state_root, state_root_id, coordinator_id, run_id, report_id, now,
    )
    packets = reconciliation.get("packets") or []
    by_state = reconciliation.get("by_state") or {}
    attention = list(reconciliation.get("attention_required") or [])
    plan_totals = reconciliation.get("plan_totals") or {}
    attempted = list(reconciliation.get("attempted_packet_ids") or [])
    passed = bool(
        (reconciliation.get("reconciliation") or {}).get("all_invariants_passed")
        if isinstance(reconciliation.get("reconciliation"), dict)
        else reconciliation.get("all_invariants_passed")
    )
    return {
        "generated_at": now,
        "end_reason": end_reason,
        "iterations": len(iterations),
        "what_happened": {
            "end_reason": end_reason,
            "iteration_count": len(iterations),
            "iteration_statuses": [item["status"] for item in iterations],
        },
        "what_changed": {
            "attempted_packet_ids": attempted,
            "by_state": by_state,
        },
        "what_passed": {
            "all_invariants_passed": passed,
            "plan_totals": plan_totals,
        },
        "what_needs_attention": attention,
        "packets": [
            {
                "packet_id": row.get("packet_id"),
                "state": row.get("state"),
                "disposition": row.get("disposition"),
            }
            for row in packets
        ],
        "reconciliation_report_id": reconciliation.get("report_id"),
        "reconciliation_sha256": reconciliation.get("report_sha256"),
        "all_invariants_passed": passed,
    }


def run_night(
    state_root: str,
    coordinator_id: str,
    run_id: str,
    trusted_process_context: Dict[str, Any],
    now: str,
    execution_plan: Dict[str, Any],
    worker_adapters: Optional[Mapping[str, Any]] = None,
    provider_state: Optional[Mapping[str, Any]] = None,
    disabled_lanes: Optional[List[str]] = None,
    morning_at: Optional[str] = None,
    stop_check: Optional[Callable[[], bool]] = None,
    tick_seconds: int = 0,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
) -> Dict[str, Any]:
    """Repeat ``run_once`` until the night ends. Restart-safe.

    ``morning_at`` is an inclusive RFC3339 UTC instant. ``stop_check`` is an
    operator signal; when it returns True the existing graceful-stop path
    fires. ``tick_seconds`` advances the explicit ``now`` between iterations
    so a simulated night does not wall-sleep. ``max_iterations`` is a
    fail-closed spin guard, not a budget.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    if tick_seconds < 0:
        raise ValueError("tick_seconds cannot be negative")

    state_root_id = _read_state_root_id(state_root)
    iterations: List[Dict[str, Any]] = []
    last_fingerprint = None
    stop_requested = False
    end_reason = "max_iterations"
    status = "iteration_cap"

    for _index in range(max_iterations):
        if morning_at is not None and now >= morning_at and not stop_requested:
            _request_stop(
                state_root, state_root_id, execution_plan,
                coordinator_id, run_id, now, _STOP_REASON_MORNING,
            )
            stop_requested = True

        if stop_check is not None and stop_check() and not stop_requested:
            _request_stop(
                state_root, state_root_id, execution_plan,
                coordinator_id, run_id, now, _STOP_REASON_MORNING,
            )
            stop_requested = True

        result = run_once(
            state_root, coordinator_id, run_id, trusted_process_context, now,
            disabled_lanes=disabled_lanes,
            worker_adapters=worker_adapters,
            execution_plan=execution_plan,
            provider_state=provider_state,
        )
        iterations.append(_summarize_iteration(result, now))
        result_status = result.get("status")
        fingerprint = (result_status, result.get("packet_id"), now)

        if result_status in _TERMINAL_STATUSES:
            end_reason = (
                "plan_complete" if result_status == "plan_complete"
                else (result.get("stop_reason_code") or "graceful_stopped")
            )
            status = result_status
            break

        if result_status in _PROVIDER_BLOCKED_STATUSES:
            if not stop_requested:
                _request_stop(
                    state_root, state_root_id, execution_plan,
                    coordinator_id, run_id, now, _STOP_REASON_PROVIDER,
                )
                stop_requested = True
                continue
            end_reason = result.get("stop_reason_code") or "provider_unavailable"
            status = "provider_unavailable"
            break

        if result_status == "no_eligible_work":
            end_reason = "queue_drained"
            status = "queue_drained"
            break

        if fingerprint == last_fingerprint and result_status in _NO_PROGRESS_STATUSES:
            end_reason = "no_progress"
            status = "no_progress"
            break

        last_fingerprint = fingerprint

        if tick_seconds:
            now = _advance(now, tick_seconds)
    else:
        end_reason = "max_iterations"
        status = "iteration_cap"

    morning_report = _morning_report(
        state_root, state_root_id, coordinator_id, run_id, now,
        end_reason, iterations,
    )
    return {
        "status": status,
        "end_reason": end_reason,
        "now": now,
        "iterations": iterations,
        "iteration_count": len(iterations),
        "morning_report": morning_report,
    }


_ATTENTION_WORTHY_DISPOSITIONS = {
    "quarantined": "packet_quarantined",
    "blocked_human": "packet_blocked_human",
}


def combine_morning_reports(reports: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Merge N independent lanes' own ``run_night()`` results into one
    morning report. Pure: no state-root I/O, no side effects -- every input
    is already-produced, in-memory lane output (each lane's own ``run_night``
    return dict). This is the seam that lets Alex read one report instead of
    opening N state roots by hand when ingestion and app-build lanes run
    concurrently (PLAN.md's two-lane overnight design, Invariant 15).

    ``reports`` maps an arbitrary caller-chosen lane name to that lane's own
    ``run_night()`` return dict (each of which nests its own
    ``morning_report``). The combined result has three parts:

    - ``lanes``: the per-lane breakdown, each sub-report kept verbatim and
      keyed by lane name -- nothing here is summarized or dropped, so a
      reader can always drill into one lane's own full detail.
    - ``what_needs_attention``: the union of two things, each item tagged
      with its source ``lane`` so it is traceable back to which lane
      produced it:
        1. every item each lane's own reconciliation already flagged
           (``morning_report.what_needs_attention`` -- genuine integrity
           findings, carried through unchanged);
        2. one synthesized item per packet whose disposition is
           ``quarantined`` or ``blocked_human``. These are correct,
           EXPECTED dispositions, not integrity violations -- reconcile.py's
           own ``attention_required`` deliberately does not flag a packet
           for reaching one of them (see ``_o5_disposition``'s docstring:
           they are self-explanatory terminal/paused outcomes) -- so
           without this they would be invisible in a morning report even
           though O6's own exit criterion is that Alex can tell "what needs
           attention" from one report. A quarantined packet or one blocked
           on human authority is exactly the kind of thing a human should
           see without opening that packet's own state root by hand.
    - ``all_invariants_passed``: the logical AND of every lane's own
      ``morning_report.all_invariants_passed`` -- true only when every lane
      independently reports a clean night.
    """
    if not isinstance(reports, Mapping) or not reports:
        raise ValueError("combine_morning_reports requires at least one lane report")

    lanes: Dict[str, Any] = {}
    what_needs_attention: List[Dict[str, Any]] = []
    all_passed = True

    for lane_name in sorted(reports):
        if not isinstance(lane_name, str) or not lane_name:
            raise ValueError("lane names must be non-empty strings")
        lane_report = reports[lane_name]
        if not isinstance(lane_report, Mapping) or "morning_report" not in lane_report:
            raise ValueError("lane %r report is missing morning_report" % (lane_name,))
        morning = lane_report["morning_report"]
        if not isinstance(morning, Mapping):
            raise ValueError("lane %r morning_report is not a mapping" % (lane_name,))
        lanes[lane_name] = lane_report

        for item in morning.get("what_needs_attention") or []:
            tagged = dict(item) if isinstance(item, Mapping) else {"detail": item}
            tagged["lane"] = lane_name
            what_needs_attention.append(tagged)

        for row in morning.get("packets") or []:
            disposition = row.get("disposition") if isinstance(row, Mapping) else None
            code = _ATTENTION_WORTHY_DISPOSITIONS.get(disposition)
            if code is None:
                continue
            what_needs_attention.append({
                "packet_id": row.get("packet_id"),
                "code": code,
                "detail": "%s reached disposition %r" % (row.get("packet_id"), disposition),
                "lane": lane_name,
            })

        all_passed = all_passed and bool(morning.get("all_invariants_passed"))

    return {
        "lanes": lanes,
        "what_needs_attention": what_needs_attention,
        "all_invariants_passed": all_passed,
    }


__all__ = ["run_night", "combine_morning_reports"]
