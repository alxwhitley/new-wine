"""O5 invocation safety limits and durable graceful-stop state.

Two boundaries are tested here, and the whole point of the file is that they
stay different things:

* **Immediate** limits terminate the worker's process group, because letting
  it finish would defeat the safety boundary.  They are per-command timeout
  and per-attempt output bytes.  They are never recorded as a graceful plan
  stop -- the graceful reason vocabulary structurally excludes them.
* **Graceful** limits let the active attempt reach a durable outcome, complete
  mandatory O4 postflight, and only then stop, before the next claim.  They
  are the plan's wall-clock backstop and authenticated provider exhaustion.

Every process spawned here is a local synthetic fixture under a disposable
temp dir.  Nothing touches the network, a provider, a database, or the user's
repository.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import validate_journal_event
from harness_coordinator.v1.coordinator import attempt_session_id
from harness_coordinator.v1.invoke import WorkerAdapter, invoke_worker
from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, _make_event
from test_o3_p5_invocation import _packet as _invocation_packet, _worker_result as _invocation_result


PYTHON_EXECUTABLE = os.path.realpath(sys.executable)

SCHEMA_PATH = (
    Path(__file__).parents[2] / "schemas" / "harness" / "v1" / "journal-event.schema.json"
)

COORDINATOR_ID = "coord-o5-stop"
RUN_ID = "run-o5-stop"
STATE_ROOT_ID = "srid-o5-stop"
PLAN_ID = "plan-o5-stop"
PLAN_SHA = "9" * 64

T_RUN_START = "2026-08-11T00:00:00Z"
T_BIND = "2026-08-11T00:05:00Z"
T_EARLY = "2026-08-11T00:30:00Z"
T_NOW = "2026-08-11T01:00:00Z"


# --------------------------------------------------------------------------
# Section 1 -- immediate process-safety limits at the invocation boundary
# --------------------------------------------------------------------------


# A worker that spawns a grandchild, records both pids, then blocks forever.
# Neither descendant calls setsid, so both stay in the worker's process group
# and an honest group termination must reap all three.
SPAWN_GRANDCHILD_THEN_BLOCK = """import os, subprocess, sys, time
grandchild_code = 'import time; time.sleep(600)'
child_code = (
    "import subprocess, sys, time\\n"
    "g = subprocess.Popen([sys.executable, '-c', %r])\\n"
    "sys.stdout.write(str(g.pid) + chr(10))\\n"
    "sys.stdout.flush()\\n"
    "time.sleep(600)\\n"
) % grandchild_code
child = subprocess.Popen([sys.executable, '-c', child_code], stdout=subprocess.PIPE, text=True)
grandchild_pid = child.stdout.readline().strip()
with open(os.environ['SYNTHETIC_MARKER_PATH'], 'w') as handle:
    handle.write('%d\\n%s\\n' % (child.pid, grandchild_pid))
time.sleep(600)
"""

FLOOD_GRANDCHILD_THEN_BLOCK = """import os, subprocess, sys, time
grandchild_code = 'import time; time.sleep(600)'
child_code = (
    "import subprocess, sys, time\\n"
    "g = subprocess.Popen([sys.executable, '-c', %r])\\n"
    "sys.stdout.write(str(g.pid) + chr(10))\\n"
    "sys.stdout.flush()\\n"
    "time.sleep(600)\\n"
) % grandchild_code
child = subprocess.Popen([sys.executable, '-c', child_code], stdout=subprocess.PIPE, text=True)
grandchild_pid = child.stdout.readline().strip()
with open(os.environ['SYNTHETIC_MARKER_PATH'], 'w') as handle:
    handle.write('%d\\n%s\\n' % (child.pid, grandchild_pid))
sys.stderr.write('y' * 100000)
sys.stderr.flush()
time.sleep(600)
"""


def _plan_budgets(command_timeout_seconds=30, output_bytes=1024 * 1024):
    return {
        "attempt_limit": 2,
        "retry_limit": 1,
        "revision_limit": 1,
        "turn_limit": 12,
        "command_timeout_seconds": command_timeout_seconds,
        "output_bytes": output_bytes,
    }


def _invoke_with_plan_limit(tmp_path, code, plan_budgets=None, adapter=None,
                            marker=None, **kwargs):
    """Run one disposable synthetic worker under plan-derived limits."""
    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    if adapter is None:
        env = {"SYNTHETIC_RESULT": json.dumps(
            _invocation_result(packet, session), separators=(",", ":"))}
        if marker is not None:
            env = {"SYNTHETIC_MARKER_PATH": str(marker)}
        adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", code), env=env)
    nonce = uuid.uuid4().hex
    outcome = invoke_worker(
        str(tmp_path / ("state-" + nonce)), STATE_ROOT_ID, packet,
        "attempt-" + nonce, session, adapter,
        allowed_worktree=packet["worktree"]["path"],
        plan_budgets=plan_budgets, **kwargs)
    return outcome


def _pid_is_gone(pid):
    for _ in range(300):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        time.sleep(.01)
    return False


def _assert_group_contained(outcome):
    """Containment held, asked of the GROUP rather than of chosen pids.

    Per-pid polling proves the two descendants this fixture happens to know
    about are gone.  The process group is the honest unit -- anything the
    worker spawned without detaching is in it -- so the public predicate is
    asked directly, and the pgid it is asked about must be a real one.
    """
    from harness_coordinator.v1.process_sidecar import process_group_is_live

    assert outcome.process_group_dead is True
    assert isinstance(outcome.pgid, int) and outcome.pgid > 0, (
        "a spawned invocation must name the process group it contained")
    assert process_group_is_live(outcome.pgid) is False, (
        "worker process group %s survived" % outcome.pgid)


def test_terminate_process_group_recognizes_an_all_zombie_group_as_dead():
    """EPERM against an all-zombie group must read as contained, not lost.

    On macOS, ``os.killpg(pgid, sig)`` raises ``PermissionError`` (EPERM) --
    not ``ProcessLookupError`` (ESRCH) -- when every remaining member of the
    process group is an unreaped zombie.  The group IS dead in that case,
    just not yet reaped, and reporting containment loss for it is wrong.
    This constructs the all-zombie state directly, deterministically, rather
    than racing a flood/timeout fixture to hit it: a forked child gives
    itself a brand-new process group and exits immediately, and is left
    unreaped (by this process, its real parent) until the assertion below is
    done with it, so the zombie window is guaranteed rather than hoped for.
    """
    import harness_coordinator.v1.process_sidecar as process_sidecar

    child_pid = os.fork()
    if child_pid == 0:
        os.setpgid(0, 0)
        os._exit(0)

    try:
        deadline = time.monotonic() + 5.0
        identity = process_sidecar.process_start_identity(child_pid)
        while identity is not None and time.monotonic() < deadline:
            time.sleep(.01)
            identity = process_sidecar.process_start_identity(child_pid)
        assert identity is None, (
            "child never settled into the all-zombie state this test needs")

        # pgid == child_pid: the child made itself its own process-group leader.
        assert process_sidecar.terminate_process_group(child_pid, .05) is True
    finally:
        os.waitpid(child_pid, 0)


def test_terminate_process_group_still_reports_loss_for_a_genuinely_live_group(monkeypatch):
    """EPERM against a real, live group must still be containment loss.

    The fix must not overcorrect: when a signal genuinely cannot reach a
    group that some other, still-live member proves is not a zombie
    remnant, the original conservative behaviour -- report containment loss
    rather than waving it through -- must still hold.
    """
    import harness_coordinator.v1.process_sidecar as process_sidecar

    def refuse_signal(_pgid, _sig):
        raise PermissionError("cannot signal a live group this process does not own")

    monkeypatch.setattr(process_sidecar.os, "killpg", refuse_signal)
    monkeypatch.setattr(process_sidecar, "_group_is_live", lambda _pgid: True)

    assert process_sidecar.terminate_process_group(4242, .0) is False


def test_plan_output_limit_terminates_process_group_and_caps_artifacts(tmp_path):
    outcome = _invoke_with_plan_limit(
        tmp_path,
        "import sys, time; sys.stdout.write('x' * 100000); sys.stdout.flush(); time.sleep(600)",
        plan_budgets=_plan_budgets(command_timeout_seconds=30, output_bytes=1024))

    assert outcome.termination_reason == "OUTPUT_LIMIT_EXCEEDED"
    assert outcome.output_exceeded is True
    assert outcome.process_group_dead is True
    captured = os.path.getsize(outcome.stdout_path) + os.path.getsize(outcome.stderr_path)
    assert captured <= 1024


def test_plan_command_timeout_terminates_process_group(tmp_path):
    outcome = _invoke_with_plan_limit(
        tmp_path, "import time; time.sleep(600)",
        plan_budgets=_plan_budgets(command_timeout_seconds=1),
        terminate_grace_seconds=.1)

    assert outcome.termination_reason == "COMMAND_TIMEOUT"
    assert outcome.timed_out is True
    assert outcome.process_group_dead is True


def test_adapter_cannot_raise_plan_command_timeout(tmp_path):
    """The plan is a ceiling, not a default an adapter may widen."""
    adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c", "import time; time.sleep(600)"), env={},
        requested_timeout_seconds=600.0)

    outcome = _invoke_with_plan_limit(
        tmp_path, None, plan_budgets=_plan_budgets(command_timeout_seconds=1),
        adapter=adapter, timeout_seconds=600.0, terminate_grace_seconds=.1)

    assert outcome.termination_reason == "COMMAND_TIMEOUT"
    assert outcome.process_group_dead is True


def test_adapter_cannot_raise_plan_output_limit(tmp_path):
    adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c",
              "import sys, time; sys.stdout.write('x' * 100000); sys.stdout.flush(); time.sleep(600)"),
        env={}, requested_output_limit_bytes=10 * 1024 * 1024)

    outcome = _invoke_with_plan_limit(
        tmp_path, None,
        plan_budgets=_plan_budgets(command_timeout_seconds=30, output_bytes=1024),
        adapter=adapter, output_limit_bytes=10 * 1024 * 1024)

    assert outcome.termination_reason == "OUTPUT_LIMIT_EXCEEDED"
    assert os.path.getsize(outcome.stdout_path) <= 1024


def test_an_adapter_may_only_lower_a_plan_limit(tmp_path):
    """Lowering is always permitted; only raising is refused."""
    from harness_coordinator.v1.invoke import resolve_invocation_limits

    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={},
                            requested_timeout_seconds=2.0,
                            requested_output_limit_bytes=512)
    timeout, output = resolve_invocation_limits(
        _plan_budgets(command_timeout_seconds=60, output_bytes=4096), adapter, 30.0, 2048)
    assert (timeout, output) == (2.0, 512)


@pytest.mark.parametrize("requested_timeout", [None, 0.5, 5.0, 1e9])
@pytest.mark.parametrize("requested_output", [None, 16, 4096, 10 ** 9])
@pytest.mark.parametrize("caller_timeout", [0.25, 30.0, 1e9])
@pytest.mark.parametrize("caller_output", [64, 1024 * 1024, 10 ** 9])
def test_resolved_limits_never_exceed_the_plan(
        requested_timeout, requested_output, caller_timeout, caller_output):
    """The hard property: no input channel can widen a plan-derived limit."""
    from harness_coordinator.v1.invoke import resolve_invocation_limits

    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={},
                            requested_timeout_seconds=requested_timeout,
                            requested_output_limit_bytes=requested_output)
    budgets = _plan_budgets(command_timeout_seconds=7, output_bytes=333)

    timeout, output = resolve_invocation_limits(
        budgets, adapter, caller_timeout, caller_output)

    assert timeout <= 7
    assert output <= 333


def test_absent_plan_budgets_leave_the_caller_defaults_untouched():
    from harness_coordinator.v1.invoke import resolve_invocation_limits

    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={})
    assert resolve_invocation_limits(None, adapter, 30.0, 4096) == (30.0, 4096)


@pytest.mark.parametrize("budgets", [
    {"command_timeout_seconds": 0, "output_bytes": 10},
    {"command_timeout_seconds": 10, "output_bytes": 0},
    {"command_timeout_seconds": True, "output_bytes": 10},
    {"command_timeout_seconds": 10, "output_bytes": True},
    {"command_timeout_seconds": "10", "output_bytes": 10},
    {"command_timeout_seconds": 10},
    {"output_bytes": 10},
    [],
    "budgets",
])
def test_malformed_plan_budgets_fail_closed(budgets):
    from harness_coordinator.v1.invoke import resolve_invocation_limits

    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={})
    with pytest.raises(ValueError):
        resolve_invocation_limits(budgets, adapter, 30.0, 4096)


@pytest.mark.parametrize("field,value", [
    ("requested_timeout_seconds", 0),
    ("requested_timeout_seconds", -1.0),
    ("requested_timeout_seconds", True),
    ("requested_timeout_seconds", "60"),
    ("requested_output_limit_bytes", 0),
    ("requested_output_limit_bytes", -1),
    ("requested_output_limit_bytes", True),
    ("requested_output_limit_bytes", 1.5),
])
def test_adapter_requested_limits_must_be_sane(field, value):
    with pytest.raises(ValueError, match="requested"):
        WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={}, **{field: value})


def test_command_timeout_kills_child_and_grandchild(tmp_path):
    marker = tmp_path / "descendants.txt"
    outcome = _invoke_with_plan_limit(
        tmp_path, SPAWN_GRANDCHILD_THEN_BLOCK,
        plan_budgets=_plan_budgets(command_timeout_seconds=1),
        marker=marker, terminate_grace_seconds=.1)

    assert outcome.termination_reason == "COMMAND_TIMEOUT"
    child_pid, grandchild_pid = [int(line) for line in
                                 marker.read_text().split()]
    assert _pid_is_gone(child_pid), "worker child survived the timeout"
    assert _pid_is_gone(grandchild_pid), "worker grandchild survived the timeout"
    _assert_group_contained(outcome)


def test_output_flood_kills_child_and_grandchild(tmp_path):
    marker = tmp_path / "descendants.txt"
    outcome = _invoke_with_plan_limit(
        tmp_path, FLOOD_GRANDCHILD_THEN_BLOCK,
        plan_budgets=_plan_budgets(command_timeout_seconds=30, output_bytes=1024),
        marker=marker, terminate_grace_seconds=.1)

    assert outcome.termination_reason == "OUTPUT_LIMIT_EXCEEDED"
    child_pid, grandchild_pid = [int(line) for line in
                                 marker.read_text().split()]
    assert _pid_is_gone(child_pid), "worker child survived the output flood"
    assert _pid_is_gone(grandchild_pid), "worker grandchild survived the output flood"
    _assert_group_contained(outcome)


@pytest.mark.parametrize("bad_pgid", [0, -1, True, "123", None, 1.0])
def test_the_group_predicate_refuses_a_pgid_it_cannot_answer_for(bad_pgid):
    """It must never be askable in a way that quietly returns 'not live'."""
    from harness_coordinator.v1.process_sidecar import process_group_is_live

    with pytest.raises(ValueError, match="process group id"):
        process_group_is_live(bad_pgid)


def test_a_pre_spawn_interruption_names_no_process_group(tmp_path):
    """pgid is None because no group exists, not because one went unrecorded."""
    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    adapter = WorkerAdapter(argv=(PYTHON_EXECUTABLE, "-c", "pass"), env={})

    outcome = invoke_worker(
        str(tmp_path / "state-interrupted"), STATE_ROOT_ID, packet,
        "attempt-interrupted", session, adapter,
        allowed_worktree=packet["worktree"]["path"],
        plan_budgets=_plan_budgets(), stop_requested=lambda: True)

    assert outcome.interrupted is True
    assert outcome.pgid is None
    assert outcome.termination_reason is None


def test_a_reconstructed_outcome_reports_its_pgid_as_unknown(tmp_path):
    """After a restart the recorded group is unknowable, and says so.

    The receipt deliberately carries no pgid: one written before a crash names
    a group this process never observed and whose id the OS may have reused,
    so reconstructing it would offer a containment answer nobody may rely on.
    """
    from harness_coordinator.v1.invoke import load_completed_invocation
    from harness_coordinator.v1.seals_runtime import open_state_root
    from test_o3_p5_invocation import WRITE_RESULT

    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c", WRITE_RESULT),
        env={"SYNTHETIC_RESULT": json.dumps(
            _invocation_result(packet, session), separators=(",", ":"))})
    state_root = str(tmp_path / "state-restart")
    live = invoke_worker(state_root, STATE_ROOT_ID, packet, "attempt-restart",
                         session, adapter,
                         allowed_worktree=packet["worktree"]["path"],
                         plan_budgets=_plan_budgets())
    assert isinstance(live.pgid, int) and live.pgid > 0

    receipt = json.loads(Path(
        state_root, "invocations", "attempt-restart", "completion.json"
    ).read_bytes().decode("utf-8"))
    assert "pgid" not in receipt

    with open_state_root(state_root) as handle:
        reloaded = load_completed_invocation(
            handle, STATE_ROOT_ID, packet, "attempt-restart", session, adapter)
    assert reloaded.pgid is None
    assert reloaded.process_group_dead is True


@pytest.mark.parametrize("field,value", [
    ("requested_timeout_seconds", 5.0),
    ("requested_output_limit_bytes", 4096),
])
def test_adapter_identity_covers_the_requested_limits(field, value):
    """Two adapters differing only in a requested limit are different adapters.

    They resolve to different effective limits, so a completion receipt
    written under one must not reconstruct under the other -- which means the
    limits have to be inside the identity digest, not beside it.
    """
    from harness_coordinator.v1.invoke import _adapter_sha256

    argv = (PYTHON_EXECUTABLE, "-c", "pass")
    plain = WorkerAdapter(argv=argv, env={})
    limited = WorkerAdapter(argv=argv, env={}, **{field: value})

    assert _adapter_sha256(plain) != _adapter_sha256(limited)
    assert _adapter_sha256(limited) == _adapter_sha256(
        WorkerAdapter(argv=argv, env={}, **{field: value}))


def test_adapter_identity_reads_an_int_and_float_timeout_as_one_adapter():
    """The digest tracks the effective bound, not how it was spelled."""
    from harness_coordinator.v1.invoke import _adapter_sha256

    argv = (PYTHON_EXECUTABLE, "-c", "pass")
    assert (_adapter_sha256(WorkerAdapter(argv=argv, env={},
                                          requested_timeout_seconds=2))
            == _adapter_sha256(WorkerAdapter(argv=argv, env={},
                                             requested_timeout_seconds=2.0)))


def test_a_receipt_does_not_reconstruct_under_a_differently_limited_adapter(tmp_path):
    from harness_coordinator.v1.invoke import load_completed_invocation
    from harness_coordinator.v1.seals_runtime import open_state_root
    from test_o3_p5_invocation import WRITE_RESULT

    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    env = {"SYNTHETIC_RESULT": json.dumps(
        _invocation_result(packet, session), separators=(",", ":"))}
    argv = (PYTHON_EXECUTABLE, "-c", WRITE_RESULT)
    written_under = WorkerAdapter(argv=argv, env=env, requested_timeout_seconds=20.0)
    state_root = str(tmp_path / "state-identity")
    invoke_worker(state_root, STATE_ROOT_ID, packet, "attempt-identity", session,
                  written_under, allowed_worktree=packet["worktree"]["path"],
                  plan_budgets=_plan_budgets())

    other = WorkerAdapter(argv=argv, env=env, requested_timeout_seconds=1.0)
    with open_state_root(state_root) as handle:
        with pytest.raises(ValueError):
            load_completed_invocation(
                handle, STATE_ROOT_ID, packet, "attempt-identity", session, other)
        # The adapter it was actually written under still reconstructs.
        assert load_completed_invocation(
            handle, STATE_ROOT_ID, packet, "attempt-identity", session,
            written_under) is not None


def test_a_clean_exit_carries_no_immediate_termination_reason(tmp_path):
    from test_o3_p5_invocation import WRITE_RESULT

    outcome = _invoke_with_plan_limit(
        tmp_path, WRITE_RESULT, plan_budgets=_plan_budgets())
    assert outcome.termination_reason is None
    assert outcome.result is not None


def test_completion_receipt_records_the_reason_and_never_the_output(tmp_path):
    """Bounded metadata is preserved; captured bytes never enter the record."""
    from harness_coordinator.v1.invoke import load_completed_invocation
    from harness_coordinator.v1.seals_runtime import open_state_root

    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c",
              "import sys, time; sys.stdout.write('SECRET' * 20000); sys.stdout.flush(); time.sleep(600)"),
        env={})
    state_root = str(tmp_path / "state-receipt")
    outcome = invoke_worker(
        state_root, STATE_ROOT_ID, packet, "attempt-receipt", session, adapter,
        allowed_worktree=packet["worktree"]["path"],
        plan_budgets=_plan_budgets(command_timeout_seconds=30, output_bytes=1024))
    assert outcome.termination_reason == "OUTPUT_LIMIT_EXCEEDED"

    raw = Path(state_root, "invocations", "attempt-receipt", "completion.json").read_bytes()
    receipt = json.loads(raw.decode("utf-8"))
    assert receipt["termination_reason"] == "OUTPUT_LIMIT_EXCEEDED"
    assert b"SECRET" not in raw
    assert receipt["stdout"]["byte_length"] <= 1024

    with open_state_root(state_root) as handle:
        reloaded = load_completed_invocation(
            handle, STATE_ROOT_ID, packet, "attempt-receipt", session, adapter)
    assert reloaded.termination_reason == "OUTPUT_LIMIT_EXCEEDED"


def test_a_receipt_whose_reason_disagrees_with_its_flags_is_refused(tmp_path):
    """The stored reason and the flags are one fact recorded twice.

    They are produced by one function from one pair of flags, so a receipt
    where they disagree is internally inconsistent and must not reconstruct
    into a usable outcome.
    """
    from harness_contracts.v1.canonical import canonical_bytes as _canonical
    from harness_coordinator.v1.invoke import load_completed_invocation
    from harness_coordinator.v1.seals_runtime import open_state_root
    from test_o3_p5_invocation import WRITE_RESULT

    packet = _invocation_packet(tmp_path)
    session = attempt_session_id(RUN_ID, packet["packet_id"], packet["attempt"])
    adapter = WorkerAdapter(
        argv=(PYTHON_EXECUTABLE, "-c", WRITE_RESULT),
        env={"SYNTHETIC_RESULT": json.dumps(
            _invocation_result(packet, session), separators=(",", ":"))})
    state_root = str(tmp_path / "state-disagree")
    invoke_worker(state_root, STATE_ROOT_ID, packet, "attempt-disagree", session,
                  adapter, allowed_worktree=packet["worktree"]["path"],
                  plan_budgets=_plan_budgets())

    path = Path(state_root, "invocations", "attempt-disagree", "completion.json")
    receipt = json.loads(path.read_bytes().decode("utf-8"))
    assert receipt["termination_reason"] is None
    # Claim an immediate termination the flags do not support, and re-seal the
    # receipt so its self-hash still verifies -- only the agreement check can
    # catch this.
    receipt["termination_reason"] = "COMMAND_TIMEOUT"
    receipt["receipt_sha256"] = compute_sha256(
        _canonical(receipt, omit={"receipt_sha256"}))
    path.write_bytes(_canonical(receipt))

    with open_state_root(state_root) as handle:
        with pytest.raises(ValueError, match="termination reason"):
            load_completed_invocation(
                handle, STATE_ROOT_ID, packet, "attempt-disagree", session, adapter)


# --------------------------------------------------------------------------
# Section 2 -- the immediate/graceful boundary is structural, not a convention
# --------------------------------------------------------------------------


def test_the_disjointness_guard_survives_python_dash_o():
    """A contract guard an interpreter flag can strip is not a guard.

    ``python -O`` removes ``assert``, so the import-time check that this
    boundary's own limits are still in the immediate vocabulary has to raise
    rather than assert.  Run in a subprocess because ``-O`` is a startup flag.
    """
    import subprocess
    import textwrap

    probe = textwrap.dedent(
        """
        import harness_coordinator.v1.invoke as invoke
        import harness_contracts.v1.journal as journal

        journal.IMMEDIATE_STOP_REASON_CODES = {"OUTPUT_LIMIT_EXCEEDED"}
        for name in [n for n in list(__import__("sys").modules)
                     if n.startswith("harness_coordinator.v1.invoke")]:
            del __import__("sys").modules[name]
        try:
            import harness_coordinator.v1.invoke  # noqa: F401
        except RuntimeError:
            print("guarded")
        else:
            print("STRIPPED")
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).parents[2] / "scripts"), str(Path(__file__).parent)])
    completed = subprocess.run(
        [PYTHON_EXECUTABLE, "-O", "-c", probe], env=env, capture_output=True,
        text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "guarded", completed.stdout


def test_immediate_reason_codes_can_never_be_a_graceful_stop_reason():
    from harness_contracts.v1.journal import (
        BUDGET_REASON_CODES, GRACEFUL_STOP_REASON_CODES, IMMEDIATE_STOP_REASON_CODES)

    assert IMMEDIATE_STOP_REASON_CODES == {"COMMAND_TIMEOUT", "OUTPUT_LIMIT_EXCEEDED"}
    assert IMMEDIATE_STOP_REASON_CODES <= BUDGET_REASON_CODES
    assert GRACEFUL_STOP_REASON_CODES <= BUDGET_REASON_CODES
    assert not (IMMEDIATE_STOP_REASON_CODES & GRACEFUL_STOP_REASON_CODES)
    assert "QUEUE_SAFETY_CEILING_REACHED" in GRACEFUL_STOP_REASON_CODES


@pytest.mark.parametrize("event_type", ["GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"])
@pytest.mark.parametrize("immediate", ["COMMAND_TIMEOUT", "OUTPUT_LIMIT_EXCEEDED"])
def test_an_immediate_limit_cannot_be_journaled_as_a_graceful_stop(event_type, immediate):
    """A process-safety failure must never be reinterpreted as a plan stop."""
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    event = _stop_event(event_type)
    event["payload"][key]["reason_code"] = immediate
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))

    result = validate_journal_event(event, None, STATE_ROOT_ID)
    assert result["valid"] is False
    assert any(err["path"] == "/payload/%s/reason_code" % key for err in result["errors"])


def test_graceful_stop_payloads_have_no_channel_for_command_output():
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_SPECS

    for key in ("graceful_stop_request", "graceful_stop_effective"):
        fields = set(BUDGET_PAYLOAD_SPECS[key])
        assert not (fields & {"stdout", "stderr", "output", "detail", "message",
                              "excerpt", "command", "prompt"})


@pytest.mark.parametrize("event_type", ["GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"])
def test_a_graceful_stop_payload_refuses_a_smuggled_output_field(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    event = _stop_event(event_type)
    event["payload"][key]["stdout"] = "x" * 32
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


# --------------------------------------------------------------------------
# Section 3 -- durable graceful-stop event contract
# --------------------------------------------------------------------------


def _request_body(reason_code="QUEUE_SAFETY_CEILING_REACHED"):
    return {
        "plan_id": PLAN_ID,
        "plan_sha256": PLAN_SHA,
        "reason_code": reason_code,
        "evidence_ids": ["evidence-a", "evidence-b"],
    }


def _effective_body(reason_code="QUEUE_SAFETY_CEILING_REACHED"):
    return {
        "plan_id": PLAN_ID,
        "plan_sha256": PLAN_SHA,
        "reason_code": reason_code,
        "requested_event_id": "%s-1" % RUN_ID,
        "evidence_ids": ["evidence-a", "evidence-b"],
    }


STOP_EVENT_BODIES = {
    "GRACEFUL_STOP_REQUESTED": _request_body,
    "GRACEFUL_STOP_EFFECTIVE": _effective_body,
}


def _stop_event(event_type, body=None, seq=1, prev=None, at=T_NOW, packet_id=None,
                run_id=RUN_ID, coordinator_id=COORDINATOR_ID):
    from harness_coordinator.v1.budget_runtime import budget_event_payload

    if body is None:
        body = STOP_EVENT_BODIES[event_type]()
    return _make_event(
        seq, event_type, coordinator_id, run_id, STATE_ROOT_ID, prev, at,
        packet_id=packet_id, payload=budget_event_payload(event_type, body))


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_event_validates(event_type):
    result = validate_journal_event(_stop_event(event_type), None, STATE_ROOT_ID)
    assert result["valid"] is True, result["errors"]


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_payload_is_closed(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]

    extra = _stop_event(event_type)
    extra["payload"][key]["unexpected"] = True
    extra["event_sha256"] = compute_sha256(canonical_bytes(extra, omit={"event_sha256"}))
    assert validate_journal_event(extra, None, STATE_ROOT_ID)["valid"] is False

    missing = _stop_event(event_type)
    del missing["payload"][key][sorted(missing["payload"][key])[0]]
    missing["event_sha256"] = compute_sha256(canonical_bytes(missing, omit={"event_sha256"}))
    assert validate_journal_event(missing, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_body_is_required_for_its_own_type(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    event = _stop_event(event_type)
    event["payload"][key] = None
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_body_cannot_ride_on_an_unrelated_event(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    payload = {
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": None, "report": None,
        key: STOP_EVENT_BODIES[event_type](),
    }
    event = _make_event(1, "RUN_ENDED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
                        None, T_NOW, payload=payload)
    result = validate_journal_event(event, None, STATE_ROOT_ID)
    assert result["valid"] is False
    assert any(err["path"] == "/payload/%s" % key for err in result["errors"])


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_events_are_run_scoped(event_type):
    """A graceful stop is a run decision; it never carries a packet id."""
    event = _stop_event(event_type, packet_id="packet-1")
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_events_never_drive_a_state_transition(event_type):
    event = _stop_event(event_type)
    event["from_state"] = "READY"
    event["to_state"] = "RUNNING"
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


@pytest.mark.parametrize("event_type", sorted(STOP_EVENT_BODIES))
def test_graceful_stop_events_reject_an_unknown_reason_code(event_type):
    from harness_contracts.v1.journal import BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE

    key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
    event = _stop_event(event_type)
    event["payload"][key]["reason_code"] = "MADE_UP_REASON"
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    assert validate_journal_event(event, None, STATE_ROOT_ID)["valid"] is False


def test_runtime_and_json_schema_agree_on_the_graceful_stop_vocabulary():
    from harness_contracts.v1.journal import (
        BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE, BUDGET_PAYLOAD_SPECS,
        GRACEFUL_STOP_EVENT_TYPES, GRACEFUL_STOP_REASON_CODES, JOURNAL_EVENT_TYPES)

    schema = json.loads(SCHEMA_PATH.read_text())
    assert set(schema["properties"]["event_type"]["enum"]) == JOURNAL_EVENT_TYPES
    assert GRACEFUL_STOP_EVENT_TYPES <= JOURNAL_EVENT_TYPES

    payload_properties = schema["properties"]["payload"]["properties"]
    for event_type in GRACEFUL_STOP_EVENT_TYPES:
        key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[event_type]
        declared = payload_properties[key]
        assert declared["additionalProperties"] is False
        assert set(declared["required"]) == set(BUDGET_PAYLOAD_SPECS[key])
        assert set(declared["properties"]) == set(BUDGET_PAYLOAD_SPECS[key])
        assert set(declared["properties"]["reason_code"]["enum"]) == GRACEFUL_STOP_REASON_CODES
        assert key not in schema["properties"]["payload"]["required"]


def test_stop_schema_branches_are_appended_after_the_workspace_baseline_branch():
    """allOf[0] stays the WORKSPACE_BASELINE_RECORDED branch O4 pins by index."""
    from harness_contracts.v1.journal import GRACEFUL_STOP_EVENT_TYPES

    schema = json.loads(SCHEMA_PATH.read_text())
    assert (schema["allOf"][0]["then"]["properties"]["payload"]["properties"]
            ["artifacts"]["items"]["properties"]["kind"]) == {"const": "workspace_baseline"}
    branch_types = [rule["if"]["properties"]["event_type"].get("const")
                    for rule in schema["allOf"]]
    for event_type in GRACEFUL_STOP_EVENT_TYPES:
        assert event_type in branch_types
        assert branch_types.index(event_type) > branch_types.index(
            "WORKSPACE_BASELINE_RECORDED")


def test_phantom_root_folds_tolerate_graceful_stop_events():
    """reconcile's inventory fold and replay's prefix fold have no state root."""
    events = _stop_sequence()
    packets, counters = _fold_journal("/dev/null", events)
    assert packets == {}
    assert counters["attempts_started_total"] == 0
    for index in range(1, len(events) + 1):
        _fold_journal("/dev/null", events[:index])


def test_real_reconcile_and_replay_callers_tolerate_graceful_stop_events(tmp_path):
    """Use the real callers, not a reimplementation of their fold convention.

    reconcile folds against ``/dev/null`` and replay folds every prefix against
    a deliberately absent root; a new event type that either fold cannot
    traverse shows up as ``fold_failed`` / ``FOLD_FAILED_AT_PREFIX`` rather
    than as an exception, which is exactly how it went unnoticed once before.
    """
    from harness_coordinator.v1.reconcile import build_reconciliation_report
    from harness_coordinator.v1.replay_schedule import replay_schedule

    run_started = _run_started_event(seq=1, prev=None)
    request = _stop_event("GRACEFUL_STOP_REQUESTED", seq=2, prev=run_started, at=T_EARLY)
    effective = _stop_event(
        "GRACEFUL_STOP_EFFECTIVE",
        body=dict(_effective_body(), requested_event_id=request["event_id"]),
        seq=3, prev=request, at=T_NOW)
    state_root = _minimal_state_root(tmp_path, [run_started, request, effective])
    report = build_reconciliation_report(
        state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-stop", T_NOW)
    codes = {item["code"] for item in report["attention_required"]}
    assert "fold_failed" not in codes

    divergences = replay_schedule(state_root, STATE_ROOT_ID)["divergences"]
    assert not [item for item in divergences
                if item.get("code") == "FOLD_FAILED_AT_PREFIX"]


# --------------------------------------------------------------------------
# Section 4 -- the fold refuses contradictory or post-stop journals
# --------------------------------------------------------------------------


def _stop_sequence(run_id=RUN_ID):
    request = _stop_event("GRACEFUL_STOP_REQUESTED", seq=1, prev=None, at=T_EARLY,
                          run_id=run_id)
    effective = _stop_event(
        "GRACEFUL_STOP_EFFECTIVE",
        body=dict(_effective_body(), requested_event_id=request["event_id"]),
        seq=2, prev=request, at=T_NOW, run_id=run_id)
    return [request, effective]


def _minimal_state_root(tmp_path, events, name=None):
    """A disposable state root carrying exactly ``events`` and nothing else."""
    from test_o3_p5_review import _write_manifest

    state_root = os.path.realpath(str(tmp_path / (name or "stop-root")))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    with open(os.path.join(state_root, "journal.ndjson"), "wb") as handle:
        for event in events:
            handle.write(canonical_bytes(event) + b"\n")
    return state_root


def test_an_effective_stop_without_a_request_is_an_integrity_error():
    effective = _stop_event("GRACEFUL_STOP_EFFECTIVE", seq=1, prev=None)
    with pytest.raises(IntegrityError, match="GRACEFUL_STOP_EFFECTIVE_WITHOUT_REQUEST"):
        _fold_journal("/dev/null", [effective])


def test_a_duplicate_stop_request_is_an_integrity_error():
    first = _stop_event("GRACEFUL_STOP_REQUESTED", seq=1, prev=None, at=T_EARLY)
    second = _stop_event("GRACEFUL_STOP_REQUESTED", seq=2, prev=first, at=T_NOW)
    with pytest.raises(IntegrityError, match="GRACEFUL_STOP_DUPLICATE_REQUEST"):
        _fold_journal("/dev/null", [first, second])


def test_a_duplicate_effective_stop_is_an_integrity_error():
    request, effective = _stop_sequence()
    again = _stop_event(
        "GRACEFUL_STOP_EFFECTIVE",
        body=dict(_effective_body(), requested_event_id=request["event_id"]),
        seq=3, prev=effective, at=T_NOW)
    with pytest.raises(IntegrityError, match="GRACEFUL_STOP_DUPLICATE_EFFECTIVE"):
        _fold_journal("/dev/null", [request, effective, again])


def test_a_stop_request_after_the_stop_took_effect_is_an_integrity_error():
    request, effective = _stop_sequence()
    late = _stop_event("GRACEFUL_STOP_REQUESTED", seq=3, prev=effective, at=T_NOW)
    with pytest.raises(IntegrityError, match="GRACEFUL_STOP_REQUEST_AFTER_EFFECTIVE"):
        _fold_journal("/dev/null", [request, effective, late])


def test_a_stop_in_one_run_does_not_stop_a_different_run():
    """Stop state is bound to a run identity, never global."""
    request, effective = _stop_sequence(run_id="run-other")
    other = _stop_event("GRACEFUL_STOP_REQUESTED", seq=3, prev=effective, at=T_NOW,
                        run_id=RUN_ID)
    packets, _ = _fold_journal("/dev/null", [request, effective, other])
    assert packets == {}


# --------------------------------------------------------------------------
# Section 5 -- pure stop-state and wall-clock backstop helpers
# --------------------------------------------------------------------------


def test_graceful_stop_state_folds_requested_then_effective():
    from harness_coordinator.v1.recovery import graceful_stop_state

    assert graceful_stop_state([], RUN_ID) == {
        "requested": None, "effective": None, "pending": False,
        "stopped": False, "reason_code": None}

    request, effective = _stop_sequence()
    pending = graceful_stop_state([request], RUN_ID)
    assert pending["pending"] is True and pending["stopped"] is False
    assert pending["reason_code"] == "QUEUE_SAFETY_CEILING_REACHED"

    stopped = graceful_stop_state([request, effective], RUN_ID)
    assert stopped["pending"] is False and stopped["stopped"] is True
    assert stopped["effective"]["payload"]["graceful_stop_effective"][
        "requested_event_id"] == request["event_id"]


def test_graceful_stop_state_ignores_another_runs_stop():
    from harness_coordinator.v1.recovery import graceful_stop_state

    request, effective = _stop_sequence(run_id="run-other")
    state = graceful_stop_state([request, effective], RUN_ID)
    assert state["pending"] is False and state["stopped"] is False


@pytest.mark.parametrize("now,expected", [
    ("2026-08-11T00:59:59Z", False),
    ("2026-08-11T01:00:00Z", True),
    ("2026-08-11T01:00:01Z", True),
])
def test_the_wall_clock_backstop_fires_exactly_at_its_boundary(now, expected):
    from harness_coordinator.v1.recovery import wall_clock_ceiling_reached

    events = [_run_started_event()]
    assert wall_clock_ceiling_reached(events, RUN_ID, 3600, now) is expected


def test_the_wall_clock_backstop_needs_an_authenticated_run_start():
    """No RUN_STARTED for this run means no elapsed time can be claimed."""
    from harness_coordinator.v1.recovery import wall_clock_ceiling_reached

    assert wall_clock_ceiling_reached([], RUN_ID, 1, T_NOW) is False


def test_the_run_start_anchor_is_the_earliest_not_the_first_in_the_list():
    """A safety backstop must not depend on how events were ordered.

    A restart appends a second RUN_STARTED for the same run.  Anchoring on
    whichever one happens to come first in the caller's list would move the
    deadline forward by the gap between them -- here 50 minutes -- so the
    anchor is the earliest by VALUE and reversing the list changes nothing.
    """
    from harness_coordinator.v1.recovery import (
        _run_started_at, wall_clock_ceiling_reached)

    early = _run_started_event(at=T_RUN_START, seq=1)
    late = _run_started_event(at="2026-08-11T00:50:00Z", seq=2, prev=early)
    forward, reversed_order = [early, late], [late, early]

    assert _run_started_at(forward, RUN_ID) == T_RUN_START
    assert _run_started_at(reversed_order, RUN_ID) == T_RUN_START
    # 01:00:00 is exactly one hour after the earliest start and only ten
    # minutes after the later one, so an order-dependent anchor would report
    # the ceiling as not yet reached.
    for events in (forward, reversed_order):
        assert wall_clock_ceiling_reached(events, RUN_ID, 3600, T_NOW) is True


def test_a_run_start_from_another_run_never_anchors_this_one():
    from harness_coordinator.v1.recovery import _run_started_at

    other = _run_started_event(at="2026-08-10T00:00:00Z", run_id="run-other")
    mine = _run_started_event(at=T_RUN_START, seq=2, prev=other)
    assert _run_started_at([other, mine], RUN_ID) == T_RUN_START


@pytest.mark.parametrize("bad_now", [
    "2026-08-10T23:00:00Z", "not-a-time", None, 17, "2026-08-11T01:00:00",
])
def test_clock_regression_against_the_run_start_fails_closed(bad_now):
    """A clock that moved backwards cannot be read as 'time remains'."""
    from harness_coordinator.v1.recovery import wall_clock_ceiling_reached

    with pytest.raises(IntegrityError, match="CLOCK"):
        wall_clock_ceiling_reached([_run_started_event()], RUN_ID, 3600, bad_now)


@pytest.mark.parametrize("ceiling", [0, -1, True, "3600", None])
def test_an_unusable_ceiling_fails_closed(ceiling):
    from harness_coordinator.v1.recovery import wall_clock_ceiling_reached

    with pytest.raises(IntegrityError):
        wall_clock_ceiling_reached([_run_started_event()], RUN_ID, ceiling, T_NOW)


def _run_started_event(at=T_RUN_START, run_id=RUN_ID, seq=1, prev=None):
    """A contract-valid RUN_STARTED, so these fixtures survive ``read_journal``."""
    payload = {
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "report": None,
        "run": {
            "coordinator": {"coordinator_id": COORDINATOR_ID, "boot_id": "boot",
                            "hostname": "host", "pid": 1},
            "trust_roots": {
                "reviewer_sessions_path": "trust/reviewer_sessions.json",
                "reviewer_sessions_sha256": "0" * 64,
                "provider_signals_path": "trust/provider_signals.json",
                "provider_signals_sha256": "0" * 64,
            },
            "contract_versions": {
                "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1,
                "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1,
                "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
            "end_reason": None, "end_detail": None, "disabled_lanes": [],
        },
    }
    return _make_event(seq, "RUN_STARTED", COORDINATOR_ID, run_id, STATE_ROOT_ID,
                       prev, at, payload=payload)


def test_the_stop_fixtures_are_contract_valid_events():
    """Otherwise the fold/replay checks below would be proving nothing."""
    run_started = _run_started_event()
    assert validate_journal_event(run_started, None, STATE_ROOT_ID)["valid"] is True
    request, effective = _stop_sequence()
    assert validate_journal_event(request, None, STATE_ROOT_ID)["valid"] is True
    assert validate_journal_event(effective, request, STATE_ROOT_ID)["valid"] is True


# --------------------------------------------------------------------------
# Section 6 -- exact stop ordering against the real coordinator
# --------------------------------------------------------------------------


def _stop_events(state_root):
    from harness_coordinator.v1.store import read_journal

    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    return [event["event_type"] for event in events
            if event["event_type"].startswith("GRACEFUL_STOP_")]


def _attempt_started_count(state_root, packet_id):
    from harness_coordinator.v1.store import read_journal

    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    return len([event for event in events
                if event["event_type"] == "ATTEMPT_STARTED"
                and event["packet_id"] == packet_id])


def test_a_stop_observed_while_idle_is_requested_then_effective(tmp_path):
    from harness_coordinator.v1.coordinator import run_once

    state = _two_packet_plan_state(tmp_path, "idle")
    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"])

    assert result["status"] == "graceful_stopped"
    assert result["stop_reason_code"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert _stop_events(state["state_root"]) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    for packet_id in state["packet_ids"]:
        assert _attempt_started_count(state["state_root"], packet_id) == 0


def test_queue_ceiling_during_attempt_finishes_then_blocks_next_claim(tmp_path):
    """The open attempt reaches a durable outcome; the next packet is untouched."""
    from harness_coordinator.v1.coordinator import claim_and_start_attempt, run_once
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "during")
    first, second = state["packet_ids"]
    events, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state["state_root"], events)
    claim_and_start_attempt(
        state_root=state["state_root"], state_root_id=STATE_ROOT_ID,
        journal_events=events, packet_id=first, packet=folded[first],
        coordinator_id=COORDINATOR_ID, run_id=RUN_ID,
        trusted_process_context=_context(), now=state["before_ceiling"])

    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"],
                      worker_adapters={"kimi_implementation": state["adapters"][first]})

    assert result["status"] == "graceful_stopped"
    assert _stop_events(state["state_root"]) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]

    final, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                            state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state["state_root"], final)
    assert folded[first]["state"] in {"REVIEW", "ACCEPTED", "QUARANTINED",
                                      "HUMAN_REQUIRED", "REVISE"}
    assert folded[first]["open_attempt"] is None
    assert folded[second]["state"] == "READY"
    assert _attempt_started_count(state["state_root"], second) == 0

    # The stop only becomes effective after the attempt is durably resolved.
    types = [event["event_type"] for event in final]
    assert types.index("GRACEFUL_STOP_REQUESTED") < types.index("ATTEMPT_FINISHED")
    assert types.index("ATTEMPT_FINISHED") < types.index("GRACEFUL_STOP_EFFECTIVE")
    assert types.index("WORKSPACE_POSTFLIGHT_RECORDED") < types.index(
        "GRACEFUL_STOP_EFFECTIVE")


def test_a_restart_after_a_pending_stop_completes_recovery_before_effect(tmp_path):
    """Requested-without-effective is honoured conservatively across a restart."""
    from harness_coordinator.v1.coordinator import claim_and_start_attempt, run_once
    from harness_coordinator.v1.recovery import graceful_stop_state, request_graceful_stop
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "restart")
    first, second = state["packet_ids"]
    state_root = state["state_root"]
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    claim_and_start_attempt(
        state_root=state_root, state_root_id=STATE_ROOT_ID, journal_events=events,
        packet_id=first, packet=folded[first], coordinator_id=COORDINATOR_ID,
        run_id=RUN_ID, trusted_process_context=_context(), now=state["before_ceiling"])

    # Crash boundary: the stop was requested, then the process died before it
    # could take effect and before the open attempt was resolved.
    with open_state_root(state_root) as handle:
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                 state_root_id=STATE_ROOT_ID)
        request_graceful_stop(
            os.path.join(state_root, "journal.ndjson"),
            os.path.join(state_root, "locks", "journal.wlock"), events,
            state["plan"], COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            state["past_ceiling"], "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
    assert _stop_events(state_root) == ["GRACEFUL_STOP_REQUESTED"]

    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"],
                      worker_adapters={"kimi_implementation": state["adapters"][first]})

    assert result["status"] == "graceful_stopped"
    assert _stop_events(state_root) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    final, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                            state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, final)
    assert folded[first]["open_attempt"] is None
    assert folded[second]["state"] == "READY"
    assert _attempt_started_count(state_root, second) == 0
    assert graceful_stop_state(final, RUN_ID)["stopped"] is True


def _open_attempt_then_stop(tmp_path, name):
    """A run with a stop due and one RUNNING packet whose worker never ran."""
    from harness_coordinator.v1.coordinator import claim_and_start_attempt
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, name)
    first = state["packet_ids"][0]
    events, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state["state_root"], events)
    claim_and_start_attempt(
        state_root=state["state_root"], state_root_id=STATE_ROOT_ID,
        journal_events=events, packet_id=first, packet=folded[first],
        coordinator_id=COORDINATOR_ID, run_id=RUN_ID,
        trusted_process_context=_context(), now=state["before_ceiling"])
    return state


def test_an_attempt_whose_worker_never_ran_still_resolves_before_the_stop(tmp_path):
    """Crash-matrix row: stop observed while RUNNING, before any worker exit.

    The attempt is driven to a durable outcome -- here an infra retry, since
    no adapter can produce a result -- and only then does the stop take
    effect.  The next packet is never claimed.
    """
    from harness_coordinator.v1.coordinator import run_once
    from harness_coordinator.v1.store import read_journal

    state = _open_attempt_then_stop(tmp_path, "noadapter")
    first, second = state["packet_ids"]

    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"])

    assert result["status"] == "graceful_stopped"
    assert _stop_events(state["state_root"]) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    final, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                            state_root_id=STATE_ROOT_ID)
    types = [event["event_type"] for event in final]
    assert types.index("GRACEFUL_STOP_REQUESTED") < types.index("ATTEMPT_FINISHED")
    assert types.index("ATTEMPT_FINISHED") < types.index("GRACEFUL_STOP_EFFECTIVE")
    folded, _ = _fold_journal(state["state_root"], final)
    assert folded[first]["open_attempt"] is None
    assert _attempt_started_count(state["state_root"], second) == 0


def _journal_worker_result_without_its_outcome(state, packet_id):
    """Reach the live evidence contradiction that leaves a packet RUNNING.

    ``resolve_open_attempts`` catches a per-packet ``IntegrityError`` on
    purpose, so one packet's contradiction does not abort resolution for the
    others -- and that packet is left RUNNING with its attempt still open.
    Journaling WORKER_RESULT_RECORDED for the open attempt while
    ``attempt_outcome.json`` is absent is exactly that contradiction
    (EVIDENCE_MISSING), and it needs no monkeypatch to produce.
    """
    from harness_coordinator.v1.recovery import _make_event
    from harness_coordinator.v1.store import append_journal, read_journal

    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    started = next(event for event in reversed(events)
                   if event["event_type"] == "ATTEMPT_STARTED"
                   and event["packet_id"] == packet_id)
    previous = events[-1]
    event = _make_event(
        seq=previous["seq"] + 1, event_type="WORKER_RESULT_RECORDED",
        coordinator_id=COORDINATOR_ID, run_id=RUN_ID, state_root_id=STATE_ROOT_ID,
        prev_event=previous, event_at=state["before_ceiling"],
        packet_id=packet_id, intent_id=started["intent_id"],
        payload={"packet": None, "attempt": started["payload"]["attempt"],
                 "artifacts": [], "classification": None,
                 "transition_detail": None, "recovery": None, "run": None,
                 "report": None})
    append_journal(journal_path, event,
                   os.path.join(state_root, "locks", "journal.wlock"),
                   expected_head=previous)
    return event


def test_a_stop_stays_pending_while_an_attempt_is_still_unresolved(tmp_path):
    """The conservative branch: never call a stop effective over an open attempt.

    This is a LIVE path, not a defensive one.  A packet whose evidence
    contradicts itself is deliberately left RUNNING by ``resolve_open_attempts``
    rather than aborting the whole iteration, so the stop genuinely arrives at
    a point where an attempt is still open.  Recording EFFECTIVE anyway would
    assert the active attempt had finished when it had not -- so the stop stays
    pending, and nothing new is claimed while it does.
    """
    from harness_coordinator.v1.coordinator import run_once
    from harness_coordinator.v1.store import read_journal

    state = _open_attempt_then_stop(tmp_path, "unresolved")
    first, second = state["packet_ids"]
    _journal_worker_result_without_its_outcome(state, first)

    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"])

    assert result["status"] == "graceful_stop_pending"
    assert result["stop_reason_code"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert _stop_events(state["state_root"]) == ["GRACEFUL_STOP_REQUESTED"]

    final, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                            state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state["state_root"], final)
    assert folded[first]["state"] == "RUNNING"
    assert folded[first]["open_attempt"] == 1
    assert folded[second]["state"] == "READY"
    assert _attempt_started_count(state["state_root"], second) == 0


def test_attempt_level_attention_survives_into_the_returned_result(tmp_path):
    """The attention that kept the stop pending must reach the caller.

    ``review_attention`` used to be REBOUND by review resolution, silently
    discarding everything ``resolve_open_attempts`` had reported -- so the
    contradiction that left the packet RUNNING, and therefore the stop
    pending, came back to the caller as an empty list.
    """
    from harness_coordinator.v1.coordinator import run_once

    state = _open_attempt_then_stop(tmp_path, "attention")
    first = state["packet_ids"][0]
    _journal_worker_result_without_its_outcome(state, first)

    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"])

    assert result["status"] == "graceful_stop_pending"
    attention = result["review_attention"]
    assert [item for item in attention
            if item.get("packet_id") == first
            and item.get("code") == "EVIDENCE_MISSING"], attention


def test_a_restart_after_an_effective_stop_is_deterministic_and_claims_nothing(tmp_path):
    from harness_coordinator.v1.coordinator import run_once
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "after")
    run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
             state["past_ceiling"], execution_plan=state["plan"])
    first_events, _ = read_journal(
        os.path.join(state["state_root"], "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    first_fold, _ = _fold_journal(state["state_root"], first_events)

    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"], execution_plan=state["plan"])

    assert result["status"] == "graceful_stopped"
    assert _stop_events(state["state_root"]) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    second_events, _ = read_journal(
        os.path.join(state["state_root"], "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    second_fold, _ = _fold_journal(state["state_root"], second_events)
    assert second_fold == first_fold
    for packet_id in state["packet_ids"]:
        assert _attempt_started_count(state["state_root"], packet_id) == 0


def test_a_completed_plan_without_a_stop_still_claims_normally(tmp_path):
    """The backstop must not be mistaken for the definition of success."""
    from harness_coordinator.v1.coordinator import run_once

    state = _two_packet_plan_state(tmp_path, "normal")
    first = state["packet_ids"][0]
    result = run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
                      state["before_ceiling"], execution_plan=state["plan"],
                      worker_adapters={"kimi_implementation": state["adapters"][first]})

    assert result["status"] == "completed_attempt"
    assert _stop_events(state["state_root"]) == []
    assert _attempt_started_count(state["state_root"], first) == 1


@pytest.mark.parametrize("make_effective", [False, True])
def test_a_direct_claim_is_refused_once_a_stop_is_pending_or_effective(
        tmp_path, make_effective):
    """Every pre-claim path checks the stop, not only the iteration loop."""
    from harness_coordinator.v1.coordinator import claim_and_start_attempt
    from harness_coordinator.v1.recovery import (
        make_graceful_stop_effective, request_graceful_stop)
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "guard-%s" % int(make_effective))
    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    with open_state_root(state_root) as handle:
        events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
        events = request_graceful_stop(
            journal_path, lock_path, events, state["plan"],
            COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
            "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
        if make_effective:
            events = make_graceful_stop_effective(
                journal_path, lock_path, events,
                COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
                plan=state["plan"], handle=handle)

    first = state["packet_ids"][0]
    folded, _ = _fold_journal(state_root, events)
    with pytest.raises(IntegrityError, match="GRACEFUL_STOP_IN_EFFECT"):
        claim_and_start_attempt(
            state_root=state_root, state_root_id=STATE_ROOT_ID, journal_events=events,
            packet_id=first, packet=folded[first], coordinator_id=COORDINATOR_ID,
            run_id=RUN_ID, trusted_process_context=_context(),
            now=state["past_ceiling"])
    assert _attempt_started_count(state_root, first) == 0


def test_request_graceful_stop_refuses_an_immediate_reason_code(tmp_path):
    """An immediate safety failure can never be laundered into a plan stop."""
    from harness_coordinator.v1.recovery import request_graceful_stop
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "immediate")
    state_root = state["state_root"]
    with open_state_root(state_root) as handle:
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                 state_root_id=STATE_ROOT_ID)
        with pytest.raises(ValueError, match="COMMAND_TIMEOUT"):
            request_graceful_stop(
                os.path.join(state_root, "journal.ndjson"),
                os.path.join(state_root, "locks", "journal.wlock"), events,
                state["plan"], COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
                state["past_ceiling"], "COMMAND_TIMEOUT", [], handle=handle)
    assert _stop_events(state_root) == []


def test_making_a_stop_effective_requires_a_recorded_request(tmp_path):
    from harness_coordinator.v1.recovery import make_graceful_stop_effective
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "no-request")
    state_root = state["state_root"]
    with open_state_root(state_root) as handle:
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"),
                                 state_root_id=STATE_ROOT_ID)
        with pytest.raises(ValueError, match="request"):
            make_graceful_stop_effective(
                os.path.join(state_root, "journal.ndjson"),
                os.path.join(state_root, "locks", "journal.wlock"), events,
                COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
                state["past_ceiling"], plan=state["plan"], handle=handle)
    assert _stop_events(state_root) == []


def test_an_effective_stop_refuses_a_plan_other_than_the_requests(tmp_path):
    """The pair must name ONE plan; a mismatched argument is refused, not used.

    Reason code and evidence were already copied from the request, but the
    plan identity used to come from the caller's own argument -- so a stop
    requested under one plan could be closed naming another, and the pair read
    back as a perfectly valid journal while defeating requested_event_id
    pairing.  Ambiguity about which plan is being stopped fails closed.
    """
    from harness_coordinator.v1.recovery import (
        make_graceful_stop_effective, request_graceful_stop)
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "conflict")
    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    other_plan = dict(state["plan"], plan_id="plan-totally-different")
    other_plan["plan_sha256"] = compute_sha256(
        canonical_bytes(other_plan, omit={"plan_sha256"}))

    with open_state_root(state_root) as handle:
        events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
        events = request_graceful_stop(
            journal_path, lock_path, events, state["plan"], COORDINATOR_ID,
            RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
            "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_CONFLICT"):
            make_graceful_stop_effective(
                journal_path, lock_path, events, COORDINATOR_ID, RUN_ID,
                STATE_ROOT_ID, state["past_ceiling"], plan=other_plan,
                handle=handle)

    # Refused means nothing was written: the stop is still merely pending.
    assert _stop_events(state_root) == ["GRACEFUL_STOP_REQUESTED"]


def test_the_effective_stop_copies_the_plan_identity_of_its_request(tmp_path):
    from harness_coordinator.v1.recovery import (
        make_graceful_stop_effective, request_graceful_stop)
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "same-plan")
    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    with open_state_root(state_root) as handle:
        events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
        events = request_graceful_stop(
            journal_path, lock_path, events, state["plan"], COORDINATOR_ID,
            RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
            "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
        # No plan argument at all: the binding still comes from the request.
        make_graceful_stop_effective(
            journal_path, lock_path, events, COORDINATOR_ID, RUN_ID,
            STATE_ROOT_ID, state["past_ceiling"], handle=handle)

    final, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    request = next(event for event in final
                   if event["event_type"] == "GRACEFUL_STOP_REQUESTED")
    effective = next(event for event in final
                     if event["event_type"] == "GRACEFUL_STOP_EFFECTIVE")
    requested_body = request["payload"]["graceful_stop_request"]
    effective_body = effective["payload"]["graceful_stop_effective"]
    assert effective_body["plan_id"] == requested_body["plan_id"] == PLAN_ID
    assert effective_body["plan_sha256"] == requested_body["plan_sha256"]
    assert effective_body["requested_event_id"] == request["event_id"]


def test_a_restart_closes_a_pending_stop_without_being_handed_the_plan(tmp_path):
    """Design decision 4's restart claim, in the shipped configuration.

    The plan here is explicit and was never bound into the journal, and the
    restart omits ``execution_plan`` -- so no plan is resolvable at all.  The
    pending stop must still close from the recorded request; a run that can
    never leave ``requested-without-effective`` would hand the supervising
    loop a crash where a stop belongs.
    """
    from harness_coordinator.v1.coordinator import run_once
    from harness_coordinator.v1.recovery import (
        bound_execution_plan_for_run, graceful_stop_state, request_graceful_stop)
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "restart-noplan")
    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    with open_state_root(state_root) as handle:
        events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
        request_graceful_stop(
            journal_path, os.path.join(state_root, "locks", "journal.wlock"),
            events, state["plan"], COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            state["past_ceiling"], "QUEUE_SAFETY_CEILING_REACHED", [],
            handle=handle)
    assert _stop_events(state_root) == ["GRACEFUL_STOP_REQUESTED"]

    # Precondition of the regression: nothing in the journal names a plan.
    events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    assert bound_execution_plan_for_run(state_root, events, RUN_ID) is None

    result = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(),
                      state["past_ceiling"])

    assert result["status"] == "graceful_stopped"
    assert result["stop_reason_code"] == "QUEUE_SAFETY_CEILING_REACHED"
    assert _stop_events(state_root) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]
    final, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
    assert graceful_stop_state(final, RUN_ID)["stopped"] is True
    effective = next(event for event in final
                     if event["event_type"] == "GRACEFUL_STOP_EFFECTIVE")
    assert effective["payload"]["graceful_stop_effective"]["plan_id"] == PLAN_ID
    for packet_id in state["packet_ids"]:
        assert _attempt_started_count(state_root, packet_id) == 0


def test_stop_helpers_are_idempotent_across_a_repeated_call(tmp_path):
    from harness_coordinator.v1.recovery import (
        make_graceful_stop_effective, request_graceful_stop)
    from harness_coordinator.v1.seals_runtime import open_state_root
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "idempotent")
    state_root = state["state_root"]
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    with open_state_root(state_root) as handle:
        events, _ = read_journal(journal_path, state_root_id=STATE_ROOT_ID)
        events = request_graceful_stop(
            journal_path, lock_path, events, state["plan"],
            COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
            "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
        events = request_graceful_stop(
            journal_path, lock_path, events, state["plan"],
            COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, state["past_ceiling"],
            "QUEUE_SAFETY_CEILING_REACHED", [], handle=handle)
        events = make_graceful_stop_effective(
            journal_path, lock_path, events, COORDINATOR_ID, RUN_ID,
            STATE_ROOT_ID, state["past_ceiling"], plan=state["plan"], handle=handle)
        events = make_graceful_stop_effective(
            journal_path, lock_path, events, COORDINATOR_ID, RUN_ID,
            STATE_ROOT_ID, state["past_ceiling"], plan=state["plan"], handle=handle)

    assert _stop_events(state_root) == [
        "GRACEFUL_STOP_REQUESTED", "GRACEFUL_STOP_EFFECTIVE"]


# --------------------------------------------------------------------------
# Section 7 -- plan-derived limits actually reach the real invocation
# --------------------------------------------------------------------------


def test_the_coordinator_passes_plan_limits_to_the_worker(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator_module
    from harness_coordinator.v1.coordinator import run_once

    state = _two_packet_plan_state(tmp_path, "limits")
    first = state["packet_ids"][0]
    seen = {}
    real_invoke = coordinator_module.invoke_worker

    def recording_invoke(*args, **kwargs):
        seen.update(kwargs.get("plan_budgets") or {})
        return real_invoke(*args, **kwargs)

    monkeypatch.setattr(coordinator_module, "invoke_worker", recording_invoke)
    run_once(state["state_root"], COORDINATOR_ID, RUN_ID, _context(),
             state["before_ceiling"], execution_plan=state["plan"],
             worker_adapters={"kimi_implementation": state["adapters"][first]})

    assert seen.get("command_timeout_seconds") == PLAN_COMMAND_TIMEOUT_SECONDS
    assert seen.get("output_bytes") == PLAN_OUTPUT_BYTES


def test_the_coordinator_derives_plan_limits_from_the_bound_journal(tmp_path):
    """A durably bound plan supplies the limits even without an explicit argument."""
    from harness_coordinator.v1.recovery import bound_execution_plan_for_run
    from harness_coordinator.v1.store import read_journal

    state = _two_packet_plan_state(tmp_path, "bound", bind=True)
    events, _ = read_journal(os.path.join(state["state_root"], "journal.ndjson"),
                             state_root_id=STATE_ROOT_ID)
    derived = bound_execution_plan_for_run(state["state_root"], events, RUN_ID)
    assert derived == state["plan"]
    assert bound_execution_plan_for_run("/dev/null", events, RUN_ID) is None
    assert bound_execution_plan_for_run(state["state_root"], events, "run-other") is None


# --------------------------------------------------------------------------
# Disposable two-packet plan fixture
# --------------------------------------------------------------------------


PLAN_COMMAND_TIMEOUT_SECONDS = 45
PLAN_OUTPUT_BYTES = 65536
WALL_CLOCK_SAFETY_SECONDS = 3600

WORKER = str(Path(__file__).with_name("synthetic_p5_worker.py").resolve())


def _context(coordinator_id=COORDINATOR_ID):
    return {"coordinator_id": coordinator_id, "hostname": "synthetic-host",
            "boot_id": "synthetic-boot", "pid": os.getpid(),
            "live_coordinator_ids": {coordinator_id}, "now": T_NOW}


def _execution_plan(packets):
    plan = {
        "schema_version": 1,
        "plan_id": PLAN_ID,
        "plan_sha256": "",
        "packets": [
            {
                "packet_id": packet["packet_id"],
                "packet_sha256": packet["packet_sha256"],
                "dependencies": list(packet.get("dependency_ids") or []),
                "capability_class": "implementation",
                "budgets": {
                    "attempt_limit": 2,
                    "retry_limit": 1,
                    "revision_limit": 1,
                    "turn_limit": 12,
                    "command_timeout_seconds": PLAN_COMMAND_TIMEOUT_SECONDS,
                    "output_bytes": PLAN_OUTPUT_BYTES,
                },
            }
            for packet in packets
        ],
        "routes": {
            "implementation": [{
                "route_id": "implementation-primary",
                "provider": "opencode",
                "model_id": "kimi-k2.7-code",
                "minimum_reasoning": "high",
                "enabled": True,
                "qualification_id": "qual-implementation-primary",
                "fallback_to": None,
            }],
        },
        "provider_backoff": {
            "max_retries": 3, "base_delay_seconds": 30, "max_delay_seconds": 300},
        "wall_clock_safety_seconds": WALL_CLOCK_SAFETY_SECONDS,
        "human_stop_categories": ["deployment", "governed_content"],
    }
    plan["plan_sha256"] = compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))
    return plan


def _two_packet_plan_state(tmp_path, name, bind=False, start_run=True):
    """Two enrolled packets in real registered worktrees under one plan.

    ``start_run`` performs one adapter-free iteration so the run has an
    authenticated RUN_STARTED to measure elapsed time against.  Without it the
    wall-clock backstop can never fire, because a run's clock starts when the
    run starts -- not when its packets were enrolled.  That iteration claims
    nothing: both packets declare writable paths and no adapter is supplied,
    so the coordinator reports ``awaiting_worker_adapter`` and leaves them
    READY.
    """
    from harness_coordinator.v1.enroll import enroll_packets
    from test_o3_p5_commissioning import (
        _commission_result, _registered_packet, _registered_worktrees)
    from test_o3_p5_review import _write_manifest, _write_trust_roots

    base = tmp_path / name
    base.mkdir()
    state_root = os.path.realpath(str(base / "state"))
    os.makedirs(os.path.join(state_root, "locks"))
    _write_manifest(state_root, state_root_id=STATE_ROOT_ID)
    _write_trust_roots(state_root)

    worktrees = _registered_worktrees(base, "one", "two")
    packets = [_registered_packet("%s-one" % name, worktrees[0]),
               _registered_packet("%s-two" % name, worktrees[1])]
    enroll_packets(state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID,
                   T_RUN_START, packets)

    plan = _execution_plan(packets)
    if bind:
        from harness_contracts.v1.execution_plan import bind_execution_plan
        from harness_coordinator.v1.seals_runtime import open_state_root

        # Bound after enrollment but before the run opens, so the journal stays
        # chronologically ordered and the binding precedes any claim.
        with open_state_root(state_root) as handle:
            bind_execution_plan(handle, canonical_bytes(plan), COORDINATOR_ID,
                                RUN_ID, T_BIND)

    adapters = {}
    for packet in packets:
        session = attempt_session_id(RUN_ID, packet["packet_id"], 1)
        result = _commission_result(packet, session, attempt=1)
        adapters[packet["packet_id"]] = WorkerAdapter(
            argv=(WORKER,),
            env={"SYNTHETIC_RESULT": json.dumps(
                     result, sort_keys=True, separators=(",", ":")),
                 "SYNTHETIC_MARKER_PATH": str(base / "markers.txt")})

    before_ceiling = "2026-08-11T00:10:00Z"
    past_ceiling = "2026-08-11T02:00:00Z"
    if start_run:
        from harness_coordinator.v1.coordinator import run_once

        opened = run_once(state_root, COORDINATOR_ID, RUN_ID, _context(),
                          before_ceiling, execution_plan=plan)
        assert opened["status"] == "awaiting_worker_adapter", opened["status"]

    return {
        "state_root": state_root,
        "plan": plan,
        "packets": packets,
        "packet_ids": [packet["packet_id"] for packet in packets],
        "adapters": adapters,
        "before_ceiling": before_ceiling,
        "past_ceiling": past_ceiling,
    }
