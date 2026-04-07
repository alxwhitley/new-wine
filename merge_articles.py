#!/usr/bin/env python3
"""
New Wine Magazine Article Merge Script
Reads raw extracted txt files from pipeline/raw_extracted/,
detects and merges split articles caused by batch boundaries,
writes clean merged files to corpus/copyrighted/ or corpus/open/,
and logs what was merged for audit purposes.
"""

import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

# ── CONFIGURATION ────────────────────────────────────────────────────────────

BASE_DIR = Path("/Users/alexwhitley/Desktop/rhemata")
INPUT_DIR = BASE_DIR / "pipeline" / "raw_extracted"
OUTPUT_COPYRIGHTED = BASE_DIR / "corpus" / "copyrighted"
OUTPUT_OPEN = BASE_DIR / "corpus" / "open"
MERGE_LOG_PATH = BASE_DIR / "pipeline" / "merge_log.json"


# ── DATA STRUCTURES ──────────────────────────────────────────────────────────

class Article:
    def __init__(self):
        self.title = ""          # type: str
        self.author = ""         # type: str
        self.magazine = ""       # type: str
        self.issue = ""          # type: str
        self.date = ""           # type: str
        self.categories = ""     # type: str
        self.category_reasoning = ""  # type: str
        self.content = ""        # type: str
        self.books_mentioned = ""  # type: str
        self.truncated = False   # type: bool
        self.raw_block = ""      # type: str


# ── TITLE NORMALIZATION ──────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """Normalize a title for grouping: lowercase, strip punctuation,
    strip leading articles, strip continuation markers."""
    t = title.lower().strip()

    # Strip common section prefixes
    t = re.sub(r'^new wine forum\b[:\s—–-]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^forum\b[:\s—–-]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^bible study\b[:\s—–-]*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^letters to\b[:\s—–-]*', '', t, flags=re.IGNORECASE)

    # Remove continuation markers and parenthetical notes
    t = re.sub(r'\(continued.*?\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(continuation.*?\)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'continued from.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'continuation.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\[continuation.*?\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\[continued.*?\]', '', t, flags=re.IGNORECASE)

    # Remove leading "continuation from page X:" patterns
    t = re.sub(r'^\[?continuation from page \d+:?\s*', '', t, flags=re.IGNORECASE)

    # Remove "— continuation & conclusion" suffixes
    t = re.sub(r'\s*[—–-]\s*(continuation|continued).*$', '', t, flags=re.IGNORECASE)

    # Strip punctuation
    t = re.sub(r'[^\w\s]', '', t)

    # Strip leading articles
    t = re.sub(r'^(the|a|an)\s+', '', t)

    # Collapse whitespace
    t = re.sub(r'\s+', ' ', t).strip()

    return t


STOP_WORDS = {
    "the", "and", "not", "for", "with", "from", "that", "this", "into", "unto",
    "they", "them", "their", "have", "been", "will", "shall", "shalt", "your",
    "our", "its", "all", "are", "was", "were", "but", "also", "when", "then",
    "than", "thus", "such", "each", "very", "more",
}


def _significant_keywords(normalized_title: str) -> List[str]:
    """Extract significant keywords (4+ chars, no stop words) from a normalized title."""
    return [w for w in normalized_title.split() if len(w) >= 4 and w not in STOP_WORDS]


def _stems_match(word_a: str, word_b: str) -> bool:
    """Stemming-lite: true if either word starts with the other (min 4 chars)."""
    if len(word_a) < 4 or len(word_b) < 4:
        return False
    return word_a.startswith(word_b) or word_b.startswith(word_a)


def titles_match_strict(title_a: str, title_b: str) -> bool:
    """Check if two titles match via exact normalized match or 60%+ substring.
    Does NOT use keyword overlap — use for non-continuation matching."""
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)

    if not norm_a or not norm_b:
        return False

    # Condition 1: Exact match after normalization
    if norm_a == norm_b:
        return True

    # Condition 2: One is a 60%+ substring of the other
    shorter, longer = sorted([norm_a, norm_b], key=len)
    if shorter in longer and len(shorter) >= len(longer) * 0.6:
        return True

    return False


def keyword_overlap_count(title_a: str, title_b: str) -> int:
    """Count the number of significant keyword stem-matches between two titles."""
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)
    kw_a = _significant_keywords(norm_a)
    kw_b = _significant_keywords(norm_b)
    count = 0
    used_b = set()  # type: set
    for wa in kw_a:
        for j, wb in enumerate(kw_b):
            if j not in used_b and _stems_match(wa, wb):
                count += 1
                used_b.add(j)
                break
    return count


# ── PARSING ──────────────────────────────────────────────────────────────────

def extract_toc(text: str) -> Optional[str]:
    """Extract TABLE OF CONTENTS block if present."""
    match = re.search(
        r'(TABLE OF CONTENTS.*?END TABLE OF CONTENTS)',
        text,
        re.DOTALL
    )
    return match.group(1).strip() if match else None


def parse_field(block: str, field_name: str, next_fields: List[str]) -> str:
    """Extract a field value from an article block.
    Looks for FIELD_NAME: value, terminated by the next field or end of block."""
    # Build pattern: field name followed by content until next field
    next_pattern = "|".join(re.escape(f) for f in next_fields)
    pattern = re.compile(
        rf'^{re.escape(field_name)}:\s*(.*?)(?=^(?:{next_pattern}):|\Z)',
        re.MULTILINE | re.DOTALL
    )
    match = pattern.search(block)
    if match:
        return match.group(1).strip()
    return ""


def parse_articles(text: str) -> List[Article]:
    """Parse all ARTICLE START...ARTICLE END blocks from text."""
    blocks = re.findall(
        r'ARTICLE START\s*\n(.*?)ARTICLE END',
        text,
        re.DOTALL
    )

    articles = []
    field_order = [
        "TITLE", "AUTHOR", "MAGAZINE", "ISSUE", "DATE",
        "CATEGORIES", "CATEGORY REASONING",
        "CONTENT", "BOOKS MENTIONED"
    ]

    for block in blocks:
        art = Article()
        art.raw_block = block.strip()
        art.title = parse_field(block, "TITLE", field_order[1:])
        art.author = parse_field(block, "AUTHOR", field_order[2:])
        art.magazine = parse_field(block, "MAGAZINE", field_order[3:])
        art.issue = parse_field(block, "ISSUE", field_order[4:])
        art.date = parse_field(block, "DATE", field_order[5:])
        art.categories = parse_field(block, "CATEGORIES", field_order[6:])
        art.category_reasoning = parse_field(block, "CATEGORY REASONING", field_order[7:])

        # CONTENT is special — everything between CONTENT: and BOOKS MENTIONED:
        content_match = re.search(
            r'CONTENT:\s*\n(.*?)(?=\nBOOKS MENTIONED:|\Z)',
            block,
            re.DOTALL
        )
        art.content = content_match.group(1).strip() if content_match else ""

        art.books_mentioned = parse_field(block, "BOOKS MENTIONED", [])

        # Clean continuation markers from content
        art.content = art.content.replace("[CONTINUES IN NEXT BATCH]", "").strip()
        art.content = art.content.replace("[CONTINUED IN NEXT BATCH]", "").strip()

        # Clean embedded batch boundaries from content (when ARTICLE END was missing)
        # Remove: BOOKS IN THIS BATCH: ... ARTICLE START ... CONTENT:\n
        art.content = re.sub(
            r'BOOKS IN THIS BATCH:.*?CONTENT:\s*\n?',
            '\n\n',
            art.content,
            flags=re.DOTALL
        )
        # Also remove standalone ARTICLE START blocks embedded in content
        art.content = re.sub(
            r'ARTICLE START\s*\nTITLE:.*?CONTENT:\s*\n?',
            '\n\n',
            art.content,
            flags=re.DOTALL
        )
        art.content = art.content.strip()

        # Detect truncation marker from extraction
        if "[TRUNCATED - MAX TOKENS HIT]" in art.content:
            art.truncated = True
            art.content = art.content.replace("[TRUNCATED - MAX TOKENS HIT]", "").strip()

        articles.append(art)

    return articles


# ── MERGE LOGIC ──────────────────────────────────────────────────────────────

def is_continuation_block(article: Article) -> bool:
    """Check if an article block looks like a continuation of a previous article."""
    title = article.title.lower()
    return bool(
        re.search(r'continu(ed|ation)', title, re.IGNORECASE)
        or title.startswith('[continuation')
        or title.startswith('[continued')
    )


def group_articles(articles: List[Article]) -> Tuple[List[List[int]], List[Dict]]:
    """Group article indices by normalized title.
    Returns (groups, orphan_notes) where groups is list of index lists
    and orphan_notes is a list of dicts describing orphan merges.
    Continuation blocks are matched to the most recent non-continuation
    article with a matching normalized title. Unmatched continuations
    are appended to the most recent non-continuation article."""
    groups = []  # type: List[List[int]]
    # Map normalized title -> group index
    title_to_group = {}  # type: Dict[str, int]
    orphan_notes = []  # type: List[Dict]
    # Track the group index of the most recent non-continuation article
    last_non_continuation_group = -1  # type: int

    for i, art in enumerate(articles):
        norm = normalize_title(art.title)

        if is_continuation_block(art):
            # Pass 1: Try strict matching (exact norm or substring)
            matched = False
            for existing_norm, group_idx in title_to_group.items():
                if titles_match_strict(art.title, articles[groups[group_idx][0]].title):
                    groups[group_idx].append(i)
                    matched = True
                    break
            if not matched and norm in title_to_group:
                groups[title_to_group[norm]].append(i)
                matched = True

            # Pass 2: Try keyword overlap — pick best match (most hits, recency tiebreak)
            if not matched:
                best_group = -1
                best_score = 0
                for existing_norm, group_idx in title_to_group.items():
                    score = keyword_overlap_count(art.title, articles[groups[group_idx][0]].title)
                    if score > best_score or (score == best_score and score > 0 and group_idx > best_group):
                        best_score = score
                        best_group = group_idx
                if best_score > 0:
                    groups[best_group].append(i)
                    matched = True

            # Pass 3: Orphan fallback
            if not matched:
                if last_non_continuation_group >= 0:
                    # Orphan continuation — append to most recent non-continuation
                    parent_idx = groups[last_non_continuation_group][0]
                    groups[last_non_continuation_group].append(i)
                    orphan_notes.append({
                        "orphan_title": art.title,
                        "appended_to": articles[parent_idx].title
                    })
                    print(f"    Orphan continuation '{art.title}' → appended to '{articles[parent_idx].title}'")
                else:
                    # No parent at all — create new group
                    group_idx = len(groups)
                    groups.append([i])
                    if norm:
                        title_to_group[norm] = group_idx
        else:
            if norm in title_to_group:
                # Same title as existing group — merge
                groups[title_to_group[norm]].append(i)
            else:
                # New group
                group_idx = len(groups)
                groups.append([i])
                if norm:
                    title_to_group[norm] = group_idx
            last_non_continuation_group = title_to_group.get(norm, len(groups) - 1)

    return groups, orphan_notes


def merge_group(articles: List[Article], indices: List[int]) -> Article:
    """Merge multiple article blocks into one. Keeps metadata from first,
    concatenates content, deduplicates books mentioned."""
    first = articles[indices[0]]

    if len(indices) == 1:
        return first

    merged = Article()
    # Keep all metadata from first occurrence
    merged.title = first.title
    merged.author = first.author
    merged.magazine = first.magazine
    merged.issue = first.issue
    merged.date = first.date
    merged.categories = first.categories
    merged.category_reasoning = first.category_reasoning

    # Concatenate content
    contents = []
    for idx in indices:
        c = articles[idx].content.strip()
        if c:
            contents.append(c)
    merged.content = "\n\n".join(contents)

    # Combine and deduplicate books mentioned
    all_books = set()
    for idx in indices:
        books = articles[idx].books_mentioned.strip()
        if books and books.lower() != "none":
            for book in re.split(r'[,;|\n]', books):
                book = book.strip()
                if book and book.lower() != "none":
                    all_books.add(book)
    merged.books_mentioned = ", ".join(sorted(all_books)) if all_books else "None"

    # Propagate truncation flag from any block in the group
    merged.truncated = any(articles[idx].truncated for idx in indices)

    return merged


# ── OUTPUT FORMATTING ────────────────────────────────────────────────────────

def format_article(article: Article) -> str:
    """Format a single article as ARTICLE START...ARTICLE END block."""
    lines = [
        "ARTICLE START",
        f"TITLE: {article.title}",
        f"AUTHOR: {article.author}",
        f"MAGAZINE: {article.magazine}",
        f"ISSUE: {article.issue}",
        f"DATE: {article.date}",
        f"CATEGORIES: {article.categories}",
        f"CATEGORY REASONING: {article.category_reasoning}",
    ]
    if article.truncated:
        lines.append("TRUNCATED: YES — content may be incomplete, manual review needed")
    lines += [
        "",
        "CONTENT:",
        "",
        article.content,
        "",
        f"BOOKS MENTIONED: {article.books_mentioned}",
        "ARTICLE END",
    ]
    return "\n".join(lines)


def format_output(
    toc: Optional[str],
    articles: List[Article],
    raw_block_count: int,
    merge_count: int,
    merge_time: str
) -> str:
    """Format the complete merged output file."""
    parts = [
        f"MERGED: {merge_time}",
        f"MERGE NOTES: {len(articles)} articles merged from {raw_block_count} raw blocks",
    ]

    if toc:
        parts.append("")
        parts.append(toc)

    for art in articles:
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append(format_article(art))

    return "\n".join(parts) + "\n"


# ── MERGE LOG ────────────────────────────────────────────────────────────────

def load_merge_log() -> List[Dict]:
    """Load existing merge log or return empty list."""
    if MERGE_LOG_PATH.exists():
        with open(MERGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_merge_log(log: List[Dict]) -> None:
    """Save merge log to disk."""
    with open(MERGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def is_already_merged(log: List[Dict], filename: str, output_dir: Path) -> bool:
    """Check if a file has already been merged."""
    output_path = output_dir / filename
    for entry in log:
        if entry.get("filename") == filename and entry.get("status") == "merged":
            if Path(entry.get("output_path", "")).exists() or output_path.exists():
                return True
    return False


# ── PROCESS SINGLE FILE ─────────────────────────────────────────────────────

def process_file(txt_path: Path, log: List[Dict]) -> Optional[Dict]:
    """Process a single raw extracted file. Returns log entry or None."""
    filename = txt_path.name

    # Determine output directory
    if "NewWine" in filename:
        output_dir = OUTPUT_COPYRIGHTED
    else:
        output_dir = OUTPUT_OPEN

    # Skip if already merged
    if is_already_merged(log, filename, output_dir):
        print(f"  Skipping {filename} — already merged.")
        return None

    print(f"\n  Processing: {filename}")

    try:
        raw_text = txt_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ERROR reading file: {e}")
        return {
            "filename": filename,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "failed",
            "reason": str(e)
        }

    # Extract TOC
    toc = extract_toc(raw_text)

    # Parse articles
    try:
        articles = parse_articles(raw_text)
    except Exception as e:
        print(f"  ERROR parsing articles: {e}")
        return {
            "filename": filename,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "failed",
            "reason": f"Parse error: {e}"
        }

    raw_block_count = len(articles)
    print(f"  Raw blocks found: {raw_block_count}")

    if raw_block_count == 0:
        print(f"  WARNING: No articles found")
        return {
            "filename": filename,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "failed",
            "reason": "No ARTICLE START blocks found"
        }

    # Group and merge
    groups, orphan_notes = group_articles(articles)
    merges_performed = []

    merged_articles = []
    truncated_titles = []
    for group_indices in groups:
        merged = merge_group(articles, group_indices)
        merged_articles.append(merged)
        if len(group_indices) > 1:
            merges_performed.append({
                "title": merged.title,
                "blocks_merged": len(group_indices)
            })
        if merged.truncated:
            truncated_titles.append(merged.title)

    articles_after_merge = len(merged_articles)

    if truncated_titles:
        print(f"  TRUNCATION WARNING: {len(truncated_titles)} article(s) flagged: {truncated_titles}")

    if merges_performed:
        print(f"  Merges performed: {[m['title'] for m in merges_performed]}")
    else:
        print(f"  Merges performed: none")
    print(f"  Articles after merge: {articles_after_merge}")

    # Format output
    merge_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_text = format_output(toc, merged_articles, raw_block_count, len(merges_performed), merge_time)

    # Write output
    output_path = output_dir / filename
    try:
        output_path.write_text(output_text, encoding="utf-8")
        print(f"  Written to: {output_path}")
    except Exception as e:
        print(f"  ERROR writing output: {e}")
        return {
            "filename": filename,
            "processed_at": merge_time,
            "status": "failed",
            "reason": f"Write error: {e}"
        }

    return {
        "filename": filename,
        "processed_at": merge_time,
        "status": "merged",
        "output_path": str(output_path),
        "raw_blocks_found": raw_block_count,
        "articles_after_merge": articles_after_merge,
        "merges_performed": merges_performed,
        "orphan_continuations": orphan_notes,
        "truncated_articles": truncated_titles
    }


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    """Process all txt files in raw_extracted/."""
    # Ensure output dirs exist
    OUTPUT_COPYRIGHTED.mkdir(parents=True, exist_ok=True)
    OUTPUT_OPEN.mkdir(parents=True, exist_ok=True)

    # Load merge log
    log = load_merge_log()

    # Find files
    txt_files = sorted(INPUT_DIR.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {INPUT_DIR}")
        return

    print(f"Found {len(txt_files)} file(s) to process")

    processed = skipped = failed = 0
    all_truncations = []  # type: List[Tuple[str, str]]  # (title, filename)
    for txt_path in txt_files:
        entry = process_file(txt_path, log)
        if entry is None:
            skipped += 1
        elif entry.get("status") == "merged":
            log.append(entry)
            save_merge_log(log)
            processed += 1
            for t in entry.get("truncated_articles", []):
                all_truncations.append((t, txt_path.name))
        else:
            log.append(entry)
            save_merge_log(log)
            failed += 1

    print(f"\n{'='*60}")
    print(f"Done. {processed} merged, {skipped} skipped, {failed} failed.")

    if all_truncations:
        issues_with_truncations = set(f for _, f in all_truncations)
        print(f"\nTRUNCATION WARNINGS: {len(all_truncations)} articles flagged across {len(issues_with_truncations)} issues")
        for title, fname in all_truncations:
            print(f"  - \"{title}\" in {fname}")


if __name__ == "__main__":
    run()
