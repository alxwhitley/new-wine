#!/usr/bin/env python3
"""
Concurrency regression for the 2026-08-18 quote-creation race close
(CLAUDE.md Landmines' logged idempotency finding, PLAN.md W7):
create_and_approve_quote()'s check-then-insert body is now wrapped in
quotes._creation_lock(), a Postgres session-level advisory lock keyed on
the exact (chunk_id, quote_text, teacher_source_id) triple
_find_existing_quote_for_passage() matches on -- see quotes.py's
_creation_lock docstring for why an advisory lock was chosen over a new
UNIQUE constraint (no migration needed; the identity spans two tables).

Two things are proven here, both with REAL threads racing the REAL
create_and_approve_quote() body -- not a description of the mechanism,
executable evidence:

1. test_concurrent_creation_is_serialized_with_lock: with the real lock in
   place (only its psycopg2 connection swapped for an in-process fake that
   still provides genuine cross-thread mutual exclusion via a real
   threading.Lock), two threads racing the identical triple always produce
   exactly one quotes row and the same returned id -- regardless of
   scheduling, proven by starting both threads from a shared barrier to
   maximize real contention.

2. test_concurrent_creation_duplicates_without_lock: the harness's own
   sensitivity check. _creation_lock is patched to a no-op (simulating the
   fix being absent/reverted) and the idempotency check
   (_find_existing_quote_for_passage) is wrapped with a barrier that force
   -interleaves two threads through the exact TOCTOU window the lock
   exists to close. This reliably reproduces the duplicate-row bug,
   proving the harness would have caught the original defect -- the
   "demonstrated to FAIL when the fix is reverted" requirement, run here
   automatically rather than by hand-editing quotes.py.

A third, independent confirmation (not automated here, run manually during
development and not re-run by CI): temporarily removing the
`with _creation_lock(...):` wrapping in quotes.py's
create_and_approve_quote() and re-running test 1 above (unmodified) also
reproduces the duplicate -- proving the wrapping is actually load-bearing
in the real function, not just that _creation_lock works in isolation.

Run from project root:
  /private/tmp/newwine-w1w4-venv/bin/python scripts/test_quote_creation_race.py
"""
from __future__ import annotations

import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.services import quotes
from app.services.async_answers import db as async_db_module

failures = []


def check(label, condition, detail=None):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


@contextmanager
def _noop_lock(*_args, **_kwargs):
    yield


# ─────────────────────────────────────────────────────────────────────────
# FakeDb -- same minimal Supabase-client-shaped in-memory store used by
# scripts/test_quote_passage_relevance.py, reproduced here rather than
# imported so this file has no import-order dependency on that one.
# ─────────────────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._rows = list(db.tables.get(table_name, []))
        self._limit = None

    def select(self, _cols):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def neq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) != value]
        return self

    def in_(self, field, values):
        values = set(values)
        self._rows = [r for r in self._rows if r.get(field) in values]
        return self

    def order(self, _field):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self._rows if self._limit is None else self._rows[: self._limit]
        return _FakeResult(rows)

    def insert(self, row):
        full = dict(row)
        full.setdefault("id", str(uuid.uuid4()))
        full.setdefault("created_at", self._db.next_timestamp())
        with self._db.write_lock:
            self._db.tables.setdefault(self._table_name, []).append(full)
        return _FakeInsert(full)


class _FakeInsert:
    def __init__(self, row):
        self._row = row

    def execute(self):
        return _FakeResult([self._row])


class FakeDb:
    def __init__(self):
        self.tables = {}
        self._clock = 0
        self._clock_lock = threading.Lock()
        # Only used to make the *unprotected* reproduction test's
        # concurrent appends deterministic to observe (CPython's GIL
        # already makes list.append atomic; this just documents the
        # intent rather than relying on that implementation detail).
        self.write_lock = threading.Lock()

    def next_timestamp(self):
        with self._clock_lock:
            self._clock += 1
            return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self._clock)).isoformat()

    def table(self, name):
        return _FakeQuery(self, name)


PRINCE_ID = next(iter(quotes.CONFIRMED_TEACHER_SOURCE_IDS))
CHUNK_CONTENT = (
    "Intro filler sentence here. This is the real raced sentence for our "
    "concurrency test. Trailing filler sentence follows nicely."
)
CANDIDATE_TEXT = "This is the real raced sentence for our concurrency test."


def _seed_fixture():
    db = FakeDb()
    db.tables["chunks"] = [
        {"id": "chunk-1", "document_id": "doc-1", "content": CHUNK_CONTENT, "quote_ineligible_reason": None},
    ]
    db.tables["documents"] = [{"id": "doc-1", "source_id": PRINCE_ID}]
    db.tables["quote_source_revisions"] = []
    db.tables["quotes"] = []
    db.tables["quote_verification_log"] = []
    return db


# ─────────────────────────────────────────────────────────────────────────
# Fake advisory-lock connection: an in-process stand-in for the real
# psycopg2 connection _creation_lock() opens, but backed by a REAL
# threading.Lock per key -- so two "connections" from two Python threads
# genuinely serialize on the same key, the same guarantee Postgres's own
# pg_advisory_lock provides across real sessions.
# ─────────────────────────────────────────────────────────────────────────

class _FakeLockCursor:
    _registry = {}
    _registry_guard = threading.Lock()

    def __init__(self, held_by_conn):
        self._held = held_by_conn

    def execute(self, sql, params=None):
        key = params[0] if params else None
        if "pg_advisory_unlock" in sql:
            lock = _FakeLockCursor._registry.get(key)
            if lock is not None and key in self._held:
                lock.release()
                self._held.discard(key)
            return
        if "pg_advisory_lock" in sql:
            with _FakeLockCursor._registry_guard:
                lock = _FakeLockCursor._registry.setdefault(key, threading.Lock())
            lock.acquire()  # blocks -- real cross-thread mutual exclusion
            self._held.add(key)
            return
        raise AssertionError("unexpected SQL in fake lock cursor: %r" % sql)

    def close(self):
        pass


class _FakeLockConn:
    def __init__(self):
        self.autocommit = False
        self._held = set()

    def cursor(self):
        return _FakeLockCursor(self._held)

    def close(self):
        pass


def test_advisory_lock_key_is_deterministic_per_triple():
    k1 = quotes._advisory_lock_key("chunk-1", "some text", PRINCE_ID)
    k2 = quotes._advisory_lock_key("chunk-1", "some text", PRINCE_ID)
    k3 = quotes._advisory_lock_key("chunk-2", "some text", PRINCE_ID)
    check("the same triple always hashes to the same lock key", k1 == k2, detail="%r != %r" % (k1, k2))
    check("a different triple hashes to a different lock key", k1 != k3, detail="%r == %r" % (k1, k3))
    check(
        "the key fits Postgres bigint range (pg_advisory_lock(bigint))",
        -(2 ** 63) <= k1 < 2 ** 63,
        detail=repr(k1),
    )


def test_concurrent_creation_is_serialized_with_lock():
    """The real fix, real function, real threads. Two threads call
    create_and_approve_quote() with the identical (chunk_id, quote_text,
    teacher_source_id) triple. Only the psycopg2 connection
    _creation_lock() opens is swapped for the in-process fake above --
    create_and_approve_quote() itself and _creation_lock() itself both run
    unmodified.

    _find_existing_quote_for_passage is wrapped with a real, unconditional
    time.sleep() between its check and its return -- widening the TOCTOU
    window it guards to something far larger than CPython's GIL scheduling
    granularity. This is deliberate: an earlier version of this test only
    started both threads from a shared barrier and relied on them
    happening to overlap, which turned out to pass whether or not the lock
    was actually wired into create_and_approve_quote (fast, sleep-free
    FakeDb calls could run start-to-finish inside one GIL slice, so the
    unprotected case sometimes never actually raced). The explicit sleep
    makes the window wide enough that an UNPROTECTED pair reliably races
    every run (proven by test_concurrent_creation_duplicates_without_lock's
    equivalent forced window), so a PROTECTED pair reliably NOT racing is
    real evidence of the lock working, not scheduling luck."""
    db = _seed_fixture()
    results = [None, None]
    errors = [None, None]
    start_barrier = threading.Barrier(2)
    real_check = quotes._find_existing_quote_for_passage

    def slow_check(db_arg, chunk_id, quote_text, teacher_source_id):
        result = real_check(db_arg, chunk_id, quote_text, teacher_source_id)
        time.sleep(0.05)
        return result

    def worker(idx, note):
        try:
            start_barrier.wait(timeout=5)
            results[idx] = quotes.create_and_approve_quote(
                db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", note, "user-1"
            )
        except Exception as e:  # noqa: BLE001 -- captured for the assertion below
            errors[idx] = e

    with patch.object(async_db_module, "connect", side_effect=_FakeLockConn), \
            patch.object(quotes, "_find_existing_quote_for_passage", side_effect=slow_check):
        t1 = threading.Thread(target=worker, args=(0, "thread-1"))
        t2 = threading.Thread(target=worker, args=(1, "thread-2"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

    check("neither worker raised", errors == [None, None], detail=repr(errors))
    check(
        "both racing calls returned the SAME quote id",
        results[0] is not None and results[1] is not None and results[0]["id"] == results[1]["id"],
        detail=repr(results),
    )
    check(
        "a real concurrent race under the lock produces exactly ONE quotes row",
        len(db.tables["quotes"]) == 1,
        detail="quotes table has %d rows" % len(db.tables["quotes"]),
    )
    check(
        "a real concurrent race under the lock produces exactly ONE quote_source_revisions row",
        len(db.tables["quote_source_revisions"]) == 1,
        detail="quote_source_revisions table has %d rows" % len(db.tables["quote_source_revisions"]),
    )


def test_concurrent_creation_duplicates_without_lock():
    """Harness sensitivity check: with _creation_lock disabled (the fix
    absent) and the exact TOCTOU window forced open by a barrier inside
    _find_existing_quote_for_passage, the identical two-thread race DOES
    produce a duplicate. This is the executable version of "demonstrated to
    FAIL when the fix is reverted" -- it proves this harness can actually
    detect the bug the lock exists to close, rather than trivially passing
    no matter what."""
    db = _seed_fixture()
    results = [None, None]
    errors = [None, None]
    start_barrier = threading.Barrier(2)
    race_barrier = threading.Barrier(2)
    real_check = quotes._find_existing_quote_for_passage

    def racy_check(db_arg, chunk_id, quote_text, teacher_source_id):
        result = real_check(db_arg, chunk_id, quote_text, teacher_source_id)
        # Force BOTH threads to observe "not found" before either is
        # allowed to proceed to verification/insert -- the exact race
        # window a real concurrent pair could hit by unlucky timing,
        # reproduced deterministically instead of hoping for it.
        race_barrier.wait(timeout=5)
        return result

    def worker(idx, note):
        try:
            start_barrier.wait(timeout=5)
            results[idx] = quotes.create_and_approve_quote(
                db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", note, "user-1"
            )
        except Exception as e:  # noqa: BLE001
            errors[idx] = e

    with patch.object(quotes, "_creation_lock", _noop_lock), \
            patch.object(quotes, "_find_existing_quote_for_passage", side_effect=racy_check):
        t1 = threading.Thread(target=worker, args=(0, "thread-1"))
        t2 = threading.Thread(target=worker, args=(1, "thread-2"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

    check("neither worker raised or deadlocked", errors == [None, None], detail=repr(errors))
    check(
        "WITHOUT the lock, the forced race reproduces the bug: TWO quotes rows",
        len(db.tables["quotes"]) == 2,
        detail="quotes table has %d rows (expected 2 -- this test WANTS the bug to reproduce)" % len(
            db.tables["quotes"]),
    )
    check(
        "WITHOUT the lock, the forced race also duplicates quote_source_revisions",
        len(db.tables["quote_source_revisions"]) == 2,
        detail="quote_source_revisions table has %d rows" % len(db.tables["quote_source_revisions"]),
    )


def main():
    print("quote-creation concurrency regression suite")
    print("=" * 70)
    test_advisory_lock_key_is_deterministic_per_triple()
    test_concurrent_creation_is_serialized_with_lock()
    test_concurrent_creation_duplicates_without_lock()
    print("=" * 70)
    if failures:
        print("%d check(s) FAILED:" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
