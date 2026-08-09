"""O2 Opus verdict contract tests."""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.verdict import validate_verdict


def _minimal_valid_verdict():
    verdict = {
        "schema_version": 1,
        "verdict_id": "verdict-o2-test-001",
        "packet_id": "pkt-o2-test-001",
        "packet_sha256": "c" * 64,
        "result_id": "res-o2-test-001",
        "result_sha256": "d" * 64,
        "reviewer": {
            "role": "opus_judgment",
            "session_id": "sess-opus-001",
            "model": "claude-opus-5",
        },
        "reviewed_at": "2026-08-09T12:10:00Z",
        "verdict": "ACCEPT",
        "criterion_findings": [
            {
                "criterion_id": "ac-1",
                "finding": "PASS",
                "evidence_ids": ["ev-verify"],
                "reason": "All checks passed",
            }
        ],
        "global_findings": [
            {"rule_id": "premise", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "Premise verified"},
            {"rule_id": "repo_only_boundary", "finding": "PASS", "evidence_ids": ["ev-verify"], "reason": "No production writes requested"},
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
        "integration_revision": "a" * 40,
    }
    verdict["verdict_sha256"] = compute_sha256(canonical_bytes(verdict, omit={"verdict_sha256"}))
    return verdict


class TestVerdictValidation(unittest.TestCase):
    def test_valid_accept_passes(self):
        result = validate_verdict(_minimal_valid_verdict())
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_verdict_sha256_fails(self):
        v = _minimal_valid_verdict()
        del v["verdict_sha256"]
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("MISSING_FIELD", [e["code"] for e in result["errors"]])

    def test_hash_tamper_fails(self):
        v = _minimal_valid_verdict()
        v["verdict"] = "REVISE"
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("EVIDENCE_HASH_MISMATCH", [e["code"] for e in result["errors"]])

    def test_invalid_verdict_enum_fails(self):
        v = _minimal_valid_verdict()
        v["verdict"] = "MAYBE"
        v["verdict_sha256"] = compute_sha256(canonical_bytes(v, omit={"verdict_sha256"}))
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_ENUM", [e["code"] for e in result["errors"]])

    def test_reviewer_must_be_opus_judgment(self):
        v = _minimal_valid_verdict()
        v["reviewer"]["role"] = "kimi_implementation"
        v["verdict_sha256"] = compute_sha256(canonical_bytes(v, omit={"verdict_sha256"}))
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_VALUE", [e["code"] for e in result["errors"]])

    def test_accept_requires_all_criterion_findings_pass(self):
        v = _minimal_valid_verdict()
        v["criterion_findings"][0]["finding"] = "FAIL"
        v["verdict_sha256"] = compute_sha256(canonical_bytes(v, omit={"verdict_sha256"}))
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("ACCEPTANCE_UNSATISFIED", [e["code"] for e in result["errors"]])

    def test_accept_requires_global_findings_pass(self):
        v = _minimal_valid_verdict()
        v["global_findings"][0]["finding"] = "FAIL"
        v["verdict_sha256"] = compute_sha256(canonical_bytes(v, omit={"verdict_sha256"}))
        result = validate_verdict(v)
        self.assertFalse(result["valid"])
        self.assertIn("ACCEPTANCE_UNSATISFIED", [e["code"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
