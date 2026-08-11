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

from harness_contracts.v1.worker_result import validate_worker_result
from harness_coordinator.v1.paths import validate_harness_id
from harness_coordinator.v1.process_sidecar import terminate_process_group, write_sidecar


_ALLOWED_ADAPTER_ENV = {"SYNTHETIC_RESULT", "SYNTHETIC_MARKER_PATH"}
_FD_CWD_LAUNCHER = (
    "import os,sys; cwd_fd=int(sys.argv[1]); executable_fd=int(sys.argv[2]); argv=sys.argv[3:]; "
    "expected=os.fstat(executable_fd); actual=os.stat(argv[0],follow_symlinks=False); "
    "assert (expected.st_dev,expected.st_ino)==(actual.st_dev,actual.st_ino); "
    "os.fchdir(cwd_fd); os.execv(argv[0], argv)"
)


@dataclass(frozen=True)
class WorkerAdapter:
    """Operator-owned immutable synthetic adapter configuration."""

    argv: Tuple[str, ...]
    env: Mapping[str, str]

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


def _under(path: str, parent: str) -> bool:
    normalized = os.path.normpath(path)
    base = os.path.normpath(parent)
    return normalized == base or normalized.startswith(base + os.sep)


def _result_paths_allowed(packet: Dict[str, Any], result: Dict[str, Any]) -> bool:
    writable = packet.get("writable_paths", [])
    forbidden = packet.get("forbidden_surfaces", [])
    for changed in result.get("changed_files", []):
        path = changed.get("path") if isinstance(changed, dict) else None
        if not isinstance(path, str):
            return False
        if any(_under(path, item) or _under(item, path) for item in forbidden):
            return False
        if not any(_under(path, item) for item in writable):
            return False
    return True


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
                  allowed_worktree: str) -> InvocationOutcome:
    """Invoke one fixed synthetic adapter; never executes packet-selected commands."""
    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    validate_harness_id(intent_id, "/intent_id")
    if stop_requested is not None and stop_requested():
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
                            elif not _result_paths_allowed(packet, value):
                                errors.append("FORBIDDEN_PATH")
                            else:
                                result = value
            except (OSError, ValueError):
                errors.append("RESULT_PATH_UNSAFE")
            except OverflowError:
                errors.append("RESULT_LIMIT_EXCEEDED")
        public_paths = (stdout_path, stderr_path, result_path, sidecar_path) if aliases_intact else ("", "", "", "")
        outcome = InvocationOutcome(result, tuple(dict.fromkeys(errors)), process.returncode,
                                    timed_out, output_exceeded, interrupted, group_dead, process.pid,
                                    *public_paths,
                                    tuple(sorted(environment)))
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


__all__ = ["InvocationOutcome", "WorkerAdapter", "invoke_worker"]
