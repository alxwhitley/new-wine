from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin_role, require_user
from app.db.supabase import get_supabase

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/delete-request")
async def submit_delete_request(user_id: str = Depends(require_user)):
    """Any authenticated user -- request account deletion. Logs the request
    for manual admin follow-up; does not delete anything itself."""
    db = get_supabase()

    existing = (
        db.table("deletion_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending deletion request",
        )

    email = ""
    email_result = db.rpc("get_user_emails", {"user_ids": [user_id]}).execute()
    if email_result.data:
        email = email_result.data[0].get("email") or ""

    db.table("deletion_requests").insert({
        "user_id": user_id,
        "email": email,
        "status": "pending",
    }).execute()

    logger.info("Deletion request submitted: user_id=%s", user_id)
    return {"success": True}


@router.get("/delete-requests")
async def list_delete_requests(admin_id: str = Depends(require_admin_role)):
    """Admin only -- list all pending account deletion requests."""
    db = get_supabase()
    result = (
        db.table("deletion_requests")
        .select("id, user_id, email, created_at")
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    return result.data or []


@router.post("/delete-requests/{request_id}/resolve")
async def resolve_delete_request(
    request_id: str,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only -- mark a deletion request resolved. Does not delete any
    data -- that still happens manually, outside this endpoint."""
    db = get_supabase()

    existing = (
        db.table("deletion_requests")
        .select("id, status")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")
    if existing.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")

    db.table("deletion_requests").update({
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", request_id).execute()

    logger.info("Deletion request resolved: request_id=%s by admin=%s", request_id, admin_id)
    return {"success": True}
