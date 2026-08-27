#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/consent.py.
Uses a fake Supabase client -- no real database.

Run: python3.12 scripts/test_analytics_consent_service.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ANALYTICS_HMAC_SECRET_V1", "test-secret")

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


class _FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._filters = []
        self._payload = None
        self._mode = None

    def select(self, *_args, **_kwargs):
        self._mode = "select"
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = self.store.setdefault(self.name, {})
        if self._mode == "select":
            matches = [r for r in rows.values() if all(r.get(c) == v for c, v in self._filters)]
            from types import SimpleNamespace
            return SimpleNamespace(data=matches)
        if self._mode == "insert":
            key = self._payload["user_id"]
            rows[key] = dict(self._payload)
            from types import SimpleNamespace
            return SimpleNamespace(data=[rows[key]])
        if self._mode == "update":
            for k, r in list(rows.items()):
                if all(r.get(c) == v for c, v in self._filters):
                    r.update(self._payload)
            from types import SimpleNamespace
            return SimpleNamespace(data=[])
        if self._mode == "delete":
            for k in list(rows.keys()):
                r = rows[k]
                if all(r.get(c) == v for c, v in self._filters):
                    del rows[k]
            from types import SimpleNamespace
            return SimpleNamespace(data=[])
        raise AssertionError("no mode set")


class _FakeSupabase:
    def __init__(self):
        self._store = {}

    def table(self, name):
        return _FakeTable(self._store, name)


def main() -> int:
    from app.services.search_analytics import consent

    supabase = _FakeSupabase()
    user_id = "11111111-1111-1111-1111-111111111111"

    status = consent.get_consent_status(supabase, user_id)
    check("a user with no consent row needs acknowledgment", status["needs_acknowledgment"] is True)

    consent.acknowledge(supabase, user_id)
    status2 = consent.get_consent_status(supabase, user_id)
    check("after acknowledging, needs_acknowledgment is False", status2["needs_acknowledgment"] is False)
    check("policy_version matches the current version", status2["policy_version"] == consent.CURRENT_POLICY_VERSION)

    # Idempotent re-acknowledge: no error, no duplicate row.
    consent.acknowledge(supabase, user_id)
    status3 = consent.get_consent_status(supabase, user_id)
    check("re-acknowledging the same version is a no-op success", status3["needs_acknowledgment"] is False)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
