#!/usr/bin/env python3
"""
scrape_ccel.py — Download public domain PDFs from CCEL (Christian Classics Ethereal Library)

Reads URLs from scripts/ccel_urls.txt, fetches each page, finds the PDF download link,
and saves to sources/documents/ with filename format author_slug.pdf.
Skips files that already exist. Logs failures to logs/ccel_scrape.log.
"""

import os
import re
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
URLS_FILE = ROOT / "scripts" / "ccel_urls.txt"
OUTPUT_DIR = ROOT / "sources" / "documents"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "ccel_scrape.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT = 30
DELAY = 1.0

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# -- HELPERS -----------------------------------------------------------------

def log_failure(url, reason):
    """Append a failure line to the log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {url} | {reason}\n")


def make_filename(author, url):
    """Build filename from author last name + URL slug."""
    # URL like https://ccel.org/ccel/murray/true_vine/true_vine → slug = true_vine
    parts = url.rstrip("/").split("/")
    slug = parts[-1] if parts else "unknown"

    # Author last name
    if author:
        last = author.strip().split()[-1].lower()
    else:
        # Fallback: try to get author from URL path segment
        # /ccel/murray/true_vine/true_vine → murray
        last = parts[-3] if len(parts) >= 3 else "unknown"

    return f"{last}_{slug}.pdf"


# -- EXTRACTION --------------------------------------------------------------

def extract_pdf_info(html, page_url):
    """Parse a CCEL book page. Returns (title, author, pdf_url) or None."""
    soup = BeautifulSoup(html, "html.parser")

    # Title from h1
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None

    # Author from "by Author Name" in h3
    author = None
    by_tag = soup.find(string=re.compile(r"^\s*by\s+"))
    if by_tag:
        match = re.match(r"\s*by\s+(.+)", by_tag.strip())
        if match:
            author = match.group(1).strip()

    # PDF link — href ending in .pdf
    pdf_url = None
    for a in soup.find_all("a", href=True):
        if a["href"].endswith(".pdf"):
            href = a["href"]
            if href.startswith("/"):
                href = "https://ccel.org" + href
            pdf_url = href
            break

    return title, author, pdf_url


# -- MAIN --------------------------------------------------------------------

def main():
    if not URLS_FILE.exists():
        print(f"URL file not found: {URLS_FILE}")
        sys.exit(1)

    urls = [
        line.strip()
        for line in URLS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(f"Loaded {len(urls)} URLs from {URLS_FILE.name}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = {f.name for f in OUTPUT_DIR.glob("*.pdf")}

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}

    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(DELAY)

        # Fetch page
        try:
            r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                print(f"  [{i+1}] HTTP {r.status_code} — {url}")
                log_failure(url, f"HTTP {r.status_code}")
                stats["failed"] += 1
                continue
        except requests.RequestException as e:
            print(f"  [{i+1}] Fetch failed — {url}: {e}")
            log_failure(url, f"Fetch error: {e}")
            stats["failed"] += 1
            continue

        # Extract metadata + PDF link
        title, author, pdf_url = extract_pdf_info(r.text, url)

        if not pdf_url:
            print(f"  [{i+1}] No PDF link found — {url}")
            log_failure(url, "No PDF link on page")
            stats["failed"] += 1
            continue

        filename = make_filename(author, url)

        if filename in existing:
            print(f"  [{i+1}] Exists, skipping — {filename}")
            stats["skipped"] += 1
            continue

        # Download PDF
        try:
            pdf_r = requests.get(pdf_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if pdf_r.status_code != 200:
                print(f"  [{i+1}] PDF download HTTP {pdf_r.status_code} — {pdf_url}")
                log_failure(url, f"PDF download HTTP {pdf_r.status_code}")
                stats["failed"] += 1
                continue
        except requests.RequestException as e:
            print(f"  [{i+1}] PDF download failed — {pdf_url}: {e}")
            log_failure(url, f"PDF download error: {e}")
            stats["failed"] += 1
            continue

        out_path = OUTPUT_DIR / filename
        out_path.write_bytes(pdf_r.content)
        size_kb = len(pdf_r.content) / 1024
        existing.add(filename)
        stats["downloaded"] += 1

        print(f"  [{i+1}] {title or filename} — {filename} ({size_kb:.0f} KB)")

    print(f"\n{'=' * 60}")
    print(f"Done.")
    print(f"  Downloaded : {stats['downloaded']}")
    print(f"  Skipped    : {stats['skipped']}")
    print(f"  Failed     : {stats['failed']}")
    print(f"  Output     : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
