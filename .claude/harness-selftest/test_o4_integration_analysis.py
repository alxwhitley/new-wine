"""O4 integration analysis tests using disposable local Git repositories."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.integration_analysis import (
    analyze_integration,
    build_integration_manifest,
)


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True,
        env={"PATH": os.environ["PATH"], "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1"},
    ).stdout.strip()


def _git_bytes(path: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=path, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ["PATH"], "LANG": "C", "GIT_CONFIG_NOSYSTEM": "1"},
    ).stdout


def _repository_fingerprint(path: Path) -> tuple:
    """Observable state that read-only analysis must never alter."""
    return (
        _git_bytes(path, "for-each-ref", "--format=%(refname) %(objectname)"),
        hashlib.sha256(_git_bytes(path, "ls-files", "-s", "-z")).hexdigest(),
        _git_bytes(path, "status", "--porcelain=v2", "-z"),
        _git(path, "count-objects", "-v"),
    )


@pytest.fixture
def integration_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "O4 Test")
    _git(repo, "config", "user.email", "o4@example.test")
    (repo / "README").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "root")
    root = _git(repo, "rev-parse", "HEAD")
    (repo / "allowed").mkdir()
    (repo / "allowed" / "a.py").write_text("base = 1\n", encoding="utf-8")
    (repo / "allowed" / "b.py").write_text("base = 1\n", encoding="utf-8")
    _git(repo, "add", "allowed")
    _git(repo, "commit", "-m", "base")
    starting = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-b", "codex/packet")
    (repo / "allowed" / "a.py").write_text("packet = 1\n", encoding="utf-8")
    _git(repo, "commit", "-am", "packet")

    _git(repo, "checkout", starting)
    _git(repo, "checkout", "-b", "integration-disjoint")
    (repo / "allowed" / "b.py").write_text("integration = 1\n", encoding="utf-8")
    _git(repo, "commit", "-am", "disjoint integration")
    disjoint = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", starting)
    _git(repo, "checkout", "-b", "integration-overlap")
    (repo / "allowed" / "a.py").write_text("integration = 2\n", encoding="utf-8")
    _git(repo, "commit", "-am", "overlap integration")
    overlap = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", root)
    _git(repo, "checkout", "-b", "divergent")
    (repo / "README").write_text("divergent\n", encoding="utf-8")
    _git(repo, "commit", "-am", "divergent")
    divergent = _git(repo, "rev-parse", "HEAD")
    return repo, starting, disjoint, overlap, divergent


def _assert_read_only(repo: Path, call) -> dict:
    before = _repository_fingerprint(repo)
    result = call()
    assert _repository_fingerprint(repo) == before
    return result


def test_analysis_accepts_disjoint_descendant_without_mutating_repository(integration_repo) -> None:
    """Fails if a disjoint descendant is treated as a merge or alters Git state."""
    repo, starting, disjoint, _overlap, _divergent = integration_repo
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, disjoint,
        [{"path": "allowed/a.py", "status": "modified", "before_sha256": "a" * 64,
          "after_sha256": "b" * 64}],
    ))
    assert result["decision"] == "CLEAN_CANDIDATE"
    assert result["reason_codes"] == []
    assert result["integration_base_changed_paths"] == ["allowed/b.py"]


def test_analysis_requires_human_for_overlapping_descendant_without_mutating_repository(integration_repo) -> None:
    """Fails if a base change can silently overwrite a packet's changed path."""
    repo, starting, _disjoint, overlap, _divergent = integration_repo
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, overlap, [{"path": "allowed/a.py"}],
    ))
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_codes"] == ["INTEGRATION_CONFLICT_PATH_OVERLAP"]


def test_analysis_requires_human_for_divergent_base_without_mutating_repository(integration_repo) -> None:
    """Fails if a non-descendant integration base is reported as safe."""
    repo, starting, _disjoint, _overlap, divergent = integration_repo
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, divergent, [{"path": "allowed/a.py"}],
    ))
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_codes"] == ["INTEGRATION_BASE_NOT_DESCENDANT"]


@pytest.mark.parametrize("starting, integration_base", [
    ("0" * 40, "0" * 40),
    ("not-an-object", "also-not-an-object"),
])
def test_analysis_requires_human_for_missing_git_objects_without_mutating_repository(
        integration_repo, starting: str, integration_base: str) -> None:
    """Fails if absent revisions are allowed through to an ambiguous Git operation."""
    repo, _real_start, _disjoint, _overlap, _divergent = integration_repo
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, integration_base, [{"path": "allowed/a.py"}],
    ))
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_codes"] == ["INTEGRATION_MISSING_OBJECT"]


def test_analysis_requires_human_for_dirty_target_without_mutating_repository(integration_repo, tmp_path: Path) -> None:
    """Fails if the prospective integration target already has uncommitted work."""
    repo, starting, disjoint, _overlap, _divergent = integration_repo
    target = tmp_path / "target"
    _git(repo, "worktree", "add", "-b", "integration-target", str(target), disjoint)
    (target / "allowed" / "target.py").write_text("dirty\n", encoding="utf-8")
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, disjoint, [{"path": "allowed/a.py"}], str(target),
    ))
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_codes"] == ["INTEGRATION_TARGET_DIRTY"]


def test_analysis_rejects_invalid_packet_change_path_without_mutating_repository(integration_repo) -> None:
    """Fails if unnormalized packet evidence reaches integration analysis."""
    repo, starting, disjoint, _overlap, _divergent = integration_repo
    result = _assert_read_only(repo, lambda: analyze_integration(
        str(repo), starting, disjoint, [{"path": "../outside.py"}],
    ))
    assert result["decision"] == "HUMAN_REQUIRED"
    assert result["reason_codes"] == ["INTEGRATION_INVALID_PATH"]


def test_integration_manifest_is_canonical_and_carries_postflight_authority() -> None:
    """Fails if an integration publication can omit the postflight's safety evidence."""
    packet = {
        "packet_id": "o4-integration", "packet_sha256": "a" * 64,
        "starting_revision": "b" * 40,
        "worktree": {"path": "/tmp/o4-worktree", "branch": "codex/o4-integration"},
    }
    postflight = {
        "packet_id": "o4-integration", "packet_sha256": "a" * 64,
        "intent_id": "attempt-o4-integration-1",
        "derived_changes": [{"path": "allowed/a.py", "status": "modified",
                              "before_sha256": "c" * 64, "after_sha256": "d" * 64}],
        "protected_findings": [], "secret_findings": [],
        "acceptance_allowed": True,
        "worktree_identity": {"repo_root": "/tmp", "worktree_path": "/tmp/o4-worktree",
                                "common_dir": "/tmp/.git", "branch": "refs/heads/codex/o4-integration",
                                "head": "b" * 40},
        "content_sha256": "", "artifact_sha256": "",
    }
    analysis = {
        "starting_revision": "b" * 40, "integration_base": "b" * 40,
        "integration_target_path": None, "integration_target_status": "NOT_SUPPLIED",
        "decision": "CLEAN_CANDIDATE",
        "reason_codes": [], "packet_changed_paths": ["allowed/a.py"],
        "integration_base_changed_paths": [],
        "verification_evidence_ids": ["verify-1", "verify-2"],
        "accepted_replay": {"replay_bundle_sha256": "e" * 64, "verdict_sha256": "f" * 64,
                            "terminal_seal_sha256": "0" * 64},
    }
    postflight["content_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"content_sha256", "artifact_sha256"})
    )
    postflight["artifact_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"artifact_sha256"})
    )
    artifact = build_integration_manifest(packet, postflight, analysis)
    assert artifact["verification_evidence_ids"] == ["verify-1", "verify-2"]
    assert artifact["protected_tree_result"] == "CLEAN"
    assert artifact["secret_result"] == "CLEAN"
    assert artifact["required_human_action"] is False
    assert artifact["content_sha256"] == compute_sha256(
        canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"})
    )
    assert artifact["artifact_sha256"] == compute_sha256(
        canonical_bytes(artifact, omit={"artifact_sha256"})
    )


def test_manifest_rejects_clean_decision_for_unverifiable_target() -> None:
    """Fails if target uncertainty can be represented as a clean integration candidate."""
    packet = {
        "packet_id": "o4-target-invariant", "packet_sha256": "a" * 64,
        "starting_revision": "b" * 40,
        "worktree": {"path": "/tmp/o4-target-invariant", "branch": "codex/o4-target-invariant"},
    }
    postflight = {
        "packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
        "intent_id": "attempt-o4-target-invariant-1", "derived_changes": [],
        "protected_findings": [], "secret_findings": [], "acceptance_allowed": True,
        "worktree_identity": {"repo_root": "/tmp", "worktree_path": packet["worktree"]["path"],
                                "common_dir": "/tmp/.git", "branch": "refs/heads/codex/o4-target-invariant",
                                "head": packet["starting_revision"]},
        "content_sha256": "", "artifact_sha256": "",
    }
    postflight["content_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"content_sha256", "artifact_sha256"})
    )
    postflight["artifact_sha256"] = compute_sha256(canonical_bytes(postflight, omit={"artifact_sha256"}))
    analysis = {
        "starting_revision": packet["starting_revision"], "integration_base": packet["starting_revision"],
        "integration_target_path": None, "integration_target_status": "UNVERIFIABLE",
        "packet_changed_paths": [], "decision": "CLEAN_CANDIDATE", "reason_codes": [],
        "verification_evidence_ids": [],
        "accepted_replay": {"replay_bundle_sha256": "c" * 64, "verdict_sha256": "d" * 64,
                            "terminal_seal_sha256": "e" * 64},
    }
    with pytest.raises(ValueError, match="target"):
        build_integration_manifest(packet, postflight, analysis)


def test_manifest_rejects_supplied_path_with_not_supplied_status() -> None:
    """Fails if a supplied target path can claim that no target was supplied."""
    packet = {
        "packet_id": "o4-target-inverse", "packet_sha256": "a" * 64,
        "starting_revision": "b" * 40,
        "worktree": {"path": "/tmp/o4-target-inverse", "branch": "codex/o4-target-inverse"},
    }
    postflight = {
        "packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
        "intent_id": "attempt-o4-target-inverse-1", "derived_changes": [],
        "protected_findings": [], "secret_findings": [], "acceptance_allowed": True,
        "worktree_identity": {"repo_root": "/tmp", "worktree_path": packet["worktree"]["path"],
                                "common_dir": "/tmp/.git",
                                "branch": "refs/heads/codex/o4-target-inverse",
                                "head": packet["starting_revision"]},
        "content_sha256": "", "artifact_sha256": "",
    }
    postflight["content_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"content_sha256", "artifact_sha256"})
    )
    postflight["artifact_sha256"] = compute_sha256(
        canonical_bytes(postflight, omit={"artifact_sha256"})
    )
    analysis = {
        "starting_revision": packet["starting_revision"],
        "integration_base": packet["starting_revision"],
        "integration_target_path": "/private/tmp/o4-target-inverse",
        "integration_target_status": "NOT_SUPPLIED",
        "packet_changed_paths": [], "decision": "HUMAN_REQUIRED", "reason_codes": [],
        "verification_evidence_ids": [],
        "accepted_replay": {"replay_bundle_sha256": "c" * 64,
                            "verdict_sha256": "d" * 64,
                            "terminal_seal_sha256": "e" * 64},
    }
    with pytest.raises(ValueError, match="target"):
        build_integration_manifest(packet, postflight, analysis)
