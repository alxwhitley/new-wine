#!/usr/bin/env python3
"""HTTP-level authorization wiring proof for the search-analytics routers.

Unlike test_analytics_consent_api.py / test_admin_analytics_api.py (which
call route FUNCTIONS directly with an explicit user_id/admin_id kwarg,
bypassing FastAPI's dependency injection entirely -- useful for testing
route LOGIC, but blind to whether Depends(require_user)/
Depends(require_admin_role) is actually still declared on the route),
this test mounts the real routers on a real FastAPI app and issues real
HTTP requests via TestClient with NO token -- proving the auth dependency
is genuinely wired, not just present in the function signature. Same
pattern and same caveat as scripts/test_admin_auth_regression.py's
no-token checks: get_optional_user returns None with no live Supabase
call, so this covers the 401 (no dependency reached, or dependency
correctly rejects) path, not the 403 (wrong role) path.

Run: python3.12 scripts/test_analytics_auth_wiring.py
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers import analytics, admin_analytics  # noqa: E402


class ConsentAuthWiringTest(unittest.TestCase):
    """/analytics/consent requires ANY authenticated user (require_user) --
    a no-token request must 401, never silently succeed or 422."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(analytics.router, prefix="/analytics")
        self.client = TestClient(app)

    def test_get_consent_with_no_token_is_401(self) -> None:
        response = self.client.get("/analytics/consent")
        self.assertEqual(401, response.status_code)
        self.assertEqual("Authentication required", response.json().get("detail"))

    def test_put_consent_with_no_token_is_401(self) -> None:
        response = self.client.put("/analytics/consent")
        self.assertEqual(401, response.status_code)

    def test_delete_consent_with_no_token_is_401(self) -> None:
        response = self.client.delete("/analytics/consent")
        self.assertEqual(401, response.status_code)


class AdminAnalyticsAuthWiringTest(unittest.TestCase):
    """Every /admin/analytics/* route requires require_admin_role -- a
    no-token request must 401 (get_optional_user returns None before
    get_user_role is ever called), never silently succeed or 422."""

    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(admin_analytics.router, prefix="/admin/analytics")
        self.client = TestClient(app)

    def test_summary_with_no_token_is_401(self) -> None:
        response = self.client.get("/admin/analytics/summary")
        self.assertEqual(401, response.status_code)
        self.assertEqual("Authentication required", response.json().get("detail"))

    def test_topic_gaps_with_no_token_is_401(self) -> None:
        response = self.client.get("/admin/analytics/topics/Deliverance%20Ministry/gaps")
        self.assertEqual(401, response.status_code)

    def test_create_retest_with_no_token_is_401(self) -> None:
        response = self.client.post("/admin/analytics/gaps/gap-1/retests")
        self.assertEqual(401, response.status_code)

    def test_resolve_gap_with_no_token_is_401(self) -> None:
        response = self.client.patch("/admin/analytics/gaps/gap-1")
        self.assertEqual(401, response.status_code)

    def test_no_admin_route_ever_422s_on_no_token(self) -> None:
        """Same class of bug test_admin_auth_regression.py's
        test_require_role_signature_excludes_request_param guards against
        structurally -- a 422 here would mean FastAPI's dependency
        injection failed to resolve BEFORE the auth check ever ran,
        letting an unauthenticated request past the intended 401."""
        for method, path in (
            ("GET", "/admin/analytics/summary"),
            ("GET", "/admin/analytics/topics/Deliverance%20Ministry/gaps"),
            ("POST", "/admin/analytics/gaps/gap-1/retests"),
            ("PATCH", "/admin/analytics/gaps/gap-1"),
        ):
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path)
                self.assertNotEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
