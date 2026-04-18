#!/usr/bin/env python3
"""
whisper_transcribe.py — Download audio from a URL, transcribe with Whisper,
clean via Groq, and write a sermon-ready .txt to sources/youtube/cleaned/
(same format as scrape_youtube.py output) for ingest.py to pick up.

Two modes:
  1. Single URL (CLI args):
     python3 scripts/whisper_transcribe.py --url ... --title ... --speaker ... --channel ...
  2. Batch (no args): processes every .txt in sources/youtube/no_captions/,
     moves processed stubs to sources/youtube/no_captions/done/
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

OUTPUT_DIR      = ROOT / "sources" / "youtube" / "cleaned"
NO_CAPTIONS_DIR = ROOT / "sources" / "youtube" / "no_captions"
DONE_DIR        = NO_CAPTIONS_DIR / "done"
WHISPER_MODEL = "medium"
GROQ_MODEL = "llama-3.3-70b-versatile"
CHUNK_WORDS = 6000

CLEANING_PROMPT = (
    "You are cleaning a YouTube sermon transcript for a theological research "
    "database. Remove ALL advertisement segments, sponsor reads, and promotional "
    "content. Remove non-speech markers like [music], [laughter], [applause], "
    "[clears throat], [cough]. Remove auto-caption filler artifacts like repeated "
    "phrases or mid-sentence restarts. Preserve ALL theological content verbatim. "
    "Return only the cleaned text with no commentary or preamble."
)


def slugify(title: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s]", "", title.lower())
    s = re.sub(r"\s+", "_", s.strip())
    return s[:max_len].rstrip("_")


def download_audio(url: str, out_dir: Path) -> Path:
    """Download best audio as mp3 via yt-dlp. Returns the path to the mp3."""
    out_template = str(out_dir / "audio.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-x", "--audio-format", "mp3",
        "-o", out_template,
        url,
    ]
    subprocess.run(cmd, check=True)
    mp3_path = out_dir / "audio.mp3"
    if not mp3_path.exists():
        raise RuntimeError(f"Audio download failed — no file at {mp3_path}")
    return mp3_path


def transcribe(audio_path: Path) -> str:
    """Transcribe audio using Whisper medium."""
    import whisper
    print(f"  Loading Whisper model: {WHISPER_MODEL}")
    model = whisper.load_model(WHISPER_MODEL)
    print(f"  Transcribing {audio_path.name}...")
    result = model.transcribe(str(audio_path), fp16=False, language="en")
    return result["text"].strip()


def clean_transcript(raw: str) -> str:
    """Send transcript to Groq for cleaning. Chunk at CHUNK_WORDS to stay
    within the 8192 output token limit."""
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    words = raw.split()

    if len(words) <= CHUNK_WORDS:
        chunks = [raw]
    else:
        chunks = [
            " ".join(words[i:i + CHUNK_WORDS])
            for i in range(0, len(words), CHUNK_WORDS)
        ]

    print(f"  Cleaning via Groq ({len(chunks)} chunk(s), {len(words):,} words)...")
    cleaned_parts = []
    for i, chunk in enumerate(chunks, 1):
        print(f"    Chunk {i}/{len(chunks)}...")
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": CLEANING_PROMPT},
                {"role": "user", "content": chunk},
            ],
        )
        cleaned_parts.append((response.choices[0].message.content or "").strip())

    return "\n\n".join(cleaned_parts)


def write_transcript(
    out_path: Path,
    title: str,
    speaker: str,
    channel: str,
    url: str,
    cleaned: str,
) -> None:
    header = (
        f"TITLE: {title}\n"
        f"SPEAKER: {speaker}\n"
        f"CHANNEL: {channel}\n"
        f"URL: {url}\n"
        f"SOURCE_URL: {url}\n"
        f"PUBLISHED: NA\n"
        f"DURATION_MIN: 0.0\n"
        f"SOURCE_TYPE: sermon\n"
        f"---\n\n"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + cleaned, encoding="utf-8")


def parse_stub(path: Path) -> dict:
    """Parse a no_captions/ metadata .txt file. Returns dict with URL, TITLE,
    SPEAKER, CHANNEL."""
    meta = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().upper()] = val.strip()
    return meta


def process_video(url: str, title: str, speaker: str, channel: str) -> Path:
    """Run the full pipeline for a single URL. Returns the output path."""
    fname = slugify(title) + ".txt"
    out_path = OUTPUT_DIR / fname

    print(f"URL:      {url}")
    print(f"Title:    {title}")
    print(f"Speaker:  {speaker}")
    print(f"Channel:  {channel}")
    print(f"Output:   {out_path}\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        print("Downloading audio...")
        audio_path = download_audio(url, tmp_path)

        print("Transcribing...")
        raw = transcribe(audio_path)
        print(f"  {len(raw.split()):,} words transcribed")

        print("Cleaning transcript...")
        cleaned = clean_transcript(raw)
        print(f"  {len(cleaned.split()):,} words after cleaning")

    print(f"\nWriting {out_path}...")
    write_transcript(out_path, title, speaker, channel, url, cleaned)
    print(f"✓ Done: {out_path}")
    return out_path


def run_batch() -> None:
    """Process every stub in sources/youtube/no_captions/. Move processed
    stubs to done/ on success; leave failures in place."""
    if not NO_CAPTIONS_DIR.is_dir():
        print(f"No no_captions/ folder at {NO_CAPTIONS_DIR}")
        return

    stubs = sorted(p for p in NO_CAPTIONS_DIR.iterdir()
                   if p.is_file() and p.suffix == ".txt")
    if not stubs:
        print(f"No stubs to process in {NO_CAPTIONS_DIR}")
        return

    DONE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Found {len(stubs)} stub(s) to process\n")

    processed = failed = 0
    for i, stub in enumerate(stubs, 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(stubs)}] {stub.name}")
        print('=' * 60)
        meta = parse_stub(stub)
        missing = [k for k in ("URL", "TITLE", "SPEAKER", "CHANNEL") if not meta.get(k)]
        if missing:
            print(f"  ✗ Missing fields: {missing} — skipping")
            failed += 1
            continue
        try:
            process_video(meta["URL"], meta["TITLE"], meta["SPEAKER"], meta["CHANNEL"])
            dest = DONE_DIR / stub.name
            shutil.move(str(stub), str(dest))
            print(f"  Moved stub to: {dest}")
            processed += 1
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Done. {processed} processed, {failed} failed.")


def main():
    parser = argparse.ArgumentParser(description="Whisper transcribe + Groq clean")
    parser.add_argument("--url", help="YouTube or audio URL (single-video mode)")
    parser.add_argument("--title", help="Title of the sermon")
    parser.add_argument("--speaker", help="Speaker name")
    parser.add_argument("--channel", help="Channel name")
    parser.add_argument("--copyrighted", action="store_true",
                        help="(No-op — output always goes to sources/youtube/cleaned/, "
                             "which ingest.py treats as copyrighted by path)")
    args = parser.parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("✗ GROQ_API_KEY not set in backend/app/.env")
        sys.exit(1)

    # Batch mode — no single-video args supplied
    if not any([args.url, args.title, args.speaker, args.channel]):
        run_batch()
        return

    # Single-video mode — require all four
    missing = [k for k in ("url", "title", "speaker", "channel") if not getattr(args, k)]
    if missing:
        parser.error(
            f"single-video mode requires --{', --'.join(missing)} "
            f"(or run with no args to batch-process sources/youtube/no_captions/)"
        )

    process_video(args.url, args.title, args.speaker, args.channel)


if __name__ == "__main__":
    main()
