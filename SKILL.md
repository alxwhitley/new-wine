---
name: rhemata
description: Full project context for Rhemata — Alex's AI-powered theological research tool for charismatic Christians. Read this skill at the start of every Rhemata work session before doing anything else. Trigger whenever Alex mentions Rhemata, the theological research app, the RAG project, or any of its components (ingestion, chat, citations, frontend, backend).
---

# Rhemata — Project Skill

## What It Is
Rhemata (ῥήματα) is an AI-powered theological research tool targeting charismatic and Spirit-filled Christians. Users ask natural language questions and receive answers drawn from a curated library of theological documents, with inline citations pointing back to the source.

The primary product model is **Magisterium AI**. The primary UX model is **Perplexity** — centered chat input, inline citations, clickable source panel.

---

## Who It's For
Charismatic and Spirit-filled Christians who want to research theology from within their tradition. The content library is built from documents Alex personally owns and has rights to — sermon outlines, theology papers, and similar material. New Wine Magazine (300 issues) is a future content source pending copyright clearance and must not be ingested yet.

---

## Repo & Git
- Git repo initialized and pushed to `alxwhitley/rhemata` on GitHub
- `.gitignore` covers `.env`, `.env.local`, `__pycache__`, `.venv`, `node_modules`, `.next`, `.DS_Store`

---

## Monorepo Structure

```
repo/
├── frontend/          # Next.js app (Vercel)
├── backend/
│   ├── app/           # FastAPI Python package
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routers/
│   │   ├── services/
│   │   ├── db/
│   │   └── system_prompt.txt
│   ├── requirements.txt   # pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml      # locks Python 3.9
└── pdf/               # source documents for ingestion
```

- All imports use `from app.x import y` (absolute, not relative)
- `requirements.txt` pinned to exact versions, includes `tiktoken`
- Railway start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (React), Tailwind, deployed to Vercel |
| Backend | Python 3.9 / FastAPI, deployed to Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat / LLM | Anthropic Claude Haiku |
| Retrieval | Hybrid search: pgvector + PostgreSQL FTS, fused via RRF |
| OCR | EasyOCR + Claude Vision (fallback) |

---

## Architecture

**Frontend → Backend → Supabase → LLM**

1. User types a query in the chat interface
2. Frontend POSTs to `/chat` on the FastAPI backend (field: `question`, plus `anon_id` for guests)
3. Backend expands query into 3 semantic variants via Claude Haiku (`expand_query()`)
4. For each variant: pgvector cosine similarity (top 20) + PostgreSQL full-text search (top 20)
5. Results fused via Reciprocal Rank Fusion (RRF_K=60), deduplicated, top 10 selected
6. Backend assembles prompt: system instructions + retrieved chunks (tagged with `source_type`) + query
7. Claude Haiku generates a response, streamed back via SSE
8. Frontend renders response with inline citation tags

---

## Database Schema

**`documents` table** — one row per source document
- `id` (uuid)
- `title` (text)
- `author` (text)
- `source` (text)
- `year` (int)
- `issue` (text)
- `topic_tags` (text[])
- `file_path` (text)
- `source_type` (text) — `'sermon'` | `'background'`
- `source_name` (text)
- `url` (text, nullable) — source URL (e.g. YouTube link for scraped transcripts)
- `created_at` (timestamptz)

**`chunks` table** — one row per text chunk
- `id` (uuid)
- `document_id` (foreign key → documents)
- `content` (text)
- `embedding` (vector(1536))
- `chunk_index` (int)
- `page_number` (int)
- `source_hash` (text)
- `created_at` (timestamptz)

**`guest_sessions` table** — server-side guest query tracking
- `id` (uuid)
- `anon_id` (text, unique)
- `query_count` (int, default 0)
- `created_at` (timestamptz)
- `last_seen` (timestamptz)

**`conversations` table** — saved chat history for authenticated users
- `id` (uuid)
- `user_id` (uuid, FK → auth.users)
- `title` (text)
- `created_at` (timestamptz)

**`messages` table** — individual messages within conversations
- `id` (uuid)
- `conversation_id` (uuid, FK → conversations)
- `role` (text: 'user' | 'assistant')
- `content` (text)
- `created_at` (timestamptz)

---

## Key Decisions Already Made

- **HNSW indexing** over ivfflat for pgvector (faster, more accurate); `match_chunks` sets `hnsw.ef_search=200` (migration 003) to fix recall on small corpus
- **Page-level citations** — not chunk-level. The full page a chunk belongs to is surfaced as the citation context
- **Two-tier content model:**
  - `source_type = 'sermon'` — citable, renders citation tags in frontend
  - `source_type = 'background'` — informs LLM context silently, never cited
  - System prompt explicitly instructs Claude on this distinction; chunks tagged with `source_type` in prompt header
- **Metadata trimmed for LLM** — each chunk in the prompt only receives Title, Author, and chunk reference (no UUIDs, file paths, or topic tags)
- **Recursive character text splitting** — 1000 char chunks, 200 char overlap (20%), separators: `\n\n` → `\n` → `. ` → ` ` → `""`
- **Hybrid search with RRF** — query expansion (3 variants via Claude Haiku) → vector search + FTS per variant → Reciprocal Rank Fusion (K=60) → top 10 chunks. `/search` endpoint uses vector-only (no FTS/RRF)
- **k=10 retrieval** post-RRF (was k=5 with Cohere reranking, now replaced by hybrid search)
- **Claude Vision** as OCR fallback for corrupted/unreadable PDF pages
- **Single-column PDFs only** for now — current content is not multi-column, multi-column OCR logic not needed yet
- **CORS middleware** — `ALLOWED_ORIGINS` env var (comma-separated), updated with Vercel production URL
- **Guest query limit** — 6 free queries enforced server-side via `guest_sessions` table + `increment_guest_query` RPC; frontend sends `anon_id` (persisted in localStorage as `rhemata_anon_id`); 429 triggers login modal
- **JWT auth** via Supabase JWKS endpoint (`PyJWKClient`), no static secret needed

---

## Content Rules
- Only ingest documents that Alex personally owns or has rights to
- New Wine Magazine is on hold — do not plan ingestion until copyright is resolved
- Current documents are single-column — no multi-column OCR handling needed

---

## YouTube Scraping Pipeline
- Script: `/Users/alexwhitley/Desktop/Cowork OS/Rhemata/scrape_youtube.py`
- Tracker: `/Users/alexwhitley/Desktop/Cowork OS/Rhemata/rhemata_youtube_tracker.xlsx`
- Cookies: `/Users/alexwhitley/Desktop/Cowork OS/Rhemata/youtube_cookies.txt` (required — YouTube blocks without auth)
- Pipeline: yt-dlp (video listing with cookies) → `youtube-transcript-api` (transcript via cookies session) → Claude Haiku (cleaning) → structured .txt with metadata headers → `pdf/copyrighted/`
- .txt header format: `TITLE`, `SPEAKER`, `CHANNEL`, `SOURCE_URL`, `PUBLISHED`, `DURATION_MIN`, `SOURCE_TYPE` (parsed by `ingest.py` → `url` column)
- `ingest.py` supports `.pdf`, `.docx`, `.doc`, and `.txt` files
- `.txt` ingestion: parses KEY: VALUE headers before first blank line, extracts `SOURCE_URL` into `documents.url`
- `.docx` uses `python-docx`, `.doc` uses macOS `textutil`
- `ingest.py` scans `pdf/` root, `pdf/open/`, and `pdf/copyrighted/` directories
- **Python 3.9 constraint**: do not use `str | None` union syntax — use `Optional[str]` or untyped defaults

---

## Corpus
- 27 documents ingested (500 chunks)
- 17 open (sermon outlines, theology papers, Holy Spirit teaching — `.pdf`, `.docx`, `.doc` formats)
- 10 copyrighted (John Bevere TV YouTube transcripts, with `url` populated)

---

## UX Model
- Centered chat input as primary interaction (not a sidebar topic browser)
- Perplexity-style inline citations rendered as gold-highlighted tags
- Clicking a citation opens a source panel with document title, author, and page content
- Sidebar for conversation history (authenticated users); delete via inline confirm bar (three-dot → confirm row replaces conversation row)
- Auth flow: login modal triggered by AuthButton, sidebar sign-in link, or guest limit reached
- Supabase client used directly from frontend for conversations/messages CRUD (anon key, session managed by SDK)
- Guest users get 6 free queries before prompted to sign up

---

## Brand
- **Name:** Rhemata
- **Fonts:** Lora (headings/logo), Inter (UI/body)
- **Dark theme** — near-black backgrounds, warm neutrals
- **Gold accents** — `#b49238` (CTA), `#d4b96a` (citations)
- **Logo gradient:** blue-grey to muted rose-grey (vertical)
- **Voice:** Scholarly but accessible. Conviction, not performance. Serves the researcher, not the spectacle.

Full brand spec: `/mnt/project/rhemata-brand.md`

---

## Deployment

| Target | Status | Notes |
|---|---|---|
| Railway (backend) | Live, health check 200 | Root dir: `backend/`, Python 3.9 via nixpacks.toml |
| Vercel (frontend) | Live, end-to-end confirmed | Root dir: `frontend/` |
| Supabase | Live | PostgreSQL + pgvector |

### Backend env vars (Railway)
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `ALLOWED_ORIGINS`

### Frontend env vars (Vercel)
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## Remaining
- **RLS policies needed on `conversations` and `messages` tables** — frontend deletes (and all CRUD) use Supabase anon key from the browser; without DELETE policies, deletes silently fail and rows reappear on refresh. SELECT policies may also be missing.
- **`increment_guest_query()` SQL function missing from migrations** — called at `chat.py:200` but definition not in `migrations/`; must exist directly in Supabase or guest rate limiting silently fails
- **Remove delete trace logs** — `[DELETE TRACE]` console.logs in `sidebar.tsx`, `page.tsx`, and `useConversations.ts` should be removed once delete is confirmed working end-to-end
- **Run migration 003 in Supabase SQL Editor** (`migrations/003_fix_hnsw_ef_search.sql`) — converts `match_chunks` to PLPGSQL with `hnsw.ef_search=200` to fix vector search returning 0 results for many queries
- **YouTube cookies not yet exported** — scraper cannot pull new transcripts until Alex exports cookies from Arc (via "Get cookies.txt LOCALLY" extension) and saves to `Cowork OS/Rhemata/youtube_cookies.txt`
- **source_hash dedup unreliable** — re-ingesting the same files produces different hashes (possibly due to OS-level file metadata changes), causing duplicates. Consider switching dedup to title+author or file_path matching
- Gemini audit items not yet implemented: context compaction, prompt caching

---

## How to Work on This Project
- **Code changes always go to Claude Code in terminal** — do not write or edit code in chat unless the change is trivial (1-2 lines)
- Alex works fast — short messages, quick pivots, direct feedback
- Surface risks and blockers before building, not after
- When Alex references a component, check the actual file before assuming structure
