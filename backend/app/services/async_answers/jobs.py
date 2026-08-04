"""Durable job lifecycle for the async answer path.

enqueue()   idempotency + single-flight + exact-match reuse, all race-safe via
            the answer_jobs unique indexes (a duplicate submission or a
            concurrent identical question never produces duplicate generation).
claim_next() reclaims dead-worker jobs, then claims one ready job with
            SELECT ... FOR UPDATE SKIP LOCKED (many workers, no double-claim).
complete()  writes the verified answer + instrumentation and marks it done.
fail_or_requeue() retries with backoff up to max_attempts, else fails. A retry
            re-runs the producer -> re-runs the accuracy check (no skip path).
defer()     returns a claimed job to the queue with a future run_after (rate /
            spend / pause deferral) WITHOUT consuming an attempt.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json

from .config import AsyncAnswerConfig
from .db import dict_cursor

_WS = re.compile(r"\s+")


def _normalize_question(question: str) -> str:
    """Exact-match normalization for the reuse/single-flight key: strip, collapse
    internal whitespace, lowercase. This is NOT semantic matching (no embeddings,
    no synonyms) -- it only folds trivial spelling/whitespace/case variants of the
    same literal question, which is the Phase 3 contract."""
    return _WS.sub(" ", (question or "").strip()).lower()


def compute_dedup_key(
    question: str,
    filters: Optional[Dict[str, Any]],
    evidence_version: str,
    prompt_version: str,
    policy_version: str,
) -> str:
    """Deterministic content key = sha256 over the exact reuse dimensions.
    filters are canonicalized (sorted keys) so key ordering never splits the
    key. Any change to evidence/prompt/policy version invalidates reuse -- which
    is exactly the intended cache-busting behaviour."""
    payload = {
        "q": _normalize_question(question),
        "filters": filters or {},
        "evidence_version": evidence_version,
        "prompt_version": prompt_version,
        "policy_version": policy_version,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def queue_depth(db) -> int:
    """Outstanding work: queued + running jobs (the backpressure signal)."""
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "SELECT count(*) AS c FROM answer_jobs WHERE status IN ('queued','running')"
            )
            return int(cur.fetchone()["c"])
    return db.run(_q)


def _find_shareable(db, dedup_key: str, idempotency_key: Optional[str], cfg: Optional[AsyncAnswerConfig]):
    """Resolve an existing job this submission should share, in priority order:
    idempotent resubmit -> reusable completed answer -> in-flight single-flight.
    Returns {"reason", "job"} or None."""
    reuse_ttl = cfg.reuse_ttl_seconds if cfg is not None else 0

    def _q(conn):
        with dict_cursor(conn) as cur:
            if idempotency_key:
                cur.execute(
                    "SELECT * FROM answer_jobs WHERE idempotency_key = %s", (idempotency_key,)
                )
                r = cur.fetchone()
                if r:
                    return ("idempotent", r)
            if reuse_ttl and reuse_ttl > 0:
                cur.execute(
                    "SELECT * FROM answer_jobs WHERE dedup_key = %s AND status = 'done' "
                    "AND outcome = 'answered' AND finished_at >= now() - (%s * interval '1 second') "
                    "ORDER BY finished_at DESC LIMIT 1",
                    (dedup_key, reuse_ttl),
                )
                r = cur.fetchone()
                if r:
                    return ("reuse", r)
            cur.execute(
                "SELECT * FROM answer_jobs WHERE dedup_key = %s AND status IN ('queued','running') "
                "ORDER BY created_at LIMIT 1",
                (dedup_key,),
            )
            r = cur.fetchone()
            if r:
                return ("single_flight", r)
            return None

    res = db.run(_q)
    if res is None:
        return None
    return {"reason": res[0], "job": res[1]}


def enqueue(
    db,
    question: str,
    evidence_version: str,
    prompt_version: str,
    policy_version: str,
    filters: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    idempotency_key: Optional[str] = None,
    cfg: Optional[AsyncAnswerConfig] = None,
) -> Dict[str, Any]:
    """Submit a question. Returns {"reason", "job", "dedup_key"} where reason is
    one of: created | idempotent | reuse | single_flight | rejected_backpressure.
    Never creates duplicate work for the same submission (idempotency) or the
    same concurrent content (single-flight)."""
    filters = filters or {}
    messages = messages or []
    dedup_key = compute_dedup_key(question, filters, evidence_version, prompt_version, policy_version)

    # Backpressure: refuse new work past the configured depth.
    if cfg is not None and cfg.max_queue_depth is not None:
        if queue_depth(db) >= cfg.max_queue_depth:
            return {"reason": "rejected_backpressure", "job": None, "dedup_key": dedup_key}

    # Fast path -- an existing idempotent / reusable / in-flight job.
    existing = _find_shareable(db, dedup_key, idempotency_key, cfg)
    if existing is not None:
        existing["dedup_key"] = dedup_key
        return existing

    def _insert(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "INSERT INTO answer_jobs (idempotency_key, dedup_key, question, filters, "
                "messages, evidence_version, prompt_version, policy_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (
                    idempotency_key, dedup_key, question, Json(filters), Json(messages),
                    evidence_version, prompt_version, policy_version,
                ),
            )
            return cur.fetchone()

    try:
        row = db.run(_insert)
        return {"reason": "created", "job": row, "dedup_key": dedup_key}
    except psycopg2.errors.UniqueViolation:
        # Lost the create race (idempotency_key UNIQUE, or the active-dedup
        # partial-unique index). Resolve the winner.
        winner = _find_shareable(db, dedup_key, idempotency_key, cfg)
        if winner is not None:
            winner["dedup_key"] = dedup_key
            return winner
        # The winning active job already completed between the violation and
        # this lookup, and reuse is off -- retry the insert once.
        row = db.run(_insert)
        return {"reason": "created", "job": row, "dedup_key": dedup_key}


def reap_expired_leases(db, max_attempts_guard: bool = True) -> int:
    """Requeue running jobs whose lease expired (their worker died). Bumps
    attempts; a job that keeps outliving its lease eventually fails rather than
    looping forever. Returns rows affected."""
    def _reap(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs "
                "SET attempts = attempts + 1, "
                "    status = CASE WHEN attempts + 1 >= max_attempts THEN 'failed' ELSE 'queued' END, "
                "    worker_id = NULL, "
                "    lease_expires_at = NULL, "
                "    last_error = CASE WHEN attempts + 1 >= max_attempts "
                "                      THEN 'lease expired (max attempts reached)' "
                "                      ELSE 'lease expired -- reclaimed' END, "
                "    finished_at = CASE WHEN attempts + 1 >= max_attempts THEN now() ELSE finished_at END, "
                "    run_after = now(), "
                "    updated_at = now() "
                "WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < now() "
                "RETURNING id"
            )
            return len(cur.fetchall())
    return db.run(_reap)


def claim_next(db, worker_id: str, lease_seconds: int) -> Optional[Dict[str, Any]]:
    """Reclaim dead-worker jobs, then atomically claim the oldest ready queued
    job. Returns the claimed job row, or None if the queue is empty. The
    FOR UPDATE SKIP LOCKED subselect makes concurrent workers never double-claim."""
    reap_expired_leases(db)

    def _claim(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs "
                "SET status = 'running', worker_id = %s, started_at = now(), "
                "    lease_expires_at = now() + (%s * interval '1 second'), updated_at = now() "
                "WHERE id = ( "
                "    SELECT id FROM answer_jobs "
                "    WHERE status = 'queued' AND run_after <= now() "
                "    ORDER BY created_at "
                "    FOR UPDATE SKIP LOCKED "
                "    LIMIT 1 "
                ") "
                "RETURNING *",
                (worker_id, lease_seconds),
            )
            return cur.fetchone()
    return db.run(_claim)


def complete(
    db,
    job_id: str,
    answer: str,
    outcome: str,
    citations: Any,
    verified_references: Any,
    retrieved_chunk_ids: Any,
    retrieved_point_ids: Any,
    model: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    cache_read_tokens: Optional[int],
    cache_write_tokens: Optional[int],
    cost_usd: Optional[float],
) -> None:
    """Persist a verified answer + Phase-4 instrumentation and mark the job done."""
    def _done(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs SET status = 'done', answer = %s, outcome = %s, "
                "citations = %s, verified_references = %s, retrieved_chunk_ids = %s, "
                "retrieved_point_ids = %s, model = %s, input_tokens = %s, output_tokens = %s, "
                "cache_read_tokens = %s, cache_write_tokens = %s, cost_usd = %s, "
                "finished_at = now(), lease_expires_at = NULL, updated_at = now() "
                "WHERE id = %s",
                (
                    answer, outcome, Json(citations), Json(verified_references),
                    Json(retrieved_chunk_ids), Json(retrieved_point_ids), model,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                    cost_usd, job_id,
                ),
            )
    db.run(_done)


def fail_or_requeue(db, job_id: str, error: str, backoff_seconds: int = 15) -> str:
    """Increment attempts. If under max_attempts, requeue with backoff (a retry
    will re-run the producer, hence the accuracy check). Otherwise mark failed.
    Returns the resulting status."""
    def _fail(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs "
                "SET attempts = attempts + 1, "
                "    status = CASE WHEN attempts + 1 >= max_attempts THEN 'failed' ELSE 'queued' END, "
                "    worker_id = NULL, lease_expires_at = NULL, "
                "    last_error = %s, "
                "    finished_at = CASE WHEN attempts + 1 >= max_attempts THEN now() ELSE NULL END, "
                "    run_after = now() + (%s * interval '1 second'), "
                "    updated_at = now() "
                "WHERE id = %s "
                "RETURNING status",
                (error[:4000] if error else None, backoff_seconds, job_id),
            )
            r = cur.fetchone()
            return r["status"] if r else "unknown"
    return db.run(_fail)


def defer(db, job_id: str, delay_seconds: int, reason: str = "deferred") -> None:
    """Return a claimed job to the queue with a future run_after WITHOUT
    consuming an attempt (rate-limit / spend / pause backpressure)."""
    def _defer(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs SET status = 'queued', worker_id = NULL, "
                "lease_expires_at = NULL, last_error = %s, "
                "run_after = now() + (%s * interval '1 second'), updated_at = now() "
                "WHERE id = %s",
                (reason, delay_seconds, job_id),
            )
    db.run(_defer)


def get_job(db, job_id: str) -> Optional[Dict[str, Any]]:
    def _get(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT * FROM answer_jobs WHERE id = %s", (job_id,))
            return cur.fetchone()
    return db.run(_get)
