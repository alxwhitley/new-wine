"""O2 contract adversarial tests.

Validate the strict machine-readable packet/worker-result/verdict/replay
contracts defined for PLAN.md O2.  Every test below first constructs a
near-valid object, then mutates exactly the field under attack and asserts
that the validator rejects it with a deterministic, well-formed error.
"""

import copy
import hashlib
import json
import os
import sys
import unittest

# Repo root is two levels up from this file.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.join(REPO_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet
from harness_contracts.v1.replay import validate_replay_bundle
from harness_contracts.v1.transition import validate_transition
from harness_contracts.v1.verdict import validate_verdict
from harness_contracts.v1.worker_result import validate_worker_result


ZERO_SHA256 = "0" * 64
ONE_SHA256 = "1" * 64
A_SHA256 = "a" * 64
B_SHA256 = "b" * 64
REVISION_A = "a" * 40
REVISION_B = "b" * 40


def _self_hash(obj, omit):
    return compute_sha256(canonical_bytes(obj, omit=omit))


def _make_packet(**overrides):
    obj = {
        "schema_version": 1,
        "packet_id": "pkt-1",
        "objective": "Implement O2 contract",
        "dependency_ids": [],
        "lane": "kimi_implementation",
        "assigned_worker": {
            "worker_id": "kimi-worker-1",
            "provider": "kimi",
            "model": "kimi-k2.7-code",
        },
        "starting_revision": REVISION_A,
        "worktree": {"path": "/tmp/wt-1", "branch": "o2/pkt-1"},
        "writable_paths": ["scripts/harness_contracts/v1/packet.py"],
        "forbidden_surfaces": [],
        "required_context": [{"path": "PLAN.md", "sha256": A_SHA256}],
        "premise_checks": [
            {"check_id": "premise-1", "command_id": "cmd-p1", "expected": "ok"},
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "crit-1",
                "statement": "Packet validates",
                "required_evidence_ids": ["ev-accept-1"],
            },
        ],
        "verification_commands": [
            {
                "command_id": "cmd-1",
                "argv": ["python", "-m", "pytest"],
                "cwd": ".",
                "timeout_seconds": 60,
                "expected_exit_code": 0,
                "expected_evidence_ids": ["ev-cmd-1"],
            },
        ],
        "budgets": {
            "max_turns": 20,
            "wall_clock_seconds": 600,
            "retry_limit": 2,
            "max_output_bytes": 1_000_000,
            "cost_class": "low",
            "allowance_limit": 5,
        },
        "network_policy": "denied",
        "checkpoint_artifacts": [
            {"artifact_id": "cp-1", "path": "checkpoints/cp-1.json", "required_for_fallback": False},
        ],
        "rollback": {
            "method": "git checkout",
            "allowed_commands": [{"argv": ["git", "checkout", "--", "."], "cwd": "."}],
        },
        "human_stop_conditions": ["scope creep"],
        "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "opus-1", "model": "claude-opus-5"},
        "packet_sha256": "",
    }
    obj.update(overrides)
    obj["packet_sha256"] = _self_hash(obj, {"packet_sha256"})
    return obj


def _make_worker_result(packet=None, **overrides):
    packet = packet or _make_packet()
    worker = copy.deepcopy(packet["assigned_worker"])
    worker["lane"] = packet["lane"]
    worker["session_id"] = "sess-kimi-001"
    obj = {
        "schema_version": 1,
        "result_id": "res-1",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "attempt": 1,
        "worker": worker,
        "started_at": "2026-08-09T00:00:00Z",
        "finished_at": "2026-08-09T00:01:00Z",
        "starting_revision": packet["starting_revision"],
        "ending_revision": REVISION_B,
        "outcome": "COMPLETED",
        "changed_files": [
            {
                "path": "scripts/harness_contracts/v1/packet.py",
                "status": "modified",
                "before_sha256": A_SHA256,
                "after_sha256": B_SHA256,
            },
        ],
        "commands": [
            {
                "command_id": "cmd-1",
                "argv": ["python", "-m", "pytest"],
                "cwd": ".",
                "timestamps": {
                    "started_at": "2026-08-09T00:00:10Z",
                    "finished_at": "2026-08-09T00:00:20Z",
                },
                "exit_code": 0,
                "outcome": "PASSED",
                "stdout_sha256": A_SHA256,
                "stderr_sha256": ZERO_SHA256,
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev-accept-1",
                "kind": "acceptance",
                "criterion_ids": ["crit-1"],
                "command_id": None,
                "artifact_path": None,
                "artifact_sha256": None,
                "summary": "Criterion met",
            },
            {
                "evidence_id": "ev-cmd-1",
                "kind": "verification",
                "criterion_ids": [],
                "command_id": "cmd-1",
                "artifact_path": None,
                "artifact_sha256": None,
                "summary": "Command passed",
            },
            {
                "evidence_id": "ev-premise-1",
                "kind": "premise",
                "criterion_ids": [],
                "command_id": None,
                "artifact_path": None,
                "artifact_sha256": None,
                "summary": "Premise holds",
            },
        ],
        "criteria": [
            {
                "criterion_id": "crit-1",
                "status": "SATISFIED",
                "evidence_ids": ["ev-accept-1"],
            },
        ],
        "checkpoints": [
            {
                "artifact_id": "cp-1",
                "path": "checkpoints/cp-1.json",
                "sha256": A_SHA256,
            },
        ],
        "remaining_criterion_ids": [],
        "fallback": None,
        "human_required_reasons": [],
        "budgets": {"turns_used": 5, "output_bytes": 1024, "retry_count": 0, "allowance_used": "5"},
        "result_sha256": "",
    }
    obj.update(overrides)
    obj["result_sha256"] = _self_hash(obj, {"result_sha256"})
    return obj


def _make_verdict(packet=None, worker_result=None, **overrides):
    packet = packet or _make_packet()
    worker_result = worker_result or _make_worker_result(packet)
    obj = {
        "schema_version": 1,
        "verdict_id": "vd-1",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "result_id": worker_result["result_id"],
        "result_sha256": worker_result["result_sha256"],
        "reviewer": {"role": "opus_judgment", "session_id": "opus-reviewer-1", "model": "claude-opus-5"},
        "reviewed_at": "2026-08-09T00:02:00Z",
        "verdict": "ACCEPT",
        "criterion_findings": [
            {
                "criterion_id": "crit-1",
                "finding": "PASS",
                "evidence_ids": ["ev-accept-1"],
                "reason": "Criterion satisfied with evidence",
            },
        ],
        "global_findings": [
            {"rule_id": rule, "finding": "PASS", "evidence_ids": ["ev-premise-1"], "reason": "ok"}
            for rule in [
                "premise",
                "repo_only_boundary",
                "allowlist_scope",
                "changed_manifest",
                "command_integrity",
                "batch_reconciliation",
                "pre_batch",
                "migration_comment",
                "n_plus_one",
                "reuse_path",
                "governed_records",
                "reviewer_independence",
            ]
        ],
        "required_corrections": [],
        "human_decisions_required": [],
        "next_state": "ACCEPTED",
        "integration_revision": REVISION_B,
        "verdict_sha256": "",
    }
    obj.update(overrides)
    obj["verdict_sha256"] = _self_hash(obj, {"verdict_sha256"})
    return obj


def _trusted_contexts_for_bundle(bundle):
    """Return trusted external contexts required by validate_replay_bundle."""
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
    """Validate a bundle with the trusted external contexts it requires."""
    trusted_dep, trusted_rev = _trusted_contexts_for_bundle(bundle)
    return validate_replay_bundle(bundle, trusted_dep, trusted_rev)


def _make_bundle(packet=None, worker_result=None, verdict=None, **overrides):
    packet = packet or _make_packet()
    worker_result = worker_result or _make_worker_result(packet)
    verdict = verdict or _make_verdict(packet, worker_result)
    obj = {
        "schema_version": 1,
        "packet": packet,
        "prior_state_event": {
            "from_state": "REVIEW",
            "to_state": verdict["next_state"],
            "event_at": "2026-08-09T00:02:30Z",
        },
        "dependency_states": [],
        "worker_result": worker_result,
        "opus_verdict": verdict,
        "validator_version": "1",
        "bundle_sha256": "",
    }
    obj.update(overrides)
    obj["bundle_sha256"] = _self_hash(obj, {"bundle_sha256"})
    return obj


def _assert_invalid(test, result, code=None, path=None):
    test.assertFalse(result["valid"], f"Expected invalid result, got {result}")
    if code:
        codes = {e["code"] for e in result["errors"]}
        test.assertIn(code, codes, f"Expected error code {code} in {result['errors']}")
    if path:
        paths = {e["path"] for e in result["errors"]}
        test.assertIn(path, paths, f"Expected error path {path} in {result['errors']}")


class TestCanonicalHash(unittest.TestCase):
    def test_hash_stable_across_key_order(self):
        a = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
        b = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))
        self.assertEqual(compute_sha256(canonical_bytes(a)), compute_sha256(canonical_bytes(b)))


class TestPacketBase(unittest.TestCase):
    def test_valid_packet(self):
        result = validate_packet(_make_packet())
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_field(self):
        p = _make_packet()
        del p["objective"]
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        _assert_invalid(self, validate_packet(p), "MISSING_FIELD", "/objective")

    def test_unknown_field(self):
        p = _make_packet(extra_field="x")
        _assert_invalid(self, validate_packet(p), "UNKNOWN_FIELD", "/extra_field")

    def test_empty_string_rejected(self):
        p = _make_packet(objective="   ")
        _assert_invalid(self, validate_packet(p), "INVALID_VALUE", "/objective")

    def test_dependency_ids_may_be_empty(self):
        p = _make_packet(dependency_ids=[])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        self.assertTrue(validate_packet(p)["valid"])


class TestPacketSelfDependency(unittest.TestCase):
    def test_self_dependency_rejected(self):
        p = _make_packet(packet_id="pkt-1", dependency_ids=["pkt-1"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        _assert_invalid(self, validate_packet(p), "SELF_DEPENDENCY", "/dependency_ids/0")


class TestPacketDependencyStates(unittest.TestCase):
    def test_unknown_dependency_rejected_with_context(self):
        p = _make_packet(packet_id="pkt-1", dependency_ids=["pkt-0"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        result = validate_packet(p, dependency_states={})
        _assert_invalid(self, result, "UNKNOWN_DEPENDENCY", "/dependency_ids/0")

    def test_not_accepted_dependency_rejected(self):
        p = _make_packet(packet_id="pkt-1", dependency_ids=["pkt-0"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        result = validate_packet(p, dependency_states={"pkt-0": "READY"})
        _assert_invalid(self, result, "DEPENDENCY_NOT_ACCEPTED", "/dependency_ids/0")

    def test_accepted_dependency_allowed(self):
        p = _make_packet(packet_id="pkt-1", dependency_ids=["pkt-0"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        result = validate_packet(p, dependency_states={"pkt-0": "ACCEPTED"})
        self.assertTrue(result["valid"], result["errors"])

    def test_dependency_context_is_optional(self):
        p = _make_packet(packet_id="pkt-1", dependency_ids=["pkt-0"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        # Without context, dependency state cannot be checked; packet is structurally valid.
        result = validate_packet(p)
        self.assertTrue(result["valid"], result["errors"])


class TestPacketAuthority(unittest.TestCase):
    def test_opus_lane_for_implementation_packet_rejected(self):
        p = _make_packet(lane="opus_judgment")
        _assert_invalid(self, validate_packet(p), "FORBIDDEN_AUTHORITY", "/lane")

    def test_replay_worker_lane_must_match_packet_lane(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["lane"] = "sonnet_implementation"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/lane")

    def test_replay_worker_provider_must_match_packet(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["provider"] = "other"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/provider")

    def test_replay_worker_model_must_match_packet(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["model"] = "other"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/model")


class TestPacketBudgets(unittest.TestCase):
    def test_zero_max_turns_rejected(self):
        p = _make_packet()
        p["budgets"]["max_turns"] = 0
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        _assert_invalid(self, validate_packet(p), "INVALID_VALUE", "/budgets/max_turns")

    def test_negative_wall_clock_rejected(self):
        p = _make_packet()
        p["budgets"]["wall_clock_seconds"] = -1
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        _assert_invalid(self, validate_packet(p), "INVALID_VALUE", "/budgets/wall_clock_seconds")

    def test_bool_as_int_rejected(self):
        p = _make_packet()
        p["budgets"]["retry_limit"] = True
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        _assert_invalid(self, validate_packet(p), "INVALID_TYPE", "/budgets/retry_limit")


class TestPacketPaths(unittest.TestCase):
    def test_governed_path_in_writable_paths_rejected(self):
        p = _make_packet(writable_paths=["CLAUDE.md"])
        _assert_invalid(self, validate_packet(p), "GOVERNED_PATH", "/writable_paths/0")

    def test_governed_path_in_forbidden_surfaces_rejected(self):
        p = _make_packet(forbidden_surfaces=["PLAN.md"])
        _assert_invalid(self, validate_packet(p), "GOVERNED_PATH", "/forbidden_surfaces/0")

    def test_ancestor_descendant_overlap_rejected(self):
        p = _make_packet(writable_paths=["scripts/harness_contracts", "scripts/harness_contracts/v1/packet.py"])
        _assert_invalid(self, validate_packet(p), "PATH_OVERLAP", "/writable_paths")

    def test_writable_forbidden_overlap_rejected(self):
        p = _make_packet(writable_paths=["scripts/a.py"], forbidden_surfaces=["scripts/a.py"])
        _assert_invalid(self, validate_packet(p), "PATH_OVERLAP", "/writable_paths")

    def test_path_escape_rejected(self):
        p = _make_packet(writable_paths=["../escape.py"])
        _assert_invalid(self, validate_packet(p), "PATH_ESCAPE", "/writable_paths/0")


class TestWorkerResultBase(unittest.TestCase):
    def test_valid_worker_result(self):
        p = _make_packet()
        r = _make_worker_result(p)
        result = validate_worker_result(r)
        self.assertTrue(result["valid"], result["errors"])

    def test_completed_requires_all_commands_passed(self):
        p = _make_packet()
        r = _make_worker_result(p)
        r["commands"][0]["outcome"] = "FAILED"
        r["result_sha256"] = _self_hash(r, {"result_sha256"})
        _assert_invalid(self, validate_worker_result(r), "COMMAND_FAILED", "/commands/0/outcome")

    def test_completed_requires_no_remaining_criteria(self):
        p = _make_packet()
        r = _make_worker_result(p, remaining_criterion_ids=["crit-1"])
        _assert_invalid(self, validate_worker_result(r), "INVALID_VALUE", "/remaining_criterion_ids")

    def test_checkpointed_requires_fallback(self):
        p = _make_packet()
        r = _make_worker_result(p, outcome="CHECKPOINTED")
        _assert_invalid(self, validate_worker_result(r), "CHECKPOINT_INCOMPLETE", "/fallback")

    def test_checkpointed_requires_remaining_criteria(self):
        p = _make_packet()
        p["acceptance_criteria"].append({
            "criterion_id": "crit-2",
            "statement": "Second criterion",
            "required_evidence_ids": ["ev-accept-2"],
        })
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            outcome="CHECKPOINTED",
            fallback={
                "reason": "confirmed_quota_exhaustion",
                "provider_evidence_id": "ev-quota-1",
                "reassign_to": "sonnet_implementation",
            },
            criteria=[
                {
                    "criterion_id": "crit-1",
                    "status": "SATISFIED",
                    "evidence_ids": ["ev-accept-1"],
                },
            ],
            remaining_criterion_ids=["crit-2"],
        )
        r["result_sha256"] = _self_hash(r, {"result_sha256"})
        result = validate_worker_result(r)
        self.assertTrue(result["valid"], result["errors"])


class TestVerdictBase(unittest.TestCase):
    def test_valid_verdict(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        result = validate_verdict(v)
        self.assertTrue(result["valid"], result["errors"])

    def test_accept_requires_pass_findings(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, criterion_findings=[
            {"criterion_id": "crit-1", "finding": "FAIL", "evidence_ids": ["ev-accept-1"], "reason": "nope"},
        ])
        _assert_invalid(self, validate_verdict(v), "ACCEPTANCE_UNSATISFIED", "/criterion_findings/0/finding")

    def test_accept_requires_global_pass_or_na(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        v["global_findings"][0]["finding"] = "FAIL"
        v["verdict_sha256"] = _self_hash(v, {"verdict_sha256"})
        _assert_invalid(self, validate_verdict(v), "ACCEPTANCE_UNSATISFIED", "/global_findings/0/finding")

    def test_accept_next_state_must_be_accepted(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, next_state="READY")
        _assert_invalid(self, validate_verdict(v), "INVALID_TRANSITION", "/next_state")

    def test_revise_next_state_must_be_revise(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, verdict="REVISE", next_state="ACCEPTED", required_corrections=["fix it"])
        _assert_invalid(self, validate_verdict(v), "INVALID_TRANSITION", "/next_state")

    def test_revise_requires_corrections(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, verdict="REVISE", next_state="REVISE", required_corrections=[])
        _assert_invalid(self, validate_verdict(v), "ACCEPTANCE_UNSATISFIED", "/required_corrections")

    def test_quarantine_next_state_must_be_quarantined(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, verdict="QUARANTINE", next_state="ACCEPTED")
        _assert_invalid(self, validate_verdict(v), "INVALID_TRANSITION", "/next_state")

    def test_human_required_next_state_must_be_human_required(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, verdict="HUMAN_REQUIRED", next_state="ACCEPTED", human_decisions_required=[])
        _assert_invalid(self, validate_verdict(v), "INVALID_TRANSITION", "/next_state")

    def test_human_required_requires_decisions(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, verdict="HUMAN_REQUIRED", next_state="HUMAN_REQUIRED", human_decisions_required=[])
        _assert_invalid(self, validate_verdict(v), "ACCEPTANCE_UNSATISFIED", "/human_decisions_required")


class TestReplayCrossObject(unittest.TestCase):
    def test_valid_bundle(self):
        b = _make_bundle()
        result = _validate_bundle(b)
        self.assertTrue(result["valid"], result["errors"])

    def test_worker_lane_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["lane"] = "sonnet_implementation"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/lane")

    def test_worker_provider_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["provider"] = "other"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/provider")

    def test_worker_model_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["worker"]["model"] = "other"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/worker/model")

    def test_starting_revision_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["starting_revision"] = "b" * 40
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "REVISION_MISMATCH", "/worker_result/starting_revision")

    def test_undeclared_changed_file_rejected(self):
        b = _make_bundle()
        b["worker_result"]["changed_files"].append({
            "path": "scripts/secret.py",
            "status": "added",
            "before_sha256": None,
            "after_sha256": A_SHA256,
        })
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "CHANGED_FILE_UNDECLARED", "/worker_result/changed_files/1/path")

    def test_command_argv_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["argv"] = ["python", "-m", "unittest"]
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "COMMAND_MISMATCH", "/worker_result/commands/0/argv")

    def test_command_cwd_mismatch_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["cwd"] = "tests"
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "COMMAND_MISMATCH", "/worker_result/commands/0/cwd")

    def test_command_expected_exit_mismatch_rejected(self):
        b = _make_bundle()
        b["packet"]["verification_commands"][0]["expected_exit_code"] = 1
        b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "COMMAND_MISMATCH", "/worker_result/commands/0/exit_code")

    def test_missing_verification_command_rejected(self):
        b = _make_bundle()
        b["packet"]["verification_commands"].append({
            "command_id": "cmd-missing",
            "argv": ["ls"],
            "cwd": ".",
            "timeout_seconds": 10,
            "expected_exit_code": 0,
            "expected_evidence_ids": [],
        })
        b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "COMMAND_NOT_RUN", "/worker_result/commands")

    def test_criterion_not_in_packet_rejected(self):
        b = _make_bundle()
        b["worker_result"]["criteria"].append({
            "criterion_id": "crit-unknown",
            "status": "SATISFIED",
            "evidence_ids": ["ev-accept-1"],
        })
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED", "/worker_result/criteria")

    def test_required_evidence_missing_from_result_rejected(self):
        b = _make_bundle()
        b["packet"]["acceptance_criteria"][0]["required_evidence_ids"].append("ev-missing")
        b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING", "/worker_result/evidence")

    def test_attempt_exceeds_retry_limit_rejected(self):
        b = _make_bundle()
        b["worker_result"]["attempt"] = 5
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "BUDGET_EXCEEDED", "/worker_result/attempt")

    def test_invalid_fallback_when_not_allowed_rejected(self):
        b = _make_bundle()
        b["packet"]["sonnet_reassignment_allowed"] = False
        b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
        b["worker_result"]["outcome"] = "CHECKPOINTED"
        b["worker_result"]["fallback"] = {
            "reason": "confirmed_quota_exhaustion",
            "provider_evidence_id": "ev-quota-1",
            "reassign_to": "sonnet_implementation",
        }
        b["worker_result"]["remaining_criterion_ids"] = ["crit-1"]
        b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "INVALID_FALLBACK", "/worker_result/fallback")

    def test_verdict_evidence_not_in_result_rejected(self):
        b = _make_bundle()
        b["opus_verdict"]["global_findings"][0]["evidence_ids"].append("ev-missing")
        b["opus_verdict"]["verdict_sha256"] = _self_hash(b["opus_verdict"], {"verdict_sha256"})
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING", "/opus_verdict/global_findings/0/evidence_ids/1")

    def test_prior_state_destination_must_match_next_state(self):
        b = _make_bundle()
        b["prior_state_event"]["to_state"] = "QUARANTINED"
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "INVALID_TRANSITION", "/prior_state_event/to_state")


class TestVerdictAcceptEvidence(unittest.TestCase):
    def test_accept_rejects_empty_criterion_evidence_ids(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, criterion_findings=[
            {"criterion_id": "crit-1", "finding": "PASS", "evidence_ids": [], "reason": "no evidence"},
        ])
        _assert_invalid(self, validate_verdict(v), "EVIDENCE_MISSING", "/criterion_findings/0/evidence_ids")

    def test_accept_rejects_empty_global_evidence_ids(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        v["global_findings"][0]["evidence_ids"] = []
        v["verdict_sha256"] = _self_hash(v, {"verdict_sha256"})
        _assert_invalid(self, validate_verdict(v), "EVIDENCE_MISSING", "/global_findings/0/evidence_ids")

    def test_completed_satified_requires_evidence(self):
        p = _make_packet()
        r = _make_worker_result(p)
        r["criteria"][0]["evidence_ids"] = []
        r["result_sha256"] = _self_hash(r, {"result_sha256"})
        v = _make_verdict(p, r)
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r)), "EVIDENCE_MISSING", "/worker_result/criteria/0/evidence_ids")

    def test_accept_requires_full_required_evidence_ids(self):
        p = _make_packet()
        p["acceptance_criteria"][0]["required_evidence_ids"] = ["ev-accept-1", "ev-accept-2"]
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r, v)), "EVIDENCE_MISSING", "/worker_result/evidence")

    def test_accept_requires_premise_proof(self):
        p = _make_packet()
        r = _make_worker_result(p)
        r["evidence"] = [e for e in r["evidence"] if e["kind"] != "premise"]
        r["result_sha256"] = _self_hash(r, {"result_sha256"})
        v = _make_verdict(p, r)
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r, v)), "EVIDENCE_MISSING")

    def test_accept_rejects_remaining_criteria(self):
        p = _make_packet()
        r = _make_worker_result(p, remaining_criterion_ids=["crit-1"])
        v = _make_verdict(p, r)
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r, v)), "ACCEPTANCE_UNSATISFIED", "/worker_result/remaining_criterion_ids")

    def test_accept_rejects_fallback(self):
        p = _make_packet()
        r = _make_worker_result(p)
        r["fallback"] = {
            "reason": "confirmed_quota_exhaustion",
            "provider_evidence_id": "ev-quota-1",
            "reassign_to": "sonnet_implementation",
        }
        r["result_sha256"] = _self_hash(r, {"result_sha256"})
        v = _make_verdict(p, r)
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r, v)), "INVALID_FALLBACK", "/worker_result/fallback")

    def test_reviewer_independence_by_session_id(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r, reviewer={
            "role": "opus_judgment",
            "session_id": r["worker"]["session_id"],
            "model": "claude-opus-5",
        })
        _assert_invalid(self, _validate_bundle(_make_bundle(p, r, v)), "WORKER_SELF_ACCEPT", "/opus_verdict/reviewer/session_id")


class TestReplayStability(unittest.TestCase):
    def test_key_order_does_not_affect_bundle(self):
        b = _make_bundle()
        # Re-serialize with random-ish key order by round-tripping through JSON
        # with sort_keys disabled.
        text = json.dumps(b, ensure_ascii=False, sort_keys=False)
        parsed = json.loads(text)
        result = _validate_bundle(parsed)
        self.assertTrue(result["valid"], result["errors"])


class TestTransitionMatrix(unittest.TestCase):
    def test_valid_transitions(self):
        valid = [
            ("BLOCKED", "READY"),
            ("READY", "RUNNING"),
            ("RUNNING", "REVIEW"),
            ("RUNNING", "READY"),
            ("RUNNING", "QUARANTINED"),
            ("RUNNING", "HUMAN_REQUIRED"),
            ("REVIEW", "ACCEPTED"),
            ("REVIEW", "REVISE"),
            ("REVIEW", "QUARANTINED"),
            ("REVIEW", "HUMAN_REQUIRED"),
            ("REVISE", "READY"),
        ]
        for before, after in valid:
            with self.subTest(before=before, after=after):
                self.assertTrue(validate_transition(before, after)["valid"])

    def test_invalid_transitions(self):
        invalid = [
            ("READY", "ACCEPTED"),
            ("RUNNING", "ACCEPTED"),
            ("ACCEPTED", "READY"),
            ("QUARANTINED", "READY"),
            ("HUMAN_REQUIRED", "READY"),
        ]
        for before, after in invalid:
            with self.subTest(before=before, after=after):
                _assert_invalid(self, validate_transition(before, after), "INVALID_TRANSITION")


if __name__ == "__main__":
    unittest.main()
