# Rhemata — Claude Code Context

## Project Overview
Rhemata is an AI-powered theological research tool for charismatic Christians. RAG-based chat interface with inline citations. Modeled after Magisterium AI (product) and Perplexity (UX).

---

## Directory Structure
```
/Users/alexwhitley/Desktop/rhemata/
├── ingest.py                  # Standalone PDF ingestion script
���── pdf/                       # Source documents for ingestion
│   ├── open/                  # Non-copyrighted documents
│   └── copyrighted/           # Copyrighted documents (is_copyrighted=true)
├── migrations/                # SQL migrations (run in Supabase SQL Editor)
├── CLAUDE.md                  # This file
└── backend/app/               # Backend package
    ├── main.py                # FastAPI app entry point
    ├── .env                   # Environment variables
    ├── routers/
    │   ├── chat.py            # /chat endpoint — retrieval + LLM
    │   ├── ingest.py          # /ingest endpoint
    │   ├── search.py          # /search endpoint
    │   └── document.py        # /document endpoint
    ���── services/
    │   ├── embeddings.py
    │   ├── chunker.py
    │   ├── metadata.py
    │   └── extractor.py
    └── db/
        └── supabase.py

/Users/alexwhitley/Desktop/rhemata/frontend/
├── package.json
└── ...                        # Next.js frontend
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

### Ingest PDFs
```bash
# Drop files into pdf/open/ or pdf/copyrighted/
cd /Users/alexwhitley/Desktop/rhemata && python3 ingest.py
```

### Kill Port 8000
```bash
kill -9 $(lsof -t -i:8000)
```

---

## Tech Stack
- **Frontend:** Next.js (React), Tailwind — deploys to Vercel
- **Backend:** Python / FastAPI — deploys to Railway
- **Database:** Supabase (PostgreSQL + pgvector)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dims)
- **Chat LLM:** Anthropic Claude Haiku
- **OCR:** pdfplumber (primary), Claude Vision (fallback)

---

## Database
- **Supabase** with pgvector enabled
- Two tables: `documents` and `chunks`
- `documents.source_type` — `'sermon'` (citable) | `'background'` (informs LLM, never cited)
- `documents.is_copyrighted` — boolean, default false. Copyrighted docs stay in DB but are excluded from retrieval when `INCLUDE_COPYRIGHTED=false`
- Vector similarity via `match_chunks` SQL function (HNSW index)
- Both `match_chunks` and `search_chunks_fts` accept `include_copyrighted` boolean param

---

## Key Decisions
- CORS middleware enabled for `http://localhost:3000`
- Page-level citations (not chunk-level)
- Two-tier content: sermon = cited, background = silent context
- Recursive paragraph chunking (not fixed-size)
- k=5 retrieval (bump to 10-15 when more content ingested)
- Single-column PDFs only — no multi-column OCR needed yet
- New Wine Magazine on hold until copyright cleared

---

## Environment Variables (in backend/app/.env)
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `INCLUDE_COPYRIGHTED` — `true`/`false` (default `false`). Controls whether copyrighted documents appear in search results

---

## How to Work on This Project
- Alex works fast — short messages, direct feedback
- Surface risks before building, not after
- All code changes stay in Claude Code — don't suggest manual edits unless trivial (1-2 lines)
- Read output directly — never ask Alex to copy-paste terminal output
- Check actual files before assuming structure
