# Rhemata — Claude Code Context

## Project Overview
Rhemata is an AI-powered theological research tool for charismatic Christians. RAG-based chat interface with inline citations. Modeled after Magisterium AI (product) and Perplexity (UX).

---

## Session Routing

This table is the load-map. For a given session type, load the listed CLAUDE.md sections and
files; skip the rest to save context. An agentic loop or a fresh session should read this table
first and load only what the row calls for.

**Always loaded (every session — small, cheap):**
- CLAUDE.md: Project Overview, this Session Routing table, Tech Stack, How to Work on This
  Project, Project Knowledge Read Contract
- rhemata-status.md (full — live session state)
- PLAN.md: Standing session rules, the current session's row, Open decisions table

Everything below is loaded IN ADDITION to that core.

| Session type | Also load | Skip |
|---|---|---|
| Chokepoint conversion (PLAN #6–13) | CLAUDE.md: Directory Structure, both Scripts tables, the propositions-per-script section, the shared_ingest decision entry; plus the specific script file being converted | POSITIONING.md, DESIGN.md, most of Database, frontend tree |
| Propositions / quote backfill (#17, #25) | CLAUDE.md: Database (propositions + chunks schema), propositions-per-script section, relevant decision entries; plus scripts/propositions.py | POSITIONING.md, DESIGN.md, frontend tree, Key Commands |
| Core serving / retrieval (#15–20) | CLAUDE.md: Database (retrieval pipeline, RPCs) + these Key Decisions entries — License Control System (289–297), SOURCE_KIND_FUSION_WEIGHTS (275), Commentary context cap (276), Neighbor expansion skips commentary/lexicon (277), FTS OR-fallback (278), citable_count gate (279), Low-material fallback rework (280), System prompt rewrite (281); plus backend/app/routers/chat.py, search.py. For #18 specifically (propositions into retrieval RPCs): also the Propositions layer decision entry (303–315). | Scripts tables, marketing, DESIGN.md unless the sub-step touches UI |
| Quote track (#21–24) | CLAUDE.md: Database (chunks schema — verifier ground truth), propositions-per-script section; POSITIONING.md (quote posture / guardrail #3) | DESIGN.md, frontend tree, Scripts tables |
| Corpus growth (#26–29) | CLAUDE.md: Directory Structure, Scripts tables, propositions-per-script section, the license/alias decision entries | POSITIONING.md, DESIGN.md, Database internals, frontend tree |
| Marketing / landing (#5) | CLAUDE.md: docs/ + frontend marketing tree; POSITIONING.md (full); DESIGN.md | Database, Scripts, propositions, migrations |
| Backend infra (#4 Resend; #32–37) | CLAUDE.md: relevant backend tree, Environment Variables, relevant decision entries | POSITIONING.md, DESIGN.md, Scripts tables, Database internals |
| Planning / status / plan revision | PLAN.md (full); rhemata-status.md; POSITIONING.md if positioning is in question | All CLAUDE.md heavy blocks (Directory, Database, Decisions, Scripts), frontend tree |

Note: "Key Decisions" is coarse here — most sessions need some entries, none need all. When the
CLAUDE.md restructure (thin core + pull-on-demand detail) lands, these rows get precise.

---

## Directory Structure
```
/Users/alexwhitley/rhemata/
├── sources/
│   ├── youtube/               # YouTube transcript pipeline
│   │   ├── raw/               # Freshly scraped transcripts
│   │   ├── cleaned/           # Groq-cleaned, ready for ingest
│   │   ├── ingested/          # Already in Supabase
│   │   │   └── ingest_queue.xlsx       # Master ingest queue (Queue + HowToRun control tabs + source tabs; gitignored)
│   │   # NOTE: youtube_tracker.xlsx and individual_videos.xlsx archived to _archive/2026-06-27/ (2026-06-27)
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
│   ├── ingest.py              # Standalone PDF/docx/txt ingestion with auto-tagging; skip_dedup=False param on ingest_file(); routes resolve/insert/chunk/embed/propositions through shared_ingest.py
│   ├── shared_ingest.py       # Shared document-writer chokepoint (ingest_document()): resolve -> insert -> chunk -> embed -> propositions. Converted: ingest.py (1 of 5). Not yet: ingest_magazine.py, ingest_preceptaustin.py, ingest_lexicon.py, ingest_commentaries.py
│   ├── youtube_triage.py      # Stage 2: channel enumeration + Groq classification; exports process_sheet() callable; --sheet NAME still works direct
│   ├── youtube_ingest.py      # Stage 3: transcript fetch + ingest_file(skip_dedup=True); exports ingest_sheet() callable; --sheet NAME still works direct. SELF-CONTAINED as of 2026-06-27 (find_ytdlp, try_auto_captions, download_and_whisper, clean_transcript, CLEANING_PROMPT inlined; no longer imports from scrape_individual_videos)
│   ├── run_queue_triage.py    # Stage 5 Run 1: Queue-driven triage orchestrator (reads Queue tab, drives process_sheet per source)
│   ├── run_queue_ingest.py    # Stage 5 Run 2: Queue-driven ingest orchestrator (walks source tabs, drives ingest_sheet per tab)
│   ├── discover_sermonindex_playlists.py  # Discovery-only: enumerate SermonIndex playlists vs whitelist_sermonindex.txt (prints only, zero writes)
│   ├── whitelist_sermonindex.txt          # 17-entry whitelist for SermonIndex multi-speaker channel (13 speakers; period variants for Tozer/Austin-Sparks)
│   ├── propositions.py        # Shared proposition extraction + storage module (Groq v3 prompt, process_document entry point)
│   ├── tag_existing_articles.py   # Backfill topic_tags on existing articles via Groq
│   ├── tag_sermons_transcripts.py # Backfill topic_tags on sermons/transcripts/papers via Groq
│   ├── scrape_preceptaustin.py    # Scrape Precept Austin Greek/Hebrew word studies
│   ├── ingest_preceptaustin.py    # Ingest Precept Austin word studies into Supabase
│   ├── ingest_lexicon.py          # Ingest STEPBible lexicon files (TBESG, TBESH, TFLSJ)
│   ├── ingest_bible.py            # Ingest WEB Bible into verses table
│   ├── ingest_interlinear.py      # Ingest STEPBible interlinear NT into verses table
│   ├── ingest_tahot.py            # Ingest TAHOT Hebrew OT alignment data
│   ├── extract_bible_refs.py      # Backfill bible_references on all documents
│   ├── download_book_covers.py    # Download book cover images to frontend/public/images/books/
│   └── test_metering.py           # End-to-end metering test suite (increment, rollover, hard stop)
├── taxonomy.md                # 258-tag topic taxonomy (15 categories); generated from scripts/taxonomy.py, the source of truth
├── migrations/                # SQL migrations (run in Supabase SQL Editor)
│   ├── 038_pastors_notes.sql  # user_roles, contributor_requests, pastors_cards tables + RLS
│   ├── 039_user_usage.sql     # user_usage table + increment_user_query + get_user_usage RPCs
│   ├── 040_fix_increment_user_query.sql  # Conditional increment (SELECT FOR UPDATE, returns allowed bool)
│   ├── 041_pastors_notes_approval.sql    # Adds 'pending' status to pastors_cards, RLS for own-pending read, get_user_emails RPC
│   ├── 042_document_image_url.sql        # Adds nullable image_url (text) column to documents — run before setup_document_images.py
│   ├── 043_sources_license.sql           # sources table (one row per rights-holder) + source_license_audit; RLS service-role only
│   ├── 044_documents_source_id.sql       # documents.source_id uuid FK → sources (ON DELETE SET NULL) + index
│   ├── 045_sources_visible.sql           # sources.visible boolean (superseded by 046)
│   ├── 046_sources_visibility.sql        # replaces visible with visibility text ('shown'|'hidden', DEFAULT 'hidden' = fail-closed)
│   ├── 047_retrieval_visibility_gate.sql # visibility gate WHERE clause in match_chunks + search_chunks_fts (variant a)
│   ├── 048_safe_mode.sql                 # app_settings table + safe_mode='off' row; gate reads flag once per RPC call
│   ├── 049_seal_null_source_id.sql       # sentinel source row + backfill 18 orphans + NOT NULL + ON DELETE SET DEFAULT + removes IS NULL gate arm
│   ├── 050_source_aliases.sql            # source_aliases table + 54 normalized alias seeds; adds CLF Church + An Unknown Christian sources
│   ├── 051_propositions_table.sql        # propositions table + HNSW index + GIN fts index + btree document_id index (SHIPPED 2026-06-25)
│   ├── 052_guest_sessions.sql            # guest_sessions table + increment_guest_query RPC — documents existing live schema; idempotent (COMMITTED 2026-06-26)
│   ├── 053_original_title.sql            # adds documents.original_title column only — the 3,678-row backfill ran separately, not in this file (APPLIED 2026-06-27)
│   ├── 054_removed_urls.sql              # removed_urls blocklist table (url PK, document_id, title, original_title, removed_at, reason) (APPLIED 2026-06-29)
│   ├── 055_lock_corpus_tables.sql        # RLS lockdown: drops public-read policies on documents/chunks, enables RLS on propositions/removed_urls — corpus no longer dumpable via anon key (APPLIED 2026-06)
│   ├── 056_gate_remaining_rpcs.sql       # ports the license gate to the 5 retrieval RPCs that bypassed it (match_lexicon_chunks, match_commentary_by_book, match_commentary_chunks, match_sermon_chunks_by_ref, search_documents) (APPLIED 2026-06)
│   ├── 057_guest_ip_rate_limit.sql       # guest_sessions.ip_address + IP-capped new-session creation in increment_guest_query (20/hr/IP) — closes anon_id-rotation metering bypass (APPLIED 2026-07)
│   └── 058_clf_aliases.sql               # source_aliases: 'alex whitley' (author-key) + 'clf church' (source_name-key), both -> CLF Church (29bfe81f-a150-4e43-baac-042e366fb4b3) — closes migration-050 doc/DB mismatch (APPLIED 2026-07-03)
├── CLAUDE.md                  # This file
├── SKILL.md                   # Full project skill context
├── docs/                      # Source markdown for static marketing pages
│   ├── how-rhemata-handles-sources.md   # Content source for /sources page
│   └── our-theological-lens.md          # Content source for /beliefs page
├── backend/
│   ├── app/                   # FastAPI Python package
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── auth.py            # JWT auth via Supabase JWKS; shared DB-role guard (get_user_role, require_admin_role, require_contributor) — used by admin/feedback/ingest/pastors-notes
│   │   ├── .env               # Environment variables
│   │   ├── routers/
│   │   │   ├── chat.py        # /chat endpoint — retrieval + LLM
│   │   │   ├── search.py      # /search + /search/documents endpoints
│   │   │   ├── document.py    # /document/{id} + /document/{id}/article
│   │   │   ├── library.py     # /library/books + /library/book/{id} + /library/doc-meta + /library/recent + /library/counts
│   │   │   ├── study.py       # /study/verse + /study/corpus + /study/lexicon + /study/excerpt + /study/interlinear + /study/commentary + /study/wordsearch + /study/wordstudy
│   │   │   ├── pastors_notes.py  # /pastors-notes/* — cards (pending/approve/reject), requests, role management; /pastors-notes/pending + /recent
│   │   │   ├── usage.py       # GET /usage — weekly query count for authenticated users
│   │   │   ├── ingest.py      # /ingest endpoint (admin-only as of 2026-06-10)
│   │   │   ├── admin.py       # /admin/* — sources, document edit/delete, corpus documents, license-sources + visibility/license-status toggles, safe-mode get/set, stats, card-counts (admin-role gated)
│   │   │   └── feedback.py    # /feedback — POST submit (open) + GET read (admin-role gated)
│   │   ├── services/
│   │   │   ├── embeddings.py
│   │   │   ├── chunker.py
│   │   │   ├── metadata.py
│   │   │   ├── extractor.py
│   │   │   └── source_filter.py  # source_toggles lookup for disabled sources (60s cache)
│   │   ├── db/
│   │   │   └── supabase.py
│   │   ├── system_prompt.txt
│   │   └── theological_guardrails.txt
│   ├── requirements.txt       # Pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml          # Locks Python 3.9
└── frontend/                  # Next.js 16 frontend (Vercel)
    ├── app/
    │   ├── home/              # Public marketing landing page (no auth required)
    │   │   └── page.tsx       # Animated mockups, marquee, Why It Matters, CTA — BetaGate + LoginModal wired; footer includes FooterNav (Home | Sources | Beliefs)
    │   ├── sources/           # Static marketing page (2026-07-06)
    │   │   └── page.tsx       # "How Rhemata Handles Sources" — rendered from docs/how-rhemata-handles-sources.md content
    │   └── beliefs/           # Static marketing page (2026-07-06)
    │       └── page.tsx       # "Our Theological Lens" — rendered from docs/our-theological-lens.md content
    ├── contexts/
    │   └── chat-focus-context.tsx    # ChatFocusContext — shares input focus state between ChatInput and MobileTabBar; drives tab-bar keyboard-hide + pb-0 main padding when focused
    ├── hooks/
    │   ├── useUserRole.ts     # Role + displayName hook; module-level cache keyed by access token; 5-minute TTL
    │   └── useChat.ts         # weeklyUsage state; seeds from GET /usage on mount, updates from SSE meta
    ├── components/
    │   ├── auth/
    │   │   └── BetaGate.tsx          # Beta password gate modal — prompts for "rhema", stores beta_access in sessionStorage
    │   ├── marketing/                # Shared components for static marketing pages (2026-07-06)
    │   │   ├── article.tsx           # Long-form article typography primitives (ArticlePage/H1/H2/H3/P/Refs/Ol/...)
    │   │   └── footer-nav.tsx        # "Home | Sources | Beliefs" muted pipe-separated nav — used in /home footer AND app-shell Sidebar bottom-left
    │   ├── admin/
    │   │   ├── AdminModal.tsx        # 4-tab admin popup: Corpus (Documents/Sources/Pipelines sub-views), Feedback, Contributors, Notes Queue
    │   │   └── CorpusDocumentsPanel.tsx  # Paginated doc list with stats, filters, View Sheet, Remove AlertDialog; exports CopyButton + CorpusLicenseSource
    │   ├── ui/
    │   │   └── alert-dialog.tsx      # Radix UI AlertDialog primitive (all sub-components)
    │   └── rhemata/
    │       ├── mobile-tab-bar.tsx    # Mobile bottom nav (Study · Chat · Discover); slides off-screen via translate-y-full when inputFocused (reads ChatFocusContext)
    │       ├── usage-ring.tsx        # SVG weekly usage ring (track=--muted, arc=--foreground)
    │       └── weekly-limit-card.tsx # Inline hard-stop card on 429; BILLING_ENABLED=false flag
    ├── package.json
    └── ...
```

---

## Key Commands

### Deploy Backend
Backend deploys to Railway via git push to main. There is no local backend.
```bash
git add -A && git commit -m '...' && git push
```

### Start Frontend
```bash
cd /Users/alexwhitley/rhemata/frontend && npm run dev
# Runs at http://localhost:3000
```

### Ingest Documents (standalone)
```bash
cd /Users/alexwhitley/rhemata && python3 scripts/ingest.py
```

### Magazine Pipeline
```bash
cd /Users/alexwhitley/rhemata
# Step 1: Extract — PDFs in sources/magazine/01_to_extract/ → sources/magazine/02_extracted/
python3 scripts/extract_magazine.py
# Step 2: Review — manually move approved articles to sources/magazine/03_approved/
# Step 3: Ingest — sources/magazine/03_approved/ → Supabase
python3 scripts/ingest_magazine.py
```

### YouTube Pipeline (legacy — scrape_youtube.py path)
```bash
cd /Users/alexwhitley/rhemata
python3 scripts/scrape_youtube.py      # Scrape → sources/youtube/raw/
python3 scripts/clean_transcripts.py   # Clean via Groq → sources/youtube/cleaned/
python3 scripts/ingest.py              # Ingest cleaned transcripts → Supabase
```

### YouTube Pipeline (new — ingest_queue.xlsx path)

Single-source direct (Stage 2/3):
```bash
cd /Users/alexwhitley/rhemata
python3 scripts/youtube_triage.py --sheet "Sam Storms" --add URL   # Stage 2: enumerate + classify
python3 scripts/youtube_ingest.py --sheet "Sam Storms"             # Stage 3: ingest triaged rows
```

Queue orchestrator (Stage 5 — all pending rows):
```bash
cd /Users/alexwhitley/rhemata
# 1. Paste pending URLs into the Queue tab of sources/youtube/ingest_queue.xlsx
#    Columns: url | source_name | review | filter | limit | status
#    filter tokens: min5 (skip ≤5min clips), whitelist (title-whitelist mode)
#    limit: integer cap applied via --playlist-items at yt-dlp enumeration time
# 2. Triage — enumerate + classify all pending Queue rows
python3 scripts/run_queue_triage.py
python3 scripts/run_queue_triage.py --only "Sermonindex"  # single source only
# 3. Review source tabs in the workbook; set ingest=TRUE on approved rows
# 4. Ingest — ingest all ingest=TRUE triaged rows across all source tabs
python3 scripts/run_queue_ingest.py
python3 scripts/run_queue_ingest.py --sheet "Sam Storms"  # single tab only
```

### Backfill Topic Tags
```bash
cd /Users/alexwhitley/rhemata && python3 scripts/tag_existing_articles.py
cd /Users/alexwhitley/rhemata && python3 scripts/tag_sermons_transcripts.py
```

---

## Design System
Design system: `DESIGN.md` in project root is the styling authority. Lumen system (shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme locked via `forcedTheme`). Chat page, sidebar, library, study, and admin pages are on design tokens. `components/center/DocumentCard.tsx` and `app/admin/edit/[id]/page.tsx` editor panel still carry old hex — re-migration pending.

---

## Tech Stack
- **Frontend:** Next.js 16 (React 19), Tailwind CSS 4 — deploys to Vercel
- **Backend:** Python 3.9 / FastAPI — deploys to Railway
- **Database:** Supabase (PostgreSQL + pgvector)
- **Embeddings:** OpenAI `text-embedding-3-small` (1536 dims)
- **Answer Generation LLM:** Anthropic Claude Sonnet 4.5 (`claude-sonnet-4-5`) via `anthropic` SDK
- **Query Expansion / Metadata / Tagging / Transcript Cleaning LLM:** Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- **Reranking:** Cohere rerank-v3.5 (`cohere` SDK) — narrows top 30 RRF → top 8
- **Vision / OCR (magazine extraction):** Gemini 2.5 Flash (`gemini-2.5-flash`) via `google-genai` SDK
- **Markdown rendering:** `react-markdown` + `@tailwindcss/typography`
- **Removed:** GPT-4o Vision (replaced by Gemini 2.5 Flash)

---

## Database
- **Supabase** with pgvector enabled
- Tables: `documents`, `chunks`, `propositions`, `verses`, `saved_words`, `excerpts`, `guest_sessions`, `conversations`, `messages`, `interlinear_words`, `book_quotes`, `user_usage`, `sources`, `source_aliases`, `source_license_audit`, `app_settings`, `removed_urls`
- `documents.source_type` — `'sermon'` | `'background'` | `'magazine_article'` | `'commentary'` | `'book'` | `'paper'` | `'other'`
- `documents.source_kind` — taxonomy field (e.g. `'magazine_article'`)
- `documents.citation_mode` — `'citable'` | `'silent_context'`
- `documents.is_copyrighted` — boolean, derived from folder path during ingest
- `documents.topic_tags` — text[] assigned from taxonomy (can be `null`, not just empty array — confirmed from live API)
- `documents.bible_references` — text[], canonical refs like `"Romans 8:28"`, GIN indexed
- `documents.fts_weighted` — tsvector on title, author, source_name, topic_tags
- `documents.image_url` — text, nullable; Supabase Storage public URL for featured hero card image (migration 042)
- `documents.source_id` — uuid NOT NULL FK → `sources` (ON DELETE SET DEFAULT, default = sentinel `267a09ac-76f3-43fb-901f-3015aef88e22`); new inserts that omit source_id land on the sentinel (hidden, not served); no NULLs exist post-migration-049; the SQL-layer license gate reads this column
- `documents.original_title` — text, nullable; title as captured at ingest before any display normalization. Populated for all new documents since Session A (June 2026); backfilled on 3,678 rows via migration 053. Shown in CorpusDocumentsPanel when it differs from `title`.
- `removed_urls` table — blocklist of intentionally-deleted URLs: `url text PK`, `document_id uuid`, `title text`, `original_title text`, `removed_at timestamptz DEFAULT now()`, `reason text`. Written by `DELETE /admin/document/{id}` before the delete; checked by `youtube_ingest.py` before each ingest call (non-fatal skip on hit). Migration 054 (APPLIED 2026-06-29).
- `sources` — one row per rights-holder entity (43 rows, including sentinel). `license_status` text ('public_domain'|'owned'|'licensed'|'unlicensed') = truth about rights; `visibility` text ('shown'|'hidden', DEFAULT 'hidden' = fail-closed) = what the gate obeys; `retrievable` generated boolean (informational only, NOT read by the gate). RLS: service-role only.
- `source_aliases` — normalized alias_key (text UNIQUE; lowercase + trim + collapsed whitespace) → source_id FK ON DELETE CASCADE. 54 alias rows across 39 entities. Lookup: `SELECT source_id FROM source_aliases WHERE alias_key = lower(trim(regexp_replace(input, '\s+', ' ', 'g')))`. RLS: service-role only.
- `source_license_audit` — immutable log of `license_status` changes. Created, not yet written by any UI.
- `app_settings` — global key/value table. One row: `key='safe_mode', value='off'`. RLS: service-role only.
- `propositions` — atomic paraphrase-level decompositions of unlicensed documents (migration 051). Columns: `id` uuid PK, `document_id` uuid NOT NULL FK → documents ON DELETE CASCADE, `content` text NOT NULL, `embedding` vector(1536), `proposition_index` int NOT NULL, `fts` tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content,'')) STORED, `created_at` timestamptz. Indexes: `propositions_embedding_hnsw` (HNSW vector_cosine_ops m=16/ef_construction=64), `propositions_fts_gin` (GIN on fts), `propositions_document_id_idx` (btree). Licensing resolves through document_id → documents.source_id → sources — no license columns on propositions by design. Gate (in `propositions.process_document()`, final rule 2026-07-02): extracts for `license_status IN ('licensed','unlicensed')` only; skips `public_domain` and `owned` (already safely servable as verbatim chunks); missing source_id fails closed. One named exception: **Precept Austin never gets propositions** (locked out by source_id constant `PRECEPT_AUSTIN_SOURCE_ID` in propositions.py — its excerpts are near-verbatim reorderings, not paraphrases, and fresh extraction was declined).
- Vector similarity via `match_chunks` SQL function (HNSW index, `hnsw.ef_search=200`)
- Hybrid retrieval: query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) → top 30 (SOURCE_KIND_FUSION_WEIGHTS applied: commentary ×0.6, book ×0.8, lexicon ×0.5) → Cohere rerank top 30 → top 8
- `search_documents` RPC: document-level FTS with highlighted snippets via ts_headline

---

## Key Decisions
- CORS middleware enabled — `ALLOWED_ORIGINS` env var (comma-separated)
- Page-level citations (not chunk-level)
- Two-tier content: citable vs silent_context (controlled by `citation_mode`)
- Magazine chunking: tiktoken cl100k_base, 550 tokens target, 80 overlap
- Standalone ingest: recursive character text splitting, 1000 char chunks, 200 char overlap
- k=30 retrieval pool post-RRF; Cohere reranks to top 8
- Single-column PDFs only — no multi-column OCR needed yet
- Bible Study articles excluded from extraction pipeline
- Topic tagging: 258-tag taxonomy (15 categories), validated against VALID_TAGS set in scripts/taxonomy.py, retry if < 3 valid. taxonomy.py is the single source of truth for all tagging scripts (including retag_sermons.py, fixed 2026-07-02 — it previously parsed taxonomy.md independently, which had drifted to 209 tags); taxonomy.md is generated from taxonomy.py for human reference only.
- is_copyrighted derived from folder path: `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false. **This flag is unreliable** (e.g. Derek Prince docs are `false` despite being copyrighted works). The license gate deliberately ignores it — do not "fix" the gate to read `is_copyrighted`.
- Design system: `DESIGN.md` in project root is the styling authority. Lumen system (shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme locked via `forcedTheme`). No hardcoded hex.
- Brand reset complete (June 2026): Lora/Inter/gold hex removed. Geist Sans, shadcn primitives, CSS variable tokens throughout. `DESIGN.md` is source of truth.
- Study Mode restructured (June 2026): single-column layout, interlinear always visible attached to verse, inline word expansion, commentary visible without tab click, Pastors' Notes stub in place. Tabs removed. (Jewish Perspective feature removed entirely — `jewish_perspective.py` deleted from backend; residual refs only in `frontend/app/library/*` and `backend/app/constants.py`.)
- Guest session migration complete (June 2026): `guest_sessions` table and `increment_guest_query` RPC created in Supabase. Frontend and backend were already wired. Schema documented in migration 052 (committed 2026-06-26, idempotent — RLS and service-role policy live in migration 037). `increment_guest_query` uses INSERT ... ON CONFLICT DO UPDATE upsert; returns bare integer; SECURITY DEFINER bypasses RLS. Backend checks count against `GUEST_QUERY_LIMIT = 6`.
- Pastors' Notes complete (June 2026): three-tier role system (user/contributor/admin), verse-anchored cards, contributor request flow, 50–2000 char limit, soft delete only, auto-tagging via Groq with 5s timeout fallback. Tables: `user_roles`, `contributor_requests`, `pastors_cards` (migrations 038, 041).
- Pastors' Notes approval gate (June 2026): contributor notes save as `'pending'`, require admin approval before publishing; admins post directly as `'published'`. `pastors_cards.status`: `'pending'` | `'published'` | `'removed'`. New endpoints: `GET /pastors-notes/pending` (admin queue with email + display_name), `POST /cards/{id}/approve`, `POST /cards/{id}/reject`. `get_user_emails` RPC in migration 041. `useUserRole` cache TTL 5 min (was indefinite). `GET /cards` optionally authenticated — returns own pending cards to contributor, all pending to admin.
- Admin consolidation (June 2026): all admin surfaces merged into single `/admin` page with sticky anchor-nav (Overview · Contributors · Corpus). Role-based auth via `GET /pastors-notes/me` (no more hardcoded ADMIN_USER_ID). `/admin/contributors` and `/rhemata-corpus-admin` redirect to `/admin`. `app/rhemata-corpus-admin/` deleted. Corpus components in `frontend/components/admin/`. `components/ui/switch.tsx` added (shadcn Switch using radix-ui). Precept Austin Greek card has `notFilter` to exclude Hebrew docs. HistoricalChristianFaith card description corrected. Superseded (June 2026): Corpus anchor-nav section replaced by Governance/Pipelines two-tab view; further superseded by Corpus v2 four-tab popup (Corpus/Feedback/Contributors/Notes Queue; Corpus has Documents/Sources/Pipelines sub-views); backend auth moved from ADMIN_EMAIL email check (broken — never set on Railway) onto user_roles DB guard (auth.py `require_admin_role`) for all 13 `/admin/*`, `/feedback`-read, and `/ingest` handlers; frontend page gate still uses `GET /pastors-notes/me`.
- SOURCE_KIND_FUSION_WEIGHTS (June 2026): applied at step 2.75 of RRF pipeline (before doc-collapse): commentary ×0.6, book ×0.8, lexicon ×0.5, all others ×1.0. Prevents commentary and lexicon from crowding out citable sermons in the top-30 rerank pool.
- Commentary context cap (June 2026): after neighbor expansion, commentary chunks capped at 3 in final assembled context (`COMMENTARY_CONTEXT_CAP = 3`).
- Neighbor expansion skips commentary/lexicon (June 2026): `_NEIGHBOR_SKIP_KINDS = frozenset({"commentary", "lexicon"})` — their neighbors are not fetched. They add no useful context and would further crowd out citable content.
- FTS OR-fallback (June 2026): when `websearch_to_tsquery` returns 0 FTS results, `hybrid_search_rrf()` retries with OR-joined query of up to 3 longest meaningful tokens (min 6 chars, common theological/stopword terms excluded via `_FTS_BROAD_TERMS`). Prevents multi-term keyword queries from silently failing the FTS arm.
- citable_count gate (June 2026): counted from post-Cohere, pre-neighbor-expansion top-8 window. Only sermon/citable chunks count. Controls graceful-degradation and fallback paths.
- Low-material fallback rework (June 2026): hard short-circuit fires only for truly empty chunk sets. When `citable_count < 2` but silent_context chunks exist, proceeds to normal LLM call with retrieval note appended to context block. System prompt graceful-degradation rules handle the response.
- System prompt rewrite (June 2026): conviction-first classification (settled convictions evaluated BEFORE retrieved sources; source diversity never reclassifies a conviction as debate); voice and attribution firewall (inflammatory language banned from Rhemata's own voice); graceful degradation (WHAT → synthesize from background; WHO/attribution → direct to Study Mode; truly uncovered → bare refusal); verbatim retrieval quotes permitted up to 50 words from citable sources only; `<research_analysis>` expanded to 5 checks (added demotion guard and voice firewall check).
- Weekly query metering (June 2026): 50 queries/week per authenticated user, Monday UTC reset. `user_usage` table; `weekly_limit` stored per-row (not hardcoded) so Phase 2 billing can override per user. `increment_user_query` RPC uses `SELECT FOR UPDATE` + conditional UPDATE — counter never exceeds limit, no race at cap. Returns `allowed bool`; hard 429 fires before any LLM call. SSE meta includes `usage: {used, limit, week_start}`. Study endpoints excluded from count. Guest meter unchanged. Frontend: `useChat` owns state, seeds from `GET /usage` on mount, updates from SSE meta. `BILLING_ENABLED=false` flag in `weekly-limit-card.tsx`.
- Discover page (June 2026): `app/library/page.tsx` rewritten as 6-section Discover view. Section order: Featured → Browse by type → Featured Authors → Recently Added → New Wine Archive → Pastors' Notes. All sections always render (empty state shown when no data). No card renders `description` or `content_summary` — both fields contain raw body text; omit-when-absent rule applies to all cards. Card display: type chip, author, title, up to 2 topic tags, year only.
- Featured section daily rotation (June 2026): `FEATURED_SERMON_POOL` (8 sermons) and `FEATURED_ARTICLE_POOL` (7 New Wine articles) in `app/library/page.tsx`. LCG seeded by UTC day index, two independent seeds (`dayIndex * 2`, `dayIndex * 2 + 1`). Returns `[articles[0], sermons[0], sermons[1]]` — article in hero, sermons in supporting slots. Books excluded from Featured eligibility.
- Hero card image slot (June 2026, revised): Featured hero uses `grid-cols-[3fr_2fr] gap-6` (60/40), grid stretch (no `items-start`), `text-xl` title, tightened margins. Right panel: `<Image fill object-cover>` when `image_url` present, sparkle `✦` placeholder otherwise. `image_url text` column via migration 042 (APPLIED — column live, 1 doc populated). `document-images` Supabase Storage bucket (public); first image: `mumford-life-of-worship.jpg`. `frontend/next.config.ts` adds Supabase hostname to `images.remotePatterns`.
- FastAPI `Query` import bug (June 2026): Any `Query(...)`, `Path(...)`, etc. used as route default parameters are evaluated at module import time — missing import causes `NameError` → uvicorn never binds → all routes in the file are absent (not a 500; they 404). Always include fastapi symbols in the import line if used as defaults.
- `/home` landing page (June 2026, copy rewrite 2026-07-02 commit f4642bc): Public route `app/home/page.tsx` — no auth required. Animated Chat/Study mockups (IntersectionObserver, once at 30% viewport), marquee, Why It Matters two-column contrast, Final CTA. Copy rewritten per POSITIONING.md (anti-flattening hook, verified-quote proof, Pastors' Notes reframed as coming). Discover feature section + DiscoverMockup component + nav `/library` link + Jewish Perspective explore card all DELETED 2026-07-02 — Library is a low-priority pointer directory per positioning, not a landing feature. New CSS token: `--gold-light: 44 60% 62%` in `globals.css`. `/` route untouched.
- Beta password gate (June 2026): `components/auth/BetaGate.tsx` — client-side modal, required code "rhema", stores `beta_access=1` in `sessionStorage` on success. Wired in all three app pages and `/home`. "Try it free — no account needed" and direct `/` are ungated. `LoginModal` gained `initialMode?: "signin" | "signup"` prop; sidebar guest footer changed from "Sign in" to "Become a test user" primary Button.
- License Control System (June 2026, migrations 043–050): SQL-layer fail-closed gate preventing unlicensed content from reaching retrieval. Does NOT touch `INCLUDE_COPYRIGHTED` env flag or Python `citation_mode` filtering — both still operate as before.
  - **Migrations 043–048** established the `sources` table, `documents.source_id` FK, two-column model (`license_status`/`visibility`), SQL-layer gate in both RPCs, and `app_settings`/`safe_mode`.
  - **Migration 049 (2026-06-24) — NULL hole sealed:** The prior gate had a `d.source_id IS NULL OR ...` arm that passed documents with no source unconditionally — fail-OPEN. Fix: (a) Created PROTECTED SENTINEL source (fixed UUID `267a09ac-76f3-43fb-901f-3015aef88e22`, "Unassigned — needs source", `unlicensed/hidden`). (b) Backfilled the 18 then-orphaned docs onto the sentinel. (c) `documents.source_id` is now NOT NULL with DEFAULT = sentinel UUID; FK changed from ON DELETE SET NULL to ON DELETE SET DEFAULT. (d) Removed the IS NULL arm from BOTH RPCs — eligibility is now purely the EXISTS check. ⚠ **NEVER DELETE the sentinel row `267a09ac-76f3-43fb-901f-3015aef88e22`** — it is the FK DEFAULT target; deleting it breaks every document pointing at it. The admin UI must hard-guard against deleting it.
  - **Migration 050 (2026-06-25) — source_aliases lookup table:** `source_aliases` (alias_key text UNIQUE normalized → source_id FK ON DELETE CASCADE). 54 aliases seeded across 39 entities. New source rows: "CLF Church" (`clf-church`, `owned/shown`) and "An Unknown Christian" (`public_domain/shown`). F.F. Bosworth set to `unlicensed/hidden` (d.1958, not US public domain).
  - **Gate rule (MUST be preserved in all future RPC edits):** `EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id AND (s.license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility = 'shown')))`. `safe_mode_on` is a plpgsql variable read ONCE per function call. Both RPCs are `LANGUAGE plpgsql`. There is NO `IS NULL` arm — every document has a source_id (NOT NULL constraint since migration 049). Gate keys on the entity; deliberately ignores `documents.is_copyrighted`.
  - **Safe mode:** `UPDATE app_settings SET value='on' WHERE key='safe_mode'` serves only PD/owned; `'off'` restores unlicensed-but-shown content; `sources.visibility` is never written by the switch.
  - **Entity-consolidation rules (encoded in source_aliases):** re-upload venues → speaker (Good News Church / The Crossroads / Christ for the Nations → Derek Prince; Sandals Church → John Bevere); name variants → canonical (Derek Prince Ministries → Derek Prince; John Bevere TV / johnbeveretv / Drawing Near → John Bevere); co-authored Bevere + Renner → John Bevere; Ruth Prince is her OWN entity, NOT folded into Derek Prince.
  - **Ingest pipeline status (complete as of 2026-07-02, commit 9692f8b):** ALL ingest scripts now resolve `documents.source_id` at ingest time via the shared resolver (`scripts/source_resolver.py`): `ingest.py`, `ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_helloao.py`, `ingest_commentaries.py`. Resolution order: source_name alias → author alias → sentinel (fail-closed). Misses fall to the sentinel AND emit a grep-able `ALIAS_MISS` log line (standardized across the whole pipeline, including youtube's speaker lookup). `youtube_ingest.py` threads its gate-approved source_id into `ingest_file` via the `source_id_override` param instead of letting it re-resolve from headers. `ingest_magazine.py` resolves New Wine Magazine to hardcoded UUID `72b2f583-d7f9-4361-be1c-6d5aebe59fac` through the same resolver path. Column DEFAULT remains the safety net beneath the resolver.
  - **Open items:** single-y admin demotion (UID `1ea99425-08ec-40f2-9ed3-588b88122a82` → role `user`, pending verification nothing keys off it); `/pastors-notes/requests` CORS (`ALLOWED_ORIGINS` missing `https://rhemata.app` on Railway); backfill "The Kneeling Christian" → An Unknown Christian source. (`NEXT_PUBLIC_ADMIN_EMAIL` item CLOSED — zero references remain in frontend code.)
- Stage-2 ingest resolver (June 2026): `scripts/source_resolver.py` — shared source_id resolution and normalization used by `ingest.py` and `ingest_magazine.py`. Exports: `SENTINEL_SOURCE_ID`, `NEW_WINE_MAGAZINE_SOURCE_ID`, `normalize_alias_key(s)` (lowercase + strip + collapse whitespace — **MUST match migration 050 seed normalization exactly or aliases miss**), `resolve_source_id(db, source_name, author)` (returns `(source_id, norm_key, via)`; tries source_name alias → author alias → sentinel + `ALIAS_MISS` log), `print_resolution_table()`. Both ingest scripts gained `--dry-run-sources` flag (resolves + prints attribution table, writes nothing). Never fork `normalize_alias_key` — the single shared normalization is the contract.
- Corpus v2 admin UI (June 2026): AdminModal popup has 4 top-level tabs: Corpus, Feedback, Contributors, Notes Queue. Corpus has 3 sub-views: Documents (paginated list via `GET /admin/corpus/documents`, View Sheet + Remove AlertDialog backed by `DELETE /admin/document/{id}` → `removed_urls`), Sources (read-only license badge, visibility Switch, manage Sheet with CopyButton for source ID), Pipelines (stats pills + ingestion command reference with CopyButton per command). Governance and Pipelines are no longer top-level tabs. `GET /admin/stats` (service-key, bypasses RLS). `GET /admin/license-sources` uses bulk fetch + Python Counter. Realtime uses unique channel name per mount (`admin-realtime-${Date.now()}`) to prevent "cannot add postgres_changes after subscribe()" on re-open. New components: `frontend/components/ui/alert-dialog.tsx` (Radix UI AlertDialog primitive), `frontend/components/admin/CorpusDocumentsPanel.tsx`.
- Admin auth cutover (June 2026): `/admin/*`, `/feedback` read, and `/ingest` moved from the `ADMIN_EMAIL` email-equality guard onto the user_roles DB-role guard. `_RequireRole` and `get_user_role` promoted from `pastors_notes.py` into `auth.py` as the single implementation; `pastors_notes.py` now imports from `auth.py`. `require_admin_role = _RequireRole(["admin"])` and `require_contributor = _RequireRole(["contributor","admin"])` exported from `auth.py`. All 13 prior `require_admin` handlers swapped. Old `require_admin` function and `ADMIN_EMAIL` env var reference deleted from codebase. Multiple admins now possible — grant via `user_roles` row, no code change. Railway `ADMIN_EMAIL` env var is now dead and can be removed. Root cause: `ADMIN_EMAIL` was never set on Railway, so the old guard 403'd every `/admin/*` call since backend launch — invisible because all admin fetch `.catch()` blocks rendered empty/zero states rather than surfacing the 403.
- Admin fetch failures must surface, never silently render empty (June 2026 lesson): Frontend `.catch(() => setX([]))` / `.catch(() => {})` on admin data fetches hid a total backend 403 wall behind innocuous "No sources found" / zero-stat states for the entire backend lifetime. Admin fetches now set an `adminDataError` flag rendering a visible error banner in the Governance tab. **Rule: admin data fetches must surface errors — never silently substitute empty/zero.**
- Per-row N+1 queries time out on Railway (June 2026 lesson): One COUNT (or any per-row query) fired in a loop is manageable locally but blows Railway's request timeout in production. `GET /admin/license-sources` ran 43 sequential COUNT queries (100ms each ≈ 4.3s locally, worse on Railway) causing a timeout that the silent frontend catch masked as "No sources found." Fix: bulk-fetch all records, aggregate in Python. **If any admin/data endpoint is slow or flaky in production, check for an N+1 loop first.**
- Propositions layer (June 2026 — migration 051 SHIPPED):
  - **What it is:** `propositions` table stores atomic paraphrase-level decompositions of unlicensed document content, extracted by Groq Llama 3.3 70B (`llama-3.3-70b-versatile`) using the v3 "four-corners" prompt (in `scripts/propositions.py::EXTRACTION_PROMPT`). Safe, always-available representation of unlicensed material.
  - **Copyright posture CHANGED (June 2026):** Alex is holding copyrighted chunks in the DB (accepted risk for ≤20-person private beta). Propositions are a parallel layer — not a replacement for chunks, not a cold-storage rebuild. Chunks serve on top when display-safe; propositions are always retrievable.
  - **Serving rule (designed, NOT yet built in RPCs):** propositions ALWAYS retrievable regardless of license_status or visibility. Chunks served only when `license_status IN ('public_domain','owned','licensed')` OR (`visibility='shown'` AND `safe_mode='off'`). Hidden now means "propositions only, never chunks" rather than "fully excluded." Dedup/rerank needed at retrieval so shown-set sources don't double-weight (chunk + proposition).
  - **Ingest wiring (complete as of 2026-07-02):** `ingest.py` — proposition step runs after `insert_chunks`, before `tag_document`; dedicated psycopg2 connection opened/closed per document; non-fatal. `ingest_magazine.py` — same pattern; passes clean `body` (pre-chunk article text, not stitched chunks); uses the backend `embed_text` (`dimensions=1536` explicit). `ingest_lexicon.py`, `ingest_helloao.py` — same dedicated-connection pattern. `ingest_commentaries.py` — reuses its existing per-father connection, calls after the document+chunks commit. `youtube_ingest.py` — inherits via `ingest_file()` delegation (no direct call in that file, by design). All print/log `propositions: {result}`.
  - **`ingest.py` idempotency gap:** `ingest.py` is skip-on-hash — re-ingest skips entirely, so propositions only generate on first ingest of a new doc_id. Backfill of already-ingested docs requires a separate script.
  - **`store_propositions` is clear-then-write:** DELETE by document_id then insert — re-running on the same doc_id is always safe.
  - **Precept Austin decision (DECIDED 2026-07-02):** locked out of the propositions layer entirely — enforced structurally in `propositions.py` via `PRECEPT_AUSTIN_SOURCE_ID` (skip fires before any DB lookup, returns `"skipped_precept_austin"`). The excerpt-reuse option was investigated and DISPROVEN: `generate_excerpts.py`'s prompt requires preserving original sentences ("Never rewrite sentences... Preserve full length"), and sampled output confirmed near-verbatim reproduction — the excerpts are derivative reorderings, not paraphrases, and would mislabel unsafe text as the safe layer. Fresh Groq extraction was also declined. Under `safe_mode=ON`, Precept Austin (~1,700 docs) goes fully dark, by choice.
  - **Do NOT label paraphrase rewrites as "owned":** A rewrite of copyrighted source is a derivative, not owned content. Labeling it owned would serve it as safe verbatim and create a hole safe_mode can't close. The paraphrase layer (source stays truthfully unlicensed) is the correct home for rewrites.
  - **v3 "four-corners" prompt rules (in use, verbatim in EXTRACTION_PROMPT):** Use ONLY what's physically in the document; capture every scripture reference the source prints, invent none it doesn't; no 3+ consecutive source words (definitional sentences included); merge near-duplicates; no target count; ~80–150 words each; output JSON array only.
  - **Migration 051 gotcha — no semicolons in SQL comments:** Migration failed silently ~3 times because a comment line contained a semicolon, which the multi-statement runner (both Supabase SQL editor and naive `text.split(";")`) treated as a statement terminator. The resulting syntax error mid-batch rolled back the whole transaction, while an earlier verification in the same uncommitted editor session appeared to show the table present. **Rule: never put a semicolon inside a `--` SQL comment in a migration file. Verify migrations via `SELECT to_regclass('public.<table>')` on a FRESH connection, not the same editor session.**
  - **Validated end-to-end (June 2026):** Flora "How To Overcome" (stored:12) and "Christ's Eternal Lordship" (stored:15) — all rows have non-null embedding + fts; four-corners quality held on both documents.
  - **Remaining:** backfill extraction over the already-ingested corpus that predates the wiring (excluding Precept Austin, which the gate now blocks structurally); build serving-rule into retrieval RPCs (proposition RPC or extend match_chunks) with dedup. (Ingest-path fan-out is DONE as of 2026-07-02 — all scripts wired.)
- Stage 5 Queue Orchestration (June 2026): `ingest_queue.xlsx` (gitignored) extended with two control tabs — Queue and HowToRun — alongside per-teacher source detail tabs. Workflow: paste URLs into Queue tab → run triage → review source tabs → run ingest.
  - **Queue tab columns:** `url | source_name | review | filter | limit | status` (cols 1–6). `QUEUE_COL = {name: i+1 for i, name in enumerate(QUEUE_COLS)}`.
  - **Filter tokens (col 4):** `min5` → skip clips ≤5min (`--min-duration 300`); `whitelist` → title-match mode, Groq classification skipped, pre-classified `sermon=TRUE`. Comma-separate for combos (e.g. `whitelist,min5`). Unrecognized tokens warn explicitly.
  - **limit column (col 5):** integer cap applied via `--playlist-items 1:{limit}` to yt-dlp at enumeration time — NOT a Python break after the fact. Critical for large channels (e.g. `@sermonindex/videos`); prevents subprocess timeout. `enumerate_channel()` timeout bumped 120s → 300s. Non-integer values warn: "Did you put a filter token in the limit column by mistake?"
  - **Whitelist mode:** `source_name` blank is valid (intentional for multi-speaker channels). Tab label derived from URL handle: `@sermonindex/videos` → `sermonindex` → `.capitalize()` → `Sermonindex`. Whitelist file resolved as `scripts/whitelist_{slug}.txt`. `source_name` guard is conditional: skip only when `not source_name AND not whitelist_mode`.
  - **De-dup:** `all_urls_in_sheet(ws)` built once per channel expansion; only new URLs appended. Re-runs with larger limit are purely additive. To re-enumerate a channel row: reset its `status` to blank first.
  - **`run_queue_triage.py`:** `--only LABEL` processes only the Queue row matching tab_label (case-insensitive). Fault-tolerant: bad rows marked `error: {msg}`, run continues.
  - **`run_queue_ingest.py`:** walks all source tabs (skips Queue + HowToRun); `--sheet NAME` for single-tab mode. Prints grand total table: TAB | DONE | FAILED | NEEDS_SOURCE | ERROR.
  - **`discover_sermonindex_playlists.py`:** discovery-only (prints only, zero writes). Known issues: fetches only first page of playlists (~40 entries); multi-name false positive (playlist title containing both speaker names matches whichever whitelist entry appears first). Fix needed before trusting output fully.
  - **`whitelist_sermonindex.txt`:** 17 entries covering 13 speakers. Period variants for A.W. Tozer (3) and T. Austin-Sparks (3). Stored in `scripts/`, NOT `sources/` (`sources/` is gitignored).
  - **New sources added (June 2026):** Gabriel Heights, Philip Anthony Mitchell, Leonard Ravenhill, David Wilkerson, SermonIndex channel (whitelist mode, 13 speakers). All registered `unlicensed/hidden`. Jesus Image: actively blocks scraping — dropped. Smith Wigglesworth and Frank Bartleman better sourced as TEXT (little/no audio at SermonIndex). Visibility rule: new unlicensed sources always REGISTER as `hidden`; flipping to `shown` is never an IP clearance — it requires an explicit beta-scope decision recorded in this decision log (see "Tier-1 beta visibility decision," 2026-07-09, below).
  - **SermonIndex public-domain claim:** SermonIndex states it is "committed to the public domain where applicable." This is a credible intent signal but NOT a clean legal grant — SermonIndex doesn't own underlying copyrights for third-party preachers, and "where applicable" is load-bearing. All SermonIndex content stays `unlicensed/hidden` until IP attorney review. Do NOT upgrade to `public_domain` without legal confirmation.
  - **`ingest_file(skip_dedup=True)`:** Stage 3 ingest passes `True` to bypass the dedup guard (sheet `status` column is the authoritative dedup guard). No migration created (053 proposed and immediately deleted). Chunk inserts must NOT include `page_number` or `source_hash` — neither column has ever existed in the live schema (the guard's 2026-07-03 rebuild replaced a broken `chunks.source_hash` lookup with a `documents.url`/`source_name`/`file_path`-keyed check — see `shared_ingest.py`).
- CLF Church / Alex Whitley alias gap closed (migration 058, 2026-07-03): live `source_aliases` had no row for `'clf church'` (source_name-key) or `'alex whitley'` (author-key), despite the migration-050 note above implying `clf-church` was seeded — it wasn't; confirmed by live query. Migration 058 adds both, pointing at the existing CLF Church source (`29bfe81f-a150-4e43-baac-042e366fb4b3`, `owned/shown`). Verified live: both resolve correctly; Rhemata's `rhemata` alias and its 3 position papers were untouched. Demo-ingested "Stuck in the Wilderness" (an Alex Whitley sermon, previously unlabeled in `sources/documents/`) — resolves via the new `alex whitley` author-key to CLF Church, not the sentinel. **Known residual gap:** live `source_aliases` still runs well ahead of this file's older counts (67 sources / 91 aliases / 64 entities live vs. 43/54/39 documented elsewhere in this file) — migration 058 closed one specific instance, not a full reconciliation. Other confirmed gaps: Jack Deere (8 existing docs) and Michael Brown (2 existing docs) have zero aliases — re-ingesting their content today would sentinel.
- `ingest.py` dedup guard rebuilt (2026-07-03): the prior guard queried `chunks.source_hash` — a column that has never existed in the live schema — so any standalone `ingest.py` folder run crashed with `UndefinedColumn` on the first non-skipped file (invisible until now because the YouTube pipeline always passes `skip_dedup=True`). Replaced with a key-based check, now living in `shared_ingest.already_ingested()`: `documents.url` + `documents.source_name` exact match (NULL-safe) when a URL is known, else a filename-suffix match against `documents.file_path` (robust to relative-vs-absolute paths and which subfolder a file currently sits in). No new column, no backfill. Verified live against real duplicates, including the filename-fallback path.
- Shared ingest chokepoint — script 1 of 5 (2026-07-03): `scripts/shared_ingest.py` is a new shared writer (`ingest_document()`) owning the resolve → insert → chunk → embed → propositions flow previously duplicated across `ingest.py`, `ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_commentaries.py`. Hooks exist for the load-bearing differences those scripts will need when converted: attribution (`source_id` override or `resolve_from`), reuse-by-identity (`find_existing_fn`/`on_existing`: skip/reuse/delete_and_reingest — unused by ingest.py today), chunking (`chunk_fn`, defaults to the shared token chunker — lexicon will need its own one-entry-one-chunk override), insert mechanics (`insert_mode`; only `rest_per_chunk` is implemented, `psycopg2_batch` deliberately deferred rather than guessed at speculatively), and propositions connection reuse (`propositions_conn`, for commentaries' pattern). `ingest.py` is converted; the other four are not — convert one at a time in separate sessions, not big-bang, per the migration-path analysis behind this decision. Side effect: fixed a latent bug where `ingest.py`'s old local `embed_text()` omitted `dimensions=1536` (relied on the OpenAI model's current implicit default) — the shared writer imports `embed_text`/`embed_batch` from `backend/app/services/embeddings.py` instead, which sets `dimensions=1536` explicitly. Verified live: a real document round-tripped through the full resolve→insert→chunk→embed→propositions flow, embedding confirmed at exactly 1536 dims in Postgres; test artifacts deleted after.
- **Tier-1 beta visibility decision (Alex, recorded 2026-07-09):** 25 unlicensed sources are deliberately set `visibility='shown'` for the Tier-1 private beta (≤20 users) — an accepted-risk beta-scope call under the risk-tier model (PLAN.md Decision 5), NOT an IP-review clearance. Flips cluster on 2026-06-23 (14 sources) and 2026-06-26 (11 sources) per `sources.updated_at` (best-available dates — `updated_at` is row-level, not a visibility-flip timestamp). Canonical list is the live DB, not this file: `SELECT name FROM sources WHERE license_status='unlicensed' AND visibility='shown'` — any static list here would silently rot. At the Tier-1→Tier-2 jump (beta >20 or open signup, Decision 5's trip line), every one of these goes back through the pre-public-tier gate (PLAN.md #32–37) before serving publicly. Going-forward rule: new unlicensed sources still register `hidden` by default; `shown` requires an explicit beta-scope decision recorded here.

---

## Harness / Agentic-Loop — Gate Design Principles

Durable architecture the supervised agentic-loop harness (`executor`/`planner-reviewer`
subagents; `.claude/hooks/guard_pretooluse.py` PreToolUse; `.claude/hooks/deterministic_gate.py`
SubagentStop) is built toward. These are the stated design constitution, not a claim that
every line of current code already conforms — where it doesn't yet, that's noted inline
rather than glossed over.

1. **Mismatch-only rule.** The stop-gate blocks ONLY when the agent's claimed work and the
   recorded tool-calls disagree — never on the presence of a write alone. A recorded write
   with a matching honest report must pass.
2. **Prose is the subject, never the signal.** The agent's self-report is the thing being
   audited; the gate must never trust its self-declared work-type or scan it for
   write-flavored words to make its decision. The record-primary migration gets finished;
   the prose fallback is retired, not left as a permanent bridge.
   **Current conformance (interim, not final):** the garble fix shipped in `5b43332`
   (`deterministic_gate.py`'s `check_recorded_writes()`) is an INTERIM conformer to this
   principle, not a finished one — it still reads and trusts the executor's self-declared
   `WORK_TYPE` marker to decide whether a recorded write is acceptable, which this principle
   forbids. This was a deliberate, pragmatic move to stop the garble loop (see PLAN.md #5.5)
   and it holds — but it is a bridge, not the finished state. Full conformance lands when
   the record-only migration (#5.5's remaining open exit condition) completes and the prose
   fallback is retired. Do not describe the garble fix as "done" or "final" anywhere — it is
   fixed for its original failure mode, not yet fully conformant with this principle.
3. **Agent identity is first-class.** Every recorded action and every gate decision carries
   "whose action was this" as a required field, not an enrichment. The stop-gate evaluates
   only the finishing agent's own records, never the whole session's.
4. **The machinery is invisible to itself.** The harness's own bookkeeping (any report-save,
   log-write, etc.) happens off the monitored path, so the enforcement layer can never
   observe — and never trip on — its own writes.
5. **Fallible, not adversarial.** Subagents are treated as prone to honest error and drift,
   not deceit. Broad detection catches mistakes; hard denial (not detection) makes the few
   genuinely irreversible operations impossible. The harness is not to be grown toward
   defeating a deliberate adversary.

### Standing decisions (harness scope)

- **Subagent scope: `executor`/`planner-reviewer` are SCRIPT-ONLY for now** (Alex,
  2026-07-12) — no MCP or external-tool access granted to either subagent type. Every task
  on the current roadmap is expressible as a script; building write-detection for tool
  access nobody has granted yet is speculative scope. **Revisit trigger:** reopen this
  decision only when a queued task genuinely cannot be expressed as a script — not
  preemptively.
- **Report-to-disk feature: DROPPED, not deferred** (Alex, 2026-07-12) — the mandatory
  backstop-save build (a prior session's uncommitted changes to `executor.md`/
  `planner-reviewer.md`) is discarded. A prior diagnostic confirmed nothing in the codebase
  reads the saved report, and the mechanical write-state record (Approach B) already
  survives report-garbling untouched, making the backstop redundant. This removes the
  report-save/read-only write-collision bug by deleting its cause, not by fixing it. If a
  genuine readable-report need arises later, principle 4 above ("the machinery is invisible
  to itself") is the blueprint for rebuilding it off the monitored path — not a reason to
  resurrect this specific implementation.

---

## Environment Variables (in backend/app/.env)
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY` — Claude Sonnet 4.5 for answer generation
- `COHERE_API_KEY` — Cohere rerank-v3.5 for retrieval reranking
- `GEMINI_API_KEY` — Gemini 2.5 Flash for magazine extraction (read at `scripts/extract_magazine.py:86`). Note: `GOOGLE_API_KEY` is dead — its only consumer was the removed Jewish Perspective feature; nothing reads it anymore.
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_DB_URL` — direct PostgreSQL connection for psycopg2 (bypasses PostgREST timeouts)
- `SUPABASE_JWT_JWKS_URL`
- `INCLUDE_COPYRIGHTED` — `true`/`false` (default `true` in chat.py, `false` in search.py)
- `ALLOWED_ORIGINS`

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/extract_magazine.py` | 3-pass Gemini/Groq extraction pipeline (Vision → Segmentation → QA) |
| `scripts/ingest_magazine.py` | Ingest approved .md articles from sources/magazine/03_approved/ into Supabase |
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal). `ingest_file(skip_dedup=False)` — pass `True` to bypass the dedup guard (Stage 3 uses this). Metadata detection + Bible-ref extraction stay here; resolve/insert/chunk/embed/propositions are delegated to `shared_ingest.ingest_document()` (2026-07-03 conversion, script 1 of 5). |
| `scripts/shared_ingest.py` | Shared document-writer chokepoint. `ingest_document()`: dedup (`documents.url`+`source_name` exact match, or filename-suffix match against `documents.file_path` when no URL — no `source_hash` column, never has existed) -> resolve attribution (`source_id` override or `resolve_from=(source_name, author)`) -> insert document row -> chunk (`chunk_fn`, default the shared token chunker) -> embed + insert chunks (`insert_mode="rest_per_chunk"` implemented; `"psycopg2_batch"` deferred, not yet needed) -> propositions (`propositions_conn` to reuse caller's connection, else opens/closes its own). Also exposes `find_existing_fn`/`on_existing` (skip/reuse/delete_and_reingest) for the reuse patterns `ingest_preceptaustin.py`/`ingest_lexicon.py`/`ingest_commentaries.py` will need when converted. Imports `embed_text`/`embed_batch` from `backend/app/services/embeddings.py` (fixes a latent bug: `ingest.py`'s old local `embed_text()` omitted `dimensions=1536`). |
| `scripts/youtube_triage.py` | Stage 2 YouTube pipeline: channel enumeration + Groq title classification (sermon/worship/promo/other). Exports `process_sheet()` callable used by run_queue_triage.py. `--sheet NAME` still works direct. `--add URL`, `--limit N`, `--retry-unknown`, `--dry-run`. |
| `scripts/youtube_ingest.py` | Stage 3 YouTube pipeline: captions-first/Whisper fallback + Groq clean + `ingest_file(skip_dedup=True)`. Exports `ingest_sheet()` callable used by run_queue_ingest.py. `--sheet NAME` still works direct. `--limit N`, `--dry-run`. `done_prior` rows excluded. Checks `removed_urls` blocklist before each ingest call (non-fatal skip on hit). |
| `scripts/run_queue_triage.py` | Stage 5 Run 1: Queue-driven triage orchestrator. Reads Queue tab in ingest_queue.xlsx; for each pending row calls `process_sheet()` on the named source tab. `--only LABEL` (case-insensitive tab match), `--time-limit MINUTES` (stops between sources after elapsed time), `--dry-run`. Fault-tolerant: bad rows marked `error: {msg}`. |
| `scripts/run_queue_ingest.py` | Stage 5 Run 2: Queue-driven ingest orchestrator. Walks all source tabs (skips Queue + HowToRun), calls `ingest_sheet()` per tab. `--sheet NAME` for single-tab mode, `--time-limit MINUTES` (stops between tabs after elapsed time), `--dry-run`. Grand total table: TAB \| DONE \| FAILED \| NEEDS_SOURCE \| ERROR. |
| `scripts/discover_sermonindex_playlists.py` | Discovery-only: enumerate SermonIndex `/playlists` tab via yt-dlp, match against `whitelist_sermonindex.txt`, print match table. Prints only — no workbook writes, no Queue rows, no triage, no ingest. Known issues: first page only (~40 playlists); multi-name false positive on playlist titles containing multiple speaker names. |
| `scripts/source_resolver.py` | Shared source_id resolution + alias normalization. Imported by `ingest.py` and `ingest_magazine.py`. Exports `resolve_source_id()`, `normalize_alias_key()`, `SENTINEL_SOURCE_ID`, `NEW_WINE_MAGAZINE_SOURCE_ID`, `print_resolution_table()` |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run) |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |
| `scripts/generate_excerpts.py` | Batch-generate word study articles from Precept Austin chunks via Anthropic Claude |
| `scripts/whisper_transcribe.py` | Whisper medium transcription + Groq cleaning (batch or single-URL) |
| `scripts/youtube_pipeline.sh` | Full YouTube pipeline: scrape → clean → whisper → ingest |
| `scripts/retag_sermons.py` | Retag sermon_transcript docs via Claude Haiku against new taxonomy |
| `scripts/ingest_commentaries.py` | Ingest HistoricalChristianFaith commentaries from SQLite DB |
| `scripts/scrape_individual_videos.py` | ORPHANED LEGACY (2026-06-27) — individual_videos.xlsx retired; its 21 videos consolidated into ingest_queue.xlsx; utility functions inlined into youtube_ingest.py. Do not run. Do not delete. |
| `scripts/scrape_channel_titles.py` | Dump all video titles from YouTube channels to CSV |
| `scripts/propositions.py` | Shared proposition extraction + storage module. `extract_propositions(text)` — Groq Llama 3.3 70B, v3 "four-corners" prompt, strips ```json fences, returns `[]` + logs `PROPOSITION_EXTRACT_FAIL` on any error (never raises). `store_propositions(conn, document_id, propositions, embed_fn)` — DELETE by document_id then embed + INSERT each via injected `embed_fn`; commits. `process_document(conn, doc_id, source_id, text, embed_fn)` — entry point for ingest scripts; gate: extracts for licensed/unlicensed only (skips public_domain + owned), Precept Austin locked out by name; returns `"skipped_licensed"` / `"skipped_precept_austin"` / `"no_propositions"` / `"stored:{n}"` / `"error"`; rolls back + returns `"error"` on any exception. Groq client lazy-init. |
| `scripts/taxonomy.py` | Single source of truth for the 258-tag `VALID_TAGS` set — all tagging scripts import from here; `taxonomy.md` is generated from it for human reference |
| `scripts/bible_refs.py` | Shared Bible reference extractor (Groq) — used by ingest.py and ingest_magazine.py |
| `scripts/backfill_phrase_refs.py` | Backfill bible_references via phrase matching (no LLM). Flags: `--source-kind`, `--author`, `--limit`, `--dry-run`, `--force`, `--chunks` |
| `scripts/fix_article_json.py` | One-off migration: fixed 30 chunks with raw JSON content (run 2026-04-17) |
| `scripts/extract_book_quotes.py` | Extract quotable passages from Murray books via Claude Haiku 4.5. Flags: `--dry-run`, `--limit`, `--title` |
| `scripts/setup_document_images.py` | One-off: creates `document-images` Storage bucket, downloads Unsplash image, uploads, assigns `image_url` to Mumford doc. Run after migration 042. |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

### Additional Pipeline Scripts (in scripts/)

| Script | Purpose |
|---|---|
| `scripts/scrape_preceptaustin.py` | Scrape Precept Austin Greek/Hebrew word studies |
| `scripts/ingest_preceptaustin.py` | Ingest Precept Austin word studies into Supabase |
| `scripts/ingest_lexicon.py` | Ingest STEPBible lexicon files (TBESG, TBESH, TFLSJ) |
| `scripts/ingest_bible.py` | Ingest WEB Bible into verses table |
| `scripts/ingest_interlinear.py` | Ingest STEPBible interlinear NT into verses table |
| `scripts/ingest_tahot.py` | Ingest TAHOT Hebrew OT alignment data |
| `scripts/extract_bible_refs.py` | Backfill bible_references on all documents |
| `scripts/download_book_covers.py` | Download book cover images to frontend/public/images/books/ |
| `scripts/test_metering.py` | End-to-end metering test suite (increment, rollover, hard stop) |
| `scripts/ingest_helloao.py` | Ingest Matthew Henry / Adam Clarke / JFB commentaries from the HelloAO Bible API — one document per book per commentary, REST-based, resolves source_id + wired to propositions. Flags: `--test`, `--book`, `--time-limit` |
| `scripts/diagnose_retrieval.py` | Retrieval pipeline diagnostic for chat — exercises real production code paths, no reimplementation |
| `scripts/rewrite_sermons.py` | Batch rewrite sermon transcripts into structured notes via Claude Haiku. Flags: `--limit`, `--dry-run` |
| `scripts/scrape_ccel.py` | Download public-domain PDFs from CCEL — reads URLs from `scripts/ccel_urls.txt`, saves to `sources/documents/`, skips existing |
| `scripts/scrape_derek_prince.py` | Derek Prince sermon transcript scraper — fetches listing page, extracts transcript + metadata per sermon |
| `scripts/register_youtube_source.py` | Register new YouTube teachers in sources + source_aliases (fetches real channel name via yt-dlp; unlicensed/hidden). Reusable registration tool |
| `scripts/register_sermonindex_speakers.py` | ONE-OFF (run): registered the 13 SermonIndex archive preachers as unlicensed/hidden sources + aliases. Idempotent |
| `scripts/register_bill_johnson_gabriel_heights.py` | ONE-OFF (run): registered Bill Johnson + Gabriel Heights as unlicensed/hidden. Idempotent |
| `scripts/register_jesus_image.py` | ONE-OFF (run): registered Jesus Image (ministry, multi-voice) + aliases. Idempotent. Note: Jesus Image scraping was later dropped (blocks scraping) |
| `scripts/demo_ravenhill_ingest.py` | ONE-OFF demo: Stage 3 ingest for Leonard Ravenhill rows in the Sermonindex tab (title-filtered wrapper around ingest_video) |
| `scripts/backfill_era.py` | ONE-OFF backfill: era column on documents and books tables |
| `scripts/seed_books.py` | ONE-OFF seed: books table with curated book data |
| `scripts/download_ccel.py` | ONE-OFF download: hardcoded CCEL PDF list into `pdf/open/` (superseded by scrape_ccel.py's URL-file approach) |
| `scripts/download_corpus_batch3.py` | ONE-OFF download: hardcoded public-domain PDF batches 1–3 into `sources/documents/` |
| `scripts/test_excerpt_generation.py` | Test harness: single Precept Austin word study through the excerpt-editing prompt, prints + saves result |
| `scripts/test_pastors_rls.py` | Test suite: verifies RLS policies on the three Pastors' Notes tables (run after migration 038) |

---

## Ingest scripts: propositions are per-script, not enforced

Every ingest script must generate propositions for gated content. This is
NOT enforced anywhere — no central chokepoint, no DB backstop. It lives in
each script's discipline. Forget it, and content ingests with zero
paraphrase layer and NO error. Silent gap.

**Rule for any new or modified ingest script:**
1. Call `process_document(...)` after chunk insert (or route through
   `ingest_file()`, which calls it internally).
2. Confirm the full pre-chunk document text is still in scope at that point.
3. Verify it actually fires — don't trust comments or docstrings:
   `grep -n "process_document\|propositions\." scripts/<name>.py`

**What the gate does (propositions.py, final rule 2026-07-02):** extracts
for licensed + unlicensed sources only; skips public_domain + owned (already
safely servable as verbatim chunks). Fails closed on a missing source. One
named exception enforced inside the gate itself: Precept Austin never gets
propositions (`PRECEPT_AUSTIN_SOURCE_ID` constant — its excerpts are
near-verbatim reorderings, not paraphrases; decided 2026-07-02). A script
whose sources are all public_domain will correctly produce zero
propositions — that's expected, not a bug.

**Gotchas, both hit in practice:**
- Comments/docstrings lie. `youtube_ingest.py` line 15 claimed propositions
  "auto-fire" — the actual call lived one level down in `ingest_file()`.
  Only a grep of the real call site proves coverage.
- This is per-script. Unlike the source_id gate (enforced at DB level via
  NOT NULL + sentinel default), nothing stops a new script from skipping
  propositions entirely.

**In progress (2026-07-03):** `scripts/shared_ingest.py` now provides exactly
this shared function (`ingest_document()`), converted from a prior
diagnose-first design session. `ingest.py` is routed through it — propositions
can no longer be skipped by omission for that script specifically. The other
four scripts (`ingest_magazine.py`, `ingest_preceptaustin.py`,
`ingest_lexicon.py`, `ingest_commentaries.py`) are NOT yet converted; the
per-script-discipline gap described above still fully applies to them.
Convert one at a time, not big-bang — each has its own load-bearing
divergence the shared writer's hooks need to accommodate (magazine's
chunk-content header baking, lexicon's one-entry-one-chunk chunking and
batched/paced inserts, commentaries' connection-reuse and once-per-run
resolve, precept_austin's cross-pipeline reuse-by-title). See
`shared_ingest.py`'s module docstring for the hook list.

---

## How to Work on This Project
- Alex works fast — short messages, direct feedback
- Surface risks before building, not after
- All code changes stay in Claude Code — don't suggest manual edits unless trivial (1-2 lines)
- Read output directly — never ask Alex to copy-paste terminal output
- Check actual files before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`

# Rhemata — Project Knowledge Read Contract

Chat reads project state directly from five repo files. No Notion
mirroring, no sync step, no drift-check for this project — there is
exactly one copy of each, so there's nothing to drift from. (Notion sync
retired 2026-07-09; this repo-local change does not touch the shared
"Client Projects" Notion database, the Rhemata Notion page, any other
row in it, or the global Notion Project Tracker contract.)

- **CLAUDE.md** — durable architecture, decisions log, conventions.
  "How the system works."
- **POSITIONING.md** — messaging/positioning source of truth.
- **DESIGN.md** — styling-token authority.
- **PLAN.md** — the roadmap: numbered session list, standing session
  rules, open-decisions table, ground-truth findings log.
- **rhemata-status.md** — live session state only ("what's next,"
  "what's blocked," current counts). Overwritten each session. Never
  durable truth.

**Writer rules differ by file:**
- `CLAUDE.md`, `SKILL.md`, `DESIGN.md` — terminal both authors and
  writes these, from confirmed-working builds only.
- `rhemata-status.md` — terminal both authors and writes this, directly
  from live repo/DB state, overwritten each session.
- `PLAN.md` — terminal is the sole writer and committer, same as every
  other repo file; chat never physically edits it. But PLAN.md's
  CONTENT is chat-originated: roadmap revisions, session sequencing,
  standing-rule changes, and open-decision entries are decided in the
  planning/chat lane, handed to terminal as a prompt, and terminal
  writes and commits them verbatim. Terminal does NOT originate
  roadmap decisions on its own — it is the pen, not the author. This
  keeps the judgment lane (what to build next) separate from the
  execution lane (building it), which is the core discipline the
  whole workflow depends on.

Chat never edits any of the five files directly. If chat proposes a
change to a terminal-authored file, terminal makes it in the repo, then
commits.

Never log planned work as done. Never claim build state you can't see.