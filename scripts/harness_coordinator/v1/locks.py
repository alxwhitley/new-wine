"""Claim-record I/O and reclaim for the harness coordinator v1."""

import json
import os
from typing import Any, Dict

from harness_contracts.v1.canonical import canonical_bytes
from harness_contracts.v1.claim import classify_claim
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id


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
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Claim record root is not an object")
    return parsed


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


__all__ = ["create_claim", "read_claim", "reclaim_lock", "classify_claim"]
