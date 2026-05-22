from __future__ import annotations

import logging
import os
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_EMAIL = "alxwhitley@gmail.com"

_jwks_client = PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])


def _require_admin(request: Request) -> str:
    """Extract JWT, verify email is admin. Returns user_id or raises 403."""
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

    email = payload.get("email", "")
    if email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    return payload.get("sub", "")


@router.get("/sources")
async def list_sources(request: Request, user_id: str = Depends(_require_admin)):
    db = get_supabase()

    rows = db.table("source_toggles").select("*").order("created_at").execute()
    toggles = rows.data or []

    results = []
    for toggle in toggles:
        identifier = toggle["source_identifier"]
        id_type = toggle["identifier_type"]

        doc_count = None
        try:
            if id_type == "source_kind":
                count_result = (
                    db.table("documents")
                    .select("id", count="exact")
                    .eq("source_kind", identifier)
                    .execute()
                )
                doc_count = count_result.count
            elif id_type == "source_name":
                count_result = (
                    db.table("documents")
                    .select("id", count="exact")
                    .ilike("author", "%" + identifier + "%")
                    .execute()
                )
                doc_count = count_result.count
        except Exception:
            logger.warning("Failed to count docs for %s/%s", id_type, identifier)

        results.append({
            "id": toggle["id"],
            "source_identifier": identifier,
            "identifier_type": id_type,
            "label": toggle["label"],
            "enabled": toggle["enabled"],
            "doc_count": doc_count,
        })

    return {"sources": results}


@router.patch("/sources/{toggle_id}")
async def toggle_source(toggle_id: str, request: Request, user_id: str = Depends(_require_admin)):
    db = get_supabase()

    # Get current state
    current = db.table("source_toggles").select("*").eq("id", toggle_id).limit(1).execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Toggle not found")

    new_enabled = not current.data[0]["enabled"]
    result = (
        db.table("source_toggles")
        .update({"enabled": new_enabled})
        .eq("id", toggle_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to update toggle")

    # Invalidate cache
    from app.services.source_filter import _cache_ts
    import app.services.source_filter as sf
    sf._cache = None
    sf._cache_ts = 0.0

    return result.data[0]
