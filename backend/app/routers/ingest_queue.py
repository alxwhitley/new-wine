from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator, model_validator

from app.auth import require_admin_role
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_FORMATS = frozenset({"web_page", "pdf"})
_VALID_SCOPES = frozenset({"single", "collection"})
_VALID_MODES = frozenset({"declared", "per_item"})

RECENT_QUEUE_LIMIT = 50


def _extract_domain(url: str) -> str:
    """netloc, lowercased, 'www.' stripped -- the domain-memory key."""
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


# ── Request models ────────────────────────────────────────────────────────────

class QueueCreateBody(BaseModel):
    url: str
    source_format: str
    source_scope: str
    attribute_to: Optional[str] = None
    attribution_mode: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        # type: (str) -> str
        v = v.strip()
        if not v:
            raise ValueError("url must not be empty")
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("url must be a valid http(s) URL")
        return v

    @field_validator("source_format")
    @classmethod
    def validate_format(cls, v):
        # type: (str) -> str
        if v not in _VALID_FORMATS:
            raise ValueError(f"source_format must be one of: {sorted(_VALID_FORMATS)}")
        return v

    @field_validator("source_scope")
    @classmethod
    def validate_scope(cls, v):
        # type: (str) -> str
        if v not in _VALID_SCOPES:
            raise ValueError(f"source_scope must be one of: {sorted(_VALID_SCOPES)}")
        return v

    @field_validator("attribution_mode")
    @classmethod
    def validate_mode(cls, v):
        # type: (str) -> str
        if v not in _VALID_MODES:
            raise ValueError(f"attribution_mode must be one of: {sorted(_VALID_MODES)}")
        return v

    @model_validator(mode="after")
    def validate_attribution_present(self):
        # 'declared' requires a real name. 'per_item' never requires one --
        # but either a name or 'per_item' must be present; never neither.
        if self.attribution_mode == "declared" and not (self.attribute_to or "").strip():
            raise ValueError(
                "attribute_to is required when attribution_mode is 'declared' "
                "(or choose 'find per item')"
            )
        return self


class AssignBody(BaseModel):
    attribute_to: str

    @field_validator("attribute_to")
    @classmethod
    def validate_name(cls, v):
        # type: (str) -> str
        v = v.strip()
        if not v:
            raise ValueError("attribute_to must not be empty")
        return v


class DropBody(BaseModel):
    reason: Optional[str] = None


class ClearedToRunBody(BaseModel):
    cleared_to_run: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("")
async def create_queue_row(
    body: QueueCreateBody,
    user_id: str = Depends(require_admin_role),
):
    """Admin only -- submit a candidate source URL. Nothing fetches on submit;
    the row lands as status='waiting', cleared_to_run=false."""
    db = get_supabase()

    declared_name = body.attribute_to.strip() if (body.attribution_mode == "declared" and body.attribute_to) else None

    result = (
        db.table("source_ingest_queue")
        .insert({
            "url": body.url,
            "source_format": body.source_format,
            "source_scope": body.source_scope,
            "attribute_to": declared_name,
            "attribution_mode": body.attribution_mode,
            "submitted_by": user_id,
        })
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create queue row")

    # Domain memory: remember this domain's last attribution choice for prefill.
    # Upserted unconditionally (even for per_item, with attribute_to=None) so
    # the form can prefill the mode too, not just a name.
    domain = _extract_domain(body.url)
    if domain:
        db.table("source_ingest_domain_memory").upsert({
            "domain": domain,
            "attribute_to": declared_name,
            "attribution_mode": body.attribution_mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="domain").execute()

    logger.info("[INGEST-QUEUE] row created by admin=%s domain=%s", user_id, domain)
    return result.data[0]


@router.get("")
async def list_queue(
    user_id: str = Depends(require_admin_role),
    limit: int = Query(RECENT_QUEUE_LIMIT, ge=1, le=200),
):
    """Admin only -- needs-attention rows plus the recent queue, one round trip."""
    db = get_supabase()

    attention_result = (
        db.table("source_ingest_queue")
        .select("*")
        .eq("status", "needs_attention")
        .order("created_at", desc=False)
        .execute()
    )

    queue_result = (
        db.table("source_ingest_queue")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return {
        "needs_attention": attention_result.data or [],
        "queue": queue_result.data or [],
    }


@router.get("/domain-memory")
async def get_domain_memory(
    url: str = Query(...),
    user_id: str = Depends(require_admin_role),
):
    """Admin only -- prefill lookup for the submit form, keyed by URL domain."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=422, detail="url must be a valid http(s) URL")

    domain = _extract_domain(url)
    db = get_supabase()
    result = (
        db.table("source_ingest_domain_memory")
        .select("attribute_to, attribution_mode")
        .eq("domain", domain)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"found": False, "attribute_to": None, "attribution_mode": None}
    row = result.data[0]
    return {"found": True, "attribute_to": row.get("attribute_to"), "attribution_mode": row.get("attribution_mode")}


@router.post("/{row_id}/assign")
async def assign_attention_row(
    row_id: str,
    body: AssignBody,
    user_id: str = Depends(require_admin_role),
):
    """Admin only -- resolve a needs_attention row by naming an author. Returns
    the row to 'waiting' so a future ingestion run can pick it up."""
    db = get_supabase()

    existing = db.table("source_ingest_queue").select("id, status").eq("id", row_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Queue row not found")

    result = (
        db.table("source_ingest_queue")
        .update({
            "attribute_to": body.attribute_to,
            "status": "waiting",
            "flag_reason": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", row_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to assign attribution")

    logger.info("[INGEST-QUEUE] row %s assigned to %r by admin=%s", row_id, body.attribute_to, user_id)
    return result.data[0]


@router.post("/{row_id}/drop")
async def drop_attention_row(
    row_id: str,
    body: DropBody,
    user_id: str = Depends(require_admin_role),
):
    """Admin only -- drop a needs_attention (or any) row as failed."""
    db = get_supabase()

    existing = db.table("source_ingest_queue").select("id, flag_reason").eq("id", row_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Queue row not found")

    reason = (body.reason or existing.data[0].get("flag_reason") or "Dropped by admin").strip()

    result = (
        db.table("source_ingest_queue")
        .update({
            "status": "failed",
            "flag_reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", row_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to drop row")

    logger.info("[INGEST-QUEUE] row %s dropped by admin=%s (%s)", row_id, user_id, reason)
    return result.data[0]


@router.patch("/{row_id}/cleared-to-run")
async def toggle_cleared_to_run(
    row_id: str,
    body: ClearedToRunBody,
    user_id: str = Depends(require_admin_role),
):
    """Admin only -- arm/disarm a row for a future ingestion run to pick up."""
    db = get_supabase()

    existing = db.table("source_ingest_queue").select("id").eq("id", row_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Queue row not found")

    result = (
        db.table("source_ingest_queue")
        .update({
            "cleared_to_run": body.cleared_to_run,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", row_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update cleared_to_run")

    logger.info("[INGEST-QUEUE] row %s cleared_to_run -> %s by admin=%s", row_id, body.cleared_to_run, user_id)
    return result.data[0]
