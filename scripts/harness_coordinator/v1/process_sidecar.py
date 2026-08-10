"""Advisory process identity records for recovery-safe worker termination."""

import json
import os
import ctypes
import platform
import signal
import time
from typing import Any, Dict, Optional

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256


def _linux_stat_starttime(text: str) -> Optional[str]:
    """Extract field 22 without splitting spaces inside the parenthesized comm."""
    closing = text.rfind(")")
    if closing < 0:
        return None
    tail = text[closing + 1:].strip().split()
    return tail[19] if len(tail) > 19 else None


def process_start_identity(pid: int) -> Optional[str]:
    """Return a stable-enough kernel process identity, or None when not live."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        return None
    if platform.system() == "Darwin":
        class ProcBsdInfo(ctypes.Structure):
            _fields_ = [
                ("pbi_flags", ctypes.c_uint32), ("pbi_status", ctypes.c_uint32),
                ("pbi_xstatus", ctypes.c_uint32), ("pbi_pid", ctypes.c_uint32),
                ("pbi_ppid", ctypes.c_uint32), ("pbi_uid", ctypes.c_uint32),
                ("pbi_gid", ctypes.c_uint32), ("pbi_ruid", ctypes.c_uint32),
                ("pbi_rgid", ctypes.c_uint32), ("pbi_svuid", ctypes.c_uint32),
                ("pbi_svgid", ctypes.c_uint32), ("rfu_1", ctypes.c_uint32),
                ("pbi_comm", ctypes.c_char * 16), ("pbi_name", ctypes.c_char * 32),
                ("pbi_nfiles", ctypes.c_uint32), ("pbi_pgid", ctypes.c_uint32),
                ("pbi_pjobc", ctypes.c_uint32), ("e_tdev", ctypes.c_uint32),
                ("e_tpgid", ctypes.c_uint32), ("pbi_nice", ctypes.c_int32),
                ("pbi_start_tvsec", ctypes.c_uint64), ("pbi_start_tvusec", ctypes.c_uint64),
            ]
        info = ProcBsdInfo()
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        size = libproc.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if size != ctypes.sizeof(info) or info.pbi_status == 5:
            return None
        material = f"{info.pbi_pid}:{info.pbi_start_tvsec}:{info.pbi_start_tvusec}"
        return compute_sha256(material.encode("ascii"))
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="ascii") as handle:
            text = handle.read()
        closing = text.rfind(")")
        tail = text[closing + 1:].strip().split() if closing >= 0 else []
        starttime = _linux_stat_starttime(text)
        if not tail or tail[0] == "Z" or starttime is None:
            return None
        return compute_sha256(f"{pid}:{starttime}".encode("ascii"))
    except (OSError, IndexError):
        return None


def _validate_sidecar(value: Any) -> Dict[str, Any]:
    required = {
        "schema_version", "state_root_id", "packet_id", "attempt", "intent_id",
        "pid", "pgid", "process_start_identity", "sidecar_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("invalid process sidecar fields")
    if value["schema_version"] != 1:
        raise ValueError("invalid process sidecar schema")
    for key in ("state_root_id", "packet_id", "intent_id", "process_start_identity"):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError(f"invalid process sidecar {key}")
    for key in ("attempt", "pid", "pgid"):
        if isinstance(value[key], bool) or not isinstance(value[key], int) or value[key] < 1:
            raise ValueError(f"invalid process sidecar {key}")
    expected = compute_sha256(canonical_bytes(value, omit={"sidecar_sha256"}))
    if value["sidecar_sha256"] != expected:
        raise ValueError("process sidecar hash mismatch")
    return value


def write_sidecar(path: str, state_root_id: str, packet_id: str, attempt: int,
                  intent_id: str, pid: int, pgid: int, *, dir_fd: Optional[int] = None) -> Dict[str, Any]:
    if dir_fd is not None and (path != os.path.basename(path) or path in {"", ".", ".."}):
        raise ValueError("sidecar dir_fd requires a basename")
    identity = process_start_identity(pid)
    if identity is None:
        raise ValueError("worker process is not live")
    value = {
        "schema_version": 1, "state_root_id": state_root_id, "packet_id": packet_id,
        "attempt": attempt, "intent_id": intent_id, "pid": pid, "pgid": pgid,
        "process_start_identity": identity, "sidecar_sha256": "",
    }
    value["sidecar_sha256"] = compute_sha256(canonical_bytes(value, omit={"sidecar_sha256"}))
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600,
                 dir_fd=dir_fd)
    try:
        data = canonical_bytes(value)
        while data:
            written = os.write(fd, data)
            data = data[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return value


def read_sidecar(path: str, *, dir_fd: Optional[int] = None) -> Dict[str, Any]:
    if dir_fd is not None and (path != os.path.basename(path) or path in {"", ".", ".."}):
        raise ValueError("sidecar dir_fd requires a basename")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
    try:
        raw = b""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            raw += chunk
            if len(raw) > 16384:
                raise ValueError("process sidecar exceeds size limit")
    finally:
        os.close(fd)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid process sidecar JSON") from exc
    if raw != canonical_bytes(value):
        raise ValueError("process sidecar is not canonical")
    return _validate_sidecar(value)


def _group_is_live(pgid: int) -> bool:
    if platform.system() == "Darwin":
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        capacity = 4096
        pids = (ctypes.c_int * capacity)()
        size = libproc.proc_listpids(2, pgid, ctypes.byref(pids), ctypes.sizeof(pids))
        if size <= 0:
            return False
        return any(process_start_identity(pid) is not None for pid in pids[: size // ctypes.sizeof(ctypes.c_int)] if pid > 0)
    try:
        names = os.listdir("/proc")
    except OSError:
        return True
    for name in names:
        if not name.isdigit():
            continue
        try:
            if os.getpgid(int(name)) == pgid and process_start_identity(int(name)) is not None:
                return True
        except (ProcessLookupError, PermissionError):
            continue
    return False


def terminate_process_group(pgid: int, grace_seconds: float) -> bool:
    """TERM, then KILL if required, returning only after group death."""
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < deadline:
        if not _group_is_live(pgid):
            return True
        time.sleep(.01)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _group_is_live(pgid):
            return True
        time.sleep(.01)
    return False


def terminate_sidecar_process(intent_dir_fd: int, basename: str, expected_state_root_id: str,
                              expected_packet_id: str, expected_attempt: int, expected_intent_id: str,
                              grace_seconds: float = 1.0) -> bool:
    """Read by trusted intent dir FD and terminate only the exact attempt."""
    if basename != os.path.basename(basename) or basename in {"", ".", ".."}:
        raise ValueError("sidecar termination requires a strict basename")
    sidecar = read_sidecar(basename, dir_fd=intent_dir_fd)
    expected = (expected_state_root_id, expected_packet_id, expected_attempt, expected_intent_id)
    actual = (sidecar["state_root_id"], sidecar["packet_id"], sidecar["attempt"], sidecar["intent_id"])
    if actual != expected:
        raise ValueError("process sidecar identity does not match expected attempt")
    if process_start_identity(sidecar["pid"]) != sidecar["process_start_identity"]:
        return False
    try:
        if os.getpgid(sidecar["pid"]) != sidecar["pgid"]:
            return False
        if sidecar["pid"] != sidecar["pgid"] or os.getsid(sidecar["pid"]) != sidecar["pid"]:
            return False
    except ProcessLookupError:
        return False
    return terminate_process_group(sidecar["pgid"], grace_seconds)


__all__ = ["process_start_identity", "read_sidecar", "terminate_process_group",
           "terminate_sidecar_process", "write_sidecar"]
