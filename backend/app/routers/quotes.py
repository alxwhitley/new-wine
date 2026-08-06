from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import require_admin_role
from app.db.supabase import get_supabase
from app.services import quotes as quotes_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/teachers")
async def get_teachers(user_id: str = Depends(require_admin_role)):
    return quotes_service.list_confirmed_teachers()


@router.get("/documents")
async def get_documents(
    teacher_source_id: str = Query(...),
    user_id: str = Depends(require_admin_role),
):
    db = get_supabase()
    try:
        return quotes_service.list_documents_for_teacher(db, teacher_source_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{document_id}/passages")
async def get_passages(document_id: str, user_id: str = Depends(require_admin_role)):
    db = get_supabase()
    return quotes_service.list_passages_for_document(db, document_id)


class ClearRequest(BaseModel):
    note: str


@router.post("/documents/{document_id}/clear")
async def clear_document(
    document_id: str,
    body: ClearRequest,
    user_id: str = Depends(require_admin_role),
):
    db = get_supabase()
    try:
        return quotes_service.clear_document(db, document_id, user_id, body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CreateQuoteRequest(BaseModel):
    chunk_id: str
    quote_text: str
    teacher_source_id: str
    topic: str
    reviewer_note: str


@router.post("")
async def create_quote(body: CreateQuoteRequest, user_id: str = Depends(require_admin_role)):
    db = get_supabase()
    try:
        return quotes_service.create_and_approve_quote(
            db,
            body.chunk_id,
            body.quote_text,
            body.teacher_source_id,
            body.topic,
            body.reviewer_note,
            user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.warning("Quote approval rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{quote_id}/revoke")
async def revoke_quote_endpoint(quote_id: str, user_id: str = Depends(require_admin_role)):
    db = get_supabase()
    return quotes_service.revoke_quote(db, quote_id, user_id)


@router.get("/{quote_id}/resolve")
async def resolve_quote_endpoint(quote_id: str, user_id: str = Depends(require_admin_role)):
    db = get_supabase()
    result = quotes_service.resolve_quote(db, quote_id)
    if result is None:
        raise HTTPException(status_code=404, detail="quote not found, not approved, or revoked")
    return result
