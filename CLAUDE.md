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
│   ├── scrape_youtube.py      # YouTube transcript scraper (yt-dlp + Supabase dedupe)
│   ├── clean_transcripts.py   # Clean raw transcripts via Groq Llama 3.3 70B
│   ├── extract_magazine.py    # 3-pass Gemini/Groq extraction pipeline
│   ├── ingest_magazine.py     # Supabase ingestion from .md files with frontmatter
│   ├── ingest.py              # Standalone PDF/docx/txt ingestion with auto-tagging
│   ├── tag_existing_articles.py   # Backfill topic_tags on existing articles via Groq
│   └── tag_sermons_transcripts.py # Backfill topic_tags on sermons/transcripts/papers via Groq
├── taxonomy.md                # 257-tag topic taxonomy (15 categories)
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
│   └── 050_source_aliases.sql            # source_aliases table + 54 normalized alias seeds; adds CLF Church + An Unknown Christian sources
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
│   │   │   ├── library.py     # /library/books + /library/book/{id} + /library/doc-meta + /library/recent + /library/counts
│   │   │   ├── study.py       # /study/verse + /study/corpus + /study/lexicon + /study/excerpt + /study/interlinear + /study/commentary + /study/wordsearch + /study/wordstudy
│   │   │   ├── pastors_notes.py  # /pastors-notes/* — cards (pending/approve/reject), requests, role management; /pastors-notes/pending + /recent
│   │   │   ├── usage.py       # GET /usage — weekly query count for authenticated users
│   │   │   └── ingest.py      # /ingest endpoint (admin-only as of 2026-06-10)
│   │   ├── services/
│   │   │   ├── embeddings.py
│   │   │   ├── chunker.py
│   │   │   ├── metadata.py
│   │   │   └── extractor.py
│   │   ├── db/
│   │   │   └── supabase.py
│   │   ├── system_prompt.txt
│   │   └── theological_guardrails.txt
│   ├── requirements.txt       # Pinned via pip freeze
│   ├── railway.toml
│   └── nixpacks.toml          # Locks Python 3.9
└── frontend/                  # Next.js 16 frontend (Vercel)
    ├── app/
    │   └── home/              # Public marketing landing page (no auth required)
    │       └── page.tsx       # Animated mockups, marquee, Why It Matters, CTA — BetaGate + LoginModal wired
    ├── hooks/
    │   ├── useUserRole.ts     # Role + displayName hook; module-level cache keyed by access token; 5-minute TTL
    │   └── useChat.ts         # weeklyUsage state; seeds from GET /usage on mount, updates from SSE meta
    ├── components/
    │   ├── auth/
    │   │   └── BetaGate.tsx   # Beta password gate modal — prompts for "rhema", stores beta_access in sessionStorage
    │   └── rhemata/
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
- Tables: `documents`, `chunks`, `verses`, `saved_words`, `excerpts`, `guest_sessions`, `conversations`, `messages`, `interlinear_words`, `book_quotes`, `user_usage`, `sources`, `source_aliases`, `source_license_audit`, `app_settings`
- `documents.source_type` — `'sermon'` | `'background'` | `'magazine_article'` | `'commentary'` | `'book'` | `'paper'` | `'other'`
- `documents.source_kind` — taxonomy field (e.g. `'magazine_article'`)
- `documents.citation_mode` — `'citable'` | `'silent_context'`
- `documents.is_copyrighted` — boolean, derived from folder path during ingest
- `documents.topic_tags` — text[] assigned from taxonomy (can be `null`, not just empty array — confirmed from live API)
- `documents.bible_references` — text[], canonical refs like `"Romans 8:28"`, GIN indexed
- `documents.fts_weighted` — tsvector on title, author, source_name, topic_tags
- `documents.image_url` — text, nullable; Supabase Storage public URL for featured hero card image (migration 042)
- `documents.source_id` — uuid NOT NULL FK → `sources` (ON DELETE SET DEFAULT, default = sentinel `267a09ac-76f3-43fb-901f-3015aef88e22`); new inserts that omit source_id land on the sentinel (hidden, not served); no NULLs exist post-migration-049; the SQL-layer license gate reads this column
- `sources` — one row per rights-holder entity (43 rows, including sentinel). `license_status` text ('public_domain'|'owned'|'licensed'|'unlicensed') = truth about rights; `visibility` text ('shown'|'hidden', DEFAULT 'hidden' = fail-closed) = what the gate obeys; `retrievable` generated boolean (informational only, NOT read by the gate). RLS: service-role only.
- `source_aliases` — normalized alias_key (text UNIQUE; lowercase + trim + collapsed whitespace) → source_id FK ON DELETE CASCADE. 54 alias rows across 39 entities. Lookup: `SELECT source_id FROM source_aliases WHERE alias_key = lower(trim(regexp_replace(input, '\s+', ' ', 'g')))`. RLS: service-role only.
- `source_license_audit` — immutable log of `license_status` changes. Created, not yet written by any UI.
- `app_settings` — global key/value table. One row: `key='safe_mode', value='off'`. RLS: service-role only.
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
- Topic tagging: 257-tag taxonomy (15 categories), validated against VALID_TAGS set in scripts/taxonomy.py, retry if < 3 valid
- is_copyrighted derived from folder path: `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false. **This flag is unreliable** (e.g. Derek Prince docs are `false` despite being copyrighted works). The license gate deliberately ignores it — do not "fix" the gate to read `is_copyrighted`.
- Design system: `DESIGN.md` in project root is the styling authority. Lumen system (shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme locked via `forcedTheme`). No hardcoded hex.
- Brand reset complete (June 2026): Lora/Inter/gold hex removed. Geist Sans, shadcn primitives, CSS variable tokens throughout. `DESIGN.md` is source of truth.
- Study Mode restructured (June 2026): single-column layout, interlinear always visible attached to verse, inline word expansion, commentary visible without tab click, Pastors' Notes stub in place, Jewish Perspective collapsed by default. Tabs removed.
- Guest session migration complete (June 2026): `guest_sessions` table and `increment_guest_query` RPC created in Supabase. Frontend and backend were already wired.
- Pastors' Notes complete (June 2026): three-tier role system (user/contributor/admin), verse-anchored cards, contributor request flow, 50–2000 char limit, soft delete only, auto-tagging via Groq with 5s timeout fallback. Tables: `user_roles`, `contributor_requests`, `pastors_cards` (migrations 038, 041).
- Pastors' Notes approval gate (June 2026): contributor notes save as `'pending'`, require admin approval before publishing; admins post directly as `'published'`. `pastors_cards.status`: `'pending'` | `'published'` | `'removed'`. New endpoints: `GET /pastors-notes/pending` (admin queue with email + display_name), `POST /cards/{id}/approve`, `POST /cards/{id}/reject`. `get_user_emails` RPC in migration 041. `useUserRole` cache TTL 5 min (was indefinite). `GET /cards` optionally authenticated — returns own pending cards to contributor, all pending to admin.
- Admin consolidation (June 2026): all admin surfaces merged into single `/admin` page with sticky anchor-nav (Overview · Contributors · Corpus). Role-based auth via `GET /pastors-notes/me` (no more hardcoded ADMIN_USER_ID). `/admin/contributors` and `/rhemata-corpus-admin` redirect to `/admin`. `app/rhemata-corpus-admin/` deleted. Corpus components in `frontend/components/admin/`. `components/ui/switch.tsx` added (shadcn Switch using radix-ui). Precept Austin Greek card has `notFilter` to exclude Hebrew docs. HistoricalChristianFaith card description corrected.
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
- Hero card image slot (June 2026, revised): Featured hero uses `grid-cols-[3fr_2fr] gap-6` (60/40), grid stretch (no `items-start`), `text-xl` title, tightened margins. Right panel: `<Image fill object-cover>` when `image_url` present, sparkle `✦` placeholder otherwise. `image_url text` column via migration 042 (pending). `document-images` Supabase Storage bucket (public); first image: `mumford-life-of-worship.jpg`. `frontend/next.config.ts` adds Supabase hostname to `images.remotePatterns`. Setup: run migration 042, then `python3 scripts/setup_document_images.py`.
- FastAPI `Query` import bug (June 2026): Any `Query(...)`, `Path(...)`, etc. used as route default parameters are evaluated at module import time — missing import causes `NameError` → uvicorn never binds → all routes in the file are absent (not a 500; they 404). Always include fastapi symbols in the import line if used as defaults.
- `/home` landing page (June 2026): New public route `app/home/page.tsx` — no auth required. Animated Chat/Study/Discover mockups (IntersectionObserver, once at 30% viewport), marquee with `@keyframes marquee-left/right` in `globals.css`, Why It Matters two-column contrast, Final CTA. New CSS token: `--gold-light: 44 60% 62%` added to `:root` and `@theme inline` in `globals.css`. `/` route untouched.
- Beta password gate (June 2026): `components/auth/BetaGate.tsx` — client-side modal, required code "rhema", stores `beta_access=1` in `sessionStorage` on success. Wired in all three app pages and `/home`. "Try it free — no account needed" and direct `/` are ungated. `LoginModal` gained `initialMode?: "signin" | "signup"` prop; sidebar guest footer changed from "Sign in" to "Become a test user" primary Button.
- License Control System (June 2026, migrations 043–050): SQL-layer fail-closed gate preventing unlicensed content from reaching retrieval. Does NOT touch `INCLUDE_COPYRIGHTED` env flag or Python `citation_mode` filtering — both still operate as before.
  - **Migrations 043–048** established the `sources` table, `documents.source_id` FK, two-column model (`license_status`/`visibility`), SQL-layer gate in both RPCs, and `app_settings`/`safe_mode`.
  - **Migration 049 (2026-06-24) — NULL hole sealed:** The prior gate had a `d.source_id IS NULL OR ...` arm that passed documents with no source unconditionally — fail-OPEN. Fix: (a) Created PROTECTED SENTINEL source (fixed UUID `267a09ac-76f3-43fb-901f-3015aef88e22`, "Unassigned — needs source", `unlicensed/hidden`). (b) Backfilled the 18 then-orphaned docs onto the sentinel. (c) `documents.source_id` is now NOT NULL with DEFAULT = sentinel UUID; FK changed from ON DELETE SET NULL to ON DELETE SET DEFAULT. (d) Removed the IS NULL arm from BOTH RPCs — eligibility is now purely the EXISTS check. ⚠ **NEVER DELETE the sentinel row `267a09ac-76f3-43fb-901f-3015aef88e22`** — it is the FK DEFAULT target; deleting it breaks every document pointing at it. The admin UI must hard-guard against deleting it.
  - **Migration 050 (2026-06-25) — source_aliases lookup table:** `source_aliases` (alias_key text UNIQUE normalized → source_id FK ON DELETE CASCADE). 54 aliases seeded across 39 entities. New source rows: "CLF Church" (`clf-church`, `owned/shown`) and "An Unknown Christian" (`public_domain/shown`). F.F. Bosworth set to `unlicensed/hidden` (d.1958, not US public domain).
  - **Gate rule (MUST be preserved in all future RPC edits):** `EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id AND (s.license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility = 'shown')))`. `safe_mode_on` is a plpgsql variable read ONCE per function call. Both RPCs are `LANGUAGE plpgsql`. There is NO `IS NULL` arm — every document has a source_id (NOT NULL constraint since migration 049). Gate keys on the entity; deliberately ignores `documents.is_copyrighted`.
  - **Safe mode:** `UPDATE app_settings SET value='on' WHERE key='safe_mode'` serves only PD/owned; `'off'` restores unlicensed-but-shown content; `sources.visibility` is never written by the switch.
  - **Entity-consolidation rules (encoded in source_aliases):** re-upload venues → speaker (Good News Church / The Crossroads / Christ for the Nations → Derek Prince; Sandals Church → John Bevere); name variants → canonical (Derek Prince Ministries → Derek Prince; John Bevere TV / johnbeveretv / Drawing Near → John Bevere); co-authored Bevere + Renner → John Bevere; Ruth Prince is her OWN entity, NOT folded into Derek Prince.
  - **Ingest pipeline status:** ALL ingest scripts do NOT yet set `documents.source_id`. New content lands on sentinel via column DEFAULT — fail-closed (hidden, not served) but requires manual reassignment. Stage-2 workstream: wire scripts to resolve source_id via `source_aliases` lookup.
  - **Open items:** ingest source_id enforcement (stage-2, not yet built); admin UI for `source_license_audit` (not built); backfill "The Kneeling Christian" → An Unknown Christian source.

---

## Environment Variables (in backend/app/.env)
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY` — Claude Sonnet 4.5 for answer generation
- `COHERE_API_KEY` — Cohere rerank-v3.5 for retrieval reranking
- `GOOGLE_API_KEY` — Gemini 2.5 Flash for magazine extraction
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
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal) |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run) |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |
| `scripts/generate_excerpts.py` | Batch-generate word study articles from Precept Austin chunks via Anthropic Claude |
| `scripts/whisper_transcribe.py` | Whisper medium transcription + Groq cleaning (batch or single-URL) |
| `scripts/youtube_pipeline.sh` | Full YouTube pipeline: scrape → clean → whisper → ingest |
| `scripts/retag_sermons.py` | Retag sermon_transcript docs via Claude Haiku against new taxonomy |
| `scripts/ingest_commentaries.py` | Ingest HistoricalChristianFaith commentaries from SQLite DB |
| `scripts/scrape_individual_videos.py` | Individual YouTube video ingestion from xlsx tracker |
| `scripts/scrape_channel_titles.py` | Dump all video titles from YouTube channels to CSV |
| `scripts/bible_refs.py` | Shared Bible reference extractor (Groq) — used by ingest.py and ingest_magazine.py |
| `scripts/backfill_phrase_refs.py` | Backfill bible_references via phrase matching (no LLM). Flags: `--source-kind`, `--author`, `--limit`, `--dry-run`, `--force`, `--chunks` |
| `scripts/fix_article_json.py` | One-off migration: fixed 30 chunks with raw JSON content (run 2026-04-17) |
| `scripts/extract_book_quotes.py` | Extract quotable passages from Murray books via Claude Haiku 4.5. Flags: `--dry-run`, `--limit`, `--title` |
| `scripts/setup_document_images.py` | One-off: creates `document-images` Storage bucket, downloads Unsplash image, uploads, assigns `image_url` to Mumford doc. Run after migration 042. |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

### Root-Level Ingestion Scripts

| Script | Purpose |
|---|---|
| `scrape_preceptaustin.py` | Scrape Precept Austin Greek/Hebrew word studies |
| `ingest_preceptaustin.py` | Ingest Precept Austin word studies into Supabase |
| `ingest_lexicon.py` | Ingest STEPBible lexicon files (TBESG, TBESH, TFLSJ) |
| `ingest_bible.py` | Ingest WEB Bible into verses table |

---

## How to Work on This Project
- Alex works fast — short messages, direct feedback
- Surface risks before building, not after
- All code changes stay in Claude Code — don't suggest manual edits unless trivial (1-2 lines)
- Read output directly — never ask Alex to copy-paste terminal output
- Check actual files before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
