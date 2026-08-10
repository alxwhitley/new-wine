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
  and journals a RECONCILIATION_EMITTED event -- for a future coordinator
  loop (not this packet's CLI) that wants the report durably recorded.

D0.4 (no implicit clock, no implicit randomness): every function here
takes ``now``/``report_id`` as explicit arguments; nothing in this module
calls ``datetime.now()`` or ``uuid.uuid4()`` itself.

**Known, disclosed gap -- ``integrity.state_cache_in_sync`` and
``integrity.preserved_evidence_mismatches`` are placeholders, not
independently verified.** Design 1.4's per-packet ``state/<pid>.json``
staleness cache and design 7.2's ``assert_preserved()`` re-hash check are
BOTH referenced by the design but were never built in ANY prior accepted
round (P1 through P3R) -- confirmed by grep: no code anywhere in this
repo writes a ``state/<packet_id>.json`` cache file, and
``assert_preserved`` exists only as a comment in ``classify_runtime.py``,
never as a real function. This is not a P4-introduced gap; P4 is simply
the first packet whose job is to REPORT on these two invariants, which
surfaced that their producers don't exist. Given that, this module keeps
the schema-required fields at their weakest legitimate values
(``state_cache_in_sync=True``, ``preserved_evidence_mismatches=[]``) --
NOT because either was checked and passed, but because there is nothing
to check them against yet. Read ``all_invariants_passed=True`` as "every
invariant this build can currently verify passed," not as design 9's
full I1-I12 guarantee. Every report also carries an ``unverified_invariants``
``attention_required`` item naming this plainly -- a disclosure that lives
only in this docstring is invisible to whoever actually reads a report at
7am, not just to whoever reads the source; it must be visible in the
artifact itself. Flagged explicitly for the final O3 integration gate:
either build the two missing producers, or make this limitation a
permanent, loudly-documented product decision -- silently trusting these
two fields is the one option this disclosure exists to rule out.
"""

import json
import os
from typing import Any, Dict, List, Optional, Set

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.journal import ZERO_SHA256
from harness_contracts.v1.reconciliation import compute_reconciliation, validate_reconciliation_report
from harness_contracts.v1.seal import validate_terminal_seal

from harness_coordinator.v1.recovery import IntegrityError, _fold_journal, _last_seq, _make_event
from harness_coordinator.v1.paths import safe_state_path
from harness_coordinator.v1.store import append_journal, read_journal


def _read_manifest_read_only(state_root: str, expected_state_root_id: str) -> Dict[str, Any]:
    """Read and validate MANIFEST.json WITHOUT the init-on-absent side
    effect ``recovery._read_or_init_manifest`` has (that function writes
    a fresh MANIFEST.json via ``atomic_replace`` when one is missing --
    unsafe to call from a read-only reporting/CLI path). A missing or
    mismatched MANIFEST.json is a real finding here (a typo'd
    ``--state-root``, or a state root that was never actually
    initialized by a real coordinator run), never silently treated as
    "nothing to reconcile yet"."""
    manifest_path = os.path.join(state_root, "MANIFEST.json")
    if not os.path.exists(manifest_path):
        raise IntegrityError("INVALID_VALUE", f"No MANIFEST.json at {manifest_path} -- state root was never initialized by a coordinator run")
    with open(manifest_path, "rb") as f:
        raw = f.read()
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


def _check_seal_consistency(state_root: str, packets_by_id: Dict[str, Any]) -> List[Dict[str, Any]]:
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
    seal_dir = os.path.join(state_root, "state", "terminal")
    if not os.path.isdir(seal_dir):
        return findings
    for name in sorted(os.listdir(seal_dir)):
        if not name.endswith(".seal.json"):
            continue
        pid = name[: -len(".seal.json")]
        try:
            seal_path = safe_state_path(
                state_root,
                "state",
                "terminal",
                identifier=pid,
                identifier_suffix=".seal.json",
            )
        except ValueError:
            findings.append({
                "packet_id": pid,
                "code": "TERMINAL_SEAL_MISMATCH",
                "detail": f"Seal path for {pid} escapes state root",
            })
            continue
        try:
            with open(seal_path, "rb") as f:
                seal = json.loads(f.read().decode("utf-8"))
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


def build_reconciliation_report(
    state_root: str,
    state_root_id: str,
    coordinator_id: str,
    run_id: str,
    report_id: str,
    now: str,
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
    _read_manifest_read_only(state_root, state_root_id)

    journal_path = os.path.join(state_root, "journal.ndjson")
    journal_events, torn_tail = read_journal(journal_path, state_root_id=state_root_id)
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
    _inventory_fold_root = os.path.join(state_root, ".o3-reconcile-inventory-fold-root")
    seal_mismatches: List[str] = []
    fold_failure_attention: List[Dict[str, Any]] = []
    try:
        packets_by_id, counters = _fold_journal(_inventory_fold_root, journal_events)
        fold_ok = True
    except IntegrityError as exc:
        # A genuine (non-seal) fold failure is itself the most important
        # thing the report can say -- never silently produce a
        # degraded/empty report instead.
        packets_by_id, counters = {}, {}
        fold_ok = False
        fold_failure_attention.append({"packet_id": None, "code": "fold_failed", "detail": f"journal fold raised {exc.code}: {exc.message}"})

    if fold_ok:
        for finding in _check_seal_consistency(state_root, packets_by_id):
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
            # citation), and defers quietly, with zero events, if any
            # seal is missing -- see that module's own "Known, disclosed
            # caller obligation" docstring. No producer of terminal seals
            # exists in this build (see the final O3 integration gate
            # report), so this is currently the PERMANENT state for every
            # dependent packet, not a transient one-pass-behind race.
            # Must never be silently green: without this, blocked_on==[]
            # gives this packet zero attention codes and the report reads
            # fully healthy while real work is permanently stuck.
            attention_codes.append("promotion_stalled")
            attention_required.append({"packet_id": pid, "code": "promotion_stalled", "detail": f"{pid}'s dependencies are all ACCEPTED but it is still BLOCKED -- promotion is deferred pending a terminal seal that nothing in this build currently writes"})
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
    # H3/H4's disclosed gap (see module docstring) surfaced IN the report
    # itself, not only in source -- nobody doing morning triage reads
    # reconcile.py. Always present, every report; purely informational
    # (does not affect all_invariants_passed -- these two fields are
    # placeholders in every report this build produces, not a failure of
    # THIS particular run).
    attention_required.append({
        "packet_id": None,
        "code": "unverified_invariants",
        "detail": "state_cache_in_sync and preserved_evidence_mismatches are placeholders, not independently verified -- their producers (a per-packet state cache, assert_preserved()) do not exist in this build",
    })

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
            "preserved_evidence_mismatches": [],
        },
        "attention_required": attention_required,
        "enrolled_packet_ids": enrolled_ids,
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
        "content_sha256": "",
        "report_sha256": "",
    }
    report["content_sha256"] = compute_sha256(canonical_bytes(
        report, omit={"report_id", "generated_at", "coordinator_id", "run_id", "report_sha256", "content_sha256"},
    ))
    report["report_sha256"] = compute_sha256(canonical_bytes(report, omit={"report_sha256"}))
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

    report_path = safe_state_path(
        state_root,
        "reports",
        identifier=report["report_id"],
        identifier_suffix=".json",
    )
    report_path_rel = os.path.relpath(report_path, os.path.realpath(state_root))
    os.makedirs(os.path.join(state_root, "reports"), exist_ok=True)
    atomic_replace(report_path, canonical_bytes(report), coordinator_id=coordinator_id, nonce=report["report_id"])

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
    append_journal(journal_path, event, lock_path, expected_head=journal_events[-1] if journal_events else None)
    journal_events.append(event)
    return journal_events
