"""Reader-facing quote resolution (Project 3 wiring, 2026-08-06).

A separate, un-gated route from backend/app/routers/quotes.py -- every route
there carries Depends(require_admin_role), because that router is the
CURATION surface (create/approve/revoke), where the admin identity is itself
part of what migration 082's trigger enforces. This router is the DELIVERY
surface: turning an id an answer already carries into text + topic at render
time. A guest already reads a full chat answer with no auth at all, so a
quote_id embedded in that same answer's meta is not privileged information --
gating this endpoint would just break the guest half of the product for no
real protection.

Calls quotes_service.resolve_quote() -- the SAME single resolution point the
admin route's own /quotes/{quote_id}/resolve calls -- never a second query
against `quotes.quote_text`. A revoked or draft quote resolves to nothing
here exactly as it does there (CLAUDE.md Settled decision #16/#17).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.supabase import get_supabase
from app.services import quotes as quotes_service

router = APIRouter()

# Small defensive bound -- an answer carries at most MAX_QUOTES_PER_ANSWER (3,
# services/quotes.py) ids; this just stops an arbitrary-length list turning
# into an arbitrary number of DB round-trips from an unauthenticated caller.
_MAX_IDS_PER_REQUEST = 10


class ResolveQuotesRequest(BaseModel):
    quote_ids: List[str]


@router.post("/resolve")
async def resolve_quotes(body: ResolveQuotesRequest):
    db = get_supabase()
    resolved = []
    for quote_id in body.quote_ids[:_MAX_IDS_PER_REQUEST]:
        result = quotes_service.resolve_quote(db, quote_id)
        if result is not None:
            resolved.append(result)
    return {"quotes": resolved}
