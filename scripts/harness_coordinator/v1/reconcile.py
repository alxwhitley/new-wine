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
from typing import Any, Dict, List, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_contracts.v1.reconciliation import compute_reconciliation, validate_reconciliation_report
from harness_contracts.v1.seal import validate_terminal_seal

from harness_coordinator.v1.recovery import (
    IntegrityError, WORKSPACE_STAGE_SPECS, _direct_state_root_path, _fold_journal, _last_seq,
    _make_event, validate_workspace_stage_artifact,
)
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
    }

    computed = compute_reconciliation(fold_data)
    if workspace_attention:
        computed["reconciliation"]["all_invariants_passed"] = False
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
