# Rhemata — Architecture Reference

Load on demand. Not always-loaded. See `CLAUDE.md` for invariants.

**Eviction rule:** if you can learn it by reading the repo in under 2 minutes,
delete it rather than maintain a copy. This file decays silently.

Repo root: `/Users/alexwhitley/rhemata`

---

## Shape

```
sources/          # gitignored — raw/cleaned/ingested per pipeline
  youtube/        # raw → cleaned → ingested; ingest_queue.xlsx (Queue + HowToRun + source tabs)
  magazine/       # 01_to_extract → 02_extracted → 03_approved → 04_ingested → 05_archived
  documents/      # non-copyrighted (sermons, papers)
scripts/          # all ingestion + maintenance
migrations/       # SQL, run manually in Supabase SQL Editor
recovery/         # deletion exports — NOT under sources/ (gitignored would drop them)
docs/             # source markdown for static marketing pages
  audits/         # one-off reports, diagnostics, comparisons
backend/app/      # FastAPI: main.py, auth.py, routers/, services/, db/,
                  # system_prompt.txt, theological_guardrails.txt
frontend/app/     # Next.js 16 — /home, /sources, /beliefs public; app routes gated
```

Public marketing routes (no auth): `/home`, `/sources`, `/beliefs`. Latter two
render from `docs/*.md`, linked via shared `FooterNav`.

Backend routers: `chat`, `search`, `document`, `library`, `study`,
`pastors_notes`, `usage`, `ingest`, `admin`, `feedback`.

---

## Database

Tables: `documents`, `chunks`, `propositions`, `verses`, `saved_words`,
`excerpts`, `guest_sessions`, `conversations`, `messages`, `interlinear_words`,
`book_quotes`, `user_usage`, `sources`, `source_aliases`,
`source_license_audit`, `app_settings`, `removed_urls`, `user_roles`,
`contributor_requests`, `pastors_cards`.

**documents** — `source_type` (sermon|background|magazine_article|commentary|
book|paper|other) · `source_kind` · `citation_mode` (citable|silent_context) ·
`is_copyrighted` (unreliable — see CLAUDE.md invariant 4) · `topic_tags` text[]
(nullable) · `bible_references` text[] GIN · `fts_weighted` tsvector ·
`image_url` · `source_id` uuid NOT NULL FK → sources, ON DELETE SET DEFAULT ·
`original_title`.

**sources** — one row per rights-holder. `license_status`
(public_domain|owned|licensed|unlicensed) = truth about rights. `visibility`
(shown|hidden, DEFAULT hidden = fail-closed) = what the gate obeys. `retrievable`
generated boolean is informational only, NOT read by the gate. RLS service-role.

**source_aliases** — normalized `alias_key` UNIQUE → `source_id` FK ON DELETE
CASCADE. Resolution order: source_name alias → author alias → sentinel + a
grep-able `ALIAS_MISS` log line.

**propositions** — atomic paraphrase decompositions. `document_id` FK CASCADE,
`content`, `embedding` vector(1536), `proposition_index`, `fts` generated.
Indexes: HNSW (m=16, ef_construction=64), GIN on fts, btree on document_id. No
license columns by design — resolves through document_id → source_id → sources.
Gate: extracts for `licensed`/`unlicensed` only; skips `public_domain`/`owned`;
missing source fails closed; Precept Austin locked out by name
(`PRECEPT_AUSTIN_SOURCE_ID`) — its excerpts are near-verbatim reorderings, not
paraphrases. `store_propositions` is clear-then-write (DELETE by document_id then
insert) — re-running on the same doc_id is always safe.

**app_settings** — one row, `key='safe_mode'`. On = only PD/owned retrievable
regardless of visibility. Never writes `sources.visibility`.

**removed_urls** — blocklist written by `DELETE /admin/document/{id}`, checked by
`youtube_ingest.py` before each ingest (non-fatal skip on hit).

### Retrieval

Query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) →
top 30 with `SOURCE_KIND_FUSION_WEIGHTS` (commentary ×0.6, book ×0.8, lexicon
×0.5) → Cohere rerank → top 8.

- `match_chunks` — HNSW, `hnsw.ef_search=200`
- `search_documents` — document-level FTS, ts_headline snippets
- Neighbor expansion skips commentary/lexicon (`_NEIGHBOR_SKIP_KINDS`)
- Commentary capped at 3 in final context (`COMMENTARY_CONTEXT_CAP`)
- FTS OR-fallback: on 0 results, retries OR-joined top-3 longest tokens (min 6
  chars, `_FTS_BROAD_TERMS` excluded)
- `citable_count` gate counts post-Cohere, pre-neighbor top-8; sermon/citable
  only. Hard short-circuit fires only for truly empty chunk sets.

Chunking: magazine — tiktoken cl100k_base, 550 tokens, 80 overlap. Standalone —
recursive character, 1000 chars, 200 overlap. Lexicon — one entry, one chunk.

---

## Scripts

**Shared writer:** `shared_ingest.py::ingest_document()` — resolve → insert →
chunk → embed → propositions. Hooks: `source_id` override / `resolve_from`,
`find_existing_fn` / `on_existing` (skip|reuse|delete_and_reingest), `chunk_fn`,
`propositions_conn`. Chunk inserts run through a single unconditional batched
`execute_values(...)` — there is no `insert_mode` parameter (collapsed in the
all-or-nothing rewrite). Chunk inserts must NOT include `page_number` or
`source_hash`; neither column has ever existed live.

Routed through `shared_ingest`: `ingest.py`, `ingest_magazine.py`,
`ingest_preceptaustin.py`, `ingest_lexicon.py`. **Not routed:**
`ingest_helloao.py`.

| Script | Purpose |
|---|---|
| `source_resolver.py` | `normalize_alias_key`, `resolve_source_id`, sentinel + New Wine constants, `print_resolution_table` |
| `propositions.py` | Extraction + storage. v3 prompt default; `EXTRACTION_PROMPT_V4` exists but is unwired — requires `prompt_version="v4"` explicitly |
| `ingest.py` | Standalone PDF/docx/txt + auto-tagging; `skip_dedup` param |
| `ingest_magazine.py` | From .md + frontmatter; bakes chunk-content headers |
| `ingest_lexicon.py` | STEPBible TBESG/TBESH/TFLSJ; one-entry-one-chunk |
| `ingest_lexicon_runner.py` | Batching/pacing driver over `ingest_lexicon`, checkpointed slices |
| `ingest_preceptaustin.py` | Precept Austin word studies; cross-pipeline reuse-by-title |
| `ingest_helloao.py` | Live API fetch, resume-safe; own Supabase REST inserts |
| `ingest_bible.py` / `ingest_interlinear.py` / `ingest_tahot.py` | verses table |
| `extract_magazine.py` | 3-pass Gemini/Groq extraction |
| `scrape_youtube.py` | yt-dlp + Supabase dedupe (legacy path) |
| `clean_transcripts.py` | Groq transcript cleaning |
| `youtube_triage.py` | Stage 2: enumerate + Groq classify; `process_sheet()` |
| `youtube_ingest.py` | Stage 3: fetch + `ingest_file(skip_dedup=True)`; `ingest_sheet()`. Self-contained since 2026-06-27 |
| `run_queue_triage.py` / `run_queue_ingest.py` | Stage 5 Queue orchestrators |
| `discover_sermonindex_playlists.py` | Discovery only, zero writes. Known: first page only (~40); multi-name false positives |
| `verify_chunk_alignment.py` | Standalone embedding/content alignment spot-check. **Docstring is stale** — describes insert modes that no longer exist |
| `taxonomy.py` | 258-tag taxonomy, 15 categories. **Single source of truth** — `taxonomy.md` is generated for humans only |
| `tag_existing_articles.py` / `tag_sermons_transcripts.py` | topic_tags backfill |
| `extract_bible_refs.py` | bible_references backfill |

### Queue tab contract

`url | source_name | review | filter | limit | status`

- `filter`: `min5` (skip ≤5min), `whitelist` (title-match, Groq skipped,
  pre-classified sermon=TRUE). Comma-separate for combos.
- `limit`: integer, applied via `--playlist-items 1:{limit}` at yt-dlp
  enumeration time — not a Python break after the fact. Critical for large
  channels; `enumerate_channel()` timeout is 300s.
- Whitelist mode: blank `source_name` is valid. Tab label derives from URL
  handle. Whitelist file resolves as `scripts/whitelist_{slug}.txt`.
- De-dup is additive; re-runs with a larger limit only append. To re-enumerate,
  blank the row's `status` first.

---

## Commands

```bash
# Backend deploys to Railway on push to main. There is no local backend.
git add -A && git commit -m '...' && git push

cd /Users/alexwhitley/rhemata/frontend && npm run dev   # localhost:3000

cd /Users/alexwhitley/rhemata
python3 scripts/ingest.py                               # standalone

python3 scripts/extract_magazine.py                     # magazine: extract
# manually move approved → sources/magazine/03_approved/
python3 scripts/ingest_magazine.py                      # magazine: ingest

python3 scripts/run_queue_triage.py                     # youtube: all pending
python3 scripts/run_queue_triage.py --only "Sermonindex"
python3 scripts/run_queue_ingest.py
python3 scripts/run_queue_ingest.py --sheet "Sam Storms"

python3 scripts/ingest.py --dry-run-sources             # resolve + print, no writes
```

---

## Environment

`backend/app/.env` — Supabase URL/keys, OpenAI, Groq, Cohere, Gemini, Anthropic,
`ALLOWED_ORIGINS` (comma-separated), `GUEST_QUERY_LIMIT=6`.
`ADMIN_EMAIL` is dead — auth moved to the `user_roles` DB-role guard in
`auth.py` (`require_admin_role`, `require_contributor`).

Frontend (Vercel): `NEXT_PUBLIC_*`. `next.config.ts` adds the Supabase hostname
to `images.remotePatterns`.

`nixpacks.toml` locks Python 3.9. `requirements.txt` pinned via pip freeze.

---

## Admin

Single `/admin`, role-gated via `user_roles`. One modal (`AdminModal.tsx`), 4
tabs: **Corpus** (Documents / Sources / Pipelines), **Feedback**,
**Contributors**, **Notes Queue**. Realtime uses a unique channel name per mount
(`admin-realtime-${Date.now()}`).

**Rule: admin data fetches must surface errors — never silently render
empty/zero.** A `.catch(() => setX([]))` hid a total backend 403 wall behind
"No sources found" for the entire backend lifetime.

**Rule: no N+1 in admin endpoints.** 43 sequential COUNTs timed out on Railway
and the silent catch masked it as empty state. Bulk-fetch, aggregate in Python.
If any admin endpoint is slow or flaky in prod, check for an N+1 loop first.

**FastAPI gotcha:** `Query(...)` / `Path(...)` as route defaults evaluate at
import time. A missing fastapi import → `NameError` → uvicorn never binds → every
route in that file 404s (not 500).

---

## Metering

Authenticated: 50 queries/week, Monday UTC reset. `user_usage.weekly_limit` is
per-row, not hardcoded. `increment_user_query` uses `SELECT FOR UPDATE` +
conditional UPDATE — no race at cap, returns `allowed bool`, hard 429 before any
LLM call. Study endpoints excluded. Guests: `guest_sessions` +
`increment_guest_query`, IP-capped at 20/hr/IP (migration 057) to close the
anon_id-rotation bypass. SSE meta carries `usage: {used, limit, week_start}`.

---

## Standing source policy

- New unlicensed sources register `hidden`. Flipping to `shown` is never an IP
  clearance — it requires an explicit beta-scope decision recorded in PLAN.md.
- Tier-1 beta (≤20 users) has unlicensed sources deliberately `shown` as accepted
  risk. Canonical list is the live DB, never a static list here:
  `SELECT name FROM sources WHERE license_status='unlicensed' AND visibility='shown'`.
  At the Tier-1→Tier-2 trip line, every one goes back through the gate.
- SermonIndex's "public domain where applicable" is intent, not a legal grant —
  it doesn't own third-party preachers' copyrights. Stays `unlicensed/hidden`
  until attorney review. Do NOT upgrade without legal confirmation.
- Entity consolidation lives in `source_aliases`: re-upload venues → speaker;
  name variants → canonical; co-authored → primary. Ruth Prince is her own
  entity, NOT folded into Derek Prince.
