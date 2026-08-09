"""O2 adversarial bypass tests.

Each test constructs a near-valid, correctly rehashed bundle, mutates exactly
the field or relationship under attack, and asserts that the replay validator
rejects it.  These tests were written against the pre-fix validators to
reproduce accepted-invalid bundles (RED); after the fix they must pass (GREEN).
"""

import copy
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Import helpers from the main contract test module.
from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.replay import validate_replay_bundle

# test_o2_contract.py is in the same directory and only runs on __main__.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_o2_contract import (
    A_SHA256,
    B_SHA256,
    REVISION_A,
    REVISION_B,
    ZERO_SHA256,
    _make_bundle,
    _make_packet,
    _make_verdict,
    _make_worker_result,
    _self_hash,
    _validate_bundle,
)


def _assert_invalid(test, result, code=None, path=None):
    test.assertFalse(result["valid"], f"Expected invalid result, got {result}")
    if code:
        codes = {e["code"] for e in result["errors"]}
        test.assertIn(code, codes, f"Expected error code {code} in {result['errors']}")
    if path:
        paths = {e["path"] for e in result["errors"]}
        test.assertIn(path, paths, f"Expected error path {path} in {result['errors']}")


def _rehash_worker_result_in_bundle(b):
    b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


def _rehash_packet_in_bundle(b):
    b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


def _rehash_verdict_in_bundle(b):
    b["opus_verdict"]["verdict_sha256"] = _self_hash(b["opus_verdict"], {"verdict_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


def _dep_state(dep, evidence_id):
    """Build a dependency_state record with upstream digests matching the trusted context."""
    return {
        "packet_id": dep,
        "state": "ACCEPTED",
        "evidence_id": evidence_id,
        "upstream_packet_sha256": compute_sha256(f"upstream-packet-{dep}".encode()),
        "upstream_result_sha256": compute_sha256(f"upstream-result-{dep}".encode()),
        "upstream_verdict_sha256": compute_sha256(f"upstream-verdict-{dep}".encode()),
        "upstream_bundle_sha256": compute_sha256(f"upstream-bundle-{dep}".encode()),
    }


class TestDependencyStates(unittest.TestCase):
    """Replay dependency_states must exactly cover packet dependencies with ACCEPTED records backed by evidence."""

    def test_empty_dependency_states_when_no_dependencies(self):
        b = _make_bundle()
        self.assertEqual(b["packet"]["dependency_ids"], [])
        result = _validate_bundle(b)
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_dependency_state_record_rejected(self):
        p = _make_packet(dependency_ids=["pkt-dep-1"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        # dependency_states is empty but packet has a dependency.
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING")

    def test_dependency_state_not_accepted_rejected(self):
        p = _make_packet(dependency_ids=["pkt-dep-1"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            evidence=[
                {"evidence_id": "ev-dep-1", "kind": "acceptance", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "dep accepted"},
                {"evidence_id": "ev-accept-1", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-cmd-1", "kind": "verification", "criterion_ids": [], "command_id": "cmd-1", "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-premise-1", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
            ],
        )
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        b["dependency_states"] = [_dep_state("pkt-dep-1", "ev-dep-1")]
        b["dependency_states"][0]["state"] = "READY"
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "DEPENDENCY_NOT_ACCEPTED")

    def test_dependency_state_evidence_missing_rejected(self):
        p = _make_packet(dependency_ids=["pkt-dep-1"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        b["dependency_states"] = [_dep_state("pkt-dep-1", "ev-missing")]
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING")

    def test_extra_dependency_state_rejected(self):
        p = _make_packet()
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        b["dependency_states"] = [_dep_state("pkt-extra", "ev-accept-1")]
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "UNKNOWN_DEPENDENCY")

    def test_duplicate_dependency_state_rejected(self):
        p = _make_packet(dependency_ids=["pkt-dep-1"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            evidence=[
                {"evidence_id": "ev-dep-1", "kind": "acceptance", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "dep accepted"},
                {"evidence_id": "ev-accept-1", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-cmd-1", "kind": "verification", "criterion_ids": [], "command_id": "cmd-1", "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-premise-1", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
            ],
        )
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        b["dependency_states"] = [
            _dep_state("pkt-dep-1", "ev-dep-1"),
            _dep_state("pkt-dep-1", "ev-dep-1"),
        ]
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        _assert_invalid(self, _validate_bundle(b), "DUPLICATE_ID")


class TestAlwaysApplicableGlobalRules(unittest.TestCase):
    """ACCEPT requires the seven always-applicable global rules to PASS."""

    def test_premise_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "premise":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_repo_only_boundary_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "repo_only_boundary":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_allowlist_scope_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "allowlist_scope":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_changed_manifest_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "changed_manifest":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_command_integrity_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "command_integrity":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_governed_records_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "governed_records":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_reviewer_independence_not_applicable_rejected(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "reviewer_independence":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_conditional_rule_not_applicable_allowed(self):
        b = _make_bundle()
        for gf in b["opus_verdict"]["global_findings"]:
            if gf["rule_id"] == "batch_reconciliation":
                gf["finding"] = "NOT_APPLICABLE"
        _rehash_verdict_in_bundle(b)
        result = _validate_bundle(b)
        self.assertTrue(result["valid"], result["errors"])


class TestCriterionCoverage(unittest.TestCase):
    """Criterion IDs must match exactly across packet, result, and verdict."""

    def test_result_missing_packet_criterion_rejected(self):
        p = _make_packet()
        p["acceptance_criteria"].append({
            "criterion_id": "crit-2",
            "statement": "Second criterion",
            "required_evidence_ids": ["ev-accept-2"],
        })
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p)
        v = _make_verdict(p, r)
        # crit-2 is not in result criteria or remaining.
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_result_extra_criterion_rejected(self):
        b = _make_bundle()
        b["worker_result"]["criteria"].append({
            "criterion_id": "crit-extra",
            "status": "SATISFIED",
            "evidence_ids": ["ev-accept-1"],
        })
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_verdict_missing_packet_criterion_rejected(self):
        p = _make_packet()
        p["acceptance_criteria"].append({
            "criterion_id": "crit-2",
            "statement": "Second criterion",
            "required_evidence_ids": ["ev-accept-2"],
        })
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            criteria=[
                {"criterion_id": "crit-1", "status": "SATISFIED", "evidence_ids": ["ev-accept-1"]},
                {"criterion_id": "crit-2", "status": "SATISFIED", "evidence_ids": ["ev-accept-2"]},
            ],
            evidence=[
                {"evidence_id": "ev-accept-1", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-accept-2", "kind": "acceptance", "criterion_ids": ["crit-2"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-premise-1", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
            ],
        )
        v = _make_verdict(p, r, criterion_findings=[
            {"criterion_id": "crit-1", "finding": "PASS", "evidence_ids": ["ev-accept-1"], "reason": "ok"},
        ])
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_verdict_extra_criterion_rejected(self):
        b = _make_bundle()
        b["opus_verdict"]["criterion_findings"].append({
            "criterion_id": "crit-extra",
            "finding": "PASS",
            "evidence_ids": ["ev-accept-1"],
            "reason": "ok",
        })
        _rehash_verdict_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")


class TestRequiredEvidenceCited(unittest.TestCase):
    """Every packet-required evidence ID must be cited by the result criterion
    and by the verdict criterion finding."""

    def test_required_evidence_not_cited_by_result_criterion(self):
        p = _make_packet()
        p["acceptance_criteria"][0]["required_evidence_ids"].append("ev-accept-2")
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            evidence=[
                {"evidence_id": "ev-accept-1", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-accept-2", "kind": "acceptance", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-cmd-1", "kind": "verification", "criterion_ids": [], "command_id": "cmd-1", "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-premise-1", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
            ],
        )
        # crit-1 only cites ev-accept-1, omitting required ev-accept-2.
        v = _make_verdict(p, r, criterion_findings=[
            {"criterion_id": "crit-1", "finding": "PASS", "evidence_ids": ["ev-accept-1", "ev-accept-2"], "reason": "ok"},
        ])
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING")

    def test_required_evidence_not_cited_by_verdict_finding(self):
        p = _make_packet()
        p["acceptance_criteria"][0]["required_evidence_ids"].append("ev-accept-2")
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(
            p,
            criteria=[{"criterion_id": "crit-1", "status": "SATISFIED", "evidence_ids": ["ev-accept-1", "ev-accept-2"]}],
            evidence=[
                {"evidence_id": "ev-accept-1", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-accept-2", "kind": "acceptance", "criterion_ids": ["crit-1"], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-cmd-1", "kind": "verification", "criterion_ids": [], "command_id": "cmd-1", "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
                {"evidence_id": "ev-premise-1", "kind": "premise", "criterion_ids": [], "command_id": None, "artifact_path": None, "artifact_sha256": None, "summary": "ok"},
            ],
        )
        v = _make_verdict(p, r, criterion_findings=[
            {"criterion_id": "crit-1", "finding": "PASS", "evidence_ids": ["ev-accept-1"], "reason": "ok"},
        ])
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING")


class TestEvidenceReferenceResolution(unittest.TestCase):
    """Evidence criterion_ids and command_ids must resolve to declared IDs."""

    def test_evidence_unknown_criterion_id_rejected(self):
        b = _make_bundle()
        b["worker_result"]["evidence"][0]["criterion_ids"].append("crit-unknown")
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "ACCEPTANCE_UNSATISFIED")

    def test_evidence_unknown_command_id_rejected(self):
        b = _make_bundle()
        b["worker_result"]["evidence"][1]["command_id"] = "cmd-unknown"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "COMMAND_MISMATCH")


class TestVerificationCommandEvidence(unittest.TestCase):
    """Verification command expected_evidence must exist and cite that command."""

    def test_expected_evidence_not_citing_command_rejected(self):
        b = _make_bundle()
        # ev-cmd-1 currently cites cmd-1; change it to cmd-other.
        for ev in b["worker_result"]["evidence"]:
            if ev["evidence_id"] == "ev-cmd-1":
                ev["command_id"] = "cmd-other"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "COMMAND_MISMATCH")

    def test_expected_evidence_missing_rejected(self):
        b = _make_bundle()
        b["packet"]["verification_commands"][0]["expected_evidence_ids"].append("ev-missing")
        _rehash_packet_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "EVIDENCE_MISSING")


class TestTimestampAndBudgetOrdering(unittest.TestCase):
    """Timestamps must be ordered; elapsed time must fit within budgets."""

    def test_worker_finished_before_started_rejected(self):
        b = _make_bundle()
        b["worker_result"]["started_at"] = "2026-08-09T00:02:00Z"
        b["worker_result"]["finished_at"] = "2026-08-09T00:01:00Z"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "INVALID_VALUE")

    def test_command_finished_before_started_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["timestamps"]["started_at"] = "2026-08-09T00:00:20Z"
        b["worker_result"]["commands"][0]["timestamps"]["finished_at"] = "2026-08-09T00:00:10Z"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "INVALID_VALUE")

    def test_worker_elapsed_exceeds_wall_clock_rejected(self):
        b = _make_bundle()
        b["worker_result"]["started_at"] = "2026-08-09T00:00:00Z"
        b["worker_result"]["finished_at"] = "2026-08-09T00:11:00Z"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "BUDGET_EXCEEDED")

    def test_command_elapsed_exceeds_timeout_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["timestamps"]["started_at"] = "2026-08-09T00:00:00Z"
        b["worker_result"]["commands"][0]["timestamps"]["finished_at"] = "2026-08-09T00:02:00Z"
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "BUDGET_EXCEEDED")


class TestBoolSafeIntegers(unittest.TestCase):
    """Booleans must not pass where integers are required."""

    def test_attempt_true_rejected(self):
        b = _make_bundle()
        b["worker_result"]["attempt"] = True
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "INVALID_TYPE")

    def test_command_exit_code_true_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["exit_code"] = True
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "INVALID_TYPE")


class TestResourceBudgets(unittest.TestCase):
    """worker_result.budgets must stay within packet budgets and reject booleans."""

    def test_turns_used_bool_rejected(self):
        b = _make_bundle()
        b["worker_result"]["budgets"]["turns_used"] = True
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "INVALID_TYPE")

    def test_output_bytes_over_budget_rejected(self):
        b = _make_bundle()
        b["worker_result"]["budgets"]["output_bytes"] = 2_000_000
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "BUDGET_EXCEEDED")

    def test_retry_count_over_limit_rejected(self):
        b = _make_bundle()
        b["worker_result"]["budgets"]["retry_count"] = 5
        _rehash_worker_result_in_bundle(b)
        _assert_invalid(self, _validate_bundle(b), "BUDGET_EXCEEDED")


class TestChangedFileContainment(unittest.TestCase):
    """Changed files must be under writable paths and avoid forbidden/governed."""

    def test_changed_file_overlaps_forbidden_surface_rejected(self):
        p = _make_packet(writable_paths=["scripts/a.py"], forbidden_surfaces=["backend/app.py"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p, changed_files=[{
            "path": "backend/app.py",
            "status": "modified",
            "before_sha256": A_SHA256,
            "after_sha256": B_SHA256,
        }])
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "CHANGED_FILE_UNDECLARED")

    def test_changed_file_overlaps_governed_path_rejected(self):
        p = _make_packet(writable_paths=["scripts/a.py"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p, changed_files=[{
            "path": "CLAUDE.md",
            "status": "modified",
            "before_sha256": A_SHA256,
            "after_sha256": B_SHA256,
        }])
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        _assert_invalid(self, _validate_bundle(b), "CHANGED_FILE_UNDECLARED")

    def test_changed_file_descendant_of_writable_allowed(self):
        p = _make_packet(writable_paths=["scripts/harness_contracts"])
        p["packet_sha256"] = _self_hash(p, {"packet_sha256"})
        r = _make_worker_result(p, changed_files=[{
            "path": "scripts/harness_contracts/v1/packet.py",
            "status": "modified",
            "before_sha256": A_SHA256,
            "after_sha256": B_SHA256,
        }])
        v = _make_verdict(p, r)
        b = _make_bundle(p, r, v)
        result = _validate_bundle(b)
        self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
