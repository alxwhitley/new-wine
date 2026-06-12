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
- `.gitignore` covers `.env`, `.env.local`, `__pycache__`, `.venv`, `node_modules`, `.next`, `.DS_Store`, `sources/`
- `sources/` stripped from git history (2026-06-10) via BFG Repo Cleaner — 1,151 files removed across all 215 commits; `.git` reduced from 55 MB to 3.1 MB; force-pushed to origin main

---

## Monorepo Structure

```
repo/
├── frontend/          # Next.js 16 app (Vercel)
│   └── hooks/
│       └── useUserRole.ts  # Role + displayName hook; module-level cache keyed by access token
├── backend/
│   ├── app/           # FastAPI Python package
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routers/
│   │   │   ├── chat.py       # /chat endpoint — retrieval + LLM
│   │   │   ├── search.py     # /search + /search/documents endpoints
│   │   │   ├── document.py   # /document/{id} + /document/{id}/article
│   │   │   ├── study.py      # /study/verse + /study/corpus + /study/lexicon + /study/excerpt endpoints
│   │   │   ├── pastors_notes.py  # /pastors-notes/* — cards, requests, role management (user/contributor/admin)
│   │   │   └── ingest.py     # /ingest endpoint
│   │   ├── services/
│   │   ├── db/
│   │   ├── system_prompt.txt
│   │   └── theological_guardrails.txt
│   ├── requirements.txt   # pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml      # locks Python 3.9
├── sources/
│   ├── youtube/               # YouTube transcript pipeline
│   │   ├── raw/               # Freshly scraped transcripts
│   │   ├── cleaned/           # Groq-cleaned, ready for ingest
│   │   ├── ingested/          # Already in Supabase
│   │   ├── youtube_tracker.xlsx
│   │   └── individual_videos.xlsx  # Individual video ingestion tracker
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
├── scrape_preceptaustin.py # Precept Austin word study scraper (page caching, multi-strategy anchor matching)
├── ingest_preceptaustin.py # Precept Austin word study ingestion (psycopg2 chunks, OpenAI embeddings)
├── ingest_lexicon.py      # STEPBible lexicon ingestion (TBESG, TBESH, TFLSJ)
├── ingest_bible.py        # WEB Bible VPL ingestion into verses table (psycopg2)
├── migrations/            # SQL migrations (run in Supabase SQL Editor)
│   └── 038_pastors_notes.sql  # user_roles, contributor_requests, pastors_cards tables + RLS
├── taxonomy.md            # 257-tag topic taxonomy (15 categories)
├── CLAUDE.md              # Claude Code context
└── SKILL.md               # Full project skill context
```

- All imports use `from app.x import y` (absolute, not relative)
- `requirements.txt` pinned to exact versions, includes `tiktoken`, `httpcore>=1.0.7`
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
8. Backend assembles prompt: system instructions + theological guardrails + retrieved chunks (tagged with `source_kind` and `citation_mode`) + query
9. Anthropic Claude Sonnet 4.5 generates a response, streamed back via SSE with `<answer>` tag extraction. Runtime-appended faithfulness instruction preserves source document views without editorializing. Theological guardrails (`theological_guardrails.txt`) appended to system prompt enforce non-negotiable framings (e.g., Holy Spirit personhood).
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

**`verses` table** — Bible verse text (WEB translation)
- `id` (uuid), `verse_id` (text, unique — format: `SBL.CHAPTER.VERSE`, e.g. `JHN.3.16`)
- `book` (text — full name), `book_num` (int — 1-66), `chapter` (int), `verse` (int)
- `text` (text), `translation` (text, default `'WEB'`)
- `created_at` (timestamptz)
- Indexes on `verse_id` and `(book, chapter, verse)`

**`saved_words` table** — user's saved Greek words for Study mode
- `id` (uuid), `user_id` (uuid, FK → auth.users, cascade delete)
- `strongs_number` (text), `greek_word` (text), `transliteration` (text), `english_gloss` (text, nullable)
- `created_at` (timestamptz)
- Unique constraint on `(user_id, strongs_number)`
- RLS enabled: users can only manage their own rows (`auth.uid() = user_id`)

**`guest_sessions` table** — server-side guest query tracking
- `id` (uuid), `anon_id` (text, unique)
- `query_count` (int, default 0)
- `created_at` / `last_seen` (timestamptz)

**`conversations` table** — saved chat history for authenticated users
- `id` (uuid), `user_id` (uuid, FK → auth.users), `title` (text), `created_at`

**`messages` table** — individual messages within conversations
- `id` (uuid), `conversation_id` (FK → conversations)
- `role` (text: 'user' | 'assistant'), `content` (text), `created_at`

**`book_quotes` table** — extracted quotable passages from books (migration 034)
- `id` (uuid), `document_id` (FK → documents, cascade delete)
- `quote_text` (text), `quote_index` (int), `created_at` (timestamptz)
- Index on `document_id`

---

## Key Decisions Already Made

- **HNSW indexing** over ivfflat for pgvector; `match_chunks` sets `hnsw.ef_search=200`
- **Page-level citations** — not chunk-level
- **Two-tier content model:** `citation_mode = 'citable'` (renders citations) vs `'silent_context'` (informs LLM only)
- **Magazine chunking:** tiktoken cl100k_base, 550 tokens target, 80 overlap
- **Standalone ingest:** recursive character text splitting, 1000 char chunks, 200 char overlap
- **Hybrid search with RRF** — query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) → document collapse → top 10
- **CORS middleware** — `ALLOWED_ORIGINS` env var (comma-separated)
- **Guest query limit** — 6 free queries via `guest_sessions` + `increment_guest_query` RPC (migration complete June 2026)
- **Design system:** `DESIGN.md` in project root is the styling authority. Lumen system (shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme locked via `forcedTheme`). No hardcoded hex. Admin pages still have old hex — deferred, internal only.
- **Brand reset complete (June 2026):** Lora/Inter/gold hex removed. Geist Sans, shadcn primitives, CSS variable tokens throughout. `DESIGN.md` is source of truth.
- **Study Mode restructured (June 2026):** single-column layout, interlinear always visible attached to verse, inline word expansion, commentary visible without tab click, Pastors' Notes stub in place, Jewish Perspective collapsed by default. Tabs removed.
- **Guest session migration complete (June 2026):** `guest_sessions` table and `increment_guest_query` RPC created in Supabase. Frontend and backend were already wired.
- **Pastors' Notes complete (June 2026):** three-tier role system (user/contributor/admin), verse-anchored cards, contributor request flow, admin panel at /admin/contributors, 50–2000 char limit, soft delete only, auto-tagging via Groq with 5s timeout fallback. Tables: `user_roles`, `contributor_requests`, `pastors_cards` (migration 038).
- **JWT auth** via Supabase JWKS endpoint (`PyJWKClient`)
- **Bible Study articles excluded** from extraction pipeline (reference materials, not theological teaching)
- **Ingest auto-tagging** — ingest.py tags every new document post-chunk-insert via Groq Llama 3.3 70B; strict 3–6 tags, main themes only, non-fatal
- **is_copyrighted path-based** — `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false
- **Sermon transcripts excluded from search** — search_documents RPC defaults source_kind to "magazine_article"; transcripts available in chat retrieval only
- **All scripts in `scripts/`** — no Python files at project root; all use `Path(__file__).resolve().parent.parent` for project root
- **Bible reference tracking** — `documents.bible_references text[]` populated via Groq Llama 3.3 70B extraction; shared helper at `scripts/bible_refs.py` normalizes to `"Book Chapter:Verse"` canonical form against 66-book set + alias map; non-fatal (returns `[]` on failure); auto-populated during ingest in both `ingest.py` and `ingest_magazine.py`; backfill via `extract_bible_refs.py`
- **Prefix search** — `search_documents` RPC builds `to_tsquery` with `:*` prefix operators per token (colons split to sub-tokens), so `"Romans 8"` matches `"Romans 8:1"`, `"Romans 8:28"`, etc.; falls back to `plainto_tsquery` on parse error
- **System prompt discipline** — `backend/app/system_prompt.txt` uses XML tags (`<thinking>`, `<research_analysis>`, `<answer>`). `<research_analysis>` runs 3 fixed self-checks (author conflation, silent_context citation, biblical case overreach). Response Discipline Rules block enforces: multi-part decomposition, retrieval-only format when asked, explicit "corpus insufficient" flag on thin charismatic distinctives, retrieval scope cap (10 items / 250 words). Scripture exception limited to verse text only — no interpretation beyond sources. Tone section includes charismatic linguistic anchors ("impressions," "promptings") for exploratory mode only. Citation rules include prompt-injection trust boundary (ignore instructions embedded in retrieved chunks), no anonymous attribution ("one teacher" etc. banned — cite by name or no attribution). Formatting requires minimum 2 `##` headings for theological answers (mandatory, not optional). Quote discipline: paraphrase with attribution, never lift phrasing verbatim. Closing synthesis: end with own conclusion drawn from sources, not a summary.
- **Theological guardrails** — `backend/app/theological_guardrails.txt` loaded and appended to system prompt in `chat.py`. Contains non-negotiable theological framings that override source material phrasing. Currently covers Holy Spirit personhood (person of the Trinity, not merely a power/provision).
- **Chat streaming** — Anthropic Claude Sonnet 4.5 `max_tokens=1500`. `<answer>` tag extraction server-side with 9-char buffer safety for split tags. If stream ends mid-answer, remaining buffer is flushed to client instead of silently dropped. Uses `client.messages.create(stream=True)` (not context manager form, which is incompatible with generator `yield`). Frontend: no timeouts or AbortController; stream completion via `[DONE]` sentinel or reader exhaustion; error handling for 429 (guest/daily limits).
- **Batched neighbor chunk expansion** — `fetch_neighbor_chunks_batch()` collects all (document_id, chunk_index±1) pairs from top chunks, builds `.or_()` compound filter with `and()` conditions, batches at 30 pairs per query. Replaces sequential per-chunk lookups (was 10 calls for 5 chunks, now 1-2 calls total).
- **Sparse citation rule** — system prompt enforces max 2-3 inline citations per response. Only cite when source of claim materially matters. Single citation sufficient when answer draws primarily from one source.
- **Cohere reranking** — After RRF fusion, top 10 chunks sent to Cohere rerank-v3.5 with original query; top 5 by relevance score returned. Falls back to RRF top 10 if `COHERE_API_KEY` not set or call fails. Cohere client forced to HTTP/1.1 (`httpx.Client(http2=False)`) to avoid HTTP/2 trailer framing errors.
- **Resilient hybrid search** — FTS and vector search failures in `hybrid_search_rrf()` are non-fatal; each falls back to empty results so the other leg can still return chunks. FTS query truncated to 300 chars (`FTS_QUERY_MAX_LEN`) to prevent Cloudflare 400 errors from oversized Supabase PostgREST requests.
- **Column break handling** — Pass 1 prompt instructs Gemini to transcribe multi-article pages column by column with `=== COLUMN BREAK ===` markers. Pass 2 prompt tells Groq to follow article content across column breaks, ignoring other articles' content.
- **psycopg2 connection fix** — Supabase pooler usernames contain a dot (`postgres.{ref}`) which `psycopg2.connect(uri)` misparses, truncating to `postgres`. All ingestion scripts (`ingest_lexicon.py`, `ingest_preceptaustin.py`, `ingest.py`, `ingest_commentaries.py`) now parse `SUPABASE_DB_URL` with `urlparse` and pass explicit keyword args (`host`, `port`, `user`, `password`, `dbname`).

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

- `taxonomy.md` in project root contains 257 unique tags across 15 categories:
  1. Holy Spirit & Spiritual Gifts (27 tags)
  2. Spiritual Warfare & Deliverance (13 tags)
  3. Prayer, Intercession & the Prophetic (18 tags)
  4. Inner Healing & Identity (20 tags)
  5. Presence, Worship & Encounter (10 tags)
  6. Fivefold Ministry (26 tags)
  7. Kingdom, Theology & Mission (23 tags)
  8. Leadership & Church Culture (17 tags)
  9. Faith, Finances & Provision (19 tags)
  10. Purpose, Calling & Destiny (6 tags)
  11. Christian Growth & Discipleship (19 tags)
  12. Family, Purity & Relationships (16 tags)
  13. Divine Healing & Wholeness (15 tags)
  14. Biblical Studies & Theology (14 tags)
  15. Church History & Revival (20 tags)
- Some tags intentionally appear in multiple categories (e.g. "Fruit of the Spirit" in 1 and 11, "Dying to Self" in 4 and 11)
- `scripts/taxonomy.py` contains the hardcoded `VALID_TAGS` set — must be kept in sync with `taxonomy.md`
- Tags assigned during Pass 2 extraction (5-8 per article)
- Strict rules: only assign if article directly teaches on topic for at least one paragraph
- Validated against `VALID_TAGS` set in both `extract_magazine.py` and `tag_existing_articles.py`
- Invalid/invented tags automatically removed
- `tag_existing_articles.py` for backfilling existing magazine articles (retries if < 3 valid tags)
- `tag_sermons_transcripts.py` for backfilling non-magazine documents via Groq (3-6 tags, retries if < 2 valid)
- `retag_sermons.py` for retagging sermon_transcript documents via Anthropic claude-haiku-4-5 with first 3 chunks as context. Flags: `--limit N`, `--author`, `--suggest-tags`, `--dry-run`, `--force`. `--suggest-tags` writes taxonomy gap suggestions to `sources/tag_suggestions.jsonl`.

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
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal). Auto-populates `bible_references`. Skip reason tracking: `ingest_file()` returns `(status, reason)` tuples; `main()` prints grouped summary table of all skipped/failed files with reasons at end of run. Uses psycopg2 direct query for `already_ingested()` (same `DB_PARAMS` pattern as other scripts). |
| `scripts/bible_refs.py` | Shared Bible reference extractor (Groq Llama 3.3 70B). `extract_bible_references(content) -> List[str]`. Segments at ~12k chars, normalizes against 66-book canonical set + alias map, dedupes. Non-fatal (returns `[]`). |
| `extract_bible_refs.py` (project root) | Backfill `bible_references` on all documents. Flags: `--dry-run`, `--force`, `--limit N`, `--source-kind KIND`. Uses psycopg2 for reads (avoids PostgREST timeouts). |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/youtube_pipeline.sh` | Full YouTube pipeline convenience script: scrape → clean → whisper → ingest. Shell alias: `rh-youtube`. |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run). Writes no_captions stubs for videos without captions or with < 400 words. |
| `scripts/whisper_transcribe.py` | Whisper medium transcription + Groq cleaning. Batch mode processes `no_captions/` stubs; single-URL mode via CLI args. |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |
| `scripts/scrape_individual_videos.py` | Individual YouTube video ingestion. Reads from `sources/youtube/individual_videos.xlsx`, tries yt-dlp captions → Whisper fallback → Groq clean → writes to `cleaned/` → runs `ingest.py`. Resume-safe via xlsx Status column (Pending → Whisper → Cleaning → Scraped → Ingested). Shell alias: `rh-individual`. |
| `scripts/scrape_channel_titles.py` | Dumps all video titles from YouTube channels into `sources/channel_titles.csv`. Uses yt-dlp `--flat-playlist --print title`. Flags: `--channel "Name"` for single channel. |
| `scripts/retag_sermons.py` | Retags sermon_transcript documents using Anthropic claude-haiku-4-5 with first 3 chunks as context. Validates against taxonomy.md. Flags: `--limit N`, `--author`, `--suggest-tags`, `--dry-run`, `--force`. `--suggest-tags` runs second Haiku call for taxonomy gap analysis → `sources/tag_suggestions.jsonl`. |
| `scripts/generate_excerpts.py` | Batch-generate edited word study articles from Precept Austin raw chunks. Concatenates all chunks per document, sends to Anthropic Claude for editing into clean articles, writes to `excerpts` table (`excerpt_type = 'word_study_article'`). Flags: `--test`, `--test-quality`, `--model sonnet|haiku`, `--time-limit`. |
| `scripts/ingest_commentaries.py` | Ingests HistoricalChristianFaith commentaries from SQLite DB. Groups by father_name, one document per father, chunks with tiktoken, embeds with OpenAI, inserts via psycopg2. Single-transaction pattern (`connect_with_retry()` + `ingest_father()`). Theological tagging (Reformed, Cessationist, Charismatic-Friendly, Desert Fathers, Patristic). Flags: `--dry-run`, `--father "Name"`, `--filter-charismatic`. |
| `scripts/fix_article_json.py` | One-off migration: fixed 30 chunks with raw JSON content in Supabase (run 2026-04-17). |
| `scripts/extract_book_quotes.py` | Extract quotable passages from Andrew Murray books via Claude Haiku 4.5. 10 batches per book, 5 quotes per batch (~50 quotes/book). Validates length (100-600 chars), filters metadata/URLs. Flags: `--dry-run`, `--limit N`, `--title`. Resume-safe. Inserts into `book_quotes` table. |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

### Root-Level Ingestion Scripts

| Script | Purpose |
|---|---|
| `scrape_preceptaustin.py` | Scrapes Precept Austin Greek word studies. Page caching to `sources/precept_austin/page_cache/`, randomized sleep (2-5s), 4-strategy anchor matching (exact → case-insensitive → partial → reverse word), quality filters (<100 words, nav bleed, fragmented). `--fetch` runs full pipeline, `--test` limits to 10 entries. Outputs to `sources/precept_austin/raw/` + `index.json`. |
| `ingest_preceptaustin.py` | Ingests Precept Austin word studies into Supabase. Chunks via psycopg2 `execute_values` with `::vector` cast. Documents via Supabase client. Skip logic checks `excerpts` table for existing `word_study_article` excerpt (not just document existence). Reuses existing doc_id when document exists but has no excerpt. Uses `backend/app/services/chunker.py` (550 tokens, 80 overlap). |
| `ingest_lexicon.py` | Ingests STEPBible lexicon files (TBESG, TBESH, TFLSJ). One chunk per lexical entry. tiktoken truncation at 8000 tokens for embedding. Resume-safe (tracks existing chunk counts). CLI flags: `--lexicon TBESG\|TBESH\|TFLSJ`, `--delete` (removes existing data first), `--sample N`. Brief mode for TBESG: stores only gloss + bolded sub-meanings (no full Abbott-Smith HTML). Chunk inserts via psycopg2 `execute_values` with `ON CONFLICT DO NOTHING`. |
| `ingest_bible.py` | Parses WEB VPL file, maps 66 canonical books (VPL→SBL abbreviations), inserts into `verses` table via psycopg2. Batch size 1000, `ON CONFLICT DO NOTHING`. `--test` limits to 100 verses. Skips deuterocanonical books. |

Note: `ingest_commentaries.py` is now in `scripts/` (see Scripts table above).

**Data sources:**
- `sources/precept_austin/` — word study `.txt` files + `index.json` + `page_cache/` (gitignored)
- `sources/lexicon/` — STEPBible TSV files (TBESG, TBESH, TFLSJ)
- `sources/bible/eng-web_vpl.txt` — World English Bible verse-per-line file

---

## Corpus (as of 2026-06-03)
- **~2,628 documents** total, **~124,346 chunks**
- By source_kind: 1,779 word_study, ~568 sermon_transcript (includes 11 Daniel Kolenda), 186 commentary, 58 unknown, 33 magazine_article, 4 lexicon
- By source_type: 1,783 background, ~568 sermon, 186 commentary, 49 book, 33 magazine_article, 5 paper, 4 other
- Copyrighted: 1,862 | Non-copyrighted: 755
- **Lexicons:** TBESG 11,034 chunks (complete), TBESH 10,258 chunks (complete), TFLSJ 15,767 chunks across 2 docs (complete)
- **Verses:** 31,098 rows (WEB, 66-book Protestant canon, complete)
- **Excerpts:** 1,713 of 1,779 word_study docs have generated articles (96%, 66 remaining)
- **All commentary docs backfilled with `bible_references`** (2026-05-30) — 307 HistoricalChristianFaith commentaries processed across 3 runs (connection timeouts required re-runs). 400 got refs, 93 had no refs found.

---

## UX Model
- Centered chat input as primary interaction
- Perplexity-style inline citations rendered as gold-highlighted tags
- Clicking a citation opens a source panel with document title, author, and page content
- Sidebar: Shared across all routes. "Rhemata" wordmark, gold "New Chat" CTA, nav items (Chat/Library/Study), conditional content (Recents on chat, Saved Words on study). No right border — sidebar blends with `bg-sidebar` outer canvas. Uses design tokens.
- Chat page: Floating panel layout — outer shell `bg-sidebar`, main content in `bg-background rounded-xl` panel (8px inset on all sides). Scroll fade (`sticky top-0 h-8 gradient`) at top of message list. Top bar has no bottom border; panel edge provides separation.
- Search page at `/search` with keyword search, browse-all default listing, result cards with topic tag pills, and full article reader
- Auth flow: login modal triggered by AuthButton, sidebar sign-in link, or guest limit reached
- Guest users get 6 free queries before prompted to sign up

---

## Brand
- **Name:** Rhemata
- **Design system:** Lumen — shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme. `DESIGN.md` is the styling authority. No hardcoded hex in fully migrated files.
- **Migration status:** Chat page (`app/page.tsx`), sidebar, library, and study pages fully on design tokens. Phase 4 (remaining files) attempted but linter reverted edits — `app/admin/`, `app/rhemata-corpus-admin/`, and `components/center/DocumentCard.tsx` still carry old hex. Re-migration pending.
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
- `SUPABASE_DB_URL` — direct PostgreSQL connection string for psycopg2 (bypasses PostgREST timeouts). Used by `ingest_bible.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py` (psycopg2 variant).

---

## Study Mode (frontend)

- **Route:** `/study` — Study Mode page with tab-driven layout
- **Layout:** Shared sidebar (w-64) with Saved Words list | Left panel (380px fixed: search, verse card, chapter view) | Right panel (flex:1: tab content)
- **Sidebar:** Shared `sidebar.tsx` across Chat and Study. Uses `usePathname()` for active route. Chat shows Recents; Study shows Saved Words. Nav items: Chat (MessageSquare), Discover (Compass), Study (BookOpen). Active nav text `#e6e6e6`, inactive `#c1c1b8`. Gold "New Chat" CTA (`#b49238`). Hover standard: `onMouseEnter` bg `#262624`, `onMouseLeave` transparent.
- **Saved words:** `saved_words` table in Supabase (migration 017). RLS policy scoped to `auth.uid()`. Toggle save/unsave from definition panel bookmark icon. Sidebar shows English gloss + Strong's number, transliteration below.
- **Verse lookup:** Direct Supabase query from frontend (`verses` table, keyed by `verse_id`). Client-side `parseRef()` with full 66-book `BOOK_MAP` + `ABBREV_TO_NAME`.
- **Left panel:** Search bar, verse card, "View Chapter" button, chapter view. No interlinear or definition content.
- **Chapter view:** Flowing text with inline `<sup>` verse numbers. Verses queried via `.like("verse_id", "JHN.1.%")` pattern. Active verse highlighted with `#2f2f2c` background. Clicking a verse in chapter view loads it as the active verse.
- **Right panel tabs:** `CorpusTab` type: `"commentaries" | "word_study" | "jewish"`. Tab state lifted to parent `StudyPage` for cross-panel coordination.
  - **Commentary tab:** `GET /study/commentary` with book-level pre-filter + scoped vector search. Pre-filter uses `match_commentary_by_book` RPC (migration 028) to get doc IDs for the current book via `bible_references && ARRAY[book_name]`. When doc IDs found, calls `match_commentary_chunks` RPC (migration 029) with `document_ids uuid[]` parameter for scoped vector search. Falls back to unfiltered `match_chunks` if no book matches. No `citation_mode` filter — commentary docs use `silent_context` for chat but are always shown in study mode. Author boosts: Matthew Henry +0.15, JFB +0.08, Adam Clarke +0.03, others −0.10. **Both commentary and sermon results use `_fetch_neighbor_content()` (±1 chunk expansion)** for richer context. Sermon results via `match_sermon_chunks_by_ref` RPC (max 2). Paginated at 3 per page. Study mode uses `study_filters` that ignores `source_name` toggles (chat-only).
  - **Word Study tab:** Interlinear word blocks → definition panel → Precept Austin excerpt → "From the Library" corpus results. Interlinear fetch gated by `corpusTab === "word_study"` (not fetched on every verse change). Auto-selects first interlinear word when tokens load.
  - **Jewish Perspective tab:** Inline generate flow (no modal/disclaimer). Single "Generate Jewish Perspective" button → spinner → cached result. `jpCacheChecked` state tracks whether cache has been checked. Auto-checks cache on verse change. 3 sections: Jewish Background, Messianic Perspective, Cultural Context + sources list. Generated via Gemini 2.5 Flash with Google Search grounding. Env var: `GOOGLE_API_KEY` (not `GEMINI_API_KEY`).
- **Excerpt panel:** `GET /study/excerpt?strongs=G####` endpoint returns Precept Austin word study article for selected Strong's number. Tries `excerpts` table first, falls back to concatenated chunks.
- **Corpus panel ("From the Library"):** Backend `GET /study/corpus?verse=...&transliteration=...` endpoint. Embeds query via OpenAI, runs `match_chunks` RPC (match_count=20, include_copyrighted=true), filters to `citation_mode='citable'` + `source_kind IN ('sermon_transcript', 'magazine_article', 'commentary', 'word_study')`, dedupes by document, returns top 5. Frontend shows skeleton loader, empty state, or real results.
- **Definition panel:** Fetches lexicon data from `GET /study/lexicon?strongs=G####` endpoint. Displays gloss inline with transliteration/Strong's number, plus parsed definition and usage from TBESG chunks.
- **Backend router:** `backend/app/routers/study.py` — `GET /study/verse` (parses ref, queries verses table), `GET /study/corpus` (semantic search), `GET /study/lexicon` (TBESG lexicon lookup), `GET /study/excerpt` (word study excerpt by Strong's number), `GET /study/interlinear` (interlinear words by verse_id), `GET /study/commentary` (commentary semantic search), `GET /study/wordsearch` + `GET /study/wordstudy/{document_id}` (word study search and detail). Registered in `main.py` with `prefix="/study"`.
- **Interlinear blocks:** Inline styles for spacing/sizing (not Tailwind — classes weren't taking effect). Hover color `#2f2f2c` (since resting bg is `#262624`). No bookmark icons on word blocks. Now rendered in Word Study tab of right panel (not left panel).
- **Interlinear data:** Live from `interlinear_words` table (142,096 rows). Backend `GET /study/interlinear?verse_id=JHN.1.1` returns word data ordered by word_position.

---

## Remaining / Known Issues

- **Full 300-issue batch not yet run** — only 4 articles ingested from issue 03-1973
- **Migration 012 not yet run** — needs to be applied in Supabase SQL Editor (Migration 013 for `bible_references` is applied as of 2026-04-10)
- **`sources/youtube/youtube_tracker.xlsx` still tracked** — needs `git rm --cached sources/youtube/youtube_tracker.xlsx` to finish the earlier `sources/` cleanup. Shows up as modified on every commit.
- **Issue_03-1973 cleanup A/B/C options** never resolved in the continuation-resolver session — was left in `02_extracted/` in an uncertain state.
- **scrape_youtube.py dead Haiku code** — removed (2026-04-15)
- **content_summary not auto-populated** on new article inserts (trigger only updates fts_weighted, not content_summary)
- **Tagging retry logic** sometimes needs improvement for complex articles
- ~~**Guest query limit**~~ — **DONE (June 2026):** `guest_sessions` table and `increment_guest_query` RPC created in Supabase.
- ~~**RLS policies needed** on `conversations` and `messages` tables~~ — **DONE:** RLS enabled on both
- **INCLUDE_COPYRIGHTED not confirmed on Railway** — check dashboard
- **poppler no longer required** — pdf2image replaced by PyMuPDF (fitz) in extract_magazine.py
- **Bible ref extraction occasionally produces malformed JSON** from Groq on edge-case batches (~1 in 38 docs in backfill run). Helper handles gracefully by dropping that segment and continuing; other segments in the same doc still succeed.
- **System prompt and chat.py changes deployed** (2026-04-15) — pushed to main; Railway/Vercel should auto-deploy.
- **Anthropic + Cohere rerank deployed** (2026-04-17) — answer gen switched to Claude Sonnet 4.5, Cohere rerank-v3.5 added. Pushed to main.
- **Article reader date display** — issue date (month/year) added to frontend but not yet visually confirmed in browser. `console.log` left in `handleCardClick` for debugging — remove after confirming.
- **30 malformed JSON chunks fixed** (2026-04-17) — `fix_article_json.py` migration ran successfully; content_summary refreshed on all 30 affected documents.
- **Shell aliases expanded** — 11 `rh-*` aliases in `~/.zshrc` covering all pipeline scripts (includes `rh-individual` for individual video ingestion).
- **Proposed but unapplied system prompt changes** (2026-04-29 session): example response section, retrieval formatting (bullets→headings+prose), softer Holy Spirit guardrails revision, Niagara Falls metaphor ban, "Go Deeper" follow-up questions, NIV translation preference. All shown as diffs but not confirmed by user.
- ~~**Migration 016**~~ — **DONE:** verses table created, 31,098 rows ingested via `ingest_bible.py`
- **`scrape_preceptaustin.py` hardened version not yet re-run** — page cache from first run will speed up re-run; first run had 2.6% success rate before DOM fix
- **`ingest_preceptaustin.py` not yet run** — depends on successful scrape completion
- ~~**TBESG re-ingestion**~~ — **DONE:** 11,034 chunks ingested in brief mode (gloss + bold sub-meanings)
- **Debug logging in study.py lexicon endpoint** — verbose print statements added for TBESG debugging. Remove after confirming lexicon endpoint works correctly with re-ingested TBESG data.
- ~~**Study Mode interlinear data is placeholder only**~~ — **DONE:** Live from `interlinear_words` table (142,096 rows), fetched via `GET /study/interlinear` endpoint.
- ~~**Migration 017 (saved_words)**~~ — **DONE:** saved_words table exists with RLS enabled
- **10 YouTube transcripts ingested (2026-05-22)** — side effect of running skip tracking test against `youtube/ingested/`. These had different MD5 hashes than stored (likely re-cleaned). 1 duplicate ("Your Calling Is Holy" by Derek Prince) was found and the older copy deleted.
- ~~**`mode-toggle.tsx` is orphaned**~~ — **DONE (2026-06-11):** Deleted. Was unused in all routes.
- **Word study excerpt generation 96% complete** — 1,713 of 1,779 word_study documents have excerpts generated (`excerpts` table, `excerpt_type = 'word_study_article'`). 66 remaining. Script: `scripts/generate_excerpts.py`.
- **Commentary ingestion not yet run** — `scripts/ingest_commentaries.py` rewritten and pushed, needs to be executed (325 fathers, 82,567 rows from SQLite DB at `/tmp/commentaries-db/data.out`).
- **Hebrew word study pipeline ready** — `scrape_preceptaustin.py --language hebrew --fetch` and `ingest_preceptaustin.py --language hebrew` ready to run.
- **Taxonomy expanded to 257 tags** (May 2026) — old 100-tag/8-category taxonomy replaced with 257-tag/15-category version. `taxonomy.md` and `scripts/taxonomy.py` updated. Existing documents still have old tags — need full retag via `retag_sermons.py --force`.
- **Full sermon retag not yet run** — `scripts/retag_sermons.py` tested with `--limit 3 --dry-run --suggest-tags --force` (3/3 success). Full run (`--force`) needed to retag all ~557 sermon_transcript documents against new taxonomy.
- ~~**Individual video ingestion not yet run**~~ — **DONE:** 10 original videos ingested + 11 Daniel Kolenda Cessationism series added. 2 Kolenda videos ingested (1 & 2), 9 failed ("No captions and Whisper failed") — reset to Pending for retry. Likely yt-dlp cookie/bot detection issue.
- **Uncommitted changes from May 2026 session** — taxonomy.md, taxonomy.py, retag_sermons.py, scrape_channel_titles.py, channel_titles.csv, tag_suggestions.jsonl. Need commit + push.
- **3 YouTube channels not found** — Dr. Michael Brown (`@AskDrBrown`), Jack Deere (`@JackDeere`), Myles Munroe (`@MylesMonroeTV`) handles don't resolve on YouTube. Need correct handles or removal from channel_titles scraper.
- **Individual Videos dashboard card** — added to corpus admin Pipelines group, filters on `source_name ILIKE '%Individual Videos%'`.
- **Interlinear deployment verification needed** — confirm `GET /study/interlinear` works on live Railway (tested locally only).
- ~~**SUPABASE_DB_URL psycopg2 connection refused**~~ — **FIXED:** dotted username was being truncated by psycopg2 URI parsing. All scripts now use `urlparse` + explicit keyword args.
- ~~**Migration 028 pending**~~ — **DONE:** `match_commentary_by_book` RPC applied.
- ~~**Commentary bible_references incomplete**~~ — **DONE:** All 307 HistoricalChristianFaith commentaries backfilled (2026-05-30). 400 got refs, 93 had no refs.
- ~~**Jewish Perspective GEMINI_API_KEY env var mismatch**~~ — **FIXED:** changed to `GOOGLE_API_KEY` in `jewish_perspective.py`.
- ~~**Chat endpoint 500 error (HTTP/2 framing)**~~ — **FIXED:** "Trailers must have END_STREAM set" error from httpcore. Pinned `httpcore>=1.0.7` and forced Cohere client to HTTP/1.1.
- **Migration 029 pending** — `match_commentary_chunks` RPC must be run in Supabase SQL Editor before scoped commentary vector search works. Without it, the commentary endpoint will 500 when book doc IDs are found.
- **Commentary `bible_references` mismatch** — `match_commentary_by_book` uses `&&` (array overlap) checking for bare book name `"John"`, but backfill stored references as `"John 3:16"`, `"John 1:1"` etc. The RPC only matches docs that happen to have the bare book name in their array. Needs either SQL function change to `LIKE 'John%'` or backfill to also include bare book names.
- ~~**Commentary not showing in study mode for disabled authors**~~ — **FIXED:** `study_filters` in commentary endpoint ignores `source_name` toggles (chat-only).
- ~~**Commentary chunks returned single chunk content in study mode**~~ — **FIXED (2026-06-03):** `/study/commentary` now uses `_fetch_neighbor_content()` (±1 chunk) for commentary results, matching existing sermon expansion. Deployed to Railway.
- **Commentary chunk bible_references 4.3% coverage** — `backfill_phrase_refs.py` phrase matching only populated 3,731 of 86,501 commentary chunks. Remaining 82,770 need LLM-based extraction (similar to `backfill_chunks` for sermons).
- **Sermon chunk bible_references backfill complete** — 582 docs, 4,881 chunks, 11,557 refs, 0 failures (see `logs/backfill_chunks.log`).
- **9 Kolenda Cessationism videos pending retry** — videos 3–11 failed with "No captions and Whisper failed". Reset to Pending in `individual_videos.xlsx`. Likely need fresh `scripts/youtube_cookies.txt` or different yt-dlp player client args.
- **Daniel Kolenda not in youtube_tracker.xlsx** — only in `individual_videos.xlsx` (not a channel scrape).
- **Migration 033 pending** — `books.document_id` column. Must run in Supabase SQL Editor, then backfill with `UPDATE books b SET document_id = d.id FROM documents d WHERE lower(b.title) = lower(d.title) AND lower(b.author) = lower(d.author)`. "Read Excerpts" button on book cards won't render until this is done.
- **Migration 034 pending** — `book_quotes` table. Must run in Supabase SQL Editor before `extract_book_quotes.py` can be executed.
- **`extract_book_quotes.py` not yet run** — depends on migration 034. Will extract ~50 quotes per Murray book via Claude Haiku 4.5.
- **Library book reader supports quotes + chunk fallback** — `GET /library/book/{id}` returns `quotes` array if `book_quotes` has data for the document, otherwise falls back to `chunks` array. Frontend handles both shapes.
- **`/ingest` endpoint now admin-only (2026-06-10)** — was open to any authenticated user (corpus-pollution risk). Now uses `require_admin` (email check) from `auth.py`; dead `_require_user` helper removed. Deployed on next git push.
- **JWT payload logging removed + log level INFO (2026-06-10)** — `auth.py` no longer logs full JWT payloads (was leaking emails/claims into Railway logs); `main.py` `basicConfig` changed DEBUG → INFO. Deployed on next git push.
- **RLS disabled on `verses`, `excerpts`, `background_topics` (found 2026-06-10)** — anon key has full read/WRITE on these three tables. `background_topics` content is injected into chat prompts, so anon write = prompt-injection vector. Enable RLS with public-SELECT-only policies. (Verified live: `conversations`/`messages` have correct owner policies; `documents`/`chunks` are public-SELECT-only — those are fine.)
- **`interlinear_words` INSERT policy is `WITH CHECK (true)`** (migration 023) — named "service role" but allows anon inserts. Change to `auth.role() = 'service_role'`.
- **`match_sermon_chunks_by_ref` seq-scans all 193k chunks (2026-06-10 review)** — `verse_ref = ANY(c.bible_references)` cannot use the GIN index (0 scans ever, confirmed via EXPLAIN). Fix: change predicate to `c.bible_references @> ARRAY[verse_ref]`. Worst query in the system; hits every Study Mode commentary load with a verse_id.
- **Chat FTS arm returns 0 matches for sentence queries (verified 2026-06-10)** — `websearch_to_tsquery` ANDs all terms; full-sentence questions and Groq paraphrase variants match nothing. Fix: have query expansion emit a keyword variant for the FTS arm. Related: original user question is never searched — `expand_query()` replaces it with 3 paraphrases.
- **`search_documents` RPC ignores stored `chunks.fts`** — snippet subquery recomputes `to_tsvector('english', c.content)` per chunk (~1,100 parses per search at 55 chunks/doc × 20 results). Fix: use `c.fts` in both the filter and `ts_rank`.
- **HNSW index built with default params** — m=16, ef_construction=64, float32; 1.47 GB at 193,775 chunks (→ ~3.8 GB at 500k, RAM risk). Plan: re-embed at 1024 dims (~$3) or halfvec index, rebuild with ef_construction=128. Full scaling roadmap in 2026-06-10 architecture review.
- **24,429 chunks (12.6%) have `source_kind='unknown'`** — early-ingest books/papers backfilled as 'unknown' by migration 005. Invisible to source toggles; backfill before any source_kind-based retrieval work.
- **`conversations.updated_at` never updated** — no trigger exists; sidebar orders by it, so appending to an old conversation doesn't bubble it up. Add trigger on `messages` INSERT + indexes `messages(conversation_id, created_at)`, `conversations(user_id, updated_at DESC)`.
- **`articles` table is empty (0 rows)** — no backend references; six indexes. Drop it. Also droppable: `chunks.parent_chunk_id`/`chunk_type`/`page_number`/`source_hash` (unused), `idx_documents_year`, `idx_documents_source_year_issue`, duplicate `verses_verse_id_idx`.
- **Security review follow-ups (2026-06-10, not yet done)** — verify API keys were rotated after the 2026-04-09 BFG history scrub; Python 3.9 is EOL (bump nixpacks to python312); PyPDF2 deprecated → pypdf; guest `anon_id` is client-generated and spoofable (limit bypassable; add per-IP rate limiting); no rate limits on unauthenticated embed-cost endpoints (`/search`, `/study/corpus`, `/study/commentary`); `/jewish-perspective` POST bypasses daily query limit; admin email hardcoded in `auth.py` + `admin/page.tsx`; `/rhemata-corpus-admin` page has no auth guard.
- **Retrieval quality follow-ups (2026-06-10 review, not yet done)** — rerank pool too small (Cohere sees only RRF top-10; should rerank ~50 fused candidates then apply caps); content-type pollution (commentary 44.6% + lexicon 19.1%, both silent_context, compete for top-40 against 8% citable sermons — needs source_kind retrieval pools after denormalizing source_kind/citation_mode onto chunks); neighbor expansion should skip commentary/lexicon; `[Source N]` numbering includes silent_context chunks while frontend citations array is filtered (misalignment risk); low-material fallback counts neighbors/lexicon instead of citable chunks.
- **Phase 4 hex→token migration reverted by linter (2026-06-11)** — Phase 4 ran successfully (grep zero hits, build pass) in the prior session, but linter subsequently reverted all edits. Confirmed old hex still present in: `components/center/DocumentCard.tsx`, `app/rhemata-corpus-admin/CorpusCard.tsx`, `app/rhemata-corpus-admin/CardModal.tsx`, plus likely all other Phase 4 targets (`app/admin/page.tsx`, `app/admin/edit/[id]/page.tsx`, `app/rhemata-corpus-admin/page.tsx`, `app/library/page.tsx`, `app/library/authors/page.tsx`, `app/library/book/[id]/page.tsx`, `app/document/[id]/page.tsx`). Re-run needed; investigate linter config first.
- ~~**Chat page floating panel layout**~~ — **DONE (2026-06-11):** `app/page.tsx` restructured — outer shell `bg-sidebar`, main panel `bg-background rounded-xl` (8px inset). Scroll fade added. Top bar border removed. `sidebar.tsx` desktop + mobile `border-r border-sidebar-border` removed. Committed `d982a13`.

---

## How to Work on This Project
- **Code changes always go to Claude Code in terminal** — do not write or edit code in chat unless the change is trivial (1-2 lines)
- Alex works fast — short messages, quick pivots, direct feedback
- Surface risks and blockers before building, not after
- When Alex references a component, check the actual file before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
