#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "========================================"
echo "  Step 1/4: Scrape YouTube transcripts"
echo "========================================"
python3 scripts/scrape_youtube.py

echo ""
echo "========================================"
echo "  Step 2/4: Clean transcripts via Groq"
echo "========================================"
python3 scripts/clean_transcripts.py

echo ""
echo "========================================"
echo "  Step 3/4: Whisper transcribe (no_captions queue)"
echo "========================================"
python3 scripts/whisper_transcribe.py

echo ""
echo "========================================"
echo "  Step 4/4: Ingest into Supabase"
echo "========================================"
python3 scripts/ingest.py

echo ""
echo "========================================"
echo "  YouTube pipeline complete"
echo "========================================"
