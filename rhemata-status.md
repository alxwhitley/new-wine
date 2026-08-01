# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-01.

Trimmed 2026-08-01 back to live-state-only per the Project Knowledge Read
Contract (the file had grown to ~2,700 lines of accumulated session
narrative). The prior session-by-session history (2026-07-17 → 2026-08-01)
lives in git history; retrieve it there if a past session's detail is needed.

---

## Current state

**Phase 1.1 + 1.2 fixed — request queuing and connection handling
(2026-08-01, repo-only, plain/direct terminal session — two one-line-scale
edits, not a harness build).** Root cause of 1.1 (concurrent requests
serializing): `chat()` in `backend/app/routers/chat.py` was declared
`async def` but its entire body is synchronous blocking I/O (Supabase REST
calls, Groq query expansion, OpenAI embeddings, Cohere rerank, Anthropic
streaming) with zero `await` anywhere — Starlette only offloads *sync*
(`def`) endpoints to its worker thread pool, so the async-but-blocking
handler monopolized the single event loop thread and every other request
queued behind whichever request was currently running. Fix: dropped `async`
from the signature (`def chat(...)`), letting FastAPI run each request via
`run_in_threadpool` (anyio default capacity 40) — genuine concurrency, no
`await` needed anywhere since nothing in the call chain was ever actually
async. Root cause of 1.2 (compounding connection-handling issue):
`get_supabase()` in `backend/app/db/supabase.py` called `create_client(url,
key)` fresh on every single invocation (72 call sites codebase-wide) — a
brand-new Supabase `Client` (its own auth/postgrest/realtime sub-clients,
each with its own `httpx` connection pool) constructed per call, with no
connection reuse across requests. Once 1.1 legitimately unlocked
concurrency, this meant many concurrent requests would each independently
pay fresh TCP+TLS setup simultaneously — exactly the compounding described
in the build plan. Fix: made `get_supabase()` a module-level cached
singleton (matching the existing `_ai`/`_cohere_client`/`_anthropic_client`
lazy-singleton pattern already used elsewhere in this codebase); confirmed
no per-request auth/session state is ever mutated on the shared client
(grepped for `.auth.`/`session`/header mutation — none found), so sharing
one instance across concurrent request threads is safe.
**Verified with real before/after timing** (harness: real `chat.router`
served by a real `uvicorn` instance; only the external network calls —
Supabase client construction, Groq, OpenAI embeddings — were swapped for
deterministic `time.sleep()`-based stand-ins so the exact blocking
mechanism under test is preserved without needing live API keys; process
caches pre-warmed before the timed burst so results reflect steady-state
per-request cost, not one-time cold-cache cost). 6 concurrent requests to
`/chat`: **before** — 3.317s total wall clock, every request individually
~3.315s (fully serialized) and 6 separate `create_client()` calls; **after**
— 0.554s total wall clock, every request individually ~0.551s (genuinely
concurrent) and 0 additional `create_client()` calls (singleton reused).
~6x wall-clock improvement for 6 concurrent requests, matching the
predicted mechanism exactly. **Flagged, not fixed this session:** this same
`async def` + fully-synchronous-body pattern exists in essentially every
other router in the backend (admin.py, study.py, library.py, search.py,
etc.) — this session touched only `chat.py` (the answer endpoint) and
`db/supabase.py` (shared connection layer), per the session's explicit
scope. **Prompt A's live-answer latency baseline (Phase 0 measurement) is
now stale and must be re-run after this fix** — any measurement taken
before this session would have been measuring artificially serialized
request handling and would not reflect true post-fix concurrent-load
latency. Commit: build commit for the two code files; this file is the
separate records commit, per the standing two-commits-per-session pattern.

**Build plan adopted (2026-08-01) — accuracy / anti-fabrication sequence, Phases
0–3; now the front-of-queue priority.** Written from four adversarial architecture
audits (Claude + Codex, two rounds each, the last two with live DB access, which
independently converged). **Trigger — the "is speaking in tongues for today"
answer audit:** of its four named attributions, one was sound (Daniel Kolenda, who
has a real cessationism series in the corpus) and three failed — a claim credited
to Michael Brown was actually Kolenda's own material (plus a wrong date, "mid-to-
late 1800s" for what the source dates to the beginning of the twentieth century);
John Bevere was wholly fabricated (zero material anywhere in the corpus, his name
in no document — yet the fabricated attribution PASSES verification and renders as
a verified teacher link to an empty author page); and a real Billy Graham quotation
existed only inside Kolenda's document as Kolenda quoting Graham, extracted and
attributed to Graham verbatim, which the product's own rules forbid. **Mechanism
correction, now settled:** retrieval worked perfectly (Kolenda's material was the
best possible evidence and all of it was present) — the fabrication was NOT a
retrieval gap. The author-citation cap plus the push for multiple voices makes the
model redistribute one teacher's substance across other names it knows are
charismatic teachers; it knew too much, not too little. The only fix is deciding,
outside the model, which names are permitted (Phase 2's teacher-name check). The
verification gap named here — a name that exists and is allowed to show passes,
whether or not its material was used — is Phase 2's target, not closed yet. Full
plan folded into PLAN.md (active phase sequence) and CLAUDE.md (ranked failure
modes + 12 settled decisions, conflicts flagged inline). **Phase 0 (read-only
measurement) and Phase 1 (live contradictions) are the queued next sessions;** the
position-layer live cutover is reframed to post-launch (PLAN.md #48). No code, no
DB this session — records only.

**Proposition generation — resumed, current.** Runs on the bypass-proof v3.1
path (named-teacher extraction; provenance stamping structurally required,
CLAUDE.md Invariant 10). The corpus-wide backfill (PLAN.md #17/#49) completed
2026-07-30; a small number of documents remain unprocessed — the known
JSON-escaping defect (a model-emitted unescaped quote inside a nested scripture
quotation, present in v3/v3.1 alike) plus the book-length single-call gap
(partially addressed, below). Processed/remaining totals: query live.

**Chapter-scoped book extraction — committed, proven, in use.** The
`title_repeat_boundary` path (`split_book_into_chapters()` /
`_extract_and_store_book_chapters()` / `process_book_document()`, plus
`is_front_back_matter()` front/back-matter skipping) is committed and reliably
covers the 8 of 53 book documents whose chapters repeat their own title. Seven
public-domain books now have real propositions via this path, most recently
John Wesley's "The Journal of John Wesley" (1,249 propositions, v3.1, real
write 2026-08-01, independently re-verified on a fresh connection). The second
detector for roman-numeral / bare-"Chapter N" books (`detect_book_chapters()`
etc.) remains DELIBERATELY uncommitted with zero production callers — do not
assume it runs (CLAUDE.md Landmines, PLAN.md #50).

**2026-08-01 live-DB corrections — both closed, re-verified.** Fix (a)/(b)
(third-party byline detector, editorial-apparatus label set, tightened
digit-ratio roman-numeral arm) committed `8e251c8`.
- "The New Life" (Andrew Murray): a Translator's Note wrongly attributed to
  Murray removed — 411 → 408 propositions (3 rows deleted, disambiguated from
  10 genuine Preface rows via `proposition_chunks`).
- "The Lord's Table" (Andrew Murray): the real ~57-word "VII. Saturday" entry,
  previously excluded by the pre-fix digit-ratio arm, extracted and stored —
  148 → 149 propositions.
Both re-verified on fresh connections (separate from the writing connection),
clean `proposition_index` sequences. The two "live imperfection" Landmines and
CLAUDE.md Open Decision #22 are now closed. (DB-write session, no commit — the
DB is the durable record, per repo convention.)

**Position layer — house-voice Position Papers live for 2 pillars.**
`backend/app/services/position_papers.py` serves baptism-in-the-Spirit and
speaking-in-tongues in Rhemata's own voice via `chat.py` interception (newly
documented in ARCHITECTURE.md, "Position papers (house-voice answer path)",
2026-08-01). Remaining charismatic pillars are future work (drafts in the
untracked `docs/position_papers/`, owned by Alex).

**Position layer — serving path built + proven standalone, corpus ban lifted
(2026-08-01, PLAN.md #48).** Alex's explicit call lifted the corpus-wide ban.
Both structural locks widened together: migration 076 (`positions.kind` CHECK
`'teacher'` → `IN ('teacher','corpus')`, widened not dropped; `source_id`
NULLABLE + scope/source coupling CHECK) and the `write_position` /
`write_corpus_position` application gate. Migration 077 added the
versioning/lookup record shape (`lineage_id`/`version`/`is_current`/
`supersedes_id`/`topic_key`/`requested_teacher_id`, one-current-per-lineage
partial unique index). `scripts/serve_position.py` is the question-time
lookup-or-generate path: serve stored current version or generate+persist+
serve; corpus generation source-blind (Invariant 12 now covers both
generators — teacher NAME labels only); scope by `DOMINANCE_THRESHOLD = 0.60`
(Open Decision #13); contributors derived from evidence with counts;
disagreement presented not averaged; versioning + teacher→corpus widening;
four empty-state rules; no LLM call on refusal. **NOT wired into live chat** —
that cutover + teacher-card migration are the next slice. Proven:
`scripts/prove_serving_path.py` (39/39, fresh-connection verified),
`scripts/test_serve_position.py` (deterministic). Live table now holds 6
positions: the original 3 Savchuk `position_v1` drafts (untouched) + 3 genuine
new drafts this session (Derek Prince/divine-exchange teacher; holiness corpus;
"can a believer lose their salvation" corpus); the widening-demo lineage was
cleaned up. Invariants 13/14 rewritten/preserved. **Hard dependency for the
live cutover (new finding):** the pass-both eligible set is CPU-bound to
compute whole-corpus (~15+ min, book-length docs dominate) — not viable at
question time; the serving path uses a lazy `EligibilityChecker`, but
production must materialize eligibility, not recompute live.

**Repo at session close.** This session (2026-08-01, position serving path)
added three commits on `main`: ban-lift `2183a38` (migration 076 +
`write_position` gate), serving-path `6b66199` (migration 077 + `serve_position.py`
+ corpus generation/versioning in `positions.py` + `eligible_statements.py`
lazy checker + tests), and a docs commit (CLAUDE.md Invariants 12/13, PLAN.md,
this file). Migrations 076 and 077 are already APPLIED to the live DB (the code
and schema are in sync). Pre-existing and still uncommitted, untouched by this
session: the deliberately-uncommitted numeral-heading detector + its test
(`scripts/propositions.py`, `scripts/test_propositions_book_numeral_detection.py`),
two frontend commentary-styling tweaks, and the untracked `docs/position_papers/`
drafts. Local `main` is ahead of `origin/main` (unpushed) — pushing is a
separate decision (push to main deploys the backend to Railway).

---

## Open blockers

Open items only; #1, #2, #3, #5 are resolved (git history — commits `5bdf720`,
`d4826dc`).

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe; blocks the 8 further
HelloAO commentaries (PLAN.md #27). The real chokepoint gap.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace:
`docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace: `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill gap (residual).** Some unlicensed docs ingested
before the wiring, plus alias gaps for several entities (re-ingest sentinels
silently — `ALIAS_MISS` breadcrumb). Counts unverified; query live.

**9. v4 propositions prompt — decision pending.** `EXTRACTION_PROMPT_V4` exists,
committed `ff0652c`, unwired; v3 is the default and v3.1 the named-teacher
path. Median word count still short of target on the 18-doc test
(`docs/audits/proposition-v3-v4-comparison-2026-07-16.md`). Adopt / iterate /
discard — and if adopt, decide backfill.

**10. Precept Austin raw-source gap.** Fewer raw scrape files in
`sources/precept_austin/raw/` than ingested documents — some have no local raw
backing if re-verification is ever needed.

**11. `verify_chunk_alignment.py` docstring stale.** Describes `shared_ingest`
insert modes (`psycopg2_batch` / `rest_per_chunk`) that no longer exist.

**12. `jewish_perspectives` table orphaned.** 2 rows, zero code references
outside migrations/docs.

**13. SP2 Study Panel — no real screen-reader pass ever run.** Phase 9 fixed 5
keyboard/ARIA gaps via a structural/keyboard audit; no VoiceOver/NVDA listen
has been done.

**14. Hebrew lexicon permission gate.** TBESH (Hebrew) is NOT covered by the
CC BY 4.0 grant that clears Greek (TBESG/TFLSJ); needs Online Bible's own
permission. SP2 renders Greek only, structurally. Do not build against TBESH
until cleared (PLAN.md Open Decisions #11).

**15. Attribution-mode mismatch, 307 HistoricalChristianFaith docs.** The
importer set `citation_mode='citable'`; all 307 live rows are `silent_context`
— unknown whether intentional. Decision needed (attribution is core
positioning, Invariant 7). Audit:
`docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`.

**16. Copyright flag, HistoricalChristianFaith source.** Three authors under a
blanket `public_domain`/`shown` source record may not be PD: C.S. Lewis
(d. 1963), J.R.R. Tolkien (d. 1973), Douglas Wilson (living). Verify or gate
before treating as servable; interim lever = the `source_kind='commentary'`
"Historical Commentaries" toggle (currently enabled). Same audit as #15.

---

## Known harness bugs

Both resolved: the 2026-07-18 executor write-accounting loop (fixed 2026-07-19,
`d9ab1cc`) and the `BASH_WRITE_INDICATORS` SQL-verb over-flagging (narrowed
2026-07-31, `569d412` — no DB-write-capable command is ever allowlisted).
CLAUDE.md's Session Routing DB-write hard rule is unchanged; its revisit
trigger's second condition — a deliberately-run, reviewed, clean DB-write
harness session — remains open. Proofs:
`.claude/harness-selftest/test_write_accounting_loop_fix.py`,
`test_sql_verb_narrowing.py`.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar). The
  tab bar is gated off by default behind `NEXT_PUBLIC_FULL_NAV_ENABLED`
  (chat-only beta); `=true` restores it exactly.
- Pass B pending: `UsageRing` was pulled from the mobile top bar and not yet
  remounted in the sidebar drawer.

---

## Next

Reprioritized 2026-08-01 by the adopted build plan (PLAN.md active phase
sequence). Phase 0/1 lead; the position-layer cutover is now a post-launch
milestone, not the immediate next slice.

1. **Phase 0 — measurement (read-only, per the adopted plan).** Actual
   fabrication rate with the corrected recognition; run-to-run variance on
   repeated questions; false-positive rate of the two prototype deterministic
   checks (Phase 2's teacher-name and numbers checks); live-answer latency
   baseline. Sizes everything after it; input to Open Decision #20. See PLAN.md's
   active phase sequence.
2. **Phase 1 — stop the live contradictions.** Request queuing (1.1) + connection
   handling (1.2) **done 2026-08-01** (see Current state above — re-run Phase 0's
   latency baseline before trusting it). Next: reverse hidden-by-default +
   inventory (1.3); the doctrinal ruling before router work (1.4); the
   tongues-paper neutrality breach (1.5); the teacher-question hijack (1.6); the
   wrong-doctrine routing (1.7). See PLAN.md.
3. **Position layer — reframed to POST-LAUNCH (PLAN.md #48).** The plan's call:
   launch on the current answer path; make the source-blind position path the
   next milestone after launch, not a launch blocker. The serving path is built
   and proven standalone but NOT wired into chat; the live cutover still needs
   (a) **materialized eligibility** — the pass-both set is CPU-bound to compute
   whole-corpus (~15+ min), not viable at question time; (b) the wire-in +
   `get_teacher_card()` migration off live source-text synthesis (still the
   standing leak); (c) the license/visibility predicate the position layer lacks
   today; (d) the still-provisional floor calibration (evidence-count 5 /
   similarity 0.45 / dominance 0.60); (e) a draft-rows review/approval UI (also
   the home for Open Decision #20 side-by-side verification). The 3 draft
   positions written 2026-08-01 await that review.
4. **Blocker #4 — route `ingest_helloao.py` through `shared_ingest`.** Sole
   remaining chokepoint conversion; unblocks HelloAO commentary growth
   (PLAN.md #27) only, not corpus growth generally.
5. **Folder renames** (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop
   the orphaned `jewish_perspectives` table.
6. **Staging Supabase + backup/restore test.** The `sources/` backup exists
   (2026-07-19) but a restore has never been verified — do not assume it works
   until tested.

SP track: SP2 done (Phases 1–9); SP4 teacher cards shipped and signed off; SP
panel refinement done. Next SP item is #43 (SP5, mobile bottom-sheet). #38
(SP0 mobile mockup) completion unverified — confirm before assuming.
