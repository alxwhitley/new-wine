# Rhemata — Claude Code Context

AI-assisted Bible study tool for Spirit-filled/charismatic believers. RAG chat
with inline citations over a vetted, named corpus. Product model: Magisterium AI.
UX model: Perplexity.

**Design filter for any new feature:** does it make Rhemata sound more like a
spiritual authority in its own right, or more like a directory pointing to real
ones? The former is always wrong. Time-in-app is not a success metric — the goal
is sending users back to real teachers and real churches. A feature that makes a
user say "I don't need my pastor, I have Rhemata" gets killed regardless of
quality.

---

## Invariants — violating these reopens a closed hole

1. **Python 3.9.** Use `Optional[str]`, never `str | None`. Railway locks 3.9 via
   `nixpacks.toml`; newer syntax runs locally and breaks in prod.

2. **License gate SQL — preserve in every future RPC edit:**
   ```sql
   EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id
     AND (s.license_status IN ('public_domain','owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')))
   ```
   `safe_mode_on` is read ONCE per plpgsql call. There is NO `IS NULL` arm —
   migration 049 removed it and made `source_id` NOT NULL. Re-adding one is
   fail-open. Gate keys on the entity.

3. **Never delete the sentinel source** `267a09ac-76f3-43fb-901f-3015aef88e22`
   ("Unassigned — needs source", unlicensed/hidden). It is the FK DEFAULT target
   for `documents.source_id`. Deleting it breaks every document resolving to it.
   It looks like an orphaned row during cleanup. It is not. Admin UI hard-guards
   against its deletion.

4. **`is_copyrighted` is unreliable and the gate ignores it on purpose.** Derived
   from folder path; wrong in practice (Derek Prince docs read `false`). Do NOT
   "fix" the gate to read it. Reading the code alone makes this look like an
   obvious improvement. It is a bug.

5. **Propositions are per-script, not DB-enforced.** Unlike `source_id` (NOT NULL
   + sentinel default), nothing stops a new ingest script from skipping
   propositions silently. Any new write path must route through
   `shared_ingest.ingest_document()`. **Verify by grepping the real call site —
   comments and docstrings lie** (`youtube_ingest.py:15` claimed propositions
   "auto-fire"; the call was one level down in `ingest_file()`).

6. **Never fork `normalize_alias_key`.** It must match migration 050's seed
   normalization exactly (lowercase + strip + collapse whitespace) or aliases
   miss silently. One shared implementation in `scripts/source_resolver.py` is
   the contract.

7. **Citable requires a real attributable name.** `citation_mode='citable'` only
   if a real name attaches as source or author. Anonymous/pseudonymous stays
   `silent_context` permanently, even with a real servable `sources` row. "The
   Kneeling Christian" → "An Unknown Christian" (public_domain/shown) is
   deliberately `silent_context`. Do not read it as a sentinel artifact and flip
   it.

8. **Never label a paraphrase rewrite as `owned`.** A rewrite of copyrighted
   source is a derivative. Labeling it owned serves it as safe verbatim and opens
   a hole safe_mode cannot close.

9. **No semicolons inside `--` SQL comments in migrations.** The multi-statement
   runner treats them as terminators; the batch rolls back silently. Verify with
   `SELECT to_regclass('public.<table>')` on a FRESH connection.

---

## Landmines (live, as of last audit — verify before trusting)

- `ingest_helloao.py` is not routed through `shared_ingest`. Fetches a live
  API and is the real gap.
- Some sources have no alias rows; re-ingesting their content sentinels
  silently. `ALIAS_MISS` is the grep-able breadcrumb.

**Corpus counts are never documented here.** Query live — any static number rots
within days and has already caused one round of false blockers.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (React 19), Tailwind 4 → Vercel |
| Backend | Python 3.9 / FastAPI → Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, set explicitly) |
| Answer generation | Anthropic `claude-sonnet-4-5` via `anthropic` SDK |
| Query expansion / metadata / tagging / transcript cleaning | Groq `llama-3.3-70b-versatile` |
| Reranking | Cohere rerank-v3.5 — top 30 RRF → top 8 |
| Vision / OCR | Gemini 2.5 Flash |

---

## How to Work on This Project

- Alex works fast — short messages, direct feedback.
- Surface risks before building, not after.
- All code changes stay in Claude Code. Don't suggest manual edits unless trivial.
- Read output directly — never ask Alex to copy-paste terminal output.
- Check actual files before assuming structure.
- Never log planned work as done. Never claim build state you can't see.

---

## Project Knowledge Read Contract

State lives in repo files. No Notion mirroring, no sync step (retired 2026-07-09).

| File | Owns |
|---|---|
| `CLAUDE.md` | This file. Invariants, stack, working rules. Always loaded. |
| `ARCHITECTURE.md` | Tree, schema, scripts, env vars, commands. Load on demand. |
| `HARNESS.md` | Executor/planner-reviewer gate design. Harness sessions only. |
| `POSITIONING.md` | Messaging, voice, product posture. Source of truth. |
| `PRODUCT.md` | Who it's for, brand register, design principles, anti-references. Read before UI work. |
| `DESIGN.md` | Styling-token authority. No hardcoded hex. |
| `PLAN.md` | Roadmap, standing session rules, open decisions, findings log. |
| `rhemata-status.md` | Live state only. Overwritten each session. Never durable truth. |

**Writer rules:** terminal authors and writes `CLAUDE.md`, `ARCHITECTURE.md`,
`HARNESS.md`, `PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — from
confirmed-working builds only. `PLAN.md` content is chat-originated: chat decides roadmap, terminal writes
it verbatim. Terminal is the pen, not the author. Chat never edits any file
directly.

**Eviction rule for this file:** every line must change what you'd do on a normal
task. If a line describes the codebase accurately but wouldn't stop a mistake,
it belongs in ARCHITECTURE.md. If a decision is superseded, **delete it** — do
not stack a correction on top. Git is the provenance record. This file reached
12,000 words because nothing was ever removed, only appended to.

**Repo root is reserved.** Only these markdown files may live at root:
`CLAUDE.md`, `ARCHITECTURE.md`, `HARNESS.md`, `PLAN.md`, `POSITIONING.md`,
`PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — plus tooling config. Every other markdown
file goes in a folder: audits and one-off reports to `docs/audits/`, marketing
source markdown to `docs/`. A new file at root is a mistake, not a decision.
`CLAUDE.md` must stay at root — Claude Code looks for it there.
