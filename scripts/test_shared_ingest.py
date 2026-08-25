#!/usr/bin/env python3
"""
test_shared_ingest.py — DB-free / network-free fixture proof that
shared_ingest.ingest_document() correctly runs a queued source (a web
article, in these fixtures) through the shared chokepoint: document
insert, chunk insert, the chunk-id back-link fetch, v3.1 named-author
proposition generation, and atomic all-or-nothing commit/rollback.

This is the first direct test of shared_ingest.ingest_document() itself
(existing coverage only exercises it indirectly through
source_ingest_queue.processor's injectable writer_fn seam). Built to
satisfy the source-ingest runner's blog-ingestion work: "prove a valid
article flows through the existing shared writer contract" without ever
calling a real model provider or opening a real database connection.

Same established DB-free convention as test_propositions_closeness_gate.py
and test_propositions_book_chapters.py: hand-built FakeConn/FakeCursor,
and module-global function/attribute reassignment (this codebase's
existing, deliberate pattern for psycopg2.extras.execute_values, which
calls real C-extension internals a hand-built fake cursor cannot satisfy)
rather than a mocking framework. Every reassignment is saved and restored
in a finally block so no test leaks state into another test or module.

Run: python3 scripts/test_shared_ingest.py
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import shared_ingest  # noqa: E402
import propositions as props_mod  # noqa: E402
from magazine_review.schemas import ApprovedPropositionSet  # noqa: E402
from source_resolver import SENTINEL_SOURCE_ID  # noqa: E402
from source_ingest_queue.processor import execute_ingest, PreparedIngest  # noqa: E402


# ── Fake conn/cursor (DB-free) — same shape as test_propositions_*.py ──────

class FakeCursor:
    def __init__(self, *, license_status="unlicensed", chunk_id_rows=None, source_name_row=None):
        self._license_status = license_status
        self._chunk_id_rows = chunk_id_rows or []
        self._source_name_row = source_name_row
        self.executed = []  # [(sql, params), ...]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        last_sql = self.executed[-1][0] if self.executed else ""
        if "license_status" in last_sql:
            return (self._license_status,)
        if "SELECT name FROM sources" in last_sql:
            return self._source_name_row
        return None

    def fetchall(self):
        last_sql = self.executed[-1][0] if self.executed else ""
        if "FROM chunks WHERE document_id" in last_sql:
            return [(row_id,) for row_id in self._chunk_id_rows]
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    def __init__(self, **kwargs):
        self._cursor = FakeCursor(**kwargs)
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def inserted_sql(self, needle):
        return [(sql, params) for sql, params in self._cursor.executed if needle in sql]


class FakePsycopg2Module:
    """Stands in for the real `psycopg2` module inside shared_ingest's own
    namespace only -- the global psycopg2 module used by every other part
    of the process is never touched."""

    def __init__(self, conn):
        self._conn = conn
        self.connect_calls = []

    def connect(self, **kwargs):
        self.connect_calls.append(kwargs)
        return self._conn


class FakeEmbeddingItem:
    def __init__(self, index, embedding):
        self.index = index
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self, data):
        self.data = data


class FakeEmbeddings:
    def __init__(self, calls):
        self._calls = calls

    def create(self, *, input, model, dimensions):
        self._calls.append(list(input))
        return FakeEmbeddingResponse(
            [FakeEmbeddingItem(i, [0.001 * (i + 1)] * dimensions) for i in range(len(input))]
        )


class FakeOpenAIClient:
    def __init__(self, calls):
        self.embeddings = FakeEmbeddings(calls)


def fake_execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
    cur.executed.append((sql, list(argslist)))


def fake_proposition_embedding(text):
    return [0.01, 0.02, 0.03]


class _Patched:
    """Context manager: save/restore a list of (obj, attr, value) triples."""

    def __init__(self, *assignments):
        self._assignments = assignments
        self._originals = []

    def __enter__(self):
        for obj, attr, value in self._assignments:
            self._originals.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, value)
        return self

    def __exit__(self, *exc_info):
        for obj, attr, original in reversed(self._originals):
            setattr(obj, attr, original)
        return False


def canned_propositions():
    return [
        {"proposition_index": 1, "content": "First real teaching point from the article."},
        {"proposition_index": 2, "content": "Second real teaching point from the article."},
    ]


def substantive_body_text():
    """>= MIN_SUBSTANTIVE_WORD_COUNT (50) words, so process_document()
    proceeds past its word-count floor to a real extraction call instead
    of short-circuiting to "too_thin_to_extract" before this fixture's
    fake extract_propositions() is ever reached."""
    return (
        "The complete extracted article body text about grace and truth, "
        "written to be long enough that it clears the minimum substantive "
        "word count floor comfortably, so this fixture exercises the real "
        "extraction call path rather than the too-thin short circuit that "
        "a shorter body would trigger before reaching that call at all, "
        "with a closing sentence added here purely to push the total word "
        "count safely past fifty for this specific fixture's own purpose."
    )


class SharedWriterHappyPathTests(unittest.TestCase):
    def test_approved_set_crosses_atomic_writer_without_regeneration(self):
        article_text = substantive_body_text()
        approved = ApprovedPropositionSet(
            article_id="reviewed-article",
            article_hash=hashlib.sha256(article_text.encode("utf-8")).hexdigest(),
            model=props_mod.EXTRACTION_MODEL,
            prompt_version="v3.1",
            prompt_fingerprint=props_mod.prompt_fingerprint("v3.1"),
            proposition_artifact_hash="b" * 64,
            propositions=(
                (1, "Exact reviewed text with  intentional spacing."),
                (2, "Exact reviewed text with a\nline break."),
            ),
        )
        capability = props_mod._ValidatedReviewedPropositions(
            article_id=approved.article_id,
            article_hash=approved.article_hash,
            speaker="Ada North",
            model=approved.model,
            prompt_version=approved.prompt_version,
            prompt_fingerprint=approved.prompt_fingerprint,
            proposition_artifact_hash=approved.proposition_artifact_hash,
            propositions=approved.propositions,
        )
        conn = FakeConn(license_status="unlicensed", chunk_id_rows=["chunk-a"])

        def forbidden_generation(*args, **kwargs):
            raise AssertionError("reviewed ingestion must not regenerate")

        with _Patched(
            (shared_ingest, "psycopg2", FakePsycopg2Module(conn)),
            (shared_ingest, "execute_values", fake_execute_values),
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "_get_openai_client", lambda: FakeOpenAIClient([])),
            (shared_ingest, "embed_text", fake_proposition_embedding),
            (props_mod, "execute_values", fake_execute_values),
            (props_mod, "extract_propositions", forbidden_generation),
        ):
            result = shared_ingest.ingest_document(
                db=object(),
                db_params={},
                title="Reviewed article",
                body_text=article_text,
                filename="reviewed.md",
                author="Ada North",
                source_name="New Wine Magazine",
                source_id="22222222-2222-2222-2222-222222222222",
                skip_dedup=True,
                _reviewed_propositions=capability,
            )

        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["propositions"], "stored:2")
        inserts = conn.inserted_sql("INSERT INTO propositions")
        self.assertEqual([params[2] for _sql, params in inserts], [
            content for _index, content in approved.propositions
        ])
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)

    def test_web_article_flows_through_document_chunks_and_v31_propositions_atomically(self):
        conn = FakeConn(
            license_status="unlicensed",
            chunk_id_rows=["chunk-a", "chunk-b"],
        )
        openai_calls = []
        extract_calls = []

        def fake_extract_propositions(text, doc_id="", speaker=None, prompt_version=None):
            extract_calls.append(
                {"text": text, "doc_id": doc_id, "speaker": speaker, "prompt_version": prompt_version}
            )
            return canned_propositions()

        with _Patched(
            (shared_ingest, "psycopg2", FakePsycopg2Module(conn)),
            (shared_ingest, "execute_values", fake_execute_values),
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "_get_openai_client", lambda: FakeOpenAIClient(openai_calls)),
            (shared_ingest, "embed_text", fake_proposition_embedding),
            (props_mod, "execute_values", fake_execute_values),
            (props_mod, "extract_propositions", fake_extract_propositions),
        ):
            result = shared_ingest.ingest_document(
                db=object(),
                db_params={},
                title="Grace and Truth",
                body_text=substantive_body_text(),
                filename="grace-and-truth.html",
                author="Derek Prince",
                source_name="Derek Prince",
                source_type="article",
                source_kind="unknown",
                citation_mode="silent_context",
                url="https://example.com/blog/grace-and-truth",
                file_path="grace-and-truth.html",
                source_id="22222222-2222-2222-2222-222222222222",
                allow_sentinel=False,
            )

        # ── Document preparation ──
        self.assertEqual(result["status"], "processed")
        doc_inserts = conn.inserted_sql("INSERT INTO documents")
        self.assertEqual(len(doc_inserts), 1)

        # ── Chunks ──
        chunk_inserts = conn.inserted_sql("INSERT INTO chunks")
        self.assertEqual(len(chunk_inserts), 1)
        _sql, rows = chunk_inserts[0]
        self.assertEqual(len(rows), 1)  # one short body -> one chunk

        # ── Embeddings through an injected/test double, never the network ──
        self.assertEqual(len(openai_calls), 1)
        self.assertIn("grace", openai_calls[0][0])

        # ── v3.1 named-author proposition generation through an injected double ──
        self.assertEqual(len(extract_calls), 1)
        self.assertEqual(extract_calls[0]["speaker"], "Derek Prince")
        self.assertEqual(extract_calls[0]["prompt_version"], "v3.1")

        prop_inserts = conn.inserted_sql("INSERT INTO propositions")
        self.assertEqual(len(prop_inserts), 2)
        for _sql, params in prop_inserts:
            self.assertEqual(params[5], "v3.1")  # prompt_version column

        # ── Proposition-to-chunk links (cartesian product: 2 props x 2 chunks) ──
        link_inserts = conn.inserted_sql("INSERT INTO proposition_chunks")
        self.assertEqual(len(link_inserts), 1)
        _sql, pairs = link_inserts[0]
        self.assertEqual(len(pairs), 4)
        self.assertEqual({chunk_id for _prop_id, chunk_id in pairs}, {"chunk-a", "chunk-b"})

        # ── Atomic commit, never rolled back on the happy path ──
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)
        self.assertTrue(conn.closed)

    def test_exact_attempted_stored_skipped_errored_accounting_through_the_queue_contract(self):
        """The same happy-path flow, but driven through
        source_ingest_queue.processor.execute_ingest() (the queue's own
        writer_fn call), proving the exact reconciliation counts the runner
        actually persists to source_ingest_queue are correct for a real
        (faked-leaves) shared_ingest.ingest_document() call, not just a
        stubbed writer_fn as the existing processor tests use."""
        conn = FakeConn(license_status="unlicensed", chunk_id_rows=["chunk-a"])
        prepared = PreparedIngest(
            row_id="11111111-1111-1111-1111-111111111111",
            source_id="22222222-2222-2222-2222-222222222222",
            title="A Real Post",
            author="Derek Prince",
            source_name="Derek Prince",
            body_text="Real article body text, long enough for one chunk.",
            filename="a-real-post.html",
            source_url="https://example.com/blog/a-real-post",
            source_type="article",
            source_kind="unknown",
            citation_mode="silent_context",
            year=None,
            topic_tags=[],
            bible_references=[],
            page_count=1,
            chunk_count=1,
            content_sha256="abc",
            fetched_bytes=52,
            duplicate=False,
        )

        with _Patched(
            (shared_ingest, "psycopg2", FakePsycopg2Module(conn)),
            (shared_ingest, "execute_values", fake_execute_values),
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "_get_openai_client", lambda: FakeOpenAIClient([])),
            (shared_ingest, "embed_text", fake_proposition_embedding),
            (props_mod, "execute_values", fake_execute_values),
            (props_mod, "extract_propositions", lambda *a, **k: canned_propositions()),
        ):
            outcome = execute_ingest(prepared, db=object(), db_params={})

        self.assertEqual(outcome.status, "processed")
        self.assertEqual((outcome.attempted, outcome.stored, outcome.skipped, outcome.errored), (1, 1, 0, 0))
        self.assertIsNotNone(outcome.document_id)


class SharedWriterFailureAndBoundaryTests(unittest.TestCase):
    def test_proposition_generation_failure_leaves_no_partial_document_chunks_or_propositions(self):
        conn = FakeConn(license_status="unlicensed", chunk_id_rows=["chunk-a"])

        def failing_extract(text, doc_id="", speaker=None, prompt_version=None):
            raise RuntimeError("groq is down")

        with _Patched(
            (shared_ingest, "psycopg2", FakePsycopg2Module(conn)),
            (shared_ingest, "execute_values", fake_execute_values),
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "_get_openai_client", lambda: FakeOpenAIClient([])),
            (shared_ingest, "embed_text", fake_proposition_embedding),
            (props_mod, "execute_values", fake_execute_values),
            (props_mod, "extract_propositions", failing_extract),
        ):
            result = shared_ingest.ingest_document(
                db=object(),
                db_params={},
                title="A Post That Fails",
                body_text=substantive_body_text(),
                filename="fails.html",
                author="Derek Prince",
                source_name="Derek Prince",
                source_id="22222222-2222-2222-2222-222222222222",
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "paraphrase_failed")
        self.assertIsNone(result["doc_id"])
        # The document/chunk INSERTs were staged on the connection (the
        # atomic-transaction design computes chunking/embedding first, then
        # writes record+chunks+propositions together) but never committed --
        # rollback is the only thing that actually happened durably.
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)
        self.assertEqual(conn.inserted_sql("INSERT INTO propositions"), [])

    def test_resolve_from_path_refuses_silent_sentinel_fallback_before_any_db_write(self):
        """A caller using resolve_from=(...) (not the queue's pre-resolved
        source_id path) must never silently land an unresolved author on
        the sentinel source. No psycopg2 module is patched at all here --
        if this refusal did not fire before any write, the test would fail
        loudly (a real connection attempt against an empty db_params dict),
        never silently pass."""

        def resolve_to_sentinel(db, source_name, author):
            return SENTINEL_SOURCE_ID, "unknown person", "MISS"

        with _Patched(
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "resolve_source_id", resolve_to_sentinel),
        ):
            with self.assertRaises(shared_ingest.SilentSentinelRefused):
                shared_ingest.ingest_document(
                    db=object(),
                    db_params={},
                    title="Unknown Author Post",
                    body_text="Body text for an article with no resolvable author.",
                    filename="unknown.html",
                    resolve_from=("Unknown Person", None),
                    allow_sentinel=False,
                )

    def test_duplicate_content_is_skipped_before_any_db_write(self):
        """Same no-psycopg2-patch guard as the sentinel test above: if the
        dedup short-circuit ever regressed, this would fail with a real
        connection error against db_params={}, not silently pass."""
        with _Patched((shared_ingest, "already_ingested", lambda *a, **k: True)):
            result = shared_ingest.ingest_document(
                db=object(),
                db_params={},
                title="Already Ingested Post",
                body_text="Doesn't matter, dedup short-circuits before this is read.",
                filename="dup.html",
                source_id="22222222-2222-2222-2222-222222222222",
            )

        self.assertEqual(result, {
            "status": "skipped", "reason": "already_ingested",
            "doc_id": None, "source_id": None, "chunks": [], "propositions": None,
        })

    def test_article_below_substantive_threshold_commits_document_and_chunks_honestly(self):
        """A too-thin article is not silently dropped and not silently
        credited with propositions it never got: the document and its
        chunks are still committed (a real, retrievable record exists),
        and the writer's own return value truthfully reports
        "too_thin_to_extract" rather than pretending a normal success."""
        conn = FakeConn(license_status="unlicensed", chunk_id_rows=["chunk-a"])

        def extract_should_not_be_called(*a, **k):
            raise AssertionError("extract_propositions must not run below the word floor")

        with _Patched(
            (shared_ingest, "psycopg2", FakePsycopg2Module(conn)),
            (shared_ingest, "execute_values", fake_execute_values),
            (shared_ingest, "already_ingested", lambda *a, **k: False),
            (shared_ingest, "_get_openai_client", lambda: FakeOpenAIClient([])),
            (shared_ingest, "embed_text", fake_proposition_embedding),
            (props_mod, "execute_values", fake_execute_values),
            (props_mod, "extract_propositions", extract_should_not_be_called),
        ):
            result = shared_ingest.ingest_document(
                db=object(),
                db_params={},
                title="Just a few words",
                body_text="Too short to be a real article.",
                filename="thin.html",
                author="Derek Prince",
                source_name="Derek Prince",
                source_id="22222222-2222-2222-2222-222222222222",
            )

        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["propositions"], "too_thin_to_extract")
        self.assertEqual(len(conn.inserted_sql("INSERT INTO documents")), 1)
        self.assertEqual(len(conn.inserted_sql("INSERT INTO chunks")), 1)
        self.assertEqual(conn.inserted_sql("INSERT INTO propositions"), [])
        self.assertTrue(conn.committed)
        self.assertFalse(conn.rolled_back)


if __name__ == "__main__":
    unittest.main()
