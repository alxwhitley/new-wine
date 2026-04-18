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
Charismatic and Spirit-filled Christians who want to research theology from within their tradition. The content library is built from documents Alex personally owns and has rights to — sermon outlines, theology papers, and similar material. New Wine Magazine extraction and ingestion pipeline is now operational (4 articles ingested from issue 03-1973, full 300-issue batch pending).

---

## Repo & Git
- Git repo initialized and pushed to `alxwhitley/rhemata` on GitHub
- `.gitignore` covers `.env`, `.env.local`, `__pycache__`, `.venv`, `node_modules`, `.next`, `.DS_Store`

---

## Monorepo Structure

```
repo/
├── frontend/          # Next.js 16 app (Vercel)
├── backend/
│   ├── app/           # FastAPI Python package
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routers/
│   │   │   ├── chat.py       # /chat endpoint — retrieval + LLM
│   │   │   ├── search.py     # /search + /search/documents endpoints
│   │   │   ├── document.py   # /document/{id} + /document/{id}/article
│   │   │   └── ingest.py     # /ingest endpoint
│   │   ├── services/
│   │   ├── db/
│   │   └── system_prompt.txt
│   ├── requirements.txt   # pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml      # locks Python 3.9
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
│   ├── scrape_youtube.py      # YouTube transcript scraper (yt-dlp + Supabase dedupe, raw only — no cleaning)
│   ├── youtube_pipeline.sh    # Full YouTube pipeline: scrape → clean → ingest
│   ├── whisper_transcribe.py   # Whisper medium + Groq clean (batch from no_captions/ or single URL)
│   ├── clean_transcripts.py   # Clean raw transcripts via Groq Llama 3.3 70B
│   ├── fix_article_json.py    # One-off migration: fix raw JSON chunks in Supabase (run 2026-04-17, 30 fixed)
│   ├── extract_magazine.py    # 3-pass Gemini/Groq extraction pipeline
│   ├── ingest_magazine.py     # Supabase ingestion from .md files with frontmatter
│   ├── ingest.py              # Standalone PDF/docx/txt ingestion with auto-tagging; moves YouTube transcripts to ingested/ on success
│   ├── tag_existing_articles.py  # Backfill topic_tags on existing articles
│   └── tag_sermons_transcripts.py  # Backfill topic_tags on sermons/transcripts/papers
├── migrations/            # SQL migrations (run in Supabase SQL Editor)
├── taxonomy.md            # 100-tag topic taxonomy (8 categories)
├── CLAUDE.md              # Claude Code context
└── SKILL.md               # Full project skill context
```

- All imports use `from app.x import y` (absolute, not relative)
- `requirements.txt` pinned to exact versions, includes `tiktoken`
- Railway start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (React 19), Tailwind CSS 4, deployed to Vercel |
| Backend | Python 3.9 / FastAPI, deployed to Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Answer Generation LLM | Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5`) via `anthropic` SDK |
| Query Expansion / Metadata / Tagging / Transcript Cleaning LLM | Groq Llama 3.3 70B (`llama-3.3-70b-versatile`) |
| Vision / OCR (magazine extraction) | Gemini 2.5 Flash (`gemini-2.5-flash`) via `google-genai` SDK |
| Reranking | Cohere rerank-v3.5 (`cohere` SDK) — narrows top 10 RRF → top 5 |
| Retrieval | Hybrid search: pgvector + PostgreSQL FTS, fused via RRF |
| Markdown rendering | `react-markdown` + `@tailwindcss/typography` |

**Removed:** GPT-4o Vision (replaced by Gemini 2.5 Flash). Groq for answer generation (replaced by Anthropic Claude Sonnet 4.5, April 2026).

---

## Architecture

**Frontend → Backend → Supabase → LLM**

1. User types a query in the chat interface
2. Frontend POSTs to `/chat` on the FastAPI backend (field: `question`, plus `anon_id` for guests)
3. Backend expands query into 3 semantic variants via Groq Llama 3.3 70B (`expand_query()`)
4. For each variant: pgvector cosine similarity (top 40) + PostgreSQL full-text search (top 30)
5. Results fused via Reciprocal Rank Fusion (RRF_K=60), deduplicated, document-level collapse (max 2 chunks per doc), top 10 selected
6. Cohere rerank-v3.5 narrows top 10 → top 5 by relevance (graceful fallback to top 10 if COHERE_API_KEY unset)
7. Neighbor chunk expansion (±1 chunk_index, cap at 12 total)
8. Backend assembles prompt: system instructions + retrieved chunks (tagged with `source_kind` and `citation_mode`) + query
9. Anthropic Claude Sonnet 4.5 generates a response, streamed back via SSE with `<answer>` tag extraction. Runtime-appended faithfulness instruction preserves source document views without editorializing.
9. Frontend renders response with inline citation tags

---

## Database Schema

**`documents` table** — one row per source document
- `id` (uuid), `title` (text), `author` (text)
- `source_name` (text), `source_type` (text), `source_kind` (text)
- `citation_mode` (text) — `'citable'` | `'silent_context'`
- `is_copyrighted` (boolean, default false)
- `year` (int), `issue` (text), `url` (text, nullable)
- `topic_tags` (text[]) — assigned from taxonomy
- `bible_references` (text[], default `'{}'`) — canonical refs like `"Romans 8:28"`; GIN indexed
- `fts_weighted` (tsvector) — weighted FTS on title (A), author (A), source_name (B), bible_references (C, colons stripped)
- `content_summary` (text) — first chunk content for display
- `created_at` (timestamptz)

**`chunks` table** — one row per text chunk
- `id` (uuid), `document_id` (FK → documents)
- `content` (text), `embedding` (vector(1536))
- `chunk_index` (int), `created_at` (timestamptz)

**`guest_sessions` table** — server-side guest query tracking
- `id` (uuid), `anon_id` (text, unique)
- `query_count` (int, default 0)
- `created_at` / `last_seen` (timestamptz)

**`conversations` table** — saved chat history for authenticated users
- `id` (uuid), `user_id` (uuid, FK → auth.users), `title` (text), `created_at`

**`messages` table** — individual messages within conversations
- `id` (uuid), `conversation_id` (FK → conversations)
- `role` (text: 'user' | 'assistant'), `content` (text), `created_at`

---

## Key Decisions Already Made

- **HNSW indexing** over ivfflat for pgvector; `match_chunks` sets `hnsw.ef_search=200`
- **Page-level citations** — not chunk-level
- **Two-tier content model:** `citation_mode = 'citable'` (renders citations) vs `'silent_context'` (informs LLM only)
- **Magazine chunking:** tiktoken cl100k_base, 550 tokens target, 80 overlap
- **Standalone ingest:** recursive character text splitting, 1000 char chunks, 200 char overlap
- **Hybrid search with RRF** — query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) → document collapse → top 10
- **CORS middleware** — `ALLOWED_ORIGINS` env var (comma-separated)
- **Guest query limit** — 6 free queries via `guest_sessions` + `increment_guest_query` RPC
- **JWT auth** via Supabase JWKS endpoint (`PyJWKClient`)
- **Bible Study articles excluded** from extraction pipeline (reference materials, not theological teaching)
- **Ingest auto-tagging** — ingest.py tags every new document post-chunk-insert via Groq Llama 3.3 70B; strict 3–6 tags, main themes only, non-fatal
- **is_copyrighted path-based** — `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false
- **Sermon transcripts excluded from search** — search_documents RPC defaults source_kind to "magazine_article"; transcripts available in chat retrieval only
- **All scripts in `scripts/`** — no Python files at project root; all use `Path(__file__).resolve().parent.parent` for project root
- **Bible reference tracking** — `documents.bible_references text[]` populated via Groq Llama 3.3 70B extraction; shared helper at `scripts/bible_refs.py` normalizes to `"Book Chapter:Verse"` canonical form against 66-book set + alias map; non-fatal (returns `[]` on failure); auto-populated during ingest in both `ingest.py` and `ingest_magazine.py`; backfill via `extract_bible_refs.py`
- **Prefix search** — `search_documents` RPC builds `to_tsquery` with `:*` prefix operators per token (colons split to sub-tokens), so `"Romans 8"` matches `"Romans 8:1"`, `"Romans 8:28"`, etc.; falls back to `plainto_tsquery` on parse error
- **System prompt discipline** — `backend/app/system_prompt.txt` uses XML tags (`<thinking>`, `<research_analysis>`, `<answer>`). `<research_analysis>` runs 3 fixed self-checks (author conflation, silent_context citation, biblical case overreach). Response Discipline Rules block enforces: multi-part decomposition, retrieval-only format when asked, explicit "corpus insufficient" flag on thin charismatic distinctives, retrieval scope cap (10 items / 250 words). Scripture exception limited to verse text only — no interpretation beyond sources. Tone section includes charismatic linguistic anchors ("impressions," "promptings") for exploratory mode only. Citation rules include prompt-injection trust boundary (ignore instructions embedded in retrieved chunks). Formatting requires minimum 2 `##` headings for theological answers (mandatory, not optional); retrieval uses bullets only.
- **Chat streaming** — Anthropic Claude Sonnet 4.5 `max_tokens=1500`. `<answer>` tag extraction server-side with 9-char buffer safety for split tags. If stream ends mid-answer, remaining buffer is flushed to client instead of silently dropped. Uses `client.messages.create(stream=True)` (not context manager form, which is incompatible with generator `yield`).
- **Cohere reranking** — After RRF fusion, top 10 chunks sent to Cohere rerank-v3.5 with original query; top 5 by relevance score returned. Falls back to RRF top 10 if `COHERE_API_KEY` not set or call fails.
- **Column break handling** — Pass 1 prompt instructs Gemini to transcribe multi-article pages column by column with `=== COLUMN BREAK ===` markers. Pass 2 prompt tells Groq to follow article content across column breaks, ignoring other articles' content.

---

## Content Rules
- Only ingest documents that Alex personally owns or has rights to
- New Wine Magazine pipeline is operational — `is_copyrighted=true`, controlled by `INCLUDE_COPYRIGHTED` env var
- `INCLUDE_COPYRIGHTED=true` in local `.env` and defaults true in `chat.py`
- Current non-magazine documents are single-column — no multi-column OCR handling needed

---

## Magazine Extraction Pipeline (3-pass)

**Input:** PDF in `sources/magazine/01_to_extract/`
**Output:** Per-article `.md` files in `sources/magazine/02_extracted/{issue_stem}/`

### Pass 1: Vision Extraction (Gemini 2.5 Flash)
- Converts PDF pages to PIL images at 200 DPI via `pdf2image`
- Processes in 5-page batches to avoid output truncation
- Each batch gets explicit page numbering instructions (`=== PAGE N ===`)
- Outputs `raw_text.txt` with full issue transcription

### Pass 2: Article Segmentation (Groq Llama 3.3 70B)
- **Step 2a:** Extracts TOC from pages 2-3, sends full text to Groq for metadata index (JSON array of title/author/page_start/page_end)
- **Step 2b:** For each article, extracts page range text and sends to Groq for body extraction + topic tagging
- Returns JSON: `{"topic_tags": [...], "body": "..."}`
- Tags validated against `VALID_TAGS` set — invalid tags removed
- Outputs individual `.md` files with frontmatter metadata

### Pass 3: QA Inspection (Groq Llama 3.3 70B)
- Checks each article for: truncation, duplicates, mismatch, word count (min 200), OCR errors
- Returns JSON: `{"status": "PASS"|"WARN"|"FLAG", "issues": [...], "confidence": 0.0-1.0}`
- FLAG articles moved to `flagged/` subfolder
- WARN articles get `<!-- QA WARNINGS -->` comment prepended
- Outputs `qa_report.json`

### Article Format
Each article saved as `.md` with frontmatter:
```
---
TITLE: Article Title
AUTHOR: Author Name
ISSUE: 03-1973
DATE: March 1973
PAGE_START: 4
PAGE_END: 10
SOURCE_TYPE: magazine_article
TOPIC_TAGS: Fivefold Ministry, Prophetic Ministry, Biblical Leadership
---

# Article Title
*by Author Name*

Body text formatted as markdown...
```

### Exclusions
- Bible Study, Bible Lesson, Study Guide articles excluded from extraction
- Letters to editor, order forms, subscription info, staff boxes, ads excluded
- Cover/back cover, full-page illustrations, advertisement pages skipped in Pass 1

---

## YouTube Pipeline

1. **Scrape:** `python3 scripts/scrape_youtube.py` — scrapes transcripts via yt-dlp from channels in youtube_tracker.xlsx, dedupes against Supabase, saves raw transcripts to `sources/youtube/raw/` (max 10 per run). Videos with no captions or low-quality transcripts (< 400 words) write metadata stubs to `sources/youtube/no_captions/` for Whisper processing.
2. **Clean:** `python3 scripts/clean_transcripts.py` — cleans via Groq Llama 3.3 70B, moves to `sources/youtube/cleaned/`
3. **Whisper:** `python3 scripts/whisper_transcribe.py` — batch-processes stubs in `no_captions/`, downloads audio via yt-dlp, transcribes with Whisper medium, cleans via Groq, outputs to `cleaned/`. Also supports single-URL mode with `--url --title --speaker --channel`.
4. **Ingest:** `python3 scripts/ingest.py` — ingests cleaned transcripts into Supabase with auto-tagging. Moves successfully ingested files from `cleaned/` to `ingested/` via `shutil.move`.

**Convenience script:** `./scripts/youtube_pipeline.sh` runs all 4 steps in sequence (`set -euo pipefail` — stops on failure). Shell alias: `rh-youtube` (in `~/.zshrc`).

Transcript files include metadata headers (TITLE, SPEAKER, URL, SOURCE_TYPE) parsed by ingest.py.

---

## Topic Tagging

- `taxonomy.md` in project root contains 100-tag taxonomy across 8 categories:
  1. Holy Spirit & Spiritual Gifts (14 tags)
  2. Charismatic Experience (14 tags)
  3. Prayer & Spiritual Warfare (14 tags)
  4. Healing & Wholeness (14 tags)
  5. Christian Leadership (15 tags)
  6. Christian Growth & Discipleship (14 tags)
  7. Kingdom & Theology (14 tags)
  8. Family & Relationships (13 tags)
- Tags assigned during Pass 2 extraction (5-8 per article)
- Strict rules: only assign if article directly teaches on topic for at least one paragraph
- Validated against `VALID_TAGS` set in both `extract_magazine.py` and `tag_existing_articles.py`
- Invalid/invented tags automatically removed
- `tag_existing_articles.py` for backfilling existing magazine articles (retries if < 3 valid tags)
- `tag_sermons_transcripts.py` for backfilling non-magazine documents (3-6 tags, retries if < 2 valid)

---

## Search Feature

- **GET /search/documents** — document-level FTS via `search_documents` RPC function
  - Parameters: `q`, `author`, `source_kind`, `include_copyrighted`
  - Returns: id, title, author, issue, year, highlighted_snippet, rank
  - `fts_weighted` column includes title (A), author (A), source_name (B), bible_references (C, colons stripped)
  - **Prefix tsquery builder** — tokenizes query, strips non-alphanumerics, appends `:*` to each token, AND-joins; `"Romans 8"` matches `"Romans 8:1"`, `"Romans 8:28"`, etc. Falls back to `plainto_tsquery` on parse error.
  - `ts_headline` generates keyword-highlighted snippets from best-matching chunk
  - Markdown/metadata stripped from snippets via nested `regexp_replace`
  - Fallback to first 200 chars if no FTS match in chunk content
  - `source_kind` defaults to "magazine_article" — excludes sermon_transcript from search results
- **GET /document/{id}/article** — reassembles full article from chunks
  - Strips per-chunk metadata headers, trims overlap, strips markdown bold/italic
  - Cleans author (truncates at parenthesis)
- **GET /search/documents/browse** — lists all documents of a source_kind, ordered by year/issue DESC
  - Parameters: `source_kind`, `include_copyrighted`
  - Returns same shape as search_documents (id, title, author, issue, year, topic_tags, highlighted_snippet=null, rank=0)
  - Both `/search/documents` and `/search/documents/browse` return `topic_tags` (secondary lookup on doc IDs for search; direct select for browse)
- **Search page at /search** — sidebar, search bar, result cards, article reader
  - Browse listing on initial load (all magazine articles, before any search)
  - `hasSearched` state flag distinguishes "no search yet" (show browse) vs "searched with no results" (show empty state)
  - Result cards show author-only metadata (no date/year/issue)
  - Topic tag pills on cards: rounded, `#d4b96a` gold text on `rgba(212, 185, 106, 0.12)` background
  - `ReactMarkdown` renders article body in reader view (title/byline stripped to avoid duplication)
  - `dangerouslySetInnerHTML` renders `<mark>` highlighted snippets in result cards
  - `mark` styled with gold color (#d4b96a), transparent background, font-weight 600

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/extract_magazine.py` | 3-pass Gemini/Groq extraction pipeline (Vision → Segmentation → QA). Supports `--max-issues N` and `--time-limit`. Continuation resolver (BFS, depth 5) handles "continued on page N" markers. PDFs archived into `02_extracted/{issue_stem}/` after extraction. Empty Gemini batches log warning + substitute `""` (non-fatal). |
| `scripts/ingest_magazine.py` | Ingest approved .md articles from sources/magazine/03_approved/ into Supabase. Auto-populates `bible_references`. Archives PDFs to `05_archived/` on success. |
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal). Auto-populates `bible_references`. |
| `scripts/bible_refs.py` | Shared Bible reference extractor (Groq Llama 3.3 70B). `extract_bible_references(content) -> List[str]`. Segments at ~12k chars, normalizes against 66-book canonical set + alias map, dedupes. Non-fatal (returns `[]`). |
| `extract_bible_refs.py` (project root) | Backfill `bible_references` on all documents. Flags: `--dry-run`, `--force` (re-process docs that already have refs). |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/youtube_pipeline.sh` | Full YouTube pipeline convenience script: scrape → clean → whisper → ingest. Shell alias: `rh-youtube`. |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run). Writes no_captions stubs for videos without captions or with < 400 words. |
| `scripts/whisper_transcribe.py` | Whisper medium transcription + Groq cleaning. Batch mode processes `no_captions/` stubs; single-URL mode via CLI args. |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |
| `scripts/fix_article_json.py` | One-off migration: fixed 30 chunks with raw JSON content in Supabase (run 2026-04-17). |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

---

## Corpus
- 50 documents ingested
- 25 non-magazine documents (sermons, papers, book, other) — all tagged
- 21 YouTube transcripts ingested (sermon_transcript)
- 4 copyrighted magazine articles (New Wine Magazine, issue 03-1973) — all tagged
- 35 chunks across magazine articles
- **All 38 backfilled docs have `bible_references` populated** (2026-04-10). 35/38 had refs (2 to 138 each); 3 with no refs (session notes, zoom outlines, marketplace calling)

---

## UX Model
- Centered chat input as primary interaction
- Perplexity-style inline citations rendered as gold-highlighted tags
- Clicking a citation opens a source panel with document title, author, and page content
- Sidebar: "Rhemata" wordmark, New Chat (plain, above Search), Search link, "Recents" section label, conversation history (title + timestamp, no icons)
- Search page at `/search` with keyword search, browse-all default listing, result cards with topic tag pills, and full article reader
- Auth flow: login modal triggered by AuthButton, sidebar sign-in link, or guest limit reached
- Guest users get 6 free queries before prompted to sign up

---

## Brand
- **Name:** Rhemata
- **Fonts:** Lora (headings/logo), Inter (UI/body)
- **Dark theme** — near-black backgrounds, warm neutrals
- **Gold accents** — `#d4b96a` (citations/highlights/tag pills), `rgba(212, 185, 106, 0.12)` (tag pill backgrounds)
- **Voice:** Scholarly but accessible. Conviction, not performance. Serves the researcher, not the spectacle.

---

## Deployment

| Target | Status | Notes |
|---|---|---|
| Railway (backend) | Live | Root dir: `backend/`, Python 3.9 via nixpacks.toml |
| Vercel (frontend) | Live | Root dir: `frontend/` |
| Supabase | Live | PostgreSQL + pgvector |

### Backend env vars (Railway)
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `ALLOWED_ORIGINS`
- `INCLUDE_COPYRIGHTED`

### Frontend env vars (Vercel)
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## Environment Variables (local — backend/app/.env)
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY` — Claude Sonnet 4.5 for answer generation
- `COHERE_API_KEY` — Cohere rerank-v3.5 for retrieval reranking
- `GOOGLE_API_KEY` — Gemini 2.5 Flash for magazine extraction
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_JWT_JWKS_URL`
- `INCLUDE_COPYRIGHTED` — `true`/`false` (default `true` in chat.py, `false` in search.py)
- `ALLOWED_ORIGINS`

---

## Remaining / Known Issues

- **Full 300-issue batch not yet run** — only 4 articles ingested from issue 03-1973
- **Migration 012 not yet run** — needs to be applied in Supabase SQL Editor (Migration 013 for `bible_references` is applied as of 2026-04-10)
- **`sources/youtube/youtube_tracker.xlsx` still tracked** — needs `git rm --cached sources/youtube/youtube_tracker.xlsx` to finish the earlier `sources/` cleanup. Shows up as modified on every commit.
- **Issue_03-1973 cleanup A/B/C options** never resolved in the continuation-resolver session — was left in `02_extracted/` in an uncertain state.
- **scrape_youtube.py dead Haiku code** — removed (2026-04-15)
- **content_summary not auto-populated** on new article inserts (trigger only updates fts_weighted, not content_summary)
- **Tagging retry logic** sometimes needs improvement for complex articles
- **Guest query limit** — `increment_guest_query()` SQL function needs migration file
- **RLS policies needed** on `conversations` and `messages` tables
- **INCLUDE_COPYRIGHTED not confirmed on Railway** — check dashboard
- **poppler required** — `brew install poppler` for pdf2image to work locally
- **Bible ref extraction occasionally produces malformed JSON** from Groq on edge-case batches (~1 in 38 docs in backfill run). Helper handles gracefully by dropping that segment and continuing; other segments in the same doc still succeed.
- **System prompt and chat.py changes deployed** (2026-04-15) — pushed to main; Railway/Vercel should auto-deploy.
- **Anthropic + Cohere rerank deployed** (2026-04-17) — answer gen switched to Claude Sonnet 4.5, Cohere rerank-v3.5 added. Pushed to main.
- **Article reader date display** — issue date (month/year) added to frontend but not yet visually confirmed in browser. `console.log` left in `handleCardClick` for debugging — remove after confirming.
- **30 malformed JSON chunks fixed** (2026-04-17) — `fix_article_json.py` migration ran successfully; content_summary refreshed on all 30 affected documents.
- **Shell aliases expanded** — 10 `rh-*` aliases in `~/.zshrc` covering all pipeline scripts.

---

## How to Work on This Project
- **Code changes always go to Claude Code in terminal** — do not write or edit code in chat unless the change is trivial (1-2 lines)
- Alex works fast — short messages, quick pivots, direct feedback
- Surface risks and blockers before building, not after
- When Alex references a component, check the actual file before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
