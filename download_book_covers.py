#!/usr/bin/env python3
"""
Download book covers from Open Library Covers API.
Usage: python3 download_book_covers.py
Images saved to: frontend/public/images/books/
"""

import os
import requests
import time
from pathlib import Path

# Open Library Covers API: https://covers.openlibrary.org/b/isbn/{ISBN}-L.jpg
# Falls back to title search if ISBN not found

BOOKS = [
    # Derek Prince
    {"filename": "blessing-or-curse.jpg",           "isbn": "9780800794088"},
    {"filename": "they-shall-expel-demons.jpg",     "isbn": "9780800758509"},
    {"filename": "shaping-history-prayer-fasting.jpg", "isbn": "9780800793494"},
    {"filename": "spiritual-warfare.jpg",            "isbn": "9780883682219"},
    {"filename": "foundational-truths.jpg",          "isbn": "9781782631408"},
    {"filename": "gods-medicine-bottle.jpg",         "isbn": "9780883681343"},
    {"filename": "holy-spirit-in-you.jpg",           "isbn": "9780883685112"},

    # Bob Mumford
    {"filename": "agape-road.jpg",                   "isbn": "9780830729975"},
    {"filename": "take-another-look-at-guidance.jpg","isbn": "9780882706191"},
    {"filename": "purpose-of-temptation.jpg",        "isbn": "9780884190646"},
    {"filename": "the-king-and-you.jpg",             "isbn": "9780882706207"},
    {"filename": "fifteen-steps-out.jpg",            "isbn": "9780882706214"},

    # Ern Baxter
    {"filename": "thy-kingdom-come.jpg",             "isbn": "9780940252004"},

    # Charles Simpson
    {"filename": "the-challenge-to-care.jpg",        "isbn": "9780892742073"},
    {"filename": "courageous-living.jpg",            "isbn": "9780892741526"},
    {"filename": "straight-answers-prayer.jpg",      "isbn": "9780892741731"},

    # Don Basham
    {"filename": "face-up-with-a-miracle.jpg",       "isbn": "9780882706009"},
    {"filename": "deliver-us-from-evil.jpg",         "isbn": "9780882706634"},
    {"filename": "handbook-holy-spirit-baptism.jpg", "isbn": "9780882706641"},
    {"filename": "true-and-false-prophets.jpg",      "isbn": "9780883681039"},

    # John Bevere
    {"filename": "bait-of-satan.jpg",                "isbn": "9781599790244"},
    {"filename": "under-cover.jpg",                  "isbn": "9780785268789"},
    {"filename": "driven-by-eternity.jpg",           "isbn": "9780446578011"},
    {"filename": "good-or-god.jpg",                  "isbn": "9781933185743"},
    {"filename": "awe-of-god.jpg",                   "isbn": "9781954201231"},
    {"filename": "killing-kryptonite.jpg",           "isbn": "9781944967215"},

    # Michael Brown
    {"filename": "our-hands-are-stained.jpg",        "isbn": "9780800792954"},
    {"filename": "answering-jewish-objections.jpg",  "isbn": "9780801063343"},
    {"filename": "whatever-happened-power-of-god.jpg","isbn": "9781560431428"},
    {"filename": "authentic-fire.jpg",               "isbn": "9780615917788"},
    {"filename": "hyper-grace.jpg",                  "isbn": "9781621365631"},
    {"filename": "revolution-in-the-church.jpg",     "isbn": "9780800793012"},

    # Jack Deere
    {"filename": "surprised-by-power-of-spirit.jpg", "isbn": "9780310209775"},
    {"filename": "surprised-by-voice-of-god.jpg",    "isbn": "9780310209812"},
    {"filename": "even-in-our-darkness.jpg",         "isbn": "9780310341130"},
    {"filename": "still-surprised-by-spirit.jpg",    "isbn": "9780310109082"},

    # Oswald J. Smith
    {"filename": "passion-for-souls.jpg",            "isbn": "9780825474323"},
    {"filename": "the-man-god-uses.jpg",             "isbn": "9780825474330"},
    {"filename": "enduement-of-power.jpg",           "isbn": "9780825474316"},
    {"filename": "the-revival-we-need.jpg",          "isbn": "9780825474309"},
]

def download_cover(book, output_dir):
    filename = book["filename"]
    isbn = book["isbn"]
    output_path = output_dir / filename

    if output_path.exists():
        print(f"  SKIP (exists): {filename}")
        return True

    # Try Open Library Covers API (large size)
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    try:
        r = requests.get(url, timeout=10)
        # Open Library returns a 1x1 gif if not found
        if r.status_code == 200 and len(r.content) > 1000:
            with open(output_path, "wb") as f:
                f.write(r.content)
            print(f"  OK: {filename}")
            return True
        else:
            print(f"  NOT FOUND on OpenLibrary: {filename} (isbn: {isbn})")
            return False
    except Exception as e:
        print(f"  ERROR: {filename} — {e}")
        return False

def main():
    # Find the output directory relative to this script
    script_dir = Path(__file__).resolve().parent
    # Try to find frontend/public/images/books
    output_dir = script_dir / "frontend" / "public" / "images" / "books"

    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        print("Make sure you run this from the rhemata project root.")
        return

    print(f"Downloading {len(BOOKS)} book covers to: {output_dir}\n")
    success, failed = 0, 0

    for book in BOOKS:
        result = download_cover(book, output_dir)
        if result:
            success += 1
        else:
            failed += 1
        time.sleep(0.5)  # be polite to Open Library

    print(f"\nDone. {success} downloaded, {failed} not found.")
    if failed > 0:
        print("For missing covers, manually download and drop into frontend/public/images/books/")

if __name__ == "__main__":
    main()
