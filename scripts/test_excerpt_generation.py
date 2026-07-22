"""
Test script: fetch Precept Austin logos/G3056 word study from Supabase,
send to Claude Sonnet 4.5 for editing, print and save the result.

Usage (run from repo root):
    python3 scripts/test_excerpt_generation.py
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
import os

# Load env from backend/app/.env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

from supabase import create_client
import anthropic


def main():
    # 1. Find the logos word study document
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    doc_result = (
        db.table("documents")
        .select("id, title, author")
        .eq("source_kind", "word_study")
        .ilike("title", "%G3056%")
        .limit(1)
        .execute()
    )

    if not doc_result.data:
        print("ERROR: No logos word study document found")
        sys.exit(1)

    doc = doc_result.data[0]
    print(f"Document: {doc['title']}")
    print(f"Author: {doc['author']}")
    print(f"ID: {doc['id']}")

    # 2. Fetch all chunks ordered by chunk_index
    chunk_result = (
        db.table("chunks")
        .select("content, chunk_index")
        .eq("document_id", doc["id"])
        .order("chunk_index")
        .execute()
    )

    chunks = chunk_result.data or []
    print(f"Chunks: {len(chunks)}")

    if not chunks:
        print("ERROR: No chunks found for this document")
        sys.exit(1)

    concatenated = "\n\n".join(c["content"] for c in chunks)
    print(f"Total chars: {len(concatenated)}")
    print("---")

    # 3. Send to Claude Sonnet 4.5
    word = "logos"
    strongs = "G3056"

    system_prompt = """You are a scholarly editor preparing word study articles for a theological research library. Your job is to take raw extracted text from Precept Austin word studies and edit them into clean, readable articles.

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

    user_message = f"""The following is raw extracted text from a Precept Austin word study on "{word}" ({strongs}). Edit it into a clean article following your instructions.

SOURCE TEXT:
{concatenated}"""

    print("Sending to Claude Sonnet 4.5...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    output = response.content[0].text
    print(f"Response tokens: input={response.usage.input_tokens}, output={response.usage.output_tokens}")
    print("===\n")
    print(output)

    # 4. Save to file
    output_path = PROJECT_ROOT / "scripts" / "test_excerpt_output.md"
    output_path.write_text(output, encoding="utf-8")
    print(f"\n===\nSaved to {output_path}")


if __name__ == "__main__":
    main()
