from __future__ import annotations

import logging
import os
from typing import List, Optional

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Request

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_jwks_client = PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])

# Supabase Auth issues tokens with aud="authenticated" (platform-wide
# convention, not project-specific) and iss="{SUPABASE_URL}/auth/v1"
# (project-specific). Verified against a real generated token before adding
# this check -- both values confirmed exactly, 2026-07-02.
_EXPECTED_AUDIENCE = "authenticated"
_EXPECTED_ISSUER = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1"


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
            audience=_EXPECTED_AUDIENCE,
            issuer=_EXPECTED_ISSUER,
        )
        user_id = payload.get("sub")
        logger.info("[AUTH] JWT decoded successfully, user_id=%s", user_id)
        return user_id
    except Exception as e:
        logger.warning("[AUTH] JWT decode failed: %s: %s | token prefix: %s...", type(e).__name__, e, token[:20])
        return None


def get_user_role(user_id: str) -> str:
    """Return the role for user_id from user_roles, defaulting to 'user'."""
    db = get_supabase()
    result = db.table("user_roles").select("role").eq("user_id", user_id).limit(1).execute()
    if result.data:
        return result.data[0]["role"]
    return "user"


def require_user(request: Request) -> str:
    """FastAPI dependency: verify user is authenticated. No role check -- any
    logged-in user (role 'user', 'contributor', or 'admin') passes. Use this
    for endpoints that must exclude guests but don't need role restriction."""
    user_id = get_optional_user(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


class _RequireRole:
    """FastAPI dependency: verify user is authenticated and has one of the allowed roles.

    __call__ takes user_id via a nested Depends(get_optional_user) rather than
    a direct `request: Request` parameter. With this file's `from __future__
    import annotations`, FastAPI's dependency introspection fails to resolve
    a bound method's own `Request`-typed parameter (confirmed via an isolated
    repro: identical code as a plain function resolves correctly; as this
    class's __call__ it does not) -- every request 422s with "field required:
    query.request" before this dependency's own logic ever runs, so no
    admin/contributor-gated route was reachable at all. Routing through
    get_optional_user (a plain function, unaffected) sidesteps the bug
    entirely without changing behavior.
    """

    def __init__(self, allowed):
        # type: (List[str]) -> None
        self.allowed = allowed

    def __call__(self, user_id: Optional[str] = Depends(get_optional_user)) -> str:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        role = get_user_role(user_id)
        if role not in self.allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user_id


require_contributor = _RequireRole(["contributor", "admin"])
require_admin_role = _RequireRole(["admin"])
