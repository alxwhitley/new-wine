"""Admin-facing corpus-gap operations: list, retest, resolve.

Retest reuses the exact same enqueue mechanism the public chat submit path
uses (jobs.enqueue) plus occurrences.create_occurrence with
origin="admin_retest" -- never a parallel, divergent answer path. Resolve
is intentionally NOT automatic: it always requires an admin's explicit
PATCH, gated on the linked retest's outcome already being known and not
no_material.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from .occurrences import create_occurrence

GAP_TEXT_RETENTION_DAYS = 30


class GapNotFoundError(Exception):
    pass


class GapNotRetestedError(Exception):
    """Raised when resolving a gap whose linked retest hasn't succeeded
    (or hasn't been run at all) yet."""


def list_gaps_for_topic(supabase, topic: str, cursor: Optional[str] = None, page_size: int = 20) -> Dict[str, object]:
    query = (
        supabase.table("search_gap_details")
        .select("*, search_occurrences!inner(primary_topic)")
        .eq("search_occurrences.primary_topic", topic)
        .order("created_at", desc=True)
        .limit(page_size + 1)
    )
    if cursor:
        query = query.lt("created_at", cursor)
    result = query.execute()
    rows = result.data or []
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = rows[-1]["created_at"] if (has_more and rows) else None
    return {"gaps": rows, "next_cursor": next_cursor}


def _get_gap(supabase, gap_id: str) -> dict:
    result = supabase.table("search_gap_details").select("*").eq("id", gap_id).limit(1).execute()
    if not result.data:
        raise GapNotFoundError(gap_id)
    return result.data[0]


def create_retest(
    db,
    supabase,
    *,
    gap_id: str,
    evidence_version: str,
    prompt_version: str,
    policy_version: str,
) -> Dict[str, object]:
    gap = _get_gap(supabase, gap_id)
    question = gap.get("redacted_question")
    if not question:
        raise GapNotFoundError("gap %s has no retestable text (purged or redaction_failed)" % gap_id)

    from app.services.async_answers import jobs as jobs_module

    job_result = jobs_module.enqueue(
        db,
        question=question,
        evidence_version=evidence_version,
        prompt_version=prompt_version,
        policy_version=policy_version,
        filters={},
        messages=[],
        topics_established={},
        idempotency_key=None,
        cfg=None,
    )
    job = job_result["job"]

    occurrence_id = create_occurrence(
        db,
        submission_id="admin-retest-%s" % uuid.uuid4(),
        job_id=job["id"],
        origin="admin_retest",
        subject_key=None,
        subject_key_version=None,
        question=question,
    )

    supabase.table("search_gap_details").update({
        "retest_occurrence_id": occurrence_id,
        "retest_outcome": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", gap_id).execute()

    return {"job_id": job["id"], "occurrence_id": occurrence_id}


def resolve_gap(supabase, gap_id: str) -> Dict[str, object]:
    gap = _get_gap(supabase, gap_id)
    retest_outcome = gap.get("retest_outcome")
    if not retest_outcome or retest_outcome == "no_material":
        raise GapNotRetestedError(
            "gap %s cannot be resolved -- linked retest has not succeeded yet (retest_outcome=%r)"
            % (gap_id, retest_outcome)
        )
    now = datetime.now(timezone.utc)
    purge_at = now + timedelta(days=GAP_TEXT_RETENTION_DAYS)
    supabase.table("search_gap_details").update({
        "status": "resolved",
        "resolved_at": now.isoformat(),
        "text_purge_at": purge_at.isoformat(),
        "updated_at": now.isoformat(),
    }).eq("id", gap_id).execute()
    return {"status": "resolved", "resolved_at": now.isoformat(), "text_purge_at": purge_at.isoformat()}
