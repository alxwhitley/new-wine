# Rhemata — Claude Code Context

## Project Overview
Rhemata is an AI-powered theological research tool for charismatic Christians. RAG-based chat interface with inline citations. Modeled after Magisterium AI (product) and Perplexity (UX).

---

## Directory Structure
```
/Users/alexwhitley/Desktop/rhemata/
├── sources/
│   ├── youtube/               # YouTube transcript pipeline
│   │   ├── raw/               # Freshly scraped transcripts
│   │   ├── cleaned/           # Groq-cleaned, ready for ingest
│   │   ├── ingested/          # Already in Supabase
│   │   └── youtube_tracker.xlsx
│   ├── magazine/              # New Wine Magazine pipeline
│   │   ├── 01_to_extract/     # Drop PDFs here (~198 issues)
│   │   ├── 02_extracted/      # Per-issue .md articles + raw_text.txt
│   │   ├── 03_approved/       # Reviewed and approved for ingest
│   │   ├── 04_ingested/       # Completed issues
│   │   ├── 05_archived/       # Original PDFs after extraction
│   │   └── rhemata_tracker.xlsx
│   └── documents/             # Non-copyrighted docs (sermons, papers)
│       └── ingested/          # Already in Supabase
├── scripts/                   # All pipeline scripts
│   ├── scrape_youtube.py      # YouTube transcript scraper (yt-dlp + Supabase dedupe)
│   ├── clean_transcripts.py   # Clean raw transcripts via Groq Llama 3.3 70B
│   ├── extract_magazine.py    # 3-pass Gemini/Groq extraction pipeline
│   ├── ingest_magazine.py     # Supabase ingestion from .md files with frontmatter
│   ├── ingest.py              # Standalone PDF/docx/txt ingestion with auto-tagging
│   ├── tag_existing_articles.py   # Backfill topic_tags on existing articles via Groq
│   └── tag_sermons_transcripts.py # Backfill topic_tags on sermons/transcripts/papers via Groq
├── taxonomy.md                # 100-tag topic taxonomy (8 categories)
├── migrations/                # SQL migrations (run in Supabase SQL Editor)
├── CLAUDE.md                  # This file
├── SKILL.md                   # Full project skill context
├── backend/
│   ├── app/                   # FastAPI Python package
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── auth.py            # JWT auth via Supabase JWKS
│   │   ├── .env               # Environment variables
│   │   ├── routers/
│   │   │   ├── chat.py        # /chat endpoint — retrieval + LLM
│   │   │   ├── search.py      # /search + /search/documents endpoints
│   │   │   ├── document.py    # /document/{id} + /document/{id}/article
│   │   │   └── ingest.py      # /ingest endpoint
│   │   ├── services/
│   │   │   ├── embeddings.py
│   │   │   ├── chunker.py
│   │   │   ├── metadata.py
│   │   │   └── extractor.py
│   │   ├── db/
│   │   │   └── supabase.py
│   │   └── system_prompt.txt
│   ├── requirements.txt       # Pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml          # Locks Python 3.9
└── frontend/                  # Next.js 16 frontend (Vercel)
    ├── package.json
    └── ...
```

---

## Key Commands

### Start Backend
```bash
cd /Users/alexwhitley/Desktop/rhemata
kill -9 $(lsof -t -i:8000) 2>/dev/null; python3 -m uvicorn app.main:app --app-dir backend --reload --log-level debug
```

### Start Frontend
```bash
cd /Users/alexwhitley/Desktop/rhemata/frontend && npm run dev
# Runs at http://localhost:3000
```

### Ingest Documents (standalone)
```bash
cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/ingest.py
```

### Magazine Pipeline
```bash
cd /Users/alexwhitley/Desktop/rhemata
# Step 1: Extract — PDFs in sources/magazine/01_to_extract/ → sources/magazine/02_extracted/
python3 scripts/extract_magazine.py
# Step 2: Review — manually move approved articles to sources/magazine/03_approved/
# Step 3: Ingest — sources/magazine/03_approved/ → Supabase
python3 scripts/ingest_magazine.py
```

### YouTube Pipeline
```bash
cd /Users/alexwhitley/Desktop/rhemata
python3 scripts/scrape_youtube.py      # Scrape → sources/youtube/raw/
python3 scripts/clean_transcripts.py   # Clean via Groq → sources/youtube/cleaned/
python3 scripts/ingest.py              # Ingest cleaned transcripts → Supabase
```

### Backfill Topic Tags
```bash
cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/tag_existing_articles.py
cd /Users/alexwhitley/Desktop/rhemata && python3 scripts/tag_sermons_transcripts.py
```

### Kill Port 8000
```bash
kill -9 $(lsof -t -i:8000)
```

---

## Tech Stack
- **Frontend:** Next.js 16 (React 19), Tailwind CSS 4 — deploys to Vercel
- **Backend:** Python 3.9 / FastAPI — deploys to Railway
- **Database:** Supabase (PostgreSQL + pgvector)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dims)
- **Chat / Query Expansion / Metadata / Tagging / Transcript Cleaning LLM:** Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- **Vision / OCR (magazine extraction):** Gemini 2.5 Flash (`gemini-2.5-flash`) via `google-genai` SDK
- **Markdown rendering:** `react-markdown` + `@tailwindcss/typography`
- **Removed:** Anthropic Claude fully removed (April 2026), GPT-4o Vision (replaced by Gemini 2.5 Flash)

---

## Database
- **Supabase** with pgvector enabled
- Tables: `documents`, `chunks`, `guest_sessions`, `conversations`, `messages`
- `documents.source_type` — `'sermon'` | `'background'` | `'magazine_article'`
- `documents.source_kind` — taxonomy field (e.g. `'magazine_article'`)
- `documents.citation_mode` — `'citable'` | `'silent_context'`
- `documents.is_copyrighted` — boolean, derived from folder path during ingest
- `documents.topic_tags` — text[] assigned from taxonomy
- `documents.fts_weighted` — tsvector on title, author, source_name, topic_tags
- Vector similarity via `match_chunks` SQL function (HNSW index, `hnsw.ef_search=200`)
- Hybrid retrieval: query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) → top 10
- `search_documents` RPC: document-level FTS with highlighted snippets via ts_headline

---

## Key Decisions
- CORS middleware enabled — `ALLOWED_ORIGINS` env var (comma-separated)
- Page-level citations (not chunk-level)
- Two-tier content: citable vs silent_context (controlled by `citation_mode`)
- Magazine chunking: tiktoken cl100k_base, 550 tokens target, 80 overlap
- Standalone ingest: recursive character text splitting, 1000 char chunks, 200 char overlap
- k=10 retrieval post-RRF
- Single-column PDFs only — no multi-column OCR needed yet
- Bible Study articles excluded from extraction pipeline
- Topic tagging: 100-tag taxonomy, validated against VALID_TAGS set, retry if < 3 valid
- is_copyrighted derived from folder path: `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false

---

## Environment Variables (in backend/app/.env)
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY` — Gemini 2.5 Flash for magazine extraction
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `INCLUDE_COPYRIGHTED` — `true`/`false` (default `true` in chat.py, `false` in search.py)
- `ALLOWED_ORIGINS`

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/extract_magazine.py` | 3-pass Gemini/Groq extraction pipeline (Vision → Segmentation → QA) |
| `scripts/ingest_magazine.py` | Ingest approved .md articles from sources/magazine/03_approved/ into Supabase |
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal) |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run) |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

---

## How to Work on This Project
- Alex works fast — short messages, direct feedback
- Surface risks before building, not after
- All code changes stay in Claude Code — don't suggest manual edits unless trivial (1-2 lines)
- Read output directly — never ask Alex to copy-paste terminal output
- Check actual files before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
