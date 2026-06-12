from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.auth import get_optional_user
from app.constants import TAXONOMY_LIST, VALID_TAGS
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

GROQ_MODEL = "llama-3.3-70b-versatile"
TAGGING_TIMEOUT = 5  # seconds; non-fatal if exceeded

_TAGGING_PROMPT = (
    "Based on this short pastoral note, assign 3-5 topic tags from the taxonomy below.\n\n"
    "RULES:\n"
    "- Only assign a tag if the note directly addresses that topic\n"
    "- Copy tag names exactly — do not create new tags\n"
    "- Return JSON only: {\"topic_tags\": [\"tag1\", \"tag2\", ...]}\n\n"
    "TAXONOMY (use ONLY these exact tags):\n" + TAXONOMY_LIST
)


# ── Role helpers ──────────────────────────────────────────────────────────────

def get_user_role(user_id):
    # type: (str) -> str
    """Return the role for user_id from user_roles, defaulting to 'user'."""
    db = get_supabase()
    result = db.table("user_roles").select("role").eq("user_id", user_id).limit(1).execute()
    if result.data:
        return result.data[0]["role"]
    return "user"


class _RequireRole:
    """FastAPI dependency: verify user is authenticated and has one of the allowed roles."""

    def __init__(self, allowed):
        # type: (List[str]) -> None
        self.allowed = allowed

    def __call__(self, request):
        # type: (Request) -> str
        user_id = get_optional_user(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        role = get_user_role(user_id)
        if role not in self.allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user_id


require_contributor = _RequireRole(["contributor", "admin"])
require_admin_role = _RequireRole(["admin"])


def _get_current_user(request):
    # type: (Request) -> str
    """Require any authenticated user. Returns user_id or raises 401."""
    user_id = get_optional_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ── Tagging ───────────────────────────────────────────────────────────────────

def _parse_tag_json(raw):
    # type: (str) -> List[str]
    """Parse topic_tags list from Groq JSON response."""
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    text = fence.group(1).strip() if fence else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        obj = re.search(r"\{[\s\S]*?\}", text)
        if not obj:
            return []
        try:
            data = json.loads(obj.group())
        except json.JSONDecodeError:
            return []
    tags = data.get("topic_tags", [])
    if not isinstance(tags, list):
        return []
    return [t for t in tags if isinstance(t, str) and t in VALID_TAGS]


def _tag_content(content):
    # type: (str) -> List[str]
    """
    Call Groq to assign 3-5 tags from the taxonomy. 5s timeout.
    Returns empty list on any failure — caller saves card anyway.
    """
    try:
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=256,
            timeout=TAGGING_TIMEOUT,
            messages=[
                {"role": "system", "content": _TAGGING_PROMPT},
                {"role": "user", "content": content},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        tags = _parse_tag_json(raw)
        if len(tags) < 3:
            logger.warning("Tagging returned only %d valid tags; saving with what we have", len(tags))
        return tags
    except Exception:
        logger.warning("Tagging failed (non-fatal) — saving card with empty topic_tags")
        return []


# ── Request / response models ─────────────────────────────────────────────────

class CardCreateBody(BaseModel):
    verse_id: str
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        # type: (str) -> str
        v = v.strip()
        if len(v) < 50 or len(v) > 2000:
            raise ValueError("content must be between 50 and 2000 characters")
        return v

    @field_validator("verse_id")
    @classmethod
    def validate_verse_id(cls, v):
        # type: (str) -> str
        v = v.strip()
        if not v:
            raise ValueError("verse_id must not be empty")
        return v


class CardUpdateBody(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        # type: (str) -> str
        v = v.strip()
        if len(v) < 50 or len(v) > 2000:
            raise ValueError("content must be between 50 and 2000 characters")
        return v


class RequestCreateBody(BaseModel):
    message: Optional[str] = None


class RevokeBody(BaseModel):
    remove_cards: bool = False


class MeUpdateBody(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v):
        # type: (str) -> str
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be empty")
        if len(v) > 100:
            raise ValueError("display_name must be at most 100 characters")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/cards")
async def list_cards(verse_id: str):
    """Public — returns all published cards for a verse with contributor display_name."""
    db = get_supabase()
    cards_result = (
        db.table("pastors_cards")
        .select("id, verse_id, content, topic_tags, created_at, updated_at, user_id")
        .eq("verse_id", verse_id)
        .eq("status", "published")
        .execute()
    )
    cards = cards_result.data or []

    if not cards:
        return []

    # Batch-fetch display names for all unique user_ids
    user_ids = list({c["user_id"] for c in cards})
    roles_result = (
        db.table("user_roles")
        .select("user_id, display_name")
        .in_("user_id", user_ids)
        .execute()
    )
    display_map = {
        r["user_id"]: r.get("display_name")
        for r in (roles_result.data or [])
    }  # type: Dict[str, Optional[str]]

    return [
        {
            "id": c["id"],
            "verse_id": c["verse_id"],
            "content": c["content"],
            "topic_tags": c.get("topic_tags") or [],
            "display_name": display_map.get(c["user_id"]),
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "user_id": c["user_id"],
        }
        for c in cards
    ]


@router.post("/cards")
async def create_card(
    body: CardCreateBody,
    user_id: str = Depends(require_contributor),
):
    """Contributor or admin — create a published card for a verse."""
    db = get_supabase()
    topic_tags = _tag_content(body.content)

    result = (
        db.table("pastors_cards")
        .insert({
            "user_id": user_id,
            "verse_id": body.verse_id,
            "content": body.content,
            "topic_tags": topic_tags,
            "status": "published",
        })
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create card")
    return result.data[0]


@router.patch("/cards/{card_id}")
async def update_card(
    card_id: str,
    body: CardUpdateBody,
    user_id: str = Depends(require_contributor),
):
    """Contributor can edit own cards; admin can edit any card."""
    db = get_supabase()
    role = get_user_role(user_id)

    existing = (
        db.table("pastors_cards")
        .select("id, user_id, status")
        .eq("id", card_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Card not found")
    card = existing.data[0]

    if role != "admin" and card["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Cannot edit another contributor's card")

    topic_tags = _tag_content(body.content)

    result = (
        db.table("pastors_cards")
        .update({
            "content": body.content,
            "topic_tags": topic_tags,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", card_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update card")
    return result.data[0]


@router.delete("/cards/{card_id}")
async def remove_card(
    card_id: str,
    user_id: str = Depends(require_admin_role),
):
    """Admin only — soft-delete by setting status='removed'."""
    db = get_supabase()
    result = (
        db.table("pastors_cards")
        .update({"status": "removed"})
        .eq("id", card_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Card not found")
    return {"success": True}


@router.get("/requests")
async def list_requests(user_id: str = Depends(require_admin_role)):
    """Admin only — list all pending contributor requests with requester email."""
    db = get_supabase()

    requests_result = (
        db.table("contributor_requests")
        .select("id, user_id, message, created_at")
        .eq("status", "pending")
        .execute()
    )
    requests = requests_result.data or []

    if not requests:
        return []

    # Batch-fetch emails from auth.users via RPC or direct select
    # Supabase service role can query auth.users through the admin API
    user_ids = list({r["user_id"] for r in requests})
    try:
        from app.db.supabase import get_supabase
        # Use a raw RPC to fetch emails from auth schema
        emails_result = db.rpc(
            "get_user_emails",
            {"user_ids": user_ids},
        ).execute()
        email_map = {
            row["id"]: row["email"]
            for row in (emails_result.data or [])
        }  # type: Dict[str, str]
    except Exception:
        logger.warning("Could not fetch emails via RPC — falling back to empty email map")
        email_map = {}

    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "email": email_map.get(r["user_id"], ""),
            "message": r.get("message"),
            "created_at": r["created_at"],
        }
        for r in requests
    ]


@router.post("/requests")
async def submit_request(
    body: RequestCreateBody,
    user_id: str = Depends(_get_current_user),
):
    """Any authenticated user — submit a contributor request."""
    db = get_supabase()

    # Check for an existing pending request
    existing = (
        db.table("contributor_requests")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending contributor request",
        )

    db.table("contributor_requests").insert({
        "user_id": user_id,
        "message": body.message,
        "status": "pending",
    }).execute()

    return {"success": True}


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only — approve a pending contributor request."""
    db = get_supabase()

    req = (
        db.table("contributor_requests")
        .select("id, user_id, status")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")

    applicant_id = req.data[0]["user_id"]
    now = datetime.now(timezone.utc).isoformat()

    db.table("contributor_requests").update({
        "status": "approved",
        "reviewed_at": now,
        "reviewed_by": admin_id,
    }).eq("id", request_id).execute()

    # Upsert role — grant contributor (admin retains admin if already set)
    existing_role = (
        db.table("user_roles")
        .select("role")
        .eq("user_id", applicant_id)
        .limit(1)
        .execute()
    )
    if existing_role.data and existing_role.data[0]["role"] == "admin":
        pass  # don't downgrade an admin
    elif existing_role.data:
        db.table("user_roles").update({
            "role": "contributor",
            "granted_by": admin_id,
        }).eq("user_id", applicant_id).execute()
    else:
        db.table("user_roles").insert({
            "user_id": applicant_id,
            "role": "contributor",
            "granted_by": admin_id,
        }).execute()

    logger.info("Contributor approved: user_id=%s by admin=%s", applicant_id, admin_id)
    return {"success": True}


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: str,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only — reject a pending contributor request."""
    db = get_supabase()

    req = (
        db.table("contributor_requests")
        .select("id, status")
        .eq("id", request_id)
        .limit(1)
        .execute()
    )
    if not req.data:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.data[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request is not pending")

    now = datetime.now(timezone.utc).isoformat()
    db.table("contributor_requests").update({
        "status": "rejected",
        "reviewed_at": now,
        "reviewed_by": admin_id,
    }).eq("id", request_id).execute()

    logger.info("Contributor request rejected: %s by admin=%s", request_id, admin_id)
    return {"success": True}


@router.get("/contributors")
async def list_contributors(admin_id: str = Depends(require_admin_role)):
    """Admin only — list all contributors with email and published card count."""
    db = get_supabase()

    roles_result = (
        db.table("user_roles")
        .select("user_id, display_name, created_at")
        .eq("role", "contributor")
        .execute()
    )
    contributors = roles_result.data or []

    if not contributors:
        return []

    user_ids = [c["user_id"] for c in contributors]

    try:
        emails_result = db.rpc("get_user_emails", {"user_ids": user_ids}).execute()
        email_map = {
            row["id"]: row["email"]
            for row in (emails_result.data or [])
        }  # type: Dict[str, str]
    except Exception:
        logger.warning("Could not fetch contributor emails via RPC")
        email_map = {}

    # Count published cards per contributor in one query
    cards_result = (
        db.table("pastors_cards")
        .select("user_id")
        .in_("user_id", user_ids)
        .eq("status", "published")
        .execute()
    )
    card_counts = {}  # type: Dict[str, int]
    for card in (cards_result.data or []):
        uid = card["user_id"]
        card_counts[uid] = card_counts.get(uid, 0) + 1

    return [
        {
            "user_id": c["user_id"],
            "display_name": c.get("display_name"),
            "email": email_map.get(c["user_id"], ""),
            "card_count": card_counts.get(c["user_id"], 0),
            "created_at": c["created_at"],
        }
        for c in contributors
    ]


@router.get("/me")
async def get_me(user_id: str = Depends(_get_current_user)):
    """Authenticated user — return own role and display_name."""
    db = get_supabase()
    result = (
        db.table("user_roles")
        .select("role, display_name")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return {
            "role": result.data[0]["role"],
            "display_name": result.data[0].get("display_name"),
        }
    return {"role": "user", "display_name": None}


@router.patch("/me")
async def update_me(
    body: MeUpdateBody,
    user_id: str = Depends(_get_current_user),
):
    """Authenticated user — upsert own display_name in user_roles."""
    db = get_supabase()
    existing = (
        db.table("user_roles")
        .select("role")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        db.table("user_roles").update({
            "display_name": body.display_name,
        }).eq("user_id", user_id).execute()
    else:
        db.table("user_roles").insert({
            "user_id": user_id,
            "role": "user",
            "display_name": body.display_name,
        }).execute()
    return {"success": True}


@router.post("/contributors/{target_user_id}/revoke")
async def revoke_contributor(
    target_user_id: str,
    body: RevokeBody,
    admin_id: str = Depends(require_admin_role),
):
    """Admin only — revoke contributor role; optionally soft-delete their cards."""
    db = get_supabase()

    role_row = (
        db.table("user_roles")
        .select("role")
        .eq("user_id", target_user_id)
        .limit(1)
        .execute()
    )
    if not role_row.data:
        raise HTTPException(status_code=404, detail="User role record not found")
    if role_row.data[0]["role"] == "admin":
        raise HTTPException(status_code=400, detail="Cannot revoke an admin's role via this endpoint")

    db.table("user_roles").update({
        "role": "user",
        "granted_by": admin_id,
    }).eq("user_id", target_user_id).execute()

    # Mark the most-recent approved request as revoked
    db.table("contributor_requests").update({
        "status": "revoked",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": admin_id,
    }).eq("user_id", target_user_id).eq("status", "approved").execute()

    if body.remove_cards:
        db.table("pastors_cards").update({
            "status": "removed",
        }).eq("user_id", target_user_id).eq("status", "published").execute()
        logger.info("Cards soft-deleted for revoked contributor user_id=%s", target_user_id)

    logger.info("Contributor revoked: user_id=%s by admin=%s", target_user_id, admin_id)
    return {"success": True}
