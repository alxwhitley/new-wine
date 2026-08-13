"""O5 authenticated execution-plan contract and durable binding tests."""

import copy
import json
import os

import pytest

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256


T_NOW = "2026-08-11T00:00:00Z"
COORDINATOR_ID = "coord-o5"
RUN_ID = "run-o5"
STATE_ROOT_ID = "state-root-o5"


def _rehash(plan):
    plan["plan_sha256"] = compute_sha256(
        canonical_bytes(plan, omit={"plan_sha256"})
    )
    return plan


def _valid_plan(plan_id="plan-o5"):
    plan = {
        "schema_version": 1,
        "plan_id": plan_id,
        "plan_sha256": "",
        "packets": [
            {
                "packet_id": "packet-1",
                "packet_sha256": "a" * 64,
                "dependencies": [],
                "capability_class": "implementation",
                "budgets": {
                    "attempt_limit": 2,
                    "retry_limit": 1,
                    "revision_limit": 1,
                    "turn_limit": 12,
                    "command_timeout_seconds": 60,
                    "output_bytes": 4096,
                },
            },
            {
                "packet_id": "packet-2",
                "packet_sha256": "b" * 64,
                "dependencies": ["packet-1"],
                "capability_class": "independent_review",
                "budgets": {
                    "attempt_limit": 1,
                    "retry_limit": 0,
                    "revision_limit": 0,
                    "turn_limit": 8,
                    "command_timeout_seconds": 60,
                    "output_bytes": 4096,
                },
            },
        ],
        "routes": {
            "design_judgment": [
                {
                    "route_id": "design-fable",
                    "provider": "anthropic",
                    "model_id": "claude-fable-5",
                    "minimum_reasoning": "max",
                    "enabled": True,
                    "qualification_id": "qual-design-fable",
                    "fallback_to": "design-sol",
                },
                {
                    "route_id": "design-sol",
                    "provider": "openai",
                    "model_id": "gpt-5.6-sol",
                    "minimum_reasoning": "max",
                    "enabled": False,
                    "qualification_id": "qual-design-sol",
                    "fallback_to": None,
                },
            ],
            "implementation": [
                {
                    "route_id": "implementation-primary",
                    "provider": "opencode",
                    "model_id": "kimi-k2.7-code",
                    "minimum_reasoning": "high",
                    "enabled": True,
                    "qualification_id": "qual-implementation-primary",
                    "fallback_to": "implementation-terra",
                },
                {
                    "route_id": "implementation-terra",
                    "provider": "openai",
                    "model_id": "gpt-5.6-terra",
                    "minimum_reasoning": "high",
                    "enabled": True,
                    "qualification_id": "qual-implementation-terra",
                    "fallback_to": None,
                },
            ],
            "independent_review": [
                {
                    "route_id": "review-sol",
                    "provider": "openai",
                    "model_id": "gpt-5.6-sol",
                    "minimum_reasoning": "xhigh",
                    "enabled": True,
                    "qualification_id": "qual-review-sol",
                    "fallback_to": None,
                },
            ],
        },
        "provider_backoff": {
            "max_retries": 3,
            "base_delay_seconds": 30,
            "max_delay_seconds": 300,
        },
        "wall_clock_safety_seconds": 3600,
        "human_stop_categories": [
            "production_database_write",
            "deployment",
            "destructive_filesystem_git",
            "governed_content",
            "licensing_determination",
            "real_provider_commissioning",
            "material_plan_expansion",
        ],
    }
    return _rehash(plan)


def _mutated_plan(mutation):
    plan = _valid_plan()
    if mutation == "boolean_budget":
        plan["packets"][0]["budgets"]["attempt_limit"] = True
    elif mutation == "duplicate_packet":
        plan["packets"].append(copy.deepcopy(plan["packets"][0]))
    elif mutation == "dependency_outside_plan":
        plan["packets"][0]["dependencies"] = ["outside-plan"]
    elif mutation == "fallback_cycle":
        plan["routes"]["implementation"][1]["fallback_to"] = "implementation-primary"
    elif mutation == "enabled_unqualified_model":
        plan["routes"]["implementation"][0]["qualification_id"] = ""
    elif mutation == "design_sol_enabled":
        plan["routes"]["design_judgment"][1]["enabled"] = True
    elif mutation == "design_third_model_enabled":
        plan["routes"]["design_judgment"][1]["model_id"] = "gpt-5.6-terra"
        plan["routes"]["design_judgment"][1]["enabled"] = True
    elif mutation == "noncanonical_model_id":
        plan["routes"]["implementation"][0]["model_id"] = "GPT-5.6-Terra"
    elif mutation == "zero_wall_clock":
        plan["wall_clock_safety_seconds"] = 0
    else:
        raise AssertionError("unknown mutation: %s" % mutation)
    return _rehash(plan)


def _write_manifest(handle):
    manifest = {
        "schema_version": 1,
        "state_root_id": STATE_ROOT_ID,
        "created_at": T_NOW,
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
        "manifest_sha256": "",
    }
    manifest["manifest_sha256"] = compute_sha256(
        canonical_bytes(manifest, omit={"manifest_sha256"})
    )
    handle.publish(("MANIFEST.json",), canonical_bytes(manifest))


def _bound_state(tmp_path, plan):
    from harness_contracts.v1.execution_plan import bind_execution_plan
    from harness_coordinator.v1.seals_runtime import open_state_root

    state_root = os.path.realpath(str(tmp_path / "state"))
    os.makedirs(state_root)
    handle = open_state_root(state_root)
    _write_manifest(handle)
    bound = bind_execution_plan(
        handle, canonical_bytes(plan), COORDINATOR_ID, RUN_ID, T_NOW
    )
    return state_root, handle, bound


def _packet_artifact(packet_id):
    packet = {
        "schema_version": 1,
        "packet_id": packet_id,
        "objective": "O5 packet artifact fixture",
        "dependency_ids": [],
        "lane": "kimi_implementation",
        "assigned_worker": {
            "worker_id": "kimi-1",
            "provider": "opencode",
            "model": "kimi-k2.7-code",
        },
        "starting_revision": "a" * 40,
        "worktree": {"path": "/tmp/o5-worktree", "branch": "codex/o5"},
        "writable_paths": ["scripts/o5.py"],
        "forbidden_surfaces": ["backend/app/services/answer_toolbox.py"],
        "required_context": [{"path": "HARNESS.md", "sha256": "b" * 64}],
        "premise_checks": [{"check_id": "c1", "command_id": "v1", "expected": "present"}],
        "acceptance_criteria": [{
            "criterion_id": "a1", "statement": "works", "required_evidence_ids": ["e1"],
        }],
        "verification_commands": [{
            "command_id": "v1", "argv": ["python3", "-m", "pytest"], "cwd": ".",
            "timeout_seconds": 60, "expected_exit_code": 0,
            "expected_evidence_ids": ["e1"],
        }],
        "budgets": {
            "max_turns": 2, "wall_clock_seconds": 120, "retry_limit": 1,
            "max_output_bytes": 4096, "cost_class": "low", "allowance_limit": 1,
        },
        "network_policy": "denied",
        "checkpoint_artifacts": [{
            "artifact_id": "artifact-1", "path": "scripts/o5.py",
            "required_for_fallback": True,
        }],
        "rollback": {"method": "status", "allowed_commands": [{"argv": ["git", "status"], "cwd": "."}]},
        "human_stop_conditions": ["governed_doc_touched"],
        "sonnet_reassignment_allowed": True,
        "created_by": {"role": "opus_judgment", "session_id": "session-1", "model": "claude-opus-5"},
        "packet_sha256": "",
    }
    packet["packet_sha256"] = compute_sha256(
        canonical_bytes(packet, omit={"packet_sha256"})
    )
    return packet


def _payload(**overrides):
    payload = {
        "packet": None, "attempt": None, "artifacts": [], "classification": None,
        "transition_detail": None, "recovery": None, "run": None, "report": None,
        "execution_plan": None,
    }
    payload.update(overrides)
    return payload


def _aligned_plan_and_artifact(plan_id="plan-o5", packet_id="packet-1"):
    """A plan whose first member digest matches a real publishable artifact."""
    artifact = _packet_artifact(packet_id)
    plan = _valid_plan(plan_id)
    plan["packets"][0]["packet_sha256"] = artifact["packet_sha256"]
    return _rehash(plan), artifact


def _state_root_with_plan_artifacts(tmp_path, plan, artifact):
    """A concrete state root holding both authenticated immutable artifacts."""
    from harness_coordinator.v1.seals_runtime import open_state_root

    state_root = os.path.realpath(str(tmp_path / "state"))
    os.makedirs(state_root)
    handle = open_state_root(state_root)
    _write_manifest(handle)
    handle.publish(("plans", "%s.json" % plan["plan_id"]), canonical_bytes(plan))
    handle.publish(
        ("packets", "%s.json" % artifact["packet_id"]), canonical_bytes(artifact)
    )
    return state_root, handle


def _bound_event(seq, previous, plan):
    from harness_coordinator.v1.recovery import _make_event

    return _make_event(
        seq, "EXECUTION_PLAN_BOUND", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
        previous, T_NOW, payload=_payload(execution_plan={
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "plan_path": "plans/%s.json" % plan["plan_id"],
            "packet_count": len(plan["packets"]),
        }),
    )


def _enrolled_event(seq, previous, packet_sha256, packet_id="packet-1"):
    from harness_coordinator.v1.recovery import _make_event

    return _make_event(
        seq, "PACKET_ENROLLED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, previous,
        T_NOW, packet_id=packet_id, intent_id="enroll-%s" % packet_id,
        to_state="READY", cause="enrollment", payload=_payload(packet={
            "packet_sha256": packet_sha256,
            "packet_path": "packets/%s.json" % packet_id,
            "lane": "kimi_implementation",
            "dependency_ids": [],
            "sonnet_reassignment_allowed": False,
            "retry_limit": 1,
            "enqueue_seq": seq,
        }),
    )


def _attempt_started_event(seq, previous, packet_id="packet-1"):
    from harness_coordinator.v1.recovery import _make_event

    return _make_event(
        seq, "ATTEMPT_STARTED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, previous,
        T_NOW, packet_id=packet_id, intent_id="attempt-%s-1" % packet_id,
        from_state="READY", to_state="RUNNING", cause="claim_committed",
        payload=_payload(attempt={
            "attempt": 1, "lane": "kimi_implementation",
            "worker": {
                "worker_id": "w1", "session_id": "s1",
                "provider": "opencode", "model": "kimi-k2.7-code",
            },
            "claim_sha256": None, "worktree_path": None,
        }),
    )


def _run_started_event(seq=1, previous=None):
    from harness_coordinator.v1.recovery import _make_event

    return _make_event(
        seq, "RUN_STARTED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID, previous, T_NOW,
        payload=_payload(run={
            "coordinator": {
                "coordinator_id": COORDINATOR_ID, "boot_id": "boot-1",
                "hostname": "host-1", "pid": 1,
            },
            "trust_roots": {
                "reviewer_sessions_path": "x", "reviewer_sessions_sha256": "0" * 64,
                "provider_signals_path": "y", "provider_signals_sha256": "0" * 64,
            },
            "contract_versions": {
                "packet": 1, "worker_result": 1, "verdict": 1, "replay": 1,
                "journal": 1, "queue": 1, "claim": 1, "attempt_outcome": 1,
                "provider_evidence": 1, "reassignment": 1, "reconciliation": 1,
            },
            "end_reason": None, "end_detail": None, "disabled_lanes": [],
        }),
    )


def _ordered_plan_journal(plan, order, packet_sha256, packet_id="packet-1"):
    """Build a two-event journal in either binding order.

    The ``PLAN_IDENTITY_LATE_BIND`` guard permits enrolment before binding, so
    both orders are real, reachable shapes that must behave identically.
    """
    if order == "bind_then_enroll":
        bound = _bound_event(1, None, plan)
        return [bound, _enrolled_event(2, bound, packet_sha256, packet_id)]
    enrolled = _enrolled_event(1, None, packet_sha256, packet_id)
    return [enrolled, _bound_event(2, enrolled, plan)]


BIND_ORDERS = ["bind_then_enroll", "enroll_then_bind"]


def test_execution_plan_is_closed_canonical_and_hash_bound():
    from harness_contracts.v1.execution_plan import (
        execution_plan_sha256,
        validate_execution_plan,
    )

    plan = _valid_plan()
    assert validate_execution_plan(plan)["valid"] is True
    assert plan["plan_sha256"] == execution_plan_sha256(plan)
    extra = copy.deepcopy(plan)
    extra["unexpected"] = True
    assert validate_execution_plan(extra)["errors"][0]["code"] == "UNKNOWN_PROPERTY"


def test_execution_plan_schema_is_closed_and_matches_root_contract():
    from harness_contracts.v1.execution_plan import CAPABILITY_CLASSES, REQUIRED

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    schema_path = os.path.join(
        repo_root, "schemas", "harness", "v1", "execution-plan.schema.json"
    )
    with open(schema_path, "r", encoding="utf-8") as schema_file:
        schema = json.load(schema_file)

    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == REQUIRED
    assert set(schema["properties"]["routes"]["properties"]) == CAPABILITY_CLASSES


# Deliberate deviation from the plan's Task 1 Step 1 list of nine mutations:
# ``packet_digest_mismatch`` is deliberately absent here.  It cannot be
# expressed against the standalone validator, which by contract never reads an
# external artifact -- a plan's ``packet_sha256`` has nothing to disagree WITH
# until the real packet artifact is present.  It is covered at the recovery
# boundary instead, where those bytes exist, by
# ``test_recovery_rejects_packet_digest_disagreement_with_authenticated_artifact``
# and ``test_plan_scope_rejects_digest_drift_in_either_bind_order``.
# ``design_third_model_enabled`` is added beyond the plan's list to cover the
# design-judgment allowlist (an arbitrary third model, not only Sol).
@pytest.mark.parametrize("mutation", [
    "boolean_budget", "duplicate_packet", "dependency_outside_plan",
    "fallback_cycle", "enabled_unqualified_model", "design_sol_enabled",
    "design_third_model_enabled", "noncanonical_model_id", "zero_wall_clock",
])
def test_execution_plan_rejects_authority_and_identity_bypasses(mutation):
    from harness_contracts.v1.execution_plan import validate_execution_plan

    assert validate_execution_plan(_mutated_plan(mutation))["valid"] is False


@pytest.mark.parametrize(("mutation", "path"), [
    ("design_sol_enabled", "/routes/design_judgment/1/enabled"),
    ("design_third_model_enabled", "/routes/design_judgment/1/model_id"),
])
def test_design_judgment_is_an_allowlist_not_a_single_model_denylist(mutation, path):
    """Only an enabled ``claude-fable-5`` may hold design judgment.

    The named ``gpt-5.6-sol`` prohibition stays legible in its own error, but
    an arbitrary third model is refused by the same closed rule rather than
    validating merely because it was never named.
    """
    from harness_contracts.v1.execution_plan import validate_execution_plan

    result = validate_execution_plan(_mutated_plan(mutation))
    assert result["valid"] is False
    forbidden = [e for e in result["errors"] if e["code"] == "FORBIDDEN_AUTHORITY"]
    assert [e["path"] for e in forbidden] == [path]


def test_disabled_design_candidates_of_any_model_still_validate():
    """The allowlist gates ENABLED authority only; disabled candidates remain."""
    from harness_contracts.v1.execution_plan import validate_execution_plan

    plan = _valid_plan()
    # The disabled Sol candidate the design records, plus a disabled third
    # model, must both survive -- disabling is how a candidate is parked.
    plan["routes"]["design_judgment"].append({
        "route_id": "design-terra",
        "provider": "openai",
        "model_id": "gpt-5.6-terra",
        "minimum_reasoning": "high",
        "enabled": False,
        "qualification_id": "qual-design-terra",
        "fallback_to": None,
    })
    assert validate_execution_plan(_rehash(plan))["valid"] is True


def test_bind_publishes_one_canonical_plan_and_durable_event(tmp_path):
    from harness_coordinator.v1.store import read_journal

    plan = _valid_plan()
    state_root, handle, bound = _bound_state(tmp_path, plan)
    try:
        assert bound == plan
        raw = handle.read(("plans", "%s.json" % plan["plan_id"]))
        assert raw == canonical_bytes(plan)
        events, torn = read_journal(
            os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID
        )
        assert torn is None
        assert len(events) == 1
        event = events[0]
        assert event["event_type"] == "EXECUTION_PLAN_BOUND"
        assert event["payload"]["execution_plan"] == {
            "plan_id": plan["plan_id"],
            "plan_sha256": plan["plan_sha256"],
            "plan_path": "plans/%s.json" % plan["plan_id"],
            "packet_count": 2,
        }
    finally:
        handle.close()


def test_second_different_plan_for_run_is_integrity_error(tmp_path):
    from harness_contracts.v1.execution_plan import bind_execution_plan
    from harness_coordinator.v1.recovery import IntegrityError

    _state_root, handle, _bound = _bound_state(tmp_path, _valid_plan("plan-a"))
    try:
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_CONFLICT"):
            bind_execution_plan(
                handle, canonical_bytes(_valid_plan("plan-b")),
                COORDINATOR_ID, RUN_ID, T_NOW,
            )
    finally:
        handle.close()


def test_rebinding_requires_the_previously_bound_artifact(tmp_path):
    from harness_contracts.v1.execution_plan import bind_execution_plan
    from harness_coordinator.v1.recovery import IntegrityError

    _state_root, handle, bound = _bound_state(tmp_path, _valid_plan())
    try:
        assert handle.unlink(("plans", "%s.json" % bound["plan_id"])) is True
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_ARTIFACT_MISSING"):
            bind_execution_plan(
                handle, canonical_bytes(bound), COORDINATOR_ID, RUN_ID, T_NOW,
            )
    finally:
        handle.close()


def test_binding_rejects_noncanonical_plan_bytes(tmp_path):
    from harness_contracts.v1.execution_plan import bind_execution_plan
    from harness_coordinator.v1.recovery import IntegrityError
    from harness_coordinator.v1.seals_runtime import open_state_root

    state_root = os.path.realpath(str(tmp_path / "state"))
    os.makedirs(state_root)
    handle = open_state_root(state_root)
    _write_manifest(handle)
    try:
        raw = json.dumps(_valid_plan(), indent=2, sort_keys=False).encode("utf-8")
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_NONCANONICAL"):
            bind_execution_plan(handle, raw, COORDINATOR_ID, RUN_ID, T_NOW)
    finally:
        handle.close()


def test_recovery_rejects_missing_or_noncanonical_bound_plan_artifact(tmp_path):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal
    from harness_coordinator.v1.store import read_journal

    state_root, handle, bound = _bound_state(tmp_path, _valid_plan())
    try:
        events, torn = read_journal(
            os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID
        )
        assert torn is None
        assert handle.unlink(("plans", "%s.json" % bound["plan_id"])) is True
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_ARTIFACT_MISSING"):
            _fold_journal(state_root, events)

        noncanonical = json.dumps(bound, indent=2, sort_keys=False).encode("utf-8")
        handle.publish(("plans", "%s.json" % bound["plan_id"]), noncanonical)
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_NONCANONICAL"):
            _fold_journal(state_root, events)
    finally:
        handle.close()


def test_recovery_rejects_plan_artifact_hash_disagreement(tmp_path):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal
    from harness_coordinator.v1.store import read_journal

    state_root, handle, bound = _bound_state(tmp_path, _valid_plan())
    try:
        events, torn = read_journal(
            os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID
        )
        assert torn is None
        changed = copy.deepcopy(bound)
        changed["wall_clock_safety_seconds"] = 7200
        _rehash(changed)
        assert handle.unlink(("plans", "%s.json" % bound["plan_id"])) is True
        handle.publish(("plans", "%s.json" % bound["plan_id"]), canonical_bytes(changed))
        with pytest.raises(IntegrityError, match="PLAN_IDENTITY_CONFLICT"):
            _fold_journal(state_root, events)
    finally:
        handle.close()


def test_recovery_rejects_packet_outside_bound_plan(tmp_path):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, _make_event
    from harness_coordinator.v1.store import read_journal

    state_root, handle, _bound = _bound_state(tmp_path, _valid_plan())
    try:
        events, torn = read_journal(
            os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID
        )
        assert torn is None
        foreign = _make_event(
            2, "PACKET_ENROLLED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            events[0], T_NOW, packet_id="foreign-packet", intent_id="enroll-foreign",
            to_state="READY", cause="enrollment", payload={
                "packet": {
                    "packet_sha256": "c" * 64,
                    "packet_path": "packets/foreign-packet.json",
                    "lane": "kimi_implementation",
                    "dependency_ids": [],
                    "sonnet_reassignment_allowed": True,
                    "retry_limit": 1,
                    "enqueue_seq": 2,
                },
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
                "execution_plan": None,
            },
        )
        with pytest.raises(IntegrityError, match="PLAN_SCOPE_PACKET_OUTSIDE_PLAN"):
            _fold_journal(state_root, [events[0], foreign])
    finally:
        handle.close()


def test_recovery_rejects_packet_digest_disagreement_with_authenticated_artifact(tmp_path):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, _make_event
    from harness_coordinator.v1.store import read_journal

    plan = _valid_plan()
    state_root, handle, _bound = _bound_state(tmp_path, plan)
    try:
        artifact = _packet_artifact("packet-1")
        handle.publish(("packets", "packet-1.json"), canonical_bytes(artifact))
        events, torn = read_journal(
            os.path.join(state_root, "journal.ndjson"), state_root_id=STATE_ROOT_ID
        )
        assert torn is None
        bound_event = events[0]
        enrolled = _make_event(
            2, "PACKET_ENROLLED", COORDINATOR_ID, RUN_ID, STATE_ROOT_ID,
            bound_event, T_NOW, packet_id="packet-1", intent_id="enroll-packet-1",
            to_state="READY", cause="enrollment", payload={
                "packet": {
                    "packet_sha256": plan["packets"][0]["packet_sha256"],
                    "packet_path": "packets/packet-1.json",
                    "lane": "kimi_implementation",
                    "dependency_ids": [],
                    "sonnet_reassignment_allowed": True,
                    "retry_limit": 1,
                    "enqueue_seq": 2,
                },
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
                "execution_plan": None,
            },
        )
        with pytest.raises(IntegrityError, match="PLAN_SCOPE_PACKET_DIGEST_MISMATCH"):
            _fold_journal(state_root, [bound_event, enrolled])
    finally:
        handle.close()


@pytest.mark.parametrize("order", BIND_ORDERS)
def test_plan_scope_accepts_an_in_plan_packet_in_either_bind_order(tmp_path, order):
    """Enrolment may precede or follow binding; both must fold cleanly.

    The ``PLAN_IDENTITY_LATE_BIND`` guard rejects binding only after an
    ``ATTEMPT_STARTED``, so enrol-then-bind is explicitly permitted -- and the
    retro membership check it triggers must therefore be able to succeed.
    """
    from harness_coordinator.v1.recovery import _fold_journal

    plan, artifact = _aligned_plan_and_artifact()
    state_root, handle = _state_root_with_plan_artifacts(tmp_path, plan, artifact)
    try:
        events = _ordered_plan_journal(plan, order, artifact["packet_sha256"])
        packets, _counters = _fold_journal(state_root, events)
        assert sorted(packets) == ["packet-1"]
        assert packets["packet-1"]["state"] == "READY"
        # Both call sites must supply the same record shape, or the retro
        # check compares a missing key against the canonical path.
        assert packets["packet-1"]["packet_path"] == "packets/packet-1.json"
    finally:
        handle.close()


@pytest.mark.parametrize("order", BIND_ORDERS)
def test_plan_scope_rejects_an_out_of_plan_packet_in_either_bind_order(tmp_path, order):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal

    plan, artifact = _aligned_plan_and_artifact()
    state_root, handle = _state_root_with_plan_artifacts(tmp_path, plan, artifact)
    try:
        foreign = _packet_artifact("foreign-packet")
        handle.publish(("packets", "foreign-packet.json"), canonical_bytes(foreign))
        events = _ordered_plan_journal(
            plan, order, foreign["packet_sha256"], packet_id="foreign-packet")
        with pytest.raises(IntegrityError) as caught:
            _fold_journal(state_root, events)
        assert caught.value.code == "PLAN_SCOPE_PACKET_OUTSIDE_PLAN"
        assert caught.value.packet_id == "foreign-packet"
    finally:
        handle.close()


@pytest.mark.parametrize("order", BIND_ORDERS)
def test_plan_scope_rejects_digest_drift_in_either_bind_order(tmp_path, order):
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal

    plan, artifact = _aligned_plan_and_artifact()
    state_root, handle = _state_root_with_plan_artifacts(tmp_path, plan, artifact)
    try:
        events = _ordered_plan_journal(plan, order, "d" * 64)
        with pytest.raises(IntegrityError) as caught:
            _fold_journal(state_root, events)
        assert caught.value.code == "PLAN_SCOPE_PACKET_DIGEST_MISMATCH"
        assert caught.value.packet_id == "packet-1"
    finally:
        handle.close()


def test_binding_after_an_attempt_claim_is_rejected(tmp_path):
    """A run cannot retroactively acquire a plan once it has already claimed."""
    from harness_coordinator.v1.recovery import IntegrityError, _fold_journal

    plan, artifact = _aligned_plan_and_artifact()
    state_root, handle = _state_root_with_plan_artifacts(tmp_path, plan, artifact)
    try:
        enrolled = _enrolled_event(1, None, artifact["packet_sha256"])
        started = _attempt_started_event(2, enrolled)
        late = _bound_event(3, started, plan)
        with pytest.raises(IntegrityError) as caught:
            _fold_journal(state_root, [enrolled, started, late])
        assert caught.value.code == "PLAN_IDENTITY_LATE_BIND"
    finally:
        handle.close()


def test_plan_bearing_journal_folds_cleanly_through_both_phantom_root_paths(tmp_path):
    """Reconciliation and replay fold against roots that deliberately do not exist.

    ``reconcile`` folds its inventory against ``/dev/null`` and
    ``replay_schedule`` folds every prefix against a path it never creates, so
    an unguarded plan-artifact read would make EVERY O5 run report a
    ``fold_failed`` attention record and a ``FOLD_FAILED_AT_PREFIX``
    divergence.  The final full fold still uses the real state root, so real
    plan authentication is proven to remain in force here too.
    """
    from harness_coordinator.v1.reconcile import build_reconciliation_report
    from harness_coordinator.v1.replay_schedule import replay_schedule

    plan, artifact = _aligned_plan_and_artifact()
    state_root, handle = _state_root_with_plan_artifacts(tmp_path, plan, artifact)
    try:
        run_started = _run_started_event()
        bound = _bound_event(2, run_started, plan)
        enrolled = _enrolled_event(3, bound, artifact["packet_sha256"])
        started = _attempt_started_event(4, enrolled)
        os.makedirs(os.path.join(state_root, "locks"), exist_ok=True)
        with open(os.path.join(state_root, "journal.ndjson"), "wb") as journal:
            for event in (run_started, bound, enrolled, started):
                journal.write(canonical_bytes(event) + b"\n")

        report = build_reconciliation_report(
            state_root, STATE_ROOT_ID, COORDINATOR_ID, RUN_ID, "report-o5", T_NOW)
        assert [
            item for item in report["attention_required"]
            if item.get("code") == "fold_failed"
        ] == []
        assert report["inventory_total"] == 1

        replay = replay_schedule(state_root, STATE_ROOT_ID)
        assert [
            item for item in replay["divergences"]
            if item.get("code") in ("FOLD_FAILED_AT_PREFIX", "FOLD_FAILED")
        ] == []
        assert replay["attempt_started_events_checked"] == 1
        assert replay["replay_passed"] is True
    finally:
        handle.close()


def test_non_plan_event_cannot_carry_an_execution_plan_payload():
    """Only ``EXECUTION_PLAN_BOUND`` may populate ``payload.execution_plan``."""
    from harness_contracts.v1.journal import validate_journal_event

    plan, _artifact = _aligned_plan_and_artifact()
    event = _run_started_event()
    event["payload"]["execution_plan"] = {
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_path": "plans/%s.json" % plan["plan_id"],
        "packet_count": len(plan["packets"]),
    }
    event["event_sha256"] = compute_sha256(canonical_bytes(event, omit={"event_sha256"}))
    result = validate_journal_event(event, None, STATE_ROOT_ID)
    assert result["valid"] is False
    assert [e["path"] for e in result["errors"]] == ["/payload/execution_plan"]


def test_execution_plan_payload_has_runtime_and_json_schema_parity():
    """The runtime validator and the JSON Schema constrain the same shape.

    No JSON Schema evaluator is vendored here, so parity is asserted the way
    the O4 workspace-event parity test does it: exercise the runtime, then
    read back the schema's own declaration for the same condition.
    """
    from harness_contracts.v1.journal import validate_journal_event

    plan, _artifact = _aligned_plan_and_artifact()
    binding = {
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "plan_path": "plans/%s.json" % plan["plan_id"],
        "packet_count": len(plan["packets"]),
    }
    bound = _bound_event(1, None, plan)
    assert validate_journal_event(bound, None, STATE_ROOT_ID)["valid"] is True

    # Runtime: the bound event REQUIRES the object, every other type forbids it.
    stripped = copy.deepcopy(bound)
    stripped["payload"]["execution_plan"] = None
    stripped["event_sha256"] = compute_sha256(
        canonical_bytes(stripped, omit={"event_sha256"}))
    assert validate_journal_event(stripped, None, STATE_ROOT_ID)["valid"] is False

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(
        os.path.join(repo_root, "schemas", "harness", "v1", "journal-event.schema.json"),
        "r", encoding="utf-8",
    ) as schema_file:
        schema = json.load(schema_file)
    conditional = next(
        rule for rule in schema["allOf"]
        if rule["if"]["properties"]["event_type"].get("const") == "EXECUTION_PLAN_BOUND"
    )
    then_payload = conditional["then"]["properties"]["payload"]
    assert then_payload["required"] == ["execution_plan"]
    assert then_payload["properties"]["execution_plan"] == {"type": "object"}
    # Schema parity for the negative case the runtime already enforces above.
    assert (conditional["else"]["properties"]["payload"]["properties"]
            ["execution_plan"]) == {"type": "null"}
    assert binding.keys() == set(
        schema["properties"]["payload"]["properties"]["execution_plan"]["required"])


def test_integrity_error_names_its_code_once_without_doubling_the_message():
    """``str`` carries the code for every code; ``message`` stays raw.

    ``reconcile`` formats ``"{code}: {message}"`` into a durable attention
    record, so a code-prefixed ``message`` would emit the code twice.
    """
    from harness_coordinator.v1.recovery import IntegrityError

    planned = IntegrityError("PLAN_IDENTITY_CONFLICT", "run has conflicting bindings")
    assert str(planned) == "PLAN_IDENTITY_CONFLICT: run has conflicting bindings"
    assert planned.message == "run has conflicting bindings"

    other = IntegrityError("INVALID_TRANSITION", "packet is already terminal")
    assert str(other) == "INVALID_TRANSITION: packet is already terminal"
    assert other.message == "packet is already terminal"
