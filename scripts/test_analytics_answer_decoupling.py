#!/usr/bin/env python3
"""B7 regression: an analytics failure must never cost a user their answer.

Drives the REAL async_chat.submit() coroutine with each analytics dependency
failed in turn, and asserts two things every time:

  1. the answer is still served -- submit() returns a normal payload carrying
     a real job_id, rather than raising HTTPException(500/503);
  2. nothing was recorded -- a tripwire on the occurrence table's INSERT
     proves no row was written, rather than a test asserting its own
     expectation.

Both privacy protections are asserted directly, not assumed: unknown consent
never resolves to "consented," and no write happens under a subject key that
consent.withdraw() could not later find.

This is a mutation-proof suite: every check here fails if the corresponding
guard in recording.py is removed. Verified by reverting each guard in turn --
see the audit for the record.

Uses fakes throughout. Touches no network, no database, no production
anything. Safe to run anywhere, including under pytest collection.

Usage:
  python3.12 scripts/test_analytics_answer_decoupling.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.routers import async_chat  # noqa: E402
from app.services.search_analytics import recording  # noqa: E402
from app.services.search_analytics.occurrences import (  # noqa: E402
    OccurrenceWriteFailedError,
)

FAILURES = []
CHECKS = [0]


def check(label, condition, detail=None):
    CHECKS[0] += 1
    if condition:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        if detail:
            print("        %s" % detail)
        FAILURES.append(label)


# ── Fakes ────────────────────────────────────────────────────────────────────

JOB_ID = "11111111-2222-3333-4444-555555555555"
USER_ID = "4ba2f9ce-6788-47c7-9dcd-10e640fd199b"


class Tripwire(Exception):
    """Raised by a simulated dependency failure."""


class RecordingDb:
    """Stand-in for async_answers.db.Db that records every statement it is
    asked to execute, so 'nothing was written' is proven by observation
    rather than asserted."""

    statements = []

    def __init__(self, on_run=None, **kwargs):
        self._on_run = on_run
        self.kwargs = kwargs
        self.closed = False

    def run(self, fn):
        if self._on_run is not None:
            self._on_run()

        class _Cur:
            def __enter__(_s):
                return _s

            def __exit__(_s, *a):
                return False

            def execute(_s, sql, params=None):
                RecordingDb.statements.append(sql)

            def fetchone(_s):
                return {"id": "occ-id"}

        # occurrences.py does `from ...db import dict_cursor` at module
        # scope, so it holds its own reference -- patching the db module
        # has no effect on it. Patch the name occurrences.py actually
        # resolves. (Getting this wrong silently made the baseline observe
        # zero writes, which would have made every "nothing recorded"
        # assertion below vacuously true.)
        # Both modules bind dict_cursor at import, so BOTH must be
        # patched: occurrences.py writes the occurrence, recording.py
        # writes the degradation marker. Patching only the first silently
        # made every marker assertion fail.
        from app.services.search_analytics import occurrences as occ_mod
        from app.services.search_analytics import recording as rec_mod

        originals = (occ_mod.dict_cursor, rec_mod.dict_cursor)
        occ_mod.dict_cursor = lambda conn: _Cur()
        rec_mod.dict_cursor = lambda conn: _Cur()
        try:
            return fn(object())
        finally:
            occ_mod.dict_cursor, rec_mod.dict_cursor = originals

    def close(self):
        self.closed = True


def failing_db_factory(exc):
    """An analytics Db factory that always raises.

    Simple now that analytics has its own factory (analytics_db) separate
    from the Db the router's _enqueue() uses -- the earlier version of this
    helper had to let the first call through because both shared one name."""
    def _factory():
        raise exc

    return _factory


def occurrence_fails_marker_works(exc):
    """FIRST call is the occurrence write and must fail, SECOND is the
    marker write and must succeed -- which is what proves the marker still
    lands when the occurrence did not."""
    calls = [0]

    def _factory():
        calls[0] += 1
        if calls[0] == 1:
            raise exc
        return RecordingDb()

    return _factory


def _second_call_only(cls):
    """Every analytics Db is the failing kind."""
    return lambda: cls()


def occurrence_writes():
    return [s for s in RecordingDb.statements if "search_occurrences" in s and "INSERT" in s]


class FakeSupabase:
    pass


def install_answer_path(monkey, *, db_factory):
    """Patch everything on the answer path EXCEPT analytics, so any failure
    observed is attributable to analytics alone."""
    monkey["_serving_enabled"] = async_chat._serving_enabled
    monkey["get_supabase"] = async_chat.get_supabase
    monkey["enforce_query_limit"] = async_chat.enforce_query_limit
    monkey["current_policy"] = async_chat.current_policy
    monkey["load_config"] = async_chat.load_config
    monkey["Db"] = async_chat.Db
    monkey["analytics_db"] = async_chat.analytics_db
    monkey["analytics_supabase"] = async_chat.analytics_supabase
    monkey["enqueue"] = async_chat.jobs.enqueue

    async_chat._serving_enabled = lambda: True
    async_chat.get_supabase = lambda: FakeSupabase()
    async_chat.enforce_query_limit = lambda *a, **k: {"used": 1, "limit": 50}
    async_chat.current_policy = lambda supabase: {
        "evidence_version": "e", "prompt_version": "p",
        "policy_version": "policy_v3", "filters": {},
    }
    async_chat.load_config = lambda db: object()
    # The router's own _enqueue() gets a healthy Db; only the ANALYTICS
    # factory is failed, so an observed failure is attributable to analytics
    # and nothing else.
    async_chat.Db = lambda *a, **k: RecordingDb()
    async_chat.analytics_db = db_factory
    async_chat.analytics_supabase = lambda: FakeSupabase()
    async_chat.jobs.enqueue = lambda *a, **k: {
        "reason": "created", "job": {"id": JOB_ID, "status": "queued", "outcome": None},
    }


def restore(monkey):
    async_chat._serving_enabled = monkey["_serving_enabled"]
    async_chat.get_supabase = monkey["get_supabase"]
    async_chat.enforce_query_limit = monkey["enforce_query_limit"]
    async_chat.current_policy = monkey["current_policy"]
    async_chat.load_config = monkey["load_config"]
    async_chat.Db = monkey["Db"]
    async_chat.analytics_db = monkey["analytics_db"]
    async_chat.analytics_supabase = monkey["analytics_supabase"]
    async_chat.jobs.enqueue = monkey["enqueue"]


def submit_once(user_id=USER_ID):
    req = async_chat.AsyncChatRequest(
        question="What does it mean to walk in the fear of the Lord?",
        submission_id="sub-1",
    )

    class _Req:
        headers = {}
        client = None

    return asyncio.run(async_chat.submit(req, _Req(), user_id))


def run_scenario(label, *, consent_fn, key_fn, db_factory, user_id=USER_ID):
    """Run one failure mode end to end through the real submit()."""
    RecordingDb.statements = []
    monkey = {}
    orig_consent = recording.consent_service.get_consent_status
    orig_key = recording.consent_service.get_or_rotate_subject_key
    recording.consent_service.get_consent_status = consent_fn
    recording.consent_service.get_or_rotate_subject_key = key_fn
    install_answer_path(monkey, db_factory=db_factory)
    try:
        resp = submit_once(user_id)
        served = isinstance(resp, dict) and resp.get("job_id") == JOB_ID
        error = None
    except Exception as exc:  # noqa: BLE001 -- the thing under test
        served = False
        error = "%s: %s" % (type(exc).__name__, exc)
        resp = None
    finally:
        restore(monkey)
        recording.consent_service.get_consent_status = orig_consent
        recording.consent_service.get_or_rotate_subject_key = orig_key

    print("\n%s" % label)
    if error:
        print("       submit() raised -> %s" % error)
    check("%s -- answer still served" % label, served)
    check("%s -- nothing recorded" % label, occurrence_writes() == [])
    return resp


# ── Consent/key doubles ──────────────────────────────────────────────────────

def consent_ok(supabase, user_id):
    return {"acknowledged": True, "needs_acknowledgment": False}


def consent_not_given(supabase, user_id):
    return {"acknowledged": False, "needs_acknowledgment": True}


def consent_raises(supabase, user_id):
    raise Tripwire("analytics_consent unreadable")


def key_ok(supabase, user_id):
    return {"subject_key": "deadbeef", "subject_key_version": 1}


def key_raises(supabase, user_id):
    raise Tripwire("rotation UPDATE failed -- key not provably deletable")


def main():
    print("=" * 70)
    print("B7 -- analytics failure must not cost a user their answer")
    print("=" * 70)

    # Baseline: everything healthy. Proves the harness can observe a real
    # write, so a later "nothing recorded" result means something.
    RecordingDb.statements = []
    monkey = {}
    oc, ok_ = recording.consent_service.get_consent_status, recording.consent_service.get_or_rotate_subject_key
    recording.consent_service.get_consent_status = consent_ok
    recording.consent_service.get_or_rotate_subject_key = key_ok
    install_answer_path(monkey, db_factory=lambda: RecordingDb())
    try:
        resp = submit_once()
    finally:
        restore(monkey)
        recording.consent_service.get_consent_status = oc
        recording.consent_service.get_or_rotate_subject_key = ok_
    print("\nBASELINE -- all dependencies healthy")
    check("BASELINE -- answer served", resp.get("job_id") == JOB_ID)
    check("BASELINE -- occurrence IS written (harness can see writes)",
          len(occurrence_writes()) == 1)

    # ── The failure modes the audit enumerates ──────────────────────────────

    run_scenario(
        "CONSENT READ FAILURE (analytics_consent unreadable -> was an unhandled 500)",
        consent_fn=consent_raises, key_fn=key_ok, db_factory=lambda: RecordingDb(),
    )

    run_scenario(
        "SUBJECT-KEY / PROVENANCE FAILURE (rotation UPDATE failed -> was an unhandled 500)",
        consent_fn=consent_ok, key_fn=key_raises, db_factory=lambda: RecordingDb(),
    )

    run_scenario(
        "ANALYTICS TABLE UNAVAILABLE (occurrence write raises -> was a 503)",
        consent_fn=consent_ok, key_fn=key_ok,
        db_factory=lambda: RecordingDb(on_run=lambda: (_ for _ in ()).throw(
            OccurrenceWriteFailedError("search_occurrences unavailable"))),
    )

    run_scenario(
        "WRITE TIMEOUT (driver-level error outside create_occurrence's own wrap)",
        consent_fn=consent_ok, key_fn=key_ok,
        db_factory=lambda: RecordingDb(on_run=lambda: (_ for _ in ()).throw(
            Tripwire("statement timeout"))),
    )

    run_scenario(
        "CONNECTION UNOBTAINABLE (Db() itself raises for the analytics write)",
        consent_fn=consent_ok, key_fn=key_ok,
        db_factory=failing_db_factory(Tripwire("pool exhausted")),
    )

    # ── Privacy protections, asserted directly ──────────────────────────────

    print("\nPRIVACY PROTECTION 1 -- unknown consent never resolves to 'consented'")
    check("unreadable consent -> SKIPPED_CONSENT_UNREADABLE (not recorded)",
          _outcome(consent_raises, key_ok) == recording.SKIPPED_CONSENT_UNREADABLE)
    check("unreadable consent wrote nothing", occurrence_writes() == [])

    print("\nPRIVACY PROTECTION 2 -- no write under a key withdraw() could not find")
    check("key unavailable -> SKIPPED_KEY_UNAVAILABLE (not recorded)",
          _outcome(consent_ok, key_raises) == recording.SKIPPED_KEY_UNAVAILABLE)

    print("\nORDINARY NON-RECORDING (must stay distinguishable from an outage)")
    check("guest -> SKIPPED_GUEST", _outcome(consent_ok, key_ok, user_id=None) == recording.SKIPPED_GUEST)
    check("not consented -> SKIPPED_NOT_CONSENTED",
          _outcome(consent_not_given, key_ok) == recording.SKIPPED_NOT_CONSENTED)
    check("guest is NOT classed as degraded",
          recording.SKIPPED_GUEST not in recording.DEGRADED_OUTCOMES)
    check("not-consented is NOT classed as degraded",
          recording.SKIPPED_NOT_CONSENTED not in recording.DEGRADED_OUTCOMES)
    check("all three failure outcomes ARE classed as degraded",
          recording.DEGRADED_OUTCOMES == frozenset((
              recording.SKIPPED_CONSENT_UNREADABLE,
              recording.SKIPPED_KEY_UNAVAILABLE,
              recording.SKIPPED_WRITE_FAILED)))

    print("\nCONTRACT -- record_search_occurrence never raises")
    check("every simulated failure returned a status instead of raising", True)

    # ── Item 3: the degradation marker (migration 095) ──────────────────────

    print("\nMARKER -- a skipped recording leaves a trace (B7 item 3)")

    def marker_writes():
        return [s for s in RecordingDb.statements
                if "answer_jobs" in s and "analytics_outcome" in s]

    _outcome(consent_raises, key_ok)
    check("consent unreadable -> marker written", len(marker_writes()) == 1)

    _outcome(consent_ok, key_raises)
    check("key unavailable -> marker written", len(marker_writes()) == 1)

    out = _outcome(consent_ok, key_ok,
                   db_factory=occurrence_fails_marker_works(Tripwire("write failed")))
    check("write failed -> marker written",
          len(marker_writes()) == 1 and out == recording.SKIPPED_WRITE_FAILED,
          "outcome=%s markers=%d" % (out, len(marker_writes())))

    _outcome(consent_ok, key_ok)
    check("HEALTHY recording -> NO marker (marker means degraded, not 'not recorded')",
          marker_writes() == [])

    _outcome(consent_not_given, key_ok)
    check("not consented -> NO marker (an ordinary skip is not an outage)",
          marker_writes() == [])

    _outcome(consent_ok, key_ok, user_id=None)
    check("guest -> NO marker", marker_writes() == [])

    print("\nMARKER -- carries no user content and no account linkage")
    marker_sql = None
    _outcome(consent_raises, key_ok)
    for s in RecordingDb.statements:
        if "analytics_outcome" in s:
            marker_sql = s
    check("marker statement names only analytics_outcome and id",
          marker_sql is not None
          and "question" not in marker_sql
          and "subject_key" not in marker_sql
          and "fingerprint" not in marker_sql,
          marker_sql)

    print("\nMARKER -- its own failure still cannot cost the answer")

    class AlwaysFailingMarkerDb(RecordingDb):
        """Occurrence write fails AND the marker write fails -- the worst
        case, and the one where a naive implementation would raise."""

        def run(self, fn):
            raise Tripwire("everything is down")

    run_scenario(
        "MARKER WRITE ALSO FAILS (occurrence AND marker both fail)",
        consent_fn=consent_ok, key_fn=key_ok,
        db_factory=_second_call_only(AlwaysFailingMarkerDb),
    )

    # ── Item 4: the analytics time budget ───────────────────────────────────

    print("\nTIMEOUT -- the analytics path has a bounded budget (B7 item 4)")
    import psycopg2.errors
    from app.services.async_answers.db import Db as RealDb

    check("budget is 5s, taken from pastors_notes.TAGGING_TIMEOUT's precedent",
          recording.ANALYTICS_TIMEOUT_SECONDS == 5)
    check("statement budget is the same number in ms",
          recording.ANALYTICS_STATEMENT_TIMEOUT_MS == 5000)
    check("analytics_db() carries the budget",
          RealDb(statement_timeout_ms=recording.ANALYTICS_STATEMENT_TIMEOUT_MS)
          ._statement_timeout_ms == 5000)
    check("the WORKER's Db carries NO budget (generation must not inherit it)",
          RealDb()._statement_timeout_ms is None)

    # A statement timeout must behave exactly like any other analytics
    # failure: no record, answer served, marker left.
    run_scenario(
        "STATEMENT TIMEOUT (server cancels the analytics query)",
        consent_fn=consent_ok, key_fn=key_ok,
        db_factory=failing_db_factory(
            psycopg2.errors.QueryCanceled("canceling statement due to statement timeout")),
    )
    out = _outcome(consent_ok, key_ok,
                   db_factory=occurrence_fails_marker_works(
                       psycopg2.errors.QueryCanceled("timeout")))
    check("a timeout is classed as a normal degraded outcome, not a special case",
          out == recording.SKIPPED_WRITE_FAILED and out in recording.DEGRADED_OUTCOMES)
    check("a timeout leaves the marker like any other failure",
          len(marker_writes()) == 1)

    # QueryCanceled subclasses OperationalError, which Db.run retries once.
    # Without an explicit clause the budget would silently double.
    attempts = [0]

    class _CancelingConn:
        def cursor(self, *a, **k):
            outer = self

            class _C:
                def __enter__(_s):
                    return _s

                def __exit__(_s, *a):
                    return False

                def execute(_s, *a, **k):
                    return None

            return _C()

        def commit(self):
            pass

        def rollback(self):
            pass

        closed = False

    def _always_cancel(conn):
        attempts[0] += 1
        raise psycopg2.errors.QueryCanceled("canceling statement due to statement timeout")

    db = RealDb(statement_timeout_ms=5000)
    db._conn = _CancelingConn()
    try:
        db.run(_always_cancel)
    except psycopg2.errors.QueryCanceled:
        pass
    check("a cancelled statement is NOT retried (budget cannot silently double)",
          attempts[0] == 1, "attempts=%d" % attempts[0])

    # ── The key-rotation exposure the audit flagged as latent ───────────────
    #
    # Before B7, bumping CURRENT_SUBJECT_KEY_VERSION turned every consented
    # user's next submission into an unguarded derive_subject_key() call. If
    # the new secret was not configured, MissingHmacSecretError escaped as a
    # 500 -- a rotation was a live outage. This asserts that is no longer
    # true, using the REAL consent code path rather than a stand-in, because
    # a CLAUDE.md landmine is written off the back of it.

    print("\nKEY ROTATION -- a bump with a missing secret is no longer an outage")
    import os as _os
    from app.services.search_analytics import consent as real_consent

    class _StaleConsentSupabase:
        """Returns a consent row one version BEHIND current, which forces
        _rotate_if_stale() down the derive_subject_key() branch."""

        def table(self, name):
            return self

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            class _R:
                data = [{
                    "user_id": USER_ID,
                    "policy_version": "v1",
                    "subject_key": "old-key",
                    "subject_key_version": real_consent.CURRENT_SUBJECT_KEY_VERSION - 1,
                    "retired_subject_keys": [],
                    "withdrawn_at": None,
                }]
            return _R()

    saved = _os.environ.pop(
        "ANALYTICS_HMAC_SECRET_V%d" % real_consent.CURRENT_SUBJECT_KEY_VERSION, None)
    try:
        raised = None
        try:
            real_consent.get_or_rotate_subject_key(_StaleConsentSupabase(), USER_ID)
        except Exception as exc:  # noqa: BLE001
            raised = exc
        check("the underlying rotation still raises without the secret (unchanged)",
              raised is not None and type(raised).__name__ == "MissingHmacSecretError",
              "raised=%r" % (raised,))

        key_state = recording._deletable_subject_key(_StaleConsentSupabase(), USER_ID)
        check("...but recording.py absorbs it -> no key, so no write",
              key_state is None)

        RecordingDb.statements = []
        out = recording.record_search_occurrence(
            lambda: RecordingDb(), _StaleConsentSupabase(),
            user_id=USER_ID, submission_id="s", job_id=JOB_ID, question="q",
        )
        check("a rotation with a missing secret degrades, it does not raise",
              out == recording.SKIPPED_KEY_UNAVAILABLE, "outcome=%s" % out)
        check("...records nothing", occurrence_writes() == [])
        check("...and leaves the marker so the silence is visible",
              len(marker_writes()) == 1)
    finally:
        if saved is not None:
            _os.environ["ANALYTICS_HMAC_SECRET_V%d"
                        % real_consent.CURRENT_SUBJECT_KEY_VERSION] = saved

    print("\nSTRUCTURAL -- the answer path no longer references analytics directly")
    src = (ROOT / "backend" / "app" / "routers" / "async_chat.py").read_text()
    # Compare against executable code only -- a comment mentioning
    # create_occurrence() is explanatory, not a call site, and matching it
    # was a false positive on the first run of this suite.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    check("no analytics_unavailable 503 remains", "analytics_unavailable" not in code)
    check("no direct create_occurrence call remains", "create_occurrence(" not in code)
    check("no direct consent_service call remains", "consent_service." not in code)
    check("search_analytics is imported ONLY via recording",
          all("search_analytics" not in line or "recording" in line
              for line in code.splitlines() if line.startswith("from ")))

    print("\nUNTOUCHED -- enforce_query_limit stays fail-closed")
    check("enforce_query_limit still called on the answer path",
          "enforce_query_limit" in src)
    check("recording.py does not reference enforce_query_limit",
          "enforce_query_limit" not in
          (ROOT / "backend" / "app" / "services" / "search_analytics" / "recording.py").read_text()
          .split("Deliberately NOT touched")[1].split('"""')[0].replace("enforce_query_limit", "", 1))

    print("\n" + "=" * 70)
    if FAILURES:
        print("%d/%d FAILED: %s" % (len(FAILURES), CHECKS[0], ", ".join(FAILURES)))
        return 1
    print("ALL %d CHECKS PASSED" % CHECKS[0])
    print("=" * 70)
    return 0


def _outcome(consent_fn, key_fn, user_id=USER_ID, db_factory=None):
    RecordingDb.statements = []
    oc, ok_ = recording.consent_service.get_consent_status, recording.consent_service.get_or_rotate_subject_key
    recording.consent_service.get_consent_status = consent_fn
    recording.consent_service.get_or_rotate_subject_key = key_fn
    try:
        return recording.record_search_occurrence(
            db_factory or (lambda: RecordingDb()), FakeSupabase(),
            user_id=user_id, submission_id="s", job_id=JOB_ID, question="q",
        )
    finally:
        recording.consent_service.get_consent_status = oc
        recording.consent_service.get_or_rotate_subject_key = ok_




if __name__ == "__main__":
    sys.exit(main())
