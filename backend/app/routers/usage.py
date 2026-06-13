from __future__ import annotations

import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_optional_user
from app.db.supabase import get_supabase

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_usage(user_id: Optional[str] = Depends(get_optional_user)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    db = get_supabase()
    try:
        result = db.rpc("get_user_usage", {"p_user_id": user_id}).execute()
        row = result.data[0] if result.data else {}
        count = int(row.get("query_count", 0))
        limit = int(row.get("weekly_limit", 50))
        week_start_str = str(row.get("week_start", ""))

        if week_start_str:
            week_start_date = datetime.date.fromisoformat(week_start_str)
        else:
            # Fallback: compute current Monday
            today = datetime.date.today()
            week_start_date = today - datetime.timedelta(days=today.weekday())

        next_monday = week_start_date + datetime.timedelta(days=7)

        return {
            "used": count,
            "limit": limit,
            "week_start": week_start_date.isoformat(),
            "resets": next_monday.isoformat(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to fetch usage for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to fetch usage")
