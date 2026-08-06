"""
Quote rail service functions (Project 3, manual-curation-only).

Document/passage listing for review, source clearance, quote creation +
approval, revocation, and the single resolution point (Step 4) -- the only
sanctioned way anything in this codebase may read an approved quote's text.
See migration 082 for the schema and the hard database-level approval
gates (commentary exclusion, source clearance, admin-only approval,
exact-substring match) -- this module is the application-side counterpart,
never a substitute for them. A quote this module tries to approve without
satisfying every gate is rejected by the database itself, not just by the
checks here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.services.quote_verifier import verify_quote_exact_match

# The two teachers this rail is currently scoped to -- an application-level
# curation decision (docs/audits/quote_rail_project3_audit_2026-08-06.md),
# not a schema constraint. Widening it later needs no migration.
CONFIRMED_TEACHER_SOURCE_IDS = {
    "17be391b-d025-4178-8543-3e84da675c5d": "Derek Prince",
    "d26f77e7-6ce0-4311-991b-03d9900a6045": "Andrew Murray",
}


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


def create_and_approve_quote(
    db,
    chunk_id: str,
    quote_text: str,
    teacher_source_id: str,
    topic: str,
    reviewer_note: str,
    user_id: str,
):
    """Create a quote and immediately attempt to approve it in one action --
    the review tool has one human doing selection and approval together, so
    a separate draft step adds no real safety. Runs the Step 2 verifier
    first for a clean, specific rejection reason; the database's own
    trigger (migration 082) re-checks the same rule plus the other three
    hard gates as the authoritative backstop, against the immutable
    snapshot this function captures, not a later re-read of the chunk."""
    _require_confirmed_teacher(teacher_source_id)
    for label, value in (("quote_text", quote_text), ("topic", topic), ("reviewer_note", reviewer_note)):
        if not value or not value.strip():
            raise ValueError("%s is required" % label)

    verification = verify_quote_exact_match(db, chunk_id, quote_text)
    if not verification.valid:
        raise ValueError("verifier rejected candidate: %s" % verification.reason)

    chunk_rows = db.table("chunks").select("content").eq("id", chunk_id).limit(1).execute().data
    if not chunk_rows:
        raise ValueError("chunk %s not found" % chunk_id)
    passage_text = chunk_rows[0]["content"]

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
