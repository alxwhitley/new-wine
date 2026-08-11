"""Coordinator-owned Git worktree identity evidence for O4."""

import hashlib
import json
import os
import stat
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import normalize_repo_relative_path


class WorkspaceEvidenceError(Exception):
    """Stable preflight failure that never exposes Git stderr."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run_git(cwd: str, argv: List[str], timeout_seconds: int = 10) -> bytes:
    """Run Git without a shell or inherited configuration/environment."""
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", *argv],
        cwd=cwd,
        shell=False,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        env=environment,
    ).stdout


def _canonical_directory(path: str) -> str:
    endpoint = _separator_trimmed_endpoint(path)
    try:
        mode = os.lstat(endpoint).st_mode
    except OSError:
        raise WorkspaceEvidenceError("WORKTREE_IDENTITY_PATH", "Path is unavailable: %s" % path)
    if stat.S_ISLNK(mode):
        raise WorkspaceEvidenceError("WORKTREE_IDENTITY_SYMLINK", "Path is a symlink: %s" % path)
    canonical = os.path.realpath(path)
    if not os.path.isdir(canonical):
        raise WorkspaceEvidenceError("WORKTREE_IDENTITY_PATH", "Path is not a directory: %s" % canonical)
    return canonical


def _separator_trimmed_endpoint(path: str) -> str:
    """Return the actual endpoint for lstat without following a final symlink."""
    if path == os.path.sep:
        return path
    trimmed = path.rstrip(os.path.sep)
    if trimmed:
        return trimmed
    return os.path.sep if path else path


def _git_common_dir(worktree_path: str) -> str:
    try:
        raw = _run_git(worktree_path, ["rev-parse", "--git-common-dir"])
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_COMMON_DIR", "Could not resolve Git common directory"
        )
    common_dir = raw.decode("utf-8", "surrogateescape").strip()
    if not os.path.isabs(common_dir):
        common_dir = os.path.join(worktree_path, common_dir)
    return os.path.realpath(common_dir)


def discover_repo_root(worktree_path: str) -> str:
    """Return a worktree's Git top level, refusing unverifiable worktrees."""
    try:
        root = _run_git(worktree_path, ["rev-parse", "--show-toplevel"])
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_REPOSITORY", "Could not resolve the packet worktree Git repository"
        )
    return _canonical_directory(root.decode("utf-8", "surrogateescape").strip())


def _parse_worktree_records(raw: bytes) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for encoded_record in raw.split(b"\0\0"):
        if not encoded_record:
            continue
        record: Dict[str, str] = {}
        for encoded_field in encoded_record.split(b"\0"):
            if not encoded_field:
                continue
            field = encoded_field.decode("utf-8", "surrogateescape")
            key, separator, value = field.partition(" ")
            if separator:
                record[key] = value
            else:
                record[key] = ""
        if record:
            records.append(record)
    return records


def inspect_worktree(
    repo_root: str,
    worktree_path: str,
    expected_branch: str,
    expected_revision: str,
) -> Dict[str, Any]:
    """Return pinned identity evidence for one registered, non-detached worktree."""
    canonical_repo_root = _canonical_directory(repo_root)
    canonical_worktree = _canonical_directory(worktree_path)
    try:
        records = _parse_worktree_records(
            _run_git(canonical_repo_root, ["worktree", "list", "--porcelain", "-z"])
        )
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_REGISTRATION", "Could not read registered worktrees"
        )
    matching = [
        record
        for record in records
        if "worktree" in record and os.path.realpath(record["worktree"]) == canonical_worktree
    ]
    if len(matching) != 1:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_REGISTRATION",
            "Expected exactly one registration for %s" % canonical_worktree,
        )
    record = matching[0]
    canonical_common_dir = _git_common_dir(canonical_worktree)
    if _git_common_dir(canonical_repo_root) != canonical_common_dir:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_COMMON_DIR", "Repository and worktree common directories differ"
        )
    branch = record.get("branch")
    if not branch:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_DETACHED", "Worktree is detached: %s" % canonical_worktree
        )
    expected_ref = "refs/heads/%s" % expected_branch
    if branch != expected_ref:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_BRANCH",
            "Expected branch %s, got %s" % (expected_ref, branch),
        )
    head = record.get("HEAD")
    if head != expected_revision:
        raise WorkspaceEvidenceError(
            "WORKTREE_IDENTITY_REVISION",
            "Expected revision %s, got %s" % (expected_revision, head),
        )
    return {
        "schema_version": 1,
        "repo_root": canonical_repo_root,
        "worktree_path": canonical_worktree,
        "common_dir": canonical_common_dir,
        "branch": branch,
        "head": head,
    }


def _snapshot_git(worktree_path: str, argv: List[str]) -> bytes:
    try:
        return _run_git(worktree_path, argv)
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_GIT", "Could not read worktree state")


def _normalized_status_path(raw_path: bytes) -> str:
    path = raw_path.decode("utf-8", "surrogateescape")
    normalized = normalize_repo_relative_path(path)
    if normalized is None or normalized == "":
        raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_PATH", "Invalid repository-relative path")
    return normalized


def _parse_index(raw: bytes) -> Dict[str, Tuple[str, str]]:
    index: Dict[str, Tuple[str, str]] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, separator, raw_path = entry.partition(b"\t")
        if not separator:
            continue
        fields = metadata.split(b" ")
        if len(fields) != 3:
            continue
        index[_normalized_status_path(raw_path)] = (
            fields[0].decode("ascii"), fields[1].decode("ascii"),
        )
    return index


def _parse_status(raw: bytes) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    records = raw.split(b"\0")
    position = 0
    while position < len(records):
        record = records[position]
        position += 1
        if not record:
            continue
        if record.startswith(b"1 "):
            fields = record.split(b" ", 8)
            if len(fields) != 9:
                raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_FORMAT", "Malformed tracked status")
            path = _normalized_status_path(fields[8])
            xy = fields[1].decode("ascii")
            status[path] = _status_state(_status_character(xy, 0), _status_character(xy, 1), False)
        elif record.startswith(b"2 "):
            fields = record.split(b" ", 9)
            if len(fields) != 10:
                raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_FORMAT", "Malformed rename status")
            path = _normalized_status_path(fields[9])
            xy = fields[1].decode("ascii")
            index_status = _status_character(xy, 0)
            status[path] = _status_state(index_status, _status_character(xy, 1), False)
            if position >= len(records) or not records[position]:
                raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_FORMAT", "Rename source path is missing")
            source_path = _normalized_status_path(records[position])
            position += 1
            if index_status == "R":
                status[source_path] = _status_state(
                    "D", None, False, fields[6].decode("ascii")
                )
        elif record.startswith(b"u "):
            fields = record.split(b" ", 10)
            if len(fields) != 11:
                raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_FORMAT", "Malformed unmerged status")
            path = _normalized_status_path(fields[10])
            xy = fields[1].decode("ascii")
            status[path] = _status_state(_status_character(xy, 0), _status_character(xy, 1), False)
        elif record.startswith(b"? "):
            status[_normalized_status_path(record[2:])] = _status_state(None, None, True)
        else:
            raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_FORMAT", "Unrecognized Git status record")
    return status


def _status_state(
    index_status: Optional[str],
    worktree_status: Optional[str],
    untracked: bool,
    object_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "index_status": index_status,
        "worktree_status": worktree_status,
        "untracked": untracked,
        "object_id": object_id,
    }


def _status_character(xy: str, position: int) -> Optional[str]:
    if len(xy) <= position or xy[position] == ".":
        return None
    return xy[position]


def _lstat(path: str) -> Optional[os.stat_result]:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _content_sha256(path: str, metadata: os.stat_result) -> Optional[str]:
    if not stat.S_ISREG(metadata.st_mode):
        return None
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_HASH", "Safe no-follow open is unavailable")
    flags = os.O_RDONLY | nofollow
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_HASH", "Could not safely open regular file")
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
        ):
            raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_HASH", "Regular file identity changed")
        digest = hashlib.sha256()
        while True:
            try:
                block = os.read(descriptor, 1024 * 1024)
            except OSError:
                raise WorkspaceEvidenceError("WORKSPACE_SNAPSHOT_HASH", "Could not safely read regular file")
            if not block:
                return digest.hexdigest()
            digest.update(block)
    finally:
        os.close(descriptor)


def _entry_kind(
    metadata: Optional[os.stat_result], index_metadata: Optional[Tuple[str, str]], untracked: bool
) -> str:
    if metadata is not None and stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    if index_metadata is not None and index_metadata[0] == "160000":
        return "submodule"
    if metadata is not None and stat.S_ISDIR(metadata.st_mode) and index_metadata is not None:
        return "submodule"
    if untracked:
        return "untracked"
    return "tracked"


def snapshot_sha256(snapshot: Dict[str, Any]) -> str:
    """Return the canonical self-hash for a workspace snapshot."""
    return compute_sha256(canonical_bytes(snapshot, omit={"snapshot_sha256"}))


def capture_snapshot(worktree_path: str) -> Dict[str, Any]:
    """Capture canonical Git and filesystem evidence for all non-ignored changes."""
    canonical_worktree = _canonical_directory(worktree_path)
    index = _parse_index(_snapshot_git(canonical_worktree, ["ls-files", "-s", "-z"]))
    status = _parse_status(
        _snapshot_git(
            canonical_worktree,
            ["status", "--porcelain=v2", "-z", "--untracked-files=all"],
        )
    )
    entries: List[Dict[str, Any]] = []
    for path in sorted(status):
        state = status[path]
        index_metadata = index.get(path)
        absolute_path = os.path.join(canonical_worktree, *path.split("/"))
        metadata = _lstat(absolute_path)
        entries.append(
            {
                "path": path,
                "kind": _entry_kind(metadata, index_metadata, state["untracked"]),
                "index_status": state["index_status"],
                "worktree_status": state["worktree_status"],
                "mode": format(metadata.st_mode, "06o") if metadata is not None else None,
                "object_id": state["object_id"] or (
                    index_metadata[1] if index_metadata is not None else None
                ),
                "content_sha256": _content_sha256(absolute_path, metadata)
                if metadata is not None and not stat.S_ISLNK(metadata.st_mode)
                else None,
            }
        )
    snapshot: Dict[str, Any] = {
        "schema_version": 1,
        "entries": entries,
        "snapshot_sha256": "",
    }
    snapshot["snapshot_sha256"] = snapshot_sha256(snapshot)
    return snapshot


_ACTIVE_OWNERSHIP_STATES = {"READY", "RUNNING", "REVIEW", "REVISE"}
_BASELINE_TOP_LEVEL_KEYS = {
    "schema_version", "artifact_kind", "packet_id", "packet_sha256", "intent_id",
    "worktree_identity", "packet_snapshot", "protected_snapshot", "writable_paths",
    "forbidden_surfaces", "content_sha256", "artifact_sha256",
}


def paths_overlap(a: str, b: str) -> bool:
    """Return whether normalized repository-relative prefixes overlap."""
    left = normalize_repo_relative_path(a)
    right = normalize_repo_relative_path(b)
    if left is None or right is None or left == "" or right == "":
        raise WorkspaceEvidenceError(
            "OWNERSHIP_CONFLICT_PATH", "Ownership paths must be normalized repository-relative paths"
        )
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _packet_is_write_capable(packet: Dict[str, Any]) -> bool:
    return bool(packet.get("writable_paths"))


def validate_ownership(packet: Dict[str, Any], active_packets: List[Dict[str, Any]]) -> None:
    """Fail closed when a nonterminal write packet overlaps an existing owner."""
    if not _packet_is_write_capable(packet):
        return
    packet_id = packet.get("packet_id")
    worktree = packet.get("worktree") or {}
    current_path = os.path.realpath(str(worktree.get("path", "")))
    current_branch = worktree.get("branch")
    current_paths = packet.get("writable_paths") or []
    for active in active_packets:
        if active.get("packet_id") == packet_id:
            continue
        if active.get("state") not in _ACTIVE_OWNERSHIP_STATES or not _packet_is_write_capable(active):
            continue
        other_worktree = active.get("worktree") or {}
        if current_path and current_path == os.path.realpath(str(other_worktree.get("path", ""))):
            raise WorkspaceEvidenceError(
                "OWNERSHIP_CONFLICT_WORKTREE", "A nonterminal packet already owns this worktree"
            )
        if current_branch and current_branch == other_worktree.get("branch"):
            raise WorkspaceEvidenceError(
                "OWNERSHIP_CONFLICT_BRANCH", "A nonterminal packet already owns this branch"
            )
        for current in current_paths:
            for other in active.get("writable_paths") or []:
                if paths_overlap(current, other):
                    raise WorkspaceEvidenceError(
                        "OWNERSHIP_CONFLICT_PATH", "A nonterminal packet already owns an overlapping path"
                    )


def build_baseline(
    packet: Dict[str, Any], repo_root: str, protected_worktree_path: Optional[str],
    active_packets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Collect authoritative pre-invocation evidence without publishing it."""
    validate_ownership(packet, active_packets)
    worktree = packet["worktree"]
    identity = inspect_worktree(
        repo_root, worktree["path"], worktree["branch"], packet["starting_revision"]
    )
    packet_snapshot = capture_snapshot(worktree["path"])
    if packet_snapshot["entries"]:
        raise WorkspaceEvidenceError(
            "WORKTREE_SNAPSHOT_DIRTY", "Packet worktree must be clean before invocation"
        )
    protected_snapshot = (
        capture_snapshot(protected_worktree_path) if protected_worktree_path is not None else None
    )
    return {
        "worktree_identity": identity,
        "packet_snapshot": packet_snapshot,
        "protected_snapshot": protected_snapshot,
    }


def _workspace_artifact_hashes(artifact: Dict[str, Any]) -> Tuple[str, str]:
    content_sha256 = compute_sha256(
        canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"})
    )
    copy = dict(artifact)
    copy["content_sha256"] = content_sha256
    artifact_sha256 = compute_sha256(canonical_bytes(copy, omit={"artifact_sha256"}))
    return content_sha256, artifact_sha256


def _validated_workspace_artifact(
    raw: bytes, expected_packet_id: str, expected_intent_id: str
) -> Dict[str, Any]:
    from harness_coordinator.v1.recovery import IntegrityError

    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("WORKSPACE_BASELINE_INVALID", "Workspace baseline is not valid JSON") from exc
    if not isinstance(artifact, dict) or raw != canonical_bytes(artifact):
        raise IntegrityError("WORKSPACE_BASELINE_INVALID", "Workspace baseline is not canonical")
    if set(artifact) != _BASELINE_TOP_LEVEL_KEYS:
        raise IntegrityError("WORKSPACE_BASELINE_INVALID", "Workspace baseline has an invalid field set")
    if (artifact.get("schema_version") != 1
            or artifact.get("artifact_kind") != "workspace_baseline"
            or artifact.get("packet_id") != expected_packet_id
            or artifact.get("intent_id") != expected_intent_id):
        raise IntegrityError("WORKSPACE_BASELINE_MISMATCH", "Workspace baseline identity disagrees")
    content_sha256, artifact_sha256 = _workspace_artifact_hashes(artifact)
    if (artifact.get("content_sha256") != content_sha256
            or artifact.get("artifact_sha256") != artifact_sha256):
        raise IntegrityError("WORKSPACE_BASELINE_MISMATCH", "Workspace baseline hashes disagree")
    return artifact


def publish_workspace_artifact(
    handle, relative_parts: Tuple[str, ...], artifact: Dict[str, Any]
) -> Dict[str, str]:
    """Publish one immutable canonical workspace artifact through the pinned root."""
    artifact = dict(artifact)
    content_sha256, artifact_sha256 = _workspace_artifact_hashes(artifact)
    artifact["content_sha256"] = content_sha256
    artifact["artifact_sha256"] = artifact_sha256
    raw = canonical_bytes(artifact)
    handle.publish(relative_parts, raw)
    return {
        "artifact_path": "/".join(relative_parts),
        "artifact_sha256": artifact_sha256,
        "content_sha256": content_sha256,
    }


def ensure_attempt_baseline(
    handle, packet: Dict[str, Any], intent_id: str, repo_root: str,
    protected_worktree_path: Optional[str], active_packets: List[Dict[str, Any]], *,
    revalidate: bool = True,
) -> Dict[str, Any]:
    """Load a valid existing baseline or build and publish the one immutable baseline."""
    from harness_coordinator.v1.paths import validate_harness_id

    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    intent_id = validate_harness_id(intent_id, "/intent_id")
    parts = ("workspace", packet_id, f"{intent_id}.baseline.json")
    existing = handle.read(parts)
    if existing is not None:
        artifact = _validated_workspace_artifact(existing, packet_id, intent_id)
        if artifact.get("packet_sha256") != packet.get("packet_sha256"):
            from harness_coordinator.v1.recovery import IntegrityError
            raise IntegrityError("WORKSPACE_BASELINE_MISMATCH", "Workspace baseline packet hash disagrees")
        if revalidate:
            try:
                current = build_baseline(packet, repo_root, protected_worktree_path, active_packets)
            except WorkspaceEvidenceError as exc:
                from harness_coordinator.v1.recovery import IntegrityError
                raise IntegrityError("WORKSPACE_BASELINE_DRIFT", "Workspace baseline preflight drifted") from exc
            expected = {
                "worktree_identity": current["worktree_identity"],
                "packet_snapshot": current["packet_snapshot"],
                "protected_snapshot": current["protected_snapshot"],
                "writable_paths": sorted(packet["writable_paths"]),
                "forbidden_surfaces": sorted(packet["forbidden_surfaces"]),
            }
            if any(artifact.get(key) != value for key, value in expected.items()):
                from harness_coordinator.v1.recovery import IntegrityError
                raise IntegrityError("WORKSPACE_BASELINE_DRIFT", "Workspace baseline evidence drifted")
        return {
            "artifact_path": "/".join(parts),
            "artifact_sha256": artifact["artifact_sha256"],
            "content_sha256": artifact["content_sha256"],
        }
    baseline = build_baseline(packet, repo_root, protected_worktree_path, active_packets)
    artifact = {
        "schema_version": 1,
        "artifact_kind": "workspace_baseline",
        "packet_id": packet_id,
        "packet_sha256": packet["packet_sha256"],
        "intent_id": intent_id,
        "worktree_identity": baseline["worktree_identity"],
        "packet_snapshot": baseline["packet_snapshot"],
        "protected_snapshot": baseline["protected_snapshot"],
        "writable_paths": sorted(packet["writable_paths"]),
        "forbidden_surfaces": sorted(packet["forbidden_surfaces"]),
        "content_sha256": "",
        "artifact_sha256": "",
    }
    return publish_workspace_artifact(handle, parts, artifact)
