"""Async answer path -- the ONLY answer path (2026-08-07, mirror-unification
job complete: chat.py, the old synchronous /chat endpoint, is deleted).

Provides a durable, horizontally-scalable answer-generation queue backed by
the existing Supabase Postgres:

  - db.py        reconnect-resilient psycopg2 access
  - config.py    the one-row control plane (dials)
  - budget.py    provider rate-limit reservation + spend ceiling
  - jobs.py      enqueue / claim / complete / reclaim (idempotency, single-flight, reuse)
  - producer.py  produces the verified answer, reusing retrieval leaf helpers
                 from app.services.answer_toolbox (moved out of chat.py
                 2026-08-07, batch 1) and reference_verifier's accuracy check
  - metering.py  fail-closed guest/user query-limit metering, called from
                 async_chat.py's /submit route -- the single metering
                 implementation (chat.py used to keep its own duplicate
                 inline copy; consolidated onto this module in batch 3,
                 before chat.py itself was deleted in batch 4)

The worker entrypoint is scripts/answer_worker.py. The HTTP surface is
backend/app/routers/async_chat.py. See CLAUDE.md 2026-08-03 decision #14.
"""
