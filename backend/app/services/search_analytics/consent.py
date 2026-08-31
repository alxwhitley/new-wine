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
    "During this private beta, New Wine tracks the topics you search so we "
    "can understand what material is most needed. When New Wine says it "
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


def _rotate_if_stale(row: dict) -> Dict[str, object]:
    """Given an existing consent row, returns the subject-key fields to
    write: unchanged if already on CURRENT_SUBJECT_KEY_VERSION, or
    advanced with the OLD (version, key) preserved in
    retired_subject_keys if stale.

    2026-08-27 privacy review, Finding 2: a naive overwrite of subject_key/
    subject_key_version on re-acknowledgment silently dropped the old key
    with no record in retired_subject_keys, permanently breaking
    withdraw()'s ability to find and delete occurrences written under a
    pre-rotation key. This is the one place that decision gets made, used
    by both acknowledge() (an existing row, on re-ack) and
    get_or_rotate_subject_key() (lazy catch-up at submission time,
    independent of whether the user is ever prompted to re-acknowledge --
    a key rotation alone does not change policy_version, so
    needs_acknowledgment would never fire for it on its own)."""
    if row["subject_key_version"] >= CURRENT_SUBJECT_KEY_VERSION:
        return {
            "subject_key": row["subject_key"],
            "subject_key_version": row["subject_key_version"],
            "retired_subject_keys": row.get("retired_subject_keys") or [],
        }
    retired = list(row.get("retired_subject_keys") or [])
    retired.append({"version": row["subject_key_version"], "key": row["subject_key"]})
    return {
        "subject_key": derive_subject_key(row["user_id"], CURRENT_SUBJECT_KEY_VERSION),
        "subject_key_version": CURRENT_SUBJECT_KEY_VERSION,
        "retired_subject_keys": retired,
    }


def acknowledge(supabase, user_id: str) -> None:
    """Idempotent upsert: acknowledging the current version again is a
    no-op success, never a duplicate row or an error."""
    existing = _get_row(supabase, user_id)
    now = datetime.now(timezone.utc).isoformat()
    if existing and existing.get("policy_version") == CURRENT_POLICY_VERSION and not existing.get("withdrawn_at"):
        return
    if existing:
        key_state = _rotate_if_stale(existing)
        supabase.table("analytics_consent").update({
            "policy_version": CURRENT_POLICY_VERSION,
            "acknowledged_at": now,
            "withdrawn_at": None,
            "subject_key": key_state["subject_key"],
            "subject_key_version": key_state["subject_key_version"],
            "retired_subject_keys": key_state["retired_subject_keys"],
            "updated_at": now,
        }).eq("user_id", user_id).execute()
    else:
        subject_key = derive_subject_key(user_id, CURRENT_SUBJECT_KEY_VERSION)
        supabase.table("analytics_consent").insert({
            "user_id": user_id,
            "policy_version": CURRENT_POLICY_VERSION,
            "acknowledged_at": now,
            "subject_key": subject_key,
            "subject_key_version": CURRENT_SUBJECT_KEY_VERSION,
        }).execute()


def get_or_rotate_subject_key(supabase, user_id: str) -> Dict[str, object]:
    """The subject key to use for a NEW occurrence, transparently catching
    up a stale row to the current HMAC version if one has been configured
    since the account last wrote/refreshed its key -- the old (version,
    key) pair is preserved in retired_subject_keys first, so withdraw()
    can still find and delete rows written under it. Callers must have
    already confirmed current-version consent (get_consent_status) before
    calling this -- it does not itself acknowledge anything, only keeps
    the key fresh at the point of use (async_chat.py's /submit)."""
    row = _get_row(supabase, user_id)
    if row is None:
        raise ValueError("no consent row for user_id=%s" % user_id)
    key_state = _rotate_if_stale(row)
    if key_state["subject_key_version"] != row["subject_key_version"]:
        supabase.table("analytics_consent").update({
            "subject_key": key_state["subject_key"],
            "subject_key_version": key_state["subject_key_version"],
            "retired_subject_keys": key_state["retired_subject_keys"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("user_id", user_id).execute()
    return {"subject_key": key_state["subject_key"], "subject_key_version": key_state["subject_key_version"]}


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
