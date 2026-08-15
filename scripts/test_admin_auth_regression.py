#!/usr/bin/env python3
"""Regression proof for the da27fe4 admin-auth failure mode.

Before da27fe4, `_RequireRole.__call__` (backend/app/auth.py) took a direct
`request: Request` parameter. Under a `from __future__ import annotations`
file, FastAPI's dependency introspection failed to resolve that bound
method's own `Request`-typed parameter for a specific pydantic version --
every request to an admin/contributor-gated route 422'd with "field
required: query.request" before `_RequireRole.__call__`'s own logic (the
401/403 auth check) ever ran. The fix routes user_id in via a nested
`Depends(get_optional_user)` instead.

IMPORTANT, verified 2026-08-15 (independent reproduction against the real
pre-fix source, `git show da27fe4^:backend/app/auth.py`, dropped into
`app.routers.admin` and run in this same pinned venv -- pydantic 2.13.4 /
starlette 0.52.1 / fastapi 0.128.8 / Python 3.12.13): the historical 422
failure mode does NOT reproduce on this newly-pinned stack. Both the
pre-fix and current shapes return 401 for a no-token request. This means
the HTTP-level checks below (`test_no_token_returns_401_not_422` and
`test_no_token_never_422s_across_multiple_admin_routes`) CANNOT by
themselves distinguish the buggy shape from the fixed one on this stack --
they still pass identically if the code were reverted to the pre-fix
shape. They remain in this file as a legitimate smoke test that the admin
routes are reachable and correctly gated (a real, useful thing to know),
but they are NOT proof the da27fe4 shape is fenced. Do not read their
presence, or their passing, as guarding against reintroducing the bug.

The actual durable guard against reintroducing the da27fe4 shape is
`test_require_role_signature_excludes_request_param` below, a structural
check on `_RequireRole.__call__`'s own `inspect.signature()`: the buggy
shape takes a `request` parameter; the fixed shape does not (it takes
`user_id` via `Depends(get_optional_user)` instead). This distinguishes
the two shapes unconditionally, regardless of which pydantic/starlette/
fastapi versions happen to be pinned at the time it runs -- unlike the
HTTP-level checks, which the independent reproduction above proved are
version-dependent and, on the CURRENT pin set, blind to this exact bug.

Per CLAUDE.md's auth.py docstring: the no-token HTTP path raises 401 out of
`get_optional_user` returning None -- it never calls `get_user_role()` and
never touches Supabase. Reaching 403 (wrong role) DOES require a live
`get_user_role()` Supabase call, so that branch is deliberately NOT
exercised here -- this script only covers the zero-DB-dependency 401 path,
which is the one that reproduces da27fe4's HTTP-level symptom with no live
credentials needed.

Dummy SUPABASE_JWT_JWKS_URL / SUPABASE_URL values are set (via setdefault,
so a real backend/app/.env is respected if present) purely to satisfy
app.auth's module-level `os.environ[...]` reads at import time --
`jwt.PyJWKClient.__init__` does not make a network call at construction
(only `get_signing_key_from_jwt` does, which this test never reaches), so
these values never need to resolve to anything real.

Standalone script, not pytest -- this repo's scripts/test_*.py convention
(see scripts/test_async_serving_gate.py).
"""
from __future__ import annotations

import inspect
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

from app.auth import _RequireRole  # noqa: E402
from app.routers import admin  # noqa: E402


class AdminAuthRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(admin.router, prefix="/admin")
        self.client = TestClient(app)

    def test_require_role_signature_excludes_request_param(self) -> None:
        """THE durable regression guard for da27fe4.

        The pre-fix `_RequireRole.__call__(self, request: Request)` and the
        fixed `_RequireRole.__call__(self, user_id: Optional[str] =
        Depends(get_optional_user))` are distinguished by this one
        structural fact regardless of pydantic/starlette/fastapi version:
        the buggy shape has a `request` parameter, the fixed shape does
        not. Independently verified 2026-08-15 by loading the real
        `git show da27fe4^:backend/app/auth.py` source and confirming this
        exact assertion fails against it ('request' in parameters == True)
        while passing against the current tracked file ('request' in
        parameters == False) -- on the identical pinned dependency stack
        this whole script runs under.
        """
        sig = inspect.signature(_RequireRole.__call__)
        self.assertNotIn(
            "request",
            sig.parameters,
            "_RequireRole.__call__ has reverted to taking a direct "
            "`request` parameter -- this is the exact da27fe4 shape. "
            "Route it through Depends(get_optional_user) instead.",
        )

    def test_no_token_returns_401_not_422(self) -> None:
        """Smoke test only -- NOT proof of the da27fe4 shape being fenced.

        Verified 2026-08-15: on the currently-pinned stack (pydantic
        2.13.4 / starlette 0.52.1 / fastapi 0.128.8 / Python 3.12.13), the
        real pre-fix `_RequireRole.__call__(self, request: Request)` shape
        ALSO returns 401 here, not 422 -- the historical 422 failure mode
        does not reproduce on this stack at all, so this assertion passes
        identically whether the fix is present or reverted. It still
        confirms something real and worth checking (the admin route is
        reachable and correctly rejects a no-token request with 401), just
        not the thing its old docstring used to claim. See
        test_require_role_signature_excludes_request_param above for the
        actual da27fe4 regression guard.
        """
        response = self.client.get("/admin/sources")

        self.assertEqual(401, response.status_code)
        self.assertEqual("Authentication required", response.json().get("detail"))

    def test_no_token_never_422s_across_multiple_admin_routes(self) -> None:
        """Smoke test only, same caveat as above -- exercises a second,
        independently-defined admin route (a different function object,
        same require_admin_role dependency) to rule out a single-route
        fluke in the reachability/gating check, not the da27fe4 shape."""
        response = self.client.get("/admin/stats")
        self.assertEqual(401, response.status_code)
        self.assertNotEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
