"""Bounded, synthetic-only worker invocation boundary for P5B."""

import json
import os
import selectors
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.classification import validate_attempt_outcome
from harness_contracts.v1.journal import IMMEDIATE_STOP_REASON_CODES
from harness_contracts.v1.worker_result import validate_worker_result
from harness_coordinator.v1.paths import validate_harness_id
from harness_coordinator.v1.process_sidecar import terminate_process_group, write_sidecar


_ALLOWED_ADAPTER_ENV = {"SYNTHETIC_RESULT", "SYNTHETIC_MARKER_PATH"}

# The two immediate process-safety limits enforced at this boundary.  Both are
# in the design's stable reason vocabulary, and both are excluded from the
# graceful stop vocabulary by construction: terminating a runaway process
# group is never an orderly end to the plan, and must not be recorded as one.
COMMAND_TIMEOUT = "COMMAND_TIMEOUT"
OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
# A subset check, not equality: a future immediate limit may legitimately join
# the contract vocabulary, but neither of these two may quietly leave it -- or
# be reclassified as graceful -- without this import failing loudly.  Raised,
# never asserted: ``python -O`` strips an assert, and a contract guard that an
# interpreter flag can optimise away is not a guard.
if not {COMMAND_TIMEOUT, OUTPUT_LIMIT_EXCEEDED} <= IMMEDIATE_STOP_REASON_CODES:
    raise RuntimeError(
        "immediate stop vocabulary no longer covers this boundary's own limits")

_PLAN_BUDGET_LIMIT_FIELDS = ("command_timeout_seconds", "output_bytes")
_FD_CWD_LAUNCHER = (
    "import os,sys; cwd_fd=int(sys.argv[1]); executable_fd=int(sys.argv[2]); argv=sys.argv[3:]; "
    "expected=os.fstat(executable_fd); actual=os.stat(argv[0],follow_symlinks=False); "
    "assert (expected.st_dev,expected.st_ino)==(actual.st_dev,actual.st_ino); "
    "os.fchdir(cwd_fd); os.execv(argv[0], argv)"
)


@dataclass(frozen=True)
class WorkerAdapter:
    """Operator-owned immutable synthetic adapter configuration.

    An adapter may REQUEST a tighter command timeout or output cap than the
    plan allows, and never a looser one: ``resolve_invocation_limits`` takes
    the minimum, so these two fields can only ever narrow the boundary.
    """

    argv: Tuple[str, ...]
    env: Mapping[str, str]
    requested_timeout_seconds: Optional[float] = None
    requested_output_limit_bytes: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.argv or not all(isinstance(arg, str) and arg for arg in self.argv):
            raise ValueError("adapter argv must be a non-empty fixed string tuple")
        if not isinstance(self.argv, tuple):
            raise ValueError("adapter argv must be immutable")
        if not os.path.isabs(self.argv[0]):
            raise ValueError("adapter executable must be an absolute operator-owned path")
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("adapter environment must contain strings")
            if key not in _ALLOWED_ADAPTER_ENV:
                raise ValueError(f"adapter environment key is not allowlisted: {key}")
        timeout = self.requested_timeout_seconds
        if timeout is not None and (isinstance(timeout, bool)
                                    or not isinstance(timeout, (int, float))
                                    or timeout <= 0):
            raise ValueError("adapter requested_timeout_seconds must be a positive number")
        output = self.requested_output_limit_bytes
        if output is not None and (isinstance(output, bool)
                                   or not isinstance(output, int)
                                   or output <= 0):
            raise ValueError(
                "adapter requested_output_limit_bytes must be a positive integer")


@dataclass(frozen=True)
class InvocationOutcome:
    result: Optional[Dict[str, Any]]
    error_codes: Tuple[str, ...]
    exit_code: Optional[int]
    timed_out: bool
    output_exceeded: bool
    interrupted: bool
    process_group_dead: bool
    pid: Optional[int]
    stdout_path: str
    stderr_path: str
    result_path: str
    sidecar_path: str
    environment_keys: Tuple[str, ...]
    # The stable immediate reason code that ended this invocation, or None
    # when nothing terminated it.  Never a graceful stop reason.
    termination_reason: Optional[str] = None
    # The worker's process GROUP, which is the honest unit of containment: a
    # child and grandchild inherit it unless they detach, so a group still
    # live is containment that did not hold.  ``None`` has exactly two
    # meanings, both of them "no group to ask about", never "the group is
    # dead": nothing was ever spawned (the pre-spawn interrupted return), or
    # the outcome was reconstructed from a completion receipt after a restart,
    # which records no pgid and whose process is gone regardless.
    pgid: Optional[int] = None


def resolve_invocation_limits(
    plan_budgets: Optional[Mapping[str, Any]],
    adapter: WorkerAdapter,
    timeout_seconds: float,
    output_limit_bytes: int,
) -> Tuple[float, int]:
    """Clamp the requested invocation limits to the authenticated plan.

    The plan value is a CEILING, not a default that some other channel may
    raise.  The result is the minimum over every bound supplied -- the plan,
    the adapter's own request, and the caller's argument -- so no adapter,
    caller, or future call site can widen a plan-derived limit.  This is the
    hard property; the clamp is not a convention that a later caller could
    opt out of by passing a larger number.

    ``plan_budgets`` may be ``None`` (no plan bound yet), in which case the
    caller's own bounds stand.  Anything else that is present but unusable
    fails closed with ``ValueError`` rather than silently going unbounded.
    """
    if not _is_positive_number(timeout_seconds):
        raise ValueError("timeout_seconds must be a positive number")
    if not _is_positive_int(output_limit_bytes):
        raise ValueError("output_limit_bytes must be a positive integer")

    timeout_bounds = [float(timeout_seconds)]
    output_bounds = [int(output_limit_bytes)]

    if plan_budgets is not None:
        if not isinstance(plan_budgets, Mapping):
            raise ValueError("plan budgets must be a mapping")
        for field in _PLAN_BUDGET_LIMIT_FIELDS:
            if field not in plan_budgets:
                raise ValueError(f"plan budgets are missing {field}")
        plan_timeout = plan_budgets["command_timeout_seconds"]
        plan_output = plan_budgets["output_bytes"]
        if not _is_positive_int(plan_timeout):
            raise ValueError("plan command_timeout_seconds must be a positive integer")
        if not _is_positive_int(plan_output):
            raise ValueError("plan output_bytes must be a positive integer")
        timeout_bounds.append(float(plan_timeout))
        output_bounds.append(int(plan_output))

    if adapter.requested_timeout_seconds is not None:
        timeout_bounds.append(float(adapter.requested_timeout_seconds))
    if adapter.requested_output_limit_bytes is not None:
        output_bounds.append(int(adapter.requested_output_limit_bytes))

    return min(timeout_bounds), min(output_bounds)


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_positive_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value > 0)


def _immediate_termination_reason(timed_out: bool, output_exceeded: bool) -> Optional[str]:
    """Name the immediate limit that ended this invocation, deterministically.

    Ordering matters only when both fire in the same poll: the deadline is
    reported first because it bounds the whole attempt, while the output cap
    bounds one channel of it.  Operator interruption is deliberately NOT given
    a code here -- the design names no reason family for it, and it already
    has a durable representation in ``interrupted``/``INTERRUPTED``.
    """
    if timed_out:
        return COMMAND_TIMEOUT
    if output_exceeded:
        return OUTPUT_LIMIT_EXCEEDED
    return None


def _claimed_paths_violate_packet(packet: Dict[str, Any], result: Dict[str, Any]) -> bool:
    """Retain an invocation diagnostic; postflight is the acceptance authority."""
    def under(path: str, parent: str) -> bool:
        normalized, base = os.path.normpath(path), os.path.normpath(parent)
        return normalized == base or normalized.startswith(base + os.sep)

    writable = packet.get("writable_paths", [])
    forbidden = packet.get("forbidden_surfaces", [])
    for changed in result.get("changed_files", []):
        path = changed.get("path") if isinstance(changed, dict) else None
        if not isinstance(path, str):
            return True
        if any(under(path, item) or under(item, path) for item in forbidden):
            return True
        if not any(under(path, item) for item in writable):
            return True
    return False


def _bounded_read_regular(dir_fd: int, name: str, maximum: int, expected_identity: Tuple[int, int]) -> bytes:
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != expected_identity:
            raise ValueError("result path was substituted")
        raw = b""
        while len(raw) <= maximum:
            chunk = os.read(fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                return raw
            raw += chunk
        raise OverflowError("result exceeds size limit")
    finally:
        os.close(fd)


def _adapter_sha256(adapter: WorkerAdapter) -> str:
    """The adapter identity a completion receipt is checked against.

    The two requested limit fields belong in this digest, not outside it: they
    change the EFFECTIVE timeout and output cap the adapter produces, so two
    adapters differing only in them are genuinely different adapters and a
    receipt written under one must not reconstruct under the other.  The
    timeout is normalised through ``float`` exactly as
    ``resolve_invocation_limits`` does, so the identity tracks the effective
    bound rather than whether the operator happened to write ``2`` or ``2.0``.
    """
    timeout = adapter.requested_timeout_seconds
    return compute_sha256(canonical_bytes({
        "argv": list(adapter.argv),
        "env": dict(adapter.env),
        "requested_timeout_seconds": None if timeout is None else float(timeout),
        "requested_output_limit_bytes": adapter.requested_output_limit_bytes,
    }))


def _publish_completion_receipt(dir_fd: int, receipt: Dict[str, Any]) -> None:
    data = canonical_bytes(receipt)
    pending = "completion.pending"
    final = "completion.json"
    fd = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dir_fd)
    try:
        remaining = data
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.link(pending, final, src_dir_fd=dir_fd, dst_dir_fd=dir_fd,
            follow_symlinks=False)
    os.fsync(dir_fd)
    os.unlink(pending, dir_fd=dir_fd)
    os.fsync(dir_fd)


def _secure_artifact_dir(state_root: str, intent_id: str) -> Tuple[str, int, int, int]:
    os.makedirs(state_root, mode=0o700, exist_ok=True)
    root_info = os.lstat(state_root)
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("state root is not a trusted directory")
    root_fd = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            os.mkdir("invocations", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        inv_fd = os.open("invocations", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
        try:
            os.mkdir(intent_id, mode=0o700, dir_fd=inv_fd)
            child_fd = os.open(intent_id, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=inv_fd)
        except Exception:
            os.close(inv_fd)
            raise
    except Exception:
        os.close(root_fd)
        raise
    return os.path.join(os.path.realpath(state_root), "invocations", intent_id), root_fd, inv_fd, child_fd


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _fd_identity(fd: int) -> Tuple[int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def _canonical_aliases_intact(state_root: str, root_fd: int, inv_fd: int,
                              artifact_fd: int, intent_id: str) -> bool:
    check_root = check_inv = check_artifact = None
    try:
        check_root = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        if not _same_identity(os.fstat(check_root), os.fstat(root_fd)):
            return False
        check_inv = os.open("invocations", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=check_root)
        if not _same_identity(os.fstat(check_inv), os.fstat(inv_fd)):
            return False
        check_artifact = os.open(intent_id, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=check_inv)
        return _same_identity(os.fstat(check_artifact), os.fstat(artifact_fd))
    except OSError:
        return False
    finally:
        for fd in (check_artifact, check_inv, check_root):
            if fd is not None:
                os.close(fd)


def invoke_worker(state_root: str, state_root_id: str, packet: Dict[str, Any],
                  intent_id: str, attempt_session_id: str, adapter: WorkerAdapter,
                  *, timeout_seconds: float = 30.0, output_limit_bytes: int = 1024 * 1024,
                  result_limit_bytes: int = 1024 * 1024, terminate_grace_seconds: float = 1.0,
                  stop_requested: Optional[Callable[[], bool]] = None,
                  plan_budgets: Optional[Mapping[str, Any]] = None,
                  allowed_worktree: str) -> InvocationOutcome:
    """Invoke one fixed synthetic adapter; never executes packet-selected commands.

    ``plan_budgets`` supplies the authenticated plan's ``command_timeout_seconds``
    and ``output_bytes``.  They are ceilings: the effective limits are resolved
    before anything is spawned, and neither this call's own arguments nor the
    adapter can raise them.
    """
    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    validate_harness_id(intent_id, "/intent_id")
    # Resolved before the stop check and before any spawn, so an unusable plan
    # budget refuses the invocation instead of running it unbounded.
    timeout_seconds, output_limit_bytes = resolve_invocation_limits(
        plan_budgets, adapter, timeout_seconds, output_limit_bytes)
    if stop_requested is not None and stop_requested():
        # Nothing was spawned, so there is no process group to name: pgid stays
        # None because none exists, not because containment is unknown.
        return InvocationOutcome(None, ("INTERRUPTED",), None, False, False, True, True, None,
                                 "", "", "", "", tuple())
    packet_worktree = packet.get("worktree", {}).get("path")
    if not isinstance(allowed_worktree, str) or packet_worktree != allowed_worktree:
        raise ValueError("packet worktree does not match operator-owned allowed worktree")
    worktree_info = os.lstat(allowed_worktree)
    if stat.S_ISLNK(worktree_info.st_mode) or not stat.S_ISDIR(worktree_info.st_mode):
        raise ValueError("allowed worktree is not a real directory")
    executable_fd = worktree_fd = root_fd = inv_fd = artifact_fd = None
    stdout_fd = stderr_fd = result_fd = None
    selector = process = None
    process_identity = None
    sidecar: Optional[Dict[str, Any]] = None
    artifact_dir = stdout_path = stderr_path = result_path = sidecar_path = ""
    result_identity = None
    environment: Dict[str, str] = {}
    timed_out = output_exceeded = interrupted = False
    group_dead = True
    capture_total = 0
    outcome: Optional[InvocationOutcome] = None
    try:
        try:
            executable_fd = os.open(adapter.argv[0], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ValueError("adapter executable cannot be opened without following links") from exc
        executable_info = os.fstat(executable_fd)
        if not stat.S_ISREG(executable_info.st_mode) or not executable_info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            raise ValueError("adapter executable must be a non-symlink executable regular file")
        worktree_fd = os.open(allowed_worktree, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        artifact_dir, root_fd, inv_fd, artifact_fd = _secure_artifact_dir(state_root, intent_id)
        stdout_path = os.path.join(artifact_dir, "stdout.bin")
        stderr_path = os.path.join(artifact_dir, "stderr.bin")
        result_path = os.path.join(artifact_dir, "worker-result.json")
        sidecar_path = os.path.join(artifact_dir, "process.json")
        create_flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        stdout_fd = os.open("stdout.bin", create_flags, 0o600, dir_fd=artifact_fd)
        stderr_fd = os.open("stderr.bin", create_flags, 0o600, dir_fd=artifact_fd)
        result_fd = os.open("worker-result.json", create_flags, 0o600, dir_fd=artifact_fd)
        result_info = os.fstat(result_fd)
        result_identity = (result_info.st_dev, result_info.st_ino)
        environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
        environment.update(dict(adapter.env))
        environment.update({
            "HARNESS_RESULT_FD": str(result_fd),
            "HARNESS_PACKET_ID": packet_id, "HARNESS_ATTEMPT": str(packet["attempt"]),
            "HARNESS_ATTEMPT_SESSION_ID": attempt_session_id,
        })
        selector = selectors.DefaultSelector()
        launch_argv = (os.path.realpath(sys.executable), "-c", _FD_CWD_LAUNCHER,
                       str(worktree_fd), str(executable_fd), *adapter.argv)
        process = subprocess.Popen(launch_argv, cwd=None, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   shell=False, start_new_session=True, close_fds=True,
                                   pass_fds=(worktree_fd, executable_fd, result_fd))
        assert process.stdout is not None and process.stderr is not None
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ, stdout_fd)
        selector.register(process.stderr, selectors.EVENT_READ, stderr_fd)
        sidecar = write_sidecar(
            "process.json",
            state_root_id,
            packet_id,
            packet["attempt"],
            intent_id,
            process.pid,
            os.getpgid(process.pid),
            dir_fd=artifact_fd,
        )
        process_identity = sidecar["process_start_identity"]
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            for key, _ in selector.select(.01):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                capture_fd = key.data
                remaining = max(0, output_limit_bytes - capture_total)
                if len(chunk) > remaining:
                    output_exceeded = True
                if remaining:
                    written = os.write(capture_fd, chunk[:remaining])
                    capture_total += written
            if stop_requested is not None and stop_requested():
                interrupted = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            if output_exceeded:
                break
        if process.poll() is None:
            group_dead = terminate_process_group(
                process.pid,
                terminate_grace_seconds,
                expected_leader_identity=process_identity,
            )
            process.wait(timeout=3)
        else:
            process.wait()
        group_dead = terminate_process_group(
            process.pid,
            terminate_grace_seconds,
            expected_leader_identity=process_identity,
        )
        if not group_dead:
            raise RuntimeError("worker process group survived completion cleanup")
        for key in list(selector.get_map().values()):
            while True:
                try:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    break
                capture_fd = key.data
                remaining = max(0, output_limit_bytes - capture_total)
                if len(chunk) > remaining:
                    output_exceeded = True
                if remaining:
                    written = os.write(capture_fd, chunk[:remaining])
                    capture_total += written

        errors = []
        result = None
        if interrupted:
            errors.append("INTERRUPTED")
        if timed_out:
            errors.append("TIMED_OUT")
        if output_exceeded:
            errors.append("OUTPUT_LIMIT_EXCEEDED")
        aliases_intact = _canonical_aliases_intact(state_root, root_fd, inv_fd, artifact_fd, intent_id)
        if not aliases_intact:
            errors.append("ARTIFACT_PATH_UNSAFE")
        if aliases_intact:
            try:
                raw = _bounded_read_regular(artifact_fd, "worker-result.json", result_limit_bytes, result_identity)
                if not raw:
                    errors.append("RESULT_MISSING")
                else:
                    try:
                        value = json.loads(raw.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        errors.append("INVALID_JSON")
                    else:
                        validation = validate_worker_result(value)
                        errors.extend(item["code"] for item in validation["errors"])
                        if validation["valid"]:
                            assigned = packet["assigned_worker"]
                            expected = (packet_id, packet["packet_sha256"], packet["attempt"], attempt_session_id,
                                        assigned["worker_id"], assigned["provider"], assigned["model"], packet["lane"])
                            worker = value.get("worker", {})
                            actual = (value.get("packet_id"), value.get("packet_sha256"), value.get("attempt"),
                                      worker.get("session_id"), worker.get("worker_id"), worker.get("provider"),
                                      worker.get("model"), worker.get("lane"))
                            if actual != expected:
                                errors.append("RESULT_IDENTITY_MISMATCH")
                            else:
                                # Only the coordinator's Git postflight is authoritative
                                # for changed-path scope. A worker's manifest remains a
                                # claim that postflight compares after completion.
                                if _claimed_paths_violate_packet(packet, value):
                                    errors.append("FORBIDDEN_PATH")
                                result = value
            except (OSError, ValueError):
                errors.append("RESULT_PATH_UNSAFE")
            except OverflowError:
                errors.append("RESULT_LIMIT_EXCEEDED")
        public_paths = (stdout_path, stderr_path, result_path, sidecar_path) if aliases_intact else ("", "", "", "")
        outcome = InvocationOutcome(result, tuple(dict.fromkeys(errors)), process.returncode,
                                    timed_out, output_exceeded, interrupted, group_dead, process.pid,
                                    *public_paths,
                                    tuple(sorted(environment)),
                                    termination_reason=_immediate_termination_reason(
                                        timed_out, output_exceeded),
                                    pgid=(sidecar or {}).get("pgid"))
        stdout_raw = _bounded_read_regular(
            artifact_fd, "stdout.bin", output_limit_bytes,
            _fd_identity(stdout_fd))
        stderr_raw = _bounded_read_regular(
            artifact_fd, "stderr.bin", output_limit_bytes,
            _fd_identity(stderr_fd))
        try:
            captured_result = _bounded_read_regular(
                artifact_fd, "worker-result.json", result_limit_bytes, result_identity)
        except (OSError, ValueError, OverflowError):
            captured_result = None
        receipt = {
            "schema_version": 1, "state_root_id": state_root_id,
            "packet_id": packet_id, "packet_sha256": packet["packet_sha256"],
            "attempt": packet["attempt"], "intent_id": intent_id,
            "attempt_session_id": attempt_session_id,
            "adapter_sha256": _adapter_sha256(adapter),
            "exit_code": outcome.exit_code, "timed_out": outcome.timed_out,
            "output_exceeded": outcome.output_exceeded,
            "interrupted": outcome.interrupted,
            "process_group_dead": outcome.process_group_dead,
            # Bounded metadata only: the stable reason an immediate limit
            # ended this invocation.  Captured bytes are represented by their
            # digest and length below, never by their content.
            "termination_reason": outcome.termination_reason,
            "pid": outcome.pid, "error_codes": list(outcome.error_codes),
            "stdout": {"sha256": compute_sha256(stdout_raw), "byte_length": len(stdout_raw)},
            "stderr": {"sha256": compute_sha256(stderr_raw), "byte_length": len(stderr_raw)},
            "result": {"sha256": (compute_sha256(captured_result)
                                  if captured_result is not None else None),
                       "byte_length": (len(captured_result) if captured_result is not None else 0),
                       "present": captured_result is not None, "valid": result is not None},
            "receipt_sha256": "",
        }
        receipt["receipt_sha256"] = compute_sha256(
            canonical_bytes(receipt, omit={"receipt_sha256"}))
        _publish_completion_receipt(artifact_fd, receipt)
    finally:
        if process is not None:
            group_dead = terminate_process_group(
                process.pid,
                terminate_grace_seconds,
                expected_leader_identity=process_identity,
            )
            if process.poll() is None:
                process.wait(timeout=3)
            if not group_dead:
                raise RuntimeError("worker process group survived cleanup")
        if selector is not None:
            selector.close()
        for fd in (result_fd, stderr_fd, stdout_fd, artifact_fd, inv_fd, root_fd, worktree_fd, executable_fd):
            if fd is not None:
                os.close(fd)
    assert outcome is not None
    return outcome


def persist_invocation_outcome(handle, packet: Dict[str, Any], intent_id: str,
                               invocation: InvocationOutcome, adapter: WorkerAdapter,
                               coordinator_id: str, run_id: str, now: str,
                               postflight: Dict[str, Any]) -> Dict[str, Any]:
    """Publish coordinator-owned attempt evidence, with outcome last.

    ``attempt_outcome.json`` is the durable completion marker consumed by
    restart recovery. Every source artifact is read through the pinned state
    root; worker-supplied paths are never accepted.
    """
    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    from harness_coordinator.v1.workspace_evidence import validate_postflight_binding

    validated_postflight = validate_postflight_binding(handle, packet, intent_id, postflight)
    persisted_postflight = validated_postflight["artifact"]
    postflight_binding = validated_postflight["binding"]
    attempt = packet["attempt"]
    base = ("results", packet_id, str(attempt))
    invocation_base = ("invocations", validate_harness_id(intent_id, "/intent_id"))
    stdout = handle.read(invocation_base + ("stdout.bin",))
    stderr = handle.read(invocation_base + ("stderr.bin",))
    if stdout is None or stderr is None:
        raise ValueError("invocation capture is missing from the pinned state root")
    stdout_path = "/".join(base + ("stdout.bin",))
    stderr_path = "/".join(base + ("stderr.bin",))
    handle.publish(base + ("stdout.bin",), stdout)
    handle.publish(base + ("stderr.bin",), stderr)

    result = invocation.result
    result_raw = canonical_bytes(result) if result is not None else None
    result_path = "/".join(base + ("worker-result.json",)) if result_raw is not None else None
    if result_raw is not None:
        handle.publish(base + ("worker-result.json",), result_raw)
    errors = list(invocation.error_codes)
    authority = {"guard_denials": [], "undeclared_changed_paths": [],
                 "governed_path_touches": [], "hard_stop_matches": [],
                 "hard_stop_reasons": []}
    if not persisted_postflight.get("acceptance_allowed", False):
        scope = persisted_postflight.get("scope_findings") or []
        authority["undeclared_changed_paths"] = sorted({
            item.get("path") for item in scope
            if isinstance(item, dict) and isinstance(item.get("path"), str)
            and item.get("code") != "ALLOWLIST_VIOLATION_GOVERNED"
        })
        authority["governed_path_touches"] = sorted({
            item.get("path") for item in scope
            if isinstance(item, dict) and item.get("code") == "ALLOWLIST_VIOLATION_GOVERNED"
            and isinstance(item.get("path"), str)
        })
        hard_stop_paths = []
        for key in ("worker_manifest_findings", "protected_findings", "secret_findings"):
            hard_stop_paths.extend(
                item.get("path") for item in (persisted_postflight.get(key) or [])
                if isinstance(item, dict) and isinstance(item.get("path"), str) and item.get("path")
        )
        if not hard_stop_paths:
            hard_stop_paths = list(persisted_postflight.get("writable_paths") or [])[:1]
        authority["hard_stop_matches"] = sorted(set(hard_stop_paths))
        capture_unverifiable = any(
            item.get("code") == "PROTECTED_WORKTREE_CHANGED_UNVERIFIABLE"
            for item in (persisted_postflight.get("protected_findings") or []) if isinstance(item, dict)
        )
        if capture_unverifiable or not hard_stop_paths:
            authority["hard_stop_reasons"] = ["workspace_postflight_capture_failed"]
    record = {
        "schema_version": 1,
        "packet_id": packet_id,
        "packet_sha256": packet["packet_sha256"],
        "attempt": attempt,
        "coordinator_id": coordinator_id,
        "run_id": run_id,
        "lane": packet["lane"],
        "invocation": {
            "argv": list(adapter.argv), "cwd": ".", "started_at": now,
            "finished_at": now, "exit_code": invocation.exit_code,
            "signal": (-invocation.exit_code if invocation.exit_code is not None
                       and invocation.exit_code < 0 else None),
            "timed_out": invocation.timed_out, "wall_clock_seconds": 0,
        },
        "stdout": {"path": stdout_path, "sha256": compute_sha256(stdout),
                   "byte_length": len(stdout)},
        "stderr": {"path": stderr_path, "sha256": compute_sha256(stderr),
                   "byte_length": len(stderr)},
        "raw_result": {"path": result_path,
                       "sha256": result.get("result_sha256") if result is not None else None,
                       "byte_length": len(result_raw) if result_raw is not None else 0},
        "result_validation": {"present": result is not None, "valid": result is not None,
                              "error_codes": errors, "error_count": len(errors)},
        "authority": authority,
        "provider_evidence_sha256": None,
        "workspace_postflight": postflight_binding,
        "outcome": result.get("outcome") if result is not None else "FAILED",
        "fallback": result.get("fallback") if result is not None else None,
        "outcome_sha256": "",
    }
    record["outcome_sha256"] = compute_sha256(
        canonical_bytes(record, omit={"outcome_sha256"}))
    validation = validate_attempt_outcome(record)
    if not validation["valid"]:
        raise ValueError(
            f"coordinator-built attempt outcome is invalid: {validation['errors'][0]['message']}")
    handle.publish(base + ("attempt_outcome.json",), canonical_bytes(record))
    return record


def load_completed_invocation(handle, state_root_id: str, packet: Dict[str, Any],
                              intent_id: str, attempt_session_id: str,
                              adapter: WorkerAdapter) -> Optional[InvocationOutcome]:
    """Authenticate and reconstruct one durably completed invocation."""
    parts = ("invocations", validate_harness_id(intent_id, "/intent_id"))
    raw = handle.read(parts + ("completion.json",))
    pending = False
    if raw is None:
        raw = handle.read(parts + ("completion.pending",))
        pending = raw is not None
    if raw is None:
        return None
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invocation completion receipt is invalid JSON") from exc
    if raw != canonical_bytes(receipt):
        raise ValueError("invocation completion receipt is not canonical")
    declared = receipt.get("receipt_sha256")
    if declared != compute_sha256(canonical_bytes(receipt, omit={"receipt_sha256"})):
        raise ValueError("invocation completion receipt self-hash mismatch")
    expected = (
        state_root_id, packet["packet_id"], packet["packet_sha256"], packet["attempt"],
        intent_id, attempt_session_id, _adapter_sha256(adapter), True)
    actual = (
        receipt.get("state_root_id"), receipt.get("packet_id"),
        receipt.get("packet_sha256"), receipt.get("attempt"),
        receipt.get("intent_id"), receipt.get("attempt_session_id"),
        receipt.get("adapter_sha256"), receipt.get("process_group_dead"))
    if actual != expected:
        raise ValueError("invocation completion receipt identity mismatch")

    captures = {}
    for name in ("stdout", "stderr"):
        capture = handle.read(parts + (f"{name}.bin",))
        pointer = receipt.get(name) or {}
        if (capture is None or len(capture) != pointer.get("byte_length")
                or compute_sha256(capture) != pointer.get("sha256")):
            raise ValueError(f"invocation completion {name} mismatch")
        captures[name] = capture
    result_pointer = receipt.get("result") or {}
    result_raw = None
    if result_pointer.get("present"):
        result_raw = handle.read(parts + ("worker-result.json",))
        if (result_raw is None or len(result_raw) != result_pointer.get("byte_length")
                or compute_sha256(result_raw) != result_pointer.get("sha256")):
            raise ValueError("invocation completion result mismatch")
    # Re-derived from the receipt's own authenticated flags, then checked
    # against what the receipt recorded.  The two are produced by one function
    # from one pair of flags, so a disagreement means the record is internally
    # inconsistent and must not be reconstructed into a usable outcome.
    termination_reason = _immediate_termination_reason(
        bool(receipt.get("timed_out")), bool(receipt.get("output_exceeded")))
    if receipt.get("termination_reason", termination_reason) != termination_reason:
        raise ValueError("invocation completion receipt termination reason disagrees")

    result = None
    if result_pointer.get("valid"):
        if result_raw is None:
            raise ValueError("valid invocation receipt has no worker result")
        try:
            candidate = json.loads(result_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("completed worker result is invalid JSON") from exc
        validation = validate_worker_result(candidate)
        if not validation["valid"] or result_raw != canonical_bytes(candidate):
            raise ValueError("completed worker result is contract-invalid")
        assigned = packet["assigned_worker"]
        worker = candidate.get("worker") or {}
        if ((candidate.get("packet_id"), candidate.get("packet_sha256"), candidate.get("attempt"),
             worker.get("session_id"), worker.get("worker_id"), worker.get("provider"),
             worker.get("model"), worker.get("lane")) !=
                (packet["packet_id"], packet["packet_sha256"], packet["attempt"],
                 attempt_session_id, assigned["worker_id"], assigned["provider"],
                 assigned["model"], packet["lane"])):
            raise ValueError("completed worker result identity mismatch")
        result = candidate
    artifact_dir = os.path.join(handle.path, *parts)
    if pending:
        handle.publish(parts + ("completion.json",), raw)
        handle.unlink(parts + ("completion.pending",), predicate=lambda current: current == raw)
    # pgid is left None deliberately, and the receipt is not extended to carry
    # one: it is UNKNOWN AFTER RESTART.  A pgid recorded before a crash names a
    # process group this process never observed and whose id the operating
    # system is free to have reused, so reconstructing one would offer a
    # containment answer nobody may rely on.  ``process_group_dead`` is True
    # here on the receipt's own authority, which is the claim that is sound.
    return InvocationOutcome(
        result, tuple(receipt.get("error_codes") or ()), receipt.get("exit_code"),
        bool(receipt.get("timed_out")), bool(receipt.get("output_exceeded")),
        bool(receipt.get("interrupted")), True, receipt.get("pid"),
        os.path.join(artifact_dir, "stdout.bin"), os.path.join(artifact_dir, "stderr.bin"),
        os.path.join(artifact_dir, "worker-result.json"),
        os.path.join(artifact_dir, "process.json"), tuple(),
        termination_reason=termination_reason, pgid=None)


__all__ = ["COMMAND_TIMEOUT", "OUTPUT_LIMIT_EXCEEDED", "InvocationOutcome",
           "WorkerAdapter", "invoke_worker", "load_completed_invocation",
           "persist_invocation_outcome", "resolve_invocation_limits"]
