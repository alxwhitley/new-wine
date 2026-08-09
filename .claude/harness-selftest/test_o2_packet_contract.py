"""O2 packet contract tests — canonical hash and strict schema validation."""

import json
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import validate_packet


def _minimal_valid_packet():
    packet = {
        "schema_version": 1,
        "packet_id": "pkt-o2-test-001",
        "objective": "Verify O2 packet contract validation",
        "dependency_ids": [],
        "lane": "kimi_implementation",
        "assigned_worker": {
            "worker_id": "kimi-1",
            "provider": "opencode",
            "model": "kimi-k2.7-code",
        },
        "starting_revision": "a" * 40,
        "worktree": {
            "path": "/Users/alexwhitley/.codex/worktrees/75cf/rhemata",
            "branch": "o2-test",
        },
        "writable_paths": ["scripts/harness_contracts/v1/packet.py"],
        "forbidden_surfaces": ["backend/app/services/answer_toolbox.py"],
        "required_context": [
            {"path": "PLAN.md", "sha256": "b" * 64},
        ],
        "premise_checks": [
            {"check_id": "ck-1", "command_id": "cmd-read-plan", "expected": "present"},
        ],
        "acceptance_criteria": [
            {
                "criterion_id": "ac-1",
                "statement": "Canonical hash is stable",
                "required_evidence_ids": ["ev-hash"],
            }
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
        "budgets": {
            "max_turns": 10,
            "wall_clock_seconds": 300,
            "retry_limit": 1,
            "max_output_bytes": 1_000_000,
            "cost_class": "low",
            "allowance_limit": 100,
        },
        "network_policy": "denied",
        "checkpoint_artifacts": [
            {
                "artifact_id": "art-1",
                "path": "scripts/harness_contracts/v1/__init__.py",
                "required_for_fallback": True,
            }
        ],
        "rollback": {
            "method": "git_reset",
            "allowed_commands": [
                {"argv": ["git", "checkout", "--", "scripts/harness_contracts/"], "cwd": "."}
            ],
        },
        "human_stop_conditions": ["governed_doc_touched"],
        "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
    }
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


class TestCanonicalHash(unittest.TestCase):
    def test_canonical_bytes_stable_and_deterministic(self):
        packet = _minimal_valid_packet()
        first = canonical_bytes(packet)
        second = canonical_bytes(packet)
        self.assertEqual(first, second)
        # Key order must not matter.
        reordered = json.loads(json.dumps(packet, sort_keys=False))
        self.assertEqual(canonical_bytes(reordered), first)

    def test_packet_sha256_computed_with_itself_omitted(self):
        packet = _minimal_valid_packet()
        base = dict(packet)
        base["packet_sha256"] = "x" * 64
        computed = compute_sha256(canonical_bytes(base, omit={"packet_sha256"}))
        self.assertNotEqual(computed, "x" * 64)
        # Setting the field to the computed value makes canonical form identical.
        packet["packet_sha256"] = computed
        self.assertEqual(
            compute_sha256(canonical_bytes(packet, omit={"packet_sha256"})),
            computed,
        )


_WINDOWS_ABSOLUTE_PATHS = [
    r"\outside\owned.py",
    r"C:\outside\owned.py",
    "C:/outside/owned.py",
    r"\\server\share\owned.py",
]


class TestWindowsAbsolutePathRejection(unittest.TestCase):
    """Windows-style absolute paths must be rejected before normalization on every packet path surface."""

    def _assert_path_not_relative(self, packet):
        result = validate_packet(packet)
        self.assertFalse(result["valid"], f"Expected invalid, got {result}")
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("PATH_NOT_RELATIVE", codes)

    def test_writable_paths_reject_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["writable_paths"] = [path]
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)

    def test_forbidden_surfaces_reject_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["forbidden_surfaces"] = [path]
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)

    def test_required_context_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["required_context"][0]["path"] = path
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)

    def test_verification_command_cwd_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["verification_commands"][0]["cwd"] = path
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)

    def test_checkpoint_artifact_path_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["checkpoint_artifacts"][0]["path"] = path
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)

    def test_rollback_allowed_command_cwd_rejects_windows_absolute(self):
        for path in _WINDOWS_ABSOLUTE_PATHS:
            with self.subTest(path=path):
                packet = _minimal_valid_packet()
                packet["rollback"]["allowed_commands"][0]["cwd"] = path
                packet["packet_sha256"] = compute_sha256(
                    canonical_bytes(packet, omit={"packet_sha256"})
                )
                self._assert_path_not_relative(packet)


class TestStrictSchemaErrors(unittest.TestCase):
    def test_valid_packet_passes(self):
        result = validate_packet(_minimal_valid_packet())
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["errors"], [])

    def test_missing_required_field_fails(self):
        packet = _minimal_valid_packet()
        del packet["objective"]
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("MISSING_FIELD", codes)

    def test_unknown_top_level_field_fails(self):
        packet = _minimal_valid_packet()
        packet["extra_field"] = "surprise"
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("UNKNOWN_FIELD", codes)

    def test_empty_string_fails(self):
        packet = _minimal_valid_packet()
        packet["objective"] = "   "
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("INVALID_VALUE", codes)

    def test_invalid_enum_fails(self):
        packet = _minimal_valid_packet()
        packet["lane"] = "invalid_lane"
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("INVALID_ENUM", codes)

    def test_empty_nonempty_list_fails(self):
        packet = _minimal_valid_packet()
        packet["writable_paths"] = []
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("INVALID_VALUE", codes)

    def test_invalid_sha_format_fails(self):
        packet = _minimal_valid_packet()
        packet["starting_revision"] = "not-forty-chars"
        result = validate_packet(packet)
        self.assertFalse(result["valid"])
        codes = [e["code"] for e in result["errors"]]
        self.assertIn("INVALID_FORMAT", codes)


if __name__ == "__main__":
    unittest.main()
