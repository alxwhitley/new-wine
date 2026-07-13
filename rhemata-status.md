# rhemata-status.md

**As of:** 2026-07-13 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** none open. #9's shared batch loader (`psycopg2_batch`) is built, proven on a synthetic document, and committed. **#9 is NOT fully done** — the actual `ingest_preceptaustin.py` conversion (real files, real corpus) has not started.
- **Next action:** convert `ingest_preceptaustin.py` to route through `shared_ingest.ingest_document(insert_mode="psycopg2_batch")`. This is its own session: real files, dry-run + single-item verification before any batch (Standing Rule 2), and — per Open Flag #1 below — real-ingest verification must run from the main/orchestrating session, not a subagent, since Rule 10's freeze blocks `executor`/`planner-reviewer` from invoking any still-unconverted script for real.

---

## This session (2026-07-13, build) — #9 loader built + proven, not yet used on real data

Three commits, kept separate per Standing Rule 7 (build separate from docs):

1. **`ffc8c81`** — precondition: threaded `db_params` through `ingest_document()`'s call to `insert_chunks_fn`, so a psycopg2-based insert mode can open a direct connection without re-deriving its own DSN. `_insert_chunks_rest` (REST mode) now accepts and ignores `db_params` — behavior unchanged, verified no other call site depended on the old signature.
2. **`fb575ae`** — built `psycopg2_batch` (replacing the `NotImplementedError` stub) + a new standalone tool, `scripts/verify_chunk_alignment.py`. `psycopg2_batch`: whole-document batch-embed + one `execute_values()` insert, one transaction, one commit, all-or-nothing per document. Client-side UUIDs preserved (no `RETURNING` remapping). Three alignment safeguards built in, not bolted on: (a) explicit length assert before `zip()`; (b) a new `_embed_batch_verified()` that checks the OpenAI response's own `item.index` against intended position instead of trusting order positionally — closes the sharpest unproven link identified in #9's diagnostic (Q3); (c) `verify_chunk_alignment.py` — recomputes a stored chunk's embedding and cosine-compares it to what's in the DB via pgvector's `<=>`, same technique used at #8. Scoped narrowly to Precept Austin's whole-doc-batch shape only — lexicon's paced/resumable sub-batching stays a separate, later need (#11/#12), not built speculatively here.
3. This doc regeneration (below).

**Part 3 — proof on a synthetic document (no real corpus touched), all checks passed:**
- Rigged both safeguards deliberately before trusting them: a fake client returning fewer items than requested correctly raised `EmbeddingAlignmentError` ("returned 2 items for 3 inputs"); a fake client with an out-of-range `item.index` correctly raised too ("item.index=8 out of range for a 3-item sub-batch"). Client restored immediately after each rig — confirmed via identity check, not assumed.
- Built a 150-paragraph synthetic document → 150 chunks (confirmed via `chunk_text()` before ingest), comfortably crossing the 100-item embed sub-batch boundary. Routed through `ingest_document(insert_mode="psycopg2_batch", allow_sentinel=True)` — landed on the sentinel source deliberately (throwaway test data, not real attribution).
- **Reconciliation:** attempted 150, `SELECT count(*)` in DB = 150. Match.
- **Alignment spot-check:** 106 chunks sampled (indices 0–105, spanning both sub-batches) via `verify_chunk_alignment.spot_check()`. Cosine similarity range 0.999993–1.0; zero below 0.999. The boundary region itself (chunk_index 95–104, split across both sub-batches) came back ~1.0 across the board — the specific failure mode this safeguard exists to catch (an off-by-one at the sub-batch boundary silently cross-pairing text and embedding) did not occur.
- **Index integrity:** zero duplicate `chunk_index` rows for the synthetic doc. Migration 061's `UNIQUE(document_id, chunk_index)` constraint was live throughout this insert and never fired — the batch insert never attempted a colliding index, so this run doesn't independently prove the constraint blocks a violation (already proven separately when the constraint was added — see below), but it does confirm `psycopg2_batch` doesn't produce one under normal operation.
- **`full_text` tripwire:** populated, length matched the synthetic body exactly — confirms the run went through `ingest_document()`, not a bypass.
- **Cleanup:** chunks, document row, and propositions (the sentinel is `unlicensed`, so `process_document()`'s gate did fire a real extraction attempt — result `no_propositions`, a valid non-error outcome for content with nothing to extract) all explicitly deleted and confirmed gone via fresh `SELECT count(*)` — zero remaining in all three tables.

**Bonus, as anticipated going in:** Standing Rule 10's freeze never fired this session — `ingest_preceptaustin.py` was never invoked, real or dry-run, so `check_rule_10_freeze()` had no occasion to act.

---

## Earlier today (2026-07-13, prior session) — live chunk-duplication cleanup + guardrail

Found during #9's read-only diagnostic scoping (the alignment-guarantee question, Q3): `chunks` had no uniqueness constraint on `(document_id, chunk_index)`, and duplicates already existed in live, `shown` data. Classified read-only first (IDENTICAL vs DIVERGENT), Alex-approved, then cleaned up: **9,168 duplicate rows removed across 186 documents** (145 Precept Austin + 1 STEPBible + 40 Derek Prince), verified zero collisions remain, then **migration `061`** added `UNIQUE(document_id, chunk_index)` so this class of corruption can no longer occur, from any script. Two commits: `d7ef162` (migration), `026baf0` (docs correction — Open Flag #3 and PLAN.md's previously-unexplained "186 documents have broken chunk_index sequences" line, both corrected in place; full detail lives there, not restated here). Root-cause remediation for the two still-live-exposed scripts (Precept Austin's excerpt-keyed skip check, STEPBible/lexicon's resume-by-count) remains #11's job — the constraint defused the symptom, not the cause.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end — every exit condition closed, all three diagnosed harness bugs closed. Commit trail: `35ae840` → `8816804` → `6379925` → `f2378a7` → `b6340d5` → `96bc3ff` → `874ba8f` → `7afc77c`. Full design history lives in CLAUDE.md's "Harness / Agentic-Loop — Gate Design Principles" section, not here.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — commit `dc39dab`.
- **#7 (`documents.full_text` chokepoint): DONE** — commit `55e46f1`.
- **#8 (convert `ingest_magazine.py`): DONE** — commit `0935697`.
- **#9 (build `psycopg2_batch`, then convert `ingest_preceptaustin.py`): PARTIALLY DONE.** Diagnostic scoping done. Loader built and proven on synthetic data (`ffc8c81`, `fb575ae`, this session). **The `ingest_preceptaustin.py` conversion itself — real files, real verification — has not started.** Do not mark #9 complete until that lands.
- **#10–#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames and the `jewish_perspectives` drop remain genuinely open, untouched.

---

## Open Flags — carried forward, none newly opened this session

1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). Denies any Bash command merely *mentioning* an unconverted script's filename, and doesn't track mid-session conversions. **Will recur at the actual #9 conversion session** (`ingest_preceptaustin.py` real-ingest verification must run from the main/orchestrating session, exempt from `GUARDED_AGENT_TYPES`, not from `executor`/`planner-reviewer`) — same as it did at #8. Known fix: switch to an invocation check, needs its own harness session.
2. **Magazine queue hard pre-ingest gate — 27 of 27 (100%) pending articles contaminated** (found at #8, 2026-07-12). No article in `sources/magazine/03_approved/` is safe to ingest for real right now. Needs its own diagnosis session.
3. **`on_existing="reuse"` PATTERN — two known holes, still open, symptom now structurally closed** (found at #7, 2026-07-12; live-exposure correction + DB-level closure 2026-07-13 — see "Earlier today" above and PLAN.md for full detail). Holes (1) unconditional re-chunk/re-insert and (2) document-row/`full_text` skipped on reuse are unchanged and unfixed — #11's remediation is still required when Precept Austin/lexicon convert. The migration `061` constraint means a violation now fails loudly instead of silently duplicating, but does not fix either script's own reuse-check logic.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). Not exercised this session — both the dedup cleanup and this session's build were done directly by the orchestrating session with explicit drift-guards and post-commit DB verification, not via the executor/planner-reviewer harness loop.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`. Its own separate session.
6. **PLAN.md #5.5 closing line is stale.** Needs Alex's explicit go-ahead on replacement wording.
7. **PLAN.md #14 drift.** Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift, last touched 2026-07-10/11 — not this session's work) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — every file this session actually created (migration `061`, `shared_ingest.py` edits, `verify_chunk_alignment.py`, this doc, PLAN.md) was committed, none left as carve-out drift.

---

## Next Session Should

Convert `ingest_preceptaustin.py` for real: route it through `shared_ingest.ingest_document(insert_mode="psycopg2_batch")`, dry-run + single-item first (Standing Rule 2), then a real batch with a hard reconciliation count (Standing Rule 3) checked against the DB. Expect Rule 10's freeze to block any real-ingest verification attempted from a subagent (flag 1 above) — same main-session workaround as #8. Once that conversion lands and is verified, #9 is actually done — update this file and PLAN.md accordingly, not before. Everything in "Open Flags" is carried forward untouched; each needs its own scoped session when picked up.
