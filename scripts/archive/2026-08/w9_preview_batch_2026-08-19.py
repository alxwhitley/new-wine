#!/usr/bin/env python3
"""W9 Phase 1b: no-write preview for all three batch queue rows.

Loads each uncleared row, sets cleared_to_run=True only in-memory, runs
preview_row with live gpt-oss-120b metadata + propositions, writes immutable
JSON under source_ingest_preview_review/, prints a human review summary.

Zero corpus / queue / quote writes. DB cleared_to_run stays false.
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

from app.db.supabase import get_supabase  # noqa: E402
from source_ingest_queue.preview import (  # noqa: E402
    DEFAULT_REVIEW_DIR,
    preview_row,
    write_preview_report,
)

# Filled by enqueue script output / live query if omitted.
ROW_IDS_ENV = os.environ.get("W9_ROW_IDS", "").strip()


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


def _load_row_ids(cur) -> list[str]:
    if ROW_IDS_ENV:
        return [x.strip() for x in ROW_IDS_ENV.split(",") if x.strip()]
    urls = [
        "https://pastorvlad.org/tenways/",
        "https://pastorvlad.org/planted-not-buried-what-god-is-doing-while-you-wait/",
        "https://pastorvlad.org/intrusive-thoughts-demon-stronghold-or-just-your-mind/",
    ]
    ids = []
    for url in urls:
        cur.execute(
            """
            SELECT id::text
            FROM source_ingest_queue
            WHERE url = %s AND status = 'waiting' AND cleared_to_run = false
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (url,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"missing uncleared waiting row for {url}")
        ids.append(row["id"])
    return ids


def main() -> int:
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    row_ids = _load_row_ids(cur)
    summaries = []

    for row_id in row_ids:
        cur.execute("SELECT * FROM source_ingest_queue WHERE id = %s", (row_id,))
        row = cur.fetchone()
        if row is None:
            print(f"queue row missing {row_id}", file=sys.stderr)
            return 2
        row = dict(row)
        if row.get("cleared_to_run") is True:
            print(
                f"REFUSING: {row_id} already cleared_to_run=true",
                file=sys.stderr,
            )
            return 2

        print(f"\n=== PREVIEW {row_id} url={row.get('url')} ===")
        row["cleared_to_run"] = True  # in-memory only
        report = preview_row(row, db=get_supabase(), db_params=_db_params())
        path = write_preview_report(report, review_dir=DEFAULT_REVIEW_DIR)
        props = report.get("propositions") or []
        quotes = report.get("quote_span_proposals") or report.get("quote_spans") or []
        accounting = report.get("accounting") or {}
        source = report.get("source") or {}
        summary = {
            "row_id": row_id,
            "url": row.get("url"),
            "report_id": report.get("report_id"),
            "preview_path": str(path),
            "title": report.get("title"),
            "source": source,
            "chunks": accounting.get("chunks_computed")
            or len(report.get("chunks") or []),
            "propositions": len(props),
            "quote_proposals": len(quotes),
            "database_rows_written": accounting.get("database_rows_written"),
            "quote_rows_written": accounting.get("quote_rows_written"),
            "cost_usd_total": report.get("cost_usd_total")
            or accounting.get("cost_usd_total"),
            "prop_previews": [
                {
                    "i": i,
                    "eligible": p.get("eligible"),
                    "claim": (p.get("content") or p.get("text") or "")[:220],
                }
                for i, p in enumerate(props)
            ],
        }
        summaries.append(summary)
        print(json.dumps({k: summary[k] for k in summary if k != "prop_previews"}, indent=2))
        for p in summary["prop_previews"]:
            print(f"  [{p['i']}] eligible={p['eligible']} claim={p['claim']!r}")

        cur.execute(
            """
            SELECT cleared_to_run, status, stored_documents, result_document_id
            FROM source_ingest_queue WHERE id = %s
            """,
            (row_id,),
        )
        q = cur.fetchone()
        assert q["cleared_to_run"] is False
        assert q["result_document_id"] is None
        print("QUEUE_STILL_UNCLEARED", dict(q))

    cur.close()
    conn.close()

    out = ROOT / "docs/audits/w9_preview_summary_2026-08-19.json"
    out.write_text(json.dumps(summaries, indent=2))
    print(f"\nWrote {out}")
    print("OK — 3 previews complete; queue still uncleared; zero corpus writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
