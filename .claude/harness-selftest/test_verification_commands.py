"""Verification-command execution — real subprocess, real timeout.

Proves ``run_verification_command`` (scripts/harness_coordinator/v1/
verification_commands.py) actually launches a packet-declared
``verification_commands[]`` entry as a real child process, applies its
declared ``timeout_seconds`` up front, and returns a result shaped exactly
like a ``worker-result.schema.json`` ``commands[]`` item — closing the gap
a prior daytime harness probe found: no code path anywhere previously did
this for real.
"""

import calendar
import os
import re
import sys
import time

import pytest

from harness_contracts.v1.worker_result import COMMAND_OUTCOMES
from harness_coordinator.v1 import verification_commands
from harness_coordinator.v1.verification_commands import run_verification_command


_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_EXPECTED_COMMAND_FIELDS = {
    "command_id", "argv", "cwd", "timestamps", "exit_code", "outcome",
    "stdout_sha256", "stderr_sha256",
}


def _parse_rfc3339(value):
    return time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _elapsed_seconds(started_at, finished_at):
    return calendar.timegm(_parse_rfc3339(finished_at)) - calendar.timegm(_parse_rfc3339(started_at))


def _assert_matches_worker_result_commands_item_shape(result):
    """Direct key/type check against worker-result.schema.json's commands[]
    item shape -- proving conformance to the real contract, not an ad hoc
    dict. Reuses COMMAND_OUTCOMES from harness_contracts.v1.worker_result
    rather than redefining the enum."""
    assert set(result.keys()) == _EXPECTED_COMMAND_FIELDS

    assert isinstance(result["command_id"], str) and result["command_id"]
    assert isinstance(result["argv"], list) and result["argv"]
    assert all(isinstance(arg, str) for arg in result["argv"])
    assert isinstance(result["cwd"], str) and result["cwd"]

    timestamps = result["timestamps"]
    assert isinstance(timestamps, dict)
    assert set(timestamps.keys()) == {"started_at", "finished_at"}
    for key in ("started_at", "finished_at"):
        assert _TIMESTAMP_PATTERN.match(timestamps[key]), timestamps[key]

    assert result["exit_code"] is None or (
        isinstance(result["exit_code"], int) and not isinstance(result["exit_code"], bool)
    )

    assert result["outcome"] in COMMAND_OUTCOMES

    for key in ("stdout_sha256", "stderr_sha256"):
        value = result[key]
        assert value is None or (isinstance(value, str) and _SHA256_PATTERN.match(value))


def test_run_verification_command_completes_within_declared_timeout():
    command = {
        "command_id": "quick-sleep",
        "argv": [sys.executable, "-c", "import time; time.sleep(1)"],
        "cwd": ".",
        "timeout_seconds": 10,
        "expected_exit_code": 0,
    }
    result = run_verification_command(command, repo_root=os.getcwd())

    assert result["outcome"] == "PASSED"
    assert result["exit_code"] == 0

    elapsed = _elapsed_seconds(
        result["timestamps"]["started_at"], result["timestamps"]["finished_at"])
    # Proves it returned promptly on completion, not after waiting out some
    # fixed ceiling -- well under the declared 10s timeout.
    assert elapsed < 5

    _assert_matches_worker_result_commands_item_shape(result)


def test_run_verification_command_stops_cleanly_when_it_exceeds_declared_timeout(tmp_path):
    pid_file = tmp_path / "child.pid"
    child_code = (
        "import os, sys, time\n"
        "with open(sys.argv[1], 'w') as fh:\n"
        "    fh.write(str(os.getpid()))\n"
        "time.sleep(10)\n"
    )
    command = {
        "command_id": "slow-sleep",
        "argv": [sys.executable, "-c", child_code, str(pid_file)],
        "cwd": ".",
        "timeout_seconds": 1,
        "expected_exit_code": 0,
    }

    wall_start = time.monotonic()
    result = run_verification_command(command, repo_root=os.getcwd())
    wall_elapsed = time.monotonic() - wall_start

    # Proof it didn't hang or silently background: real wall-clock close to
    # the declared 1s timeout, nowhere near the child's full 10s sleep.
    assert wall_elapsed < 5

    assert result["outcome"] == "TIMED_OUT"
    assert result["exit_code"] is None

    _assert_matches_worker_result_commands_item_shape(result)

    # Proof the spawned process is actually dead (signalled AND reaped) --
    # not just orphaned or left to background silently.
    assert pid_file.exists(), "child never started; timeout assertion is meaningless without this"
    child_pid = int(pid_file.read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


@pytest.mark.parametrize("bad_command", [
    pytest.param(
        {
            "command_id": "missing-timeout",
            "argv": [sys.executable, "-c", "pass"],
            "cwd": ".",
            "expected_exit_code": 0,
        },
        id="missing_timeout_seconds",
    ),
    pytest.param(
        {
            "command_id": "zero-timeout",
            "argv": [sys.executable, "-c", "pass"],
            "cwd": ".",
            "timeout_seconds": 0,
            "expected_exit_code": 0,
        },
        id="zero_timeout_seconds",
    ),
    pytest.param(
        {
            "command_id": "negative-timeout",
            "argv": [sys.executable, "-c", "pass"],
            "cwd": ".",
            "timeout_seconds": -5,
            "expected_exit_code": 0,
        },
        id="negative_timeout_seconds",
    ),
])
def test_run_verification_command_raises_valueerror_without_spawning_when_timeout_is_not_a_positive_int(
        monkeypatch, bad_command):
    def _fail_if_spawned(*args, **kwargs):
        raise AssertionError(
            "subprocess.Popen must never be called for a command with no "
            "validly declared positive timeout")

    monkeypatch.setattr(verification_commands.subprocess, "Popen", _fail_if_spawned)

    with pytest.raises(ValueError):
        run_verification_command(bad_command, repo_root=os.getcwd())
