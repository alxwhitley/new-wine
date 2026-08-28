"""Admin-only search-analytics dashboard API: summary, per-topic gap
listing, retest, resolve. Every route is require_admin_role-gated (same
posture as quotes.py's admin-only tooling).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin_role
from app.db.supabase import get_supabase
from app.services.async_answers.db import Db
from app.services.async_answers.producer import current_policy
from app.services.search_analytics import aggregation, gaps as gaps_service

router = APIRouter()


@router.get("/summary")
async def get_summary_route(days: int = 30, admin_id: str = Depends(require_admin_role)):
    supabase = get_supabase()
    summary = aggregation.get_summary(supabase, days=days)
    topics = aggregation.get_topic_bars(supabase, days=days)
    return {"summary": summary, "topics": topics}


@router.get("/topics/{topic_key}/gaps")
async def list_gaps_route(
    topic_key: str,
    cursor: Optional[str] = None,
    admin_id: str = Depends(require_admin_role),
):
    supabase = get_supabase()
    return gaps_service.list_gaps_for_topic(supabase, topic_key, cursor=cursor)


@router.post("/gaps/{gap_id}/retests")
async def create_retest_route(gap_id: str, admin_id: str = Depends(require_admin_role)):
    supabase = get_supabase()
    db = Db()
    try:
        policy = current_policy(supabase)
        try:
            result = gaps_service.create_retest(
                db,
                supabase,
                gap_id=gap_id,
                evidence_version=policy["evidence_version"],
                prompt_version=policy["prompt_version"],
                policy_version=policy["policy_version"],
            )
        except gaps_service.GapNotFoundError:
            raise HTTPException(status_code=404, detail="gap_not_found")
    finally:
        db.close()
    return result


@router.patch("/gaps/{gap_id}")
async def resolve_gap_route(gap_id: str, admin_id: str = Depends(require_admin_role)):
    supabase = get_supabase()
    try:
        return gaps_service.resolve_gap(supabase, gap_id)
    except gaps_service.GapNotFoundError:
        raise HTTPException(status_code=404, detail="gap_not_found")
    except gaps_service.GapNotRetestedError:
        raise HTTPException(status_code=400, detail="gap_not_yet_retested")
