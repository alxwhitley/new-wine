"""Read-only reconciliation/replay CLI for the harness coordinator v1.

Design's explicit requirement: a repo-local, READ-ONLY CLI with explicit
input paths that never infers production paths, performs writes, or
repairs state automatically. This module therefore calls only
``reconcile.build_reconciliation_report`` (pure, in-memory) and
``replay_schedule.replay_schedule`` (pure, in-memory) -- never
``reconcile.emit_reconciliation_report`` or any ``atomic_replace``/
``append_journal`` call. No production database or network access
anywhere in this module.

This is the one place in the ``reconcile``/``replay_schedule`` call graph
allowed to call ``datetime.now()``/generate an id (D0.4's own carve-out:
"Only the CLI entry point calls datetime/uuid") -- ``build_reconciliation_report``,
``replay_schedule``, and ``emit_reconciliation_report`` all take them as
explicit arguments instead. This is narrower than "the only place in the
O3 coordinator packages": ``recovery._read_or_init_manifest`` also calls
``uuid.uuid4()`` (pre-existing P2 code, for the id of a freshly-initialized
MANIFEST.json -- a real one-time init event, not a report/replay
computation) -- not reopened here, just not mis-scoped by this docstring.
"""

import argparse
import datetime
import json
import sys
import uuid
from typing import Any, Dict, List, Optional

from harness_coordinator.v1.reconcile import build_reconciliation_report
from harness_coordinator.v1.replay_schedule import replay_schedule

# Attention codes that mean "durable state is internally consistent, but
# real progress is blocked and needs a human" -- distinct from
# integrity.all_invariants_passed (I1-I12's internal-consistency meaning,
# an already-ACCEPTED P1 contract this module does not overload). A
# permanently-stuck packet (e.g. promotion_stalled -- see reconcile.py:
# nothing in this build writes a terminal seal, so dependency promotion
# never fires) is a real operational problem an automated morning check
# must not read as healthy just because all_invariants_passed is True.
_NEEDS_HUMAN_ATTENTION_CODES = frozenset({
    "promotion_stalled",
    "attempt_budget_exhausted",
    "dependency_terminal_not_accepted",
})


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _reconcile_exit_code(report: Dict[str, Any]) -> int:
    if not report["reconciliation"]["all_invariants_passed"]:
        return 1
    if any(a.get("code") in _NEEDS_HUMAN_ATTENTION_CODES for a in report.get("attention_required") or []):
        return 1
    return 0


def run_reconcile(state_root: str, state_root_id: str, coordinator_id: str, run_id: str) -> Dict[str, Any]:
    """Build a reconciliation report and return it, exit-code decision
    left to the caller (main()). Pure aside from the id/timestamp it
    generates for this one invocation -- the report itself is a pure
    function of durable state, given those."""
    report_id = f"report-{uuid.uuid4()}"
    return build_reconciliation_report(state_root, state_root_id, coordinator_id, run_id, report_id, _now())


def run_replay(state_root: str, state_root_id: str) -> Dict[str, Any]:
    """Replay scheduling and transition decisions from durable state
    alone (design section 10.2) and return the diff report."""
    return replay_schedule(state_root, state_root_id)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness-coordinator",
        description="Read-only reconciliation/replay CLI. Never writes, never infers a production path.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reconcile_parser = subparsers.add_parser("reconcile", help="Build and print a reconciliation report (read-only).")
    reconcile_parser.add_argument("--state-root", required=True, help="Explicit path to the harness state root.")
    reconcile_parser.add_argument("--state-root-id", required=True, help="Expected state_root_id (from MANIFEST.json).")
    reconcile_parser.add_argument("--coordinator-id", required=True)
    reconcile_parser.add_argument("--run-id", required=True)

    replay_parser = subparsers.add_parser("replay", help="Replay scheduling/transition decisions from durable state (read-only).")
    replay_parser.add_argument("--state-root", required=True, help="Explicit path to the harness state root.")
    replay_parser.add_argument("--state-root-id", required=True, help="Expected state_root_id (from MANIFEST.json).")

    args = parser.parse_args(argv)

    if args.command == "reconcile":
        try:
            report = run_reconcile(args.state_root, args.state_root_id, args.coordinator_id, args.run_id)
        except Exception as exc:  # noqa: BLE001 -- deliberate: see _error_payload's docstring
            print(json.dumps(_error_payload(exc), sort_keys=True, indent=2))
            return 1
        print(json.dumps(report, sort_keys=True, indent=2))
        return _reconcile_exit_code(report)

    if args.command == "replay":
        try:
            result = run_replay(args.state_root, args.state_root_id)
        except Exception as exc:  # noqa: BLE001 -- deliberate: see _error_payload's docstring
            print(json.dumps(_error_payload(exc), sort_keys=True, indent=2))
            return 1
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["replay_passed"] else 1

    parser.error(f"unknown command: {args.command}")
    return 2


def _error_payload(exc: Exception) -> Dict[str, Any]:
    """Turn ANY exception reaching main() into the same machine-readable
    JSON shape the CLI always emits -- a broken state root must be
    reported (design's own "never silently discard corrupt state"
    posture), never surfaced as a raw Python traceback on stdout/stderr.

    Deliberately broad (catches ``Exception``, not just the integrity
    exception types this module knows about): a crash-damaged or
    adversarial state root can fail in ways this code never anticipated
    -- a truncated seal file raising ``json.JSONDecodeError``, a
    directory where a file was expected raising ``IsADirectoryError``,
    an unreadable file raising ``PermissionError`` -- and a read-only
    diagnostic CLI must degrade to a clean error report on all of them,
    not just the ones it happens to have a named except-clause for."""
    code = getattr(exc, "code", None) or type(exc).__name__
    message = getattr(exc, "message", None) or str(exc)
    return {"error": True, "code": code, "message": message}


if __name__ == "__main__":
    sys.exit(main())
