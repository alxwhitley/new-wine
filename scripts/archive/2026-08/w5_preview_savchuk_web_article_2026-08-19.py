#!/usr/bin/env python3
"""No-write preview for W5 queue row 85962adf-… (Savchuk prayer-language article).

Loads the queue row, sets cleared_to_run=True only in-memory (DB stays false),
runs preview_row, writes immutable JSON under source_ingest_preview_review/,
prints a human review summary. Zero corpus / queue / quote writes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

import propositions  # noqa: E402
from app.db.supabase import get_supabase  # noqa: E402
from app.services.metadata import MetadataComputation  # noqa: E402
from source_ingest_queue.preview import (  # noqa: E402
    DEFAULT_REVIEW_DIR,
    _default_propositions,
    preview_row,
    write_preview_report,
)

PREVIEW_GROQ_MODEL = "openai/gpt-oss-120b"

ROW_ID = "85962adf-f4d6-440a-bd32-de414dbc4605"


def _stub_metadata(_text: str) -> MetadataComputation:
    """W5-only: Groq llama-3.3-70b-versatile is 404 on this key.

    Web_page prepare_ingest still forces source_kind=web_article and
    citation_mode=citable after metadata. Stub supplies article-shaped fields
    so preview can continue without a production model change.
    """
    return MetadataComputation(
        output={
            "title": "How to Develop Your Prayer Language in Private",
            "author": "Vlad Savchuk",
            "source_type": "article",
            "source_name": "Vlad Savchuk (web staging)",
            "year": None,
            "topic_tags": ["Prayer", "Speaking in Tongues"],
        },
        model="stub:w5_preview_2026-08-19",
        usage=None,
        cost_usd=0.0,
    )


def _db_params() -> dict:
    db_url = os.environ["SUPABASE_DB_URL"]
    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def main() -> int:
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM source_ingest_queue WHERE id = %s", (ROW_ID,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        print("queue row missing", file=sys.stderr)
        return 2

    row = dict(row)
    if row.get("cleared_to_run") is True:
        print("REFUSING: DB cleared_to_run already true; unexpected for this step", file=sys.stderr)
        return 2

    # In-memory only — worker claim still blocked until Alex clears.
    row["cleared_to_run"] = True

    def _preview_propositions(text, *, document_id, speaker, prompt_version):
        previous = propositions.EXTRACTION_MODEL
        propositions.EXTRACTION_MODEL = PREVIEW_GROQ_MODEL
        try:
            return _default_propositions(
                text,
                document_id=document_id,
                speaker=speaker,
                prompt_version=prompt_version,
            )
        finally:
            propositions.EXTRACTION_MODEL = previous

    print(
        "Starting no-write preview "
        f"(fetch + stub metadata + {PREVIEW_GROQ_MODEL} propositions)…"
    )
    report = preview_row(
        row,
        db=get_supabase(),
        db_params=_db_params(),
        prepare_options={"metadata_fn": _stub_metadata},
        preview_options={"proposition_model_fn": _preview_propositions},
    )
    path = write_preview_report(report, review_dir=DEFAULT_REVIEW_DIR)
    print(f"preview_report={path}")

    props = report.get("propositions") or []
    quotes = report.get("quote_span_proposals") or report.get("quote_spans") or []
    accounting = report.get("accounting") or {}
    meta = report.get("metadata") or {}
    source = report.get("source") or {}

    print("SUMMARY")
    print(f"  report_id={report.get('report_id')}")
    print(f"  title={report.get('title')!r}")
    print(f"  source={source}")
    print(f"  chunks={accounting.get('chunks_computed') or len(report.get('chunks') or [])}")
    print(f"  propositions={len(props)}")
    print(f"  quote_proposals={len(quotes)}")
    print(f"  database_rows_written={accounting.get('database_rows_written')}")
    print(f"  quote_rows_written={accounting.get('quote_rows_written')}")
    print(f"  cost_usd_total={report.get('cost_usd_total') or accounting.get('cost_usd_total')}")

    print("PROPOSITIONS (content + supporting passage excerpt)")
    for i, p in enumerate(props):
        content = (p.get("content") or p.get("text") or "")[:240]
        passage = (p.get("supporting_passage") or p.get("source_passage") or p.get("passage") or "")
        if not passage and p.get("chunk_index") is not None:
            chunks = report.get("chunks") or []
            idx = p.get("chunk_index")
            if isinstance(idx, int) and 0 <= idx < len(chunks):
                passage = (chunks[idx].get("content") or "")[:240]
        else:
            passage = str(passage)[:240]
        eligible = p.get("eligible")
        print(f"  [{i}] eligible={eligible}")
        print(f"      claim: {content!r}")
        print(f"      passage: {passage!r}")

    # Re-check DB uncleared
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT cleared_to_run, status, stored_documents, result_document_id FROM source_ingest_queue WHERE id = %s",
        (ROW_ID,),
    )
    q = cur.fetchone()
    cur.close()
    conn.close()
    print("QUEUE_AFTER_PREVIEW", dict(q))
    assert q["cleared_to_run"] is False
    assert q["result_document_id"] is None
    print("OK — preview complete; queue still uncleared; zero DB corpus writes expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
