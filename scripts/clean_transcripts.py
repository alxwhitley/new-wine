#!/usr/bin/env python3
"""
clean_transcripts.py
Cleans YouTube sermon transcripts using Groq Llama 3.3 70B.
Strips ads, sponsor reads, non-speech markers, and caption artifacts.
Preserves all theological content verbatim.
"""

import os
import sys
import glob
import shutil
from groq import Groq

# ── Config ────────────────────────────────────────────────────────────────────
ENV_PATH    = "/Users/alexwhitley/Desktop/rhemata/backend/app/.env"
INPUT_DIR   = "/Users/alexwhitley/Desktop/rhemata/sources/youtube/raw"
OUTPUT_DIR  = "/Users/alexwhitley/Desktop/rhemata/sources/youtube/cleaned"
MODEL       = "llama-3.3-70b-versatile"
SEPARATOR   = "---"

CLEAN_PROMPT = (
    "You are cleaning a YouTube sermon transcript for a theological research database. "
    "Remove ALL advertisement segments, sponsor reads, and promotional content. "
    "Remove non-speech markers like [music], [laughter], [applause], [clears throat], [cough]. "
    "Remove auto-caption filler artifacts like repeated phrases or mid-sentence restarts. "
    "Preserve ALL theological content verbatim. "
    "Return only the cleaned text with no commentary or preamble."
)

# ── Load .env ─────────────────────────────────────────────────────────────────
def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"ERROR: .env not found at {path}")
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

# ── Clean via Groq ───────────────────────────────────────────────────────────
def clean_text(client, raw_text):
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[
            {"role": "user", "content": f"{CLEAN_PROMPT}\n\n{raw_text}"}
        ]
    )
    return (response.choices[0].message.content or "").strip()

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    load_env(ENV_PATH)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("ERROR: GROQ_API_KEY not found in .env")

    client = Groq(api_key=api_key)

    txt_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.txt")))
    if not txt_files:
        print(f"No .txt files found in {INPUT_DIR}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Found {len(txt_files)} file(s) to process.\n")
    print(f"{'File':<50} {'Original':>10} {'Cleaned':>10} {'Reduction':>10}")
    print("-" * 84)

    for filepath in txt_files:
        filename = os.path.basename(filepath)

        with open(filepath, "r", encoding="utf-8") as f:
            full_content = f.read()

        # Split on first "---" separator
        if SEPARATOR in full_content:
            parts = full_content.split(SEPARATOR, 1)
            header = parts[0]          # metadata block (title, author, etc.)
            raw_body = parts[1].lstrip("\n")
        else:
            # No separator found — treat entire file as body, no header
            header = ""
            raw_body = full_content

        original_word_count = len(raw_body.split())

        try:
            cleaned_body = clean_text(client, raw_body)
        except Exception as e:
            print(f"  ERROR on {filename}: {e}")
            continue

        cleaned_word_count = len(cleaned_body.split())
        reduction = original_word_count - cleaned_word_count
        pct = (reduction / original_word_count * 100) if original_word_count else 0

        # Reconstruct file with header + cleaned body
        if header:
            new_content = header + SEPARATOR + "\n" + cleaned_body + "\n"
        else:
            new_content = cleaned_body + "\n"

        # Write cleaned file to output dir
        dest = os.path.join(OUTPUT_DIR, filename)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Remove original from input dir
        os.remove(filepath)

        print(f"{filename:<50} {original_word_count:>10,} {cleaned_word_count:>10,} {f'-{pct:.1f}%':>10}")

    print("\nDone.")

if __name__ == "__main__":
    main()
