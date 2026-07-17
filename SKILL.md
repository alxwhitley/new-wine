---
name: rhemata
description: Full project context for Rhemata — Alex's AI-assisted Bible study tool for Spirit-filled/charismatic believers. Read this skill at the start of every Rhemata work session before doing anything else. Trigger whenever Alex mentions Rhemata, the theological research app, the RAG project, or any of its components (ingestion, chat, citations, frontend, backend, copyright/licensing).
---

# Rhemata — Project Skill

## What It Is
Rhemata (ῥήματα) is an AI-assisted Bible study tool for Spirit-filled/charismatic believers. Users ask questions in plain language and get answers drawn only from a vetted, named corpus — never from an anonymous, averaged AI voice — with inline citations pointing back to the real teacher behind each answer.

Product model: Magisterium AI. UX model: Perplexity (centered chat input, inline citations, clickable source panel).

---

## Core Product Philosophy — read this before proposing any feature

Full doc: `POSITIONING.md` (project root, if present) is the source of truth for messaging and product decisions. Treat the summary below as binding until told otherwise.

- **AI is not a counterfeit for discipleship.** Rhemata's job is deliberately limited: find the right teaching, show whose it is, and send the user to the human. It never speaks as an oracle, never offers "a word," never substitutes for a pastor.
- **Refuses to flatten or filter.** General AI averages every tradition into one beige, inoffensive answer. Rhemata answers only from named, vetted sources within the charismatic/Spirit-filled tradition — convictions intact, not softened to seem more palatable.
- **Every claim is attributed.** No anonymous synthesis presented as teaching. AI-generated paraphrase is always labeled as summary, never as the teacher's own words; brief quotes are machine-verified verbatim against the source before they can be served. **⚠ Status (2026-07-07 diagnostic sweep): the machine verifier does NOT exist yet** — quote discipline is currently enforced only by system-prompt instruction (`backend/app/system_prompt.txt:112`), and the claim ships on the live `/sources` page. Before building it, read `DIAGNOSTIC_SWEEP_2026-07-07.md` Check A: there is no canonical full-document text to verify against (chunks only; overlap-trim reconstruction is lossy; 186 docs have broken chunk_index sequences).
- **Send-them-back posture.** Time-in-app is not a success metric. The product's stated design goal is connecting users to real teachers and real churches. A feature that would make a user say "I don't need my pastor, I have Rhemata" gets killed, no matter how good it is.
- **Decision filter for any new feature:** does it make Rhemata sound more like a spiritual authority in its own right, or more like a directory pointing to real ones? The former direction is always wrong.

---

## Who It's For

Primary persona: **the Discerning Student** — 20s/30s, Spirit-filled, wants to go deeper, carries real trust anxiety about false teachers, has tried ChatGPT for theology and felt the flattening. Secondary: lay teachers/small-group leaders (served via citations they can show their group) and seasoned deep-study believers (Study Mode is their home).

---

## Repo Structure

See `CLAUDE.md` (project root) for the full annotated directory tree, script table, and migration list — don't re-derive it here, it drifts every session and CLAUDE.md is what stays current.

Top-level shape: `frontend/` (Next.js 16, Vercel) · `backend/` (FastAPI, Railway) · `sources/` (per-pipeline raw/cleaned/ingested folders, gitignored) · `scripts/` (all ingestion + maintenance scripts) · `migrations/` (SQL, run manually in the Supabase SQL Editor) · `docs/` (source markdown for static marketing pages) · `CLAUDE.md` / `SKILL.md` (context docs) · `DESIGN.md` (styling authority).

**Repo location (2026-07-06):** the repo moved from `~/Desktop/rhemata` to **`/Users/alexwhitley/rhemata`**. The old Desktop stub was found and deleted 2026-07-16 — confirmed unrelated to the repo (no `.git`, different inode, just 2 stale docs files + an `.impeccable` cache from a 2026-07-06 editing session). It no longer exists.

Public marketing routes (no auth): `/home` (landing), `/sources` ("How Rhemata Handles Sources"), `/beliefs` ("Our Theological Lens") — the latter two added 2026-07-06, long-form static pages built from `docs/*.md`, linked via a shared `FooterNav` (landing-page footer + app-shell sidebar bottom-left).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (React 19), Tailwind CSS 4 → Vercel |
| Backend | Python 3.9 / FastAPI → Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| **Answer generation** | **Anthropic Claude Sonnet 4.5** (`claude-sonnet-4-5`), streamed via the `anthropic` SDK — confirmed live in `backend/app/routers/chat.py` |
| Query expansion / metadata / tagging / transcript cleaning | Groq Llama 3.3 70B (`llama-3.3-70b-versatile`) |
| Reranking | Cohere rerank-v3.5 |
| Vision / OCR (magazine extraction) | Gemini 2.5 Flash |

**Resolved contradiction (2026-07-02):** some older notes claimed Claude was removed from answer generation in April 2026 and replaced by Groq-only. That's false as of this rewrite — `chat.py` calls `claude-sonnet-4-5` directly for the streamed answer; Groq is used only for query expansion, metadata extraction, tagging, and transcript cleaning, never for the final answer. If this changes again, update this file and say so explicitly — don't let two docs silently disagree a second time.

---

## Copyright & License Architecture

Full mechanics: `CLAUDE.md` → "License Control System" and "Propositions layer" under Key Decisions. Summary:

- **`sources`** — one row per rights-holder. `license_status` (`public_domain`/`owned`/`licensed`/`unlicensed`) is the truth about rights. `visibility` (`shown`/`hidden`, default hidden) is what the SQL-layer retrieval gate actually obeys.
- **Sentinel source** (`267a09ac-76f3-43fb-901f-3015aef88e22`, unlicensed/hidden) — the FK DEFAULT every document falls to if source_id resolution fails or is skipped. Fail-closed by construction. **Never delete this row.**
- **`source_aliases`** — normalized alias_key → source_id lookup used by every ingest script to resolve attribution at write time. `ALIAS_MISS` is the one grep-able breadcrumb for a resolution failure anywhere in the pipeline. **Known gap (confirmed live, 2026-07-03):** live counts materially exceed CLAUDE.md's static numbers (67 sources / 91 aliases / 64 entities vs. the documented 43/54/39) — treat CLAUDE.md's alias counts as stale, not authoritative; query live when precision matters. Migration 058 closed one specific instance of this drift (see below) but did not attempt a full reconciliation.
- **`safe_mode`** (`app_settings` flag) — global kill switch; when on, only public_domain/owned sources are retrievable regardless of individual visibility settings.
- **`propositions` table** — atomic paraphrase-level decompositions, extracted via Groq's "four-corners" prompt (no invented content, no 3+ consecutive source words). Gate (final rule, 2026-07-02): extracts for licensed + unlicensed sources only, skips public_domain + owned, fails closed on a missing source, and Precept Austin is locked out by name inside the gate (`PRECEPT_AUSTIN_SOURCE_ID` — its excerpts are near-verbatim reorderings, not paraphrases). A parallel safety layer, not a chunk replacement — chunks still serve directly wherever license-safe.
- **Known gap:** propositions wiring is per-script discipline, not a DB-enforced guarantee — unlike source_id, which is NOT NULL + sentinel-defaulted at the schema level. Read CLAUDE.md's "Ingest scripts: propositions are per-script, not enforced" section before writing any new ingest script. **In progress (2026-07-03):** a shared writer (`scripts/shared_ingest.py`) now owns resolve→insert→chunk→embed→propositions as one chokepoint. `ingest.py` (1 of 5 document-writing scripts) is converted; `ingest_magazine.py`, `ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_commentaries.py` are not yet — the per-script-discipline gap above still applies to those four.

---

## Admin Panel

Single `/admin` route, role-gated (`user_roles` table, DB-role guard in `auth.py` — not an email allowlist). One modal (`AdminModal.tsx`) with 4 top-level tabs: **Corpus** (Documents / Sources / Pipelines sub-views), **Feedback**, **Contributors**, **Notes Queue**.

---

## Mobile UI Status

**Pass A — shipped:** floating-panel chat layout, full-bleed mobile shell, bottom tab bar (Study · Chat · Discover) that hides on keyboard focus via `ChatFocusContext`, circular floating menu button replacing the desktop top bar.

**Pass B — pending:** `UsageRing` was pulled from the mobile top bar and has not yet been remounted in the sidebar drawer.

---

## Known Blockers (as of 2026-07-16 — see the audit reports below for full detail)

Resolved this session (2026-07-05→07): chat-UI design drift fixed (`--ring` restored to blue, shine-border restored to gold `--primary`, dead `mode-toggle.tsx` deleted, off-scale radii fixed — commits `1db5077`/`a627705`); Study Mode verse+interlinear restructured borderless with horizontal-scroll interlinear (`cfda88b`/`69b78b4`); `/sources` + `/beliefs` marketing pages + FooterNav shipped (`c47bbd3`); `.gitignore`'s unanchored `sources/` rule fixed to `/sources/` (was silently ignoring `frontend/app/sources/`).

Resolved this session (2026-07-16): six living-ministry YouTube sources (Vlad Savchuk, John Bevere, Daniel Kolenda, Jack Deere, CLF Church, Bible Study Podcast) had never been checked for guest/multi-speaker misattribution — content hosted on a teacher's channel but not actually spoken by them, served under their name. Classified all 403 in-scope documents (free metadata pass + a Groq check reading only each document's first 2 chunks). Deleted 17 Savchuk documents (12 confirmed-guest + 5 unresolvable), 2 Bevere, 2 Deere. Deleted Sam Storms entirely (5 document rows — 3 distinct videos, 2 of which were accidental duplicate ingests — plus cleared 242 unvetted queue rows; the source row itself was kept, dark, for a future clean re-ingest). Deleted Bible Study Podcast entirely — both its 10 documents and the source row — no reliable single-host attribution exists for that channel at all. Set 4 CLF Church documents to `citation_mode='silent_context'` (still retrievable as context, never cited). Every deletion has a full recovery export — `recovery/deleted_urls_backup_2026-07-16.json`, committed to git — with url/title/speaker/chunk+proposition counts for every removed document and all 242 cleared queue rows. Separately, the stale Desktop repo stub (see Repo Structure above) was located and deleted.

Open blockers, roughly by severity:
1. **Quote verifier doesn't exist** (see Core Product Philosophy status note above) — and no canonical full text exists to verify against; 186 docs have broken `chunk_index` sequences.
2. **8 scripts hardcode the dead `~/Desktop/rhemata` path** (broken since the 2026-07-06 repo move): `clean_transcripts.py`, `extract_book_quotes.py`, `generate_excerpts.py`, `ingest_interlinear.py`, `ingest_tahot.py`, `ingest.py` (`DOCS_FOLDER`), `scrape_youtube.py`, `test_excerpt_generation.py`.
3. **`sources/` has no visible backup** — gitignored, single GitHub remote, no backup script/config anywhere; raw corpus exists only on this Mac. (Distinct from the new `recovery/` directory added 2026-07-16 — that only backs up specific deleted rows, not the corpus as a whole.)
4. **Guest→account conversion is unlinked** and the email-confirmation session handoff is likely broken (cookie-vs-localStorage mismatch) — full trace in `GUEST_AUTH_AUDIT.md`.
5. **Auth CTA inconsistencies** — `/library/authors` bypasses BetaGate and opens the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead `AuthButton.tsx` — full trace in `BUTTON_AUTH_UX_AUDIT.md`.
6. **Proposition backfill gap: 2,980 unlicensed docs with zero propositions** (251 covered). Aliases still missing for Jack Deere, Michael Brown, Tom Bedford, Church Life Class (new ingests would sentinel).
7. Migration `058_clf_aliases.sql` applied live but still uncommitted to git; `jewish_perspectives` table (2 rows) is fully orphaned — zero code references remain.
8. **v4 propositions prompt built, not deployed.** `scripts/propositions.py::EXTRACTION_PROMPT_V4` (named-speaker attribution instead of "the author," fuller 80–150-word target, specifics-preserving voice — added 2026-07-16) exists alongside v3, which is unchanged and still the default everywhere. v4 is uncommitted and not wired into any ingest script — calling it requires passing `prompt_version="v4"` explicitly. Tested against 18 real documents (`docs/proposition-v3-v4-comparison-2026-07-16.md`): median word count improved from v3's 40 to 60, still short of the 80–150 target. Awaiting a decision — adopt, iterate further, or discard — and, if adopted, whether to backfill existing propositions.
9. **Precept Austin raw-source gap (found 2026-07-16).** 2,176 documents are ingested in the DB, but only 1,778 raw scrape files remain in `sources/precept_austin/raw/` — 398 documents have no local raw-source backing if re-verification or re-scraping is ever needed. Not confirmed whether this is the same 398 referenced in blocker #6's "excerpt-less" figure — the two weren't cross-checked against each other.

---

## Where to Look for More

- **Current architecture, scripts, migrations, decisions log:** `CLAUDE.md` (project root) — the living source of truth, updated every session.
- **Point-in-time state** (corpus counts, in-flight tasks, known issues, "what's left to run"): `rhemata-status.md` (project root) — this skill file deliberately doesn't carry that kind of detail, because it goes stale within days.
- **Diagnostic audit reports (2026-07-06/07, repo root, uncommitted):** `GUEST_AUTH_AUDIT.md` (guest→signup→signin flow), `BUTTON_AUTH_UX_AUDIT.md` (auth CTA/button inventory), `DIAGNOSTIC_SWEEP_2026-07-07.md` (11-check facts sweep incl. the quote-verifier finding).
- **Messaging, voice, positioning decisions:** `POSITIONING.md` (project root, if present).
- **Styling rules:** `DESIGN.md` (project root).
