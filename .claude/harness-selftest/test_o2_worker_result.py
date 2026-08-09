"""O2 worker result contract tests."""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.worker_result import validate_worker_result


def _minimal_valid_worker_result():
    result = {
        "schema_version": 1,
        "result_id": "res-o2-test-001",
        "packet_id": "pkt-o2-test-001",
        "packet_sha256": "c" * 64,
        "attempt": 1,
        "worker": {
            "worker_id": "kimi-1",
            "session_id": "sess-kimi-001",
            "lane": "kimi_implementation",
            "provider": "opencode",
            "model": "kimi-k2.7-code",
        },
        "started_at": "2026-08-09T12:00:00Z",
        "finished_at": "2026-08-09T12:05:00Z",
        "starting_revision": "a" * 40,
        "ending_revision": "d" * 40,
        "outcome": "COMPLETED",
        "changed_files": [
            {
                "path": "scripts/harness_contracts/v1/packet.py",
                "status": "modified",
                "before_sha256": "e" * 64,
                "after_sha256": "f" * 64,
            }
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
            {
                "evidence_id": "ev-verify",
                "kind": "verification",
                "criterion_ids": ["ac-1"],
                "command_id": "cmd-verify",
                "artifact_path": None,
                "artifact_sha256": None,
                "summary": "Tests passed",
            }
        ],
        "criteria": [
            {
                "criterion_id": "ac-1",
                "status": "SATISFIED",
                "evidence_ids": ["ev-verify"],
            }
        ],
        "checkpoints": [
            {
                "artifact_id": "art-1",
                "path": "scripts/harness_contracts/v1/__init__.py",
                "sha256": "0" * 64,
            }
        ],
        "remaining_criterion_ids": [],
        "fallback": None,
        "human_required_reasons": [],
        "budgets": {"turns_used": 5, "output_bytes": 1024, "retry_count": 0, "allowance_used": "5"},
    }
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    return result


class TestWorkerResultValidation(unittest.TestCase):
    def test_valid_completed_passes(self):
        result = validate_worker_result(_minimal_valid_worker_result())
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_result_sha256_fails(self):
        wr = _minimal_valid_worker_result()
        del wr["result_sha256"]
        result = validate_worker_result(wr)
        self.assertFalse(result["valid"])
        self.assertIn("MISSING_FIELD", [e["code"] for e in result["errors"]])

    def test_hash_tamper_fails(self):
        wr = _minimal_valid_worker_result()
        wr["outcome"] = "FAILED"
        result = validate_worker_result(wr)
        self.assertFalse(result["valid"])
        self.assertIn("EVIDENCE_HASH_MISMATCH", [e["code"] for e in result["errors"]])

    def test_worker_result_cannot_contain_verdict(self):
        wr = _minimal_valid_worker_result()
        wr["verdict"] = "ACCEPT"
        result = validate_worker_result(wr)
        self.assertFalse(result["valid"])
        self.assertIn("UNKNOWN_FIELD", [e["code"] for e in result["errors"]])

    def test_completed_requires_no_remaining_criteria(self):
        wr = _minimal_valid_worker_result()
        wr["remaining_criterion_ids"] = ["ac-1"]
        wr["result_sha256"] = compute_sha256(canonical_bytes(wr, omit={"result_sha256"}))
        result = validate_worker_result(wr)
        self.assertFalse(result["valid"])
        self.assertIn("INVALID_VALUE", [e["code"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
