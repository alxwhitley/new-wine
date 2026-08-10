"""Trusted verdict ingestion and REVIEW resume for the harness coordinator v1.

The security property this module exists to hold:

> A reviewer -- even a trusted one -- contributes an ``opus_verdict`` and
> nothing else. The coordinator supplies its own enrolled packet and its own
> durably recorded worker result, assembles the replay bundle itself, and
> only then asks ``validate_replay_bundle`` whether the verdict is authorized.

``validate_replay_bundle`` has no parameter carrying coordinator ground
truth: every cross-check it performs is internal to the bundle it is handed.
A self-consistent, correctly self-hashed bundle carrying a fabricated packet
and a fabricated worker result, deposited by a genuinely trusted reviewer
session, therefore passes every check in it. That is not a defect in the
validator -- it is a statement about who must assemble its input. Assembling
the bundle here, from the journal and from coordinator-owned artifacts, is
what turns those internal cross-checks into checks of an external verdict
against durable truth. It also closes verdict replay for free: a genuine
verdict for attempt N fails ``result_sha256`` against the assembled attempt
N+1 result.

Self-hashes are integrity, never authenticity. A rehashed verdict is still
perfectly self-consistent; it fails here because it disagrees with state the
depositor does not control.

REVIEW resume distinguishes exactly four durable situations:

* no verdict anywhere            -> ``awaiting_verdict`` (a legitimate rest)
* a verdict, not yet journaled   -> validate and commit it now
* a verdict already journaled    -> ``already_recorded``, byte-identical no-op
* two verdicts that disagree     -> ``VerdictConflict``, fail closed

A refused verdict (untrusted reviewer, self-review, substituted ground truth,
incomplete ACCEPT evidence) leaves the packet resting in REVIEW and preserves
the rejected verdict as evidence. It never advances state and never deletes
what it rejected.
"""

import errno
import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from harness_contracts.v1.canonical import canonical_bytes, compute_sha256
from harness_contracts.v1.claim import classify_claim, validate_claim
from harness_contracts.v1.queue_state import ZERO_SHA256, validate_queue
from harness_contracts.v1.replay import validate_replay_bundle
from harness_contracts.v1.verdict import validate_verdict
from harness_contracts.v1.worker_result import validate_worker_result
from harness_coordinator.v1.paths import safe_state_path, validate_harness_id
from harness_coordinator.v1.recovery import _build_derived_queue, _fold_journal, _make_event, _validate_trust_roots
from harness_coordinator.v1.seals_runtime import (
    ArtifactConflict,
    open_state_root,
    SealContradiction,
    authenticate_seal,
    build_terminal_seal,
    seal_binding,
    terminal_seal_parts,
)
from harness_coordinator.v1.store import JournalHeadMoved, append_journal, atomic_replace, read_journal

_CAUSE_BY_VERDICT = {
    "ACCEPT": "verdict_accept",
    "REVISE": "verdict_revise",
    "QUARANTINE": "verdict_quarantine",
    "HUMAN_REQUIRED": "verdict_human_required",
}

_MAX_JOURNAL_CAS_RETRIES = 8


class ReviewRefused(ValueError):
    """A deposited verdict is not authorized; the packet stays in REVIEW."""

    def __init__(self, codes, message: str) -> None:
        super().__init__(message)
        self.codes = tuple(dict.fromkeys(codes))


class VerdictConflict(ValueError):
    """Two durable verdicts disagree; the state root needs a human."""


# --------------------------------------------------------------------------
# Canonical artifact locations
# --------------------------------------------------------------------------

def _attempt_suffix(attempt: int, name: str) -> str:
    number = int(attempt)
    if number < 1:
        raise ValueError(f"attempt must be a positive integer, got {attempt!r}")
    return os.path.join(str(number), name)


def worker_result_artifact_path(state_root: str, packet_id: str, attempt: int) -> str:
    """Where the coordinator durably records a validated worker result."""
    return safe_state_path(state_root, "results", identifier=packet_id,
                           suffix=_attempt_suffix(attempt, "worker-result.json"))


def verdict_artifact_path(state_root: str, packet_id: str, attempt: int) -> str:
    """Where the coordinator records the verdict it accepted."""
    return safe_state_path(state_root, "results", identifier=packet_id,
                           suffix=_attempt_suffix(attempt, "opus-verdict.json"))


def bundle_artifact_path(state_root: str, packet_id: str, attempt: int) -> str:
    """Where the coordinator records the bundle it assembled and validated."""
    return safe_state_path(state_root, "results", identifier=packet_id,
                           suffix=_attempt_suffix(attempt, "replay-bundle.json"))


def verdict_inbox_path(state_root: str, packet_id: str, attempt: int) -> str:
    """The one location an external reviewer may write, holding a verdict only."""
    return safe_state_path(state_root, "review", "inbox", identifier=packet_id,
                           identifier_suffix=f".{int(attempt)}.verdict.json")


def review_claim_path(state_root: str, packet_id: str, attempt: int) -> str:
    """Attempt-scoped review ownership, deliberately outside ``locks/``.

    ``recovery._reconcile_locks`` scans ``<state_root>/locks/*.lock.json`` and
    treats every record it finds as a worker claim -- journaling
    LOCK_RECLAIMED/INTENT_ABANDONED and reclaiming the file. A review claim
    living there would be swept by that machinery and conflated with the
    worker claim for the same packet. Keeping review ownership under
    ``review/locks/`` makes the two structurally distinct, which is why
    ``reclaim_lock`` is also not reused here: it derives the state root as
    ``dirname(dirname(lock_path))`` and its destination is not attempt-scoped.
    ``validate_claim`` and ``classify_claim`` -- the actual decision logic --
    are reused unchanged.
    """
    return safe_state_path(state_root, "review", "locks", identifier=packet_id,
                           identifier_suffix=f".{int(attempt)}.lock.json")


def _relative(state_root: str, path: str) -> str:
    return os.path.relpath(path, os.path.realpath(state_root))


def _review_claim_parts(packet_id: str, attempt: int) -> Tuple[str, str, str]:
    return ("review", "locks", f"{validate_harness_id(packet_id)}.{int(attempt)}.lock.json")


def _verdict_parts(packet_id: str, attempt: int) -> Tuple[str, str, str, str]:
    return ("results", validate_harness_id(packet_id), str(int(attempt)), "opus-verdict.json")


def _bundle_parts(packet_id: str, attempt: int) -> Tuple[str, str, str, str]:
    return ("results", validate_harness_id(packet_id), str(int(attempt)), "replay-bundle.json")


def _refusal_parts(packet_id: str, evidence_sha: str) -> Tuple[str, str, str]:
    return ("rejected", "review", f"{validate_harness_id(packet_id)}.{evidence_sha}.json")


def _worker_result_parts(packet_id: str, attempt: int) -> Tuple[str, str, str, str]:
    return ("results", validate_harness_id(packet_id), str(int(attempt)), "worker-result.json")


def _inbox_parts(packet_id: str, attempt: int) -> Tuple[str, str, str]:
    return ("review", "inbox", f"{validate_harness_id(packet_id)}.{int(attempt)}.verdict.json")


def _archive_parts(run_id: str, basename: str) -> Tuple[str, str, str]:
    return ("review", "reclaimed", validate_harness_id(run_id), basename)


_TRUST_PARTS = ("trust", "reviewer_sessions.json")
_QUEUE_PARTS = ("queue.json",)


def _read_json_via(handle, parts):
    """Read and parse a pinned artifact, or None when absent."""
    raw = handle.read(parts)
    if raw is None:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerdictConflict(f"artifact {'/'.join(parts)} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise VerdictConflict(f"artifact {'/'.join(parts)} is not an object")
    return value


# --------------------------------------------------------------------------
# Deterministic review-claim ownership
# --------------------------------------------------------------------------

def review_intent_id(packet_id: str, attempt: int, generation: int) -> str:
    """One intent id per review *generation* of one attempt.

    Deliberately identical to the id the VERDICT_RECORDED event will carry, so
    "is this intent committed in the journal?" answers "did this review
    complete?" -- the same relationship P5A's worker claim has with
    ATTEMPT_STARTED, and the discriminator ``_reconcile_locks`` already uses.

    The generation exists because generic recovery owns the other half of that
    relationship. ``recovery._resolve_pending_intents`` journals
    INTENT_ABANDONED for any pending intent with no committing event -- which
    is exactly what a crashed review leaves behind. Reusing that id afterwards
    would commit an intent the journal already records as abandoned. Advancing
    the generation keeps both statements true and needs no change to recovery.
    """
    return f"verdict-{packet_id}-{int(attempt)}-g{int(generation)}"


def _is_review_intent(intent_id: Any, packet_id: str, attempt: int) -> bool:
    prefix = f"verdict-{packet_id}-{int(attempt)}-g"
    return (isinstance(intent_id, str) and intent_id.startswith(prefix)
            and intent_id[len(prefix):].isdigit())


def current_review_generation(journal_events: List[Dict[str, Any]], packet_id: str, attempt: int) -> int:
    """Derive the current review generation from durable journal history alone.

    Both event types that can name a review generation are parsed --
    INTENT_ABANDONED (generic recovery gave up on it) and VERDICT_RECORDED (it
    committed) -- because a history is only meaningful when read as a whole.

    Fails closed rather than guessing on: a malformed generation suffix, a gap
    in the abandoned prefix, a generation recorded as both committed and
    abandoned, more than one committed generation, or an abandonment numbered
    above a committed one. Counting distinct ids alone was not enough: a
    history of g0+g2 counts 2 and would reuse g2, and a lone g5 counts 1 and
    would reuse g1.

    Repeated abandonment of one generation is idempotent -- ``_resolve_pending_intents``
    does not clear queue.json, so a second restart legitimately re-abandons the
    same intent, and that must advance nothing.

    A committed verdict settles the attempt: its generation is returned as-is,
    never a fresh one.
    """
    prefix = f"verdict-{packet_id}-{int(attempt)}-g"
    abandoned: Set[int] = set()
    committed: Set[int] = set()
    for event in journal_events:
        intent_id = event.get("intent_id")
        if not isinstance(intent_id, str) or not intent_id.startswith(prefix):
            continue
        suffix = intent_id[len(prefix):]
        if not suffix.isdigit():
            raise VerdictConflict(f"malformed review generation in intent {intent_id!r}")
        generation = int(suffix)
        if event.get("event_type") == "INTENT_ABANDONED":
            abandoned.add(generation)
        elif event.get("event_type") == "VERDICT_RECORDED":
            committed.add(generation)

    if len(committed) > 1:
        raise VerdictConflict(
            f"{packet_id} attempt {attempt} records more than one committed review generation")
    if abandoned & committed:
        raise VerdictConflict(
            f"{packet_id} attempt {attempt} records a review generation as both committed and abandoned")
    if sorted(abandoned) != list(range(len(abandoned))):
        raise VerdictConflict(
            f"{packet_id} attempt {attempt} abandoned review generations are not a contiguous prefix")
    if committed:
        settled = next(iter(committed))
        if any(generation > settled for generation in abandoned):
            raise VerdictConflict(
                f"{packet_id} attempt {attempt} records an abandonment after a committed review generation")
        if settled != len(abandoned):
            raise VerdictConflict(
                f"{packet_id} attempt {attempt} committed review generation does not follow its abandoned prefix")
        return settled
    return len(abandoned)


def _build_review_claim(packet_id: str, attempt: int, generation: int, coordinator_id: str, run_id: str,
                        trusted_process_context: Dict[str, Any], now: str) -> Dict[str, Any]:
    record = {
        "schema_version": 1, "packet_id": packet_id,
        "intent_id": review_intent_id(packet_id, attempt, generation), "stage": "review_claim",
        "attempt": int(attempt), "coordinator_id": coordinator_id, "run_id": run_id,
        "hostname": trusted_process_context["hostname"],
        "boot_id": trusted_process_context["boot_id"], "pid": trusted_process_context["pid"],
        "acquired_at": now, "heartbeat_at": now, "lease_seconds": 60,
        # The judgment lane, not the packet's implementation lane: the claim
        # records who is reviewing, and it is never the worker.
        "lane": "opus_judgment", "worktree_path": None, "claim_sha256": "",
    }
    record["claim_sha256"] = compute_sha256(canonical_bytes(record, omit={"claim_sha256"}))
    result = validate_claim(record)
    if not result["valid"]:
        raise VerdictConflict(f"derived review claim is contract-invalid: {result['errors'][0]['message']}")
    return record


def _archive_review_claim(handle, packet_id: str, attempt: int, run_id: str,
                          record: Dict[str, Any]) -> None:
    """Move a stale or superseded review claim aside verbatim; never delete.

    Both source and destination are reached through the pinned root, so a
    swapped parent can never turn this into a move of an outside file. The
    destination is keyed by the archived record's own ``claim_sha256`` so
    successive generations archived within one run cannot collide.
    """
    source = _review_claim_parts(packet_id, attempt)
    basename = f"{source[-1]}.{record.get('claim_sha256', 'unknown')}"
    destination = _archive_parts(run_id, basename)
    try:
        handle.rename(source, destination)
    except FileExistsError:
        return


def acquire_review_claim(state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                         packet_id: str, attempt: int, coordinator_id: str, run_id: str,
                         trusted_process_context: Dict[str, Any], now: str,
                         handle=None) -> Optional[Dict[str, Any]]:
    """Take exclusive, attempt-scoped ownership of one packet's review.

    Returns the claim record on success, or ``None`` when another coordinator
    legitimately owns it. Journal compare-and-swap alone cannot provide this:
    it prevents a duplicate *commit* once a verdict exists, but two
    coordinators would still both read the inbox and -- once a real adapter
    exists -- both invoke the reviewer. Ownership has to be taken before that
    action, not after it.
    """
    if handle is None:
        with open_state_root(state_root) as scoped:
            return acquire_review_claim(state_root, state_root_id, journal_events, packet_id,
                                        attempt, coordinator_id, run_id, trusted_process_context,
                                        now, handle=scoped)
    validate_harness_id(packet_id, "/packet_id")
    generation = current_review_generation(journal_events, packet_id, attempt)
    record = _build_review_claim(packet_id, attempt, generation, coordinator_id, run_id,
                                 trusted_process_context, now)
    parts = _review_claim_parts(packet_id, attempt)
    data = canonical_bytes(record)
    for _ in range(3):
        try:
            handle.publish(parts, data)
            return record  # created, or an identical claim already published: ours either way
        except ArtifactConflict:
            pass
        existing = _read_json_via(handle, parts)
        if existing is None:
            continue
        if not validate_claim(existing)["valid"]:
            raise VerdictConflict(f"existing review claim for {packet_id} is contract-invalid")
        classification = classify_claim(existing, trusted_process_context)["status"]
        if classification in {"FOREIGN_LIVE", "FOREIGN_HOST"}:
            return None
        if classification == "SELF_OWNED" and existing.get("intent_id") == record["intent_id"]:
            return existing
        # Either a dead owner, or our own claim from a generation that generic
        # recovery has since abandoned. Both are superseded; archive and retry.
        _archive_review_claim(handle, packet_id, attempt, run_id, existing)
    raise VerdictConflict(f"review claim for {packet_id} kept being recreated during acquisition")


def release_review_claim(handle, claim: Dict[str, Any]) -> None:
    """Drop ownership we took, matching on the exact record we wrote.

    A claim that changed hands in between is left alone. An idle REVIEW packet
    holding ownership forever would block every other coordinator.
    """
    _release_claim_if(handle, claim["packet_id"], claim["attempt"],
                      lambda existing: existing.get("claim_sha256") == claim.get("claim_sha256"))


def _release_claim_if(handle, packet_id: str, attempt: int, predicate) -> None:
    """Unlink only through the pinned root, and only what the predicate accepts."""
    def guard(raw: bytes) -> bool:
        try:
            existing = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return isinstance(existing, dict) and predicate(existing)

    try:
        handle.unlink(_review_claim_parts(packet_id, attempt), predicate=guard)
    except FileNotFoundError:
        # Neither the claim nor its directory exists: nothing of ours to drop.
        return


def load_pending_intents(handle, state_root_id: str) -> List[Dict[str, Any]]:
    """Read the pending-intent projection, validated by the accepted contract.

    ``validate_queue`` is the authority and is reused whole -- no field list is
    reimplemented here, so invalid types, unknown fields, bad stages or
    timestamps, and duplicate intent/packet ids are all caught by the same
    logic the rest of the harness uses.

    It is applied to a canonical probe carrying ``entries: []`` rather than to
    the file itself, for one specific reason: the accepted
    ``_build_derived_queue`` orders entries by packet_id while ``validate_queue``
    requires ascending enqueue_seq, so a projection the accepted writer itself
    produces can fail its own contract whenever those orders differ. Validating
    the whole file would therefore fail closed on legitimate output. The probe
    isolates exactly the part this module reads and merges. That ordering
    defect lives in recovery.py and is disclosed, not silently accommodated.

    Precondition: P5C's queue read/modify/write runs under the top-level
    coordinator singleton flock held by ``run_started_recovery``. This is not a
    CAS protocol and does not claim to be one.
    """
    queue = _read_json_via(handle, _QUEUE_PARTS)
    if queue is None:
        return []
    pending = queue.get("pending_intents")
    if not isinstance(pending, list):
        raise VerdictConflict("queue projection has no pending_intents array")

    probe = {
        "schema_version": 1,
        "state_root_id": state_root_id,
        "derived_from": {"journal_last_seq": 0, "journal_last_event_sha256": ZERO_SHA256},
        "entries": [],
        "pending_intents": pending,
        "queue_sha256": "",
    }
    probe["queue_sha256"] = compute_sha256(canonical_bytes(probe, omit={"queue_sha256"}))
    result = validate_queue(probe, state_root_id=state_root_id)
    if not result["valid"]:
        first = result["errors"][0]
        raise VerdictConflict(
            f"queue pending_intents fail the accepted contract: {first['code']} at {first['path']}: {first['message']}")
    return pending


def _write_queue_projection(handle, state_root_id: str, journal_events: List[Dict[str, Any]],
                            coordinator_id: str, nonce: str,
                            pending_intents: List[Dict[str, Any]],
                            folded: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Project the queue cache. ``folded`` is reused when the caller already has it.

    Re-deriving it here would not merely be wasted work: the fold validates
    every terminal seal in the state root, so a projection write would start
    failing on a seal problem that belongs to a different packet entirely, and
    would pre-empt the more specific check the caller is on its way to make.
    """
    if folded is None:
        folded, _ = _fold_journal(handle.path, journal_events)
    queue = _build_derived_queue(folded, state_root_id, journal_events[-1] if journal_events else None)
    queue["pending_intents"] = pending_intents
    queue["queue_sha256"] = compute_sha256(canonical_bytes(queue, omit={"queue_sha256"}))
    # ``atomic_replace`` is the accepted atomic writer and takes a pathname;
    # it is deliberately not duplicated here. Root identity is verified
    # immediately before and after, so a root swapped around the write is
    # detected and halts the iteration rather than silently redirecting it.
    handle.verify_identity()
    atomic_replace(os.path.join(handle.path, "queue.json"), canonical_bytes(queue), coordinator_id, nonce)
    handle.verify_identity()


def write_review_pending_intent(handle, state_root_id: str,
                                journal_events: List[Dict[str, Any]], claim: Dict[str, Any],
                                now: str, folded: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Project the in-flight review into queue.json, per design 3.4's write order.

    This is what makes a crash between claim and verdict recoverable by the
    accepted machinery: ``recovery._resolve_pending_intents`` sees an intent
    with no committing journal event and journals INTENT_ABANDONED for it.
    That is correct and harmless here -- the abandonment names the intent, not
    a state transition, and a later pass re-claims and commits the same intent
    id once a verdict is available.
    """
    owned = {"intent_id": claim["intent_id"], "packet_id": claim["packet_id"],
             "stage": "review_claim", "created_at": now,
             "coordinator_id": claim["coordinator_id"], "run_id": claim["run_id"],
             "boot_id": claim["boot_id"], "pid": claim["pid"]}
    # Merge, never replace: unrelated pending intents belong to other packets'
    # in-flight work and must survive byte-for-byte. Any entry for OUR packet is
    # a superseded generation of this same review and is the one thing replaced
    # -- the queue contract permits at most one pending intent per packet.
    others = [i for i in load_pending_intents(handle, state_root_id)
              if i["packet_id"] != claim["packet_id"]]
    _write_queue_projection(handle, state_root_id, journal_events, claim["coordinator_id"],
                            f"review-pending-{claim['packet_id']}-{claim['attempt']}-{claim['intent_id']}",
                            others + [owned], folded=folded)


def _clear_review_pending_intent(handle, state_root_id: str,
                                 journal_events: List[Dict[str, Any]], coordinator_id: str,
                                 packet_id: str, attempt: int, intent_id: str,
                                 folded: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Remove only our own intent id, preserving every unrelated pending intent."""
    remaining = [i for i in load_pending_intents(handle, state_root_id)
                 if i["intent_id"] != intent_id]
    _write_queue_projection(handle, state_root_id, journal_events, coordinator_id,
                            f"review-cleared-{packet_id}-{attempt}-{intent_id}",
                            remaining, folded=folded)


def _release_ownership(handle, state_root_id: str, journal_events: List[Dict[str, Any]],
                       claim: Dict[str, Any], folded: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Clear only this coordinator's own pending intent, then its own claim.

    Used on every handled refusal and after a successful commit. Deliberately
    NOT used from a broad ``finally``: an unexpected interruption must leave the
    claim and pending intent behind as recovery evidence.
    """
    _clear_review_pending_intent(handle, state_root_id, journal_events, claim["coordinator_id"],
                                 claim["packet_id"], claim["attempt"], claim["intent_id"], folded=folded)
    release_review_claim(handle, claim)


# --------------------------------------------------------------------------
# Operator-owned reviewer trust
# --------------------------------------------------------------------------

def load_trusted_reviewer_sessions(handle) -> Set[str]:
    """Read the operator-owned reviewer registry, failing closed.

    ``_validate_trust_roots`` is the accepted authority on whether the
    registry is well-formed and self-consistent, so it -- not a second
    validator here -- decides that. The digest it returns is then compared
    against the bytes actually parsed, so a registry swapped between the
    validation and the read cannot take effect. The coordinator has no write
    path to this file and never creates one: automatic self-registration
    would make reviewer trust self-signing.
    """
    digests = _validate_trust_roots(handle.path)
    raw = handle.read(_TRUST_PARTS)
    if raw is None or compute_sha256(raw) != digests["reviewer_sessions_sha256"]:
        raise VerdictConflict("reviewer trust registry changed while it was being read")
    registry = json.loads(raw.decode("utf-8"))
    return {session for session in registry.get("sessions", []) if isinstance(session, str)}


# --------------------------------------------------------------------------
# Durable ground truth
# --------------------------------------------------------------------------

def _current_attempt(journal_events: List[Dict[str, Any]], packet_id: str) -> Tuple[int, Dict[str, Any]]:
    """Resolve the attempt this packet is actually in REVIEW for.

    The fold clears ``open_attempt`` at ATTEMPT_FINISHED, so a resting REVIEW
    packet carries no attempt number; the journal does. Every artifact path is
    attempt-scoped as a result, which is also what stops a genuine verdict for
    attempt N being replayed onto attempt N+1.
    """
    started = None
    for event in journal_events:
        if event.get("event_type") == "ATTEMPT_STARTED" and event.get("packet_id") == packet_id:
            started = event
    if started is None:
        raise ReviewRefused(["EVIDENCE_MISSING"], f"packet {packet_id} is in REVIEW with no ATTEMPT_STARTED")
    attempt_payload = (started.get("payload") or {}).get("attempt") or {}
    return attempt_payload["attempt"], attempt_payload


def _artifact_entry(event: Dict[str, Any], kind: str, packet_id: str) -> Dict[str, Any]:
    artifacts = (event.get("payload") or {}).get("artifacts") or []
    entries = [a for a in artifacts if isinstance(a, dict) and a.get("kind") == kind]
    if len(entries) != 1:
        raise ReviewRefused(
            ["EVIDENCE_MISSING"],
            f"packet {packet_id}'s journal does not reference exactly one {kind} artifact",
        )
    return entries[0]


def _durable_worker_result(handle, journal_events: List[Dict[str, Any]],
                           packet_id: str, attempt: int, attempt_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Load the worker result the coordinator itself recorded for this attempt."""
    recorded = None
    for event in journal_events:
        if (event.get("event_type") == "WORKER_RESULT_RECORDED"
                and event.get("packet_id") == packet_id
                and ((event.get("payload") or {}).get("attempt") or {}).get("attempt") == attempt):
            recorded = event
    if recorded is None:
        raise ReviewRefused(
            ["EVIDENCE_MISSING"],
            f"packet {packet_id} attempt {attempt} has no WORKER_RESULT_RECORDED to review",
        )
    entry = _artifact_entry(recorded, "worker_result", packet_id)
    parts = _worker_result_parts(packet_id, attempt)
    if entry.get("path") != "/".join(parts):
        raise ReviewRefused(
            ["EVIDENCE_HASH_MISMATCH"],
            f"worker result for {packet_id} is recorded outside its canonical location",
        )
    try:
        raw = handle.read(parts)
    except OSError as exc:
        raise ReviewRefused(["EVIDENCE_MISSING"], f"worker result for {packet_id} is unreadable: {exc}") from exc
    if raw is None:
        raise ReviewRefused(["EVIDENCE_MISSING"], f"worker result for {packet_id} is missing")
    if compute_sha256(raw) != entry.get("sha256") or len(raw) != entry.get("byte_length"):
        raise ReviewRefused(
            ["EVIDENCE_HASH_MISMATCH"],
            f"worker result for {packet_id} does not match its journaled digest",
        )
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewRefused(["INVALID_JSON"], f"worker result for {packet_id} is not valid JSON: {exc}") from exc
    validation = validate_worker_result(result)
    if not validation["valid"]:
        raise ReviewRefused([e["code"] for e in validation["errors"]],
                            f"durable worker result for {packet_id} fails its contract")
    expected_session = (attempt_payload.get("worker") or {}).get("session_id")
    if (result.get("packet_id") != packet_id or result.get("attempt") != attempt
            or (result.get("worker") or {}).get("session_id") != expected_session):
        raise ReviewRefused(
            ["PROVENANCE_MISMATCH"],
            f"durable worker result for {packet_id} does not match the journaled attempt identity",
        )
    return result


def _load_seal(handle, dependency_id: str, journal_events: List[Dict[str, Any]],
               folded: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Authenticate a dependency's seal against the CURRENT journal and fold.

    Reading the seal at bundle-assembly time is not enough. Coordinator
    maintenance may have validated this seal moments earlier, and the file can
    be swapped in between -- so the seal is re-authenticated here and, more
    importantly, its binding is rebuilt from durable state via the accepted
    ``build_terminal_seal`` and compared. A forged seal therefore cannot
    contribute dependency provenance even if it is internally perfect, because
    it must also agree with the journal event that actually made the
    dependency terminal.
    """
    parts = terminal_seal_parts(dependency_id)
    try:
        raw = handle.read(parts)
    except OSError as exc:
        raise ReviewRefused(
            ["EVIDENCE_MISSING"],
            f"dependency {dependency_id} has no readable terminal seal to cite: {exc}",
        ) from exc
    if raw is None:
        raise ReviewRefused(["EVIDENCE_MISSING"],
                            f"dependency {dependency_id} has no terminal seal to cite")
    try:
        seal = authenticate_seal(raw, dependency_id, "/".join(parts))
    except SealContradiction as exc:
        raise ReviewRefused(["EVIDENCE_HASH_MISMATCH"], str(exc)) from exc

    dependency_state = folded.get(dependency_id)
    if dependency_state is None or dependency_state.get("state") != "ACCEPTED":
        raise ReviewRefused(
            ["DEPENDENCY_NOT_ACCEPTED"],
            f"dependency {dependency_id} is not ACCEPTED in the current fold",
        )
    if seal.get("terminal_state") != "ACCEPTED" or not isinstance(seal.get("upstream_digests"), dict):
        raise ReviewRefused(
            ["DEPENDENCY_NOT_ACCEPTED"],
            f"dependency {dependency_id}'s seal does not attest an ACCEPTED outcome",
        )
    try:
        expected = build_terminal_seal(handle, journal_events, dependency_id, dependency_state, seal["sealed_at"])
    except SealContradiction as exc:
        raise ReviewRefused(["EVIDENCE_HASH_MISMATCH"],
                            f"dependency {dependency_id}'s seal cannot be rebuilt from durable state: {exc}") from exc
    if seal_binding(seal) != seal_binding(expected):
        raise ReviewRefused(
            ["PROVENANCE_MISMATCH"],
            f"dependency {dependency_id}'s seal disagrees with the journal event that made it terminal",
        )
    return seal


def _dependency_context(handle, packet: Dict[str, Any], journal_events: List[Dict[str, Any]],
                        folded: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """Derive dependency provenance from the dependencies' own terminal seals.

    The seal is the provenance root: it is the only artifact that binds a
    dependency's packet/result/verdict/bundle digests to the journal event
    that made it terminal. Nothing here trusts the reviewer's account of an
    upstream packet.
    """
    dependency_states: List[Dict[str, Any]] = []
    provenance: Dict[str, Dict[str, str]] = {}
    for dependency_id in packet.get("dependency_ids") or []:
        seal = _load_seal(handle, dependency_id, journal_events, folded)
        digests = seal["upstream_digests"]
        provenance[dependency_id] = {
            "packet_sha256": digests["packet_sha256"],
            "result_sha256": digests["result_sha256"],
            "verdict_sha256": digests["verdict_sha256"],
            "bundle_sha256": digests["bundle_sha256"],
        }
        dependency_states.append({
            "packet_id": dependency_id,
            "state": "ACCEPTED",
            "evidence_id": f"ev-dep-{dependency_id}",
            "upstream_packet_sha256": digests["packet_sha256"],
            "upstream_result_sha256": digests["result_sha256"],
            "upstream_verdict_sha256": digests["verdict_sha256"],
            "upstream_bundle_sha256": digests["bundle_sha256"],
        })
    return dependency_states, provenance


def assemble_replay_bundle(handle, packet: Dict[str, Any], worker_result: Dict[str, Any],
                           verdict: Dict[str, Any], now: str, journal_events: List[Dict[str, Any]],
                           folded: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    """Build the bundle from coordinator-owned truth plus the external verdict.

    ``journal_events``/``folded`` are the authoritative current context and are
    required, not optional: dependency provenance is authenticated against them
    at assembly time rather than trusted from whatever is on disk.
    """
    dependency_states, provenance = _dependency_context(handle, packet, journal_events, folded)
    bundle = {
        "schema_version": 1,
        "packet": packet,
        "prior_state_event": {"from_state": "REVIEW", "to_state": verdict["next_state"], "event_at": now},
        "dependency_states": dependency_states,
        "worker_result": worker_result,
        "opus_verdict": verdict,
        "validator_version": "1",
    }
    bundle["bundle_sha256"] = compute_sha256(canonical_bytes(bundle, omit={"bundle_sha256"}))
    return bundle, provenance


# --------------------------------------------------------------------------
# Artifact persistence
# --------------------------------------------------------------------------

def _persist_artifact(handle, parts, value: Dict[str, Any]) -> bytes:
    """Publish canonical bytes atomically; identical content is a no-op."""
    data = canonical_bytes(value)
    try:
        handle.publish(parts, data)
    except ArtifactConflict as exc:
        raise VerdictConflict(str(exc)) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise VerdictConflict(f"artifact slot {parts!r} is a symlink") from exc
        raise
    return data


def _preserve_refusal(handle, packet_id: str, verdict: Any, codes) -> None:
    """Keep a refused verdict as evidence, outside the state-changing journal."""
    evidence = {"packet_id": packet_id, "codes": list(codes), "refused_verdict": verdict}
    data = canonical_bytes(evidence)
    evidence_sha = compute_sha256(data)
    try:
        handle.publish(_refusal_parts(packet_id, evidence_sha), data)
    except ArtifactConflict:
        return


# --------------------------------------------------------------------------
# Review resolution
# --------------------------------------------------------------------------

def _journaled_verdict_event(journal_events: List[Dict[str, Any]], packet_id: str,
                             attempt: int) -> Optional[Dict[str, Any]]:
    """Any generation's committed verdict settles this attempt."""
    for event in journal_events:
        if (event.get("event_type") == "VERDICT_RECORDED"
                and event.get("packet_id") == packet_id
                and _is_review_intent(event.get("intent_id"), packet_id, attempt)):
            return event
    return None


def _verify_committed_artifacts(handle, event: Dict[str, Any], packet_id: str,
                                attempt: int, persisted: Optional[Dict[str, Any]]) -> None:
    """A committed verdict must still have its evidence, intact.

    Returning ``already_recorded`` on the strength of an intent id alone would
    report a decision as durably settled while the artifacts that justify it
    are missing, truncated, swapped, or digest-mismatched -- and those
    artifacts are exactly what a terminal seal will later bind. Every
    committed-verdict resume therefore re-verifies them and fails closed.
    """
    handle.verify_identity()
    expected = {
        "opus_verdict": _verdict_parts(packet_id, attempt),
        "replay_bundle": _bundle_parts(packet_id, attempt),
    }
    for kind, parts in expected.items():
        entries = [a for a in (event.get("payload") or {}).get("artifacts") or []
                   if isinstance(a, dict) and a.get("kind") == kind]
        if len(entries) != 1:
            raise VerdictConflict(
                f"committed verdict for {packet_id} attempt {attempt} does not reference exactly one {kind}")
        entry = entries[0]
        if entry.get("path") != "/".join(parts):
            raise VerdictConflict(
                f"committed {kind} for {packet_id} is recorded outside its canonical location")
        try:
            raw = handle.read(parts)
        except OSError as exc:
            raise VerdictConflict(
                f"committed {kind} for {packet_id} is missing or unreadable: {exc}") from exc
        if raw is None:
            raise VerdictConflict(f"committed {kind} for {packet_id} is missing")
        if compute_sha256(raw) != entry.get("sha256") or len(raw) != entry.get("byte_length"):
            raise VerdictConflict(
                f"committed {kind} for {packet_id} no longer matches its journaled digest")
    if persisted is None:
        raise VerdictConflict(f"committed verdict for {packet_id} has no readable verdict artifact")


def resolve_review(state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                   folded: Dict[str, Dict[str, Any]], packet_id: str, coordinator_id: str,
                   run_id: str, trusted_process_context: Dict[str, Any], now: str,
                   handle=None) -> Dict[str, Any]:
    """Resolve one packet resting in REVIEW from durable state alone.

    ``handle`` pins the state root for the whole resolution. A caller inside a
    coordinator iteration passes the iteration's handle so every P5C artifact
    operation shares one identity; a direct caller gets a scoped one. Identity
    is verified on entry, so a root renamed or replaced since it was pinned
    halts here rather than being written through.
    """
    if handle is None:
        with open_state_root(state_root) as scoped:
            return resolve_review(state_root, state_root_id, journal_events, folded, packet_id,
                                  coordinator_id, run_id, trusted_process_context, now,
                                  handle=scoped)
    handle.verify_identity()
    validate_harness_id(packet_id, "/packet_id")
    packet_state = folded.get(packet_id)
    if packet_state is None:
        raise ValueError(f"packet {packet_id} is not enrolled")

    attempt, attempt_payload = _current_attempt(journal_events, packet_id)
    # Conflict detection and idempotency are both evaluated BEFORE the REVIEW
    # guard, and in that order. Once a verdict is committed the packet has
    # already left REVIEW, so a resume that guarded on REVIEW first would
    # raise on exactly the replay it is supposed to absorb -- and would miss a
    # contradicting verdict deposited after the decision was recorded, which
    # is the case that most needs to fail closed.
    persisted = _read_json_via(handle, _verdict_parts(packet_id, attempt))
    deposited = _read_json_via(handle, _inbox_parts(packet_id, attempt))
    if persisted is not None and deposited is not None and canonical_bytes(persisted) != canonical_bytes(deposited):
        raise VerdictConflict(
            f"packet {packet_id} attempt {attempt} has a committed verdict and a different deposited verdict"
        )

    committed = _journaled_verdict_event(journal_events, packet_id, attempt)
    if committed is not None:
        _verify_committed_artifacts(handle, committed, packet_id, attempt, persisted)
        # A crash between commit and cleanup leaves the committed generation's
        # claim and pending intent behind. They are safe to clear only now that
        # the committed artifacts have been verified, and only for the exact
        # intent the journal says committed.
        _clear_review_pending_intent(handle, state_root_id, journal_events, coordinator_id,
                                     packet_id, attempt, committed["intent_id"], folded=folded)
        _release_claim_if(handle, packet_id, attempt,
                          lambda existing: existing.get("intent_id") == committed["intent_id"])
        return {"packet_id": packet_id, "attempt": attempt, "status": "already_recorded",
                "verdict": (persisted or {}).get("verdict")}

    if packet_state.get("state") != "REVIEW":
        raise ValueError(f"packet {packet_id} is not resting in REVIEW")

    # Ownership is taken before any reviewer-owned action, and dropped again if
    # there turns out to be nothing to do.
    claim = acquire_review_claim(state_root, state_root_id, journal_events, packet_id, attempt,
                                 coordinator_id, run_id, trusted_process_context, now, handle=handle)
    if claim is None:
        return {"packet_id": packet_id, "attempt": attempt, "status": "review_claimed_elsewhere",
                "verdict": None}

    verdict = persisted if persisted is not None else deposited
    if verdict is None:
        release_review_claim(handle, claim)
        return {"packet_id": packet_id, "attempt": attempt, "status": "awaiting_verdict", "verdict": None}

    write_review_pending_intent(handle, state_root_id, journal_events, claim, now, folded=folded)
    try:
        return _decide(handle, state_root, state_root_id, journal_events, folded, packet_id, packet_state,
                       attempt, attempt_payload, claim, verdict, coordinator_id, run_id, now)
    except ReviewRefused:
        # Handled refusal: the packet stays in REVIEW and ownership is dropped so
        # another pass can retry. An unexpected interruption deliberately does
        # NOT reach here, leaving claim+pending intent as recovery evidence.
        _release_ownership(handle, state_root_id, journal_events, claim, folded=folded)
        raise


def _decide(handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
            folded: Dict[str, Dict[str, Any]], packet_id: str, packet_state: Dict[str, Any],
            attempt: int, attempt_payload: Dict[str, Any], claim: Dict[str, Any],
            verdict: Dict[str, Any], coordinator_id: str, run_id: str, now: str) -> Dict[str, Any]:
    """Authorize and commit one verdict under an already-owned review claim."""
    from harness_coordinator.v1.coordinator import _load_enrolled_packet

    verdict_intent_id = claim["intent_id"]
    schema_result = validate_verdict(verdict)
    if not schema_result["valid"]:
        codes = [e["code"] for e in schema_result["errors"]]
        _preserve_refusal(handle, packet_id, verdict, codes)
        raise ReviewRefused(codes, f"deposited verdict for {packet_id} is not a valid verdict object")

    trusted_sessions = load_trusted_reviewer_sessions(handle)
    reviewer_session = (verdict.get("reviewer") or {}).get("session_id")
    if reviewer_session not in trusted_sessions:
        _preserve_refusal(handle, packet_id, verdict, ["UNAUTHORIZED_REVIEWER"])
        raise ReviewRefused(["UNAUTHORIZED_REVIEWER"],
                            f"reviewer session {reviewer_session!r} is not in the operator-owned registry")

    packet = _load_enrolled_packet(state_root, packet_id, packet_state, journal_events, handle=handle)
    worker_result = _durable_worker_result(handle, journal_events, packet_id, attempt, attempt_payload)
    bundle, provenance = assemble_replay_bundle(handle, packet, worker_result, verdict, now,
                                                journal_events, folded)

    bundle_result = validate_replay_bundle(bundle, provenance, trusted_sessions)
    if not bundle_result["valid"]:
        codes = [e["code"] for e in bundle_result["errors"]]
        _preserve_refusal(handle, packet_id, verdict, codes)
        raise ReviewRefused(codes, f"coordinator-assembled bundle for {packet_id} is not authorized")

    verdict_bytes = _persist_artifact(handle, _verdict_parts(packet_id, attempt), verdict)
    bundle_bytes = _persist_artifact(handle, _bundle_parts(packet_id, attempt), bundle)
    artifacts = [
        {"kind": "opus_verdict", "artifact_id": f"verdict-{packet_id}-{attempt}",
         "path": _relative(state_root, verdict_artifact_path(state_root, packet_id, attempt)),
         "sha256": compute_sha256(verdict_bytes), "byte_length": len(verdict_bytes)},
        {"kind": "replay_bundle", "artifact_id": f"bundle-{packet_id}-{attempt}",
         "path": _relative(state_root, bundle_artifact_path(state_root, packet_id, attempt)),
         "sha256": compute_sha256(bundle_bytes), "byte_length": len(bundle_bytes)},
    ]
    _commit_verdict(handle, state_root, state_root_id, journal_events, packet_id, verdict_intent_id,
                    verdict, attempt_payload, artifacts, coordinator_id, run_id, now)
    _release_ownership(handle, state_root_id, journal_events, claim)
    return {"packet_id": packet_id, "attempt": attempt, "status": "recorded",
            "verdict": verdict["verdict"], "next_state": verdict["next_state"]}


def _commit_verdict(handle, state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                    packet_id: str, intent_id: str, verdict: Dict[str, Any],
                    attempt_payload: Dict[str, Any], artifacts: List[Dict[str, Any]],
                    coordinator_id: str, run_id: str, now: str) -> Dict[str, Any]:
    """Append VERDICT_RECORDED under compare-and-swap, re-checking on a race.

    ``append_journal``, ``read_journal`` and ``_fold_journal`` are accepted
    primitives that address the journal by pathname and are deliberately not
    duplicated. Root identity is verified immediately before and after each of
    them, so a root replaced around the single authoritative write is detected:
    before the append nothing is written to a replacement, and after it the
    iteration halts rather than sealing or cleaning up against one.
    """
    journal_path = os.path.join(state_root, "journal.ndjson")
    lock_path = os.path.join(state_root, "locks", "journal.wlock")
    payload = {"packet": None, "attempt": attempt_payload, "artifacts": artifacts,
               "classification": None, "transition_detail": None, "recovery": None,
               "run": None, "report": None}
    prev = journal_events[-1] if journal_events else None
    moves = 0
    while True:
        event = _make_event(seq=(prev["seq"] + 1) if prev else 1, event_type="VERDICT_RECORDED",
                            coordinator_id=coordinator_id, run_id=run_id, state_root_id=state_root_id,
                            prev_event=prev, event_at=now, packet_id=packet_id, intent_id=intent_id,
                            from_state="REVIEW", to_state=verdict["next_state"],
                            cause=_CAUSE_BY_VERDICT[verdict["verdict"]], payload=payload)
        try:
            handle.verify_identity()
            append_journal(journal_path, event, lock_path, expected_head=prev)
            handle.verify_identity()
            break
        except JournalHeadMoved:
            moves += 1
            if moves >= _MAX_JOURNAL_CAS_RETRIES:
                raise VerdictConflict("journal head kept moving while committing a verdict")
            handle.verify_identity()
            fresh, torn = read_journal(journal_path, state_root_id=state_root_id)
            handle.verify_identity()
            if torn is not None:
                raise VerdictConflict("torn journal tail while committing a verdict")
            if _journaled_verdict_event(fresh, packet_id, attempt_payload["attempt"]) is not None:
                journal_events[:] = fresh
                return fresh[-1]
            refolded, _ = _fold_journal(state_root, fresh)
            handle.verify_identity()
            if (refolded.get(packet_id) or {}).get("state") != "REVIEW":
                raise VerdictConflict(f"packet {packet_id} left REVIEW while its verdict was being committed")
            journal_events[:] = fresh
            prev = fresh[-1] if fresh else None
    journal_events.append(event)
    return event


def resolve_pending_reviews(state_root: str, state_root_id: str, journal_events: List[Dict[str, Any]],
                            folded: Dict[str, Dict[str, Any]], coordinator_id: str, run_id: str,
                            trusted_process_context: Dict[str, Any], now: str,
                            handle=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Resolve every packet resting in REVIEW, isolating per-packet refusals.

    A refusal is scoped to its packet -- it is not one of design 2.6's
    run-halting conditions, and one untrusted deposit must not stop every
    other packet's review, mirroring ``resolve_open_attempts``' own
    per-packet isolation. ``VerdictConflict`` deliberately propagates: two
    disagreeing durable verdicts are a state-root contradiction, not a
    packet-scoped problem.
    """
    if handle is None:
        # Exactly one pinned root for the entire batch: letting each packet
        # open its own would mean a root replaced between packets is silently
        # accepted by the next one.
        with open_state_root(state_root) as scoped:
            return resolve_pending_reviews(state_root, state_root_id, journal_events, folded,
                                           coordinator_id, run_id, trusted_process_context, now,
                                           handle=scoped)

    outcomes: List[Dict[str, Any]] = []
    attention: List[Dict[str, Any]] = []
    for packet_id in sorted(folded):
        if (folded.get(packet_id) or {}).get("state") != "REVIEW":
            continue
        # Packet boundary: a root replaced since the previous packet halts the
        # batch here rather than processing the remainder from a replacement.
        handle.verify_identity()
        try:
            outcomes.append(resolve_review(state_root, state_root_id, journal_events, folded,
                                           packet_id, coordinator_id, run_id,
                                           trusted_process_context, now, handle=handle))
        except ReviewRefused as exc:
            attention.append({"packet_id": packet_id, "code": "review_refused",
                              "detail": str(exc), "codes": list(exc.codes)})
            continue
        folded, _ = _fold_journal(state_root, journal_events)
    return journal_events, outcomes, attention


__all__ = [
    "ReviewRefused",
    "VerdictConflict",
    "acquire_review_claim",
    "assemble_replay_bundle",
    "current_review_generation",
    "bundle_artifact_path",
    "load_pending_intents",
    "load_trusted_reviewer_sessions",
    "release_review_claim",
    "resolve_pending_reviews",
    "resolve_review",
    "review_claim_path",
    "review_intent_id",
    "verdict_artifact_path",
    "verdict_inbox_path",
    "worker_result_artifact_path",
    "write_review_pending_intent",
]
