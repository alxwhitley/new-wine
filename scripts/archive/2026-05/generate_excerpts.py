"""
Batch generate edited word study articles from Precept Austin raw chunks.

Usage (run from repo root):
    python3 scripts/generate_excerpts.py                        # full batch (sonnet)
    python3 scripts/generate_excerpts.py --test                 # 5 docs, print only, no DB writes
    python3 scripts/generate_excerpts.py --test-quality --model haiku  # 3 docs with haiku for quality review
    python3 scripts/generate_excerpts.py --model haiku          # full batch with haiku
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

from supabase import create_client
import anthropic

MODELS = {
    "sonnet": {"id": "claude-sonnet-4-5", "label": "claude-sonnet-4-5"},
    "haiku": {"id": "claude-haiku-4-5-20251001", "label": "claude-haiku-4-5"},
}
EXCERPT_TYPE = "word_study_article"

SYSTEM_PROMPT = """You are a scholarly editor preparing word study articles for a theological research library. Your job is to take raw extracted text from Precept Austin word studies and edit them into clean, readable articles.

RULES — YOU MUST FOLLOW THESE EXACTLY:
1. Never rewrite sentences. You may only reorder sentences, remove redundant repetition, and fix transitions between thoughts.
2. Never add new content, interpretation, or bridging sentences you have invented. Every sentence in the output must exist in the source text.
3. Preserve full length — do not condense or summarize. All substantive content must be retained.
4. Preserve academic tone throughout. Do not warm up or simplify the language.
5. Remove formatting artifacts: parenthetical Strong's number references like "(G3056)", OCR artifacts, broken punctuation, mid-sentence line breaks, and duplicate phrases caused by chunk overlap.
6. Add subheadings throughout the article. Infer subheadings from the content — do not impose a fixed structure. Subheadings should reflect what each section actually covers (e.g. "Etymology", "Classical Greek Usage", "Usage in the Septuagint", "New Testament Occurrences", "Key Passages"). Use ## for subheadings.
7. The article should read as one continuous flowing piece, not a list of excerpts.
8. Output only the article body in markdown. No preamble, no meta-commentary, no "Here is the article" intro.
9. When the source text quotes another scholar, commentary, or external source, italicize the quoted passage using markdown italics (*like this*). This applies to block quotes and inline quotes from named sources. Do not italicize scripture references."""


def parse_title(title):
    # type: (str) -> Tuple[str, str]
    """Extract word and strongs from title like 'Word Study: Word (logos, G3056)'."""
    m = re.search(r'\(([^,]+),\s*(G\d+|H\d+)\)', title)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Fallback: try just strongs
    m2 = re.search(r'(G\d+|H\d+)', title)
    if m2:
        return title.split(":")[-1].strip().split("(")[0].strip(), m2.group(1)
    return title, ""


def generate_article(client, word, strongs, concatenated, model_id):
    # type: (anthropic.Anthropic, str, str, str, str) -> str
    user_message = (
        f'The following is raw extracted text from a Precept Austin word study on '
        f'"{word}" ({strongs}). Edit it into a clean article following your instructions.\n\n'
        f'SOURCE TEXT:\n{concatenated}'
    )
    response = client.messages.create(
        model=model_id,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def setup_logging():
    # type: () -> logging.Logger
    log_dir = PROJECT_ROOT / "scripts" / "logs"
    log_dir.mkdir(exist_ok=True)
    logger = logging.getLogger("excerpt_generation")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_dir / "excerpt_generation.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
    logger.addHandler(fh)
    return logger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run on 5 docs, print output, no DB writes")
    parser.add_argument("--test-quality", action="store_true", help="Run 3 docs, print full output for quality review, no DB writes")
    parser.add_argument("--model", choices=["sonnet", "haiku"], default="sonnet", help="Model to use (default: sonnet)")
    parser.add_argument("--time-limit", type=int, default=None, help="Stop after this many minutes (graceful)")
    args = parser.parse_args()

    if args.test_quality:
        args.test = True

    model_cfg = MODELS[args.model]
    model_id = model_cfg["id"]
    model_label = model_cfg["label"]
    print(f"Using model: {model_id}")

    logger = setup_logging()
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Fetch all word_study documents
    all_docs = []  # type: List[dict]
    page_size = 1000
    offset = 0
    while True:
        batch = (
            db.table("documents")
            .select("id, title")
            .eq("source_kind", "word_study")
            .order("title")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = batch.data or []
        all_docs.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    total_docs = len(all_docs)
    print(f"Found {total_docs} word_study documents")

    if args.test_quality:
        all_docs = all_docs[:3]
        print(f"QUALITY TEST: processing {len(all_docs)} documents with {model_id} (no DB writes)\n")
    elif args.test:
        all_docs = all_docs[:5]
        print(f"TEST MODE: processing {len(all_docs)} documents (no DB writes)\n")

    # Fetch already-completed document IDs (skip in test mode — nothing to skip)
    completed_ids = set()  # type: set
    if not args.test:
        exc_offset = 0
        while True:
            exc_batch = (
                db.table("excerpts")
                .select("document_id")
                .eq("excerpt_type", EXCERPT_TYPE)
                .range(exc_offset, exc_offset + page_size - 1)
                .execute()
            )
            exc_rows = exc_batch.data or []
            for r in exc_rows:
                completed_ids.add(r["document_id"])
            if len(exc_rows) < page_size:
                break
            exc_offset += page_size
        print(f"Already completed: {len(completed_ids)}")

    processed = 0
    skipped = 0
    failed = 0
    failed_list = []  # type: List[Tuple[str, str, str]]
    batch_start = time.time()

    time_limit_seconds = args.time_limit * 60 if args.time_limit else None

    for i, doc in enumerate(all_docs, 1):
        if time_limit_seconds and (time.time() - batch_start) >= time_limit_seconds:
            print(f"\nTime limit ({args.time_limit}m) reached. Stopping gracefully.")
            logger.info("TIME LIMIT reached after %.0fs", time.time() - batch_start)
            break

        doc_id = doc["id"]
        title = doc["title"]

        # Skip if already done
        if doc_id in completed_ids:
            skipped += 1
            logger.info("SKIPPED  %s  %s  already completed", doc_id, title)
            print(f"[{i}/{len(all_docs)}] -- {title} (already done)")
            continue

        t0 = time.time()

        try:
            # Fetch chunks
            chunk_result = (
                db.table("chunks")
                .select("content")
                .eq("document_id", doc_id)
                .order("chunk_index")
                .execute()
            )
            chunks = chunk_result.data or []
            if not chunks:
                skipped += 1
                logger.warning("SKIPPED  %s  %s  no chunks", doc_id, title)
                print(f"[{i}/{len(all_docs)}] -- {title} (no chunks)")
                continue

            concatenated = "\n\n".join(c["content"] for c in chunks)
            word, strongs = parse_title(title)

            # Generate
            article = generate_article(ai, word, strongs, concatenated, model_id)
            elapsed = time.time() - t0

            if args.test:
                print(f"[{i}/{len(all_docs)}] OK {title} — {elapsed:.1f}s")
                print(f"  word={word}, strongs={strongs}, chunks={len(chunks)}, chars={len(concatenated)}")
                print("--- OUTPUT ---")
                print(article)
                print("--- END ---\n")
            else:
                # Insert into excerpts
                db.table("excerpts").insert({
                    "document_id": doc_id,
                    "content": article,
                    "model": model_label,
                    "excerpt_type": EXCERPT_TYPE,
                }).execute()
                print(f"[{i}/{len(all_docs)}] OK {title} — {elapsed:.1f}s")

            processed += 1
            logger.info("SUCCESS  %s  %s  %.1fs", doc_id, title, elapsed)

        except Exception as e:
            elapsed = time.time() - t0
            failed += 1
            err_msg = str(e)[:200]
            failed_list.append((doc_id, title, err_msg))
            logger.error("FAILED   %s  %s  %s", doc_id, title, err_msg)
            print(f"[{i}/{len(all_docs)}] FAIL {title} — {err_msg[:80]}")

    total_elapsed = time.time() - batch_start

    # Summary
    print("\n" + "=" * 60)
    print(f"DONE in {total_elapsed:.0f}s ({total_elapsed / 60:.1f}m)")
    print(f"  Processed: {processed}")
    print(f"  Skipped:   {skipped}")
    print(f"  Failed:    {failed}")
    if failed_list:
        print("\nFailed documents:")
        for doc_id, title, err in failed_list:
            print(f"  {doc_id}  {title}")
            print(f"    {err}")


if __name__ == "__main__":
    main()
