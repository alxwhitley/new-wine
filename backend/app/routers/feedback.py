from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import get_optional_user, require_admin
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    message_id: Optional[str] = None
    rating: str  # 'thumbs_up' or 'thumbs_down'
    comment: Optional[str] = None
    question: str
    anon_id: Optional[str] = None
    source_type: Optional[str] = None  # 'chat_answer', 'commentary', 'word_study'
    source_document_id: Optional[str] = None


@router.post("", status_code=201)
async def submit_feedback(
    body: FeedbackRequest,
    user_id: Optional[str] = Depends(get_optional_user),
):
    if body.rating not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(status_code=400, detail="rating must be 'thumbs_up' or 'thumbs_down'")

    db = get_supabase()

    row = {
        "rating": body.rating,
        "question": body.question,
        "comment": body.comment,
        "user_id": user_id,
        "anon_id": body.anon_id,
        "source_type": body.source_type,
    }
    if body.message_id:
        row["message_id"] = body.message_id
    if body.source_document_id:
        row["source_document_id"] = body.source_document_id

    try:
        db.table("feedback").insert(row).execute()
    except Exception:
        logger.exception("Failed to insert feedback")
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    return {"status": "ok"}


@router.get("")
async def list_feedback(
    request: Request,
    rating: Optional[str] = Query(None, description="Filter by rating: thumbs_up or thumbs_down"),
    source_type: Optional[str] = Query(None, description="Filter by source_type: chat_answer, commentary, word_study"),
    user_id: str = Depends(require_admin),
):
    db = get_supabase()

    query = db.table("feedback").select("*").order("created_at", desc=True).limit(50)
    if rating:
        query = query.eq("rating", rating)
    if source_type:
        if source_type == "chat_answer":
            query = query.is_("source_type", "null")
        else:
            query = query.eq("source_type", source_type)

    result = query.execute()
    return {"feedback": result.data or []}
