#!/usr/bin/env python3
"""Router-level tests for /analytics/consent. Calls the route functions
directly (FastAPI dependency injection bypassed by calling with explicit
kwargs, same pattern as scripts/test_quote_selection_gate.py's direct SSE
generator test) -- no live server, no real database.

Run: python3.12 scripts/test_analytics_consent_api.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("ANALYTICS_HMAC_SECRET_V1", "test-secret")

import asyncio  # noqa: E402
from app.routers import analytics  # noqa: E402
from app.services.search_analytics import consent as consent_module  # noqa: E402

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if condition else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if condition:
        _pass += 1
    else:
        _fail += 1


def main() -> int:
    with patch.object(analytics, "get_supabase", return_value=object()), \
         patch.object(consent_module, "get_consent_status", return_value={
             "acknowledged": False, "needs_acknowledgment": True,
             "policy_version": None, "current_policy_version": "v1", "policy_copy": "copy text",
         }):
        status = asyncio.run(analytics.get_consent_status_route(user_id="user-1"))
        check("GET returns needs_acknowledgment=True for a new user", status["needs_acknowledgment"] is True)
        check("GET response includes the policy copy for the frontend to render", "policy_copy" in status)
        check("GET response never includes a subject_key or any hashed identity", "subject_key" not in status)

    with patch.object(analytics, "get_supabase", return_value=object()), \
         patch.object(consent_module, "acknowledge") as mock_ack:
        result = asyncio.run(analytics.acknowledge_consent_route(user_id="user-1"))
        check("PUT calls acknowledge() exactly once", mock_ack.call_count == 1)
        check("PUT returns a success shape", result.get("success") is True)

    with patch.object(analytics, "get_supabase", return_value=object()), \
         patch.object(analytics, "Db") as mock_db_cls, \
         patch.object(consent_module, "withdraw") as mock_withdraw:
        result = asyncio.run(analytics.withdraw_consent_route(user_id="user-1"))
        check("DELETE calls withdraw() exactly once", mock_withdraw.call_count == 1)
        check("DELETE returns a success shape", result.get("success") is True)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
