"""Fail-safe search-occurrence recording for the answer path (B7).

WHY THIS MODULE EXISTS. Until 2026-08-31 the answer path made three
blocking analytics calls inline in async_chat.py's /submit, and an
analytics failure took the ANSWER away from a real user: two unguarded
consent reads produced an unhandled 500, and the occurrence write produced
a 503. All three ran AFTER the quota was spent and the job was enqueued, so
the worker still generated and paid for an answer nobody received. Full
diagnosis: docs/audits/2026-08/analytics_answer_coupling_2026-08-31.md.

THE RULE, and it is the whole point of the module (Alex's decision,
2026-08-31): when analytics cannot be reached, or consent state cannot be
determined, DO NOT RECORD -- and ANSWER ANYWAY.

WHAT DID NOT CHANGE. Both privacy protections are preserved exactly. They
are the hard constraint this module is built around, not something traded
away for availability:

  1. An unknown or unreadable consent state NEVER resolves to "consented."
     Every failure resolves to "do not record." The only path that records
     is an affirmative, successfully-read, current-version acknowledgement.

  2. No occurrence is written that a later withdrawal could not delete.
     consent.withdraw() finds rows by the account's current subject_key
     plus every key in retired_subject_keys, so a key that never landed in
     the consent row is a key whose rows are undeletable. This module
     therefore only ever writes under a key returned by
     consent.get_or_rotate_subject_key(), which returns only after the
     rotation UPDATE has succeeded (or after establishing no rotation was
     needed). If that call fails for any reason, we skip the write
     entirely rather than write under an unrecorded key.

What changed is ONLY the consequence of those refusals: previously refusing
to record also refused the answer. Now it skips the write and serves.

NEVER RAISES. That is this module's contract with async_chat.py -- the
caller has no except clause and must not need one. Every outcome is a
returned status string. Adding a raise here silently reintroduces exactly
the coupling this module was built to remove.

Deliberately NOT touched: enforce_query_limit (async_chat.py, one call
earlier) stays fail-closed. Failing open there would let a caller exceed
their weekly quota -- a real abuse/cost control whose failure mode is the
user getting MORE than they should. Analytics has no equivalent: failing
open costs a dashboard row.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.services.async_answers.db import dict_cursor

from . import consent as consent_service
from .occurrences import create_occurrence

logger = logging.getLogger(__name__)

# Outcomes. Exactly one is returned per call, and only RECORDED means a row
# exists. Every SKIPPED_* value means: no occurrence was written, and the
# answer proceeds regardless.
RECORDED = "recorded"
SKIPPED_GUEST = "skipped_guest"
SKIPPED_NOT_CONSENTED = "skipped_not_consented"
SKIPPED_CONSENT_UNREADABLE = "skipped_consent_unreadable"
SKIPPED_KEY_UNAVAILABLE = "skipped_key_unavailable"
SKIPPED_WRITE_FAILED = "skipped_write_failed"

# The subset that means "analytics is degraded," as distinct from the two
# ordinary, non-degraded reasons for not recording (a guest, or an account
# that simply has not consented). Callers use this to tell a real outage
# apart from normal traffic -- the distinction the 2026-08-31 smoke could
# not make from the data alone.
DEGRADED_OUTCOMES = frozenset(
    (SKIPPED_CONSENT_UNREADABLE, SKIPPED_KEY_UNAVAILABLE, SKIPPED_WRITE_FAILED)
)


def _consent_permits_recording(supabase, user_id: str) -> Optional[bool]:
    """True only on an affirmative, current-version acknowledgement.
    False when the account is readable but has not consented (or has
    withdrawn). None when consent state could not be determined at all.

    None and False are both "do not record" -- they are kept distinct only
    so a genuine outage is reportable separately from ordinary
    non-consent. Protection 1 lives here: there is no branch on which an
    exception yields True."""
    try:
        status = consent_service.get_consent_status(supabase, user_id)
    except Exception:
        logger.warning(
            "search-analytics: consent state unreadable -- not recording, serving the answer anyway",
            exc_info=True,
        )
        return None
    return bool(status["acknowledged"]) and not bool(status["needs_acknowledgment"])


def _deletable_subject_key(supabase, user_id: str):
    """The (key, version) to write under, or None if we cannot guarantee a
    later withdrawal would find it.

    Protection 2 lives here. consent.get_or_rotate_subject_key() returns
    only after the key it hands back is recorded in the account's consent
    row -- either it was already current, or the rotation UPDATE (which
    also preserves the outgoing key in retired_subject_keys) succeeded. So
    a returned key is a deletable key, and any exception -- including the
    rotation UPDATE failing halfway, and including MissingHmacSecretError
    on a version bump -- means we do not write.

    Reused rather than reimplemented on purpose: forking the rotation
    logic here would be a second place that decides what withdraw() can
    find, and the two would drift."""
    try:
        key_state = consent_service.get_or_rotate_subject_key(supabase, user_id)
    except Exception:
        logger.warning(
            "search-analytics: subject key unavailable or not provably deletable -- not recording, serving the answer anyway",
            exc_info=True,
        )
        return None
    return key_state


def _stamp_degraded(db_factory, job_id, outcome: str) -> bool:
    """Mark this job's row as one whose analytics recording was skipped by a
    FAILURE (migration 095). Returns True if the marker landed.

    This is the trace Alex required: without it, "analytics was down for
    these hours" and "nobody searched during these hours" are the same
    observation -- the exact ambiguity that cost a phase of work in the
    2026-08-31 smoke. An answer_jobs row is guaranteed to exist by now
    (jobs.enqueue already succeeded over this same direct-Postgres
    connection), so the marker always has somewhere to land.

    Stamps the outcome only. No question, no fingerprint, no subject key --
    and answer_jobs has no user_id column, so this creates no
    account-to-search linkage. It must never reconstruct the occurrence the
    privacy protections just refused to write.

    Best-effort by construction, and last in the chain: if this fails there
    is nothing further to fall back to except the log line, and it must
    never be the reason an answer is lost."""
    try:
        db = db_factory()
    except Exception:
        logger.warning(
            "analytics_degraded outcome=%s job_id=%s marker=unwritten "
            "(no connection) -- log line is the only trace of this one",
            outcome, job_id, exc_info=True,
        )
        return False

    try:
        def _write(conn):
            with dict_cursor(conn) as cur:
                cur.execute(
                    "UPDATE answer_jobs SET analytics_outcome = %s WHERE id = %s",
                    (outcome, job_id),
                )

        db.run(_write)
        return True
    except Exception:
        logger.warning(
            "analytics_degraded outcome=%s job_id=%s marker=unwritten "
            "-- log line is the only trace of this one",
            outcome, job_id, exc_info=True,
        )
        return False
    finally:
        try:
            db.close()
        except Exception:
            logger.warning("search-analytics: marker connection close failed", exc_info=True)


def record_search_occurrence(
    db_factory,
    supabase,
    *,
    user_id: Optional[str],
    submission_id: Optional[str],
    job_id,
    question: str,
) -> str:
    """Record one occurrence if -- and only if -- it is permitted and
    provably deletable. Returns an outcome string. NEVER raises.

    A degraded outcome additionally leaves a marker on the job row, so the
    gap is visible afterwards rather than silent.

    `db_factory` is a zero-arg callable returning a Db (injected rather
    than imported so a test can substitute one without patching module
    globals)."""
    outcome = _resolve_and_write(
        db_factory, supabase,
        user_id=user_id, submission_id=submission_id,
        job_id=job_id, question=question,
    )
    if outcome in DEGRADED_OUTCOMES:
        _stamp_degraded(db_factory, job_id, outcome)
    return outcome


def _resolve_and_write(
    db_factory,
    supabase,
    *,
    user_id: Optional[str],
    submission_id: Optional[str],
    job_id,
    question: str,
) -> str:
    if not user_id:
        return SKIPPED_GUEST

    permitted = _consent_permits_recording(supabase, user_id)
    if permitted is None:
        return SKIPPED_CONSENT_UNREADABLE
    if not permitted:
        return SKIPPED_NOT_CONSENTED

    key_state = _deletable_subject_key(supabase, user_id)
    if key_state is None:
        return SKIPPED_KEY_UNAVAILABLE

    try:
        db = db_factory()
    except Exception:
        logger.warning(
            "search-analytics: could not open a connection for the occurrence write -- not recording, serving the answer anyway",
            exc_info=True,
        )
        return SKIPPED_WRITE_FAILED

    try:
        create_occurrence(
            db,
            submission_id=submission_id or str(uuid.uuid4()),
            job_id=job_id,
            origin="user",
            subject_key=key_state["subject_key"],
            subject_key_version=key_state["subject_key_version"],
            question=question,
        )
        return RECORDED
    except Exception:
        # Deliberately broader than OccurrenceWriteFailedError. The old
        # inline code caught only that, so anything else -- a timeout, a
        # driver-level error raised outside create_occurrence's own wrap --
        # escaped as a 500. Nothing analytics can raise may reach the
        # caller.
        logger.warning(
            "search-analytics: occurrence write failed -- not recording, serving the answer anyway",
            exc_info=True,
        )
        return SKIPPED_WRITE_FAILED
    finally:
        try:
            db.close()
        except Exception:
            logger.warning("search-analytics: connection close failed", exc_info=True)
