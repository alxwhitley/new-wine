#!/usr/bin/env python3
"""Behavior checks for queued source preparation and shared-writer execution."""

import unittest

from source_ingest_queue.fetcher import FetchResult
from source_ingest_queue.pdf import ExtractedPdf
from source_ingest_queue.processor import (
    AttentionRequired,
    PreparedIngest,
    ProcessOutcome,
    RetryableIngestError,
    classify_row,
    execute_ingest,
    prepare_ingest,
)
from source_resolver import SENTINEL_SOURCE_ID


def valid_row():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "url": "https://example.com/original.pdf",
        "source_format": "pdf",
        "source_scope": "single",
        "attribution_mode": "declared",
        "attribute_to": " Derek Prince ",
        "retain_original_text": True,
    }


def fetched_pdf():
    return FetchResult(
        content=b"pdf bytes",
        final_url="https://cdn.example.com/final.pdf",
        sha256="abc123",
        byte_count=9,
        filename="final.pdf",
    )


class ClassifyRowTests(unittest.TestCase):
    def test_accepts_only_the_supported_first_slice(self):
        self.assertIsNone(
            classify_row(
                {
                    "source_format": "pdf",
                    "source_scope": "single",
                    "attribution_mode": "declared",
                    "attribute_to": " Derek Prince ",
                    "retain_original_text": True,
                }
            )
        )

    def test_returns_one_stable_reason_for_each_unsupported_shape(self):
        valid = {
            "source_format": "pdf",
            "source_scope": "single",
            "attribution_mode": "declared",
            "attribute_to": "Derek Prince",
            "retain_original_text": True,
        }
        cases = (
            ("source_format", "web_page", "unsupported_source_format"),
            ("source_scope", "collection", "unsupported_source_scope"),
            ("attribution_mode", "per_item", "unsupported_attribution_mode"),
            ("attribute_to", "  ", "declared_author_missing"),
            ("retain_original_text", False, "retention_policy_missing"),
            ("retain_original_text", None, "retention_policy_missing"),
        )

        for field, value, expected in cases:
            with self.subTest(field=field, value=value):
                row = dict(valid)
                row[field] = value
                self.assertEqual(classify_row(row), expected)


class PrepareIngestTests(unittest.TestCase):
    def test_dry_run_prepares_exact_read_only_identity_and_counts(self):
        calls = []
        db = object()
        db_params = {"dbname": "test"}

        def fetch(url):
            calls.append(("fetch", url))
            return fetched_pdf()

        def extract(content):
            calls.append(("extract", content))
            return ExtractedPdf(text="Complete original text", page_count=12)

        def resolve(given_db, source_name, author):
            calls.append(("resolve", given_db, source_name, author))
            return "22222222-2222-2222-2222-222222222222", "derek prince", "source_name"

        def servable(given_db, source_id):
            calls.append(("servable", given_db, source_id))
            return True

        def dedup(params, source_url, source_name, filename):
            calls.append(("dedup", params, source_url, source_name, filename))
            return False

        result = prepare_ingest(
            valid_row(),
            db=db,
            db_params=db_params,
            dry_run=True,
            fetch_fn=fetch,
            extract_fn=extract,
            resolve_fn=resolve,
            servable_fn=servable,
            dedup_fn=dedup,
            chunk_fn=lambda text: ["chunk one", "chunk two"],
            metadata_fn=lambda text: self.fail("dry run called metadata provider"),
        )

        self.assertIsInstance(result, PreparedIngest)
        self.assertEqual(result.row_id, valid_row()["id"])
        self.assertEqual(result.source_id, "22222222-2222-2222-2222-222222222222")
        self.assertEqual(result.author, "Derek Prince")
        self.assertEqual(result.source_name, "Derek Prince")
        self.assertEqual(result.body_text, "Complete original text")
        self.assertEqual(result.filename, "final.pdf")
        self.assertEqual(result.source_url, "https://cdn.example.com/final.pdf")
        self.assertEqual(result.page_count, 12)
        self.assertEqual(result.chunk_count, 2)
        self.assertEqual(result.content_sha256, "abc123")
        self.assertEqual(result.fetched_bytes, 9)
        self.assertFalse(result.duplicate)
        self.assertEqual(
            calls,
            [
                ("fetch", "https://example.com/original.pdf"),
                ("extract", b"pdf bytes"),
                ("resolve", db, "Derek Prince", None),
                ("servable", db, "22222222-2222-2222-2222-222222222222"),
                (
                    "dedup",
                    db_params,
                    "https://cdn.example.com/final.pdf",
                    "Derek Prince",
                    "final.pdf",
                ),
            ],
        )

    def test_stops_policy_and_attribution_failures_before_later_boundaries(self):
        boundary_calls = []

        with self.assertRaises(AttentionRequired) as unsupported:
            prepare_ingest(
                {**valid_row(), "source_format": "web_page"},
                db=object(),
                db_params={},
                dry_run=True,
                fetch_fn=lambda url: boundary_calls.append("fetch"),
            )
        self.assertEqual(unsupported.exception.code, "unsupported_source_format")
        self.assertEqual(boundary_calls, [])

        with self.assertRaises(AttentionRequired) as unresolved:
            prepare_ingest(
                valid_row(),
                db=object(),
                db_params={},
                dry_run=True,
                fetch_fn=lambda url: fetched_pdf(),
                extract_fn=lambda content: ExtractedPdf("Text", 1),
                resolve_fn=lambda *args: (SENTINEL_SOURCE_ID, "unknown", "MISS"),
                servable_fn=lambda *args: boundary_calls.append("servable"),
                dedup_fn=lambda *args: boundary_calls.append("dedup"),
                chunk_fn=lambda text: [text],
            )
        self.assertEqual(unresolved.exception.code, "source_unresolved")
        self.assertEqual(boundary_calls, [])

        with self.assertRaises(AttentionRequired) as hidden:
            prepare_ingest(
                valid_row(),
                db=object(),
                db_params={},
                dry_run=True,
                fetch_fn=lambda url: fetched_pdf(),
                extract_fn=lambda content: ExtractedPdf("Text", 1),
                resolve_fn=lambda *args: ("source-id", "derek prince", "source_name"),
                servable_fn=lambda *args: False,
                dedup_fn=lambda *args: boundary_calls.append("dedup"),
                chunk_fn=lambda text: [text],
            )
        self.assertEqual(hidden.exception.code, "source_not_servable")
        self.assertEqual(boundary_calls, [])

    def test_normal_mode_validates_metadata_and_retains_declared_identity(self):
        result = prepare_ingest(
            valid_row(),
            db=object(),
            db_params={},
            dry_run=False,
            fetch_fn=lambda url: fetched_pdf(),
            extract_fn=lambda content: ExtractedPdf("Text", 1),
            resolve_fn=lambda *args: ("source-id", "derek prince", "source_name"),
            servable_fn=lambda *args: True,
            dedup_fn=lambda *args: False,
            chunk_fn=lambda text: [text],
            metadata_fn=lambda text: {
                "title": "Model title",
                "author": "Wrong model author",
                "source_name": "Wrong model source",
                "year": 1984,
                "source_type": "book",
                "source_kind": "unknown",
                "citation_mode": "silent_context",
                "topic_tags": ["Prayer", 7, ""],
            },
        )

        self.assertEqual(result.title, "Model title")
        self.assertEqual(result.author, "Derek Prince")
        self.assertEqual(result.source_name, "Derek Prince")
        self.assertEqual(result.year, 1984)
        self.assertEqual(result.source_type, "book")
        self.assertEqual(result.topic_tags, ["Prayer"])

    def test_duplicate_skips_metadata_but_remains_a_prepared_outcome(self):
        result = prepare_ingest(
            valid_row(),
            db=object(),
            db_params={},
            dry_run=False,
            fetch_fn=lambda url: fetched_pdf(),
            extract_fn=lambda content: ExtractedPdf("Text", 1),
            resolve_fn=lambda *args: ("source-id", "derek prince", "source_name"),
            servable_fn=lambda *args: True,
            dedup_fn=lambda *args: True,
            chunk_fn=lambda text: [text],
            metadata_fn=lambda text: self.fail("duplicate called metadata provider"),
        )

        self.assertTrue(result.duplicate)

    def test_provider_and_boundary_errors_use_stable_retry_or_attention_codes(self):
        from source_ingest_queue.fetcher import FetchRejected, FetchTransient
        from source_ingest_queue.pdf import PdfRejected

        cases = (
            (
                AttentionRequired,
                "unsafe_url",
                lambda url: (_ for _ in ()).throw(FetchRejected("unsafe_url", "raw")),
                lambda content: ExtractedPdf("Text", 1),
                lambda text: {},
            ),
            (
                RetryableIngestError,
                "dns_failure",
                lambda url: (_ for _ in ()).throw(FetchTransient("dns_failure", "raw")),
                lambda content: ExtractedPdf("Text", 1),
                lambda text: {},
            ),
            (
                AttentionRequired,
                "pdf_empty",
                lambda url: fetched_pdf(),
                lambda content: (_ for _ in ()).throw(PdfRejected("pdf_empty", "raw")),
                lambda text: {},
            ),
            (
                RetryableIngestError,
                "metadata_provider_failure",
                lambda url: fetched_pdf(),
                lambda content: ExtractedPdf("Text", 1),
                lambda text: (_ for _ in ()).throw(RuntimeError("provider raw")),
            ),
        )

        for error_type, code, fetch, extract, metadata in cases:
            with self.subTest(code=code):
                with self.assertRaises(error_type) as raised:
                    prepare_ingest(
                        valid_row(),
                        db=object(),
                        db_params={},
                        dry_run=False,
                        fetch_fn=fetch,
                        extract_fn=extract,
                        resolve_fn=lambda *args: ("source-id", "key", "source_name"),
                        servable_fn=lambda *args: True,
                        dedup_fn=lambda *args: False,
                        chunk_fn=lambda text: [text],
                        metadata_fn=metadata,
                    )
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("raw", raised.exception.detail)


class ExecuteIngestTests(unittest.TestCase):
    def prepared(self, *, duplicate=False):
        return PreparedIngest(
            row_id="11111111-1111-1111-1111-111111111111",
            source_id="22222222-2222-2222-2222-222222222222",
            title="Model title",
            author="Derek Prince",
            source_name="Derek Prince",
            body_text="Complete original text",
            filename="final.pdf",
            source_url="https://cdn.example.com/final.pdf",
            source_type="book",
            source_kind="unknown",
            citation_mode="silent_context",
            year=1984,
            topic_tags=["Prayer"],
            bible_references=["John 3:16"],
            page_count=12,
            chunk_count=2,
            content_sha256="abc123",
            fetched_bytes=9,
            duplicate=duplicate,
        )

    def test_duplicate_returns_reconciled_skip_without_writer(self):
        result = execute_ingest(
            self.prepared(duplicate=True),
            db=object(),
            db_params={},
            writer_fn=lambda **kwargs: self.fail("duplicate called writer"),
        )

        self.assertEqual(
            result,
            ProcessOutcome(
                status="skipped",
                reason="already_ingested",
                document_id=None,
                attempted=1,
                stored=0,
                skipped=1,
                errored=0,
            ),
        )

    def test_calls_shared_writer_once_with_declared_identity_and_full_text(self):
        calls = []
        db = object()
        db_params = {"dbname": "test"}

        def writer(**kwargs):
            calls.append(kwargs)
            return {
                "status": "processed",
                "reason": None,
                "doc_id": "33333333-3333-3333-3333-333333333333",
                "source_id": kwargs["source_id"],
                "chunks": ["one", "two"],
                "propositions": "stored:1",
            }

        result = execute_ingest(
            self.prepared(), db=db, db_params=db_params, writer_fn=writer
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0],
            {
                "db": db,
                "db_params": db_params,
                "title": "Model title",
                "body_text": "Complete original text",
                "filename": "final.pdf",
                "author": "Derek Prince",
                "year": 1984,
                "source_name": "Derek Prince",
                "source_type": "book",
                "source_kind": "unknown",
                "citation_mode": "silent_context",
                "is_copyrighted": False,
                "topic_tags": ["Prayer"],
                "bible_references": ["John 3:16"],
                "url": "https://cdn.example.com/final.pdf",
                "file_path": "final.pdf",
                "source_id": "22222222-2222-2222-2222-222222222222",
                "allow_sentinel": False,
            },
        )
        self.assertEqual(result.status, "processed")
        self.assertEqual(result.document_id, "33333333-3333-3333-3333-333333333333")
        self.assertEqual(
            (result.attempted, result.stored, result.skipped, result.errored),
            (1, 1, 0, 0),
        )

    def test_maps_shared_skip_to_exact_reconciliation(self):
        result = execute_ingest(
            self.prepared(),
            db=object(),
            db_params={},
            writer_fn=lambda **kwargs: {
                "status": "skipped",
                "reason": "already_ingested",
                "doc_id": None,
            },
        )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.reason, "already_ingested")
        self.assertEqual(
            (result.attempted, result.stored, result.skipped, result.errored),
            (1, 0, 1, 0),
        )

    def test_shared_failure_is_retryable_and_records_corpus_attempt(self):
        with self.assertRaises(RetryableIngestError) as raised:
            execute_ingest(
                self.prepared(),
                db=object(),
                db_params={},
                writer_fn=lambda **kwargs: {
                    "status": "failed",
                    "reason": "paraphrase_failed",
                    "doc_id": None,
                },
            )

        self.assertEqual(raised.exception.code, "proposition_provider_failure")
        self.assertTrue(raised.exception.attempted)

    def test_writer_exception_is_bounded_retryable_failure(self):
        def writer(**kwargs):
            raise RuntimeError("raw provider response")

        with self.assertRaises(RetryableIngestError) as raised:
            execute_ingest(
                self.prepared(), db=object(), db_params={}, writer_fn=writer
            )

        self.assertEqual(raised.exception.code, "embedding_provider_failure")
        self.assertTrue(raised.exception.attempted)
        self.assertNotIn("raw provider", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
