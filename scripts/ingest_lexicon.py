#!/usr/bin/env python3
"""
New Wine STEPBible Lexicon Ingestion Script
Parses TBESG, TBESH, and TFLSJ TSV files from sources/stepbible/,
embeds each lexical entry, and inserts into Supabase.

Converted (#12) to route through shared_ingest.ingest_document() -- resolve/
insert/chunk/embed/propositions is the shared writer's job now; this script
keeps only what's genuinely lexicon-specific: TSV parsing, one-entry-one-
chunk formatting (via a chunk_fn override -- a lexicon entry is not split
the way a sermon is), and truncation of unusually long entries.

Three edge behaviors this conversion preserves (see rhemata-status.md and
PLAN.md #12 for the full record):
  1. One-entry-one-chunk -- `_lexicon_chunk_fn` ignores the writer's default
     token-chunker entirely and returns the pre-formatted per-entry list.
  2. Paraphrase stays off -- STEPBible is public_domain, so the writer's
     existing propositions gate already skips it (`skipped_licensed`);
     nothing lexicon-specific was needed for this.
  3. Append, not rewrite -- resuming a partially-loaded lexicon file now
     goes through the writer's `on_existing="reuse"` continued-numbering
     append (built and proven in the session before this one), not a
     bespoke count-and-resume loop. The old re-chunk-from-0 bug this was
     built to fix was confirmed on this exact script.

Resumable across re-runs (the writer's reuse/append mechanism); `--delete`
now routes through the writer's `on_existing="delete_and_reingest"` atomic
swap instead of a separate, non-atomic pre-delete step.
"""

import os
import re
import sys
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse, unquote

import tiktoken
from supabase import create_client
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
import shared_ingest

# ── Config ────────────────────────────────────────────────────────────────────

LEXICON_DIR = PROJECT_ROOT / "sources" / "stepbible"

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
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

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# File configs: (filename, document title)
FILE_CONFIGS = [
    (
        "TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt",
        "STEPBible Greek Lexicon (TBESG)",
    ),
    (
        "TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt",
        "STEPBible Hebrew Lexicon (TBESH)",
    ),
    (
        "TFLSJ  0-5624 - Translators Formatted full LSJ Bible lexicon - STEPBible.org CC BY.txt",
        "LSJ Greek Lexicon (TFLSJ) — Entries 0-5624",
    ),
    (
        "TFLSJ extra - Translators Formatted full LSJ Bible lexicon - STEPBible.org CC BY.txt",
        "LSJ Greek Lexicon (TFLSJ) — Extended Entries",
    ),
]

MAX_EMBED_TOKENS = 8000
_enc = tiktoken.get_encoding("cl100k_base")

STRONGS_RE = re.compile(r'^[GH]\d+$')
HTML_TAG_RE = re.compile(r'<[^>]+>')


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    cleaned = HTML_TAG_RE.sub(' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def truncate_for_embedding(text: str) -> str:
    """Truncate text to MAX_EMBED_TOKENS tokens if it exceeds the limit."""
    tokens = _enc.encode(text)
    if len(tokens) <= MAX_EMBED_TOKENS:
        return text
    truncated = _enc.decode(tokens[:MAX_EMBED_TOKENS])
    return truncated + " [truncated]"


def find_header_and_data(lines: List[str]) -> Tuple[Optional[Dict[str, int]], int]:
    """Find the TSV header row and return (column_map, data_start_line_index).
    column_map maps lowercase normalized column names to indices."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if '\t' not in stripped:
            continue
        fields = stripped.split('\t')
        first_lower = fields[0].strip().lower().rstrip('#')
        has_estrong = first_lower == 'estrong'
        has_gloss = any('gloss' in f.strip().lower() for f in fields)
        if has_estrong and has_gloss:
            col_map = {}  # type: Dict[str, int]
            for idx, f in enumerate(fields):
                name = f.strip().lower()
                if name.startswith('estrong'):
                    col_map['estrong'] = idx
                elif name == 'greek' or name == 'hebrew':
                    col_map['lemma'] = idx
                elif name == 'transliteration':
                    col_map['transliteration'] = idx
                elif name == 'gloss':
                    col_map['gloss'] = idx
                elif name == 'morph':
                    col_map['morph'] = idx
                elif idx == len(fields) - 1:
                    col_map['meaning'] = idx
            data_start = i + 1
            while data_start < len(lines):
                l = lines[data_start].strip()
                if l.startswith('===') or l == '':
                    data_start += 1
                else:
                    break
            return col_map, data_start
    return None, 0


def parse_file(filepath: Path) -> List[Dict[str, str]]:
    """Parse a STEPBible lexicon file and return list of entry dicts."""
    text = filepath.read_text(encoding='utf-8')
    lines = text.split('\n')

    col_map, data_start = find_header_and_data(lines)
    if col_map is None:
        print(f"  WARNING: Could not find header row in {filepath.name}")
        return []

    print(f"  Header columns: {col_map}")
    print(f"  Data starts at line {data_start + 1}")

    entries = []  # type: List[Dict[str, str]]
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        fields = stripped.split('\t')

        estrong_idx = col_map.get('estrong')
        gloss_idx = col_map.get('gloss')
        if estrong_idx is None or gloss_idx is None:
            continue
        if estrong_idx >= len(fields) or gloss_idx >= len(fields):
            continue

        strongs = fields[estrong_idx].strip()
        gloss = fields[gloss_idx].strip()

        if not STRONGS_RE.match(strongs) or not gloss:
            continue

        entry = {'strongs': strongs, 'gloss': gloss}

        lemma_idx = col_map.get('lemma')
        if lemma_idx is not None and lemma_idx < len(fields):
            entry['lemma'] = fields[lemma_idx].strip()

        translit_idx = col_map.get('transliteration')
        if translit_idx is not None and translit_idx < len(fields):
            entry['transliteration'] = fields[translit_idx].strip()

        meaning_idx = col_map.get('meaning')
        if meaning_idx is not None and meaning_idx < len(fields):
            raw_meaning_text = fields[meaning_idx].strip()
            if raw_meaning_text:
                entry['raw_meaning'] = raw_meaning_text
                entry['meaning'] = strip_html(raw_meaning_text)

        entries.append(entry)

    return entries


BOLD_RE = re.compile(r'<b>([^<]+)</b>')


def extract_bold_meanings(html_meaning: str) -> str:
    """Extract bolded sub-definitions from Abbott-Smith HTML meaning field.
    Returns a clean comma-separated string like 'a word, a saying, speech, doctrine'."""
    bolds = BOLD_RE.findall(html_meaning)
    # First bold is usually the lemma itself — skip it
    if bolds:
        bolds = bolds[1:]
    # Filter out very short or unhelpful entries
    cleaned = []
    for b in bolds:
        b = b.strip()
        if len(b) < 2 or b in ('id.', 'al.', 'cf.'):
            continue
        cleaned.append(b)
    return ', '.join(cleaned)


def format_chunk_content(entry: Dict[str, str], brief: bool = False) -> str:
    """Format a lexicon entry into chunk content text.
    If brief=True, use only gloss + extracted bold sub-meanings (no raw Abbott-Smith)."""
    strongs = entry['strongs']
    translit = entry.get('transliteration', '')
    lemma = entry.get('lemma', '')
    gloss = entry['gloss']
    meaning = entry.get('meaning', '')
    raw_meaning = entry.get('raw_meaning', '')

    parts = []
    if translit and lemma:
        parts.append(f"Strong's {strongs} ({translit} / {lemma}): {gloss}.")
    elif translit:
        parts.append(f"Strong's {strongs} ({translit}): {gloss}.")
    elif lemma:
        parts.append(f"Strong's {strongs} ({lemma}): {gloss}.")
    else:
        parts.append(f"Strong's {strongs}: {gloss}.")

    if brief and raw_meaning:
        # Extract clean sub-definitions from the HTML
        bold_meanings = extract_bold_meanings(raw_meaning)
        if bold_meanings:
            parts.append(bold_meanings)
    elif meaning:
        parts.append(meaning)

    return ' '.join(parts)


def _find_existing_by_title(title: str) -> Optional[str]:
    """Title-keyed lookup, same key ingest_lexicon.py has always used --
    handed to the shared writer's find_existing_fn hook instead of branching
    on it locally."""
    result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def ingest_file(filename: str, title: str, max_entries: Optional[int] = None,
                 brief: bool = False, delete: bool = False) -> Dict[str, int]:
    """Ingest a single lexicon file through the shared writer. Returns a
    stats dict compatible with main()'s aggregation.
    If brief=True, store only gloss + extracted bold sub-meanings (for TBESG).
    If delete=True, atomically swap out any existing document (REDO) instead
    of appending to it.
    """
    filepath = LEXICON_DIR / filename
    stats = {"parsed": 0, "inserted": 0, "skipped": 0}

    if not filepath.exists():
        print(f"\n  WARNING: File not found, skipping: {filename}")
        return stats

    print(f"\n{'='*60}")
    print(f"Processing: {filename}")
    print(f"  Title: {title}")
    if brief:
        print("  Mode: BRIEF (gloss + bold sub-meanings only)")
    print('='*60)

    entries = parse_file(filepath)
    if max_entries is not None:
        entries = entries[:max_entries]
    stats["parsed"] = len(entries)

    if not entries:
        print("  No entries parsed — skipping")
        return stats

    print(f"  {len(entries)} entries parsed")

    # One-entry-one-chunk (edge behavior #1): each entry is formatted into
    # exactly one chunk's worth of content, then truncated if unusually
    # long -- both the STORED content and the EMBEDDED text are the same
    # truncated string, matching this script's behavior before conversion.
    chunk_texts = [
        truncate_for_embedding(format_chunk_content(entry, brief=brief))
        for entry in entries
    ]
    # full_text is what the writer stores as documents.full_text and would
    # feed to the paraphrase step if the gate ever passed (it doesn't --
    # STEPBible is public_domain, edge behavior #2). Each entry is
    # independently short; a full lexicon file is thousands of them, so
    # this join is NOT a coherent single "document" in the sense
    # propositions.py's extraction prompt assumes -- unchanged concern from
    # before conversion, now just documented once instead of duplicated.
    full_text = "\n\n".join(chunk_texts)

    def _lexicon_chunk_fn(_body_text: str) -> List[str]:
        # Ignores the writer's default token-chunker and the body_text
        # argument entirely -- returns the pre-formatted, one-per-entry
        # list captured by closure. This is edge behavior #1: a lexicon
        # entry is not split the way a sermon is.
        return chunk_texts

    existing_id = _find_existing_by_title(title)
    on_existing = "delete_and_reingest" if (delete and existing_id) else "reuse"

    result = shared_ingest.ingest_document(
        db=supabase,
        db_params=DB_PARAMS,
        title=title,
        body_text=full_text,
        filename=filename,
        author="STEPBible / Tyndale House",
        source_name="STEPBible",
        source_type="background",
        source_kind="lexicon",
        citation_mode="silent_context",
        is_copyrighted=False,
        topic_tags=[],
        bible_references=[],
        # Title-keyed, not url/file_path -- skip_dedup=True makes that
        # explicit instead of relying on an accidental no-op.
        skip_dedup=True,
        find_existing_fn=lambda: existing_id,
        on_existing=on_existing,
        chunk_fn=_lexicon_chunk_fn,
    )

    if result["status"] == "processed":
        total_now = len(result["chunks"])
        print(f"  OK: document now has {total_now} chunk(s) total")
        stats["inserted"] = stats["parsed"]
    elif result["status"] == "skipped" and result["reason"] == "already_complete":
        print(f"  All {len(chunk_texts)} entries already present — nothing to append")
        stats["inserted"] = stats["parsed"]
    elif result["status"] == "skipped":
        print(f"  SKIPPED: {result['reason']}")
        stats["skipped"] = stats["parsed"]
    else:
        print(f"  FAILED: {result['reason']}")
        stats["skipped"] = stats["parsed"]

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def print_resume_status():
    """Print current chunk counts in Supabase for each lexicon document."""
    print("\nCurrent Supabase chunk counts:")
    for _, title in FILE_CONFIGS:
        result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
        if result.data:
            doc_id = result.data[0]["id"]
            count_result = supabase.table("chunks").select("id", count="exact").eq("document_id", doc_id).execute()
            count = count_result.count if count_result.count is not None else 0
            print(f"  {title}: {count} chunks (doc {doc_id[:8]}...)")
        else:
            print(f"  {title}: not yet created")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="New Wine STEPBible Lexicon Ingestion")
    parser.add_argument("--test", action="store_true", help="Limit to 50 entries per file")
    parser.add_argument("--lexicon", type=str, default=None,
                        help="Run a single lexicon: TBESG, TBESH, or TFLSJ")
    parser.add_argument("--delete", action="store_true",
                        help="Atomically swap out any existing document + chunks (REDO) instead of appending")
    parser.add_argument("--sample", type=int, default=0,
                        help="Print N sample chunks after parsing (before ingesting)")
    args = parser.parse_args()

    max_entries = 50 if args.test else None

    # Map --lexicon shorthand to FILE_CONFIGS entries
    LEXICON_MAP = {
        "TBESG": [FILE_CONFIGS[0]],
        "TBESH": [FILE_CONFIGS[1]],
        "TFLSJ": [FILE_CONFIGS[2], FILE_CONFIGS[3]],
    }

    if args.lexicon:
        key = args.lexicon.upper()
        if key not in LEXICON_MAP:
            print(f"Unknown lexicon: {args.lexicon}. Choose from: {', '.join(LEXICON_MAP.keys())}")
            sys.exit(1)
        configs = LEXICON_MAP[key]
        print(f"Single lexicon mode: {key}")
    else:
        configs = FILE_CONFIGS

    print("New Wine STEPBible Lexicon Ingestion")
    if args.test:
        print("TEST MODE: limited to 50 entries per file")
    print("="*60)

    print_resume_status()

    total_stats = {"parsed": 0, "inserted": 0, "skipped": 0}

    for filename, title in configs:
        brief = "TBESG" in title

        if args.sample > 0:
            # Parse and print samples, then continue to ingest
            filepath = LEXICON_DIR / filename
            entries = parse_file(filepath)
            if max_entries is not None:
                entries = entries[:max_entries]
            print(f"\n  Sample chunks ({args.sample}):")
            for i, entry in enumerate(entries[:args.sample]):
                chunk = format_chunk_content(entry, brief=brief)
                print(f"  [{i}] {chunk[:200]}")
            print()

        stats = ingest_file(filename, title, max_entries=max_entries, brief=brief, delete=args.delete)
        for k in total_stats:
            total_stats[k] += stats[k]

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"  Total parsed:   {total_stats['parsed']}")
    print(f"  Total inserted: {total_stats['inserted']}")
    print(f"  Total skipped:  {total_stats['skipped']}")
    print('='*60)


if __name__ == "__main__":
    main()
