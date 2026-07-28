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

## Session Routing

Determines which path a session's task runs on — not a judgment call. Read
this table first, identify the session type from objective properties of the
task (not vibes), then follow its assigned path. If a task doesn't cleanly
fit one row, it's two sessions, not one hybrid session — split it.

**Hard rule — no exceptions.** Any session that writes to the database, by
any mechanism (a `psycopg2` script, a migration apply, an SQL Editor
statement, a write RPC), runs on the plain script path. Never
`executor`/`planner-reviewer`. This holds regardless of how cleanly a prior
harness session went — the 2026-07-25 document-linking build (migration 071)
was a clean harness result and does not change this rule. Reason: the
harness's write recorder is real ground truth for what it *does* record
(`guard_pretooluse.py`, record-primary since commit `96bc3ff`), but
`BASH_WRITE_INDICATORS` still deliberately over-flags benign Bash calls as
writes (documented, open — `rhemata-status.md`'s "Known Harness Bugs"). A
false-positive write flag costs real data-risk turns on a genuine DB-write
session in a way it doesn't on a repo-only session, where the worst case is
an extra review cycle. (The 2026-07-18 12-turn stall this over-flagging
behavior is related to was itself fixed 2026-07-19, commit `d9ab1cc` — the
residual risk named here is the over-flagging pattern, not that closed bug.)
**Revisit trigger:** once the over-flagging classifier is narrowed (its own
dedicated session, flagged but not scheduled) and a second clean DB-write
harness session is deliberately run and reviewed, this rule gets revisited —
not before, and not by default.

| Session type | Objective trigger criteria | Path | Also load | Skip | Reason |
|---|---|---|---|---|---|
| **Database write** | Any Bash-run script, migration apply, or SQL statement performs INSERT/UPDATE/DELETE/ALTER/schema DDL against Supabase — including via `psycopg2` or the SQL Editor. | **Plain script.** Never harness. | N/A — harness not used | N/A — harness not used | Hard rule above. |
| **Read-only diagnostic / audit** | Zero `Edit`/`Write` calls, zero DB mutation — SELECT-only queries, file reads, greps, read-only script runs. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | No build-then-judge loop needed for a single read-only pass; harness review overhead buys nothing here. |
| **Repo-only multi-step build** | Task ships a working repo change across multiple files and/or multiple ordered steps (new feature, new script plus its own verification, a refactor) — zero DB writes anywhere in the session. | **Harness** (`executor`/`planner-reviewer`). | `HARNESS.md` (always, for harness sessions); `ARCHITECTURE.md` (near-universal for build work); `PRODUCT.md` + `DESIGN.md` only if the task touches UI; `POSITIONING.md` only if it touches copy. | `PRODUCT.md`/`DESIGN.md`/`POSITIONING.md` unless the task's own surface requires them. | This is what the harness exists for — multi-step work that benefits from a planning/review split. |
| **Repo-only single-script / trivial edit** | A single mechanical edit or one-shot script, no multi-step build sequence — zero DB writes anywhere in the session. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | A planning/review loop is overhead a one-shot change doesn't need. |
| **Docs/records-only** | Task's only output is a change to `CLAUDE.md` / `PLAN.md` / `POSITIONING.md` / `DESIGN.md` / `rhemata-status.md`. | **Plain — chat proposes, terminal commits**, per the Project Knowledge Read Contract's propose→commit rule. | N/A — harness not used | N/A — harness not used | Structurally enforced, not just preferred: `guard_pretooluse.py` denies `Edit`/`Write` on all five governed files for any subagent — the harness physically cannot do this work. |

**Stall-risk mitigation for harness sessions (repo-only multi-step build
row):** if a harness session shows the same flagged-item count across ≥3
consecutive turns with no underlying action changing (the 2026-07-18 stall's
signature), abort to the plain path immediately rather than keep retrying —
and log the abort in `rhemata-status.md`'s Known Harness Bugs section with
the turn count and the flagged item, even if you route around it rather than
fixing it that session.

**The upcoming closeness check (Phase 2, paraphrase wording gate) falls
under Repo-only multi-step build → harness**, for the build-and-test work
itself (new detection script, its own verification pass, no DB write). If a
later session runs that check against real corpus data and writes
flags/results back to the database, *that* session is a **Database write**
session and moves to the plain path — same project, different session,
different row, per the hard rule above.

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

10. **Every proposition write must stamp provenance** (prompt version label,
    a fingerprint of the exact instruction wording, model) — added 2026-07-23
    after a leaked worked example required a manual text search across every
    stored row plus git archaeology, because nothing recorded which prompt
    produced what. The fingerprint is authoritative over the label when they
    disagree — labels drift (this project's own "v4" label covered three
    different actual wordings in one afternoon); a fingerprint computed fresh
    from the literal text each time cannot. Any new proposition-writing path —
    a new ingest script, the eventual full backfill, anything calling the
    storage function directly rather than through the shared entry point —
    must pass real values for all three. An unstamped write silently reopens
    this hole.

11. **Scripture-reference grounding inside `extract_propositions()` must stay
    unconditional — never make it opt-in.** Unlike the closeness-check gate
    (`process_document()`'s `name_pattern`/`verse_lookup` params, default-off
    by design), the reference-grounding strip (PLAN.md #45.5) has no
    off-switch on purpose. A now-deleted one-off script
    (`sample_v4_propositions_2026-07-23.py`) proved `extract_propositions()`/
    `store_propositions()` are directly callable, bypassing
    `process_document()`'s gates entirely — an opt-out parameter here would
    reopen exactly the citation-fabrication hole this fix exists to close. If
    a future caller genuinely can't tolerate it, that means the check belongs
    somewhere else, not that it needs a bypass flag.

---

## Landmines (live, as of last audit — verify before trusting)

- `ingest_helloao.py` is not routed through `shared_ingest`. Fetches a live
  API and is the real gap.
- **No live proposition row has real provenance — confirmed corpus-wide
  2026-07-28, not just for pre-07-23 rows as previously stated here.**
  Provenance stamping (migration 067) has never fired on an actual write:
  every write since it shipped, same as before, went through a since-deleted
  one-off script that called `extract_propositions()`/`store_propositions()`
  directly, bypassing the stamping call site inside `process_document()`
  (see Invariant 11). A 2026-07-23 diagnostic built a reasonably strong
  circumstantial case for what produced the pre-07-23 rows specifically (git
  history + a full-corpus text sweep for one known leak), but that's
  evidence, not a stored fact — and it doesn't extend to post-07-23 rows
  either. Treat any claim about which prompt version produced ANY current
  row as unverified unless re-checked by the same method (PLAN.md #45.5).
- **A batch of live propositions carry a scripture reference flagged
  UNGROUNDED by a 2026-07-28 corpus-wide, read-only scan** — local, gitignored
  `reference_fabrication_review/corpus_findings.jsonl`, not in git, not in
  the DB. These are human-review candidates, not confirmed fabrications: the
  WEB-only translation gap (`verses` stores only the WEB translation) means a
  genuinely-quoted verse in a different translation with no citation string
  nearby can misread UNGROUNDED. Nothing in this list has been fixed,
  deleted, or flagged in the database — fixing it is deliberately its own
  future session. Full breakdown and disclosed limitations: PLAN.md #45.5 /
  `rhemata-status.md`.
- Some sources have no alias rows; re-ingesting their content sentinels
  silently. `ALIAS_MISS` is the grep-able breadcrumb.
- **No cheap check exists for the demonstrated fabrication class: real,
  accurate content correctly sourced from one named teacher, attached to a
  different named teacher's document.** Tested 2026-07-24: a similarity-based
  check (does a proposition's meaning match something in its own document)
  was built, run corpus-wide, and rejected — confirmed-accurate propositions
  routinely scored as extreme as or more extreme than the one known real
  fabrication, so no cutoff separates them. A names/numbers/citations-present
  check remains worth building but is blind to this exact failure by
  construction — the known fabrication contains no checkable specifics at
  all. Don't treat either check, if one gets built, as covering this failure
  class without re-confirming against it directly.
- **Delete account is a stub, not real deletion.** `POST /account/delete-request`
  only inserts a row into `deletion_requests` for manual admin follow-up
  (Admin panel → Contributors → "Account Deletion Requests"). No cascading
  deletion of `conversations`, `saved_words`, `pastors_cards`, `user_roles`,
  or the Supabase auth user exists anywhere in the codebase. A submitted
  request means nothing has been removed yet.
- **YouTube ingestion has stopped — Alex's decision, 2026-07-25.** Do not run
  `run_queue_triage.py` / `run_queue_ingest.py` or otherwise pull new YouTube
  material without checking with Alex first. Vlad Savchuk and Zac Poonen — 61%
  of the current propositions layer between them — both entered via this
  route; a stale-looking ingest queue is a decision, not an oversight. See
  `PLAN.md` #44 for the reason (duplicate clip/full-sermon content found the
  same day).
- **No mechanism exists anywhere in this schema to link two documents as one
  work.** The standing "link, don't merge" policy for split-work groups and
  duplicate clips (`PLAN.md` #44) has no table or column backing it yet —
  confirmed by a direct schema check 2026-07-25. Don't assume a linked-work
  concept is queryable; it has to be designed and built first.

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
