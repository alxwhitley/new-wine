"""O2 replay bundle contract tests."""

import json
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.replay import validate_replay_bundle


def _trusted_contexts_for_bundle(bundle):
    packet = bundle["packet"]
    verdict = bundle["opus_verdict"]
    reviewer_session = verdict["reviewer"]["session_id"]
    trusted_reviewer_sessions = {reviewer_session}
    trusted_dependency_provenance = {}
    for dep in packet.get("dependency_ids", []):
        trusted_dependency_provenance[dep] = {
            "packet_sha256": compute_sha256(f"upstream-packet-{dep}".encode()),
            "result_sha256": compute_sha256(f"upstream-result-{dep}".encode()),
            "verdict_sha256": compute_sha256(f"upstream-verdict-{dep}".encode()),
            "bundle_sha256": compute_sha256(f"upstream-bundle-{dep}".encode()),
        }
    return trusted_dependency_provenance, trusted_reviewer_sessions


def _validate_bundle(bundle):
    trusted_dep, trusted_rev = _trusted_contexts_for_bundle(bundle)
    return validate_replay_bundle(bundle, trusted_dep, trusted_rev)


def _minimal_valid_packet():
    from harness_contracts.v1.packet import validate_packet
    packet = {
        "schema_version": 1,
        "packet_id": "pkt-o2-test-001",
        "objective": "Verify O2 replay",
        "dependency_ids": [],
        "lane": "kimi_implementation",
        "assigned_worker": {"worker_id": "kimi-1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "starting_revision": "a" * 40,
        "worktree": {"path": "/Users/alexwhitley/.codex/worktrees/75cf/newwine", "branch": "o2-test"},
        "writable_paths": ["scripts/harness_contracts/v1/packet.py"],
        "forbidden_surfaces": [],
        "required_context": [{"path": "PLAN.md", "sha256": "b" * 64}],
        "premise_checks": [{"check_id": "ck-1", "command_id": "cmd-read-plan", "expected": "present"}],
        "acceptance_criteria": [
            {"criterion_id": "ac-1", "statement": "Tests pass", "required_evidence_ids": ["ev-verify"]}
        ],
        "verification_commands": [
            {
                "command_id": "cmd-verify",
                "argv": ["python3", "-m", "pytest", "test_o2_packet_contract.py"],
                "cwd": ".claude/harness-selftest",
                "timeout_seconds": 60,
                "expected_exit_code": 0,
                "expected_evidence_ids": ["ev-verify"],
            }
        ],
        "budgets": {"max_turns": 10, "wall_clock_seconds": 300, "retry_limit": 1, "max_output_bytes": 1000000, "cost_class": "low", "allowance_limit": 100},
        "network_policy": "denied",
        "checkpoint_artifacts": [{"artifact_id": "art-1", "path": "scripts/harness_contracts/v1/__init__.py", "required_for_fallback": True}],
        "rollback": {"method": "git_reset", "allowed_commands": [{"argv": ["git", "checkout", "--", "scripts/harness_contracts/"], "cwd": "."}]},
        "human_stop_conditions": [],
        "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
    }
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


def _minimal_valid_worker_result(packet):
    result = {
        "schema_version": 1,
        "result_id": "res-o2-test-001",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "attempt": 1,
        "worker": {"worker_id": "kimi-1", "session_id": "sess-kimi-001", "lane": "kimi_implementation", "provider": "opencode", "model": "kimi-k2.7-code"},
        "started_at": "2026-08-09T12:00:00Z",
        "finished_at": "2026-08-09T12:05:00Z",
        "starting_revision": packet["starting_revision"],
        "ending_revision": "d" * 40,
        "outcome": "COMPLETED",
        "changed_files": [
            {"path": "scripts/harness_contracts/v1/packet.py", "status": "modified", "before_sha256": "e" * 64, "after_sha256": "f" * 64}
        ],
        "commands": [
            {
                "command_id": "cmd-verify",
                "argv": ["python3", "-m", "pytest", "test_o2_packet_contract.py"],
                "cwd": ".claude/harness-selftest",
                "timestamps": {"started_at": "2026-08-09T12:01:00Z", "finished_at": "2026-08-09T12:02:00Z"},
                "exit_code": 0,
                "outcome": "PASSED",
                "stdout_sha256": "0" * 64,
                "stderr_sha256": "1" * 64,
            }
        ],
        "evidence": [
            {"evidence_id": "ev-verify", "kind": "verification", "criterion_ids": ["ac-1"], "command_id": "cmd-verify", "artifact_path": None, "artifact_sha256": None, "summary": "Tests passed"},
            {"evidence_id": "ev-premise", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "Premise holds"},
        ],
        "criteria": [{"criterion_id": "ac-1", "status": "SATISFIED", "evidence_ids": ["ev-verify"]}],
        "checkpoints": [{"artifact_id": "art-1", "path": "scripts/harness_contracts/v1/__init__.py", "sha256": "0" * 64}],
        "remaining_criterion_ids": [],
        "fallback": None,
        "human_required_reasons": [],
        "budgets": {"turns_used": 5, "output_bytes": 1024, "retry_count": 0, "allowance_used": "5"},
    }
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    return result


def _minimal_valid_verdict(packet, worker_result):
    verdict = {
        "schema_version": 1,
        "verdict_id": "verdict-o2-test-001",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "result_id": worker_result["result_id"],
        "result_sha256": worker_result["result_sha256"],
        "reviewer": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
        "reviewed_at": "2026-08-09T12:10:00Z",
        "verdict": "ACCEPT",
        "criterion_findings": [
            {"criterion_id": "ac-1", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "All checks passed"}
        ],
        "global_findings": [
            {"rule_id": "premise", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Premise verified"},
            {"rule_id": "repo_only_boundary", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "No production writes"},
            {"rule_id": "allowlist_scope", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Scope respected"},
            {"rule_id": "changed_manifest", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Changed files declared"},
            {"rule_id": "command_integrity", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Commands match"},
            {"rule_id": "batch_reconciliation", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Reconciled"},
            {"rule_id": "pre_batch", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Pre-batch done"},
            {"rule_id": "migration_comment", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Migration comments OK"},
            {"rule_id": "n_plus_one", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "No N+1"},
            {"rule_id": "reuse_path", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "No reuse path issues"},
            {"rule_id": "governed_records", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Governed records untouched"},
            {"rule_id": "reviewer_independence", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Reviewer independent"},
        ],
        "required_corrections": [],
        "human_decisions_required": [],
        "next_state": "ACCEPTED",
        "integration_revision": packet["starting_revision"],
    }
    verdict["verdict_sha256"] = compute_sha256(canonical_bytes(verdict, omit={"verdict_sha256"}))
    return verdict


def _minimal_valid_bundle():
    packet = _minimal_valid_packet()
    worker_result = _minimal_valid_worker_result(packet)
    verdict = _minimal_valid_verdict(packet, worker_result)
    bundle = {
        "schema_version": 1,
        "packet": packet,
        "prior_state_event": {"from_state": "REVIEW", "to_state": "ACCEPTED", "event_at": "2026-08-09T12:10:01Z"},
        "dependency_states": [],
        "worker_result": worker_result,
        "opus_verdict": verdict,
        "validator_version": "1",
    }
    bundle["bundle_sha256"] = compute_sha256(canonical_bytes(bundle, omit={"bundle_sha256"}))
    return bundle


_WINDOWS_ABSOLUTE_PATHS = [
    r"\outside\owned.py",
    r"C:\outside\owned.py",
    "C:/outside/owned.py",
    r"\\server\share\owned.py",
]


class TestWindowsAbsolutePathReplayRejection(unittest.TestCase):
    """Windows-style absolute paths must be rejected before normalization on every worker path surface in a fully rehashed replay bundle."""

    def _rehash_bundle(self, bundle):
        bundle["worker_result"]["result_sha256"] = compute_sha256(
            canonical_bytes(bundle["worker_result"], omit={"result_sha256"})
        )
        bundle["bundle_sha256"] = compute_sha256(
            canonical_bytes(bundle, omit={"bundle_sha256"})
        )

    def _assert_path_not_relative(self, bundle):
        result = _validate_bundle(bundle)
        self.assertFalse(result["valid"], f"Expected invalid, got {result}")
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("PATH_NOT_RELATIVE", codes)

    def test_changed_file_path_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                bundle = _minimal_valid_bundle()
                bundle["worker_result"]["changed_files"][0]["path"] = path
                self._rehash_bundle(bundle)
                self._assert_path_not_relative(bundle)

    def test_command_cwd_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                bundle = _minimal_valid_bundle()
                bundle["worker_result"]["commands"][0]["cwd"] = path
                self._rehash_bundle(bundle)
                self._assert_path_not_relative(bundle)

    def test_evidence_artifact_path_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                bundle = _minimal_valid_bundle()
                bundle["worker_result"]["evidence"][0]["artifact_path"] = path
                self._rehash_bundle(bundle)
                self._assert_path_not_relative(bundle)

    def test_checkpoint_path_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                bundle = _minimal_valid_bundle()
                bundle["worker_result"]["checkpoints"][0]["path"] = path
                self._rehash_bundle(bundle)
                self._assert_path_not_relative(bundle)

    def test_packet_writable_path_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                bundle = _minimal_valid_bundle()
                bundle["packet"]["writable_paths"] = [path]
                bundle["packet"]["packet_sha256"] = compute_sha256(
                    canonical_bytes(bundle["packet"], omit={"packet_sha256"})
                )
                self._rehash_bundle(bundle)
                self._assert_path_not_relative(bundle)


class TestReplayBundleValidation(unittest.TestCase):
    def test_valid_bundle_passes(self):
        bundle = _minimal_valid_bundle()
        result = _validate_bundle(bundle)
        self.assertTrue(result["valid"], result["errors"])

    def test_bundle_hash_tamper_fails(self):
        bundle = _minimal_valid_bundle()
        bundle["validator_version"] = "2"
        result = _validate_bundle(bundle)
        self.assertFalse(result["valid"])
        self.assertIn("EVIDENCE_HASH_MISMATCH", [e["code"] for e in result["errors"]])

    def test_key_order_invariance(self):
        bundle = _minimal_valid_bundle()
        reordered = json.loads(json.dumps(bundle, sort_keys=False))
        first = _validate_bundle(bundle)
        second = _validate_bundle(reordered)
        self.assertEqual(first["valid"], second["valid"])
        self.assertEqual(first["errors"], second["errors"])

    def test_mismatched_packet_id_fails(self):
        bundle = _minimal_valid_bundle()
        bundle["worker_result"]["packet_id"] = "different"
        bundle["bundle_sha256"] = compute_sha256(canonical_bytes(bundle, omit={"bundle_sha256"}))
        result = _validate_bundle(bundle)
        self.assertFalse(result["valid"])
        self.assertIn("REVISION_MISMATCH", [e["code"] for e in result["errors"]])

    def test_mismatched_result_id_fails(self):
        bundle = _minimal_valid_bundle()
        bundle["opus_verdict"]["result_id"] = "different"
        bundle["bundle_sha256"] = compute_sha256(canonical_bytes(bundle, omit={"bundle_sha256"}))
        result = _validate_bundle(bundle)
        self.assertFalse(result["valid"])
        self.assertIn("REVISION_MISMATCH", [e["code"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
