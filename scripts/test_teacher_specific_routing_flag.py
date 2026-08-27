#!/usr/bin/env python3
"""Regression proof for the B6-F1 production-activation flag (migration 091).

Offline only -- no DB/network. Proves three things:
  1. AsyncAnswerConfig defaults experimental_teacher_routing_enabled to False.
  2. load_config() maps the new column onto that field.
  3. Worker._tick() threads cfg.experimental_teacher_routing_enabled straight
     into produce_fn's experimental_teacher_routing kwarg, both ways.

Does not touch producer.py's own routing/retrieval behavior -- that was
already reviewed and accepted (PLAN.md B6-F1, 2026-08-26). This only proves
the flag reaches the one real caller correctly.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services.async_answers.config import AsyncAnswerConfig, load_config  # noqa: E402

import answer_worker  # noqa: E402


class _FakeDb:
    """load_config()'s db.run(fn) contract is `fn(conn) -> row-or-None`; this
    fake skips straight to a canned row so the test exercises load_config's
    field-mapping, not psycopg2/dict_cursor plumbing."""

    def __init__(self, row):
        self._row = row

    def run(self, fn):
        return self._row


class ConfigDefaultTest(unittest.TestCase):
    def test_dataclass_defaults_to_off(self) -> None:
        cfg = AsyncAnswerConfig()
        self.assertFalse(cfg.experimental_teacher_routing_enabled)

    def test_missing_row_defaults_to_off(self) -> None:
        cfg = load_config(_FakeDb(None))
        self.assertFalse(cfg.experimental_teacher_routing_enabled)

    def test_load_config_maps_column_true(self) -> None:
        row = _full_row(experimental_teacher_routing_enabled=True)
        cfg = load_config(_FakeDb(row))
        self.assertTrue(cfg.experimental_teacher_routing_enabled)

    def test_load_config_maps_column_false(self) -> None:
        row = _full_row(experimental_teacher_routing_enabled=False)
        cfg = load_config(_FakeDb(row))
        self.assertFalse(cfg.experimental_teacher_routing_enabled)


def _full_row(experimental_teacher_routing_enabled: bool):
    return {
        "paused": False,
        "max_queue_depth": 5000,
        "reuse_ttl_seconds": 0,
        "rpm_limit": None,
        "itpm_limit": None,
        "otpm_limit": None,
        "spend_ceiling_usd": None,
        "spend_window": "rolling_24h",
        "lease_seconds": 300,
        "serving_enabled": True,
        "experimental_teacher_routing_enabled": experimental_teacher_routing_enabled,
    }


class WorkerTickThreadsFlagTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_load_config = answer_worker.load_config
        self._orig_claim_next = answer_worker.jobs.claim_next
        self._orig_complete = answer_worker.jobs.complete
        self._orig_spend_ok = answer_worker.budget.spend_ok
        self._orig_reserve_rate = answer_worker.budget.reserve_rate
        self._orig_reconcile_rate = answer_worker.budget.reconcile_rate

        answer_worker.budget.spend_ok = lambda db, cfg: True
        answer_worker.budget.reserve_rate = lambda db, cfg, est_in, est_out: True
        answer_worker.budget.reconcile_rate = lambda *a, **k: None
        answer_worker.jobs.claim_next = lambda db, worker_id, lease_seconds: {
            "id": "job-1", "question": "What does Derek Prince teach about deliverance?",
            "messages": [], "topics_established": {},
        }
        answer_worker.jobs.complete = lambda *a, **k: None

    def tearDown(self) -> None:
        answer_worker.load_config = self._orig_load_config
        answer_worker.jobs.claim_next = self._orig_claim_next
        answer_worker.jobs.complete = self._orig_complete
        answer_worker.budget.spend_ok = self._orig_spend_ok
        answer_worker.budget.reserve_rate = self._orig_reserve_rate
        answer_worker.budget.reconcile_rate = self._orig_reconcile_rate

    def _run_tick(self, flag_value: bool):
        answer_worker.load_config = lambda db: AsyncAnswerConfig(
            experimental_teacher_routing_enabled=flag_value
        )
        calls = []

        def _fake_produce_fn(supabase, question, messages, topics_established, **kwargs):
            calls.append(kwargs)
            return answer_worker.ProducerResult(
                answer="stub", outcome="answered", citations=[], verified_references=[],
                retrieved_chunk_ids=[], retrieved_point_ids=[], model="fake",
                input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
                cost_usd=0.0, updated_topics={},
            )

        worker = answer_worker.Worker(produce_fn=_fake_produce_fn)
        worker._supabase = "fake-supabase-client"
        did_work = worker._tick(db=None, worker_id="test-worker")
        self.assertTrue(did_work)
        self.assertEqual(1, len(calls))
        return calls[0]

    def test_flag_on_threads_true_into_produce_fn(self) -> None:
        kwargs = self._run_tick(True)
        self.assertEqual({"experimental_teacher_routing": True}, kwargs)

    def test_flag_off_threads_false_into_produce_fn(self) -> None:
        kwargs = self._run_tick(False)
        self.assertEqual({"experimental_teacher_routing": False}, kwargs)


class FakeProduceAcceptsFlagTest(unittest.TestCase):
    def test_fake_produce_ignores_the_kwarg_without_error(self) -> None:
        import os

        os.environ["ASYNC_FAKE_LATENCY"] = "0"
        result = answer_worker._fake_produce(
            "fake-supabase", "a question", [], {}, experimental_teacher_routing=True
        )
        self.assertEqual("answered", result.outcome)


if __name__ == "__main__":
    unittest.main()
