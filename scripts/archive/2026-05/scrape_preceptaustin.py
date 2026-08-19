#!/usr/bin/env python3
"""
Rhemata Precept Austin Word Study Scraper

Supports Greek and Hebrew word studies via --language flag.
Step 1A: Parse the index page
Step 1B: Fetch and extract individual word study content
Step 1C: QA report

Usage:
  python3 scrape_preceptaustin.py --language greek --test   # Greek, first 10
  python3 scrape_preceptaustin.py --language hebrew --test  # Hebrew, first 10
  python3 scrape_preceptaustin.py --language hebrew --fetch # Hebrew, full run
"""

import gc
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

# Flush stdout on every print for nohup compatibility
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

HEADERS = {"User-Agent": "Mozilla/5.0"}
SLEEP_MIN = 2
SLEEP_MAX = 5

# Language-specific config — set by set_language() before use
SOURCES_DIR = None  # type: Optional[Path]
RAW_DIR = None  # type: Optional[Path]
CACHE_DIR = None  # type: Optional[Path]
INDEX_FILE = None  # type: Optional[Path]
QA_FILE = None  # type: Optional[Path]
INDEX_URLS = None  # type: Optional[List[str]]
LANGUAGE = None  # type: Optional[str]

LANG_CONFIG = {
    "greek": {
        "subdir": "precept_austin",
        "index_urls": ["https://www.preceptaustin.org/greek_word_studies"],
    },
    "hebrew": {
        "subdir": "precept_austin_hebrew",
        "index_urls": [
            "https://www.preceptaustin.org/hebrew_word_studies",
            "https://www.preceptaustin.org/hebrew_definitions",
            "https://www.preceptaustin.org/hebrew_definitions_2",
        ],
    },
}


def set_language(lang):
    # type: (str) -> None
    """Configure global paths and URL for the given language."""
    global SOURCES_DIR, RAW_DIR, CACHE_DIR, INDEX_FILE, QA_FILE, INDEX_URLS, LANGUAGE
    cfg = LANG_CONFIG[lang]
    SOURCES_DIR = PROJECT_ROOT / "sources" / cfg["subdir"]
    RAW_DIR = SOURCES_DIR / "raw"
    CACHE_DIR = SOURCES_DIR / "page_cache"
    INDEX_FILE = SOURCES_DIR / "index.json"
    QA_FILE = SOURCES_DIR / "qa_report.json"
    INDEX_URLS = cfg["index_urls"]
    LANGUAGE = lang


# ── Helpers ──────────────────────────────────────────────────────────────────

def url_to_cache_slug(url):
    # type: (str) -> str
    """Convert a URL to a safe filename for the page cache."""
    slug = url.replace("https://", "").replace("http://", "")
    slug = re.sub(r'[/.\-:?&=%#]', '_', slug)
    return slug + ".html"


def load_or_fetch_page(page_url):
    # type: (str) -> tuple
    """Load page from cache or fetch live. Returns (html_str, from_cache)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / url_to_cache_slug(page_url)

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8"), True

    resp = requests.get(page_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    cache_path.write_text(html, encoding="utf-8")
    return html, False


# ── Step 1A: Parse the index page ────────────────────────────────────────────

def parse_index(index_url):
    # type: (str) -> List[Dict[str, str]]
    """Fetch and parse a single word studies index page.

    Each entry in the HTML follows this pattern inside a <p>:
      <b>English Word</b> (optional synonyms) (studylight_link) <a href="/path#anchor">transliteration</a>
    """
    print("Fetching index page: {}".format(index_url))
    resp = requests.get(index_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    entries = []  # type: List[Dict[str, str]]
    skip_reasons = {"no_bold_text": 0, "no_pa_link": 0, "no_strongs": 0}
    total_bold_p = 0

    for p in soup.find_all("p"):
        bold = p.find("b")
        if not bold:
            continue
        total_bold_p += 1

        english_word = bold.get_text(strip=True)
        if not english_word:
            skip_reasons["no_bold_text"] += 1
            continue

        # Find preceptaustin link (required)
        links = p.find_all("a")
        pa_link = None
        studylight_link = None

        for a in links:
            href = a.get("href", "")
            if "studylight" in href and studylight_link is None:
                studylight_link = a
            elif ("preceptaustin" in href or href.startswith("/")) and pa_link is None:
                pa_link = a

        if pa_link is None:
            skip_reasons["no_pa_link"] += 1
            continue

        # Extract Strong's number: prefer studylight link text, fall back to parenthesized number
        strongs_num = None
        if studylight_link is not None:
            strongs_text = studylight_link.get_text(strip=True)
            m = re.search(r'(\d+)', strongs_text)
            if m:
                strongs_num = m.group(1)

        if strongs_num is None:
            # Fallback: scan raw <p> text for standalone number in parentheses
            p_text = p.get_text()
            m = re.search(r'\((\d{2,5})\)', p_text)
            if m:
                strongs_num = m.group(1)

        if strongs_num is None:
            skip_reasons["no_strongs"] += 1
            continue

        # Determine prefix from studylight href or language setting
        if studylight_link is not None:
            sl_href = studylight_link.get("href", "").lower()
            is_hebrew = "hebrew" in sl_href or "/heb/" in sl_href or LANGUAGE == "hebrew"
        else:
            is_hebrew = LANGUAGE == "hebrew"
        strongs_number = ("H" if is_hebrew else "G") + strongs_num.zfill(4)

        # Transliteration: prefer PA link text, fall back to english word
        transliteration = pa_link.get_text(strip=True)
        if not transliteration:
            transliteration = english_word

        pa_href = pa_link.get("href", "")

        if pa_href.startswith("/"):
            target_url = "https://www.preceptaustin.org" + pa_href
        else:
            target_url = pa_href

        if "#" in target_url:
            page_url, anchor = target_url.rsplit("#", 1)
        else:
            page_url = target_url
            anchor = ""

        entries.append({
            "english_word": english_word,
            "strongs_number": strongs_number,
            "transliteration": transliteration,
            "target_url": target_url,
            "page_url": page_url,
            "anchor": anchor,
        })

    # Summary
    total_skipped = sum(skip_reasons.values())
    print("\nParse summary:")
    print("  <p> tags with <b>: {}".format(total_bold_p))
    print("  Entries captured: {}".format(len(entries)))
    print("  Skipped: {} total".format(total_skipped))
    for reason, count in sorted(skip_reasons.items()):
        if count > 0:
            print("    {}: {}".format(reason, count))

    return entries


def run_step_1a():
    # type: () -> List[Dict[str, str]]
    """Parse all index pages and save combined index.json."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    all_entries = []  # type: List[Dict[str, str]]
    for url in INDEX_URLS:
        page_entries = parse_index(url)
        all_entries.extend(page_entries)

    seen = set()  # type: set
    unique_entries = []  # type: List[Dict[str, str]]
    for entry in all_entries:
        key = entry["strongs_number"]
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)

    with open(INDEX_FILE, "w") as f:
        json.dump(unique_entries, f, indent=2)

    print("\nIndex saved to {}".format(INDEX_FILE))
    print("Total entries found (across {} pages): {}".format(len(INDEX_URLS), len(all_entries)))
    print("Unique entries (by Strong's number): {}".format(len(unique_entries)))

    print("\nSample entries:")
    for entry in unique_entries[:5]:
        print("  {} ({}) -- {}".format(entry["english_word"], entry["strongs_number"], entry["transliteration"]))
        print("    URL: {}".format(entry["target_url"]))

    return unique_entries


# ── Step 1B: Fetch and extract word study content ────────────────────────────

def find_anchor(soup, anchor_fragment):
    # type: (BeautifulSoup, str) -> Optional[object]
    """Find an anchor <a> element using multiple matching strategies."""
    anchor_clean = anchor_fragment.lstrip("#")
    if not anchor_clean:
        return None

    # Strategy 1: Exact match on id or name
    target = (
        soup.find("a", attrs={"id": anchor_clean})
        or soup.find("a", attrs={"name": anchor_clean})
    )
    if target:
        return target

    # Strategy 2: Case-insensitive exact match
    anchor_lower = anchor_clean.lower()
    for el in soup.find_all("a"):
        el_id = (el.get("id") or "").lower()
        el_name = (el.get("name") or "").lower()
        if el_id == anchor_lower or el_name == anchor_lower:
            return el

    # Strategy 3: Partial match — anchor fragment contained within id or name
    for el in soup.find_all("a"):
        el_id = (el.get("id") or "").lower()
        el_name = (el.get("name") or "").lower()
        if anchor_lower in el_id or anchor_lower in el_name:
            return el

    # Strategy 4: Reverse partial — any word in id/name matches any word in anchor
    anchor_words = set(anchor_lower.split())
    if anchor_words:
        for el in soup.find_all("a"):
            el_id = (el.get("id") or "").lower()
            el_name = (el.get("name") or "").lower()
            el_words = set(el_id.split()) | set(el_name.split())
            if anchor_words & el_words:
                return el

    return None


def is_leaf_div(tag):
    # type: (object) -> bool
    """Check if a div has no child block-level elements (leaf div only)."""
    block_tags = {"p", "blockquote", "ul", "ol", "div", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
    for child in tag.children:
        if hasattr(child, 'name') and child.name in block_tags:
            return False
    return True


def passes_quality_filter(content):
    # type: (str) -> Optional[str]
    """Check content quality. Returns rejection reason or None if passes."""
    words = content.split()
    word_count = len(words)

    if word_count < 100:
        return "Content too short ({} words)".format(word_count)

    # Check for nav bleed in first 50 words
    first_50 = " ".join(words[:50]).lower()
    if "skip to main content" in first_50:
        return "Nav bleed detected (skip to main content)"
    if "precept austin" in first_50 and word_count < 200:
        return "Nav bleed detected (Precept Austin in intro)"

    # Check for fragmented text (> 40% of words are 1-2 chars)
    short_words = sum(1 for w in words if len(w) <= 2)
    if word_count > 0 and short_words / word_count > 0.4:
        return "Fragmented text ({:.0f}% short words)".format(100.0 * short_words / word_count)

    return None


def _is_yellow_span(tag):
    # type: (object) -> bool
    """Check if a tag is a yellow-highlighted span (word study heading marker)."""
    if not hasattr(tag, 'name') or tag.name != "span":
        return False
    style = (tag.get("style") or "").lower().replace(" ", "")
    return "background-color:#ffff00" in style


def _clean_extracted_text(raw_text):
    # type: (str) -> str
    """Clean up extracted word study text: strip junk lines, collapse whitespace."""
    lines = raw_text.split("\n")
    cleaned_lines = []  # type: List[str]
    for line in lines:
        line = line.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if re.match(r'^[GH]?\d{1,5}$', line):
            continue
        if len(line) < 5 and not any(c.isalpha() for c in line):
            continue
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def extract_word_study(soup, anchor):
    # type: (BeautifulSoup, str) -> Optional[str]
    """Extract word study content starting from the given anchor point.

    Walks forward through the DOM from the anchor using find_all_next().
    Collects text from block-level elements. Stops at the second yellow
    highlight span (the first is the current word's heading, the second
    marks the next word study).
    """
    block_tags = {"p", "blockquote", "ul", "ol", "li", "table", "div"}
    max_chars = 80000

    # Find starting element
    if anchor:
        target = find_anchor(soup, anchor)
        if not target:
            return None
        start = target
    else:
        # No anchor — start from main content area
        content_div = (
            soup.find("div", class_="field-item")
            or soup.find("article")
            or soup.find("div", id="content")
        )
        if not content_div:
            return None
        start = content_div

    # Walk forward through all elements after the anchor
    content_parts = []  # type: List[str]
    total = 0
    yellow_count = 0

    for el in start.find_all_next():
        if total >= max_chars:
            break

        # Check for yellow span stop marker (only count non-empty ones)
        if _is_yellow_span(el) and el.get_text(strip=True):
            yellow_count += 1
            if yellow_count >= 2:
                break
            continue

        # Skip non-block elements (they'll be captured via parent get_text)
        if not hasattr(el, 'name') or el.name is None:
            continue
        if el.name not in block_tags:
            continue

        # Skip divs that contain other block elements (avoid double-counting)
        if el.name == "div" and not is_leaf_div(el):
            continue

        text = el.get_text(separator=" ", strip=True)
        if text:
            content_parts.append(text)
            total += len(text)

    if not content_parts:
        return None

    raw_text = "\n\n".join(content_parts)
    return _clean_extracted_text(raw_text)


def run_step_1b(entries, resume=False):
    # type: (List[Dict[str, str]], bool) -> Dict
    """Fetch pages and extract word study content for each entry."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if resume:
        print("RESUME MODE: skipping existing files")
    else:
        # Clean start: delete all existing .txt files in raw/
        existing = list(RAW_DIR.glob("*.txt"))
        if existing:
            print("Cleaning {} existing files from raw/...".format(len(existing)))
            for f in existing:
                f.unlink()

    # Group entries by page_url, preserving insertion order
    page_groups = {}  # type: Dict[str, List[Dict[str, str]]]
    for entry in entries:
        url = entry["page_url"]
        if url not in page_groups:
            page_groups[url] = []
        page_groups[url].append(entry)

    total_pages = len(page_groups)
    print("\n{} unique pages to fetch".format(total_pages))
    print("Estimated time (no cache): ~{} minutes\n".format(total_pages * 3 // 60))

    results = {"attempted": 0, "success": 0, "failed": 0, "failures": []}  # type: Dict
    pages_fetched = 0
    pages_cached = 0
    pages_failed = 0

    for page_idx, (page_url, page_entries) in enumerate(page_groups.items()):
        # Resume: skip entire page if all entries already have files
        if resume:
            all_exist = True
            for entry in page_entries:
                safe_t = re.sub(r'[^a-zA-Z0-9_]', '', entry["transliteration"].replace(" ", "_"))
                if not (RAW_DIR / "{}_{}.txt".format(entry["strongs_number"], safe_t)).exists():
                    all_exist = False
                    break
            if all_exist:
                for entry in page_entries:
                    results["attempted"] += 1
                    results["success"] += 1
                continue

        # Fetch or load from cache
        soup = None  # type: Optional[BeautifulSoup]
        from_cache = False
        try:
            html, from_cache = load_or_fetch_page(page_url)
            soup = BeautifulSoup(html, "html.parser")
            if from_cache:
                pages_cached += 1
            else:
                pages_fetched += 1
        except Exception as e:
            pages_failed += 1
            print("  PAGE FAIL [{}/{}]: {} -- {}".format(page_idx + 1, total_pages, page_url, e))
            for entry in page_entries:
                results["attempted"] += 1
                results["failed"] += 1
                results["failures"].append({
                    "strongs": entry["strongs_number"],
                    "english_word": entry["english_word"],
                    "url": entry["target_url"],
                    "reason": "Page fetch failed: {}".format(e),
                })
            if page_idx < total_pages - 1 and not from_cache:
                time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
            continue

        # Extract content for each entry on this page
        for entry in page_entries:
            results["attempted"] += 1

            # Resume: skip if file already exists
            if resume:
                safe_t = re.sub(r'[^a-zA-Z0-9_]', '', entry["transliteration"].replace(" ", "_"))
                existing_file = RAW_DIR / "{}_{}.txt".format(entry["strongs_number"], safe_t)
                if existing_file.exists():
                    results["success"] += 1
                    continue

            anchor = entry["anchor"]

            content = extract_word_study(soup, anchor)

            if content is None:
                results["failed"] += 1
                results["failures"].append({
                    "strongs": entry["strongs_number"],
                    "english_word": entry["english_word"],
                    "url": entry["target_url"],
                    "reason": "Anchor not found or no content extracted",
                })
                continue

            # Quality filter
            rejection = passes_quality_filter(content)
            if rejection:
                results["failed"] += 1
                results["failures"].append({
                    "strongs": entry["strongs_number"],
                    "english_word": entry["english_word"],
                    "url": entry["target_url"],
                    "reason": rejection,
                })
                continue

            # Save to file
            safe_translit = re.sub(r'[^a-zA-Z0-9_]', '', entry["transliteration"].replace(" ", "_"))
            filename = "{}_{}.txt".format(entry["strongs_number"], safe_translit)
            filepath = RAW_DIR / filename
            filepath.write_text(content, encoding="utf-8")

            results["success"] += 1

        # Memory cleanup
        del soup
        gc.collect()

        # Progress report every 10 pages
        page_num = page_idx + 1
        if page_num % 10 == 0 or page_num == total_pages:
            remaining = total_pages - page_num
            print(
                "[PROGRESS] Pages: {}/{} done, {} remaining | "
                "Live: {} | Cached: {} | Errors: {} | "
                "Extracted: {} | Failed: {}".format(
                    page_num, total_pages, remaining,
                    pages_fetched, pages_cached, pages_failed,
                    results["success"], results["failed"],
                )
            )

        # Rate limiting (only for live fetches, not cache hits)
        if page_idx < total_pages - 1 and not from_cache:
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    return results


def run_step_1c(results):
    # type: (Dict) -> None
    """Generate QA report from extraction results."""
    with open(QA_FILE, "w") as f:
        json.dump({
            "total_attempted": results["attempted"],
            "total_success": results["success"],
            "total_failed": results["failed"],
            "failures": results["failures"],
        }, f, indent=2)

    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY (Step 1C)")
    print("  Total attempted: {}".format(results["attempted"]))
    print("  Extracted successfully: {}".format(results["success"]))
    print("  Failed/skipped: {}".format(results["failed"]))
    print("\nQA report saved to {}".format(QA_FILE))
    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    args_set = set(args)

    # Parse --language flag
    lang = "greek"
    for i, a in enumerate(args):
        if a == "--language" and i + 1 < len(args):
            lang = args[i + 1].lower()
    if lang not in LANG_CONFIG:
        print("ERROR: --language must be one of: {}".format(", ".join(LANG_CONFIG.keys())))
        sys.exit(1)
    set_language(lang)
    print("Language: {} | Index pages: {}".format(LANGUAGE, len(INDEX_URLS)))

    if "--fetch" in args_set or "--test" in args_set:
        # Load or build index
        if INDEX_FILE.exists():
            with open(INDEX_FILE) as f:
                entries = json.load(f)
            print("Loaded {} entries from existing index.json".format(len(entries)))
        else:
            entries = run_step_1a()

        # --test: limit to first 10 entries
        if "--test" in args_set:
            entries = entries[:10]
            print("TEST MODE: limited to first {} entries".format(len(entries)))

        resume = "--resume" in args_set
        results = run_step_1b(entries, resume=resume)
        run_step_1c(results)
    else:
        # Default: Step 1A only
        run_step_1a()
