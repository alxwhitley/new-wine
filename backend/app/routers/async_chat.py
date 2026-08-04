"""Async answer path -- HTTP delivery surface (BUILT BUT NOT MOUNTED / INERT).

This router is deliberately NOT included in app.main this session, so the live
FastAPI app is byte-identical and nothing an existing reader experiences
changes. It is the delivery half of the durable path, ready for the cutover
session. To mount at cutover (a deliberate, separate change):

    from app.routers import async_chat
    app.include_router(async_chat.router, prefix="/async-chat", tags=["async-chat"])

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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool

from app.auth import get_optional_user
from app.db.supabase import get_supabase
from app.services.async_answers import conversation_store, jobs
from app.services.async_answers.config import load_config
from app.services.async_answers.db import Db
from app.services.async_answers.metering import enforce_query_limit
from app.services.async_answers.producer import current_policy

router = APIRouter()


class AsyncChatRequest(BaseModel):
    question: str
    messages: List[Dict[str, Any]] = []
    topics_established: Dict[str, int] = {}
    idempotency_key: Optional[str] = None
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


@router.get("/mode")
async def mode():
    """The seconds-reversible TRAFFIC switch (async_answer_config.serving_enabled,
    default OFF). The frontend calls the async path only when this returns
    async_enabled=true. When these routes aren't mounted (env off), the fetch
    404s and the frontend stays on the live path. Reversible with one UPDATE."""
    def _read():
        db = Db()
        try:
            return load_config(db).serving_enabled
        finally:
            db.close()

    enabled = await run_in_threadpool(_read)
    return {"async_enabled": bool(enabled)}


@router.post("/submit")
async def submit(
    req: AsyncChatRequest,
    http_request: Request,
    user_id: Optional[str] = Depends(get_optional_user),
):
    """Enqueue a question. Idempotent by idempotency_key; single-flight + reuse
    by content. Returns instantly with a job_id to poll/stream.

    Metering runs FIRST, fail-closed, keyed on the CALLER (user_id / anon_id),
    BEFORE enqueue's single-flight/reuse collapse -- so every submission is counted
    independently even when several submissions share one generation (parity with
    chat.py, which meters every /chat request)."""
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
            conversation_store.save_exchange(
                db,
                user_id=uid,
                conversation_id=conv_id,
                question=job.get("question") or "",
                answer=job.get("answer") or "",
                citations=job.get("citations") or [],
                verified_references=job.get("verified_references") or [],
                job_id=str(job_id),
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
            if user_id:
                conv_id = conversation_store.resolve_conversation_id(conversation_id, str(job_id), user_id)
                message_id = conversation_store.assistant_message_id(conv_id, str(job_id))
                await run_in_threadpool(_persist, job, user_id, conv_id)

            yield _sse(json.dumps({
                "citations": job.get("citations") or [],
                "verified_references": job.get("verified_references") or [],
                "outcome": job.get("outcome"),
                "evidence_version": job.get("evidence_version"),
                "topics_established": rmeta.get("updated_topics") or {},
                "conversation_id": conv_id,
                "message_id": message_id,
                "job_id": job_id,
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
