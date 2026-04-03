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

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (React), Tailwind, deployed to Vercel |
| Backend | Python / FastAPI, deployed to Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat / LLM | Anthropic Claude Haiku |
| OCR | EasyOCR + Claude Vision (fallback) |

---

## Architecture

**Frontend → Backend → Supabase → LLM**

1. User types a query in the chat interface
2. Frontend POSTs to `/chat` on the FastAPI backend
3. Backend generates an OpenAI embedding of the query
4. pgvector runs cosine similarity search, returns top-k chunks
5. Backend assembles prompt: system instructions + retrieved chunks + query
6. Claude Haiku generates a response, streamed back to frontend
7. Frontend renders response with inline citation tags

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
- `created_at` (timestamptz)

**`chunks` table** — one row per text chunk
- `id` (uuid)
- `document_id` (foreign key → documents)
- `content` (text)
- `embedding` (vector(1536))
- `created_at` (timestamptz)

---

## Key Decisions Already Made

- **HNSW indexing** over ivfflat for pgvector (faster, more accurate)
- **Page-level citations** — not chunk-level. The full page a chunk belongs to is surfaced as the citation context
- **Two-tier content model:**
  - `source_type = 'sermon'` — citable, renders citation tags in frontend
  - `source_type = 'background'` — informs LLM context silently, never cited
- **Recursive character text splitting** over fixed-size chunking (keeps theological arguments intact)
- **k=5 retrieval** (to be bumped to 10-15 once more content is ingested)
- **Claude Vision** as OCR fallback for corrupted/unreadable PDF pages
- **Single-column PDFs only** for now — current content is not multi-column, multi-column OCR logic not needed yet
- **CORS middleware** added to FastAPI with `allow_origins=["http://localhost:3000"]`

---

## Content Rules
- Only ingest PDFs that Alex personally owns
- New Wine Magazine is on hold — do not plan ingestion until copyright is resolved
- Current documents are single-column — no multi-column OCR handling needed

---

## UX Model
- Centered chat input as primary interaction (not a sidebar topic browser)
- Perplexity-style inline citations rendered as gold-highlighted tags
- Clicking a citation opens a source panel with document title, author, and page content
- Sidebar for conversation history
- No auth layer yet

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

## Deployment Targets
- Frontend → Vercel
- Backend → Railway
- Database → Supabase (stays there)

---

## How to Work on This Project
- **Code changes always go to Claude Code in terminal** — do not write or edit code in chat unless the change is trivial (1-2 lines)
- Alex works fast — short messages, quick pivots, direct feedback
- Surface risks and blockers before building, not after
- When Alex references a component, check the actual file before assuming structure
