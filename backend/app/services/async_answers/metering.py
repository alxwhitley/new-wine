"""Usage-limit metering for the async submit path (Stage 2, Project 1).

MIRRORS chat.py's fail-closed query metering (guest + authenticated user), calling
the SAME atomic RPCs (`increment_guest_query` / `increment_user_query`). Kept as a
deliberate copy rather than a shared import so chat.py's LIVE serving path stays
byte-identical this pre-cutover session -- the same convention producer.py already
follows for chat.py's retrieval/generation orchestration. DRIFT POINT: any change
to chat.py's metering (limits, RPC names, fail-closed posture) must be applied here
too; unify at full cutover.

Every submission meters INDEPENDENTLY, keyed on the CALLER'S identity (user_id or
anon_id) -- never on the answer's dedup key. The router calls this BEFORE
jobs.enqueue(), so a single-flight/reuse collapse (which shares one *generation*)
never collapses *metering*: two users asking the identical question at the same
instant are each counted, though only one generation runs.

Fails CLOSED exactly as chat.py does: any metering fault raises 503 rather than
letting an unmetered request through.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import datetime
import logging
from typing import Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Mirrors chat.GUEST_QUERY_LIMIT. If chat.py's value changes, change it here too
# (documented drift point above).
GUEST_QUERY_LIMIT = 6


def enforce_query_limit(
    supabase,
    user_id: Optional[str],
    anon_id: Optional[str],
    client_ip: Optional[str],
) -> Dict[str, object]:
    """Meter one submission against the caller's usage limit.

    Returns the usage meta dict for an authenticated user ({"used","limit",
    "week_start"}) or {} for a guest. Raises HTTPException(400/429/503) with the
    SAME detail shapes chat.py raises, so the existing frontend error handling
    (guest_limit_reached / weekly_limit_reached) works unchanged. Fails CLOSED.
    """
    if not user_id:
        # Guest limit. Metering fails CLOSED: any exception blocks the request
        # (503) rather than letting it through unmetered -- a Supabase blip must
        # not silently disable the guest query cap. (Mirror of chat.py.)
        if not anon_id:
            raise HTTPException(status_code=400, detail="anon_id required for guest users")
        try:
            result = supabase.rpc("increment_guest_query", {
                "p_anon_id": anon_id,
                "p_ip_address": client_ip,
            }).execute()
            count = result.data if isinstance(result.data, int) else 0
            logger.info("[GUEST][async] anon_id=%s ip=%s query_count=%s", anon_id, client_ip, count)
            # count == -1 is the RPC's sentinel for "too many new guest sessions
            # from this IP recently" (migration 057) -- same user-facing message
            # as the ordinary limit, so an abuser rotating anon_id gets no signal
            # distinguishing the two reasons.
            if count < 0 or count > GUEST_QUERY_LIMIT:
                raise HTTPException(status_code=429, detail="guest_limit_reached")
        except HTTPException:
            raise
        except Exception:
            logger.exception("[async] Guest query count check failed for anon_id=%s -- failing closed", anon_id)
            raise HTTPException(status_code=503, detail="metering_unavailable")
        return {}

    # Authenticated user weekly limit -- atomic RPC, limit from the per-user row
    # (migration 039). Fails CLOSED. (Mirror of chat.py.)
    try:
        result = supabase.rpc("increment_user_query", {"p_user_id": user_id}).execute()
        row = result.data[0] if result.data else {}
        count = int(row.get("query_count", 0))
        weekly_limit = int(row.get("weekly_limit", 50))
        week_start_str = str(row.get("week_start", ""))
        allowed = bool(row.get("allowed", True))
        logger.info("[USER][async] user_id=%s weekly_count=%d limit=%d allowed=%s", user_id, count, weekly_limit, allowed)
        if not allowed:
            # RPC did not increment -- count is already AT the limit, not over it.
            week_start_date = (
                datetime.date.fromisoformat(week_start_str) if week_start_str else datetime.date.today()
            )
            next_monday = week_start_date + datetime.timedelta(days=7)
            raise HTTPException(status_code=429, detail={
                "error": "weekly_limit_reached",
                "used": count,
                "limit": weekly_limit,
                "week_start": week_start_str,
                "resets": next_monday.isoformat(),
            })
        return {"used": count, "limit": weekly_limit, "week_start": week_start_str}
    except HTTPException:
        raise
    except Exception:
        logger.exception("[async] User weekly query count check failed for user_id=%s -- failing closed", user_id)
        raise HTTPException(status_code=503, detail="metering_unavailable")
