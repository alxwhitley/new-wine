"""Durable, atomic filesystem primitives for the harness coordinator v1.

All paths are absolute (rooted at the caller-supplied ``state_root``).
"""

import fcntl
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import validate_journal_event


class JournalChainBroken(Exception):
    """A non-final journal line failed validation; refuse to start."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class JournalHeadMoved(Exception):
    """The journal head no longer matches the in-memory expected head."""

    def __init__(self, actual_head: Optional[Dict[str, Any]]) -> None:
        super().__init__("Journal head moved")
        self.actual_head = actual_head


def atomic_replace(path: str, data: bytes, coordinator_id: str, nonce: str) -> None:
    """Atomically replace ``path`` with ``data``.

    Implements design section 3.1's exact 7-step sequence.  The temporary
    file is created in the same directory as ``path`` so the final rename
    cannot cross filesystems.
    """
    directory = os.path.dirname(path)
    tmp = f"{path}.tmp.{coordinator_id}.{os.getpid()}.{nonce}"
    fd = -1
    created = False
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        remaining = data
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(tmp, path)
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except Exception:
        if fd != -1:
            try:
                os.close(fd)
            except Exception:
                pass
        # Only clean up a tmp file THIS call actually created (defect 10:
        # an EEXIST from another writer's in-flight tmp file must never be
        # deleted by the call that failed to create it).
        if created:
            try:
                os.unlink(tmp)
            except Exception:
                pass
        raise


def append_journal(
    journal_path: str,
    event: Dict[str, Any],
    lock_path: str,
    expected_head: Optional[Dict[str, Any]],
) -> None:
    """Append ``event`` to ``journal_path`` under an exclusive flock.

    Uses ``fcntl.flock`` (fd-scoped, released by the kernel on process
    death), not ``fcntl.lockf``.  Compares the journal's last line against
    ``expected_head`` and raises ``JournalHeadMoved`` on mismatch so the
    caller can re-derive and retry.
    """
    wfd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(wfd, fcntl.LOCK_EX)
        try:
            actual_head = _read_last_event(journal_path)
            if actual_head != expected_head:
                raise JournalHeadMoved(actual_head)

            if expected_head is None:
                if event.get("seq") != 1:
                    raise JournalHeadMoved(None)
                if event.get("prev_event_sha256") != ("0" * 64):
                    raise JournalHeadMoved(None)
            else:
                if event.get("seq") != expected_head.get("seq", 0) + 1:
                    raise JournalHeadMoved(actual_head)
                if event.get("prev_event_sha256") != expected_head.get("event_sha256"):
                    raise JournalHeadMoved(actual_head)

            line = canonical_bytes(event) + b"\n"
            fd = os.open(journal_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            fcntl.flock(wfd, fcntl.LOCK_UN)
    finally:
        os.close(wfd)


def _read_last_event(journal_path: str) -> Optional[Dict[str, Any]]:
    """Return the last parsed event in ``journal_path``, or None if empty.

    This is used only for the compare-and-swap inside ``append_journal``.
    The journal's full chain is validated separately by ``read_journal``.
    """
    if not os.path.exists(journal_path):
        return None
    with open(journal_path, "rb") as f:
        raw = f.read()
    if not raw:
        return None
    lines = raw.splitlines(keepends=True)
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return None
    return None


def read_journal(
    journal_path: str, state_root_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[bytes]]:
    """Read and validate ``journal_path``.

    Returns ``(valid_events, torn_tail)``.  A non-final line that fails
    validation raises ``JournalChainBroken``.  Only the final non-empty
    line may fail, in which case the raw trailing bytes are returned as
    ``torn_tail`` for quarantine and truncation by the caller.  Position in
    the file, not the shape of the damage, is the sole discriminator: a
    torn/corrupted FINAL line is recoverable even when no valid event
    precedes it (design 3.3 -- an empty valid prefix is still a valid
    prefix).

    When ``state_root_id`` is supplied, every event's own ``state_root_id``
    is cross-checked against it. Unlike every other per-event validation
    failure, a ``state_root_id`` mismatch is NEVER torn-tail-eligible --
    it always raises ``JournalChainBroken``, even on the final/only line.
    Torn-tail recovery is a destructive repair (quarantine + truncate) of
    damage THIS state root is entitled to repair; a foreign
    ``state_root_id`` means the file isn't this state root's journal at
    all, which is a jurisdiction question, not a damage-shape one -- so
    position-based leniency does not apply to it.
    """
    if not os.path.exists(journal_path):
        return [], None
    with open(journal_path, "rb") as f:
        raw = f.read()
    if not raw:
        return [], None

    lines = raw.splitlines(keepends=True)
    last_nonempty_idx = None
    for i, line in enumerate(lines):
        if line.strip():
            last_nonempty_idx = i

    valid_events: List[Dict[str, Any]] = []
    prev_event: Optional[Dict[str, Any]] = None
    valid_prefix_byte_length = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            valid_prefix_byte_length += len(line)
            continue

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            # Defect 6: position (only the final line may be torn), not
            # whether a valid prefix already exists, is the discriminator.
            if i == last_nonempty_idx:
                return valid_events, raw[valid_prefix_byte_length:]
            raise JournalChainBroken(f"JSON decode error at line {i + 1}: {exc}")

        result = validate_journal_event(parsed, prev_event=prev_event, state_root_id=state_root_id)
        if not result["valid"]:
            # A foreign state_root_id is not a corrupted-write shape (the
            # position discriminator design 3.3 describes) -- it means
            # this journal belongs to a different state root entirely.
            # Design 3.5 step 2 treats state_root_id mismatch as always
            # fail-closed, independent of position; never torn-tail-eligible.
            is_foreign_state_root = any(
                e.get("code") == "EVIDENCE_HASH_MISMATCH" and e.get("path") == "/state_root_id"
                for e in result["errors"]
            )
            if i == last_nonempty_idx and not is_foreign_state_root:
                return valid_events, raw[valid_prefix_byte_length:]
            raise JournalChainBroken(
                f"Invalid event at line {i + 1}: {result['errors'][0]['message']}"
            )

        valid_events.append(parsed)
        prev_event = parsed
        valid_prefix_byte_length += len(line)

    return valid_events, None


def sweep_orphans(state_root: str, run_id: str) -> List[str]:
    """Move every ``*.tmp.*`` file under ``state_root`` to ``sweep/<run_id>/``.

    Preserves relative structure and never deletes.  Returns the list of
    moved relative paths.
    """
    import fnmatch

    sweep_dir = os.path.join(state_root, "sweep", run_id)
    os.makedirs(sweep_dir, exist_ok=True)
    moved: List[str] = []
    for root, _dirs, files in os.walk(state_root):
        if root.startswith(os.path.join(state_root, "sweep")):
            continue
        for name in files:
            if fnmatch.fnmatch(name, "*.tmp.*"):
                src = os.path.join(root, name)
                rel = os.path.relpath(src, state_root)
                dst = os.path.join(sweep_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                moved.append(rel)
    return moved
