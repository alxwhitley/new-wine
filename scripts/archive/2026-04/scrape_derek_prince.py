#!/usr/bin/env python3
"""
scrape_derek_prince.py — Derek Prince Sermon Transcript Scraper

Pipeline:
  1. Fetch sermon listing page to get all sermon URLs
  2. For each sermon, fetch detail page and extract transcript + metadata
  3. Save as structured .txt to sources/web/derek_prince/raw/
  4. Skip already-saved sermons (deduplicate by filename)
  5. Log failures to sources/web/derek_prince/failed.log
"""

import os
import re
import sys
import time
import random
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "sources" / "web" / "derek_prince" / "raw"
FAILED_LOG = ROOT / "sources" / "web" / "derek_prince" / "failed.log"

LISTING_URL = "https://www.derekprince.com/sermons"
BASE_URL = "https://www.derekprince.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT = 20
DELAY_MIN = 1.0
DELAY_MAX = 2.0

# -- TEST / THROTTLE CONTROLS -----------------------------------------------
TEST_MODE = False   # Set True to only scrape a few sermons
MAX_SERMONS = 5     # Only used when TEST_MODE is True

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# -- HELPERS -----------------------------------------------------------------

def log_failure(url, reason):
    """Append a failure line to failed.log."""
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(FAILED_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {url} | {reason}\n")


def make_filename(resource_code, url_slug):
    """Build filename from resource code or URL slug."""
    if resource_code:
        safe = re.sub(r"[^\w\-]", "_", resource_code)
        return f"{safe}.txt"
    safe = re.sub(r"[^\w\-]", "_", url_slug)
    return f"sermon_{safe}.txt"


def fetch_page(url):
    """Fetch a URL with retries. Returns response text or None."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.text
            logger.warning("HTTP %d for %s (attempt %d)", r.status_code, url, attempt + 1)
        except requests.RequestException as e:
            logger.warning("Request failed for %s: %s (attempt %d)", url, e, attempt + 1)
        if attempt < 2:
            time.sleep(2)
    return None


# -- LISTING PAGE ------------------------------------------------------------

def get_sermon_urls():
    """Fetch the sermon listing page and extract all unique /sermons/{id} URLs."""
    print(f"Fetching sermon listing from {LISTING_URL}...")
    html = fetch_page(LISTING_URL)
    if not html:
        print("Failed to fetch listing page")
        sys.exit(1)

    soup = BeautifulSoup(html, "html.parser")

    urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = re.match(r"^/sermons/(\d+)$", href)
        if match:
            urls.add(href)

    # Sort numerically by sermon ID
    sorted_urls = sorted(urls, key=lambda u: int(u.split("/")[-1]))
    print(f"  Found {len(sorted_urls)} unique sermon URLs")
    return sorted_urls


# -- DETAIL PAGE EXTRACTION --------------------------------------------------

def extract_sermon(html, url):
    """Parse a sermon detail page. Returns dict with metadata + transcript, or None."""
    soup = BeautifulSoup(html, "html.parser")

    # Title — from h1
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title:
        return None

    # Resource code — "Code: MV-4258-100-ENG"
    resource_code = None
    code_div = soup.find("div", class_=re.compile(r"text-i-grey-normal-14-1.*pt-10-1"))
    if code_div:
        code_text = code_div.get_text(strip=True)
        code_match = re.search(r"Code:\s*(.+)", code_text)
        if code_match:
            resource_code = code_match.group(1).strip()

    # Series — from series icon links (can be multiple)
    series_list = []
    seen_series = set()
    for series_link in soup.find_all("a", class_=re.compile(r"div-series-icon-1")):
        for p in series_link.find_all("p", class_="text-i-white-bold-16-1"):
            text = p.get_text(strip=True)
            p_classes = p.get("class") or []
            if text and text != "Series:" and "w-dyn-bind-empty" not in p_classes:
                if text not in seen_series:
                    series_list.append(text)
                    seen_series.add(text)
    series = ", ".join(series_list) if series_list else None

    # Topics — from tag divs (exclude hidden/empty ones)
    topics = []
    seen_topics = set()
    for tag_div in soup.find_all("div", class_=re.compile(r"div-tags-3")):
        classes = tag_div.get("class", [])
        if "w-condition-invisible" in classes:
            continue
        inner = tag_div.find("div", class_=re.compile(r"text-i-black-normal-14-1"))
        if inner:
            inner_classes = inner.get("class", [])
            if "w-dyn-bind-empty" in inner_classes:
                continue
            topic = inner.get_text(strip=True)
            if topic and topic not in seen_topics:
                topics.append(topic)
                seen_topics.add(topic)

    # Description — from meta tag
    description = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "").strip()

    # Transcript — from div.div-transcript-container-2 > p tags
    transcript_parts = []
    transcript_container = soup.find("div", class_="div-transcript-container-2")
    if transcript_container:
        for p in transcript_container.find_all("p"):
            classes = p.get("class", [])
            # Skip font-size toggle buttons (have text-i- classes)
            class_str = " ".join(classes) if classes else ""
            if "text-i-" in class_str:
                continue
            text = p.get_text(strip=True)
            if text:
                transcript_parts.append(text)

    transcript = "\n\n".join(transcript_parts)

    if not transcript:
        return None

    return {
        "title": title,
        "resource_code": resource_code,
        "series": series,
        "topics": topics,
        "description": description,
        "transcript": transcript,
        "url": url,
    }


def write_sermon_file(path, data):
    """Write a sermon transcript file with metadata header."""
    topics_str = ", ".join(data["topics"]) if data["topics"] else ""
    header = (
        f"TITLE: {data['title']}\n"
        f"AUTHOR: Derek Prince\n"
        f"SOURCE: Derek Prince Ministries\n"
        f"URL: {data['url']}\n"
        f"SOURCE_TYPE: sermon\n"
    )
    if data.get("series"):
        header += f"SERIES: {data['series']}\n"
    if topics_str:
        header += f"TOPICS: {topics_str}\n"
    if data.get("resource_code"):
        header += f"RESOURCE_CODE: {data['resource_code']}\n"
    if data.get("description"):
        header += f"DESCRIPTION: {data['description']}\n"
    header += "---\n\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + data["transcript"], encoding="utf-8")


# -- MAIN --------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sermon_paths = get_sermon_urls()

    # Check what's already saved
    existing = {f.name for f in OUTPUT_DIR.glob("*.txt")}
    print(f"  {len(existing)} sermons already saved\n")

    stats = {"new": 0, "skipped": 0, "no_transcript": 0, "errors": 0}

    for i, path in enumerate(sermon_paths):
        if TEST_MODE and stats["new"] >= MAX_SERMONS:
            print(f"\n  TEST_MODE: reached {MAX_SERMONS} — stopping.")
            break

        url = BASE_URL + path
        url_slug = path.split("/")[-1]

        # Quick dedupe check — we'll do a more precise check after extracting
        # the resource code, but this catches the common case
        if f"sermon_{url_slug}.txt" in existing:
            stats["skipped"] += 1
            continue

        # Delay between requests
        if stats["new"] + stats["no_transcript"] + stats["errors"] > 0:
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            time.sleep(delay)

        html = fetch_page(url)
        if not html:
            logger.warning("Failed to fetch %s", url)
            log_failure(url, "HTTP fetch failed after retries")
            stats["errors"] += 1
            continue

        data = extract_sermon(html, url)

        if not data:
            logger.warning("No transcript found for %s", url)
            log_failure(url, "No transcript text on page")
            stats["no_transcript"] += 1
            continue

        # Build filename and check dedupe again with resource code
        filename = make_filename(data["resource_code"], url_slug)
        if filename in existing:
            stats["skipped"] += 1
            continue

        out_path = OUTPUT_DIR / filename
        word_count = len(data["transcript"].split())

        try:
            write_sermon_file(out_path, data)
            existing.add(filename)
            stats["new"] += 1
            print(
                f"  [{stats['new']:3d}] {data['title'][:60]}"
                f" ({word_count:,} words) — {filename}"
            )
        except Exception as e:
            logger.warning("Write failed for %s: %s", url, e)
            log_failure(url, f"Write error: {e}")
            stats["errors"] += 1

    print(f"\n{'=' * 60}")
    print(f"Done.")
    print(f"  New transcripts  : {stats['new']}")
    print(f"  Skipped (exists) : {stats['skipped']}")
    print(f"  No transcript    : {stats['no_transcript']}")
    print(f"  Errors           : {stats['errors']}")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
