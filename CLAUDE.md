# Rhemata — Claude Code Context

## Project Overview
Rhemata is an AI-powered theological research tool for charismatic Christians. RAG-based chat interface with inline citations. Modeled after Magisterium AI (product) and Perplexity (UX).

---

## Directory Structure
```
/Users/alexwhitley/Desktop/rhemata/
├── extract_magazine.py        # GPT-4o Vision PDF extraction (scanned magazines)
├── merge_articles.py          # Detect & merge batch-split articles
├── ingest_magazine.py         # Supabase ingestion (documents + chunks + articles)
├── ingest.py                  # Standalone PDF/docx/txt ingestion script
├── pdf/                       # Source documents for ingestion
│   ├── open/                  # Non-copyrighted documents
│   ├── copyrighted/           # Copyrighted documents (is_copyrighted=true)
│   ├── magazine/              # Unprocessed magazine PDFs (extract_magazine.py input)
│   └── magazine_done/         # Processed magazine PDFs (moved here after extraction)
├── pipeline/                  # Extraction & ingestion artifacts
│   ├── raw_extracted/         # Raw GPT-4o Vision output (pre-merge)
│   ├── checkpoints/           # Per-issue extraction checkpoints
│   ├── needs_review/          # Articles that failed QA gate
│   ├── rhemata_tracker.xlsx   # Active extraction tracker (updated by extract_magazine.py)
│   ├── merge_log.json         # Merge audit log
│   ├── ingestion_log.json     # Per-article ingestion log
│   ├── qa_log.json            # QA failures log
│   └── blocked_batches.json   # Failed GPT-4o batch log
├── corpus/                    # Clean text ready for ingestion
│   ├── open/                  # Non-copyrighted merged articles
│   └── copyrighted/           # Copyrighted merged articles (New Wine Magazine)
├── migrations/                # SQL migrations (run in Supabase SQL Editor)
├── CLAUDE.md                  # This file
├── SKILL.md                   # Full project skill context
├── backend/app/               # Backend package
│   ├── main.py                # FastAPI app entry point
│   ├── .env                   # Environment variables
│   ├── routers/
│   │   ├── chat.py            # /chat endpoint — retrieval + LLM
│   │   ├── ingest.py          # /ingest endpoint
│   │   ├── search.py          # /search endpoint
│   │   └── document.py        # /document endpoint
│   ├── services/
│   │   ├── embeddings.py
│   │   ├── chunker.py
│   │   ├── metadata.py
│   │   └── extractor.py
│   └── db/
│       └── supabase.py
└── frontend/                  # Next.js frontend (Vercel)
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

### Ingest PDFs (standalone)
```bash
cd /Users/alexwhitley/Desktop/rhemata && python3 ingest.py
```

### Magazine Pipeline (3-step)
```bash
cd /Users/alexwhitley/Desktop/rhemata
# Step 1: Extract — PDFs in pdf/magazine/ → raw_extracted/
python3 extract_magazine.py
# Step 2: Merge — raw_extracted/ → corpus/copyrighted/
python3 merge_articles.py
# Step 3: Ingest — corpus/copyrighted/ → Supabase
python3 ingest_magazine.py
```

### Kill Port 8000
```bash
kill -9 $(lsof -t -i:8000)
```

---

## Tech Stack
- **Frontend:** Next.js (React), Tailwind — deploys to Vercel
- **Backend:** Python 3.9 / FastAPI — deploys to Railway
- **Database:** Supabase (PostgreSQL + pgvector)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dims)
- **Chat / Query Expansion / Metadata LLM:** Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- **PDF Extraction (magazines):** OpenAI GPT-4o Vision
- **Anthropic:** Fully removed from codebase (April 2026)

---

## Database
- **Supabase** with pgvector enabled
- Tables: `documents`, `chunks`, `articles`, `guest_sessions`, `conversations`, `messages`
- `documents.source_type` — `'sermon'` | `'background'` | `'magazine_article'`
- `documents.source_kind` — taxonomy field (e.g. `'magazine_article'`)
- `documents.citation_mode` — `'citable'` | `'silent_context'`
- `documents.is_copyrighted` — boolean, default false
- Vector similarity via `match_chunks` SQL function (HNSW index, `hnsw.ef_search=200`)
- Both `match_chunks` and `search_chunks_fts` accept `include_copyrighted` boolean param
- Hybrid retrieval: query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) → top 10

---

## Key Decisions
- CORS middleware enabled — `ALLOWED_ORIGINS` env var (comma-separated)
- Page-level citations (not chunk-level)
- Two-tier content: citable vs silent_context (controlled by `citation_mode`)
- Magazine chunking: tiktoken cl100k_base, 600 tokens target, 80 overlap
- Standalone ingest: recursive character text splitting, 1000 char chunks, 200 char overlap
- k=10 retrieval post-RRF
- Single-column PDFs only — no multi-column OCR needed yet
- New Wine Magazine pipeline operational (extract → merge → ingest)

---

## Environment Variables (in backend/app/.env)
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `INCLUDE_COPYRIGHTED` — `true`/`false` (default `true` in chat.py, `false` in search.py)
- `ALLOWED_ORIGINS`

---

## Recent Changes (April 2026)

### Session 2026-04-07
- **Anthropic fully removed** — all LLM calls swapped to Groq Llama 3.3 70B (chat, query expansion, metadata, ingest.py)
- `anthropic` package removed from `backend/requirements.txt`
- `extract_magazine.py`: added `load_dotenv()` fix
- `ingest.py`: swapped from Anthropic to Groq client
- Full 6-category audit passed on 9 pipeline files

### This session
- **Tracker consolidated** — moved active tracker from `Desktop/Cowork OS/Rhemata/rhemata_tracker.xlsx` into `pipeline/rhemata_tracker.xlsx`
- Deleted stale orphaned `pipeline/extraction_tracker.xlsx`
- Updated `TRACKER_PATH` in `extract_magazine.py` to `pipeline/rhemata_tracker.xlsx`
- Confirmed no other scripts reference old paths

---

## How to Work on This Project
- Alex works fast — short messages, direct feedback
- Surface risks before building, not after
- All code changes stay in Claude Code — don't suggest manual edits unless trivial (1-2 lines)
- Read output directly — never ask Alex to copy-paste terminal output
- Check actual files before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
