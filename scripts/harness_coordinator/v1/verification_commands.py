"""Execute a single packet-declared verification command as a real subprocess.

Closes a gap found in a prior daytime harness probe: nothing in this
codebase actually launched one ``verification_commands[]`` entry
(``schemas/harness/v1/packet.schema.json``) as a real child process with
its own declared ``timeout_seconds`` applied up front, before this module.
This is additive only -- no existing schema, validator, or coordinator file
changes; it fills a missing execution step, it does not redesign one.

``run_verification_command`` fails closed on a malformed input command
(missing/wrong-typed ``command_id``/``argv``/``cwd``/``timeout_seconds``/
``expected_exit_code``, or a non-positive ``timeout_seconds``) via
``ValueError`` raised before any process is spawned -- there is no code
path here that runs a command without a validly declared positive timeout.

Process-group containment on timeout reuses
``harness_coordinator.v1.process_sidecar.terminate_process_group`` (SIGTERM
then SIGKILL, returns only after group death) rather than reimplementing
process-group termination -- the same function the sidecar/invoke path
already relies on for the same guarantee. Hashing reuses
``harness_contracts.v1.canonical.compute_sha256``.

Output-hashing convention (stated explicitly, since the schema permits
either): on a command that actually ran to completion, ``stdout_sha256``/
``stderr_sha256`` are always the SHA-256 of the captured bytes, including
the empty-bytes digest when a stream produced no output -- this matches
the existing precedent at ``invoke.py``'s completion-receipt construction,
which hashes ``stdout_raw``/``stderr_raw`` unconditionally rather than
substituting ``null`` for empty output; ``null`` there is reserved for data
that was never captured at all (its ``result`` field), not for data that
was captured and happened to be empty. A ``TIMED_OUT`` command's output is
deliberately NOT captured after the kill (no post-mortem partial read of
the pipes -- correctness over completeness for a killed process), so its
``stdout_sha256``/``stderr_sha256`` are ``null``, matching that same
never-captured semantics.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Mapping, Optional

from harness_contracts.v1.canonical import compute_sha256
from harness_coordinator.v1.process_sidecar import terminate_process_group


_COMMAND_RESULT_FIELDS = frozenset({
    "command_id", "argv", "cwd", "timestamps", "exit_code", "outcome",
    "stdout_sha256", "stderr_sha256",
})

# Grace window between SIGTERM and SIGKILL when a timed-out command's
# process group must be torn down. Small and fixed on purpose -- this is
# cleanup after a declared timeout has already fired, not a second timeout
# a caller can tune per command.
_TERMINATE_GRACE_SECONDS = 5.0

# Bound on the post-kill reap/drain call so a confirmed-dead process group
# can never turn this function itself into an unbounded wait.
_REAP_TIMEOUT_SECONDS = 5.0


def _now() -> str:
    """RFC3339 UTC timestamp, matching this codebase's existing convention
    (see ``harness_coordinator.v1.cli._now`` / ``night_loop._RFC3339``)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_non_empty_string(command: Mapping[str, Any], field: str) -> str:
    if field not in command:
        raise ValueError("verification command missing required field '%s'" % field)
    value = command[field]
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError("verification command field '%s' must be a non-empty string" % field)
    return value


def _validate_command(command: Mapping[str, Any]) -> None:
    """Fail closed on any malformed input. Raises ValueError, never returns
    a partial or best-effort result for a bad command shape."""
    if not isinstance(command, Mapping):
        raise ValueError("verification command must be a mapping")

    for field in ("command_id", "argv", "cwd", "timeout_seconds", "expected_exit_code"):
        if field not in command:
            raise ValueError("verification command missing required field '%s'" % field)

    _require_non_empty_string(command, "command_id")
    _require_non_empty_string(command, "cwd")

    argv = command["argv"]
    if not isinstance(argv, list) or len(argv) == 0 or not all(isinstance(a, str) for a in argv):
        raise ValueError("verification command field 'argv' must be a non-empty list of strings")

    timeout_seconds = command["timeout_seconds"]
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise ValueError("verification command field 'timeout_seconds' must be a positive integer")

    expected_exit_code = command["expected_exit_code"]
    if isinstance(expected_exit_code, bool) or not isinstance(expected_exit_code, int):
        raise ValueError("verification command field 'expected_exit_code' must be an integer")


def run_verification_command(command: Mapping[str, Any], *, repo_root: str) -> Dict[str, Any]:
    """Run one packet-side ``verification_commands[]`` entry for real.

    Returns a dict shaped exactly like a ``worker-result.schema.json``
    ``commands[]`` item: ``command_id``, ``argv``, ``cwd``,
    ``timestamps.{started_at,finished_at}``, ``exit_code``, ``outcome``,
    ``stdout_sha256``, ``stderr_sha256`` -- no extra keys, no missing keys.

    Raises ``ValueError`` only for a malformed input ``command`` (checked
    before anything is spawned). A normal command timeout is not an
    exception here -- it is reported as ``outcome == "TIMED_OUT"`` in the
    returned dict, same as ``PASSED``/``FAILED``.
    """
    _validate_command(command)

    command_id = command["command_id"]
    argv: List[str] = list(command["argv"])
    cwd = command["cwd"]
    timeout_seconds = command["timeout_seconds"]
    expected_exit_code = command["expected_exit_code"]

    cwd_abs = os.path.join(repo_root, cwd)

    started_at = _now()
    process = subprocess.Popen(
        argv,
        cwd=cwd_abs,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        # start_new_session=True makes the child its own process-group
        # leader, so its pgid equals its own pid -- terminate_process_group
        # is reused directly, not reimplemented.
        terminate_process_group(process.pid, grace_seconds=_TERMINATE_GRACE_SECONDS)
        # The group is confirmed dead, but this process (the parent) still
        # needs to reap it and release the pipe handles. Bounded, and
        # expected to return immediately since the child is already gone.
        # Whatever bytes surface here are deliberately discarded -- see the
        # module docstring's output-hashing convention.
        try:
            process.communicate(timeout=_REAP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        finished_at = _now()
        return {
            "command_id": command_id,
            "argv": argv,
            "cwd": cwd,
            "timestamps": {"started_at": started_at, "finished_at": finished_at},
            "exit_code": None,
            "outcome": "TIMED_OUT",
            "stdout_sha256": None,
            "stderr_sha256": None,
        }

    finished_at = _now()
    outcome = "PASSED" if process.returncode == expected_exit_code else "FAILED"
    return {
        "command_id": command_id,
        "argv": argv,
        "cwd": cwd,
        "timestamps": {"started_at": started_at, "finished_at": finished_at},
        "exit_code": process.returncode,
        "outcome": outcome,
        "stdout_sha256": compute_sha256(stdout_bytes),
        "stderr_sha256": compute_sha256(stderr_bytes),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m harness_coordinator.v1.verification_commands",
        description=(
            "Run one packet-declared verification command as a real "
            "subprocess with its declared timeout applied up front, and "
            "print the worker-result.schema.json commands[] item shape "
            "as JSON."
        ),
    )
    parser.add_argument("--command-id", required=True)
    parser.add_argument("--timeout-seconds", required=True, type=int)
    parser.add_argument("--expected-exit-code", required=True, type=int)
    parser.add_argument("--cwd", required=True)
    parser.add_argument(
        "--repo-root", default=None,
        help="Defaults to the current working directory at invocation.",
    )
    # argparse.REMAINDER does not strip a literal leading "--" the way
    # normal positional collection does -- _strip_leading_separator below
    # handles the documented `-- <argv...>` invocation shape.
    parser.add_argument("command_argv", nargs=argparse.REMAINDER)
    return parser


def _strip_leading_separator(argv: List[str]) -> List[str]:
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    command_argv = _strip_leading_separator(args.command_argv)
    if not command_argv:
        parser.error("no command argv supplied after '--'")

    repo_root = args.repo_root if args.repo_root is not None else os.getcwd()

    command = {
        "command_id": args.command_id,
        "argv": command_argv,
        "cwd": args.cwd,
        "timeout_seconds": args.timeout_seconds,
        "expected_exit_code": args.expected_exit_code,
    }

    result = run_verification_command(command, repo_root=repo_root)
    print(json.dumps(result, sort_keys=True))
    # The wrapper process succeeding just means it ran and reported --
    # PASSED/FAILED/TIMED_OUT lives in the printed JSON, matching how
    # worker-result.schema.json already separates "did verification
    # produce a result" from "did the underlying command pass".
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run_verification_command"]
