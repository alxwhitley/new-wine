#!/usr/bin/env python3
"""
test_teacher_card_metering.py -- regression tests proving GET
/study/teacher/{source_id} (backend/app/routers/study.py::get_teacher_card)
is metered against the same weekly allowance as /async-chat/submit, and
fails closed.

The metering call (enforce_query_limit, added 2026-08-19, commit
`f14c7e1c6c95213644cb997f7c308943d3f2bbb4` -- "fix: meter GET
/study/teacher/{source_id} -- unmetered-generation gap") already runs live
in production, confirmed by direct code reading: it is the FIRST
substantive line in get_teacher_card(), strictly before the
teacher_profiles lookup and every downstream step including the paid
Anthropic call. What was still missing, and what this file adds, is a
regression test that actually proves that structural claim rather than
just reading it off the source -- an over-limit or metering-failure case
must never reach the profile lookup, let alone generate.

Same fake-harness conventions as scripts/test_teacher_card_guards.py
(_FakeDB/_FakeQuery/_FakeRPCQuery/_Patch, restore-in-finally
monkeypatching of study's module attributes) -- no live DB / Anthropic /
OpenAI calls anywhere in this file.

Run: python3 scripts/test_teacher_card_metering.py
"""
import asyncio
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "dummy-openai-key")

from fastapi import HTTPException  # noqa: E402

from app.routers import study  # noqa: E402

failures = []


def _check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if not condition:
        failures.append(label)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeRPCQuery:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResult(self._data)


class _RaisingRPCQuery:
    def execute(self):
        raise RuntimeError("simulated Supabase outage")


class _FakeDB:
    """table() calls are tracked too -- proving get_teacher_card() never
    even reaches the teacher_profiles lookup (let alone generation) when
    metering denies or errors is the whole point of these tests."""

    def __init__(self, rpc_response=None, rpc_raises=False):
        self._rpc_response = rpc_response
        self._rpc_raises = rpc_raises
        self.rpc_calls = []
        self.table_calls = []

    def table(self, name):
        self.table_calls.append(name)
        return _FakeQuery([{"bio": "unreachable", "sources": {"name": "unreachable"}}])

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if self._rpc_raises:
            return _RaisingRPCQuery()
        return _FakeRPCQuery(self._rpc_response)


class _UnreachableAnthropicClient:
    """Any call at all is a test failure -- metering must block before this
    is ever touched."""

    class _UnreachableMessages:
        def create(self, **_kwargs):
            raise AssertionError("Anthropic was called despite metering denial")

    def __init__(self):
        self.messages = self._UnreachableMessages()


class _Patch:
    def __init__(self, obj, name, value):
        self._obj = obj
        self._name = name
        self._value = value
        self._had = hasattr(obj, name)
        self._orig = getattr(obj, name, None)

    def __enter__(self):
        setattr(self._obj, self._name, self._value)
        return self

    def __exit__(self, *_exc):
        if self._had:
            setattr(self._obj, self._name, self._orig)
        else:
            delattr(self._obj, self._name)


def test_over_limit_user_never_reaches_profile_lookup_or_generation():
    print("\n" + "=" * 78)
    print("Over-limit authenticated user: metering denies, nothing downstream runs")
    print("=" * 78)

    db = _FakeDB(rpc_response=[{
        "query_count": 50, "weekly_limit": 50, "week_start": "2026-08-24", "allowed": False,
    }])
    client = _UnreachableAnthropicClient()

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client):
        raised = None
        try:
            asyncio.run(study.get_teacher_card("src-derek", "What does grace mean?", user_id="over-limit-user"))
        except HTTPException as exc:
            raised = exc

    _check("HTTPException was raised", raised is not None)
    _check("status is 429 (weekly_limit_reached)", raised is not None and raised.status_code == 429)
    _check(
        "detail identifies the weekly limit, matching /async-chat/submit's shape",
        raised is not None
        and isinstance(raised.detail, dict)
        and raised.detail.get("error") == "weekly_limit_reached",
    )
    _check("increment_user_query was called exactly once", db.rpc_calls == [
        ("increment_user_query", {"p_user_id": "over-limit-user"}),
    ])
    _check(
        "no table lookup (teacher_profiles or otherwise) was ever reached",
        db.table_calls == [],
    )


def test_metering_rpc_failure_fails_closed():
    print("\n" + "=" * 78)
    print("Metering RPC itself errors (a Supabase blip): fails closed, not open")
    print("=" * 78)

    db = _FakeDB(rpc_raises=True)
    client = _UnreachableAnthropicClient()

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client):
        raised = None
        try:
            asyncio.run(study.get_teacher_card("src-derek", "What does grace mean?", user_id="some-user"))
        except HTTPException as exc:
            raised = exc

    _check("HTTPException was raised rather than silently proceeding", raised is not None)
    _check(
        "status is 503 (metering_unavailable) -- fails closed, never open",
        raised is not None and raised.status_code == 503,
    )
    _check(
        "detail is the stable metering_unavailable shape the frontend already handles",
        raised is not None and raised.detail == "metering_unavailable",
    )
    _check("no table lookup was ever reached", db.table_calls == [])


def test_allowed_user_passes_metering_and_reaches_profile_lookup():
    print("\n" + "=" * 78)
    print("Sanity check: an allowed user clears metering and continues past it")
    print("=" * 78)

    db = _FakeDB(rpc_response=[{
        "query_count": 3, "weekly_limit": 50, "week_start": "2026-08-24", "allowed": True,
    }])

    with _Patch(study, "get_supabase", lambda: db):
        try:
            asyncio.run(study.get_teacher_card("src-derek", "What does grace mean?", user_id="normal-user"))
        except HTTPException:
            pass  # Expected -- teacher_profiles is empty in this fake, so it 404s downstream.
        except Exception:
            pass

    _check(
        "metering allowed the request through to the profile lookup",
        "teacher_profiles" in db.table_calls,
    )


def main() -> int:
    test_over_limit_user_never_reaches_profile_lookup_or_generation()
    test_metering_rpc_failure_fails_closed()
    test_allowed_user_passes_metering_and_reaches_profile_lookup()

    print("\n" + "=" * 78)
    if failures:
        print("FAILED (%d):" % len(failures))
        for f in failures:
            print("  -", f)
        return 1
    print("All teacher-card metering checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
