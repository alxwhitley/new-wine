#!/usr/bin/env python3
"""
Rhemata Magazine Ingestion Script (Phase 2)
Reads clean merged txt files from corpus/copyrighted/ and corpus/open/,
ingests them into Supabase: documents table, chunks table, articles table.
"""

import os
import re
import sys
import json
import uuid
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

import openai
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path("/Users/alexwhitley/Desktop/rhemata/backend")))
from app.services.chunker import chunk_text

# ── CONFIGURATION ────────────────────────────────────────────────────────────

BASE_DIR = Path("/Users/alexwhitley/Desktop/rhemata")
INPUT_COPYRIGHTED = BASE_DIR / "corpus" / "copyrighted"
INPUT_OPEN = BASE_DIR / "corpus" / "open"
INGESTION_LOG_PATH = BASE_DIR / "pipeline" / "ingestion_log.json"
QA_LOG_PATH = BASE_DIR / "pipeline" / "qa_log.json"
NEEDS_REVIEW_DIR = BASE_DIR / "pipeline" / "needs_review"
ENV_PATH = BASE_DIR / "backend" / "app" / ".env"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# ── ENVIRONMENT ──────────────────────────────────────────────────────────────

load_dotenv(ENV_PATH)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# ── CLIENTS ──────────────────────────────────────────────────────────────────

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


# ── MIGRATION ────────────────────────────────────────────────────────────────

ARTICLES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
  title text NOT NULL,
  author text,
  magazine text,
  issue text,
  date text,
  year int,
  month int,
  categories text[],
  keywords text[],
  scripture_refs text[],
  people_mentioned text[],
  summary text,
  word_count int,
  source_type text DEFAULT 'magazine',
  is_copyrighted bool DEFAULT true,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS articles_categories_idx
  ON articles USING GIN(categories);
CREATE INDEX IF NOT EXISTS articles_keywords_idx
  ON articles USING GIN(keywords);
CREATE INDEX IF NOT EXISTS articles_scripture_idx
  ON articles USING GIN(scripture_refs);
CREATE INDEX IF NOT EXISTS articles_people_idx
  ON articles USING GIN(people_mentioned);
CREATE INDEX IF NOT EXISTS articles_year_idx
  ON articles(year);
CREATE INDEX IF NOT EXISTS articles_fts_idx
  ON articles USING GIN(
    to_tsvector('english',
      coalesce(title,'') || ' ' ||
      coalesce(author,'') || ' ' ||
      coalesce(summary,'')
    )
  );
"""


def ensure_articles_table() -> None:
    """Verify articles table exists. If not, print migration SQL and exit."""
    try:
        sb.table("articles").select("id").limit(1).execute()
        print("  articles table exists")
    except Exception:
        print("  ERROR: articles table does not exist.")
        print("  Run the ARTICLES_TABLE_SQL migration in Supabase SQL Editor first.")
        print("  (See the SQL block at the top of this script.)")
        sys.exit(1)


# ── INGESTION LOG ────────────────────────────────────────────────────────────

def load_ingestion_log() -> Dict:
    """Load existing ingestion log or return empty dict."""
    if INGESTION_LOG_PATH.exists():
        with open(INGESTION_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_ingestion_log(log: Dict) -> None:
    """Save ingestion log to disk."""
    with open(INGESTION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def is_ingested(log: Dict, filename: str, title: str) -> bool:
    """Check if an article has already been ingested."""
    file_log = log.get(filename, {})
    entry = file_log.get(title, {})
    return entry.get("status") in ("ingested", "partial")


def load_qa_log() -> List[Dict]:
    """Load existing QA log or return empty list."""
    if QA_LOG_PATH.exists():
        with open(QA_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_qa_log(qa_log: List[Dict]) -> None:
    """Save QA log to disk."""
    with open(QA_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(qa_log, f, indent=2)


# ── PARSING ──────────────────────────────────────────────────────────────────

class ArticleData:
    def __init__(self):
        self.title = ""          # type: str
        self.author = ""         # type: str
        self.magazine = ""       # type: str
        self.issue = ""          # type: str
        self.date = ""           # type: str
        self.categories = []     # type: List[str]
        self.category_reasoning = ""  # type: str
        self.summary = ""        # type: str
        self.keywords = []       # type: List[str]
        self.scripture_refs = [] # type: List[str]
        self.people_mentioned = []  # type: List[str]
        self.content = ""        # type: str
        self.books_mentioned = ""  # type: str


def parse_field(block: str, field_name: str, next_fields: List[str]) -> str:
    """Extract a single-line or multi-line field from an article block."""
    next_pattern = "|".join(re.escape(f) for f in next_fields)
    pattern = re.compile(
        rf'^{re.escape(field_name)}:\s*(.*?)(?=^(?:{next_pattern}):|\Z)',
        re.MULTILINE | re.DOTALL
    )
    match = pattern.search(block)
    if match:
        return match.group(1).strip()
    return ""


def parse_list_field(value: str) -> List[str]:
    """Parse a comma-separated field into a list, filtering 'None'."""
    if not value or value.strip().lower() == "none":
        return []
    return [item.strip() for item in re.split(r'[,;]', value) if item.strip()]


def parse_issue(issue_str: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse issue string like '02-1974' into (month, year)."""
    match = re.search(r'(\d+)-(\d{4})', issue_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    # Try just year
    match = re.search(r'(\d{4})', issue_str)
    if match:
        return None, int(match.group(1))
    return None, None


def parse_articles(text: str) -> List[ArticleData]:
    """Parse all ARTICLE START...ARTICLE END blocks from a merged file."""
    blocks = re.findall(
        r'ARTICLE START\s*\n(.*?)ARTICLE END',
        text,
        re.DOTALL
    )

    field_order = [
        "TITLE", "AUTHOR", "MAGAZINE", "ISSUE", "DATE",
        "CATEGORIES", "CATEGORY REASONING", "SUMMARY", "KEYWORDS",
        "SCRIPTURE_REFS", "PEOPLE_MENTIONED",
        "CONTENT", "BOOKS MENTIONED"
    ]

    articles = []
    for block in blocks:
        art = ArticleData()
        art.title = parse_field(block, "TITLE", field_order[1:])
        art.author = parse_field(block, "AUTHOR", field_order[2:])
        art.magazine = parse_field(block, "MAGAZINE", field_order[3:])
        art.issue = parse_field(block, "ISSUE", field_order[4:])
        art.date = parse_field(block, "DATE", field_order[5:])

        cats_raw = parse_field(block, "CATEGORIES", field_order[6:])
        art.categories = parse_list_field(cats_raw)

        art.category_reasoning = parse_field(block, "CATEGORY REASONING", field_order[7:])
        art.summary = parse_field(block, "SUMMARY", field_order[8:])

        kw_raw = parse_field(block, "KEYWORDS", field_order[9:])
        art.keywords = parse_list_field(kw_raw)

        sr_raw = parse_field(block, "SCRIPTURE_REFS", field_order[10:])
        art.scripture_refs = parse_list_field(sr_raw)

        pm_raw = parse_field(block, "PEOPLE_MENTIONED", field_order[11:])
        art.people_mentioned = parse_list_field(pm_raw)

        # CONTENT: everything between CONTENT:\n and \nBOOKS MENTIONED:
        content_match = re.search(
            r'CONTENT:\s*\n(.*?)(?=\nBOOKS MENTIONED:|\Z)',
            block,
            re.DOTALL
        )
        art.content = content_match.group(1).strip() if content_match else ""

        art.books_mentioned = parse_field(block, "BOOKS MENTIONED", [])

        articles.append(art)

    return articles


def primary_author(author_str: str) -> str:
    """Extract primary author from potentially comma-separated string."""
    if not author_str:
        return ""
    # Take first name if comma-separated
    parts = author_str.split(",")
    return parts[0].strip()


# ── EMBEDDING ────────────────────────────────────────────────────────────────

def embed_text(text: str) -> Optional[List[float]]:
    """Generate embedding with one retry on failure."""
    for attempt in range(2):
        try:
            response = openai_client.embeddings.create(
                input=text,
                model=EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            if attempt == 0:
                print(f"    Embedding failed, retrying: {e}")
                time.sleep(1)
            else:
                print(f"    Embedding failed permanently: {e}")
                return None
    return None


# ── SUPABASE INSERTS ─────────────────────────────────────────────────────────

def insert_document(art: ArticleData, is_copyrighted: bool) -> Optional[str]:
    """Insert a document row and return its UUID."""
    doc_id = str(uuid.uuid4())
    author = primary_author(art.author)
    month, year = parse_issue(art.issue)

    row = {
        "id": doc_id,
        "title": art.title,
        "author": author,
        "source": art.magazine,
        "source_name": f"New Wine Magazine Issue {art.issue}" if art.magazine else None,
        "source_type": "magazine_article",
        "source_kind": "magazine_article",
        "citation_mode": "citable",
        "year": year,
        "issue": art.issue,
        "topic_tags": art.categories,
        "file_path": None,
        "is_copyrighted": is_copyrighted,
    }
    try:
        sb.table("documents").insert(row).execute()
        return doc_id
    except Exception as e:
        print(f"    ERROR inserting document: {e}")
        return None


def insert_chunks(doc_id: str, content: str, art: ArticleData) -> int:
    """Chunk content, embed, and insert. Returns number of chunks inserted."""
    prefix = f"[{art.magazine} | {art.date} | {art.title} by {primary_author(art.author)}]\n\n"

    chunks = chunk_text(content)
    inserted = 0

    for idx, chunk_content in enumerate(chunks):
        prefixed = prefix + chunk_content
        embedding = embed_text(prefixed)
        if embedding is None:
            print(f"    Skipping chunk {idx + 1} — embedding failed")
            continue

        try:
            sb.table("chunks").insert({
                "id": str(uuid.uuid4()),
                "document_id": doc_id,
                "content": prefixed,
                "embedding": embedding,
                "chunk_index": idx,
                "page_number": 0,
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"    ERROR inserting chunk {idx + 1}: {e}")

    return inserted


def insert_article(doc_id: str, art: ArticleData, is_copyrighted: bool) -> bool:
    """Insert into articles table. Returns True on success."""
    author = primary_author(art.author)
    month, year = parse_issue(art.issue)

    row = {
        "document_id": doc_id,
        "title": art.title,
        "author": author,
        "magazine": art.magazine,
        "issue": art.issue,
        "date": art.date,
        "year": year,
        "month": month,
        "categories": art.categories,
        "keywords": art.keywords,
        "scripture_refs": art.scripture_refs,
        "people_mentioned": art.people_mentioned,
        "summary": art.summary,
        "word_count": len(art.content.split()),
        "source_type": "magazine_article",
        "is_copyrighted": is_copyrighted,
    }
    try:
        sb.table("articles").insert(row).execute()
        return True
    except Exception as e:
        print(f"    ERROR inserting article row: {e}")
        return False


# ── PROCESS SINGLE FILE ─────────────────────────────────────────────────────

def process_file(
    txt_path: Path,
    is_copyrighted: bool,
    log: Dict
) -> None:
    """Process a single merged txt file."""
    filename = txt_path.name
    print(f"\n{'='*60}")
    print(f"Processing: {filename} ({'copyrighted' if is_copyrighted else 'open'})")
    print(f"{'='*60}")

    try:
        raw_text = txt_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ERROR reading file: {e}")
        return

    articles = parse_articles(raw_text)
    if not articles:
        print(f"  No articles found — skipping")
        return

    print(f"  {len(articles)} articles found")

    if filename not in log:
        log[filename] = {}

    for art in articles:
        if not art.title or not art.content:
            print(f"  Skipping empty article")
            continue

        if is_ingested(log, filename, art.title):
            print(f"  [{filename}] → {art.title} → already ingested, skipping")
            continue

        # QA gate
        word_count = len(art.content.split())
        has_title = bool(art.title and art.title.strip())
        has_author = bool(art.author and art.author.strip())
        alpha_ratio = sum(c.isalpha() for c in art.content) / max(len(art.content), 1)
        is_truncated = '[TRUNCATED' in art.content or '[CONTINUED' in art.content
        paragraph_count = len([p for p in art.content.split('\n\n') if p.strip()])

        qa_flags = []
        if word_count < 150:
            qa_flags.append('low_word_count')
        if not has_title:
            qa_flags.append('missing_title')
        if not has_author:
            qa_flags.append('missing_author')
        if alpha_ratio < 0.70:
            qa_flags.append('low_alpha_ratio')
        if is_truncated:
            qa_flags.append('truncated')
        if paragraph_count < 2:
            qa_flags.append('low_paragraph_count')

        qa_status = 'needs_review' if qa_flags else 'ok'

        if qa_status == 'needs_review':
            print(f"  [{filename}] → {art.title} → QA FAILED: {qa_flags}")
            NEEDS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
            issue_part = art.issue.replace('-', '_') if art.issue else 'unknown'
            title_slug = re.sub(r'[^\w\s]', '', art.title.lower())
            title_slug = re.sub(r'\s+', '_', title_slug.strip())[:60]
            review_path = NEEDS_REVIEW_DIR / f"{issue_part}_{title_slug}.txt"
            review_path.write_text(art.content, encoding="utf-8")
            qa_log = load_qa_log()
            qa_log.append({
                "title": art.title,
                "author": art.author,
                "issue": art.issue,
                "word_count": word_count,
                "alpha_ratio": round(alpha_ratio, 3),
                "paragraph_count": paragraph_count,
                "is_truncated": is_truncated,
                "qa_flags": qa_flags,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            save_qa_log(qa_log)
            log[filename][art.title] = {
                "status": "qa_failed",
                "qa_flags": qa_flags,
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_ingestion_log(log)
            continue

        print(f"  [{filename}] → {art.title}", end="")

        # Step 1: Insert document
        doc_id = insert_document(art, is_copyrighted)
        if doc_id is None:
            print(f" → FAILED (document insert)")
            log[filename][art.title] = {
                "status": "failed",
                "reason": "document insert failed",
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_ingestion_log(log)
            continue

        print(f" → doc created", end="")

        # Step 2: Chunk and embed
        chunk_count = insert_chunks(doc_id, art.content, art)
        print(f" → {chunk_count} chunks", end="")

        # Step 3: Insert article row
        article_ok = insert_article(doc_id, art, is_copyrighted)
        if article_ok:
            print(f" → articles table → done")
            log[filename][art.title] = {
                "status": "ingested",
                "document_id": doc_id,
                "chunks": chunk_count,
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            print(f" → articles table FAILED (partial)")
            log[filename][art.title] = {
                "status": "partial",
                "document_id": doc_id,
                "chunks": chunk_count,
                "reason": "articles table insert failed",
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        # Save after every article
        save_ingestion_log(log)


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    """Process all txt files in corpus directories."""
    print("Rhemata Magazine Ingestion")
    print("=" * 60)

    # Ensure articles table exists
    ensure_articles_table()

    # Load ingestion log
    log = load_ingestion_log()

    # Collect files
    files = []  # type: List[Tuple[Path, bool]]

    # Copyrighted txt files
    if INPUT_COPYRIGHTED.is_dir():
        for f in sorted(INPUT_COPYRIGHTED.glob("*.txt")):
            files.append((f, True))

    # Open txt files
    if INPUT_OPEN.is_dir():
        for f in sorted(INPUT_OPEN.glob("*.txt")):
            files.append((f, False))

    if not files:
        print("No .txt files found")
        return

    print(f"Found {len(files)} .txt file(s)")

    for txt_path, is_copyrighted in files:
        process_file(txt_path, is_copyrighted, log)

    print(f"\n{'='*60}")
    print("Ingestion complete.")


if __name__ == "__main__":
    run()
