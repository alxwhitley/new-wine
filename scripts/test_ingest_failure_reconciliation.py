#!/usr/bin/env python3
"""Deterministic contract checks for reconcilable /ingest failures."""
import asyncio
import logging
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))

from fastapi import HTTPException  # noqa: E402
from app.routers import ingest as ingest_module  # noqa: E402
from app.routers.ingest import _log_ingest_failure  # noqa: E402


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _FakeFile:
    filename = "batch.pdf"

    async def read(self):
        return b"fake-pdf"


class _FakeResult:
    data = []


class _InsertQuery:
    def __init__(self, table_name, db):
        self.table_name = table_name
        self.db = db

    def insert(self, rows):
        self.rows = rows
        return self

    def execute(self):
        if self.table_name == "chunks":
            self.db.chunk_batches += 1
            if self.db.chunk_batches == 2:
                raise RuntimeError("simulated second-batch failure")
        return _FakeResult()


class _FakeDb:
    def __init__(self):
        self.chunk_batches = 0

    def table(self, name):
        return _InsertQuery(name, self)


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    print("OK:", label)


def main():
    capture = _CaptureHandler()
    test_logger = logging.getLogger("rhemata.test.ingest_reconciliation")
    test_logger.handlers = [capture]
    test_logger.propagate = False
    test_logger.setLevel(logging.ERROR)

    progress = {
        "filename": "sermon\npacket.pdf",
        "source_type": "sermon",
        "stage": "insert_chunks",
        "document_id": "doc-123",
        "title": "A Sermon",
        "chunks_attempted": 13,
        "chunks_stored": 6,
    }
    try:
        raise RuntimeError("simulated failure")
    except RuntimeError:
        _log_ingest_failure(test_logger, progress)

    check("one failure record emitted", len(capture.records) == 1)
    record = capture.records[0]
    rendered = record.getMessage()
    check("record retains exception information", record.exc_info is not None)
    check("upload filename is safely repr-escaped", "sermon\\npacket.pdf" in rendered)
    check("source type is present", "source_type=sermon" in rendered)
    check("failure stage is present", "stage=insert_chunks" in rendered)
    check("created document ID is present", "document_id=doc-123" in rendered)
    check("document title is safely represented", "title='A Sermon'" in rendered)
    check("attempted chunk count is present", "chunks_attempted=13" in rendered)
    check("stored chunk count is present", "chunks_stored=6" in rendered)
    check("document content is not accepted by the logging contract", "content" not in progress)

    capture.records.clear()
    try:
        raise RuntimeError("simulated oversized identity")
    except RuntimeError:
        _log_ingest_failure(test_logger, {**progress, "title": "x" * 500})
    bounded = capture.records[0].getMessage()
    check("untrusted title is bounded in logs", "x" * 241 not in bounded and "..." in bounded)

    capture.records.clear()
    fake_db = _FakeDb()
    chunks = ["chunk-%d" % i for i in range(13)]
    with (
        patch.object(ingest_module, "logger", test_logger),
        patch.object(ingest_module, "extract_text_from_pdf", return_value="text"),
        patch.object(
            ingest_module,
            "extract_metadata",
            return_value={"title": "Batch Sermon", "author": "Teacher", "year": 2026, "topic_tags": []},
        ),
        patch.object(ingest_module, "chunk_text", return_value=chunks),
        patch.object(ingest_module, "embed_batch", return_value=[[0.0]] * len(chunks)),
        patch.object(ingest_module, "get_supabase", return_value=fake_db),
        patch.object(ingest_module.uuid, "uuid4", side_effect=["doc-456"] + ["chunk-%d" % i for i in range(13)]),
    ):
        try:
            asyncio.run(ingest_module.ingest(None, _FakeFile(), "sermon", "admin"))
            raise AssertionError("partial ingest should fail")
        except HTTPException as exc:
            check("partial database failure becomes HTTP 500", exc.status_code == 500)

    check("partial flow emits one reconciliation record", len(capture.records) == 1)
    partial = capture.records[0].getMessage()
    check("partial flow identifies upload", "filename='batch.pdf'" in partial)
    check("partial flow identifies generated document", "document_id=doc-456" in partial)
    check("partial flow identifies failing stage", "stage=insert_chunks" in partial)
    check("partial flow reports all attempted chunks", "chunks_attempted=13" in partial)
    check("partial flow reports only committed batch", "chunks_stored=6" in partial)

    print("All ingest failure reconciliation checks passed.")


if __name__ == "__main__":
    main()
