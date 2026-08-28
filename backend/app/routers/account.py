from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin_role, require_user
from app.db.supabase import get_supabase
from app.services.account_deletion import DeletionFailure, resolve_deletion_request
from app.services.async_answers.db import Db

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
    """Admin only -- list pending and failed (retryable) account deletion
    requests. Resolved requests no longer exist here (deletion_requests
    cascades away with the deleted account) -- see GET /delete-requests/history."""
    db = get_supabase()
    result = (
        db.table("deletion_requests")
        .select("id, user_id, email, created_at, status, failure_reason")
        .in_("status", ["pending", "failed"])
        .order("created_at")
        .execute()
    )
    return result.data or []


@router.get("/delete-requests/history")
async def list_delete_request_history(admin_id: str = Depends(require_admin_role)):
    """Admin only -- resolved/failed deletion history, from the durable
    audit log (deletion_requests itself cascades away once an account is
    actually deleted -- this is the only surviving record)."""
    db = get_supabase()
    result = (
        db.table("deletion_audit_log")
        .select(
            "id, deleted_user_id, email, requested_at, resolved_at, "
            "resolved_by, outcome, failure_reason"
        )
        .order("resolved_at", desc=True)
        .execute()
    )
    return result.data or []


@router.post("/delete-requests/{request_id}/resolve")
async def resolve_delete_request(
    request_id: str,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only -- perform a real, reconciled account deletion.

    Per docs/audits/2026-08/b4_account_deletion_design_2026-08-28.md
    (approved 2026-08-28): this now actually deletes the account and its
    owned data via app.services.account_deletion.resolve_deletion_request(),
    rather than only flipping a status flag. A request may not become
    'resolved' while owned data or the Auth account still exist -- that
    module's own reconciliation step enforces this, not this route."""
    supabase = get_supabase()

    existing = (
        supabase.table("deletion_requests")
        .select("id, user_id, email, status, created_at")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")
    row = existing.data[0]
    if row["status"] not in ("pending", "failed"):
        raise HTTPException(
            status_code=400, detail="Request is not pending or retryable"
        )

    db = Db()
    try:
        try:
            audit_row = resolve_deletion_request(
                db,
                supabase,
                request_id=request_id,
                user_id=row["user_id"],
                email=row["email"],
                requested_at=datetime.fromisoformat(row["created_at"]),
                admin_id=admin_id,
            )
        except DeletionFailure as exc:
            # Failed strictly before the Auth API delete succeeded --
            # deletion_requests is guaranteed to still exist to record this
            # on directly (see DeletionFailure's own docstring).
            supabase.table("deletion_requests").update({
                "status": "failed",
                "failure_reason": str(exc),
            }).eq("id", request_id).execute()
            logger.error(
                "Deletion request failed before Auth delete: request_id=%s admin=%s error=%s",
                request_id, admin_id, exc,
            )
            raise HTTPException(status_code=500, detail="Deletion failed") from exc

        # The Auth API delete succeeded (or was already done) -- deletion_requests
        # has cascaded away by this point. Record the outcome in
        # deletion_audit_log regardless of whether it's 'resolved' or 'failed'
        # (reconciliation itself can still fail after this point).
        supabase.table("deletion_audit_log").insert(audit_row).execute()

        if audit_row["outcome"] != "resolved":
            logger.error(
                "Deletion request failed reconciliation after Auth delete: "
                "request_id=%s admin=%s reason=%s",
                request_id, admin_id, audit_row["failure_reason"],
            )
            raise HTTPException(status_code=500, detail="Deletion did not reconcile cleanly")
    finally:
        db.close()

    logger.info("Deletion request resolved: request_id=%s by admin=%s", request_id, admin_id)
    return {"success": True}
