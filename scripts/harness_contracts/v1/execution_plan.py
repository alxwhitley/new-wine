"""Authenticated, closed execution-plan contract for O5.

An execution plan is a self-hashed, canonical artifact that fixes the finite
set of coordinator work before the first claim.  This module deliberately
validates only the plan artifact itself; packet-artifact identity is verified
at the binding/recovery boundary where those authenticated bytes are present.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.packet import RE_SHA256, is_harness_id


REQUIRED = {
    "schema_version", "plan_id", "plan_sha256", "packets", "routes",
    "provider_backoff", "wall_clock_safety_seconds", "human_stop_categories",
}

CAPABILITY_CLASSES = {
    "design_judgment", "planning_architecture", "implementation",
    "independent_review", "adversarial_audit", "mechanical_check",
}

REASONING_LEVELS = {"none", "low", "medium", "high", "xhigh", "max"}

# Design judgment is an ALLOWLIST, not a single-model denylist: only these
# model IDs may be enabled under ``design_judgment``.  ``gpt-5.6-sol`` stays a
# DISABLED candidate until Alex separately approves its design evaluation, and
# any other model is forbidden outright rather than silently permitted.
DESIGN_JUDGMENT_ENABLED_MODELS = {"claude-fable-5"}
DESIGN_JUDGMENT_DISABLED_CANDIDATES = {"gpt-5.6-sol"}

HUMAN_STOP_CATEGORIES = {
    "production_database_write",
    "migration",
    "deployment",
    "destructive_filesystem_git",
    "git_stage",
    "git_commit",
    "git_merge",
    "git_push",
    "git_clean",
    "git_delete",
    "governed_content",
    "licensing_determination",
    "real_provider_commissioning",
    "material_plan_expansion",
}

PACKET_BUDGET_FIELDS = {
    "attempt_limit",
    "retry_limit",
    "revision_limit",
    "turn_limit",
    "command_timeout_seconds",
    "output_bytes",
}

ROUTE_FIELDS = {
    "route_id",
    "provider",
    "model_id",
    "minimum_reasoning",
    "enabled",
    "qualification_id",
    "fallback_to",
}

PROVIDER_BACKOFF_FIELDS = {
    "max_retries", "base_delay_seconds", "max_delay_seconds",
}

MAX_WALL_CLOCK_SAFETY_SECONDS = 86400
_MODEL_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")


class ExecutionPlanContractError(ValueError):
    """A plan artifact failed its standalone authenticated contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def execution_plan_sha256(plan: Dict[str, Any]) -> str:
    """Return the canonical SHA-256 identity for ``plan``.

    The self-referential ``plan_sha256`` is the only omitted field.  Every
    other field, including packet order and route order, is authenticated.
    """
    return compute_sha256(canonical_bytes(plan, omit={"plan_sha256"}))


def validate_execution_plan(value: Any) -> Dict[str, Any]:
    """Validate one closed execution plan without reading external artifacts."""
    if isinstance(value, (str, bytes, bytearray)):
        try:
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8")
            value = json.loads(value)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _invalid([_error("INVALID_JSON", "", "JSON decode error: %s" % exc, 0)])
    if not isinstance(value, dict):
        return _invalid([_error("ROOT_NOT_OBJECT", "", "Execution plan root is not an object", 0)])

    errors: List[Dict[str, Any]] = []
    for key in value:
        if key not in REQUIRED:
            errors.append(_error("UNKNOWN_PROPERTY", "/%s" % key, "Unknown property '%s'" % key, 1))
    for key in REQUIRED:
        if key not in value:
            errors.append(_error("MISSING_PROPERTY", "/%s" % key, "Missing required property '%s'" % key, 1))
    if errors:
        return _invalid(errors)

    _check_exact_int(errors, value.get("schema_version"), "/schema_version", minimum=1)
    if value.get("schema_version") != 1:
        errors.append(_error("INVALID_VALUE", "/schema_version", "schema_version must be 1", 2))

    if not is_harness_id(value.get("plan_id")):
        errors.append(_error("INVALID_FORMAT", "/plan_id", "plan_id must be a safe harness identifier", 2))
    _check_sha256(errors, value.get("plan_sha256"), "/plan_sha256")

    packet_rows = value.get("packets")
    packet_by_id = _validate_packets(errors, packet_rows)
    _validate_routes(errors, value.get("routes"), packet_by_id)
    _validate_provider_backoff(errors, value.get("provider_backoff"))
    _check_exact_int(
        errors, value.get("wall_clock_safety_seconds"), "/wall_clock_safety_seconds",
        minimum=1, maximum=MAX_WALL_CLOCK_SAFETY_SECONDS,
    )
    _validate_human_stops(errors, value.get("human_stop_categories"))

    if _matches_sha256(value.get("plan_sha256")):
        actual = execution_plan_sha256(value)
        if actual != value.get("plan_sha256"):
            errors.append(_error(
                "EVIDENCE_HASH_MISMATCH", "/plan_sha256",
                "plan_sha256 does not match canonical self-hash", 5,
            ))

    return _invalid(errors) if errors else {"valid": True, "errors": []}


def authenticate_execution_plan_bytes(raw: bytes) -> Dict[str, Any]:
    """Parse and authenticate canonical plan bytes, raising on any ambiguity."""
    if not isinstance(raw, bytes):
        raise ExecutionPlanContractError("PLAN_IDENTITY_INVALID", "execution plan bytes are required")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionPlanContractError("PLAN_IDENTITY_INVALID", "execution plan is not valid UTF-8 JSON: %s" % exc) from exc
    result = validate_execution_plan(value)
    if not result["valid"]:
        first = result["errors"][0]
        raise ExecutionPlanContractError("PLAN_IDENTITY_INVALID", first["message"])
    if raw != canonical_bytes(value):
        raise ExecutionPlanContractError("PLAN_IDENTITY_NONCANONICAL", "execution plan artifact is not canonically encoded")
    return value


def bind_execution_plan(handle, raw: bytes, coordinator_id: str, run_id: str, now: str) -> Dict[str, Any]:
    """Durably bind one immutable canonical plan artifact to one run.

    The artifact is published through the caller's pinned state-root handle
    before its binding event is appended.  A bounded compare-and-swap retry
    handles unrelated journal-head movement, while a same-run differing plan
    is an integrity error rather than an implicit replacement.
    """
    from harness_coordinator.v1.recovery import IntegrityError, _make_event
    from harness_coordinator.v1.seals_runtime import ArtifactConflict
    from harness_coordinator.v1.store import JournalHeadMoved, append_journal, read_journal

    if not is_harness_id(coordinator_id):
        raise IntegrityError("PLAN_IDENTITY_INVALID", "coordinator_id must be a safe harness identifier")
    if not is_harness_id(run_id):
        raise IntegrityError("PLAN_IDENTITY_INVALID", "run_id must be a safe harness identifier")
    try:
        plan = authenticate_execution_plan_bytes(raw)
    except ExecutionPlanContractError as exc:
        raise IntegrityError(exc.code, exc.message) from exc

    handle.verify_identity()
    state_root_id = _read_authenticated_state_root_id(handle)
    plan_id = plan["plan_id"]
    plan_path = "plans/%s.json" % plan_id
    binding = {
        "plan_id": plan_id,
        "plan_sha256": plan["plan_sha256"],
        "plan_path": plan_path,
        "packet_count": len(plan["packets"]),
    }

    # The journal primitive needs its lock pathname.  Create its parent
    # through the pinned handle before any pathname-based append call.
    with handle.directory(("locks",), create=True):
        pass
    journal_path = "%s/journal.ndjson" % handle.path
    lock_path = "%s/locks/journal.wlock" % handle.path

    for _attempt in range(8):
        handle.verify_identity()
        events, torn_tail = read_journal(journal_path, state_root_id=state_root_id)
        if torn_tail is not None:
            raise IntegrityError("PLAN_IDENTITY_INVALID", "plan binding refuses a torn journal tail")
        existing = _binding_for_run(events, run_id)
        if existing is not None:
            if existing != binding:
                raise IntegrityError("PLAN_IDENTITY_CONFLICT", "run_id already has a different execution plan binding")
            try:
                persisted = handle.read(("plans", "%s.json" % plan_id))
            except OSError as exc:
                raise IntegrityError("PLAN_IDENTITY_INVALID", "bound execution plan artifact cannot be safely read") from exc
            if persisted is None:
                raise IntegrityError("PLAN_IDENTITY_ARTIFACT_MISSING", "bound execution plan artifact is missing")
            try:
                persisted_plan = authenticate_execution_plan_bytes(persisted)
            except ExecutionPlanContractError as exc:
                raise IntegrityError(exc.code, exc.message) from exc
            if persisted_plan != plan:
                raise IntegrityError("PLAN_IDENTITY_CONFLICT", "bound execution plan artifact disagrees with requested plan")
            return plan

        try:
            handle.publish(("plans", "%s.json" % plan_id), raw)
        except ArtifactConflict as exc:
            raise IntegrityError("PLAN_IDENTITY_CONFLICT", "execution plan artifact identity conflicts") from exc
        handle.verify_identity()

        previous = events[-1] if events else None
        event = _make_event(
            (previous["seq"] + 1) if previous else 1,
            "EXECUTION_PLAN_BOUND",
            coordinator_id,
            run_id,
            state_root_id,
            previous,
            now,
            payload={
                "packet": None,
                "attempt": None,
                "artifacts": [],
                "classification": None,
                "transition_detail": None,
                "recovery": None,
                "run": None,
                "report": None,
                "execution_plan": binding,
            },
        )
        # ``append_journal`` authenticates the same event shape on later
        # replay; validate here so no malformed event can be published.
        from harness_contracts.v1.journal import validate_journal_event
        event_result = validate_journal_event(event, previous, state_root_id)
        if not event_result["valid"]:
            raise IntegrityError("PLAN_IDENTITY_INVALID", event_result["errors"][0]["message"])
        try:
            append_journal(journal_path, event, lock_path, expected_head=previous)
            handle.verify_identity()
            return plan
        except JournalHeadMoved:
            continue

    raise IntegrityError("PLAN_IDENTITY_CONFLICT", "journal head kept moving during bounded execution-plan binding")


def _read_authenticated_state_root_id(handle) -> str:
    raw = handle.read(("MANIFEST.json",))
    if raw is None:
        raise _integrity_error("PLAN_IDENTITY_INVALID", "MANIFEST.json is required before plan binding")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _integrity_error("PLAN_IDENTITY_INVALID", "MANIFEST.json is unreadable: %s" % exc) from exc
    if not isinstance(manifest, dict):
        raise _integrity_error("PLAN_IDENTITY_INVALID", "MANIFEST.json must be an object")
    declared = manifest.get("manifest_sha256")
    if declared != compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"})):
        raise _integrity_error("PLAN_IDENTITY_INVALID", "MANIFEST.json self-hash disagrees")
    state_root_id = manifest.get("state_root_id")
    if not isinstance(state_root_id, str) or not state_root_id.strip():
        raise _integrity_error("PLAN_IDENTITY_INVALID", "MANIFEST.json state_root_id is invalid")
    return state_root_id


def _integrity_error(code: str, message: str):
    # Keep this helper lazy to avoid an import cycle while recovery imports
    # artifact authentication from this module.
    from harness_coordinator.v1.recovery import IntegrityError
    return IntegrityError(code, message)


def _binding_for_run(events: List[Dict[str, Any]], run_id: str) -> Optional[Dict[str, Any]]:
    binding = None
    for event in events:
        if event.get("event_type") != "EXECUTION_PLAN_BOUND" or event.get("run_id") != run_id:
            continue
        candidate = ((event.get("payload") or {}).get("execution_plan"))
        if not isinstance(candidate, dict):
            raise _integrity_error("PLAN_IDENTITY_INVALID", "execution plan binding payload is invalid")
        required = {"plan_id", "plan_sha256", "plan_path", "packet_count"}
        if set(candidate) != required:
            raise _integrity_error("PLAN_IDENTITY_INVALID", "execution plan binding payload is not closed")
        if binding is None:
            binding = dict(candidate)
        elif binding != candidate:
            raise _integrity_error("PLAN_IDENTITY_CONFLICT", "run_id has conflicting execution plan bindings")
    return binding


def _validate_packets(errors: List[Dict[str, Any]], packets: Any) -> Dict[str, Dict[str, Any]]:
    packet_by_id: Dict[str, Dict[str, Any]] = {}
    if not isinstance(packets, list):
        errors.append(_error("INVALID_TYPE", "/packets", "packets must be an array", 2))
        return packet_by_id
    if not packets:
        errors.append(_error("INVALID_VALUE", "/packets", "packets must not be empty", 2))
        return packet_by_id
    for index, packet in enumerate(packets):
        path = "/packets/%d" % index
        if not isinstance(packet, dict):
            errors.append(_error("INVALID_TYPE", path, "packet must be an object", 2))
            continue
        required = {"packet_id", "packet_sha256", "dependencies", "capability_class", "budgets"}
        _check_closed_object(errors, packet, required, path)
        packet_id = packet.get("packet_id")
        if not is_harness_id(packet_id):
            errors.append(_error("INVALID_FORMAT", path + "/packet_id", "packet_id must be a safe harness identifier", 2))
        elif packet_id in packet_by_id:
            errors.append(_error("DUPLICATE_ID", path + "/packet_id", "packet_id is duplicated in plan", 3))
        else:
            packet_by_id[packet_id] = packet
        _check_sha256(errors, packet.get("packet_sha256"), path + "/packet_sha256")
        capability = packet.get("capability_class")
        if capability not in CAPABILITY_CLASSES:
            errors.append(_error("INVALID_ENUM", path + "/capability_class", "unknown capability class", 2))
        _validate_packet_budgets(errors, packet.get("budgets"), path + "/budgets")

        dependencies = packet.get("dependencies")
        if not isinstance(dependencies, list):
            errors.append(_error("INVALID_TYPE", path + "/dependencies", "dependencies must be an array", 2))
        else:
            seen: Set[str] = set()
            for dep_index, dependency in enumerate(dependencies):
                dep_path = path + "/dependencies/%d" % dep_index
                if not is_harness_id(dependency):
                    errors.append(_error("INVALID_FORMAT", dep_path, "dependency must be a safe harness identifier", 2))
                    continue
                if dependency in seen:
                    errors.append(_error("DUPLICATE_ID", dep_path, "dependency is duplicated", 3))
                seen.add(dependency)
                if dependency == packet_id:
                    errors.append(_error("SELF_DEPENDENCY", dep_path, "packet cannot depend on itself", 5))

    for packet_id, packet in packet_by_id.items():
        dependencies = packet.get("dependencies")
        if not isinstance(dependencies, list):
            continue
        for index, dependency in enumerate(dependencies):
            if isinstance(dependency, str) and dependency not in packet_by_id:
                errors.append(_error(
                    "UNKNOWN_DEPENDENCY", "/packets/%s/dependencies/%d" % (packet_id, index),
                    "dependency is outside execution-plan membership", 6,
                ))
    _validate_packet_dependency_cycles(errors, packet_by_id)
    return packet_by_id


def _validate_packet_budgets(errors: List[Dict[str, Any]], budgets: Any, path: str) -> None:
    if not isinstance(budgets, dict):
        errors.append(_error("INVALID_TYPE", path, "budgets must be an object", 2))
        return
    _check_closed_object(errors, budgets, PACKET_BUDGET_FIELDS, path)
    for field in ("attempt_limit", "retry_limit", "revision_limit"):
        _check_exact_int(errors, budgets.get(field), path + "/" + field, minimum=0)
    for field in ("turn_limit", "command_timeout_seconds", "output_bytes"):
        _check_exact_int(errors, budgets.get(field), path + "/" + field, minimum=1)


def _validate_packet_dependency_cycles(errors: List[Dict[str, Any]], packets: Dict[str, Dict[str, Any]]) -> None:
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(packet_id: str) -> None:
        if packet_id in visited:
            return
        if packet_id in visiting:
            errors.append(_error("INVALID_FALLBACK", "/packets", "packet dependency graph contains a cycle", 6))
            return
        visiting.add(packet_id)
        for dependency in packets[packet_id].get("dependencies", []):
            if dependency in packets:
                visit(dependency)
        visiting.remove(packet_id)
        visited.add(packet_id)

    for packet_id in sorted(packets):
        visit(packet_id)


def _validate_routes(errors: List[Dict[str, Any]], routes: Any, packets: Dict[str, Dict[str, Any]]) -> None:
    if not isinstance(routes, dict):
        errors.append(_error("INVALID_TYPE", "/routes", "routes must be an object", 2))
        return
    for capability, route_hops in routes.items():
        capability_path = "/routes/%s" % capability
        if capability not in CAPABILITY_CLASSES:
            errors.append(_error("INVALID_ENUM", capability_path, "unknown route capability class", 2))
            continue
        if not isinstance(route_hops, list) or not route_hops:
            errors.append(_error("INVALID_TYPE", capability_path, "route capability must contain a non-empty array", 2))
            continue
        routes_by_id: Dict[str, Dict[str, Any]] = {}
        for index, route in enumerate(route_hops):
            path = capability_path + "/%d" % index
            if not isinstance(route, dict):
                errors.append(_error("INVALID_TYPE", path, "route hop must be an object", 2))
                continue
            _check_closed_object(errors, route, ROUTE_FIELDS, path)
            route_id = route.get("route_id")
            if not is_harness_id(route_id):
                errors.append(_error("INVALID_FORMAT", path + "/route_id", "route_id must be a safe harness identifier", 2))
            elif route_id in routes_by_id:
                errors.append(_error("DUPLICATE_ID", path + "/route_id", "route_id is duplicated", 3))
            else:
                routes_by_id[route_id] = route
            _check_nonempty_string(errors, route.get("provider"), path + "/provider")
            model_id = route.get("model_id")
            if not isinstance(model_id, str) or _MODEL_ID.fullmatch(model_id) is None:
                errors.append(_error("INVALID_FORMAT", path + "/model_id", "model_id must be canonical lowercase identifier", 2))
            reasoning = route.get("minimum_reasoning")
            if reasoning not in REASONING_LEVELS:
                errors.append(_error("INVALID_ENUM", path + "/minimum_reasoning", "unknown minimum reasoning level", 2))
            if not isinstance(route.get("enabled"), bool):
                errors.append(_error("INVALID_TYPE", path + "/enabled", "enabled must be boolean", 2))
            qualification_id = route.get("qualification_id")
            if not is_harness_id(qualification_id):
                errors.append(_error("INVALID_VALUE", path + "/qualification_id", "qualification_id must be present and safe", 2))
            fallback_to = route.get("fallback_to")
            if fallback_to is not None and not is_harness_id(fallback_to):
                errors.append(_error("INVALID_FORMAT", path + "/fallback_to", "fallback_to must be a safe route_id or null", 2))
            if capability == "design_judgment" and route.get("enabled") is True:
                # Keep the named Sol prohibition legible in the error surface,
                # then close the class: everything else is refused too.
                if model_id in DESIGN_JUDGMENT_DISABLED_CANDIDATES:
                    errors.append(_error("FORBIDDEN_AUTHORITY", path + "/enabled", "gpt-5.6-sol must remain disabled for design_judgment", 5))
                elif model_id not in DESIGN_JUDGMENT_ENABLED_MODELS:
                    errors.append(_error(
                        "FORBIDDEN_AUTHORITY", path + "/model_id",
                        "design_judgment permits only an enabled claude-fable-5 route", 5,
                    ))

        for route_id, route in routes_by_id.items():
            fallback_to = route.get("fallback_to")
            if fallback_to is not None and fallback_to not in routes_by_id:
                errors.append(_error("INVALID_FALLBACK", capability_path, "fallback target is not in the same capability class", 6))
        _validate_route_cycles(errors, routes_by_id, capability_path)

    packet_capabilities = {packet.get("capability_class") for packet in packets.values()}
    for capability in packet_capabilities:
        if capability not in routes:
            errors.append(_error("INVALID_FALLBACK", "/routes", "plan has no routes for packet capability class '%s'" % capability, 6))


def _validate_route_cycles(errors: List[Dict[str, Any]], routes: Dict[str, Dict[str, Any]], path: str) -> None:
    visiting: Set[str] = set()
    visited: Set[str] = set()

    def visit(route_id: str) -> None:
        if route_id in visited:
            return
        if route_id in visiting:
            errors.append(_error("INVALID_FALLBACK", path, "fallback graph contains a cycle", 6))
            return
        visiting.add(route_id)
        fallback_to = routes[route_id].get("fallback_to")
        if fallback_to in routes:
            visit(fallback_to)
        visiting.remove(route_id)
        visited.add(route_id)

    for route_id in sorted(routes):
        visit(route_id)


def _validate_provider_backoff(errors: List[Dict[str, Any]], backoff: Any) -> None:
    path = "/provider_backoff"
    if not isinstance(backoff, dict):
        errors.append(_error("INVALID_TYPE", path, "provider_backoff must be an object", 2))
        return
    _check_closed_object(errors, backoff, PROVIDER_BACKOFF_FIELDS, path)
    _check_exact_int(errors, backoff.get("max_retries"), path + "/max_retries", minimum=0)
    _check_exact_int(errors, backoff.get("base_delay_seconds"), path + "/base_delay_seconds", minimum=1)
    _check_exact_int(errors, backoff.get("max_delay_seconds"), path + "/max_delay_seconds", minimum=1)
    base = backoff.get("base_delay_seconds")
    maximum = backoff.get("max_delay_seconds")
    if _is_int(base) and _is_int(maximum) and maximum < base:
        errors.append(_error("INVALID_VALUE", path + "/max_delay_seconds", "max_delay_seconds must be at least base_delay_seconds", 5))


def _validate_human_stops(errors: List[Dict[str, Any]], values: Any) -> None:
    path = "/human_stop_categories"
    if not isinstance(values, list) or not values:
        errors.append(_error("INVALID_TYPE", path, "human_stop_categories must be a non-empty array", 2))
        return
    seen: Set[str] = set()
    for index, value in enumerate(values):
        item_path = path + "/%d" % index
        if value not in HUMAN_STOP_CATEGORIES:
            errors.append(_error("INVALID_ENUM", item_path, "unknown human-stop category", 2))
        elif value in seen:
            errors.append(_error("DUPLICATE_ID", item_path, "human-stop category is duplicated", 3))
        seen.add(value)


def _check_closed_object(errors: List[Dict[str, Any]], value: Dict[str, Any], required: Set[str], path: str) -> None:
    for key in value:
        if key not in required:
            errors.append(_error("UNKNOWN_PROPERTY", path + "/" + key, "Unknown property '%s'" % key, 1))
    for key in required:
        if key not in value:
            errors.append(_error("MISSING_PROPERTY", path + "/" + key, "Missing required property '%s'" % key, 1))


def _check_exact_int(errors: List[Dict[str, Any]], value: Any, path: str, minimum: Optional[int] = None, maximum: Optional[int] = None) -> None:
    if not _is_int(value):
        errors.append(_error("INVALID_TYPE", path, "expected integer, not boolean", 2))
        return
    if minimum is not None and value < minimum:
        errors.append(_error("INVALID_VALUE", path, "must be at least %d" % minimum, 2))
    if maximum is not None and value > maximum:
        errors.append(_error("INVALID_VALUE", path, "must be at most %d" % maximum, 2))


def _check_nonempty_string(errors: List[Dict[str, Any]], value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(_error("INVALID_VALUE", path, "must be a non-empty string", 2))


def _check_sha256(errors: List[Dict[str, Any]], value: Any, path: str) -> None:
    if not _matches_sha256(value):
        errors.append(_error("INVALID_FORMAT", path, "must be 64-character lowercase SHA-256 hex", 2))


def _matches_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(RE_SHA256, value) is not None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _error(code: str, path: str, message: str, phase: int) -> Dict[str, Any]:
    return {"code": code, "path": path, "message": message, "_phase": phase}


def _invalid(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
    ordered = sorted(errors, key=lambda item: (item["_phase"], item["path"], item["code"], item["message"]))
    return {
        "valid": False,
        "errors": [{"code": item["code"], "path": item["path"], "message": item["message"]} for item in ordered],
    }


__all__ = [
    "CAPABILITY_CLASSES",
    "DESIGN_JUDGMENT_DISABLED_CANDIDATES",
    "DESIGN_JUDGMENT_ENABLED_MODELS",
    "ExecutionPlanContractError",
    "REQUIRED",
    "authenticate_execution_plan_bytes",
    "bind_execution_plan",
    "execution_plan_sha256",
    "validate_execution_plan",
]
