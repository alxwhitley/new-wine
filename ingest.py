#!/usr/bin/env python3
"""
Rhemata Document Ingestion Script
Extracts text from PDFs, DOCX, and DOC files, auto-detects metadata via Claude,
chunks by paragraph, embeds with OpenAI, writes to Supabase.
"""

import os
import re
import sys
import uuid
import json
import hashlib
from pathlib import Path

import anthropic
import openai
from supabase import create_client
import subprocess
import pdfplumber
import docx

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app.services.chunker import chunk_pages, token_len

# ── Config ────────────────────────────────────────────────────────────────────

DOCS_FOLDER = Path("/Users/alexwhitley/Desktop/rhemata/pdf")
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_SERVICE_KEY"]

EMBEDDING_MODEL  = "text-embedding-3-small"
EMBEDDING_DIM    = 1536

# ── Clients ───────────────────────────────────────────────────────────────────

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
openai_client    = openai.OpenAI(api_key=OPENAI_API_KEY)
supabase         = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Text Extraction ──────────────────────────────────────────────────────────

def extract_pages(pdf_path: Path) -> list[str]:
    """Return a list of page text strings from a PDF."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text.strip())
    return pages


def extract_docx(path: Path) -> list[str]:
    """Extract text from a .docx file. Returns a list of strings grouped by
    page breaks, or as a single-element list if no page breaks are found."""
    doc = docx.Document(str(path))
    pages = []
    current = []
    for para in doc.paragraphs:
        # Check for page break in the paragraph's runs
        has_break = any(
            run._element.xml.find(
                '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}br'
            ) != -1
            and 'type="page"' in run._element.xml
            for run in para.runs
        )
        if has_break and current:
            pages.append("\n".join(current))
            current = []
        if para.text.strip():
            current.append(para.text.strip())
    if current:
        pages.append("\n".join(current))
    return pages


def extract_doc(path: Path) -> list[str]:
    """Extract text from a .doc file using macOS textutil. Returns a
    single-element list since .doc files have no reliable page boundary info."""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True, text=True,
    )
    raw = result.stdout.strip()
    return [raw] if raw else []


def extract_txt(path: Path) -> tuple[list[str], dict[str, str]]:
    """Extract text from a .txt file. Parses optional metadata headers at the top.
    Headers are lines matching KEY: VALUE before the first blank line.
    Returns (pages, headers_dict)."""
    raw = path.read_text(encoding="utf-8").strip()
    headers: dict[str, str] = {}
    body = raw

    # Parse metadata headers (lines before first blank line)
    lines = raw.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            header_end = i + 1
            break
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            headers[key.strip().upper()] = value.strip()
            header_end = i + 1
        else:
            break

    if headers:
        body = "\n".join(lines[header_end:]).strip()

    return [body] if body else [], headers


# ── Metadata Extraction ───────────────────────────────────────────────────────

def extract_metadata(first_page_text: str, filename: str) -> dict:
    """Ask Claude to extract structured metadata from the first page."""
    prompt = f"""You are processing a document for a theological research database.
Extract metadata from the first page text below. Return ONLY valid JSON with these exact keys:
{{
  "title": "document title or best guess",
  "author": "author name or null",
  "year": year as integer or null,
  "issue": "issue number/identifier as string or null",
  "source_name": "publication name (e.g. New Wine Magazine) or null",
  "source_type": "magazine | sermon | paper | book | other",
  "topic_tags": ["tag1", "tag2"]  // 2-5 relevant theological topics
}}

Filename: {filename}

First page text:
{first_page_text[:3000]}

Return only the JSON object. No explanation, no markdown.
"""

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON if Claude added any surrounding text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Claude returned non-JSON metadata: {raw}")

# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

# ── Supabase Write ────────────────────────────────────────────────────────────

def already_ingested(source_hash: str) -> bool:
    """Return True if this source_hash already exists in chunks."""
    result = supabase.table("chunks") \
        .select("id") \
        .eq("source_hash", source_hash) \
        .limit(1) \
        .execute()
    return len(result.data) > 0


def insert_document(metadata: dict, file_path: str, is_copyrighted: bool = False, url=None) -> str:
    """Insert a document row and return its UUID."""
    doc_id = str(uuid.uuid4())
    row = {
        "id":          doc_id,
        "title":       metadata.get("title"),
        "author":      metadata.get("author"),
        "year":        metadata.get("year"),
        "issue":       metadata.get("issue"),
        "source_name": metadata.get("source_name"),
        "source_type": metadata.get("source_type"),
        "source":      metadata.get("source_name"),  # mirrors source_name
        "topic_tags":  metadata.get("topic_tags", []),
        "file_path":   file_path,
        "is_copyrighted": is_copyrighted,
    }
    if url:
        row["url"] = url
    try:
        supabase.table("documents").insert(row).execute()
    except Exception:
        # url column may not exist yet — retry without it
        row.pop("url", None)
        supabase.table("documents").insert(row).execute()
    return doc_id


def insert_chunks(doc_id: str, chunks: list[tuple[str, int]], author: str = None, year: int = None, source_hash: str = None):
    """Embed and insert all chunks for a document."""
    for idx, (text, page_num) in enumerate(chunks):
        print(f"  Embedding chunk {idx + 1}/{len(chunks)} (page {page_num})...")
        prefix = f"Author: {author} | Year: {year} | "
        embedding = embed_text(prefix + text)

        supabase.table("chunks").insert({
            "id":          str(uuid.uuid4()),
            "document_id": doc_id,
            "content":     text,
            "embedding":   embedding,
            "chunk_index": idx,
            "page_number": page_num,
            "source_hash": source_hash,
        }).execute()

# ── Main ──────────────────────────────────────────────────────────────────────

def ingest_file(file_path: Path, dry_run: bool = False, is_copyrighted: bool = False) -> str:
    """Returns 'processed', 'skipped', or 'failed'."""
    print(f"\n{'='*60}")
    print(f"Processing: {file_path.name} {'[COPYRIGHTED]' if is_copyrighted else '[OPEN]'}")
    print('='*60)

    # 0. Duplicate check via file content hash
    source_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
    if not dry_run and already_ingested(source_hash):
        print(f"  ⏭️  Already ingested — skipping")
        return "skipped"

    # 1. Extract text
    ext = file_path.suffix.lower()
    txt_headers: dict[str, str] = {}
    if ext == ".txt":
        print(f"Extracting text ({ext})...")
        pages, txt_headers = extract_txt(file_path)
        if txt_headers:
            print(f"  Parsed headers: {txt_headers}")
    else:
        extractors = {
            ".pdf": extract_pages,
            ".docx": extract_docx,
            ".doc": extract_doc,
        }
        print(f"Extracting text ({ext})...")
        pages = extractors[ext](file_path)
    if not pages or not any(pages):
        print("  ⚠️  No text extracted — skipping")
        return "failed"

    print(f"  {len(pages)} pages extracted")

    # 2. Auto-detect metadata from first page
    print("Detecting metadata via Claude...")
    metadata = extract_metadata(pages[0], file_path.name)
    print(f"  Title:   {metadata.get('title')}")
    print(f"  Author:  {metadata.get('author')}")
    print(f"  Year:    {metadata.get('year')}")
    print(f"  Source:  {metadata.get('source_name')}")
    print(f"  Tags:    {metadata.get('topic_tags')}")

    # 3. Chunk by paragraph
    print("Chunking by paragraph...")
    chunks = chunk_pages(pages)
    print(f"  {len(chunks)} chunks created")

    if dry_run:
        author = metadata.get("author")
        year = metadata.get("year")
        prefix = f"Author: {author} | Year: {year} | "
        preview = chunks[:3]
        print(f"\n  [DRY RUN] Previewing first {len(preview)} of {len(chunks)} chunks:\n")
        for idx, (text, page_num) in enumerate(preview):
            tokens = token_len(text)
            print(f"  ── Chunk {idx + 1} | Page {page_num} | {tokens} tokens ──")
            print(f"  Embed prefix: {prefix}")
            print(f"  Content: {text[:300]}{'...' if len(text) > 300 else ''}")
            print()
        print("  [DRY RUN] No data written to Supabase.")
        return "processed"

    # 4. Insert document row
    source_url = txt_headers.get("SOURCE_URL") if txt_headers else None
    print("Inserting document record...")
    doc_id = insert_document(metadata, str(file_path), is_copyrighted=is_copyrighted, url=source_url)
    print(f"  Document ID: {doc_id}")

    # 5. Embed + insert chunks
    print(f"Embedding and inserting {len(chunks)} chunks...")
    insert_chunks(doc_id, chunks, author=metadata.get("author"), year=metadata.get("year"), source_hash=source_hash)

    print(f"✅  Done: {file_path.name}")
    return "processed"


def main():
    dry_run = "--dry-run" in sys.argv

    # Scan pdf/ root, pdf/open/, and pdf/copyrighted/ subdirectories
    open_dir = DOCS_FOLDER / "open"
    copyrighted_dir = DOCS_FOLDER / "copyrighted"

    files: list[tuple[Path, bool]] = []  # (path, is_copyrighted)

    # Root-level files (non-copyrighted)
    for f in sorted(DOCS_FOLDER.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append((f, False))

    for folder, copyrighted in [(open_dir, False), (copyrighted_dir, True)]:
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append((f, copyrighted))

    if not files:
        print(f"No supported files found in {open_dir} or {copyrighted_dir}")
        return

    if dry_run:
        print(f"[DRY RUN] Found {len(files)} file(s) to process")
    else:
        print(f"Found {len(files)} file(s) to process")

    processed = skipped = failed = 0
    for file_path, is_copyrighted in files:
        result = ingest_file(file_path, dry_run=dry_run, is_copyrighted=is_copyrighted)
        if result == "processed":
            processed += 1
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Done. {processed} processed, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
