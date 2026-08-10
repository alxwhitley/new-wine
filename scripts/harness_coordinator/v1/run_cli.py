"""Explicit write-capable CLI for one bounded coordinator iteration."""

import argparse
import json
import os
import socket
import subprocess
import sys
from typing import List, Optional

from harness_coordinator.v1.coordinator import run_once


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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="harness-coordinator-run")
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--coordinator-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--now", required=True)
    args = parser.parse_args(argv)
    context = derive_local_process_context(args.coordinator_id, args.now)
    result = run_once(args.state_root, args.coordinator_id, args.run_id, context, args.now)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
