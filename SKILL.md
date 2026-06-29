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
- `.gitignore` covers `.env`, `.env.local`, `__pycache__`, `.venv`, `node_modules`, `.next`, `.DS_Store`, `sources/`, `logs/`, `scripts/logs/`, `scripts/youtube_cookies.txt`, `license-mapping/`
- `sources/` stripped from git history (2026-06-10) via BFG Repo Cleaner — 1,151 files removed across all 215 commits; `.git` reduced from 55 MB to 3.1 MB; force-pushed to origin main
- Dead credentials + `scripts/youtube_cookies.txt` permanently removed from all git history via git-filter-repo (2026-06-26): service-role JWT and two postgresql:// DB URLs (previously hardcoded in `test_metering.py` and `ingest_bible.py`) scrubbed across all 319 commits; `.git` 8.0 MB → 4.4 MB. All commit SHAs changed by rewrite; force-pushed to origin main.

---

## Monorepo Structure

```
repo/
├── frontend/          # Next.js 16 app (Vercel)
│   ├── hooks/
│   │   ├── useUserRole.ts  # Role + displayName hook; module-level cache keyed by access token; 5-minute TTL
│   │   └── useChat.ts      # Chat state + weeklyUsage state (mount fetch from /usage, update from SSE meta)
│   └── components/
│       ├── auth/
│       │   ├── LoginModal.tsx    # Shared auth modal; initialMode prop ("signin"|"signup"); signup title/button → "Become a test user"
│       │   └── BetaGate.tsx      # Beta password gate (NEW June 2026): prompts for "rhema" access code; stores beta_access=1 in sessionStorage; inline error on wrong entry
│       ├── rhemata/
│       │   ├── usage-ring.tsx        # SVG weekly usage ring (track=--muted, arc=--foreground, grows with usage)
│       │   └── weekly-limit-card.tsx # Inline hard-stop card on 429; BILLING_ENABLED=false flag
│       ├── admin/          # Admin corpus components (corpus-types.ts, corpus-data.ts, corpus-card.tsx, card-modal.tsx)
│       └── ui/
│           └── switch.tsx  # shadcn Switch (radix-ui)
├── backend/
│   ├── app/           # FastAPI Python package
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── routers/
│   │   │   ├── chat.py       # /chat endpoint — retrieval + LLM
│   │   │   ├── search.py     # /search + /search/documents endpoints
│   │   │   ├── document.py   # /document/{id} + /document/{id}/article
│   │   │   ├── study.py      # /study/verse + /study/corpus + /study/lexicon + /study/excerpt endpoints
│   │   │   ├── pastors_notes.py  # /pastors-notes/* — cards (pending/approve/reject), requests, role management; /pending + /recent
│   │   │   ├── usage.py      # GET /usage — weekly query count for authenticated users
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
│   │   # NOTE: individual_videos.xlsx archived to _archive/2026-06-27/ (2026-06-27); all 21 rows consolidated into ingest_queue.xlsx
│   │   └── ingest_queue.xlsx       # Master ingest queue (Queue + HowToRun control tabs + source tabs; Sam Storms, John Bevere, + more; gitignored)
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
│   ├── setup_document_images.py  # One-off: create document-images Storage bucket, upload test image, assign to Mumford doc
│   ├── scrape_youtube.py      # YouTube transcript scraper (yt-dlp + Supabase dedupe, raw only — no cleaning)
│   ├── youtube_pipeline.sh    # Full YouTube pipeline: scrape → clean → ingest
│   ├── whisper_transcribe.py   # Whisper medium + Groq clean (batch from no_captions/ or single URL)
│   ├── clean_transcripts.py   # Clean raw transcripts via Groq Llama 3.3 70B
│   ├── fix_article_json.py    # One-off migration: fix raw JSON chunks in Supabase (run 2026-04-17, 30 fixed)
│   ├── extract_magazine.py    # 3-pass Gemini/Groq extraction pipeline
│   ├── ingest_magazine.py     # Supabase ingestion from .md files with frontmatter
│   ├── ingest.py              # Standalone PDF/docx/txt ingestion with auto-tagging; skip_dedup=False param bypasses MD5 guard for Stage 3
│   ├── youtube_triage.py      # Stage 2: channel enumeration + Groq title classification; exports process_sheet() callable; --sheet NAME still works direct
│   ├── youtube_ingest.py      # Stage 3: captions-first/Whisper fallback + Groq clean + ingest_file(skip_dedup=True); exports ingest_sheet() callable; --sheet NAME still works direct
│   ├── run_queue_triage.py    # Stage 5 Run 1: Queue-driven triage orchestrator (reads Queue tab, drives process_sheet per source)
│   ├── run_queue_ingest.py    # Stage 5 Run 2: Queue-driven ingest orchestrator (walks source tabs, drives ingest_sheet per tab)
│   ├── discover_sermonindex_playlists.py  # Discovery-only: enumerate SermonIndex playlists vs whitelist_sermonindex.txt (prints only, zero writes)
│   ├── whitelist_sermonindex.txt          # 17-entry whitelist for SermonIndex multi-speaker channel (13 speakers; period variants for Tozer/Austin-Sparks)
│   ├── propositions.py        # Shared proposition extraction + storage module (Groq Llama 3.3 70B, v3 four-corners prompt); process_document() entry point for ingest scripts
│   ├── source_resolver.py     # Shared source_id resolution + alias normalization; imported by ingest.py and ingest_magazine.py
│   ├── tag_existing_articles.py  # Backfill topic_tags on existing articles
│   ├── tag_sermons_transcripts.py  # Backfill topic_tags on sermons/transcripts/papers
│   ├── scrape_preceptaustin.py  # Precept Austin word study scraper (page caching, multi-strategy anchor matching)
│   ├── ingest_preceptaustin.py  # Precept Austin word study ingestion (psycopg2 chunks, OpenAI embeddings)
│   ├── ingest_lexicon.py       # STEPBible lexicon ingestion (TBESG, TBESH, TFLSJ)
│   ├── ingest_bible.py         # WEB Bible VPL ingestion into verses table (psycopg2)
│   ├── ingest_interlinear.py   # STEPBible interlinear NT ingestion into verses table
│   ├── ingest_tahot.py         # TAHOT Hebrew OT alignment data ingestion
│   ├── extract_bible_refs.py   # Backfill bible_references on all documents (psycopg2)
│   ├── download_book_covers.py # Download book cover images to frontend/public/images/books/
│   └── test_metering.py        # End-to-end metering test suite (increment, rollover, hard stop)
├── migrations/            # SQL migrations (run in Supabase SQL Editor)
│   ├── 038_pastors_notes.sql  # user_roles, contributor_requests, pastors_cards tables + RLS
│   ├── 039_user_usage.sql     # user_usage table + increment_user_query + get_user_usage RPCs
│   ├── 040_fix_increment_user_query.sql  # Conditional increment fix (SELECT FOR UPDATE, returns allowed bool)
│   ├── 041_pastors_notes_approval.sql    # Adds 'pending' status to pastors_cards, RLS for own-pending read, get_user_emails RPC
│   ├── 042_document_image_url.sql        # Adds nullable image_url (text) column to documents
│   ├── 043_sources_license.sql           # sources table (one row per rights-holder) + source_license_audit; RLS service-role only
│   ├── 044_documents_source_id.sql       # documents.source_id uuid FK → sources (ON DELETE SET NULL) + index
│   ├── 045_sources_visible.sql           # sources.visible boolean (superseded by 046)
│   ├── 046_sources_visibility.sql        # replaces visible with visibility text ('shown'|'hidden', DEFAULT 'hidden' = fail-closed)
│   ├── 047_retrieval_visibility_gate.sql # visibility gate WHERE clause in match_chunks + search_chunks_fts (variant a)
│   ├── 048_safe_mode.sql                 # app_settings table + safe_mode='off' row; gate reads flag once per RPC call
│   ├── 049_seal_null_source_id.sql       # sentinel source row + backfill 18 orphans + NOT NULL + ON DELETE SET DEFAULT + removes IS NULL gate arm
│   ├── 050_source_aliases.sql            # source_aliases table + 54 normalized alias seeds; adds CLF Church + An Unknown Christian sources
│   ├── 051_propositions_table.sql        # propositions table + HNSW index + GIN fts index + btree document_id index (SHIPPED 2026-06-25)
│   └── 052_guest_sessions.sql            # guest_sessions table + increment_guest_query RPC — idempotent doc of existing live schema (COMMITTED 2026-06-26)
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
| Reranking | Cohere rerank-v3.5 (`cohere` SDK) — narrows top 30 RRF → top 8 |
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
5. Results fused via Reciprocal Rank Fusion (RRF_K=60), deduplicated, SOURCE_KIND_FUSION_WEIGHTS applied (commentary ×0.6, book ×0.8, lexicon ×0.5), document-level collapse (max 2 chunks per doc), top 30 selected
6. Cohere rerank-v3.5 narrows top 30 → top 8 by relevance (graceful fallback to top 30 if COHERE_API_KEY unset); citable_count signal measured here (pre-expansion)
7. Neighbor chunk expansion (±1 chunk_index, skips commentary/lexicon parents, cap at 12 total); commentary chunks capped at 3 in final context
8. Backend assembles prompt: system instructions + theological guardrails + retrieved chunks (tagged with `source_kind` and `citation_mode`) + query
9. Anthropic Claude Sonnet 4.5 generates a response, streamed back via SSE with `<answer>` tag extraction. Runtime-appended faithfulness instruction preserves source document views without editorializing. Theological guardrails (`theological_guardrails.txt`) appended to system prompt enforce non-negotiable framings (e.g., Holy Spirit personhood).
9. Frontend renders response with inline citation tags

---

## Database Schema

**`documents` table** — one row per source document
- `id` (uuid), `title` (text), `author` (text)
- `source_name` (text), `source_type` (text), `source_kind` (text)
- `citation_mode` (text) — `'citable'` | `'silent_context'`
- `is_copyrighted` (boolean, default false) — **unreliable** (e.g. Derek Prince docs are `false` despite being copyrighted). License gate ignores this field deliberately.
- `source_id` (uuid NOT NULL) — FK → `sources` (ON DELETE SET DEFAULT, default = sentinel `267a09ac-76f3-43fb-901f-3015aef88e22`). New inserts that omit source_id land on sentinel (hidden, not served). No NULLs exist post-migration-049.
- `year` (int), `issue` (text), `url` (text, nullable)
- `topic_tags` (text[]) — assigned from taxonomy
- `bible_references` (text[], default `'{}'`) — canonical refs like `"Romans 8:28"`; GIN indexed
- `fts_weighted` (tsvector) — weighted FTS on title (A), author (A), source_name (B), bible_references (C, colons stripped)
- `content_summary` (text) — first chunk content for display
- `image_url` (text, nullable) — Supabase Storage public URL for hero card image (migration 042, pending run)
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

**`guest_sessions` table** — server-side guest query tracking (migration 052, COMMITTED 2026-06-26)
- `id` (uuid PK DEFAULT gen_random_uuid()), `anon_id` (text NOT NULL UNIQUE)
- `query_count` (integer DEFAULT 0), `created_at` / `last_seen` (timestamptz DEFAULT now())
- RLS enabled; one policy: service_role ALL only. `increment_guest_query(p_anon_id text) RETURNS integer` RPC: INSERT ... ON CONFLICT DO UPDATE upsert; SECURITY DEFINER; returns new query_count as bare integer. Backend checks against `GUEST_QUERY_LIMIT = 6` in `chat.py`.

**`conversations` table** — saved chat history for authenticated users
- `id` (uuid), `user_id` (uuid, FK → auth.users), `title` (text), `created_at`

**`messages` table** — individual messages within conversations
- `id` (uuid), `conversation_id` (FK → conversations)
- `role` (text: 'user' | 'assistant'), `content` (text), `created_at`

**`book_quotes` table** — extracted quotable passages from books (migration 034)
- `id` (uuid), `document_id` (FK → documents, cascade delete)
- `quote_text` (text), `quote_index` (int), `created_at` (timestamptz)
- Index on `document_id`

**`sources` table** — one row per rights-holder entity (migrations 043, 046, 049, 050; 43 rows including sentinel)
- `id` (uuid PK), `name` (text UNIQUE), `slug` (text UNIQUE, nullable)
- `license_status` text NOT NULL DEFAULT 'unlicensed' CHECK ('public_domain'|'owned'|'licensed'|'unlicensed') — TRUTH about rights; never overwritten by switches
- `visibility` text NOT NULL DEFAULT 'hidden' CHECK ('shown'|'hidden') — what the gate obeys; DEFAULT 'hidden' = fail-closed for new entities
- `retrievable` boolean GENERATED ALWAYS AS (license_status IN ('public_domain','owned')) — informational only; NOT read by the gate
- `permission_granted_at`, `permission_contact`, `permission_terms`, `notes` — optional provenance fields
- RLS: service-role only

**`source_aliases` table** — normalized alias_key → source_id lookup for ingest resolution (migration 050)
- `id` (uuid PK), `alias_key` (text UNIQUE — lowercased + trimmed + whitespace-collapsed), `alias_display` (text), `source_id` (uuid NOT NULL FK → sources ON DELETE CASCADE), `note` (text), `created_at` (timestamptz)
- ON DELETE CASCADE: aliases are disposable (unlike documents, which fall to sentinel); 54 rows seeded across 39 entities
- Lookup: `SELECT source_id FROM source_aliases WHERE alias_key = lower(trim(regexp_replace(input, '\s+', ' ', 'g')))`
- RLS: service-role only

**`source_license_audit` table** — immutable log of license_status changes (migration 043)
- `id` (uuid), `source_id` (FK → sources CASCADE DELETE), `old_status`, `new_status`, `changed_by`, `note`, `changed_at`
- Created but not yet written by any admin UI.

**`propositions` table** — atomic paraphrase-level decompositions of unlicensed documents (migration 051, SHIPPED 2026-06-25)
- `id` (uuid PK), `document_id` (uuid NOT NULL FK → documents ON DELETE CASCADE)
- `content` (text NOT NULL), `embedding` (vector(1536))
- `proposition_index` (int NOT NULL), `created_at` (timestamptz)
- `fts` (tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content,'')) STORED) — identical expression to `chunks.fts`
- Indexes: `propositions_embedding_hnsw` (HNSW vector_cosine_ops m=16/ef_construction=64), `propositions_fts_gin` (GIN on fts), `propositions_document_id_idx` (btree)
- Licensing resolves through document_id → documents.source_id → sources — no license columns on propositions by design
- Populated for unlicensed sources only; gate enforced in `propositions.process_document()`

**`app_settings` table** — global key/value store (migration 048)
- `key` (text PK), `value` (text NOT NULL), `updated_at` (timestamptz)
- One row: `key='safe_mode', value='off'` (default — no behavior change on apply)
- RLS: service-role only

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
- **Design system:** `DESIGN.md` in project root is the styling authority. Lumen system (shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme locked via `forcedTheme`). No hardcoded hex in migrated files. `components/center/DocumentCard.tsx`, `app/admin/edit/[id]/page.tsx` editor panel, and several library/document pages still carry old hex — re-migration pending.
- **Brand reset complete (June 2026):** Lora/Inter/gold hex removed. Geist Sans, shadcn primitives, CSS variable tokens throughout. `DESIGN.md` is source of truth.
- **Study Mode restructured (June 2026):** single-column layout, interlinear always visible attached to verse, inline word expansion, commentary visible without tab click, Pastors' Notes stub in place, Jewish Perspective collapsed by default. Tabs removed.
- **Guest session migration complete (June 2026):** `guest_sessions` table and `increment_guest_query` RPC created in Supabase. Frontend and backend were already wired.
- **Pastors' Notes complete (June 2026):** three-tier role system (user/contributor/admin), verse-anchored cards, contributor request flow, 50–2000 char limit, soft delete only, auto-tagging via Groq with 5s timeout fallback. Tables: `user_roles`, `contributor_requests`, `pastors_cards` (migrations 038, 041).
- **Pastors' Notes approval gate (June 2026):** contributor notes save as `'pending'`, require admin approval before publishing; admins post directly as `'published'`. `pastors_cards.status`: `'pending'` | `'published'` | `'removed'`. New endpoints: `GET /pastors-notes/pending` (admin queue — oldest-first, includes display_name + email via `get_user_emails` RPC), `POST /cards/{id}/approve` (`pending` → `published`), `POST /cards/{id}/reject` (`pending` → `removed`). `revoke_contributor` now also clears pending cards. Contributor sees "Pending review" chip on their own unreviewed note in Study Mode. Admin sees Notes Queue section in `/admin` with pending count badge on nav link. `GET /cards` optionally authenticated — returns own pending + published to contributor, all pending + published to admin. Role cache TTL 5 min added to `useUserRole.ts` (was indefinite — caused new contributors to stay stuck on 'user' role). `editError` state added to `PastorsNotesSection` — surfaces backend error text on failed edits (was silent). **Blocked until migration 041 is run in Supabase SQL Editor** — without it, `pastors_cards` CHECK constraint rejects `'pending'` and `POST /cards` 500s for contributors.
- **Admin consolidation complete (June 2026):** all admin surfaces merged into single `/admin` page with sticky anchor-nav (Overview · Contributors · Corpus). Role-based auth via `GET /pastors-notes/me` — `ADMIN_USER_ID` hardcoded constant gone from all frontend files. `/admin/contributors` and `/rhemata-corpus-admin` both redirect to `/admin` (Next.js config redirects). `app/rhemata-corpus-admin/` deleted. Corpus components in `frontend/components/admin/`. `components/ui/switch.tsx` added (shadcn Switch using radix-ui). Precept Austin Greek card has `notFilter` to exclude Hebrew docs from count. HistoricalChristianFaith card description de-staled.
- **Profile menu in sidebar (June 2026):** `AuthButton` email pill removed from all 4 page headers. Sidebar footer now has a profile `DropdownMenu` for logged-in users (displayName + email, Profile sheet, Become a contributor [user role only], Admin panel → /admin [admin only], Log out) and a Sign In button for guests.
- **JWT auth** via Supabase JWKS endpoint (`PyJWKClient`)
- **Bible Study articles excluded** from extraction pipeline (reference materials, not theological teaching)
- **Ingest auto-tagging** — ingest.py tags every new document post-chunk-insert via Groq Llama 3.3 70B; strict 3–6 tags, main themes only, non-fatal
- **is_copyrighted path-based** — `sources/youtube/` and `sources/magazine/` → true, `sources/documents/` → false. **Unreliable** (Derek Prince → `false` despite being copyrighted). License gate deliberately ignores this flag — do not "fix" the gate to read `is_copyrighted`.
- **Sermon transcripts excluded from search** — search_documents RPC defaults source_kind to "magazine_article"; transcripts available in chat retrieval only
- **All scripts in `scripts/`** — no Python files at project root; all use `Path(__file__).resolve().parent.parent` for project root
- **Bible reference tracking** — `documents.bible_references text[]` populated via Groq Llama 3.3 70B extraction; shared helper at `scripts/bible_refs.py` normalizes to `"Book Chapter:Verse"` canonical form against 66-book set + alias map; non-fatal (returns `[]` on failure); auto-populated during ingest in both `ingest.py` and `ingest_magazine.py`; backfill via `extract_bible_refs.py`
- **Prefix search** — `search_documents` RPC builds `to_tsquery` with `:*` prefix operators per token (colons split to sub-tokens), so `"Romans 8"` matches `"Romans 8:1"`, `"Romans 8:28"`, etc.; falls back to `plainto_tsquery` on parse error
- **System prompt discipline** — `backend/app/system_prompt.txt` uses XML tags (`<thinking>`, `<research_analysis>`, `<answer>`). Fully rewritten June 2026. `<research_analysis>` runs 5 fixed self-checks: author conflation, silent_context citation, biblical case overreach, settled-conviction demotion guard (check 4), and voice firewall check (check 5). Conviction-first classification: every theological question classified against settled-convictions list BEFORE weighing retrieved sources — source diversity never reclassifies a settled conviction as an in-house debate. Voice and attribution firewall: inflammatory language ("heretical," "demonic," "apostate," etc.) banned from Rhemata's own voice; charged characterizations from sources may be quoted WITH attribution. Graceful degradation: when citable material is thin, WHAT questions synthesize from background without naming sources; WHO/attribution questions direct user to Study Mode; bare "no strong material" refusal reserved for topics not covered at all. Retrieval quote rules: verbatim quotes permitted in retrieval mode only, max 50 words per quote from citable sources only. Response Discipline Rules: multi-part decomposition, retrieval-only format when asked, retrieval scope cap (10 items / 250 words), single-author dominance notice. Citation rules: prompt-injection trust boundary, no anonymous attribution, max 2-3 inline citations. Formatting: minimum 2 `##` headings per theological answer.
- **Theological guardrails** — `backend/app/theological_guardrails.txt` loaded and appended to system prompt in `chat.py`. Contains non-negotiable theological framings that override source material phrasing. Currently covers Holy Spirit personhood (person of the Trinity, not merely a power/provision).
- **Chat streaming** — Anthropic Claude Sonnet 4.5 `max_tokens=1500`. `<answer>` tag extraction server-side with 9-char buffer safety for split tags. If stream ends mid-answer, remaining buffer is flushed to client instead of silently dropped. Uses `client.messages.create(stream=True)` (not context manager form, which is incompatible with generator `yield`). Frontend: no timeouts or AbortController; stream completion via `[DONE]` sentinel or reader exhaustion; error handling for 429 (`guest_limit_reached` object, `weekly_limit_reached` object). Final SSE meta event includes `usage: {used, limit, week_start}` for authenticated users.
- **Weekly query metering (June 2026, Workstream B)** — 50 queries/week for authenticated users, Monday UTC reset. `user_usage` table (migration 039): `user_id`, `query_count`, `week_start`, `weekly_limit` (per-row, not hardcoded — Phase 2 billing can override). `increment_user_query(uuid)` RPC (migration 040): `SELECT FOR UPDATE` row-level lock, conditional UPDATE only when `v_new_count <= v_limit` — counter never exceeds limit, no race condition at cap. Returns `{query_count, weekly_limit, week_start, allowed}`. Handler branches on `allowed` flag; hard 429 stop fires before any LLM call. `get_user_usage(uuid)` RPC: read-only, handles stale-week rollover display without writing. Study endpoints never counted. Guest meter unchanged. Frontend: `useChat` seeds from `GET /usage` on mount; updates from SSE meta `usage` field after each query (no extra fetch). Hard-stop card renders inline in message stream. Usage ring in sidebar footer (desktop) and top bar left (mobile). `BILLING_ENABLED=false` flag in `weekly-limit-card.tsx` for future Stripe wiring. `daily_limit_reached` dead code stripped (not emitted by backend).
- **Discover page (June 2026)** — `app/library/page.tsx` rewritten as 6-section Discover view. Section order: Featured → Browse by type → Featured Authors → Recently Added → New Wine Archive → Pastors' Notes. All sections always render (empty state when no data). No card ever renders `description` or `content_summary` — both contain raw body text. Card fields: type chip, author, title, up to 2 topic tags, year only. `DiscoverDoc` TS interface in `frontend/lib/api.ts` — `topic_tags` is `string[] | null` (not just empty array).
- **Featured section daily rotation (June 2026)** — `FEATURED_SERMON_POOL` (8 sermons) + `FEATURED_ARTICLE_POOL` (7 New Wine articles) in `app/library/page.tsx`. LCG seeded by UTC day index, two independent seeds (`dayIndex * 2`, `dayIndex * 2 + 1`), Fisher-Yates shuffle per pool. Returns `[articles[0], sermons[0], sermons[1]]` — article in hero, sermons in supporting. Books excluded from Featured pools currently. New endpoints: `GET /library/doc-meta?ids=...` (max 20 UUIDs), `GET /library/recent?limit=N`, `GET /library/counts`, `GET /pastors-notes/recent?limit=N`.
- **Hero card image slot (June 2026, revised)** — Featured hero in `app/library/page.tsx` uses two-column layout: `grid-cols-[3fr_2fr] gap-6`, default grid stretch so image matches text height. Left column: `text-xl` title, tightened inter-element margins (mb-2/mb-1.5). Right panel: renders `<Image fill object-cover className="rounded-lg">` when `image_url` present, sparkle `✦` placeholder otherwise. `image_url?: string | null` on `DiscoverDoc` TS type; `image_url text` column added to `documents` via migration 042 (pending run). `document-images` Supabase Storage bucket (public) holds per-document images; first test image is Mumford "Maintaining a Life of Worship". `scripts/setup_document_images.py` automates bucket creation + image upload + doc assignment. `frontend/next.config.ts` adds Supabase storage hostname (`jjerxncanaxlbdzcybab.supabase.co`) to `images.remotePatterns`.
- **FastAPI `Query` import bug (June 2026)** — route default parameters like `Query(...)`, `Path(...)` are evaluated at module import time. Missing import → `NameError` at startup → uvicorn never binds → all routes in that file return 404 (not 500). Always include fastapi symbol in the import line if used as a route default.
- **Batched neighbor chunk expansion** — `fetch_neighbor_chunks_batch()` collects all (document_id, chunk_index±1) pairs from top chunks, builds `.or_()` compound filter with `and()` conditions, batches at 30 pairs per query. Replaces sequential per-chunk lookups (was 10 calls for 5 chunks, now 1-2 calls total).
- **Sparse citation rule** — system prompt enforces max 2-3 inline citations per response. Only cite when source of claim materially matters. Single citation sufficient when answer draws primarily from one source.
- **Cohere reranking** — After RRF fusion, top 30 chunks sent to Cohere rerank-v3.5 with original query; top 8 by relevance score returned. Falls back to RRF top 30 if `COHERE_API_KEY` not set or call fails. Cohere client forced to HTTP/1.1 (`httpx.Client(http2=False)`) to avoid HTTP/2 trailer framing errors.
- **SOURCE_KIND_FUSION_WEIGHTS** — Applied at step 2.75 of RRF pipeline (before doc-collapse and Cohere): commentary ×0.6, book ×0.8, lexicon ×0.5, all others ×1.0. Prevents commentary and lexicon (both silent_context) from crowding out citable sermons in the top-30 rerank pool. Constants in `chat.py`.
- **Commentary context cap** — After neighbor expansion, commentary chunks capped at 3 in final assembled context (`COMMENTARY_CONTEXT_CAP = 3`). Constant in `chat.py`.
- **Neighbor expansion skips commentary/lexicon** — `_NEIGHBOR_SKIP_KINDS = frozenset({"commentary", "lexicon"})`. Neighbors of these chunk types are not fetched — they add no useful context and would crowd out citable content.
- **FTS OR-fallback** — When `websearch_to_tsquery` returns 0 results, `hybrid_search_rrf()` retries with OR-joined query of up to 3 longest meaningful tokens (min 6 chars, common theological/stopword terms excluded via `_FTS_BROAD_TERMS` frozenset). Prevents multi-term keyword and sentence queries from silently failing the FTS arm.
- **citable_count gate** — Counted from post-Cohere, pre-neighbor-expansion top-8 window (not the final expanded context). Only chunks where `_is_citable()` returns True count. Controls both the LLM-context retrieval note and the truly-empty short-circuit.
- **Low-material fallback rework** — Hard short-circuit ("I don't have strong material") fires only for truly empty chunk sets (`not chunks and not topic_context_parts`). When `citable_count < 2` but silent_context chunks exist, proceeds to normal LLM call with retrieval note appended to context block. System prompt graceful-degradation rules determine the response shape.
- **Resilient hybrid search** — FTS and vector search failures in `hybrid_search_rrf()` are non-fatal; each falls back to empty results so the other leg can still return chunks. FTS query truncated to 300 chars (`FTS_QUERY_MAX_LEN`) to prevent Cloudflare 400 errors from oversized Supabase PostgREST requests.
- **Column break handling** — Pass 1 prompt instructs Gemini to transcribe multi-article pages column by column with `=== COLUMN BREAK ===` markers. Pass 2 prompt tells Groq to follow article content across column breaks, ignoring other articles' content.
- **psycopg2 connection fix** — Supabase pooler usernames contain a dot (`postgres.{ref}`) which `psycopg2.connect(uri)` misparses, truncating to `postgres`. All ingestion scripts (`ingest_lexicon.py`, `ingest_preceptaustin.py`, `ingest.py`, `ingest_commentaries.py`) now parse `SUPABASE_DB_URL` with `urlparse` and pass explicit keyword args (`host`, `port`, `user`, `password`, `dbname`).
- **Chat page UX polish (June 2026):** `app/page.tsx` — smart auto-scroll with 150px threshold (only scrolls when user is near the bottom, not on distant history scroll); `/` keyboard shortcut focuses the textarea (guarded against HTMLInput/HTMLTextArea focus); `handleRetry` function clears messages and resends last query synchronously (React 18 batching processes `setMessages([])` before the functional update from `sendMessage`, so history clears correctly); `suppressHydrationWarning` on greeting h2 silences SSR/client time-of-day mismatch; `role="alert" aria-live="polite"` on both chatError paragraphs; "Try again" retry button adjacent to error; `WeeklyLimitCard` receives `onNewChat` prop and renders "Start a new conversation →" link; `border-b border-border` added to top bar.
- **Study page accessibility + token pass (June 2026):** `app/study/page.tsx` — `font-serif` on all 4 verse text elements changed to `font-sans` (confirmed migration gap, not an approved exception); `prose-sm` and `max-w-none` removed from word study Sheet (both DESIGN.md violations); `role="alert" aria-live="polite"` on both verseError elements (desktop + mobile); `SheetTitle className="sr-only"` added to mobile word study sheet (`definition?.word ?? "Word Study"`) and chapter sheet (`verseData.book + chapter`); desktop + mobile chapter verse `<span>` elements made keyboard-accessible (`role="button"`, `tabIndex={0}`, `onKeyDown` for Enter/Space, `focus-visible:ring-1 focus-visible:ring-ring`); top bar brought into consistency with other pages (`border-b border-border`, `aria-label="Open sidebar"` on hamburger, `aria-label="Saved words"` on bookmark button).
- **Library Discover page polish (June 2026):** `app/library/page.tsx` — topic tag pills changed from `bg-secondary text-secondary-foreground` (near-white in dark mode, ~97% lightness) to ghost-outlined (`border border-border/60 text-muted-foreground/70`); New Wine Archive row: year date span removed, `<ArrowRight>` icon added in its place; archive row hover padding loosened (`py-4 px-2 -mx-2 rounded-md`). A11y pass: focus rings on all interactive elements (`focus-visible:ring-1 focus-visible:ring-ring`), `aria-hidden="true"` on decorative ✦, dynamic `aria-label` on filter button, `motion-reduce:animate-none` on all 10 skeleton loaders, `<hr>` replacing `<div>` dividers. Token fix: hero placeholder inline hex gradient removed, replaced with `bg-primary/25`.
- **Discover search suggestions panel bug fix (June 2026):** `app/library/page.tsx:704` — search input handler changed from `onFocus` to `onClick`. Root cause: article-close effect called `searchInputRef.current?.focus()` (lines 330–337), which fired `onFocus` and reopened the suggestions panel on back-navigation. `onClick` only fires on genuine user interaction, not programmatic focus.
- **Commentary reading view rewrite (June 2026):** `CommentarySection` in `app/study/page.tsx` — sentence-splitting flatMap regex (`(?<=\.)\s+(?=[A-Z])`) removed entirely; content now split on `\n\n+` only; lemma-boundary reparagraphing via `(?<=\. )(?=[A-Z][^.!?\n]{0,55} - )` regex (requires sentence-end before potential lemma); `[Author's Commentary | Book Chapter:Verse]` blocks parsed from chunk content and rendered as styled section dividers (author in uppercase tracking-widest text-muted-foreground font-sans, verse ref in font-medium text-foreground font-sans, border-t divider between stacked headers); bold lemma promotion — opening phrase up to ` - ` rendered as `font-semibold text-foreground`, rest as normal weight; reading container changed to `max-w-2xl font-serif`. Commentary chunk content format: `[Author | Verse]\n\nProse...` — header is stored in chunk content, not derived at display time.
- **`/home` landing page (June 2026):** New public route `app/home/page.tsx` — marketing landing page, no auth required. Sections: nav, hero, marquee, Why It Matters two-column contrast, Chat/Discover/Study feature mockups with IntersectionObserver scroll-triggered animations (once at 30% viewport, no loop), stats strip, Explore More six-card grid, Final CTA, footer. Mockups use imperative DOM manipulation (Chat/Discover) and React state (Study) to avoid excessive re-renders. Marquee: two rows, `@keyframes marquee-left/right` in `globals.css`, 88s/72s durations, Spirit-gifts topic pills, `prefers-reduced-motion` guard. New design token: `--gold-light: 44 60% 62%` added to `:root` and `@theme inline`. `/` route untouched.
- **Beta password gate (June 2026):** `components/auth/BetaGate.tsx` — client-side modal password prompt for beta access. Required code: `rhema` (case-sensitive, exact). On success: writes `beta_access=1` to `sessionStorage` and calls `onSuccess`. On failure: inline "Incorrect access code", retry allowed. Once unlocked in a session, clicking any "Become a test user" button skips the gate and opens `LoginModal` directly. Gate is client-side only — not server-enforced; acceptable for beta-access-control (not security). Guest path (`/` direct, "Try it free — no account needed") is fully ungated. Gate wired in `app/page.tsx`, `app/library/page.tsx`, `app/study/page.tsx`, and `app/home/page.tsx`. Sidebar guest footer: single "Become a test user" primary Button (replaces "Sign in" ghost button); routes through gate. `/home` nav: "Log in" link removed; "Become a test user" routes through gate.
- **`LoginModal.initialMode` prop (June 2026):** `initialMode?: "signin" | "signup"` controls which mode the modal opens in (default: "signin"). Signup mode shows "Become a test user" as title and submit button label. Toggle link still present in both modes — returning users can always switch to signin after entering the gate.
- **License Control System (June 2026, migrations 043–050):** SQL-layer fail-closed gate preventing unlicensed content from reaching retrieval. Does NOT touch `INCLUDE_COPYRIGHTED` env flag or Python `citation_mode` filtering — both still operate as before.
  - **Architecture:** `sources` (one row per rights-holder, 43 rows including sentinel): `license_status` text = TRUTH about rights; `visibility` text DEFAULT 'hidden' = what the gate obeys; `retrievable` generated boolean = informational only (NOT read by gate). `documents.source_id` uuid NOT NULL FK → sources ON DELETE SET DEFAULT (default = sentinel `267a09ac-76f3-43fb-901f-3015aef88e22`). `source_aliases` normalized alias_key → source_id lookup (54 aliases, 39 entities). `source_license_audit` table created, not yet written by any UI. `app_settings` key/value with `safe_mode='off'` default.
  - **Sentinel row (migration 049, ⚠ NEVER DELETE):** UUID `267a09ac-76f3-43fb-901f-3015aef88e22`, "Unassigned — needs source", `unlicensed/hidden`. It is the FK DEFAULT target — deleting it breaks every document pointing at it. Admin UI must hard-guard against this. When a source is deleted, its docs fall to the sentinel (hidden) rather than becoming NULL.
  - **Gate rule (MUST be preserved in all future RPC edits):** In both `match_chunks` and `search_chunks_fts`, a document is eligible if: `EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id AND (s.license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility = 'shown')))`. `safe_mode_on` is a plpgsql variable read ONCE per function call from `app_settings`. Gate keys on the entity; deliberately ignores `documents.is_copyrighted`. There is NO `d.source_id IS NULL OR` arm — every doc has a source_id (NOT NULL since migration 049).
  - **Fail-closed cases:** hidden entity → excluded. New entity row → DEFAULT 'hidden' → excluded until explicitly shown. New ingest with no source_id → sentinel (hidden) → excluded until manually reassigned. Deleting a source → docs fall to sentinel → excluded.
  - **`search_chunks_fts` is `LANGUAGE plpgsql`** (converted from sql in migration 048 to support the safe_mode variable). Keep it plpgsql.
  - **Safe mode toggle:** `UPDATE app_settings SET value='on', updated_at=now() WHERE key='safe_mode'` — serves only PD/owned; ignores visibility; never writes to `sources.visibility` (reversible). `'off'` restores unlicensed-but-shown content. HNSW index preserved in both states.
  - **Entity-consolidation rules (encoded in source_aliases):** re-upload venues → speaker (Good News Church / The Crossroads / Christ for the Nations → Derek Prince; Sandals Church → John Bevere); name variants → canonical (Derek Prince Ministries → Derek Prince; John Bevere TV / johnbeveretv / Drawing Near → John Bevere); co-authored Bevere + Renner → John Bevere; Ruth Prince is her OWN entity, NOT folded into Derek Prince. F.F. Bosworth is `unlicensed/hidden` (d.1958, not US public domain).
  - **Ingest pipeline status:** `ingest.py` and `ingest_magazine.py` now resolve `documents.source_id` at ingest time via the shared resolver (`scripts/source_resolver.py`). Resolution order: source_name alias → author alias → sentinel (fail-closed). Misses fall to sentinel AND emit a grep-able `ALIAS_MISS` log line. `ingest_magazine.py` resolves New Wine Magazine to hardcoded UUID `72b2f583-d7f9-4361-be1c-6d5aebe59fac` through the same path. Column DEFAULT remains the safety net. `ingest_preceptaustin.py`, `ingest_lexicon.py`, and root-level scripts still omit source_id and land on sentinel via DEFAULT.
  - **Open items:** single-y admin demotion (UID `1ea99425-08ec-40f2-9ed3-588b88122a82` → role `user`, pending verification); `NEXT_PUBLIC_ADMIN_EMAIL` still gates the frontend Admin nav link to one email (breaks multi-admin at the UI layer — move to DB role check); `/pastors-notes/requests` CORS (`ALLOWED_ORIGINS` missing `https://rhemata.app` on Railway); backfill "The Kneeling Christian" → An Unknown Christian source.
- **Stage-2 ingest resolver (June 2026):** `scripts/source_resolver.py` — shared source_id resolution and alias normalization imported by `ingest.py` and `ingest_magazine.py`. Exports: `SENTINEL_SOURCE_ID`, `NEW_WINE_MAGAZINE_SOURCE_ID`, `normalize_alias_key(s)` (lowercase + strip + collapse whitespace — must match migration 050 seed normalization exactly), `resolve_source_id(db, source_name, author)` (returns `(source_id, norm_key, via)`; tries source_name alias → author alias → sentinel + `ALIAS_MISS` log), `print_resolution_table()`. Both scripts gained `--dry-run-sources` flag (resolves + prints table, no DB writes). Never fork `normalize_alias_key` — single shared normalization is the contract.
- **Corpus governance UI / Step 6 (June 2026):** `/admin` Corpus section replaced by two-tab view: Governance (default) and Pipelines. Governance: safe_mode switch + per-source table (name, doc count, license_status badge-dropdown, visibility toggle), amber "unlicensed + shown" counter pill. Writes immediate (no confirm dialog). Sentinel row locked — no controls rendered, backend 403s on edit attempts. Pipelines: ingestion cards relocated unchanged. `GET /admin/stats` endpoint (service-key, bypasses RLS) replaced broken anon-client HEAD count queries. `GET /admin/license-sources` moved from N+1 COUNT loop (43 queries ≈ 4.6s/timeout) to single bulk fetch + Python Counter (~0.5s).
- **Admin auth cutover (June 2026):** `/admin/*`, `/feedback` read, `/ingest` moved from `ADMIN_EMAIL` email-equality guard to user_roles DB-role guard. `_RequireRole` and `get_user_role` promoted from `pastors_notes.py` into `auth.py` as single implementation; `pastors_notes.py` now imports from `auth.py`. `require_admin_role` and `require_contributor` exported from `auth.py`. All 13 handlers swapped. `require_admin` function and `ADMIN_EMAIL` env var reference deleted from codebase. Multiple admins possible — grant via `user_roles` row insert, no code change. Railway `ADMIN_EMAIL` env var is dead, can be removed. Root cause: it was never set on Railway, so every `/admin/*` call 403'd since launch — invisible because all admin fetch `.catch()` blocks rendered empty/zero.
- **Admin fetch failures must surface — never silently render empty (June 2026 lesson):** `.catch(() => setX([]))` / `.catch(() => {})` on admin data fetches masked a total 403 wall behind "No sources found" / zero stats for the entire backend lifetime. Admin fetches now set `adminDataError` → visible error banner in Governance tab. Rule: admin fetches surface errors; never silently substitute empty/zero.
- **Per-row N+1 queries time out on Railway (June 2026 lesson):** One COUNT (or any per-row query) in a loop runs fine locally but blows Railway's timeout in production. `GET /admin/license-sources` ran 43 sequential COUNTs (≈4.3s), masked by the silent catch. Fix: bulk-fetch, aggregate in Python. If any admin/data endpoint is slow or flaky in production, check for an N+1 loop first.
- **Propositions layer (June 2026, migration 051 SHIPPED):** `propositions` table stores atomic paraphrase-level decompositions of unlicensed document content. Safe, always-available representation of unlicensed material — parallel to chunks, not a replacement.
  - **Copyright posture CHANGED (June 2026):** Alex is holding copyrighted chunks (accepted risk for ≤20-person private beta). Propositions are a parallel always-available layer; chunks serve on top only when display-safe.
  - **Serving rule (designed, NOT yet built in RPCs):** Propositions ALWAYS retrievable (all modes, all license statuses). Chunks served only when `license_status IN ('public_domain','owned','licensed')` OR (`visibility='shown'` AND `safe_mode='off'`). "Hidden" now means "propositions only, never chunks" rather than "fully excluded." Dedup needed at retrieval so shown-set sources don't double-weight.
  - **Ingest wiring DONE:** `ingest.py` (after chunk insert, before tagging) and `ingest_magazine.py` (after chunk loop, before final print). Both: dedicated psycopg2 connection per document, non-fatal, print `propositions: {result}`. `ingest_magazine.py` passes clean `body` (pre-chunk article text). `ingest.py` is skip-on-hash — propositions only generate on first ingest; backfill needed for already-ingested docs.
  - **`store_propositions` is clear-then-write:** DELETE by document_id then insert — re-running on same doc_id is always safe.
  - **Precept Austin decision (locked):** NOT wired, NOT paraphrased. Goes dark under safe_mode=ON. Parked option: reuse existing excerpts as proposition layer. NOT decided.
  - **Do NOT label paraphrase rewrites as "owned":** A rewrite of copyrighted material is a derivative; labeling it owned would serve verbatim under safe_mode and create an ungated hole. Source stays truthfully unlicensed; propositions are the safe-mode path.
  - **Migration 051 gotcha — no semicolons in `--` SQL comments:** A semicolon inside a comment split the migration mid-statement, caused a syntax error, and silently rolled back the whole transaction. The same-session Supabase SQL editor appeared to show success because the check ran before the implicit rollback. Rule: no semicolons in `--` comments in migration files. Verify via `SELECT to_regclass('public.<table>')` on a FRESH connection.
  - **Validated end-to-end:** Flora "How To Overcome" (stored:12) and "Christ's Eternal Lordship" (stored:15) — all rows non-null embedding + fts; four-corners quality confirmed (no invented scripture references).
- **Unified YouTube ingest pipeline (Stage 4a → Stage 5, June 2026):** `youtube_triage.py` (Stage 2) + `youtube_ingest.py` (Stage 3) are the core ingest path. Both now export `process_sheet()` and `ingest_sheet()` callables used by the Stage 5 queue orchestrators. `--sheet NAME` still works for direct single-tab use. Master workbook `sources/youtube/ingest_queue.xlsx` (gitignored) — now has Queue + HowToRun control tabs plus source tabs: Sam Storms, John Bevere (221 done_prior backfilled from DB), plus tabs for Wommack, Keener, Pawson, Clark, Virkler, Savchuk, Liardon, Kendall, Kolenda, Gabriel Heights, Philip Anthony Mitchell, Sermonindex, Leonard Ravenhill, David Wilkerson. **2026-06-27:** individual_videos.xlsx retired; its 21 rows (2 Michael Brown + 8 Jack Deere + 11 Daniel Kolenda, all confirmed in DB) added as done_prior to new "Michael Brown" and "Jack Deere" tabs and the existing "Daniel Kolenda" tab. `youtube_ingest.py` is now self-contained (find_ytdlp, try_auto_captions, download_and_whisper, clean_transcript, CLEANING_PROMPT inlined; scrape_individual_videos import removed).
- **`done_prior` status (June 2026):** new terminal status in `ingest_queue.xlsx` meaning "already in DB before this tool — never re-ingest." Used to seed the John Bevere tab with 221 existing DB documents. Rows have `ingest=FALSE` and `status=done_prior` — double-excluded from Stage 3 ingest loop (allowlist filter requires `ingest=TRUE AND status=triaged`).
- **`ingest_file()` skip_dedup param (June 2026):** `skip_dedup: bool = False` bypasses the MD5 `already_ingested()` check in `ingest.py`. Default `False` leaves the directory-scan pipeline guard unchanged. Stage 3 (`youtube_ingest.py`) passes `True` because sheet `status=done` is the authoritative dedup guard, and because `chunks.source_hash` is absent from the live DB schema. **DO NOT add `chunks.source_hash` via migration** — it is listed as droppable (see known issues line 678). Migration 053 was proposed for this, created, and immediately deleted.
- **`chunks.page_number` and `chunks.source_hash` absent from live schema (confirmed June 2026):** Both listed as droppable/unused. Neither column exists in the live DB. `insert_chunks()` in `ingest.py` must NOT include them in PostgREST insert dicts — doing so triggers PGRST204. Do not create migrations to add either column.
- **Stage 5 Queue Orchestration (June 2026):** `ingest_queue.xlsx` (gitignored) extended with Queue + HowToRun control tabs. Workflow: paste pending URLs into Queue tab → `run_queue_triage.py` → review source tabs → `run_queue_ingest.py`.
  - **Queue tab columns:** `url | source_name | review | filter | limit | status` (cols 1–6). `QUEUE_COL = {name: i+1 for i, name in enumerate(QUEUE_COLS)}`.
  - **Filter tokens (col 4):** `min5` → `--min-duration 300` (skip ≤5min clips); `whitelist` → title-match mode, Groq skipped, pre-classified `sermon=TRUE`. Comma-separate: `whitelist,min5`. Unrecognized tokens warn explicitly.
  - **limit column (col 5):** integer cap applied via `--playlist-items 1:{limit}` to yt-dlp at enumeration time — NOT a Python break. Critical for large channels. `enumerate_channel()` timeout bumped 120s → 300s. Non-integer in limit warns: "Did you put a filter token in the limit column by mistake?"
  - **Whitelist mode:** `source_name` blank is valid for multi-speaker channels. Tab label: `@sermonindex/videos` → `sermonindex` → `.capitalize()` → `Sermonindex`. Whitelist file: `scripts/whitelist_{slug}.txt`. Guard: skip only when `not source_name AND not whitelist_mode`.
  - **De-dup:** `all_urls_in_sheet(ws)` built once per channel expansion; only new URLs appended. Re-runs with larger limit are purely additive. Reset channel row `status` to blank to re-enumerate.
  - **`run_queue_triage.py`:** `--only LABEL` (case-insensitive). Fault-tolerant: bad rows marked `error: {msg}`.
  - **`run_queue_ingest.py`:** walks all source tabs (skips Queue + HowToRun); `--sheet NAME` for single-tab. Grand total table: TAB | DONE | FAILED | NEEDS_SOURCE | ERROR.
  - **`discover_sermonindex_playlists.py`:** prints only, zero writes. Known issues: first page only (~40 playlists); multi-name false positive on playlist titles containing multiple speaker names.
  - **`whitelist_sermonindex.txt`:** 17 entries, 13 speakers. Period variants for A.W. Tozer (3) and T. Austin-Sparks (3). In `scripts/`, NOT `sources/` (sources/ is gitignored).
  - **New sources (June 2026):** Gabriel Heights, Philip Anthony Mitchell, Leonard Ravenhill, David Wilkerson, SermonIndex (whitelist, 13 speakers). All `unlicensed/hidden`. Jesus Image: blocks scraping — dropped. Wigglesworth + Bartleman better sourced as TEXT. Always `license_status='unlicensed'`, `visibility='hidden'` for new sources; never set 'shown' before IP review.
  - **SermonIndex public-domain claim:** "committed to the public domain where applicable" — credible intent but NOT a clean legal grant. SermonIndex doesn't own third-party copyrights; "where applicable" is load-bearing. Stays `unlicensed/hidden` until IP attorney review. Do NOT upgrade to `public_domain` without legal confirmation.

---

## Content Rules
- Only ingest documents that Alex personally owns or has rights to
- New Wine Magazine pipeline is operational — `is_copyrighted=true`, controlled by `INCLUDE_COPYRIGHTED` env var
- `INCLUDE_COPYRIGHTED=true` in local `.env` and defaults true in `chat.py`
- Current non-magazine documents are single-column — no multi-column OCR handling needed
- **License gate enforcement:** every new document without `source_id` lands on the sentinel row (`unlicensed/hidden`) via column DEFAULT — fail-closed, not served. Manually reassign to the correct `sources` row after ingest, or look up via `source_aliases`. Stage-2 wiring (auto-resolve at ingest time) is not yet built — see License Control System in Key Decisions.

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
| `scripts/ingest.py` | Standalone PDF/docx/txt ingestion with auto-tagging (3–6 tags, Groq, non-fatal). Auto-populates `bible_references`. `ingest_file()` has `skip_dedup: bool = False` param — pass `True` to bypass the MD5 `already_ingested()` check (Stage 3 YouTube ingest uses this; default False preserves directory-scan guard). `insert_chunks()` does NOT send `page_number` or `source_hash` — both columns are absent from the live schema and must NOT be added (see known issues). |
| `scripts/youtube_triage.py` | Stage 2 of the unified YouTube pipeline. Reads/writes `sources/youtube/ingest_queue.xlsx`. `--sheet NAME` required (errors with available tab list if omitted or wrong — no silent fallback). Phases: (1) channel expansion via yt-dlp flat-playlist; (2) title fetch for bare video rows; (3) Groq classification into sermon/worship/promo/other using keyed `{"i": N, "label": "..."}` protocol (BATCH_SIZE=10). Sets `ingest=TRUE` for sermons, `status=triaged` on completion. Flags: `--add URL`, `--limit N`, `--retry-unknown` (re-classifies guess=unknown rows without changing status), `--dry-run`. `done_prior` rows (status ≠ "triaged") are never re-processed. |
| `scripts/youtube_ingest.py` | Stage 3 of the unified YouTube pipeline. Reads `ingest_queue.xlsx`; processes rows where `ingest=TRUE AND status=triaged`. `--sheet NAME` required. For each row: (1) resolves source via channel_name alias (`_resolve_channel_name()` handles "NA" channel names by fetching real channel via yt-dlp); sentinel hit → `status=needs_source`; (2) fetches transcript — yt-dlp auto-captions first, Whisper-medium fallback; (3) Groq clean; (4) calls `ingest_file(is_copyrighted=True, skip_dedup=True)` — chunks, propositions, tagging all fire; (5) writes `status=done` + `resolved_source` to sheet. `done_prior` rows are excluded by the `status="triaged"` allowlist — double-excluded because `ingest=FALSE` too. Flags: `--limit N`, `--dry-run`. |
| `scripts/source_resolver.py` | Shared source_id resolution + normalization. Imported by `ingest.py` and `ingest_magazine.py`. `resolve_source_id(db, source_name, author)` → `(source_id, norm_key, via)`. `normalize_alias_key(s)` → lowercase + strip + collapse whitespace (must match migration 050 seeds exactly). Emits `ALIAS_MISS` log on resolution miss. `--dry-run-sources` flag in both ingest scripts exercises this without DB writes. |
| `scripts/propositions.py` | Shared proposition extraction + storage module. `extract_propositions(text)` — Groq Llama 3.3 70B, v3 "four-corners" prompt; strips ```json fences; returns `[]` + logs `PROPOSITION_EXTRACT_FAIL` on error (never raises). `get_license_status(conn, source_id)` — looks up license_status from sources. `store_propositions(conn, document_id, propositions, embed_fn)` — DELETE by document_id then embed + INSERT each via injected `embed_fn`; commits; returns count. `process_document(conn, doc_id, source_id, text, embed_fn)` — ingest entry point; skips unless unlicensed; returns `"skipped_licensed"` / `"no_propositions"` / `"stored:{n}"` / `"error"`; rolls back + returns `"error"` on exception; never raises. Groq client lazy-init. |
| `scripts/bible_refs.py` | Shared Bible reference extractor (Groq Llama 3.3 70B). `extract_bible_references(content) -> List[str]`. Segments at ~12k chars, normalizes against 66-book canonical set + alias map, dedupes. Non-fatal (returns `[]`). |
| `scripts/extract_bible_refs.py` | Backfill `bible_references` on all documents. Flags: `--dry-run`, `--force`, `--limit N`, `--source-kind KIND`. Uses psycopg2 for reads (avoids PostgREST timeouts). |
| `scripts/tag_existing_articles.py` | Backfill topic_tags on existing magazine articles via Groq |
| `scripts/tag_sermons_transcripts.py` | Backfill topic_tags on existing sermon/transcript/paper documents via Groq |
| `scripts/youtube_pipeline.sh` | Full YouTube pipeline convenience script: scrape → clean → whisper → ingest. Shell alias: `rh-youtube`. |
| `scripts/scrape_youtube.py` | YouTube transcript scraper (yt-dlp, Supabase dedupe, max 10 per run). Writes no_captions stubs for videos without captions or with < 400 words. |
| `scripts/whisper_transcribe.py` | Whisper medium transcription + Groq cleaning. Batch mode processes `no_captions/` stubs; single-URL mode via CLI args. |
| `scripts/clean_transcripts.py` | Clean raw transcripts via Groq Llama 3.3 70B, move to cleaned/ |
| `scripts/scrape_individual_videos.py` | ORPHANED LEGACY (2026-06-27) — individual_videos.xlsx retired and archived; its 21 videos consolidated into ingest_queue.xlsx as done_prior rows; utility functions inlined into youtube_ingest.py. Do not run. Do not delete. |
| `scripts/scrape_channel_titles.py` | Dumps all video titles from YouTube channels into `sources/channel_titles.csv`. Uses yt-dlp `--flat-playlist --print title`. Flags: `--channel "Name"` for single channel. |
| `scripts/retag_sermons.py` | Retags sermon_transcript documents using Anthropic claude-haiku-4-5 with first 3 chunks as context. Validates against taxonomy.md. Flags: `--limit N`, `--author`, `--suggest-tags`, `--dry-run`, `--force`. `--suggest-tags` runs second Haiku call for taxonomy gap analysis → `sources/tag_suggestions.jsonl`. |
| `scripts/generate_excerpts.py` | Batch-generate edited word study articles from Precept Austin raw chunks. Concatenates all chunks per document, sends to Anthropic Claude for editing into clean articles, writes to `excerpts` table (`excerpt_type = 'word_study_article'`). Flags: `--test`, `--test-quality`, `--model sonnet|haiku`, `--time-limit`. |
| `scripts/ingest_commentaries.py` | Ingests HistoricalChristianFaith commentaries from SQLite DB. Groups by father_name, one document per father, chunks with tiktoken, embeds with OpenAI, inserts via psycopg2. Single-transaction pattern (`connect_with_retry()` + `ingest_father()`). Theological tagging (Reformed, Cessationist, Charismatic-Friendly, Desert Fathers, Patristic). Flags: `--dry-run`, `--father "Name"`, `--filter-charismatic`. |
| `scripts/fix_article_json.py` | One-off migration: fixed 30 chunks with raw JSON content in Supabase (run 2026-04-17). |
| `scripts/extract_book_quotes.py` | Extract quotable passages from Andrew Murray books via Claude Haiku 4.5. 10 batches per book, 5 quotes per batch (~50 quotes/book). Validates length (100-600 chars), filters metadata/URLs. Flags: `--dry-run`, `--limit N`, `--title`. Resume-safe. Inserts into `book_quotes` table. |
| `scripts/setup_document_images.py` | One-off: creates `document-images` Supabase Storage bucket (public), downloads Unsplash image, uploads as `mumford-life-of-worship.jpg`, assigns public URL to "Maintaining a Life of Worship" document's `image_url`. Run after migration 042. |

**Deleted:** `merge_articles.py` (replaced by Pass 2 per-article segmentation)

### Additional Pipeline Scripts (in scripts/)

| Script | Purpose |
|---|---|
| `scripts/scrape_preceptaustin.py` | Scrapes Precept Austin Greek word studies. Page caching to `sources/precept_austin/page_cache/`, randomized sleep (2-5s), 4-strategy anchor matching (exact → case-insensitive → partial → reverse word), quality filters (<100 words, nav bleed, fragmented). `--fetch` runs full pipeline, `--test` limits to 10 entries. Outputs to `sources/precept_austin/raw/` + `index.json`. |
| `scripts/ingest_preceptaustin.py` | Ingests Precept Austin word studies into Supabase. Chunks via psycopg2 `execute_values` with `::vector` cast. Documents via Supabase client. Skip logic checks `excerpts` table for existing `word_study_article` excerpt (not just document existence). Reuses existing doc_id when document exists but has no excerpt. Uses `backend/app/services/chunker.py` (550 tokens, 80 overlap). |
| `scripts/ingest_lexicon.py` | Ingests STEPBible lexicon files (TBESG, TBESH, TFLSJ). One chunk per lexical entry. tiktoken truncation at 8000 tokens for embedding. Resume-safe (tracks existing chunk counts). CLI flags: `--lexicon TBESG\|TBESH\|TFLSJ`, `--delete` (removes existing data first), `--sample N`. Brief mode for TBESG: stores only gloss + bolded sub-meanings (no full Abbott-Smith HTML). Chunk inserts via psycopg2 `execute_values` with `ON CONFLICT DO NOTHING`. |
| `scripts/ingest_bible.py` | Parses WEB VPL file, maps 66 canonical books (VPL→SBL abbreviations), inserts into `verses` table via psycopg2. Batch size 1000, `ON CONFLICT DO NOTHING`. `--test` limits to 100 verses. Skips deuterocanonical books. |
| `scripts/ingest_interlinear.py` | Ingests STEPBible interlinear NT data into `verses` table via psycopg2. `PROJECT_ROOT / sources/lexicon/`. Flags: `--test` (Matthew 1 only), `--book`. |
| `scripts/ingest_tahot.py` | Ingests TAHOT Hebrew OT alignment data via psycopg2. `PROJECT_ROOT / sources/`. Cache dir: `/tmp/tahot` (absolute). Flags: `--test` (100 rows), `--book`. |
| `scripts/extract_bible_refs.py` | Backfill `bible_references` on all documents. Flags: `--dry-run`, `--force`, `--limit N`, `--source-kind KIND`. Uses psycopg2 for reads (avoids PostgREST timeouts). Imports `bible_refs.extract_bible_references` as a sibling module. |
| `scripts/download_book_covers.py` | Downloads book cover images to `frontend/public/images/books/`. No DB credentials needed. |
| `scripts/test_metering.py` | End-to-end metering test suite (increment sequence, week rollover, hard stop, stale-week GET /usage). Run from repo root — uses CWD-relative `migrations/039_user_usage.sql` path. |

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
- Sidebar: Shared across all routes. "Rhemata" wordmark, `text-primary` "New Chat" CTA, nav items (Chat/Discover/Study), conditional content (Recents on chat, Saved Words on study). Footer: profile `DropdownMenu` for authenticated users (displayName/email, Profile sheet, Become a contributor [user role], Admin panel [admin role], Log out); Sign In button for guests. No right border — blends with `bg-sidebar` outer canvas. Design tokens throughout.
- Chat page: Floating panel layout — outer shell `bg-sidebar`, main content in `bg-background rounded-xl` panel (8px inset on all sides). Scroll fade (`sticky top-0 h-8 gradient`) at top of message list. Top bar has no bottom border; panel edge provides separation.
- Search page at `/search` with keyword search, browse-all default listing, result cards with topic tag pills, and full article reader
- Auth flow: all "Become a test user" entry points (sidebar, /home nav, /home hero, /home final CTA, guest limit) route through BetaGate → LoginModal; sessionStorage flag prevents re-gate within session. "Try it free — no account needed" and direct / visits bypass the gate entirely.
- Guest users get 6 free queries before prompted to sign up (still routes through BetaGate)

---

## Brand
- **Name:** Rhemata
- **Design system:** Lumen — shadcn new-york, Tailwind v4 CSS vars, Geist Sans, single dark theme. `DESIGN.md` is the styling authority. No hardcoded hex in fully migrated files.
- **Migration status:** Chat page, sidebar, library (Discover), study, and all admin pages fully on design tokens. `font-serif` migration gap on verse text in `study/page.tsx` found and resolved (June 2026) — all 4 verse text elements changed to `font-sans`; `prose-sm`/`max-w-none` violations in word study Sheet also resolved. Remaining old hex: `components/center/DocumentCard.tsx`, `app/admin/edit/[id]/page.tsx` editor panel, `app/library/authors/page.tsx`, `app/library/book/[id]/page.tsx`, `app/document/[id]/page.tsx`. Re-migration pending.
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
- **Sidebar:** Shared `sidebar.tsx` across Chat and Study. Uses `usePathname()` for active route. Chat shows Recents; Study shows Saved Words. Nav items: Chat (MessageSquare), Discover (Compass, href `/library`), Study (BookOpen). Active nav text `#e6e6e6`, inactive `#c1c1b8`. Gold "New Chat" CTA (`#b49238`). Hover standard: `onMouseEnter` bg `#262624`, `onMouseLeave` transparent. Nav label was "Library" — renamed to "Discover" (June 2026) in both `sidebar.tsx` and `mobile-tab-bar.tsx`.
- **Saved words:** `saved_words` table in Supabase (migration 017). RLS policy scoped to `auth.uid()`. Toggle save/unsave from definition panel bookmark icon. Sidebar shows English gloss + Strong's number, transliteration below.
- **Verse lookup:** Direct Supabase query from frontend (`verses` table, keyed by `verse_id`). Client-side `parseRef()` with full 66-book `BOOK_MAP` + `ABBREV_TO_NAME`.
- **Left panel:** Search bar, verse card, "View Chapter" button, chapter view. No interlinear or definition content.
- **Chapter view:** Flowing text with inline `<sup>` verse numbers. Verses queried via `.like("verse_id", "JHN.1.%")` pattern. Active verse highlighted with `#2f2f2c` background. Clicking a verse in chapter view loads it as the active verse.
- **Right panel tabs:** `CorpusTab` type: `"commentaries" | "word_study" | "jewish"`. Tab state lifted to parent `StudyPage` for cross-panel coordination.
  - **Commentary tab:** `GET /study/commentary` with book-level pre-filter + scoped vector search. Pre-filter uses `match_commentary_by_book` RPC (migration 028) to get doc IDs for the current book via `bible_references && ARRAY[book_name]`. When doc IDs found, calls `match_commentary_chunks` RPC (migration 029) with `document_ids uuid[]` parameter for scoped vector search. Falls back to unfiltered `match_chunks` if no book matches. No `citation_mode` filter — commentary docs use `silent_context` for chat but are always shown in study mode. Author boosts: Matthew Henry +0.15, JFB +0.08, Adam Clarke +0.03, others −0.10. **Both commentary and sermon results use `_fetch_neighbor_content()` (±1 chunk expansion)** for richer context — returns prev+current+next chunks joined by `\n\n`. Sermon results via `match_sermon_chunks_by_ref` RPC (max 2). Paginated at 3 per page. Study mode uses `study_filters` that ignores `source_name` toggles (chat-only). **Frontend render (June 2026):** splits on `\n\n+` only (sentence-splitting regex removed); detects `[Author | Verse]` header blocks and renders as styled dividers; body paragraphs split at lemma boundaries; opening lemma phrase bolded. Reading container: `max-w-2xl font-serif`.
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

- **Sam Storms tab has 237 triaged rows** ready for Stage 3 ingest — run `python3 scripts/youtube_ingest.py --sheet "Sam Storms"`. 2 rows already `status=done` (demo rows confirmed clean).
- **9 teacher tabs are empty** (Andrew Wommack, Craig Keener, David Pawson, Randy Clark, Mark Virkler, Vlad Savchuk, Roberts Liardon, R.T. Kendall) — seed each by adding a channel URL: `python3 scripts/youtube_triage.py --sheet "Name" --add URL`. Note: Daniel Kolenda tab now has 11 done_prior rows (all confirmed in DB, migrated from individual_videos.xlsx 2026-06-27).
- **Sam Storms tab has 10 guess=unknown rows** (from `--retry-unknown` run). Remaining unknowns out of original 100 — Groq could not classify them. Manual review or another `--retry-unknown` pass.

- **Proposition backfill not yet run** — `ingest.py` is skip-on-hash, so already-ingested docs never hit the new proposition step. Need a separate backfill script to run `propositions.process_document()` over all unlicensed docs with chunks but no propositions yet. Precept Austin explicitly excluded from backfill (Alex's decision).
- **Proposition serving rule not yet built into RPCs** — `match_chunks` / `search_chunks_fts` do not yet serve propositions. Designed rule: propositions ALWAYS retrievable; chunks only when `license_status IN ('public_domain','owned','licensed')` OR (`visibility='shown'` AND `safe_mode='off'`). Dedup needed so shown-set sources don't double-weight. Not started.
- **Two live test propositions in DB** — Flora doc (12 rows) and "Christ's Eternal Lordship" (15 rows) from validation runs. `store_propositions` is clear-then-write so re-ingest will safely overwrite them; leave as-is.
- ~~**Ingest scripts do not set `source_id`**~~ — **PARTIALLY DONE (June 2026):** `ingest.py` and `ingest_magazine.py` now resolve `source_id` at ingest time via `scripts/source_resolver.py`. `ingest_preceptaustin.py`, `ingest_lexicon.py`, and `rh-*` aliases still omit `source_id` and land on sentinel via DEFAULT.
- **License admin UI** — `source_license_audit` table is live but nothing writes to it yet. Governance UI (June 2026) added `sources.visibility` and `license_status` controls directly; `source_license_audit` writes still not implemented.
- **Migration 041 not yet run** — `migrations/041_pastors_notes_approval.sql` must be applied in Supabase SQL Editor before the approval gate is live. Without it, the `pastors_cards_status_check` constraint rejects `'pending'` and `POST /cards` 500s for contributors. Also creates the `get_user_emails` RPC and the own-pending-read RLS policy.
- **Full 300-issue batch not yet run** — only 4 articles ingested from issue 03-1973
- **Migration 012 not yet run** — needs to be applied in Supabase SQL Editor (Migration 013 for `bible_references` is applied as of 2026-04-10)
- **`sources/youtube/youtube_tracker.xlsx` still tracked** — needs `git rm --cached sources/youtube/youtube_tracker.xlsx` to finish the earlier `sources/` cleanup. Shows up as modified on every commit.
- **Issue_03-1973 cleanup A/B/C options** never resolved in the continuation-resolver session — was left in `02_extracted/` in an uncertain state.
- **scrape_youtube.py dead Haiku code** — removed (2026-04-15)
- **content_summary not auto-populated** on new article inserts (trigger only updates fts_weighted, not content_summary)
- **Tagging retry logic** sometimes needs improvement for complex articles
- ~~**Guest query limit**~~ — **DONE (June 2026):** `guest_sessions` table and `increment_guest_query` RPC created in Supabase. ~~**Missing migration file**~~ — **DONE (2026-06-26):** `migrations/052_guest_sessions.sql` committed; idempotent, safe to re-run, does not touch existing data. RLS/service-role policy intentionally NOT in 052 — those live in migration 037.
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
- ~~**Individual video ingestion not yet run**~~ — **DONE:** All 21 videos confirmed in DB (2 Michael Brown + 8 Jack Deere + 11 Daniel Kolenda Cessationism 1–11). All confirmed via URL + title match against `documents` table (2026-06-27). Prior SKILL.md note about 9 Kolenda videos pending retry was stale — all 11 were already in DB.
- **Uncommitted changes from May 2026 session** — taxonomy.md, taxonomy.py, retag_sermons.py, scrape_channel_titles.py, channel_titles.csv, tag_suggestions.jsonl. Need commit + push.
- **3 YouTube channels not found** — Dr. Michael Brown (`@AskDrBrown`), Jack Deere (`@JackDeere`), Myles Munroe (`@MylesMonroeTV`) handles don't resolve on YouTube. Need correct handles or removal from channel_titles scraper.
- **Individual Videos dashboard card** — added to corpus admin Pipelines group, filters on `source_name ILIKE '%Individual Videos%'`. Note: individual_videos.xlsx archived 2026-06-27; card may show zero (all 21 videos ingested under speaker source names, not "Individual Videos").
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
- ~~**9 Kolenda Cessationism videos pending retry**~~ — **RESOLVED (2026-06-27):** DB check confirmed all 11 Kolenda videos present. All 11 added as done_prior to Daniel Kolenda tab in ingest_queue.xlsx. individual_videos.xlsx archived.
- ~~**Daniel Kolenda not in youtube_tracker.xlsx**~~ — **RESOLVED (2026-06-27):** Daniel Kolenda tab in ingest_queue.xlsx now has 11 done_prior rows. youtube_tracker.xlsx also archived.
- **Migration 033 pending** — `books.document_id` column. Must run in Supabase SQL Editor, then backfill with `UPDATE books b SET document_id = d.id FROM documents d WHERE lower(b.title) = lower(d.title) AND lower(b.author) = lower(d.author)`. "Read Excerpts" button on book cards won't render until this is done.
- **Migration 034 pending** — `book_quotes` table. Must run in Supabase SQL Editor before `extract_book_quotes.py` can be executed.
- **`extract_book_quotes.py` not yet run** — depends on migration 034. Will extract ~50 quotes per Murray book via Claude Haiku 4.5.
- **Library book reader supports quotes + chunk fallback** — `GET /library/book/{id}` returns `quotes` array if `book_quotes` has data for the document, otherwise falls back to `chunks` array. Frontend handles both shapes.
- **`/ingest` endpoint admin-only (2026-06-10, updated June 2026)** — was open to any authenticated user. Now uses `require_admin_role` (DB user_roles check) from `auth.py`; originally used `require_admin` (ADMIN_EMAIL email check, broken — never set on Railway). Auth cutover done June 2026.
- **JWT payload logging removed + log level INFO (2026-06-10)** — `auth.py` no longer logs full JWT payloads (was leaking emails/claims into Railway logs); `main.py` `basicConfig` changed DEBUG → INFO. Deployed on next git push.
- **RLS disabled on `verses`, `excerpts`, `background_topics` (found 2026-06-10)** — anon key has full read/WRITE on these three tables. `background_topics` content is injected into chat prompts, so anon write = prompt-injection vector. Enable RLS with public-SELECT-only policies. (Verified live: `conversations`/`messages` have correct owner policies; `documents`/`chunks` are public-SELECT-only — those are fine.)
- **`interlinear_words` INSERT policy is `WITH CHECK (true)`** (migration 023) — named "service role" but allows anon inserts. Change to `auth.role() = 'service_role'`.
- ~~**`match_sermon_chunks_by_ref` seq-scans all 193k chunks**~~ — **FIXED (migration 036, confirmed 2026-06-13):** `c.bible_references @> ARRAY[verse_ref]` already applied. EXPLAIN ANALYZE shows index scan at 4.2ms.
- **Chat FTS arm returns 0 matches for sentence queries (verified 2026-06-10)** — `websearch_to_tsquery` ANDs all terms; full-sentence questions and Groq paraphrase variants match nothing. Fix: have query expansion emit a keyword variant for the FTS arm. Related: original user question is never searched — `expand_query()` replaces it with 3 paraphrases.
- **`search_documents` RPC ignores stored `chunks.fts`** — snippet subquery recomputes `to_tsvector('english', c.content)` per chunk (~1,100 parses per search at 55 chunks/doc × 20 results). Fix: use `c.fts` in both the filter and `ts_rank`.
- **HNSW index built with default params** — m=16, ef_construction=64, float32; 1.47 GB at 193,775 chunks (→ ~3.8 GB at 500k, RAM risk). Plan: re-embed at 1024 dims (~$3) or halfvec index, rebuild with ef_construction=128. Full scaling roadmap in 2026-06-10 architecture review.
- **24,429 chunks (12.6%) have `source_kind='unknown'`** — early-ingest books/papers backfilled as 'unknown' by migration 005. Invisible to source toggles; backfill before any source_kind-based retrieval work.
- **`conversations.updated_at` never updated** — no trigger exists; sidebar orders by it, so appending to an old conversation doesn't bubble it up. Add trigger on `messages` INSERT + indexes `messages(conversation_id, created_at)`, `conversations(user_id, updated_at DESC)`.
- **`articles` table is empty (0 rows)** — no backend references; six indexes. Drop it. Also droppable: `chunks.parent_chunk_id`/`chunk_type`/`page_number`/`source_hash` (unused), `idx_documents_year`, `idx_documents_source_year_issue`, duplicate `verses_verse_id_idx`.
- **Security review follow-ups (2026-06-10, partially done)** — verify API keys were rotated after the 2026-04-09 BFG history scrub; Python 3.9 is EOL (bump nixpacks to python312); PyPDF2 deprecated → pypdf; guest `anon_id` is client-generated and spoofable (limit bypassable; add per-IP rate limiting); no rate limits on unauthenticated embed-cost endpoints (`/search`, `/study/corpus`, `/study/commentary`); `/jewish-perspective` POST bypasses daily query limit; ~~admin email hardcoded in `admin/page.tsx`~~ — **FIXED (June 2026):** all frontend admin pages now use role-based auth via `GET /pastors-notes/me`; ~~`/rhemata-corpus-admin` has no auth guard~~ — **FIXED (June 2026):** deleted, redirects to `/admin`; ~~admin email hardcoded in `backend/app/auth.py` `require_admin()`~~ — **FIXED (June 2026):** `ADMIN_EMAIL` guard replaced by `require_admin_role` (user_roles DB check); ADMIN_EMAIL deleted from codebase.
- **Retrieval quality follow-ups (2026-06-10 review, not yet done)** — rerank pool too small (Cohere sees only RRF top-10; should rerank ~50 fused candidates then apply caps); content-type pollution (commentary 44.6% + lexicon 19.1%, both silent_context, compete for top-40 against 8% citable sermons — needs source_kind retrieval pools after denormalizing source_kind/citation_mode onto chunks); neighbor expansion should skip commentary/lexicon; `[Source N]` numbering includes silent_context chunks while frontend citations array is filtered (misalignment risk); low-material fallback counts neighbors/lexicon instead of citable chunks.
- ~~**Phase 4 hex→token migration reverted by linter**~~ — **PARTIALLY DONE (June 2026):** `app/rhemata-corpus-admin/` deleted. `app/admin/page.tsx` and `app/library/page.tsx` rewritten with design tokens. Remaining old hex: `components/center/DocumentCard.tsx`, `app/admin/edit/[id]/page.tsx` editor panel, `app/library/authors/page.tsx`, `app/library/book/[id]/page.tsx`, `app/document/[id]/page.tsx`. Re-migration pending.
- ~~**Chat page floating panel layout**~~ — **DONE (2026-06-11):** `app/page.tsx` restructured — outer shell `bg-sidebar`, main panel `bg-background rounded-xl` (8px inset). Scroll fade added. Top bar border removed. `sidebar.tsx` desktop + mobile `border-r border-sidebar-border` removed. Committed `d982a13`.
- ~~**Library image 400 errors**~~ — **FIXED (2026-06-13, commit f9c286d):** `AUTHOR_IMAGES` trimmed to 5 entries with correct extensions (`.webp`/`.jpeg`); `BOOK_COVERS` trimmed from 40 to 15 entries matching actual files on disk. Updated in both `frontend/app/library/page.tsx` and `frontend/app/library/authors/page.tsx`.
- **Vercel Analytics not enabled in dashboard** — `<Analytics />` is mounted in `layout.tsx` behind `NODE_ENV === "production"`, but the feature must be toggled on in Vercel → project → Analytics. Until then the analytics script 404s in production.
- **Study page slow load is Railway cold start** — not a DB issue. DB confirmed optimized: interlinear index scan 4.2ms, `match_sermon_chunks_by_ref` GIN index confirmed active. First request after idle takes 3-8s due to Railway sleep. No code fix; consider Railway paid plan or keep-alive ping if this becomes a user complaint.
- **Stripe billing not yet wired** — `BILLING_ENABLED = false` constant in `frontend/components/rhemata/weekly-limit-card.tsx`. Upgrade button renders disabled with "Coming soon" label. Flip to `true` and implement Stripe checkout when ready.
- **All-caps titles (15 documents)** — OCR artifact from early magazine extraction. All are `magazine_article` (14) + 1 paper. Titles like "THE PLACE OF TRANFORMATION" (also has a spelling error). Approach not yet decided — options: in-place SQL title-caser UPDATE, or manual review. Scope confirmed, fix deferred.
- **Migration 042 + image setup not yet run** — `migrations/042_document_image_url.sql` must be run in Supabase SQL Editor to add `image_url text` to `documents`. Then `python3 scripts/setup_document_images.py` creates the `document-images` Storage bucket and assigns the first test image to the Mumford doc. Until migration 042 runs, the backend `/doc-meta` SELECT will error. Hero card falls back to sparkle placeholder until `image_url` is populated.
- **Weekly usage ring: 0-query state** — at `used=0` the ring shows only the faint `--muted` track (arc guarded by `used > 0` to prevent zero-length arc producing a dot artifact with `stroke-linecap: round`). Expected behavior on first login of the week.

---

## How to Work on This Project
- **Code changes always go to Claude Code in terminal** — do not write or edit code in chat unless the change is trivial (1-2 lines)
- Alex works fast — short messages, quick pivots, direct feedback
- Surface risks and blockers before building, not after
- When Alex references a component, check the actual file before assuming structure
- Python 3.9 constraint: use `Optional[str]` not `str | None`
