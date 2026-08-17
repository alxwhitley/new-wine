#!/usr/bin/env python3
"""DB/network-free checks for full-compute source-ingest previews."""

from __future__ import annotations

import hashlib
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import propositions
import shared_ingest
from app.services import quotes
from source_ingest_queue.fetcher import FetchResult
from source_ingest_queue.html_extract import ExtractedArticle
from source_ingest_queue.preview import (
    ModelComputation,
    PreviewCollisionError,
    PreviewValidationError,
    build_preview,
    canonical_preview_json,
    preview_row,
    write_preview_report,
)
from source_ingest_queue.processor import PreparedIngest, prepare_ingest


ROW_ID = "11111111-1111-1111-1111-111111111111"
SOURCE_ID = "22222222-2222-2222-2222-222222222222"
CONTENT_SHA256 = hashlib.sha256(b"captured article bytes").hexdigest()


def article_text() -> str:
    return (
        "An introductory sentence provides context before the central teaching begins. "
        "Grace is not a reward earned through good behavior; it is God's free gift "
        "to people who could never earn it through their own effort or merit. "
        "A final sentence supplies surrounding context after the central teaching ends."
    )


def prepared_article() -> PreparedIngest:
    body = article_text()
    return PreparedIngest(
        row_id=ROW_ID,
        source_id=SOURCE_ID,
        title="Grace Is a Gift",
        author="Teacher One",
        source_name="Teacher One",
        body_text=body,
        filename="grace-is-a-gift.html",
        source_url="https://example.com/grace-is-a-gift",
        source_type="article",
        source_kind="web_article",
        citation_mode="citable",
        year=2026,
        topic_tags=["Grace"],
        bible_references=[],
        page_count=1,
        chunk_count=1,
        content_sha256=CONTENT_SHA256,
        fetched_bytes=len(b"captured article bytes"),
        duplicate=False,
        extraction_evidence={"container": "article", "word_count": 48},
        license_status="licensed",
        source_visibility="hidden",
        metadata_computed=True,
    )


def chunk_embeddings(texts):
    return ModelComputation(
        output=[[1.0, 2.0, 3.0] for _ in texts],
        model="test-embedding-model",
        usage={"input_tokens": 40, "total_tokens": 40},
        cost_usd=0.001,
    )


def proposition_model(text, *, document_id, speaker, prompt_version):
    return ModelComputation(
        output=[
            {
                "proposition_index": 1,
                "content": (
                    "Teacher One teaches that grace is a free gift rather than "
                    "a reward for merit."
                ),
                "ignored_untrusted_field": "../../never-used-as-a-path",
            }
        ],
        model="test-proposition-model",
        usage={"input_tokens": 120, "output_tokens": 20, "total_tokens": 140},
        cost_usd=0.002,
    )


def proposition_embeddings(texts):
    return ModelComputation(
        output=[[4.0, 5.0, 6.0] for _ in texts],
        model="test-embedding-model",
        usage={"input_tokens": 18, "total_tokens": 18},
        cost_usd=0.0005,
    )


class _ReadOnlyQuery:
    def __init__(self, database, table_name):
        self._database = database
        self._table_name = table_name

    def select(self, fields):
        self._database.reads.append(("select", self._table_name, fields))
        return self

    def eq(self, field, value):
        self._database.reads.append(("eq", field, value))
        return self

    def limit(self, count):
        self._database.reads.append(("limit", count))
        return self

    def execute(self):
        self._database.reads.append(("execute", self._table_name))
        return type(
            "Response",
            (),
            {"data": [{"license_status": "licensed", "visibility": "hidden"}]},
        )()

    def insert(self, *args, **kwargs):
        self._database.refuse_write("insert")

    def update(self, *args, **kwargs):
        self._database.refuse_write("update")

    def upsert(self, *args, **kwargs):
        self._database.refuse_write("upsert")

    def delete(self, *args, **kwargs):
        self._database.refuse_write("delete")


class WritePoisonedDb:
    def __init__(self):
        self.reads = []
        self.write_attempts = []

    def table(self, name):
        self.reads.append(("table", name))
        return _ReadOnlyQuery(self, name)

    def rpc(self, *args, **kwargs):
        self.refuse_write("rpc")

    def refuse_write(self, operation):
        self.write_attempts.append(operation)
        raise AssertionError("preview attempted database write: %s" % operation)


class CompletePreviewTests(unittest.TestCase):
    def test_full_compute_report_is_deterministic_and_review_only(self):
        kwargs = {
            "chunk_fn": lambda text: [text],
            "chunk_embeddings_fn": chunk_embeddings,
            "proposition_model_fn": proposition_model,
            "proposition_embeddings_fn": proposition_embeddings,
            "expected_embedding_dimensions": 3,
        }

        first = build_preview(prepared_article(), **kwargs)
        second = build_preview(prepared_article(), **kwargs)

        self.assertEqual(first, second)
        self.assertEqual(canonical_preview_json(first), canonical_preview_json(second))
        self.assertEqual(len(first["report_id"]), 64)
        self.assertEqual(first["capture"]["row_id"], ROW_ID)
        self.assertEqual(first["capture"]["url"], "https://example.com/grace-is-a-gift")
        self.assertEqual(first["capture"]["content_sha256"], CONTENT_SHA256)
        self.assertEqual(first["capture"]["fetched_bytes"], 22)
        self.assertEqual(first["attribution"]["source_id"], SOURCE_ID)
        self.assertEqual(first["attribution"]["teacher"], "Teacher One")
        self.assertEqual(first["attribution"]["license_status"], "licensed")
        self.assertEqual(first["attribution"]["visibility"], "hidden")
        self.assertEqual(first["metadata"]["source_kind"], "web_article")
        self.assertEqual(first["metadata"]["citation_mode"], "citable")
        self.assertIs(first["metadata"]["computed"], True)

        self.assertEqual(len(first["chunks"]), 1)
        chunk = first["chunks"][0]
        self.assertEqual(chunk["content"], article_text())
        self.assertEqual(chunk["embedding"]["dimensions"], 3)
        self.assertEqual(len(chunk["embedding"]["sha256"]), 64)

        self.assertEqual(len(first["propositions"]), 1)
        proposition = first["propositions"][0]
        self.assertIs(proposition["eligible"], False)
        self.assertEqual(proposition["prompt_version"], "v3.1")
        self.assertEqual(len(proposition["prompt_fingerprint"]), 64)
        self.assertEqual(proposition["model"], "test-proposition-model")
        self.assertEqual(proposition["chunk_ids"], [chunk["id"]])
        self.assertNotIn("ignored_untrusted_field", proposition)

        self.assertTrue(first["quote_spans"])
        for proposal in first["quote_spans"]:
            self.assertEqual(proposal["status"], "proposal")
            self.assertEqual(
                chunk["content"][proposal["start"] : proposal["end"]],
                proposal["text"],
            )
            self.assertIn(proposal["text"], proposal["surrounding_passage"]["text"])

        computation = first["computation"]
        self.assertEqual(computation["chunk_embeddings"]["usage"]["input_tokens"], 40)
        self.assertEqual(computation["proposition_extraction"]["usage"]["output_tokens"], 20)
        self.assertEqual(computation["known_cost_usd"], 0.0035)
        self.assertEqual(
            computation["known_tokens"],
            {"input_tokens": 178, "output_tokens": 20, "total_tokens": 198},
        )

    def test_row_preview_completes_with_every_write_and_approval_path_poisoned(self):
        database = WritePoisonedDb()
        raw_bytes = b"captured article bytes"
        row = {
            "id": ROW_ID,
            "url": "https://example.com/grace-is-a-gift",
            "source_format": "web_page",
            "source_scope": "single",
            "attribution_mode": "declared",
            "attribute_to": "Teacher One",
            "retain_original_text": True,
            "cleared_to_run": True,
        }

        def forbidden(*args, **kwargs):
            raise AssertionError("preview crossed a persistence or approval boundary")

        prepare_options = {
            "html_fetch_fn": lambda url: FetchResult(
                content=raw_bytes,
                final_url=url,
                sha256=hashlib.sha256(raw_bytes).hexdigest(),
                byte_count=len(raw_bytes),
                filename="grace-is-a-gift.html",
            ),
            "html_extract_fn": lambda content: ExtractedArticle(
                title="Grace Is a Gift",
                text=article_text(),
                word_count=len(article_text().split()),
                evidence={"container": "article", "word_count": len(article_text().split())},
            ),
            "resolve_fn": lambda *args: (SOURCE_ID, "teacher one", "source_name"),
            "dedup_fn": lambda *args: False,
            "chunk_fn": lambda text: [text],
            "metadata_fn": lambda text: {
                "title": "Grace Is a Gift",
                "author": "../../ignored-model-author",
                "source_name": "../../ignored-model-source",
                "source_type": "article",
                "source_kind": "background_note",
                "citation_mode": "silent_context",
                "year": 2026,
                "topic_tags": ["Grace"],
                "bible_references": [],
            },
        }
        preview_options = {
            "chunk_fn": lambda text: [text],
            "chunk_embeddings_fn": chunk_embeddings,
            "proposition_model_fn": proposition_model,
            "proposition_embeddings_fn": proposition_embeddings,
            "expected_embedding_dimensions": 3,
        }

        with patch.object(shared_ingest, "ingest_document", new=forbidden), patch.object(
            propositions, "store_propositions", new=forbidden
        ), patch.object(quotes, "create_and_approve_quote", new=forbidden):
            report = preview_row(
                row,
                db=database,
                db_params={"read_only": True},
                prepare_fn=prepare_ingest,
                prepare_options=prepare_options,
                preview_options=preview_options,
            )

        self.assertEqual(database.write_attempts, [])
        self.assertIn(("table", "sources"), database.reads)
        self.assertEqual(report["reconciliation"]["database_rows_written"], 0)
        self.assertEqual(report["reconciliation"]["quote_rows_written"], 0)
        self.assertEqual(report["reconciliation"]["quotes_approved"], 0)
        self.assertEqual(report["attribution"]["license_status"], "licensed")
        self.assertEqual(report["attribution"]["visibility"], "hidden")
        self.assertEqual(report["metadata"]["author"], "Teacher One")
        self.assertEqual(report["metadata"]["source_kind"], "web_article")
        self.assertEqual(report["metadata"]["citation_mode"], "citable")

    def test_default_model_boundaries_use_the_canonical_prompt_and_embedding_model(self):
        extraction_calls = []
        embedding_calls = []

        def extract(text, *, doc_id, speaker, prompt_version):
            extraction_calls.append((text, doc_id, speaker, prompt_version))
            return [{"proposition_index": 1, "content": "A validated proposition."}]

        def embed(texts):
            embedding_calls.append(list(texts))
            return [[1.0, 2.0, 3.0] for _ in texts]

        with patch.object(propositions, "extract_propositions", new=extract), patch.object(
            shared_ingest, "_embed_batch_verified", new=embed
        ):
            report = build_preview(
                prepared_article(),
                chunk_fn=lambda text: [text],
                expected_embedding_dimensions=3,
            )

        self.assertEqual(extraction_calls[0][0], article_text())
        self.assertEqual(extraction_calls[0][2:], ("Teacher One", "v3.1"))
        self.assertEqual(len(extraction_calls[0][1]), 64)
        self.assertEqual(embedding_calls, [[article_text()], ["A validated proposition."]])
        self.assertEqual(
            report["computation"]["proposition_extraction"]["model"],
            propositions.EXTRACTION_MODEL,
        )
        self.assertEqual(
            report["computation"]["chunk_embeddings"]["model"],
            "text-embedding-3-small",
        )


class ImmutableArtifactTests(unittest.TestCase):
    def test_same_capture_is_idempotent_but_conflicting_overwrite_is_refused(self):
        report = build_preview(
            prepared_article(),
            chunk_fn=lambda text: [text],
            chunk_embeddings_fn=chunk_embeddings,
            proposition_model_fn=proposition_model,
            proposition_embeddings_fn=proposition_embeddings,
            expected_embedding_dimensions=3,
        )

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            first_path = write_preview_report(report, review_dir=review_dir)
            first_bytes = first_path.read_bytes()
            second_path = write_preview_report(report, review_dir=review_dir)

            self.assertEqual(first_path, second_path)
            self.assertEqual(first_bytes, canonical_preview_json(report).encode("utf-8"))
            self.assertEqual(stat.S_IMODE(first_path.stat().st_mode), 0o600)

            conflicting = {**report, "metadata": {**report["metadata"], "title": "Changed"}}
            with self.assertRaises(PreviewCollisionError):
                write_preview_report(conflicting, review_dir=review_dir)

            self.assertEqual(first_path.read_bytes(), first_bytes)

            wrong_identity = {**report, "report_id": "0" * 64}
            with self.assertRaises(PreviewValidationError):
                write_preview_report(wrong_identity, review_dir=review_dir)
            self.assertFalse((review_dir / (("0" * 64) + ".json")).exists())


class ModelBoundaryValidationTests(unittest.TestCase):
    def build_with(self, prepared=None, **overrides):
        options = {
            "chunk_fn": lambda text: [text],
            "chunk_embeddings_fn": chunk_embeddings,
            "proposition_model_fn": proposition_model,
            "proposition_embeddings_fn": proposition_embeddings,
            "expected_embedding_dimensions": 3,
        }
        options.update(overrides)
        return build_preview(prepared or prepared_article(), **options)

    def test_invalid_captured_body_is_refused_before_any_model_or_chunk_call(self):
        invalid = replace(prepared_article(), body_text=None)

        with self.assertRaises(PreviewValidationError):
            build_preview(
                invalid,
                chunk_fn=lambda text: self.fail("invalid body reached chunking"),
                chunk_embeddings_fn=lambda texts: self.fail("invalid body reached embeddings"),
                proposition_model_fn=lambda *args, **kwargs: self.fail(
                    "invalid body reached proposition model"
                ),
                proposition_embeddings_fn=lambda texts: self.fail(
                    "invalid body reached proposition embeddings"
                ),
                expected_embedding_dimensions=3,
            )

    def test_pre_metadata_dry_run_cannot_claim_full_compute_preview(self):
        invalid = replace(prepared_article(), metadata_computed=False)

        with self.assertRaises(PreviewValidationError):
            build_preview(
                invalid,
                chunk_fn=lambda text: self.fail("pre-metadata input reached chunking"),
                chunk_embeddings_fn=lambda texts: self.fail(
                    "pre-metadata input reached embeddings"
                ),
                proposition_model_fn=lambda *args, **kwargs: self.fail(
                    "pre-metadata input reached proposition model"
                ),
                proposition_embeddings_fn=lambda texts: self.fail(
                    "pre-metadata input reached proposition embeddings"
                ),
                expected_embedding_dimensions=3,
            )

    def test_unparsed_or_malformed_proposition_output_is_refused(self):
        bad_outputs = (
            '[{"proposition_index":1,"content":"../../not-a-path"}]',
            [
                {"proposition_index": 1, "content": "Valid"},
                {"proposition_index": 1, "content": "Duplicate"},
            ],
            [{"proposition_index": True, "content": "Boolean indexes are invalid"}],
            [{"proposition_index": 1, "content": ""}],
        )
        for output in bad_outputs:
            with self.subTest(output=output):
                with self.assertRaises(PreviewValidationError):
                    self.build_with(
                        proposition_model_fn=(
                            lambda *args, value=output, **kwargs: ModelComputation(
                                output=value,
                                model="untrusted-model",
                            )
                        )
                    )

    def test_non_finite_embedding_and_negative_usage_are_refused(self):
        bad_computations = (
            ModelComputation(output=[[1.0, float("nan"), 3.0]], model="embed"),
            ModelComputation(
                output=[[1.0, 2.0, 3.0]],
                model="embed",
                usage={"input_tokens": -1},
            ),
        )
        for computation in bad_computations:
            with self.subTest(computation=computation):
                with self.assertRaises(PreviewValidationError):
                    self.build_with(chunk_embeddings_fn=lambda texts, value=computation: value)

    def test_quote_proposer_cannot_invent_or_redirect_a_span(self):
        with self.assertRaises(PreviewValidationError):
            self.build_with(
                quote_spans_fn=lambda content: [(1, 15, "../../not-source-text")]
            )

    def test_non_numeric_capture_size_is_rejected_as_invalid_evidence(self):
        invalid = replace(prepared_article(), fetched_bytes="22")

        with self.assertRaises(PreviewValidationError):
            build_preview(
                invalid,
                chunk_fn=lambda text: self.fail("invalid size reached chunking"),
                chunk_embeddings_fn=lambda texts: self.fail("invalid size reached embeddings"),
                proposition_model_fn=lambda *args, **kwargs: self.fail(
                    "invalid size reached proposition model"
                ),
                proposition_embeddings_fn=lambda texts: self.fail(
                    "invalid size reached proposition embeddings"
                ),
                expected_embedding_dimensions=3,
            )

    def test_capture_hash_must_use_one_canonical_lowercase_identity(self):
        invalid = replace(prepared_article(), content_sha256=CONTENT_SHA256.upper())

        with self.assertRaises(PreviewValidationError):
            self.build_with(prepared=invalid)

    def test_embedding_dimension_contract_rejects_non_integer_configuration(self):
        with self.assertRaises(PreviewValidationError):
            self.build_with(expected_embedding_dimensions="1536")


if __name__ == "__main__":
    unittest.main()
