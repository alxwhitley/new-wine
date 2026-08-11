"""Provider exhaustion evidence and signal registry validation for O3."""

import hashlib
import json
from typing import Any, Dict, List, Optional

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import RE_SHA256, _matches, _normalize_relative_path, _PacketValidator, is_repo_relative_path
from harness_contracts.v1.worker_result import RE_RFC3339, FALLBACK_REASONS


CLASSIFICATIONS = {
    "CONFIRMED_QUOTA_EXHAUSTION",
    "CONFIRMED_RATE_LIMIT_EXHAUSTION",
    "NOT_EXHAUSTION",
}

CHANNELS = {"stdout", "stderr"}
MATCH_KINDS = {"substring", "exit_code"}

# O5 provider capacity observation.  Subscriptions are capacity-constrained
# services, so the authenticated evidence path records OBSERVED PROVIDER
# STATE -- never an estimated dollar spend, and never anything that could
# carry a secret.  The field set below is closed on purpose: raw headers,
# credentials, response bodies, subscription identifiers, and prompt content
# have no representable slot here, so they cannot be persisted even by a
# caller that wants to.
CAPACITY_STATES = {
    "AVAILABLE",
    "RATE_LIMITED",
    "ALLOWANCE_EXHAUSTED",
    "UNAVAILABLE",
}

CAPACITY_OBSERVATION_FIELDS = {
    "provider",
    "model_id",
    "state",
    "observed_at",
    "reset_at",
    "evidence_sha256",
}

# An exact provider model identifier, in canonical lowercase form.  Aliases
# and catalog display names cannot match, so a runtime catalog rename can
# never resolve onto a plan-pinned route.  ``execution_plan._MODEL_ID`` is
# the same expression for the same reason; consolidate the two the next time
# that module is in scope.
RE_MODEL_ID = r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$"

REASON_TO_CLASSIFICATION = {
    "confirmed_quota_exhaustion": "CONFIRMED_QUOTA_EXHAUSTION",
    "confirmed_rate_limit_exhaustion": "CONFIRMED_RATE_LIMIT_EXHAUSTION",
}

CLASSIFICATION_TO_REASON = {v: k for k, v in REASON_TO_CLASSIFICATION.items()}


def _check_non_empty_string(v: _PacketValidator, value: Any, path: str) -> bool:
    if not isinstance(value, str):
        v.add("INVALID_TYPE", path, "Expected string", phase="scalar")
        return False
    if value.strip() == "":
        v.add("INVALID_VALUE", path, "Empty or whitespace-only string", phase="value")
        return False
    return True


def _check_sha256(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_SHA256):
        v.add("INVALID_FORMAT", path, "Must be 64-character lowercase SHA-256 hex", phase="format")
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


def _check_rfc3339(v: _PacketValidator, value: Any, path: str) -> bool:
    if not _matches(value, RE_RFC3339):
        v.add("INVALID_FORMAT", path, "Must be RFC3339 UTC timestamp ending in Z", phase="format")
        return False
    return True


def validate_provider_evidence(value: Any) -> Dict[str, Any]:
    """Validate a provider-evidence record."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Provider evidence root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_provider_evidence_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def validate_provider_capacity_observation(value: Any) -> Dict[str, Any]:
    """Validate one closed, authenticated provider capacity observation.

    This is the only shape through which observed provider capacity may enter
    the coordinator.  Worker prose, stderr text, and guessed reset times are
    untrusted and have no representation here: a reset time is accepted only
    as an explicit ``reset_at``, and ``null`` means "no authenticated reset
    time exists", never "assume one".
    """
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Capacity observation root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_capacity_observation_object(v, value, "")
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_capacity_observation_object(v: _PacketValidator, observation: Any, path: str) -> None:
    """Collect capacity-observation errors into ``v`` at ``path``."""
    if not isinstance(observation, dict):
        v.add("INVALID_TYPE", path or "/", "Expected object", phase="scalar")
        return
    for key in observation:
        if key not in CAPACITY_OBSERVATION_FIELDS:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    for key in CAPACITY_OBSERVATION_FIELDS:
        if key not in observation:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    _check_non_empty_string(v, observation.get("provider"), f"{path}/provider")
    model_id = observation.get("model_id")
    if not _matches(model_id, RE_MODEL_ID):
        v.add("INVALID_FORMAT", f"{path}/model_id", "model_id must be a canonical lowercase model identifier", phase="format")
    v.check_enum(observation.get("state"), CAPACITY_STATES, f"{path}/state")
    _check_rfc3339(v, observation.get("observed_at"), f"{path}/observed_at")
    reset_at = observation.get("reset_at")
    if reset_at is not None:
        _check_rfc3339(v, reset_at, f"{path}/reset_at")
    _check_sha256(v, observation.get("evidence_sha256"), f"{path}/evidence_sha256")

    observed_at = observation.get("observed_at")
    if (_matches(observed_at, RE_RFC3339) and _matches(reset_at, RE_RFC3339)
            and reset_at < observed_at):
        v.add(
            "CHRONOLOGY_VIOLATION",
            f"{path}/reset_at",
            "reset_at must not precede observed_at",
            phase="cross_field",
        )


def _validate_provider_evidence_object(v: _PacketValidator) -> None:
    required = {
        "schema_version",
        "evidence_id",
        "packet_id",
        "attempt",
        "provider",
        "captured_by",
        "invocation",
        "stdout_path",
        "stdout_sha256",
        "stderr_path",
        "stderr_sha256",
        "matched_signal",
        "classification",
        "evidence_sha256",
    }
    # ``capacity`` is optional so every pre-O5 evidence record stays valid;
    # when present it must be the same closed observation the journal records.
    allowed = required | {"capacity"}
    value = v.value
    for key in value:
        if key not in allowed:
            v.add("UNKNOWN_FIELD", f"/{key}", f"Unknown field '{key}'")
    for key in required:
        if key not in value:
            v.add("MISSING_FIELD", f"/{key}", f"Missing required field '{key}'")
    if v.errors:
        return

    if "capacity" in value and value.get("capacity") is not None:
        _validate_capacity_observation_object(v, value["capacity"], "/capacity")

    if value.get("schema_version") != 1:
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1", phase="value")

    for field in ("evidence_id", "packet_id", "provider", "stdout_path", "stderr_path"):
        _check_non_empty_string(v, value.get(field), f"/{field}")

    for field in ("stdout_path", "stderr_path"):
        p = value.get(field)
        if isinstance(p, str) and p.strip() != "":
            _check_repo_relative_path(v, p, f"/{field}")

    for field in ("stdout_sha256", "stderr_sha256"):
        _check_sha256(v, value.get(field), f"/{field}")

    attempt = value.get("attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        v.add("INVALID_TYPE", "/attempt", "Expected integer", phase="scalar")
    elif attempt < 1:
        v.add("INVALID_VALUE", "/attempt", "attempt must be a positive integer", phase="value")

    captured_by = value.get("captured_by")
    if not isinstance(captured_by, dict):
        v.add("INVALID_TYPE", "/captured_by", "Expected object", phase="scalar")
    else:
        for key in ("role", "coordinator_id", "boot_id", "hostname", "run_id"):
            if key not in captured_by:
                v.add("MISSING_FIELD", f"/captured_by/{key}", f"Missing required field '{key}'")
            elif key == "role":
                if captured_by[key] != "coordinator":
                    v.add("INVALID_VALUE", f"/captured_by/{key}", "role must be 'coordinator'", phase="value")
            else:
                _check_non_empty_string(v, captured_by[key], f"/captured_by/{key}")
        for key in captured_by:
            if key not in {"role", "coordinator_id", "boot_id", "hostname", "run_id"}:
                v.add("UNKNOWN_FIELD", f"/captured_by/{key}", f"Unknown field '{key}'")

    invocation = value.get("invocation")
    if not isinstance(invocation, dict):
        v.add("INVALID_TYPE", "/invocation", "Expected object", phase="scalar")
    else:
        for key in ("argv", "exit_code", "signal", "started_at", "finished_at", "timed_out"):
            if key not in invocation:
                v.add("MISSING_FIELD", f"/invocation/{key}", f"Missing required field '{key}'")
        argv = invocation.get("argv")
        if not isinstance(argv, list) or len(argv) == 0:
            v.add("INVALID_VALUE", "/invocation/argv", "argv must be a non-empty array", phase="value")
        else:
            for i, arg in enumerate(argv):
                if not isinstance(arg, str):
                    v.add("INVALID_TYPE", f"/invocation/argv/{i}", "argv elements must be strings", phase="scalar")
        ec = invocation.get("exit_code")
        if ec is not None and (isinstance(ec, bool) or not isinstance(ec, int)):
            v.add("INVALID_TYPE", "/invocation/exit_code", "Expected integer or null", phase="scalar")
        sig = invocation.get("signal")
        if sig is not None and (isinstance(sig, bool) or not isinstance(sig, int)):
            v.add("INVALID_TYPE", "/invocation/signal", "Expected integer or null", phase="scalar")
        _check_rfc3339(v, invocation.get("started_at"), "/invocation/started_at")
        _check_rfc3339(v, invocation.get("finished_at"), "/invocation/finished_at")
        if not isinstance(invocation.get("timed_out"), bool):
            v.add("INVALID_TYPE", "/invocation/timed_out", "Expected boolean", phase="scalar")
        for key in invocation:
            if key not in {"argv", "exit_code", "signal", "started_at", "finished_at", "timed_out"}:
                v.add("UNKNOWN_FIELD", f"/invocation/{key}", f"Unknown field '{key}'")

    matched_signal = value.get("matched_signal")
    if matched_signal is not None:
        if not isinstance(matched_signal, dict):
            v.add("INVALID_TYPE", "/matched_signal", "Expected object or null", phase="scalar")
        else:
            for key in ("channel", "rule_id", "registry_id", "verbatim_excerpt", "byte_offset", "byte_length"):
                if key not in matched_signal:
                    v.add("MISSING_FIELD", f"/matched_signal/{key}", f"Missing required field '{key}'")
            v.check_enum(matched_signal.get("channel"), CHANNELS, "/matched_signal/channel")
            for key in ("rule_id", "registry_id"):
                _check_non_empty_string(v, matched_signal.get(key), f"/matched_signal/{key}")
            _check_non_empty_string(v, matched_signal.get("verbatim_excerpt"), "/matched_signal/verbatim_excerpt")
            offset = matched_signal.get("byte_offset")
            if isinstance(offset, bool) or not isinstance(offset, int):
                v.add("INVALID_TYPE", "/matched_signal/byte_offset", "Expected integer", phase="scalar")
            elif offset < 0:
                v.add("INVALID_VALUE", "/matched_signal/byte_offset", "Must be a non-negative integer", phase="value")
            length = matched_signal.get("byte_length")
            if isinstance(length, bool) or not isinstance(length, int):
                v.add("INVALID_TYPE", "/matched_signal/byte_length", "Expected integer", phase="scalar")
            elif length < 1:
                v.add("INVALID_VALUE", "/matched_signal/byte_length", "Must be a positive integer", phase="value")
            for key in matched_signal:
                if key not in {"channel", "rule_id", "registry_id", "verbatim_excerpt", "byte_offset", "byte_length"}:
                    v.add("UNKNOWN_FIELD", f"/matched_signal/{key}", f"Unknown field '{key}'")

    v.check_enum(value.get("classification"), CLASSIFICATIONS, "/classification")

    declared = value.get("evidence_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"evidence_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/evidence_sha256", "evidence_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/evidence_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")


def validate_provider_signals_registry(value: Any) -> Dict[str, Any]:
    """Validate the pinned provider-signals registry."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}", phase="json_decode")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Provider signals registry root is not an object", phase="root_type")])

    v = _PacketValidator(value)
    _validate_provider_signals_registry_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_provider_signals_registry_object(v: _PacketValidator) -> None:
    allowed = {"schema_version", "registry_id", "providers", "registry_sha256"}
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

    _check_non_empty_string(v, value.get("registry_id"), "/registry_id")

    providers = value.get("providers")
    if not isinstance(providers, dict):
        v.add("INVALID_TYPE", "/providers", "Expected object", phase="scalar")
    else:
        for provider, rules in providers.items():
            if not isinstance(provider, str) or provider.strip() == "":
                v.add("INVALID_VALUE", f"/providers/{provider}", "Provider key must be a non-empty string", phase="value")
            if not isinstance(rules, list):
                v.add("INVALID_TYPE", f"/providers/{provider}", "Expected array of rules", phase="scalar")
                continue
            seen_rule_ids: set = set()
            for i, rule in enumerate(rules):
                p = f"/providers/{provider}/{i}"
                if not isinstance(rule, dict):
                    v.add("INVALID_TYPE", p, "Expected object", phase="scalar")
                    continue
                for key in ("rule_id", "channel", "match_kind", "pattern", "exit_code", "classification", "captured_from"):
                    if key not in rule:
                        v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
                if "rule_id" in rule:
                    rid = rule["rule_id"]
                    if not isinstance(rid, str) or rid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/rule_id", "rule_id must be a non-empty string", phase="value")
                    elif rid in seen_rule_ids:
                        v.add("DUPLICATE_ID", f"{p}/rule_id", "Duplicate rule_id for provider", phase="uniqueness")
                    else:
                        seen_rule_ids.add(rid)
                v.check_enum(rule.get("channel"), CHANNELS, f"{p}/channel")
                v.check_enum(rule.get("match_kind"), MATCH_KINDS, f"{p}/match_kind")
                v.check_enum(rule.get("classification"), CLASSIFICATIONS, f"{p}/classification")

                match_kind = rule.get("match_kind")
                pattern = rule.get("pattern")
                exit_code = rule.get("exit_code")
                if match_kind == "substring":
                    if not isinstance(pattern, str) or pattern.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/pattern", "substring pattern must be a non-empty string", phase="value")
                    if exit_code is not None:
                        v.add("INVALID_VALUE", f"{p}/exit_code", "exit_code must be null for substring match", phase="value")
                elif match_kind == "exit_code":
                    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
                        v.add("INVALID_TYPE", f"{p}/exit_code", "Expected integer for exit_code match", phase="scalar")
                    if pattern is not None:
                        v.add("INVALID_VALUE", f"{p}/pattern", "pattern must be null for exit_code match", phase="value")

                captured_from = rule.get("captured_from")
                if captured_from is None:
                    v.add("INVALID_VALUE", f"{p}/captured_from", "Every rule must have a captured_from sample", phase="value")
                elif not isinstance(captured_from, dict):
                    v.add("INVALID_TYPE", f"{p}/captured_from", "Expected object", phase="scalar")
                else:
                    for key in ("sample_path", "sample_sha256", "captured_at"):
                        if key not in captured_from:
                            v.add("MISSING_FIELD", f"{p}/captured_from/{key}", f"Missing required field '{key}'")
                        elif key == "sample_path":
                            sp = captured_from[key]
                            if isinstance(sp, str) and sp.strip() != "":
                                _check_repo_relative_path(v, sp, f"{p}/captured_from/{key}")
                            else:
                                v.add("INVALID_VALUE", f"{p}/captured_from/{key}", "sample_path must be a non-empty string", phase="value")
                        elif key == "sample_sha256":
                            _check_sha256(v, captured_from[key], f"{p}/captured_from/{key}")
                        else:
                            _check_rfc3339(v, captured_from[key], f"{p}/captured_from/{key}")
                    for key in captured_from:
                        if key not in {"sample_path", "sample_sha256", "captured_at"}:
                            v.add("UNKNOWN_FIELD", f"{p}/captured_from/{key}", f"Unknown field '{key}'")

                for key in rule:
                    if key not in {"rule_id", "channel", "match_kind", "pattern", "exit_code", "classification", "captured_from"}:
                        v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")

    declared = value.get("registry_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"registry_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/registry_sha256", "registry_sha256 does not match canonical self-hash", phase="cross_field")
    elif not _matches(declared, RE_SHA256):
        v.add("INVALID_FORMAT", "/registry_sha256", "Must be 64-character lowercase SHA-256 hex", phase="format")


def confirm_provider_exhaustion(
    worker_result: Dict[str, Any],
    provider_evidence: Optional[Dict[str, Any]],
    signal_registry: Optional[Dict[str, Any]],
    stdout_bytes: Optional[bytes] = None,
    stderr_bytes: Optional[bytes] = None,
    outcome_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply the four-guard confirmation rule from design 6.3.

    Returns {"classification": ..., "errors": [...]}.  Classification is one of
    CONFIRMED_QUOTA_EXHAUSTION, CONFIRMED_RATE_LIMIT_EXHAUSTION, or NOT_EXHAUSTION.

    ``outcome_record`` supplies the attempt's own timestamps and is always
    considered by Guard 3, regardless of whether ``worker_result`` is also
    supplied.  This keeps live-ingest and replay call shapes deterministic.
    """
    errors = []

    if provider_evidence is None:
        return {"classification": "NOT_EXHAUSTION", "errors": []}

    classification = provider_evidence.get("classification")
    if classification not in {"CONFIRMED_QUOTA_EXHAUSTION", "CONFIRMED_RATE_LIMIT_EXHAUSTION"}:
        return {"classification": "NOT_EXHAUSTION", "errors": []}

    fallback = (worker_result or {}).get("fallback") or {}

    # Guard 1: registry match with verbatim excerpt.
    matched_signal = provider_evidence.get("matched_signal")
    if not isinstance(matched_signal, dict):
        errors.append(error("EVIDENCE_MISSING", "/matched_signal", "Provider exhaustion requires a matched_signal", phase="evidence_accept"))
    else:
        provider = provider_evidence.get("provider")
        rule_id = matched_signal.get("rule_id")
        registry_id = matched_signal.get("registry_id")
        channel = matched_signal.get("channel")
        excerpt = matched_signal.get("verbatim_excerpt")
        offset = matched_signal.get("byte_offset")
        length = matched_signal.get("byte_length")

        if not isinstance(signal_registry, dict) or signal_registry.get("schema_version") != 1:
            errors.append(error("TRUST_CONTEXT_MISSING", "", "Valid signal registry is required for guard 1", phase="path_authority"))
        else:
            providers = signal_registry.get("providers") or {}
            rules = providers.get(provider) if isinstance(providers, dict) else []
            rule = next((r for r in (rules or []) if isinstance(r, dict) and r.get("rule_id") == rule_id), None)
            if rule is None:
                errors.append(error("EVIDENCE_HASH_MISMATCH", "/matched_signal/rule_id", "Matched rule_id not found in registry for provider", phase="evidence_accept"))
            else:
                if rule.get("registry_id") is not None and rule.get("registry_id") != registry_id:
                    errors.append(error("EVIDENCE_HASH_MISMATCH", "/matched_signal/registry_id", "Registry id mismatch", phase="evidence_accept"))
                if rule.get("channel") != channel:
                    errors.append(error("EVIDENCE_HASH_MISMATCH", "/matched_signal/channel", "Channel mismatch", phase="evidence_accept"))
                if rule.get("classification") != classification:
                    errors.append(error("EVIDENCE_HASH_MISMATCH", "/matched_signal/classification", "Classification mismatch", phase="evidence_accept"))

                data = stdout_bytes if channel == "stdout" else stderr_bytes
                expected_sha = provider_evidence.get("stdout_sha256") if channel == "stdout" else provider_evidence.get("stderr_sha256")
                if data is None:
                    errors.append(error("EVIDENCE_MISSING", f"/{channel}", f"{channel} bytes required for verbatim re-verification", phase="evidence_accept"))
                else:
                    if hashlib.sha256(data).hexdigest() != expected_sha:
                        errors.append(error("EVIDENCE_HASH_MISMATCH", f"/{channel}_sha256", "Channel digest does not match provided bytes", phase="evidence_accept"))
                    else:
                        if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length < 1:
                            errors.append(error("INVALID_VALUE", "/matched_signal", "Invalid byte offset/length", phase="value"))
                        elif offset + length > len(data):
                            errors.append(error("INVALID_VALUE", "/matched_signal/byte_offset", "Excerpt range exceeds channel length", phase="value"))
                        else:
                            try:
                                actual = data[offset:offset + length].decode("utf-8")
                            except UnicodeDecodeError:
                                actual = None
                            if actual != excerpt:
                                errors.append(error("EVIDENCE_HASH_MISMATCH", "/matched_signal/verbatim_excerpt", "Verbatim excerpt does not match channel bytes", phase="evidence_accept"))

    # Guard 2: worker claim binds to coordinator evidence.
    evidence_id = provider_evidence.get("evidence_id")
    if fallback.get("provider_evidence_id") != evidence_id:
        errors.append(error("INVALID_FALLBACK", "/fallback/provider_evidence_id", "Fallback provider_evidence_id does not match captured evidence", phase="evidence_accept"))
    if fallback.get("reassign_to") != "sonnet_implementation":
        errors.append(error("INVALID_FALLBACK", "/fallback/reassign_to", "Fallback reassign_to must be 'sonnet_implementation'", phase="evidence_accept"))
    expected_reason = CLASSIFICATION_TO_REASON.get(classification)
    if fallback.get("reason") != expected_reason:
        errors.append(error("INVALID_FALLBACK", "/fallback/reason", f"Fallback reason must be '{expected_reason}'", phase="evidence_accept"))

    # Guard 3: chronology.  Exhaustion must be the last thing that happened in
    # the attempt.  Take the maximum over every available anchor, always
    # including the outcome record's own invocation.finished_at so that live
    # ingest (worker_result present) and replay (worker_result absent) call
    # shapes classify identically for byte-identical evidence/outcome timestamps.
    invocation = provider_evidence.get("invocation") or {}
    evidence_finished = invocation.get("finished_at")
    anchors: List[str] = []
    outcome = (outcome_record or {}).get("invocation") or {}
    if outcome.get("finished_at"):
        anchors.append(outcome["finished_at"])
    wr = worker_result or {}
    if isinstance(wr.get("invocation"), dict) and wr["invocation"].get("finished_at"):
        anchors.append(wr["invocation"]["finished_at"])
    if wr.get("finished_at"):
        anchors.append(wr["finished_at"])
    for cmd in wr.get("commands") or []:
        ts = (cmd or {}).get("timestamps") or {}
        finished = ts.get("finished_at")
        if finished:
            anchors.append(finished)
    attempt_finished = max(anchors) if anchors else None
    if evidence_finished and attempt_finished and evidence_finished < attempt_finished:
        errors.append(error("CHRONOLOGY_VIOLATION", "/invocation/finished_at", "Evidence finished_at precedes attempt finished_at", phase="cross_object"))

    # Guard 4: abnormal termination corroboration.
    exit_code = invocation.get("exit_code")
    timed_out = invocation.get("timed_out")
    if exit_code == 0 and timed_out is not True:
        errors.append(error("INVALID_VALUE", "/invocation", "Provider exhaustion requires abnormal termination", phase="value"))

    if errors:
        return {"classification": "NOT_EXHAUSTION", "errors": errors}
    return {"classification": classification, "errors": []}
