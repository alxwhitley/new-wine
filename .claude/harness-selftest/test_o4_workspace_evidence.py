"""O4 registered-worktree identity tests using disposable local repositories."""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes
from harness_coordinator.v1 import workspace_evidence
from harness_coordinator.v1.workspace_evidence import (
    WorkspaceEvidenceError,
    capture_snapshot,
    compare_worker_manifest,
    derive_changes,
    inspect_worktree,
    scan_secret_like_additions,
    snapshot_sha256,
)


def _git(cwd: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


@dataclass
class RepoFixture:
    root: Path
    packet_worktree: Path
    packet_revision: str
    common_dir: str

    def apply_identity_mutation(self, mutation: str) -> None:
        if mutation == "symlink":
            original = self.packet_worktree.with_name("packet-real")
            self.packet_worktree.rename(original)
            self.packet_worktree.symlink_to(original, target_is_directory=True)
        elif mutation == "detached":
            _git(self.packet_worktree, "checkout", "--detach", self.packet_revision)
        elif mutation == "wrong_branch":
            _git(self.packet_worktree, "checkout", "codex/packet-b")
        elif mutation == "wrong_revision":
            changed = self.packet_worktree / "allowed" / "later.txt"
            changed.write_text("later\n", encoding="utf-8")
            _git(self.packet_worktree, "add", "allowed/later.txt")
            _git(self.packet_worktree, "commit", "-m", "advance packet worktree")
        elif mutation == "foreign_repo":
            foreign = self.root.parent / "foreign"
            foreign.mkdir()
            _git(foreign, "init")
            _git(foreign, "config", "user.name", "O4 Test")
            _git(foreign, "config", "user.email", "o4@example.test")
            self.root = foreign
        else:
            raise AssertionError("unknown mutation: %s" % mutation)

    def make_change(self, shape: str) -> str:
        allowed = self.packet_worktree / "allowed"
        if shape == "tracked":
            (allowed / "base.txt").write_text("modified\n", encoding="utf-8")
            return "allowed/base.txt"
        if shape == "staged":
            (allowed / "staged.txt").write_text("staged\n", encoding="utf-8")
            _git(self.packet_worktree, "add", "allowed/staged.txt")
            return "allowed/staged.txt"
        if shape == "deleted":
            (allowed / "delete.txt").unlink()
            return "allowed/delete.txt"
        if shape == "renamed":
            _git(self.packet_worktree, "mv", "allowed/rename-old.txt", "allowed/rename-new.txt")
            return "allowed/rename-new.txt"
        if shape == "mode":
            executable = allowed / "executable.sh"
            executable.chmod(executable.stat().st_mode | 0o111)
            return "allowed/executable.sh"
        if shape == "untracked":
            (allowed / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            return "allowed/untracked.txt"
        if shape == "submodule":
            source = self.root.parent / "submodule-source"
            source.mkdir()
            _git(source, "init")
            _git(source, "config", "user.name", "O4 Test")
            _git(source, "config", "user.email", "o4@example.test")
            (source / "source.txt").write_text("source\n", encoding="utf-8")
            _git(source, "add", "source.txt")
            _git(source, "commit", "-m", "submodule base")
            _git(
                self.packet_worktree,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(source),
                "allowed/submodule",
            )
            (allowed / "submodule" / "source.txt").write_text("dirty\n", encoding="utf-8")
            return "allowed/submodule"
        raise AssertionError("unknown shape: %s" % shape)

    def make_all_change_shapes(self) -> None:
        for shape in ("tracked", "staged", "deleted", "renamed", "mode", "untracked", "submodule"):
            self.make_change(shape)

    def rename_outside_source_into_allowed_path(self) -> None:
        _git(
            self.packet_worktree,
            "mv",
            "outside/rename-source.txt",
            "allowed/rename-from-outside.txt",
        )


@pytest.fixture
def repo_fixture(tmp_path: Path) -> RepoFixture:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "O4 Test")
    _git(root, "config", "user.email", "o4@example.test")
    (root / "allowed").mkdir()
    (root / "allowed" / "base.txt").write_text("base\n", encoding="utf-8")
    (root / "allowed" / "delete.txt").write_text("delete\n", encoding="utf-8")
    (root / "allowed" / "rename-old.txt").write_text("rename\n", encoding="utf-8")
    (root / "allowed" / "executable.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "outside").mkdir()
    (root / "outside" / "rename-source.txt").write_text("outside\n", encoding="utf-8")
    _git(root, "add", "allowed", "outside")
    _git(root, "commit", "-m", "base")
    _git(root, "branch", "codex/packet-a")
    _git(root, "branch", "codex/packet-b")
    packet_worktree = tmp_path / "packet-worktree"
    _git(root, "worktree", "add", str(packet_worktree), "codex/packet-a")
    return RepoFixture(
        root=root,
        packet_worktree=packet_worktree,
        packet_revision=_git(packet_worktree, "rev-parse", "HEAD"),
        common_dir=os.path.realpath(root / _git(root, "rev-parse", "--git-common-dir")),
    )


def test_registered_branch_and_revision_are_pinned(repo_fixture: RepoFixture) -> None:
    """Fails if registration, branch, revision, or common-dir evidence is not pinned."""
    evidence = inspect_worktree(
        str(repo_fixture.root),
        str(repo_fixture.packet_worktree),
        "codex/packet-a",
        repo_fixture.packet_revision,
    )
    assert evidence["branch"] == "refs/heads/codex/packet-a"
    assert evidence["head"] == repo_fixture.packet_revision
    assert evidence["common_dir"] == repo_fixture.common_dir
    assert evidence == {
        "schema_version": 1,
        "repo_root": os.path.realpath(repo_fixture.root),
        "worktree_path": os.path.realpath(repo_fixture.packet_worktree),
        "common_dir": repo_fixture.common_dir,
        "branch": "refs/heads/codex/packet-a",
        "head": repo_fixture.packet_revision,
    }


@pytest.mark.parametrize(
    "mutation", ["symlink", "detached", "wrong_branch", "wrong_revision", "foreign_repo"]
)
def test_identity_mismatch_fails_before_snapshot(
    repo_fixture: RepoFixture, mutation: str
) -> None:
    """Fails if an operator-provided worktree identity can drift before capture."""
    repo_fixture.apply_identity_mutation(mutation)
    with pytest.raises(WorkspaceEvidenceError) as caught:
        inspect_worktree(
            str(repo_fixture.root),
            str(repo_fixture.packet_worktree),
            "codex/packet-a",
            repo_fixture.packet_revision,
        )
    assert caught.value.code.startswith("WORKTREE_IDENTITY_")


@pytest.mark.parametrize("suffix", ["", os.sep])
def test_symlink_worktree_endpoint_is_rejected_with_or_without_trailing_separator(
    repo_fixture: RepoFixture, suffix: str
) -> None:
    """Fails if trailing separators let a symlink operator path bypass preflight."""
    repo_fixture.apply_identity_mutation("symlink")
    with pytest.raises(WorkspaceEvidenceError) as caught:
        inspect_worktree(
            str(repo_fixture.root),
            str(repo_fixture.packet_worktree) + suffix,
            "codex/packet-a",
            repo_fixture.packet_revision,
        )
    assert caught.value.code == "WORKTREE_IDENTITY_SYMLINK"


@pytest.mark.parametrize(
    "shape",
    [
        "tracked",
        "staged",
        "deleted",
        "renamed",
        "mode",
        "untracked",
        "submodule",
    ],
)
def test_snapshot_records_exact_fields_for_each_git_change_shape(
    repo_fixture: RepoFixture, shape: str
) -> None:
    """Fails if a dirty Git shape loses its required status, mode, object, or digest evidence."""
    changed_path = repo_fixture.make_change(shape)
    snapshot = capture_snapshot(str(repo_fixture.packet_worktree))
    rows = {entry["path"]: entry for entry in snapshot["entries"]}
    assert set(rows[changed_path]) == {
        "path", "kind", "index_status", "worktree_status", "mode", "object_id", "content_sha256"
    }
    digest = lambda content: hashlib.sha256(content).hexdigest()
    if shape == "tracked":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "tracked", "index_status": None, "worktree_status": "M",
            "mode": "100644", "object_id": _git(repo_fixture.packet_worktree, "rev-parse", "HEAD:allowed/base.txt"),
            "content_sha256": digest(b"modified\n"),
        }
    elif shape == "staged":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "tracked", "index_status": "A", "worktree_status": None,
            "mode": "100644", "object_id": _git(repo_fixture.packet_worktree, "rev-parse", ":allowed/staged.txt"),
            "content_sha256": digest(b"staged\n"),
        }
    elif shape == "deleted":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "tracked", "index_status": None, "worktree_status": "D",
            "mode": None, "object_id": _git(repo_fixture.packet_worktree, "rev-parse", "HEAD:allowed/delete.txt"),
            "content_sha256": None,
        }
    elif shape == "renamed":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "tracked", "index_status": "R", "worktree_status": None,
            "mode": "100644", "object_id": _git(repo_fixture.packet_worktree, "rev-parse", ":allowed/rename-new.txt"),
            "content_sha256": digest(b"rename\n"),
        }
        assert rows["allowed/rename-old.txt"] == {
            "path": "allowed/rename-old.txt", "kind": "tracked", "index_status": "D", "worktree_status": None,
            "mode": None, "object_id": _git(repo_fixture.packet_worktree, "rev-parse", "HEAD:allowed/rename-old.txt"),
            "content_sha256": None,
        }
    elif shape == "mode":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "tracked", "index_status": None, "worktree_status": "M",
            "mode": "100755", "object_id": _git(repo_fixture.packet_worktree, "rev-parse", "HEAD:allowed/executable.sh"),
            "content_sha256": digest(b"#!/bin/sh\n"),
        }
    elif shape == "untracked":
        assert rows[changed_path] == {
            "path": changed_path, "kind": "untracked", "index_status": None, "worktree_status": None,
            "mode": "100644", "object_id": None, "content_sha256": digest(b"untracked\n"),
        }
    else:
        assert rows[changed_path]["kind"] == "submodule"
        assert rows[changed_path]["index_status"] == "A"
        assert rows[changed_path]["worktree_status"] == "M"
        assert rows[changed_path]["mode"] == format((repo_fixture.packet_worktree / changed_path).lstat().st_mode, "06o")
        assert rows[changed_path]["object_id"] is not None
        assert rows[changed_path]["content_sha256"] is None


def test_snapshot_keeps_rename_source_path_for_ownership(repo_fixture: RepoFixture) -> None:
    """Fails if a rename hides an out-of-allowlist source behind an allowed destination."""
    repo_fixture.rename_outside_source_into_allowed_path()
    rows = {entry["path"]: entry for entry in capture_snapshot(str(repo_fixture.packet_worktree))["entries"]}
    assert rows["allowed/rename-from-outside.txt"]["index_status"] == "R"
    assert rows["outside/rename-source.txt"] == {
        "path": "outside/rename-source.txt", "kind": "tracked", "index_status": "D",
        "worktree_status": None, "mode": None,
        "object_id": _git(repo_fixture.packet_worktree, "rev-parse", "HEAD:outside/rename-source.txt"),
        "content_sha256": None,
    }


def test_snapshot_marks_dirty_symlink_without_following_it(repo_fixture: RepoFixture) -> None:
    """Fails if a dirty symlink is followed or receives a regular-file digest."""
    link = repo_fixture.packet_worktree / "allowed" / "dirty-link"
    link.symlink_to("base.txt")
    row = next(
        entry for entry in capture_snapshot(str(repo_fixture.packet_worktree))["entries"]
        if entry["path"] == "allowed/dirty-link"
    )
    assert row == {
        "path": "allowed/dirty-link", "kind": "symlink", "index_status": None,
        "worktree_status": None, "mode": format(link.lstat().st_mode, "06o"),
        "object_id": None, "content_sha256": None,
    }


def test_snapshot_fails_closed_when_regular_file_cannot_be_opened(
    repo_fixture: RepoFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails if a lstat-regular dirty file loses its digest after a safe-open failure."""
    repo_fixture.make_change("tracked")
    monkeypatch.setattr(workspace_evidence.os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")))
    with pytest.raises(WorkspaceEvidenceError) as caught:
        capture_snapshot(str(repo_fixture.packet_worktree))
    assert caught.value.code == "WORKSPACE_SNAPSHOT_HASH"


def test_snapshot_is_canonical_and_complete(repo_fixture: RepoFixture) -> None:
    """Fails if repeated snapshots differ or lose a dirty path category."""
    repo_fixture.make_all_change_shapes()
    first = capture_snapshot(str(repo_fixture.packet_worktree))
    second = capture_snapshot(str(repo_fixture.packet_worktree))
    assert first == second
    assert [row["path"] for row in first["entries"]] == sorted(
        row["path"] for row in first["entries"]
    )
    assert first["snapshot_sha256"] == snapshot_sha256(first)
    assert {row["kind"] for row in first["entries"]} >= {
        "tracked",
        "untracked",
        "submodule",
    }


def _ownership_packet() -> dict:
    return {
        "packet_id": "packet-current",
        "worktree": {"path": "/tmp/o4-worktree-current", "branch": "codex/o4-current"},
        "writable_paths": ["scripts/harness_coordinator/v1/workspace_evidence.py"],
    }


def _conflicting_packet(packet: dict, field: str, state: str) -> dict:
    active = {
        "packet_id": "packet-active",
        "state": state,
        "worktree": {"path": "/tmp/o4-worktree-other", "branch": "codex/o4-other"},
        "writable_paths": ["scripts/harness_coordinator/v1/other.py"],
    }
    if field == "same_worktree":
        active["worktree"]["path"] = packet["worktree"]["path"]
    elif field == "same_branch":
        active["worktree"]["branch"] = packet["worktree"]["branch"]
    elif field == "equal_path":
        active["writable_paths"] = list(packet["writable_paths"])
    elif field == "parent_path":
        active["writable_paths"] = ["scripts/harness_coordinator"]
    elif field == "child_path":
        active["writable_paths"] = ["scripts/harness_coordinator/v1/workspace_evidence.py/helper.py"]
    else:
        raise AssertionError("unknown ownership conflict field")
    return active


@pytest.mark.parametrize("field", [
    "same_worktree", "same_branch", "equal_path", "parent_path", "child_path",
])
def test_nonterminal_write_ownership_conflicts(field: str) -> None:
    """Fails until nonterminal write ownership is checked before invocation."""
    from harness_coordinator.v1.workspace_evidence import validate_ownership

    packet = _ownership_packet()
    active = _conflicting_packet(packet, field, state="RUNNING")
    with pytest.raises(WorkspaceEvidenceError) as caught:
        validate_ownership(packet, [active])
    assert caught.value.code.startswith("OWNERSHIP_CONFLICT_")


@pytest.mark.parametrize("state", ["ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED"])
def test_terminal_packets_do_not_conflict_with_write_ownership(state: str) -> None:
    """Terminal packets release their declared write ownership."""
    from harness_coordinator.v1.workspace_evidence import validate_ownership

    packet = _ownership_packet()
    validate_ownership(packet, [_conflicting_packet(packet, "equal_path", state=state)])


def test_read_only_packet_does_not_claim_write_ownership() -> None:
    """An empty writable-path list remains a read-only lane for conflict purposes."""
    from harness_coordinator.v1.workspace_evidence import validate_ownership

    packet = _ownership_packet()
    active = _conflicting_packet(packet, "equal_path", state="RUNNING")
    active["writable_paths"] = []
    validate_ownership(packet, [active])


def test_derived_changes_are_authoritative_and_worker_manifest_must_agree() -> None:
    """Coordinator evidence, not a worker claim, determines every changed path."""
    baseline = {"entries": [{
        "path": "allowed/old.py", "kind": "tracked", "index_status": None,
        "worktree_status": None, "mode": "100644", "object_id": "a" * 40,
        "content_sha256": "a" * 64,
    }]}
    current = {"entries": [
        {
            "path": "allowed/old.py", "kind": "tracked", "index_status": None,
            "worktree_status": "M", "mode": "100755", "object_id": "a" * 40,
            "content_sha256": "b" * 64,
        },
        {
            "path": "allowed/new.py", "kind": "untracked", "index_status": None,
            "worktree_status": None, "mode": "100644", "object_id": None,
            "content_sha256": "c" * 64,
        },
    ]}
    derived = derive_changes(baseline, current)
    assert derived == [
        {"path": "allowed/new.py", "status": "added", "before_sha256": None,
         "after_sha256": "c" * 64, "mode_changed": False,
         "index_status": None, "worktree_status": None, "kind": "untracked"},
        {"path": "allowed/old.py", "status": "modified", "before_sha256": "a" * 64,
         "after_sha256": "b" * 64, "mode_changed": True,
         "index_status": None, "worktree_status": "M", "kind": "tracked"},
    ]
    claimed = [{key: change[key] for key in ("path", "status", "before_sha256", "after_sha256")}
               for change in derived]
    assert compare_worker_manifest(derived, claimed) == []
    omitted = compare_worker_manifest(derived, claimed[:1])
    assert omitted == [{"code": "WORKER_MANIFEST_MISMATCH_OMITTED", "path": "allowed/old.py"}]
    invented = compare_worker_manifest(derived, claimed + [{
        "path": "allowed/invented.py", "status": "added", "before_sha256": None,
        "after_sha256": None,
    }])
    assert invented == [{"code": "WORKER_MANIFEST_MISMATCH_INVENTED", "path": "allowed/invented.py"}]
    wrong = list(claimed)
    wrong[0] = dict(wrong[0], after_sha256="d" * 64)
    assert compare_worker_manifest(derived, wrong) == [
        {"code": "WORKER_MANIFEST_MISMATCH_AFTER_DIGEST", "path": "allowed/new.py"}
    ]
    for field, code in (("status", "WORKER_MANIFEST_MISMATCH_STATUS"),
                        ("before_sha256", "WORKER_MANIFEST_MISMATCH_BEFORE_DIGEST")):
        mismatched = list(claimed)
        mismatched[1] = dict(mismatched[1], **{field: "deleted" if field == "status" else None})
        assert compare_worker_manifest(derived, mismatched) == [{"code": code, "path": "allowed/old.py"}]


def test_secret_scan_records_only_safe_metadata(repo_fixture: RepoFixture) -> None:
    """Secret-like additions never put the matching value in the artifact."""
    target = repo_fixture.packet_worktree / "allowed" / "new.py"
    target.write_text("a = 1\nAPI_KEY = 'fixture-secret-never-persisted'\n", encoding="utf-8")
    findings = scan_secret_like_additions(str(repo_fixture.packet_worktree), [{
        "path": "allowed/new.py", "status": "added", "before_sha256": None,
        "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }])
    assert findings == [{
        "code": "SECRET_LIKE_DIFF_PATTERN", "rule_id": "api_key_assignment",
        "path": "allowed/new.py", "line": 2,
    }]
    assert b"fixture-secret-never-persisted" not in canonical_bytes({"findings": findings})


def test_clean_baseline_deletion_is_deleted_not_modified() -> None:
    """A porcelain D entry remains a deletion when the clean baseline has no row."""
    deleted = {
        "path": "allowed/gone.py", "kind": "tracked", "index_status": None,
        "worktree_status": "D", "mode": None, "object_id": "a" * 40,
        "content_sha256": None,
    }
    assert derive_changes({"entries": []}, {"entries": [deleted]})[0]["status"] == "deleted"


@pytest.mark.parametrize("shape, expected_status, expected_mode_changed", [
    ("deleted", "deleted", False),
    ("renamed", "renamed", False),
    ("mode", "modified", True),
    ("tracked", "modified", False),
])
def test_real_git_postflight_change_semantics(
        repo_fixture: RepoFixture, shape: str, expected_status: str, expected_mode_changed: bool) -> None:
    """Deletion, rename, and M status semantics use Git's actual raw modes."""
    path = repo_fixture.make_change(shape)
    changes = derive_changes({"entries": []}, capture_snapshot(str(repo_fixture.packet_worktree)))
    workspace_evidence._hydrate_mode_changes(
        str(repo_fixture.packet_worktree), repo_fixture.packet_revision, changes)
    row = next(change for change in changes if change["path"] == path)
    assert row["status"] == expected_status
    assert row["mode_changed"] is expected_mode_changed
    if shape == "renamed":
        assert any(change["path"] == "allowed/rename-old.txt" and change["status"] == "deleted"
                   for change in changes)


def test_secret_scan_fails_closed_without_nofollow(repo_fixture: RepoFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Platforms without O_NOFOLLOW require review instead of following additions."""
    target = repo_fixture.packet_worktree / "allowed" / "new.py"
    target.write_text("plain\n", encoding="utf-8")
    monkeypatch.delattr(workspace_evidence.os, "O_NOFOLLOW", raising=False)
    findings = scan_secret_like_additions(str(repo_fixture.packet_worktree), [{
        "path": "allowed/new.py", "status": "added", "before_sha256": None,
        "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }])
    assert findings == [{
        "code": "SECRET_LIKE_DIFF_REVIEW_REQUIRED", "path": "allowed/new.py",
        "reason": "nofollow_unavailable",
    }]


@pytest.mark.parametrize("name, line, rule_id", [
    ("private.py", "-----BEGIN PRIVATE KEY-----", "private_key_header"),
    ("api.py", "API_KEY = 'value'", "api_key_assignment"),
    ("bearer.py", "Authorization: Bearer token-value", "bearer_token"),
    ("cloud.py", "value = AKIA" + "A" * 16, "cloud_credential_prefix"),
])
def test_secret_scan_covers_each_stable_rule(
        repo_fixture: RepoFixture, name: str, line: str, rule_id: str) -> None:
    target = repo_fixture.packet_worktree / "allowed" / name
    target.write_text("safe\n" + line + "\n", encoding="utf-8")
    findings = scan_secret_like_additions(str(repo_fixture.packet_worktree), [{
        "path": f"allowed/{name}", "status": "added", "before_sha256": None,
        "after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }])
    assert findings == [{"code": "SECRET_LIKE_DIFF_PATTERN", "rule_id": rule_id,
                        "path": f"allowed/{name}", "line": 2}]
    assert line.encode() not in canonical_bytes({"findings": findings})


@pytest.mark.parametrize("shape", ["binary", "large", "unreadable", "symlink"])
def test_secret_scan_requires_review_for_unscannable_additions(
        repo_fixture: RepoFixture, monkeypatch: pytest.MonkeyPatch, shape: str) -> None:
    target = repo_fixture.packet_worktree / "allowed" / f"{shape}.dat"
    if shape == "binary":
        target.write_bytes(b"\xff\x00")
    elif shape == "large":
        target.write_text("too large\n", encoding="utf-8")
    elif shape == "unreadable":
        target.write_text("unreadable\n", encoding="utf-8")
        monkeypatch.setattr(workspace_evidence.os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")))
    else:
        target.symlink_to("base.txt")
    findings = scan_secret_like_additions(str(repo_fixture.packet_worktree), [{
        "path": f"allowed/{shape}.dat", "status": "added", "before_sha256": None,
        "after_sha256": None,
    }], maximum_bytes=1 if shape == "large" else 1048576)
    assert findings[0]["code"] == "SECRET_LIKE_DIFF_REVIEW_REQUIRED"
    assert findings[0]["path"] == f"allowed/{shape}.dat"


@pytest.mark.parametrize("change, expected", [
    ({"path": "outside.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_UNDECLARED"),
    ({"path": "forbidden/a.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_FORBIDDEN"),
    ({"path": "PLAN.md", "kind": "tracked"}, "ALLOWLIST_VIOLATION_GOVERNED"),
    ({"path": "../escape.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_ESCAPED"),
    ({"path": "allowed/link", "kind": "symlink"}, "ALLOWLIST_VIOLATION_SYMLINK"),
    ({"path": "allowed/module", "kind": "submodule"}, "ALLOWLIST_VIOLATION_SUBMODULE"),
])
def test_scope_matrix_rejects_every_disallowed_change(change: dict, expected: str) -> None:
    packet = {"writable_paths": ["allowed"], "forbidden_surfaces": ["forbidden"]}
    findings = workspace_evidence._scope_findings(packet, [change])
    assert findings == [{"code": expected, "path": change["path"]}]
    assert workspace_evidence._scope_findings(
        {"writable_paths": [], "forbidden_surfaces": []}, [{"path": "allowed/a.py", "kind": "tracked"}]
    ) == [{"code": "ALLOWLIST_VIOLATION_UNDECLARED", "path": "allowed/a.py"}]


@pytest.mark.parametrize("change, expected", [
    ({"path": "outside.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_UNDECLARED"),
    ({"path": "forbidden/a.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_FORBIDDEN"),
    ({"path": "PLAN.md", "kind": "tracked"}, "ALLOWLIST_VIOLATION_GOVERNED"),
    ({"path": "../escape.py", "kind": "tracked"}, "ALLOWLIST_VIOLATION_ESCAPED"),
    ({"path": "allowed/link", "kind": "symlink"}, "ALLOWLIST_VIOLATION_SYMLINK"),
    ({"path": "allowed/module", "kind": "submodule"}, "ALLOWLIST_VIOLATION_SUBMODULE"),
])
def test_build_postflight_denies_every_scope_violation(
        monkeypatch: pytest.MonkeyPatch, change: dict, expected: str) -> None:
    """The final artifact, not only the helper finding, disallows every scope breach."""
    identity = {"schema_version": 1, "repo_root": "/repo", "worktree_path": "/worktree",
                "common_dir": "/repo/.git", "branch": "refs/heads/codex/o4", "head": "a" * 40}
    baseline = {"worktree_identity": identity, "packet_snapshot": {"entries": []},
                "protected_snapshot": None}
    current = {"entries": [{
        "path": change["path"], "kind": change["kind"], "index_status": None,
        "worktree_status": None, "mode": "100644", "object_id": None, "content_sha256": None,
    }]}
    monkeypatch.setattr(workspace_evidence, "inspect_worktree", lambda *_args: identity)
    monkeypatch.setattr(workspace_evidence, "capture_snapshot", lambda *_args: current)
    monkeypatch.setattr(workspace_evidence, "_hydrate_before_digests", lambda *_args: None)
    monkeypatch.setattr(workspace_evidence, "_hydrate_mode_changes", lambda *_args: None)
    monkeypatch.setattr(workspace_evidence, "scan_secret_like_additions", lambda *_args: [])
    packet = {"packet_id": "o4-scope", "packet_sha256": "b" * 64,
              "writable_paths": ["allowed"], "forbidden_surfaces": ["forbidden"]}
    postflight = workspace_evidence.build_postflight(packet, "attempt-o4-scope-1", baseline, None)
    assert postflight["acceptance_allowed"] is False
    assert postflight["scope_findings"] == [{"code": expected, "path": change["path"]}]


def test_scope_violation_is_recorded_without_removing_worker_file(repo_fixture: RepoFixture) -> None:
    """Postflight rejects an out-of-scope addition but never mutates worker output."""
    identity = inspect_worktree(str(repo_fixture.root), str(repo_fixture.packet_worktree),
                                "codex/packet-a", repo_fixture.packet_revision)
    baseline = {"worktree_identity": identity,
                "packet_snapshot": capture_snapshot(str(repo_fixture.packet_worktree)),
                "protected_snapshot": None}
    outside = repo_fixture.packet_worktree / "outside" / "worker-output.py"
    outside.write_text("retained\n", encoding="utf-8")
    packet = {"packet_id": "o4-scope-preserve", "packet_sha256": "c" * 64,
              "writable_paths": ["allowed"], "forbidden_surfaces": []}
    postflight = workspace_evidence.build_postflight(
        packet, "attempt-o4-scope-preserve-1", baseline, None)
    assert postflight["acceptance_allowed"] is False
    assert any(item["path"] == "outside/worker-output.py"
               for item in postflight["scope_findings"])
    assert outside.read_text(encoding="utf-8") == "retained\n"


def test_protected_snapshot_preserves_preexisting_dirt_then_reports_new_drift(repo_fixture: RepoFixture) -> None:
    """Only changes after preflight trigger protected tracked/untracked findings."""
    protected = repo_fixture.root
    (protected / "allowed" / "base.txt").write_text("preexisting\n", encoding="utf-8")
    (protected / "preexisting-untracked.txt").write_text("preexisting\n", encoding="utf-8")
    baseline = {"protected_snapshot": {
        "worktree_path": str(protected), "snapshot": capture_snapshot(str(protected)),
    }}
    assert workspace_evidence._protected_findings(baseline) == []
    (protected / "allowed" / "base.txt").write_text("postflight\n", encoding="utf-8")
    (protected / "new-untracked.txt").write_text("new\n", encoding="utf-8")
    assert workspace_evidence._protected_findings(baseline) == [
        {"code": "PROTECTED_WORKTREE_CHANGED_MODIFIED", "path": "allowed/base.txt"},
        {"code": "PROTECTED_WORKTREE_CHANGED_ADDED", "path": "new-untracked.txt"},
    ]


def test_full_postflight_artifact_never_contains_literal_secret(repo_fixture: RepoFixture) -> None:
    """The canonical full artifact retains only secret finding metadata."""
    secret = "fixture-secret-must-not-persist"
    path = repo_fixture.packet_worktree / "allowed" / "new.py"
    path.write_text(f"API_KEY = '{secret}'\n", encoding="utf-8")
    identity = inspect_worktree(str(repo_fixture.root), str(repo_fixture.packet_worktree),
                                "codex/packet-a", repo_fixture.packet_revision)
    packet = {"packet_id": "o4-secret", "packet_sha256": "a" * 64,
              "writable_paths": ["allowed"], "forbidden_surfaces": []}
    baseline = {"worktree_identity": identity, "packet_snapshot": {"entries": []},
                "protected_snapshot": None}
    worker = {"changed_files": [{"path": "allowed/new.py", "status": "added",
                                  "before_sha256": None,
                                  "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
    postflight = workspace_evidence.build_postflight(packet, "attempt-o4-secret-1", baseline, worker)
    assert b"fixture-secret-must-not-persist" not in canonical_bytes(postflight)
