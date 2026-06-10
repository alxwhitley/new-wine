"""
Extract quotable passages from Andrew Murray books using Claude Haiku.

Usage:
    cd /Users/alexwhitley/Desktop/rhemata
    python3 scripts/extract_book_quotes.py
    python3 scripts/extract_book_quotes.py --dry-run
    python3 scripts/extract_book_quotes.py --limit 2
    python3 scripts/extract_book_quotes.py --title "Abide in Christ"
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

import anthropic
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY is not set in backend/app/.env")
    sys.exit(1)
if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

PROMPT = """You are extracting quotable passages from a classic Christian devotional book.

Extract exactly 5 standalone quotable passages from the text below. Requirements:
- Each quote must be 2-5 complete sentences
- Each quote must be readable with no surrounding context needed
- Each quote must be a complete thought — do not cut mid-sentence
- Avoid: page numbers, table of contents entries, metadata, publisher info, URLs, roman numerals, repeated headers
- Prefer: spiritually rich, devotionally meaningful passages that stand alone beautifully

Return ONLY a valid JSON array of exactly 5 strings. No preamble, no markdown, no explanation.
Example format: ["Quote one here.", "Quote two here.", "Quote three here.", "Quote four here.", "Quote five here."]"""

SKIP_STRINGS = ["ccel.org", "PDF", "Copyright", "Calvin College", "http"]


def validate_quote(text):
    # type: (str) -> bool
    if len(text) < 100 or len(text) > 600:
        return False
    if text[0].isdigit():
        return False
    for skip in SKIP_STRINGS:
        if skip in text:
            return False
    return True


def extract_quotes_from_batch(client, batch_text):
    # type: (...) -> list
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": f"{PROMPT}\n\n---\n\n{batch_text}"}],
        )
        raw = resp.content[0].text.strip()
        quotes = json.loads(raw)
        if not isinstance(quotes, list):
            return []
        return [q for q in quotes if isinstance(q, str)]
    except json.JSONDecodeError:
        logger.warning("JSON parse failed for batch")
        return []
    except Exception:
        logger.exception("API call failed for batch")
        return []


def main():
    parser = argparse.ArgumentParser(description="Extract book quotes from Murray books")
    parser.add_argument("--dry-run", action="store_true", help="Print quotes without inserting")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to process")
    parser.add_argument("--title", type=str, default=None, help="Process single book by title match")
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    # Find Murray book documents
    if args.title:
        cur.execute(
            "SELECT id, title, author FROM documents WHERE source_type = 'book' AND author ILIKE %s AND title ILIKE %s ORDER BY title",
            ("%murray%", f"%{args.title}%"),
        )
    else:
        cur.execute(
            "SELECT id, title, author FROM documents WHERE source_type = 'book' AND author ILIKE %s ORDER BY title",
            ("%murray%",),
        )

    docs = cur.fetchall()
    logger.info("Found %d Murray book documents", len(docs))

    if args.limit:
        docs = docs[:args.limit]

    for doc_id, title, author in docs:
        # Skip if already extracted
        cur.execute("SELECT COUNT(*) FROM book_quotes WHERE document_id = %s", (doc_id,))
        existing = cur.fetchone()[0]
        if existing > 0:
            logger.info("Skipping '%s' — already has %d quotes", title, existing)
            continue

        # Fetch chunks
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (doc_id,),
        )
        chunks = [row[0] for row in cur.fetchall()]
        if not chunks:
            logger.warning("No chunks for '%s', skipping", title)
            continue

        # Divide into 10 evenly spaced batches
        n_batches = 10
        batch_size = max(1, len(chunks) // n_batches)
        batches = []
        for i in range(n_batches):
            start = i * batch_size
            end = start + batch_size if i < n_batches - 1 else len(chunks)
            if start < len(chunks):
                batches.append(chunks[start:end])

        all_quotes = []
        quote_index = 0

        for batch_num, batch_chunks in enumerate(batches):
            batch_text = "\n\n".join(batch_chunks)
            raw_quotes = extract_quotes_from_batch(client, batch_text)

            valid = []
            skipped = 0
            for q in raw_quotes:
                if validate_quote(q):
                    all_quotes.append((doc_id, q.strip(), quote_index))
                    quote_index += 1
                    valid.append(q)
                else:
                    skipped += 1

            logger.info(
                "'%s' batch %d/%d: %d extracted, %d valid, %d skipped",
                title, batch_num + 1, len(batches), len(raw_quotes), len(valid), skipped,
            )

        if not all_quotes:
            logger.warning("No valid quotes for '%s'", title)
            continue

        if args.dry_run:
            logger.info("DRY RUN — '%s': %d quotes", title, len(all_quotes))
            for _, qt, qi in all_quotes:
                print(f"  [{qi}] {qt[:120]}...")
        else:
            execute_values(
                cur,
                "INSERT INTO book_quotes (document_id, quote_text, quote_index) VALUES %s",
                all_quotes,
            )
            conn.commit()
            logger.info("Inserted %d quotes for '%s'", len(all_quotes), title)

    cur.close()
    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
