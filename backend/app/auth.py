from __future__ import annotations

import logging
import os
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

_jwks_client = PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])


def get_optional_user(request: Request) -> Optional[str]:
    """Extract user_id from a Supabase JWT if present. Returns None if missing or invalid."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        logger.info("[AUTH] JWT decoded successfully, user_id=%s", user_id)
        return user_id
    except Exception as e:
        logger.warning("[AUTH] JWT decode failed: %s: %s | token prefix: %s...", type(e).__name__, e, token[:20])
        return None


ADMIN_EMAIL = "alxwhitley@gmail.com"


def require_admin(request: Request) -> str:
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
