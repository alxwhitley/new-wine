#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "========================================"
echo "  Step 1/3: Scrape YouTube transcripts"
echo "========================================"
python3 scripts/scrape_youtube.py

echo ""
echo "========================================"
echo "  Step 2/3: Clean transcripts via Groq"
echo "========================================"
python3 scripts/clean_transcripts.py

echo ""
echo "========================================"
echo "  Step 3/3: Ingest into Supabase"
echo "========================================"
python3 scripts/ingest.py

echo ""
echo "========================================"
echo "  YouTube pipeline complete"
echo "========================================"
