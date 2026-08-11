"""Claim-record I/O and reclaim for the harness coordinator v1."""

import json
import os
import stat
from typing import Any, Dict, List

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.claim import classify_claim, validate_claim
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id


def _claim_name(packet_id: str) -> str:
    return f"{validate_harness_id(packet_id)}.lock.json"


def _write_all(fd: int, data: bytes) -> None:
    remaining = data
    while remaining:
        remaining = remaining[os.write(fd, remaining):]


def _read_regular_at(directory_fd: int, name: str) -> bytes:
    fd = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"claim slot {name!r} is not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _parse_claim(raw: bytes) -> Dict[str, Any]:
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Claim record root is not an object")
    return parsed


def create_claim_at(handle, packet_id: str, record: Dict[str, Any]) -> None:
    """Create a canonical claim through a pinned state-root handle."""
    name = _claim_name(packet_id)
    data = canonical_bytes(record)
    with handle.directory(("locks",), create=True) as locks_fd:
        fd = os.open(
            name,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=locks_fd,
        )
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(locks_fd)


def read_claim_at(handle, packet_id: str) -> Dict[str, Any]:
    """Read a regular claim through the pinned root, never following links."""
    with handle.directory(("locks",)) as locks_fd:
        return _parse_claim(_read_regular_at(locks_fd, _claim_name(packet_id)))


def list_worker_claim_ids(handle) -> List[str]:
    """List canonical worker-claim IDs from the pinned locks directory."""
    try:
        with handle.directory(("locks",)) as locks_fd:
            packet_ids = []
            for name in os.listdir(locks_fd):
                if not name.endswith(".lock.json"):
                    continue
                packet_id = name[:-len(".lock.json")]
                if _claim_name(packet_id) != name:
                    raise ValueError(f"non-canonical worker claim name: {name!r}")
                info = os.stat(name, dir_fd=locks_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError(f"worker claim {name!r} is not a regular file")
                packet_ids.append(packet_id)
            return sorted(packet_ids)
    except FileNotFoundError:
        return []


def reclaim_lock_at(handle, packet_id: str, run_id: str, classification: str,
                    expected_claim_sha256: str) -> None:
    """Exclusively archive an unchanged claim through pinned directory FDs."""
    if classification not in {"STALE_PRIOR_BOOT", "STALE_SAME_BOOT"}:
        raise ValueError(
            f"reclaim_lock_at called with non-reclaimable classification: {classification}"
        )
    validate_harness_id(run_id)
    name = _claim_name(packet_id)
    with handle.directory(("locks",)) as source_fd:
        record = _parse_claim(_read_regular_at(source_fd, name))
        validation = validate_claim(record)
        if not validation["valid"]:
            raise ValueError(
                f"Claim changed after reclaim evidence was recorded: "
                f"{validation['errors'][0]['message']}"
            )
        if record.get("packet_id") != packet_id:
            raise ValueError("Claim record packet_id disagrees with its slot")
        if record.get("claim_sha256") != expected_claim_sha256:
            raise ValueError("Claim changed after reclaim evidence was recorded")
        with handle.directory(("locks", "reclaimed", run_id), create=True) as destination_fd:
            # linkat is the portable exclusive publication primitive here:
            # unlike rename it cannot overwrite an immutable archive slot.
            os.link(name, name, src_dir_fd=source_fd, dst_dir_fd=destination_fd,
                    follow_symlinks=False)
            os.fsync(destination_fd)
            os.unlink(name, dir_fd=source_fd)
            os.fsync(source_fd)


def complete_claim_at(handle, packet_id: str, intent_id: str, run_id: str) -> bool:
    """Archive a claim only after its exact intent durably finished."""
    validate_harness_id(run_id)
    name = _claim_name(packet_id)
    if not isinstance(intent_id, str) or not intent_id:
        raise ValueError("completed claim intent_id must be non-empty")
    archive_name = (
        f"{validate_harness_id(packet_id)}.{compute_sha256(intent_id.encode('utf-8'))[:32]}.lock.json")
    try:
        with handle.directory(("locks",)) as source_fd:
            try:
                raw = _read_regular_at(source_fd, name)
            except FileNotFoundError:
                return False
            record = _parse_claim(raw)
            validation = validate_claim(record)
            if not validation["valid"]:
                raise ValueError(
                    f"completed claim is invalid: {validation['errors'][0]['message']}")
            if record.get("packet_id") != packet_id or record.get("intent_id") != intent_id:
                raise ValueError("completed claim identity disagrees with terminal attempt intent")
            with handle.directory(("locks", "completed", run_id), create=True) as destination_fd:
                try:
                    os.link(name, archive_name, src_dir_fd=source_fd, dst_dir_fd=destination_fd,
                            follow_symlinks=False)
                except FileExistsError:
                    if _read_regular_at(destination_fd, archive_name) != raw:
                        raise ValueError("completed claim archive conflicts with prior evidence")
                os.fsync(destination_fd)
                os.unlink(name, dir_fd=source_fd)
                os.fsync(source_fd)
                return True
    except FileNotFoundError:
        return False


def create_claim(lock_path: str, record: Dict[str, Any]) -> None:
    """Create a claim record exclusively.

    Uses ``O_CREAT | O_EXCL | O_WRONLY`` with mode ``0o600``.  Raises
    ``FileExistsError`` if the slot is already taken.
    """
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    data = canonical_bytes(record)
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        remaining = data
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def read_claim(lock_path: str) -> Dict[str, Any]:
    """Read and parse a claim record.

    Raises on unparseable content; never returns a default.
    """
    with open(lock_path, "rb") as f:
        raw = f.read()
    return _parse_claim(raw)


def reclaim_lock(lock_path: str, run_id: str, classification: str) -> None:
    """Move a stale lock to ``locks/reclaimed/<run_id>/`` verbatim.

    Only ``STALE_PRIOR_BOOT`` and ``STALE_SAME_BOOT`` classifications are
    accepted.  The lock content is preserved unchanged.
    """
    if classification not in {"STALE_PRIOR_BOOT", "STALE_SAME_BOOT"}:
        raise ValueError(
            f"reclaim_lock called with non-reclaimable classification: {classification}"
        )

    record = read_claim(lock_path)
    packet_id = record.get("packet_id")
    if not packet_id:
        raise ValueError("Claim record missing packet_id")
    validate_harness_id(packet_id)

    state_root = os.path.dirname(os.path.dirname(lock_path))
    dst_dir = safe_state_path(
        state_root, "locks", "reclaimed", identifier=run_id
    )
    os.makedirs(dst_dir, exist_ok=True)
    dst = safe_state_path(
        dst_dir, identifier=packet_id, identifier_suffix=".lock.json"
    )
    if os.path.exists(dst):
        raise FileExistsError(f"Reclaimed lock destination already exists: {dst}")

    os.replace(lock_path, dst)


__all__ = [
    "create_claim", "create_claim_at", "read_claim", "read_claim_at",
    "list_worker_claim_ids", "reclaim_lock", "reclaim_lock_at", "classify_claim",
]
