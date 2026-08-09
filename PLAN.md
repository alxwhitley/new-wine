# Rhemata — Master Plan (v6.0 · lean/phased)

> **Chat-authored, terminal-committed.** Chat proposes roadmap changes; terminal
> is the sole committer of this file (same propose→commit pattern as any other
> repo edit) — see CLAUDE.md's Project Knowledge Read Contract. `rhemata-status.md`
> pulls its "Where We Are" one-liners from here. **When this doc and reality
> diverge, update this doc.**
>
> **v6.0 restructure (2026-08-07):** v5.33 (694 lines, ~75k tokens) had every
> shipped item's full build narrative and the entire version-history changelog
> live in the same file as the active roadmap — a "what's next" query loaded
> ~16k tokens of pure history it never needed. Per Standing Rule 14's own
> "closed items collapse to one line, detail lives elsewhere" discipline, the
> full v5.33 file (history, done-item narratives, resolved decisions, killed
> items) moved verbatim to **`docs/plan-archive.md`**. This file now holds only
> the active roadmap, pending decisions, and a terse Done ledger. **No content
> was deleted** — everything from v5.33 is either restated here (active items)
> or preserved verbatim in the archive (history/detail). If a status below
> looks thin, the reasoning trail is one file away.

---

## Read map — read only the section you need

| You're asking... | Read this | Skip |
|---|---|---|
| "What's next / what's left before backend-complete?" | **§ Active Phases** below | Done ledger, archive, Horizon |
| "Is X decided yet? What's the default?" | **§ Open Decisions** | archive (unless resolved) |
| "How do I run a session here?" | **§ Standing session rules** | everything else |
| "Has X already shipped?" | **§ Done ledger** (terse one-liners) | archive (unless you need *why*) |
| "Future features not yet scheduled?" | **§ Horizon / Backlog** | Active Phases (do not treat as current work) |
| "Why was X decided that way / what actually happened in that session?" | **`docs/plan-archive.md`** | — |
| "What got killed / superseded and why?" | **`docs/plan-archive.md`**'s Superseded/killed section | — |

**Parallelism legend** (used throughout § Active Phases):
- `[∥ safe]` — no shared files/state with its phase-siblings; can run concurrently.
- `[seq: after <item>]` — hard dependency; must follow the named item.
- No tag — sequential within its phase by default, no cross-item hazard flagged.

---

## Standing session rules

1. Read-only diagnostics confirmed by Alex before any build prompt runs.
2. Dry-run + single-item verification before any full batch.
3. **Every batch/backfill ends with a hard reconciliation count** — attempted / stored / errored / skipped, checked against the DB. A "success" with no count is not a success.
4. Long jobs: `nohup` + timestamped logs, `tail -f`.
5. Git from repo root, never `~`. Repo root is `/Users/alexwhitley/rhemata`.
6. `CLAUDE.md`/`SKILL.md` updated only after a build is confirmed working.
7. Two isolated commits: build separate from docs. No bundling — own-session items stay own-session.
8. Prompts written fresh each session against the current codebase.
9. **RESOLVED 2026-08-08 — the ingest chokepoint freeze is lifted.** Phase 5 #13 (`ingest_helloao.py`) was the last unconverted document-writing ingest script (ARCHITECTURE.md's Scripts table); it now routes through `shared_ingest` (commit `929bc34`). The YouTube/Sermonindex path was already fully converted and was never affected.
10. **Answers paraphrase and cite; they never quote freely.** Permanent product posture — verbatim text reaches users only through the verified-quotes component (Project 3 / quote rail). This is an accuracy posture, not a copyright-permission gate: nothing inspects the token stream, so nothing can guarantee a model-emitted "quote" is real or correctly attributed. Only the verified-quotes-table architecture delivers "cannot," because it removes quote generation from the model entirely. Full reasoning + the B5 enforceable-claim correction: archive.
11. **Shipping a fix includes correcting the record in the same session.** Code and its description move together, never staggered to a cleanup pass.
12. **A human blind-read pass does not reliably catch generation-output leakage.** The review method proven to catch it is a NON-blind, side-by-side read (answer next to its own evidence rows) — see Open Decision #20.
13. **Closing a roadmap item replaces its entry — it never gets another paragraph stacked on top.** Collapse to `DONE — <one line> (commit <hash> / docs/audits/<file>)`; full reasoning lives in the commit/audit doc and, for anything pre-v6.0, in `docs/plan-archive.md`.
14. **xAI Grok for mechanical, non-reasoning subtasks.** For bulk text reformatting, sorting/compacting grep or log output, terse first-pass summaries, changelog compaction, and plain string transforms — prefer delegating to **xAI Grok** (fast, non-reasoning) over the session's reasoning model, to go faster and cheaper. **Do NOT use Grok for:** anything on the answer-accuracy/retrieval/generation path, anything touching theological correctness, any DB-write decision, or any judgment call this repo's failure history flags (see CLAUDE.md's Ranked Failure Modes). Reasoning model when correctness matters; Grok when it's pure mechanical throughput. **Not yet wired as of 2026-08-07** — confirm the exact xAI Grok model id and how a session invokes it (subagent/tool/API access) before relying on this in practice; until then this rule states intent, not a working path. Distinct from **Groq** (`llama-3.3-70b-versatile`), already in the stack for query expansion/tagging/transcript cleaning — different vendor, do not conflate.

---

## Active Phases — toward "backend/infra complete, ingestion-only"

Ordering below is the recommended sequence. The **Ongoing** track (bottom) runs
in parallel with all six phases and is *not* a blocker for declaring
backend-complete — it's the steady state the milestone unlocks. Statuses were
re-verified against the live DB/repo through 2026-08-07 (v5.33), with a
2026-08-07 mechanical pass (T2 status-check + Railway pooler + Phase 1.3
inventory) folded in below; re-check anything load-bearing before acting on
it if this file is more than a few sessions stale.

### Phase 1 — Async cutover hardening
Async path (`answer_jobs` queue + worker) is confirmed serving 100% of live
traffic (`async_answer_config.serving_enabled = TRUE`, set 2026-08-06).
`chat.py` no longer exists.
- **DONE (2026-08-07)** — the `producer.py`/`chat.py` mirror is deleted, not just unified: `chat.py` itself is gone (commits `4557e5c` toolbox extraction, `e223c98` chat.py deletion + fallback removal). Shared leaf functions moved to `answer_toolbox.py`; metering consolidated to one function; the frontend's silent fallback-on-failure removed entirely (Alex's explicit decision — a failure surfaces as a real, visible error, never a silent handoff to a second path); `async_answer_config.serving_enabled` recharacterized as an honest emergency pause, not a rollback (nothing left to roll back to). Full detail: CLAUDE.md's Project 1 landmine.
- **DONE (2026-08-07)** — worker `SUPABASE_DB_URL` is transaction pooler **:6543** (Railway `answer-worker` + `rhemata` backend both confirmed via `railway variables`; host `aws-1-us-east-1.pooler.supabase.com`). Local `backend/app/.env` remains :5432 (session) for dev only — not the production residual. Remaining scale item is a real concurrency window at the 100-dial, not pooler misconfig.
- Latency — generation still ~50s. **Target corrected 2026-08-08 (Open Decision #17 resolved): 20s, not 7s** — the 7s figure was unrealistic for a checked answer (verification is inherently slower than raw generation); this was the only live occurrence of the 7s figure in the repo, now replaced. **Hold on speed investment until the 100-dial concurrency load test is complete** — correctness is proven, concurrency is not. **No owner.** Independent strand, doesn't block the items above.
- `[∥ safe]` Core-serving safety gate (#15) still not closeable: Supabase project-level backup/PITR status is genuinely unknown (no Management API credential available in this environment); no staging Supabase project exists; full-project disaster-restore unproven. Record-level restore *is* proven (2026-07-24).

### Phase 2 — Answer-quality / safety guards
Ranked Failure Mode 1 territory (theologically wrong / misattributed answers) — highest-priority category per CLAUDE.md.
- `[∥ safe]` **Phase 1.3** (from the 2026-08-01 accuracy sequence): reverse hidden-by-default + inventory (Settled Decision #12, CLAUDE.md). **Inventory DONE 2026-08-07 (read-only, no flip)** — live counts: owned/shown 2, public_domain/shown 28, unlicensed/shown 29, unlicensed/hidden **14**. Schema `sources.visibility` DEFAULT still `'hidden'`; registration scripts still fail-closed to hidden. Of the 14 hidden: **Ravenhill** (117 docs / 767 eligible props), **Savchuk** (126 / 983), **Poonen** (50 / 411) hold nearly all content; **sentinel** "Unassigned — needs source" (2 docs) must stay hidden (Invariant 3); 10 empty shells (0 docs). All 14 have `retrievable=false` but the live license gate keys on visibility+license, not `retrievable` — a visibility flip alone would open those three teachers under `safe_mode=off`. **The policy is already settled** (CLAUDE.md Settled decision #12, 2026-08-01: hidden-by-default reverses; new material defaults visible; everything currently hidden becomes visible eventually — "buys time, not a pass"). **Corrected 2026-08-08 — what's still genuinely open is narrower than "whether": which subset to flip first (never sentinel) and the mechanical execution** (schema default + script defaults + the actual visibility-bit change on the 14 rows), none of which has happened yet. Alex's call is on subset/timing, not on whether the reversal happens at all.
- **RESOLVED 2026-08-07** — Precept Austin "citable author" leak (found 2026-08-07, fixed same day, Alex's go-ahead): `is_commentary_chunk()` in `answer_toolbox.py` now treats `source_kind="word_study"` as commentary-equivalent, same hard exclusion as `"commentary"` (Precept Austin is the only `word_study` source, so this closes all of it). Live-confirmed before/after: an ordinary question went from 33/67 retrieved chunks being Precept Austin to 0. Full detail: CLAUDE.md's Landmines section. **Still separately unbuilt, not touched by this fix:** the word-study lookup panel (surfacing Precept Austin content when a user clicks a Greek/Hebrew word) — a different surface, scoped for later.
- **Open Decision #20** — generation-output verification guard. 5 attempts have failed to separate true-negative near-misses from true-positive answers; accepted-for-now gap. Do not attempt a 6th automated variant without first running the queued read-only diagnostic (false-flag rate of the existing direct-contact check against known-good positions).
- Phase 2.4 (numbers/absolutes check) — **HELD**, unusable as prototyped (100% false positives). Phase 3 (continuous measurement) — **not started**.
- Open Decision #18 — system-prompt review timing (not decided; natural fit here since the 3-answer-source design changes prompt shape).

### Phase 3 — Position layer decision (durable stored positions)
Explicitly **deferred** pending real usage; corpus-wide ban stays lifted but nothing is being built on it. Largely sequential — gated on decisions before build work is meaningful:
1. Open Decision #13 — **RESOLVED 2026-08-08**: no override mechanism; `DOMINANCE_THRESHOLD=0.60` stays as-is, near-boundary cases logged for later review. See CLAUDE.md Settled decision #20.
2. Open Decision #14 — **RESOLVED 2026-08-08**: automatic scheduled re-check; only meaningful shifts escalate, via a new admin-panel notification (surface not yet built — see Horizon item 4's dependency). See CLAUDE.md Settled decision #21.
3. Open Decision #15 — **RESOLVED 2026-08-08**: versioning, not replace — closes the open question in favor of the behavior `_insert_position_version()` already implements. See CLAUDE.md Settled decision #22.
4. Open Decision #16 — topic list: **V1 adopted** 2026-08-06/07 (6 topics, seed only — fasting, deliverance, prayer, divine exchange, losing salvation, holiness). Unblocks but does not build the matcher.
5. **DONE (2026-08-08)** — matcher (`match_stored_position()`, 2026-08-07) + evidence-injection wiring (`backend/app/services/stored_position_evidence.py` + `producer.py`'s `produce()`, commit `eca8070`) both built: on a match, the position's underlying PROPOSITIONS (never rendered text) replace normal retrieval's chunk set, then run through the unchanged generation/verification/citation pipeline — the accepted one-hop design (CLAUDE.md Settled decision #18), not the two-hop shape rejected 2026-08-04. Live license/visibility gate + commentary exclusion re-applied per evidence proposition at serve time (`position_evidence` was only gate-filtered at build time). A build-time bug was found and fixed during verification: the position lookup originally required `requested_teacher_id IS NULL`, silently missing 4 of the 6 seeded positions (built via teacher-explicit asks, not topic-only ones) — corrected to look up by `topic_key` alone. **Verified end-to-end with real generation across all six OD #16 V1 topics — zero stored-position-text leakage into any served answer.** 3 of 6 (fasting, deliverance from demons and spiritual warfare, how to pray effectively) currently no-op to normal RAG because their sole evidence source, Vlad Savchuk, is still hidden — see Phase 2's Phase 1.3 entry above — expected, not a gap, activates automatically once he's unhidden, no further code change needed. **Status: built, locally committed (`eca8070` build / `34f6b0b` docs), NOT pushed to origin.** `producer.py` is the live answer path serving 100% of traffic — pushing deploys this immediately. Push is Alex's call, not yet given. Still open, out of this build's scope: production concurrency/rollout under real load.

### Phase 4 — Quote rail curation
Project 3 (schema + verifier + selection + frontend) is built and live on the answer path (originally async-only by deliberate decision; `chat.py`'s deletion 2026-08-07 makes this moot -- there's only one path now, and it always runs quote selection). All items below `[∥ safe]` — independent surfaces:
- Calibrate `QUOTE_TOPIC_SIMILARITY_THRESHOLD` (currently 0.40, provisional) against real traffic.
- **DONE (2026-08-08)** — Sub-chunk exclusion mechanism for embedded non-teacher text sharing a chunk with real teacher material (commits `ca984cb` build, `c0c34c7` docs). Implemented in `backend/app/services/quote_subchunk_exclusion.py` and wired into `quote_verifier.py` as a `subchunk_exclusion` rule; covers translator footnotes, `:—`/`writes:` block quotations, Heidelberg/directory catechism Q&A, and inline Müller quotations in the George Müller chapter. Regression tests in `scripts/test_quote_verifier.py` cases 14–25 pass; dry-run in `scripts/dry_run_subchunk_exclusion.py`. Residual gaps (cross-chunk catechism continuation, `:—`/`writes:` false-exclusion risk) and full reasoning live in the commit messages and dry-run output.
- **Curation rescoped 2026-08-08 (Alex's decision — records-only; no pipeline, detector, or flagging code touched).** Quote extraction from ALL book-type source documents (`source_type='book'`, all 53 book documents — including all 10 Andrew Murray books and Doug Kreighbaum's 4 books) is **tabled indefinitely**. Reason: `docs/audits/book_structure_diagnostic.md` (read-only, run 2026-08-08) found no body/apparatus or chapter-boundary structure exists anywhere in the schema for books — a book is a flat chunk run; `quote_ineligible_reason` covers only 66 of 25,064 book chunks across 10 of 53 documents (all Andrew Murray); the one existing chapter detector (`detect_book_chapters()`) is unwired with two documented, unfixed accuracy regressions (CLAUDE.md's book-length-extraction Landmine; Open Decision #21). Whether/how to build proper boundary detection for books is now a separate future decision, explicitly not blocking anything else.
  **Follow-on (2026-08-08/09, read-only, not applied):** human-reviewable chapter-boundary proposals for the 18 HIGH-confidence books from the full survey live at `~/rhemata-analysis/chapter_boundary_proposals_2026-08-08.md` (per-book front/back matter + exclusive start/end chunk indices). Survey ground truth: `~/rhemata-analysis/book_structure_survey_2026-08-08.md`. Ryle *Holiness* Ch. XXI (“Extracts from Old Writers”) held from that batch — attribution check (`~/rhemata-analysis/ryle_ch21_attribution_check_2026-08-08.md`) found exactly two credited extracts (Robert Trail/Traill; Thomas Brooks), zero uncredited; same-day follow-up registered both as hidden one-off sources (see rhemata-status.md). **Does not resolve Open Decision #21** and does not wire any detector.
  **Consequence: Andrew Murray drops out of active curation scope entirely.** Live-DB-confirmed 2026-08-08 (`rhemata_readonly_analysis` role, SELECT-only): all 10 of his documents are book-type; zero non-book material exists to curate from. The session's original 2-teacher seed (Murray, Prince) is no longer the target.
  **Rescoped target: Derek Prince plus all other currently-visible non-book teachers** (`source_type != 'book'` — sermon/transcript/paper/magazine material), expanding past the original 2-teacher seed toward the existing 50–100 first-pass approved-quote target (`docs/plan-archive.md`). Live-DB-confirmed 2026-08-08 non-book document counts by currently-**shown** teacher (excluding Precept Austin — permanently excluded from the quote pipeline regardless of book/non-book status — and excluding pure-commentary sources, out of scope for quotes under the standing commentary-exclusion rule): **Derek Prince 496** (491 sermon + 5 magazine_article — by far the deepest bench), New Wine Magazine 15, CLF Church 14, Daniel Kolenda 11, Jack Deere 6, Carter Conlon 6, **Doug Kreighbaum 5** (1 manual + 3 papers + 1 sermon — his 4 *books* stay tabled under the exclusion above), Charles Simpson 4, Bob Mumford 4, Michael Brown 2, Ruth Prince 2, Ern Baxter 2, Don Basham 2, Oswald J. Smith 1. Currently-**hidden** teachers with non-book material also exist (Vlad Savchuk 126, Leonard Ravenhill 117, Zac Poonen 50) but curating them now would be wasted work while hidden (Phase 1.3/Settled Decision #12 above) — the same reasoning Alex already gave for prioritizing Prince first.
  **DONE (2026-08-09) — Derek Prince non-book candidate extraction to pending.** 250 verified candidates inserted as `status='pending'` across 249 of 496 documents (491 sermon + 5 magazine_article). Used the existing `quote_verifier` checks unchanged; migration 086 added `'pending'` to `quotes.status`. The remaining 247 Prince docs were not attempted because the 250-quote ceiling was reached. Log: `logs/extract_prince_20260809_080948.log`.
  **Next curation step:** a separate review session to flip selected pending rows to `approved` (requires `document_quote_clearance` per source document; approved rows are still blocked by the DB approval gates).
- *(Superseded from the old #21–25 quote-track numbering: #21/#22 table+verifier are done, folded into Project 3; #23 serving-gate is functionally superseded by the async resolution point; #24 AI-suggested extraction and #25 whole-corpus backfill stay explicitly deferred, B3.)*

### Phase 5 — Chokepoint code gaps
Pipeline-code items, not corpus content — these gate specific *future* ingestion paths, not corpus growth generally.
- `[∥ safe]` **#7** — `documents.full_text` backfill for pre-chokepoint docs (chunks-only today; every doc ingested since #7 shipped already gets it). Live gap ~3,539 missing / 56 present as of 2026-08-07 probe (not a fixed number — re-query before acting).
- **#9 / #12 DONE** (status-check 2026-08-07; PLAN had listed both open — stale). Both scripts call `shared_ingest.ingest_document()` for real (not comments-only). **#9** `ingest_preceptaustin.py` — convert commit `c678514`, closed `f128ddd`. **#12** `ingest_lexicon.py` — convert commit `33e92b4`, closed `512a47d` (+ slice-runner `dd609fb`). ARCHITECTURE already lists both under "Routed through shared_ingest." **`psycopg2_batch` as a named insert_mode** was built (`fb575ae`) then **retired** by the all-or-nothing writer (`6708060`) — no `psycopg2_batch` / `_INSERT_MODES` in `shared_ingest.py` today; `_insert_chunks` is the single path. Do not rebuild #9/#12.
- **#13 DONE (2026-08-08)** — `ingest_helloao.py` converted to `shared_ingest.ingest_document()` (commit `929bc34`), mirroring #9/#12's pattern; a chunk_fn override keeps its one-chunk-per-verse formatting. Verified: `--dry-run` (new flag, zero Supabase reads/writes) against the live API; a real single-item write through the full path (isolated throwaway title, independently confirmed in the DB, then deleted); a full unfiltered batch (attempted=198 stored=0 skipped=198 failed=0), reconciled against the live DB (186 HelloAO documents unchanged, no stray rows). The 0-stored result corrects Ongoing #27's stale "8 further, content ready" — see that entry.
- `[∥ safe]` **#14 rename portion DONE** — `sources/lexicon/` → `sources/stepbible/` and `sources/documents/` → `sources/inbox/`; call sites updated in 5 scripts + `ARCHITECTURE.md` tree (commit `37fbc08`). Local directories renamed; push deployed live. **Drop `jewish_perspectives` still OPEN** — table still has 2 rows, zero runtime refs; requires Alex's explicit call and a separate DB-write session to apply draft migration 084.
- `[∥ safe]` **#16** — feedback→flag-proposition path + dry-run backfill on one genre. **Still OPEN** (2026-08-07 status-check): `POST /feedback` only stores thumbs up/down; no proposition id, no `eligible` flip, no auto path from user feedback into the propositions layer. Manual eligibility scripts only. Keep or kill is Alex's call — not urgent vs. the position matcher. **Broader product intent** (feedback → actionable content flag, same shape as corpus-contamination flagging; needs real design first) captured 2026-08-08 under **§ Horizon / Backlog item 3** — not a second open task.

**Status-check resolved 2026-08-07** (old T2-track items that had no DONE marker; full original scope in archive):
- **#3** DONE — chokepoint verified live 2026-07-10 (`4c843a0`); `ingest.py` → `shared_ingest` still the path.
- **#5** DONE — landing rewrite `f4642bc` (+ later copy passes).
- **#18** SUPERSEDED — license gate on `match_chunks`/`search_chunks_fts` + 5 other RPCs shipped (migrations 047/049/056); live path fuses vector+FTS with collapse/rerank. "Propositions into match_chunks" never shipped; props stay on the position layer. Do not rebuild under old scope.
- **#19** DONE / superseded by SP1/SP2 + `SourcePanel` (citations open source cards).
- **#20** MOSTLY SUPERSEDED — prompt/citation/study-notes shipped via later work; residual never closed under this number: library Full-text/synthesis indicator (spin out only if still wanted).

### Phase 6 — Pre-public-tier gate (#32–37)
The real Tier 1→Tier 2 launch checkpoint (Open Decision #5) — triggers once beta exceeds ~20 users or signups open. Explicitly **NOT near-term**, listed here so it isn't lost. Mostly `[∥ safe]` (independent legal/UI surfaces):
- #32 STEPBible CC-BY-NC audit — status not recently confirmed, recheck.
- #33 openbible.info attribution surface — not built (STEPBible half is done; no cross-ref UI exists yet to attribute against).
- #34 SermonIndex visibility audit — open, 6 "shown" sources need resolving before public serving.
- #35 DMCA agent + takedown procedure — not started (~$6 estimated cost).
- #36 Guest-limit hardening — not started, needs a coverage check.
- #37 Admin remainder (contributor activity view, pending-count badge, delete endpoint, mobile drawer) — not started.

### Other active track — Inline Study Panel (SP) residuals
Track is decision-complete and ~90% shipped; only these remain, all `[∥ safe]`:
- **#38 DONE** — mobile bottom-sheet source panel shipped with grab handle + swipe-to-close, following the study panel #43 pattern; verified at mobile width via Playwright (commit `c37200e`).
- #42.5 Phase 2 (floating overlay v3) — built but only verified against local-dev doubles; a full authenticated production pass is still owed.
- #43 — swipe-to-close shipped; full drag-to-follow-with-peek is NOT shipped (deliberately reduced scope). Whether the reduced scope is final is **Alex's decision, not yet made.**

---

## Ongoing (non-blocking) — Corpus ingestion

Runs in parallel with every phase above. **Not a blocker for declaring
backend/infra complete** — this is the steady state that milestone unlocks.

- **#26 New Wine** — 167 raw PDFs still untouched (9 already ingested via the already-converted `ingest_magazine.py`).
- **#27 HelloAO PD commentaries — CORRECTED 2026-08-08, not code-blocked, not content-ready.** Phase 5 #13's conversion is done; a full unfiltered batch run against the live API found the corpus's 12 previously-missing HelloAO book/commentary combinations (1 Matthew Henry, 10 Adam Clarke, 1 Jamieson-Fausset-Brown — all `Song of Solomon`, plus a scattered Adam Clarke set: Deuteronomy, Judges, Psalms, Proverbs, Ecclesiastes, Jeremiah, Joel, Malachi, Matthew) have no verse-level commentary at the HelloAO API for those specific books: either a 404, or content that exists only under a chapter-level `introduction` field this script has never parsed (confirmed live, e.g. Adam Clarke's Song of Solomon: `chapter.content` is an empty list every chapter, `chapter.introduction` holds real prose instead). The stale "8 further, content ready" figure predates this check. Not scheduled: reading `chapter.introduction` would need new parsing/chunking logic (a chapter-level entry has no verse number to key a chunk on) — a separate scoping question, not a code-gate.
- **#28 Reference datasets** (openbible.info cross-refs, Strong's, TIPNR, etc.) — each needs a new script; not started.
- **#29 PD books + Pentecostal archives** — not started; some titles gated by Open Decision #3 (verify PD status per title — the PD line advances every Jan 1).
- **#30/#31 Phase 3 "differentiator"** (owned verse-anchored synthesis pipeline) — design stage is "???"; not started; sized only after #27/#29 land more PD material.

---

## Open Decisions — pending only

*(Resolved decisions — #6 file location, #7 full_text-at-chokepoint, #8 commentaries atomicity, #9 skip-check/#11 overlap (merged, 2026-08-08), #12 ingest_commentaries retire, #13 position scope-boundary ownership (2026-08-08, CLAUDE.md Settled decision #20), #14 refresh trigger (2026-08-08, CLAUDE.md Settled decision #21), #15 rebuilt-position version history (2026-08-08, CLAUDE.md Settled decision #22), #17 answer-speed target (20s, 2026-08-08 — see Phase 1 latency item), #22 the two live-DB imperfections — #6/#7/#8/#12/#22 moved to `docs/plan-archive.md` (one-line pointer only); #9/#13/#14/#15/#17 resolved 2026-08-08, reasoning lives in CLAUDE.md/Phase 3/Phase 1 as cross-referenced, not archived. #10 (below) is a DIFFERENT question from CLAUDE.md Settled decision #26's 2026-08-08 word-study *reintroduction* initiative — #10 is about rewriting/modernizing word-study content, still genuinely undecided.)*

| # | Decision | Current default / state |
|---|---|---|
| 1 | Cold storage vs. visibility gate | Gate canonical; deletion parked as final hardening |
| 2 | Quote serving flip rule (stream-level verbatim quotes) | Stays OFF — superseded in relevance by Project 3's separate async resolution point, which doesn't touch this flag |
| 3 | Near-1930 PD verification (Lake, Brengle, Penn-Lewis, Morgan, Wigglesworth 1924) | Alex checks pub date per title; PD line advances every Jan 1 |
| 4 | Admin shell: modal or sidebar | Keep modal |
| 5 | **Risk tier — Tier 1→2 gate.** | You are Tier 1 (≤20 private beta). Signup opening or exceeding ~20 users triggers Tier 2 → Phase 6 (#32–37) + Phase 1 (serving rebuild) + quote verifier (now done, Project 3) all required first |
| 10 | Precept Austin word-study **rewrite** (distinct from the 2026-08-08 retrieval-*reintroduction* initiative, CLAUDE.md Settled decision #26 / Horizon item 7) | Deferred, not decided — high meaning-drift risk on word studies specifically |
| 11 | Hebrew lexicon permission gate (TBESH) | Blocked pending Online Bible's permission; Greek (TBESG/TFLSJ, CC BY 4.0) unaffected |
| 16 | Ahead-of-time position topic list | **V1 adopted** 2026-08-06/07 — see Phase 3 |
| 18 | System-prompt review timing | Not decided — see Phase 2 |
| 19 | Commentary archaic-voice fix | Not decided — holding on in-flight licensing conversations |
| 20 | Generation-output verification guard | Open, accepted-for-now — see Phase 2 |
| 21 | Numeral-heading chapter detector — harden/wire or leave inert | Not decided — built, zero production callers, two prior guard-patch attempts each surfaced a new regression. **2026-08-08/09:** human-reviewed chapter-boundary *proposals* for the 18 HIGH books exist at `~/rhemata-analysis/chapter_boundary_proposals_2026-08-08.md` (proposal only; nothing applied; does not close this decision) |

Full reasoning for every row (including resolved ones): `docs/plan-archive.md`.

---

## Horizon / Backlog — not scheduled (captured 2026-08-08)

**Not active work. Not scoped. Not sequenced into Active Phases.** Captured
for the record so these do not get lost; do not start any of them without
Alex bringing the item back and defining scope. Distinct from § Ongoing
(corpus ingestion that already runs in parallel) and from Phase 6 (Tier 2
launch gate — also not near-term, but a known checkpoint with numbered
items).

### 1. Full rebrand and UI redesign — held until product Phase 2

The product rename (Rhemata → Manna) is **now formally settled and recorded**
(CLAUDE.md Settled decision #25, 2026-08-08 — naming decision only, no code/
repo/domain/identifier changes in scope from that decision alone). Once its
actual implementation across the product is scoped separately, Alex wants
a full visual identity and UI redesign built around Manna, **built directly
in the app via Claude Code**, not designed first in Framer.

**Two-phase framing (not a schedule):** Alex sees the project in two product
phases. **Phase 1** (current) is finishing architecture and infrastructure so
ingesting new material works correctly and reliably by default. **Phase 2**
begins once Phase 1 is essentially done and Alex is mainly in
content-ingestion mode — the rebrand and UI redesign happens in Phase 2, as
the last major project before opening the product to test users. The exact
trigger for moving into Phase 2 is **not phase-boundary-defined yet**; Alex
will define it in a future session. Record this as framing only, not as a
scheduled task.

### 2. Commentary enrichment — three-part future feature

Today Study Mode commentary cards show only public-domain commentary text
as-is. Future richer resource, three parts — hold the whole feature; do not
scope further until Alex brings it back.

- **Part A — quote-to-verse linking.** Approved quotes that clearly reference
  a specific verse (thematic connection is enough — an explicit verse
  citation is not required) should also surface on that verse's own
  commentary card, not just in chat answers. A quote can link to more than
  one verse if it genuinely touches more than one. A quote does **not** need
  to be linked to any verse to exist — quotes can stand alone or attach only
  to a teaching position. Verse-linking is an additional discoverability
  layer, not a requirement. **Mechanically:** scripture-reference flagging
  should happen during ingestion (mark places in source material where a
  specific verse is being discussed); quote extraction should then work
  outward from those flagged locations (strong quotable material near a
  flagged verse reference) rather than extracting quotes blind and matching
  them to verses afterward.
- **Part B — commentary rewriting for clarity.** Many public-domain
  commentaries are archaic. Rewrite for readability — modernize language and
  sentence structure only. Explicitly **not** a rewrite of the underlying
  argument or claims: substance stays exactly as the original author wrote
  it; only phrasing changes. Related pending decision: Open Decision #19
  (commentary archaic-voice fix) is still open under a different frame
  (licensing conversations); this Horizon item states the PD case has no
  copyright/derivative-work blocker — see Part C for the real risk.
- **Part C — review before build.** Because these commentaries are confirmed
  public domain (unlike the Precept Austin situation recorded elsewhere),
  there is no copyright/derivative-work blocker — PD material can be freely
  rewritten. The real risk is accuracy and trust: modernized language must
  not drift from or soften what the original author meant. Needs a real
  quality-review design before Part B is built — faithfulness review, not
  legal review.

### 3. Feedback-to-flag connection — needs real design

**Current state (do not re-describe as missing):** thumbs-up/down feedback
already exists on chat answers (and related surfaces report into the admin
panel). Phase 5 **#16** already tracks the live gap accurately: `POST
/feedback` stores ratings only — no proposition id, no `eligible` flip, no
auto path into the propositions layer. Manual eligibility scripts only.

**What does not exist yet:** a connection from user feedback into the actual
content-flagging and correction system, so a thumbs-down becomes an
actionable flag tied to that content — same shape as existing
corpus-contamination flagging — rather than sitting in a feedback table for
manual review only. Needs real design in a future session before build.
**Not a second open task** — this is the fuller product intent behind #16;
keep/kill of #16 remains Alex's call. Hold here as backlog needing design.

### 4. Search analytics + corpus-gap flagging — future admin panel feature

Two connected pieces, both opt-in dependent. Hold in backlog, not scoped.

- **Consent first.** Before any of this can be built, users must be able to
  opt in to letting the app see their question history and search terms.
  Not built by default — requires explicit permission from each user.
- **Part A — topic analytics.** For users who opt in, the admin panel should
  show a percentage breakdown of what topics/questions are actually being
  asked, so Alex can see real user demand rather than guessing what corpus
  material or position papers to prioritize.
- **Part B — honesty-gap flagging.** When the app's honest-empty behavior
  triggers (not enough material to answer confidently, and it says so rather
  than guessing), that event should be flagged and surfaced as a
  notification in the admin panel, showing exactly what was searched —
  demand *and* where the corpus currently fails to deliver.

**Dependency:** Part B depends on an admin-panel notification surface.
Closest live entry is Open Decision #14 (position refresh trigger, leaning
flag-and-approve) — that work **implies** a notification/review surface but
PLAN does **not** yet name a standalone "admin notification system" build
item. Dependency is real and under-specified until that surface is designed.

### 5. Suggested follow-up questions — future feature

At the end of an answer, the app should sometimes offer genuinely specific,
pre-thought-out follow-up questions related to the topic just answered — not
generic "want to know more?" prompts. Example: after baptism of the Holy
Spirit, offer something like "see Bible verses related to this" or "learn
whether tongues is necessary to receive it." Goal: lower effort for someone
who does not know what to ask next by anticipating natural next questions.
Hold in backlog, not scoped.

### 6. Long-conversation nudge and cutoff — future feature

**Concern:** users who never start a new chat keep building a long
conversation, increasing API cost and degrading performance without
realizing it.

**Desired behaviour:** after a conversation reaches a certain length,
gently suggest starting a new session, and offer a one-click option to
generate a summary of the current session that carries into a fresh one
(similar to other chat products). First two times the trigger fires in a
session: soft nudge only. Third time: hard stop — the user is prevented
from continuing to type in that conversation, not just nudged.

Needs real scoping (length/token trigger; how summary generation and
hand-off work) before it is buildable. Hold in backlog.

### 7. Precept Austin word-study reintroduction — future initiative (added 2026-08-08)

Precept Austin word-study material stays hard-excluded from answers today
(2026-08-07 fix, CLAUDE.md Landmines) — that exclusion is not weakened by
this item. Alex decided 2026-08-08 (CLAUDE.md Settled decision #26) that
the exclusion is not permanent: find a reliable, trustworthy method of
reintroducing word-study content into answers without meaning drift. Needs
real scoping before any work happens; not scheduled. Distinct from Open
Decision #10 (PA word-study *rewrite*/modernization — a different, still
separately undecided question). Does **not** touch PA's separate, permanent
exclusion from the quote pipeline or from paraphrase generation.

---

## Done ledger

Terse pointer only — full build/decision narrative for every item lives in
`docs/plan-archive.md` (search the item's number or name there).

- **#1** Backup `sources/`+`ingest_queue.xlsx` to Google Drive (2026-07-19). Restore itself untested.
- **#1.5 / #2** Chokepoint working-tree commit + honesty fix (stream-quote claim corrected everywhere incl. `/sources`) — 2026-07-10/17.
- **#3** Chokepoint conversion verified on real item (WORKING WITH CAVEATS) — 2026-07-10, `4c843a0`.
- **#4** Resend transactional email — 2026-07-10, delivery proven.
- **#5** Landing page copy rewrite (cut Discover section, anti-flattening hook, quote posture) — `f4642bc` + later home copy passes.
- **#5.5** Harness tool-invocation ground truth (`guard_pretooluse.py` record-primary gate) — 2026-07-12.
- **#6** Aliases + sentinel cleanup + strict mode — 2026-07-11/14.
- **#8** Convert `ingest_magazine.py`.
- **#9** Convert `ingest_preceptaustin.py` through `shared_ingest` — `c678514` / closed `f128ddd` (status-check reconfirmed 2026-08-07). Named `psycopg2_batch` insert_mode later retired by all-or-nothing writer.
- **#10** `ingest_commentaries.py` retired (not rebuilt) — 2026-07-22.
- **#10.5** Ingest integrity track (paraphrase-failure honesty, broken-doc cleanup, all-or-nothing writer) — 2026-07-13.
- **#11** `on_existing="reuse"` chunk-dedup mechanism — 2026-07-14.
- **#12** Convert `ingest_lexicon.py` through `shared_ingest` — `33e92b4` / closed `512a47d` (status-check reconfirmed 2026-08-07); slice-runner `dd609fb`.
- **#17 / #49** Full propositions backfill — closed 2026-08-02, 850/857 eligible docs.
- **#40 / SP2** Inline Study Panel frontend, all 10 phases — 2026-07-17.
- **#41** SP3 tool rows — dissolved into SP2, translations/cross-refs cut entirely.
- **#42** SP4 teacher card content gate — cleared.
- **#42.5 Phase 1** Reference persistence — 2026-07-23, live-verified on production.
- **#45 / #45.5–47** Closeness check retired; citation-fabrication scanner/verifier work; human calibration (24/24 blind) — 2026-07-28/30.
- **#45.8** Bypass-proof grounded-extraction generator rebuild — 2026-07-29/30.
- **#48 (single-voice half)** → shipped as **Project 2** (see Phase 2's dependencies above; retrieval lock is built+wired but currently inert, tracked live not archived).
- **#50** Chapter-scoped book extraction (7 public-domain books, safe repeated-title detector) — 2026-08-01.
- **#18** Serving-rule RPC build — **SUPERSEDED** (gate + chunk RRF path live; prop-into-RPC design never built; do not rebuild) — status-check 2026-08-07.
- **#19** Perplexity-style source links — DONE via SP1/SP2 + `SourcePanel`.
- **#20** Serving experience pass — **MOSTLY SUPERSEDED** by SP1/SP2/prompt evolution; optional residual = library Full-text/synthesis indicator only.
- **Project 1** Async answer execution — architecture built, deployed, traffic switch confirmed ON 2026-08-06 (residuals tracked live in Phase 1). Worker pooler residual **closed 2026-08-07** (`SUPABASE_DB_URL` :6543 on Railway `answer-worker` + backend).
- **Project 3** Quote rail (schema, verifier, admin review, frontend `QuoteRail`) — built + live-verified 2026-08-06/07 (curation residuals tracked live in Phase 4).
- **Settled decisions #8/#9/#16/#17** (CLAUDE.md) — position papers rebuilt as fence + guarded retrieval, contradiction-exclusion, disclaimer fallback — 2026-08-06.
- **CLAUDE.md Settled decision #5** — commentaries hard-excluded from answers — 2026-08-07.
- **Phase 1.3 inventory** (no flip) — 2026-08-07 read-only: 14 unlicensed+hidden sources; material content is Ravenhill/Savchuk/Poonen; flip still open (Phase 2).
- **Mirror unification** — `chat.py` deleted; async is the only answer path. Shared toolbox extracted (`answer_toolbox.py`), metering consolidated, silent fallback-on-failure removed entirely, `serving_enabled` recharacterized as an honest emergency pause. Commits `4557e5c` / `e223c98`, 2026-08-07.

---

## Scope honesty

~38 sessions total, stopping-point-defined, not clock-time-defined. Mid-2027
holds with margin.

---

*Everything else — the full version-history changelog, every item's build
narrative, resolved Open Decisions in full, the Ground Truth verification log,
the Superseded/killed list, and the pre-v6.0 Inline Study Panel / Quote track
detail — lives in* **`docs/plan-archive.md`**.
