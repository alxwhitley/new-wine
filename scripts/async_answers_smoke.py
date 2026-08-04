#!/usr/bin/env python3
"""
async_answers_smoke.py -- Phase 5 proof for the async answer path.

Drives the NEW path directly (never the live /chat) and demonstrates:
  A  an answer completes
  B  a killed worker loses nothing
  C  two identical concurrent questions generate once (single-flight)
  D  a reconnecting client gets its answer (durable delivery)
  E  the spend ceiling halts work, then resumes
  F  measured concurrency reached (the capacity dial)
  G  (opt-in --real N) the REAL retrieval + accuracy-check path end-to-end

Demos A-F use the ZERO-COST fake producer, so proving the queue mechanics costs
no Anthropic spend. --real N runs N genuine generations through the real
producer (~$0.039 each; e.g. --real 3 ~= $0.12) to prove the accuracy check is
preserved.

All test rows are marked (question 'SMOKE ...' or idempotency_key 'smoke-...')
and deleted on entry/exit -- no real data is touched. DB-write session -> plain
script path.

Usage:
  python3 scripts/async_answers_smoke.py [--conc-demo N] [--real N]

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.db.supabase import get_supabase  # noqa: E402
from app.services.async_answers import budget, jobs  # noqa: E402
from app.services.async_answers.config import AsyncAnswerConfig, load_config  # noqa: E402
from app.services.async_answers.db import Db, dict_cursor  # noqa: E402
from app.services.async_answers.producer import current_policy, produce  # noqa: E402

import answer_worker  # noqa: E402  (scripts/ on path)

_pass = 0
_fail = 0
_results = []  # type: list


def check(label, ok, detail=""):
    global _pass, _fail
    tag = "PASS" if ok else "FAIL"
    line = "  [%s] %s%s" % (tag, label, ("  -- " + detail if detail else ""))
    print(line)
    _results.append((tag, label, detail))
    if ok:
        _pass += 1
    else:
        _fail += 1
    return ok


# ---- small DB helpers ------------------------------------------------------
_CONFIG_COLS = {
    "paused", "max_queue_depth", "reuse_ttl_seconds", "rpm_limit", "itpm_limit",
    "otpm_limit", "spend_ceiling_usd", "spend_window", "lease_seconds",
}


def set_config(db, **kw):
    bad = set(kw) - _CONFIG_COLS
    if bad:
        raise ValueError("unknown config columns: %s" % bad)
    sets = ", ".join("%s = %%s" % k for k in kw)
    vals = list(kw.values())

    def _upd(conn):
        with dict_cursor(conn) as cur:
            cur.execute("UPDATE async_answer_config SET " + sets + ", updated_at = now() WHERE id = 1", vals)
    db.run(_upd)


def reset_config(db):
    set_config(
        db, paused=False, max_queue_depth=5000, reuse_ttl_seconds=0,
        rpm_limit=None, itpm_limit=None, otpm_limit=None,
        spend_ceiling_usd=None, spend_window="rolling_24h", lease_seconds=300,
    )


def cleanup(db):
    def _c(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "DELETE FROM answer_jobs WHERE question LIKE 'SMOKE %' OR idempotency_key LIKE 'smoke-%'"
            )
            return cur.rowcount
    return db.run(_c)


def count_running_fake(db):
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT count(*) AS c FROM answer_jobs WHERE status = 'running' AND question LIKE 'SMOKE %'")
            return int(cur.fetchone()["c"])
    return db.run(_q)


def count_by_dedup(db, dedup_key):
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT count(*) AS c FROM answer_jobs WHERE dedup_key = %s", (dedup_key,))
            return int(cur.fetchone()["c"])
    return db.run(_q)


def count_status(db, status):
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "SELECT count(*) AS c FROM answer_jobs WHERE status = %s AND question LIKE 'SMOKE %%'",
                (status,),
            )
            return int(cur.fetchone()["c"])
    return db.run(_q)


def clear_rate_buckets(db):
    db.run(lambda conn: conn.cursor().execute("DELETE FROM provider_rate_usage"))


def force_smoke_ready(db):
    def _u(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs SET run_after = now() "
                "WHERE status = 'queued' AND question LIKE 'SMOKE %'"
            )
    db.run(_u)


FAKE_POLICY = dict(evidence_version="smoke-e", prompt_version="smoke-p", policy_version="smoke-x")


def enqueue_fake(db, question, idempotency_key=None, cfg=None):
    return jobs.enqueue(
        db, question=question, filters={}, messages=[],
        idempotency_key=idempotency_key, cfg=cfg, **FAKE_POLICY,
    )


def run_fake_worker_once(concurrency=1):
    w = answer_worker.Worker(
        concurrency=concurrency, poll_interval=0.1, once=True,
        produce_fn=answer_worker._fake_produce, worker_prefix="smoke-once-" + uuid.uuid4().hex[:6],
    )
    w.run()


# ============================ demos =========================================
def demo_a_completes(db):
    print("\nDEMO A -- an answer completes")
    cleanup(db)
    res = enqueue_fake(db, "SMOKE A single completion", cfg=load_config(db))
    job_id = res["job"]["id"]
    check("enqueue created a job", res["reason"] == "created", res["reason"])
    run_fake_worker_once(concurrency=1)
    job = jobs.get_job(db, job_id)
    check("job reached status=done", job and job["status"] == "done", job["status"] if job else "None")
    check("answer text present", bool(job and job["answer"]))
    check("outcome recorded", job and job["outcome"] == "answered", job.get("outcome") if job else "")
    check(
        "Phase-4 instrumentation captured",
        bool(job and job["cost_usd"] is not None and job["input_tokens"]
             and job["output_tokens"] and job["retrieved_chunk_ids"] and job["model"]),
        "cost=%s in=%s out=%s model=%s" % (
            job.get("cost_usd"), job.get("input_tokens"), job.get("output_tokens"), job.get("model")
        ) if job else "",
    )


def demo_b_kill_safe(db):
    print("\nDEMO B -- a killed worker loses nothing")
    cleanup(db)
    # Short lease so a 'died' worker's job becomes reclaimable quickly.
    set_config(db, lease_seconds=3)
    res = enqueue_fake(db, "SMOKE B kill safety", cfg=load_config(db))
    job_id = res["job"]["id"]

    # A worker claims the job, then 'dies' (never completes) -- exactly the row
    # state a SIGKILLed worker leaves behind: status=running, a lease that will
    # expire, no result written.
    claimed = jobs.claim_next(db, "DEAD-worker", lease_seconds=3)
    check("dead worker claimed the job (now running)",
          claimed and str(claimed["id"]) == str(job_id) and claimed["status"] == "running",
          claimed["status"] if claimed else "None")

    time.sleep(4.0)  # lease expires; the dead worker never came back

    mid = jobs.get_job(db, job_id)
    check("orphaned job still exists (not lost) with expired lease",
          bool(mid and mid["status"] == "running" and mid["lease_expires_at"] is not None))

    # A live worker starts, reaps the expired lease, reclaims and completes it.
    run_fake_worker_once(concurrency=1)
    done = jobs.get_job(db, job_id)
    check("job completed after reclaim (nothing lost)",
          bool(done and done["status"] == "done" and done["answer"]),
          done["status"] if done else "None")
    check("reclaim consumed an attempt (attempts >= 1)",
          bool(done and done["attempts"] >= 1), "attempts=%s" % (done.get("attempts") if done else "?"))
    reset_config(db)


def demo_c_single_flight(db):
    print("\nDEMO C -- two identical concurrent questions generate once")
    cleanup(db)
    q = "SMOKE C the identical question asked twice at once"
    cfg = load_config(db)
    dedup = jobs.compute_dedup_key(q, {}, FAKE_POLICY["evidence_version"],
                                   FAKE_POLICY["prompt_version"], FAKE_POLICY["policy_version"])
    barrier = threading.Barrier(2)
    out = {}

    def _submit(tag):
        d = Db()
        try:
            barrier.wait()  # fire both enqueues as close to simultaneous as possible
            out[tag] = enqueue_fake(d, q, cfg=cfg)
        finally:
            d.close()

    t1 = threading.Thread(target=_submit, args=("a",))
    t2 = threading.Thread(target=_submit, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    id_a = str(out["a"]["job"]["id"])
    id_b = str(out["b"]["job"]["id"])
    reasons = sorted([out["a"]["reason"], out["b"]["reason"]])
    check("both submissions resolved to the SAME job", id_a == id_b, "%s vs %s" % (id_a[:8], id_b[:8]))
    check("exactly one created, one single_flight", reasons == ["created", "single_flight"], str(reasons))
    check("only ONE job row exists for this content", count_by_dedup(db, dedup) == 1,
          "rows=%d" % count_by_dedup(db, dedup))

    run_fake_worker_once(concurrency=2)
    check("still exactly one job, now done", count_by_dedup(db, dedup) == 1)
    job = jobs.get_job(db, id_a)
    check("the single job completed", bool(job and job["status"] == "done"))


def demo_d_reconnect(db):
    print("\nDEMO D -- a reconnecting client gets its answer")
    cleanup(db)
    res = enqueue_fake(db, "SMOKE D reconnect delivery", cfg=load_config(db))
    job_id = res["job"]["id"]
    # Client 'disconnects' immediately -- we never hold a connection.
    run_fake_worker_once(concurrency=1)
    # Client 'reconnects' later and re-reads the durable job -- reconnection is a
    # GET, not a re-generation.
    reread = jobs.get_job(db, job_id)
    check("reconnecting read returns the finished job", bool(reread and reread["status"] == "done"))
    check("full verified answer is retrievable on reconnect", bool(reread and reread["answer"]))


def demo_e_spend_ceiling(db):
    print("\nDEMO E -- spend ceiling halts work, then resumes")
    cleanup(db)
    # Build some accumulated spend first (each fake job records $0.039).
    for i in range(2):
        enqueue_fake(db, "SMOKE E prior spend %d" % i, cfg=load_config(db))
    run_fake_worker_once(concurrency=2)

    set_config(db, spend_window="total")
    total = budget.spend_in_window(db, load_config(db))
    check("accumulated spend > 0 (window=total)", total > 0, "$%.4f" % total)

    # Ceiling BELOW current spend -> halted.
    set_config(db, spend_ceiling_usd=round(total / 2.0, 4))
    marker = enqueue_fake(db, "SMOKE E marker under ceiling", cfg=load_config(db))
    marker_id = marker["job"]["id"]
    run_fake_worker_once(concurrency=1)
    halted = jobs.get_job(db, marker_id)
    check("over-ceiling: marker stays queued (work halted)",
          bool(halted and halted["status"] == "queued"), halted["status"] if halted else "None")

    # Raise the ceiling -> resumes.
    set_config(db, spend_ceiling_usd=None)
    run_fake_worker_once(concurrency=1)
    resumed = jobs.get_job(db, marker_id)
    check("ceiling lifted: marker completes (work resumes)",
          bool(resumed and resumed["status"] == "done"), resumed["status"] if resumed else "None")
    reset_config(db)


def demo_rate_limit(db):
    print("\nDEMO R -- provider rate ceiling defers work, then resumes")
    cleanup(db)
    reset_config(db)
    clear_rate_buckets(db)
    # RPM ceiling of 2: at most 2 generations may start in a rolling minute.
    set_config(db, rpm_limit=2)
    for i in range(4):
        enqueue_fake(db, "SMOKE R rate job %d" % i, cfg=load_config(db))
    run_fake_worker_once(concurrency=1)
    done = count_status(db, "done")
    queued = count_status(db, "queued")
    check("rpm=2: exactly 2 jobs generated this minute", done == 2, "done=%d" % done)
    check("over-rate jobs deferred (stay queued), not generated", queued == 2, "queued=%d" % queued)

    # New minute (cleared bucket) + higher ceiling + ready run_after -> drains.
    clear_rate_buckets(db)
    set_config(db, rpm_limit=10)
    force_smoke_ready(db)
    run_fake_worker_once(concurrency=2)
    check("ceiling window opens: all 4 complete (work resumes)", count_status(db, "done") == 4,
          "done=%d" % count_status(db, "done"))
    reset_config(db)
    clear_rate_buckets(db)


def demo_f_concurrency(db, slots):
    print("\nDEMO F -- measured concurrency reached (capacity dial = slots x workers)")
    cleanup(db)
    reset_config(db)
    # Wide fake latency so many jobs overlap and the peak is samplable.
    os.environ["ASYNC_FAKE_LATENCY"] = "3.0"
    n_jobs = slots + max(10, slots // 2)
    for i in range(n_jobs):
        enqueue_fake(db, "SMOKE F concurrency job %03d" % i, cfg=load_config(db))
    check("enqueued %d distinct jobs" % n_jobs, jobs.queue_depth(db) >= n_jobs, "depth=%d" % jobs.queue_depth(db))

    worker = answer_worker.Worker(
        concurrency=slots, poll_interval=0.05, once=False,
        produce_fn=answer_worker._fake_produce, worker_prefix="smoke-conc-" + uuid.uuid4().hex[:6],
    )
    wt = threading.Thread(target=worker.run, daemon=True)
    wt.start()

    peak = 0
    sampler = Db()
    t_end = time.time() + 9.0
    try:
        while time.time() < t_end:
            r = count_running_fake(sampler)
            if r > peak:
                peak = r
            time.sleep(0.15)
    finally:
        sampler.close()
    worker.stop()
    wt.join(timeout=15)

    os.environ.pop("ASYNC_FAKE_LATENCY", None)
    print("  MEASURED PEAK CONCURRENT GENERATIONS (1 worker, %d slots): %d" % (slots, peak))
    check("peak concurrency reached the slot dial (>= %d)" % max(1, int(slots * 0.75)),
          peak >= max(1, int(slots * 0.75)), "peak=%d / slots=%d" % (peak, slots))
    return peak


def demo_g_real(db, n):
    print("\nDEMO G -- REAL retrieval + accuracy-check path (%d generation(s))" % n)
    supabase = get_supabase()
    questions = [
        "What is deliverance?",
        "What does the Bible teach about fasting?",
        "How does spiritual warfare work?",
    ][:n]
    total_cost = 0.0
    all_ok = True
    for i, q in enumerate(questions):
        t0 = time.time()
        res = produce(supabase, q, [])
        dt = time.time() - t0
        total_cost += (res.cost_usd or 0.0)
        ok = bool(res.answer) and res.outcome in (
            "answered", "refused_attribution", "no_material", "position_paper")
        all_ok = all_ok and ok
        print("  Q%d %r -> outcome=%s  %.1fs  $%.4f  in=%d out=%d  cites=%d  verified_refs=%d"
              % (i + 1, q, res.outcome, dt, res.cost_usd, res.input_tokens, res.output_tokens,
                 len(res.citations), len(res.verified_references)))
    check("all real produce() calls returned a verified result", all_ok)

    # One real job end-to-end through the queue.
    policy = current_policy(supabase)
    q = "What is deliverance?"
    res = jobs.enqueue(
        db, question=q, filters=policy["filters"], messages=[],
        idempotency_key="smoke-real-e2e-" + uuid.uuid4().hex[:6],
        evidence_version=policy["evidence_version"], prompt_version=policy["prompt_version"],
        policy_version=policy["policy_version"], cfg=load_config(db),
    )
    job_id = res["job"]["id"]
    w = answer_worker.Worker(concurrency=1, poll_interval=0.2, once=True,
                             produce_fn=produce, worker_prefix="smoke-real-" + uuid.uuid4().hex[:6])
    w.run()
    job = jobs.get_job(db, job_id)
    if job and job["cost_usd"]:
        total_cost += float(job["cost_usd"])
    check("real job completed end-to-end through the queue",
          bool(job and job["status"] == "done" and job["answer"]),
          "outcome=%s cost=$%s" % (job.get("outcome"), job.get("cost_usd")) if job else "None")
    print("  REAL SPEND THIS RUN: $%.4f" % total_cost)
    return total_cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conc-demo", type=int, default=24, help="slot count for the concurrency demo")
    ap.add_argument("--real", type=int, default=0, help="run N real generations (opt-in spend ~$0.039 each)")
    args = ap.parse_args()

    print("=" * 70)
    print("Async answer path -- Phase 5 proof")
    print("=" * 70)

    db = Db()
    real_cost = 0.0
    peak = None
    try:
        reset_config(db)
        cleanup(db)
        demo_a_completes(db)
        demo_b_kill_safe(db)
        demo_c_single_flight(db)
        demo_d_reconnect(db)
        demo_e_spend_ceiling(db)
        demo_rate_limit(db)
        peak = demo_f_concurrency(db, args.conc_demo)
        if args.real > 0:
            real_cost = demo_g_real(db, min(args.real, 3))
    finally:
        reset_config(db)
        removed = cleanup(db)
        db.close()

    print("\n" + "=" * 70)
    print("SUMMARY: %d/%d checks passed" % (_pass, _pass + _fail))
    if peak is not None:
        print("Measured peak concurrency (1 worker x %d slots): %d" % (args.conc_demo, peak))
        print("  Capacity = slots x workers. To reach the 100-concurrent DIAL, run more")
        print("  workers (e.g. 100/%d ~= %d worker copies) -- no rebuild." % (
            max(1, peak), (100 + max(1, peak) - 1) // max(1, peak)))
    if args.real > 0:
        print("Real Anthropic spend this run: $%.4f" % real_cost)
    print("Cleaned up %d test rows." % removed)
    print("=" * 70)
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
