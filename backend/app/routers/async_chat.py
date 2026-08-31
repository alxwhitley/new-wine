"""Async answer path -- HTTP delivery surface.

MOUNTED and LIVE, unconditionally (corrected 2026-08-07, mirror-unification
batch 4 -- this docstring previously described a two-switch gate: an env
ASYNC_ANSWER_ENABLED controlling whether these routes existed in the route
table at all, plus the DB switch below. The env gate was removed this batch,
Alex's explicit decision: main.py mounts this router the same way it mounts
every other router, no conditional -- with chat.py deleted this same batch,
this is the ONLY answer path, and gating whether its routes even exist behind
an env var defaulting to "false" created a way to accidentally end up with
zero answer paths mounted and no visible error. Stale docstrings are exactly
the kind of thing CLAUDE.md Invariant 5 warns not to trust -- keep this
current). One switch remains:

  DB async_answer_config.serving_enabled -- an EMERGENCY PAUSE, not a
  rollback mechanism (corrected 2026-08-07, mirror-unification batch 3,
  Part 3 -- this docstring previously described the frontend "silently
  falling back to the old synchronous /chat path" when this switch is
  off or /mode is unreachable; that fallback was removed the same batch,
  Alex's explicit decision: no fallback of any kind). The frontend no
  longer calls /mode as a router at all -- it calls this path directly
  and treats a 503 async_serving_disabled response (or any network
  failure reaching this router) as a real, user-visible error. Flipping
  this switch off now takes the WHOLE PRODUCT offline for chat answers --
  chat.py's /chat endpoint no longer exists at all (deleted 2026-08-07,
  mirror-unification batch 4), so there is no legacy path to fall back to
  even in principle. The switch itself stays; only its meaning changes,
  from soft rollback to honest kill-switch.

Shape (decision #14): submission and delivery are decoupled from generation.
  POST /async-chat/submit  -> enqueue; returns {job_id, status, reason}. Returns
                              immediately. No client connection owns a worker.
  GET  /async-chat/result/{job_id} -> reconnectable SSE. Because the answer is
                              durable in answer_jobs, a reader who drops and
                              returns just re-reads the job -- reconnection is a
                              GET, not a re-generation. When the job is done the
                              server delivers the ALREADY-VERIFIED answer at once
                              and the CLIENT paces the typewriter reveal (the
                              server never sleeps for pacing, never holds a
                              worker). Retries re-run the accuracy check inside
                              the worker, never here.

Concurrency note for cutover: the result generator uses asyncio.sleep between
polls and offloads the (blocking psycopg2) reads to the threadpool, so a waiting
reader does NOT hold a worker thread for its whole wait -- the ~40-thread
occupancy ceiling the live path hits does not recur here. Not exercised over
HTTP this session; the durable-read property it depends on is proven by
scripts/async_answers_smoke.py.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool

from app.auth import get_optional_user
from app.db.supabase import get_supabase
from app.services import quotes as quotes_service
from app.services.async_answers import conversation_store, jobs
from app.services.async_answers.config import estimate_cost_usd, load_config
from app.services.async_answers.db import Db
from app.services.async_answers.metering import enforce_query_limit
from app.services.async_answers.producer import current_policy
from app.services.search_analytics.recording import (
    DEGRADED_OUTCOMES,
    record_search_occurrence,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class AsyncChatRequest(BaseModel):
    question: str
    messages: List[Dict[str, Any]] = []
    topics_established: Dict[str, int] = {}
    idempotency_key: Optional[str] = None
    # submission_id: analytics-only idempotency key, distinct from
    # idempotency_key above (which dedups the answer_jobs row itself). Two
    # different submission_ids that happen to share one job (single-flight
    # collapse) must still create two separate analytics occurrences --
    # that's why this can never be the same field as idempotency_key.
    submission_id: Optional[str] = None
    # anon_id: guest metering key (mirrors chat.py's ChatRequest.anon_id). Required
    # for guests, ignored for authenticated callers.
    anon_id: Optional[str] = None

    @field_validator("question")
    @classmethod
    def _validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > 1000:
            raise ValueError("question must be 1000 characters or fewer")
        return v


def _sse(data: str) -> str:
    return "data: %s\n\n" % data


def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": str(job["id"]),
        "status": job["status"],
        "outcome": job.get("outcome"),
    }


def _client_ip(http_request: Request) -> Optional[str]:
    """Real client IP behind Railway's edge proxy -- read X-Forwarded-For's
    leftmost entry, exactly as chat.py's _get_client_ip does (uvicorn isn't run
    with --proxy-headers, so request.client.host is the internal proxy)."""
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else None


def _serving_enabled() -> bool:
    """Read the traffic switch fresh for each control-plane request."""
    db = Db()
    try:
        return bool(load_config(db).serving_enabled)
    finally:
        db.close()


@router.get("/mode")
async def mode():
    """Reports the emergency-pause switch (async_answer_config.serving_enabled,
    default OFF) -- an honest kill-switch, not a rollback toggle (corrected
    2026-08-07, mirror-unification batch 3, Part 3: this previously described
    the frontend routing to the async path only when this returned
    async_enabled=true, falling back to the live /chat path otherwise -- that
    routing/fallback behavior was removed the same batch; the frontend no
    longer calls this endpoint at all). Kept as a standalone read-only
    diagnostic/health-check surface (e.g. for future ops tooling), not as
    part of any request path. Reversible with one UPDATE."""
    enabled = await run_in_threadpool(_serving_enabled)
    return {"async_enabled": bool(enabled)}


@router.post("/submit")
async def submit(
    req: AsyncChatRequest,
    http_request: Request,
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Enqueue a question. Idempotent by idempotency_key; single-flight + reuse
    by content. Returns instantly with a job_id to poll/stream.

    The serving switch runs first. Once enabled, metering is fail-closed and keyed
    on the CALLER (user_id / anon_id), BEFORE enqueue's single-flight/reuse collapse
    -- so every accepted submission is counted independently even when several
    submissions share one generation (parity with chat.py)."""
    # Enforce the traffic switch at the trusted boundary. A browser may retain a
    # stale mode=true cache briefly after rollback; direct callers can bypass
    # /mode entirely. Refuse before metering so a disabled-path probe neither
    # consumes quota nor creates work.
    if not await run_in_threadpool(_serving_enabled):
        raise HTTPException(status_code=503, detail="async_serving_disabled")

    supabase = get_supabase()
    client_ip = _client_ip(http_request)

    # Fail-closed usage metering (raises 400/429/503 exactly as chat.py does).
    usage_meta = await run_in_threadpool(
        enforce_query_limit, supabase, user_id, req.anon_id, client_ip
    )

    def _enqueue():
        db = Db()
        try:
            policy = current_policy(supabase)
            cfg = load_config(db)
            return jobs.enqueue(
                db,
                question=req.question,
                evidence_version=policy["evidence_version"],
                prompt_version=policy["prompt_version"],
                policy_version=policy["policy_version"],
                filters=policy["filters"],
                messages=req.messages,
                topics_established=req.topics_established,
                idempotency_key=req.idempotency_key,
                cfg=cfg,
            )
        finally:
            db.close()

    result = await run_in_threadpool(_enqueue)
    if result.get("reason") == "rejected_backpressure":
        raise HTTPException(status_code=503, detail="queue_full")
    job = result["job"]

    # Search-analytics occurrence: one per accepted submission, only for an
    # authenticated account with current-version consent. A guest or a
    # not-yet-consented account is simply not monitored -- no error, no
    # occurrence. Runs AFTER enqueue: it needs job["id"]. origin is always
    # "user" here -- never client-suppliable -- the only other origin,
    # "admin_retest", is written exclusively by the admin retest endpoint
    # calling create_occurrence() directly.
    #
    # B7 (2026-08-31): this whole step is now non-blocking for the answer.
    # record_search_occurrence() never raises -- it returns an outcome and
    # keeps BOTH privacy protections (unknown consent never resolves to
    # "consented"; nothing is written that withdraw() could not delete),
    # changing only the consequence of a refusal from "no answer" to "no
    # row." There is deliberately no try/except here: if this call ever
    # needs one, the contract in recording.py has been broken.
    # docs/audits/2026-08/analytics_answer_coupling_2026-08-31.md
    outcome = await run_in_threadpool(
        record_search_occurrence,
        Db,
        supabase,
        user_id=user_id,
        submission_id=req.submission_id,
        job_id=job["id"],
        question=req.question,
    )
    if outcome in DEGRADED_OUTCOMES:
        logger.warning(
            "search-analytics degraded (%s) -- answer served, occurrence not recorded", outcome
        )

    resp = {"reason": result["reason"], **_public_job(job)}
    if usage_meta:
        resp["usage"] = usage_meta  # authenticated-user weekly usage (parity with chat.py meta.usage)
    return resp


@router.get("/result/{job_id}")
async def result(
    job_id: str,
    http_request: Request,
    poll_interval: float = 1.0,
    timeout: float = 300.0,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Reconnectable delivery. Streams keepalives until the job reaches a
    terminal state, then delivers the whole verified answer + meta at once (the
    client paces the reveal). Reconnecting mid-wait is just another GET.

    For an authenticated reader, the completed exchange is persisted to their
    conversation history here (per-reader, not in the worker -- one shared
    generation still yields one history per reader) and the conversation_id +
    message_id are returned in the meta, matching chat.py. Persistence is
    idempotent, so a reconnect re-GET never duplicates it."""

    def _get():
        db = Db()
        try:
            return jobs.get_job(db, job_id)
        finally:
            db.close()

    def _persist(job, uid, conv_id):
        db = Db()
        try:
            return conversation_store.save_exchange(
                db,
                user_id=uid,
                conversation_id=conv_id,
                question=job.get("question") or "",
                answer=job.get("answer") or "",
                citations=job.get("citations") or [],
                verified_references=job.get("verified_references") or [],
                job_id=str(job_id),
                input_tokens=job.get("input_tokens") or 0,
                output_tokens=job.get("output_tokens") or 0,
            )
        finally:
            db.close()

    first = await run_in_threadpool(_get)
    if first is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    async def gen():
        waited = 0.0
        job = first
        while job["status"] in ("queued", "running"):
            yield ": keepalive\n\n"  # SSE comment; ignored by data:-only clients
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            if waited >= timeout:
                yield _sse(json.dumps({"error": "timeout_waiting_for_answer", "job_id": job_id}))
                yield _sse("[DONE]")
                return
            job = await run_in_threadpool(_get)
            if job is None:
                yield _sse(json.dumps({"error": "job_disappeared"}))
                yield _sse("[DONE]")
                return

        if job["status"] == "done":
            # Deliver the whole verified answer at once; the CLIENT paces the reveal.
            rmeta = job.get("result_meta") or {}
            yield _sse(json.dumps({"answer": job.get("answer") or ""}))

            # Persist to the authenticated reader's history (idempotent, best-effort,
            # off the event loop). Guests are not persisted, matching chat.py.
            conv_id = None
            message_id = None
            conversation_cost_usd = None
            conversation_turn_count = None
            if user_id:
                conv_id = conversation_store.resolve_conversation_id(conversation_id, str(job_id), user_id)
                message_id = conversation_store.assistant_message_id(conv_id, str(job_id))
                usage_totals = await run_in_threadpool(_persist, job, user_id, conv_id)
                # Long-conversation-handoff nudge (docs/superpowers/specs/2026-08-26-
                # long-conversation-handoff.md) -- guests are out of v1 scope (no
                # server-side conversation row to accumulate against), so this stays
                # None for them, same as conv_id/message_id above.
                if usage_totals:
                    conversation_cost_usd = round(estimate_cost_usd(
                        usage_totals["cumulative_input_tokens"],
                        usage_totals["cumulative_output_tokens"],
                    ), 4)
                    conversation_turn_count = usage_totals["turn_count"]

            # Re-check at delivery so an idempotent or already-completed job
            # cannot expose persisted quote IDs after the rail is disabled.
            deliverable_quote_ids = []
            if quotes_service.quote_selection_enabled():
                deliverable_quote_ids = job.get("quote_ids") or []

            yield _sse(json.dumps({
                "citations": job.get("citations") or [],
                "verified_references": job.get("verified_references") or [],
                # Quote rail (Project 3, wired 2026-08-06, async path only) --
                # IDS ONLY, never text. Empty for the overwhelming majority of
                # answers today (2 approved quotes corpus-wide). The client
                # resolves these through the new public /answer-quotes/resolve
                # endpoint at render time -- never embed the text here.
                "quote_ids": deliverable_quote_ids,
                "outcome": job.get("outcome"),
                "evidence_version": job.get("evidence_version"),
                "topics_established": rmeta.get("updated_topics") or {},
                "conversation_id": conv_id,
                "message_id": message_id,
                "job_id": job_id,
                "conversation_cost_usd": conversation_cost_usd,
                "conversation_turn_count": conversation_turn_count,
            }))
            yield _sse("[DONE]")
        else:  # failed | canceled
            yield _sse(json.dumps({
                "error": "generation_%s" % job["status"],
                "detail": job.get("last_error"),
                "job_id": job_id,
            }))
            yield _sse("[DONE]")

    return StreamingResponse(gen(), media_type="text/event-stream")
