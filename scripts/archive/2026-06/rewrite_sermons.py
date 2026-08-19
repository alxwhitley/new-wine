"""
Batch rewrite sermon transcripts into structured notes via Claude Haiku.

Usage:
    python3 scripts/rewrite_sermons.py
    python3 scripts/rewrite_sermons.py --limit 5 --dry-run
    python3 scripts/rewrite_sermons.py --author "Derek Prince" --time-limit 30
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import anthropic
import psycopg2
import tiktoken

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY is not set in backend/app/.env")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

SYSTEM_PROMPT = """You are a sermon notes editor. You will receive a raw sermon transcript and reformat it into clean, readable structured notes.

Rules:
- Add clear subheadings (##) that reflect the actual flow of the sermon
- Break content into readable paragraphs with proper spacing
- Remove filler words, false starts, and repetition
- Preserve the speaker's voice, theology, and specific points — do not add content or change meaning
- Keep scripture references exactly as stated
- Output should feel like well-organized sermon notes, not a transcript
- Do not add an introduction or conclusion that wasn't in the original
- Return only the formatted notes, no preamble"""

CHUNK_TARGET = 550
CHUNK_OVERLAP = 80

# ── Logging ───────────────────────────────────────────────────────────────────

log_dir = Path(__file__).resolve().parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "rewrite_sermons.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Chunker (mirrors backend/app/services/chunker.py) ────────────────────────

_enc = tiktoken.get_encoding("cl100k_base")


def chunk_text(text, chunk_target=CHUNK_TARGET, overlap=CHUNK_OVERLAP):
    # type: (str, int, int) -> List[str]
    tokens = _enc.encode(text)
    if len(tokens) <= chunk_target:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_target, len(tokens))
        chunk_str = _enc.decode(tokens[start:end])

        if end < len(tokens):
            last_heading = max(
                chunk_str.rfind("\n# "),
                chunk_str.rfind("\n## "),
            )
            if last_heading > len(chunk_str) * 0.3:
                chunk_str = chunk_str[:last_heading]
                end = start + len(_enc.encode(chunk_str))
            else:
                last_para = chunk_str.rfind("\n\n")
                if last_para > len(chunk_str) * 0.5:
                    chunk_str = chunk_str[:last_para]
                    end = start + len(_enc.encode(chunk_str))
                else:
                    last_period = chunk_str.rfind(". ")
                    if last_period > len(chunk_str) * 0.5:
                        chunk_str = chunk_str[:last_period + 1]
                        end = start + len(_enc.encode(chunk_str))

        if chunk_str.strip():
            chunks.append(chunk_str.strip())

        if end >= len(tokens):
            break

        advance = max(end - start - overlap, 1)
        start = start + advance

    return chunks


# ── Main ──────────────────────────────────────────────────────────────────────

def rewrite_document(client, conn, doc_id, doc_title, dry_run=False):
    # type: (anthropic.Anthropic, ..., str, str, bool) -> bool
    """Rewrite a single document. Returns True on success."""
    cur = conn.cursor()

    # Fetch all chunks ordered by chunk_index
    cur.execute(
        "SELECT id, chunk_index, content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
        (doc_id,),
    )
    chunks = cur.fetchall()
    if not chunks:
        logger.warning("No chunks found for document %s (%s)", doc_id, doc_title)
        cur.execute(
            "UPDATE documents SET rewrite_status = 'failed' WHERE id = %s",
            (doc_id,),
        )
        conn.commit()
        cur.close()
        return False

    # Concatenate into full transcript
    full_text = "\n".join(row[2] for row in chunks)
    token_count = len(_enc.encode(full_text))
    logger.info("Document %s (%s): %d chunks, ~%d tokens", doc_id, doc_title, len(chunks), token_count)

    if dry_run:
        logger.info("[DRY RUN] Would rewrite %s (%s)", doc_id, doc_title)
        cur.close()
        return True

    # Send to Claude Haiku
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": full_text}],
    )
    rewritten = message.content[0].text

    # Re-chunk the rewritten output
    new_chunks = chunk_text(rewritten)
    logger.info("Rewritten into %d chunks", len(new_chunks))

    # Update rewritten_content on existing chunks
    # If rewritten has fewer chunks than original, update what we can and NULL the rest
    # If rewritten has more chunks than original, pack extras into the last chunk
    original_ids = [row[0] for row in chunks]

    if len(new_chunks) <= len(original_ids):
        for i, chunk_id in enumerate(original_ids):
            if i < len(new_chunks):
                cur.execute(
                    "UPDATE chunks SET rewritten_content = %s WHERE id = %s",
                    (new_chunks[i], chunk_id),
                )
            else:
                cur.execute(
                    "UPDATE chunks SET rewritten_content = NULL WHERE id = %s",
                    (chunk_id,),
                )
    else:
        # More new chunks than original — pack overflow into last original chunk
        for i in range(len(original_ids) - 1):
            cur.execute(
                "UPDATE chunks SET rewritten_content = %s WHERE id = %s",
                (new_chunks[i], original_ids[i]),
            )
        # Last chunk gets the rest joined
        overflow = "\n\n".join(new_chunks[len(original_ids) - 1:])
        cur.execute(
            "UPDATE chunks SET rewritten_content = %s WHERE id = %s",
            (overflow, original_ids[-1]),
        )

    cur.execute(
        "UPDATE documents SET rewrite_status = 'complete' WHERE id = %s",
        (doc_id,),
    )
    conn.commit()
    cur.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Rewrite sermon transcripts into structured notes")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--author", type=str, default=None, help="Filter by author name")
    parser.add_argument("--time-limit", type=int, default=None, help="Max minutes to run")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Query pending sermon transcripts
    query = """
        SELECT id, title, author
        FROM documents
        WHERE source_kind = 'sermon_transcript'
          AND (rewrite_status IS NULL OR rewrite_status = 'pending')
    """
    params = []  # type: List
    if args.author:
        query += " AND author ILIKE %s"
        params.append("%" + args.author + "%")
    query += " ORDER BY created_at"
    if args.limit:
        query += " LIMIT %s"
        params.append(args.limit)

    cur = conn.cursor()
    cur.execute(query, params)
    docs = cur.fetchall()
    cur.close()

    logger.info("Found %d sermon transcripts to rewrite", len(docs))

    start_time = time.time()
    success = 0
    failed = 0

    for doc_id, doc_title, doc_author in docs:
        if args.time_limit:
            elapsed = (time.time() - start_time) / 60
            if elapsed >= args.time_limit:
                logger.info("Time limit reached (%.1f min). Stopping.", elapsed)
                break

        try:
            ok = rewrite_document(client, conn, doc_id, doc_title, dry_run=args.dry_run)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception:
            logger.exception("Failed to rewrite document %s (%s)", doc_id, doc_title)
            failed += 1
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE documents SET rewrite_status = 'failed' WHERE id = %s",
                    (doc_id,),
                )
                conn.commit()
                cur.close()
            except Exception:
                logger.exception("Failed to mark document %s as failed", doc_id)

    elapsed = (time.time() - start_time) / 60
    logger.info("Done. %d success, %d failed in %.1f min", success, failed, elapsed)
    conn.close()


if __name__ == "__main__":
    main()
