"""Retention purge for answer_jobs' question/answer content.

Packet 4, Task 4.4 of the 2026-08-28 back-to-back completion queue.
Alex's explicit retention decision that day: answer_jobs' raw question and
answer text (plus `messages`, the multi-turn context sent to the model,
which can itself contain prior turns' question/answer wording) is disposable
after 90 days -- it exists for near-term debugging and reuse/single-flight,
not as a permanent record (that's conversations/messages for an
authenticated user's own visible history, which Alex explicitly decided
stays until account deletion, not auto-expired). Numeric/instrumentation
columns (cost_usd, token counts, outcome, timing) are NOT touched -- their
aggregate value for cost/performance analysis is exactly what this
retention decision keeps.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

RETENTION_DAYS = 90

# answer_jobs.question is NOT NULL (migration 078) -- a sentinel string,
# not NULL, both marks a row purged and is what the idempotency guard
# below checks against.
_PURGED_QUESTION_SENTINEL = "[purged]"


def purge_expired_answer_job_content(supabase, now_iso: Optional[str] = None) -> int:
    """Purges question/answer/messages on every answer_jobs row older than
    RETENTION_DAYS whose content hasn't already been purged. Idempotent: a
    second call in a row purges nothing new, since the WHERE clause excludes
    rows already purged. Numeric/instrumentation columns are untouched."""
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    result = (
        supabase.table("answer_jobs")
        .update({
            "question": _PURGED_QUESTION_SENTINEL,
            "answer": None,
            "messages": [],
        })
        .lt("created_at", cutoff.isoformat())
        .neq("question", _PURGED_QUESTION_SENTINEL)
        .execute()
    )
    return len(result.data or [])
