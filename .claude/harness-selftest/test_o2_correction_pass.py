"""O2 correction pass — focused adversarial tests.

These tests reproduce the four fresh Opus REVISE attacks against the current
validators.  They are expected to FAIL (assertions fail because the validator
incorrectly accepts the malformed bundle) before the correction pass is
implemented, and PASS after it.
"""

import copy
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
scripts_dir = os.path.join(_REPO_ROOT, "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.replay import validate_replay_bundle
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
)


def _assert_invalid(test, result, code=None, path=None):
    test.assertFalse(result["valid"], f"Expected invalid result, got {result}")
    if code:
        codes = {e["code"] for e in result["errors"]}
        test.assertIn(code, codes, f"Expected error code {code} in {result['errors']}")
    if path:
        paths = {e["path"] for e in result["errors"]}
        test.assertIn(path, paths, f"Expected error path {path} in {result['errors']}")


def _trust_for_bundle(b):
    """Return the trusted external-context objects that validate_replay_bundle now requires."""
    packet = b["packet"]
    worker = b["worker_result"]
    verdict = b["opus_verdict"]
    reviewer_session = verdict["reviewer"]["session_id"]
    trusted_reviewer_sessions = {reviewer_session}
    trusted_dependency_provenance = {}
    for dep in packet.get("dependency_ids", []):
        # Synthetic trusted digests for the upstream dependency.
        trusted_dependency_provenance[dep] = {
            "packet_sha256": compute_sha256(f"upstream-packet-{dep}".encode()),
            "result_sha256": compute_sha256(f"upstream-result-{dep}".encode()),
            "verdict_sha256": compute_sha256(f"upstream-verdict-{dep}".encode()),
            "bundle_sha256": compute_sha256(f"upstream-bundle-{dep}".encode()),
        }
    return trusted_dependency_provenance, trusted_reviewer_sessions


def _rehash_worker_result_in_bundle(b):
    b["worker_result"]["result_sha256"] = _self_hash(b["worker_result"], {"result_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


def _rehash_packet_in_bundle(b):
    b["packet"]["packet_sha256"] = _self_hash(b["packet"], {"packet_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


def _rehash_verdict_in_bundle(b):
    b["opus_verdict"]["verdict_sha256"] = _self_hash(b["opus_verdict"], {"verdict_sha256"})
    b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})


class TestDependencyProvenanceBinding(unittest.TestCase):
    """Dependency acceptance must be bound to immutable upstream digests and validated against an explicit trusted context."""

    def _make_dependency_bundle(self):
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
        b["dependency_states"] = [{
            "packet_id": "pkt-dep-1",
            "state": "ACCEPTED",
            "evidence_id": "ev-dep-1",
            "upstream_packet_sha256": compute_sha256(b"upstream-packet-pkt-dep-1"),
            "upstream_result_sha256": compute_sha256(b"upstream-result-pkt-dep-1"),
            "upstream_verdict_sha256": compute_sha256(b"upstream-verdict-pkt-dep-1"),
            "upstream_bundle_sha256": compute_sha256(b"upstream-bundle-pkt-dep-1"),
        }]
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        return b

    def test_dependency_record_without_upstream_digests_rejected(self):
        b = self._make_dependency_bundle()
        # Strip the upstream digest bindings that make the record non-forgeable.
        for key in ["upstream_packet_sha256", "upstream_result_sha256", "upstream_verdict_sha256", "upstream_bundle_sha256"]:
            del b["dependency_states"][0][key]
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "MISSING_FIELD")

    def test_dependency_record_without_trusted_context_rejected(self):
        b = self._make_dependency_bundle()
        # No external trusted dependency provenance supplied.
        _assert_invalid(self, validate_replay_bundle(b, None, {"opus-reviewer-1"}), "TRUST_CONTEXT_MISSING")

    def test_dependency_record_with_mismatched_upstream_digest_rejected(self):
        b = self._make_dependency_bundle()
        b["dependency_states"][0]["upstream_bundle_sha256"] = ZERO_SHA256
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PROVENANCE_MISMATCH")

    def test_dependency_record_with_matching_trusted_context_accepted(self):
        b = self._make_dependency_bundle()
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        result = validate_replay_bundle(b, trusted_dep, trusted_rev)
        self.assertTrue(result["valid"], result["errors"])


class TestTrustedReviewerContext(unittest.TestCase):
    """Reviewer independence must be enforced by an explicit trusted reviewer session context, not by bundle string inequality."""

    def test_no_trusted_reviewer_context_rejected(self):
        b = _make_bundle()
        trusted_dep, _ = _trust_for_bundle(b)
        # Bundle claims reviewer is opus-reviewer-1, but caller supplies no trusted reviewer sessions.
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, None), "TRUST_CONTEXT_MISSING")

    def test_reviewer_not_in_trusted_set_rejected(self):
        b = _make_bundle()
        trusted_dep, _ = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, {"some-other-session"}), "UNAUTHORIZED_REVIEWER")

    def test_worker_session_in_trusted_reviewer_set_rejected(self):
        b = _make_bundle()
        # Make reviewer session differ from worker session, but mark the worker session as trusted.
        worker_session = b["worker_result"]["worker"]["session_id"]
        b["opus_verdict"]["reviewer"]["session_id"] = "opus-reviewer-1"
        _rehash_verdict_in_bundle(b)
        trusted_dep, _ = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, {worker_session}), "UNAUTHORIZED_REVIEWER")

    def test_reviewer_in_trusted_set_accepted(self):
        b = _make_bundle()
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        result = validate_replay_bundle(b, trusted_dep, trusted_rev)
        self.assertTrue(result["valid"], result["errors"])


class TestAbsolutePathRejection(unittest.TestCase):
    """Absolute paths must be rejected before normalization on every repo-relative surface."""

    def test_changed_file_absolute_path_rejected(self):
        b = _make_bundle()
        b["worker_result"]["changed_files"][0]["path"] = "/scripts/harness_contracts/v1/packet.py"
        _rehash_worker_result_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_writable_path_absolute_rejected(self):
        b = _make_bundle()
        b["packet"]["writable_paths"] = ["/scripts/harness_contracts/v1/packet.py"]
        _rehash_packet_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_forbidden_surface_absolute_rejected(self):
        b = _make_bundle()
        b["packet"]["forbidden_surfaces"] = ["/backend/app.py"]
        _rehash_packet_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_required_context_absolute_rejected(self):
        b = _make_bundle()
        b["packet"]["required_context"][0]["path"] = "/PLAN.md"
        _rehash_packet_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_checkpoint_artifact_absolute_path_rejected(self):
        b = _make_bundle()
        b["packet"]["checkpoint_artifacts"][0]["path"] = "/checkpoints/cp-1.json"
        _rehash_packet_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_worker_evidence_artifact_absolute_path_rejected(self):
        b = _make_bundle()
        b["worker_result"]["evidence"].append({
            "evidence_id": "ev-artifact",
            "kind": "verification",
            "criterion_ids": [],
            "command_id": "cmd-1",
            "artifact_path": "/tmp/artifact.txt",
            "artifact_sha256": A_SHA256,
            "summary": "artifact",
        })
        _rehash_worker_result_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")

    def test_worker_checkpoint_absolute_path_rejected(self):
        b = _make_bundle()
        b["worker_result"]["checkpoints"][0]["path"] = "/checkpoints/cp-1.json"
        _rehash_worker_result_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "PATH_NOT_RELATIVE")


class TestCrossObjectChronology(unittest.TestCase):
    """Temporal ordering must hold across worker, commands, verdict, and state event."""

    def test_review_before_work_rejected(self):
        b = _make_bundle()
        b["opus_verdict"]["reviewed_at"] = "2026-08-08T23:59:00Z"
        _rehash_verdict_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "CHRONOLOGY_VIOLATION")

    def test_command_outside_worker_interval_rejected(self):
        b = _make_bundle()
        b["worker_result"]["commands"][0]["timestamps"]["started_at"] = "2026-08-08T23:50:00Z"
        b["worker_result"]["commands"][0]["timestamps"]["finished_at"] = "2026-08-08T23:55:00Z"
        _rehash_worker_result_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "CHRONOLOGY_VIOLATION")

    def test_command_finished_after_worker_finished_rejected(self):
        b = _make_bundle()
        b["worker_result"]["finished_at"] = "2026-08-09T00:00:15Z"
        b["worker_result"]["commands"][0]["timestamps"]["finished_at"] = "2026-08-09T00:00:20Z"
        _rehash_worker_result_in_bundle(b)
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "CHRONOLOGY_VIOLATION")

    def test_acceptance_event_before_work_rejected(self):
        b = _make_bundle()
        b["prior_state_event"]["event_at"] = "2026-08-08T23:59:00Z"
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "CHRONOLOGY_VIOLATION")

    def test_acceptance_event_before_review_rejected(self):
        b = _make_bundle()
        # event_at is currently 00:01:30, reviewed_at 00:02:00 in _make_verdict.
        # We intentionally set event_at before reviewed_at to test acceptance chronology.
        b["prior_state_event"]["event_at"] = "2026-08-09T00:01:30Z"
        b["opus_verdict"]["reviewed_at"] = "2026-08-09T00:02:00Z"
        _rehash_verdict_in_bundle(b)
        b["bundle_sha256"] = _self_hash(b, {"bundle_sha256"})
        trusted_dep, trusted_rev = _trust_for_bundle(b)
        _assert_invalid(self, validate_replay_bundle(b, trusted_dep, trusted_rev), "CHRONOLOGY_VIOLATION")


if __name__ == "__main__":
    unittest.main()
