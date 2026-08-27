"""Consent identity API for the search-analytics ledger. Any authenticated
user -- not admin-gated (this is a user managing their own consent, same
posture as account.py's /account/delete-request).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_user
from app.db.supabase import get_supabase
from app.services.async_answers.db import Db
from app.services.search_analytics import consent as consent_service

router = APIRouter()


@router.get("/consent")
async def get_consent_status_route(user_id: str = Depends(require_user)):
    supabase = get_supabase()
    return consent_service.get_consent_status(supabase, user_id)


@router.put("/consent")
async def acknowledge_consent_route(user_id: str = Depends(require_user)):
    supabase = get_supabase()
    consent_service.acknowledge(supabase, user_id)
    return {"success": True}


@router.delete("/consent")
async def withdraw_consent_route(user_id: str = Depends(require_user)):
    supabase = get_supabase()
    db = Db()
    try:
        consent_service.withdraw(db, supabase, user_id)
    finally:
        db.close()
    return {"success": True}
