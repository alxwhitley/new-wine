"""Opus verdict schema validation for harness contract v1."""

import json
from typing import Any, Dict, List, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.errors import error, invalid_result, sort_errors, valid_result
from harness_contracts.v1.packet import (
    PACKET_STATES,
    RE_REVISION,
    RE_SHA256,
    _matches,
    _PacketValidator,
)
from harness_contracts.v1.worker_result import RE_RFC3339


VERDICTS = {"ACCEPT", "REVISE", "QUARANTINE", "HUMAN_REQUIRED"}
FINDING_STATES = {"PASS", "FAIL", "NOT_PROVEN"}
GLOBAL_FINDING_STATES = {"PASS", "FAIL", "NOT_APPLICABLE"}

# Global rule applicability per the brief.
ALWAYS_APPLICABLE_RULES = {
    "premise",
    "repo_only_boundary",
    "allowlist_scope",
    "changed_manifest",
    "command_integrity",
    "governed_records",
    "reviewer_independence",
}

CONDITIONAL_RULES = {
    "batch_reconciliation",
    "pre_batch",
    "migration_comment",
    "n_plus_one",
    "reuse_path",
}

REQUIRED_GLOBAL_RULES = ALWAYS_APPLICABLE_RULES | CONDITIONAL_RULES


def validate_verdict(value: Any) -> Dict[str, Any]:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            return invalid_result([error("INVALID_JSON", "", f"JSON decode error: {exc}")])
    if not isinstance(value, dict):
        return invalid_result([error("ROOT_NOT_OBJECT", "", "Verdict root is not an object")])

    v = _PacketValidator(value)
    _validate_verdict_object(v)
    if not v.errors:
        return valid_result()
    return invalid_result(sort_errors(v.errors))


def _validate_verdict_object(v: _PacketValidator) -> None:
    allowed = {
        "schema_version",
        "verdict_id",
        "packet_id",
        "packet_sha256",
        "result_id",
        "result_sha256",
        "reviewer",
        "reviewed_at",
        "verdict",
        "criterion_findings",
        "global_findings",
        "required_corrections",
        "human_decisions_required",
        "next_state",
        "integration_revision",
        "verdict_sha256",
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
        v.add("INVALID_VALUE", "/schema_version", "schema_version must be 1")

    for field in ("verdict_id", "packet_id", "result_id"):
        v.check_non_empty_string(value[field], f"/{field}")

    for field in ("packet_sha256", "result_sha256"):
        if not _matches(value.get(field), RE_SHA256):
            v.add("INVALID_FORMAT", f"/{field}", "Must be 64-character lowercase SHA-256 hex")

    _validate_reviewer(v, value.get("reviewer"), "/reviewer")

    if not _matches(value.get("reviewed_at"), RE_RFC3339):
        v.add("INVALID_FORMAT", "/reviewed_at", "Must be RFC3339 UTC timestamp ending in Z")

    v.check_enum(value.get("verdict"), VERDICTS, "/verdict")

    _validate_criterion_findings(v, value.get("criterion_findings", []), "/criterion_findings")
    _validate_global_findings(v, value.get("global_findings", []), "/global_findings")

    rc = value.get("required_corrections", [])
    if not isinstance(rc, list):
        v.add("INVALID_TYPE", "/required_corrections", "Expected array")
    else:
        for i, corr in enumerate(rc):
            if not isinstance(corr, str) or corr.strip() == "":
                v.add("INVALID_VALUE", f"/required_corrections/{i}", "Correction must be a non-empty string")

    hdr = value.get("human_decisions_required", [])
    if not isinstance(hdr, list):
        v.add("INVALID_TYPE", "/human_decisions_required", "Expected array")
    else:
        for i, decision in enumerate(hdr):
            if not isinstance(decision, str) or decision.strip() == "":
                v.add("INVALID_VALUE", f"/human_decisions_required/{i}", "Decision must be a non-empty string")

    v.check_enum(value.get("next_state"), PACKET_STATES, "/next_state")

    if value.get("integration_revision") is not None and not _matches(value["integration_revision"], RE_REVISION):
        v.add("INVALID_FORMAT", "/integration_revision", "Must be 40-character lowercase SHA-1 hex or null")

    if not _matches(value.get("verdict_sha256"), RE_SHA256):
        v.add("INVALID_FORMAT", "/verdict_sha256", "Must be 64-character lowercase SHA-256 hex")

    _cross_field_checks_verdict(v)


def _validate_reviewer(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, dict):
        v.add("INVALID_TYPE", path, "Expected object")
        return
    for key in ("role", "session_id", "model"):
        if key not in value:
            v.add("MISSING_FIELD", f"{path}/{key}", f"Missing required field '{key}'")
    for key in value:
        if key not in {"role", "session_id", "model"}:
            v.add("UNKNOWN_FIELD", f"{path}/{key}", f"Unknown field '{key}'")
    if "role" in value and value["role"] != "opus_judgment":
        v.add("INVALID_VALUE", f"{path}/role", "role must be 'opus_judgment'")
    for key in ("session_id", "model"):
        if key in value:
            v.check_non_empty_string(value[key], f"{path}/{key}")


def _validate_criterion_findings(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one criterion finding")
    seen: Set[str] = set()
    for i, finding in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(finding, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("criterion_id", "finding", "evidence_ids", "reason"):
            if key not in finding:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in finding:
            if key not in {"criterion_id", "finding", "evidence_ids", "reason"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "criterion_id" in finding:
            cid = finding["criterion_id"]
            if not isinstance(cid, str) or cid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/criterion_id", "Criterion ID must be a non-empty string")
            elif cid in seen:
                v.add("DUPLICATE_ID", f"{p}/criterion_id", "Duplicate criterion_id")
            else:
                seen.add(cid)
        if "finding" in finding:
            v.check_enum(finding["finding"], FINDING_STATES, f"{p}/finding")
        if "evidence_ids" in finding:
            ids = finding["evidence_ids"]
            if not isinstance(ids, list):
                v.add("INVALID_TYPE", f"{p}/evidence_ids", "Expected array")
            else:
                for j, eid in enumerate(ids):
                    if not isinstance(eid, str) or eid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/evidence_ids/{j}", "Evidence ID must be a non-empty string")
        if "reason" in finding:
            v.check_non_empty_string(finding["reason"], f"{p}/reason")


def _validate_global_findings(v: _PacketValidator, value: Any, path: str) -> None:
    if not isinstance(value, list):
        v.add("INVALID_TYPE", path, "Expected array")
        return
    if len(value) == 0:
        v.add("INVALID_VALUE", path, "Must contain at least one global finding")
    seen: Set[str] = set()
    for i, finding in enumerate(value):
        p = f"{path}/{i}"
        if not isinstance(finding, dict):
            v.add("INVALID_TYPE", p, "Expected object")
            continue
        for key in ("rule_id", "finding", "evidence_ids", "reason"):
            if key not in finding:
                v.add("MISSING_FIELD", f"{p}/{key}", f"Missing required field '{key}'")
        for key in finding:
            if key not in {"rule_id", "finding", "evidence_ids", "reason"}:
                v.add("UNKNOWN_FIELD", f"{p}/{key}", f"Unknown field '{key}'")
        if "rule_id" in finding:
            rid = finding["rule_id"]
            if not isinstance(rid, str) or rid.strip() == "":
                v.add("INVALID_VALUE", f"{p}/rule_id", "Rule ID must be a non-empty string")
            elif rid in seen:
                v.add("DUPLICATE_ID", f"{p}/rule_id", "Duplicate rule_id")
            else:
                seen.add(rid)
        if "finding" in finding:
            v.check_enum(finding["finding"], GLOBAL_FINDING_STATES, f"{p}/finding")
        if "evidence_ids" in finding:
            ids = finding["evidence_ids"]
            if not isinstance(ids, list):
                v.add("INVALID_TYPE", f"{p}/evidence_ids", "Expected array")
            else:
                for j, eid in enumerate(ids):
                    if not isinstance(eid, str) or eid.strip() == "":
                        v.add("INVALID_VALUE", f"{p}/evidence_ids/{j}", "Evidence ID must be a non-empty string")
        if "reason" in finding:
            v.check_non_empty_string(finding["reason"], f"{p}/reason")


def _cross_field_checks_verdict(v: _PacketValidator) -> None:
    value = v.value

    # Self-hash.
    declared = value.get("verdict_sha256")
    if isinstance(declared, str) and _matches(declared, RE_SHA256):
        computed = compute_sha256(canonical_bytes(value, omit={"verdict_sha256"}))
        if computed != declared:
            v.add("EVIDENCE_HASH_MISMATCH", "/verdict_sha256", "verdict_sha256 does not match canonical self-hash")

    # Verdict/state consistency.
    verdict = value.get("verdict")
    next_state = value.get("next_state")
    required_corrections = value.get("required_corrections", [])
    human_decisions_required = value.get("human_decisions_required", [])

    expected_next = {
        "ACCEPT": "ACCEPTED",
        "REVISE": "REVISE",
        "QUARANTINE": "QUARANTINED",
        "HUMAN_REQUIRED": "HUMAN_REQUIRED",
    }.get(verdict)
    if expected_next is not None and next_state != expected_next:
        v.add("INVALID_TRANSITION", "/next_state", f"{verdict} verdict must transition to {expected_next}")

    if verdict == "REVISE" and not required_corrections:
        v.add("ACCEPTANCE_UNSATISFIED", "/required_corrections", "REVISE verdict must list required corrections")

    if verdict == "HUMAN_REQUIRED" and not human_decisions_required:
        v.add("ACCEPTANCE_UNSATISFIED", "/human_decisions_required", "HUMAN_REQUIRED verdict must list required human decisions")

    # ACCEPT-specific rules.
    if verdict == "ACCEPT":
        findings = value.get("criterion_findings", [])
        for i, f in enumerate(findings):
            if isinstance(f, dict):
                if f.get("finding") != "PASS":
                    v.add(
                        "ACCEPTANCE_UNSATISFIED",
                        f"/criterion_findings/{i}/finding",
                        "ACCEPT requires every criterion finding to be PASS",
                        phase="evidence_accept",
                    )
                if not f.get("evidence_ids"):
                    v.add(
                        "EVIDENCE_MISSING",
                        f"/criterion_findings/{i}/evidence_ids",
                        "ACCEPT requires recorded evidence for every criterion finding",
                        phase="evidence_accept",
                    )

        globals_ = value.get("global_findings", [])
        present_rules = {}
        for i, f in enumerate(globals_):
            if not isinstance(f, dict):
                continue
            rid = f.get("rule_id")
            state = f.get("finding")
            if rid:
                present_rules[rid] = (i, f)
            if state == "FAIL":
                v.add(
                    "ACCEPTANCE_UNSATISFIED",
                    f"/global_findings/{i}/finding",
                    "ACCEPT cannot have a FAIL global finding",
                    phase="evidence_accept",
                )
            elif state == "NOT_APPLICABLE":
                if rid not in CONDITIONAL_RULES:
                    v.add(
                        "ACCEPTANCE_UNSATISFIED",
                        f"/global_findings/{i}/finding",
                        f"Rule '{rid}' is always applicable and cannot be NOT_APPLICABLE for ACCEPT",
                        phase="evidence_accept",
                    )
            elif state == "PASS":
                if not f.get("evidence_ids"):
                    v.add(
                        "EVIDENCE_MISSING",
                        f"/global_findings/{i}/evidence_ids",
                        "PASS global finding must cite evidence",
                        phase="evidence_accept",
                    )

        # Always-applicable rules must be present and PASS.
        for rule in ALWAYS_APPLICABLE_RULES:
            if rule not in present_rules:
                v.add(
                    "EVIDENCE_MISSING",
                    "/global_findings",
                    f"ACCEPT requires global finding for rule '{rule}'",
                    phase="evidence_accept",
                )
                continue
            i, f = present_rules[rule]
            if f.get("finding") != "PASS":
                v.add(
                    "ACCEPTANCE_UNSATISFIED",
                    f"/global_findings/{i}/finding",
                    f"ACCEPT requires always-applicable rule '{rule}' to be PASS",
                    phase="evidence_accept",
                )

        if required_corrections:
            v.add("ACCEPTANCE_UNSATISFIED", "/required_corrections", "ACCEPT verdict cannot have required corrections", phase="evidence_accept")

        if human_decisions_required:
            v.add("ACCEPTANCE_UNSATISFIED", "/human_decisions_required", "ACCEPT verdict cannot have unresolved human decisions", phase="evidence_accept")
