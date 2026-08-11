"""Conservative, mutation-free integration analysis for O4 packet artifacts."""

import os
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_coordinator.v1.workspace_evidence import _normalized_status_path, paths_overlap


_GIT_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


def _run_git(repo_root: str, argv: List[str]) -> subprocess.CompletedProcess:
    """Run one permitted read-only Git query with no shell or ambient config."""
    environment = dict(_GIT_ENVIRONMENT, PATH=os.environ.get("PATH", ""))
    return subprocess.run(
        ["git", *argv], cwd=repo_root, shell=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=10, env=environment, check=False,
    )


def _is_commit(repo_root: str, revision: str) -> Optional[bool]:
    """Return commit existence, or None when the Git command cannot be trusted."""
    try:
        completed = _run_git(repo_root, ["cat-file", "-e", f"{revision}^{{commit}}"])
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.returncode == 0


def _packet_paths(packet_changes: List[Dict[str, Any]]) -> Tuple[List[str], Set[str]]:
    """Extract exact normalized packet paths; invalid evidence is fail-closed."""
    if not isinstance(packet_changes, list):
        return [], {"INTEGRATION_INVALID_PATH"}
    paths: Set[str] = set()
    reasons: Set[str] = set()
    for change in packet_changes:
        path = change.get("path") if isinstance(change, dict) else None
        if not isinstance(path, str):
            reasons.add("INTEGRATION_INVALID_PATH")
            continue
        try:
            normalized = _normalized_status_path(path.encode("utf-8", "surrogateescape"))
        except Exception:
            reasons.add("INTEGRATION_INVALID_PATH")
            continue
        if normalized != path:
            reasons.add("INTEGRATION_INVALID_PATH")
            continue
        paths.add(normalized)
    return sorted(paths), reasons


def _base_paths(repo_root: str, starting_revision: str, integration_base: str) -> Tuple[List[str], Set[str]]:
    """Read changed paths from a known descendant base, preserving uncertainty."""
    try:
        completed = _run_git(repo_root, [
            "diff", "--name-only", "-z", f"{starting_revision}..{integration_base}",
        ])
    except (OSError, subprocess.SubprocessError):
        return [], {"INTEGRATION_COMMAND_UNCERTAIN"}
    if completed.returncode != 0:
        return [], {"INTEGRATION_COMMAND_UNCERTAIN"}
    paths: Set[str] = set()
    reasons: Set[str] = set()
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            paths.add(_normalized_status_path(raw))
        except Exception:
            reasons.add("INTEGRATION_INVALID_PATH")
    return sorted(paths), reasons


def _target_status(integration_target_path: Optional[str]) -> Tuple[Optional[str], str]:
    """Return canonical target identity and its observed read-only status."""
    if integration_target_path is None:
        return None, "NOT_SUPPLIED"
    if not isinstance(integration_target_path, str) or not integration_target_path:
        return None, "UNVERIFIABLE"
    canonical = os.path.realpath(integration_target_path)
    try:
        completed = _run_git(canonical, ["status", "--porcelain=v2", "-z"])
    except (OSError, subprocess.SubprocessError):
        return canonical, "UNVERIFIABLE"
    if completed.returncode != 0:
        return canonical, "UNVERIFIABLE"
    return canonical, "DIRTY" if completed.stdout else "CLEAN"


def analyze_integration(
    repo_root: str, starting_revision: str, integration_base: str,
    packet_changes: List[Dict[str, Any]], integration_target_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Assess a candidate integration using read-only Git evidence only.

    This function deliberately reports a candidate rather than performing any
    integration.  Any inability to establish the exact ancestry, paths, or
    target cleanliness remains a human decision.
    """
    packet_paths, reasons = _packet_paths(packet_changes)
    starting_exists = _is_commit(repo_root, starting_revision)
    base_exists = _is_commit(repo_root, integration_base)
    if starting_exists is None or base_exists is None:
        reasons.add("INTEGRATION_COMMAND_UNCERTAIN")
    elif not starting_exists or not base_exists:
        reasons.add("INTEGRATION_MISSING_OBJECT")

    base_paths: List[str] = []
    if not reasons.intersection({"INTEGRATION_COMMAND_UNCERTAIN", "INTEGRATION_MISSING_OBJECT"}):
        try:
            ancestry = _run_git(repo_root, [
                "merge-base", "--is-ancestor", starting_revision, integration_base,
            ])
        except (OSError, subprocess.SubprocessError):
            reasons.add("INTEGRATION_COMMAND_UNCERTAIN")
        else:
            if ancestry.returncode == 1:
                reasons.add("INTEGRATION_BASE_NOT_DESCENDANT")
            elif ancestry.returncode != 0:
                reasons.add("INTEGRATION_COMMAND_UNCERTAIN")
        if not reasons.intersection({"INTEGRATION_COMMAND_UNCERTAIN", "INTEGRATION_BASE_NOT_DESCENDANT"}):
            base_paths, base_reasons = _base_paths(repo_root, starting_revision, integration_base)
            reasons.update(base_reasons)
            for packet_path in packet_paths:
                for base_path in base_paths:
                    try:
                        if paths_overlap(packet_path, base_path):
                            reasons.add("INTEGRATION_CONFLICT_PATH_OVERLAP")
                    except Exception:
                        reasons.add("INTEGRATION_INVALID_PATH")

    target_path, target_status = _target_status(integration_target_path)
    if target_status == "UNVERIFIABLE":
        reasons.add("INTEGRATION_COMMAND_UNCERTAIN")
    elif target_status == "DIRTY":
        reasons.add("INTEGRATION_TARGET_DIRTY")

    reason_codes = sorted(reasons)
    return {
        "schema_version": 1,
        "starting_revision": starting_revision,
        "integration_base": integration_base,
        "packet_changed_paths": packet_paths,
        "integration_base_changed_paths": base_paths,
        "integration_target_path": target_path,
        "integration_target_status": target_status,
        "decision": "CLEAN_CANDIDATE" if not reason_codes else "HUMAN_REQUIRED",
        "reason_codes": reason_codes,
        "required_human_action": bool(reason_codes),
    }


def _o4_hashes(artifact: Dict[str, Any]) -> Tuple[str, str]:
    content_sha256 = compute_sha256(
        canonical_bytes(artifact, omit={"content_sha256", "artifact_sha256"})
    )
    with_content = dict(artifact)
    with_content["content_sha256"] = content_sha256
    return content_sha256, compute_sha256(canonical_bytes(with_content, omit={"artifact_sha256"}))


def build_integration_manifest(
    packet: Dict[str, Any], postflight: Dict[str, Any], analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble canonical, non-authorizing integration evidence from O4 facts."""
    if (postflight.get("packet_id") != packet.get("packet_id")
            or postflight.get("packet_sha256") != packet.get("packet_sha256")):
        raise ValueError("postflight packet identity disagrees with packet")
    content_sha256, artifact_sha256 = _o4_hashes(postflight)
    if (postflight.get("content_sha256") != content_sha256
            or postflight.get("artifact_sha256") != artifact_sha256):
        raise ValueError("postflight hashes disagree")
    identity = postflight.get("worktree_identity")
    expected_branch = "refs/heads/%s" % packet.get("worktree", {}).get("branch")
    if (not isinstance(identity, dict)
            or identity.get("branch") != expected_branch
            or identity.get("head") != packet.get("starting_revision")
            or os.path.realpath(str(identity.get("worktree_path", "")))
            != os.path.realpath(str(packet.get("worktree", {}).get("path", "")))):
        raise ValueError("postflight worktree identity disagrees with packet")
    if analysis.get("decision") not in {"CLEAN_CANDIDATE", "HUMAN_REQUIRED"}:
        raise ValueError("integration decision is invalid")
    if analysis.get("starting_revision") != packet.get("starting_revision"):
        raise ValueError("integration analysis starting revision disagrees with packet")
    target_path = analysis.get("integration_target_path")
    target_status = analysis.get("integration_target_status")
    if target_status not in {"NOT_SUPPLIED", "CLEAN", "DIRTY", "UNVERIFIABLE"}:
        raise ValueError("integration target status is invalid")
    if ((target_status == "NOT_SUPPLIED" and target_path is not None)
            or (target_path is None and target_status not in {"NOT_SUPPLIED", "UNVERIFIABLE"})
            or (target_path is not None and (not isinstance(target_path, str)
                                            or os.path.realpath(target_path) != target_path))):
        raise ValueError("integration target identity is not canonical")
    if (analysis.get("decision") == "CLEAN_CANDIDATE"
            and target_status in {"DIRTY", "UNVERIFIABLE"}):
        raise ValueError("integration target status cannot be clean candidate")
    evidence_ids = analysis.get("verification_evidence_ids")
    if (not isinstance(evidence_ids, list)
            or any(not isinstance(evidence_id, str) or not evidence_id for evidence_id in evidence_ids)
            or evidence_ids != sorted(set(evidence_ids))):
        raise ValueError("verification evidence must come from accepted replay evidence")
    replay = analysis.get("accepted_replay")
    if not isinstance(replay, dict) or set(replay) != {
        "replay_bundle_sha256", "verdict_sha256", "terminal_seal_sha256",
    }:
        raise ValueError("accepted replay evidence is missing")
    if any(not isinstance(value, str) or len(value) != 64 for value in replay.values()):
        raise ValueError("accepted replay evidence is invalid")
    derived_changes = postflight.get("derived_changes")
    if not isinstance(derived_changes, list):
        raise ValueError("postflight derived changes are invalid")
    derived_paths = [item.get("path") for item in derived_changes if isinstance(item, dict)]
    if (len(derived_paths) != len(derived_changes)
            or derived_paths != analysis.get("packet_changed_paths")):
        raise ValueError("postflight derived paths disagree with analysis")
    protected_findings = postflight.get("protected_findings", [])
    secret_findings = postflight.get("secret_findings", [])
    artifact: Dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": "integration_manifest",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "intent_id": postflight["intent_id"],
        "starting_revision": packet["starting_revision"],
        "integration_base": analysis["integration_base"],
        "integration_target_path": target_path,
        "integration_target_status": target_status,
        "worktree_identity": identity,
        "derived_changes": derived_changes,
        "verification_evidence_ids": evidence_ids,
        "protected_tree_result": "CLEAN" if not protected_findings else "HUMAN_REQUIRED",
        "secret_result": "CLEAN" if not secret_findings else "HUMAN_REQUIRED",
        "decision": analysis["decision"],
        "reason_codes": sorted(analysis.get("reason_codes", [])),
        "postflight": {"content_sha256": content_sha256, "artifact_sha256": artifact_sha256},
        "accepted_replay": replay,
        "required_human_action": bool(analysis.get("required_human_action"))
                                 or bool(protected_findings) or bool(secret_findings),
        "content_sha256": "",
        "artifact_sha256": "",
    }
    artifact["content_sha256"], artifact["artifact_sha256"] = _o4_hashes(artifact)
    return artifact


__all__ = ["analyze_integration", "build_integration_manifest"]
