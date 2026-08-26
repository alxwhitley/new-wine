#!/usr/bin/env python3
"""Regression for save_exchange()'s cumulative usage signal (long-conversation
handoff nudge, docs/superpowers/specs/2026-08-26-long-conversation-handoff.md,
phase B).

Runs conversation_store.save_exchange() for real, against an in-memory fake
psycopg2 connection/cursor shaped to conversation_store.py's exact SQL
statements (INSERT ... ON CONFLICT DO NOTHING on `conversations`/`messages`,
then a conditional UPDATE/SELECT on `conversations`). No live DB, no network.

The critical property under test: a reconnect re-GET calls save_exchange()
again for the SAME job_id (async_chat.py's /result endpoint is reconnectable
by design). Without the cur.rowcount == 1 gate on the assistant-message
insert, the cumulative token/turn counters would double-count every replay.
test_reconnect_replay_does_not_double_count proves the real gate holds;
test_harness_catches_a_broken_conflict_gate proves the harness would have
caught it if the gate were absent -- it swaps in a fake cursor that doesn't
honor ON CONFLICT DO NOTHING (always rowcount=1) and shows the same two-call
sequence then DOES double-count, so the first test is not passing by
accident.

Run:
  python3.12 scripts/test_conversation_length_signal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.async_answers import conversation_store  # noqa: E402

failures = []


def check(label, condition, detail=None):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


class _FakeCursor:
    """Understands exactly the SQL shapes save_exchange() issues. honor_conflict
    controls whether an INSERT ... ON CONFLICT DO NOTHING against an id already
    present in the fake store reports rowcount=0 (real Postgres behavior) or
    rowcount=1 (a deliberately broken stand-in, used only by the sensitivity
    test to prove the harness would catch a reverted fix)."""

    def __init__(self, store, honor_conflict=True):
        self._store = store
        self._honor_conflict = honor_conflict
        self.rowcount = 0
        self._last_row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        if "INSERT INTO conversations" in sql:
            conv_id, user_id, title = params
            if conv_id in self._store["conversations"]:
                self.rowcount = 0 if self._honor_conflict else 1
            else:
                self._store["conversations"][conv_id] = {
                    "id": conv_id, "user_id": user_id, "title": title,
                    "cumulative_input_tokens": 0, "cumulative_output_tokens": 0,
                    "turn_count": 0,
                }
                self.rowcount = 1
            return

        if "INSERT INTO messages" in sql and "'user'" in sql:
            mid, conv_id, content = params
            self._insert_message(mid, conv_id, "user")
            return

        if "INSERT INTO messages" in sql and "'assistant'" in sql:
            mid, conv_id, content, citations, verified_refs = params
            self._insert_message(mid, conv_id, "assistant")
            return

        if sql.strip().startswith("UPDATE conversations"):
            in_tok, out_tok, conv_id = params
            row = self._store["conversations"][conv_id]
            row["cumulative_input_tokens"] += in_tok
            row["cumulative_output_tokens"] += out_tok
            row["turn_count"] += 1
            self._last_row = dict(row)
            return

        if sql.strip().startswith("SELECT cumulative_input_tokens"):
            (conv_id,) = params
            self._last_row = dict(self._store["conversations"][conv_id])
            return

        raise AssertionError("unexpected SQL in fake cursor: %r" % sql)

    def _insert_message(self, mid, conv_id, role):
        if mid in self._store["messages"]:
            self.rowcount = 0 if self._honor_conflict else 1
        else:
            self._store["messages"][mid] = {"id": mid, "conversation_id": conv_id, "role": role}
            self.rowcount = 1

    def fetchone(self):
        return self._last_row


class _FakeConn:
    def __init__(self, store, honor_conflict=True):
        self._store = store
        self._honor_conflict = honor_conflict

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self._store, honor_conflict=self._honor_conflict)


class _FakeDb:
    """Minimal stand-in for async_answers.db.Db -- .run(fn) just calls fn(conn),
    no real commit/rollback/reconnect semantics needed for this test."""

    def __init__(self, honor_conflict=True):
        self.store = {"conversations": {}, "messages": {}}
        self._conn = _FakeConn(self.store, honor_conflict=honor_conflict)

    def run(self, fn):
        return fn(self._conn)


def _call(db, job_id, conv_id="conv-1", user_id="user-1", input_tokens=100, output_tokens=50):
    return conversation_store.save_exchange(
        db,
        user_id=user_id,
        conversation_id=conv_id,
        question="What does the Bible say about prayer?",
        answer="An answer.",
        citations=[],
        verified_references=[],
        job_id=job_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def test_first_call_increments_totals():
    db = _FakeDb()
    result = _call(db, "job-1", input_tokens=100, output_tokens=50)
    check("save_exchange returns totals on first call", result is not None)
    check("cumulative_input_tokens == 100", result["cumulative_input_tokens"] == 100, result)
    check("cumulative_output_tokens == 50", result["cumulative_output_tokens"] == 50, result)
    check("turn_count == 1", result["turn_count"] == 1, result)


def test_two_different_jobs_accumulate():
    db = _FakeDb()
    _call(db, "job-1", input_tokens=100, output_tokens=50)
    result = _call(db, "job-2", input_tokens=200, output_tokens=75)
    check("cumulative_input_tokens accumulates across turns (300)", result["cumulative_input_tokens"] == 300, result)
    check("cumulative_output_tokens accumulates across turns (125)", result["cumulative_output_tokens"] == 125, result)
    check("turn_count accumulates across turns (2)", result["turn_count"] == 2, result)


def test_reconnect_replay_does_not_double_count():
    """The real property this feature depends on: async_chat.py's /result
    endpoint is reconnectable, so the same job_id's save_exchange() call can
    run twice for one real turn. Totals must reflect it exactly once."""
    db = _FakeDb(honor_conflict=True)
    first = _call(db, "job-1", input_tokens=100, output_tokens=50)
    second = _call(db, "job-1", input_tokens=100, output_tokens=50)  # reconnect replay
    check("first call increments to turn_count=1", first["turn_count"] == 1, first)
    check(
        "replayed call does NOT double-count (still turn_count=1)",
        second["turn_count"] == 1,
        second,
    )
    check(
        "replayed call does NOT double-count tokens (still 100/50)",
        second["cumulative_input_tokens"] == 100 and second["cumulative_output_tokens"] == 50,
        second,
    )


def test_harness_catches_a_broken_conflict_gate():
    """Sensitivity check: with a fake cursor that does NOT honor ON CONFLICT
    DO NOTHING (simulating the rowcount==1 gate being absent/reverted), the
    exact same two-call sequence DOES double-count -- proving the previous
    test is only green because the real gate is real, not because the fake
    can't detect a double-count."""
    db = _FakeDb(honor_conflict=False)
    _call(db, "job-1", input_tokens=100, output_tokens=50)
    second = _call(db, "job-1", input_tokens=100, output_tokens=50)
    check(
        "broken-gate fake DOES double-count (turn_count=2) -- confirms test sensitivity",
        second["turn_count"] == 2,
        second,
    )
    check(
        "broken-gate fake DOES double-count tokens (200/100) -- confirms test sensitivity",
        second["cumulative_input_tokens"] == 200 and second["cumulative_output_tokens"] == 100,
        second,
    )


def main():
    test_first_call_increments_totals()
    test_two_different_jobs_accumulate()
    test_reconnect_replay_does_not_double_count()
    test_harness_catches_a_broken_conflict_gate()

    print()
    total = 12
    print("%d checks, %d failed" % (total, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
