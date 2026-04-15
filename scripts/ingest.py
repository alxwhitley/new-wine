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
import shutil
from pathlib import Path

from groq import Groq
import openai
from supabase import create_client
import subprocess
import pdfplumber
import docx

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.chunker import chunk_text, token_len
from bible_refs import extract_bible_references

# ── Config ────────────────────────────────────────────────────────────────────

DOCS_FOLDER = Path("/Users/alexwhitley/Desktop/rhemata/sources")
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_TAG_CHARS = 4000

VALID_TAGS = {
    "Baptism in the Spirit", "Speaking in Tongues", "Prophetic Ministry",
    "Word of Knowledge", "Word of Wisdom", "Discerning of Spirits",
    "Miracles and Signs", "The Nine Gifts", "Stirring Up Gifts",
    "Moving in the Spirit", "Fruit of the Spirit", "Fresh Anointing",
    "Filling of the Spirit", "Power for Service",
    "Hearing God's Voice", "Dreams and Visions", "Interpreting Your Dreams",
    "Encounters with God", "Divine Appointments", "Supernatural Peace",
    "Manifestations of God", "Intimacy with Jesus", "Atmosphere of Worship",
    "Spiritual Sight", "Knowing God's Heart", "Personal Revelation",
    "Walking in the Spirit", "Led by the Spirit",
    "Intercessory Prayer", "Authority of the Believer",
    "Tearing Down Strongholds", "Resisting the Enemy", "Victory in Christ",
    "Deliverance from Bondage", "Casting Out Demons", "Spiritual Weapons",
    "Breaking Negative Patterns", "Binding and Loosing", "Armor of God",
    "Warfare in Prayer", "Fasting and Prayer", "Protecting Your Mind",
    "Divine Healing", "Praying for the Sick", "Inner Healing",
    "Emotional Wholeness", "Healing of Memories", "Health and Vitality",
    "Overcoming Fear", "Freedom from Anxiety", "Restoration of Soul",
    "Physical Miracles", "The Will to Heal", "Faith for Healing",
    "God's Comfort", "Wholeness in Christ",
    "Biblical Leadership", "Fivefold Ministry", "Apostolic Oversight",
    "Prophetic Direction", "Pastoral Care", "Delegated Authority",
    "Spiritual Covering", "Accountability in Leadership",
    "Covenant Relationships", "Mentoring Relationships",
    "Leading with Integrity", "Servant Leadership", "Team Ministry",
    "Equipping the Saints", "Elders and Deacons",
    "Spiritual Maturity", "Walking with God", "Discipleship and Mentoring",
    "Accountability in Christ", "Knowing God's Will", "Character of Christ",
    "Honoring Biblical Authority", "Submission to God",
    "Faith and Perseverance", "Stewardship and Finances",
    "Spiritual Disciplines", "Dying to Self", "Holiness and Sanctification",
    "Body Ministry",
    "Kingdom of God", "Word and Spirit", "Biblical Authority",
    "The New Covenant", "The Lordship of Christ", "Grace and Mercy",
    "Salvation and Repentance", "End Times Prophecy", "The Rapture",
    "Second Coming", "The Trinity", "Blood of Jesus", "Heaven and Eternity",
    "Restoration of All Things",
    "Biblical Marriage", "Christian Parenting", "Family Life",
    "Relationship Restoration", "Communication in Marriage",
    "Raising Godly Children", "Singleness and Purity",
    "Friendship in Christ", "Honoring Your Parents", "Forgiving Others",
    "Love and Sacrifice", "Conflict Resolution", "The Christian Home",
}

TAXONOMY_LIST = ", ".join(sorted(VALID_TAGS))

TAG_SYSTEM_PROMPT = f"""You are a theological taxonomy classifier. Based on this document, assign 3-6 topic tags from the taxonomy below.

STRICT RULES:
- Only assign a tag if the document CENTERS on that topic as a MAIN THEME — the topic must be a core subject the author is teaching, not a passing reference
- A single sentence or brief mention does NOT qualify. The topic must be developed across multiple paragraphs or be a clear structural focus of the document
- Ask yourself: 'Is this topic one of the 3-6 things this document is primarily ABOUT?' If no, do not assign it
- Prefer fewer, highly accurate tags over more loosely related ones
- 3-4 tags is ideal for a focused document. Only use 5-6 if the document genuinely covers that many distinct themes in depth
- Never assign a tag just because a keyword from the tag appears in the text
- You MUST only return tags from the exact list below. Do not create new tags. Do not modify tag names. Copy them exactly as written.

Return JSON only: {{"topic_tags": ["tag1", "tag2", ...]}}

TAXONOMY (use ONLY these exact tags):
{TAXONOMY_LIST}"""

GROQ_API_KEY      = os.environ["GROQ_API_KEY"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_SERVICE_KEY"]

EMBEDDING_MODEL  = "text-embedding-3-small"
EMBEDDING_DIM    = 1536

# ── Clients ───────────────────────────────────────────────────────────────────

groq_client      = Groq(api_key=GROQ_API_KEY)
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

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = (response.choices[0].message.content or "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON if LLM added any surrounding text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM returned non-JSON metadata: {raw}")

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


def insert_document(metadata: dict, file_path: str, is_copyrighted: bool = False, url=None, bible_refs=None) -> str:
    """Insert a document row and return its UUID."""
    doc_id = str(uuid.uuid4())
    st = metadata.get("source_type", "")
    if st == "sermon":
        source_kind = "sermon_transcript"
        citation_mode = "citable"
    elif st == "background":
        source_kind = "background_note"
        citation_mode = "silent_context"
    else:
        source_kind = "unknown"
        citation_mode = "silent_context"
    row = {
        "id":          doc_id,
        "title":       metadata.get("title"),
        "author":      metadata.get("author"),
        "year":        metadata.get("year"),
        "issue":       metadata.get("issue"),
        "source_name": metadata.get("source_name"),
        "source_type": st,
        "source_kind": source_kind,
        "citation_mode": citation_mode,
        "source":      metadata.get("source_name"),  # mirrors source_name
        "topic_tags":  metadata.get("topic_tags", []),
        "bible_references": bible_refs or [],
        "file_path":   file_path,
        "is_copyrighted": is_copyrighted,
    }
    if url:
        row["url"] = url
    try:
        supabase.table("documents").insert(row).execute()
    except Exception:
        # url/bible_references columns may not exist yet — retry without them
        row.pop("url", None)
        row.pop("bible_references", None)
        supabase.table("documents").insert(row).execute()
    return doc_id


def insert_chunks(doc_id: str, chunks: list[str], author: str = None, year: int = None, source_hash: str = None):
    """Embed and insert all chunks for a document."""
    for idx, text in enumerate(chunks):
        print(f"  Embedding chunk {idx + 1}/{len(chunks)}...")
        prefix = f"Author: {author} | Year: {year} | "
        embedding = embed_text(prefix + text)

        supabase.table("chunks").insert({
            "id":          str(uuid.uuid4()),
            "document_id": doc_id,
            "content":     text,
            "embedding":   embedding,
            "chunk_index": idx,
            "page_number": 0,
            "source_hash": source_hash,
        }).execute()

# ── Topic Tagging ────────────────────────────────────────────────────────────

def _parse_tag_json(raw):
    """Parse JSON from Groq response, handling code fences and trailing text."""
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    obj_match = re.search(r"\{[\s\S]*?\}", json_str)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("No valid JSON found", json_str, 0)


def _call_groq_tags(content):
    """Call Groq for topic tagging and return raw response text."""
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=512,
        messages=[
            {"role": "system", "content": TAG_SYSTEM_PROMPT},
            {"role": "user", "content": f"DOCUMENT:\n{content}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def tag_document(doc_id, chunks):
    """Assign validated topic tags to a document from its chunk content.
    Non-fatal — returns the tag list or empty list on failure."""
    content = "\n\n".join(chunks)[:MAX_TAG_CHARS]

    raw = ""
    try:
        raw = _call_groq_tags(content)
        result = _parse_tag_json(raw)
        tags = result.get("topic_tags", [])
    except Exception as e:
        print(f"  Tagging failed: {e}")
        if raw:
            print(f"  Raw response: {raw[:500]}")
        return []

    valid_tags = [t for t in tags if t in VALID_TAGS]
    invalid_tags = [t for t in tags if t not in VALID_TAGS]
    if invalid_tags:
        print(f"  Removed invalid tags: {invalid_tags}")

    # Retry once if fewer than 2 valid tags
    if len(valid_tags) < 2:
        print(f"  Only {len(valid_tags)} valid tag(s), retrying...")
        try:
            raw = _call_groq_tags(content)
            result = _parse_tag_json(raw)
            retry_tags = result.get("topic_tags", [])
            retry_valid = [t for t in retry_tags if t in VALID_TAGS]
            if len(retry_valid) > len(valid_tags):
                valid_tags = retry_valid
        except Exception as e:
            print(f"  Retry failed: {e}")

    # Cap at 6 tags
    valid_tags = valid_tags[:6]

    if valid_tags:
        try:
            supabase.table("documents").update({"topic_tags": valid_tags}).eq("id", doc_id).execute()
        except Exception as e:
            print(f"  Failed to update topic_tags: {e}")
            return []

    return valid_tags


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
    print("Detecting metadata via Groq...")
    metadata = extract_metadata(pages[0], file_path.name)

    # Override metadata with parsed .txt headers if available
    if txt_headers:
        if txt_headers.get("SPEAKER"):
            metadata["author"] = txt_headers["SPEAKER"]
        if txt_headers.get("URL"):
            metadata["_url"] = txt_headers["URL"]
        elif txt_headers.get("SOURCE_URL"):
            metadata["_url"] = txt_headers["SOURCE_URL"]
        if txt_headers.get("TITLE"):
            metadata["title"] = txt_headers["TITLE"]
        if txt_headers.get("SOURCE_TYPE"):
            metadata["source_type"] = txt_headers["SOURCE_TYPE"].lower()

    print(f"  Title:   {metadata.get('title')}")
    print(f"  Author:  {metadata.get('author')}")
    print(f"  Year:    {metadata.get('year')}")
    print(f"  Source:  {metadata.get('source_name')}")
    print(f"  Tags:    {metadata.get('topic_tags')}")

    # 3. Chunk by token
    print("Chunking...")
    content = "\n\n".join(p for p in pages if p.strip())
    chunks = chunk_text(content)
    print(f"  {len(chunks)} chunks created")

    if dry_run:
        author = metadata.get("author")
        year = metadata.get("year")
        prefix = f"Author: {author} | Year: {year} | "
        preview = chunks[:3]
        print(f"\n  [DRY RUN] Previewing first {len(preview)} of {len(chunks)} chunks:\n")
        for idx, text in enumerate(preview):
            tokens = token_len(text)
            print(f"  ── Chunk {idx + 1} | {tokens} tokens ──")
            print(f"  Embed prefix: {prefix}")
            print(f"  Content: {text[:300]}{'...' if len(text) > 300 else ''}")
            print()
        print("  [DRY RUN] No data written to Supabase.")
        return "processed"

    # 4. Extract Bible references from chunk content (non-fatal)
    print("Extracting Bible references...")
    bible_refs = extract_bible_references(content)
    if bible_refs:
        preview = ", ".join(bible_refs[:5]) + (f" ... (+{len(bible_refs) - 5})" if len(bible_refs) > 5 else "")
        print(f"  {len(bible_refs)} reference(s): {preview}")
    else:
        print("  No Bible references found")

    # 5. Insert document row
    source_url = metadata.get("_url") or (txt_headers.get("SOURCE_URL") if txt_headers else None)
    print("Inserting document record...")
    doc_id = insert_document(
        metadata,
        str(file_path),
        is_copyrighted=is_copyrighted,
        url=source_url,
        bible_refs=bible_refs,
    )
    print(f"  Document ID: {doc_id}")

    # 5. Embed + insert chunks
    print(f"Embedding and inserting {len(chunks)} chunks...")
    insert_chunks(doc_id, chunks, author=metadata.get("author"), year=metadata.get("year"), source_hash=source_hash)

    # 6. Tag document from chunk content
    print("Tagging document...")
    assigned_tags = tag_document(doc_id, chunks)
    if assigned_tags:
        print(f"  Tags: {assigned_tags}")
    else:
        print("  No valid tags assigned")

    print(f"Done: {file_path.name}")
    return "processed"


def main():
    dry_run = "--dry-run" in sys.argv

    # Scan sources/documents/ and sources/youtube/cleaned/
    scan_dirs = [
        DOCS_FOLDER / "documents",
        DOCS_FOLDER / "youtube" / "cleaned",
    ]

    files: list[Path] = []
    for folder in scan_dirs:
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(f)

    if not files:
        print(f"No supported files found in {scan_dirs}")
        return

    if dry_run:
        print(f"[DRY RUN] Found {len(files)} file(s) to process")
    else:
        print(f"Found {len(files)} file(s) to process")

    def _is_copyrighted(path: Path) -> bool:
        s = str(path)
        if "sources/youtube/" in s or "sources/magazine/" in s:
            return True
        return False

    ingested_dir = DOCS_FOLDER / "youtube" / "ingested"

    processed = skipped = failed = 0
    for file_path in files:
        is_copyrighted = _is_copyrighted(file_path)
        result = ingest_file(file_path, dry_run=dry_run, is_copyrighted=is_copyrighted)
        if result == "processed":
            processed += 1
            # Move successfully ingested YouTube transcripts to ingested/
            if not dry_run and "sources/youtube/cleaned" in str(file_path):
                ingested_dir.mkdir(parents=True, exist_ok=True)
                dest = ingested_dir / file_path.name
                shutil.move(str(file_path), str(dest))
                print(f"  Moved to: {dest}")
        elif result == "skipped":
            skipped += 1
        else:
            failed += 1

    print(f"\n{'='*60}")
    print(f"Done. {processed} processed, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
