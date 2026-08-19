#!/usr/bin/env python3
"""
Read-only pull for manual contamination review of 5 Derek Prince documents.
Connects ONLY via backend/app/.env.readonly-analysis (READONLY_ANALYSIS_DB_URL).
Asserts current_user = rhemata_readonly_analysis before any query.
Writes a single review file. Does NOT propose or apply any cuts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

PROJECT_ROOT = Path(__file__).resolve().parent.parent
READONLY_ENV_PATH = PROJECT_ROOT / "backend" / "app" / ".env.readonly-analysis"
OUT_PATH = PROJECT_ROOT / "non_teacher_span_proposals" / "prince_manual_review_pull.md"
ROLE_NAME = "rhemata_readonly_analysis"

DOCS = [
    ("49685b52-b3b6-4865-b86a-be64d27ce163", "Explanation Of Greek Word Charisma"),
    ("4a3d27bb-3b0c-43c1-a07a-3031140f91ee", "Introduction"),
    ("d5d38547-1fad-4831-a152-42de08e49103", "Resident Ministries - Shepherds and Deacons"),
    ("e47e2135-340d-4850-a3f4-71019116e364", "The Nature of the Covenant"),
    ("98d166e8-d63b-4794-b1c7-594facf6bf14", "Twenty-Six New Testament Charismata"),
]

SEARCH_TERMS = ["translated by", "translation by", "transcribed by", "translator"]
RE_TERMS = re.compile("|".join(re.escape(t) for t in SEARCH_TERMS), re.IGNORECASE)


def connect_readonly():
    import psycopg2

    if not READONLY_ENV_PATH.exists():
        raise RuntimeError("Missing %s" % READONLY_ENV_PATH)
    url = None
    for line in READONLY_ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("READONLY_ANALYSIS_DB_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url or ROLE_NAME not in url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL missing or not the analysis role")
    p = urlparse(url)
    user = unquote(p.username or "")
    if ROLE_NAME not in user:
        raise RuntimeError("Username is not the read-only analysis role: %r" % user)
    print("Connecting as %s to %s:%s (timeout 20s, no retry)..." % (
        user[:40], p.hostname, p.port or 5432,
    ))
    try:
        conn = psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            user=user,
            password=unquote(p.password or ""),
            dbname=(p.path or "/postgres").lstrip("/") or "postgres",
            connect_timeout=20,
        )
    except Exception as e:
        print("CONNECTION FAILED immediately: %s: %s" % (type(e).__name__, e))
        raise
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT current_user")
    cu = cur.fetchone()[0]
    if ROLE_NAME not in cu:
        conn.close()
        raise RuntimeError("Connected as %r, expected %r" % (cu, ROLE_NAME))
    print("Connected OK as %s" % cu)
    cur.close()
    return conn


def fetch_doc_title(conn, doc_id: str) -> str:
    cur = conn.cursor()
    cur.execute("SELECT title FROM documents WHERE id = %s::uuid", (doc_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else "(title not found)"


def fetch_all_chunks(conn, doc_id: str):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_index, content
        FROM chunks
        WHERE document_id = %s::uuid
        ORDER BY chunk_index
        """,
        (doc_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return [(int(r[0]), r[1] or "") for r in rows]


def context_around(text: str, match_start: int, match_end: int, radius: int = 200) -> str:
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    snippet = text[start:end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


def main() -> int:
    try:
        conn = connect_readonly()
    except Exception as e:
        print("FATAL: connection failed — stopping. %s" % e)
        return 2

    out_lines = []
    A = out_lines.append
    A("# Prince Documents — Manual Review Pull (chunk 0 + translation-term search)")
    A("")
    A("Read-only pull. Connection: `rhemata_readonly_analysis` only.")
    A("Asserted `current_user = rhemata_readonly_analysis` before any query.")
    A("No proposals. No cuts applied. For manual review only.")
    A("")
    A("Search terms (case-insensitive across ALL chunks): "
      "`translated by`, `translation by`, `transcribed by`, `translator`.")
    A("Context window: 400 chars centred on each match (200 each side).")
    A("")

    try:
        for doc_id, fallback_title in DOCS:
            title = fetch_doc_title(conn, doc_id)
            chunks = fetch_all_chunks(conn, doc_id)
            A("---")
            A("")
            A("## %s" % title)
            A("")
            A("- **document_id**: `%s`" % doc_id)
            A("- **stored title (from DB)**: %s" % title)
            A("- **fallback title (from brief)**: %s" % fallback_title)
            A("- **total chunks**: %d" % len(chunks))
            A("")
            # --- Chunk 0 full text ---
            if chunks:
                idx0, content0 = chunks[0]
                A("### Chunk 0 — FULL TEXT")
                A("")
                A("- **chunk_index**: %d" % idx0)
                A("- **char length**: %d" % len(content0))
                A("")
                A("```")
                A(content0)
                A("```")
                A("")
            else:
                A("### Chunk 0 — (document has no chunks)")
                A("")
            # --- Search all chunks for translation terms ---
            A("### Translation-term matches (all chunks)")
            A("")
            total_matches = 0
            for idx, content in chunks:
                for m in RE_TERMS.finditer(content):
                    total_matches += 1
                    ctx = context_around(content, m.start(), m.end(), 200)
                    A("- **chunk_index**: %d" % idx)
                    A("  - **matched term**: `%s`" % m.group(0))
                    A("  - **match position**: char %d–%d of %d" % (
                        m.start(), m.end(), len(content)))
                    A("  - **context (400 chars centred):**")
                    A("")
                    A("    ```")
                    for line in ctx.splitlines():
                        A("    " + line)
                    A("    ```")
                    A("")
            if total_matches == 0:
                A("*(no matches for any of the four search terms)*")
                A("")
            else:
                A("Total matches in this document: **%d**" % total_matches)
                A("")

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        print("Wrote %s (%d lines)" % (OUT_PATH, len(out_lines)))
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())