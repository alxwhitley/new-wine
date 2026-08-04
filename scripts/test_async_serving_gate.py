#!/usr/bin/env python3
"""Regression proof for the async submit traffic gate (no DB/network writes)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import get_optional_user  # noqa: E402
from app.routers import async_chat  # noqa: E402


class _FakeDb:
    def close(self) -> None:
        pass


class AsyncServingGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_db = async_chat.Db
        self.original_load_config = async_chat.load_config
        self.original_get_supabase = async_chat.get_supabase

        app = FastAPI()
        app.include_router(async_chat.router, prefix="/async-chat")

        def _fake_user(request: Request):
            return request.headers.get("x-test-user")

        app.dependency_overrides[get_optional_user] = _fake_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        async_chat.Db = self.original_db
        async_chat.load_config = self.original_load_config
        async_chat.get_supabase = self.original_get_supabase

    def test_submit_fails_closed_before_metering_when_serving_is_disabled(self) -> None:
        async_chat.Db = _FakeDb
        async_chat.load_config = lambda db: SimpleNamespace(serving_enabled=False)

        metering_boundary_crossed = []

        def _unexpected_supabase():
            metering_boundary_crossed.append(True)
            raise AssertionError("disabled submit reached metering")

        async_chat.get_supabase = _unexpected_supabase

        response = self.client.post(
            "/async-chat/submit",
            json={"question": "Should remain on the live path", "anon_id": "gate-test"},
        )

        self.assertEqual(503, response.status_code)
        self.assertEqual("async_serving_disabled", response.json().get("detail"))
        self.assertEqual([], metering_boundary_crossed)


if __name__ == "__main__":
    unittest.main()
