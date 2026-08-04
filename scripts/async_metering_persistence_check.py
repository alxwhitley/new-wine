#!/usr/bin/env python3
"""Blocker 2 (metering parity) + Blocker 3 (conversation persistence) proof for
the async answer path (Stage 2, Project 1). Drives the /async-chat routes via an
in-process TestClient -- never the live app, never real traffic.

What it proves
  B2  Every /async-chat/submit meters INDEPENDENTLY, keyed on the caller, EVEN
      when single-flight collapses two submissions to one generation:
        - two different users submit the identical question at the same instant ->
          exactly ONE job (one generation) but TWO independent metering calls,
          one per user;
        - an over-limit user gets 429 and is NOT enqueued;
        - guest metering mirrors chat.py (anon_id + IP; 429 over cap; 400 without
          anon_id).
  B3  A logged-in user's async answer lands in their conversation history in the
      SAME shape chat.py writes (conversations row + user msg + assistant msg with
      citations + verified_references), is IDEMPOTENT across a reconnect (a re-GET
      never duplicates), and under single-flight each reader gets their OWN
      conversation (one shared generation -> two histories). Guests are not
      persisted.

Metering RPCs are STUBBED (a fake supabase), so NO real guest_usage/user_usage
rows are touched. Queue + persistence writes are REAL (direct Postgres), all
marked and deleted on entry+exit. DB-write session -> plain script path.

Usage:  python3 scripts/async_metering_persistence_check.py
Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import json
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "backend" / "app" / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import get_optional_user  # noqa: E402
from app.routers import async_chat  # noqa: E402
from app.services.async_answers import conversation_store, jobs  # noqa: E402
from app.services.async_answers.config import load_config  # noqa: E402
from app.services.async_answers.db import Db, dict_cursor  # noqa: E402
import answer_worker  # noqa: E402

_pass = 0
_fail = 0


def check(label: str, ok: bool, detail: str = "") -> bool:
    global _pass, _fail
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", label, ("  -- " + detail if detail else "")))
    if ok:
        _pass += 1
    else:
        _fail += 1
    return ok


# ---- test markers (everything this script writes is cleaned up) --------------
QMARK = "ZZTEST"                 # question prefix
IDMARK = "zztest-"               # idempotency_key prefix
FIXED_POLICY = {"evidence_version": "zz-e", "prompt_version": "zz-p",
                "policy_version": "zz-x", "filters": {}}
_conv_ids: List[str] = []        # conversation ids to delete on teardown


# ---- fake supabase: records metering RPC calls, no real writes ---------------
class _Result:
    def __init__(self, data): self.data = data


class _RPC:
    def __init__(self, sink, name, params, data):
        sink.append((name, dict(params)))
        self._data = data

    def execute(self):
        return _Result(self._data)


class FakeSupabase:
    """Stands in for the supabase client during metering. Records every rpc()
    call and returns configurable canned data, so enforce_query_limit runs its
    real logic without touching real usage tables."""
    def __init__(self):
        self.calls: List[Any] = []
        # authenticated-user response (allowed by default)
        self.user_allowed = True
        self.user_count = 1
        self.weekly_limit = 50
        self.week_start = "2026-08-03"
        # guest response (an int count by default)
        self.guest_count = 1

    def rpc(self, name, params):
        if name == "increment_user_query":
            row = {"query_count": self.user_count, "weekly_limit": self.weekly_limit,
                   "week_start": self.week_start, "allowed": self.user_allowed}
            return _RPC(self.calls, name, params, [row])
        if name == "increment_guest_query":
            return _RPC(self.calls, name, params, self.guest_count)
        return _RPC(self.calls, name, params, None)

    def user_calls(self):
        return [p for (n, p) in self.calls if n == "increment_user_query"]

    def guest_calls(self):
        return [p for (n, p) in self.calls if n == "increment_guest_query"]


# ---- app wiring: mount the real router, override auth via a test header ------
def build_client():
    app = FastAPI()
    app.include_router(async_chat.router, prefix="/async-chat")

    def _fake_user(request: Request) -> Optional[str]:
        return request.headers.get("x-test-user") or None

    app.dependency_overrides[get_optional_user] = _fake_user
    return TestClient(app)


def parse_sse_meta(text: str) -> Dict[str, Any]:
    """Return the meta payload (the SSE data frame carrying conversation_id)."""
    meta = {}  # type: Dict[str, Any]
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        body = line[len("data: "):]
        if body == "[DONE]":
            continue
        try:
            obj = json.loads(body)
        except ValueError:
            continue
        if isinstance(obj, dict) and "conversation_id" in obj:
            meta = obj
    return meta


# ---- DB helpers -------------------------------------------------------------
def cleanup(db):
    def _c(conn):
        with dict_cursor(conn) as cur:
            if _conv_ids:
                cur.execute("DELETE FROM messages WHERE conversation_id = ANY(%s::uuid[])", (_conv_ids,))
                cur.execute("DELETE FROM conversations WHERE id = ANY(%s::uuid[])", (_conv_ids,))
            cur.execute(
                "DELETE FROM answer_jobs WHERE question LIKE %s OR idempotency_key LIKE %s",
                (QMARK + " %", IDMARK + "%"),
            )
    db.run(_c)


def real_user_ids(db, n=2):
    """conversations.user_id has an FK to auth.users, so persistence tests must use
    REAL user ids (in production these are always a JWT 'sub'). We borrow existing
    users and only ever delete the ZZTEST conversations we create under them."""
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT id FROM auth.users ORDER BY created_at LIMIT %s", (n,))
            return [str(r["id"]) for r in cur.fetchall()]
    return db.run(_q)


def messages_for(db, conv_id):
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "SELECT id, role, content, citations, verified_references FROM messages "
                "WHERE conversation_id = %s ORDER BY role",
                (conv_id,),
            )
            return cur.fetchall()
    return db.run(_q)


def conversation_row(db, conv_id):
    def _q(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT id, user_id, title FROM conversations WHERE id = %s", (conv_id,))
            return cur.fetchone()
    return db.run(_q)


def set_job_refs(db, job_id, citations, verified_references):
    from psycopg2.extras import Json

    def _u(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE answer_jobs SET citations = %s, verified_references = %s WHERE id = %s",
                (Json(citations), Json(verified_references), job_id),
            )
    db.run(_u)


# ============================ BLOCKER 2 ======================================
def blocker2_metering(db, client):
    print("\nBLOCKER 2 -- usage-limit metering parity on /async-chat/submit")

    # -- 2a: two users, identical question, same instant -> 1 job, 2 meterings --
    fake = FakeSupabase()
    async_chat.get_supabase = lambda: fake
    async_chat.current_policy = lambda supabase: dict(FIXED_POLICY)

    q = "%s two users identical question %s" % (QMARK, uuid.uuid4().hex[:8])
    uA, uB = str(uuid.uuid4()), str(uuid.uuid4())
    results: Dict[str, Any] = {}
    barrier = threading.Barrier(2)

    def _submit(user):
        c = build_client()  # per-thread client (avoid shared-client concurrency)
        barrier.wait()
        results[user] = c.post(
            "/async-chat/submit",
            json={"question": q, "messages": [], "topics_established": {}},
            headers={"x-test-user": user},
        )

    t1 = threading.Thread(target=_submit, args=(uA,))
    t2 = threading.Thread(target=_submit, args=(uB,))
    t1.start(); t2.start(); t1.join(); t2.join()

    rA, rB = results[uA], results[uB]
    check("both submissions succeeded (200)", rA.status_code == 200 and rB.status_code == 200,
          "%s / %s" % (rA.status_code, rB.status_code))
    jid_a = rA.json().get("job_id")
    jid_b = rB.json().get("job_id")
    check("single-flight: both resolve to the SAME job (one generation)", jid_a == jid_b,
          "%s vs %s" % (str(jid_a)[:8], str(jid_b)[:8]))
    reasons = sorted([rA.json().get("reason"), rB.json().get("reason")])
    check("exactly one 'created' + one 'single_flight'", reasons == ["created", "single_flight"], str(reasons))

    user_calls = fake.user_calls()
    metered_ids = sorted(p.get("p_user_id") for p in user_calls)
    check("metering ran TWICE -- once per submission (independent of single-flight)",
          len(user_calls) == 2, "increment_user_query calls=%d" % len(user_calls))
    check("each user metered under their OWN id", metered_ids == sorted([uA, uB]),
          "metered=%s" % [s[:8] for s in metered_ids])
    check("authenticated submit returns usage meta (parity with chat.py meta.usage)",
          isinstance(rA.json().get("usage"), dict) and rA.json()["usage"].get("limit") == 50,
          str(rA.json().get("usage")))

    # -- 2b: over-limit user -> 429, and NOT enqueued --
    fake_over = FakeSupabase()
    fake_over.user_allowed = False
    fake_over.user_count = 50
    async_chat.get_supabase = lambda: fake_over
    q_over = "%s over limit %s" % (QMARK, uuid.uuid4().hex[:8])
    r_over = client.post("/async-chat/submit",
                         json={"question": q_over, "messages": [], "topics_established": {}},
                         headers={"x-test-user": str(uuid.uuid4())})
    detail = r_over.json().get("detail") if r_over.status_code == 429 else None
    check("over-limit user -> 429 weekly_limit_reached",
          r_over.status_code == 429 and isinstance(detail, dict) and detail.get("error") == "weekly_limit_reached",
          "status=%s detail=%s" % (r_over.status_code, detail))

    def _count_q(conn):
        with dict_cursor(conn) as cur:
            cur.execute("SELECT count(*) AS c FROM answer_jobs WHERE question = %s", (q_over,))
            return int(cur.fetchone()["c"])
    check("over-limit submission was NOT enqueued (no generation)", db.run(_count_q) == 0,
          "rows=%d" % db.run(_count_q))

    # -- 2c: guest metering mirrors chat.py --
    fake_guest = FakeSupabase()
    fake_guest.guest_count = 1
    async_chat.get_supabase = lambda: fake_guest
    anon = "%sanon-%s" % (IDMARK, uuid.uuid4().hex[:8])
    q_g = "%s guest ok %s" % (QMARK, uuid.uuid4().hex[:8])
    r_g = client.post("/async-chat/submit",
                      json={"question": q_g, "messages": [], "topics_established": {}, "anon_id": anon})
    gcalls = fake_guest.guest_calls()
    check("guest submit meters via increment_guest_query(anon_id, ip)",
          r_g.status_code == 200 and len(gcalls) == 1 and gcalls[0].get("p_anon_id") == anon
          and "p_ip_address" in gcalls[0],
          "status=%s calls=%s" % (r_g.status_code, gcalls))

    fake_guest_over = FakeSupabase()
    fake_guest_over.guest_count = 7  # > GUEST_QUERY_LIMIT (6)
    async_chat.get_supabase = lambda: fake_guest_over
    r_go = client.post("/async-chat/submit",
                       json={"question": "%s guest over %s" % (QMARK, uuid.uuid4().hex[:6]),
                             "messages": [], "topics_established": {}, "anon_id": anon})
    check("guest over cap -> 429 guest_limit_reached",
          r_go.status_code == 429 and r_go.json().get("detail") == "guest_limit_reached",
          "status=%s detail=%s" % (r_go.status_code, r_go.json().get("detail")))

    async_chat.get_supabase = lambda: FakeSupabase()
    r_noanon = client.post("/async-chat/submit",
                           json={"question": "%s guest no anon %s" % (QMARK, uuid.uuid4().hex[:6]),
                                 "messages": [], "topics_established": {}})
    check("guest without anon_id -> 400 (parity with chat.py)", r_noanon.status_code == 400,
          "status=%s" % r_noanon.status_code)


# ============================ BLOCKER 3 ======================================
def blocker3_persistence(db, client):
    print("\nBLOCKER 3 -- conversation/message persistence for a logged-in user")

    # A real, completed job to deliver (fake producer -> no Anthropic spend).
    async_chat.current_policy = lambda supabase: dict(FIXED_POLICY)
    q = "%s persistence question %s" % (QMARK, uuid.uuid4().hex[:8])
    res = jobs.enqueue(db, question=q, messages=[],
                       idempotency_key="%spersist-%s" % (IDMARK, uuid.uuid4().hex[:6]),
                       cfg=load_config(db), **FIXED_POLICY)
    job_id = str(res["job"]["id"])
    answer_worker.Worker(concurrency=1, once=True, produce_fn=answer_worker._fake_produce,
                         worker_prefix="zztest-%s" % uuid.uuid4().hex[:6]).run()
    done = jobs.get_job(db, job_id)
    check("test job completed (fake producer)", bool(done and done["status"] == "done" and done["answer"]),
          done["status"] if done else "None")
    answer_text = done["answer"]

    # Give the job non-empty citations + verified_references so we can prove the
    # SAME columns chat.py persists round-trip through the assistant message.
    sample_cites = [{"author": "Test Author", "title": "Test Work", "chunk_id": "c1"}]
    sample_refs = [{"reference": "John 3:16", "verified": True}]
    set_job_refs(db, job_id, sample_cites, sample_refs)

    # Real auth users (conversations.user_id -> auth.users FK). Two distinct users
    # so the single-flight-separation check is meaningful.
    users = real_user_ids(db, 2)
    if len(users) < 2:
        check("need >=2 real auth users to run the persistence test", False, "found=%d" % len(users))
        return
    uA, uB = users[0], users[1]
    cidA = str(uuid.uuid4())          # user A threads an explicit conversation id
    _conv_ids.append(cidA)

    # -- user A reads the result (auth) -> persisted to their history --
    rA = client.get("/async-chat/result/%s?conversation_id=%s" % (job_id, cidA),
                    headers={"x-test-user": uA})
    metaA = parse_sse_meta(rA.text)
    check("result returns the reader's conversation_id (chat.py parity)",
          metaA.get("conversation_id") == cidA, str(metaA.get("conversation_id")))
    check("result returns an assistant message_id (chat.py parity)", bool(metaA.get("message_id")),
          str(metaA.get("message_id")))

    conv = conversation_row(db, cidA)
    check("conversations row created for the user (id, user_id, title)",
          bool(conv) and str(conv["user_id"]) == uA and conv["title"] == " ".join(q.split()[:6]),
          "%s" % (conv,))

    msgs = messages_for(db, cidA)
    by_role = {m["role"]: m for m in msgs}
    check("exactly one user + one assistant message (chat.py shape)",
          len(msgs) == 2 and "user" in by_role and "assistant" in by_role,
          "roles=%s" % [m["role"] for m in msgs])
    check("user message content == the question",
          by_role.get("user", {}).get("content") == q)
    check("assistant message content == the verified answer",
          by_role.get("assistant", {}).get("content") == answer_text)
    check("assistant message carries citations + verified_references (same columns as chat.py)",
          by_role.get("assistant", {}).get("citations") == sample_cites
          and by_role.get("assistant", {}).get("verified_references") == sample_refs,
          "cites=%s refs=%s" % (by_role.get("assistant", {}).get("citations"),
                                by_role.get("assistant", {}).get("verified_references")))
    check("assistant message_id matches the id returned in meta",
          str(by_role.get("assistant", {}).get("id")) == str(metaA.get("message_id")))

    # -- reconnect: same user re-GETs the same job -> NO duplicate rows --
    client.get("/async-chat/result/%s?conversation_id=%s" % (job_id, cidA),
               headers={"x-test-user": uA})
    msgs2 = messages_for(db, cidA)
    check("reconnect (re-GET) does NOT duplicate persistence (idempotent)", len(msgs2) == 2,
          "messages after reconnect=%d" % len(msgs2))

    # -- single-flight persistence: user B reads the SAME job, own conversation --
    cidB = conversation_store.resolve_conversation_id(None, job_id, uB)
    _conv_ids.append(cidB)
    rB = client.get("/async-chat/result/%s" % job_id, headers={"x-test-user": uB})
    metaB = parse_sse_meta(rB.text)
    check("under single-flight, user B gets a DIFFERENT conversation than user A",
          metaB.get("conversation_id") == cidB and cidB != cidA,
          "A=%s B=%s" % (cidA[:8], str(metaB.get("conversation_id"))[:8]))
    convB = conversation_row(db, cidB)
    msgsB = messages_for(db, cidB)
    check("user B has their OWN persisted history for the shared generation",
          bool(convB) and str(convB["user_id"]) == uB and len(msgsB) == 2,
          "conv=%s msgs=%d" % (bool(convB), len(msgsB)))

    # -- guest reader: answer delivered, but NOT persisted (chat.py parity) --
    rG = client.get("/async-chat/result/%s" % job_id)  # no auth
    metaG = parse_sse_meta(rG.text)
    check("guest reader gets the answer but no conversation_id (not persisted)",
          metaG.get("conversation_id") is None, str(metaG.get("conversation_id")))


def main():
    print("=" * 70)
    print("Async metering + persistence parity proof (Blockers 2 & 3)")
    print("=" * 70)
    db = Db()
    client = build_client()
    # Snapshot originals so we can restore the monkeypatched module globals.
    orig_get_supabase = async_chat.get_supabase
    orig_current_policy = async_chat.current_policy
    try:
        cleanup(db)
        blocker2_metering(db, client)
        blocker3_persistence(db, client)
    finally:
        async_chat.get_supabase = orig_get_supabase
        async_chat.current_policy = orig_current_policy
        cleanup(db)
        db.close()

    print("\n" + "=" * 70)
    print("SUMMARY: %d/%d checks passed" % (_pass, _pass + _fail))
    print("Cleaned up all ZZTEST rows (jobs, conversations, messages).")
    print("=" * 70)
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
