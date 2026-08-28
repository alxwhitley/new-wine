"""Automatic retention purge: 30 days after a gap is resolved, its
redacted question text is deleted. Anonymous counts and the resolution
date are untouched -- only the wording column is nulled.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def purge_expired_gap_text(supabase, now_iso: Optional[str] = None) -> int:
    """Nulls redacted_question on every resolved gap whose text_purge_at
    has passed and whose text hasn't already been purged. Idempotent: a
    second call in a row purges nothing new, since the WHERE clause
    excludes rows that are already NULL."""
    now = now_iso or datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("search_gap_details")
        .update({"redacted_question": None, "purged_at": now})
        .eq("status", "resolved")
        .lte("text_purge_at", now)
        .not_.is_("redacted_question", "null")
        .execute()
    )
    return len(result.data or [])
