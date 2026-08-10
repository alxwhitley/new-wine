"""Preflight-first, restart-safe packet enrollment for coordinator v1."""

import os
import errno
from typing import Any, Dict, Iterable, List

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id
from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal, _make_event
from harness_coordinator.v1.store import JournalHeadMoved, atomic_replace, append_journal, read_journal


class PacketPreflightError(ValueError):
    def __init__(self, errors: List[Dict[str, Any]]) -> None:
        super().__init__("packet enrollment preflight failed")
        self.errors = errors


class ConflictingEnrollment(ValueError):
    pass


def preflight_packets(packets: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate and canonicalize a complete batch without filesystem writes."""
    prepared: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}
    for index, packet in enumerate(packets):
        result = validate_packet(packet, dependency_states=None)
        if not result["valid"]:
            errors.extend({"packet_index": index, **error} for error in result["errors"])
            continue
        packet_id = packet["packet_id"]
        digest = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
        if digest != packet["packet_sha256"]:
            errors.append({"packet_index": index, "code": "EVIDENCE_HASH_MISMATCH", "path": "/packet_sha256", "message": "packet digest changed during preflight"})
            continue
        prior = seen.get(packet_id)
        if prior is not None and prior != digest:
            errors.append({"packet_index": index, "code": "DUPLICATE_ID", "path": "/packet_id", "message": f"conflicting packet_id {packet_id!r} in enrollment batch"})
            continue
        if prior is None:
            prepared.append({"packet": packet, "packet_id": packet_id, "packet_sha256": digest})
            seen[packet_id] = digest
    if errors:
        raise PacketPreflightError(errors)
    return prepared


def enroll_packets(
    state_root: str,
    state_root_id: str,
    coordinator_id: str,
    run_id: str,
    now: str,
    packets: Iterable[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Enroll a preflighted batch, safely resumable after a valid prefix."""
    validate_harness_id(coordinator_id, "/coordinator_id")
    validate_harness_id(run_id, "/run_id")
    prepared = preflight_packets(packets)
    os.makedirs(os.path.join(state_root, "locks"), exist_ok=True)
    journal_path = os.path.join(state_root, "journal.ndjson")
    journal_lock = os.path.join(state_root, "locks", "journal.wlock")
    events, torn = read_journal(journal_path, state_root_id=state_root_id)
    if torn is not None:
        raise PacketPreflightError([{"code": "JOURNAL_TAIL_TORN", "path": "/journal", "message": "enrollment refuses a torn journal tail"}])
    folded, _ = _fold_journal(state_root, events)

    # Durable-state and target-artifact checks are part of the same whole-
    # batch preflight.  No packet, journal, projection, or rejection write is
    # allowed until every later item has also passed these checks.
    decisions: List[Dict[str, Any]] = []
    rejections: List[Dict[str, Any]] = []
    for item in prepared:
        packet_id = item["packet_id"]
        digest = item["packet_sha256"]
        existing = folded.get(packet_id)
        if existing is not None and existing.get("packet_sha256") != digest:
            rejections.append({"packet_id": packet_id, "reason": "enrolled_digest_conflict", "existing_packet_sha256": existing.get("packet_sha256"), "offered_packet_sha256": digest})
            continue
        root = os.path.realpath(state_root)
        lexical_packet_path = os.path.join(root, "packets", f"{packet_id}.json")
        if os.path.islink(lexical_packet_path):
            rejections.append({"packet_id": packet_id, "reason": "artifact_symlink_conflict", "existing_packet_sha256": existing.get("packet_sha256") if existing else None, "offered_packet_sha256": digest})
            continue
        try:
            packet_path = safe_state_path(state_root, "packets", identifier=packet_id, identifier_suffix=".json")
        except ValueError:
            rejections.append({"packet_id": packet_id, "reason": "artifact_path_escape_conflict", "existing_packet_sha256": existing.get("packet_sha256") if existing else None, "offered_packet_sha256": digest})
            continue
        if packet_path != lexical_packet_path:
            rejections.append({"packet_id": packet_id, "reason": "artifact_path_alias_conflict", "existing_packet_sha256": existing.get("packet_sha256") if existing else None, "offered_packet_sha256": digest})
            continue
        if existing is not None and not os.path.exists(lexical_packet_path):
            rejections.append({"packet_id": packet_id, "reason": "enrolled_artifact_missing", "existing_packet_sha256": existing.get("packet_sha256"), "offered_packet_sha256": digest})
            continue
        if os.path.exists(lexical_packet_path):
            if _read_bytes_no_follow(lexical_packet_path) != canonical_bytes(item["packet"]):
                rejections.append({"packet_id": packet_id, "reason": "artifact_bytes_conflict", "existing_packet_sha256": existing.get("packet_sha256") if existing else None, "offered_packet_sha256": digest})
                continue
        decisions.append({**item, "packet_path": lexical_packet_path, "existing": existing})
    if rejections:
        for rejection in rejections:
            _preserve_rejection(state_root, coordinator_id, rejection)
        raise ConflictingEnrollment("packet enrollment rejected after whole-batch durable preflight")

    enrolled: List[str] = []
    skipped: List[str] = []
    for item in decisions:
        packet = item["packet"]
        packet_id = item["packet_id"]
        digest = item["packet_sha256"]
        existing = folded.get(packet_id)
        if existing is not None:
            if existing.get("packet_sha256") == digest:
                skipped.append(packet_id)
                continue
            raise ConflictingEnrollment(f"packet_id {packet_id!r} is already enrolled with a different digest")

        packet_path = item["packet_path"]
        os.makedirs(os.path.dirname(packet_path), exist_ok=True)
        try:
            _preserve_packet(packet_path, packet)
        except ConflictingEnrollment:
            existing_bytes_sha256 = None
            try:
                existing_bytes_sha256 = compute_sha256(_read_bytes_no_follow(packet_path))
            except OSError as exc:
                if exc.errno != errno.ELOOP:
                    raise
            _preserve_rejection(state_root, coordinator_id, {
                "packet_id": packet_id,
                "reason": "artifact_race_conflict",
                "existing_packet_sha256": None,
                "existing_bytes_sha256": existing_bytes_sha256,
                "offered_packet_sha256": digest,
            })
            raise
        prev = events[-1] if events else None
        seq = prev["seq"] + 1 if prev else 1
        payload = {
            "packet": {
                "packet_sha256": digest, "packet_path": os.path.relpath(packet_path, os.path.realpath(state_root)),
                "lane": packet["lane"], "dependency_ids": packet["dependency_ids"],
                "sonnet_reassignment_allowed": packet["sonnet_reassignment_allowed"],
                "retry_limit": packet["budgets"]["retry_limit"], "enqueue_seq": seq,
            },
            "attempt": None, "artifacts": [], "classification": None,
            "transition_detail": None, "recovery": None, "run": None, "report": None,
        }
        cas_moves = 0
        while True:
            event = _make_event(seq, "PACKET_ENROLLED", coordinator_id, run_id, state_root_id, prev, now,
                                packet_id=packet_id, intent_id=f"enroll-{packet_id}-{seq}",
                                to_state="BLOCKED" if packet["dependency_ids"] else "READY",
                                cause="enrollment", payload={**payload, "packet": {**payload["packet"], "enqueue_seq": seq}})
            try:
                append_journal(journal_path, event, journal_lock, expected_head=prev)
                break
            except JournalHeadMoved:
                cas_moves += 1
                if cas_moves >= 8:
                    rejection = {"packet_id": packet_id, "reason": "journal_head_retry_exhausted", "existing_packet_sha256": None, "offered_packet_sha256": digest}
                    _preserve_rejection(state_root, coordinator_id, rejection)
                    raise ConflictingEnrollment("journal head kept moving during bounded enrollment retry")
                events, torn = read_journal(journal_path, state_root_id=state_root_id)
                if torn is not None:
                    raise PacketPreflightError([{"code": "JOURNAL_TAIL_TORN", "path": "/journal", "message": "enrollment refuses a torn journal tail"}])
                folded, _ = _fold_journal(state_root, events)
                raced = folded.get(packet_id)
                if raced is not None:
                    if raced.get("packet_sha256") == digest:
                        skipped.append(packet_id)
                        event = None
                        break
                    rejection = {"packet_id": packet_id, "reason": "concurrent_digest_conflict", "existing_packet_sha256": raced.get("packet_sha256"), "offered_packet_sha256": digest}
                    _preserve_rejection(state_root, coordinator_id, rejection)
                    raise ConflictingEnrollment(f"packet_id {packet_id!r} was concurrently enrolled with a different digest")
                prev = events[-1] if events else None
                seq = prev["seq"] + 1 if prev else 1
        if event is None:
            continue
        events.append(event)
        folded, _ = _fold_journal(state_root, events)
        queue = _build_derived_queue(folded, state_root_id, event)
        atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(queue), coordinator_id, f"{run_id}-{seq}")
        enrolled.append(packet_id)
    return {"enrolled": enrolled, "skipped": skipped}


def _preserve_packet(path: str, packet: Dict[str, Any]) -> None:
    data = canonical_bytes(packet)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            existing = _read_bytes_no_follow(path)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ConflictingEnrollment(f"packet artifact is a symlink: {path}") from exc
            raise
        if existing != data:
            raise ConflictingEnrollment(f"packet artifact already exists with different bytes: {path}")
        return
    try:
        remaining = data
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_bytes_no_follow(path: str) -> bytes:
    """Read an existing artifact without ever following a terminal symlink."""
    if not hasattr(os, "O_NOFOLLOW") and os.path.islink(path):
        raise OSError(errno.ELOOP, "symbolic link refused", path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _preserve_rejection(state_root: str, coordinator_id: str, evidence: Dict[str, Any]) -> None:
    data = canonical_bytes(evidence)
    evidence_sha = compute_sha256(data)
    path = safe_state_path(state_root, "rejected", "enrollment", identifier=evidence["packet_id"], identifier_suffix=f".{evidence_sha}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            existing = _read_bytes_no_follow(path)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ConflictingEnrollment("rejection evidence collision is a symlink") from exc
            raise
        if existing != data:
            raise ConflictingEnrollment("rejection evidence collision")
        return
    try:
        remaining = data
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


__all__ = ["ConflictingEnrollment", "PacketPreflightError", "enroll_packets", "preflight_packets"]
