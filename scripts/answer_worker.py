#!/usr/bin/env python3
"""
answer_worker.py -- the async answer-path worker (Project 1, Stage 1).

Stateless, horizontally scalable: run more copies (or raise --concurrency) to
raise capacity toward the 100-concurrent DIAL; never a rebuild. Each worker is a
bounded pool of slots, each slot an independent claim->produce->complete loop
with its OWN psycopg2 connection (psycopg2 connections are not thread-safe to
share). The supabase (PostgREST) client used for producing IS shared across
slots -- the same singleton the live path shares across request threads.

A slot:
  load config -> honour pause / spend ceiling -> claim one ready job (SKIP
  LOCKED, reclaiming dead-worker jobs first) -> reserve provider-rate budget
  (defer if over) -> produce a VERIFIED answer -> reconcile rate -> complete.
  On a producer fault: fail_or_requeue (retry re-runs produce, hence the
  accuracy check). No path skips the check.

Runs on the plain-script path (CLAUDE.md Session Routing: any DB-writing
session). It is deployed on Railway as a SECOND service off the same repo/image
with startCommand `python3 scripts/answer_worker.py` -- one app, one queue, one
DB, one scalable worker deployment (decision #14). This session does NOT wire
that up (inert); it only builds and proves the worker.

Usage:
  python3 scripts/answer_worker.py [--concurrency N] [--poll-interval SEC]
                                   [--once] [--max-idle SEC] [--fake]

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))  # so `import app.*` resolves

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.db.supabase import get_supabase  # noqa: E402
from app.services.async_answers import budget, jobs  # noqa: E402
from app.services.async_answers.config import load_config  # noqa: E402
from app.services.async_answers.db import Db  # noqa: E402
from app.services.async_answers.producer import ProducerResult, produce  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("answer_worker")


def _seconds_to_next_minute() -> int:
    return max(1, 61 - int(time.time()) % 60)


def _fake_produce(supabase, question: str, messages=None) -> ProducerResult:
    """Zero-cost stand-in for produce(): simulates generation latency and
    returns canned verified output with synthetic token counts. Proves the queue
    mechanics (durability, single-flight, kill-safety, reconnect, spend halt,
    concurrency) without any Anthropic spend. Not for the accuracy-check proof."""
    time.sleep(float(os.environ.get("ASYNC_FAKE_LATENCY", "2.0")))
    return ProducerResult(
        answer="[fake] verified answer to: %s" % question,
        outcome="answered",
        citations=[],
        verified_references=[],
        retrieved_chunk_ids=["fake-chunk-1", "fake-chunk-2"],
        retrieved_point_ids=["fake-chunk-1"],
        model="fake",
        input_tokens=4000,
        output_tokens=1500,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.039,
    )


class Worker:
    def __init__(
        self,
        concurrency: int = 4,
        poll_interval: float = 1.0,
        once: bool = False,
        max_idle: Optional[float] = None,
        produce_fn: Optional[Callable[..., ProducerResult]] = None,
        worker_prefix: Optional[str] = None,
    ):
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.once = once
        self.max_idle = max_idle
        self.produce_fn = produce_fn or produce
        self._supabase = None
        self._stop = threading.Event()
        self._threads = []  # type: list
        self._idle_since = {}  # type: dict
        base = worker_prefix or "%s-%d" % (socket.gethostname(), os.getpid())
        self._base_id = base

    def _supabase_client(self):
        if self._supabase is None:
            self._supabase = get_supabase()
        return self._supabase

    def stop(self) -> None:
        self._stop.set()

    def _slot_loop(self, slot: int) -> None:
        worker_id = "%s-slot%d" % (self._base_id, slot)
        db = Db()
        try:
            while not self._stop.is_set():
                try:
                    did_work = self._tick(db, worker_id)
                except Exception:
                    # A transient fault at the config/claim/complete stage (e.g. a
                    # pooler connection cap or a dropped connection) must NOT kill
                    # the slot. Back off and retry; any job claimed before the
                    # fault is left 'running' and the reaper requeues it via its
                    # lease (the same kill-safety path).
                    logger.exception("[%s] tick failed -- backing off", worker_id)
                    self._stop.wait(min(5.0, self.poll_interval * 5))
                    continue
                if did_work:
                    self._idle_since.pop(slot, None)
                    continue
                # idle
                now = time.time()
                self._idle_since.setdefault(slot, now)
                if self.once:
                    break
                if self.max_idle is not None and (now - self._idle_since[slot]) >= self.max_idle:
                    break
                self._stop.wait(self.poll_interval)
        finally:
            db.close()

    def _tick(self, db: Db, worker_id: str) -> bool:
        """One claim->produce->complete cycle. Returns True if a job was worked."""
        cfg = load_config(db)
        if cfg.paused:
            return False
        if not budget.spend_ok(db, cfg):
            logger.info("[%s] spend ceiling reached -- holding (jobs stay queued)", worker_id)
            return False

        job = jobs.claim_next(db, worker_id, cfg.lease_seconds)
        if not job:
            return False

        job_id = job["id"]
        est_in = budget.DEFAULT_EST_INPUT_TOKENS
        est_out = budget.DEFAULT_EST_OUTPUT_TOKENS

        if not budget.reserve_rate(db, cfg, est_in, est_out):
            jobs.defer(db, job_id, _seconds_to_next_minute(), "rate_limited")
            logger.info("[%s] job %s deferred (provider rate ceiling)", worker_id, job_id)
            return True  # we did do work (a claim + defer); keep the loop hot

        try:
            result = self.produce_fn(self._supabase_client(), job["question"], job.get("messages") or [])
        except Exception as exc:
            status = jobs.fail_or_requeue(db, job_id, "producer error: %r" % exc)
            logger.exception("[%s] job %s produce failed -> %s", worker_id, job_id, status)
            return True

        budget.reconcile_rate(db, est_in, est_out, result.input_tokens, result.output_tokens)
        jobs.complete(
            db, job_id,
            answer=result.answer,
            outcome=result.outcome,
            citations=result.citations,
            verified_references=result.verified_references,
            retrieved_chunk_ids=result.retrieved_chunk_ids,
            retrieved_point_ids=result.retrieved_point_ids,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_write_tokens=result.cache_write_tokens,
            cost_usd=result.cost_usd,
        )
        logger.info("[%s] job %s done (%s, $%.4f)", worker_id, job_id, result.outcome, result.cost_usd)
        return True

    def run(self) -> None:
        for slot in range(self.concurrency):
            t = threading.Thread(target=self._slot_loop, args=(slot,), name="slot-%d" % slot, daemon=True)
            t.start()
            self._threads.append(t)
        for t in self._threads:
            t.join()


def main():
    ap = argparse.ArgumentParser(description="Async answer-path worker")
    ap.add_argument("--concurrency", type=int, default=int(os.environ.get("WORKER_CONCURRENCY", "4")))
    ap.add_argument("--poll-interval", type=float, default=float(os.environ.get("WORKER_POLL_INTERVAL", "1.0")))
    ap.add_argument("--once", action="store_true", help="drain the queue once, then exit")
    ap.add_argument("--max-idle", type=float, default=None, help="exit after this many idle seconds")
    ap.add_argument("--fake", action="store_true", help="use the zero-cost fake producer")
    args = ap.parse_args()

    produce_fn = _fake_produce if (args.fake or os.environ.get("ASYNC_FAKE_PRODUCER") == "1") else produce
    worker = Worker(
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
        once=args.once,
        max_idle=args.max_idle,
        produce_fn=produce_fn,
    )

    def _handle(sig, frame):
        logger.info("signal %s received -- draining in-flight slots and exiting", sig)
        worker.stop()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    logger.info(
        "answer_worker starting: concurrency=%d poll=%.1fs fake=%s",
        args.concurrency, args.poll_interval, produce_fn is _fake_produce,
    )
    worker.run()
    logger.info("answer_worker stopped")


if __name__ == "__main__":
    main()
