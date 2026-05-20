#!/usr/bin/env python3
"""Download public-domain PDFs from CCEL into pdf/open/."""

import os
import requests
from pathlib import Path

DEST_DIR = Path(__file__).resolve().parent.parent / "pdf" / "open"

BOOKS = [
    {"filename": "murray_with_christ_in_school_of_prayer.pdf", "url": "https://www.ccel.org/ccel/m/murray/prayer/cache/prayer.pdf"},
    {"filename": "murray_deeper_christian_life.pdf", "url": "https://ccel.org/ccel/m/murray/deeper/cache/deeper.pdf"},
    {"filename": "murray_new_life.pdf", "url": "https://ccel.org/ccel/m/murray/new_life/cache/new_life.pdf"},
    {"filename": "murray_waiting_on_god.pdf", "url": "https://ccel.org/ccel/m/murray/waiting/cache/waiting.pdf"},
    {"filename": "bounds_power_through_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/power/cache/power.pdf"},
    {"filename": "bounds_weapon_of_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/weapon/cache/weapon.pdf"},
    {"filename": "bounds_prayer_and_praying_men.pdf", "url": "https://www.ccel.org/ccel/b/bounds/prayingmen/cache/prayingmen.pdf"},
    {"filename": "bounds_necessity_of_prayer.pdf", "url": "https://ccel.org/ccel/b/bounds/necessity/cache/necessity.pdf"},
    {"filename": "bounds_essentials_of_prayer.pdf", "url": "https://www.ccel.org/ccel/b/bounds/essentials/cache/essentials.pdf"},
    {"filename": "torrey_person_and_work_of_holy_spirit.pdf", "url": "https://ccel.org/ccel/t/torrey/work_holy_spirit/cache/work_holy_spirit.pdf"},
    {"filename": "torrey_how_to_pray.pdf", "url": "https://www.ccel.org/t/torrey/pray/cache/pray.pdf"},
    {"filename": "finney_power_from_on_high.pdf", "url": "https://www.ccel.org/ccel/f/finney/power/cache/power.pdf"},
    {"filename": "finney_lectures_on_revivals.pdf", "url": "https://ccel.org/ccel/f/finney/revivals/cache/revivals.pdf"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def main():
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for book in BOOKS:
        dest = DEST_DIR / book["filename"]

        if dest.exists():
            print(f"  SKIPPED  {book['filename']} (already exists)")
            skipped += 1
            continue

        print(f"  DOWNLOADING  {book['filename']} ...")
        try:
            resp = requests.get(book["url"], headers=HEADERS, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            print(f"  OK  {book['filename']} ({len(resp.content) / 1024:.0f} KB)")
            downloaded += 1
        except Exception as e:
            print(f"  FAILED  {book['filename']}: {e}")
            failed += 1

    print(f"\nDone. {downloaded} downloaded, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
