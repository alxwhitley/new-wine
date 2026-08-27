"""Consent identity: acknowledgment, status, and withdrawal for the
search-analytics ledger. No question, topic, or answer data ever touches
this module -- it only ever reads/writes analytics_consent.

Uses the standard service-role supabase-py client (same convention as
account.py) -- this is low-volume, simple CRUD, unlike the high-volume
occurrence writes in occurrences.py, which need direct-Postgres
ON CONFLICT semantics.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from .subject_key import CURRENT_SUBJECT_KEY_VERSION, derive_subject_key

CURRENT_POLICY_VERSION = "v1"

POLICY_COPY = (
    "During this private beta, Rhemata tracks the topics you search so we "
    "can understand what material is most needed. When Rhemata says it "
    "does not have enough material, the wording of that question may be "
    "stored after obvious personal details are removed. Your name and "
    "email are not shown in analytics. Open gap wording is deleted 30 "
    "days after the gap is resolved. Please do not include sensitive "
    "personal information in your questions."
)


def _get_row(supabase, user_id: str) -> Optional[dict]:
    result = (
        supabase.table("analytics_consent")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_consent_status(supabase, user_id: str) -> Dict[str, object]:
    row = _get_row(supabase, user_id)
    if row is None or row.get("withdrawn_at"):
        return {
            "acknowledged": False,
            "policy_version": None,
            "current_policy_version": CURRENT_POLICY_VERSION,
            "needs_acknowledgment": True,
            "policy_copy": POLICY_COPY,
        }
    current = row.get("policy_version") == CURRENT_POLICY_VERSION
    return {
        "acknowledged": True,
        "policy_version": row.get("policy_version"),
        "current_policy_version": CURRENT_POLICY_VERSION,
        "needs_acknowledgment": not current,
        "policy_copy": POLICY_COPY,
    }


def acknowledge(supabase, user_id: str) -> None:
    """Idempotent upsert: acknowledging the current version again is a
    no-op success, never a duplicate row or an error."""
    existing = _get_row(supabase, user_id)
    now = datetime.now(timezone.utc).isoformat()
    if existing and existing.get("policy_version") == CURRENT_POLICY_VERSION and not existing.get("withdrawn_at"):
        return
    subject_key = derive_subject_key(user_id, CURRENT_SUBJECT_KEY_VERSION)
    if existing:
        supabase.table("analytics_consent").update({
            "policy_version": CURRENT_POLICY_VERSION,
            "acknowledged_at": now,
            "withdrawn_at": None,
            "subject_key": subject_key,
            "subject_key_version": CURRENT_SUBJECT_KEY_VERSION,
            "updated_at": now,
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("analytics_consent").insert({
            "user_id": user_id,
            "policy_version": CURRENT_POLICY_VERSION,
            "acknowledged_at": now,
            "subject_key": subject_key,
            "subject_key_version": CURRENT_SUBJECT_KEY_VERSION,
        }).execute()


def withdraw(db, supabase, user_id: str) -> None:
    """Marks consent withdrawn and deletes every search_occurrences /
    search_gap_details row tied to any subject key this account has ever
    held (current + retired), so withdrawal removes analytics history, not
    just future collection."""
    row = _get_row(supabase, user_id)
    if row is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    keys = [row["subject_key"]] + [
        entry.get("key") for entry in (row.get("retired_subject_keys") or [])
        if entry.get("key")
    ]

    def _delete(conn):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(conn) as cur:
            for key in keys:
                cur.execute("DELETE FROM search_occurrences WHERE subject_key = %s", (key,))

    db.run(_delete)

    supabase.table("analytics_consent").update({
        "withdrawn_at": now, "updated_at": now,
    }).eq("user_id", user_id).execute()
