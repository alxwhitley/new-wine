"""O4 registered-worktree identity tests using disposable local repositories."""

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness_coordinator.v1 import workspace_evidence
from harness_coordinator.v1.workspace_evidence import (
    WorkspaceEvidenceError,
    capture_snapshot,
    inspect_worktree,
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
