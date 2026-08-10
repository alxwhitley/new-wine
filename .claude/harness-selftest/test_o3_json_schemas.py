"""O3 contract-hygiene and validator tests.

Coverage:
- journal event validation and illegal-transition/LOCK_RECLAIMED rejection paths;
- queue/terminal-seal/claim/reassignment/packet-state schema validation;
- provider-evidence guard failures (all four, independently) plus the end-to-end
  PROVIDER_EXHAUSTED path;
- attempt classification (full precedence table);
- reconciliation invariants, including I5 set-equality and integrity-list
  population fixtures;
- ERROR_CODES append-only hygiene;
- Python 3.9 syntax AST scan (no PEP 604 X | Y annotations).
"""

import ast
import json
import os
import re
import sys
import unittest
from typing import Any, Dict, List, Optional, Set

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts")
_SCHEMAS_DIR = os.path.join(_REPO_ROOT, "schemas", "harness", "v1")
_CONTRACTS_DIR = os.path.join(_SCRIPTS_DIR, "harness_contracts", "v1")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from harness_contracts.v1 import errors as errors_module
from harness_contracts.v1.errors import ERROR_CODES, PHASE_RANK


# Snapshot of ERROR_CODES before the O3 append-only extension.
_PRE_O3_ERROR_CODES = (
    "INVALID_JSON",
    "ROOT_NOT_OBJECT",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "INVALID_TYPE",
    "INVALID_ENUM",
    "INVALID_FORMAT",
    "INVALID_VALUE",
    "DUPLICATE_ID",
    "DUPLICATE_PATH",
    "PATH_NOT_RELATIVE",
    "PATH_ESCAPE",
    "PATH_OVERLAP",
    "GOVERNED_PATH",
    "FORBIDDEN_AUTHORITY",
    "SELF_DEPENDENCY",
    "UNKNOWN_DEPENDENCY",
    "DEPENDENCY_NOT_ACCEPTED",
    "REVISION_MISMATCH",
    "BUDGET_EXCEEDED",
    "COMMAND_MISMATCH",
    "COMMAND_NOT_RUN",
    "COMMAND_FAILED",
    "EVIDENCE_MISSING",
    "EVIDENCE_HASH_MISMATCH",
    "ACCEPTANCE_UNSATISFIED",
    "CHANGED_FILE_UNDECLARED",
    "CHECKPOINT_INCOMPLETE",
    "INVALID_TRANSITION",
    "INVALID_FALLBACK",
    "WORKER_SELF_ACCEPT",
    "VERDICT_CONFLICT",
    "TRUST_CONTEXT_MISSING",
    "UNAUTHORIZED_REVIEWER",
    "PROVENANCE_MISMATCH",
    "CHRONOLOGY_VIOLATION",
)

_NEW_ERROR_CODES = (
    "JOURNAL_CHAIN_BROKEN",
    "JOURNAL_HEAD_MOVED",
    "SEQUENCE_GAP",
    "CLAIM_CONFLICT",
    "TERMINAL_SEAL_MISMATCH",
    "RECONCILIATION_MISMATCH",
    "RESERVED_STATE_PATH",
)

_NEW_SCHEMA_FILES = {
    "journal-event.schema.json",
    "queue.schema.json",
    "packet-state.schema.json",
    "claim.schema.json",
    "attempt-outcome.schema.json",
    "provider-evidence.schema.json",
    "provider-signals.schema.json",
    "reassignment.schema.json",
    "terminal-seal.schema.json",
    "reconciliation-report.schema.json",
}

# New O3 contract modules created by O3-P1.  H10 scans these for PEP 604 unions.
_O3_CONTRACT_MODULES = (
    "journal.py",
    "queue_state.py",
    "seal.py",
    "claim.py",
    "classification.py",
    "provider_evidence.py",
    "reassignment.py",
    "reconciliation.py",
    "packet_state.py",
)


def _annotation_contains_bitor(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.BinOp) and isinstance(child.op, ast.BitOr)
        for child in ast.walk(node)
    )


def _find_pep604_in_annotations(source: str) -> List[int]:
    """Return line numbers of PEP 604 X | Y unions used as type annotations.

    Only annotation contexts are inspected (AnnAssign, argument annotations, and
    return annotations), so legitimate set unions in ordinary expressions are
    not false-positive flagged.
    """
    tree = ast.parse(source)
    lines: Set[int] = set()
    for node in ast.walk(tree):
        annotation: Optional[ast.AST] = None
        if isinstance(node, ast.AnnAssign):
            annotation = node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                annotation = node.returns
            for arg in (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
            ):
                if arg.annotation is not None and _annotation_contains_bitor(arg.annotation):
                    lines.add(arg.annotation.lineno)
            if node.args.vararg is not None and node.args.vararg.annotation is not None:
                if _annotation_contains_bitor(node.args.vararg.annotation):
                    lines.add(node.args.vararg.annotation.lineno)
            if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
                if _annotation_contains_bitor(node.args.kwarg.annotation):
                    lines.add(node.args.kwarg.annotation.lineno)
        if annotation is not None and _annotation_contains_bitor(annotation):
            lines.add(annotation.lineno)
    return sorted(lines)


def _load_schema(filename: str) -> Dict[str, Any]:
    path = os.path.join(_SCHEMAS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestErrorCodesAppendOnly(unittest.TestCase):
    """H9: pre-existing ERROR_CODES indices unchanged; new codes appended at the end."""

    def test_pre_existing_codes_unchanged(self):
        self.assertEqual(ERROR_CODES[: len(_PRE_O3_ERROR_CODES)], list(_PRE_O3_ERROR_CODES))

    def test_new_codes_appended_in_order(self):
        appended = ERROR_CODES[len(_PRE_O3_ERROR_CODES):]
        self.assertEqual(appended, list(_NEW_ERROR_CODES))

    def test_phase_rank_keys_added(self):
        self.assertIn("chain", PHASE_RANK)
        self.assertIn("reconciliation", PHASE_RANK)


class TestJournalEventValidator(unittest.TestCase):
    """Smoke tests for journal.py validate_journal_event."""

    def test_run_started_event_validates(self):
        from harness_contracts.v1.journal import validate_journal_event

        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {
                        "coordinator_id": "coord-1",
                        "boot_id": "boot-1",
                        "hostname": "host-1",
                        "pid": 1234,
                    },
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1,
                        "worker_result": 1,
                        "verdict": 1,
                        "replay": 1,
                        "journal": 1,
                        "queue": 1,
                        "claim": 1,
                        "attempt_outcome": 1,
                        "provider_evidence": 1,
                        "reassignment": 1,
                        "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event, state_root_id="root-1")
        self.assertTrue(result["valid"], result["errors"])


class TestQueueStateValidator(unittest.TestCase):
    def test_minimal_queue_validates(self):
        from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
        from harness_contracts.v1.queue_state import validate_queue

        value = {
            "schema_version": 1,
            "state_root_id": "root-1",
            "derived_from": {"journal_last_seq": 0, "journal_last_event_sha256": "0" * 64},
            "entries": [],
            "pending_intents": [],
        }
        value["queue_sha256"] = compute_sha256(canonical_bytes(value, omit={"queue_sha256"}))
        result = validate_queue(value, state_root_id="root-1")
        self.assertTrue(result["valid"], result["errors"])


class TestTerminalSealValidator(unittest.TestCase):
    def test_accepted_seal_requires_upstream_digests(self):
        from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
        from harness_contracts.v1.seal import validate_terminal_seal

        value = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "terminal_state": "ACCEPTED",
            "sealing_event_seq": 5,
            "sealing_event_sha256": "0" * 64,
            "sealed_at": "2026-08-09T00:00:00Z",
            "quarantine_reason": None,
            "human_required_reasons": [],
            "upstream_digests": {
                "packet_sha256": "0" * 64,
                "result_sha256": "0" * 64,
                "verdict_sha256": "0" * 64,
                "bundle_sha256": "0" * 64,
            },
        }
        value["seal_sha256"] = compute_sha256(canonical_bytes(value, omit={"seal_sha256"}))
        result = validate_terminal_seal(value)
        self.assertTrue(result["valid"], result["errors"])


class TestClaimClassifier(unittest.TestCase):
    def test_foreign_host_refuses_reclaim(self):
        from harness_contracts.v1.claim import classify_claim

        record = {
            "hostname": "other-host",
            "boot_id": "boot-1",
            "coordinator_id": "coord-1",
            "pid": 1234,
        }
        trusted = {
            "coordinator_id": "coord-1",
            "hostname": "this-host",
            "boot_id": "boot-1",
            "pid": 1234,
            "live_coordinator_ids": set(),
            "now": "2026-08-09T00:00:00Z",
        }
        result = classify_claim(record, trusted)
        self.assertEqual(result["status"], "FOREIGN_HOST")
        self.assertTrue(any(e["code"] == "CLAIM_CONFLICT" for e in result["errors"]))


class TestProviderEvidenceConfirmation(unittest.TestCase):
    def test_registry_missing_captured_from_fails(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.provider_evidence import validate_provider_signals_registry

        registry = {
            "schema_version": 1,
            "registry_id": "reg-1",
            "providers": {
                "kimi": [
                    {
                        "rule_id": "r1",
                        "channel": "stderr",
                        "match_kind": "substring",
                        "pattern": "rate limit",
                        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
                    }
                ]
            },
        }
        registry["registry_sha256"] = compute_sha256(canonical_bytes(registry, omit={"registry_sha256"}))
        result = validate_provider_signals_registry(registry)
        self.assertFalse(result["valid"])
        self.assertTrue(any("captured_from" in e["message"] for e in result["errors"]))


class TestProviderEvidenceGuards(unittest.TestCase):
    """Design 6.3 four-guard rule and failure modes."""

    def _registry(self):
        return {
            "schema_version": 1,
            "registry_id": "reg-1",
            "providers": {
                "kimi": [
                    {
                        "rule_id": "r1",
                        "channel": "stderr",
                        "match_kind": "substring",
                        "pattern": "rate limit exceeded",
                        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
                        "captured_from": {
                            "sample_path": "trust/samples/kimi_rate_limit.json",
                            "sample_sha256": "0" * 64,
                            "captured_at": "2026-08-09T00:00:00Z",
                        },
                    }
                ]
            },
        }

    def _worker_result(self, fallback=None):
        return {
            "result_id": "wr-1",
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "worker": {"worker_id": "w1", "session_id": "s1", "lane": "kimi_implementation", "provider": "kimi", "model": "k2"},
            "started_at": "2026-08-09T00:00:00Z",
            "finished_at": "2026-08-09T00:00:05Z",
            "starting_revision": "0" * 40,
            "ending_revision": "0" * 40,
            "outcome": "CHECKPOINTED",
            "fallback": fallback or {
                "reason": "confirmed_rate_limit_exhaustion",
                "provider_evidence_id": "pe-1",
                "reassign_to": "sonnet_implementation",
            },
            "commands": [
                {
                    "command_id": "c1",
                    "argv": ["true"],
                    "cwd": "scripts",
                    "timestamps": {"started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:04Z"},
                    "exit_code": 0,
                    "outcome": "PASSED",
                    "stdout_sha256": "0" * 64,
                    "stderr_sha256": "0" * 64,
                }
            ],
        }

    def _evidence(self, overrides=None):
        import hashlib
        stderr_text = "something\nrate limit exceeded\n"
        stderr_bytes = stderr_text.encode("utf-8")
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()
        ev = {
            "schema_version": 1,
            "evidence_id": "pe-1",
            "packet_id": "p1",
            "attempt": 1,
            "provider": "kimi",
            "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
            "invocation": {
                "argv": ["python", "worker.py"],
                "exit_code": 1,
                "signal": None,
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "timed_out": False,
            },
            "stdout_path": "results/p1/1/stdout.bin",
            "stdout_sha256": "0" * 64,
            "stderr_path": "results/p1/1/stderr.bin",
            "stderr_sha256": stderr_sha256,
            "matched_signal": {
                "channel": "stderr",
                "rule_id": "r1",
                "registry_id": "reg-1",
                "verbatim_excerpt": "rate limit exceeded",
                "byte_offset": 10,
                "byte_length": 19,
            },
            "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        }
        if overrides:
            ev.update(overrides)
        return ev, stderr_bytes

    def test_guard1_rule_absent_from_registry(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence({"matched_signal": {**self._evidence()[0]["matched_signal"], "rule_id": "r-missing"}})
        result = confirm_provider_exhaustion(self._worker_result(), ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any(e["code"] == "EVIDENCE_HASH_MISMATCH" for e in result["errors"]))

    def test_guard1_excerpt_mismatch(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence({"matched_signal": {**self._evidence()[0]["matched_signal"], "verbatim_excerpt": "wrong excerpt"}})
        result = confirm_provider_exhaustion(self._worker_result(), ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any("excerpt" in e["message"].lower() for e in result["errors"]))

    def test_guard1_channel_classification_mismatch(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence({"matched_signal": {**self._evidence()[0]["matched_signal"], "channel": "stdout"}})
        result = confirm_provider_exhaustion(self._worker_result(), ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")

    def test_guard2_provider_evidence_id_mismatch(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence()
        worker = self._worker_result(fallback={"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe-other", "reassign_to": "sonnet_implementation"})
        result = confirm_provider_exhaustion(worker, ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any(e["code"] == "INVALID_FALLBACK" for e in result["errors"]))

    def test_guard2_reason_map_mismatch(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence()
        worker = self._worker_result(fallback={"reason": "confirmed_quota_exhaustion", "provider_evidence_id": "pe-1", "reassign_to": "sonnet_implementation"})
        result = confirm_provider_exhaustion(worker, ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any(e["code"] == "INVALID_FALLBACK" for e in result["errors"]))

    def test_guard3_chronology_evidence_before_command(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence()
        ev["invocation"]["finished_at"] = "2026-08-09T00:00:03Z"
        result = confirm_provider_exhaustion(self._worker_result(), ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any(e["code"] == "CHRONOLOGY_VIOLATION" for e in result["errors"]))

    def test_guard4_clean_exit_not_exhaustion(self):
        from harness_contracts.v1.provider_evidence import confirm_provider_exhaustion
        ev, stderr_bytes = self._evidence({"invocation": {**self._evidence()[0]["invocation"], "exit_code": 0}})
        result = confirm_provider_exhaustion(self._worker_result(), ev, self._registry(), stderr_bytes=stderr_bytes)
        self.assertEqual(result["classification"], "NOT_EXHAUSTION")
        self.assertTrue(any("abnormal" in e["message"] for e in result["errors"]))


class TestAttemptClassification(unittest.TestCase):
    def _base_outcome(self, overrides=None):
        base = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 0,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": "0" * 64, "byte_length": 0},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
            "result_validation": {"present": False, "valid": False, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": None,
            "outcome": "COMPLETED",
            "fallback": None,
        }
        if overrides:
            base.update(overrides)
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        base["outcome_sha256"] = compute_sha256(canonical_bytes(base, omit={"outcome_sha256"}))
        return base

    def test_completed_pending_review(self):
        from harness_contracts.v1.classification import classify_attempt

        outcome = self._base_outcome({
            "raw_result": {"path": "results/p1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "COMPLETED",
        })
        result = classify_attempt(outcome, {}, None, None)
        self.assertEqual(result["attempt_class"], "COMPLETED_PENDING_REVIEW")


class TestAttemptClassificationPrecedence(unittest.TestCase):
    """Design 5.2 precedence rows."""

    def _make_outcome(self, overrides):
        base = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 0,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": "0" * 64, "byte_length": 0},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
            "result_validation": {"present": False, "valid": False, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": None,
            "outcome": "COMPLETED",
            "fallback": None,
        }
        base.update(overrides)
        return base

    def _classify(self, outcome):
        from harness_contracts.v1.classification import classify_attempt
        return classify_attempt(outcome, {}, None, None)

    def test_authority_violation_guard_denials(self):
        outcome = self._make_outcome({
            "authority": {"guard_denials": [{"tool": "x", "target_path": None, "rule_id": "r"}], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "AUTHORITY_VIOLATION")
        self.assertEqual(result["cause"], "authority_violation")

    def test_authority_violation_undeclared_changed_paths(self):
        outcome = self._make_outcome({
            "authority": {"guard_denials": [], "undeclared_changed_paths": ["foo.py"], "governed_path_touches": [], "hard_stop_matches": []},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "AUTHORITY_VIOLATION")
        self.assertEqual(result["cause"], "authority_violation")

    def test_authority_hard_stop_governed_path(self):
        outcome = self._make_outcome({
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": ["PLAN.md"], "hard_stop_matches": []},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "AUTHORITY_VIOLATION")
        self.assertEqual(result["cause"], "authority_hard_stop")

    def test_authority_hard_stop_hard_stop_matches(self):
        outcome = self._make_outcome({
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": ["foo.py"]},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "AUTHORITY_VIOLATION")
        self.assertEqual(result["cause"], "authority_hard_stop")

    def test_human_decision(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "HUMAN_REQUIRED",
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "HUMAN_DECISION")

    def test_contract_invalid(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": False, "error_codes": ["MISSING_FIELD"], "error_count": 1},
            "outcome": "FAILED",
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "CONTRACT_INVALID")

    def test_infra_retryable_timed_out(self):
        outcome = self._make_outcome({
            "invocation": {"argv": ["x"], "cwd": "scripts", "started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:10Z", "exit_code": None, "signal": None, "timed_out": True, "wall_clock_seconds": 10},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "INFRA_RETRYABLE")

    def test_infra_retryable_signal(self):
        outcome = self._make_outcome({
            "invocation": {"argv": ["x"], "cwd": "scripts", "started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:10Z", "exit_code": None, "signal": 9, "timed_out": False, "wall_clock_seconds": 10},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "INFRA_RETRYABLE")

    def test_infra_retryable_nonzero_exit(self):
        outcome = self._make_outcome({
            "invocation": {"argv": ["x"], "cwd": "scripts", "started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:10Z", "exit_code": 1, "signal": None, "timed_out": False, "wall_clock_seconds": 10},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "INFRA_RETRYABLE")

    def test_worker_quality(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "FAILED",
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "WORKER_QUALITY")

    def test_completed_pending_review(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "COMPLETED",
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "COMPLETED_PENDING_REVIEW")

    def test_catch_all_evidence_missing(self):
        outcome = self._make_outcome({})
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "CONTRACT_INVALID")
        self.assertEqual(result["error_codes"], ["EVIDENCE_MISSING"])

    def test_d13_authority_wins_over_exhaustion(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "CHECKPOINTED",
            "authority": {"guard_denials": [{"tool": "t", "target_path": None, "rule_id": "r"}], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "fallback": {"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe", "reassign_to": "sonnet_implementation"},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "AUTHORITY_VIOLATION")

    def test_d14_human_decision_wins_over_exhaustion(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "HUMAN_REQUIRED",
            "fallback": {"reason": "confirmed_rate_limit_exhaustion", "provider_evidence_id": "pe", "reassign_to": "sonnet_implementation"},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "HUMAN_DECISION")

    def test_d18_zero_byte_clean_exit_is_contract_invalid(self):
        outcome = self._make_outcome({
            "invocation": {"argv": ["x"], "cwd": "scripts", "started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:10Z", "exit_code": 0, "signal": None, "timed_out": False, "wall_clock_seconds": 10},
            "raw_result": {"path": None, "sha256": None, "byte_length": 0},
        })
        result = self._classify(outcome)
        self.assertEqual(result["attempt_class"], "CONTRACT_INVALID")

    def test_d20_classifier_purity(self):
        outcome = self._make_outcome({
            "raw_result": {"path": "x", "sha256": "0" * 64, "byte_length": 10},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "outcome": "COMPLETED",
        })
        result1 = self._classify(outcome)
        result2 = self._classify(outcome)
        self.assertEqual(result1, result2)


class TestReassignmentRecordValidator(unittest.TestCase):
    def test_minimal_reassignment_validates(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.reassignment import validate_reassignment

        value = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "from_lane": "kimi_implementation",
            "to_lane": "sonnet_implementation",
            "reassigned_at": "2026-08-09T00:00:00Z",
            "at_event_seq": 10,
            "kimi_attempt": 1,
            "preserved": {
                "changed_files": [],
                "worker_result": {"result_id": "r1", "result_sha256": "0" * 64, "path": "results/p1/1/worker_result.json"},
                "provider_evidence": {"evidence_id": "e1", "evidence_sha256": "0" * 64, "path": "results/p1/1/provider_evidence.json"},
                "attempt_outcome": {"outcome_sha256": "0" * 64, "path": "results/p1/1/attempt_outcome.json"},
                "checkpoints": [],
                "verification_evidence": [],
                "remaining_criterion_ids": ["c1"],
                "journal_range": {
                    "first_seq": 1,
                    "last_seq": 10,
                    "first_event_sha256": "0" * 64,
                    "last_event_sha256": "0" * 64,
                },
            },
        }
        value["reassignment_sha256"] = compute_sha256(canonical_bytes(value, omit={"reassignment_sha256"}))
        result = validate_reassignment(value)
        self.assertTrue(result["valid"], result["errors"])


class TestReconciliationReport(unittest.TestCase):
    def test_healthy_reconciliation(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation

        fold_data = {
            "journal_head": {"seq": 3, "event_sha256": "0" * 64},
            "enrolled_packet_ids": {"p1"},
            "packets": [
                {
                    "packet_id": "p1",
                    "state": "ACCEPTED",
                    "lane": "kimi_implementation",
                    "enqueue_seq": 1,
                    "attempts_started": 1,
                    "infra_retries_used": 0,
                    "revise_cycles_used": 0,
                    "revise_verdicts": 0,
                    "reassignment_used": False,
                    "open_attempt": None,
                    "last_event_seq": 3,
                    "last_event_sha256": "0" * 64,
                    "quarantine_reason": None,
                    "human_required_reasons": [],
                    "blocked_on": [],
                    "attention_codes": [],
                    "retry_limit": 2,
                }
            ],
            "activity": {
                "attempts_started_total": 1,
                "infra_retries_total": 0,
                "revise_verdicts_total": 0,
                "revise_cycles_total": 0,
                "reassignments_total": 0,
                "results_recorded_total": 1,
                "verdicts_recorded_total": 1,
                "intents_abandoned_total": 0,
                "locks_reclaimed_total": 0,
            },
            "integrity": {
                "journal_chain_valid": True,
                "state_cache_in_sync": True,
                "duplicate_packet_ids": [],
                "omitted_packet_ids": [],
                "unenrolled_dependencies": [],
                "seal_mismatches": [],
                "accounting_violations": [],
                "preserved_evidence_mismatches": [],
            },
            "attention_required": [],
        }
        report = compute_reconciliation(fold_data)
        self.assertTrue(report["reconciliation"]["all_invariants_passed"])
        self.assertEqual(report["inventory_total"], 1)
        self.assertEqual(report["by_state"]["ACCEPTED"], 1)


class TestReconciliationIntegrityFixtures(unittest.TestCase):
    """Defect 5 regression: integrity lists populate and I10 fires."""

    def _packet_row(self, pid, attempts_started=0, retry_limit=2):
        return {
            "packet_id": pid,
            "state": "READY",
            "lane": "kimi_implementation",
            "enqueue_seq": 1,
            "attempts_started": attempts_started,
            "infra_retries_used": 0,
            "revise_cycles_used": 0,
            "revise_verdicts": 0,
            "reassignment_used": False,
            "open_attempt": None,
            "last_event_seq": 1,
            "last_event_sha256": "0" * 64,
            "quarantine_reason": None,
            "human_required_reasons": [],
            "blocked_on": [],
            "attention_codes": [],
            "retry_limit": retry_limit,
        }

    def _fold(self, packets, enrolled=None):
        return {
            "journal_head": {"seq": 1, "event_sha256": "0" * 64},
            "enrolled_packet_ids": set(enrolled) if enrolled is not None else {p["packet_id"] for p in packets},
            "packets": packets,
            "activity": {
                "attempts_started_total": 0,
                "infra_retries_total": 0,
                "revise_verdicts_total": 0,
                "revise_cycles_total": 0,
                "reassignments_total": 0,
                "results_recorded_total": 0,
                "verdicts_recorded_total": 0,
                "intents_abandoned_total": 0,
                "locks_reclaimed_total": 0,
            },
            "integrity": {
                "journal_chain_valid": True,
                "state_cache_in_sync": True,
                "duplicate_packet_ids": [],
                "omitted_packet_ids": [],
                "unenrolled_dependencies": [],
                "seal_mismatches": [],
                "accounting_violations": [],
                "preserved_evidence_mismatches": [],
            },
            "attention_required": [],
        }

    def test_g2_duplicate_packet_id_populates_integrity_list(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation
        rows = [self._packet_row("P1"), self._packet_row("P1")]
        report = compute_reconciliation(self._fold(rows, enrolled={"P1"}))
        self.assertFalse(report["reconciliation"]["all_invariants_passed"])
        self.assertIn("P1", report["integrity"]["duplicate_packet_ids"])

    def test_i10_attempts_exceed_retry_limit(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation
        row = self._packet_row("P1", attempts_started=4, retry_limit=2)
        row["infra_retries_used"] = 3  # keep I9 accounting identity satisfied: 3 == 4-1
        report = compute_reconciliation(self._fold([row], enrolled={"P1"}))
        self.assertFalse(report["reconciliation"]["all_invariants_passed"])
        self.assertIn("P1", report["integrity"]["accounting_violations"])
        self.assertTrue(
            any(item["code"] == "retry_budget_exceeded" for item in report["attention_required"]),
            report["attention_required"],
        )


class TestJournalIllegalTransitions(unittest.TestCase):
    """Defect 1 regression: illegal transitions must return INVALID_TRANSITION, not crash."""

    def _run_started(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1234},
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
                        "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
                        "reassignment": 1, "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def test_illegal_transition_accepted_to_ready_is_invalid_not_crash(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = {
            "schema_version": 1,
            "seq": 2,
            "event_id": "evt-2",
            "event_type": "STATE_TRANSITION",
            "event_at": "2026-08-09T00:00:01Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": "p1",
            "intent_id": "intent-2",
            "from_state": "ACCEPTED",
            "to_state": "READY",
            "cause": "revision_requeued",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": {"satisfied_by": [], "source_verdict": None, "revise_cycle": None},
                "recovery": None,
                "run": None,
                "report": None,
            },
            "prev_event_sha256": prev["event_sha256"],
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "INVALID_TRANSITION" for e in result["errors"]))


class TestJournalLockReclaimed(unittest.TestCase):
    """Defect 4 regression: LOCK_RECLAIMED must accept real claim classifications."""

    def _run_started(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1234},
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
                        "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
                        "reassignment": 1, "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def test_lock_reclaimed_with_stale_prior_boot_validates(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = {
            "schema_version": 1,
            "seq": 2,
            "event_id": "lock-2",
            "event_type": "LOCK_RECLAIMED",
            "event_at": "2026-08-09T00:00:01Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": "p1",
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": {
                    "abandoned_intent_id": None,
                    "abandoned_at_stage": None,
                    "consecutive_abandonments": None,
                    "prior_claim": {
                        "claim_sha256": "0" * 64,
                        "path": "locks/p1.lock.json",
                        "classification": "STALE_PRIOR_BOOT",
                        "coordinator_id": "coord-old",
                        "pid": 1234,
                        "boot_id": "boot-old",
                        "hostname": "host-1",
                    },
                    "truncation": None,
                    "review_failure": None,
                },
                "run": None,
                "report": None,
            },
            "prev_event_sha256": prev["event_sha256"],
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event, prev_event=prev)
        self.assertTrue(result["valid"], result["errors"])


class TestReconciliationI5SetEquality(unittest.TestCase):
    """Defect 2 regression: I5 must detect a dropped+invented packet swap."""

    def _packet_row(self, pid, state="READY", retry_limit=2):
        return {
            "packet_id": pid,
            "state": state,
            "lane": "kimi_implementation",
            "enqueue_seq": 1,
            "attempts_started": 0,
            "infra_retries_used": 0,
            "revise_cycles_used": 0,
            "revise_verdicts": 0,
            "reassignment_used": False,
            "open_attempt": None,
            "last_event_seq": 1,
            "last_event_sha256": "0" * 64,
            "quarantine_reason": None,
            "human_required_reasons": [],
            "blocked_on": [],
            "attention_codes": [],
            "retry_limit": retry_limit,
        }

    def test_g4_dropped_and_invented_packet_swap_fails_i5(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation

        fold_data = {
            "journal_head": {"seq": 1, "event_sha256": "0" * 64},
            "enrolled_packet_ids": {"P1", "P2"},
            "packets": [self._packet_row("P1"), self._packet_row("P9")],
            "activity": {
                "attempts_started_total": 0,
                "infra_retries_total": 0,
                "revise_verdicts_total": 0,
                "revise_cycles_total": 0,
                "reassignments_total": 0,
                "results_recorded_total": 0,
                "verdicts_recorded_total": 0,
                "intents_abandoned_total": 0,
                "locks_reclaimed_total": 0,
            },
            "integrity": {
                "journal_chain_valid": True,
                "state_cache_in_sync": True,
                "duplicate_packet_ids": [],
                "omitted_packet_ids": [],
                "unenrolled_dependencies": [],
                "seal_mismatches": [],
                "accounting_violations": [],
                "preserved_evidence_mismatches": [],
            },
            "attention_required": [],
        }
        report = compute_reconciliation(fold_data)
        self.assertFalse(report["reconciliation"]["all_invariants_passed"])
        omitted = set(report["integrity"]["omitted_packet_ids"])
        self.assertIn("P2", omitted)
        self.assertIn("P9", omitted)


class TestProviderExhaustedEndToEnd(unittest.TestCase):
    """Defect 3 regression: a fully valid exhaustion claim reaches PROVIDER_EXHAUSTED."""

    def _registry(self):
        return {
            "schema_version": 1,
            "registry_id": "reg-1",
            "providers": {
                "kimi": [
                    {
                        "rule_id": "r1",
                        "channel": "stderr",
                        "match_kind": "substring",
                        "pattern": "rate limit exceeded",
                        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
                        "captured_from": {
                            "sample_path": "trust/samples/kimi_rate_limit.json",
                            "sample_sha256": "0" * 64,
                            "captured_at": "2026-08-09T00:00:00Z",
                        },
                    }
                ]
            },
        }

    def test_valid_exhaustion_classifies_provider_exhausted(self):
        import hashlib
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.classification import classify_attempt

        stderr_text = "something\nrate limit exceeded\n"
        stderr_bytes = stderr_text.encode("utf-8")
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()

        outcome = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 1,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
            "raw_result": {"path": "results/p1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": "0" * 64,
            "outcome": "CHECKPOINTED",
            "fallback": {
                "reason": "confirmed_rate_limit_exhaustion",
                "provider_evidence_id": "pe-1",
                "reassign_to": "sonnet_implementation",
            },
        }
        outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))

        worker_result = {
            "result_id": "wr-1",
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "worker": {"worker_id": "w1", "session_id": "s1", "lane": "kimi_implementation", "provider": "kimi", "model": "k2"},
            "started_at": "2026-08-09T00:00:00Z",
            "finished_at": "2026-08-09T00:00:05Z",
            "starting_revision": "0" * 40,
            "ending_revision": "0" * 40,
            "outcome": "CHECKPOINTED",
            "fallback": outcome["fallback"],
            "commands": [
                {
                    "command_id": "c1",
                    "argv": ["true"],
                    "cwd": "scripts",
                    "timestamps": {"started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:04Z"},
                    "exit_code": 0,
                    "outcome": "PASSED",
                    "stdout_sha256": "0" * 64,
                    "stderr_sha256": "0" * 64,
                }
            ],
        }

        provider_evidence = {
            "schema_version": 1,
            "evidence_id": "pe-1",
            "packet_id": "p1",
            "attempt": 1,
            "provider": "kimi",
            "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
            "invocation": {
                "argv": ["python", "worker.py"],
                "exit_code": 1,
                "signal": None,
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "timed_out": False,
            },
            "stdout_path": "results/p1/1/stdout.bin",
            "stdout_sha256": "0" * 64,
            "stderr_path": "results/p1/1/stderr.bin",
            "stderr_sha256": stderr_sha256,
            "matched_signal": {
                "channel": "stderr",
                "rule_id": "r1",
                "registry_id": "reg-1",
                "verbatim_excerpt": "rate limit exceeded",
                "byte_offset": 10,
                "byte_length": 19,
            },
            "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        }
        provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))

        result = classify_attempt(
            outcome,
            {},
            provider_evidence,
            self._registry(),
            stdout_bytes=b"",
            stderr_bytes=stderr_bytes,
            worker_result=worker_result,
        )
        self.assertEqual(result["attempt_class"], "PROVIDER_EXHAUSTED", result)

    def test_guard3_chronology_without_worker_result_rejects_pre_dated_evidence(self):
        """Guard 3 must consult outcome_record.invocation timestamps even when no worker_result is supplied."""
        import hashlib
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.classification import classify_attempt

        stderr_text = "something\nrate limit exceeded\n"
        stderr_bytes = stderr_text.encode("utf-8")
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()

        outcome = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 1,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
            "raw_result": {"path": "results/p1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": "0" * 64,
            "outcome": "CHECKPOINTED",
            "fallback": {
                "reason": "confirmed_rate_limit_exhaustion",
                "provider_evidence_id": "pe-1",
                "reassign_to": "sonnet_implementation",
            },
        }
        outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))

        provider_evidence = {
            "schema_version": 1,
            "evidence_id": "pe-1",
            "packet_id": "p1",
            "attempt": 1,
            "provider": "kimi",
            "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
            "invocation": {
                "argv": ["python", "worker.py"],
                "exit_code": 1,
                "signal": None,
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:05Z",
                "timed_out": False,
            },
            "stdout_path": "results/p1/1/stdout.bin",
            "stdout_sha256": "0" * 64,
            "stderr_path": "results/p1/1/stderr.bin",
            "stderr_sha256": stderr_sha256,
            "matched_signal": {
                "channel": "stderr",
                "rule_id": "r1",
                "registry_id": "reg-1",
                "verbatim_excerpt": "rate limit exceeded",
                "byte_offset": 10,
                "byte_length": 19,
            },
            "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        }
        provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))

        result = classify_attempt(
            outcome,
            {},
            provider_evidence,
            self._registry(),
            stdout_bytes=b"",
            stderr_bytes=stderr_bytes,
        )
        self.assertNotEqual(result["attempt_class"], "PROVIDER_EXHAUSTED", result)

    def test_guard3_chronology_without_worker_result_accepts_post_dated_evidence(self):
        import hashlib
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.classification import classify_attempt

        stderr_text = "something\nrate limit exceeded\n"
        stderr_bytes = stderr_text.encode("utf-8")
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()

        outcome = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 1,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
            "raw_result": {"path": "results/p1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": "0" * 64,
            "outcome": "CHECKPOINTED",
            "fallback": {
                "reason": "confirmed_rate_limit_exhaustion",
                "provider_evidence_id": "pe-1",
                "reassign_to": "sonnet_implementation",
            },
        }
        outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))

        provider_evidence = {
            "schema_version": 1,
            "evidence_id": "pe-1",
            "packet_id": "p1",
            "attempt": 1,
            "provider": "kimi",
            "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
            "invocation": {
                "argv": ["python", "worker.py"],
                "exit_code": 1,
                "signal": None,
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "timed_out": False,
            },
            "stdout_path": "results/p1/1/stdout.bin",
            "stdout_sha256": "0" * 64,
            "stderr_path": "results/p1/1/stderr.bin",
            "stderr_sha256": stderr_sha256,
            "matched_signal": {
                "channel": "stderr",
                "rule_id": "r1",
                "registry_id": "reg-1",
                "verbatim_excerpt": "rate limit exceeded",
                "byte_offset": 10,
                "byte_length": 19,
            },
            "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        }
        provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))

        result = classify_attempt(
            outcome,
            {},
            provider_evidence,
            self._registry(),
            stdout_bytes=b"",
            stderr_bytes=stderr_bytes,
        )
        self.assertEqual(result["attempt_class"], "PROVIDER_EXHAUSTED", result)


class TestPacketStateValidator(unittest.TestCase):
    def _valid(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        value = {
            "schema_version": 1,
            "packet_id": "p1",
            "enqueue_seq": 1,
            "state": "READY",
            "lane": "kimi_implementation",
            "dependency_ids": [],
            "packet_sha256": "0" * 64,
            "attempts_started": 0,
            "infra_retries_used": 0,
            "revise_cycles_used": 0,
            "revise_verdicts": 0,
            "reassignment_used": False,
            "open_attempt": None,
            "earliest_next_attempt_at": None,
            "last_event_seq": 1,
            "terminal_seal_sha256": None,
            "lane_history": [{"lane": "kimi_implementation", "since_event_seq": 1}],
            "attempts": [],
            "quarantine_reason": None,
            "human_required_reasons": [],
            "last_applied_seq": 0,
            "last_applied_event_sha256": "0" * 64,
        }
        value["state_sha256"] = compute_sha256(canonical_bytes(value, omit={"state_sha256"}))
        return value

    def test_minimal_packet_state_validates(self):
        from harness_contracts.v1.packet_state import validate_packet_state
        result = validate_packet_state(self._valid())
        self.assertTrue(result["valid"], result["errors"])

    def test_schema_version_one_accepted(self):
        from harness_contracts.v1.packet_state import validate_packet_state
        value = self._valid()
        value["schema_version"] = 1
        result = validate_packet_state(value)
        self.assertTrue(result["valid"], result["errors"])

    def test_schema_version_two_rejected(self):
        from harness_contracts.v1.packet_state import validate_packet_state
        value = self._valid()
        value["schema_version"] = 2
        result = validate_packet_state(value)
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "INVALID_VALUE" for e in result["errors"]))

    def test_schema_version_missing_rejected(self):
        from harness_contracts.v1.packet_state import validate_packet_state
        value = self._valid()
        del value["schema_version"]
        result = validate_packet_state(value)
        self.assertFalse(result["valid"])
        self.assertTrue(any(e["code"] == "MISSING_FIELD" for e in result["errors"]))


class TestClaimClassifierBranches(unittest.TestCase):
    """Design 1.5 classify_claim precedence and fail-closed behaviour."""

    def _trusted(self, **overrides):
        base = {
            "coordinator_id": "coord-1",
            "hostname": "host-1",
            "boot_id": "boot-1",
            "pid": 1234,
            "live_coordinator_ids": set(),
            "now": "2026-08-09T00:00:00Z",
        }
        base.update(overrides)
        return base

    def _record(self, **overrides):
        base = {
            "hostname": "host-1",
            "boot_id": "boot-1",
            "coordinator_id": "coord-1",
            "pid": 1234,
        }
        base.update(overrides)
        return base

    def test_foreign_host(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(self._record(hostname="other"), self._trusted())
        self.assertEqual(result["status"], "FOREIGN_HOST")

    def test_stale_prior_boot(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(self._record(boot_id="boot-old"), self._trusted())
        self.assertEqual(result["status"], "STALE_PRIOR_BOOT")

    def test_self_owned(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(self._record(), self._trusted())
        self.assertEqual(result["status"], "SELF_OWNED")

    def test_foreign_live(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(self._record(coordinator_id="coord-2"), self._trusted(live_coordinator_ids={"coord-2"}))
        self.assertEqual(result["status"], "FOREIGN_LIVE")

    def test_stale_same_boot(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(self._record(coordinator_id="coord-2"), self._trusted(live_coordinator_ids={"coord-3"}))
        self.assertEqual(result["status"], "STALE_SAME_BOOT")

    def test_c11_lease_expiry_not_liveness_proof(self):
        from harness_contracts.v1.claim import classify_claim
        result = classify_claim(
            self._record(coordinator_id="coord-2", lease_seconds=1),
            self._trusted(live_coordinator_ids={"coord-2"}),
        )
        self.assertEqual(result["status"], "FOREIGN_LIVE")

    def test_trust_context_missing_coordinator_id(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["coordinator_id"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")

    def test_trust_context_missing_hostname(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["hostname"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")

    def test_trust_context_missing_boot_id(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["boot_id"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")

    def test_trust_context_missing_pid(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["pid"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")

    def test_trust_context_missing_live_coordinator_ids(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["live_coordinator_ids"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")

    def test_trust_context_missing_now(self):
        from harness_contracts.v1.claim import classify_claim
        trusted = self._trusted()
        del trusted["now"]
        result = classify_claim(self._record(), trusted)
        self.assertEqual(result["status"], "TRUST_CONTEXT_MISSING")


class TestPython39Syntax(unittest.TestCase):
    """H10: new O3 contract modules must not use PEP 604 X | Y annotations."""

    def test_scanner_flags_pep604_variable_annotation(self):
        source = "from __future__ import annotations\nx: int | str\n"
        self.assertEqual(_find_pep604_in_annotations(source), [2])

    def test_scanner_flags_pep604_argument_and_return_annotations(self):
        source = (
            "from __future__ import annotations\n"
            "def f(x: int | str) -> bool | None:\n"
            "    pass\n"
        )
        self.assertEqual(_find_pep604_in_annotations(source), [2])

    def test_scanner_ignores_non_annotation_bit_or(self):
        source = "x = {1} | {2}\ny: Optional[int]\n"
        self.assertEqual(_find_pep604_in_annotations(source), [])

    def test_no_pep604_unions_in_o3_contract_modules(self):
        violations: List[str] = []
        for filename in _O3_CONTRACT_MODULES:
            path = os.path.join(_CONTRACTS_DIR, filename)
            self.assertTrue(
                os.path.isfile(path),
                "O3 contract module missing: {}".format(filename),
            )
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
            for line_no in _find_pep604_in_annotations(source):
                violations.append("{}:{}".format(filename, line_no))
        self.assertEqual(violations, [])


class TestPacketEnrollmentValidation(unittest.TestCase):
    """Defect A regression: PACKET_ENROLLED must respect CAUSE_EDGES and dependency coupling."""

    def _run_started(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1234},
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
                        "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
                        "reassignment": 1, "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def _packet_payload(self, dependency_ids):
        return {
            "packet_sha256": "0" * 64,
            "packet_path": "packets/p1.json",
            "lane": "kimi_implementation",
            "dependency_ids": list(dependency_ids),
            "sonnet_reassignment_allowed": False,
            "retry_limit": 2,
            "enqueue_seq": 1,
        }

    def _enrolled_event(self, prev, to_state, dependency_ids, seq=2):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        event = {
            "schema_version": 1,
            "seq": seq,
            "event_id": "evt-{}".format(seq),
            "event_type": "PACKET_ENROLLED",
            "event_at": "2026-08-09T00:00:01Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": "p1",
            "intent_id": "intent-1",
            "from_state": None,
            "to_state": to_state,
            "cause": "enrollment",
            "payload": {
                "packet": self._packet_payload(dependency_ids),
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
            },
            "prev_event_sha256": prev["event_sha256"],
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def test_defect_a_enrollment_to_illegal_states_rejected(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        illegal = ("ACCEPTED", "QUARANTINED", "HUMAN_REQUIRED", "RUNNING", "REVIEW", "REVISE")
        for to_state in illegal:
            with self.subTest(to_state=to_state):
                event = self._enrolled_event(prev, to_state, [])
                result = validate_journal_event(event, prev_event=prev)
                self.assertFalse(result["valid"], result)
                self.assertTrue(
                    any(e["code"] == "INVALID_TRANSITION" for e in result["errors"]),
                    result["errors"],
                )

    def test_defect_a_enrollment_blocked_with_dependencies_accepted(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._enrolled_event(prev, "BLOCKED", ["dep1"])
        result = validate_journal_event(event, prev_event=prev)
        self.assertTrue(result["valid"], result["errors"])

    def test_defect_a_enrollment_ready_without_dependencies_accepted(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._enrolled_event(prev, "READY", [])
        result = validate_journal_event(event, prev_event=prev)
        self.assertTrue(result["valid"], result["errors"])

    def test_defect_a_enrollment_ready_with_dependencies_mismatch_rejected(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._enrolled_event(prev, "READY", ["dep1"])
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "INVALID_VALUE" for e in result["errors"]), result["errors"])

    def test_defect_a_enrollment_blocked_without_dependencies_mismatch_rejected(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._enrolled_event(prev, "BLOCKED", [])
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "INVALID_VALUE" for e in result["errors"]), result["errors"])


class TestJournalCauseEdgesAndPermittedCauses(unittest.TestCase):
    """General forms of the cause/edge checks."""

    def _run_started(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1234},
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
                        "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
                        "reassignment": 1, "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def test_non_enrollment_cause_edge_rejected(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = {
            "schema_version": 1,
            "seq": 2,
            "event_id": "evt-2",
            "event_type": "VERDICT_RECORDED",
            "event_at": "2026-08-09T00:00:01Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": "p1",
            "intent_id": "intent-1",
            "from_state": "REVIEW",
            "to_state": "ACCEPTED",
            "cause": "verdict_revise",
            "payload": {
                "packet": None,
                "attempt": {
                    "attempt": 1,
                    "lane": "kimi_implementation",
                    "worker": {"worker_id": "w1", "session_id": "s1", "provider": "kimi", "model": "k2"},
                    "claim_sha256": "0" * 64,
                    "worktree_path": None,
                },
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
            },
            "prev_event_sha256": prev["event_sha256"],
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(
            any(
                e["code"] == "INVALID_TRANSITION" and "verdict_revise" in e["message"]
                for e in result["errors"]
            ),
            result["errors"],
        )

    def test_cause_not_permitted_for_event_type_rejected(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.journal import validate_journal_event

        event = self._run_started()
        event["cause"] = "enrollment"
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event)
        self.assertFalse(result["valid"], result)
        self.assertTrue(
            any(
                e["code"] == "INVALID_TRANSITION" and "not permitted for event type" in e["message"]
                for e in result["errors"]
            ),
            result["errors"],
        )


class TestJournalChainIntegrity(unittest.TestCase):
    """A6, A7, A8, A9, A11, and prev-hash mismatch chain checks."""

    def _run_started(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        event = {
            "schema_version": 1,
            "seq": 1,
            "event_id": "run-1",
            "event_type": "RUN_STARTED",
            "event_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "packet_id": None,
            "intent_id": None,
            "from_state": None,
            "to_state": None,
            "cause": "none",
            "payload": {
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": {
                    "coordinator": {"coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "pid": 1234},
                    "trust_roots": {
                        "reviewer_sessions_path": "trust/reviewer_sessions.json",
                        "reviewer_sessions_sha256": "0" * 64,
                        "provider_signals_path": "trust/provider_signals.json",
                        "provider_signals_sha256": "0" * 64,
                    },
                    "contract_versions": {
                        "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1,
                        "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1,
                        "reassignment": 1, "reconciliation": 1,
                    },
                    "end_reason": None,
                    "end_detail": None,
                    "disabled_lanes": [],
                },
                "report": None,
            },
            "prev_event_sha256": "0" * 64,
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def _second_run_started(self, prev, **overrides):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        event = self._run_started()
        event.update({
            "seq": 2,
            "event_id": "evt-2",
            "event_at": "2026-08-09T00:00:01Z",
            "prev_event_sha256": prev["event_sha256"],
        })
        event.update(overrides)
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        return event

    def test_a6_sequence_gap_non_consecutive_seq(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._second_run_started(prev, seq=3)
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "SEQUENCE_GAP" for e in result["errors"]), result["errors"])

    def test_a7_genesis_event_with_non_zero_prev_hash(self):
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        from harness_contracts.v1.journal import validate_journal_event

        event = self._run_started()
        event["prev_event_sha256"] = "1" * 64
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "JOURNAL_CHAIN_BROKEN" for e in result["errors"]), result["errors"])

    def test_a8_wrong_event_sha256(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._second_run_started(prev)
        event["event_sha256"] = "1" * 64
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "EVIDENCE_HASH_MISMATCH" for e in result["errors"]), result["errors"])

    def test_a9_event_at_before_predecessor(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._second_run_started(prev, event_at="2025-08-09T00:00:00Z")
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "CHRONOLOGY_VIOLATION" for e in result["errors"]), result["errors"])

    def test_a11_schema_version_two_rejected(self):
        from harness_contracts.v1.journal import validate_journal_event

        event = self._run_started()
        event["schema_version"] = 2
        # Recompute hash so the only failure is the version value, not the hash.
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "INVALID_VALUE" and "schema_version" in e["path"] for e in result["errors"]), result["errors"])

    def test_prev_hash_mismatch_rejects_non_genesis_event(self):
        from harness_contracts.v1.journal import validate_journal_event

        prev = self._run_started()
        event = self._second_run_started(prev, prev_event_sha256="1" * 64)
        result = validate_journal_event(event, prev_event=prev)
        self.assertFalse(result["valid"], result)
        self.assertTrue(any(e["code"] == "JOURNAL_CHAIN_BROKEN" for e in result["errors"]), result["errors"])


class TestAttemptClassAndCauseEdgesHygiene(unittest.TestCase):
    """H3 and H4 static contract hygiene checks."""

    def test_h3_class_actions_keys_equal_attempt_classes(self):
        from harness_contracts.v1.classification import ATTEMPT_CLASSES, CLASS_ACTIONS

        self.assertEqual(set(CLASS_ACTIONS.keys()), ATTEMPT_CLASSES)

    def test_h4_non_null_cause_edges_subset_of_valid_transitions(self):
        from harness_contracts.v1.journal import CAUSE_EDGES
        from harness_contracts.v1.transition import VALID_TRANSITIONS

        all_edges = set(edge for edges in CAUSE_EDGES.values() for edge in edges)
        non_null = {edge for edge in all_edges if edge[0] is not None and edge[1] is not None}
        self.assertTrue(
            non_null.issubset(VALID_TRANSITIONS),
            "Non-null CAUSE_EDGES not covered by VALID_TRANSITIONS: {}".format(non_null - VALID_TRANSITIONS),
        )


class TestReconciliationRequiredCases(unittest.TestCase):
    """G6, G7, G8 reconciliation invariants."""

    def _packet_row(self, pid, **overrides):
        row = {
            "packet_id": pid,
            "state": "READY",
            "lane": "kimi_implementation",
            "enqueue_seq": 1,
            "attempts_started": 0,
            "infra_retries_used": 0,
            "revise_cycles_used": 0,
            "revise_verdicts": 0,
            "reassignment_used": False,
            "open_attempt": None,
            "last_event_seq": 1,
            "last_event_sha256": "0" * 64,
            "quarantine_reason": None,
            "human_required_reasons": [],
            "blocked_on": [],
            "attention_codes": [],
            "retry_limit": 2,
        }
        row.update(overrides)
        return row

    def _fold(self, packets, enrolled=None, journal_chain_valid=True):
        return {
            "report_id": "report-1",
            "generated_at": "2026-08-09T00:00:00Z",
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "state_root_id": "root-1",
            "journal_head": {"seq": 1, "event_sha256": "0" * 64},
            "enrolled_packet_ids": set(enrolled) if enrolled is not None else {p["packet_id"] for p in packets},
            "packets": packets,
            "activity": {
                "attempts_started_total": 0,
                "infra_retries_total": 0,
                "revise_verdicts_total": 0,
                "revise_cycles_total": 0,
                "reassignments_total": 0,
                "results_recorded_total": 0,
                "verdicts_recorded_total": 0,
                "intents_abandoned_total": 0,
                "locks_reclaimed_total": 0,
            },
            "integrity": {
                "journal_chain_valid": journal_chain_valid,
                "state_cache_in_sync": True,
                "duplicate_packet_ids": [],
                "omitted_packet_ids": [],
                "unenrolled_dependencies": [],
                "seal_mismatches": [],
                "accounting_violations": [],
                "preserved_evidence_mismatches": [],
            },
            "attention_required": [],
        }

    def test_g6_i9_accounting_identity_violation(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation

        row = self._packet_row("P1", attempts_started=2)
        report = compute_reconciliation(self._fold([row], enrolled={"P1"}))
        self.assertFalse(report["reconciliation"]["all_invariants_passed"])
        self.assertIn("P1", report["integrity"]["accounting_violations"])
        self.assertTrue(
            any(item["code"] == "accounting_identity_violation" for item in report["attention_required"]),
            report["attention_required"],
        )

    def test_g7_journal_chain_invalid_marks_all_invariants_failed(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation

        row = self._packet_row("P1")
        report = compute_reconciliation(self._fold([row], enrolled={"P1"}, journal_chain_valid=False))
        self.assertFalse(report["reconciliation"]["all_invariants_passed"])

    def test_g8_content_sha256_deterministic_across_report_identity(self):
        from harness_contracts.v1.reconciliation import compute_reconciliation

        base = self._fold([self._packet_row("P1")], enrolled={"P1"})
        report_a = compute_reconciliation(base)

        variant = dict(base)
        variant.update({
            "report_id": "report-2",
            "generated_at": "2026-08-09T00:00:01Z",
            "coordinator_id": "coord-2",
            "run_id": "run-2",
        })
        report_b = compute_reconciliation(variant)

        self.assertEqual(report_a["content_sha256"], report_b["content_sha256"])
        self.assertNotEqual(report_a["report_sha256"], report_b["report_sha256"])


class TestProviderExhaustionChronologyReplay(unittest.TestCase):
    """Defect B regression: Guard 3 must be deterministic across live/replay call shapes."""

    def _registry(self):
        return {
            "schema_version": 1,
            "registry_id": "reg-1",
            "providers": {
                "kimi": [
                    {
                        "rule_id": "r1",
                        "channel": "stderr",
                        "match_kind": "substring",
                        "pattern": "rate limit exceeded",
                        "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
                        "captured_from": {
                            "sample_path": "trust/samples/kimi_rate_limit.json",
                            "sample_sha256": "0" * 64,
                            "captured_at": "2026-08-09T00:00:00Z",
                        },
                    }
                ]
            },
        }

    def _make_inputs(self):
        import hashlib
        from harness_contracts.v1.canonical import compute_sha256, canonical_bytes

        stderr_text = "something\nrate limit exceeded\n"
        stderr_bytes = stderr_text.encode("utf-8")
        stderr_sha256 = hashlib.sha256(stderr_bytes).hexdigest()

        outcome = {
            "schema_version": 1,
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "coordinator_id": "coord-1",
            "run_id": "run-1",
            "lane": "kimi_implementation",
            "invocation": {
                "argv": ["python", "worker.py"],
                "cwd": "scripts",
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:10Z",
                "exit_code": 1,
                "signal": None,
                "timed_out": False,
                "wall_clock_seconds": 10,
            },
            "stdout": {"path": "results/p1/1/stdout.bin", "sha256": "0" * 64, "byte_length": 0},
            "stderr": {"path": "results/p1/1/stderr.bin", "sha256": stderr_sha256, "byte_length": len(stderr_bytes)},
            "raw_result": {"path": "results/p1/1/worker_result.json", "sha256": "0" * 64, "byte_length": 100},
            "result_validation": {"present": True, "valid": True, "error_codes": [], "error_count": 0},
            "authority": {"guard_denials": [], "undeclared_changed_paths": [], "governed_path_touches": [], "hard_stop_matches": []},
            "provider_evidence_sha256": "0" * 64,
            "outcome": "CHECKPOINTED",
            "fallback": {
                "reason": "confirmed_rate_limit_exhaustion",
                "provider_evidence_id": "pe-1",
                "reassign_to": "sonnet_implementation",
            },
        }
        outcome["outcome_sha256"] = compute_sha256(canonical_bytes(outcome, omit={"outcome_sha256"}))

        worker_result = {
            "result_id": "wr-1",
            "packet_id": "p1",
            "packet_sha256": "0" * 64,
            "attempt": 1,
            "worker": {"worker_id": "w1", "session_id": "s1", "lane": "kimi_implementation", "provider": "kimi", "model": "k2"},
            "started_at": "2026-08-09T00:00:00Z",
            "finished_at": "2026-08-09T00:00:05Z",
            "invocation": {
                "argv": ["python", "worker.py"],
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:05Z",
                "exit_code": 1,
                "timed_out": False,
            },
            "starting_revision": "0" * 40,
            "ending_revision": "0" * 40,
            "outcome": "CHECKPOINTED",
            "fallback": outcome["fallback"],
            "commands": [
                {
                    "command_id": "c1",
                    "argv": ["true"],
                    "cwd": "scripts",
                    "timestamps": {"started_at": "2026-08-09T00:00:00Z", "finished_at": "2026-08-09T00:00:04Z"},
                    "exit_code": 0,
                    "outcome": "PASSED",
                    "stdout_sha256": "0" * 64,
                    "stderr_sha256": "0" * 64,
                }
            ],
        }

        provider_evidence = {
            "schema_version": 1,
            "evidence_id": "pe-1",
            "packet_id": "p1",
            "attempt": 1,
            "provider": "kimi",
            "captured_by": {"role": "coordinator", "coordinator_id": "coord-1", "boot_id": "boot-1", "hostname": "host-1", "run_id": "run-1"},
            "invocation": {
                "argv": ["python", "worker.py"],
                "exit_code": 1,
                "signal": None,
                "started_at": "2026-08-09T00:00:00Z",
                "finished_at": "2026-08-09T00:00:08Z",
                "timed_out": False,
            },
            "stdout_path": "results/p1/1/stdout.bin",
            "stdout_sha256": "0" * 64,
            "stderr_path": "results/p1/1/stderr.bin",
            "stderr_sha256": stderr_sha256,
            "matched_signal": {
                "channel": "stderr",
                "rule_id": "r1",
                "registry_id": "reg-1",
                "verbatim_excerpt": "rate limit exceeded",
                "byte_offset": 10,
                "byte_length": 19,
            },
            "classification": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
        }
        provider_evidence["evidence_sha256"] = compute_sha256(canonical_bytes(provider_evidence, omit={"evidence_sha256"}))

        return outcome, provider_evidence, worker_result, stderr_bytes

    def test_defect_b_guard3_max_anchor_no_call_shape_divergence(self):
        from harness_contracts.v1.classification import classify_attempt

        outcome, provider_evidence, worker_result, stderr_bytes = self._make_inputs()

        with_worker = classify_attempt(
            outcome,
            {},
            provider_evidence,
            self._registry(),
            stdout_bytes=b"",
            stderr_bytes=stderr_bytes,
            worker_result=worker_result,
        )
        without_worker = classify_attempt(
            outcome,
            {},
            provider_evidence,
            self._registry(),
            stdout_bytes=b"",
            stderr_bytes=stderr_bytes,
        )
        self.assertEqual(
            with_worker["attempt_class"],
            without_worker["attempt_class"],
            "Live-ingest and replay call shapes diverged: {} vs {}".format(with_worker, without_worker),
        )


_O3_NEW_SCHEMA_FILES = (
    "attempt-outcome.schema.json",
    "claim.schema.json",
    "journal-event.schema.json",
    "packet-state.schema.json",
    "provider-evidence.schema.json",
    "provider-signals.schema.json",
    "queue.schema.json",
    "reassignment.schema.json",
    "reconciliation-report.schema.json",
    "terminal-seal.schema.json",
)


def _find_open_objects(node: Any, path: str = "$") -> List[str]:
    """Recursively find every JSON Schema object-type node (has
    "properties") that does NOT declare additionalProperties: false --
    H1's "closed schemas" fixture. Walks properties/items/oneOf/anyOf/
    allOf, the shapes these schemas actually use."""
    open_paths: List[str] = []
    if not isinstance(node, dict):
        return open_paths
    if "properties" in node and node.get("additionalProperties") is not False:
        open_paths.append(path)
    for key in ("properties",):
        for prop_name, prop_schema in (node.get(key) or {}).items():
            open_paths.extend(_find_open_objects(prop_schema, f"{path}.{prop_name}"))
    if "items" in node:
        open_paths.extend(_find_open_objects(node["items"], f"{path}[]"))
    for key in ("oneOf", "anyOf", "allOf"):
        for i, sub in enumerate(node.get(key) or []):
            open_paths.extend(_find_open_objects(sub, f"{path}/{key}[{i}]"))
    return open_paths


class TestO3SchemasWellFormedAndClosed(unittest.TestCase):
    """H1: every new JSON Schema exists, parses, and has
    additionalProperties: false at every object level -- closed schemas,
    consistent with this codebase's fail-closed posture everywhere else."""

    def test_every_new_schema_file_exists_and_parses(self):
        for filename in _O3_NEW_SCHEMA_FILES:
            with self.subTest(filename=filename):
                schema = _load_schema(filename)
                self.assertIsInstance(schema, dict)
                self.assertIn("type", schema)

    def test_every_new_schema_is_closed_at_every_object_level(self):
        for filename in _O3_NEW_SCHEMA_FILES:
            with self.subTest(filename=filename):
                schema = _load_schema(filename)
                open_paths = _find_open_objects(schema)
                self.assertEqual(open_paths, [], f"{filename} has open (additionalProperties != false) object(s) at: {open_paths}")


class TestO3RuntimeSchemaParity(unittest.TestCase):
    """H2: required-field parity between each new Python validator's
    accepted shape and its corresponding schema -- if these drift, a
    payload the runtime validator accepts (or rejects) could silently
    diverge from what the schema on disk claims, defeating the whole
    point of having both."""

    def test_journal_event_top_level_fields_match_schema(self):
        schema = _load_schema("journal-event.schema.json")
        schema_props = set(schema["properties"].keys())
        from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
        from harness_contracts.v1.journal import validate_journal_event

        # A minimal, fully-populated RUN_STARTED event, hand-declared --
        # the protection is that validate_journal_event must accept it
        # AS VALID below before this test trusts its field set for the
        # parity comparison; an invalid instance would fail the
        # assertTrue first, never reaching (and never falsely passing)
        # the schema-parity assertion.
        run_payload = {
            "coordinator": {"coordinator_id": "c", "boot_id": "b", "hostname": "h", "pid": 1},
            "trust_roots": {"reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0" * 64, "provider_signals_path": "y", "provider_signals_sha256": "0" * 64},
            "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1, "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1, "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
            "end_reason": None, "end_detail": None, "disabled_lanes": [],
        }
        event = {
            "schema_version": 1, "seq": 1, "event_id": "e1", "event_type": "RUN_STARTED",
            "event_at": "2026-08-10T00:00:00Z", "coordinator_id": "c", "run_id": "r",
            "state_root_id": "s", "packet_id": None, "intent_id": None,
            "from_state": None, "to_state": None, "cause": "none",
            "payload": {"packet": None, "attempt": None, "artifacts": [], "classification": None, "transition_detail": None, "recovery": None, "run": run_payload, "report": None},
            "prev_event_sha256": "0" * 64, "event_sha256": "",
        }
        event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
        result = validate_journal_event(event, prev_event=None, state_root_id="s")
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual(set(event.keys()), schema_props, "journal.py's accepted top-level fields diverged from journal-event.schema.json's properties")

    def test_reconciliation_report_top_level_fields_match_schema(self):
        schema = _load_schema("reconciliation-report.schema.json")
        schema_props = set(schema["properties"].keys())
        from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
        from harness_contracts.v1.reconciliation import validate_reconciliation_report

        report = {
            "schema_version": 1, "report_id": "r1", "generated_at": "2026-08-10T00:00:00Z",
            "coordinator_id": "c", "run_id": "run-1", "state_root_id": "s",
            "journal_head": {"seq": 0, "event_sha256": "0" * 64},
            "inventory_total": 0,
            "by_state": {"READY": 0, "BLOCKED": 0, "RUNNING": 0, "REVIEW": 0, "REVISE": 0, "ACCEPTED": 0, "QUARANTINED": 0, "HUMAN_REQUIRED": 0},
            "packets": [], "activity": {
                "attempts_started_total": 0, "infra_retries_total": 0, "revise_verdicts_total": 0,
                "revise_cycles_total": 0, "reassignments_total": 0, "results_recorded_total": 0,
                "verdicts_recorded_total": 0, "intents_abandoned_total": 0, "locks_reclaimed_total": 0,
            },
            "attention_required": [],
            "integrity": {
                "journal_chain_valid": True, "state_cache_in_sync": True, "duplicate_packet_ids": [],
                "omitted_packet_ids": [], "unenrolled_dependencies": [], "seal_mismatches": [],
                "accounting_violations": [], "preserved_evidence_mismatches": [],
            },
            "reconciliation": {
                "sum_of_by_state": 0, "packets_array_length": 0, "distinct_packet_ids": 0,
                "equals_inventory_total": True, "all_invariants_passed": True,
            },
            "content_sha256": "", "report_sha256": "",
        }
        report["content_sha256"] = compute_sha256(canonical_bytes(
            report, omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
        ))
        report["report_sha256"] = compute_sha256(canonical_bytes(report, omit={"report_sha256"}))
        result = validate_reconciliation_report(report)
        self.assertTrue(result["valid"], result.get("errors"))
        self.assertEqual(set(report.keys()), schema_props, "reconcile.py's built report fields diverged from reconciliation-report.schema.json's properties")

    def test_reconciliation_report_packet_row_fields_match_schema(self):
        """reconcile.py's own row shape (17 fields, including the
        retry_limit extension) must match the schema's per-packet-row
        object -- proven by driving the REAL runtime validator
        (validate_reconciliation_report -> _validate_packet_row), not by
        comparing a hand-written dict to the schema (which has no teeth
        against drift in either the validator's required set or the
        producer -- confirmed by mutation testing during the final O3
        integration gate review: adding a field to both reconcile.py's
        row AND reconciliation.py's validator, while leaving the schema
        untouched, passed a dict-comparison version of this test).
        Removing each schema property one at a time from an otherwise-
        valid row and confirming the validator rejects it (MISSING_FIELD)
        proves the schema's properties are a SUBSET of what the validator
        requires; adding one foreign field and confirming rejection
        (UNKNOWN_FIELD) proves nothing beyond the schema's properties is
        silently accepted. Together: the real validator's accepted shape
        equals the schema's declared shape, verified by exercising the
        validator's actual behavior, not by hand-copying its private
        `required` set (not exported) into this test."""
        from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
        from harness_contracts.v1.reconciliation import validate_reconciliation_report

        schema = _load_schema("reconciliation-report.schema.json")
        row_schema = schema["properties"]["packets"]["items"]
        schema_row_props = set(row_schema["properties"].keys())

        valid_row = {
            "packet_id": "p1", "state": "READY", "lane": "kimi_implementation", "enqueue_seq": 1,
            "attempts_started": 0, "infra_retries_used": 0, "revise_cycles_used": 0, "revise_verdicts": 0,
            "reassignment_used": False, "open_attempt": None, "last_event_seq": 1, "last_event_sha256": "0" * 64,
            "quarantine_reason": None, "human_required_reasons": [], "blocked_on": [], "attention_codes": [],
            "retry_limit": 2,
        }
        self.assertEqual(set(valid_row.keys()), schema_row_props, "sanity: this test's own fixture must start aligned with the schema")

        def _report_with_row(row: Dict[str, Any]) -> Dict[str, Any]:
            report = {
                "schema_version": 1, "report_id": "r1", "generated_at": "2026-08-10T00:00:00Z",
                "coordinator_id": "c", "run_id": "run-1", "state_root_id": "s",
                "journal_head": {"seq": 0, "event_sha256": "0" * 64},
                "inventory_total": 1,
                "by_state": {"READY": 1, "BLOCKED": 0, "RUNNING": 0, "REVIEW": 0, "REVISE": 0, "ACCEPTED": 0, "QUARANTINED": 0, "HUMAN_REQUIRED": 0},
                "packets": [row], "activity": {
                    "attempts_started_total": 0, "infra_retries_total": 0, "revise_verdicts_total": 0,
                    "revise_cycles_total": 0, "reassignments_total": 0, "results_recorded_total": 0,
                    "verdicts_recorded_total": 0, "intents_abandoned_total": 0, "locks_reclaimed_total": 0,
                },
                "attention_required": [],
                "integrity": {
                    "journal_chain_valid": True, "state_cache_in_sync": True, "duplicate_packet_ids": [],
                    "omitted_packet_ids": [], "unenrolled_dependencies": [], "seal_mismatches": [],
                    "accounting_violations": [], "preserved_evidence_mismatches": [],
                },
                "reconciliation": {
                    "sum_of_by_state": 1, "packets_array_length": 1, "distinct_packet_ids": 1,
                    "equals_inventory_total": True, "all_invariants_passed": True,
                },
                "content_sha256": "", "report_sha256": "",
            }
            report["content_sha256"] = compute_sha256(canonical_bytes(
                report, omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
            ))
            report["report_sha256"] = compute_sha256(canonical_bytes(report, omit={"report_sha256"}))
            return report

        # Sanity: the unmutated row genuinely validates.
        result = validate_reconciliation_report(_report_with_row(valid_row))
        self.assertTrue(result["valid"], result.get("errors"))

        # Every schema property is genuinely REQUIRED by the real validator.
        for prop in sorted(schema_row_props):
            with self.subTest(missing=prop):
                mutated = dict(valid_row)
                del mutated[prop]
                result = validate_reconciliation_report(_report_with_row(mutated))
                self.assertFalse(result["valid"], f"validator accepted a row missing schema property {prop!r}")

        # Nothing beyond the schema's properties is silently accepted.
        extra = dict(valid_row)
        extra["not_in_schema_or_validator"] = True
        result = validate_reconciliation_report(_report_with_row(extra))
        self.assertFalse(result["valid"], "validator silently accepted a field not in the schema")


if __name__ == "__main__":
    unittest.main()
