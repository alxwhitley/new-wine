"""Explicit write-capable CLI for one bounded coordinator iteration."""

import argparse
import json
import os
import socket
import subprocess
import sys
from typing import Any, Dict, List, Optional

from harness_contracts.v1.execution_plan import (
    ExecutionPlanContractError,
    authenticate_execution_plan_bytes,
)
from harness_coordinator.v1.coordinator import run_once
from harness_coordinator.v1.cli import _NEEDS_HUMAN_ATTENTION_CODES
from harness_coordinator.v1.night_loop import run_night


def derive_local_process_context(coordinator_id: str, now: str):
    """Derive process identity locally; no identity claim is trusted from argv."""
    boot_id = None
    proc_boot = "/proc/sys/kernel/random/boot_id"
    if os.path.exists(proc_boot):
        with open(proc_boot, "r", encoding="utf-8") as source:
            boot_id = source.read().strip()
    if not boot_id:
        boot_id = subprocess.run(["sysctl", "-n", "kern.boottime"], check=True,
                                 capture_output=True, text=True, timeout=5).stdout.strip()
    if not boot_id:
        raise RuntimeError("local boot identity unavailable")
    return {"coordinator_id": coordinator_id, "hostname": socket.gethostname(), "boot_id": boot_id,
            "pid": os.getpid(), "live_coordinator_ids": {coordinator_id}, "now": now}


def _load_execution_plan(path: str) -> Dict[str, Any]:
    """Read and authenticate one canonical execution-plan artifact from disk.

    Reuses ``harness_contracts.v1.execution_plan.authenticate_execution_plan_bytes``
    -- the exact canonical-bytes/hash-checking path Task 1 already built for
    ``bind_execution_plan`` -- rather than hand-rolling a second JSON-loading/
    validation routine here. A missing file, an unreadable file, non-canonical
    bytes, or a plan that fails ``validate_execution_plan`` all surface as the
    same ``ExecutionPlanContractError`` shape this CLI already knows how to
    render as its one machine-readable error payload (``_emit_error`` below).
    An unreadable/missing path is folded into the same ``PLAN_IDENTITY_INVALID``
    code ``authenticate_execution_plan_bytes`` already uses for "the caller
    did not hand me valid plan bytes" (e.g. non-bytes input) -- no new error
    vocabulary is introduced for this CLI-specific case.
    """
    try:
        with open(path, "rb") as source:
            raw = source.read()
    except OSError as exc:
        raise ExecutionPlanContractError(
            "PLAN_IDENTITY_INVALID",
            "execution plan file cannot be read: %s" % exc,
        ) from exc
    return authenticate_execution_plan_bytes(raw)


def _emit_error(exc: Exception) -> int:
    print(json.dumps({"error": True, "code": getattr(exc, "code", type(exc).__name__),
                      "message": getattr(exc, "message", str(exc))}, sort_keys=True))
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="harness-coordinator-run")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true",
                      help="One bounded iteration (the commissioned runner).")
    mode.add_argument("--until-morning", action="store_true",
                      help="Repeat the one-step runner until morning or a stop file.")
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--coordinator-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--morning-at",
                        help="RFC3339 UTC instant that ends an --until-morning run.")
    parser.add_argument("--stop-file",
                        help="If this path exists, request a graceful stop.")
    parser.add_argument(
        "--execution-plan-path", required=True,
        help=("Path to an authenticated, canonical execution-plan artifact. "
              "Required, no default: a governed run must never silently "
              "proceed with no plan-derived limits, no wall-clock backstop, "
              "and no pre-claim budget/routing/human-authority gate."))
    args = parser.parse_args(argv)

    # Fail closed on the plan BEFORE deriving process identity or touching
    # the state root at all -- a missing file, an unreadable file,
    # non-canonical bytes, or a validate_execution_plan failure means no
    # coordinator claim, no attempt, nothing durable written.
    try:
        execution_plan = _load_execution_plan(args.execution_plan_path)
    except Exception as exc:  # noqa: BLE001 - one machine-readable result, same posture as below
        return _emit_error(exc)

    context = derive_local_process_context(args.coordinator_id, args.now)
    try:
        if args.until_morning:
            if not args.morning_at:
                raise ValueError("--until-morning requires --morning-at")
            stop_path = args.stop_file
            result = run_night(
                args.state_root, args.coordinator_id, args.run_id, context,
                args.now, execution_plan,
                morning_at=args.morning_at,
                stop_check=(lambda: os.path.exists(stop_path)) if stop_path else None,
            )
        else:
            result = run_once(args.state_root, args.coordinator_id, args.run_id, context, args.now,
                              execution_plan=execution_plan)
    except Exception as exc:  # noqa: BLE001 - write CLI still emits one machine-readable result
        return _emit_error(exc)
    print(json.dumps(result, sort_keys=True))
    if args.until_morning:
        report = result.get("morning_report") or {}
        return 0 if report.get("all_invariants_passed") else 1
    reconciliation = result.get("reconciliation") or {}
    # Compatibility for injected/unit callers that predate P5D. A real
    # RecoveryReport always produces reconciliation before returning.
    if not reconciliation:
        return 1 if os.path.exists(os.path.join(args.state_root, "MANIFEST.json")) else 0
    if not reconciliation.get("all_invariants_passed", False):
        return 1
    if set(reconciliation.get("attention_codes") or []) & _NEEDS_HUMAN_ATTENTION_CODES:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
