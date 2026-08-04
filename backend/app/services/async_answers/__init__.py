"""Async answer path (Project 1, Stage 1).

INERT / additive. Nothing in this package is imported by the live serving path
(chat.py, main.py). It provides a durable, horizontally-scalable answer-
generation queue backed by the existing Supabase Postgres:

  - db.py        reconnect-resilient psycopg2 access
  - config.py    the one-row control plane (dials)
  - budget.py    provider rate-limit reservation + spend ceiling
  - jobs.py      enqueue / claim / complete / reclaim (idempotency, single-flight, reuse)
  - producer.py  produces the SAME verified answer the live path produces, by
                 reusing chat.py's retrieval + reference_verifier's accuracy check

The worker entrypoint is scripts/answer_worker.py. The (unmounted) HTTP surface
is backend/app/routers/async_chat.py. See CLAUDE.md 2026-08-03 decision #14.
"""
