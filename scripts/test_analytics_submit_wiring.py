#!/usr/bin/env python3
"""Wiring test for async_chat.py's /submit occurrence creation. Patches
every external call (Supabase, Db, enqueue, consent, occurrence creation)
so this exercises only the NEW wiring, not the whole answer path -- no
network, no database.

Run: python3.12 scripts/test_analytics_submit_wiring.py
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
from app.routers import async_chat  # noqa: E402
from app.services.search_analytics import consent as consent_module  # noqa: E402
from app.services.search_analytics import occurrences as occurrences_module  # noqa: E402

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


class _FakeRequest:
    def __init__(self):
        self.headers = {}
        self.client = None


class _NoopDb:
    def close(self):
        pass


def _run_submit(req, user_id, consent_status, occurrence_side_effect=None):
    calls = {"create_occurrence": []}

    def fake_create_occurrence(db, **kwargs):
        calls["create_occurrence"].append(kwargs)
        if occurrence_side_effect:
            raise occurrence_side_effect
        return "occ-1"

    with patch.object(async_chat, "_serving_enabled", return_value=True), \
         patch.object(async_chat, "get_supabase", return_value=object()), \
         patch.object(async_chat, "enforce_query_limit", return_value={}), \
         patch.object(async_chat, "current_policy", return_value={"evidence_version": "e1", "prompt_version": "p1", "policy_version": "policy_v3", "filters": {}}), \
         patch.object(async_chat, "load_config", return_value=None), \
         patch.object(async_chat, "Db", return_value=_NoopDb()), \
         patch.object(async_chat.jobs, "enqueue", return_value={"reason": "new", "job": {"id": "job-1", "status": "queued", "outcome": None}}), \
         patch.object(consent_module, "get_consent_status", return_value=consent_status), \
         patch.object(consent_module, "get_or_rotate_subject_key", return_value={"subject_key": "fake-subject-key", "subject_key_version": 1}), \
         patch.object(async_chat, "create_occurrence", side_effect=fake_create_occurrence):
        result = asyncio.run(async_chat.submit(req, _FakeRequest(), user_id=user_id))
    return result, calls


def main() -> int:
    req_no_submission_id = async_chat.AsyncChatRequest(question="What is deliverance?")
    check("submission_id is optional and defaults to None", req_no_submission_id.submission_id is None)

    req_with_id = async_chat.AsyncChatRequest(question="What is deliverance?", submission_id="client-uuid-1")
    check("submission_id is accepted when supplied", req_with_id.submission_id == "client-uuid-1")

    consented = {"acknowledged": True, "needs_acknowledgment": False, "policy_version": "v1", "current_policy_version": "v1"}
    _, calls = _run_submit(req_with_id, "user-1", consented)
    check("a consented authenticated submission creates exactly one occurrence", len(calls["create_occurrence"]) == 1)
    check("origin is always 'user' for the public submit route, never client-controlled",
          calls["create_occurrence"][0]["origin"] == "user")

    not_consented = {"acknowledged": False, "needs_acknowledgment": True, "policy_version": None, "current_policy_version": "v1"}
    _, calls2 = _run_submit(req_with_id, "user-2", not_consented)
    check("a non-consented authenticated submission creates NO occurrence (no error either)",
          len(calls2["create_occurrence"]) == 0)

    _, calls3 = _run_submit(req_with_id, None, consented)
    check("a guest submission (no user_id) creates NO occurrence", len(calls3["create_occurrence"]) == 0)

    raised_503 = False
    try:
        _run_submit(req_with_id, "user-1", consented, occurrence_side_effect=occurrences_module.OccurrenceWriteFailedError("boom"))
    except Exception as exc:
        from fastapi import HTTPException
        raised_503 = isinstance(exc, HTTPException) and exc.status_code == 503
    check("a durable-write failure for a consented user surfaces as a retryable 503, not a silent accept",
          raised_503)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
