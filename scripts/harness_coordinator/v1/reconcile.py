"""Reconciliation report assembly for the harness coordinator v1.

Implements design section 9: assembles a full reconciliation report from
durable state alone (the journal fold, terminal seals, and the O2/O3-P1
``compute_reconciliation`` invariant engine), reusing O3-P2's
``recovery._fold_journal`` and O3-P1's ``reconciliation.compute_reconciliation``
directly -- this module owns no parallel counting or invariant logic.

Two entry points, deliberately separate:

- ``build_reconciliation_report`` is PURE: reads durable state, computes
  the report in memory, returns it. No filesystem write, no journal
  append. This is what the read-only CLI (``cli.py``) uses exclusively.
- ``emit_reconciliation_report`` additionally writes the report to disk
  and journals a RECONCILIATION_EMITTED event for each bounded coordinator
  run. The read-only CLI never calls it.

D0.4 (no implicit clock, no implicit randomness): every function here
takes ``now``/``report_id`` as explicit arguments; nothing in this module
calls ``datetime.now()`` or ``uuid.uuid4()`` itself.

``integrity.preserved_evidence_mismatches`` is now independently rebuilt
from each immutable reassignment record through ``assert_preserved`` using
the same pinned state-root handle as the rest of the report. The remaining
disclosed limitation is ``integrity.state_cache_in_sync``: no prior packet
writes the optional ``state/<packet_id>.json`` projection, so that field
remains the schema-required placeholder and the report carries an explicit
``unverified_invariants`` attention item rather than silently claiming it
was checked.
"""

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_contracts.v1.reconciliation import compute_reconciliation, validate_reconciliation_report
from harness_contracts.v1.seal import validate_terminal_seal

from harness_coordinator.v1.recovery import (
    IntegrityError, WORKSPACE_STAGE_SPECS, _direct_state_root_path, _fold_journal, _last_seq,
    _make_event, bound_execution_plan_for_run, validate_workspace_stage_artifact,
)
from harness_coordinator.v1.budget_runtime import (
    _EvidenceError, _REVIEW_CAPABILITY_CLASSES, _implementer_invocations, _ordered_hops,
)
from harness_contracts.v1.packet import is_harness_id
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id
from harness_coordinator.v1.reassignment_runtime import assert_preserved
from harness_coordinator.v1.seals_runtime import open_state_root
from harness_coordinator.v1.store import append_journal, read_journal


def _read_manifest_read_only(state_root: str, expected_state_root_id: str, handle=None) -> Dict[str, Any]:
    """Read and validate MANIFEST.json WITHOUT the init-on-absent side
    effect ``recovery._read_or_init_manifest`` has (that function writes
    a fresh MANIFEST.json via ``atomic_replace`` when one is missing --
    unsafe to call from a read-only reporting/CLI path). A missing or
    mismatched MANIFEST.json is a real finding here (a typo'd
    ``--state-root``, or a state root that was never actually
    initialized by a real coordinator run), never silently treated as
    "nothing to reconcile yet"."""
    manifest_path = os.path.join(state_root, "MANIFEST.json")
    raw = handle.read(("MANIFEST.json",)) if handle is not None else None
    if handle is None and os.path.exists(manifest_path):
        with open(manifest_path, "rb") as f:
            raw = f.read()
    if raw is None:
        raise IntegrityError("INVALID_VALUE", f"No MANIFEST.json at {manifest_path} -- state root was never initialized by a coordinator run")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrityError("INVALID_JSON", f"MANIFEST.json is not valid JSON: {exc}")
    if not isinstance(manifest, dict):
        raise IntegrityError("INVALID_TYPE", "MANIFEST.json root must be an object")
    if manifest.get("schema_version") != 1:
        raise IntegrityError("INVALID_VALUE", "MANIFEST schema_version must be 1")
    declared_id = manifest.get("state_root_id")
    if not isinstance(declared_id, str) or not declared_id:
        raise IntegrityError("INVALID_VALUE", "MANIFEST state_root_id must be a non-empty string")
    declared_hash = manifest.get("manifest_sha256")
    computed_hash = compute_sha256(canonical_bytes(manifest, omit={"manifest_sha256"}))
    if declared_hash != computed_hash:
        raise IntegrityError("EVIDENCE_HASH_MISMATCH", "MANIFEST.json manifest_sha256 does not match canonical self-hash")
    if declared_id != expected_state_root_id:
        raise IntegrityError(
            "EVIDENCE_HASH_MISMATCH",
            f"MANIFEST.json declares state_root_id={declared_id!r}, caller expected {expected_state_root_id!r} -- wrong state root, or a stale/foreign one",
        )
    return manifest


def _check_seal_consistency(state_root: str, packets_by_id: Dict[str, Any], handle=None) -> List[Dict[str, Any]]:
    """Mirror ``_fold_journal``'s step-5 seal-consistency semantics
    (orphan seal, invalid seal JSON, state disagreement) but NEVER raise
    and NEVER abort -- return every finding, so one bad seal doesn't
    erase the report of every OTHER healthy packet.

    This intentionally duplicates ``_fold_journal``'s seal-check LOGIC,
    not its transition-legality logic (the actual concern D0.6 guards
    against reimplementing) -- crash recovery correctly treats a seal
    mismatch as fatal (design 2.6, "run-halting condition, must
    propagate": the coordinator must refuse to keep operating on
    inconsistent state). Reconciliation reporting is a DIFFERENT
    consumer with a different job -- itemizing every problem in a
    single morning report, not aborting on the first one -- so it
    deliberately does not inherit that abort behavior. ``packets_by_id``
    here comes from a fold against a PHANTOM seal directory (see
    ``build_reconciliation_report``), so it is never the one that
    would've triggered this exact check to begin with. Kept in lockstep
    with ``_fold_journal``'s step 5 by hand; if that check's semantics
    ever change, this must change too."""
    findings: List[Dict[str, Any]] = []
    if handle is not None:
        try:
            with handle.directory(("state", "terminal")) as seal_fd:
                names = sorted(os.listdir(seal_fd))
        except FileNotFoundError:
            return findings
    else:
        seal_dir = os.path.join(state_root, "state", "terminal")
        if not os.path.isdir(seal_dir):
            return findings
        names = sorted(os.listdir(seal_dir))
    for name in names:
        if not name.endswith(".seal.json"):
            continue
        pid = name[: -len(".seal.json")]
        try:
            validate_harness_id(pid)
            seal_path = safe_state_path(
                state_root, "state", "terminal", identifier=pid,
                identifier_suffix=".seal.json")
        except ValueError:
            findings.append({
                "packet_id": pid,
                "code": "TERMINAL_SEAL_MISMATCH",
                "detail": f"Seal path for {pid} escapes state root",
            })
            continue
        try:
            if handle is not None:
                raw = handle.read(("state", "terminal", name))
            else:
                with open(seal_path, "rb") as seal_file:
                    raw = seal_file.read()
            seal = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            findings.append({"packet_id": pid, "code": "TERMINAL_SEAL_MISMATCH", "detail": f"Seal for {pid} is not valid JSON: {exc}"})
            continue
        seal_result = validate_terminal_seal(seal)
        if not seal_result["valid"]:
            findings.append({"packet_id": pid, "code": "TERMINAL_SEAL_MISMATCH", "detail": f"Seal for {pid} is invalid: {seal_result['errors'][0]['message']}"})
            continue
        pkt = packets_by_id.get(pid)
        if pkt is None:
            findings.append({"packet_id": pid, "code": "TERMINAL_SEAL_MISMATCH", "detail": f"Seal exists for unenrolled packet {pid}"})
            continue
        if pkt.get("state") != seal.get("terminal_state"):
            findings.append({"packet_id": pid, "code": "TERMINAL_SEAL_MISMATCH", "detail": f"Seal state {seal.get('terminal_state')} does not match fold state {pkt.get('state')} for {pid}"})
    return findings


def _read_journal_pinned(handle, state_root_id: str):
    """Run the accepted journal parser over an FD pinned beneath the root."""
    try:
        journal_fd = os.open(
            "journal.ndjson", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=handle.fd)
    except FileNotFoundError:
        return [], None
    try:
        fd_root = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
        return read_journal(
            os.path.join(fd_root, str(journal_fd)), state_root_id=state_root_id)
    finally:
        os.close(journal_fd)


def _declares_workspace_evidence_v1(event: Dict[str, Any]) -> bool:
    versions = (((event.get("payload") or {}).get("run") or {})
                .get("contract_versions") or {})
    marker = versions.get("workspace_evidence")
    return type(marker) is int and marker == 1


def _workspace_evidence_attention(handle, journal_events: List[Dict[str, Any]],
                                  packets_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate O4's immutable stage bindings from the pinned state root."""
    stages = WORKSPACE_STAGE_SPECS
    attention: List[Dict[str, Any]] = []
    # The only O4 compatibility boundary is the authenticated RUN_STARTED
    # contract version. Packet/artifact presence is not a version signal:
    # legacy roots may have packet files, while missing O4 artifacts are
    # exactly what reconciliation must detect.
    o4_run_ids = {
        event.get("run_id")
        for event in journal_events
        if event.get("event_type") == "RUN_STARTED"
        and _declares_workspace_evidence_v1(event)
    }
    for packet_id, packet in sorted(packets_by_id.items()):
        started = [event for event in journal_events if event.get("event_type") == "ATTEMPT_STARTED"
                   and event.get("packet_id") == packet_id]
        o4_intent_ids = {
            start.get("intent_id") for start in started
            if start.get("run_id") in o4_run_ids and isinstance(start.get("intent_id"), str)
        }
        for start in started:
            intent_id = start.get("intent_id")
            if not isinstance(intent_id, str):
                continue
            o4_required = start.get("run_id") in o4_run_ids
            stage_events = {
                event_type: [event for event in journal_events if event.get("event_type") == event_type
                             and event.get("packet_id") == packet_id and event.get("intent_id") == intent_id]
                for event_type in stages
            }
            required = ["WORKSPACE_BASELINE_RECORDED"] if o4_required else []
            completed = any(event.get("event_type") == "ATTEMPT_FINISHED"
                            and event.get("packet_id") == packet_id
                            and event.get("intent_id") == intent_id
                            for event in journal_events)
            if completed and o4_required:
                required.append("WORKSPACE_POSTFLIGHT_RECORDED")
            for event_type in required:
                if not stage_events[event_type]:
                    code = ("workspace_baseline_missing" if event_type == "WORKSPACE_BASELINE_RECORDED"
                            else "workspace_postflight_missing")
                    attention.append({"packet_id": packet_id, "code": code,
                                      "detail": "%s has no durable %s for %s" %
                                      (packet_id, stages[event_type]["event_kind"], intent_id)})
            for event_type, events in stage_events.items():
                if not events:
                    continue
                kind, suffix = stages[event_type]["event_kind"], stages[event_type]["suffix"]
                expected_path = "workspace/%s/%s%s" % (packet_id, intent_id, suffix)
                artifact = (((events[0].get("payload") or {}).get("artifacts") or [None])[0])
                bad = len(events) != 1 or not isinstance(artifact, dict)
                if not bad:
                    raw = handle.read(tuple(expected_path.split("/")))
                    try:
                        persisted = validate_workspace_stage_artifact(raw, packet, intent_id, event_type, artifact)
                    except (IntegrityError, AttributeError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
                        bad = True
                if bad:
                    attention.append({"packet_id": packet_id, "code": "workspace_evidence_mismatch",
                                      "detail": "%s has an invalid %s binding for %s" %
                                      (packet_id, kind, intent_id)})
                if event_type == "WORKSPACE_POSTFLIGHT_RECORDED" and not bad:
                    for field, code in (("protected_findings", "protected_worktree_changed"),
                                        ("scope_findings", "allowlist_violation"),
                                        ("secret_findings", "secret_like_diff")):
                        if persisted.get(field):
                            attention.append({"packet_id": packet_id, "code": code,
                                              "detail": "%s postflight recorded %s" % (packet_id, field)})
                    if (packet.get("state") == "ACCEPTED"
                            and (persisted.get("acceptance_allowed") is not True
                                 or any(persisted.get(field) for field in (
                                     "scope_findings", "worker_manifest_findings", "protected_findings",
                                     "secret_findings")))):
                        attention.append({"packet_id": packet_id, "code": "workspace_evidence_mismatch",
                                          "detail": "%s is ACCEPTED without a passing postflight" % packet_id})
                if event_type == "INTEGRATION_MANIFEST_RECORDED" and not bad:
                    if persisted.get("decision") == "HUMAN_REQUIRED":
                        attention.append({"packet_id": packet_id, "code": "integration_human_required",
                                          "detail": "%s integration decision requires a human" % packet_id})
        if (packet.get("state") == "ACCEPTED" and o4_intent_ids and not any(
                event.get("event_type") == "WORKSPACE_POSTFLIGHT_RECORDED"
                and event.get("packet_id") == packet_id
                and event.get("intent_id") in o4_intent_ids for event in journal_events)):
            attention.append({"packet_id": packet_id, "code": "integration_human_required",
                              "detail": "%s is ACCEPTED without authenticated O4 postflight evidence" % packet_id})
    return attention


# ---------------------------------------------------------------------------
# O5 Task 5: plan-scoped row extension and terminal-disposition partition.
#
# ``compute_reconciliation`` (harness_contracts.v1.reconciliation) owns the
# actual invariant math (the six-way sum against ``planned``, folding O5
# findings into ``all_invariants_passed``) -- this section's job is purely
# ASSEMBLY: fetch the authenticated bound plan (if any), extend each row with
# real data read from the journal/plan, and classify each plan member into
# exactly one of the six closed terminal dispositions or, when the evidence
# genuinely does not resolve one, into none of them (a disclosed gap, never a
# guess -- see ``_o5_disposition``).
# ---------------------------------------------------------------------------

# Reason codes describing an observed/awaited PROVIDER capacity condition
# (budget_runtime.select_capable_route's PAUSE/BACKOFF outcomes). Sourced
# from budget_runtime.py's own PAUSE/BACKOFF reason-code literals -- kept as
# an explicit local list, not re-derived from
# ``journal.CAPACITY_EVENT_REASON_CODES`` (which is far broader: it also
# covers PACKET_BUDGET_*/MODEL_ROUTE_*/PLAN_SCOPE_* STOP-kind refusals that
# are NOT a provider-capacity condition -- see the comment on the
# blocked_human fallback below).
_O5_PROVIDER_REASON_CODES = frozenset({
    "PROVIDER_ALLOWANCE_EXHAUSTED",
    "PROVIDER_ALLOWANCE_UNAVAILABLE",
    "PROVIDER_ALLOWANCE_RESET_PENDING",
    "PROVIDER_BACKOFF_PENDING",
    "PROVIDER_BACKOFF_RETRIES_EXHAUSTED",
    "NO_CAPABLE_MODEL_AVAILABLE",
})

# A packet-level terminal fold state maps directly to a disposition with no
# further evidence needed. READY/RUNNING/BLOCKED/REVIEW are deliberately
# absent here -- those are resolved (or left unresolved) by
# ``_o5_disposition`` below, never guessed from state alone.
_O5_TERMINAL_DISPOSITION_BY_STATE = {
    "ACCEPTED": "accepted",
    "QUARANTINED": "quarantined",
    "HUMAN_REQUIRED": "blocked_human",
    "REVISE": "resting_revise",
}


def _o5_plan_packet_row(plan: Dict[str, Any], packet_id: str) -> Optional[Dict[str, Any]]:
    for row in plan.get("packets") or []:
        if row.get("packet_id") == packet_id:
            return row
    return None


def _o5_packet_paused_events(journal_events: List[Dict[str, Any]], packet_id: str) -> List[Dict[str, Any]]:
    """All ``PACKET_PAUSED`` events for one packet, in authenticated seq
    order (``journal_events`` is already seq-ordered by ``read_journal``)."""
    return [event for event in journal_events
            if event.get("event_type") == "PACKET_PAUSED" and event.get("packet_id") == packet_id]


def _o5_route_history(journal_events: List[Dict[str, Any]], packet_id: str) -> List[Dict[str, Any]]:
    """Every real routing decision recorded for one packet: which
    (provider, model_id) each ``ATTEMPT_STARTED`` actually invoked, and
    every ``MODEL_FALLBACK_SELECTED`` choice and its reason.

    Each returned entry also carries the ``run_id`` the event actually
    happened under (every journal event has one -- ``journal.py``'s schema
    requires it unconditionally). This is INTERNAL-ONLY: the public
    ``route_history`` field on a report row is schema-closed to exactly
    ``{seq, event_type, provider, model_id, reason_code}``
    (``additionalProperties: false``), so any caller that assigns this
    function's return value straight to ``row["route_history"]`` must strip
    ``run_id`` from each entry first (``_o5_plan_extension`` does this
    inline, once, when it builds ``row["route_history"]``).
    The route-authorization check (below, in ``_o5_plan_extension``) is the
    one caller that needs the unstripped ``run_id``: plan authorization is
    run-scoped (``bound_execution_plan_for_run`` selects by ``run_id``, and
    different runs against the same state root can have different bound
    plans), so checking an attempt's identity against "whichever plan is
    bound for the run currently being reconciled" is wrong whenever an
    attempt happened under a DIFFERENT run than the one being reconciled.
    """
    history: List[Dict[str, Any]] = []
    for event in journal_events:
        if event.get("packet_id") != packet_id:
            continue
        event_type = event.get("event_type")
        payload = event.get("payload") or {}
        event_run_id = event.get("run_id")
        if event_type == "ATTEMPT_STARTED":
            worker = ((payload.get("attempt") or {}).get("worker") or {})
            provider, model = worker.get("provider"), worker.get("model")
            if isinstance(provider, str) and isinstance(model, str):
                history.append({
                    "seq": event.get("seq"), "event_type": "ATTEMPT_STARTED",
                    "provider": provider, "model_id": model, "reason_code": None,
                    "run_id": event_run_id,
                })
        elif event_type == "MODEL_FALLBACK_SELECTED":
            body = payload.get("model_fallback") or {}
            provider, model = body.get("provider"), body.get("model_id")
            if isinstance(provider, str) and isinstance(model, str):
                history.append({
                    "seq": event.get("seq"), "event_type": "MODEL_FALLBACK_SELECTED",
                    "provider": provider, "model_id": model,
                    "reason_code": body.get("reason_code"),
                    "run_id": event_run_id,
                })
    history.sort(key=lambda item: item["seq"])
    return history


def _o5_hop_authorized(
    plan: Dict[str, Any], capability_class: Optional[str], identity: Tuple[str, str],
    implementer_identities: Optional[Set[Tuple[str, str]]] = None,
) -> bool:
    """Whether ``identity`` (a ``(provider, model_id)`` pair) is a hop the
    LIVE coordinator would actually ever be able to select for this
    capability class.

    **Honest scope (corrected O5 review round 4, finding B -- the previous
    docstring here claimed this "mirrors ``budget_runtime.select_capable_route``'s
    own real eligibility gate EXACTLY, condition for condition, not an
    approximation." That was false and is retracted, not softened.)**
    What this DOES check, matching the live selector condition for
    condition:

    - Reachability: reuses ``budget_runtime._ordered_hops`` DIRECTLY (same
      coordinator layer -- ``recovery.py`` and ``coordinator.py`` already
      import from ``budget_runtime.py``, so this is not a new layering
      dependency) to walk the SAME plan-pinned ``fallback_to`` reachability
      chain the live selector walks, starting from the capability class's
      first DECLARED hop. A hop present in the raw
      ``plan["routes"][capability_class]`` list that this chain never
      actually reaches (nothing points to it via ``fallback_to``, and
      positional fallthrough jumps past it because an earlier hop's
      ``fallback_to`` skips it) is never reachable by the live selector
      either, and must not read as "authorized" here -- O5 review round 3
      finding D3; this closed the gap round 2's fix (NEW-2, the
      enabled/qualification_id check below) did not: round 2 fixed WHICH
      declared hops count, D3 fixed WHICH declared hops the live selector
      can even reach in the first place.
    - Within the reachable set, a hop counts as authorized only when it is
      also ``enabled is True`` AND carries a present, valid-shaped
      ``qualification_id`` (``is_harness_id``), in addition to an exact
      ``(provider, model_id)`` match -- unchanged from round 2.
    - Reviewer-identity-diversity, exact-pair form only (O5 review round 4,
      finding B, closed the same pass this docstring was corrected): for a
      ``_REVIEW_CAPABILITY_CLASSES`` member (``independent_review``,
      ``adversarial_audit``), ``budget_runtime.select_capable_route`` also
      skips any candidate hop whose EXACT ``(provider, model_id)`` pair
      already appears in ``_implementer_invocations(journal_events)`` --
      "the same invocation cannot implement and then review itself,"
      checked project-wide over the WHOLE journal (that helper takes no
      ``packet_id`` and is never scoped to one -- confirmed by reading its
      body, not assumed), not merely the packet currently being judged.
      This function now replicates exactly that: a caller passing
      ``implementer_identities`` gets a hop that matches one of them
      treated as unauthorized for a review capability class, same as the
      live selector's ``if pair in implementers: continue``.

    **What this does NOT check (the real, disclosed residual gap, not
    closed this pass -- see the audit doc's Residual gaps section):** the
    live selector has a SECOND, weaker reviewer-diversity preference beyond
    the exact-pair exclusion above -- among hops that already survive it,
    if every remaining eligible hop shares a PROVIDER FAMILY with some
    implementer (even at a different model_id), the live selector refuses
    the whole decision (``HUMAN_REQUIRED``/``MODEL_ROUTE_REVIEWER_IDENTITY_CONFLICT``)
    rather than picking one. That is not a per-hop "is this identity ever
    authorized" fact the way everything else here is -- it depends on the
    full competing set of OTHER eligible hops at decision time (capacity/
    backoff state included), which is a different question in kind from
    what this function answers. A hop that only trips this weaker,
    provider-family-only rule can still read "authorized" here even though
    the live selector would, in that specific historical moment, have
    refused to pick it. Not replicated; not silently claimed to be.

    Fails closed (returns ``False`` for every identity) if the
    reachability walk itself cannot complete, or if ``capability_class``
    has no route table in this plan at all -- a cyclic or cross-class
    ``fallback_to`` is something ``validate_execution_plan`` already
    refuses at commissioning time, so this is a defensive backstop for an
    authenticated plan, never expected to actually fire.
    """
    if not isinstance(capability_class, str) or capability_class not in (plan.get("routes") or {}):
        return False
    try:
        hops = _ordered_hops(plan, capability_class)
    except _EvidenceError:
        return False
    review_class = capability_class in _REVIEW_CAPABILITY_CLASSES
    blocked_implementers = implementer_identities or set()
    for hop in hops:
        if hop.get("enabled") is not True:
            continue
        if not is_harness_id(hop.get("qualification_id")):
            continue
        if (hop.get("provider"), hop.get("model_id")) != identity:
            continue
        if review_class and identity in blocked_implementers:
            # Same exact-pair exclusion select_capable_route applies before
            # this hop could ever reach its own ``eligible`` list -- an
            # attempt using this identity for a review class is never
            # authorized, regardless of what else the route table lists.
            continue
        return True
    return False


def _o5_budget_usage(plan_packet: Dict[str, Any], pkt: Dict[str, Any]) -> Dict[str, Any]:
    budgets = plan_packet.get("budgets") or {}
    return {
        "attempt_limit": budgets.get("attempt_limit"),
        "retry_limit": budgets.get("retry_limit"),
        "revision_limit": budgets.get("revision_limit"),
        "attempts_started": pkt.get("attempts_started", 0),
        "infra_retries_used": pkt.get("infra_retries_used", 0),
        "revise_cycles_used": pkt.get("revise_cycles_used", 0),
    }


def _o5_provider_backoff_state(
    journal_events: List[Dict[str, Any]], plan: Dict[str, Any], capability_class: Optional[str],
) -> Optional[Dict[str, Any]]:
    """The latest authenticated ``PROVIDER_CAPACITY_RECORDED`` observation
    for this packet's capability class's PRIMARY plan-pinned route pair, or
    ``None`` if none was ever recorded. Last-write-wins over
    ``journal_events``' own authenticated seq order -- the same convention
    the fold itself already uses for every other packet-scoped field."""
    if not capability_class:
        return None
    routes = (plan.get("routes") or {}).get(capability_class) or []
    if not routes:
        return None
    primary = routes[0]
    target = (primary.get("provider"), primary.get("model_id"))
    latest: Optional[Dict[str, Any]] = None
    for event in journal_events:
        if event.get("event_type") != "PROVIDER_CAPACITY_RECORDED":
            continue
        body = (event.get("payload") or {}).get("provider_capacity") or {}
        if (body.get("provider"), body.get("model_id")) == target:
            latest = body
    if latest is None:
        return None
    return {
        "provider": latest.get("provider"), "model_id": latest.get("model_id"),
        "state": latest.get("state"), "reset_at": latest.get("reset_at"),
    }


def _o5_known_event_ids(journal_events: List[Dict[str, Any]]) -> Any:
    """Every real, authenticated event identity in this journal -- both the
    human-assigned ``event_id`` and the content ``event_sha256`` count as a
    real reference target, matching ``budget_runtime._evidence_id``'s own
    dual convention for what an ``evidence_ids`` entry may legitimately
    name."""
    known = set()
    for event in journal_events:
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id:
            known.add(event_id)
        digest = event.get("event_sha256")
        if isinstance(digest, str) and digest:
            known.add(digest)
    return known


def _o5_stop_reasons(journal_events: List[Dict[str, Any]], packet_id: str) -> List[str]:
    reasons = set()
    for event in _o5_packet_paused_events(journal_events, packet_id):
        reason = ((event.get("payload") or {}).get("packet_pause") or {}).get("reason_code")
        if isinstance(reason, str) and reason:
            reasons.add(reason)
    return sorted(reasons)


def _o5_disposition(
    pkt: Dict[str, Any], journal_events: List[Dict[str, Any]], packet_id: str,
) -> Optional[str]:
    """Exactly one of the six closed dispositions, or ``None`` when the
    evidence genuinely does not resolve one -- see the module docstring.
    Order matters, in this precedence:

    1. A genuinely terminal/resting fold state (ACCEPTED/QUARANTINED/
       HUMAN_REQUIRED/REVISE, ``_O5_TERMINAL_DISPOSITION_BY_STATE``) is
       authoritative over everything below it.
    2. A packet currently RUNNING or REVIEW has been successfully
       (re-)claimed and has a live or completed-but-unresolved attempt in
       flight -- this outranks ANY ``PACKET_PAUSED`` record, including one
       from the packet's own prior, now-superseded pause cycle.
       ``recovery.py``'s ``PACKET_PAUSED`` fold branch never transitions
       packet state (it is schema-forbidden from doing so -- see that
       branch's own comment) and its ``next_eligible_at`` backoff window is
       used VERBATIM when a real one is supplied, not always the indefinite
       sentinel -- so a packet that was backoff-paused and later
       successfully re-claimed still carries that OLD event in the journal
       even though it is now demonstrably live, not paused. A stale pause
       record must never outrank a live claim.
    3. Any other non-terminal state that has already accumulated a real
       attempt (``attempts_started > 0``) is likewise genuinely
       indeterminate, even if the packet has since fallen back to
       READY/BLOCKED (e.g. an infra-retry requeue) and even if it still
       carries an old ``PACKET_PAUSED`` record from before that attempt --
       ``attempts_started > 0`` is only ever set atomically with a
       transition through RUNNING (``ATTEMPT_STARTED``), so this condition
       is exactly "has been claimed at least once," stated a second way for
       states other than RUNNING/REVIEW themselves.
    4. Only a packet that has NEVER been claimed at all (state not RUNNING/
       REVIEW, ``attempts_started == 0``) falls through to pause-event-based
       classification (``paused_provider``/``blocked_human``).
    5. Otherwise: ``never_started``.
    """
    mapped = _O5_TERMINAL_DISPOSITION_BY_STATE.get(pkt.get("state"))
    if mapped is not None:
        return mapped
    if pkt.get("state") in ("RUNNING", "REVIEW"):
        # Genuinely indeterminate -- see this module's docstring and
        # ``_o5_plan_extension``'s own ``plan_disposition_indeterminate``
        # attention item, which the caller is required to also append
        # whenever this returns None.
        return None
    if pkt.get("attempts_started", 0) > 0:
        # Same indeterminate outcome as the RUNNING/REVIEW branch above,
        # reached from a state that has since moved on (e.g. READY after an
        # infra retry) -- deliberately checked BEFORE the pause-event
        # lookup below, so a stale PACKET_PAUSED record from before this
        # packet was ever claimed can never outrank the fact that it has.
        return None
    paused = _o5_packet_paused_events(journal_events, packet_id)
    if paused:
        latest_reason = ((paused[-1].get("payload") or {}).get("packet_pause") or {}).get("reason_code")
        if latest_reason in _O5_PROVIDER_REASON_CODES:
            return "paused_provider"
        # Every other capacity-family reason code this codebase's own
        # PACKET_PAUSED vocabulary admits (HUMAN_AUTHORITY_REQUIRED,
        # MODEL_ROUTE_REVIEWER_IDENTITY_CONFLICT, and the budget/plan-
        # integrity refusals -- BUDGET_EVIDENCE_INVALID, PLAN_SCOPE_*,
        # MODEL_ROUTE_NOT_IN_PLAN, MODEL_ROUTE_FALLBACK_CYCLE,
        # MODEL_ROUTE_CROSS_CLASS_FALLBACK, PACKET_BUDGET_*) is a stop this
        # automated classifier cannot self-resolve -- REASONED JUDGMENT
        # CALL, disclosed here rather than left implicit: default to
        # blocked_human (a human needs to look), never silently fold into
        # paused_provider, which would misreport a plan/budget-config
        # problem as something that clears on its own once a provider's
        # capacity resets.
        return "blocked_human"
    return "never_started"


def _o5_implementer_identities_by_seq(journal_events: List[Dict[str, Any]]) -> List[Tuple[Any, Tuple[str, str]]]:
    """Every real implementation-lane ``ATTEMPT_STARTED`` identity in this
    journal, paired with its own authenticated ``seq``, sorted by ``seq``.

    O5 review round 5, finding N1: ``_o5_hop_authorized``'s
    reviewer-diversity exclusion needs the implementer set as it stood AT
    THE MOMENT each individual claim was actually decided -- never a single
    whole-journal set applied uniformly and retroactively to every attempt
    (see ``_o5_plan_extension``'s use of this, below, and
    ``_o5_implementers_before_seq``, which turns this list into that
    per-attempt-scoped set). Built ONCE here as a sorted LIST, not a flat
    set -- exactly the same "compute the raw material once, scope it
    per-attempt at the check site" discipline ``_o5_plan_for_run`` already
    applies to plan binding (see that function's own docstring), applied
    here to implementer identity instead of plan identity; not a new
    pattern.

    Reuses ``budget_runtime._implementer_invocations`` PER EVENT (a
    one-event slice) rather than reimplementing its
    ``event_type``/``lane``/identity-shape filtering a second time here --
    the two therefore cannot silently drift apart the way two independent
    copies of the same ``_IMPLEMENTATION_LANES`` check could.
    """
    invocations: List[Tuple[Any, Tuple[str, str]]] = []
    for event in journal_events:
        if event.get("event_type") != "ATTEMPT_STARTED":
            continue
        for identity in _implementer_invocations([event]):
            invocations.append((event.get("seq"), identity))
    invocations.sort(key=lambda item: item[0])
    return invocations


def _o5_implementers_before_seq(
    invocations_by_seq: List[Tuple[Any, Tuple[str, str]]], before_seq: Any,
) -> Set[Tuple[str, str]]:
    """The implementer-identity set as it stood strictly BEFORE
    ``before_seq`` -- i.e. exactly what the live
    ``budget_runtime.select_capable_route`` gate could have seen at the
    moment the claim recorded at ``before_seq`` was actually decided (O5
    review round 5, finding N1).

    Two reproduced shapes this closes, both by the same seq-ordering fix:
    (1) temporal -- a review-class attempt on identity X made BEFORE any
    implementation-lane attempt on X must not be retroactively flagged once
    a LATER implementation attempt on X appears anywhere in the journal;
    (2) self-inclusion -- a review-capability-class packet whose own
    enrolled ``lane`` happens to be an implementation lane must not have
    its OWN not-yet-recorded ``ATTEMPT_STARTED`` counted into the set used
    to judge itself, since strictly-before excludes an event from its own
    set unconditionally (a real journal never has two events sharing one
    ``seq``).

    ``before_seq is None`` (a malformed/missing ``seq`` on the attempt
    actually being checked) fails closed to the FULL set -- the
    over-inclusive direction here: ``blocked_implementers`` only ever
    narrows what ``_o5_hop_authorized`` treats as authorized, never widens
    it, so a larger implementer set can produce a false POSITIVE (flagged
    when a real live gate would have allowed it) but never let a
    genuinely-unauthorized identity read as authorized -- the same
    fail-closed convention every other check in this module already uses
    (e.g. ``attempt_route_plan_unresolvable`` above, flagged rather than
    skipped on an unresolvable plan).
    """
    if before_seq is None:
        return {identity for _, identity in invocations_by_seq}
    return {identity for seq, identity in invocations_by_seq if seq is not None and seq < before_seq}


def _o5_plan_for_run(
    state_root: str, journal_events: List[Dict[str, Any]], for_run_id: Any,
    cache: Dict[Any, Tuple[bool, Optional[Dict[str, Any]]]],
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Resolve (and cache) the authenticated plan bound for ``for_run_id``,
    memoized across one whole ``_o5_plan_extension`` call so a packet whose
    route history spans several runs -- or several packets that share a
    run -- never re-authenticates the same plan artifact twice.

    Returns ``(ok, plan)``. ``ok`` is ``False`` only when authenticating
    THIS run's binding itself failed (a corrupted/cyclic artifact) --
    everything else about that run is unknown, so callers must fail closed
    rather than proceed. ``plan`` is ``None`` both when ``ok`` is False and
    when the run genuinely has no plan bound at all; callers that need to
    authorize a route never need to distinguish those two cases, because
    both mean the same thing here: an attempt under this run cannot be
    authorized, so it fails closed either way. ``for_run_id`` that is not a
    real run_id (e.g. ``None``, from a malformed journal event) simply
    matches no ``EXECUTION_PLAN_BOUND`` event and resolves to
    ``(True, None)`` -- also handled as "cannot authorize" by the caller,
    with no special-casing needed here.
    """
    if for_run_id in cache:
        return cache[for_run_id]
    try:
        resolved_plan = bound_execution_plan_for_run(state_root, journal_events, for_run_id)
    except IntegrityError:
        result: Tuple[bool, Optional[Dict[str, Any]]] = (False, None)
    else:
        result = (True, resolved_plan)
    cache[for_run_id] = result
    return result


def _o5_plan_extension(
    state_root: str, journal_events: List[Dict[str, Any]], run_id: str,
    packets_by_id: Dict[str, Dict[str, Any]], rows: List[Dict[str, Any]],
) -> Any:
    """Fetch the authenticated bound plan (if any) and extend ``rows`` in
    place with Task 5's O5 fields. Returns ``(plan_scope, o5_violations)``
    for ``compute_reconciliation`` (harness_contracts.v1.reconciliation).

    Never raises: a plan-authentication failure (a corrupted/tampered
    artifact, a cyclic route table, ...) is reported via
    ``plan_scope["authentication_error"]``, not propagated -- this module's
    own established convention (see ``build_reconciliation_report``'s
    docstring: a bad seal or a bad reassignment record never aborts the
    whole report either) applies equally to a bad plan.

    Route authorization (below) is checked per-``ATTEMPT_STARTED`` against
    the plan that was ACTUALLY BOUND for that specific event's own
    ``run_id`` -- never against ``plan`` (this run's own binding) applied
    blindly to every attempt in a packet's whole history. Plan authorization
    is inherently run-scoped: ``bound_execution_plan_for_run`` selects by
    ``run_id``, and a state root can legitimately have several runs, each
    with its own bound plan (an amendment mid-project is a real, supported
    pattern -- ``test_o3_p5_resume.py`` already exercises multiple runs
    against one state root). Checking every attempt against only the
    CURRENT run's plan produces both false positives (a legitimate attempt
    from an earlier run, under ITS OWN bound plan, reported as unauthorized
    when reconciling a later run) and false negatives (a genuinely
    unauthorized attempt from a later run never flagged while reconciling
    an earlier one) -- see ``_o5_plan_for_run``.

    The per-packet ``plan_attempt_budget_exceeded`` check (O5 review round 4
    finding A) applies the identical run-scoping principle, deliberately, not
    by oversight: each ``ATTEMPT_STARTED`` is a claim that was granted at a
    specific historical moment, under whatever plan was ACTUALLY bound to
    that moment's own run -- so whether that ONE claim was within budget is
    judged against attempt_limit from THAT run's own bound plan, at the
    cumulative attempt count that had actually accrued by then, never
    against whichever plan happens to be bound to the run currently being
    reconciled. This was investigated, not assumed: ``budget_runtime.
    evaluate_preclaim`` (the live gate) reads ``attempts_started`` as a
    single journal-wide counter that is NEVER reset or scoped per run (see
    ``budget_runtime._journal_usage``, which has no ``run_id`` parameter at
    all) -- but it only ever compares that counter against the ONE plan
    bound to whichever coordinator run is live AT THE MOMENT a NEW claim is
    being decided; it never re-judges an attempt that already happened
    against a plan adopted afterward. A plan amendment that tightens
    attempt_limit is a real, legitimate, forward-looking policy change: it
    correctly stops FURTHER claims once the live coordinator re-evaluates
    under the new plan (that is ``evaluate_preclaim``'s job, not this
    report's), but it must not retroactively brand an attempt that was
    fully legitimate under the more generous plan it actually ran under as
    a budget VIOLATION -- exactly the same false-positive shape D2 fixed
    for route authorization, and the reviewer reproduced it live the same
    way. This also matches a distinction this file already draws elsewhere
    for the sibling O3 ``retry_limit`` concept (see the
    ``attempt_budget_exhausted``/``retry_budget_exceeded`` split further
    below): a packet legitimately resting at a cap is never the same
    finding as a structural violation that should never happen. The
    alternative model -- evaluating attempts cumulatively across every run
    against whichever ONE plan the caller currently has in hand -- was
    considered and rejected for exactly the reason above: it does not match
    what the live coordinator itself does, and it would flag a run's own
    report as failed for a plan amendment that run had no part in.

    By contrast, ``row["capability_class"]``, ``row["budget_usage"]``, and
    ``row["provider_backoff_state"]`` (assigned below) are correctly
    current-run-scoped BY DESIGN, not a related gap: they are informational
    DISPLAY fields answering "what does the run currently being reconciled
    say about this packet" (current cumulative usage against THIS run's own
    limits; THIS run's own plan-pinned primary route's latest observed
    capacity state) -- never a pass/fail judgment about whether a PAST event
    was authorized, so there is no historical-misattribution failure mode
    for a false-positive/false-negative pair to open in the first place. It
    is expected, not a bug, that these three fields read differently when
    the same packet is reconciled under two different runs' plans.
    """
    try:
        plan = bound_execution_plan_for_run(state_root, journal_events, run_id)
    except IntegrityError as exc:
        return {"bound": True, "authentication_error": "%s: %s" % (exc.code, exc.message)}, []

    if plan is None:
        return {"bound": False}, []

    plan_member_ids = {row.get("packet_id") for row in (plan.get("packets") or [])}
    o5_violations: List[Dict[str, Any]] = []
    known_event_ids = _o5_known_event_ids(journal_events)
    # Pre-seed with the current run's own plan -- already successfully
    # resolved above, so this avoids re-authenticating it and guarantees
    # the current run's own attempts are checked against the exact same
    # plan object the rest of this function already uses.
    run_plan_cache: Dict[Any, Tuple[bool, Optional[Dict[str, Any]]]] = {run_id: (True, plan)}
    # O5 review round 4 finding B: the reviewer-identity-diversity exclusion
    # ``select_capable_route`` applies for review capability classes
    # (``_REVIEW_CAPABILITY_CLASSES``) is computed over the WHOLE journal,
    # never scoped to one packet or one run -- ``budget_runtime.
    # _implementer_invocations`` takes no ``packet_id``/``run_id`` parameter
    # at all (confirmed by reading its body, not assumed). Round 4 stopped
    # there and reused ONE flat set, computed once, for every attempt --
    # CORRECTED in round 5 (finding N1, retracted, not softened): the live
    # gate is called BEFORE that specific claim's own ATTEMPT_STARTED is
    # appended, so it only ever sees implementer identities that already
    # existed AT THAT MOMENT, never a later one and never (for a review-class
    # packet whose own enrolled lane happens to be an implementation lane)
    # its own not-yet-recorded attempt. A single whole-journal set applied
    # uniformly to every attempt retroactively flagged an attempt that was
    # correctly authorized at the time it was actually claimed -- reproduced
    # two ways: a review attempt on identity X preceding a LATER
    # implementation attempt on X (temporal), and a review-class packet's own
    # implementation-lane attempt counted against itself with no other
    # implementer anywhere in the journal (self-inclusion). Fixed by scoping
    # per-attempt instead: the raw (seq, identity) material is still built
    # exactly ONCE here -- not a per-packet or per-run recomputation -- but
    # as a sorted LIST (``_o5_implementer_identities_by_seq``), and each
    # attempt below derives its OWN implementer set via
    # ``_o5_implementers_before_seq(before_seq=<that attempt's own seq>)``
    # immediately before calling ``_o5_hop_authorized``, rather than reusing
    # one flat set computed here.
    implementer_invocations_by_seq = _o5_implementer_identities_by_seq(journal_events)

    for row in rows:
        pid = row["packet_id"]
        plan_packet = _o5_plan_packet_row(plan, pid)
        if plan_packet is None:
            # Enrolled under this journal but not a member of the bound
            # plan. DETECTION BACKSTOP ONLY: build_reconciliation_report's
            # own fold runs against a phantom seal directory (never a real
            # state root -- see its docstring), so recovery.py's
            # ``_fold_journal`` plan-scope retro-check
            # (``_validate_plan_packet_binding``) never actually fires on
            # THIS fold -- only a real coordinator fold gets that live
            # protection (Task 4's scheduler/enroll gates already refuse
            # this before a claim in the live path). This closes the same
            # gap here, independently, for whoever reads a reconciliation
            # report.
            o5_violations.append({
                "packet_id": pid, "code": "packet_outside_bound_plan",
                "detail": "%s is enrolled under this run but is not a member of the bound plan" % pid,
            })
            continue

        pkt = packets_by_id.get(pid) or {}
        capability_class = plan_packet.get("capability_class")
        disposition = _o5_disposition(pkt, journal_events, pid)

        row["plan_id"] = plan.get("plan_id")
        row["plan_sha256"] = plan.get("plan_sha256")
        row["capability_class"] = capability_class
        # Full history (with each entry's own run_id) is kept locally for
        # the run-scoped authorization check below; the report row only
        # ever carries the schema-shaped, run_id-stripped public form (see
        # ``_o5_route_history``'s docstring for why the two must differ).
        full_route_history = _o5_route_history(journal_events, pid)
        row["route_history"] = [
            {key: value for key, value in entry.items() if key != "run_id"}
            for entry in full_route_history
        ]
        row["budget_usage"] = _o5_budget_usage(plan_packet, pkt)
        row["provider_backoff_state"] = _o5_provider_backoff_state(journal_events, plan, capability_class)
        row["stop_reasons"] = _o5_stop_reasons(journal_events, pid)
        row["disposition"] = disposition

        for pause_event in _o5_packet_paused_events(journal_events, pid):
            body = (pause_event.get("payload") or {}).get("packet_pause") or {}
            for evidence_id in body.get("evidence_ids") or []:
                if evidence_id not in known_event_ids:
                    # No pre-existing check cross-references PACKET_PAUSED's
                    # evidence_ids against real journal event identities --
                    # a fabricated/forged reference here would otherwise
                    # pass every existing structural check (evidence_ids is
                    # only format-validated -- a non-empty string -- by
                    # journal.py's own schema).
                    o5_violations.append({
                        "packet_id": pid, "code": "forged_evidence_reference",
                        "detail": (
                            "%s's PACKET_PAUSED evidence_ids references %r, "
                            "which does not match any real event_id or "
                            "event_sha256 in this journal" % (pid, evidence_id)
                        ),
                    })

        if disposition is None:
            o5_violations.append({
                "packet_id": pid, "code": "plan_disposition_indeterminate",
                "detail": (
                    "%s has attempts_started > 0 but is not terminal, resting in REVISE, "
                    "or explained by a PACKET_PAUSED record at report time -- most likely a "
                    "currently open attempt or a pending review verdict" % pid
                ),
            })

        # RUN-SCOPED attempt-budget check (O5 review round 4 finding A --
        # see this function's own docstring for the full investigation and
        # why run-scoping, not cumulative-across-runs-against-one-plan, is
        # the correct model here). Walk this packet's REAL attempt history
        # in authenticated seq order (``full_route_history`` is already
        # seq-sorted -- see ``_o5_route_history``), maintaining a running
        # ordinal that is the SAME cumulative count ``attempts_started``
        # itself represents (global to the packet, never reset per run --
        # matching ``budget_runtime._journal_usage``'s own convention). For
        # each individual ``ATTEMPT_STARTED``, that ordinal is compared
        # against the attempt_limit of the plan that was ACTUALLY BOUND to
        # THAT event's own run_id -- i.e. "was this specific claim, at the
        # cumulative position it actually occupied, within the budget its
        # own governing plan allowed AT THE TIME" -- never against
        # whichever plan the caller currently has in hand. This is
        # deliberately NOT deduplicated by identity the way the route-
        # authorization loop below is: every individual attempt must
        # advance the ordinal, since collapsing repeats would undercount
        # and could hide a real overrun.
        attempt_ordinal = 0
        for budget_entry in full_route_history:
            if budget_entry["event_type"] != "ATTEMPT_STARTED":
                continue
            attempt_ordinal += 1
            budget_entry_run_id = budget_entry.get("run_id")
            budget_plan_ok, budget_plan = _o5_plan_for_run(
                state_root, journal_events, budget_entry_run_id, run_plan_cache)
            if not budget_plan_ok or budget_plan is None:
                # Already reported once, for this same run_id, as
                # ``attempt_route_plan_unresolvable`` by the route-
                # authorization loop below (it walks the same run_id
                # space) -- do not double-report the identical underlying
                # authentication failure under a second code. There is
                # nothing further this specific check can safely conclude
                # about THIS attempt's budget compliance without an
                # authenticated plan to check it against, so it is skipped,
                # not silently passed (the report is already fail-closed
                # via the other code).
                continue
            budget_plan_packet = _o5_plan_packet_row(budget_plan, pid)
            if budget_plan_packet is None:
                # Same reasoning: already reported once above.
                continue
            entry_attempt_limit = (budget_plan_packet.get("budgets") or {}).get("attempt_limit")
            if (isinstance(entry_attempt_limit, int) and not isinstance(entry_attempt_limit, bool)
                    and attempt_ordinal > entry_attempt_limit):
                o5_violations.append({
                    "packet_id": pid, "code": "plan_attempt_budget_exceeded",
                    "detail": (
                        "%s's attempt #%d (seq %s, run %r) exceeds the attempt_limit "
                        "of %d in the plan actually bound for THAT run -- a claim was "
                        "granted beyond what its own governing plan permitted at the "
                        "time"
                        % (pid, attempt_ordinal, budget_entry.get("seq"), budget_entry_run_id,
                           entry_attempt_limit)
                    ),
                })

        # DETECTION BACKSTOP ONLY -- this cannot and does not prevent the
        # live invocation that already happened under an unauthorized
        # identity. classify_runtime.py's routing paths (both the ordinary
        # ``select_capable_route`` flow and the legacy Kimi-to-Sonnet
        # reassignment lane, ``_resolve_reassignment_cause``) run
        # unconditionally today and never consult reconciliation before a
        # claim. Fixing that live coordinator-path gap is explicitly OUT OF
        # SCOPE for this change (deferred to a separate follow-up task) --
        # this only makes the drift visible, after the fact, in
        # reconciliation.
        #
        # Covers EVERY durable ATTEMPT_STARTED identity recorded for this
        # plan-member packet -- not only ones that went through the legacy
        # reassignment lane (O5 review round 2 finding NEW-1: the prior
        # check here was gated behind ``reassignment_used and lane ==
        # "sonnet_implementation"``, so a plan-member packet whose
        # ATTEMPT_STARTED recorded an out-of-plan identity via any OTHER
        # route -- not the legacy reassignment path -- produced zero
        # violations). A legacy reassignment's invoked identity is itself
        # just one more ATTEMPT_STARTED entry in ``row["route_history"]``
        # (already computed above), so this single general check subsumes
        # the narrower reassignment-only check that used to live here --
        # the dedicated ``_o5_reassignment_target_identity`` helper is
        # removed as redundant, not kept alongside this.
        #
        # Target-granular, not provider-granular: this checks each
        # attempt's REAL invoked ``(provider, model_id)`` against an EXACT,
        # currently-authorized, and currently-REACHABLE hop in the route
        # table for this capability_class (``_o5_hop_authorized`` -- reuses
        # ``budget_runtime._ordered_hops`` to walk the same fallback_to
        # reachability chain the live selector walks, then requires enabled
        # AND a valid qualification_id, plus (O5 review round 4 finding B,
        # closed this pass) the exact-pair reviewer-identity-diversity
        # exclusion for review capability classes -- see
        # ``_o5_hop_authorized``'s own docstring for precisely what is and
        # is not replicated; "mirrors the live gate EXACTLY, condition for
        # condition" was found FALSE in round 4 and that claim is retracted
        # here too, not merely at the docstring) -- not merely whether the
        # route table happens to mention the same provider anywhere, not a
        # hop the plan lists but disables or leaves unqualified, and not a
        # hop the plan lists but the live fallback_to chain never actually
        # reaches. A route table that authorizes
        # ``anthropic/claude-sonnet-4-5`` does not thereby authorize
        # ``anthropic/claude-opus-5`` or any other anthropic model the plan
        # never actually listed (or listed but disabled, or listed but
        # unreachable).
        #
        # RUN-SCOPED (O5 review round 3 finding D2): each ATTEMPT_STARTED is
        # checked against the plan that was ACTUALLY BOUND for THAT event's
        # own run_id -- via ``_o5_plan_for_run`` -- never against ``plan``
        # (the run currently being reconciled) applied uniformly to a
        # packet's entire cross-run history. This also re-derives
        # ``capability_class`` from THAT run's own plan-packet row, not the
        # current run's, since a plan amendment can change a packet's
        # capability_class assignment along with its routes. Dedup key is
        # (identity, run_id, <identity in its own seq-scoped implementer
        # set>), not (identity, run_id) alone -- the same (provider,
        # model_id) invoked under two different runs can be authorized under
        # one and not the other, so collapsing across runs could hide a real
        # violation. The third component exists for the identical reason,
        # one level finer (O5 review round 6, finding N3, fixing a fail-open
        # regression N1 introduced): before N1, ``_o5_hop_authorized``'s
        # verdict for a given entry was a pure function of (plan-for-that-
        # run, capability_class, identity), so any two ATTEMPT_STARTED
        # entries sharing (identity, run_id) were guaranteed to produce the
        # same verdict and collapsing them was safe. N1 made the verdict
        # also depend on the attempt's own seq, via a per-attempt-scoped
        # implementer set (``_o5_implementers_before_seq``) that only grows
        # as seq advances -- so two entries can now share (identity, run_id)
        # and still legitimately produce DIFFERENT verdicts: e.g. a
        # review-class packet's attempt on identity X made before any
        # implementer claimed X (authorized) followed by a second attempt on
        # the SAME identity, in the SAME run, made after some OTHER packet
        # implemented on X in between (must be refused, since that second
        # attempt is exactly the self-review the live gate exists to catch).
        # Keying dedup on (identity, run_id) alone after N1 meant the
        # surviving entry was, by construction, always the EARLIEST -- and
        # therefore the MOST PERMISSIVE, since the scoped set only grows --
        # so a genuinely illegitimate later attempt was silently skipped by
        # dedup and never even reached ``_o5_hop_authorized``, let alone got
        # flagged: fail-open. Folding "is this identity itself in its own
        # seq-scoped implementer set" into the key restores the original
        # guarantee -- entries sharing the extended key are once again
        # guaranteed identical verdicts, because ``_o5_hop_authorized``'s
        # reviewer-diversity exclusion only ever checks exact membership of
        # THIS identity in the passed set (see its docstring: "a caller
        # passing ``implementer_identities`` gets a hop that matches ONE OF
        # THEM treated as unauthorized" -- membership, not the set's other
        # contents), so this boolean fully captures the set's effect on this
        # identity's own authorization; there is no need to key on the whole
        # set or the raw seq. This requires computing
        # ``entry_implementer_identities`` before the dedup check rather
        # than after, since the key now depends on it.
        seen_identities: Set[Tuple[Tuple[str, str], Any, bool]] = set()
        for entry in full_route_history:
            if entry["event_type"] != "ATTEMPT_STARTED":
                continue
            identity = (entry["provider"], entry["model_id"])
            entry_run_id = entry.get("run_id")
            # O5 review round 5 finding N1's fix, moved up from below the
            # dedup check (round 6 finding N3 -- see the block comment
            # above): each attempt's own implementer set is the seq-scoped
            # snapshot of identities recorded strictly BEFORE this attempt's
            # own seq, never the whole-journal set -- so a later
            # implementation attempt on this identity never retroactively
            # poisons an earlier, correctly-authorized review attempt, and
            # this attempt's own identity (if it is itself
            # implementation-lane) is never counted against itself. See
            # ``_o5_implementers_before_seq``'s docstring for the full
            # reasoning and both reproduced shapes this closes.
            entry_implementer_identities = _o5_implementers_before_seq(
                implementer_invocations_by_seq, entry.get("seq"))
            dedup_key = (identity, entry_run_id, identity in entry_implementer_identities)
            if dedup_key in seen_identities:
                continue
            seen_identities.add(dedup_key)

            entry_plan_ok, entry_plan = _o5_plan_for_run(state_root, journal_events, entry_run_id, run_plan_cache)
            if not entry_plan_ok or entry_plan is None:
                # Fail closed (per the task instruction): if the attempt's
                # own run's plan cannot be authenticated or was never bound,
                # do not skip the check -- flag it. This also covers a
                # malformed/missing run_id on the source event, which
                # resolves to entry_plan is None the same way.
                o5_violations.append({
                    "packet_id": pid, "code": "attempt_route_plan_unresolvable",
                    "detail": (
                        "%s has a durable ATTEMPT_STARTED under run %r that invoked "
                        "%s/%s, but the execution plan bound for THAT run cannot be "
                        "authenticated or was never bound, so route authorization "
                        "cannot be verified"
                        % (pid, entry_run_id, identity[0], identity[1])
                    ),
                })
                continue

            entry_plan_packet = _o5_plan_packet_row(entry_plan, pid)
            if entry_plan_packet is None:
                o5_violations.append({
                    "packet_id": pid, "code": "attempt_route_plan_unresolvable",
                    "detail": (
                        "%s has a durable ATTEMPT_STARTED under run %r that invoked "
                        "%s/%s, but %s is not a member of that run's own bound plan, "
                        "so route authorization cannot be verified"
                        % (pid, entry_run_id, identity[0], identity[1], pid)
                    ),
                })
                continue

            entry_capability_class = entry_plan_packet.get("capability_class")
            # entry_implementer_identities was already computed above, before
            # the dedup check, since the dedup key now depends on it (O5
            # review round 6, finding N3) -- reused here as-is, not
            # recomputed.
            if not _o5_hop_authorized(entry_plan, entry_capability_class, identity, entry_implementer_identities):
                o5_violations.append({
                    "packet_id": pid, "code": "attempt_route_not_in_plan",
                    "detail": (
                        "%s has a durable ATTEMPT_STARTED under run %r that actually "
                        "invoked %s/%s, which the plan bound for THAT run's route "
                        "table for capability_class '%s' does not authorize (no "
                        "ENABLED hop with a valid qualification_id and that exact "
                        "provider/model_id)"
                        % (pid, entry_run_id, identity[0], identity[1], entry_capability_class)
                    ),
                })

    enrolled_ids = {row["packet_id"] for row in rows}
    for pid in sorted(plan_member_ids - enrolled_ids):
        o5_violations.append({
            "packet_id": pid, "code": "plan_member_never_enrolled",
            "detail": "%s is a member of the bound plan but was never enrolled" % pid,
        })

    plan_scope = {
        "bound": True,
        "authentication_error": None,
        "planned_packet_ids": sorted(plan_member_ids),
    }
    return plan_scope, o5_violations


def build_reconciliation_report(
    state_root: str,
    state_root_id: str,
    coordinator_id: str,
    run_id: str,
    report_id: str,
    now: str,
    handle=None,
) -> Dict[str, Any]:
    """Pure: read durable state, compute and return a full reconciliation
    report (design section 9.1's schema). Never writes anything.

    First validates MANIFEST.json exists and its declared
    ``state_root_id`` matches the caller's expectation
    (``_read_manifest_read_only``, WITHOUT the init-on-absent write
    ``recovery._read_or_init_manifest`` has) -- a missing or wrong-id
    state root is a real finding (typo'd path, never-initialized root),
    never silently reported as "empty and healthy."

    Validates MANIFEST.json exists and its declared ``state_root_id``
    matches (see above), then confirms ``journal.ndjson`` itself exists
    (its absence, alongside a real MANIFEST, must never report as an
    empty-and-healthy state root -- either the coordinator crashed before
    ever writing ``RUN_STARTED``, or the journal, the sole D0.1 commit
    point, was lost -- both are attention-worthy, never silent).

    Folds the journal via O3-P2's own ``_fold_journal`` (never
    reimplemented for TRANSITION legality -- that's D0.6's actual
    concern) -- but against a PHANTOM seal directory (the same technique
    ``replay_schedule.py`` uses for its own prefix folds), so a
    disagreeing/orphan terminal seal can never abort the fold and erase
    the report of every OTHER healthy packet. Seal consistency is then
    checked SEPARATELY, non-fatally, over the REAL state root via
    ``_check_seal_consistency`` (see its docstring for why this doesn't
    violate D0.6). A genuine TRANSITION/chain-level fold failure (not
    seal-related -- e.g. a terminal-safety violation) still aborts and is
    reported as ``fold_failed``, since that failure mode genuinely can't
    be attributed to one packet without risking a wrong or misleading
    partial inventory.

    ``read_journal`` itself can raise ``store.JournalChainBroken`` /
    ``store.JournalHeadMoved`` for a genuinely unparseable or foreign
    journal -- these propagate raw out of this function, exactly as
    ``recovery.run_started_recovery`` already documents doing for the
    same calls; callers (the CLI) are responsible for catching them.

    Hands the assembled ``fold_data`` to O3-P1's ``compute_reconciliation``
    -- the sole invariant engine (I1-I12), reused exactly as O3-P1 built it;
    this module does not recompute I9 (accounting identity) itself, only
    reads back what ``compute_reconciliation`` already found.

    Deterministic and replayable: given the same journal + seal files, the
    report's ``content_sha256`` (which omits report_id/generated_at/
    coordinator_id/run_id/report_sha256/content_sha256 itself) is
    byte-identical across repeated calls -- design 9.2's report
    determinism (fixture G8).
    """
    if handle is None:
        with open_state_root(_direct_state_root_path(state_root)) as pinned:
            return build_reconciliation_report(
                state_root, state_root_id, coordinator_id, run_id, report_id, now,
                handle=pinned)

    handle.verify_identity()
    _read_manifest_read_only(state_root, state_root_id, handle=handle)

    journal_path = os.path.join(state_root, "journal.ndjson")
    journal_events, torn_tail = _read_journal_pinned(handle, state_root_id)
    journal_chain_valid = torn_tail is None
    # A journal with zero real events and no torn tail is not a
    # legitimate "nothing happened yet" state: the only creation point
    # anywhere is append_journal's O_CREAT (store.py), and
    # read_journal/callers never create one -- so this is reachable only
    # by a crash between O_CREAT and the first fsync'd write, or by
    # tampering/a bad restore. Content-level, not byte-level: a file
    # containing only whitespace/newlines (e.g. `echo > journal.ndjson`)
    # produces the exact same (valid_events=[], torn_tail=None) from
    # read_journal as a genuinely absent or 0-byte file -- checking
    # os.path.getsize() > 0 alone would miss this (found by review round
    # 4's N9 follow-up). Exactly the same "coordinator crashed before
    # RUN_STARTED, or the journal was lost" attention-worthy state a
    # MISSING file is -- so it gets the identical treatment.
    journal_file_exists = bool(journal_events) or torn_tail is not None

    missing_journal_attention: List[Dict[str, Any]] = []
    if not journal_file_exists:
        journal_chain_valid = False
        missing_journal_attention.append({
            "packet_id": None,
            "code": "journal_missing",
            "detail": f"No non-empty journal.ndjson at {journal_path} despite a valid MANIFEST.json -- state root has no durability record to reconcile",
        })

    enrolled_ids: Set[str] = {
        e.get("packet_id") for e in journal_events
        if e.get("event_type") == "PACKET_ENROLLED" and e.get("packet_id")
    }

    # Fold against a phantom (non-existent) seal directory so a bad seal
    # can never abort the fold -- see this function's docstring and
    # _check_seal_consistency's docstring for the full reasoning.
    _inventory_fold_root = "/dev/null"
    seal_mismatches: List[str] = []
    fold_failure_attention: List[Dict[str, Any]] = []
    try:
        packets_by_id, counters = _fold_journal(_inventory_fold_root, journal_events)
        fold_ok = True
    except IntegrityError as exc:
        # A genuine (non-seal) fold failure is itself the most important
        # thing the report can say -- never silently produce a
        # degraded/empty report instead.
        packets_by_id, counters = getattr(exc, "partial_packets", {}), {}
        fold_ok = False
        fold_failure_attention.append({"packet_id": None, "code": "fold_failed", "detail": f"journal fold raised {exc.code}: {exc.message}"})

    if fold_ok:
        for finding in _check_seal_consistency(state_root, packets_by_id, handle=handle):
            pid = finding["packet_id"]
            if pid and pid not in seal_mismatches:
                seal_mismatches.append(pid)
            fold_failure_attention.append(finding)
    else:
        # seal_mismatches stays [] here, but that must not read as "seals
        # checked, clean" -- they were never read at all, since there's
        # no reliable packet inventory to check them against. fold_failed
        # is already loud and all_invariants_passed is already False, so
        # this is presentational, not a second failure signal.
        fold_failure_attention.append({"packet_id": None, "code": "seals_not_checked", "detail": "fold failed before seal consistency could be checked"})

    duplicate_packet_ids: List[str] = []
    omitted_packet_ids: List[str] = []
    unenrolled_dependencies: List[str] = []
    for pid, pkt in packets_by_id.items():
        for dep in pkt.get("dependency_ids") or []:
            if dep not in packets_by_id and dep not in unenrolled_dependencies:
                unenrolled_dependencies.append(dep)

    rows = []
    attention_required: List[Dict[str, Any]] = []
    for pid in sorted(packets_by_id.keys()):
        pkt = packets_by_id[pid]
        deps = pkt.get("dependency_ids") or []
        blocked_on = [d for d in deps if packets_by_id.get(d, {}).get("state") != "ACCEPTED"] if pkt.get("state") == "BLOCKED" else []
        attention_codes: List[str] = []
        if pkt.get("state") == "BLOCKED" and blocked_on:
            for d in blocked_on:
                if d not in packets_by_id:
                    attention_codes.append("dependency_not_enrolled")
                elif packets_by_id[d].get("state") in {"QUARANTINED", "HUMAN_REQUIRED"}:
                    attention_codes.append("dependency_terminal_not_accepted")
                    attention_required.append({"packet_id": pid, "code": "dependency_terminal_not_accepted", "detail": f"{pid} depends on {d}, which is terminal but not ACCEPTED ({packets_by_id[d].get('state')})"})
        elif pkt.get("state") == "BLOCKED" and deps and not blocked_on:
            # Every dependency is fold-ACCEPTED (blocked_on is empty) but
            # this packet is STILL BLOCKED -- promotion should have fired.
            # classify_runtime.promote_dependencies requires each
            # dependency's TERMINAL SEAL to exist before it will promote
            # (design 3.5 step 13, its own auditable satisfied_by
            # citation), and defers quietly, with zero events, if any seal is
            # missing. P5C now repairs seals before promotion, so a packet
            # still in this shape after maintenance needs explicit attention.
            # Must never be silently green: without this, blocked_on==[]
            # gives this packet zero attention codes and the report reads
            # fully healthy while real work is permanently stuck.
            attention_codes.append("promotion_stalled")
            attention_required.append({"packet_id": pid, "code": "promotion_stalled", "detail": f"{pid}'s dependencies are all ACCEPTED but it is still BLOCKED -- promotion remains deferred despite terminal-seal maintenance"})
        retry_limit = pkt.get("retry_limit")
        attempts_started = pkt.get("attempts_started", 0)
        if isinstance(retry_limit, int) and not isinstance(retry_limit, bool):
            if attempts_started > retry_limit + 1:
                attention_codes.append("retry_budget_exceeded")
            elif pkt.get("state") == "REVISE" and attempts_started == retry_limit + 1:
                # Design 2.3 / fixture G9: a packet resting in REVISE with no
                # budget left for another attempt is stuck until a human
                # decides -- this is the LEGITIMATE at-cap state (distinct
                # from retry_budget_exceeded above, a structural violation
                # that should never happen), and must not be invisible in
                # the human-facing channel just because nothing is "wrong."
                attention_codes.append("attempt_budget_exhausted")
                attention_required.append({"packet_id": pid, "code": "attempt_budget_exhausted", "detail": f"{pid} is resting in REVISE at its retry_limit ({retry_limit}) with no attempts left -- needs a human decision"})
        # accounting_identity_violation (I9) is deliberately NOT computed
        # here -- compute_reconciliation() below already computes it from
        # these exact row fields and owns integrity.accounting_violations/
        # attention_required for it; a second computation here previously
        # duplicated that entry. See the post-pass after compute_reconciliation
        # that back-fills this row's attention_codes from its answer.

        rows.append({
            "packet_id": pid,
            "state": pkt.get("state"),
            "lane": pkt.get("lane"),
            "enqueue_seq": pkt.get("enqueue_seq"),
            "attempts_started": pkt.get("attempts_started", 0),
            "infra_retries_used": pkt.get("infra_retries_used", 0),
            "revise_cycles_used": pkt.get("revise_cycles_used", 0),
            "revise_verdicts": pkt.get("revise_verdicts", 0),
            "reassignment_used": bool(pkt.get("reassignment_used")),
            "open_attempt": pkt.get("open_attempt"),
            "last_event_seq": pkt.get("last_event_seq"),
            "last_event_sha256": pkt.get("last_event_sha256"),
            "quarantine_reason": pkt.get("quarantine_reason"),
            "human_required_reasons": pkt.get("human_required_reasons") or [],
            "blocked_on": blocked_on,
            "attention_codes": attention_codes,
            "retry_limit": retry_limit,
        })

    for dep in sorted(unenrolled_dependencies):
        attention_required.append({"packet_id": None, "code": "dependency_not_enrolled", "detail": f"{dep} is referenced as a dependency but was never enrolled"})
    if not journal_chain_valid:
        attention_required.append({"packet_id": None, "code": "journal_chain_invalid", "detail": "journal failed to validate cleanly"})
    attention_required.extend(missing_journal_attention)
    attention_required.extend(fold_failure_attention)
    # The remaining state-cache disclosure (see module docstring) is surfaced
    # IN the report itself, not only in source. It is informational and does
    # not affect all_invariants_passed because no state-cache producer exists.
    attention_required.append({
        "packet_id": None,
        "code": "unverified_invariants",
        "detail": "state_cache_in_sync remains a placeholder; reassignment preserved evidence is independently checked when present",
    })

    preserved_mismatches: List[str] = []
    for pid, packet in sorted(packets_by_id.items()):
        if not packet.get("reassignment_used"):
            continue
        raw = handle.read(("reassignments", f"{validate_harness_id(pid)}.json"))
        if raw is None:
            preserved_mismatches.append(f"{pid}:reassignment:EVIDENCE_MISSING")
            continue
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            preserved_mismatches.append(f"{pid}:reassignment:INVALID_JSON")
            continue
        for mismatch in assert_preserved(handle, record):
            preserved_mismatches.append(
                f"{pid}:{mismatch['kind']}:{mismatch['code']}")

    workspace_attention = _workspace_evidence_attention(handle, journal_events, packets_by_id)
    attention_required.extend(workspace_attention)
    workspace_codes_by_packet: Dict[str, List[str]] = {}
    for item in workspace_attention:
        packet_id = item.get("packet_id")
        if packet_id is not None:
            workspace_codes_by_packet.setdefault(packet_id, []).append(item["code"])
    for row in rows:
        for code in workspace_codes_by_packet.get(row["packet_id"], []):
            if code not in row["attention_codes"]:
                row["attention_codes"].append(code)

    activity = {
        "attempts_started_total": counters.get("attempts_started_total", 0),
        "infra_retries_total": counters.get("infra_retries_total", 0),
        "revise_verdicts_total": counters.get("revise_verdicts_total", 0),
        "revise_cycles_total": counters.get("revise_cycles_total", 0),
        "reassignments_total": counters.get("reassignments_total", 0),
        "results_recorded_total": counters.get("results_recorded_total", 0),
        "verdicts_recorded_total": counters.get("verdicts_recorded_total", 0),
        "intents_abandoned_total": counters.get("intents_abandoned_total", 0),
        "locks_reclaimed_total": counters.get("locks_reclaimed_total", 0),
    }

    # O5 Task 5: fetch the authenticated bound plan (if any), extend every
    # row with plan identity/capability/route/budget/backoff/stop-reason/
    # disposition fields, and derive the plan-scope totals input
    # ``compute_reconciliation`` needs. A run with no O5 plan bound (every
    # pre-O5 journal) gets ``plan_scope["bound"] is False`` and this is a
    # complete no-op -- see ``_o5_plan_extension``'s own docstring.
    plan_scope, o5_violations = _o5_plan_extension(state_root, journal_events, run_id, packets_by_id, rows)

    # journal_chain_valid now means exactly "the journal chain itself" --
    # seal issues never reach the fold at all any more (they're checked
    # separately, non-fatally, via _check_seal_consistency above), so
    # fold_ok here only reflects a genuine transition/chain-level failure.
    fold_data = {
        "journal_head": {
            "seq": journal_events[-1]["seq"] if journal_events else 0,
            "event_sha256": journal_events[-1]["event_sha256"] if journal_events else ZERO_SHA256,
        },
        "packets": rows,
        "activity": activity,
        "integrity": {
            "journal_chain_valid": journal_chain_valid and fold_ok,
            "state_cache_in_sync": True,
            "duplicate_packet_ids": duplicate_packet_ids,
            "omitted_packet_ids": omitted_packet_ids,
            "unenrolled_dependencies": sorted(unenrolled_dependencies),
            "seal_mismatches": seal_mismatches,
            "accounting_violations": [],
            "preserved_evidence_mismatches": preserved_mismatches,
        },
        "attention_required": attention_required,
        "enrolled_packet_ids": enrolled_ids,
        "plan_scope": plan_scope,
        "o5_violations": o5_violations,
        # O4 workspace-isolation findings. Passed straight through into the
        # SAME all_invariants_passed computation compute_reconciliation uses
        # to derive both the nested and top-level mirror fields -- do NOT
        # reintroduce a post-hoc override on computed["reconciliation"] here;
        # that shape is exactly what let the top-level mirror go stale (see
        # compute_reconciliation's docstring, "workspace_attention").
        "workspace_attention": workspace_attention,
    }

    computed = compute_reconciliation(fold_data)
    # Back-fill accounting_identity_violation into each affected row's
    # attention_codes now that compute_reconciliation (the sole I9 owner)
    # has answered. Deliberately keyed on the attention_required items
    # tagged code=="accounting_identity_violation" -- NOT on
    # integrity["accounting_violations"], which compute_reconciliation
    # also populates from I10 (retry_budget_exceeded); keying on that
    # shared bucket previously stamped a false accounting_identity_violation
    # onto every retry-budget-exceeded row even when its identity holds
    # exactly. computed["packets"] is the same list of dicts as `rows`
    # above, mutated in place, not a fresh copy.
    identity_violation_pids = {a["packet_id"] for a in computed["attention_required"] if a.get("code") == "accounting_identity_violation"}
    for row in computed["packets"]:
        if row["packet_id"] in identity_violation_pids:
            if "accounting_identity_violation" not in row["attention_codes"]:
                row["attention_codes"].append("accounting_identity_violation")
            if row.get("state") in {"READY", "REVISE"}:
                # Final O3 integration gate, defect D5 / classify_runtime.py's
                # own "Known, disclosed gap (design 9.2 / O3-P4)" docstring:
                # I9 (infra_retries_used + revise_cycles_used + reassignment
                # == attempts_started - 1) genuinely reads FALSE for a packet
                # resting in READY right after an infra_retry, or in REVISE
                # right before revision_requeued fires -- the retry/cycle is
                # already counted but attempts_started hasn't incremented for
                # the not-yet-claimed re-entry. This does NOT un-flag the
                # accounting_identity_violation above (compute_reconciliation,
                # the sole I9 owner, is not second-guessed here) -- it adds
                # the context a human needs to judge a lone violation on a
                # READY/REVISE packet as likely benign rather than corruption,
                # without hiding the underlying signal.
                row["attention_codes"].append("possible_benign_retry_window")
                computed["attention_required"].append({
                    "packet_id": row["packet_id"],
                    "code": "possible_benign_retry_window",
                    "detail": f"{row['packet_id']}'s accounting_identity_violation may be the known I9 resting-window false positive (state={row.get('state')}) -- see classify_runtime.py's module docstring before treating this as corruption",
                })

    report = {
        "schema_version": 1,
        "report_id": report_id,
        "generated_at": now,
        "coordinator_id": coordinator_id,
        "run_id": run_id,
        "state_root_id": state_root_id,
        "journal_head": fold_data["journal_head"],
        "inventory_total": computed["inventory_total"],
        "by_state": computed["by_state"],
        "packets": computed["packets"],
        "activity": activity,
        "attention_required": computed["attention_required"],
        "integrity": computed["integrity"],
        "reconciliation": computed["reconciliation"],
        "plan_totals": computed["plan_totals"],
        "attempted_packet_ids": computed["attempted_packet_ids"],
        "all_invariants_passed": computed["all_invariants_passed"],
        "content_sha256": "",
        "report_sha256": "",
    }
    report["content_sha256"] = compute_sha256(canonical_bytes(
        report, omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
    ))
    report["report_sha256"] = compute_sha256(canonical_bytes(report, omit={"report_sha256"}))
    handle.verify_identity()
    return report


def emit_reconciliation_report(
    state_root: str,
    journal_path: str,
    lock_path: str,
    journal_events: List[Dict[str, Any]],
    report: Dict[str, Any],
    coordinator_id: str,
    run_id: str,
    state_root_id: str,
    now: str,
    handle=None,
) -> List[Dict[str, Any]]:
    """Write ``report`` to ``reports/<report_id>.json`` and journal
    RECONCILIATION_EMITTED. Not used by the read-only CLI -- for a future
    coordinator loop that wants the report durably recorded. Raises if
    ``report`` doesn't pass its own contract (never journal an invalid
    report as if it were valid), or if MANIFEST.json is missing/wrong
    for this ``state_root`` (same check ``build_reconciliation_report``
    uses -- writing a report into the wrong/uninitialized state root is
    exactly as bad as reading one from it)."""
    from harness_coordinator.v1.store import atomic_replace

    _read_manifest_read_only(state_root, state_root_id)

    result = validate_reconciliation_report(report)
    if not result["valid"]:
        raise IntegrityError("INVALID_VALUE", f"Refusing to emit an invalid reconciliation report: {result['errors'][0]['message']}")

    committed = next((
        event for event in journal_events
        if event.get("event_type") == "RECONCILIATION_EMITTED"
        and (((event.get("payload") or {}).get("report") or {}).get("report_id")
             == report["report_id"])
    ), None)
    if committed is not None:
        binding = ((committed.get("payload") or {}).get("report") or {})
        if handle is not None:
            existing = handle.read(("reports", f"{validate_harness_id(report['report_id'])}.json"))
        else:
            existing = None
            committed_path = safe_state_path(state_root, suffix=binding.get("report_path"))
            if os.path.exists(committed_path):
                with open(committed_path, "rb") as source:
                    existing = source.read()
        try:
            committed_report = json.loads(existing.decode("utf-8")) if existing is not None else None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError("INVALID_JSON", "committed reconciliation artifact is invalid") from exc
        if (committed_report is None
                or existing != canonical_bytes(committed_report)
                or not validate_reconciliation_report(committed_report)["valid"]
                or binding.get("report_sha256") != committed_report.get("report_sha256")
                or binding.get("content_sha256") != committed_report.get("content_sha256")
                or binding.get("report_path") != f"reports/{report['report_id']}.json"):
            raise IntegrityError("EVIDENCE_HASH_MISMATCH", "committed reconciliation artifact disagrees")
        return journal_events

    report_path = safe_state_path(
        state_root,
        "reports",
        identifier=report["report_id"],
        identifier_suffix=".json",
    )
    report_path_rel = f"reports/{report['report_id']}.json"
    if handle is None:
        os.makedirs(os.path.join(state_root, "reports"), exist_ok=True)
        atomic_replace(report_path, canonical_bytes(report), coordinator_id=coordinator_id, nonce=report["report_id"])
    else:
        handle.publish(("reports", f"{validate_harness_id(report['report_id'])}.json"),
                       canonical_bytes(report))

    event = _make_event(
        seq=(_last_seq(journal_events) + 1),
        event_type="RECONCILIATION_EMITTED",
        coordinator_id=coordinator_id,
        run_id=run_id,
        state_root_id=state_root_id,
        prev_event=journal_events[-1] if journal_events else None,
        event_at=now,
        payload={
            "packet": None,
            "attempt": None,
            "artifacts": [],
            "classification": None,
            "transition_detail": None,
            "recovery": None,
            "run": None,
            "report": {
                "report_id": report["report_id"],
                "report_sha256": report["report_sha256"],
                "content_sha256": report["content_sha256"],
                "report_path": report_path_rel,
                "inventory_total": report["inventory_total"],
                "all_invariants_passed": report["reconciliation"]["all_invariants_passed"],
            },
        },
    )
    if handle is not None:
        handle.verify_identity()
    append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
    if handle is not None:
        handle.verify_identity()
    journal_events.append(event)
    return journal_events
