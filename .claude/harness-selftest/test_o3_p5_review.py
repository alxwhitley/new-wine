"""P5C: trusted review, terminal seals, REVISE handling, and dependency promotion.

Every test builds a disposable state root with synthetic fixtures only. No
provider is invoked, no network is used, and no production data is touched.

The central property under test is the coordinator-assembled bundle: external
review input contributes ONLY an ``opus_verdict`` object, and the coordinator
supplies its own enrolled packet and its own durably recorded worker result.
A reviewer who is trusted must still be unable to authorize a packet/result
it fabricated.
"""

import json
import multiprocessing
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256

T_ENROLL = "2026-08-10T00:00:00Z"
T_STARTED = "2026-08-10T01:00:00Z"
T_WORKER_FINISHED = "2026-08-10T01:05:00Z"
T_FINISHED = "2026-08-10T01:06:00Z"
T_REVIEWED = "2026-08-10T01:10:00Z"
T_NOW = "2026-08-10T01:11:00Z"
T_CHILD_NOW = "2026-08-10T01:35:00Z"

TRUSTED_REVIEWER = "sess-opus-p5c"
RUN_ID = "run-p5c"
COORD_ID = "coord-p5c"
STATE_ROOT_ID = "srid-p5c"


# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

def _packet(packet_id, dependencies=None, worktree="/tmp/p5c-worktree"):
    packet = {
        "schema_version": 1, "packet_id": packet_id, "objective": "P5C fixture",
        "dependency_ids": dependencies or [], "lane": "kimi_implementation",
        "assigned_worker": {"worker_id": "kimi-1", "provider": "opencode", "model": "kimi-k2.7-code"},
        "starting_revision": "a" * 40,
        "worktree": {"path": worktree, "branch": "p5c-test"},
        "writable_paths": [f"scripts/{packet_id}.py"],
        "forbidden_surfaces": ["backend/app/services/answer_toolbox.py"],
        "required_context": [{"path": "HARNESS.md", "sha256": "b" * 64}],
        "premise_checks": [{"check_id": "ck-1", "command_id": "cmd-1", "expected": "present"}],
        "acceptance_criteria": [{"criterion_id": "ac-1", "statement": "works", "required_evidence_ids": ["ev-1"]}],
        "verification_commands": [{
            "command_id": "cmd-1", "argv": ["python3", "-m", "pytest"], "cwd": ".",
            "timeout_seconds": 60, "expected_exit_code": 0, "expected_evidence_ids": ["ev-1"],
        }],
        "budgets": {"max_turns": 10, "wall_clock_seconds": 300, "retry_limit": 2,
                    "max_output_bytes": 1000000, "cost_class": "low", "allowance_limit": 100},
        "network_policy": "denied",
        "checkpoint_artifacts": [{"artifact_id": "art-1", "path": f"scripts/{packet_id}.py", "required_for_fallback": True}],
        "rollback": {"method": "git_reset", "allowed_commands": [{"argv": ["git", "status"], "cwd": "."}]},
        "human_stop_conditions": ["governed_doc_touched"], "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "sess-opus-001", "model": "claude-opus-5"},
    }
    packet["packet_sha256"] = compute_sha256(canonical_bytes(packet, omit={"packet_sha256"}))
    return packet


def _worker_result(packet, session_id, attempt=1, satisfied=True, dependency_evidence=()):
    extra_evidence = [
        {"evidence_id": f"ev-dep-{dependency_id}", "kind": "reconciliation", "criterion_ids": [],
         "command_id": None, "artifact_path": None, "artifact_sha256": None,
         "summary": f"dependency {dependency_id} accepted upstream"}
        for dependency_id in dependency_evidence
    ]
    result = {
        "schema_version": 1, "result_id": f"res-{packet['packet_id']}-{attempt}",
        "packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"], "attempt": attempt,
        "worker": {"worker_id": "kimi-1", "session_id": session_id, "lane": "kimi_implementation",
                   "provider": "opencode", "model": "kimi-k2.7-code"},
        "started_at": T_STARTED, "finished_at": T_WORKER_FINISHED,
        "starting_revision": packet["starting_revision"], "ending_revision": "d" * 40,
        "outcome": "COMPLETED" if satisfied else "FAILED",
        "changed_files": [{"path": f"scripts/{packet['packet_id']}.py", "status": "modified",
                           "before_sha256": "e" * 64, "after_sha256": "f" * 64}],
        "commands": [{
            "command_id": "cmd-1", "argv": ["python3", "-m", "pytest"], "cwd": ".",
            "timestamps": {"started_at": "2026-08-10T01:01:00Z", "finished_at": "2026-08-10T01:02:00Z"},
            "exit_code": 0, "outcome": "PASSED" if satisfied else "FAILED",
            "stdout_sha256": "0" * 64, "stderr_sha256": "1" * 64,
        }],
        "evidence": [{"evidence_id": "ev-1", "kind": "verification", "criterion_ids": ["ac-1"],
                      "command_id": "cmd-1", "artifact_path": None, "artifact_sha256": None,
                      "summary": "verification evidence"}] + extra_evidence,
        "criteria": [{"criterion_id": "ac-1", "status": "SATISFIED" if satisfied else "UNSATISFIED",
                      "evidence_ids": ["ev-1"]}],
        "checkpoints": [{"artifact_id": "art-1", "path": f"scripts/{packet['packet_id']}.py", "sha256": "0" * 64}],
        "remaining_criterion_ids": [],
        "fallback": None, "human_required_reasons": [],
        "budgets": {"turns_used": 5, "output_bytes": 1024, "retry_count": 0, "allowance_used": "5"},
    }
    result["result_sha256"] = compute_sha256(canonical_bytes(result, omit={"result_sha256"}))
    return result


_GLOBAL_RULES = ["premise", "repo_only_boundary", "allowlist_scope", "changed_manifest",
                 "command_integrity", "governed_records", "reviewer_independence",
                 "batch_reconciliation", "pre_batch", "migration_comment", "n_plus_one", "reuse_path"]


def _verdict(packet, worker_result, decision="ACCEPT", reviewer_session=TRUSTED_REVIEWER):
    next_state = {"ACCEPT": "ACCEPTED", "REVISE": "REVISE",
                  "QUARANTINE": "QUARANTINED", "HUMAN_REQUIRED": "HUMAN_REQUIRED"}[decision]
    verdict = {
        "schema_version": 1, "verdict_id": f"verdict-{packet['packet_id']}-{worker_result['attempt']}",
        "packet_id": packet["packet_id"], "packet_sha256": packet["packet_sha256"],
        "result_id": worker_result["result_id"], "result_sha256": worker_result["result_sha256"],
        "reviewer": {"role": "opus_judgment", "session_id": reviewer_session, "model": "claude-opus-5"},
        "reviewed_at": T_REVIEWED, "verdict": decision,
        "criterion_findings": [{"criterion_id": "ac-1",
                                "finding": "PASS" if decision == "ACCEPT" else "FAIL",
                                "evidence_ids": ["ev-1"], "reason": "checked"}],
        "global_findings": [{"rule_id": rule, "finding": "PASS", "evidence_ids": ["ev-1"], "reason": "ok"}
                            for rule in _GLOBAL_RULES],
        "required_corrections": [] if decision != "REVISE" else ["tighten the guard"],
        "human_decisions_required": [] if decision != "HUMAN_REQUIRED" else ["alex must rule"],
        "next_state": next_state,
        "integration_revision": packet["starting_revision"] if decision == "ACCEPT" else None,
    }
    verdict["verdict_sha256"] = compute_sha256(canonical_bytes(verdict, omit={"verdict_sha256"}))
    return verdict


def _rehash_verdict(verdict):
    verdict["verdict_sha256"] = compute_sha256(canonical_bytes(verdict, omit={"verdict_sha256"}))
    return verdict


def _write_trust_roots(state_root, sessions=(TRUSTED_REVIEWER,)):
    trust_dir = os.path.join(state_root, "trust")
    os.makedirs(trust_dir, exist_ok=True)
    reviewer = {"schema_version": 1, "sessions": list(sessions), "registry_sha256": ""}
    reviewer["registry_sha256"] = compute_sha256(canonical_bytes(reviewer, omit={"registry_sha256"}))
    with open(os.path.join(trust_dir, "reviewer_sessions.json"), "wb") as handle:
        handle.write(canonical_bytes(reviewer))
    provider = {"schema_version": 1, "registry_id": "empty", "providers": {}, "registry_sha256": ""}
    provider["registry_sha256"] = compute_sha256(canonical_bytes(provider, omit={"registry_sha256"}))
    with open(os.path.join(trust_dir, "provider_signals.json"), "wb") as handle:
        handle.write(canonical_bytes(provider))


def _write_manifest(state_root, state_root_id=STATE_ROOT_ID):
    manifest = {
        "schema_version": 1, "state_root_id": state_root_id, "created_at": T_ENROLL,
        "contract_versions": {"packet": 1, "worker_result": 1, "verdict": 1, "replay": 1,
                              "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1,
                              "provider_evidence": 1, "reassignment": 1, "reconciliation": 1},
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"}))
    with open(os.path.join(state_root, "MANIFEST.json"), "wb") as handle:
        handle.write(canonical_bytes(manifest))


def _append(state_root, events, event_type, now, **kwargs):
    from harness_coordinator.v1.recovery import _make_event
    from harness_coordinator.v1.store import append_journal
    prev = events[-1] if events else None
    event = _make_event(seq=(prev["seq"] + 1) if prev else 1, event_type=event_type,
                        coordinator_id=COORD_ID, run_id=RUN_ID, state_root_id=STATE_ROOT_ID,
                        prev_event=prev, event_at=now, **kwargs)
    append_journal(os.path.join(state_root, "journal.ndjson"), event,
                   os.path.join(state_root, "locks", "journal.wlock"), expected_head=prev)
    events.append(event)
    return event


def _empty_payload(**overrides):
    payload = {"packet": None, "attempt": None, "artifacts": [], "classification": None,
               "transition_detail": None, "recovery": None, "run": None, "report": None}
    payload.update(overrides)
    return payload


def _state_root_in_review(tmp_path, packet_id="pkt-review", dependencies=None,
                          satisfied=True, trusted_sessions=(TRUSTED_REVIEWER,)):
    """Build a disposable state root holding one packet resting in REVIEW."""
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.store import read_journal

    state_root = str(tmp_path)
    os.makedirs(state_root, exist_ok=True)
    _write_manifest(state_root)
    _write_trust_roots(state_root, trusted_sessions)
    os.makedirs(os.path.join(state_root, "locks"), exist_ok=True)

    packet = _packet(packet_id, dependencies)
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_ENROLL, [packet])
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    return _drive_to_review(state_root, events, packet, satisfied=satisfied)


def _drive_to_review(state_root, events, packet, satisfied=True, dependency_evidence=(),
                     started_at=T_STARTED, recorded_at=T_WORKER_FINISHED, finished_at=T_FINISHED):
    """Journal ATTEMPT_STARTED -> WORKER_RESULT_RECORDED -> ATTEMPT_FINISHED(REVIEW)."""
    from harness_coordinator.v1.coordinator import attempt_session_id
    from harness_coordinator.v1.paths import safe_state_path

    packet_id = packet["packet_id"]
    attempt = 1
    intent_id = f"attempt-{packet_id}-{attempt}"
    session_id = attempt_session_id(RUN_ID, packet_id, attempt)
    worker = {"worker_id": "kimi-1", "session_id": session_id,
              "provider": "opencode", "model": "kimi-k2.7-code"}
    attempt_payload = {"attempt": attempt, "lane": packet["lane"], "worker": worker,
                       "claim_sha256": None, "worktree_path": packet["worktree"]["path"]}

    _append(state_root, events, "ATTEMPT_STARTED", started_at, packet_id=packet_id,
            intent_id=intent_id, from_state="READY", to_state="RUNNING", cause="claim_committed",
            payload=_empty_payload(attempt=attempt_payload))

    result = _worker_result(packet, session_id, attempt, satisfied=satisfied,
                            dependency_evidence=dependency_evidence)
    result_path = safe_state_path(state_root, "results", identifier=packet_id,
                                  suffix=os.path.join(str(attempt), "worker-result.json"))
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    result_bytes = canonical_bytes(result)
    with open(result_path, "wb") as handle:
        handle.write(result_bytes)
    artifact = {"kind": "worker_result", "artifact_id": f"wr-{packet_id}-{attempt}",
                "path": os.path.relpath(result_path, os.path.realpath(state_root)),
                "sha256": compute_sha256(result_bytes), "byte_length": len(result_bytes)}

    _append(state_root, events, "WORKER_RESULT_RECORDED", recorded_at, packet_id=packet_id,
            intent_id=intent_id, payload=_empty_payload(attempt=attempt_payload, artifacts=[artifact]))

    classification = {
        "attempt_class": "COMPLETED_PENDING_REVIEW" if satisfied else "WORKER_QUALITY",
        "quarantine_reason": None, "human_required_reasons": [],
        "result_sha256": compute_sha256(result_bytes), "provider_evidence_sha256": None,
        "reassignment_record_sha256": None,
        "outcome_summary": {"exit_code": 0, "signal": None, "timed_out": False,
                            "result_present": True, "result_valid": True, "error_codes": []},
    }
    _append(state_root, events, "ATTEMPT_FINISHED", finished_at, packet_id=packet_id,
            intent_id=intent_id, from_state="RUNNING", to_state="REVIEW", cause="result_recorded",
            payload=_empty_payload(attempt=attempt_payload, classification=classification))

    return {"state_root": state_root, "packet": packet, "worker_result": result,
            "session_id": session_id, "attempt": attempt, "events": events}


def _context(coordinator_id=COORD_ID, pid=None, boot_id="boot-1", hostname="test-host", live=None):
    """A trusted process context; distinct identities model distinct coordinators."""
    return {"coordinator_id": coordinator_id, "hostname": hostname, "boot_id": boot_id,
            "pid": os.getpid() if pid is None else pid,
            "live_coordinator_ids": {coordinator_id} if live is None else set(live),
            "now": T_NOW}


def _deposit(state_root, packet_id, attempt, verdict):
    from harness_coordinator.v1.review import verdict_inbox_path
    path = verdict_inbox_path(state_root, packet_id, attempt)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(verdict))
    return path


def _resolve(fixture, context=None, packet_id=None, now=T_NOW, folded=None):
    """``folded`` may be supplied to model the real run_once window, where the
    fold is computed during maintenance and reused for review assembly."""
    from harness_coordinator.v1.recovery import _fold_journal
    from harness_coordinator.v1.review import resolve_review
    if folded is None:
        folded, _ = _fold_journal(fixture["state_root"], fixture["events"])
    return resolve_review(state_root=fixture["state_root"], state_root_id=STATE_ROOT_ID,
                          journal_events=fixture["events"], folded=folded,
                          packet_id=packet_id or fixture["packet"]["packet_id"],
                          coordinator_id=(context or _context())["coordinator_id"],
                          run_id=RUN_ID, trusted_process_context=context or _context(), now=now)


def _fold(fixture):
    from harness_coordinator.v1.recovery import _fold_journal
    return _fold_journal(fixture["state_root"], fixture["events"])[0]


# --------------------------------------------------------------------------
# Reviewer trust
# --------------------------------------------------------------------------

def test_untrusted_reviewer_session_is_refused(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"], reviewer_session="sess-attacker")
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert "UNAUTHORIZED_REVIEWER" in excinfo.value.codes
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


def test_reviewer_matching_worker_session_is_refused(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    # The worker's own session is added to the trusted registry, so only the
    # independence rule can catch this.
    _write_trust_roots(fixture["state_root"], (TRUSTED_REVIEWER, fixture["session_id"]))
    verdict = _verdict(fixture["packet"], fixture["worker_result"], reviewer_session=fixture["session_id"])
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert "WORKER_SELF_ACCEPT" in excinfo.value.codes
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


def test_untrusted_reviewer_is_refused_before_ground_truth_is_assembled(tmp_path):
    """Trust is evaluated before any durable artifact is read.

    Without this ordering the refusal still happens -- ``validate_replay_bundle``
    catches an untrusted session too -- but it is reported as whatever the
    assembly happened to trip over first. Deleting the durable worker result
    makes that difference observable: the refusal must still name the trust
    failure, not a downstream evidence failure.
    """
    from harness_coordinator.v1.review import ReviewRefused, worker_result_artifact_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    os.remove(worker_result_artifact_path(fixture["state_root"], packet_id, 1))
    verdict = _verdict(fixture["packet"], fixture["worker_result"], reviewer_session="sess-attacker")
    _deposit(fixture["state_root"], packet_id, 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert excinfo.value.codes == ("UNAUTHORIZED_REVIEWER",)


def test_missing_trust_registry_fails_closed(tmp_path):
    """Reviewer trust is operator-owned; the coordinator never fabricates it."""
    from harness_coordinator.v1.recovery import IntegrityError
    fixture = _state_root_in_review(tmp_path)
    os.remove(os.path.join(fixture["state_root"], "trust", "reviewer_sessions.json"))
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(IntegrityError) as excinfo:
        _resolve(fixture)
    assert excinfo.value.code == "TRUST_CONTEXT_MISSING"
    assert not os.path.exists(os.path.join(fixture["state_root"], "trust", "reviewer_sessions.json"))
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


# --------------------------------------------------------------------------
# Coordinator-assembled ground truth
# --------------------------------------------------------------------------

def test_full_bundle_deposit_is_refused_because_inbox_carries_only_a_verdict(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    bundle_shaped = {
        "schema_version": 1, "packet": fixture["packet"],
        "prior_state_event": {"from_state": "REVIEW", "to_state": "ACCEPTED", "event_at": T_NOW},
        "dependency_states": [], "worker_result": fixture["worker_result"],
        "opus_verdict": verdict, "validator_version": "1", "bundle_sha256": "0" * 64,
    }
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, bundle_shaped)
    with pytest.raises(ReviewRefused):
        _resolve(fixture)
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


def test_verdict_referencing_substituted_packet_and_result_is_refused(tmp_path):
    """A trusted reviewer cannot authorize a packet/result it fabricated."""
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    fake_packet = _packet("pkt-review")
    fake_packet["objective"] = "attacker-controlled objective"
    fake_packet["packet_sha256"] = compute_sha256(canonical_bytes(fake_packet, omit={"packet_sha256"}))
    fake_result = _worker_result(fake_packet, "sess-fake-worker")
    verdict = _verdict(fake_packet, fake_result)
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert excinfo.value.codes
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


def test_malicious_rehashed_verdict_is_refused(tmp_path):
    """Self-consistent rehashing is not authenticity."""
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    verdict["result_sha256"] = compute_sha256(b"fabricated-result")
    _rehash_verdict(verdict)
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert "EVIDENCE_HASH_MISMATCH" in excinfo.value.codes


def test_incomplete_accept_evidence_is_refused(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    verdict["global_findings"] = [f for f in verdict["global_findings"]
                                  if f["rule_id"] != "reviewer_independence"]
    _rehash_verdict(verdict)
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(fixture)
    assert "EVIDENCE_MISSING" in excinfo.value.codes


# --------------------------------------------------------------------------
# REVIEW resume: the four distinguishable states
# --------------------------------------------------------------------------

def test_review_restart_without_verdict_awaits(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    outcome = _resolve(fixture)
    assert outcome["status"] == "awaiting_verdict"
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "REVIEW"


def test_review_restart_with_unjournaled_verdict_completes(tmp_path):
    from harness_coordinator.v1.review import verdict_artifact_path
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    outcome = _resolve(fixture)
    assert outcome["status"] == "recorded"
    assert outcome["verdict"] == "ACCEPT"
    assert _fold(fixture)[fixture["packet"]["packet_id"]]["state"] == "ACCEPTED"
    assert os.path.exists(verdict_artifact_path(fixture["state_root"], fixture["packet"]["packet_id"], 1))


def test_already_journaled_verdict_is_idempotent(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, verdict)
    assert _resolve(fixture)["status"] == "recorded"
    journal_before = Path(fixture["state_root"], "journal.ndjson").read_bytes()
    assert _resolve(fixture)["status"] == "already_recorded"
    assert Path(fixture["state_root"], "journal.ndjson").read_bytes() == journal_before


def test_conflicting_verdict_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict
    fixture = _state_root_in_review(tmp_path)
    accept = _verdict(fixture["packet"], fixture["worker_result"])
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, accept)
    assert _resolve(fixture)["status"] == "recorded"
    journal_before = Path(fixture["state_root"], "journal.ndjson").read_bytes()
    conflicting = _verdict(fixture["packet"], fixture["worker_result"], decision="QUARANTINE")
    _deposit(fixture["state_root"], fixture["packet"]["packet_id"], 1, conflicting)
    with pytest.raises(VerdictConflict):
        _resolve(fixture)
    assert Path(fixture["state_root"], "journal.ndjson").read_bytes() == journal_before


# --------------------------------------------------------------------------
# Terminal seals
# --------------------------------------------------------------------------

def test_interruption_between_verdict_and_seal_completes_seal_on_resume(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path
    from harness_coordinator.v1.seals_runtime import complete_terminal_seals
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    _resolve(fixture)
    seal_path = safe_state_path(fixture["state_root"], "state", "terminal",
                                identifier=packet_id, identifier_suffix=".seal.json")
    assert not os.path.exists(seal_path), "verdict commit must not implicitly seal"

    sealed = complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), T_NOW)
    assert sealed == [packet_id]
    seal = json.loads(Path(seal_path).read_bytes().decode("utf-8"))
    assert seal["terminal_state"] == "ACCEPTED"
    assert seal["packet_sha256"] == fixture["packet"]["packet_sha256"]
    verdict_event = [e for e in fixture["events"] if e["event_type"] == "VERDICT_RECORDED"][-1]
    assert seal["sealing_event_seq"] == verdict_event["seq"]
    assert seal["sealing_event_sha256"] == verdict_event["event_sha256"]
    assert seal["upstream_digests"]["result_sha256"] == fixture["worker_result"]["result_sha256"]
    # A second pass is a pure no-op, byte for byte.
    seal_bytes = Path(seal_path).read_bytes()
    assert complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), "2026-08-10T02:00:00Z") == []
    assert Path(seal_path).read_bytes() == seal_bytes


def test_contradictory_seal_fails_closed(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path
    from harness_coordinator.v1.seals_runtime import SealContradiction, complete_terminal_seals
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    _resolve(fixture)
    seal_path = safe_state_path(fixture["state_root"], "state", "terminal",
                                identifier=packet_id, identifier_suffix=".seal.json")
    os.makedirs(os.path.dirname(seal_path), exist_ok=True)
    # Same terminal_state (so the fold still loads it) but a forged binding.
    forged = {
        "schema_version": 1, "packet_id": packet_id,
        "packet_sha256": fixture["packet"]["packet_sha256"], "terminal_state": "ACCEPTED",
        "sealing_event_seq": 1, "sealing_event_sha256": "9" * 64, "sealed_at": T_NOW,
        "quarantine_reason": None, "human_required_reasons": [],
        "upstream_digests": {"packet_sha256": "1" * 64, "result_sha256": "2" * 64,
                             "verdict_sha256": "3" * 64, "bundle_sha256": "4" * 64},
        "seal_sha256": "",
    }
    forged["seal_sha256"] = compute_sha256(canonical_bytes(forged, omit={"seal_sha256"}))
    with open(seal_path, "wb") as handle:
        handle.write(canonical_bytes(forged))
    forged_bytes = Path(seal_path).read_bytes()
    with pytest.raises(SealContradiction):
        complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), T_NOW)
    assert Path(seal_path).read_bytes() == forged_bytes, "a contradictory seal must never be overwritten"


def test_quarantine_seal_carries_no_upstream_digests(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path
    from harness_coordinator.v1.seals_runtime import complete_terminal_seals
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1,
             _verdict(fixture["packet"], fixture["worker_result"], decision="QUARANTINE"))
    assert _resolve(fixture)["verdict"] == "QUARANTINE"
    assert complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), T_NOW) == [packet_id]
    seal_path = safe_state_path(fixture["state_root"], "state", "terminal",
                                identifier=packet_id, identifier_suffix=".seal.json")
    seal = json.loads(Path(seal_path).read_bytes().decode("utf-8"))
    assert seal["terminal_state"] == "QUARANTINED"
    assert seal["upstream_digests"] is None


# --------------------------------------------------------------------------
# REVISE
# --------------------------------------------------------------------------

def test_revise_preserves_evidence_and_requeues(tmp_path):
    from harness_coordinator.v1.classify_runtime import requeue_revise
    from harness_coordinator.v1.review import bundle_artifact_path, verdict_artifact_path
    from harness_coordinator.v1.paths import safe_state_path
    fixture = _state_root_in_review(tmp_path, satisfied=False)
    packet_id = fixture["packet"]["packet_id"]
    result_path = safe_state_path(fixture["state_root"], "results", identifier=packet_id,
                                  suffix=os.path.join("1", "worker-result.json"))
    result_bytes_before = Path(result_path).read_bytes()

    _deposit(fixture["state_root"], packet_id, 1,
             _verdict(fixture["packet"], fixture["worker_result"], decision="REVISE"))
    assert _resolve(fixture)["verdict"] == "REVISE"
    folded = _fold(fixture)
    assert folded[packet_id]["state"] == "REVISE"
    assert folded[packet_id]["revise_verdicts"] == 1

    events, _ = requeue_revise(os.path.join(fixture["state_root"], "journal.ndjson"),
                               os.path.join(fixture["state_root"], "locks", "journal.wlock"),
                               fixture["events"], folded, COORD_ID, RUN_ID, STATE_ROOT_ID, T_NOW)
    fixture["events"] = events
    folded = _fold(fixture)
    assert folded[packet_id]["state"] == "READY"
    assert folded[packet_id]["revise_cycles_used"] == 1
    assert folded[packet_id]["attempts_started"] == 1

    # Every piece of evidence survives the requeue byte-for-byte.
    assert Path(result_path).read_bytes() == result_bytes_before
    assert os.path.exists(verdict_artifact_path(fixture["state_root"], packet_id, 1))
    assert os.path.exists(bundle_artifact_path(fixture["state_root"], packet_id, 1))
    verdict = json.loads(Path(verdict_artifact_path(fixture["state_root"], packet_id, 1)).read_bytes().decode("utf-8"))
    assert verdict["required_corrections"] == ["tighten the guard"]
    stored_result = json.loads(result_bytes_before.decode("utf-8"))
    assert stored_result["criteria"][0]["status"] == "UNSATISFIED"


# --------------------------------------------------------------------------
# Dependency promotion
# --------------------------------------------------------------------------

def test_dependency_promotes_only_after_valid_seal(tmp_path):
    from harness_coordinator.v1.classify_runtime import promote_dependencies
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.seals_runtime import complete_terminal_seals
    from harness_coordinator.v1.store import read_journal

    fixture = _state_root_in_review(tmp_path, packet_id="pkt-dep")
    state_root = fixture["state_root"]
    dependent = _packet("pkt-child", dependencies=["pkt-dep"])
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_FINISHED, [dependent])
    fixture["events"], _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)

    _deposit(state_root, "pkt-dep", 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["verdict"] == "ACCEPT"
    assert _fold(fixture)["pkt-dep"]["state"] == "ACCEPTED"

    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")

    # Unsealed: the accepted dependency must NOT promote its dependent.
    events, attention = promote_dependencies(state_root, journal_path, lock_path, fixture["events"],
                                             _fold(fixture), COORD_ID, RUN_ID, STATE_ROOT_ID, T_NOW)
    fixture["events"] = events
    assert _fold(fixture)["pkt-child"]["state"] == "BLOCKED"

    complete_terminal_seals(state_root, fixture["events"], _fold(fixture), T_NOW)
    events, attention = promote_dependencies(state_root, journal_path, lock_path, fixture["events"],
                                             _fold(fixture), COORD_ID, RUN_ID, STATE_ROOT_ID, T_NOW)
    fixture["events"] = events
    assert _fold(fixture)["pkt-child"]["state"] == "READY"
    assert attention == []


# --------------------------------------------------------------------------
# Coordinator wiring
# --------------------------------------------------------------------------

def test_run_once_reviews_then_seals_then_promotes(tmp_path):
    from harness_coordinator.v1.coordinator import run_once
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.paths import safe_state_path
    from harness_coordinator.v1.recovery import _fold_journal
    from harness_coordinator.v1.store import read_journal

    fixture = _state_root_in_review(tmp_path, packet_id="pkt-dep")
    state_root = fixture["state_root"]
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, T_FINISHED,
                   [_packet("pkt-child", dependencies=["pkt-dep"])])
    _deposit(state_root, "pkt-dep", 1, _verdict(fixture["packet"], fixture["worker_result"]))

    context = {"coordinator_id": COORD_ID, "hostname": "test-host", "boot_id": "boot-1",
               "pid": os.getpid(), "live_coordinator_ids": {COORD_ID}, "now": T_NOW}
    outcome = run_once(state_root, COORD_ID, RUN_ID, context, T_NOW)

    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    folded, _ = _fold_journal(state_root, events)
    assert folded["pkt-dep"]["state"] == "ACCEPTED"
    assert os.path.exists(safe_state_path(state_root, "state", "terminal",
                                          identifier="pkt-dep", identifier_suffix=".seal.json"))
    assert outcome["sealed"] == ["pkt-dep"]

    # One bounded iteration carries the dependent all the way: BLOCKED ->
    # READY on the promotion the fresh seal unblocked, then READY -> RUNNING
    # on the claim, because it is now the only eligible packet.
    promotions = [e for e in events if e["event_type"] == "STATE_TRANSITION"
                  and e["packet_id"] == "pkt-child" and e["cause"] == "dependencies_satisfied"]
    assert len(promotions) == 1
    assert (promotions[0]["from_state"], promotions[0]["to_state"]) == ("BLOCKED", "READY")
    assert promotions[0]["payload"]["transition_detail"]["satisfied_by"][0]["packet_id"] == "pkt-dep"
    assert folded["pkt-child"]["state"] == "RUNNING"
    assert outcome["status"] == "claimed"
    assert outcome["packet_id"] == "pkt-child"


# --------------------------------------------------------------------------
# Deterministic review-claim ownership (revision 1, correction 1)
# --------------------------------------------------------------------------

def _claim_contender(state_root, coordinator_id, pid, live, barrier, results):  # noqa: D401
    """Module-level so it survives spawn; one contender per process.

    Both contenders know both coordinators are live, which is what a real
    registry reports. Without that, each would classify the other's fresh
    claim as stale and reclaim it, and both would "win" — the contention
    would be lost to a modelling error rather than proven.
    """
    sys.path.insert(0, str(SCRIPTS))
    from harness_coordinator.v1.review import acquire_review_claim
    from harness_coordinator.v1.store import read_journal
    events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    context = {"coordinator_id": coordinator_id, "hostname": "test-host", "boot_id": "boot-1",
               "pid": pid, "live_coordinator_ids": set(live), "now": T_NOW}
    barrier.wait()
    try:
        claim = acquire_review_claim(state_root, STATE_ROOT_ID, events, "pkt-review", 1,
                                     coordinator_id, RUN_ID, context, T_NOW)
        results.put("won" if claim is not None else "lost")
    except FileExistsError:
        results.put("lost")


def test_review_claim_is_attempt_scoped_and_distinct_from_the_worker_claim(tmp_path):
    from harness_coordinator.v1.paths import safe_state_path
    from harness_coordinator.v1.review import acquire_review_claim, review_claim_path, review_intent_id
    fixture = _state_root_in_review(tmp_path)
    state_root, packet_id = fixture["state_root"], fixture["packet"]["packet_id"]

    claim = acquire_review_claim(state_root, STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 COORD_ID, RUN_ID, _context(), T_NOW)
    assert claim is not None
    assert claim["stage"] == "review_claim"
    assert claim["lane"] == "opus_judgment"
    # Generation 0 on a state root where nothing has been abandoned yet.
    assert claim["intent_id"] == review_intent_id(packet_id, 1, 0)

    worker_lock = safe_state_path(state_root, "locks", identifier=packet_id, identifier_suffix=".lock.json")
    assert review_claim_path(state_root, packet_id, 1) != worker_lock
    assert not os.path.exists(worker_lock), "a review claim must never occupy the worker claim slot"
    # Attempt-scoped: a second attempt is a different ownership slot.
    assert review_claim_path(state_root, packet_id, 1) != review_claim_path(state_root, packet_id, 2)


def test_review_claim_record_satisfies_the_accepted_claim_contract(tmp_path):
    from harness_contracts.v1.claim import validate_claim
    from harness_coordinator.v1.review import acquire_review_claim, review_claim_path
    fixture = _state_root_in_review(tmp_path)
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"],
                                 fixture["packet"]["packet_id"], 1, COORD_ID, RUN_ID, _context(), T_NOW)
    assert validate_claim(claim)["valid"]
    on_disk = json.loads(Path(review_claim_path(fixture["state_root"],
                                                fixture["packet"]["packet_id"], 1)).read_bytes().decode("utf-8"))
    assert validate_claim(on_disk)["valid"]
    assert on_disk == claim


def test_second_live_contender_loses_the_review_claim(tmp_path):
    from harness_coordinator.v1.review import acquire_review_claim
    fixture = _state_root_in_review(tmp_path)
    args = (fixture["state_root"], STATE_ROOT_ID, fixture["events"], fixture["packet"]["packet_id"], 1)
    first = acquire_review_claim(*args, "coord-a", RUN_ID,
                                 _context("coord-a", pid=os.getpid()), T_NOW)
    assert first is not None
    # A second, genuinely live coordinator must not steal an owned review.
    second = acquire_review_claim(*args, "coord-b", RUN_ID,
                                  _context("coord-b", pid=os.getpid(),
                                           live=("coord-a", "coord-b")), T_NOW)
    assert second is None


def test_multiprocess_review_claim_contention_has_exactly_one_winner(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    barrier = multiprocessing.Barrier(2)
    results = multiprocessing.Queue()
    live = ("coord-0", "coord-1")
    procs = [multiprocessing.Process(target=_claim_contender,
                                     args=(fixture["state_root"], f"coord-{i}", 10000 + i, live, barrier, results))
             for i in range(2)]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(20)
    assert sorted(results.get(timeout=5) for _ in range(2)) == ["lost", "won"]


def test_review_without_a_verdict_releases_its_claim(tmp_path):
    from harness_coordinator.v1.review import review_claim_path
    fixture = _state_root_in_review(tmp_path)
    assert _resolve(fixture)["status"] == "awaiting_verdict"
    assert not os.path.exists(review_claim_path(fixture["state_root"], fixture["packet"]["packet_id"], 1)), \
        "an idle REVIEW packet must not hold ownership indefinitely"


def test_review_claimed_by_a_live_peer_is_not_processed(tmp_path):
    from harness_coordinator.v1.review import acquire_review_claim
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                         "coord-peer", RUN_ID, _context("coord-peer", pid=os.getpid()), T_NOW)
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    outcome = _resolve(fixture, context=_context("coord-mine", pid=os.getpid(),
                                                 live=("coord-peer", "coord-mine")))
    assert outcome["status"] == "review_claimed_elsewhere"
    assert _fold(fixture)[packet_id]["state"] == "REVIEW"


def test_crash_after_review_claim_before_pending_intent_recovers(tmp_path):
    """A dead owner's claim is reclaimed, never stolen from a live one."""
    from harness_coordinator.v1.review import acquire_review_claim
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    dead = _context("coord-dead", pid=999999, live=())
    acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                         "coord-dead", RUN_ID, dead, T_NOW)
    assert not os.path.exists(os.path.join(fixture["state_root"], "queue.json")) or True
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    outcome = _resolve(fixture, context=_context("coord-new", pid=os.getpid(), live=("coord-new",)))
    assert outcome["status"] == "recorded"
    assert _fold(fixture)[packet_id]["state"] == "ACCEPTED"


def test_crash_after_pending_intent_before_verdict_recovers(tmp_path):
    from harness_coordinator.v1.review import acquire_review_claim, write_review_pending_intent
    from harness_contracts.v1.queue_state import validate_queue
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    dead = _context("coord-dead", pid=999999, live=())
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 "coord-dead", RUN_ID, dead, T_NOW)
    with _scoped(fixture["state_root"]) as handle:
        write_review_pending_intent(handle, STATE_ROOT_ID, fixture["events"], claim, T_NOW)
    queue = json.loads(Path(fixture["state_root"], "queue.json").read_bytes().decode("utf-8"))
    assert validate_queue(queue, state_root_id=STATE_ROOT_ID)["valid"]
    assert [i["stage"] for i in queue["pending_intents"]] == ["review_claim"]

    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture, context=_context("coord-new", pid=os.getpid(), live=("coord-new",)))["status"] == "recorded"
    cleared = json.loads(Path(fixture["state_root"], "queue.json").read_bytes().decode("utf-8"))
    assert cleared["pending_intents"] == []


def test_run_started_recovery_does_not_reclaim_a_review_claim_as_a_worker_claim(tmp_path):
    from harness_coordinator.v1.recovery import run_started_recovery
    from harness_coordinator.v1.review import acquire_review_claim, review_claim_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                         "coord-dead", RUN_ID, _context("coord-dead", pid=999999, live=()), T_NOW)
    path = review_claim_path(fixture["state_root"], packet_id, 1)
    before = Path(path).read_bytes()

    report = run_started_recovery(state_root=fixture["state_root"], coordinator_id="coord-new",
                                  run_id="run-recover", trusted_process_context=_context("coord-new"),
                                  now="2026-08-10T01:30:00Z")
    try:
        assert report.reclaimed_locks == []
    finally:
        report.release_singleton()
    assert Path(path).read_bytes() == before, "worker-claim reconciliation must not touch review ownership"


# --------------------------------------------------------------------------
# Authenticated dependency provenance (revision 1, correction 2)
# --------------------------------------------------------------------------

def _state_root_child_in_review(tmp_path):
    """pkt-dep ACCEPTED and sealed; pkt-child depending on it, resting in REVIEW."""
    from harness_coordinator.v1.classify_runtime import promote_dependencies
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.recovery import _fold_journal
    from harness_coordinator.v1.seals_runtime import complete_terminal_seals
    from harness_coordinator.v1.store import read_journal

    fixture = _state_root_in_review(tmp_path, packet_id="pkt-dep")
    state_root = fixture["state_root"]
    _deposit(state_root, "pkt-dep", 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    complete_terminal_seals(state_root, fixture["events"], _fold(fixture), T_NOW)

    # Journal event_at must never go backwards, and the dependency's own
    # VERDICT_RECORDED already sits at T_NOW.
    child = _packet("pkt-child", dependencies=["pkt-dep"])
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, "2026-08-10T01:15:00Z", [child])
    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None, "fixture must not leave a torn journal tail"
    folded, _ = _fold_journal(state_root, events)
    assert folded["pkt-child"]["state"] == "BLOCKED"
    events, _ = promote_dependencies(state_root, os.path.join(state_root, "journal.ndjson"),
                                     os.path.join(state_root, "locks", "journal.wlock"),
                                     events, folded, COORD_ID, RUN_ID, STATE_ROOT_ID, "2026-08-10T01:20:00Z")
    child_fixture = _drive_to_review(state_root, events, child, dependency_evidence=("pkt-dep",),
                                     started_at="2026-08-10T01:21:00Z",
                                     recorded_at="2026-08-10T01:25:00Z",
                                     finished_at="2026-08-10T01:26:00Z")
    child_fixture["dependency"] = fixture
    return child_fixture


def _child_verdict(child_fixture):
    verdict = _verdict(child_fixture["packet"], child_fixture["worker_result"])
    verdict["reviewed_at"] = "2026-08-10T01:30:00Z"
    return _rehash_verdict(verdict)


def test_dependency_bearing_review_succeeds_with_an_authentic_seal(tmp_path):
    child = _state_root_child_in_review(tmp_path)
    _deposit(child["state_root"], "pkt-child", 1, _child_verdict(child))
    outcome = _resolve(child, packet_id="pkt-child", now=T_CHILD_NOW)
    assert outcome["status"] == "recorded"
    assert _fold(child)["pkt-child"]["state"] == "ACCEPTED"


def _corrupt_dep_seal(state_root, mutate):
    from harness_coordinator.v1.seals_runtime import terminal_seal_path
    path = terminal_seal_path(state_root, "pkt-dep")
    seal = json.loads(Path(path).read_bytes().decode("utf-8"))
    mutate(seal)
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(seal))
    return path


def test_dependency_seal_with_broken_self_hash_fails_closed(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    child = _state_root_child_in_review(tmp_path)
    # Fold first: this is the state maintenance already validated. The seal is
    # then swapped underneath it, so only review-time authentication can catch it.
    folded = _fold(child)
    _corrupt_dep_seal(child["state_root"], lambda s: s.update({"seal_sha256": "0" * 64}))
    _deposit(child["state_root"], "pkt-child", 1, _child_verdict(child))
    with pytest.raises(ReviewRefused) as excinfo:
        _resolve(child, packet_id="pkt-child", now=T_CHILD_NOW, folded=folded)
    assert "EVIDENCE_HASH_MISMATCH" in excinfo.value.codes
    assert folded["pkt-child"]["state"] == "REVIEW"


def test_dependency_seal_naming_a_different_packet_fails_closed(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    child = _state_root_child_in_review(tmp_path)

    def rename(seal):
        seal["packet_id"] = "pkt-other"
        seal["seal_sha256"] = compute_sha256(canonical_bytes(seal, omit={"seal_sha256"}))

    _corrupt_dep_seal(child["state_root"], rename)
    _deposit(child["state_root"], "pkt-child", 1, _child_verdict(child))
    with pytest.raises(ReviewRefused):
        _resolve(child, packet_id="pkt-child", now=T_CHILD_NOW)
    assert _fold(child)["pkt-child"]["state"] == "REVIEW"


def test_dependency_seal_swapped_after_maintenance_fails_closed(tmp_path):
    """The exact window: seal validated during maintenance, swapped before assembly."""
    from harness_coordinator.v1.review import ReviewRefused
    from harness_coordinator.v1.seals_runtime import complete_terminal_seals
    child = _state_root_child_in_review(tmp_path)
    state_root = child["state_root"]
    # Maintenance passes cleanly against the authentic seal.
    complete_terminal_seals(state_root, child["events"], _fold(child), T_NOW)

    def forge(seal):
        seal["upstream_digests"] = {"packet_sha256": "1" * 64, "result_sha256": "2" * 64,
                                    "verdict_sha256": "3" * 64, "bundle_sha256": "4" * 64}
        seal["seal_sha256"] = compute_sha256(canonical_bytes(seal, omit={"seal_sha256"}))

    _corrupt_dep_seal(state_root, forge)
    _deposit(state_root, "pkt-child", 1, _child_verdict(child))
    with pytest.raises(ReviewRefused):
        _resolve(child, packet_id="pkt-child", now=T_CHILD_NOW)
    assert _fold(child)["pkt-child"]["state"] == "REVIEW"


# --------------------------------------------------------------------------
# Codex regressions (revision 1)
# --------------------------------------------------------------------------

def test_existing_seal_with_broken_self_hash_is_not_idempotently_accepted(tmp_path):
    from harness_coordinator.v1.seals_runtime import SealContradiction, complete_terminal_seals, terminal_seal_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    _resolve(fixture)
    complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), T_NOW)

    # Fold before tampering: the fold has its own seal check, so capturing the
    # state maintenance already accepted is what isolates complete_terminal_seals.
    folded = _fold(fixture)
    path = terminal_seal_path(fixture["state_root"], packet_id)
    seal = json.loads(Path(path).read_bytes().decode("utf-8"))
    seal["seal_sha256"] = "0" * 64  # every binding field still matches exactly
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(seal))
    with pytest.raises(SealContradiction):
        complete_terminal_seals(fixture["state_root"], fixture["events"], folded, T_NOW)


def test_existing_seal_with_extra_fields_is_not_idempotently_accepted(tmp_path):
    from harness_coordinator.v1.seals_runtime import SealContradiction, complete_terminal_seals, terminal_seal_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    _resolve(fixture)
    complete_terminal_seals(fixture["state_root"], fixture["events"], _fold(fixture), T_NOW)

    folded = _fold(fixture)
    path = terminal_seal_path(fixture["state_root"], packet_id)
    seal = json.loads(Path(path).read_bytes().decode("utf-8"))
    seal["injected"] = "extra"
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(seal))
    with pytest.raises(SealContradiction):
        complete_terminal_seals(fixture["state_root"], fixture["events"], folded, T_NOW)


def test_committed_verdict_with_missing_artifact_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, bundle_artifact_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    os.remove(bundle_artifact_path(fixture["state_root"], packet_id, 1))
    with pytest.raises(VerdictConflict):
        _resolve(fixture)


def test_committed_verdict_with_digest_mismatched_artifact_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, verdict_artifact_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    from harness_coordinator.v1.review import verdict_inbox_path
    inbox = _deposit(fixture["state_root"], packet_id, 1,
                     _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    # Remove the deposit first: otherwise the persisted-vs-deposited conflict
    # check fires and this never reaches the committed-artifact verification
    # it exists to exercise.
    os.remove(inbox)
    assert not os.path.exists(verdict_inbox_path(fixture["state_root"], packet_id, 1))
    path = verdict_artifact_path(fixture["state_root"], packet_id, 1)
    tampered = json.loads(Path(path).read_bytes().decode("utf-8"))
    tampered["reviewed_at"] = "2026-08-10T01:12:00Z"
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(tampered))
    with pytest.raises(VerdictConflict):
        _resolve(fixture)


# --------------------------------------------------------------------------
# Revision 2, correction 1: atomic exclusive publication
# --------------------------------------------------------------------------

_BIG = b'{"pad":"' + b"x" * (6 * 1024 * 1024) + b'"}'


def _publish_writer(state_root, parts, payload, barrier, results):
    sys.path.insert(0, str(SCRIPTS))
    barrier.wait(timeout=30)
    try:
        from harness_coordinator.v1.seals_runtime import publish_exclusive
        results.put("created" if publish_exclusive(state_root, parts, payload) else "existed")
    except Exception as exc:  # noqa: BLE001 - the test asserts on the label
        results.put(f"error:{type(exc).__name__}")


def _publish_reader(path, expected_len, barrier, results):
    sys.path.insert(0, str(SCRIPTS))
    import time as _t
    barrier.wait(timeout=30)
    partial = 0
    deadline = _t.monotonic() + 20
    while _t.monotonic() < deadline:
        try:
            with open(path, "rb") as handle:
                observed = handle.read()
        except OSError:
            continue
        if len(observed) != expected_len:
            partial += 1
            break
        break
    results.put(f"partial:{partial}")


_PARTS = ("artifacts", "thing.json")


def test_a_failed_write_publishes_no_partial_final_artifact(tmp_path, monkeypatch):
    """The final name must never exist unless its bytes are complete."""
    import harness_coordinator.v1.seals_runtime as seals
    state_root = str(tmp_path)
    target = tmp_path / "artifacts" / "thing.json"

    def boom(fd, data):
        raise OSError("disk full")

    monkeypatch.setattr(seals, "_write_all", boom)
    with pytest.raises(OSError):
        seals.publish_exclusive(state_root, _PARTS, b'{"complete":true}')
    assert not target.exists(), "a failed write must not leave a visible final artifact"
    leftovers = os.listdir(str(tmp_path / "artifacts"))
    assert leftovers == [], f"temporary files must be cleaned up, found {leftovers}"


def test_publication_is_idempotent_for_identical_bytes_and_closed_for_different(tmp_path):
    from harness_coordinator.v1.seals_runtime import ArtifactConflict, publish_exclusive
    state_root = str(tmp_path)
    target = tmp_path / "artifacts" / "thing.json"
    payload = b'{"a":1}'
    assert publish_exclusive(state_root, _PARTS, payload) is True
    assert publish_exclusive(state_root, _PARTS, payload) is False
    with pytest.raises(ArtifactConflict):
        publish_exclusive(state_root, _PARTS, b'{"a":2}')
    assert target.read_bytes() == payload


def test_concurrent_reader_never_observes_a_partially_published_artifact(tmp_path):
    """A 6 MiB payload makes the write window wide enough to catch a partial."""
    state_root = str(tmp_path)
    parts = ("artifacts", "big.json")
    target = str(tmp_path / "artifacts" / "big.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    barrier = multiprocessing.Barrier(2)
    results = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(target=_publish_writer, args=(state_root, parts, _BIG, barrier, results)),
        multiprocessing.Process(target=_publish_reader, args=(target, len(_BIG), barrier, results)),
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(60)
    observed = sorted(results.get(timeout=10) for _ in range(2))
    assert observed == ["created", "partial:0"], observed


def _seal_writer(state_root, barrier, results):
    sys.path.insert(0, str(SCRIPTS))
    try:
        from harness_coordinator.v1.recovery import _fold_journal
        from harness_coordinator.v1.seals_runtime import complete_terminal_seals
        from harness_coordinator.v1.store import read_journal
        events, _ = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
        folded, _ = _fold_journal(state_root, events)
    except Exception as exc:  # noqa: BLE001
        barrier.wait(timeout=30)
        results.put(f"error:{type(exc).__name__}")
        return
    barrier.wait(timeout=30)
    try:
        results.put("sealed" if complete_terminal_seals(state_root, events, folded, T_NOW) else "noop")
    except Exception as exc:  # noqa: BLE001
        results.put(f"error:{type(exc).__name__}")


def test_two_identical_seal_writers_produce_exactly_one_creation(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    _resolve(fixture)
    barrier = multiprocessing.Barrier(2)
    results = multiprocessing.Queue()
    procs = [multiprocessing.Process(target=_seal_writer, args=(fixture["state_root"], barrier, results))
             for _ in range(2)]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(30)
    assert sorted(results.get(timeout=10) for _ in range(2)) == ["noop", "sealed"]


def _artifact_writer(state_root, parts, payload, barrier, results):
    sys.path.insert(0, str(SCRIPTS))
    barrier.wait(timeout=30)
    try:
        from harness_coordinator.v1.seals_runtime import publish_exclusive
        results.put("created" if publish_exclusive(state_root, parts, payload) else "existed")
    except Exception as exc:  # noqa: BLE001
        results.put(f"error:{type(exc).__name__}")


def test_two_identical_verdict_and_bundle_writers_have_one_creator_each(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    verdict = _verdict(fixture["packet"], fixture["worker_result"])
    for parts, payload in ((("results", packet_id, "1", "opus-verdict.json"), canonical_bytes(verdict)),
                           (("results", packet_id, "1", "replay-bundle.json"), b'{"bundle":"identical"}')):
        path = os.path.join(fixture["state_root"], *parts)
        barrier = multiprocessing.Barrier(2)
        results = multiprocessing.Queue()
        procs = [multiprocessing.Process(target=_artifact_writer,
                                         args=(fixture["state_root"], parts, payload, barrier, results))
                 for _ in range(2)]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(30)
        assert sorted(results.get(timeout=10) for _ in range(2)) == ["created", "existed"]
        assert Path(path).read_bytes() == payload


# --------------------------------------------------------------------------
# Revision 2, correction 2: review intent generations vs generic recovery
# --------------------------------------------------------------------------

def _recover(fixture, coordinator_id="coord-recover", run_id="run-recover", now="2026-08-10T02:00:00Z"):
    """Run the real accepted recovery, then refresh the fixture's journal view."""
    from harness_coordinator.v1.recovery import run_started_recovery
    from harness_coordinator.v1.store import read_journal
    report = run_started_recovery(state_root=fixture["state_root"], coordinator_id=coordinator_id,
                                  run_id=run_id, trusted_process_context=_context(coordinator_id), now=now)
    try:
        pass
    finally:
        report.release_singleton()
    fixture["events"], torn = read_journal(os.path.join(fixture["state_root"], "journal.ndjson"),
                                           state_root_id=STATE_ROOT_ID)
    assert torn is None
    return report


def test_generic_recovery_abandonment_advances_the_review_generation(tmp_path):
    from harness_coordinator.v1.review import (acquire_review_claim, current_review_generation,
                                               review_intent_id, write_review_pending_intent)
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    assert current_review_generation(fixture["events"], packet_id, 1) == 0

    dead = _context("coord-dead", pid=999999, live=())
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 "coord-dead", RUN_ID, dead, T_NOW)
    assert claim["intent_id"] == review_intent_id(packet_id, 1, 0)
    with _scoped(fixture["state_root"]) as handle:
        write_review_pending_intent(handle, STATE_ROOT_ID, fixture["events"], claim, T_NOW)

    _recover(fixture)
    abandoned = [e for e in fixture["events"] if e["event_type"] == "INTENT_ABANDONED"
                 and e["intent_id"] == review_intent_id(packet_id, 1, 0)]
    assert len(abandoned) == 1, "generic recovery must abandon the uncommitted review intent"
    assert current_review_generation(fixture["events"], packet_id, 1) == 1


def test_verdict_never_reuses_an_abandoned_review_intent(tmp_path):
    from harness_coordinator.v1.review import (acquire_review_claim, review_intent_id,
                                               write_review_pending_intent)
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 "coord-dead", RUN_ID, _context("coord-dead", pid=999999, live=()), T_NOW)
    with _scoped(fixture["state_root"]) as handle:
        write_review_pending_intent(handle, STATE_ROOT_ID, fixture["events"], claim, T_NOW)
    _recover(fixture)

    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    outcome = _resolve(fixture, context=_context("coord-new"), now="2026-08-10T02:05:00Z")
    assert outcome["status"] == "recorded"

    committed = [e for e in fixture["events"] if e["event_type"] == "VERDICT_RECORDED"]
    assert len(committed) == 1
    assert committed[0]["intent_id"] == review_intent_id(packet_id, 1, 1)
    abandoned_ids = {e["intent_id"] for e in fixture["events"] if e["event_type"] == "INTENT_ABANDONED"}
    assert committed[0]["intent_id"] not in abandoned_ids


def test_restart_recognizes_a_committed_generation_and_does_not_abandon_it(tmp_path):
    from harness_coordinator.v1.review import review_intent_id
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    committed_id = review_intent_id(packet_id, 1, 0)

    _recover(fixture)
    abandoned_ids = {e["intent_id"] for e in fixture["events"] if e["event_type"] == "INTENT_ABANDONED"}
    assert committed_id not in abandoned_ids, "a committed review intent must never be abandoned"
    assert _resolve(fixture, now="2026-08-10T02:05:00Z")["status"] == "already_recorded"


def test_crash_after_verdict_before_cleanup_is_resumed_and_cleaned(tmp_path):
    from harness_coordinator.v1.review import review_claim_path
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    # Simulate a crash between commit and cleanup by restoring the claim.
    from harness_coordinator.v1.review import acquire_review_claim
    path = review_claim_path(fixture["state_root"], packet_id, 1)
    if not os.path.exists(path):
        acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                             COORD_ID, RUN_ID, _context(), T_NOW)
    _recover(fixture)
    assert _resolve(fixture, now="2026-08-10T02:05:00Z")["status"] == "already_recorded"
    assert not os.path.exists(path), "a committed review must not leave its claim behind"


# --------------------------------------------------------------------------
# Revision 2, correction 3: exception-safe ownership cleanup
# --------------------------------------------------------------------------

def _assert_no_owned_ownership(state_root, packet_id, attempt=1):
    from harness_coordinator.v1.review import review_claim_path
    assert not os.path.exists(review_claim_path(state_root, packet_id, attempt))
    queue_path = os.path.join(state_root, "queue.json")
    if os.path.exists(queue_path):
        queue = json.loads(Path(queue_path).read_bytes().decode("utf-8"))
        assert [i for i in queue["pending_intents"] if i["packet_id"] == packet_id] == []


@pytest.mark.parametrize("mutate,label", [
    (lambda p, w: _verdict(p, w, reviewer_session="sess-attacker"), "untrusted"),
    (lambda p, w: {"not": "a verdict"}, "malformed"),
])
def test_refused_verdict_releases_ownership(tmp_path, mutate, label):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, mutate(fixture["packet"], fixture["worker_result"]))
    with pytest.raises(ReviewRefused):
        _resolve(fixture)
    _assert_no_owned_ownership(fixture["state_root"], packet_id)
    assert _fold(fixture)[packet_id]["state"] == "REVIEW"


def test_self_review_refusal_releases_ownership(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _write_trust_roots(fixture["state_root"], (TRUSTED_REVIEWER, fixture["session_id"]))
    _deposit(fixture["state_root"], packet_id, 1,
             _verdict(fixture["packet"], fixture["worker_result"], reviewer_session=fixture["session_id"]))
    with pytest.raises(ReviewRefused):
        _resolve(fixture)
    _assert_no_owned_ownership(fixture["state_root"], packet_id)


def test_substituted_verdict_refusal_releases_ownership(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    fake = _packet(packet_id)
    fake["objective"] = "attacker objective"
    fake["packet_sha256"] = compute_sha256(canonical_bytes(fake, omit={"packet_sha256"}))
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fake, _worker_result(fake, "sess-fake")))
    with pytest.raises(ReviewRefused):
        _resolve(fixture)
    _assert_no_owned_ownership(fixture["state_root"], packet_id)


def test_successful_commit_releases_ownership(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    _assert_no_owned_ownership(fixture["state_root"], packet_id)


# --------------------------------------------------------------------------
# Revision 2, correction 4: unrelated pending intents are preserved
# --------------------------------------------------------------------------

def _seed_foreign_pending_intent(state_root, events, packet_id="pkt-other"):
    from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal
    from harness_coordinator.v1.store import atomic_replace
    folded, _ = _fold_journal(state_root, events)
    queue = _build_derived_queue(folded, STATE_ROOT_ID, events[-1] if events else None)
    foreign = {"intent_id": f"attempt-{packet_id}-1", "packet_id": packet_id, "stage": "claim",
               "created_at": T_ENROLL, "coordinator_id": "coord-other", "run_id": "run-other",
               "boot_id": "boot-other", "pid": 4242}
    queue["pending_intents"] = [foreign]
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(queue), "coord-seed", "seed")
    return foreign


def _pending(state_root):
    queue = json.loads(Path(state_root, "queue.json").read_bytes().decode("utf-8"))
    return queue["pending_intents"]


def test_unrelated_pending_intents_survive_review_ownership(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    foreign = _seed_foreign_pending_intent(fixture["state_root"], fixture["events"])
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    survivors = _pending(fixture["state_root"])
    assert foreign in survivors, "an unrelated pending intent must survive field-for-field"
    assert [i for i in survivors if i["packet_id"] == packet_id] == []


def test_unrelated_pending_intents_survive_a_refusal(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    foreign = _seed_foreign_pending_intent(fixture["state_root"], fixture["events"])
    _deposit(fixture["state_root"], packet_id, 1,
             _verdict(fixture["packet"], fixture["worker_result"], reviewer_session="sess-attacker"))
    with pytest.raises(ReviewRefused):
        _resolve(fixture)
    assert foreign in _pending(fixture["state_root"])


def test_review_pending_intent_is_merged_not_replaced(tmp_path):
    from harness_coordinator.v1.review import acquire_review_claim, write_review_pending_intent
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    foreign = _seed_foreign_pending_intent(fixture["state_root"], fixture["events"])
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 COORD_ID, RUN_ID, _context(), T_NOW)
    with _scoped(fixture["state_root"]) as handle:
        write_review_pending_intent(handle, STATE_ROOT_ID, fixture["events"], claim, T_NOW)
    pending = _pending(fixture["state_root"])
    assert foreign in pending
    assert {i["packet_id"] for i in pending} == {"pkt-other", packet_id}


def test_malformed_queue_pending_intents_fail_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, acquire_review_claim, write_review_pending_intent
    fixture = _state_root_in_review(tmp_path)
    packet_id = fixture["packet"]["packet_id"]
    queue_path = os.path.join(fixture["state_root"], "queue.json")
    queue = json.loads(Path(queue_path).read_bytes().decode("utf-8"))
    queue["pending_intents"] = [{"intent_id": "broken"}]
    with open(queue_path, "wb") as handle:
        handle.write(canonical_bytes(queue))
    claim = acquire_review_claim(fixture["state_root"], STATE_ROOT_ID, fixture["events"], packet_id, 1,
                                 COORD_ID, RUN_ID, _context(), T_NOW)
    with _scoped(fixture["state_root"]) as handle:
        with pytest.raises(VerdictConflict):
            write_review_pending_intent(handle, STATE_ROOT_ID, fixture["events"], claim, T_NOW)


# --------------------------------------------------------------------------
# Revision 3, defect 1: pending intents validated by the accepted contract
# --------------------------------------------------------------------------

def _scoped(state_root):
    from harness_coordinator.v1.seals_runtime import open_state_root
    return open_state_root(state_root)


def _load_pending(state_root, state_root_id=STATE_ROOT_ID):
    from harness_coordinator.v1.review import load_pending_intents
    with _scoped(state_root) as handle:
        return load_pending_intents(handle, state_root_id)


def _write_pending(state_root, events, pending):
    from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal
    from harness_coordinator.v1.store import atomic_replace
    folded, _ = _fold_journal(state_root, events)
    queue = _build_derived_queue(folded, STATE_ROOT_ID, events[-1] if events else None)
    queue["pending_intents"] = pending
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    atomic_replace(os.path.join(state_root, "queue.json"), canonical_bytes(queue), "coord-seed", "seed")


def _valid_intent(packet_id="pkt-other", intent_id=None):
    return {"intent_id": intent_id or f"attempt-{packet_id}-1", "packet_id": packet_id,
            "stage": "claim", "created_at": T_ENROLL, "coordinator_id": "coord-other",
            "run_id": "run-other", "boot_id": "boot-other", "pid": 4242}


@pytest.mark.parametrize("mutate,label", [
    (lambda i: {**i, "pid": "not-an-int"}, "invalid_pid_type"),
    (lambda i: {**i, "stage": "not_a_stage"}, "invalid_stage"),
    (lambda i: {**i, "created_at": "yesterday"}, "non_rfc3339_created_at"),
    (lambda i: {**i, "surprise": "field"}, "unknown_field"),
    (lambda i: {k: v for k, v in i.items() if k != "boot_id"}, "missing_field"),
    (lambda i: {**i, "pid": 0}, "non_positive_pid"),
])
def test_malformed_pending_intent_fails_closed(tmp_path, mutate, label):
    from harness_coordinator.v1.review import VerdictConflict
    fixture = _state_root_in_review(tmp_path)
    _write_pending(fixture["state_root"], fixture["events"], [mutate(_valid_intent())])
    with pytest.raises(VerdictConflict):
        _load_pending(fixture["state_root"])


def test_duplicate_pending_intent_id_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict
    fixture = _state_root_in_review(tmp_path)
    duplicate = _valid_intent("pkt-a", "same-intent")
    other = _valid_intent("pkt-b", "same-intent")
    _write_pending(fixture["state_root"], fixture["events"], [duplicate, other])
    with pytest.raises(VerdictConflict):
        _load_pending(fixture["state_root"])


def test_duplicate_pending_packet_id_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict
    fixture = _state_root_in_review(tmp_path)
    _write_pending(fixture["state_root"], fixture["events"],
                   [_valid_intent("pkt-a", "intent-1"), _valid_intent("pkt-a", "intent-2")])
    with pytest.raises(VerdictConflict):
        _load_pending(fixture["state_root"])


def test_valid_pending_intents_load_unchanged(tmp_path):
    fixture = _state_root_in_review(tmp_path)
    intents = [_valid_intent("pkt-a", "intent-a"), _valid_intent("pkt-b", "intent-b")]
    _write_pending(fixture["state_root"], fixture["events"], intents)
    assert _load_pending(fixture["state_root"]) == intents


# --------------------------------------------------------------------------
# Revision 3, defect 2: canonical, monotonic review generations
# --------------------------------------------------------------------------

def _abandon_event(packet_id, attempt, generation, seq):
    return {"event_type": "INTENT_ABANDONED", "packet_id": packet_id, "seq": seq,
            "intent_id": f"verdict-{packet_id}-{attempt}-g{generation}"}


def _verdict_event(packet_id, attempt, generation, seq):
    return {"event_type": "VERDICT_RECORDED", "packet_id": packet_id, "seq": seq,
            "intent_id": f"verdict-{packet_id}-{attempt}-g{generation}"}


def test_generation_is_the_contiguous_prefix_length(tmp_path):
    from harness_coordinator.v1.review import current_review_generation
    assert current_review_generation([], "pkt-a", 1) == 0
    assert current_review_generation([_abandon_event("pkt-a", 1, 0, 1)], "pkt-a", 1) == 1
    assert current_review_generation(
        [_abandon_event("pkt-a", 1, 0, 1), _abandon_event("pkt-a", 1, 1, 2)], "pkt-a", 1) == 2


def test_repeated_abandonment_of_one_generation_advances_only_once(tmp_path):
    from harness_coordinator.v1.review import current_review_generation
    events = [_abandon_event("pkt-a", 1, 0, 1), _abandon_event("pkt-a", 1, 0, 2),
              _abandon_event("pkt-a", 1, 0, 3)]
    assert current_review_generation(events, "pkt-a", 1) == 1


def test_generation_gap_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    events = [_abandon_event("pkt-a", 1, 0, 1), _abandon_event("pkt-a", 1, 2, 2)]
    with pytest.raises(VerdictConflict):
        current_review_generation(events, "pkt-a", 1)


def test_non_zero_only_generation_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    with pytest.raises(VerdictConflict):
        current_review_generation([_abandon_event("pkt-a", 1, 5, 1)], "pkt-a", 1)


def test_committed_generation_never_yields_a_new_one(tmp_path):
    from harness_coordinator.v1.review import current_review_generation
    events = [_abandon_event("pkt-a", 1, 0, 1), _verdict_event("pkt-a", 1, 1, 2)]
    assert current_review_generation(events, "pkt-a", 1) == 1
    assert current_review_generation([_verdict_event("pkt-a", 1, 0, 1)], "pkt-a", 1) == 0


def test_abandonment_after_a_committed_generation_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    events = [_verdict_event("pkt-a", 1, 0, 1), _abandon_event("pkt-a", 1, 1, 2)]
    with pytest.raises(VerdictConflict):
        current_review_generation(events, "pkt-a", 1)


def test_generation_both_committed_and_abandoned_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    events = [_abandon_event("pkt-a", 1, 0, 1), _verdict_event("pkt-a", 1, 0, 2)]
    with pytest.raises(VerdictConflict):
        current_review_generation(events, "pkt-a", 1)


def test_multiple_committed_generations_fail_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    events = [_verdict_event("pkt-a", 1, 0, 1), _verdict_event("pkt-a", 1, 1, 2)]
    with pytest.raises(VerdictConflict):
        current_review_generation(events, "pkt-a", 1)


def test_malformed_generation_suffix_fails_closed(tmp_path):
    from harness_coordinator.v1.review import VerdictConflict, current_review_generation
    events = [{"event_type": "INTENT_ABANDONED", "packet_id": "pkt-a", "seq": 1,
               "intent_id": "verdict-pkt-a-1-gX"}]
    with pytest.raises(VerdictConflict):
        current_review_generation(events, "pkt-a", 1)


def test_other_packets_and_attempts_do_not_shift_a_generation(tmp_path):
    from harness_coordinator.v1.review import current_review_generation
    events = [_abandon_event("pkt-b", 1, 0, 1), _abandon_event("pkt-a", 2, 0, 2),
              _abandon_event("pkt-a", 11, 0, 3)]
    assert current_review_generation(events, "pkt-a", 1) == 0


# --------------------------------------------------------------------------
# Revision 3, defect 3: collision-safe, retry-idempotent publication
# --------------------------------------------------------------------------

def test_temp_cleanup_failure_does_not_break_the_commit_or_an_identical_retry(tmp_path, monkeypatch):
    import harness_coordinator.v1.seals_runtime as seals
    state_root = str(tmp_path)
    payload = b'{"v":1}'
    monkeypatch.setattr(seals, "_remove_temp", lambda dir_fd, name: None)
    assert seals.publish_exclusive(state_root, _PARTS, payload) is True
    leftovers = [n for n in os.listdir(str(tmp_path / "artifacts")) if n.startswith(".")]
    assert leftovers, "this test requires the temp to have been left behind"
    # An identical retry must be idempotent, not a failure on the stale temp.
    assert seals.publish_exclusive(state_root, _PARTS, payload) is False
    assert (tmp_path / "artifacts" / "thing.json").read_bytes() == payload


def test_a_stale_foreign_temp_is_neither_trusted_nor_deleted(tmp_path):
    from harness_coordinator.v1.seals_runtime import publish_exclusive
    state_root = str(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    stale = artifacts / ".thing.json.tmp.coord-1.4242.nonce-1"
    stale.write_bytes(b"someone else's leftover")
    assert publish_exclusive(state_root, _PARTS, b'{"v":1}') is True
    assert stale.exists(), "a temp this call did not create must never be removed"
    assert stale.read_bytes() == b"someone else's leftover"


def test_publication_uses_a_unique_temp_name_per_call(tmp_path, monkeypatch):
    import harness_coordinator.v1.seals_runtime as seals
    seen = []
    real_open = os.open

    def spy(path, flags, mode=0o777, **kwargs):
        if isinstance(path, str) and path.startswith(".") and ".tmp." in path:
            seen.append(path)
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(seals.os, "open", spy)
    seals.publish_exclusive(str(tmp_path), _PARTS, b'{"v":1}')
    seals.publish_exclusive(str(tmp_path), ("artifacts", "other.json"), b'{"v":2}')
    assert len(seen) == 2 and seen[0] != seen[1], seen


# --------------------------------------------------------------------------
# Revision 3, defect 4: publication directories are pinned, not re-resolved
# --------------------------------------------------------------------------

def _outside(tmp_path):
    target = tmp_path.parent / f"outside-{tmp_path.name}"
    target.mkdir(exist_ok=True)
    return target


@pytest.mark.parametrize("parts,parent", [
    (("review", "locks", "pkt-review.1.lock.json"), ("review", "locks")),
    (("state", "terminal", "pkt-review.seal.json"), ("state", "terminal")),
    (("results", "pkt-review", "1", "opus-verdict.json"), ("results", "pkt-review", "1")),
])
def test_symlinked_publication_parent_is_refused(tmp_path, parts, parent):
    from harness_coordinator.v1.seals_runtime import publish_exclusive
    state_root = tmp_path / "root"
    state_root.mkdir()
    outside = _outside(tmp_path)
    link_at = state_root.joinpath(*parent)
    link_at.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(str(outside), str(link_at))
    with pytest.raises(OSError):
        publish_exclusive(str(state_root), parts, b'{"v":1}')
    assert os.listdir(str(outside)) == [], "publication must never escape the state root"


def test_parent_swapped_mid_publication_still_lands_in_the_pinned_directory(tmp_path, monkeypatch):
    """The retained directory FD, not a re-resolved pathname, is the target."""
    import harness_coordinator.v1.seals_runtime as seals
    state_root = tmp_path / "root"
    (state_root / "artifacts").mkdir(parents=True)
    outside = _outside(tmp_path)
    real_write = seals._write_all

    def swap_then_write(fd, data):
        real_write(fd, data)
        os.rename(str(state_root / "artifacts"), str(state_root / "artifacts-moved"))
        os.symlink(str(outside), str(state_root / "artifacts"))

    monkeypatch.setattr(seals, "_write_all", swap_then_write)
    assert seals.publish_exclusive(str(state_root), _PARTS, b'{"v":1}') is True
    assert (state_root / "artifacts-moved" / "thing.json").read_bytes() == b'{"v":1}'
    assert os.listdir(str(outside)) == [], "a swapped parent must not receive the artifact"


@pytest.mark.parametrize("component", ["..", ".", "", "a/b", "/abs"])
def test_unsafe_publication_components_are_refused(tmp_path, component):
    from harness_coordinator.v1.seals_runtime import publish_exclusive
    with pytest.raises(ValueError):
        publish_exclusive(str(tmp_path), ("artifacts", component, "thing.json"), b'{"v":1}')


def test_symlinked_state_root_is_refused(tmp_path):
    from harness_coordinator.v1.seals_runtime import publish_exclusive
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    with pytest.raises(OSError):
        publish_exclusive(str(link), _PARTS, b'{"v":1}')


# --------------------------------------------------------------------------
# Revision 4: trusted state-root identity across the whole P5C lifecycle
# --------------------------------------------------------------------------

def _fd_count():
    return len(os.listdir("/dev/fd"))


def _swap_root(state_root, outside):
    """Rename the state root away and leave a symlink to `outside` in its place."""
    moved = f"{state_root}-moved"
    os.rename(state_root, moved)
    os.symlink(str(outside), state_root)
    return moved


def test_ancestor_symlinked_state_root_is_refused(tmp_path):
    from harness_coordinator.v1.seals_runtime import open_state_root
    real = tmp_path / "real"
    (real / "root").mkdir(parents=True)
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    with pytest.raises(OSError):
        open_state_root(str(link / "root"))


def test_relative_and_dotted_state_roots_are_refused(tmp_path):
    from harness_coordinator.v1.seals_runtime import open_state_root
    for candidate in ("relative/root", f"{tmp_path}/../x", f"{tmp_path}/./y"):
        with pytest.raises(ValueError):
            open_state_root(candidate)


def test_state_root_handle_detects_a_renamed_and_replaced_root(tmp_path):
    from harness_coordinator.v1.seals_runtime import StateRootMoved, open_state_root
    state_root = tmp_path / "root"
    state_root.mkdir()
    outside = _outside(tmp_path)
    with open_state_root(str(state_root)) as handle:
        handle.verify_identity()
        moved = _swap_root(str(state_root), outside)
        with pytest.raises(StateRootMoved):
            handle.verify_identity()
        # The pinned handle still writes to the ORIGINAL directory, never the
        # replacement, so a swap cannot redirect an in-flight publication.
        assert handle.publish(("artifacts", "thing.json"), b'{"v":1}') is True
    assert Path(moved, "artifacts", "thing.json").read_bytes() == b'{"v":1}'
    assert os.listdir(str(outside)) == []


def test_handle_reads_are_not_redirected_by_a_parent_swap(tmp_path):
    from harness_coordinator.v1.seals_runtime import open_state_root
    state_root = tmp_path / "root"
    (state_root / "review" / "inbox").mkdir(parents=True)
    (state_root / "review" / "inbox" / "a.json").write_bytes(b'{"real":true}')
    outside = _outside(tmp_path)
    (outside / "a.json").write_bytes(b'{"attacker":true}')
    with open_state_root(str(state_root)) as handle:
        os.rename(str(state_root / "review" / "inbox"), str(state_root / "review" / "inbox-moved"))
        os.symlink(str(outside), str(state_root / "review" / "inbox"))
        with pytest.raises(OSError):
            handle.read(("review", "inbox", "a.json"))


def test_handle_unlink_and_rename_never_touch_a_swapped_parent(tmp_path):
    from harness_coordinator.v1.seals_runtime import open_state_root
    state_root = tmp_path / "root"
    (state_root / "review" / "locks").mkdir(parents=True)
    (state_root / "review" / "locks" / "c.json").write_bytes(b'{"mine":true}')
    outside = _outside(tmp_path)
    (outside / "c.json").write_bytes(b'{"theirs":true}')
    with open_state_root(str(state_root)) as handle:
        os.rename(str(state_root / "review" / "locks"), str(state_root / "review" / "locks-moved"))
        os.symlink(str(outside), str(state_root / "review" / "locks"))
        with pytest.raises(OSError):
            handle.unlink(("review", "locks", "c.json"))
        with pytest.raises(OSError):
            handle.rename(("review", "locks", "c.json"), ("review", "archive", "c.json"))
    assert (outside / "c.json").read_bytes() == b'{"theirs":true}', "no outside file may be unlinked or moved"
    assert Path(state_root.parent, "root", "review", "locks-moved", "c.json").exists()


def test_review_claim_parent_swap_does_not_consume_a_replacement_claim(tmp_path):
    from harness_coordinator.v1.review import acquire_review_claim
    from harness_coordinator.v1.seals_runtime import open_state_root
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    packet_id = fixture["packet"]["packet_id"]
    acquire_review_claim(state_root, STATE_ROOT_ID, fixture["events"], packet_id, 1,
                         COORD_ID, RUN_ID, _context(), T_NOW)
    outside = _outside(tmp_path)
    forged = {"forged": True}
    (outside / f"{packet_id}.1.lock.json").write_bytes(canonical_bytes(forged))
    with open_state_root(state_root) as handle:
        os.rename(os.path.join(state_root, "review", "locks"), os.path.join(state_root, "review", "locks-moved"))
        os.symlink(str(outside), os.path.join(state_root, "review", "locks"))
        with pytest.raises(OSError):
            handle.read(("review", "locks", f"{packet_id}.1.lock.json"))


def test_committed_verification_fails_closed_when_root_identity_changes(tmp_path):
    from harness_coordinator.v1.recovery import _fold_journal
    from harness_coordinator.v1.review import resolve_review
    from harness_coordinator.v1.seals_runtime import StateRootMoved, open_state_root
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    packet_id = fixture["packet"]["packet_id"]
    _deposit(state_root, packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"

    outside = _outside(tmp_path)
    with open_state_root(state_root) as handle:
        _swap_root(state_root, outside)
        folded, _ = _fold_journal(os.path.join(str(tmp_path), "root-moved"), fixture["events"])
        with pytest.raises(StateRootMoved):
            resolve_review(state_root=state_root, state_root_id=STATE_ROOT_ID,
                           journal_events=fixture["events"], folded=folded, packet_id=packet_id,
                           coordinator_id=COORD_ID, run_id=RUN_ID,
                           trusted_process_context=_context(), now=T_NOW, handle=handle)
    assert os.listdir(str(outside)) == []


def test_run_once_halts_when_the_root_is_replaced_during_recovery(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    outside = _outside(tmp_path)
    real_recovery = coordinator.run_started_recovery

    def swap_after_recovery(**kwargs):
        report = real_recovery(**kwargs)
        _swap_root(state_root, outside)
        return report

    monkeypatch.setattr(coordinator, "run_started_recovery", swap_after_recovery)
    with pytest.raises(StateRootMoved):
        coordinator.run_once(state_root, COORD_ID, RUN_ID, _context(), "2026-08-10T02:00:00Z")
    assert os.listdir(str(outside)) == [], "no P5C write may reach a replacement root"


def test_no_file_descriptors_leak_on_success_refusal_or_exception(tmp_path):
    from harness_coordinator.v1.review import ReviewRefused
    from harness_coordinator.v1.seals_runtime import open_state_root

    # success
    fixture = _state_root_in_review(tmp_path / "ok")
    packet_id = fixture["packet"]["packet_id"]
    _deposit(fixture["state_root"], packet_id, 1, _verdict(fixture["packet"], fixture["worker_result"]))
    before = _fd_count()
    assert _resolve(fixture)["status"] == "recorded"
    assert _fd_count() == before, "successful review leaked a file descriptor"

    # handled refusal
    refused = _state_root_in_review(tmp_path / "refused")
    rid = refused["packet"]["packet_id"]
    _deposit(refused["state_root"], rid, 1,
             _verdict(refused["packet"], refused["worker_result"], reviewer_session="sess-attacker"))
    before = _fd_count()
    with pytest.raises(ReviewRefused):
        _resolve(refused)
    assert _fd_count() == before, "refused review leaked a file descriptor"

    # exception inside publication
    import harness_coordinator.v1.seals_runtime as seals
    root = tmp_path / "boom"
    root.mkdir()
    before = _fd_count()
    original = seals._write_all
    try:
        seals._write_all = lambda fd, data: (_ for _ in ()).throw(OSError("disk full"))
        with pytest.raises(OSError):
            seals.publish_exclusive(str(root), ("artifacts", "x.json"), b"{}")
    finally:
        seals._write_all = original
    assert _fd_count() == before, "failed publication leaked a file descriptor"

    # refused root open
    before = _fd_count()
    with pytest.raises(OSError):
        open_state_root(str(tmp_path / "does-not-exist"))
    assert _fd_count() == before, "refused root open leaked a file descriptor"


def test_root_replacement_during_recovery_halts_before_any_maintenance(tmp_path, monkeypatch):
    """The post-recovery identity check must fire before P5C does any work.

    A later guard inside `_maintenance` would also catch this, so asserting
    only "it raises" proves nothing about ordering. Recording whether
    maintenance ran at all is what pins the check to its stated position:
    halt before P5C writes, not during them.
    """
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    outside = _outside(tmp_path)
    real_recovery = coordinator.run_started_recovery
    maintenance_calls = []

    def swap_after_recovery(**kwargs):
        report = real_recovery(**kwargs)
        _swap_root(state_root, outside)
        return report

    real_maintenance = coordinator._maintenance

    def recording_maintenance(*args, **kwargs):
        maintenance_calls.append(True)
        return real_maintenance(*args, **kwargs)

    monkeypatch.setattr(coordinator, "run_started_recovery", swap_after_recovery)
    monkeypatch.setattr(coordinator, "_maintenance", recording_maintenance)
    with pytest.raises(StateRootMoved):
        coordinator.run_once(state_root, COORD_ID, RUN_ID, _context(), "2026-08-10T02:00:00Z")
    assert maintenance_calls == [], "identity must be verified before any P5C maintenance runs"
    assert os.listdir(str(outside)) == []


# --------------------------------------------------------------------------
# Revision 5: root-identity guards around the accepted pathname primitives
# --------------------------------------------------------------------------

def _accepted_fixture_with_verdict(tmp_path, packet_id="pkt-review"):
    fixture = _state_root_in_review(tmp_path / "root", packet_id=packet_id)
    _deposit(fixture["state_root"], packet_id, 1,
             _verdict(fixture["packet"], fixture["worker_result"]))
    return fixture, _outside(tmp_path)


def test_root_swap_immediately_before_verdict_append_writes_no_event(tmp_path, monkeypatch):
    """The pre-append guard must fire before any journal write leaves the root."""
    import harness_coordinator.v1.review as review
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture, outside = _accepted_fixture_with_verdict(tmp_path)
    state_root = fixture["state_root"]
    journal_before = Path(state_root, "journal.ndjson").read_bytes()

    real_persist = review._persist_artifact

    def swap_after_artifacts(handle, parts, value):
        result = real_persist(handle, parts, value)
        if parts[-1] == "replay-bundle.json":
            _swap_root(state_root, outside)
        return result

    monkeypatch.setattr(review, "_persist_artifact", swap_after_artifacts)
    with pytest.raises(StateRootMoved):
        _resolve(fixture)
    assert os.listdir(str(outside)) == [], "no journal event may reach a replacement root"
    assert Path(f"{state_root}-moved", "journal.ndjson").read_bytes() == journal_before


def test_root_swap_immediately_after_verdict_append_halts_before_more_work(tmp_path, monkeypatch):
    """A post-append swap must halt rather than seal against the replacement."""
    import harness_coordinator.v1.review as review
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture, outside = _accepted_fixture_with_verdict(tmp_path)
    state_root = fixture["state_root"]
    real_append = review.append_journal

    def append_then_swap(*args, **kwargs):
        real_append(*args, **kwargs)
        _swap_root(state_root, outside)

    monkeypatch.setattr(review, "append_journal", append_then_swap)
    with pytest.raises(StateRootMoved):
        _resolve(fixture)
    moved = f"{state_root}-moved"
    # The append itself landed in the original root and is durable.
    events, _ = __import__("harness_coordinator.v1.store", fromlist=["read_journal"]).read_journal(
        os.path.join(moved, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert [e["event_type"] for e in events][-1] == "VERDICT_RECORDED"
    # Nothing followed it into the replacement.
    assert os.listdir(str(outside)) == []
    assert not os.path.exists(os.path.join(moved, "state", "terminal"))


def test_root_swap_before_requeue_halts_and_never_requeues(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    outside = _outside(tmp_path)
    real_promote = coordinator.promote_dependencies
    requeue_calls = []

    def promote_then_swap(*args, **kwargs):
        result = real_promote(*args, **kwargs)
        _swap_root(state_root, outside)
        return result

    real_requeue = coordinator.requeue_revise

    def recording_requeue(*args, **kwargs):
        requeue_calls.append(True)
        return real_requeue(*args, **kwargs)

    monkeypatch.setattr(coordinator, "promote_dependencies", promote_then_swap)
    monkeypatch.setattr(coordinator, "requeue_revise", recording_requeue)
    with pytest.raises(StateRootMoved):
        coordinator.run_once(state_root, COORD_ID, RUN_ID, _context(), "2026-08-10T02:00:00Z")
    assert requeue_calls == [], "a swapped root must halt before REVISE requeue runs"
    assert os.listdir(str(outside)) == []


def test_root_swap_during_requeue_halts_the_iteration(tmp_path, monkeypatch):
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture = _state_root_in_review(tmp_path / "root")
    state_root = fixture["state_root"]
    outside = _outside(tmp_path)
    real_requeue = coordinator.requeue_revise

    def requeue_then_swap(*args, **kwargs):
        result = real_requeue(*args, **kwargs)
        _swap_root(state_root, outside)
        return result

    monkeypatch.setattr(coordinator, "requeue_revise", requeue_then_swap)
    with pytest.raises(StateRootMoved):
        coordinator.run_once(state_root, COORD_ID, RUN_ID, _context(), "2026-08-10T02:00:00Z")
    assert os.listdir(str(outside)) == []


def _two_packets_in_review(tmp_path):
    """pkt-a and pkt-b both resting in REVIEW with verdicts deposited."""
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.store import read_journal
    fixture = _state_root_in_review(tmp_path / "root", packet_id="pkt-a")
    state_root = fixture["state_root"]
    second = _packet("pkt-b")
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, "2026-08-10T01:15:00Z", [second])
    events, torn = read_journal(os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID)
    assert torn is None
    other = _drive_to_review(state_root, events, second,
                             started_at="2026-08-10T01:21:00Z",
                             recorded_at="2026-08-10T01:25:00Z",
                             finished_at="2026-08-10T01:26:00Z")
    _deposit(state_root, "pkt-a", 1, _verdict(fixture["packet"], fixture["worker_result"]))
    second_verdict = _verdict(other["packet"], other["worker_result"])
    second_verdict["reviewed_at"] = "2026-08-10T01:30:00Z"
    _deposit(state_root, "pkt-b", 1, _rehash_verdict(second_verdict))
    other["dependency"] = fixture
    return other


def test_review_batch_shares_one_handle_and_halts_on_a_mid_batch_root_swap(tmp_path, monkeypatch):
    import harness_coordinator.v1.review as review
    from harness_coordinator.v1.recovery import _fold_journal
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    batch = _two_packets_in_review(tmp_path)
    state_root = batch["state_root"]
    outside = _outside(tmp_path)

    real_resolve = review.resolve_review
    seen = []
    handles = []

    def recording_resolve(*args, **kwargs):
        seen.append(kwargs.get("packet_id") or args[4])
        handles.append(kwargs.get("handle"))
        result = real_resolve(*args, **kwargs)
        if len(seen) == 1:
            _swap_root(state_root, outside)
        return result

    monkeypatch.setattr(review, "resolve_review", recording_resolve)
    folded, _ = _fold_journal(state_root, batch["events"])
    with pytest.raises(StateRootMoved):
        review.resolve_pending_reviews(state_root, STATE_ROOT_ID, batch["events"], folded,
                                       COORD_ID, RUN_ID, _context(), "2026-08-10T01:35:00Z")
    assert seen == ["pkt-a"], f"packet two must never be processed after the swap, saw {seen}"
    assert handles and all(h is not None for h in handles), "the batch must supply one shared handle"
    assert os.listdir(str(outside)) == []


def test_review_batch_opens_exactly_one_state_root_handle(tmp_path, monkeypatch):
    import harness_coordinator.v1.review as review
    import harness_coordinator.v1.seals_runtime as seals
    from harness_coordinator.v1.recovery import _fold_journal
    batch = _two_packets_in_review(tmp_path)
    opens = []
    real_open = seals.open_state_root

    def counting_open(path):
        opens.append(path)
        return real_open(path)

    monkeypatch.setattr(review, "open_state_root", counting_open)
    folded, _ = _fold_journal(batch["state_root"], batch["events"])
    outcomes = review.resolve_pending_reviews(batch["state_root"], STATE_ROOT_ID, batch["events"],
                                              folded, COORD_ID, RUN_ID, _context(),
                                              "2026-08-10T01:35:00Z")[1]
    assert sorted(o["packet_id"] for o in outcomes) == ["pkt-a", "pkt-b"]
    assert len(opens) == 1, f"the batch must pin exactly one root, opened {len(opens)}"


def test_post_append_swap_halts_before_any_ownership_cleanup(tmp_path, monkeypatch):
    """A post-append swap must stop before cleanup, not merely fail during it.

    A later guard inside the queue projection would also raise, so asserting
    only "it raises" leaves the post-append guard untested. Recording whether
    ownership cleanup was even attempted pins the halt to its stated position.
    """
    import harness_coordinator.v1.review as review
    from harness_coordinator.v1.seals_runtime import StateRootMoved
    fixture, outside = _accepted_fixture_with_verdict(tmp_path)
    state_root = fixture["state_root"]
    real_append = review.append_journal
    release_calls = []

    def append_then_swap(*args, **kwargs):
        real_append(*args, **kwargs)
        _swap_root(state_root, outside)

    real_release = review._release_ownership

    def recording_release(*args, **kwargs):
        release_calls.append(True)
        return real_release(*args, **kwargs)

    monkeypatch.setattr(review, "append_journal", append_then_swap)
    monkeypatch.setattr(review, "_release_ownership", recording_release)
    with pytest.raises(StateRootMoved):
        _resolve(fixture)
    assert release_calls == [], "cleanup must not be attempted against a replacement root"
    assert os.listdir(str(outside)) == []


def test_swap_between_promotion_and_requeue_halts_before_requeue_runs(tmp_path, monkeypatch):
    """The window promotion's own post-check cannot cover.

    Promotion appends, the fold is recomputed, and only then does requeue run.
    Swapping the root inside that recompute is caught solely by the guard
    immediately before requeue.
    """
    import harness_coordinator.v1.coordinator as coordinator
    from harness_coordinator.v1.enroll import enroll_packets
    from harness_coordinator.v1.seals_runtime import StateRootMoved, complete_terminal_seals

    fixture = _state_root_in_review(tmp_path / "root", packet_id="pkt-dep")
    state_root = fixture["state_root"]
    _deposit(state_root, "pkt-dep", 1, _verdict(fixture["packet"], fixture["worker_result"]))
    assert _resolve(fixture)["status"] == "recorded"
    complete_terminal_seals(state_root, fixture["events"], _fold(fixture), T_NOW)
    enroll_packets(state_root, STATE_ROOT_ID, COORD_ID, RUN_ID, "2026-08-10T01:15:00Z",
                   [_packet("pkt-child", dependencies=["pkt-dep"])])
    outside = _outside(tmp_path)

    real_promote = coordinator.promote_dependencies
    real_fold = coordinator._fold_journal
    promoted = []
    requeue_calls = []

    def promote_then_mark(*args, **kwargs):
        result = real_promote(*args, **kwargs)
        promoted.append(True)
        return result

    def fold_and_swap_after_promotion(*args, **kwargs):
        result = real_fold(*args, **kwargs)
        if promoted and not requeue_calls:
            _swap_root(state_root, outside)
            promoted.clear()
        return result

    real_requeue = coordinator.requeue_revise

    def recording_requeue(*args, **kwargs):
        requeue_calls.append(True)
        return real_requeue(*args, **kwargs)

    monkeypatch.setattr(coordinator, "promote_dependencies", promote_then_mark)
    monkeypatch.setattr(coordinator, "_fold_journal", fold_and_swap_after_promotion)
    monkeypatch.setattr(coordinator, "requeue_revise", recording_requeue)
    with pytest.raises(StateRootMoved):
        coordinator.run_once(state_root, COORD_ID, RUN_ID, _context(), "2026-08-10T02:00:00Z")
    assert requeue_calls == [], "requeue must not run against a replacement root"
    assert os.listdir(str(outside)) == []


def test_publish_exclusive_refuses_an_ancestor_symlinked_state_root(tmp_path):
    """The exported convenience wrapper must be exactly as safe as the handle.

    ``O_NOFOLLOW`` on a whole path only constrains its final component, so a
    state root reached through a symlinked ancestor is followed unless the
    chain is walked component-by-component. Nothing may be created through
    either the link or the real path.
    """
    from harness_coordinator.v1.seals_runtime import publish_exclusive
    real = tmp_path / "real"
    (real / "root").mkdir(parents=True)
    link = tmp_path / "link"
    os.symlink(str(real), str(link))
    with pytest.raises(OSError):
        publish_exclusive(str(link / "root"), _PARTS, b'{"v":1}')
    assert list((real / "root").iterdir()) == [], "no artifact may be created via a symlinked ancestor"
    assert not (real / "root" / "artifacts").exists()
