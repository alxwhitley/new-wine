"""Reconciliation report validation and invariant computation for O3."""

import json
from typing import Any, Dict, List, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.execution_plan import CAPABILITY_CLASSES
from harness_contracts.v1.packet import PACKET_STATES, RE_SHA256, _matches, _PacketValidator
from harness_contracts.v1.provider_evidence import CAPACITY_STATES
from harness_contracts.v1.worker_result import RE_RFC3339


# O5 Task 5: the closed six-way terminal-disposition partition every plan
# member packet must land in exactly once. Deliberately NOT the same set as
# PACKET_STATES: a disposition is a REPORT-level classification derived from
# fold state plus plan/pause evidence (see reconcile.py's
# ``_o5_disposition``), not a raw packet state -- READY/RUNNING/BLOCKED
# packets are never a disposition value on their own, they resolve to
# ``paused_provider``/``blocked_human``/``never_started`` or are left
# unresolved (``None``), which deliberately produces a sum shortfall against
# ``planned`` rather than being silently folded into an existing bucket.
PLAN_DISPOSITIONS = {
    "accepted", "resting_revise", "quarantined",
    "paused_provider", "blocked_human", "never_started",
}

PLAN_TOTAL_KEYS = (
    "planned", "attempted", "accepted", "resting_revise",
    "quarantined", "paused_provider", "blocked_human", "never_started",
)


def validate_reconciliation_report(value: Any) -> Dict[str, Any]:
    """Validate a reconciliation report record."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Reconciliation report root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_reconciliation_report_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_reconciliation_report_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "report_id",
        "generated_at",
        "coordinator_id",
        "run_id",
        "state_root_id",
        "journal_head",
        "inventory_total",
        "by_state",
        "packets",
        "activity",
        "attention_required",
        "integrity",
        "reconciliation",
        "plan_totals",
        "attempted_packet_ids",
        "all_invariants_passed",
        "content_sha256",
        "report_sha256",
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

    for field in ("report_id", "generated_at", "coordinator_id", "run_id", "state_root_id"):
        val = value.get(field)
        if not isinstance(val, str) or val.strip() == "":
            v.add("INVALID_VALUE", f"/{field}", f"{field} must be a non-empty string", phase="value")

    if not _matches(value.get("generated_at"), RE_RFC3339):
        v.add("INVALID_FORMAT", "/generated_at", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

    journal_head = value.get("journal_head")
    if isinstance(journal_head, dict):
        for key in ("seq", "event_sha256"):
            if key not in journal_head:
                v.add("MISSING_FIELD", f"/journal_head/{key}", f"Missing required field '{key}'")
            elif key == "seq":
                seq = journal_head[key]
                if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
                    v.add("INVALID_VALUE", f"/journal_head/{key}", "seq must be a non-negative integer", phase="value")
            else:
                _check_sha256(v, journal_head[key], f"/journal_head/{key}")
        for key in journal_head:
            if key not in {"seq", "event_sha256"}:
                v.add("UNKNOWN_FIELD", f"/journal_head/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", "/journal_head", "Expected object", phase="scalar")

    inventory_total = value.get("inventory_total")
    if isinstance(inventory_total, bool) or not isinstance(inventory_total, int) or inventory_total < 0:
        v.add("INVALID_VALUE", "/inventory_total", "Must be a non-negative integer", phase="value")

    by_state = value.get("by_state")
    if isinstance(by_state, dict):
        if set(by_state.keys()) != PACKET_STATES:
            v.add("INVALID_VALUE", "/by_state", "by_state must contain exactly all eight PACKET_STATES keys", phase="value")
        for state in PACKET_STATES:
            val = by_state.get(state)
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                v.add("INVALID_VALUE", f"/by_state/{state}", "Count must be a non-negative integer", phase="value")
        for key in by_state:
            if key not in PACKET_STATES:
                v.add("UNKNOWN_FIELD", f"/by_state/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", "/by_state", "Expected object", phase="scalar")

    packets = value.get("packets")
    if isinstance(packets, list):
        for i, row in enumerate(packets):
            _validate_packet_row(v, row, f"/packets/{i}")
    else:
        v.add("INVALID_TYPE", "/packets", "Expected array", phase="scalar")

    _validate_activity(v, value.get("activity"), "/activity")
    _validate_attention_required(v, value.get("attention_required"), "/attention_required")
    _validate_integrity(v, value.get("integrity"), "/integrity")

    reconciliation = value.get("reconciliation")
    if isinstance(reconciliation, dict):
        for key in ("sum_of_by_state", "packets_array_length", "distinct_packet_ids", "equals_inventory_total", "all_invariants_passed"):
            if key not in reconciliation:
                v.add("MISSING_FIELD", f"/reconciliation/{key}", f"Missing required field '{key}'")
            elif key in {"equals_inventory_total", "all_invariants_passed"}:
                if not isinstance(reconciliation[key], bool):
                    v.add("INVALID_TYPE", f"/reconciliation/{key}", "Expected boolean", phase="scalar")
            else:
                val = reconciliation[key]
                if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                    v.add("INVALID_VALUE", f"/reconciliation/{key}", "Must be a non-negative integer", phase="value")
        for key in reconciliation:
            if key not in {"sum_of_by_state", "packets_array_length", "distinct_packet_ids", "equals_inventory_total", "all_invariants_passed"}:
                v.add("UNKNOWN_FIELD", f"/reconciliation/{key}", f"Unknown field '{key}'")
    else:
        v.add("INVALID_TYPE", "/reconciliation", "Expected object", phase="scalar")

    _validate_plan_totals(v, value.get("plan_totals"), "/plan_totals")

    attempted_ids = value.get("attempted_packet_ids")
    if attempted_ids is not None:
        if not isinstance(attempted_ids, list):
            v.add("INVALID_TYPE", "/attempted_packet_ids", "Expected array or null", phase="scalar")
        else:
            for i, pid in enumerate(attempted_ids):
                if not isinstance(pid, str) or pid.strip() == "":
                    v.add("INVALID_VALUE", f"/attempted_packet_ids/{i}", "Must be a non-empty string", phase="value")

    if not isinstance(value.get("all_invariants_passed"), bool):
        v.add("INVALID_TYPE", "/all_invariants_passed", "Expected boolean", phase="scalar")

    for key in ("content_sha256", "report_sha256"):
        _check_sha256(v, value.get(key), f"/{key}")

    declared_content = value.get("content_sha256")
    if isinstance(declared_content, str) and _matches(declared_content, RE_SHA256):
        computed_content = compute_sha256(
            canonical_bytes(
                value,
                omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
            )
        )
        if computed_content != declared_content:
            v.add("EVIDENCE_HASH_MISMATCH", "/content_sha256", "content_sha256 does not match canonical hash", phase="cross_field")

    declared_report = value.get("report_sha256")
    if isinstance(declared_report, str) and _matches(declared_report, RE_SHA256):
        computed_report = compute_sha256(canonical_bytes(value, omit={"report_sha256"}))
        if computed_report != declared_report:
            v.add("EVIDENCE_HASH_MISMATCH", "/report_sha256", "report_sha256 does not match canonical self-hash", phase="cross_field")


def _validate_packet_row(v: _PacketValidator, row: Any, path: str) -> None:
    if not isinstance(row, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {
        "packet_id",
        "state",
        "lane",
        "enqueue_seq",
        "attempts_started",
        "infra_retries_used",
        "revise_cycles_used",
        "revise_verdicts",
        "reassignment_used",
        "open_attempt",
        "last_event_seq",
        "last_event_sha256",
        "quarantine_reason",
        "human_required_reasons",
        "blocked_on",
        "attention_codes",
        "retry_limit",
        "plan_id",
        "plan_sha256",
        "capability_class",
        "route_history",
        "budget_usage",
        "provider_backoff_state",
        "stop_reasons",
        "disposition",
    }
    for key in row:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in row:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    val = row.get("packet_id")
    if not isinstance(val, str) or val.strip() == "":
        v.add("INVALID_VALUE", f"{path}/packet_id", "packet_id must be a non-empty string", phase="value")

    v.check_enum(row.get("state"), PACKET_STATES, f"{path}/state")
    from harness_contracts.v1.packet import LANES
    v.check_enum(row.get("lane"), LANES, f"{path}/lane")

    for key in ("enqueue_seq", "last_event_seq"):
        val = row.get(key)
        if isinstance(val, bool) or not isinstance(val, int) or val < 1:
            v.add("INVALID_VALUE", f"{path}/{key}", "Must be a positive integer", phase="value")

    for key in ("attempts_started", "infra_retries_used", "revise_cycles_used", "revise_verdicts"):
        val = row.get(key)
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            v.add("INVALID_VALUE", f"{path}/{key}", "Must be a non-negative integer", phase="value")

    if not isinstance(row.get("reassignment_used"), bool):
        v.add("INVALID_TYPE", f"{path}/reassignment_used", "Expected boolean", phase="scalar")

    open_attempt = row.get("open_attempt")
    if open_attempt is not None:
        if isinstance(open_attempt, bool) or not isinstance(open_attempt, int) or open_attempt < 1:
            v.add("INVALID_VALUE", f"{path}/open_attempt", "Must be a positive integer or null", phase="value")

    if not _matches(row.get("last_event_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", f"{path}/last_event_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

    qr = row.get("quarantine_reason")
    if qr is not None and (not isinstance(qr, str) or qr.strip() == ""):
        v.add("INVALID_VALUE", f"{path}/quarantine_reason", "Must be a non-empty string or null", phase="value")

    hrr = row.get("human_required_reasons")
    if not isinstance(hrr, list):
        v.add("INVALID_TYPE", f"{path}/human_required_reasons", "Expected array", phase="scalar")
    else:
        for i, reason in enumerate(hrr):
            if not isinstance(reason, str) or reason.strip() == "":
                v.add("INVALID_VALUE", f"{path}/human_required_reasons/{i}", "Reason must be a non-empty string", phase="value")

    for key in ("blocked_on", "attention_codes"):
        arr = row.get(key)
        if not isinstance(arr, list):
            v.add("INVALID_TYPE", f"{path}/{key}", "Expected array", phase="scalar")
        else:
            for i, item in enumerate(arr):
                if not isinstance(item, str) or item.strip() == "":
                    v.add("INVALID_VALUE", f"{path}/{key}/{i}", "Must be a non-empty string", phase="value")

    retry_limit = row.get("retry_limit")
    if isinstance(retry_limit, bool) or not isinstance(retry_limit, int) or retry_limit < 1:
        v.add("INVALID_VALUE", f"{path}/retry_limit", "Must be a positive integer", phase="value")

    _validate_o5_row_extension(v, row, path)


def _validate_o5_row_extension(v: _PacketValidator, row: Dict[str, Any], path: str) -> None:
    """Task 5's O5 row extension: plan identity, capability class, route
    history, budget usage, provider/backoff state, stop reasons, and exactly
    one terminal disposition. Every field here is nullable in the exact same
    place (a packet outside a bound plan, or a report with no O5 plan bound
    at all) -- a pre-O5 journal must validate identically to before, just
    with these fields present and null rather than absent, so no existing
    caller reading an unbound-plan report has to change shape."""
    plan_id = row.get("plan_id")
    if plan_id is not None and (not isinstance(plan_id, str) or plan_id.strip() == ""):
        v.add("INVALID_VALUE", f"{path}/plan_id", "Must be a non-empty string or null", phase="value")

    plan_sha256 = row.get("plan_sha256")
    if plan_sha256 is not None and not _matches(plan_sha256, RE_SHA256):
        v.add("INVALID_FORMAT", f"{path}/plan_sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")

    capability_class = row.get("capability_class")
    if capability_class is not None and capability_class not in CAPABILITY_CLASSES:
        v.add("INVALID_ENUM", f"{path}/capability_class", f"Value must be one of {sorted(CAPABILITY_CLASSES)} or null")

    route_history = row.get("route_history")
    if not isinstance(route_history, list):
        v.add("INVALID_TYPE", f"{path}/route_history", "Expected array", phase="scalar")
    else:
        for i, hop in enumerate(route_history):
            hop_path = f"{path}/route_history/{i}"
            if not isinstance(hop, dict):
                v.add("INVALID_TYPE", hop_path, "Expected object", phase="scalar")
                continue
            hop_required = {"seq", "event_type", "provider", "model_id", "reason_code"}
            for key in hop:
                if key not in hop_required:
                    v.add("UNKNOWN_FIELD", f"{hop_path}/{key}", f"Unknown field '{key}'")
            for key in hop_required:
                if key not in hop:
                    v.add("MISSING_FIELD", f"{hop_path}/{key}", f"Missing required field '{key}'")
            if any(err["path"].startswith(hop_path) for err in v.errors):
                continue
            seq = hop.get("seq")
            if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
                v.add("INVALID_VALUE", f"{hop_path}/seq", "Must be a positive integer", phase="value")
            v.check_enum(hop.get("event_type"), {"ATTEMPT_STARTED", "MODEL_FALLBACK_SELECTED"}, f"{hop_path}/event_type")
            for key in ("provider", "model_id"):
                val = hop.get(key)
                if not isinstance(val, str) or val.strip() == "":
                    v.add("INVALID_VALUE", f"{hop_path}/{key}", "Must be a non-empty string", phase="value")
            reason_code = hop.get("reason_code")
            if reason_code is not None and (not isinstance(reason_code, str) or reason_code.strip() == ""):
                v.add("INVALID_VALUE", f"{hop_path}/reason_code", "Must be a non-empty string or null", phase="value")

    budget_usage = row.get("budget_usage")
    if budget_usage is not None:
        if not isinstance(budget_usage, dict):
            v.add("INVALID_TYPE", f"{path}/budget_usage", "Expected object or null", phase="scalar")
        else:
            bu_keys = {
                "attempt_limit", "retry_limit", "revision_limit",
                "attempts_started", "infra_retries_used", "revise_cycles_used",
            }
            for key in budget_usage:
                if key not in bu_keys:
                    v.add("UNKNOWN_FIELD", f"{path}/budget_usage/{key}", f"Unknown field '{key}'")
            for key in bu_keys:
                if key not in budget_usage:
                    v.add("MISSING_FIELD", f"{path}/budget_usage/{key}", f"Missing required field '{key}'")
                else:
                    val = budget_usage[key]
                    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                        v.add("INVALID_VALUE", f"{path}/budget_usage/{key}", "Must be a non-negative integer", phase="value")

    backoff_state = row.get("provider_backoff_state")
    if backoff_state is not None:
        if not isinstance(backoff_state, dict):
            v.add("INVALID_TYPE", f"{path}/provider_backoff_state", "Expected object or null", phase="scalar")
        else:
            pb_keys = {"provider", "model_id", "state", "reset_at"}
            for key in backoff_state:
                if key not in pb_keys:
                    v.add("UNKNOWN_FIELD", f"{path}/provider_backoff_state/{key}", f"Unknown field '{key}'")
            for key in pb_keys:
                if key not in backoff_state:
                    v.add("MISSING_FIELD", f"{path}/provider_backoff_state/{key}", f"Missing required field '{key}'")
            if "provider" in backoff_state:
                val = backoff_state.get("provider")
                if not isinstance(val, str) or val.strip() == "":
                    v.add("INVALID_VALUE", f"{path}/provider_backoff_state/provider", "Must be a non-empty string", phase="value")
            if "model_id" in backoff_state:
                val = backoff_state.get("model_id")
                if not isinstance(val, str) or val.strip() == "":
                    v.add("INVALID_VALUE", f"{path}/provider_backoff_state/model_id", "Must be a non-empty string", phase="value")
            if "state" in backoff_state:
                v.check_enum(backoff_state.get("state"), CAPACITY_STATES, f"{path}/provider_backoff_state/state")
            if "reset_at" in backoff_state:
                reset_at = backoff_state.get("reset_at")
                if reset_at is not None and not _matches(reset_at, RE_RFC3339):
                    v.add("INVALID_FORMAT", f"{path}/provider_backoff_state/reset_at", "Must be RFC3339 UTC timestamp or null", phase="format")

    stop_reasons = row.get("stop_reasons")
    if not isinstance(stop_reasons, list):
        v.add("INVALID_TYPE", f"{path}/stop_reasons", "Expected array", phase="scalar")
    else:
        for i, reason in enumerate(stop_reasons):
            if not isinstance(reason, str) or reason.strip() == "":
                v.add("INVALID_VALUE", f"{path}/stop_reasons/{i}", "Must be a non-empty string", phase="value")

    disposition = row.get("disposition")
    if disposition is not None and disposition not in PLAN_DISPOSITIONS:
        v.add("INVALID_ENUM", f"{path}/disposition", f"Value must be one of {sorted(PLAN_DISPOSITIONS)} or null")


def _validate_plan_totals(v: _PacketValidator, value: Any, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object or null", phase="scalar")
        return
    for key in value:
        if key not in PLAN_TOTAL_KEYS:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in PLAN_TOTAL_KEYS:
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        else:
            val = value[key]
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                v.add("INVALID_VALUE", f"{path}/{key}", "Must be a non-negative integer", phase="value")


def _validate_activity(v: _PacketValidator, activity: Any, path: str) -> None:
    if not isinstance(activity, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {
        "attempts_started_total",
        "infra_retries_total",
        "revise_verdicts_total",
        "revise_cycles_total",
        "reassignments_total",
        "results_recorded_total",
        "verdicts_recorded_total",
        "intents_abandoned_total",
        "locks_reclaimed_total",
    }
    for key in activity:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in activity:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        else:
            val = activity[key]
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                v.add("INVALID_VALUE", f"{path}/{key}", "Must be a non-negative integer", phase="value")


def _validate_attention_required(v: _PacketValidator, attention: Any, path: str) -> None:
    if not isinstance(attention, list):
        v.add("INVALID_TYPE", path, "Expected array", phase="scalar")
        return
    for i, item in enumerate(attention):
        p = f"{path}/{i}"
        if not isinstance(item, dict):
            v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
            continue
        for key in ("packet_id", "code", "detail"):
            if key not in item:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        if "packet_id" in item and item["packet_id"] is not None and (not isinstance(item["packet_id"], str) or item["packet_id"].strip() == ""):
            v.add("INVALID_VALUE", f"{p}/packet_id", "packet_id must be a non-empty string or null", phase="value")
        for key in ("code", "detail"):
            if key in item and (not isinstance(item[key], str) or item[key].strip() == ""):
                v.add("INVALID_VALUE", f"{p}/{key}", f"{key} must be a non-empty string", phase="value")
        for key in item:
            if key not in {"packet_id", "code", "detail"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")


def _validate_integrity(v: _PacketValidator, integrity: Any, path: str) -> None:
    if not isinstance(integrity, dict):
        v.add("INVALID_TYPE", path, "Expected object", phase="scalar")
        return
    required = {
        "journal_chain_valid",
        "state_cache_in_sync",
        "duplicate_packet_ids",
        "omitted_packet_ids",
        "unenrolled_dependencies",
        "seal_mismatches",
        "accounting_violations",
        "preserved_evidence_mismatches",
    }
    for key in integrity:
        if key not in required:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in integrity:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
        elif key == "journal_chain_valid" or key == "state_cache_in_sync":
            if not isinstance(integrity[key], bool):
                v.add("INVALID_TYPE", f"{path}/{key}", "Expected boolean", phase="scalar")
        else:
            arr = integrity[key]
            if not isinstance(arr, list):
                v.add("INVALID_TYPE", f"{path}/{key}", "Expected array", phase="scalar")


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
        return False
    return True


def compute_reconciliation(fold_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a reconciliation report from folded journal data.

    ``fold_data`` must contain:
      - journal_head: {seq, event_sha256}
      - packets: list of per-packet rows
      - activity: activity counters
      - integrity: pre-computed integrity issue lists
      - attention_required: list of attention items
      - enrolled_packet_ids: Set[str] of PACKET_ENROLLED packet_ids (required for I5)

    O5 Task 5 additions, both OPTIONAL -- a caller that supplies neither gets
    byte-for-byte the pre-O5 behaviour this function always had:
      - plan_scope: {"bound": bool, "planned_packet_ids": List[str],
        "authentication_error": Optional[str]}. ``bound`` False (the
        default) means no execution plan governs this run; ``plan_totals``/
        ``attempted_packet_ids`` are then reported as ``None`` and no O5
        check runs. ``authentication_error`` set means the bound plan
        itself failed authentication (e.g. a corrupted/cyclic artifact) --
        this is reported as its own attention item and fails the run's O5
        invariant closed without attempting a partition.
      - o5_violations: List[{"packet_id": Optional[str], "code": str,
        "detail": str}], precomputed by the caller (reconcile.py) for every
        O5-specific fail-closed finding this engine does not itself derive
        (route-not-authorized reassignments, budget-limit overruns, foreign/
        missing plan members, forged evidence references, and so on).
      - workspace_attention: List[dict], precomputed by the caller
        (reconcile.py's ``_workspace_evidence_attention``) for every O4
        workspace-isolation finding (missing baseline/postflight, allowlist
        violation, secret-like diff, protected-worktree change). A non-empty
        list here fails ``all_invariants_passed`` closed, exactly like
        ``o5_violations`` -- this is the SAME computation that feeds both
        ``reconciliation.all_invariants_passed`` and the top-level mirror
        field below, so the two can never disagree by construction. This
        replaces a prior design where the caller overrode only the nested
        field AFTER calling this function, which let the top-level mirror
        go stale whenever workspace_attention alone was the failing
        condition -- do not reintroduce a second, out-of-band override site.

    Each row in ``packets`` is expected to already carry Task 5's row
    extension (``plan_id``, ``plan_sha256``, ``capability_class``,
    ``route_history``, ``budget_usage``, ``provider_backoff_state``,
    ``stop_reasons``, ``disposition``) -- this engine reads ``disposition``
    and ``attempts_started`` to build ``plan_totals`` but does not itself
    derive the other extension fields (that is reconcile.py's assembly
    job, not this invariant engine's). Any row missing one of these keys is
    defensively backfilled to its null/empty default here, so a caller that
    predates O5 (or a hand-built test fixture) still gets a schema-valid,
    O5-shaped report rather than a KeyError or a report the JSON Schema
    would reject.
    """
    packets = list(fold_data.get("packets") or [])
    _O5_ROW_DEFAULTS = {
        "plan_id": None, "plan_sha256": None, "capability_class": None,
        "route_history": [], "budget_usage": None, "provider_backoff_state": None,
        "stop_reasons": [], "disposition": None,
    }
    for row in packets:
        for key, default in _O5_ROW_DEFAULTS.items():
            row.setdefault(key, default)
    inventory_total = len(packets)

    # I7: all eight states present, even at zero.
    by_state: Dict[str, int] = {state: 0 for state in PACKET_STATES}
    for row in packets:
        state = row.get("state")
        if state in PACKET_STATES:
            by_state[state] += 1

    enrolled_ids: Set[str] = set(fold_data.get("enrolled_packet_ids") or [])
    row_ids: Set[str] = set()
    duplicate_ids: List[str] = []
    for row in packets:
        pid = row.get("packet_id")
        if pid in row_ids:
            if pid not in duplicate_ids:
                duplicate_ids.append(pid)
        else:
            row_ids.add(pid)

    # I4 / I5: duplicate and omitted/invented packet ids.
    omitted_ids: List[str] = sorted((enrolled_ids - row_ids) | (row_ids - enrolled_ids))

    integrity_input = fold_data.get("integrity") or {}
    integrity = {
        "journal_chain_valid": bool(integrity_input.get("journal_chain_valid", True)),
        "state_cache_in_sync": bool(integrity_input.get("state_cache_in_sync", True)),
        "duplicate_packet_ids": sorted(set(integrity_input.get("duplicate_packet_ids", []) or []) | set(duplicate_ids)),
        "omitted_packet_ids": sorted(set(integrity_input.get("omitted_packet_ids", []) or []) | set(omitted_ids)),
        "unenrolled_dependencies": sorted(set(integrity_input.get("unenrolled_dependencies", []) or [])),
        "seal_mismatches": sorted(set(integrity_input.get("seal_mismatches", []) or [])),
        "accounting_violations": sorted(set(integrity_input.get("accounting_violations", []) or [])),
        "preserved_evidence_mismatches": sorted(set(integrity_input.get("preserved_evidence_mismatches", []) or [])),
    }

    attention_required: List[Dict[str, Any]] = list(fold_data.get("attention_required") or [])

    # I9 accounting identity
    for row in packets:
        pid = row.get("packet_id")
        attempts = row.get("attempts_started", 0)
        infra = row.get("infra_retries_used", 0)
        revise = row.get("revise_cycles_used", 0)
        reassigned = 1 if row.get("reassignment_used") else 0
        if attempts >= 1 and infra + revise + reassigned != attempts - 1:
            if pid not in integrity["accounting_violations"]:
                integrity["accounting_violations"].append(pid)
            attention_required.append({"packet_id": pid, "code": "accounting_identity_violation", "detail": "infra + revise + reassign != attempts_started - 1"})

    # I10: per-packet retry budget
    for row in packets:
        pid = row.get("packet_id")
        attempts = row.get("attempts_started", 0)
        retry_limit = row.get("retry_limit")
        if isinstance(retry_limit, int) and not isinstance(retry_limit, bool) and attempts > retry_limit + 1:
            if pid not in integrity["accounting_violations"]:
                integrity["accounting_violations"].append(pid)
            attention_required.append({"packet_id": pid, "code": "retry_budget_exceeded", "detail": "attempts_started > retry_limit + 1"})

    # O5 Task 5: plan-scoped terminal-disposition partition. Disjoint from
    # I1-I12 above -- those concern fold-level bookkeeping identities that
    # hold whether or not any execution plan is bound; this concerns
    # whether every PLAN MEMBER packet has reached exactly one closed
    # terminal disposition. See ``PLAN_DISPOSITIONS``'s module docstring for
    # why a packet with no resolvable disposition is left OUT of every
    # bucket (a sum shortfall against ``planned``) rather than guessed into
    # one -- that is what "fails closed" means for this specific invariant.
    plan_scope = fold_data.get("plan_scope") or {}
    plan_bound = bool(plan_scope.get("bound"))
    plan_totals: Optional[Dict[str, int]] = None
    attempted_packet_ids: Optional[List[str]] = None
    o5_ok = True

    if plan_bound:
        authentication_error = plan_scope.get("authentication_error")
        if authentication_error:
            o5_ok = False
            attention_required.append({
                "packet_id": None, "code": "plan_identity_invalid",
                "detail": str(authentication_error),
            })
        else:
            planned_ids = sorted(set(plan_scope.get("planned_packet_ids") or []))
            rows_by_id = {row.get("packet_id"): row for row in packets}
            totals = {key: 0 for key in PLAN_TOTAL_KEYS}
            totals["planned"] = len(planned_ids)
            attempted_ids_list: List[str] = []
            for pid in planned_ids:
                row = rows_by_id.get(pid)
                if row is None:
                    # A declared plan member with no fold row at all (never
                    # enrolled) is not "never_started" -- that means known
                    # but not yet worked on. It is its own, worse finding
                    # (the caller is expected to have already appended a
                    # ``plan_member_never_enrolled`` item to o5_violations);
                    # here it simply contributes to no bucket, so the sum
                    # invariant below reports the shortfall on its own.
                    continue
                if row.get("attempts_started", 0) > 0:
                    attempted_ids_list.append(pid)
                disposition = row.get("disposition")
                if disposition in PLAN_DISPOSITIONS:
                    totals[disposition] += 1
            attempted_packet_ids = sorted(attempted_ids_list)
            totals["attempted"] = len(attempted_packet_ids)
            six_way_sum = sum(
                totals[key] for key in (
                    "accepted", "resting_revise", "quarantined",
                    "paused_provider", "blocked_human", "never_started",
                )
            )
            if six_way_sum != totals["planned"]:
                o5_ok = False
                attention_required.append({
                    "packet_id": None, "code": "plan_disposition_partition_incomplete",
                    "detail": (
                        "sum of accepted+resting_revise+quarantined+paused_provider"
                        "+blocked_human+never_started (%d) != planned (%d)"
                        % (six_way_sum, totals["planned"])
                    ),
                })
            plan_totals = totals

        o5_violations = list(fold_data.get("o5_violations") or [])
        if o5_violations:
            o5_ok = False
            for item in o5_violations:
                attention_required.append(dict(item))

    # O4 workspace-isolation findings (missing baseline/postflight, allowlist
    # violation, secret-like diff, protected-worktree change). This list is
    # already folded into ``attention_required`` by the caller before this
    # function runs; it is read again here, separately, so its presence can
    # participate in the SAME ``all_invariants_passed`` computation that
    # feeds both the nested and top-level fields below -- see this
    # function's docstring for why that single-computation shape is
    # required, not merely tidy.
    workspace_attention = list(fold_data.get("workspace_attention") or [])
    workspace_ok = not workspace_attention

    all_invariants_passed = (
        sum(by_state.values()) == inventory_total
        and len(packets) == inventory_total
        and len(row_ids) == inventory_total
        and not duplicate_ids
        and not omitted_ids
        and integrity["journal_chain_valid"]
        and integrity["state_cache_in_sync"]
        and not integrity["duplicate_packet_ids"]
        and not integrity["omitted_packet_ids"]
        and not integrity["unenrolled_dependencies"]
        and not integrity["seal_mismatches"]
        and not integrity["accounting_violations"]
        and not integrity["preserved_evidence_mismatches"]
        and o5_ok
        and workspace_ok
    )

    report = {
        "schema_version": 1,
        "report_id": fold_data.get("report_id", ""),
        "generated_at": fold_data.get("generated_at", ""),
        "coordinator_id": fold_data.get("coordinator_id", ""),
        "run_id": fold_data.get("run_id", ""),
        "state_root_id": fold_data.get("state_root_id", ""),
        "journal_head": dict(fold_data.get("journal_head") or {"seq": 0, "event_sha256": "0" * 64}),
        "inventory_total": inventory_total,
        "by_state": by_state,
        "packets": packets,
        "activity": dict(fold_data.get("activity") or {}),
        "attention_required": attention_required,
        "integrity": integrity,
        "reconciliation": {
            "sum_of_by_state": sum(by_state.values()),
            "packets_array_length": len(packets),
            "distinct_packet_ids": len(row_ids),
            "equals_inventory_total": sum(by_state.values()) == inventory_total and len(packets) == inventory_total and len(row_ids) == inventory_total,
            "all_invariants_passed": all_invariants_passed,
        },
        "plan_totals": plan_totals,
        "attempted_packet_ids": attempted_packet_ids,
        # Top-level mirror of the SAME value computed above -- single source
        # of truth (this assignment), never a second independent
        # computation. Existing callers reading the nested
        # ``reconciliation.all_invariants_passed`` field are completely
        # unaffected; this exists so a caller that only wants "did
        # everything check out, O5 included" can read one flat field.
        "all_invariants_passed": all_invariants_passed,
    }

    report["content_sha256"] = compute_sha256(
        canonical_bytes(
            report,
            omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
        )
    )
    report["report_sha256"] = compute_sha256(canonical_bytes(report, omit={"report_sha256"}))
    return report
