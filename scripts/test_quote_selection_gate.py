#!/usr/bin/env python3
"""Repository-only regression coverage for the quote-selection containment gate.

Run from the repository root:
  /private/tmp/newwine-w1w4-venv/bin/python scripts/test_quote_selection_gate.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
# async_chat imports auth at module load; this inert URL keeps the test's
# direct SSE-generator coverage local and prevents any network use.
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

from app.services import quotes
from app.services.async_answers import jobs, producer
from app.services import (
    position_papers,
    reference_verifier,
    single_teacher_lock,
    stored_position_evidence,
    stored_position_topics,
)
from app.routers import async_chat


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if not condition:
        raise AssertionError(label)


def _producer_result_with_quote_gate(env_value, selector):
    """Exercise the real producer return value with all external work stubbed.

    The selection call is the one behavior under test; retrieval/generation are
    deterministic local fixtures so this test neither reads nor writes a database.
    """
    chunk = {
        "id": "chunk-1",
        "document_id": "document-1",
        "author": "Teacher One",
        "content": "Supported answer material.",
        "citation_mode": "citable",
    }
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(position_papers, "match_position_paper", return_value=None), \
         patch.object(stored_position_topics, "match_stored_position", return_value=None), \
         patch.object(stored_position_evidence, "fetch_stored_position_evidence", return_value=None), \
         patch.object(producer, "_inject_background_topics", return_value=([], set(), {})), \
         patch.object(producer, "_retrieve", return_value=([chunk], [], 1, False)), \
         patch.object(producer, "_build_context", return_value="context"), \
         patch.object(producer, "_build_history", return_value=[]), \
         patch.object(producer, "_generate_and_capture", return_value=("Teacher One gives a supported answer.", "raw", None, usage, "test-model")), \
         patch.object(reference_verifier, "build_retrieval_grounding", return_value={}), \
         patch.object(reference_verifier, "build_name_universe", return_value=[]), \
         patch.object(reference_verifier, "ungrounded_prose_teachers", return_value=False), \
         patch.object(reference_verifier, "verify_references", return_value=[]), \
         patch.object(producer, "estimate_cost_usd", return_value=0.0), \
         patch.object(single_teacher_lock, "resolve_source_ids_for_documents", return_value={"document-1": "source-1"}), \
         patch.object(quotes, "select_quotes_for_answer", selector):
        return producer.produce(object(), "What does the teacher say?")


class _CaptureCursor:
    def __init__(self):
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, params):
        self.params = params


class _CaptureConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _CaptureDb:
    def __init__(self):
        self.cursor = _CaptureCursor()

    def run(self, work):
        work(_CaptureConnection(self.cursor))


class _NoopDb:
    def close(self):
        pass


async def _sse_meta_for_persisted_job(job, env_value=None):
    """Run the real completed-job SSE generator and return its meta object."""
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(async_chat, "Db", return_value=_NoopDb()), \
         patch.object(async_chat.jobs, "get_job", return_value=job):
        response = await async_chat.result("job-1", None, user_id=None)
        events = []
        async for chunk in response.body_iterator:
            events.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return next(
        json.loads(event[len("data: "):].strip())
        for event in events
        if event.startswith("data: ") and "quote_ids" in event
    )


def _persist_and_serialize_quote_ids(result):
    """Exercise the real jobs.complete -> async_chat.result quote-ID contract.

    This catches a persistence or SSE mutation that replaces the disabled
    producer's empty quote-ID list with a nonempty value downstream.
    """
    db = _CaptureDb()
    jobs.complete(
        db,
        job_id="job-1",
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
        updated_topics=result.updated_topics,
        quote_ids=result.quote_ids,
    )
    persisted_quote_ids = db.cursor.params[13].adapted
    job = {
        "status": "done",
        "answer": result.answer,
        "outcome": result.outcome,
        "citations": result.citations,
        "verified_references": result.verified_references,
        "quote_ids": persisted_quote_ids,
        "result_meta": {"updated_topics": result.updated_topics},
        "evidence_version": "test-evidence",
    }
    return persisted_quote_ids, asyncio.run(_sse_meta_for_persisted_job(job))


def _policy_with_quote_flag(env_value):
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(
             producer,
             "get_disabled_filters",
             return_value={
                 "source_kinds": ["commentary"],
                 "source_names": ["Excluded Source"],
                 "include_copyrighted": False,
             },
         ), \
         patch.object(producer, "get_corpus_version", return_value="test-corpus"):
        return producer.current_policy(object())


class _ShareableCursor:
    def __init__(self, existing_job, status):
        self._existing_job = existing_job
        self._status = status
        self._query = ""
        self._params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self._query = " ".join(query.split())
        self._params = params

    def fetchone(self):
        if self._params[0] != self._existing_job["dedup_key"]:
            return None
        if self._status == "done" and "status = 'done'" in self._query:
            return self._existing_job
        if self._status == "queued" and "status IN ('queued','running')" in self._query:
            return self._existing_job
        return None


class _ShareableDb:
    def __init__(self, existing_job, status):
        self._cursor = _ShareableCursor(existing_job, status)

    def run(self, work):
        return work(_CaptureConnection(self._cursor))


def main():
    print("quote selection containment gate")
    print("=" * 60)

    check("absent flag disables quote selection", quotes.quote_selection_enabled({}) is False)
    check("false flag disables quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "false"}) is False)
    check("only exact true flag enables quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "true"}) is True)
    check("case variants do not enable quote selection", quotes.quote_selection_enabled({"QUOTE_SELECTION_ENABLED": "TRUE"}) is False)

    disabled_policy = _policy_with_quote_flag(None)
    enabled_policy = _policy_with_quote_flag("true")
    check(
        "quote gate preserves legacy answer policy fields",
        set(disabled_policy) == {
            "filters", "evidence_version", "prompt_version", "policy_version"
        },
    )
    check(
        "off/on answer policy identities differ",
        disabled_policy["policy_version"] != enabled_policy["policy_version"],
    )
    disabled_key = jobs.compute_dedup_key(
        "What does the teacher say?",
        disabled_policy["filters"],
        disabled_policy["evidence_version"],
        disabled_policy["prompt_version"],
        disabled_policy["policy_version"],
    )
    enabled_key = jobs.compute_dedup_key(
        "What does the teacher say?",
        enabled_policy["filters"],
        enabled_policy["evidence_version"],
        enabled_policy["prompt_version"],
        enabled_policy["policy_version"],
    )
    check("off/on dedup identities differ", disabled_key != enabled_key)

    reuse_cfg = SimpleNamespace(reuse_ttl_seconds=300)
    completed_off_job = {"id": "completed-off", "dedup_key": disabled_key}
    check(
        "same-state completed answer remains reusable",
        jobs._find_shareable(
            _ShareableDb(completed_off_job, "done"),
            disabled_key,
            None,
            reuse_cfg,
        )["reason"] == "reuse",
    )
    check(
        "completed answer reuse does not cross quote-flag state",
        jobs._find_shareable(
            _ShareableDb(completed_off_job, "done"),
            enabled_key,
            None,
            reuse_cfg,
        ) is None,
    )
    active_off_job = {"id": "active-off", "dedup_key": disabled_key}
    check(
        "in-flight single-flight does not cross quote-flag state",
        jobs._find_shareable(
            _ShareableDb(active_off_job, "queued"),
            enabled_key,
            None,
            reuse_cfg,
        ) is None,
    )

    preexisting_job = {
        "status": "done",
        "answer": "A previously completed answer.",
        "outcome": "answered",
        "citations": [],
        "verified_references": [],
        "quote_ids": ["persisted-quote-1", "persisted-quote-2"],
        "result_meta": {"updated_topics": {}},
        "evidence_version": "test-evidence",
    }
    check(
        "disabled delivery suppresses persisted quote IDs",
        asyncio.run(_sse_meta_for_persisted_job(preexisting_job))["quote_ids"] == [],
    )
    check(
        "exact true delivery preserves persisted quote IDs",
        asyncio.run(_sse_meta_for_persisted_job(preexisting_job, "true"))["quote_ids"]
        == ["persisted-quote-1", "persisted-quote-2"],
    )

    def selector_must_not_run(*_args, **_kwargs):
        raise AssertionError("disabled producer called quote selector")

    disabled_result = _producer_result_with_quote_gate(None, selector_must_not_run)
    check("disabled producer emits no quote IDs", disabled_result.quote_ids == [])
    persisted_quote_ids, sse_meta = _persist_and_serialize_quote_ids(disabled_result)
    check("persistence stores disabled answer with no quote IDs", persisted_quote_ids == [])
    check("SSE serializes disabled answer with no quote IDs", sse_meta["quote_ids"] == [])

    enabled_result = _producer_result_with_quote_gate(
        "true", lambda *_args, **_kwargs: ["quote-1"]
    )
    check("enabled producer preserves selector output", enabled_result.quote_ids == ["quote-1"])


if __name__ == "__main__":
    main()
