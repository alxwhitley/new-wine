from __future__ import annotations

import logging
import os
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import get_optional_user
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_EMAIL = "alxwhitley@gmail.com"

_jwks_client = PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])


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


def _require_admin(request: Request) -> str:
    """Extract JWT, verify email is admin."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=403, detail="Not authenticated")

    token = auth_header[7:]
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid token")

    if payload.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    return payload.get("sub", "")


@router.get("")
async def list_feedback(
    request: Request,
    rating: Optional[str] = Query(None, description="Filter by rating: thumbs_up or thumbs_down"),
    source_type: Optional[str] = Query(None, description="Filter by source_type: chat_answer, commentary, word_study"),
    user_id: str = Depends(_require_admin),
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
