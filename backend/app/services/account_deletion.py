"""Account deletion orchestrator.

Implements the design approved 2026-08-28
(docs/audits/2026-08/b4_account_deletion_design_2026-08-28.md, Packet 4
Task 4.2 of the back-to-back completion queue). Submitting a deletion
request (backend/app/routers/account.py's existing POST /delete-request)
still only logs a row -- nothing here runs until an admin calls resolve,
which is this module's entry point, resolve_deletion_request().

Order of operations (see the design doc's Section 2 for the full
reasoning):
  1. Clear the three still-NO-ACTION actor FKs that would otherwise block
     the Auth API delete (migration 090 already fixed the other four
     tables to SET NULL automatically).
  2. Purge search-analytics history via the existing, unforked
     consent.withdraw() -- these two tables have no FK to auth.users at
     all, so the Auth API delete cannot reach them.
  3. Call the Supabase Admin API to delete the auth.users row. Every
     CASCADE/SET NULL constraint in the schema fires atomically at the
     Postgres level as a consequence -- no app code needed for those rows.
  4. Reconcile: re-query every owned-data table directly and confirm zero
     rows remain. A successful Admin API call alone is never sufficient to
     call this resolved.
  5. Write exactly one row to deletion_audit_log (migration 094) -- the
     only record that survives, since deletion_requests itself cascades
     away with the user it was about.

Idempotent: calling this twice on an already-deleted account (a retry
after a 'failed' outcome, e.g. one that failed at the Admin API network
call) is safe -- steps 1-2 are no-ops on an account with nothing left to
clear, and a "user not found" from the Admin API is treated as already
done rather than a fresh failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from supabase_auth.errors import AuthApiError

from app.services.async_answers.db import dict_cursor
from app.services.search_analytics.consent import withdraw as withdraw_analytics_consent

logger = logging.getLogger(__name__)

# Tables whose FK to auth.users is still NO ACTION (nullable actor columns
# recording who performed an admin-adjacent action on someone else's row --
# migration 090 already converted the other four affected tables to SET
# NULL automatically; these three still need an explicit clear here).
_NO_ACTION_ACTOR_CLEARS = (
    ("user_roles", "granted_by"),
    ("contributor_requests", "reviewed_by"),
    ("quote_verification_log", "submitted_by"),
)

# Tables reconciliation re-queries directly by user_id/submitted_by after
# the Admin API delete, to prove the cascade actually emptied them rather
# than assuming a successful API call was sufficient. conversations stands
# in for messages too (messages has no user_id column of its own -- it
# cascades from conversations via conversation_id, confirmed in
# conversation_store.py).
_RECONCILE_TABLES = (
    ("conversations", "user_id"),
    ("saved_words", "user_id"),
    ("study_pins", "user_id"),
    ("user_usage", "user_id"),
    ("user_roles", "user_id"),
    ("contributor_requests", "user_id"),
    ("source_ingest_queue", "submitted_by"),
    ("analytics_consent", "user_id"),
)


class DeletionFailure(RuntimeError):
    """Raised ONLY for a failure that happens strictly before the Auth API
    delete succeeds -- the deletion_requests row is guaranteed to still
    exist at that point (it CASCADEs away the moment the account is
    actually deleted), so the caller records status='failed' with str(this)
    as failure_reason directly on it and leaves the request retryable.

    A failure discovered AFTER the Auth API delete already succeeded (i.e.
    reconciliation itself finds a remaining row) is NOT raised this way --
    deletion_requests no longer exists to update at that point. See
    resolve_deletion_request()'s return value instead, whose own `outcome`
    field distinguishes 'resolved' from that later kind of 'failed'."""


def _clear_no_action_actor_columns(conn, user_id: str) -> None:
    with dict_cursor(conn) as cur:
        cur.execute(
            "UPDATE user_roles SET granted_by = NULL WHERE granted_by = %s", (user_id,)
        )
        cur.execute(
            "UPDATE contributor_requests SET reviewed_by = NULL WHERE reviewed_by = %s",
            (user_id,),
        )
        cur.execute(
            "UPDATE quote_verification_log SET submitted_by = NULL WHERE submitted_by = %s",
            (user_id,),
        )


def _delete_auth_user(supabase, user_id: str) -> bool:
    """Returns True if this call actually deleted the account, False if it
    was already gone (idempotent retry case). Raises DeletionFailure for
    any other Admin API error."""
    try:
        supabase.auth.admin.delete_user(user_id)
        return True
    except AuthApiError as exc:
        status = getattr(exc, "status", None)
        if status == 404:
            return False
        raise DeletionFailure(
            "Auth API delete_user failed: status=%s message=%s" % (status, exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001 -- any other failure is a real, reportable failure
        raise DeletionFailure("Auth API delete_user failed: %s" % exc) from exc


def _reconcile(conn, user_id: str, purged_subject_keys: list[str]) -> dict[str, int]:
    """Directly re-query every owned-data table this account could still
    appear in. Returns the per-table counts (all must be zero); the caller
    decides pass/fail so the full picture is always recorded, not just a
    boolean."""
    counts: dict[str, int] = {}
    with dict_cursor(conn) as cur:
        for table, column in _RECONCILE_TABLES:
            cur.execute(
                "SELECT count(*) AS n FROM %s WHERE %s = %%s" % (table, column),
                (user_id,),
            )
            counts[table] = cur.fetchone()["n"]

        if purged_subject_keys:
            cur.execute(
                "SELECT count(*) AS n FROM search_occurrences WHERE subject_key = ANY(%s)",
                (purged_subject_keys,),
            )
            counts["search_occurrences"] = cur.fetchone()["n"]
        else:
            counts["search_occurrences"] = 0
    return counts


def _get_analytics_subject_keys(supabase, user_id: str) -> list[str]:
    """Read the current + retired subject keys before withdraw() runs, so
    reconciliation has something concrete to re-check afterward -- once the
    auth.users row is gone, analytics_consent (CASCADE) is gone with it and
    this can no longer be looked up."""
    result = (
        supabase.table("analytics_consent")
        .select("subject_key, retired_subject_keys")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return []
    row = result.data[0]
    keys = [row["subject_key"]] if row.get("subject_key") else []
    keys.extend(
        entry.get("key")
        for entry in (row.get("retired_subject_keys") or [])
        if entry.get("key")
    )
    return keys


def resolve_deletion_request(
    db: Any,
    supabase: Any,
    request_id: str,
    user_id: str,
    email: str,
    requested_at: datetime,
    admin_id: str,
) -> dict[str, Any]:
    """Perform a real, reconciled account deletion.

    Returns the deletion_audit_log row to insert -- for BOTH outcomes, once
    the Auth API delete has actually succeeded (or was already gone),
    because deletion_requests cascades away the moment that happens and
    there is nowhere else left to record a failure discovered afterward
    (e.g. reconciliation finding a remaining row). Check the returned
    dict's `outcome` field ('resolved' or 'failed').

    Raises DeletionFailure only for a failure strictly BEFORE that point --
    clearing the NO ACTION actor columns, purging analytics history, or the
    Auth API call itself failing -- where deletion_requests is guaranteed
    to still exist for the caller to update directly instead."""
    subject_keys = _get_analytics_subject_keys(supabase, user_id)

    def _pre_delete_steps(conn):
        _clear_no_action_actor_columns(conn, user_id)

    db.run(_pre_delete_steps)

    if subject_keys:
        withdraw_analytics_consent(db, supabase, user_id)

    deleted_now = _delete_auth_user(supabase, user_id)
    if not deleted_now:
        logger.info(
            "resolve_deletion_request: user_id=%s already deleted (idempotent retry)",
            user_id,
        )

    # From here on the account is gone (or already was) -- deletion_requests
    # has cascaded away. Any further problem is recorded in
    # deletion_audit_log, never raised for the caller to write to a row
    # that no longer exists.
    def _reconcile_step(conn):
        return _reconcile(conn, user_id, subject_keys)

    counts = db.run(_reconcile_step)
    remaining = {table: n for table, n in counts.items() if n}
    resolved_at = datetime.now(timezone.utc)

    base = {
        "original_request_id": request_id,
        "deleted_user_id": user_id,
        "email": email,
        "requested_at": requested_at.isoformat(),
        "resolved_at": resolved_at.isoformat(),
        "resolved_by": admin_id,
        "reconciliation": counts,
    }
    if remaining:
        return {
            **base,
            "outcome": "failed",
            "failure_reason": (
                "Reconciliation found remaining rows after Auth API delete: %s" % remaining
            ),
        }
    return {**base, "outcome": "resolved", "failure_reason": None}
