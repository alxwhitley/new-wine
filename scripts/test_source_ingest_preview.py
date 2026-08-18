#!/usr/bin/env python3
"""DB/network-free checks for full-compute source-ingest previews."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import citation_verifier_layers
import propositions
import reference_grounding
import shared_ingest
from app.services import metadata as metadata_service
from app.services import quotes
import source_ingest_queue.preview as preview_module
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


class _RecordingPropositionCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))


class _RecordingPropositionConnection:
    def __init__(self):
        self.cursor_value = _RecordingPropositionCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True


class CompletePreviewTests(unittest.TestCase):
    def test_default_proposition_boundary_never_writes_grounding_review_file(self):
        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps(
                                    [
                                        {
                                            "proposition_index": 1,
                                            "content": (
                                                "Teacher One cites John 3:16 as support "
                                                "for this teaching."
                                            ),
                                        }
                                    ]
                                )
                            )
                        )
                    ]
                )

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        filesystem_attempts = []

        def poison_mkdir(*args, **kwargs):
            filesystem_attempts.append("mkdir")
            raise AssertionError("preview attempted a filesystem review write")

        with patch.object(propositions, "_get_groq", return_value=fake_client), patch.object(
            reference_grounding,
            "check_reference_grounded",
            return_value=reference_grounding.GroundingResult(
                reference_grounding.UNGROUNDED,
                None,
                "not_in_source",
            ),
        ), patch.object(
            citation_verifier_layers,
            "verify_reference_grounded",
            return_value=citation_verifier_layers.VerificationResult(
                False,
                None,
                "layer3_llm_denied",
                False,
                0,
            ),
        ), patch.object(Path, "mkdir", new=poison_mkdir):
            computation = preview_module._default_propositions(
                article_text(),
                document_id=ROW_ID,
                speaker="Teacher One",
                prompt_version="v3.1",
            )

        self.assertEqual(filesystem_attempts, [])
        self.assertEqual(
            computation.output,
            [
                {
                    "proposition_index": 1,
                    "content": "Teacher One cites as support for this teaching.",
                }
            ],
        )

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

        def extract(
            text,
            *,
            doc_id,
            speaker,
            prompt_version,
            grounding_review_sink,
        ):
            extraction_calls.append(
                (text, doc_id, speaker, prompt_version, grounding_review_sink)
            )
            output = [
                {"proposition_index": 1, "content": "A validated proposition."},
                {"proposition_index": 2, "content": "A second proposition."},
            ]
            return propositions.PropositionExtractionComputation(
                output=output,
                model=propositions.EXTRACTION_MODEL,
                usage=None,
                cost_usd=None,
                grounding=propositions.ReferenceGroundingComputation(
                    propositions=output,
                    review_records=[],
                    n_found=0,
                    n_grounded=0,
                    n_stripped_fabricated=0,
                    n_stripped_uncertain=0,
                    n_kept_arbitration=0,
                ),
            )

        def embed(texts):
            embedding_calls.append(list(texts))
            return shared_ingest.EmbeddingBatchComputation(
                output=[[1.0, 2.0, 3.0] for _ in texts],
                model=shared_ingest.EMBEDDING_MODEL,
                usage=None,
                cost_usd=None,
            )

        with patch.object(
            propositions, "extract_propositions_with_evidence", new=extract
        ), patch.object(
            shared_ingest, "_embed_batch_verified_with_evidence", new=embed
        ):
            report = build_preview(
                prepared_article(),
                chunk_fn=lambda text: [text],
                expected_embedding_dimensions=3,
            )

        self.assertEqual(extraction_calls[0][0], article_text())
        self.assertEqual(
            extraction_calls[0][2:],
            ("Teacher One", "v3.1", None),
        )
        self.assertEqual(len(extraction_calls[0][1]), 64)
        self.assertEqual(
            embedding_calls,
            [
                [article_text()],
                ["A validated proposition."],
                ["A second proposition."],
            ],
        )
        self.assertEqual(
            report["computation"]["proposition_extraction"]["model"],
            propositions.EXTRACTION_MODEL,
        )
        self.assertEqual(
            report["computation"]["chunk_embeddings"]["model"],
            "text-embedding-3-small",
        )

    def test_preview_proposition_payload_matches_the_real_storage_payload(self):
        raw_propositions = [
            {
                "proposition_index": 2,
                "content": "  Teacher One presents the second teaching.  ",
            },
            {
                "proposition_index": 1,
                "content": "Teacher One presents the first teaching.",
            },
        ]
        def vector_for(content):
            if "second" in content:
                return [2.0, 2.5, 3.0]
            return [1.0, 1.5, 2.0]

        report = build_preview(
            prepared_article(),
            chunk_fn=lambda text: [text],
            chunk_embeddings_fn=chunk_embeddings,
            proposition_model_fn=lambda *args, **kwargs: ModelComputation(
                output=raw_propositions,
                model=propositions.EXTRACTION_MODEL,
            ),
            proposition_embeddings_fn=lambda texts: ModelComputation(
                output=[vector_for(text) for text in texts],
                model="text-embedding-3-small",
            ),
            expected_embedding_dimensions=3,
        )

        connection = _RecordingPropositionConnection()
        propositions.store_propositions(
            connection,
            ROW_ID,
            raw_propositions,
            vector_for,
            prompt_version="v3.1",
        )
        stored_rows = [
            params
            for sql, params in connection.cursor_value.executed
            if sql.startswith("INSERT INTO propositions")
        ]

        self.assertTrue(connection.committed)
        self.assertEqual(
            [
                (
                    row["content"],
                    row["proposition_index"],
                    row["prompt_version"],
                    row["prompt_fingerprint"],
                    row["model"],
                )
                for row in report["propositions"]
            ],
            [(row[2], row[4], row[5], row[6], row[7]) for row in stored_rows],
        )
        stored_embedding_digests = [
            hashlib.sha256(
                json.dumps(
                    json.loads(row[3]),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for row in stored_rows
        ]
        self.assertEqual(
            [row["embedding"]["sha256"] for row in report["propositions"]],
            stored_embedding_digests,
        )

    def test_preview_and_storage_both_consume_the_canonical_payload_boundary(self):
        original_builder = propositions.build_proposition_payload_item

        def mutate_canonical_payload(*args, **kwargs):
            item = original_builder(*args, **kwargs)
            return item._replace(
                content="canonical:" + item.content,
            )

        with patch.object(
            propositions,
            "build_proposition_payload_item",
            new=mutate_canonical_payload,
        ):
            report = build_preview(
                prepared_article(),
                chunk_fn=lambda text: [text],
                chunk_embeddings_fn=chunk_embeddings,
                proposition_model_fn=proposition_model,
                proposition_embeddings_fn=proposition_embeddings,
                expected_embedding_dimensions=3,
            )
            connection = _RecordingPropositionConnection()
            propositions.store_propositions(
                connection,
                ROW_ID,
                proposition_model(
                    None,
                    document_id=None,
                    speaker=None,
                    prompt_version=None,
                ).output,
                lambda content: [4.0, 5.0, 6.0],
                prompt_version="v3.1",
            )

        stored_rows = [
            params
            for sql, params in connection.cursor_value.executed
            if sql.startswith("INSERT INTO propositions")
        ]
        self.assertEqual(
            report["propositions"][0]["content"],
            "canonical:Teacher One teaches that grace is a free gift rather than "
            "a reward for merit.",
        )
        self.assertEqual(report["propositions"][0]["content"], stored_rows[0][2])

    def test_storage_preserves_legacy_delete_embed_insert_event_order(self):
        events = []
        test_case = self

        class EventCursor:
            def __enter__(self):
                events.append("cursor_enter")
                return self

            def __exit__(self, exc_type, exc, traceback):
                events.append("cursor_exit")
                return False

            def execute(self, sql, params=None):
                normalized = " ".join(sql.split())
                if normalized.startswith("DELETE FROM propositions"):
                    events.append("delete")
                elif normalized.startswith("INSERT INTO propositions"):
                    events.append("insert:" + params[2])
                else:
                    test_case.fail("unexpected SQL: " + normalized)

        class EventConnection:
            def cursor(self):
                events.append("cursor_open")
                return EventCursor()

            def commit(self):
                events.append("commit")

            def rollback(self):
                events.append("rollback")

        raw_propositions = [
            {"proposition_index": 1, "content": "first teaching"},
            {"proposition_index": 2, "content": "second teaching"},
        ]

        def embed(content):
            events.append("embed:" + content)
            return [1.0, 2.0, 3.0]

        def record_links(cursor, sql, rows, **kwargs):
            events.append("links:" + str(len(rows)))

        with patch.object(propositions, "execute_values", new=record_links):
            inserted = propositions.store_propositions(
                EventConnection(),
                ROW_ID,
                raw_propositions,
                embed,
                prompt_version="v3.1",
                chunk_ids=["chunk-a"],
            )

        self.assertEqual(inserted, 2)
        self.assertEqual(
            events,
            [
                "cursor_open",
                "cursor_enter",
                "delete",
                "embed:first teaching",
                "insert:first teaching",
                "embed:second teaching",
                "insert:second teaching",
                "links:2",
                "cursor_exit",
                "commit",
            ],
        )


class ProviderEvidenceTests(unittest.TestCase):
    def test_metadata_evidence_wrapper_preserves_legacy_output_and_real_usage(self):
        self.assertTrue(
            hasattr(metadata_service, "extract_metadata_with_evidence"),
            "shared metadata boundary must expose provider evidence",
        )

        response = SimpleNamespace(
            id="chatcmpl-metadata",
            object="chat.completion",
            model=metadata_service.GROQ_MODEL,
            choices=[
                SimpleNamespace(
                    index=0,
                    finish_reason="stop",
                    message=SimpleNamespace(
                        role="assistant",
                        content=json.dumps(
                            {
                                "title": "Grace Is a Gift",
                                "author": "Teacher One",
                                "source_type": "article",
                                "source_name": "Teacher One",
                                "year": 2026,
                                "topic_tags": ["Grace"],
                            }
                        ),
                    ),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=31,
                completion_tokens=9,
                total_tokens=40,
            ),
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: response)
            )
        )

        with patch.object(metadata_service, "_get_client", return_value=client):
            computation = metadata_service.extract_metadata_with_evidence(article_text())
            legacy = metadata_service.extract_metadata(article_text())

        self.assertEqual(legacy, computation.output)
        self.assertEqual(computation.model, metadata_service.GROQ_MODEL)
        self.assertEqual(
            computation.usage,
            {"input_tokens": 31, "output_tokens": 9, "total_tokens": 40},
        )
        self.assertIsNone(computation.cost_usd)

    def test_embedding_evidence_wrapper_preserves_alignment_and_legacy_output(self):
        self.assertTrue(
            hasattr(shared_ingest, "_embed_batch_verified_with_evidence"),
            "shared embedding boundary must expose provider evidence",
        )

        def create(**kwargs):
            return SimpleNamespace(
                object="list",
                model="text-embedding-3-small",
                data=[
                    SimpleNamespace(
                        object="embedding",
                        index=1,
                        embedding=[4.0, 5.0, 6.0],
                    ),
                    SimpleNamespace(
                        object="embedding",
                        index=0,
                        embedding=[1.0, 2.0, 3.0],
                    ),
                ],
                usage=SimpleNamespace(prompt_tokens=12, total_tokens=12),
            )

        client = SimpleNamespace(
            embeddings=SimpleNamespace(create=create),
        )
        with patch.object(shared_ingest, "_get_openai_client", return_value=client):
            computation = shared_ingest._embed_batch_verified_with_evidence(
                ["first", "second"]
            )
            legacy = shared_ingest._embed_batch_verified(["first", "second"])

        self.assertEqual(legacy, computation.output)
        self.assertEqual(computation.output, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        self.assertEqual(computation.model, "text-embedding-3-small")
        self.assertEqual(
            computation.usage,
            {"input_tokens": 12, "total_tokens": 12},
        )
        self.assertIsNone(computation.cost_usd)

    def test_legacy_embedding_accepts_multi_batch_response_model_label_variation(self):
        def create(**kwargs):
            text = kwargs["input"][0]
            position = 1 if text == "first" else 2
            return SimpleNamespace(
                object="list",
                model="provider-batch-model-%d" % position,
                data=[
                    SimpleNamespace(
                        object="embedding",
                        index=0,
                        embedding=[float(position), 0.0, 0.0],
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=position,
                    total_tokens=position,
                ),
            )

        client = SimpleNamespace(
            embeddings=SimpleNamespace(create=create),
        )
        with patch.object(
            shared_ingest,
            "EMBED_BATCH_SIZE",
            new=1,
        ), patch.object(
            shared_ingest,
            "_get_openai_client",
            return_value=client,
        ):
            try:
                legacy = shared_ingest._embed_batch_verified(["first", "second"])
            except shared_ingest.EmbeddingAlignmentError as exc:
                self.fail("legacy embedding rejected provider model labels: %s" % exc)
            computation = shared_ingest._embed_batch_verified_with_evidence(
                ["first", "second"]
            )

        self.assertEqual(legacy, [[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
        self.assertEqual(computation.output, legacy)
        self.assertEqual(computation.model, shared_ingest.EMBEDDING_MODEL)
        self.assertEqual(computation.model_status, "ambiguous")
        self.assertEqual(
            computation.response_models,
            ("provider-batch-model-1", "provider-batch-model-2"),
        )
        self.assertEqual(
            computation.usage,
            {"input_tokens": 3, "total_tokens": 3},
        )

    def test_preview_surfaces_ambiguous_embedding_model_evidence(self):
        def create(**kwargs):
            text = kwargs["input"][0]
            position = 1 if text == "first" else 2
            return SimpleNamespace(
                object="list",
                model="provider-batch-model-%d" % position,
                data=[
                    SimpleNamespace(
                        object="embedding",
                        index=0,
                        embedding=[float(position), 0.0, 0.0],
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=position,
                    total_tokens=position,
                ),
            )

        client = SimpleNamespace(
            embeddings=SimpleNamespace(create=create),
        )
        with patch.object(
            shared_ingest,
            "EMBED_BATCH_SIZE",
            new=1,
        ), patch.object(
            shared_ingest,
            "_get_openai_client",
            return_value=client,
        ):
            chunk_computation = preview_module._default_chunk_embeddings(
                ["first", "second"]
            )
            proposition_computation = (
                preview_module._default_proposition_embeddings(["first", "second"])
            )

        expected_evidence = {
            "status": "ambiguous",
            "response_models": [
                "provider-batch-model-1",
                "provider-batch-model-2",
            ],
        }
        self.assertEqual(
            chunk_computation.details,
            {"model_evidence": expected_evidence},
        )
        self.assertEqual(
            proposition_computation.details,
            {"model_evidence": expected_evidence},
        )
        self.assertEqual(chunk_computation.model, shared_ingest.EMBEDDING_MODEL)
        self.assertEqual(proposition_computation.model, shared_ingest.EMBEDDING_MODEL)

    def test_proposition_evidence_wrapper_preserves_grounded_legacy_output(self):
        self.assertTrue(
            hasattr(propositions, "extract_propositions_with_evidence"),
            "shared proposition boundary must expose provider evidence",
        )
        raw_output = [
            {
                "proposition_index": 1,
                "content": "Teacher One presents a grounded teaching without a citation.",
            }
        ]
        response = SimpleNamespace(
            id="chatcmpl-propositions",
            object="chat.completion",
            model=propositions.EXTRACTION_MODEL,
            choices=[
                SimpleNamespace(
                    index=0,
                    finish_reason="stop",
                    message=SimpleNamespace(
                        role="assistant",
                        content=json.dumps(raw_output),
                    ),
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=45,
                completion_tokens=15,
                total_tokens=60,
            ),
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: response)
            )
        )

        with patch.object(propositions, "_get_groq", return_value=client):
            computation = propositions.extract_propositions_with_evidence(
                article_text(),
                doc_id=ROW_ID,
                speaker="Teacher One",
                prompt_version="v3.1",
                grounding_review_sink=None,
            )
            legacy = propositions.extract_propositions(
                article_text(),
                doc_id=ROW_ID,
                speaker="Teacher One",
                prompt_version="v3.1",
                grounding_review_sink=None,
            )

        self.assertEqual(legacy, computation.output)
        self.assertEqual(computation.output, raw_output)
        self.assertEqual(computation.model, propositions.EXTRACTION_MODEL)
        self.assertEqual(
            computation.usage,
            {"input_tokens": 45, "output_tokens": 15, "total_tokens": 60},
        )
        self.assertIsNone(computation.cost_usd)
        self.assertEqual(computation.grounding.n_found, 0)

    def test_real_preview_boundaries_surface_usage_and_explicit_unavailability(self):
        metadata_response = SimpleNamespace(
            model=metadata_service.GROQ_MODEL,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "title": "Provider Evidence Article",
                                "author": "Ignored Provider Author",
                                "source_type": "article",
                                "source_name": "Ignored Provider Source",
                                "year": 2026,
                                "topic_tags": ["Grace"],
                            }
                        )
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=4,
                total_tokens=15,
            ),
        )
        proposition_response = SimpleNamespace(
            model=propositions.EXTRACTION_MODEL,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            [
                                {
                                    "proposition_index": 1,
                                    "content": "Teacher One teaches that grace is freely given.",
                                }
                            ]
                        )
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=25,
                completion_tokens=5,
                total_tokens=30,
            ),
        )
        embedding_usages = iter((7, 3))

        def embed_create(**kwargs):
            token_count = next(embedding_usages)
            return SimpleNamespace(
                model=shared_ingest.EMBEDDING_MODEL,
                data=[
                    SimpleNamespace(index=index, embedding=[1.0, 2.0, 3.0])
                    for index, _text in enumerate(kwargs["input"])
                ],
                usage=SimpleNamespace(
                    prompt_tokens=token_count,
                    total_tokens=token_count,
                ),
            )

        row = {
            "id": ROW_ID,
            "url": "https://example.com/provider-evidence",
            "source_format": "web_page",
            "source_scope": "single",
            "attribution_mode": "declared",
            "attribute_to": "Teacher One",
            "retain_original_text": True,
            "cleared_to_run": True,
        }
        raw_bytes = b"captured article bytes"
        prepare_options = {
            "html_fetch_fn": lambda url: FetchResult(
                content=raw_bytes,
                final_url=url,
                sha256=hashlib.sha256(raw_bytes).hexdigest(),
                byte_count=len(raw_bytes),
                filename="provider-evidence.html",
            ),
            "html_extract_fn": lambda content: ExtractedArticle(
                title="Fallback",
                text=article_text(),
                word_count=len(article_text().split()),
                evidence={"container": "article"},
            ),
            "resolve_fn": lambda *args: (SOURCE_ID, "teacher one", "source_name"),
            "dedup_fn": lambda *args: False,
            "chunk_fn": lambda text: [text],
        }

        metadata_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: metadata_response)
            )
        )
        proposition_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: proposition_response)
            )
        )
        embedding_client = SimpleNamespace(
            embeddings=SimpleNamespace(create=embed_create)
        )
        with patch.object(
            metadata_service, "_get_client", return_value=metadata_client
        ), patch.object(
            propositions, "_get_groq", return_value=proposition_client
        ), patch.object(
            shared_ingest, "_get_openai_client", return_value=embedding_client
        ):
            report = preview_row(
                row,
                db=WritePoisonedDb(),
                db_params={"read_only": True},
                prepare_options=prepare_options,
                preview_options={
                    "chunk_fn": lambda text: [text],
                    "expected_embedding_dimensions": 3,
                },
            )

        computation = report["computation"]
        self.assertEqual(
            computation["metadata"]["usage"],
            {
                "status": "available",
                "input_tokens": 11,
                "output_tokens": 4,
                "total_tokens": 15,
            },
        )
        self.assertEqual(
            computation["proposition_extraction"]["usage"]["total_tokens"],
            30,
        )
        self.assertEqual(
            computation["chunk_embeddings"]["usage"]["input_tokens"],
            7,
        )
        self.assertEqual(
            computation["proposition_embeddings"]["usage"]["input_tokens"],
            3,
        )
        for boundary in (
            "metadata",
            "proposition_extraction",
            "chunk_embeddings",
            "proposition_embeddings",
            "reference_grounding_arbitration",
        ):
            self.assertEqual(
                computation[boundary]["cost_usd"]["status"],
                "unavailable",
            )
        self.assertEqual(
            computation["reference_grounding_arbitration"]["usage"],
            {"status": "unavailable"},
        )
        self.assertEqual(
            computation["known_tokens"],
            {"input_tokens": 46, "output_tokens": 9, "total_tokens": 55},
        )


class ImmutableArtifactTests(unittest.TestCase):
    def build_report(self):
        return build_preview(
            prepared_article(),
            chunk_fn=lambda text: [text],
            chunk_embeddings_fn=chunk_embeddings,
            proposition_model_fn=proposition_model,
            proposition_embeddings_fn=proposition_embeddings,
            expected_embedding_dimensions=3,
        )

    def test_capture_identity_is_stable_but_report_identity_covers_all_output(self):
        def build(*, prepared=None, model="test-proposition-model", content=None, spans=None):
            proposition_content = content or (
                "Teacher One teaches that grace is a free gift rather than "
                "a reward for merit."
            )
            return build_preview(
                prepared or prepared_article(),
                chunk_fn=lambda text: [text],
                chunk_embeddings_fn=chunk_embeddings,
                proposition_model_fn=lambda *args, **kwargs: ModelComputation(
                    output=[
                        {
                            "proposition_index": 1,
                            "content": proposition_content,
                        }
                    ],
                    model=model,
                ),
                proposition_embeddings_fn=proposition_embeddings,
                quote_spans_fn=(lambda chunk: list(spans or [])),
                expected_embedding_dimensions=3,
            )

        baseline = build()
        identical = build()
        title_changed = build(
            prepared=replace(prepared_article(), title="A Different Reviewed Title")
        )
        model_changed = build(model="another-proposition-model")
        proposition_changed = build(
            content="Teacher One presents a distinct reviewed proposition."
        )
        quote_text = "Grace is not a reward earned through good behavior"
        quote_start = article_text().index(quote_text)
        quote_changed = build(
            spans=[(quote_start, quote_start + len(quote_text), quote_text)]
        )

        self.assertIn("capture_id", baseline)
        self.assertEqual(canonical_preview_json(baseline), canonical_preview_json(identical))
        for changed in (
            title_changed,
            model_changed,
            proposition_changed,
            quote_changed,
        ):
            with self.subTest(report_id=changed["report_id"]):
                self.assertEqual(changed["capture_id"], baseline["capture_id"])
                self.assertNotEqual(changed["report_id"], baseline["report_id"])

    def test_same_capture_is_idempotent_but_conflicting_overwrite_is_refused(self):
        report = self.build_report()

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            first_path = write_preview_report(report, review_dir=review_dir)
            first_bytes = first_path.read_bytes()
            second_path = write_preview_report(report, review_dir=review_dir)

            self.assertEqual(first_path, second_path)
            self.assertEqual(first_bytes, canonical_preview_json(report).encode("utf-8"))
            self.assertEqual(stat.S_IMODE(first_path.stat().st_mode), 0o600)

            conflicting = {**report, "metadata": {**report["metadata"], "title": "Changed"}}
            with self.assertRaises(PreviewValidationError):
                write_preview_report(conflicting, review_dir=review_dir)

            self.assertEqual(first_path.read_bytes(), first_bytes)

            wrong_identity = {**report, "report_id": "0" * 64}
            with self.assertRaises(PreviewValidationError):
                write_preview_report(wrong_identity, review_dir=review_dir)
            self.assertFalse((review_dir / (("0" * 64) + ".json")).exists())

        with tempfile.TemporaryDirectory() as directory:
            occupied_path = Path(directory) / (report["report_id"] + ".json")
            occupied_path.write_bytes(b"occupied by different bytes\n")
            occupied_path.chmod(0o600)
            with self.assertRaises(PreviewCollisionError):
                write_preview_report(report, review_dir=Path(directory))
            self.assertEqual(occupied_path.read_bytes(), b"occupied by different bytes\n")

    def test_existing_symlink_wrong_mode_and_hard_link_are_never_accepted(self):
        report = self.build_report()
        payload = canonical_preview_json(report).encode("utf-8")
        filename = report["report_id"] + ".json"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_dir = root / "review"
            review_dir.mkdir()
            outside = root / "outside.json"
            outside.write_bytes(payload)
            target = review_dir / filename
            target.symlink_to(outside)
            with self.assertRaises(PreviewCollisionError):
                write_preview_report(report, review_dir=review_dir)
            self.assertEqual(outside.read_bytes(), payload)

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            target = review_dir / filename
            target.write_bytes(payload)
            target.chmod(0o644)
            with self.assertRaises(PreviewCollisionError):
                write_preview_report(report, review_dir=review_dir)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            review_dir = root / "review"
            review_dir.mkdir()
            first_link = root / "first-link.json"
            first_link.write_bytes(payload)
            first_link.chmod(0o600)
            target = review_dir / filename
            os.link(first_link, target)
            self.assertEqual(target.stat().st_nlink, 2)
            with self.assertRaises(PreviewCollisionError):
                write_preview_report(report, review_dir=review_dir)
            self.assertEqual(first_link.read_bytes(), payload)

    def test_interrupted_temp_write_leaves_no_final_and_preserves_other_files(self):
        report = self.build_report()
        real_write = os.write
        write_attempts = []

        def interrupt_after_partial_write(descriptor, data):
            write_attempts.append(len(data))
            real_write(descriptor, data[: max(1, len(data) // 2)])
            raise OSError("simulated interrupted artifact write")

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            sentinel = review_dir / "unrelated-review-note"
            sentinel.write_text("preserve me", encoding="utf-8")
            final_path = review_dir / (report["report_id"] + ".json")
            with patch.object(
                preview_module.os,
                "write",
                new=interrupt_after_partial_write,
            ):
                with self.assertRaises(OSError):
                    write_preview_report(report, review_dir=review_dir)

            self.assertTrue(write_attempts)
            self.assertFalse(final_path.exists())
            self.assertEqual(
                sorted(path.name for path in review_dir.iterdir()),
                [sentinel.name],
            )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve me")

    def test_temp_name_collision_never_removes_the_file_it_did_not_create(self):
        report = self.build_report()
        random_bytes = b"\x01" * 16
        temp_name = ".%s.%s.tmp" % (
            report["report_id"],
            random_bytes.hex(),
        )

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            occupied_temp = review_dir / temp_name
            occupied_temp.write_bytes(b"owned by someone else")
            occupied_temp.chmod(0o600)
            with patch.object(
                preview_module.os,
                "urandom",
                return_value=random_bytes,
            ):
                with self.assertRaises(FileExistsError):
                    write_preview_report(report, review_dir=review_dir)

            self.assertEqual(occupied_temp.read_bytes(), b"owned by someone else")
            self.assertFalse(
                (review_dir / (report["report_id"] + ".json")).exists()
            )

    def test_success_fsyncs_artifact_then_pinned_directory(self):
        report = self.build_report()
        real_fsync = os.fsync
        fsync_kinds = []

        def record_fsync(descriptor):
            mode = os.fstat(descriptor).st_mode
            fsync_kinds.append("directory" if stat.S_ISDIR(mode) else "file")
            real_fsync(descriptor)

        with tempfile.TemporaryDirectory() as directory, patch.object(
            preview_module.os,
            "fsync",
            new=record_fsync,
        ):
            write_preview_report(report, review_dir=Path(directory))

        self.assertEqual(fsync_kinds, ["file", "directory"])


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
