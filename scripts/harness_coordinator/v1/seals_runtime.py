"""Idempotent terminal-seal completion for the harness coordinator v1.

Design section 3.5 step 13 ("create any missing terminal seals") had no
producer anywhere in the accepted O3 build -- which is exactly why
``classify_runtime.promote_dependencies`` could never fire and every
dependent packet reported ``promotion_stalled`` permanently. This module is
that producer, and nothing else: it derives a seal from durable state alone
and writes it exclusively.

Three properties, in the order they matter:

1. **Derived, never asserted.** A seal's binding fields come from the
   committing terminal journal event plus, for ``ACCEPTED``, the replay
   bundle that event itself references. No caller supplies a digest.
2. **Idempotent.** An existing seal whose binding matches is a byte-for-byte
   no-op; the original ``sealed_at`` is preserved rather than refreshed.
3. **Fail closed.** An existing seal whose binding disagrees is never
   overwritten and never reconciled -- it raises ``SealContradiction``, the
   same posture ``_fold_journal``'s own seal check takes for a
   state-disagreeing seal (design 2.6's run-halting condition).

``sealed_at`` is deliberately excluded from the binding comparison: it
records when this coordinator wrote the seal, not what the seal attests to.
Including it would make every resume look like a contradiction.
"""

import contextlib
import json
import os
import secrets
import stat
from typing import Any, Dict, List, Optional, Sequence, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.seal import validate_terminal_seal
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id

TERMINAL_STATES = ("ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED")

# Everything a seal attests to. ``sealed_at``/``seal_sha256`` are excluded:
# the first is when this write happened, the second is derived from the rest.
_BINDING_FIELDS = (
    "schema_version",
    "packet_id",
    "packet_sha256",
    "terminal_state",
    "sealing_event_seq",
    "sealing_event_sha256",
    "quarantine_reason",
    "human_required_reasons",
    "upstream_digests",
)


class SealContradiction(ValueError):
    """An existing seal disagrees with the seal durable state requires."""


class ArtifactConflict(ValueError):
    """An immutable artifact already exists with different bytes."""


def terminal_seal_path(state_root: str, packet_id: str) -> str:
    """Canonical seal location, identifier-validated and containment-checked.

    Used for reads and for reporting. Publication does not go through this
    pathname -- see ``publish_exclusive`` and ``terminal_seal_parts``.
    """
    return safe_state_path(
        state_root, "state", "terminal", identifier=packet_id, identifier_suffix=".seal.json"
    )


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte. Factored out so a partial-write failure is testable."""
    remaining = data
    while remaining:
        remaining = remaining[os.write(fd, remaining):]


def _remove_temp(dir_fd: int, name: str) -> None:
    """Best-effort removal of THIS call's own temporary file.

    Isolated so a cleanup failure can never be confused with a publication
    failure: once the final link succeeds the artifact is durably committed,
    and a leftover temp is untidy, not ambiguous.
    """
    try:
        os.unlink(name, dir_fd=dir_fd)
    except OSError:
        pass


def _validate_component(component: Any, position: int) -> str:
    """Every publication path component is a fixed literal or a validated id."""
    if not isinstance(component, str) or component in ("", ".", ".."):
        raise ValueError(f"unsafe publication component at {position}: {component!r}")
    if "/" in component or "\\" in component or "\0" in component:
        raise ValueError(f"publication component at {position} must be a single name: {component!r}")
    return component


def _open_child_dir(parent_fd: int, component: str) -> int:
    """openat one component, creating it, never following a symlink."""
    try:
        os.mkdir(component, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    return os.open(component, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                   dir_fd=parent_fd)


def _read_final(dir_fd: int, name: str) -> Optional[bytes]:
    """Read an already-published artifact through the pinned directory FD."""
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ArtifactConflict(f"published slot {name!r} is not a regular file")
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _publish_in(dir_fd: int, name: str, data: bytes) -> bool:
    existing = _read_final(dir_fd, name)
    if existing is not None:
        if existing != data:
            raise ArtifactConflict(f"a different immutable artifact already exists at {name!r}")
        return False

    # A collision-resistant per-call name, generated by this coordinator
    # process and never derived from packet input. It names a temporary file
    # only -- it never reaches durable state, a journal event, or any decision,
    # so it is outside the no-implicit-randomness rule that governs those.
    temporary = f".{name}.tmp.{secrets.token_hex(16)}"
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                 0o600, dir_fd=dir_fd)
    linked = False
    try:
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            linked = True
        except FileExistsError:
            linked = False
    finally:
        _remove_temp(dir_fd, temporary)
    os.fsync(dir_fd)
    if not linked:
        raced = _read_final(dir_fd, name)
        if raced is None or raced != data:
            raise ArtifactConflict(f"a different immutable artifact was published concurrently at {name!r}")
        return False
    return True


class StateRootMoved(Exception):
    """The lexical state-root path no longer resolves to the pinned directory."""


def _identity(info: os.stat_result) -> Tuple[int, int]:
    return (info.st_dev, info.st_ino)


def _open_absolute_nofollow(path: str) -> int:
    """Open an absolute directory path component-by-component from ``/``.

    Every component is opened with ``O_NOFOLLOW``, so a symlink anywhere in the
    chain -- not merely at the final component -- is refused. ``/`` itself
    cannot be a symlink and is the only pathname ever handed to the kernel.
    """
    if not os.path.isabs(path):
        raise ValueError(f"state root must be an absolute path: {path!r}")
    fd = os.open("/", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in path.split("/"):
            if component == "":
                continue
            if component in (".", ".."):
                raise ValueError(f"state root must be lexically canonical: {path!r}")
            child = os.open(component,
                            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except Exception:
        os.close(fd)
        raise


class StateRootHandle:
    """A pinned, identity-bound view of one state root.

    Every P5C artifact operation goes through this handle rather than a
    pathname. A pathname is re-resolved by the kernel on every call, so a
    rename plus a symlink can redirect a read, an unlink, a rename, or a
    publication to a file outside the state root between one call and the next.
    A retained directory FD cannot be redirected: it names an inode.

    ``verify_identity`` is the complement -- it re-resolves the lexical path
    through the same no-follow chain and confirms it still reaches the pinned
    ``(st_dev, st_ino)``. Operations stay correct without it; it is what lets a
    caller *notice* the root was swapped and halt.
    """

    __slots__ = ("_path", "_fd", "_identity", "_closed")

    def __init__(self, path: str, fd: int) -> None:
        self._path = path
        self._fd = fd
        self._identity = _identity(os.fstat(fd))
        self._closed = False

    @property
    def path(self) -> str:
        return self._path

    @property
    def fd(self) -> int:
        if self._closed:
            raise ValueError("state root handle is closed")
        return self._fd

    @property
    def identity(self) -> Tuple[int, int]:
        return self._identity

    def close(self) -> None:
        if not self._closed:
            os.close(self._fd)
            self._closed = True

    def __enter__(self) -> "StateRootHandle":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def verify_identity(self) -> None:
        """Confirm the lexical path still resolves to the pinned directory.

        A failure to re-resolve at all -- the path replaced by a symlink, or
        removed outright -- is the same finding as reaching a different inode,
        so both surface as ``StateRootMoved`` rather than as a raw OS error.
        A ``ValueError`` (a path that was never canonical) is a caller mistake
        and propagates unchanged.
        """
        try:
            probe = _open_absolute_nofollow(self._path)
        except OSError as exc:
            raise StateRootMoved(
                f"state root {self._path!r} can no longer be resolved: {exc}") from exc
        try:
            if _identity(os.fstat(probe)) != self._identity:
                raise StateRootMoved(
                    f"state root {self._path!r} no longer resolves to the pinned directory")
        finally:
            os.close(probe)

    @contextlib.contextmanager
    def directory(self, components: Sequence[str], create: bool = False):
        """Yield a leaf directory FD reached only through no-follow openat."""
        opened: List[int] = []
        parent = self.fd
        try:
            for position, component in enumerate(components):
                _validate_component(component, position)
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                child = os.open(component,
                                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                                dir_fd=parent)
                opened.append(child)
                parent = child
            yield parent
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def read(self, parts: Sequence[str]) -> Optional[bytes]:
        """Read a regular file relative to the pinned root, or None if absent.

        A missing parent directory is simply an absent artifact and returns
        None. A parent that exists but is a symlink, or is not a directory, is
        a redirection attempt and still raises -- ``ENOENT`` is the only
        absence; ``ELOOP``/``ENOTDIR`` are refusals.
        """
        directories, name = _split_parts(parts)
        try:
            with self.directory(directories) as leaf:
                return _read_final(leaf, name)
        except FileNotFoundError:
            return None

    def publish(self, parts: Sequence[str], data: bytes) -> bool:
        """Atomically publish immutable bytes relative to the pinned root."""
        directories, name = _split_parts(parts)
        with self.directory(directories, create=True) as leaf:
            return _publish_in(leaf, name, data)

    def unlink(self, parts: Sequence[str], predicate=None) -> bool:
        """Remove a file relative to the pinned root, optionally guarded.

        A missing parent or file returns False. A symlinked or non-directory
        parent still raises, so a swapped parent can never redirect the unlink
        to an outside file.
        """
        directories, name = _split_parts(parts)
        try:
            with self.directory(directories) as leaf:
                if predicate is not None:
                    current = _read_final(leaf, name)
                    if current is None or not predicate(current):
                        return False
                os.unlink(name, dir_fd=leaf)
                return True
        except FileNotFoundError:
            return False

    def rename(self, source_parts: Sequence[str], destination_parts: Sequence[str]) -> None:
        """Move a file between two pinned directories, never by pathname."""
        source_dirs, source_name = _split_parts(source_parts)
        destination_dirs, destination_name = _split_parts(destination_parts)
        with self.directory(source_dirs) as source_leaf:
            with self.directory(destination_dirs, create=True) as destination_leaf:
                os.rename(source_name, destination_name,
                          src_dir_fd=source_leaf, dst_dir_fd=destination_leaf)


def _split_parts(parts: Sequence[str]) -> Tuple[Tuple[str, ...], str]:
    components = tuple(parts)
    if not components:
        raise ValueError("an artifact operation requires at least a file name")
    for position, component in enumerate(components):
        _validate_component(component, position)
    return components[:-1], components[-1]


def open_state_root(state_root: str) -> StateRootHandle:
    """Pin one state root by identity, refusing any symlinked component."""
    fd = _open_absolute_nofollow(state_root)
    try:
        return StateRootHandle(state_root, fd)
    except Exception:
        os.close(fd)
        raise


def publish_exclusive(state_root: str, parts: Sequence[str], data: bytes) -> bool:
    """Publish immutable bytes into a pinned directory, atomically.

    A convenience wrapper that scopes one ``StateRootHandle`` to a single
    publication and delegates. It carries no publication logic of its own on
    purpose: a second implementation here was reachable, exported, and subtly
    weaker than the handle -- it opened the state root by pathname, so
    ``O_NOFOLLOW`` constrained only the final component and a symlinked
    ancestor was silently followed. Callers already holding a handle should use
    ``handle.publish`` so the whole iteration shares one pinned identity.
    """
    with open_state_root(state_root) as handle:
        return handle.publish(parts, data)


def seal_binding(seal: Dict[str, Any]) -> Tuple[Any, ...]:
    """Everything a seal attests to, in a comparable form."""
    return tuple(json.dumps(seal.get(field), sort_keys=True) for field in _BINDING_FIELDS)


def authenticate_seal(raw: bytes, expected_packet_id: str, where: str) -> Dict[str, Any]:
    """Parse a seal and prove it is a well-formed, self-consistent seal for one packet.

    Binding equality alone is not authenticity: a seal whose binding fields
    happen to match but whose self-hash is wrong, whose encoding is
    non-canonical, or which carries extra fields is a tampered artifact, not
    an idempotent rewrite. ``validate_terminal_seal`` owns the schema and
    self-hash decision; the canonical-bytes comparison additionally pins the
    exact serialization, so no two byte sequences can present as one seal.
    """
    try:
        seal = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealContradiction(f"seal at {where} is not valid JSON: {exc}") from exc
    if not isinstance(seal, dict):
        raise SealContradiction(f"seal at {where} is not an object")
    result = validate_terminal_seal(seal)
    if not result["valid"]:
        raise SealContradiction(
            f"seal at {where} fails the terminal-seal contract: {result['errors'][0]['message']}"
        )
    if raw != canonical_bytes(seal):
        raise SealContradiction(f"seal at {where} is not canonically encoded")
    if seal.get("packet_id") != expected_packet_id:
        raise SealContradiction(
            f"seal at {where} names packet {seal.get('packet_id')!r}, expected {expected_packet_id!r}"
        )
    return seal


def committing_terminal_event(
    journal_events: List[Dict[str, Any]], packet_id: str, terminal_state: str
) -> Dict[str, Any]:
    """Return the event that transitioned ``packet_id`` into its terminal state.

    Terminal states cannot be left (``_fold_journal`` enforces terminal
    safety), so the last event whose ``to_state`` is the terminal state is
    unambiguously the committing one.
    """
    committing = None
    for event in journal_events:
        if event.get("packet_id") == packet_id and event.get("to_state") == terminal_state:
            committing = event
    if committing is None:
        raise SealContradiction(
            f"packet {packet_id} folds to {terminal_state} but no committing event declares it"
        )
    return committing


def replay_bundle_parts(packet_id: str, attempt: int) -> Tuple[str, str, str, str]:
    """Pinned, validated components for one attempt's replay bundle."""
    return ("results", validate_harness_id(packet_id), str(int(attempt)), "replay-bundle.json")


def _bundle_from_event(handle: "StateRootHandle", event: Dict[str, Any], packet_id: str) -> Dict[str, Any]:
    """Load and re-verify the replay bundle the committing event references."""
    artifacts = (event.get("payload") or {}).get("artifacts") or []
    entries = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == "replay_bundle"]
    if len(entries) != 1:
        raise SealContradiction(
            f"ACCEPTED packet {packet_id}'s committing event does not reference exactly one replay bundle"
        )
    entry = entries[0]
    attempt = ((event.get("payload") or {}).get("attempt") or {}).get("attempt")
    if not isinstance(attempt, int):
        raise SealContradiction(f"committing event for {packet_id} does not name its attempt")
    parts = replay_bundle_parts(packet_id, attempt)
    # The recorded path is compared to the canonical one rather than resolved:
    # a journal-supplied path is never the authority for where to read.
    if entry.get("path") != "/".join(parts):
        raise SealContradiction(
            f"replay bundle for {packet_id} is recorded outside its canonical location")
    try:
        raw = handle.read(parts)
    except OSError as exc:
        raise SealContradiction(
            f"replay bundle for {packet_id} is unreadable at its recorded path: {exc}"
        ) from exc
    if raw is None:
        raise SealContradiction(f"replay bundle for {packet_id} is missing")
    if compute_sha256(raw) != entry.get("sha256") or len(raw) != entry.get("byte_length"):
        raise SealContradiction(f"replay bundle for {packet_id} does not match its journaled digest")
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealContradiction(f"replay bundle for {packet_id} is not valid JSON: {exc}") from exc
    if not isinstance(bundle, dict):
        raise SealContradiction(f"replay bundle for {packet_id} is not an object")
    return bundle


def _upstream_digests(
    handle: "StateRootHandle", journal_events: List[Dict[str, Any]], packet_id: str,
    packet_state: Dict[str, Any], committing: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """ACCEPTED seals bind the exact packet/result/verdict/bundle digests.

    All four come from the single already-validated replay bundle the
    committing VERDICT_RECORDED event references, so they are internally
    consistent by construction rather than assembled from four independent
    reads that could disagree.
    """
    if packet_state.get("state") != "ACCEPTED":
        return None
    bundle = _bundle_from_event(handle, committing, packet_id)
    packet = bundle.get("packet") or {}
    worker_result = bundle.get("worker_result") or {}
    verdict = bundle.get("opus_verdict") or {}
    digests = {
        "packet_sha256": packet.get("packet_sha256"),
        "result_sha256": worker_result.get("result_sha256"),
        "verdict_sha256": verdict.get("verdict_sha256"),
        "bundle_sha256": bundle.get("bundle_sha256"),
    }
    if any(not isinstance(value, str) for value in digests.values()):
        raise SealContradiction(f"replay bundle for {packet_id} is missing an upstream digest")
    if digests["packet_sha256"] != packet_state.get("packet_sha256"):
        raise SealContradiction(
            f"replay bundle for {packet_id} attests a different packet than the fold"
        )
    return digests


def build_terminal_seal(
    handle: "StateRootHandle", journal_events: List[Dict[str, Any]], packet_id: str,
    packet_state: Dict[str, Any], now: str,
) -> Dict[str, Any]:
    """Derive the seal durable state requires for one terminal packet."""
    terminal_state = packet_state.get("state")
    if terminal_state not in TERMINAL_STATES:
        raise SealContradiction(f"packet {packet_id} is not terminal ({terminal_state})")
    committing = committing_terminal_event(journal_events, packet_id, terminal_state)
    seal = {
        "schema_version": 1,
        "packet_id": packet_id,
        "packet_sha256": packet_state.get("packet_sha256"),
        "terminal_state": terminal_state,
        "sealing_event_seq": committing["seq"],
        "sealing_event_sha256": committing["event_sha256"],
        "sealed_at": now,
        "quarantine_reason": packet_state.get("quarantine_reason") if terminal_state == "QUARANTINED" else None,
        "human_required_reasons": list(packet_state.get("human_required_reasons") or []) if terminal_state == "HUMAN_REQUIRED" else [],
        "upstream_digests": _upstream_digests(handle, journal_events, packet_id, packet_state, committing),
        "seal_sha256": "",
    }
    seal["seal_sha256"] = compute_sha256(canonical_bytes(seal, omit={"seal_sha256"}))
    result = validate_terminal_seal(seal)
    if not result["valid"]:
        raise SealContradiction(
            f"derived seal for {packet_id} fails the terminal-seal contract: {result['errors'][0]['message']}"
        )
    return seal


def _existing_seal(handle: "StateRootHandle", expected_packet_id: str) -> Optional[Dict[str, Any]]:
    """Return an existing seal only after authenticating it, else None."""
    parts = terminal_seal_parts(expected_packet_id)
    try:
        raw = handle.read(parts)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SealContradiction(f"existing seal for {expected_packet_id} is unreadable: {exc}") from exc
    if raw is None:
        return None
    return authenticate_seal(raw, expected_packet_id, "/".join(parts))


def terminal_seal_parts(packet_id: str) -> Tuple[str, str, str]:
    """Pinned, validated components for one packet's terminal seal."""
    return ("state", "terminal", f"{validate_harness_id(packet_id)}.seal.json")


def _write_seal_exclusive(handle: "StateRootHandle", seal: Dict[str, Any]) -> bool:
    """Publish the seal atomically; return False if an identical one raced in."""
    try:
        return handle.publish(terminal_seal_parts(seal["packet_id"]), canonical_bytes(seal))
    except ArtifactConflict:
        raced = _existing_seal(handle, seal["packet_id"])
        if raced is None or seal_binding(raced) != seal_binding(seal):
            raise SealContradiction(
                f"a conflicting seal was created concurrently for {seal['packet_id']}")
        return False


def complete_terminal_seals(
    state_root: str, journal_events: List[Dict[str, Any]],
    folded: Dict[str, Dict[str, Any]], now: str,
    handle: Optional["StateRootHandle"] = None,
) -> List[str]:
    """Write every missing terminal seal; return the packet ids newly sealed.

    Runs before dependency promotion, never after: ``promote_dependencies``
    reads each dependency's seal to build its auditable ``satisfied_by``
    citation and defers quietly when one is absent, so an unsealed ACCEPTED
    dependency silently stalls every dependent packet.

    Every terminal packet is checked on every pass, not only unsealed ones --
    an existing seal that agrees costs one read, and an existing seal that
    disagrees is exactly the tampering this fails closed on. Relying on the
    fold's ``terminal_seal_sha256`` to decide what to check would skip
    precisely the forged-but-state-consistent seal worth catching.

    ``handle`` binds every read and publication to one pinned state-root
    identity. A caller inside a coordinator iteration passes its own; a direct
    caller gets a scoped one for the duration of this call.
    """
    if handle is None:
        with open_state_root(state_root) as scoped:
            return complete_terminal_seals(state_root, journal_events, folded, now, handle=scoped)

    sealed: List[str] = []
    for packet_id in sorted(folded):
        packet_state = folded[packet_id]
        if packet_state.get("state") not in TERMINAL_STATES:
            continue
        seal = build_terminal_seal(handle, journal_events, packet_id, packet_state, now)
        existing = _existing_seal(handle, packet_id)
        if existing is not None:
            if seal_binding(existing) != seal_binding(seal):
                raise SealContradiction(
                    f"existing terminal seal for {packet_id} contradicts durable state; refusing to overwrite"
                )
            continue
        if _write_seal_exclusive(handle, seal):
            sealed.append(packet_id)
    return sealed


__all__ = [
    "ArtifactConflict",
    "SealContradiction",
    "authenticate_seal",
    "StateRootHandle",
    "StateRootMoved",
    "open_state_root",
    "publish_exclusive",
    "replay_bundle_parts",
    "terminal_seal_parts",
    "build_terminal_seal",
    "committing_terminal_event",
    "complete_terminal_seals",
    "seal_binding",
    "terminal_seal_path",
]
