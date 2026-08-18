"""
Quote rail service functions (Project 3).

Document/passage listing for curation, source clearance, quote creation,
revocation, and the single resolution point (Step 4) -- the only sanctioned
way anything in this codebase may read an approved quote's text.

Human approval was removed 2026-08-08 (CLAUDE.md "Settled product decisions
(2026-08-08)" -- per-quote review did not scale). A candidate that passes
every check in app.services.quote_verifier.verify_quote_candidate() is saved
as approved directly -- there is no separate person confirming it, and
nothing here is an LLM/AI judgment call either; approval is now a
deterministic function of the tightened verifier's checks. See migration
085 for the schema change (the admin-role approval gate removed from the
database trigger, a speaker-confirmation gate added in its place) and
migration 082 for what still stands (commentary exclusion, source
clearance, exact-substring match) -- this module is the application-side
counterpart, never a substitute for the database's own gates. A quote this
module tries to approve without satisfying every gate is rejected by the
database itself, not just by the checks here. Every acceptance and refusal
is written to quote_verification_log (migration 085) -- a record, not a
review queue; see _log_quote_decision().
"""
from __future__ import annotations

import hashlib
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, List, Mapping, Optional, Tuple

from app.services.embeddings import cosine_similarity, embed_batch, embed_text
from app.services.quote_verifier import verify_quote_candidate

logger = logging.getLogger(__name__)


def quote_selection_enabled(env: Mapping[str, str] = os.environ) -> bool:
    """Return whether live answers may attach existing quote IDs.

    The quote rail is contained by default while the inherited topic labels
    are repaired. Only the explicit lowercase opt-in enables selection.
    """
    return env.get("QUOTE_SELECTION_ENABLED") == "true"

# The two teachers this rail is currently scoped to -- an application-level
# curation decision (docs/audits/quote_rail_project3_audit_2026-08-06.md),
# not a schema constraint. Widening it later needs no migration.
CONFIRMED_TEACHER_SOURCE_IDS = {
    "17be391b-d025-4178-8543-3e84da675c5d": "Derek Prince",
    "d26f77e7-6ce0-4311-991b-03d9900a6045": "Andrew Murray",
}

# ── Live-answer selection (2026-08-06 wiring session; relevance rebuilt 2026-08-18) ──
#
# QUOTE_PASSAGE_SIMILARITY_THRESHOLD replaces QUOTE_TOPIC_SIMILARITY_THRESHOLD
# (the original 2026-08-06 constant, which scored a question against
# quotes.topic). That design was contained behind QUOTE_SELECTION_ENABLED's
# default-off flag 2026-08-17 (CLAUDE.md Landmines) after being found to have
# a systemic relevance defect, confirmed live against the real corpus
# 2026-08-18: `topic` is typically the source DOCUMENT's own first
# `topic_tags` entry (scripts/extract_quote_candidates_derek_prince.py::
# _topic_for_document()), not anything specific to the individual quoted
# passage -- so every quote pulled from the same document, or from different
# documents that merely share a first tag, scores IDENTICALLY regardless of
# what its own text says. Confirmed live: all 14 real approved quotes tagged
# "Baptism in the Holy Spirit" score exactly 0.7553 against a real baptism
# question -- a perfect tie -- even though several of those 14 passages (a
# Hebrew/Greek grammar aside, an unrelated book title mid-resurrection-
# discourse, a list of seven forms of prayer) have nothing to do with the
# question. The tie also exposed a second, independent bug: the query had no
# ORDER BY, so which quotes made the top-MAX_QUOTES_PER_ANSWER cut on a tie
# depended on Postgres's unspecified return order for an unordered SELECT,
# not on any property of the quotes themselves -- fixed below by scoring
# real text (which essentially never ties on unrelated passages) plus an
# explicit id tie-break and an explicit query ORDER BY, so a tie can no
# longer happen by construction.
#
# PROVISIONAL, same posture as the constant it replaces -- calibrated against
# real embedding calls, not a blind guess, but still a small n, not real
# question traffic. Calibrated 2026-08-18 against real text-embedding-3-small
# calls across 4 real questions and 3 real approved-quote clusters (baptism
# in the Holy Spirit, fasting, marriage), plus one shared unrelated
# "finances/giving" negative-control question run against every cluster.
# On-topic passages that directly address their cluster's own question
# scored 0.4569-0.6251. Off-topic passages -- both within an on-topic
# cluster (real content that has nothing to do with the question despite
# sharing the OLD topic tag) and under the unrelated negative-control
# question against any cluster -- scored 0.1136-0.3173. The two bands
# overlap narrowly (0.3173-0.3595): no single threshold cleanly separates
# every real match from every real non-match, because semantic similarity
# on real prose is not that tidy. 0.35 sits inside that overlap, above every
# observed non-match, at the cost of excluding a couple of weaker genuine
# matches (0.3595, 0.3656) -- the accepted trade given this file's standing
# "refuse rather than risk it" posture (same posture as quote_verifier.py's
# boundary-proximity check, and Settled decision #16): a missed true
# positive costs nothing (the answer already reads fine with no quote
# attached); a false positive is the exact defect this replaces. Revisit
# once real traffic and more quote volume exist, same as the constant this
# replaces and dominance.py's own threshold note.
QUOTE_PASSAGE_SIMILARITY_THRESHOLD = 0.35

# How many quotes may attach to a single answer. Provisional, same posture as
# the threshold above -- irrelevant at today's volume (2 approved quotes
# total, so at most 2 could ever qualify), but the selector needs SOME bound
# before quote volume grows past what "beside the answer" can reasonably show.
MAX_QUOTES_PER_ANSWER = 3

# Settled decision #16 ("cumulative unique approved-quote text per work is
# capped AT APPROVAL TIME"). No cap value was specified anywhere in the
# governing docs before this session -- PROVISIONAL, needs real-usage
# calibration, same posture as the constants above. 2000 characters is a
# conservative starting ceiling: existing approved quotes run 93-164
# characters (2026-08-06), so this permits roughly a dozen quotes per work
# before blocking further approval, comfortably short of what could read as
# reconstructing a meaningful fraction of the source text through many small
# "quotes."
#
# "Work" = one `documents` row. document_work_groups (migration 071, e.g. the
# 20-part "Roman Pilgrimage" series) is NOT wired into any consumer yet
# (confirmed docs/audits/quote_rail_project3_audit_2026-08-06.md) -- so a
# split-work series is capped PER DOCUMENT, not per underlying teaching, until
# that grouping is wired in somewhere. A known, disclosed gap, not a silent
# one: closing it means changing _document_id_for_cap() below once
# document_work_groups has a real consumer to resolve through.
QUOTE_CAP_CHARS_PER_WORK = 2000


def _require_confirmed_teacher(teacher_source_id: str) -> None:
    if teacher_source_id not in CONFIRMED_TEACHER_SOURCE_IDS:
        raise ValueError("teacher_source_id is not in the confirmed quote-rail scope")


def list_confirmed_teachers():
    return [{"source_id": sid, "name": name} for sid, name in CONFIRMED_TEACHER_SOURCE_IDS.items()]


def list_documents_for_teacher(db, teacher_source_id: str):
    _require_confirmed_teacher(teacher_source_id)
    docs = (
        db.table("documents")
        .select("id, title, source_kind")
        .eq("source_id", teacher_source_id)
        .order("title")
        .execute()
        .data
    )
    doc_ids = [d["id"] for d in docs]
    cleared_ids = set()
    if doc_ids:
        rows = (
            db.table("document_quote_clearance")
            .select("document_id")
            .in_("document_id", doc_ids)
            .execute()
            .data
        )
        cleared_ids = {r["document_id"] for r in rows}
    for d in docs:
        d["cleared"] = d["id"] in cleared_ids
    return docs


def list_passages_for_document(db, document_id: str):
    return (
        db.table("chunks")
        .select("id, chunk_index, content, quote_ineligible_reason")
        .eq("document_id", document_id)
        .order("chunk_index")
        .execute()
        .data
    )


def clear_document(db, document_id: str, cleared_by: str, note: str):
    if not note or not note.strip():
        raise ValueError("a clearance note is required")
    existing = (
        db.table("document_quote_clearance")
        .select("document_id")
        .eq("document_id", document_id)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        return {"already_cleared": True}
    db.table("document_quote_clearance").insert(
        {"document_id": document_id, "cleared_by": cleared_by, "note": note.strip()}
    ).execute()
    return {"already_cleared": False}


def _enforce_quote_cap(db, document_id: str, candidate_quote_text: str) -> None:
    """Settled decision #16's "cumulative unique approved-quote text per work
    is capped AT APPROVAL TIME" -- application-level only (unlike migration
    082's four hard gates, this is NOT also a DB trigger; see
    QUOTE_CAP_CHARS_PER_WORK's module-level comment for why that's an
    accepted, narrower boundary for this particular rule, and for the
    per-document-not-per-work-group caveat). Raises ValueError, same pattern
    as the Step 2 verifier check above -- caught by the router and turned
    into a clean 400, before any row is written."""
    sibling_chunks = db.table("chunks").select("id").eq("document_id", document_id).execute().data
    chunk_ids = [c["id"] for c in sibling_chunks]
    if not chunk_ids:
        return
    revisions = (
        db.table("quote_source_revisions").select("id").in_("chunk_id", chunk_ids).execute().data
    )
    revision_ids = [r["id"] for r in revisions]
    existing_texts = set()  # type: set
    if revision_ids:
        existing_rows = (
            db.table("quotes")
            .select("quote_text")
            .in_("source_revision_id", revision_ids)
            .eq("status", "approved")
            .execute()
            .data
        )
        existing_texts = {r["quote_text"] for r in existing_rows}
    projected_chars = sum(len(t) for t in (existing_texts | {candidate_quote_text}))
    if projected_chars > QUOTE_CAP_CHARS_PER_WORK:
        raise ValueError(
            "quote cap exceeded for this document: %d existing approved chars + this "
            "candidate would total %d chars, over the provisional cap of %d"
            % (sum(len(t) for t in existing_texts), projected_chars, QUOTE_CAP_CHARS_PER_WORK)
        )


def _log_quote_decision(
    db,
    *,
    chunk_id: Optional[str],
    document_id: Optional[str],
    teacher_source_id: Optional[str],
    quote_text: str,
    decision: str,
    rule: str,
    reason: Optional[str],
    submitted_by: str,
) -> None:
    """Write one row to quote_verification_log (migration 085). A record,
    not a review queue -- nobody reads this routinely; it exists so that if
    a bad quote ever surfaces, the path that let it through is
    reconstructable. Fail-soft on the log write itself: a logging failure
    must never change, block, or retroactively undo the actual accept/
    refuse decision it's describing."""
    try:
        db.table("quote_verification_log").insert(
            {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "teacher_source_id": teacher_source_id,
                "candidate_quote_text": quote_text,
                "decision": decision,
                "rule": rule,
                "reason": reason,
                "submitted_by": submitted_by,
            }
        ).execute()
    except Exception as e:
        logger.warning("quote_verification_log write failed (decision=%s, rule=%s): %s", decision, rule, e)


def _find_existing_quote_for_passage(
    db, chunk_id: str, quote_text: str, teacher_source_id: str
) -> Optional[dict]:
    """Idempotency lookup for create_and_approve_quote(): has this exact
    (chunk, quote_text, teacher) triple already been created? Matches only
    the exact triple a rerun with identical inputs would produce -- not
    fuzzy/overlap matching, a different, unbuilt feature. Ignores revoked
    rows: a revoked quote does not block re-creating the same passage,
    since revocation is a deliberate state change (Settled decision #16),
    not evidence the passage itself is unusable. Deterministic even if more
    than one match somehow already exists (e.g. a pre-existing duplicate
    from before this check existed): oldest created_at wins, id as a final
    tie-break -- never DB return order."""
    revisions = (
        db.table("quote_source_revisions").select("id").eq("chunk_id", chunk_id).execute().data
    )
    revision_ids = [r["id"] for r in revisions]
    if not revision_ids:
        return None
    rows = (
        db.table("quotes")
        .select("id, source_revision_id, teacher_source_id, quote_text, topic, "
                "reviewer_note, status, created_by, approved_by, approved_at")
        .in_("source_revision_id", revision_ids)
        .eq("quote_text", quote_text)
        .eq("teacher_source_id", teacher_source_id)
        .neq("status", "revoked")
        .order("created_at")
        .order("id")
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def _advisory_lock_key(chunk_id: str, quote_text: str, teacher_source_id: str) -> int:
    """Deterministic signed-64-bit key for pg_advisory_lock(bigint), derived
    from the exact triple _find_existing_quote_for_passage() matches on. The
    same triple always hashes to the same key (SHA-256, not Python's salted
    hash()), so two callers racing the same passage always contend for the
    same lock; two callers on different passages essentially never collide
    (a collision would only cost unrelated over-serialization, never a
    missed duplicate -- see _creation_lock's docstring)."""
    raw = "\x1f".join((chunk_id, teacher_source_id, quote_text)).encode("utf-8")
    digest = hashlib.sha256(raw).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def _creation_lock(chunk_id: str, quote_text: str, teacher_source_id: str):
    """Makes a concurrent duplicate quote creation genuinely impossible, not
    merely unlikely (2026-08-18 hardening -- CLAUDE.md Landmines' logged
    idempotency finding: _find_existing_quote_for_passage() was a bare
    SELECT with no lock behind it, so two callers racing the exact same
    (chunk_id, quote_text, teacher_source_id) triple could both see "not
    found" and both insert).

    A DB-level UNIQUE constraint was the other option and was rejected: the
    identity this function guards spans two tables (quote_source_revisions.
    chunk_id, quotes.quote_text/teacher_source_id), so expressing it as a
    real constraint would mean denormalizing chunk_id onto quotes plus a
    partial unique index (excluding revoked rows, which must not block
    recreation) -- schema DDL, i.e. a migration, for a race window this
    session's scope explicitly prefers to close in code alone if genuinely
    possible. A Postgres session-level advisory lock closes it just as
    completely with no schema change: pg_advisory_lock is a true
    cross-session mutex the database itself enforces, not an
    application-level convention -- two processes (or two Postgres sessions
    from the same process) requesting the same key are strictly
    serialized by Postgres, regardless of which connection later performs
    the actual idempotency SELECT or INSERT.

    Opens its own short-lived psycopg2 connection via
    app.services.async_answers.db.connect() (the existing SUPABASE_DB_URL
    helper this codebase already uses for the same class of problem --
    source_ingest_queue's FOR UPDATE SKIP LOCKED claiming) because the
    PostgREST client (`db`, supabase-py) create_and_approve_quote()
    otherwise uses has no session/transaction concept to hold a lock on;
    each PostgREST call is its own independent, auto-committing request.
    The lock is session-scoped (pg_advisory_lock, not the _xact_ variant)
    because the guarded work happens over `db`, a separate connection --
    holding the lock only needs the dedicated connection to stay open and
    unlock explicitly, not an open transaction wrapping the guarded calls.

    Not on the hot per-answer path: create_and_approve_quote() is the
    admin-only quote-creation call (backend/app/routers/quotes.py), not
    select_quotes_for_answer() (the live per-answer read path) -- a fresh
    connection per creation call is deliberately not optimized for
    throughput here."""
    from app.services.async_answers.db import connect

    key = _advisory_lock_key(chunk_id, quote_text, teacher_source_id)
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_lock(%s)", (key,))
        yield
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (key,))
        finally:
            cur.close()
            conn.close()


QUALITY_PIPELINE_VERSION_V1 = "quote_quality_v1"


def create_and_approve_quote(
    db,
    chunk_id: str,
    quote_text: str,
    teacher_source_id: str,
    topic: str,
    reviewer_note: str,
    user_id: str,
    *,
    topic_ids: Optional[List[str]] = None,
    quality_pipeline_version: Optional[str] = None,
    selection_eligible: Optional[bool] = None,
    status: str = "approved",
):
    """Create a quote after verify_quote_candidate passes.

    Default status is ``approved`` (Settled #18 auto-approve). The quality
    pipeline (Task 5) may pass ``status='pending'`` for the first gold set
    so Alex can batch-review before anything is selection-eligible as
    approved. Optional ``topic_ids`` / ``quality_pipeline_version`` /
    ``selection_eligible`` stamp migration-089 columns; when a pipeline
    version is set and selection_eligible is omitted, eligibility defaults
    to True.

    Refusals are final: this function raises rather than saving a draft for
    later reconsideration. The database trigger re-checks exact-match,
    commentary, clearance, and speaker gates against the immutable snapshot.
    Also runs the per-work quote cap (_enforce_quote_cap). Every acceptance
    and refusal is logged via _log_quote_decision().

    Idempotent (2026-08-18): re-running over the exact same
    (chunk_id, quote_text, teacher_source_id) returns the existing row
    unchanged — including a matching PENDING row, never silently flipped
    to approved by this check."""
    _require_confirmed_teacher(teacher_source_id)
    for label, value in (("quote_text", quote_text), ("topic", topic), ("reviewer_note", reviewer_note)):
        if not value or not value.strip():
            raise ValueError("%s is required" % label)
    if status not in ("approved", "pending"):
        raise ValueError("status must be 'approved' or 'pending', got %r" % status)

    with _creation_lock(chunk_id, quote_text, teacher_source_id):
        existing = _find_existing_quote_for_passage(db, chunk_id, quote_text, teacher_source_id)
        if existing is not None:
            logger.info(
                "create_and_approve_quote: idempotent no-op -- quote %s already exists "
                "for this exact chunk/text/teacher (status=%s)",
                existing["id"], existing["status"],
            )
            return existing

        chunk_lookup = db.table("chunks").select("document_id").eq("id", chunk_id).limit(1).execute().data
        document_id_for_log = chunk_lookup[0]["document_id"] if chunk_lookup else None

        verification = verify_quote_candidate(db, chunk_id, quote_text, teacher_source_id)
        if not verification.valid:
            _log_quote_decision(
                db,
                chunk_id=chunk_id,
                document_id=document_id_for_log,
                teacher_source_id=teacher_source_id,
                quote_text=quote_text,
                decision="refused",
                rule=verification.rule,
                reason=verification.reason,
                submitted_by=user_id,
            )
            raise ValueError("verifier rejected candidate: %s" % verification.reason)

        chunk_rows = db.table("chunks").select("content, document_id").eq("id", chunk_id).limit(1).execute().data
        if not chunk_rows:
            raise ValueError("chunk %s not found" % chunk_id)
        passage_text = chunk_rows[0]["content"]
        document_id = chunk_rows[0]["document_id"]

        try:
            _enforce_quote_cap(db, document_id, quote_text)
        except ValueError as e:
            _log_quote_decision(
                db,
                chunk_id=chunk_id,
                document_id=document_id,
                teacher_source_id=teacher_source_id,
                quote_text=quote_text,
                decision="refused",
                rule="quote_cap_exceeded",
                reason=str(e),
                submitted_by=user_id,
            )
            raise

        revision = (
            db.table("quote_source_revisions")
            .insert({"chunk_id": chunk_id, "passage_text": passage_text, "captured_by": user_id})
            .execute()
            .data[0]
        )

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "source_revision_id": revision["id"],
            "teacher_source_id": teacher_source_id,
            "quote_text": quote_text,
            "topic": topic.strip(),
            "reviewer_note": reviewer_note.strip(),
            "status": status,
            "created_by": user_id,
        }
        if status == "approved":
            row["approved_by"] = user_id
            row["approved_at"] = now
        if topic_ids is not None:
            row["topic_ids"] = list(topic_ids)
        if quality_pipeline_version is not None:
            row["quality_pipeline_version"] = quality_pipeline_version
            if selection_eligible is None:
                selection_eligible = True
        if selection_eligible is not None:
            row["selection_eligible"] = bool(selection_eligible)

        quote = (
            db.table("quotes")
            .insert(row)
            .execute()
            .data[0]
        )

        _log_quote_decision(
            db,
            chunk_id=chunk_id,
            document_id=document_id,
            teacher_source_id=teacher_source_id,
            quote_text=quote_text,
            decision="accepted",
            rule="accepted",
            reason=None,
            submitted_by=user_id,
        )
        return quote


def revoke_quote(db, quote_id: str, user_id: str):
    now = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("quotes")
        .update({"status": "revoked", "revoked_by": user_id, "revoked_at": now})
        .eq("id", quote_id)
        .execute()
    )
    return result.data


def resolve_quote(db, quote_id: str) -> Optional[dict]:
    """THE single resolution point (Step 4). Returns the current approved
    text + metadata, or None if the quote does not exist, is still a draft,
    or has been revoked. Every surface that might show a quote (answers,
    teacher pages, previews, exports, admin tools) must call this function
    -- nothing else in this codebase should read quotes.quote_text directly."""
    rows = (
        db.table("quotes")
        .select("id, quote_text, topic, teacher_source_id, status, approved_at")
        .eq("id", quote_id)
        .eq("status", "approved")
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    quote = rows[0]
    teacher_name = CONFIRMED_TEACHER_SOURCE_IDS.get(quote["teacher_source_id"])
    if teacher_name is None:
        source_rows = db.table("sources").select("name").eq("id", quote["teacher_source_id"]).limit(1).execute().data
        teacher_name = source_rows[0]["name"] if source_rows else None
    return {
        "id": quote["id"],
        "quote_text": quote["quote_text"],
        "topic": quote["topic"],
        "teacher_name": teacher_name,
        "approved_at": quote["approved_at"],
    }


def select_quotes_for_answer(
    db,
    question: str,
    considered_teacher_source_ids: Iterable[str],
    question_embedding: Optional[List[float]] = None,
) -> List[str]:
    """Deterministic, post-generation quote selection for the live answer
    path (2026-08-06 wiring session; async path only -- see producer.py's
    call site). Returns a list of quote IDS ONLY -- never text -- ready to
    travel in the meta frame and be resolved later through resolve_quote(),
    the single resolution point.

    Candidates (2026-08-19 quality pipeline): status='approved' AND
    selection_eligible=true AND quality_pipeline_version IS NOT NULL AND
    teacher_source_id in considered_teacher_source_ids. Legacy approved
    rows (null pipeline version / selection_eligible=false after migration
    089) are never selected even when quote_text would match the question.
    Teacher scope remains the FULL set of teachers whose material was
    considered/retrieved for this answer, deliberately NOT narrowed to
    only the teachers actually cited (Alex's explicit call, 2026-08-06).

    Matching (rebuilt 2026-08-18): cosine similarity between an embedding of
    the raw question and an embedding of each candidate's OWN quote_text --
    the exact, verified excerpt quote_verifier.verify_quote_candidate()
    already confirmed sits inside its source passage. V1 does not soft-boost
    from topic tags. See QUOTE_PASSAGE_SIMILARITY_THRESHOLD's module comment
    for calibration. Still fully deterministic given the same inputs.

    Deterministic tie-breaking: candidates are fetched in an explicit id
    order (never bare DB return order) and scored candidates are sorted by
    (score descending, quote id ascending) -- a strict total order.

    Callers MUST wrap this in their own fail-soft try/except (this function
    can raise -- an embedding-API fault, a DB fault) -- it does not swallow
    its own errors, so a caller that forgets to wrap it will not get the
    "answer delivers unchanged on any quote-rail fault" guarantee the design
    requires."""
    source_ids = sorted({sid for sid in considered_teacher_source_ids if sid})
    if not source_ids:
        return []

    rows = (
        db.table("quotes")
        .select("id, quote_text, selection_eligible, quality_pipeline_version")
        .eq("status", "approved")
        .in_("teacher_source_id", source_ids)
        .order("id")
        .execute()
        .data
    ) or []

    # Application-side eligibility (migration 089). Filtering here — not only
    # in SQL — keeps FakeDb / older clients honest and matches the predicate
    # Task 6 requires even if a row omitted the new columns.
    rows = [
        r for r in rows
        if r.get("selection_eligible") is True
        and r.get("quality_pipeline_version")
    ]
    if not rows:
        return []

    q_vec = question_embedding if question_embedding is not None else embed_text(question)
    text_vecs = embed_batch([r["quote_text"] for r in rows])

    scored = []  # type: List[Tuple[float, str]]
    for row, text_vec in zip(rows, text_vecs):
        score = cosine_similarity(q_vec, text_vec)
        if score >= QUOTE_PASSAGE_SIMILARITY_THRESHOLD:
            scored.append((score, row["id"]))

    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    selected = [quote_id for _, quote_id in scored[:MAX_QUOTES_PER_ANSWER]]
    if selected:
        logger.info(
            "quote_rail: selected %d quote(s) for question=%r | scores=%s | threshold=%.2f",
            len(selected), question, [round(s, 4) for s, _ in scored[:MAX_QUOTES_PER_ANSWER]],
            QUOTE_PASSAGE_SIMILARITY_THRESHOLD,
        )
    return selected
