"""Journal event schema validation for harness contract v1 O3."""

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.claim import CLAIM_CLASSIFICATIONS
from harness_contracts.v1.classification import ATTEMPT_CLASSES
from harness_contracts.v1.errors import PHASE_RANK, error, invalid_result, sort_errors, valid_result
# ``execution_plan`` imports only canonical/packet at module scope (its own
# journal import is function-local, inside ``bind_execution_plan``), so this
# direction is acyclic.  Importing the class vocabulary keeps one definition
# of the capability classes rather than a second hand-kept copy here.
from harness_contracts.v1.execution_plan import CAPABILITY_CLASSES
from harness_contracts.v1.provider_evidence import CAPACITY_STATES, RE_MODEL_ID
from harness_contracts.v1.packet import (
    LANES,
    PACKET_STATES,
    RE_SHA256,
    _matches,
    _normalize_relative_path,
    _PacketValidator,
    is_harness_id,
    is_repo_relative_path,
)
from harness_contracts.v1.transition import VALID_TRANSITIONS, validate_transition
from harness_contracts.v1.verdict import VERDICTS
from harness_contracts.v1.worker_result import RE_RFC3339, WORKER_OUTCOMES


JOURNAL_EVENT_TYPES = {
    "RUN_STARTED",
    "RUN_ENDED",
    "PACKET_ENROLLED",
    "STATE_TRANSITION",
    "ATTEMPT_STARTED",
    "WORKER_RESULT_RECORDED",
    "ATTEMPT_FINISHED",
    "VERDICT_RECORDED",
    "INTENT_ABANDONED",
    "LOCK_RECLAIMED",
    "JOURNAL_TAIL_TRUNCATED",
    "RECONCILIATION_EMITTED",
    "WORKSPACE_BASELINE_RECORDED",
    "WORKSPACE_POSTFLIGHT_RECORDED",
    "INTEGRATION_MANIFEST_RECORDED",
    "EXECUTION_PLAN_BOUND",
    "PROVIDER_CAPACITY_RECORDED",
    "PROVIDER_BACKOFF_SCHEDULED",
    "MODEL_FALLBACK_SELECTED",
    "PACKET_PAUSED",
    "GRACEFUL_STOP_REQUESTED",
    "GRACEFUL_STOP_EFFECTIVE",
}

# A graceful run stop is a decision about the whole run, not about one packet:
# the active attempt may finish, but no later packet may be claimed.
GRACEFUL_STOP_EVENT_TYPES = {
    "GRACEFUL_STOP_REQUESTED",
    "GRACEFUL_STOP_EFFECTIVE",
}

# O5 stop-reason vocabulary, from the approved design's stable families.  It
# is closed: an unknown reason code fails validation here and in the JSON
# Schema, so no ad hoc reason string can reach a durable event.
BUDGET_REASON_CODES = {
    # PACKET_BUDGET_* -- plan limits, derived from the journal before a claim.
    "PACKET_BUDGET_ATTEMPTS_EXHAUSTED",
    "PACKET_BUDGET_RETRIES_EXHAUSTED",
    "PACKET_BUDGET_REVISIONS_EXHAUSTED",
    # PROVIDER_ALLOWANCE_* -- observed subscription capacity, never spend.
    "PROVIDER_ALLOWANCE_EXHAUSTED",
    "PROVIDER_ALLOWANCE_UNAVAILABLE",
    "PROVIDER_ALLOWANCE_RESET_PENDING",
    # PROVIDER_BACKOFF_* -- the plan's bounded, finite retry schedule.
    "PROVIDER_BACKOFF_PENDING",
    "PROVIDER_BACKOFF_RETRIES_EXHAUSTED",
    # Immediate process-safety limits.  These terminate a process group; see
    # IMMEDIATE_STOP_REASON_CODES below for why they are never graceful.
    "COMMAND_TIMEOUT",
    "OUTPUT_LIMIT_EXCEEDED",
    # The plan's run-level wall-clock backstop against an abandoned run.
    "QUEUE_SAFETY_CEILING_REACHED",
    # MODEL_ROUTE_* -- plan-pinned routing outcomes and refusals.
    "MODEL_ROUTE_SELECTED",
    "MODEL_ROUTE_FALLBACK_SELECTED",
    "MODEL_ROUTE_DISABLED",
    "MODEL_ROUTE_UNQUALIFIED",
    "MODEL_ROUTE_NOT_IN_PLAN",
    "MODEL_ROUTE_CROSS_CLASS_FALLBACK",
    "MODEL_ROUTE_FALLBACK_CYCLE",
    "MODEL_ROUTE_REVIEWER_IDENTITY_CONFLICT",
    # Terminal families shared with the wider stop vocabulary.
    "NO_CAPABLE_MODEL_AVAILABLE",
    "HUMAN_AUTHORITY_REQUIRED",
    "BUDGET_EVIDENCE_INVALID",
    "PLAN_SCOPE_PACKET_OUTSIDE_PLAN",
    "PLAN_SCOPE_PACKET_DIGEST_MISMATCH",
}

# Immediate process-safety limits terminate the worker's process group
# because letting it finish would defeat the safety boundary.  They are NOT
# graceful plan stops, and the two vocabularies below are disjoint on purpose:
# a timeout or an output flood structurally cannot be recorded as a graceful
# run stop, so no caller can quietly relabel a containment failure as an
# orderly end to the plan.
IMMEDIATE_STOP_REASON_CODES = {
    "COMMAND_TIMEOUT",
    "OUTPUT_LIMIT_EXCEEDED",
}

# The reason codes a capacity-family payload may carry -- PACKET_PAUSED,
# PROVIDER_BACKOFF_SCHEDULED, MODEL_FALLBACK_SELECTED.  The immediate codes
# are SUBTRACTED for the same reason the graceful vocabulary excludes them,
# one surface over: those three events describe a bounded, resumable capacity
# condition, and a reconciliation that partitions PACKET_PAUSED as a capacity
# pause would silently count a containment failure as capacity if a timeout
# or an output flood could ride on one.
CAPACITY_EVENT_REASON_CODES = BUDGET_REASON_CODES - IMMEDIATE_STOP_REASON_CODES

# The only reason codes a graceful stop event may carry: the plan's
# wall-clock backstop and authenticated provider-capacity exhaustion.
GRACEFUL_STOP_REASON_CODES = {
    "QUEUE_SAFETY_CEILING_REACHED",
    "PROVIDER_ALLOWANCE_EXHAUSTED",
    "PROVIDER_ALLOWANCE_UNAVAILABLE",
    "PROVIDER_ALLOWANCE_RESET_PENDING",
    "PROVIDER_BACKOFF_RETRIES_EXHAUSTED",
}

# Each O5 budget event carries exactly one closed payload object, under its
# own payload key.  Every other event type must leave that key null/absent.
BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE = {
    "PROVIDER_CAPACITY_RECORDED": "provider_capacity",
    "PROVIDER_BACKOFF_SCHEDULED": "provider_backoff",
    "MODEL_FALLBACK_SELECTED": "model_fallback",
    "PACKET_PAUSED": "packet_pause",
    "GRACEFUL_STOP_REQUESTED": "graceful_stop_request",
    "GRACEFUL_STOP_EFFECTIVE": "graceful_stop_effective",
}

BUDGET_PAYLOAD_KEYS = frozenset(BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE.values())

# Provider capacity and its backoff schedule are provider-scoped facts, not
# packet-scoped ones; fallback selection and pause are decisions about one
# packet and carry its id.
PROVIDER_SCOPED_EVENT_TYPES = {
    "PROVIDER_CAPACITY_RECORDED",
    "PROVIDER_BACKOFF_SCHEDULED",
}

TRANSITION_CAUSES = {
    "enrollment",
    "dependencies_satisfied",
    "revision_requeued",
    "claim_committed",
    "infra_retry",
    "provider_exhausted_reassignment",
    "result_recorded",
    "contract_invalid",
    "authority_violation",
    "attempt_budget_exhausted",
    "fallback_not_permitted",
    "fallback_exhausted",
    "exhaustion_unconfirmed",
    "authority_hard_stop",
    "worker_human_required",
    "evidence_tampering",
    "verdict_accept",
    "verdict_revise",
    "verdict_quarantine",
    "verdict_human_required",
    "none",
}

# Pinned edge table: every cause maps to the (from_state, to_state) edges it may drive.
CAUSE_EDGES: Dict[str, Set[Tuple[Optional[str], Optional[str]]]] = {
    "enrollment": {(None, "BLOCKED"), (None, "READY")},
    "dependencies_satisfied": {("BLOCKED", "READY")},
    "revision_requeued": {("REVISE", "READY")},
    "claim_committed": {("READY", "RUNNING")},
    "infra_retry": {("RUNNING", "READY")},
    "provider_exhausted_reassignment": {("RUNNING", "READY")},
    "result_recorded": {("RUNNING", "REVIEW")},
    "contract_invalid": {("RUNNING", "QUARANTINED")},
    "authority_violation": {("RUNNING", "QUARANTINED")},
    "attempt_budget_exhausted": {("RUNNING", "QUARANTINED")},
    "fallback_not_permitted": {("RUNNING", "QUARANTINED")},
    "fallback_exhausted": {("RUNNING", "QUARANTINED")},
    "exhaustion_unconfirmed": {("RUNNING", "QUARANTINED")},
    "authority_hard_stop": {("RUNNING", "HUMAN_REQUIRED")},
    "worker_human_required": {("RUNNING", "HUMAN_REQUIRED")},
    "evidence_tampering": {("RUNNING", "HUMAN_REQUIRED")},
    "verdict_accept": {("REVIEW", "ACCEPTED")},
    "verdict_revise": {("REVIEW", "REVISE")},
    "verdict_quarantine": {("REVIEW", "QUARANTINED")},
    "verdict_human_required": {("REVIEW", "HUMAN_REQUIRED")},
    "none": {(None, None)},
}

# Which causes may appear on each event type.
CAUSES_BY_EVENT_TYPE: Dict[str, Set[str]] = {
    "RUN_STARTED": {"none"},
    "RUN_ENDED": {"none"},
    "PACKET_ENROLLED": {"enrollment"},
    "STATE_TRANSITION": {"dependencies_satisfied", "revision_requeued"},
    "ATTEMPT_STARTED": {"claim_committed"},
    "WORKER_RESULT_RECORDED": {"none"},
    "ATTEMPT_FINISHED": {
        "infra_retry",
        "provider_exhausted_reassignment",
        "result_recorded",
        "contract_invalid",
        "authority_violation",
        "attempt_budget_exhausted",
        "fallback_not_permitted",
        "fallback_exhausted",
        "exhaustion_unconfirmed",
        "authority_hard_stop",
        "worker_human_required",
        "evidence_tampering",
    },
    "VERDICT_RECORDED": {
        "verdict_accept",
        "verdict_revise",
        "verdict_quarantine",
        "verdict_human_required",
    },
    "INTENT_ABANDONED": {"none"},
    "LOCK_RECLAIMED": {"none"},
    "JOURNAL_TAIL_TRUNCATED": {"none"},
    "RECONCILIATION_EMITTED": {"none"},
    "WORKSPACE_BASELINE_RECORDED": {"none"},
    "WORKSPACE_POSTFLIGHT_RECORDED": {"none"},
    "INTEGRATION_MANIFEST_RECORDED": {"none"},
    "EXECUTION_PLAN_BOUND": {"none"},
    "PROVIDER_CAPACITY_RECORDED": {"none"},
    "PROVIDER_BACKOFF_SCHEDULED": {"none"},
    "MODEL_FALLBACK_SELECTED": {"none"},
    "PACKET_PAUSED": {"none"},
    "GRACEFUL_STOP_REQUESTED": {"none"},
    "GRACEFUL_STOP_EFFECTIVE": {"none"},
}

# Payload sub-objects that must be non-null for each event type.
PAYLOAD_NON_NULL_BY_TYPE: Dict[str, Set[str]] = {
    "RUN_STARTED": {"run"},
    "RUN_ENDED": {"run"},
    "PACKET_ENROLLED": {"packet"},
    "STATE_TRANSITION": {"transition_detail"},
    "ATTEMPT_STARTED": {"attempt"},
    "WORKER_RESULT_RECORDED": {"attempt"},
    "ATTEMPT_FINISHED": {"attempt", "classification"},
    "VERDICT_RECORDED": {"attempt"},
    "INTENT_ABANDONED": {"recovery"},
    "LOCK_RECLAIMED": {"recovery"},
    "JOURNAL_TAIL_TRUNCATED": {"recovery"},
    "RECONCILIATION_EMITTED": {"report"},
    "WORKSPACE_BASELINE_RECORDED": set(),
    "WORKSPACE_POSTFLIGHT_RECORDED": set(),
    "INTEGRATION_MANIFEST_RECORDED": set(),
    "EXECUTION_PLAN_BOUND": {"execution_plan"},
    "PROVIDER_CAPACITY_RECORDED": set(),
    "PROVIDER_BACKOFF_SCHEDULED": set(),
    "MODEL_FALLBACK_SELECTED": set(),
    "PACKET_PAUSED": set(),
    "GRACEFUL_STOP_REQUESTED": set(),
    "GRACEFUL_STOP_EFFECTIVE": set(),
}

ARTIFACT_KINDS = {
    "worker_result",
    "worker_result_invalid",
    "opus_verdict",
    "replay_bundle",
    "attempt_outcome",
    "provider_evidence",
    "reassignment_record",
    "terminal_seal",
    "reconciliation_report",
    "journal_tail",
    "stdout",
    "stderr",
    "workspace_baseline",
    "workspace_postflight",
    "workspace_integration",
}

STAGES = {
    "enrollment",
    "claim",
    "result_record",
    "attempt_finish",
    "review_claim",
    "verdict_record",
    "promotion",
}

RUN_END_REASONS = {
    "normal",
    "no_eligible_work",
    "budget_stop",
    "repeated_claim_abandonment",
    "fatal_integrity_error",
    "operator_stop",
}

ABANDONED_STAGES = {
    "lock_acquired",
    "queue_intent_written",
    "worker_launch_failed",
    "review_invocation_failed",
}

ZERO_SHA256 = "0" * 64


def _check_int(
    v: _PacketValidator,
    value: Any,
    path: str,
    min_value: Optional[int] = None,
    positive: bool = False,
    nonneg: bool = False,
) -> bool:
    if isinstance(value, bool):
        v.add("INVALID_TYPE", path, "Expected integer, not boolean", phase="scalar")
        return False
    if not isinstance(value, int):
        v.add("INVALID_TYPE", path, "Expected integer", phase="scalar")
        return False
    if positive and value <= 0:
        v.add("INVALID_VALUE", path, "Must be a positive integer", phase="value")
        return False
    if nonneg and value < 0:
        v.add("INVALID_VALUE", path, "Must be a non-negative integer", phase="value")
        return False
    if min_value is not None and value < min_value:
        v.add("INVALID_VALUE", path, f"Must be >= {min_value}", phase="value")
        return False
    return True


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
        return False
    return True


def _check_non_empty_string(v: _PacketValidator, value: Any, path: str) -> bool:
    if not isinstance(value, str):
        v.add("INVALID_TYPE", path, "Expected string", phase="scalar")
        return False
    if value.strip() == "":
        v.add("INVALID_VALUE", path, "Empty or whitespace-only string", phase="value")
        return False
    return True


def _check_rfc3339(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_RFC3339):
        v.add("INVALID_FORMAT", path, "Must be RFC3339 UTC timestamp ending in Z", phase="format")
        return False
    return True


def _check_repo_relative_path(v: _PacketValidator, value: Any, path: str) -> Optional[str]:
    if not isinstance(value, str) or value.strip() == "":
        v.add("INVALID_VALUE", path, "Path must be a non-empty string", phase="value")
        return None
    if not is_repo_relative_path(value):
        v.add("PATH_NOT_RELATIVE", path, "Path must be relative to the repo root", phase="path_authority")
        return None
    normalized = _normalize_relative_path(value)
    if normalized is None:
        v.add("PATH_ESCAPE", path, "Path escapes the repository root", phase="path_authority")
        return None
    return normalized


def validate_journal_event(
    value: Any,
    prev_event: Optional[Dict[str, Any]] = None,
    state_root_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a single journal event.

    ``prev_event`` is the validated preceding event, used to check chain,
    sequence, and timestamp continuity. ``state_root_id`` is the manifest's
    state root id and is checked when supplied.
    """
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Journal event root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_journal_event_object(v, prev_event=prev_event, state_root_id=state_root_id)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_journal_event_object(
    v: _PacketValidator,
    prev_event: Optional[Dict[str, Any]],
    state_root_id: Optional[str],
) -> None:
    allowed = {
        "schema_version",
        "seq",
        "event_id",
        "event_type",
        "event_at",
        "coordinator_id",
        "run_id",
        "state_root_id",
        "packet_id",
        "intent_id",
        "from_state",
        "to_state",
        "cause",
        "payload",
        "prev_event_sha256",
        "event_sha256",
    }
    value = v.value
    for key in value:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in value:
            v.add("MISSING_FIELD", f"/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    if value.get("schema_version") != 1:
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1", phase="value")

    seq = value.get("seq")
    _check_int(v, seq, "/seq", min_value=1)

    event_id = value.get("event_id")
    _check_non_empty_string(v, event_id, "/event_id")

    event_type = value.get("event_type")
    v.check_enum(event_type, JOURNAL_EVENT_TYPES, "/event_type")

    event_at = value.get("event_at")
    _check_rfc3339(v, event_at, "/event_at")

    for field in ("coordinator_id", "run_id", "state_root_id"):
        _check_non_empty_string(v, value.get(field), f"/{field}")

    if state_root_id is not None and value.get("state_root_id") != state_root_id:
        v.add("EVIDENCE_HASH_MISMATCH", "/state_root_id", "state_root_id does not match manifest", phase="cross_field")

    packet_id = value.get("packet_id")
    if event_type in ({"RUN_STARTED", "RUN_ENDED", "JOURNAL_TAIL_TRUNCATED",
                       "RECONCILIATION_EMITTED", "EXECUTION_PLAN_BOUND"}
                      | PROVIDER_SCOPED_EVENT_TYPES
                      | GRACEFUL_STOP_EVENT_TYPES):
        if packet_id is not None:
            v.add("INVALID_VALUE", "/packet_id", f"{event_type} event must have packet_id null", phase="value")
    else:
        if not is_harness_id(packet_id):
            v.add(
                "INVALID_FORMAT",
                "/packet_id",
                f"{event_type} event requires a safe harness packet_id",
                phase="format",
            )

    intent_id = value.get("intent_id")
    intent_required_types = {
        "ATTEMPT_STARTED",
        "WORKER_RESULT_RECORDED",
        "ATTEMPT_FINISHED",
        "VERDICT_RECORDED",
        "PACKET_ENROLLED",
        "STATE_TRANSITION",
        "INTENT_ABANDONED",
        "WORKSPACE_BASELINE_RECORDED",
        "WORKSPACE_POSTFLIGHT_RECORDED",
        "INTEGRATION_MANIFEST_RECORDED",
    }
    if event_type in intent_required_types:
        if not isinstance(intent_id, str) or intent_id.strip() == "":
            v.add("INVALID_VALUE", "/intent_id", f"{event_type} event requires a non-empty intent_id", phase="value")
    else:
        if intent_id is not None:
            v.add("INVALID_VALUE", "/intent_id", f"{event_type} event must have intent_id null", phase="value")

    from_state = value.get("from_state")
    to_state = value.get("to_state")
    cause = value.get("cause")
    v.check_enum(cause, TRANSITION_CAUSES, "/cause")

    # State fields may only be non-null when the event type drives a transition.
    state_changing_types = {"PACKET_ENROLLED", "STATE_TRANSITION", "ATTEMPT_STARTED", "ATTEMPT_FINISHED", "VERDICT_RECORDED"}
    if event_type in state_changing_types:
        if event_type == "PACKET_ENROLLED":
            if from_state is not None:
                v.add("INVALID_VALUE", "/from_state", "PACKET_ENROLLED must have from_state null", phase="value")
            if to_state not in PACKET_STATES:
                v.add("INVALID_ENUM", "/to_state", "to_state must be a valid packet state", phase="enum")
            allowed_edges = CAUSE_EDGES.get(cause, set()) if isinstance(cause, str) else set()
            if (None, to_state) not in allowed_edges:
                v.add(
                    "INVALID_TRANSITION",
                    "/cause",
                    f"Cause '{cause}' does not permit transition (None, {to_state})",
                    phase="transition",
                )
            # Design 2.4: enrollment state is coupled to dependency_ids presence.
            packet_payload = (value.get("payload") or {}).get("packet") or {}
            dependency_ids = packet_payload.get("dependency_ids")
            expected_state = "BLOCKED" if isinstance(dependency_ids, list) and dependency_ids else "READY"
            if to_state in ("BLOCKED", "READY") and to_state != expected_state:
                v.add(
                    "INVALID_VALUE",
                    "/to_state",
                    f"PACKET_ENROLLED to_state must be {expected_state} when dependency_ids is {'non-empty' if expected_state == 'BLOCKED' else 'empty'}",
                    phase="value",
                )
        else:
            if from_state not in PACKET_STATES:
                v.add("INVALID_ENUM", "/from_state", "from_state must be a valid packet state", phase="enum")
            if to_state not in PACKET_STATES:
                v.add("INVALID_ENUM", "/to_state", "to_state must be a valid packet state", phase="enum")
            if from_state in PACKET_STATES and to_state in PACKET_STATES:
                t_result = validate_transition(from_state, to_state)
                if not t_result["valid"]:
                    for e in t_result["errors"]:
                        v.errors.append({**e, "path": f"/from_state", "_phase": PHASE_RANK.get("transition", 7)})
                allowed_edges = CAUSE_EDGES.get(cause, set()) if isinstance(cause, str) else set()
                if (from_state, to_state) not in allowed_edges:
                    v.add(
                        "INVALID_TRANSITION",
                        "/cause",
                        f"Cause '{cause}' does not permit transition ({from_state}, {to_state})",
                        phase="transition",
                    )
    else:
        if from_state is not None:
            v.add("INVALID_VALUE", "/from_state", f"{event_type} event must have from_state null", phase="value")
        if to_state is not None:
            v.add("INVALID_VALUE", "/to_state", f"{event_type} event must have to_state null", phase="value")

    if isinstance(cause, str) and event_type in CAUSES_BY_EVENT_TYPE:
        if cause not in CAUSES_BY_EVENT_TYPE[event_type]:
            v.add(
                "INVALID_TRANSITION",
                "/cause",
                f"Cause '{cause}' is not permitted for event type '{event_type}'",
                phase="transition",
            )

    v._journal_event_type = event_type
    payload = value.get("payload")
    _validate_payload(v, payload, event_type)

    prev_event_sha256 = value.get("prev_event_sha256")
    if not _matches(prev_event_sha256, RE_SHA256):
        v.add("INVALID_FORMAT", "/prev_event_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    if prev_event is not None:
        if prev_event_sha256 != prev_event.get("event_sha256"):
            v.add("JOURNAL_CHAIN_BROKEN", "/prev_event_sha256", "prev_event_sha256 does not match previous event hash", phase="chain")
        if isinstance(seq, int) and not isinstance(seq, bool) and isinstance(prev_event.get("seq"), int) and seq != prev_event["seq"] + 1:
            v.add("SEQUENCE_GAP", "/seq", f"seq must be {prev_event['seq'] + 1}, got {seq}", phase="chain")
        if _matches(event_at, RE_RFC3339) and _matches(prev_event.get("event_at"), RE_RFC3339) and event_at < prev_event["event_at"]:
            v.add("CHRONOLOGY_VIOLATION", "/event_at", "event_at must not be before previous event_at", phase="chain")
    else:
        if seq != 1:
            v.add("SEQUENCE_GAP", "/seq", "First event seq must be 1", phase="chain")
        if prev_event_sha256 != ZERO_SHA256:
            v.add("JOURNAL_CHAIN_BROKEN", "/prev_event_sha256", "First event prev_event_sha256 must be 64 zeros", phase="chain")

    event_sha256 = value.get("event_sha256")
    if not _matches(event_sha256, RE_SHA256):
        v.add("INVALID_FORMAT", "/event_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")
    if isinstance(event_sha256, str) and _matches(event_sha256, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"event_sha256"}))
        if computed != event_sha256:
            v.add("EVIDENCE_HASH_MISMATCH", "/event_sha256", "event_sha256 does not match canonical self-hash", phase="cross_field")


def _validate_payload(v: _PacketValidator, payload: Any, event_type: str) -> None:
    if not isinstance(payload, dict):
        v.add("INVALID_TYPE", "/payload", "Expected object", phase="scalar")
        return
    required_keys = {"packet", "attempt", "artifacts", "classification", "transition_detail", "recovery", "run", "report"}
    allowed_keys = required_keys | {"execution_plan"} | set(BUDGET_PAYLOAD_KEYS)
    for key in payload:
        if key not in allowed_keys:
            v.add("UNKNOWN_FIELD", f"/payload/{key}", f"Unknown field '{key}'")
    for key in required_keys:
        if key not in payload:
            v.add("MISSING_FIELD", f"/payload/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    if not isinstance(payload.get("artifacts"), list):
        v.add("INVALID_TYPE", "/payload/artifacts", "Expected array", phase="scalar")

    non_null = PAYLOAD_NON_NULL_BY_TYPE.get(event_type, set())
    for key in required_keys:
        if key == "artifacts":
            continue
        is_non_null = payload.get(key) is not None
        should_be_non_null = key in non_null
        if is_non_null and not should_be_non_null:
            v.add("INVALID_VALUE", f"/payload/{key}", f"{event_type} event must have {key} null", phase="value")
        elif should_be_non_null and not is_non_null:
            v.add("MISSING_FIELD", f"/payload/{key}", f"{event_type} event requires {key} to be non-null", phase="unknown_missing")

    execution_plan = payload.get("execution_plan")
    if event_type == "EXECUTION_PLAN_BOUND":
        if not isinstance(execution_plan, dict):
            v.add("MISSING_FIELD", "/payload/execution_plan", "EXECUTION_PLAN_BOUND requires execution_plan to be non-null", phase="unknown_missing")
    elif execution_plan is not None:
        v.add("INVALID_VALUE", "/payload/execution_plan", f"{event_type} event must have execution_plan null or absent", phase="value")

    _validate_budget_payloads(v, payload, event_type)

    if isinstance(payload.get("artifacts"), list):
        _validate_artifacts(v, payload["artifacts"], "/payload/artifacts")

    if "packet" in non_null and isinstance(payload.get("packet"), dict):
        _validate_payload_packet(v, payload["packet"], "/payload/packet")
    if "attempt" in non_null and isinstance(payload.get("attempt"), dict):
        _validate_payload_attempt(v, payload["attempt"], "/payload/attempt")
    if "classification" in non_null and isinstance(payload.get("classification"), dict):
        _validate_payload_classification(v, payload["classification"], "/payload/classification")
    if "transition_detail" in non_null and isinstance(payload.get("transition_detail"), dict):
        _validate_payload_transition_detail(v, payload["transition_detail"], "/payload/transition_detail")
    if "recovery" in non_null and isinstance(payload.get("recovery"), dict):
        _validate_payload_recovery(v, payload["recovery"], "/payload/recovery")
    if "run" in non_null and isinstance(payload.get("run"), dict):
        _validate_payload_run(v, payload["run"], "/payload/run")
    if "report" in non_null and isinstance(payload.get("report"), dict):
        _validate_payload_report(v, payload["report"], "/payload/report")
    if "execution_plan" in non_null and isinstance(payload.get("execution_plan"), dict):
        _validate_payload_execution_plan(v, payload["execution_plan"], "/payload/execution_plan")


def _validate_closed_payload(
    v: _PacketValidator,
    value: Any,
    path: str,
    spec: Dict[str, Any],
) -> bool:
    """Validate one closed payload object against an exact field spec.

    ``spec`` maps every permitted key to a ``(v, value, path)`` checker.  Key
    membership -- unknown keys, missing keys -- is decided here, once, so each
    new closed payload declares its fields exactly once instead of re-spelling
    the same membership loop.  Returns whether the per-field checks ran.
    """
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return False
    for key in value:
        if key not in spec:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in spec:
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return False
    for key in sorted(spec):
        spec[key](v, value.get(key), f"{path}/{key}")
    return True


def _check_model_id(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_MODEL_ID):
        v.add("INVALID_FORMAT", path, "Must be a canonical lowercase model identifier", phase="format")
        return False
    return True


def _check_optional_rfc3339(v: _PacketValidator, value: Any, path: str) -> bool:
    if value is None:
        return True
    return _check_rfc3339(v, value, path)


def _check_enum_factory(allowed: Set[str], label: str):
    def check(v: _PacketValidator, value: Any, path: str) -> bool:
        return v.check_enum(value, allowed, path)

    check.__name__ = "_check_" + label
    return check


# Deliberately NOT the whole of BUDGET_REASON_CODES: an immediate
# process-safety code fails validation on a capacity-family payload rather
# than being recorded as a bounded, resumable pause or backoff.
_check_reason_code = _check_enum_factory(CAPACITY_EVENT_REASON_CODES, "reason_code")
_check_capability_class = _check_enum_factory(CAPABILITY_CLASSES, "capability_class")
_check_capacity_state = _check_enum_factory(CAPACITY_STATES, "capacity_state")
# Deliberately NOT ``_check_reason_code``: a graceful stop accepts a strict
# subset of the vocabulary, so an immediate process-safety code fails
# validation here rather than being recorded as an orderly plan stop.
_check_graceful_stop_reason_code = _check_enum_factory(
    GRACEFUL_STOP_REASON_CODES, "graceful_stop_reason_code")


def _check_harness_id(v: _PacketValidator, value: Any, path: str) -> bool:
    if not is_harness_id(value):
        v.add("INVALID_FORMAT", path, "Must be a safe harness identifier", phase="format")
        return False
    return True


def _check_nonneg_int(v: _PacketValidator, value: Any, path: str) -> bool:
    return _check_int(v, value, path, nonneg=True)


def _check_evidence_id_list(v: _PacketValidator, value: Any, path: str) -> bool:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array", phase="scalar")
        return False
    seen: Set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or item.strip() == "":
            v.add("INVALID_VALUE", f"{path}/{index}", "Evidence id must be a non-empty string", phase="value")
        elif item in seen:
            v.add("DUPLICATE_ID", f"{path}/{index}", "Duplicate evidence id", phase="uniqueness")
        else:
            seen.add(item)
    if value != sorted(value, key=lambda item: item if isinstance(item, str) else ""):
        v.add("INVALID_VALUE", path, "Evidence ids must be sorted for deterministic bytes", phase="value")
    return True


# One closed field spec per O5 budget payload.  Nothing here can hold raw
# headers, credentials, response bodies, subscription identifiers, or prompt
# content -- there is no key for any of them.
BUDGET_PAYLOAD_SPECS: Dict[str, Dict[str, Any]] = {
    "provider_capacity": {
        "provider": _check_non_empty_string,
        "model_id": _check_model_id,
        "state": _check_capacity_state,
        "observed_at": _check_rfc3339,
        "reset_at": _check_optional_rfc3339,
        "evidence_sha256": _check_sha256,
    },
    "provider_backoff": {
        "provider": _check_non_empty_string,
        "model_id": _check_model_id,
        "reason_code": _check_reason_code,
        "next_eligible_at": _check_rfc3339,
        "retry_index": _check_nonneg_int,
        "evidence_sha256": _check_sha256,
    },
    "model_fallback": {
        "capability_class": _check_capability_class,
        "from_route_id": _check_harness_id,
        "to_route_id": _check_harness_id,
        "provider": _check_non_empty_string,
        "model_id": _check_model_id,
        "reason_code": _check_reason_code,
    },
    "packet_pause": {
        "reason_code": _check_reason_code,
        "capability_class": _check_capability_class,
        "next_eligible_at": _check_optional_rfc3339,
        "evidence_ids": _check_evidence_id_list,
    },
    # Both graceful-stop payloads bind the stop to the plan whose ceiling or
    # provider allowance produced it; the run identity comes from the event
    # envelope.  There is no field for stdout, stderr, or any other command
    # output, so a stop record cannot become a smuggling channel for it.
    "graceful_stop_request": {
        "plan_id": _check_harness_id,
        "plan_sha256": _check_sha256,
        "reason_code": _check_graceful_stop_reason_code,
        "evidence_ids": _check_evidence_id_list,
    },
    "graceful_stop_effective": {
        "plan_id": _check_harness_id,
        "plan_sha256": _check_sha256,
        "reason_code": _check_graceful_stop_reason_code,
        # Names the request this stop completes, so a fold can never pair an
        # effective stop with the wrong request.
        "requested_event_id": _check_non_empty_string,
        "evidence_ids": _check_evidence_id_list,
    },
}


def _validate_budget_payloads(v: _PacketValidator, payload: Dict[str, Any], event_type: str) -> None:
    """Bind each O5 budget payload key to exactly one event type."""
    for source_type in sorted(BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE):
        key = BUDGET_PAYLOAD_KEY_BY_EVENT_TYPE[source_type]
        body = payload.get(key)
        if event_type == source_type:
            if body is None:
                v.add(
                    "MISSING_FIELD",
                    f"/payload/{key}",
                    f"{event_type} requires {key} to be non-null",
                    phase="unknown_missing",
                )
                continue
            _validate_closed_payload(v, body, f"/payload/{key}", BUDGET_PAYLOAD_SPECS[key])
            if key == "provider_capacity" and isinstance(body, dict):
                observed_at, reset_at = body.get("observed_at"), body.get("reset_at")
                if (_matches(observed_at, RE_RFC3339) and _matches(reset_at, RE_RFC3339)
                        and reset_at < observed_at):
                    v.add(
                        "CHRONOLOGY_VIOLATION",
                        f"/payload/{key}/reset_at",
                        "reset_at must not precede observed_at",
                        phase="cross_field",
                    )
            if key == "model_fallback" and isinstance(body, dict):
                if body.get("from_route_id") == body.get("to_route_id"):
                    v.add(
                        "INVALID_FALLBACK",
                        f"/payload/{key}/to_route_id",
                        "A fallback hop must differ from the route it replaces",
                        phase="cross_field",
                    )
        elif body is not None:
            v.add(
                "INVALID_VALUE",
                f"/payload/{key}",
                f"{event_type} event must have {key} null or absent",
                phase="value",
            )


def _validate_payload_execution_plan(v: _PacketValidator, binding: Dict[str, Any], path: str) -> None:
    """Validate the O5 immutable plan-binding payload and nothing else."""
    allowed = {"plan_id", "plan_sha256", "plan_path", "packet_count"}
    for key in binding:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in binding:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return
    if not is_harness_id(binding.get("plan_id")):
        v.add("INVALID_FORMAT", f"{path}/plan_id", "plan_id must be a safe harness identifier", phase="format")
    _check_sha256(v, binding.get("plan_sha256"), f"{path}/plan_sha256")
    plan_path = binding.get("plan_path")
    normalized = _check_repo_relative_path(v, plan_path, f"{path}/plan_path")
    if normalized is not None and normalized != f"plans/{binding.get('plan_id')}.json":
        v.add("INVALID_VALUE", f"{path}/plan_path", "plan_path must be the canonical plan artifact path", phase="value")
    _check_int(v, binding.get("packet_count"), f"{path}/packet_count", positive=True)


def _validate_artifacts(v: _PacketValidator, artifacts: List[Any], path: str) -> None:
    seen: Set[str] = set()
    for i, art in enumerate(artifacts):
        p = f"{path}/{i}"
        if not isinstance(art, dict):
            v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
            continue
        required = {"kind", "artifact_id", "path", "sha256", "byte_length"}
        allowed = required | {"content_sha256"}
        for key in art:
            if key not in allowed:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        for key in required:
            if key not in art:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        if "kind" in art:
            v.check_enum(art["kind"], ARTIFACT_KINDS, f"{p}/kind")
        if "artifact_id" in art:
            aid = art["artifact_id"]
            if not isinstance(aid, str) or aid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/artifact_id", "artifact_id must be a non-empty string", phase="value")
            elif aid in seen:
                v.add("DUPLICATE_ID", f"{p}/artifact_id", "Duplicate artifact_id in event", phase="uniqueness")
            else:
                seen.add(aid)
        if "path" in art:
            _check_repo_relative_path(v, art["path"], f"{p}/path")
        if "sha256" in art:
            _check_sha256(v, art["sha256"], f"{p}/sha256")
        if "byte_length" in art:
            _check_int(v, art["byte_length"], f"{p}/byte_length", nonneg=True)
        if art.get("kind") in {"workspace_baseline", "workspace_postflight", "workspace_integration"}:
            _check_sha256(v, art.get("content_sha256"), f"{p}/content_sha256")

    if not isinstance(artifacts, list):
        return
    workspace_event = getattr(v, "_journal_event_type", None)
    if workspace_event in {"WORKSPACE_BASELINE_RECORDED", "WORKSPACE_POSTFLIGHT_RECORDED", "INTEGRATION_MANIFEST_RECORDED"}:
        artifact_kind = ("workspace_baseline" if workspace_event == "WORKSPACE_BASELINE_RECORDED"
                         else "workspace_postflight" if workspace_event == "WORKSPACE_POSTFLIGHT_RECORDED"
                         else "workspace_integration")
        if len(artifacts) != 1:
            v.add("INVALID_VALUE", path, f"{workspace_event} requires exactly one artifact", phase="value")
            return
        artifact = artifacts[0] if isinstance(artifacts[0], dict) else {}
        if artifact.get("kind") != artifact_kind:
            v.add("INVALID_VALUE", f"{path}/0/kind", f"{workspace_event} requires {artifact_kind} artifact", phase="value")
        if artifact.get("artifact_id") != artifact_kind:
            v.add("INVALID_VALUE", f"{path}/0/artifact_id", f"{workspace_event} requires {artifact_kind} artifact_id", phase="value")
        _check_sha256(v, artifact.get("content_sha256"), f"{path}/0/content_sha256")
    else:
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict):
                continue
            if artifact.get("kind") in {"workspace_baseline", "workspace_postflight", "workspace_integration"}:
                v.add("INVALID_VALUE", f"{path}/{index}/kind", "workspace evidence belongs only to its matching event", phase="value")
            if "content_sha256" in artifact:
                v.add("INVALID_VALUE", f"{path}/{index}/content_sha256", "content_sha256 belongs only to workspace evidence artifacts", phase="value")


def _validate_payload_packet(v: _PacketValidator, packet: Dict[str, Any], path: str) -> None:
    allowed = {
        "packet_sha256",
        "packet_path",
        "lane",
        "dependency_ids",
        "sonnet_reassignment_allowed",
        "retry_limit",
        "enqueue_seq",
    }
    for key in packet:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in packet:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    _check_sha256(v, packet.get("packet_sha256"), f"{path}/packet_sha256")
    _check_repo_relative_path(v, packet.get("packet_path"), f"{path}/packet_path")
    v.check_enum(packet.get("lane"), LANES, f"{path}/lane")

    deps = packet.get("dependency_ids")
    if not isinstance(deps, list):
        v.add("INVALID_TYPE", f"{path}/dependency_ids", "Expected array", phase="scalar")
    else:
        for i, dep in enumerate(deps):
            if not is_harness_id(dep):
                v.add(
                    "INVALID_FORMAT",
                    f"{path}/dependency_ids/{i}",
                    "Dependency ID must be a safe harness identifier",
                    phase="format",
                )

    sra = packet.get("sonnet_reassignment_allowed")
    if not isinstance(sra, bool):
        v.add("INVALID_TYPE", f"{path}/sonnet_reassignment_allowed", "Expected boolean", phase="scalar")

    retry_limit = packet.get("retry_limit")
    _check_int(v, retry_limit, f"{path}/retry_limit", positive=True)

    enqueue_seq = packet.get("enqueue_seq")
    _check_int(v, enqueue_seq, f"{path}/enqueue_seq", min_value=1)

    if isinstance(sra, bool) and sra is True and isinstance(retry_limit, int) and retry_limit < 2:
        v.add("INVALID_VALUE", f"{path}/retry_limit", "retry_limit must be >= 2 when sonnet_reassignment_allowed is true", phase="value")


def _validate_payload_attempt(v: _PacketValidator, attempt: Dict[str, Any], path: str) -> None:
    allowed = {"attempt", "lane", "worker", "claim_sha256", "worktree_path"}
    for key in attempt:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in attempt:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    _check_int(v, attempt.get("attempt"), f"{path}/attempt", min_value=1)
    v.check_enum(attempt.get("lane"), LANES, f"{path}/lane")

    worker = attempt.get("worker")
    if not isinstance(worker, dict):
        v.add("INVALID_TYPE", f"{path}/worker", "Expected object", phase="scalar")
    else:
        w_allowed = {"worker_id", "session_id", "provider", "model"}
        for key in worker:
            if key not in w_allowed:
                v.add("UNKNOWN_FIELD", f"{path}/worker/{key}", f"Unknown field '{key}'")
        for key in w_allowed:
            if key not in worker:
                v.add("MISSING_FIELD", f"{path}/worker/{key}", f"Missing required field '{key}'")
            else:
                _check_non_empty_string(v, worker[key], f"{path}/worker/{key}")

    claim_sha256 = attempt.get("claim_sha256")
    if claim_sha256 is not None and not _matches(claim_sha256, RE_SHA256):
        v.add("INVALID_FORMAT", f"{path}/claim_sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    worktree_path = attempt.get("worktree_path")
    if worktree_path is not None:
        if not isinstance(worktree_path, str) or worktree_path.strip() == "":
            v.add("INVALID_VALUE", f"{path}/worktree_path", "worktree_path must be a non-empty string when non-null", phase="value")
        elif not worktree_path.startswith("/"):
            v.add("INVALID_VALUE", f"{path}/worktree_path", "worktree_path must be absolute when non-null", phase="value")


def _validate_payload_classification(v: _PacketValidator, classification: Dict[str, Any], path: str) -> None:
    allowed = {
        "attempt_class",
        "quarantine_reason",
        "human_required_reasons",
        "result_sha256",
        "provider_evidence_sha256",
        "reassignment_record_sha256",
        "outcome_summary",
    }
    for key in classification:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in classification:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    v.check_enum(classification.get("attempt_class"), ATTEMPT_CLASSES, f"{path}/attempt_class")

    qr = classification.get("quarantine_reason")
    if qr is not None and (not isinstance(qr, str) or qr.strip() == ""):
        v.add("INVALID_VALUE", f"{path}/quarantine_reason", "quarantine_reason must be a non-empty string or null", phase="value")

    hrr = classification.get("human_required_reasons")
    if not isinstance(hrr, list):
        v.add("INVALID_TYPE", f"{path}/human_required_reasons", "Expected array", phase="scalar")
    else:
        for i, reason in enumerate(hrr):
            if not isinstance(reason, str) or reason.strip() == "":
                v.add("INVALID_VALUE", f"{path}/human_required_reasons/{i}", "Reason must be a non-empty string", phase="value")

    for key in ("result_sha256", "provider_evidence_sha256", "reassignment_record_sha256"):
        val = classification.get(key)
        if val is not None and not _matches(val, RE_SHA256):
            v.add("INVALID_FORMAT", f"{path}/{key}", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    outcome_summary = classification.get("outcome_summary")
    if not isinstance(outcome_summary, dict):
        v.add("INVALID_TYPE", f"{path}/outcome_summary", "Expected object", phase="scalar")
    else:
        os_allowed = {"exit_code", "signal", "timed_out", "result_present", "result_valid", "error_codes"}
        for key in outcome_summary:
            if key not in os_allowed:
                v.add("UNKNOWN_FIELD", f"{path}/outcome_summary/{key}", f"Unknown field '{key}'")
        for key in os_allowed:
            if key not in outcome_summary:
                v.add("MISSING_FIELD", f"{path}/outcome_summary/{key}", f"Missing required field '{key}'")
        ec = outcome_summary.get("exit_code")
        if ec is not None and (isinstance(ec, bool) or not isinstance(ec, int)):
            v.add("INVALID_TYPE", f"{path}/outcome_summary/exit_code", "Expected integer or null", phase="scalar")
        sig = outcome_summary.get("signal")
        if sig is not None and (isinstance(sig, bool) or not isinstance(sig, int)):
            v.add("INVALID_TYPE", f"{path}/outcome_summary/signal", "Expected integer or null", phase="scalar")
        for key in ("timed_out", "result_present", "result_valid"):
            if key in outcome_summary and not isinstance(outcome_summary[key], bool):
                v.add("INVALID_TYPE", f"{path}/outcome_summary/{key}", "Expected boolean", phase="scalar")
        error_codes = outcome_summary.get("error_codes")
        if not isinstance(error_codes, list):
            v.add("INVALID_TYPE", f"{path}/outcome_summary/error_codes", "Expected array", phase="scalar")
        else:
            for i, code in enumerate(error_codes):
                if not isinstance(code, str) or code.strip() == "":
                    v.add("INVALID_VALUE", f"{path}/outcome_summary/error_codes/{i}", "Error code must be a non-empty string", phase="value")


def _validate_payload_transition_detail(v: _PacketValidator, detail: Dict[str, Any], path: str) -> None:
    allowed = {"satisfied_by", "source_verdict", "revise_cycle"}
    for key in detail:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in detail:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    satisfied_by = detail.get("satisfied_by")
    if not isinstance(satisfied_by, list):
        v.add("INVALID_TYPE", f"{path}/satisfied_by", "Expected array", phase="scalar")
    else:
        for i, rec in enumerate(satisfied_by):
            p = f"{path}/satisfied_by/{i}"
            if not isinstance(rec, dict):
                v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                continue
            for key in ("packet_id", "verdict_sha256", "seal_sha256"):
                if key not in rec:
                    v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
                elif key == "packet_id":
                    _check_non_empty_string(v, rec[key], f"{p}/{key}")
                else:
                    _check_sha256(v, rec[key], f"{p}/{key}")
            for key in rec:
                if key not in {"packet_id", "verdict_sha256", "seal_sha256"}:
                    v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    source_verdict = detail.get("source_verdict")
    if source_verdict is not None:
        if not isinstance(source_verdict, dict):
            v.add("INVALID_TYPE", f"{path}/source_verdict", "Expected object or null", phase="scalar")
        else:
            for key in ("verdict_id", "verdict_sha256", "verdict"):
                if key not in source_verdict:
                    v.add("MISSING_FIELD", f"{path}/source_verdict/{key}", f"Missing required field '{key}'")
                elif key == "verdict":
                    v.check_enum(source_verdict[key], VERDICTS, f"{path}/source_verdict/{key}")
                elif key == "verdict_id":
                    _check_non_empty_string(v, source_verdict[key], f"{path}/source_verdict/{key}")
                else:
                    _check_sha256(v, source_verdict[key], f"{path}/source_verdict/{key}")
            for key in source_verdict:
                if key not in {"verdict_id", "verdict_sha256", "verdict"}:
                    v.add("UNKNOWN_FIELD", f"{path}/source_verdict/{key}", f"Unknown field '{key}'")

    revise_cycle = detail.get("revise_cycle")
    if revise_cycle is not None and not _check_int(v, revise_cycle, f"{path}/revise_cycle", nonneg=True):
        pass


def _validate_payload_recovery(v: _PacketValidator, recovery: Dict[str, Any], path: str) -> None:
    allowed = {"abandoned_intent_id", "abandoned_at_stage", "consecutive_abandonments", "prior_claim", "truncation", "review_failure"}
    for key in recovery:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in recovery:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    abandoned_intent_id = recovery.get("abandoned_intent_id")
    if abandoned_intent_id is not None and (not isinstance(abandoned_intent_id, str) or abandoned_intent_id.strip() == ""):
        v.add("INVALID_VALUE", f"{path}/abandoned_intent_id", "Must be a non-empty string or null", phase="value")

    abandoned_at_stage = recovery.get("abandoned_at_stage")
    if abandoned_at_stage is not None:
        v.check_enum(abandoned_at_stage, ABANDONED_STAGES, f"{path}/abandoned_at_stage")

    consecutive_abandonments = recovery.get("consecutive_abandonments")
    if consecutive_abandonments is not None and not _check_int(v, consecutive_abandonments, f"{path}/consecutive_abandonments", nonneg=True):
        pass

    prior_claim = recovery.get("prior_claim")
    if prior_claim is not None:
        if not isinstance(prior_claim, dict):
            v.add("INVALID_TYPE", f"{path}/prior_claim", "Expected object or null", phase="scalar")
        else:
            for key in ("claim_sha256", "path", "classification", "coordinator_id", "pid", "boot_id", "hostname"):
                if key not in prior_claim:
                    v.add("MISSING_FIELD", f"{path}/prior_claim/{key}", f"Missing required field '{key}'")
                elif key == "claim_sha256":
                    _check_sha256(v, prior_claim[key], f"{path}/prior_claim/{key}")
                elif key == "pid":
                    _check_int(v, prior_claim[key], f"{path}/prior_claim/{key}", min_value=1)
                elif key == "classification":
                    v.check_enum(prior_claim[key], CLAIM_CLASSIFICATIONS, f"{path}/prior_claim/{key}")
                else:
                    _check_non_empty_string(v, prior_claim[key], f"{path}/prior_claim/{key}")
            for key in prior_claim:
                if key not in {"claim_sha256", "path", "classification", "coordinator_id", "pid", "boot_id", "hostname"}:
                    v.add("UNKNOWN_FIELD", f"{path}/prior_claim/{key}", f"Unknown field '{key}'")

    truncation = recovery.get("truncation")
    if truncation is not None:
        if not isinstance(truncation, dict):
            v.add("INVALID_TYPE", f"{path}/truncation", "Expected object or null", phase="scalar")
        else:
            for key in ("byte_length", "tail_path", "tail_sha256", "valid_prefix_last_seq"):
                if key not in truncation:
                    v.add("MISSING_FIELD", f"{path}/truncation/{key}", f"Missing required field '{key}'")
                elif key == "byte_length":
                    _check_int(v, truncation[key], f"{path}/truncation/{key}", nonneg=True)
                elif key == "valid_prefix_last_seq":
                    _check_int(v, truncation[key], f"{path}/truncation/{key}", nonneg=True)
                elif key == "tail_sha256":
                    _check_sha256(v, truncation[key], f"{path}/truncation/{key}")
                else:
                    _check_non_empty_string(v, truncation[key], f"{path}/truncation/{key}")
            for key in truncation:
                if key not in {"byte_length", "tail_path", "tail_sha256", "valid_prefix_last_seq"}:
                    v.add("UNKNOWN_FIELD", f"{path}/truncation/{key}", f"Unknown field '{key}'")

    review_failure = recovery.get("review_failure")
    if review_failure is not None:
        if not isinstance(review_failure, dict):
            v.add("INVALID_TYPE", f"{path}/review_failure", "Expected object or null", phase="scalar")
        else:
            for key in ("error_codes", "raw_verdict_path", "raw_verdict_sha256"):
                if key not in review_failure:
                    v.add("MISSING_FIELD", f"{path}/review_failure/{key}", f"Missing required field '{key}'")
                elif key == "error_codes":
                    ec = review_failure[key]
                    if not isinstance(ec, list):
                        v.add("INVALID_TYPE", f"{path}/review_failure/{key}", "Expected array", phase="scalar")
                    else:
                        for i, code in enumerate(ec):
                            if not isinstance(code, str) or code.strip() == "":
                                v.add("INVALID_VALUE", f"{path}/review_failure/{key}/{i}", "Error code must be a non-empty string", phase="value")
                elif key == "raw_verdict_sha256":
                    _check_sha256(v, review_failure[key], f"{path}/review_failure/{key}")
                else:
                    _check_non_empty_string(v, review_failure[key], f"{path}/review_failure/{key}")
            for key in review_failure:
                if key not in {"error_codes", "raw_verdict_path", "raw_verdict_sha256"}:
                    v.add("UNKNOWN_FIELD", f"{path}/review_failure/{key}", f"Unknown field '{key}'")


def _validate_payload_run(v: _PacketValidator, run: Dict[str, Any], path: str) -> None:
    allowed = {"coordinator", "trust_roots", "contract_versions", "end_reason", "end_detail", "disabled_lanes"}
    for key in run:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in run:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    coordinator = run.get("coordinator")
    if isinstance(coordinator, dict):
        for key in ("coordinator_id", "boot_id", "hostname", "pid"):
            if key not in coordinator:
                v.add("MISSING_FIELD", f"{path}/coordinator/{key}", f"Missing required field '{key}'")
            elif key == "pid":
                _check_int(v, coordinator[key], f"{path}/coordinator/{key}", min_value=1)
            else:
                _check_non_empty_string(v, coordinator[key], f"{path}/coordinator/{key}")
        for key in coordinator:
            if key not in {"coordinator_id", "boot_id", "hostname", "pid"}:
                v.add("UNKNOWN_FIELD", f"{path}/coordinator/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", f"{path}/coordinator", "Expected object", phase="scalar")

    trust_roots = run.get("trust_roots")
    if isinstance(trust_roots, dict):
        for key in ("reviewer_sessions_path", "reviewer_sessions_sha256", "provider_signals_path", "provider_signals_sha256"):
            if key not in trust_roots:
                v.add("MISSING_FIELD", f"{path}/trust_roots/{key}", f"Missing required field '{key}'")
            elif "sha256" in key:
                _check_sha256(v, trust_roots[key], f"{path}/trust_roots/{key}")
            else:
                _check_non_empty_string(v, trust_roots[key], f"{path}/trust_roots/{key}")
        for key in trust_roots:
            if key not in {"reviewer_sessions_path", "reviewer_sessions_sha256", "provider_signals_path", "provider_signals_sha256"}:
                v.add("UNKNOWN_FIELD", f"{path}/trust_roots/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", f"{path}/trust_roots", "Expected object", phase="scalar")

    contract_versions = run.get("contract_versions")
    if isinstance(contract_versions, dict):
        required_versions = {
            "packet",
            "worker_result",
            "verdict",
            "replay",
            "journal",
            "queue",
            "claim",
            "attempt_outcome",
            "provider_evidence",
            "reassignment",
            "reconciliation",
        }
        optional_versions = {"workspace_evidence"}
        for key in required_versions:
            if key not in contract_versions:
                v.add("MISSING_FIELD", f"{path}/contract_versions/{key}", f"Missing required field '{key}'")
            elif contract_versions[key] != 1:
                v.add("INVALID_VALUE", f"{path}/contract_versions/{key}", "Contract version must be 1", phase="value")
        for key in optional_versions:
            if (key in contract_versions
                    and (type(contract_versions[key]) is not int or contract_versions[key] != 1)):
                v.add("INVALID_VALUE", f"{path}/contract_versions/{key}", "Contract version must be 1", phase="value")
        for key in contract_versions:
            if key not in required_versions | optional_versions:
                v.add("UNKNOWN_FIELD", f"{path}/contract_versions/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", f"{path}/contract_versions", "Expected object", phase="scalar")

    end_reason = run.get("end_reason")
    if end_reason is not None:
        v.check_enum(end_reason, RUN_END_REASONS, f"{path}/end_reason")

    end_detail = run.get("end_detail")
    if end_detail is not None and (not isinstance(end_detail, str) or end_detail.strip() == ""):
        v.add("INVALID_VALUE", f"{path}/end_detail", "end_detail must be a non-empty string or null", phase="value")

    disabled_lanes = run.get("disabled_lanes")
    if not isinstance(disabled_lanes, list):
        v.add("INVALID_TYPE", f"{path}/disabled_lanes", "Expected array", phase="scalar")
    else:
        for i, lane in enumerate(disabled_lanes):
            v.check_enum(lane, LANES, f"{path}/disabled_lanes/{i}")


def _validate_payload_report(v: _PacketValidator, report: Dict[str, Any], path: str) -> None:
    allowed = {"report_id", "report_sha256", "content_sha256", "report_path", "inventory_total", "all_invariants_passed"}
    for key in report:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in allowed:
        if key not in report:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    for key in ("report_id", "report_path"):
        _check_non_empty_string(v, report.get(key), f"{path}/{key}")
    for key in ("report_sha256", "content_sha256"):
        _check_sha256(v, report.get(key), f"{path}/{key}")
    _check_int(v, report.get("inventory_total"), f"{path}/inventory_total", nonneg=True)
    if not isinstance(report.get("all_invariants_passed"), bool):
        v.add("INVALID_TYPE", f"{path}/all_invariants_passed", "Expected boolean", phase="scalar")
