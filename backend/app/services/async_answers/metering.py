"""Usage-limit metering for async_chat.py's /submit route -- the sole answer
path's entry point.

HISTORY: originally built for the async path alone, kept as a deliberate
copy of chat.py's inline metering block so chat.py's then-live serving path
stayed byte-identical pre-cutover (a read-only diff confirmed the two blocks
were byte-for-byte identical in behavior -- same RPCs, same params, same
constants, same error shapes). Consolidated 2026-08-07 (mirror-unification
batch 3): chat.py's `chat()` route was changed to call this function
directly instead of keeping its own duplicate, making this the single
metering implementation for however many answer paths existed. chat.py
itself was then deleted entirely (2026-08-07, batch 4) -- this is now called
from exactly one place, async_chat.py's /submit, not "both paths." Kept as
its own module (not folded into answer_toolbox.py) since nothing else needs
it. `GUEST_QUERY_LIMIT` below has exactly one definition in the codebase.

Every submission meters INDEPENDENTLY, keyed on the CALLER'S identity (user_id or
anon_id) -- never on the answer's dedup key. async_chat.py's /submit calls this
BEFORE jobs.enqueue(), so a single-flight/reuse collapse (which shares one
*generation*) never collapses *metering*: two users asking the identical
question at the same instant are each counted, though only one generation runs.
The call is wrapped in `run_in_threadpool` since /submit is an `async def` route.

Fails CLOSED: any metering fault raises 503 rather than letting an unmetered
request through.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import datetime
import logging
from typing import Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Single definition, repo-wide (consolidated 2026-08-07; chat.py, the only
# other place this was ever duplicated, is deleted).
GUEST_QUERY_LIMIT = 6


def enforce_query_limit(
    supabase,
    user_id: Optional[str],
    anon_id: Optional[str],
    client_ip: Optional[str],
) -> Dict[str, object]:
    """Meter one submission against the caller's usage limit.

    Returns the usage meta dict for an authenticated user ({"used","limit",
    "week_start"}) or {} for a guest. Raises HTTPException(400/429/503) with a
    stable detail shape (guest_limit_reached / weekly_limit_reached /
    metering_unavailable) that the frontend's existing error handling matches.
    Called from async_chat.py's /submit route -- the only answer path there
    is (chat.py, the only other caller this ever had, is deleted). Fails
    CLOSED.
    """
    if not user_id:
        # Guest limit. Metering fails CLOSED: any exception blocks the request
        # (503) rather than letting it through unmetered -- a Supabase blip must
        # not silently disable the guest query cap.
        if not anon_id:
            raise HTTPException(status_code=400, detail="anon_id required for guest users")
        try:
            result = supabase.rpc("increment_guest_query", {
                "p_anon_id": anon_id,
                "p_ip_address": client_ip,
            }).execute()
            count = result.data if isinstance(result.data, int) else 0
            # Packet 4, Task 4.4 (2026-08-28): this used to log the raw
            # anon_id and raw client IP on every guest request -- removed;
            # query_count is the only value with routine diagnostic value
            # here, and the RPC call itself (not this log line) is the
            # actual place anon_id/client_ip need to be used.
            logger.info("[GUEST] query_count=%s", count)
            # count == -1 is the RPC's sentinel for "too many new guest sessions
            # from this IP recently" (migration 057) -- same user-facing message
            # as the ordinary limit, so an abuser rotating anon_id gets no signal
            # distinguishing the two reasons.
            if count < 0 or count > GUEST_QUERY_LIMIT:
                raise HTTPException(status_code=429, detail="guest_limit_reached")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Guest query count check failed -- failing closed")
            raise HTTPException(status_code=503, detail="metering_unavailable")
        return {}

    # Authenticated user weekly limit -- atomic RPC, limit from the per-user row
    # (migration 039). Fails CLOSED.
    try:
        result = supabase.rpc("increment_user_query", {"p_user_id": user_id}).execute()
        row = result.data[0] if result.data else {}
        count = int(row.get("query_count", 0))
        weekly_limit = int(row.get("weekly_limit", 50))
        week_start_str = str(row.get("week_start", ""))
        allowed = bool(row.get("allowed", True))
        logger.info("[USER] user_id=%s weekly_count=%d limit=%d allowed=%s", user_id, count, weekly_limit, allowed)
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
        logger.exception("User weekly query count check failed for user_id=%s -- failing closed", user_id)
        raise HTTPException(status_code=503, detail="metering_unavailable")
