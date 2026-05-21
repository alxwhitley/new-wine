#!/usr/bin/env python3
"""
Rhemata Precept Austin Greek Word Study Scraper

Step 1A: Parse the index page at preceptaustin.org/greek_word_studies
Step 1B: Fetch and extract individual word study content
Step 1C: QA report
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

PROJECT_ROOT = Path(__file__).resolve().parent
SOURCES_DIR = PROJECT_ROOT / "sources" / "precept_austin"
RAW_DIR = SOURCES_DIR / "raw"
CACHE_DIR = SOURCES_DIR / "page_cache"
INDEX_FILE = SOURCES_DIR / "index.json"
QA_FILE = SOURCES_DIR / "qa_report.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}
INDEX_URL = "https://www.preceptaustin.org/greek_word_studies"
SLEEP_MIN = 2
SLEEP_MAX = 5


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

def parse_index():
    # type: () -> List[Dict[str, str]]
    """Fetch and parse the Greek word studies index page.

    Each entry in the HTML follows this pattern inside a <p>:
      <b>English Word</b> (studylight_link) preceptaustin_link
    """
    print("Fetching index page...")
    resp = requests.get(INDEX_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    entries = []  # type: List[Dict[str, str]]

    for p in soup.find_all("p"):
        bold = p.find("b")
        if not bold:
            continue

        links = p.find_all("a")
        studylight_link = None
        pa_link = None

        for a in links:
            href = a.get("href", "")
            if "studylight" in href and studylight_link is None:
                studylight_link = a
            elif "preceptaustin" in href or href.startswith("/"):
                if pa_link is None:
                    pa_link = a

        if studylight_link is None or pa_link is None:
            continue

        english_word = bold.get_text(strip=True)
        if not english_word:
            continue

        strongs_text = studylight_link.get_text(strip=True)
        strongs_match = re.search(r'(\d+)', strongs_text)
        if not strongs_match:
            href = studylight_link.get("href", "")
            strongs_match = re.search(r'(\d+)', href)
        if not strongs_match:
            continue

        strongs_num = strongs_match.group(1)
        href = studylight_link.get("href", "")
        if "hebrew" in href.lower() or "/h/" in href.lower():
            strongs_number = "H" + strongs_num.zfill(4)
        else:
            strongs_number = "G" + strongs_num.zfill(4)

        transliteration = pa_link.get_text(strip=True)
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

    return entries


def run_step_1a():
    # type: () -> List[Dict[str, str]]
    """Parse the index and save to index.json."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    entries = parse_index()

    seen = set()  # type: set
    unique_entries = []  # type: List[Dict[str, str]]
    for entry in entries:
        key = entry["strongs_number"]
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)

    with open(INDEX_FILE, "w") as f:
        json.dump(unique_entries, f, indent=2)

    print("\nIndex saved to {}".format(INDEX_FILE))
    print("Total entries found: {}".format(len(entries)))
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


def extract_word_study(soup, anchor):
    # type: (BeautifulSoup, str) -> Optional[str]
    """Extract word study content starting from the given anchor point.

    DOM structure: the anchor is an empty <a id="..." name="..."> inside a <p>.
    The word study content flows in sibling <p> and <blockquote> tags after that
    parent <p>. It ends when we hit a <p> containing another named <a> anchor
    (the next word study) or a <h2>/<h3> heading.
    """
    if not anchor:
        return None

    anchor_clean = anchor.lstrip("#")

    target = find_anchor(soup, anchor)
    if not target:
        return None

    # Get the parent <p> that contains this anchor
    parent_p = target.parent
    if parent_p is None or parent_p.name != "p":
        parent_p = target.find_parent("p")
    if parent_p is None:
        parent_p = target.parent
    if parent_p is None:
        return None

    # Collect text: start with the parent <p> itself, then walk its siblings
    content_parts = []  # type: List[str]
    max_chars = 80000

    text = parent_p.get_text(separator=" ", strip=True)
    if text:
        content_parts.append(text)

    total = len(text) if text else 0
    current = parent_p.next_sibling

    while current is not None and total < max_chars:
        # Skip NavigableString nodes (whitespace between tags)
        if not hasattr(current, 'name') or current.name is None:
            current = current.next_sibling
            continue

        # Stop at headings
        if current.name in ("h2", "h3"):
            break

        # Stop at a <p> that contains a named anchor (next word study entry)
        if current.name == "p":
            child_anchor = current.find("a", attrs={"id": True}) or current.find("a", attrs={"name": True})
            if child_anchor:
                child_id = child_anchor.get("id") or child_anchor.get("name") or ""
                if child_id and child_id != anchor_clean:
                    break

        # Collect text from block-level elements
        collect = False
        if current.name in ("p", "blockquote", "ul", "ol", "li", "table"):
            collect = True
        elif current.name == "div" and is_leaf_div(current):
            collect = True

        if collect:
            text = current.get_text(separator=" ", strip=True)
            if text:
                content_parts.append(text)
                total += len(text)

        current = current.next_sibling

    if not content_parts:
        return None

    raw_text = "\n\n".join(content_parts)

    # Clean up
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


def run_step_1b(entries):
    # type: (List[Dict[str, str]]) -> Dict
    """Fetch pages and extract word study content for each entry."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
    args = set(sys.argv[1:])

    if "--fetch" in args or "--test" in args:
        # Load or build index
        if INDEX_FILE.exists():
            with open(INDEX_FILE) as f:
                entries = json.load(f)
            print("Loaded {} entries from existing index.json".format(len(entries)))
        else:
            entries = run_step_1a()

        # --test: limit to first 10 entries
        if "--test" in args:
            entries = entries[:10]
            print("TEST MODE: limited to first {} entries".format(len(entries)))

        results = run_step_1b(entries)
        run_step_1c(results)
    else:
        # Default: Step 1A only
        run_step_1a()
