#!/usr/bin/env python3
"""Unit tests for backend/app/services/account_deletion.py. Uses fake
Db/cursor/connection and supabase objects -- no real database, no network
call to the Supabase Admin API.

Run: python3.12 scripts/test_account_deletion.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

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


# ── Fake raw-SQL layer (Db/connection/cursor) ────────────────────────────

class _FakeCursor:
    """Pattern-matches account_deletion.py's exact query shapes against an
    in-memory row-count table -- not a SQL engine."""

    def __init__(self, remaining_counts, updates_seen):
        self._remaining_counts = remaining_counts  # dict[table] -> int
        self._updates_seen = updates_seen  # list[(table, column, value)]
        self._last_result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        q = " ".join(query.split())
        if q.startswith("UPDATE user_roles SET granted_by = NULL"):
            self._updates_seen.append(("user_roles", "granted_by", params[0]))
        elif q.startswith("UPDATE contributor_requests SET reviewed_by = NULL"):
            self._updates_seen.append(("contributor_requests", "reviewed_by", params[0]))
        elif q.startswith("UPDATE quote_verification_log SET submitted_by = NULL"):
            self._updates_seen.append(("quote_verification_log", "submitted_by", params[0]))
        elif q.startswith("SELECT count(*) AS n FROM search_occurrences WHERE subject_key"):
            self._last_result = {"n": self._remaining_counts.get("search_occurrences", 0)}
        elif q.startswith("SELECT count(*) AS n FROM"):
            table = q.split("FROM", 1)[1].split("WHERE")[0].strip()
            self._last_result = {"n": self._remaining_counts.get(table, 0)}
        elif q.startswith("DELETE FROM search_occurrences WHERE subject_key ="):
            self._updates_seen.append(("search_occurrences", "DELETE", params[0]))
        else:
            raise AssertionError("unexpected query: %s" % q)

    def fetchone(self):
        return self._last_result


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _FakeDb:
    def __init__(self, remaining_counts=None):
        self.updates_seen = []
        self._cursor = _FakeCursor(remaining_counts or {}, self.updates_seen)
        self._conn = _FakeConnection(self._cursor)

    def run(self, fn):
        return fn(self._conn)


# ── Fake supabase client (table()/auth.admin) ────────────────────────────

class _FakeAdminAuth:
    def __init__(self, delete_error=None):
        self.delete_error = delete_error
        self.deleted_user_ids = []

    def delete_user(self, user_id, should_soft_delete=False):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted_user_ids.append(user_id)


class _FakeAuth:
    def __init__(self, admin):
        self.admin = admin


class _FakeTableQuery:
    def __init__(self, rows, on_update=None):
        self._rows = rows
        self._on_update = on_update

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def update(self, payload, *_a, **_kw):
        if self._on_update is not None:
            self._on_update(payload)
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


class _FakeSupabase:
    """analytics_consent has no consent row by default (empty subject-key
    list), so withdraw() is never called unless a test explicitly wants it."""

    def __init__(self, admin_delete_error=None, consent_row=None):
        self.auth = _FakeAuth(_FakeAdminAuth(admin_delete_error))
        self._consent_row = consent_row
        self.consent_updates = []

    def table(self, name):
        if name == "analytics_consent":
            rows = [self._consent_row] if self._consent_row is not None else []
            return _FakeTableQuery(rows, on_update=self.consent_updates.append)
        return _FakeTableQuery([])


def _run():
    global _pass, _fail
    from app.services.account_deletion import (
        DeletionFailure,
        resolve_deletion_request,
    )
    from supabase_auth.errors import AuthApiError

    requested_at = datetime(2026, 8, 20, tzinfo=timezone.utc)

    # 1. Happy path: every reconciled table is empty -> outcome resolved.
    db = _FakeDb(remaining_counts={})
    supabase = _FakeSupabase()
    result = resolve_deletion_request(
        db, supabase, request_id="req-1", user_id="user-1", email="a@example.com",
        requested_at=requested_at, admin_id="admin-1",
    )
    check("clean deletion resolves", result["outcome"] == "resolved", result)
    check("auth delete was actually called", supabase.auth.admin.deleted_user_ids == ["user-1"])
    check(
        "NO ACTION actor columns were cleared before the auth delete",
        len(db.updates_seen) == 3,
        db.updates_seen,
    )

    # 2. THE required test: reconciliation finds a remaining row after the
    # Auth API delete succeeded -- this must NEVER report 'resolved'.
    db2 = _FakeDb(remaining_counts={"conversations": 1})
    supabase2 = _FakeSupabase()
    result2 = resolve_deletion_request(
        db2, supabase2, request_id="req-2", user_id="user-2", email="b@example.com",
        requested_at=requested_at, admin_id="admin-1",
    )
    check(
        "resolution cannot succeed while owned data remains",
        result2["outcome"] == "failed",
        result2,
    )
    check(
        "failure reason names the remaining table",
        "conversations" in (result2["failure_reason"] or ""),
        result2.get("failure_reason"),
    )
    check(
        "reconciliation counts are recorded even on failure",
        result2["reconciliation"].get("conversations") == 1,
    )

    # 3. Idempotency: the Auth API already deleted this account (404) --
    # must NOT raise, must still reconcile and can still report resolved.
    db3 = _FakeDb(remaining_counts={})
    supabase3 = _FakeSupabase(
        admin_delete_error=AuthApiError("User not found", 404, None)
    )
    result3 = resolve_deletion_request(
        db3, supabase3, request_id="req-3", user_id="user-3", email="c@example.com",
        requested_at=requested_at, admin_id="admin-1",
    )
    check(
        "a 404 (already deleted) is treated as an idempotent retry, not an error",
        result3["outcome"] == "resolved",
        result3,
    )

    # 4. A real Auth API failure (not 404) raises DeletionFailure, which the
    # caller records on the still-existing deletion_requests row.
    db4 = _FakeDb(remaining_counts={})
    supabase4 = _FakeSupabase(
        admin_delete_error=AuthApiError("Internal error", 500, None)
    )
    raised = False
    try:
        resolve_deletion_request(
            db4, supabase4, request_id="req-4", user_id="user-4", email="d@example.com",
            requested_at=requested_at, admin_id="admin-1",
        )
    except DeletionFailure:
        raised = True
    check("a real Auth API failure raises DeletionFailure", raised)

    # 5. A non-existent auth account (any other unexpected exception shape)
    # also raises DeletionFailure rather than silently succeeding.
    db5 = _FakeDb(remaining_counts={})
    supabase5 = _FakeSupabase(admin_delete_error=RuntimeError("network blip"))
    raised5 = False
    try:
        resolve_deletion_request(
            db5, supabase5, request_id="req-5", user_id="user-5", email="e@example.com",
            requested_at=requested_at, admin_id="admin-1",
        )
    except DeletionFailure:
        raised5 = True
    check("an unexpected Auth API exception also raises DeletionFailure", raised5)

    # 6. An account with an analytics_consent row: consent.withdraw() must
    # actually run (its own DELETE against search_occurrences, keyed by
    # both the current and every retired subject key) before the auth
    # delete -- these tables have no FK to auth.users at all, so nothing
    # would clean them up otherwise.
    db6 = _FakeDb(remaining_counts={})
    supabase6 = _FakeSupabase(
        consent_row={
            "subject_key": "key-current",
            "retired_subject_keys": [{"version": 1, "key": "key-old"}],
        }
    )
    result6 = resolve_deletion_request(
        db6, supabase6, request_id="req-6", user_id="user-6", email="f@example.com",
        requested_at=requested_at, admin_id="admin-1",
    )
    deletes = [u for u in db6.updates_seen if u[1] == "DELETE"]
    check(
        "withdraw() purges both the current and every retired subject key",
        sorted(d[2] for d in deletes) == ["key-current", "key-old"],
        deletes,
    )
    check("consent row is marked withdrawn", len(supabase6.consent_updates) == 1)
    check("deletion with an analytics history still resolves cleanly", result6["outcome"] == "resolved")

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(_run())
