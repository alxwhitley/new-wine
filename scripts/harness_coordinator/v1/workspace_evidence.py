"""Coordinator-owned Git worktree identity evidence for O4."""

import hashlib
import json
import os
import re
import stat
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import GOVERNED_PATHS, normalize_repo_relative_path


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
_POSTFLIGHT_TOP_LEVEL_KEYS = _BASELINE_TOP_LEVEL_KEYS | {
    "derived_changes", "scope_findings", "worker_manifest_findings",
    "protected_findings", "secret_findings", "acceptance_allowed",
}
_SECRET_RULES = (
    ("private_key_header", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("api_key_assignment", re.compile(r"\b[A-Z0-9_]*API_KEY\s*=", re.IGNORECASE)),
    ("bearer_token", re.compile(r"\bBearer\s+\S+", re.IGNORECASE)),
    ("cloud_credential_prefix", re.compile(r"\b(?:AKIA|ASIA|ACCA|AGPA|AIDA|AROA)[A-Z0-9]{16}\b")),
)


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
    protected_snapshot = None
    if protected_worktree_path is not None:
        protected_snapshot = {
            "worktree_path": _canonical_directory(protected_worktree_path),
            "snapshot": capture_snapshot(protected_worktree_path),
        }
    return {
        "worktree_identity": identity,
        "packet_snapshot": packet_snapshot,
        "protected_snapshot": protected_snapshot,
    }


def _snapshot_entries(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    entries = snapshot.get("entries") if isinstance(snapshot, dict) else None
    if not isinstance(entries, list):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_SNAPSHOT", "Snapshot entries are invalid")
    result: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_SNAPSHOT", "Snapshot entry is invalid")
        path = normalize_repo_relative_path(entry["path"])
        if path is None or not path or path in result:
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_SNAPSHOT", "Snapshot path is invalid")
        result[path] = entry
    return result


def _escaped_snapshot_scope_findings(snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    """Retain a stable scope finding when an untrusted snapshot path escapes."""
    entries = snapshot.get("entries") if isinstance(snapshot, dict) else None
    if not isinstance(entries, list):
        return []
    findings = []
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path or normalize_repo_relative_path(path) is None:
            findings.append({"code": "ALLOWLIST_VIOLATION_ESCAPED", "path": path if isinstance(path, str) else ""})
    return sorted(findings, key=lambda item: (item["path"], item["code"]))


def _change_status(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> str:
    if after is None:
        return "deleted"
    if after.get("index_status") == "D" or after.get("worktree_status") == "D":
        return "deleted"
    if after.get("index_status") == "R":
        return "renamed"
    if before is None:
        if after.get("index_status") == "A" or after.get("kind") == "untracked":
            return "added"
        return "modified"
    if before.get("content_sha256") is None and after.get("content_sha256") is not None:
        return "added"
    if before.get("content_sha256") is not None and after.get("content_sha256") is None:
        return "deleted"
    return "modified"


def derive_changes(baseline_snapshot: Dict[str, Any], current_snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Derive canonical changed-file facts from snapshots, never worker claims."""
    before = _snapshot_entries(baseline_snapshot)
    after = _snapshot_entries(current_snapshot)
    changes: List[Dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        source = new if new is not None else old
        assert source is not None
        status = _change_status(old, new)
        mode_changed = old is not None and new is not None and old.get("mode") != new.get("mode")
        changes.append({
            "path": path,
            "status": status,
            "before_sha256": old.get("content_sha256") if old is not None else None,
            "after_sha256": new.get("content_sha256") if new is not None else None,
            "mode_changed": mode_changed,
            "index_status": source.get("index_status"),
            "worktree_status": source.get("worktree_status"),
            "kind": source.get("kind"),
        })
    return changes


def compare_worker_manifest(derived: List[Dict[str, Any]], claimed: Any) -> List[Dict[str, str]]:
    """Return stable, path-only findings when a claimed manifest disagrees."""
    expected = {item["path"]: item for item in derived}
    actual: Dict[str, Dict[str, Any]] = {}
    findings: List[Dict[str, str]] = []
    if not isinstance(claimed, list):
        return [{"code": "WORKER_MANIFEST_MISMATCH_INVALID", "path": ""}]
    for item in claimed:
        path = item.get("path") if isinstance(item, dict) else None
        normalized = normalize_repo_relative_path(path) if isinstance(path, str) else None
        if normalized is None or not normalized:
            findings.append({"code": "WORKER_MANIFEST_MISMATCH_INVALID", "path": path or ""})
        elif normalized in actual:
            findings.append({"code": "WORKER_MANIFEST_MISMATCH_DUPLICATE", "path": normalized})
        else:
            actual[normalized] = item
    for path in sorted(set(expected) - set(actual)):
        findings.append({"code": "WORKER_MANIFEST_MISMATCH_OMITTED", "path": path})
    for path in sorted(set(actual) - set(expected)):
        findings.append({"code": "WORKER_MANIFEST_MISMATCH_INVENTED", "path": path})
    for path in sorted(set(expected) & set(actual)):
        observed, truth = actual[path], expected[path]
        if observed.get("status") != truth["status"]:
            findings.append({"code": "WORKER_MANIFEST_MISMATCH_STATUS", "path": path})
        elif observed.get("before_sha256") != truth["before_sha256"]:
            findings.append({"code": "WORKER_MANIFEST_MISMATCH_BEFORE_DIGEST", "path": path})
        elif observed.get("after_sha256") != truth["after_sha256"]:
            findings.append({"code": "WORKER_MANIFEST_MISMATCH_AFTER_DIGEST", "path": path})
    return sorted(findings, key=lambda item: (item["path"], item["code"]))


def _path_is_within(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + "/")


def _scope_findings(packet: Dict[str, Any], changes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    writable = [normalize_repo_relative_path(path) for path in packet.get("writable_paths", [])]
    forbidden = [normalize_repo_relative_path(path) for path in packet.get("forbidden_surfaces", [])]
    findings: List[Dict[str, str]] = []
    for change in changes:
        path = change["path"]
        if (normalize_repo_relative_path(path) is None or not path):
            code = "ALLOWLIST_VIOLATION_ESCAPED"
        elif change.get("kind") == "symlink":
            code = "ALLOWLIST_VIOLATION_SYMLINK"
        elif change.get("kind") == "submodule":
            code = "ALLOWLIST_VIOLATION_SUBMODULE"
        elif path in GOVERNED_PATHS:
            code = "ALLOWLIST_VIOLATION_GOVERNED"
        elif any(parent and _path_is_within(path, parent) for parent in forbidden):
            code = "ALLOWLIST_VIOLATION_FORBIDDEN"
        elif not any(parent and _path_is_within(path, parent) for parent in writable):
            code = "ALLOWLIST_VIOLATION_UNDECLARED"
        else:
            continue
        findings.append({"code": code, "path": path})
    return sorted(findings, key=lambda item: (item["path"], item["code"]))


def _safe_regular_text(path: str, maximum_bytes: int) -> Tuple[Optional[str], Optional[str]]:
    """Read a regular non-symlink file only; return text or an unscannable reason."""
    if not hasattr(os, "O_NOFOLLOW"):
        return None, "nofollow_unavailable"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None, "unreadable"
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None, "non_regular"
        if info.st_size > maximum_bytes:
            return None, "too_large"
        raw = bytearray()
        while len(raw) <= maximum_bytes:
            block = os.read(fd, min(65536, maximum_bytes + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        if len(raw) > maximum_bytes:
            return None, "too_large"
        try:
            return bytes(raw).decode("utf-8", "strict"), None
        except UnicodeDecodeError:
            return None, "binary"
    finally:
        os.close(fd)
    return None


def _added_lines(worktree_path: str, revision: str, path: str) -> List[Tuple[int, str]]:
    try:
        raw = _run_git(worktree_path, [
            "diff", "--unified=0", "--no-ext-diff", "--no-textconv", revision, "--", path,
        ])
        text = raw.decode("utf-8", "strict")
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Could not inspect changed additions")
    lines: List[Tuple[int, str]] = []
    current = None
    for line in text.splitlines():
        match = re.match(r"^@@ -[^ ]+ \+(\d+)(?:,\d+)? @@", line)
        if match:
            current = int(match.group(1))
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            lines.append((current, line[1:]))
            current += 1
        elif current is not None and not line.startswith("-"):
            current += 1
    return lines


def scan_secret_like_additions(worktree_path: str, changes: List[Dict[str, Any]],
                               maximum_bytes: int = 1048576) -> List[Dict[str, Any]]:
    """Report secret-like additions with path/rule/line metadata only."""
    try:
        revision = next((item["_starting_revision"] for item in changes
                         if isinstance(item, dict) and isinstance(item.get("_starting_revision"), str)), None)
        if revision is None:
            revision = _run_git(worktree_path, ["rev-parse", "HEAD"]).decode("ascii").strip()
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Could not resolve starting revision")
    findings: List[Dict[str, Any]] = []
    for change in changes:
        if change.get("status") not in {"added", "modified", "renamed"}:
            continue
        path = change.get("path")
        if not isinstance(path, str) or normalize_repo_relative_path(path) != path:
            findings.append({"code": "SECRET_LIKE_DIFF_REVIEW_REQUIRED", "path": path or "", "reason": "invalid_path"})
            continue
        absolute = os.path.join(_canonical_directory(worktree_path), *path.split("/"))
        source_text, reason = _safe_regular_text(absolute, maximum_bytes)
        if reason is not None:
            findings.append({"code": "SECRET_LIKE_DIFF_REVIEW_REQUIRED", "path": path, "reason": reason})
            continue
        if change.get("kind") == "untracked" or change.get("index_status") is None and change.get("status") == "added":
            assert source_text is not None
            added = list(enumerate(source_text.splitlines(), start=1))
        else:
            added = _added_lines(worktree_path, revision, path)
        for line_number, line in added:
            for rule_id, pattern in _SECRET_RULES:
                if pattern.search(line):
                    findings.append({"code": "SECRET_LIKE_DIFF_PATTERN", "rule_id": rule_id,
                                     "path": path, "line": line_number})
    return sorted(findings, key=lambda item: (item["path"], item.get("line", -1), item.get("rule_id", "")))


def _protected_findings(baseline: Dict[str, Any]) -> List[Dict[str, str]]:
    protected = baseline.get("protected_snapshot")
    if protected is None:
        return []
    if not isinstance(protected, dict) or not isinstance(protected.get("worktree_path"), str):
        return [{"code": "PROTECTED_WORKTREE_CHANGED_UNVERIFIABLE", "path": ""}]
    before = protected.get("snapshot")
    try:
        after = capture_snapshot(protected["worktree_path"])
    except WorkspaceEvidenceError:
        return [{"code": "PROTECTED_WORKTREE_CHANGED_UNVERIFIABLE", "path": ""}]
    if before == after:
        return []
    try:
        changes = derive_changes(before, after)
    except WorkspaceEvidenceError:
        return [{"code": "PROTECTED_WORKTREE_CHANGED_UNVERIFIABLE", "path": ""}]
    return [{"code": "PROTECTED_WORKTREE_CHANGED_%s" % change["status"].upper(),
             "path": change["path"]} for change in changes]


def _rename_sources(worktree_path: str, revision: str) -> Dict[str, str]:
    """Map rename destinations to porcelain/Git-provided original paths."""
    try:
        records = _run_git(worktree_path, ["diff", "--name-status", "-z", "-M", revision, "--"]).split(b"\0")
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Could not inspect rename sources")
    sources: Dict[str, str] = {}
    index = 0
    while index < len(records):
        status = records[index]
        index += 1
        if not status:
            continue
        if status.startswith(b"R") or status.startswith(b"C"):
            if index + 1 >= len(records):
                raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Rename source record is incomplete")
            source, destination = records[index], records[index + 1]
            index += 2
            sources[_normalized_status_path(destination)] = _normalized_status_path(source)
        elif index < len(records):
            index += 1
    return sources


def _head_digest(worktree_path: str, revision: str, path: str) -> Optional[str]:
    try:
        return hashlib.sha256(_run_git(worktree_path, ["show", f"{revision}:{path}"])).hexdigest()
    except (OSError, subprocess.SubprocessError):
        return None


def _hydrate_before_digests(worktree_path: str, revision: str, changes: List[Dict[str, Any]]) -> None:
    """Fill clean-baseline before digests from the pinned starting tree."""
    rename_sources = _rename_sources(worktree_path, revision)
    for change in changes:
        if change.get("before_sha256") is not None or change.get("status") == "added":
            continue
        path = rename_sources.get(change["path"], change["path"])
        change["before_sha256"] = _head_digest(worktree_path, revision, path)


def _hydrate_mode_changes(worktree_path: str, revision: str, changes: List[Dict[str, Any]]) -> None:
    """Use Git's old/new modes, not a generic M status, for mode metadata."""
    try:
        records = _run_git(worktree_path, ["diff", "--raw", "-z", "-M", revision, "--"]).split(b"\0")
    except (OSError, subprocess.SubprocessError):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Could not inspect changed modes")
    modes: Dict[str, Tuple[str, str]] = {}
    index = 0
    while index < len(records):
        metadata = records[index]
        index += 1
        if not metadata:
            continue
        fields = metadata.split()
        if len(fields) < 5 or not fields[0].startswith(b":") or index >= len(records):
            raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Raw Git mode record is invalid")
        old_mode, new_mode, status = fields[0][1:].decode("ascii"), fields[1].decode("ascii"), fields[4]
        if status.startswith(b"R") or status.startswith(b"C"):
            if index + 1 >= len(records):
                raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_DIFF", "Raw rename mode record is incomplete")
            index += 1  # source's mode is represented by the destination change
            path = _normalized_status_path(records[index])
            index += 1
        else:
            path = _normalized_status_path(records[index])
            index += 1
        modes[path] = (old_mode, new_mode)
    for change in changes:
        if change["path"] in modes:
            old_mode, new_mode = modes[change["path"]]
            change["mode_changed"] = (
                change.get("status") not in {"added", "deleted"} and old_mode != new_mode
            )


def build_postflight(packet: Dict[str, Any], intent_id: str, baseline: Dict[str, Any],
                     worker_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build coordinator-owned postflight evidence after every worker outcome."""
    identity = baseline.get("worktree_identity")
    if not isinstance(identity, dict):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_BASELINE", "Baseline identity is invalid")
    current_identity = inspect_worktree(
        identity["repo_root"], identity["worktree_path"],
        str(identity["branch"]).removeprefix("refs/heads/"), identity["head"],
    )
    if current_identity != identity:
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_IDENTITY", "Packet worktree identity changed")
    current_snapshot = capture_snapshot(identity["worktree_path"])
    try:
        derived = derive_changes(baseline["packet_snapshot"], current_snapshot)
    except WorkspaceEvidenceError:
        # A snapshot which cannot be normalized cannot establish scope
        # authority.  Preserve the postflight contract as a durable,
        # fail-closed artifact rather than letting a caller advance without
        # one.
        return build_postflight_failure(
            packet, intent_id, baseline,
            scope_findings=_escaped_snapshot_scope_findings(current_snapshot),
        )
    _hydrate_before_digests(identity["worktree_path"], identity["head"], derived)
    _hydrate_mode_changes(identity["worktree_path"], identity["head"], derived)
    scope = _scope_findings(packet, derived)
    claimed = worker_result.get("changed_files") if isinstance(worker_result, dict) else []
    manifest = compare_worker_manifest(derived, claimed)
    protected = _protected_findings(baseline)
    scan_changes = [dict(change, _starting_revision=identity["head"]) for change in derived]
    secret = scan_secret_like_additions(identity["worktree_path"], scan_changes)
    return {
        "schema_version": 1,
        "artifact_kind": "workspace_postflight",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "intent_id": intent_id,
        "worktree_identity": identity,
        "packet_snapshot": baseline["packet_snapshot"],
        "protected_snapshot": baseline.get("protected_snapshot"),
        "writable_paths": sorted(packet["writable_paths"]),
        "forbidden_surfaces": sorted(packet["forbidden_surfaces"]),
        "derived_changes": derived,
        "scope_findings": scope,
        "worker_manifest_findings": manifest,
        "protected_findings": protected,
        "secret_findings": secret,
        "acceptance_allowed": not (scope or manifest or protected or secret),
        "content_sha256": "",
        "artifact_sha256": "",
    }


def build_postflight_failure(
    packet: Dict[str, Any], intent_id: str, baseline: Dict[str, Any], *,
    scope_findings: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Preserve a safe HUMAN_REQUIRED postflight when evidence capture itself fails."""
    return {
        "schema_version": 1,
        "artifact_kind": "workspace_postflight",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "intent_id": intent_id,
        "worktree_identity": baseline["worktree_identity"],
        "packet_snapshot": baseline["packet_snapshot"],
        "protected_snapshot": baseline.get("protected_snapshot"),
        "writable_paths": sorted(packet["writable_paths"]),
        "forbidden_surfaces": sorted(packet["forbidden_surfaces"]),
        "derived_changes": [],
        "scope_findings": scope_findings or [],
        "worker_manifest_findings": [],
        "protected_findings": [{"code": "PROTECTED_WORKTREE_CHANGED_UNVERIFIABLE", "path": ""}],
        "secret_findings": [],
        "acceptance_allowed": False,
        "content_sha256": "",
        "artifact_sha256": "",
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


def validate_postflight_binding(handle, packet: Dict[str, Any], intent_id: str,
                                artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Return the strictly validated persisted artifact and canonical binding."""
    from harness_coordinator.v1.paths import validate_harness_id

    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    intent_id = validate_harness_id(intent_id, "/intent_id")
    parts = ("workspace", packet_id, f"{intent_id}.postflight.json")
    raw = handle.read(parts)
    if raw is None:
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_MISSING", "Workspace postflight is missing")
    try:
        persisted = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_INVALID", "Postflight is not valid JSON") from exc
    if (not isinstance(persisted, dict) or raw != canonical_bytes(persisted)
            or set(persisted) != _POSTFLIGHT_TOP_LEVEL_KEYS
            or persisted.get("schema_version") != 1
            or persisted.get("artifact_kind") != "workspace_postflight"
            or persisted.get("packet_id") != packet_id
            or persisted.get("packet_sha256") != packet.get("packet_sha256")
            or persisted.get("intent_id") != intent_id):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_INVALID", "Postflight artifact is invalid")
    content_sha256, artifact_sha256 = _workspace_artifact_hashes(persisted)
    if (not isinstance(artifact, dict)
            or persisted.get("content_sha256") != content_sha256
            or persisted.get("artifact_sha256") != artifact_sha256
            or artifact.get("content_sha256") != content_sha256
            or artifact.get("artifact_sha256") != artifact_sha256):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_MISMATCH", "Postflight hashes disagree")
    return {
        "artifact": persisted,
        "binding": {"packet_id": packet_id, "intent_id": intent_id, "path": "/".join(parts),
                    "artifact_sha256": artifact_sha256, "content_sha256": content_sha256},
    }


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


def load_attempt_baseline(handle, packet: Dict[str, Any], intent_id: str) -> Dict[str, Any]:
    """Load the immutable baseline that binds a postflight to its attempt."""
    from harness_coordinator.v1.paths import validate_harness_id

    packet_id = validate_harness_id(packet["packet_id"], "/packet_id")
    intent_id = validate_harness_id(intent_id, "/intent_id")
    raw = handle.read(("workspace", packet_id, f"{intent_id}.baseline.json"))
    if raw is None:
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_BASELINE", "Workspace baseline is missing")
    artifact = _validated_workspace_artifact(raw, packet_id, intent_id)
    if artifact.get("packet_sha256") != packet.get("packet_sha256"):
        raise WorkspaceEvidenceError("WORKSPACE_POSTFLIGHT_BASELINE", "Workspace baseline packet hash disagrees")
    return artifact
