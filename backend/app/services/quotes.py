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

import logging
import os
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

# ── Live-answer selection (2026-08-06 wiring session) ────────────────────────
#
# QUOTE_TOPIC_SIMILARITY_THRESHOLD -- PROVISIONAL, needs real-USAGE
# calibration (no real question traffic has exercised this yet -- only 2
# approved quotes exist corpus-wide), but NOT a blind guess: an initial 0.75
# (chosen by analogy to position_papers.py's anchor-vs-anchor similarities,
# which run much higher because both sides of that comparison are similarly-
# shaped phrases) turned out badly miscalibrated for this comparison shape --
# a full question sentence against a short 2-4 word topic tag scores
# structurally lower. Caught live, 2026-08-06, by this session's own
# end-to-end test: the real "waiting on God" match scored 0.579, well under
# 0.75, so nothing was ever selected. Recalibrated against 10 real embedding
# calls (4 genuine question/topic matches, 6 genuine non-matches, both
# corpus topics, varied question phrasing):
#   matches:     0.4968, 0.5469, 0.5790, 0.5854
#   non-matches: 0.0844, 0.1116, 0.1451, 0.1818, 0.2482, 0.2560
# Clean separation with a ~0.24 gap between the closest match (0.4968) and
# the closest non-match (0.2560). 0.40 sits in that gap -- a real measured
# margin, not a round number, same evidentiary posture as position_papers.py's
# own TIE_BREAK_EPSILON comment. Still provisional: n=10 hand-written
# questions, not real traffic, and both corpus topics happen to be short
# noun phrases -- a future quote with a longer or oddly-worded topic tag
# could sit outside this calibration. Revisit once real traffic and more
# quote volume exist, exactly as dominance.py's own threshold note describes
# for its own constant.
QUOTE_TOPIC_SIMILARITY_THRESHOLD = 0.40

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


def create_and_approve_quote(
    db,
    chunk_id: str,
    quote_text: str,
    teacher_source_id: str,
    topic: str,
    reviewer_note: str,
    user_id: str,
):
    """Create and approve a quote in one action. There is no human approval
    step (removed 2026-08-08) -- a candidate is saved as approved directly
    once it passes every check in quote_verifier.verify_quote_candidate()
    (exact-substring match, exclusion zone, boundary/sentence-completeness,
    speaker confirmation). Refusals are final: this function raises rather
    than saving a draft for later reconsideration. The database's own
    trigger (migration 082, gates revised by migration 085) re-checks the
    exact-match, commentary, clearance, and speaker gates as the
    authoritative backstop, against the immutable snapshot this function
    captures, not a later re-read of the chunk. Also runs the per-work
    quote cap (_enforce_quote_cap, Settled decision #16) -- application-
    level only, not DB-trigger-enforced; see that function's docstring.
    Every acceptance and refusal is logged via _log_quote_decision()."""
    _require_confirmed_teacher(teacher_source_id)
    for label, value in (("quote_text", quote_text), ("topic", topic), ("reviewer_note", reviewer_note)):
        if not value or not value.strip():
            raise ValueError("%s is required" % label)

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
    quote = (
        db.table("quotes")
        .insert(
            {
                "source_revision_id": revision["id"],
                "teacher_source_id": teacher_source_id,
                "quote_text": quote_text,
                "topic": topic.strip(),
                "reviewer_note": reviewer_note.strip(),
                "status": "approved",
                "created_by": user_id,
                "approved_by": user_id,
                "approved_at": now,
            }
        )
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

    Candidates: status='approved' AND teacher_source_id in
    considered_teacher_source_ids -- the FULL set of teachers whose material
    was considered/retrieved for this answer, deliberately NOT narrowed to
    only the teachers actually cited. This is a looser-matching decision
    (Alex's explicit call, 2026-08-06): a quote can appear beside an answer
    that didn't end up citing that teacher at all. Known, accepted residual
    risk, not a bug -- narrowing to cited-only is a one-line change here
    (intersect against the answer's own citations) if this proves too loose
    in practice.

    Matching: cosine similarity between an embedding of the raw question and
    an embedding of each candidate's short `topic` tag (e.g. "fasting",
    "waiting on God") -- fully deterministic given the same inputs, no live
    LLM judgment call. See QUOTE_TOPIC_SIMILARITY_THRESHOLD's module-level
    comment for why 0.75 and its provisional status.

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
        .select("id, topic")
        .eq("status", "approved")
        .in_("teacher_source_id", source_ids)
        .execute()
        .data
    )
    if not rows:
        return []

    q_vec = question_embedding if question_embedding is not None else embed_text(question)
    topic_vecs = embed_batch([r["topic"] for r in rows])

    scored = []  # type: List[Tuple[float, str]]
    for row, topic_vec in zip(rows, topic_vecs):
        score = cosine_similarity(q_vec, topic_vec)
        if score >= QUOTE_TOPIC_SIMILARITY_THRESHOLD:
            scored.append((score, row["id"]))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected = [quote_id for _, quote_id in scored[:MAX_QUOTES_PER_ANSWER]]
    if selected:
        logger.info(
            "quote_rail: selected %d quote(s) for question=%r | scores=%s | threshold=%.2f",
            len(selected), question, [round(s, 4) for s, _ in scored[:MAX_QUOTES_PER_ANSWER]],
            QUOTE_TOPIC_SIMILARITY_THRESHOLD,
        )
    return selected
