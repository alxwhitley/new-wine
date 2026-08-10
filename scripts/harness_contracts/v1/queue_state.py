"""Queue state projection validation for harness contract v1 O3."""

import json
from typing import Any, Dict, List, Optional

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import LANES, PACKET_STATES, RE_SHA256, _matches, _PacketValidator
from harness_contracts.v1.worker_result import RE_RFC3339

ZERO_SHA256 = "0" * 64


def _check_int(v: _PacketValidator, value: Any, path: str, min_value: Optional[int] = None, nonneg: bool = False) -> bool:
    if isinstance(value, bool):
        v.add("INVALID_TYPE", path, "Expected integer, not boolean", phase="scalar")
        return False
    if not isinstance(value, int):
        v.add("INVALID_TYPE", path, "Expected integer", phase="scalar")
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


def _check_rfc3339_or_null(v: _PacketValidator, value: Any, path: str) -> bool:
    if value is None:
        return True
    if not _matches(value, RE_RFC3339):
        v.add("INVALID_FORMAT", path, "Must be RFC3339 UTC timestamp ending in Z or null", phase="format")
        return False
    return True


def validate_queue(value: Any, state_root_id: Optional[str] = None) -> Dict[str, Any]:
    """Validate a queue.json projection."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Queue root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_queue_object(v, state_root_id=state_root_id)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_queue_object(v: _PacketValidator, state_root_id: Optional[str]) -> None:
    allowed = {"schema_version", "state_root_id", "derived_from", "entries", "pending_intents", "queue_sha256"}
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

    srid = value.get("state_root_id")
    if not isinstance(srid, str) or srid.strip() == "":
        v.add("INVALID_VALUE", "/state_root_id", "state_root_id must be a non-empty string", phase="value")
    elif state_root_id is not None and srid != state_root_id:
        v.add("EVIDENCE_HASH_MISMATCH", "/state_root_id", "state_root_id does not match manifest", phase="cross_field")

    derived_from = value.get("derived_from")
    if not isinstance(derived_from, dict):
        v.add("INVALID_TYPE", "/derived_from", "Expected object", phase="scalar")
    else:
        for key in ("journal_last_seq", "journal_last_event_sha256"):
            if key not in derived_from:
                v.add("MISSING_FIELD", f"/derived_from/{key}", f"Missing required field '{key}'")
        if "journal_last_seq" in derived_from:
            _check_int(v, derived_from["journal_last_seq"], "/derived_from/journal_last_seq", nonneg=True)
        if "journal_last_event_sha256" in derived_from:
            val = derived_from["journal_last_event_sha256"]
            if val != ZERO_SHA256 and not _matches(val, RE_SHA256):
                v.add("INVALID_FORMAT", "/derived_from/journal_last_event_sha256", "Must be 64-character lowercase SHA-256 hex or 64 zeros", phase="format")
        for key in derived_from:
            if key not in {"journal_last_seq", "journal_last_event_sha256"}:
                v.add("UNKNOWN_FIELD", f"/derived_from/{key}", f"Unknown field '{key}'")

    entries = value.get("entries")
    if not isinstance(entries, list):
        v.add("INVALID_TYPE", "/entries", "Expected array", phase="scalar")
    else:
        _validate_entries(v, entries)

    pending_intents = value.get("pending_intents")
    if not isinstance(pending_intents, list):
        v.add("INVALID_TYPE", "/pending_intents", "Expected array", phase="scalar")
    else:
        _validate_pending_intents(v, pending_intents)

    declared = value.get("queue_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"queue_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/queue_sha256", "queue_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/queue_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")


def _validate_entries(v: _PacketValidator, entries: List[Any]) -> None:
    seen_packet_ids: set = set()
    seen_enqueue_seqs: set = set()
    prev_enqueue_seq: Optional[int] = None

    required = {
        "packet_id",
        "enqueue_seq",
        "state",
        "lane",
        "dependency_ids",
        "packet_sha256",
        "attempts_started",
        "infra_retries_used",
        "revise_cycles_used",
        "revise_verdicts",
        "reassignment_used",
        "open_attempt",
        "earliest_next_attempt_at",
        "last_event_seq",
        "terminal_seal_sha256",
    }

    for i, entry in enumerate(entries):
        p = f"/entries/{i}"
        if not isinstance(entry, dict):
            v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
            continue
        for key in entry:
            if key not in required:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        for key in required:
            if key not in entry:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        if v.errors:
            # Only report structural errors for this entry; clear per-entry to allow continuing.
            pass

        packet_id = entry.get("packet_id")
        if isinstance(packet_id, str) and packet_id.strip() != "":
            if packet_id in seen_packet_ids:
                v.add("DUPLICATE_ID", f"{p}/packet_id", "Duplicate packet_id in entries", phase="uniqueness")
            seen_packet_ids.add(packet_id)
        elif packet_id is not None:
            v.add("INVALID_VALUE", f"{p}/packet_id", "packet_id must be a non-empty string", phase="value")

        enqueue_seq = entry.get("enqueue_seq")
        if _check_int(v, enqueue_seq, f"{p}/enqueue_seq", min_value=1):
            if enqueue_seq in seen_enqueue_seqs:
                v.add("DUPLICATE_ID", f"{p}/enqueue_seq", "Duplicate enqueue_seq in entries", phase="uniqueness")
            seen_enqueue_seqs.add(enqueue_seq)
            if prev_enqueue_seq is not None and enqueue_seq <= prev_enqueue_seq:
                v.add("INVALID_VALUE", f"{p}/enqueue_seq", "entries must be sorted ascending by enqueue_seq", phase="value")
            prev_enqueue_seq = enqueue_seq

        v.check_enum(entry.get("state"), PACKET_STATES, f"{p}/state")
        v.check_enum(entry.get("lane"), LANES, f"{p}/lane")

        deps = entry.get("dependency_ids")
        if not isinstance(deps, list):
            v.add("INVALID_TYPE", f"{p}/dependency_ids", "Expected array", phase="scalar")
        else:
            for j, dep in enumerate(deps):
                if not isinstance(dep, str) or dep.strip() == "":
                    v.add("INVALID_VALUE", f"{p}/dependency_ids/{j}", "Dependency ID must be a non-empty string", phase="value")

        if not _matches(entry.get("packet_sha256"), RE_SHA256):
            v.add("INVALID_FORMAT", f"{p}/packet_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")

        _check_int(v, entry.get("attempts_started"), f"{p}/attempts_started", nonneg=True)
        _check_int(v, entry.get("infra_retries_used"), f"{p}/infra_retries_used", nonneg=True)
        _check_int(v, entry.get("revise_cycles_used"), f"{p}/revise_cycles_used", nonneg=True)
        _check_int(v, entry.get("revise_verdicts"), f"{p}/revise_verdicts", nonneg=True)

        if not isinstance(entry.get("reassignment_used"), bool):
            v.add("INVALID_TYPE", f"{p}/reassignment_used", "Expected boolean", phase="scalar")

        open_attempt = entry.get("open_attempt")
        if open_attempt is not None and not _check_int(v, open_attempt, f"{p}/open_attempt", min_value=1):
            pass

        _check_rfc3339_or_null(v, entry.get("earliest_next_attempt_at"), f"{p}/earliest_next_attempt_at")
        _check_int(v, entry.get("last_event_seq"), f"{p}/last_event_seq", min_value=1)

        tss = entry.get("terminal_seal_sha256")
        if tss is not None and not _matches(tss, RE_SHA256):
            v.add("INVALID_FORMAT", f"{p}/terminal_seal_sha256", "Must be 64-character lowercase SHA-256 hex or null", phase="format")


def _validate_pending_intents(v: _PacketValidator, pending_intents: List[Any]) -> None:
    seen_intent_ids: set = set()
    seen_packet_ids: set = set()
    stages = {
        "enrollment",
        "claim",
        "result_record",
        "attempt_finish",
        "review_claim",
        "verdict_record",
        "promotion",
    }

    required = {"intent_id", "packet_id", "stage", "created_at", "coordinator_id", "run_id", "boot_id", "pid"}

    for i, intent in enumerate(pending_intents):
        p = f"/pending_intents/{i}"
        if not isinstance(intent, dict):
            v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
            continue
        for key in intent:
            if key not in required:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        for key in required:
            if key not in intent:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")

        intent_id = intent.get("intent_id")
        if isinstance(intent_id, str) and intent_id.strip() != "":
            if intent_id in seen_intent_ids:
                v.add("DUPLICATE_ID", f"{p}/intent_id", "Duplicate intent_id", phase="uniqueness")
            seen_intent_ids.add(intent_id)
        elif intent_id is not None:
            v.add("INVALID_VALUE", f"{p}/intent_id", "intent_id must be a non-empty string", phase="value")

        packet_id = intent.get("packet_id")
        if isinstance(packet_id, str) and packet_id.strip() != "":
            if packet_id in seen_packet_ids:
                v.add("CLAIM_CONFLICT", f"{p}/packet_id", "At most one pending intent per packet_id", phase="uniqueness")
            seen_packet_ids.add(packet_id)
        elif packet_id is not None:
            v.add("INVALID_VALUE", f"{p}/packet_id", "packet_id must be a non-empty string", phase="value")

        v.check_enum(intent.get("stage"), stages, f"{p}/stage")

        for field in ("created_at",):
            val = intent.get(field)
            if val is not None and not _matches(val, RE_RFC3339):
                v.add("INVALID_FORMAT", f"{p}/{field}", "Must be RFC3339 UTC timestamp ending in Z", phase="format")

        for field in ("coordinator_id", "run_id", "boot_id"):
            val = intent.get(field)
            if not isinstance(val, str) or val.strip() == "":
                v.add("INVALID_VALUE", f"{p}/{field}", f"{field} must be a non-empty string", phase="value")

        pid = intent.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int):
            v.add("INVALID_TYPE", f"{p}/pid", "Expected integer", phase="scalar")
        elif pid < 1:
            v.add("INVALID_VALUE", f"{p}/pid", "pid must be a positive integer", phase="value")
