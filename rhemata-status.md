# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-04.

Trimmed 2026-08-01 back to live-state-only per the Project Knowledge Read
Contract (the file had grown to ~2,700 lines of accumulated session
narrative). The prior session-by-session history (2026-07-17 → 2026-08-01)
lives in git history; retrieve it there if a past session's detail is needed.

Re-trimmed 2026-08-04: the Current state section had re-grown to ~840
lines of 2026-08-01 → 03 session narrative; that detail now lives in git
history and the per-topic durable homes (PLAN.md, CLAUDE.md, `docs/audits/`).

---

## Current state

Live-state-only. Prior session-by-session narrative (through 2026-08-03) lives in
git history and in the per-topic durable homes — PLAN.md (roadmap/decisions),
CLAUDE.md (invariants/landmines), the `docs/audits/` reports, and the commits
named below. Retrieve detail there.

**Deployment.** `origin/main` = `5f1aa02` (Stage 1, pushed 2026-08-04). Local `main`
is AHEAD by 2 UNPUSHED Stage-2 commits: `dd71b87` (async cutover build) + this records
commit. **NOT pushed** -- the Stage-2 session was told to hold the push for explicit
confirmation. Unlike Stage 1, Stage 2 TOUCHES the live path (chat.py, main.py, frontend
useChat/api) but the TRAFFIC SWITCH IS OFF: when pushed, `main.py`'s conditional mount is
a no-op (env `ASYNC_ANSWER_ENABLED` unset), `chat.py` gains only one informational
`evidence_version` meta field (answer/citations/verification byte-identical), and the
frontend uses the live path whenever `getChatMode()` is false (routes unmounted -> 404 ->
false). Migrations 078+079 are already applied additively. So a push deploys a
behavior-equivalent live path with the async path dark behind two OFF switches.
Railway (backend) + Vercel (frontend) auto-deploy from `main`; Railway build health
is not confirmed from the repo (CLI unauthenticated). The 2026-08-01 -> 03 accuracy +
copy-fix stack is on `origin/main` (verified): `0ab9c60` (Phase-0 §7a token fix),
`01ca912` / `813ae7b` (position-paper over-match + tongues house position),
`ee3cff4` (Phase-2 retrieval-grounded teacher-name guard), `9e5fe94`
(buffer-then-verify-then-playback + prose-attribution scan), `05aa519` (proposition
JSON-repair), `b1eccf9` (copy/gate fix).

**Attribution audit — HistoricalChristianFaith + C.S. Lewis (2026-08-04,
read-only, SELECT-only; ZERO writes; this records commit + a docs/audit).** Full
report: `docs/audits/historical_commentary_attribution_reverification_2026-08-04.md`.
- **TASK 1 — the 307 "stripped attribution" commentary docs: premise is wrong.**
  Author names are intact in `documents.author` for all 307/307 (0 empty, 307
  distinct); nothing was stripped or lost. Recoverability = 307 already in-hand /
  0 re-fetch / 0 unrecoverable. The real, separate issues: `citation_mode=
  silent_context` suppresses names in CHAT (correct — commentaries are excluded
  from answers anyway, `props=0`); the author is text metadata under ONE collection
  source, not a first-class entity; raw provenance (`url`/`file_path`/`full_text`)
  is NULL and the original `/tmp` SQLite source is gone. Open blocker #15 premise
  resolved.
- **TASK 2 — the C.S. Lewis doc is CORRECT author, WRONG copyright tag (live).**
  Doc `caedc32c…` = verbatim *Mere Christianity* (705 chunks), `year=1963`, under
  the blanket `public_domain`/`shown` HCF source. Lewis d. 1963 -> protected to
  ~2033; the PD tag is indefensible. It is retrievable (license gate passes on the
  source's PD status) and shown BY NAME in Study Mode (`/study/commentary` applies
  no citation_mode filter). Same class: J.R.R. Tolkien (d. 1973) and Douglas Wilson
  (living). Interim lever: the "Historical Commentaries" `source_toggles` row
  (`enabled=true` live). Open blocker #16 — still open, a schema decision for Alex.

**Per-answer cost MEASURED (2026-08-03; sizing basis for Project 1).**
`docs/audits/per_answer_cost_measurement_2026-08-03.md`. Normal answer median
**$0.039** (range $0.030–0.074, n=43); house-voice ~$0.015. Cost is comfortable,
NOT the ceiling — the genuine open ceiling at 100 concurrent is provider rate
limits (RPM/ITPM/OTPM), unchecked, a commercial conversation (C6). The instruction
block (3,656 tok) is already cache-controlled (~25% saving warm/at scale); hidden
reasoning is ~22% of cost / ~59% of latency, not trimmable without an accuracy
oracle (decision #4). Teacher cards ~$0.015/open, no caching -> precompute
(Project 2). Recommendation (D3): build per-answer cost/token instrumentation into
Project 1.

**Build posture — three-project sequence (2026-08-03 reset).** Project 1 scalable
async answer execution -> Project 2 one named voice per answer -> Project 3
hand-curated, server-gated quote rail. Capacity target 100 concurrent (a DIAL, not
a ceiling). Position layer cut down (single-voice half -> Project 2;
durable-stored-positions deferred); quote rail reshaped (manual-approval only,
serve-by-ID). The corpus-position ban was LIFTED 2026-08-01 and STANDS (not
re-imposed; durable work simply deferred). Full detail: PLAN.md "CURRENT BUILD
SEQUENCE (2026-08-03)" + CLAUDE.md 2026-08-03 settled decisions.

**Project 1, Stage 1 — durable async answer path BUILT 2026-08-04 (INERT / additive;
NOT cut over).** The scalable asynchronous execution path now exists ALONGSIDE the
live `/chat` path, which is byte-identical and remains the serving path. Nothing is
wired into routing (`async_chat` router NOT mounted in main.py). Build `82413c9`;
migration 078 applied (answer_jobs queue + Phase-4 per-answer instrumentation,
async_answer_config dials, provider_rate_usage). One app / one Postgres-backed queue
(a table in the existing Supabase DB, claimed via `FOR UPDATE SKIP LOCKED`) / one DB /
one scalable worker (`scripts/answer_worker.py`). Implemented: durable jobs that
survive restart, idempotency keys, single-flight (STRUCTURAL — active-dedup partial-
unique index), exact-match reuse, reconnectable delivery, backpressure, provider rate
ceilings (RPM/ITPM/OTPM), spend ceiling, retries-re-run-the-accuracy-check. The
producer REUSES chat.py retrieval + reference_verifier's real accuracy check
(regenerate-once-then-refuse preserved). PROOF (`scripts/async_answers_smoke.py`):
26/26 — completes; killed worker loses nothing (lease reclaim + finish); 2 identical
concurrent → 1 generation; reconnect; spend AND provider-rate-ceiling halt+resume;
peak 12/12 concurrent (1
worker × 12 slots); real accuracy path end-to-end ($0.32 real spend, 3 topical Qs
answered, 7–10 citations + verified refs each). Phase 1 diagnostic confirmed the ~40
ceiling is AnyIO's default 40-thread pool held for the request's whole ~68s (blocking
generation + `time.sleep` playback inside a sync streaming generator).

**Stage-1 follow-ups — flagged, NOT resolved (all deliberate, left for Alex):**
(a) **DB connection route** — the current `SUPABASE_DB_URL` is the SESSION-mode pooler,
hard-capped at 15 client connections (`pool_size: 15`), so one worker process tops out
~14 slots. Reaching the 100-concurrent DIAL needs the worker fleet on the transaction
pooler (port 6543) or a directly-sized route — a Supabase config/commercial decision,
same class as the unchecked provider RPM/ITPM ceilings, NOT a rebuild. (b) **evidence_
version** — no corpus-version signal exists in the schema; the reuse key uses a
placeholder (`corpus-unversioned`). A real signal (e.g. `max(documents.updated_at)` or a
corpus generation counter) is needed before reuse is trusted in prod. (c) **producer ↔
chat.py retrieval DRIFT** — `producer.py` mirrors chat.py's retrieval orchestration +
generation constants (chat.py stays byte-identical this inert session); a retrieval or
prompt-assembly change in chat.py must ALSO be applied to producer.py until they are
unified at cutover (extraction/grounding/verification are imported, so those stay in
sync). (d) **Cutover (Stage 2+ / PLAN):** mount `async_chat`, move the reveal to the
client, and fold in the two parity gaps the producer omits this session — background-
topic injection and position-paper (house-voice) interception.

**Project 1, Stage 2 — async cutover WIRED, traffic switch OFF (2026-08-04, build
`dd71b87`).** Closes Stage-1 follow-ups (b) evidence_version and (d) cutover-wiring;
(a) DB route and new metering/auth gaps stay open (below). Nothing serves the async
path yet — two OFF switches gate it.
- **Phase 1 parity (14/14, `scripts/async_parity_check.py`).** `evidence_version` is
  now the real shared `corpus_version()` (migration 079: documents/sources/toggles/
  safe_mode hash; `services/corpus_version.py` cached + fail-safe), used in BOTH the
  async reuse key AND chat.py's informational SSE meta (Alex's Option A). `producer.py`
  now runs position-paper interception + background-topic injection matching chat.py
  exactly; routing parity is deterministic (same functions). Dedup key expanded to
  include last-6 turns + `topics_established` (fixes a latent cross-conversation
  single-flight/reuse collision). `policy_version`→v2.
- **Phase 2 cutover (LEFT OFF).** Two-level gating, both default OFF: env
  `ASYNC_ANSWER_ENABLED` mounts routes (deploy-level); DB `serving_enabled` is the
  seconds-reversible TRAFFIC switch (verified flip on/off in one UPDATE, left OFF),
  surfaced by `GET /async-chat/mode`. Frontend routes to the async client only when
  true, failing safe to live. Client-paced reveal (`lib/api.ts`, ~250 chars/s) fires
  only after the checked answer arrives — no client holds a worker. Flag-off proven
  unchanged (main.py route table byte-identical when off; chat.py +1 informational
  meta field; frontend additive+gated). Stage-1 mechanics still 24/24; real integrated
  path (producer→worker→complete) confirmed incl. position-paper + normal + e2e queue
  ($0.11 real spend).
- **Phase 3 (report-only). Known ceiling on any flip:** the session-pooler 15-client
  cap (~14 concurrent generations/worker) — NOT addressed this session; the worker
  fleet must move to the transaction pooler / a sized route for the 100-concurrent
  dial. Measured concurrency to date = peak 12/12 (1 worker × 12 slots, pooler-capped).
  A controlled real-traffic confirmation (DESCRIBED, not run): flip `serving_enabled`
  on for a single worker / small % of traffic, run a timed test sampling
  `count(*) WHERE status='running'`, then flip `serving_enabled` back OFF.
- **Remaining BEFORE a real flip (NOT built — a flip without these regresses):**
  (a) metering/usage-limit parity on `/async-chat/submit` (each submission meters
  independently even under single-flight); (b) auth→user_id + conversation persistence
  (worker writes `answer_jobs`, but nothing saves `conversations`/`messages` for a
  logged-in user's history); (c) `psycopg2-binary` in `backend/requirements.txt`;
  (d) the DB route above. See CLAUDE.md's async landmine. Observed + mirrored (NOT
  fixed): the live matcher over-matches "What is deliverance?"→baptism house voice.

**Answer path — current behavior.** Normal answers buffer fully, run the Phase-2
retrieval-grounding guard + prose-attribution scan + `verify_references`
server-side, resolve any ungrounded credit (regenerate-once-then-clean-refuse),
then reveal as paced playback — nothing unverified reaches the reader (`9e5fe94`).
A named teacher earns a verified link only if its material was retrieved for the
question (`ee3cff4`). The position-paper (house-voice) path serves the baptism +
tongues pillars via `chat.py` interception and still streams live. **Two launch
blockers stand (below): ~68s to a fully-revealed answer; ~40-chat concurrency
ceiling — both are Project 1's remit.**

**Corpus / data.** Proposition generation runs the bypass-proof v3.1 path
(Invariant 10); the corpus-wide backfill is COMPLETE (0 genuine documents
remaining; 7 residuals extracted 2026-08-02). Chapter-scoped book extraction
covers 8 of 53 books (`title_repeat_boundary`); the numeral-heading detector
stays uncommitted with zero callers. The position serving path is built + proven
standalone but NOT wired into live chat (see Next #3). All counts: query live.

---

## Open blockers

Open items only; #1, #2, #3, #5 are resolved (git history — commits `5bdf720`,
`d4826dc`).

**LAUNCH BLOCKERS (release-gating; neither blocks further build work):**
- **Both are now Project 1's remit (2026-08-03 build plan).** The concurrency
  ceiling is exactly what Project 1 (scalable async execution) replaces; the ~68s
  latency is recorded there as an OPEN launch blocker with **no owner yet** —
  moving the reveal to the client removes ~15s and fixes concurrency, but
  generation still runs ~50s, and single-teacher answers (Project 2) reduce it
  meaningfully but not sufficiently.
- **≈68s to a fully-revealed answer on the normal path** (measured live: ~54s
  before any text appears, then ~15s of playback). The deliberate cost of
  buffer-then-verify-then-playback — nothing unverified reaches the screen
  (`9e5fe94`) — accepted for now, MUST be reduced before launch. This live figure
  supersedes the earlier offline ~35s time-to-first-character estimate in the
  buffer-then-verify entry above. The dominant component is the model's hidden
  reasoning (req-7-protected; trimming it needs an accuracy oracle that does not
  exist — Open Decision #20 / settled decision #4). **Quantified 2026-08-03
  (`docs/audits/per_answer_cost_measurement_2026-08-03.md`):** offline generation
  wall-clock is median ~35s (worst ~65s), of which the hidden reasoning is
  median ~59% (worst 73%) — it is the single largest latency component, and it
  is the piece that cannot be trimmed without the missing accuracy oracle.
- **Concurrency ceiling ≈ 40 simultaneous chats.** The playback pacing +
  heartbeat `time.sleep` holds one anyio threadpool worker per active request for
  the request's whole duration; at ~40 concurrent chats the shared pool (cap 40)
  starves other work. Harmless at zero-user scale; MUST be fixed before real
  traffic. **Replacement BUILT (INERT) 2026-08-04 — Project 1 Stage 1 durable async
  path; see "Project 1, Stage 1" in Current state. NOT cut over yet; the live path
  still serves.**

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe; blocks the 8 further
HelloAO commentaries (PLAN.md #27). The real chokepoint gap.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace:
`docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace: `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill — CLOSED 2026-08-02 (0 genuine documents remaining).**
The mass run completed 2026-07-30, and the last 7 residual documents were
extracted 2026-08-02 (517 props; build `05aa519`; re-verified live —
`docs/audits/backfill_reverification_2026-08-02.md`). Unchanged residual, a
separate hygiene issue not a backfill backlog: some entities still have alias gaps
that re-ingest sentinels silently (`ALIAS_MISS` breadcrumb). Any future extraction
targets a NAMED document-id set (CLAUDE.md landmine), never "all zero-prop docs."

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

**15. Attribution-mode — 307 HistoricalChristianFaith docs — PREMISE RESOLVED
2026-08-04.** Re-verified live: author names are intact in `documents.author` for
all 307/307 (nothing stripped); `citation_mode='silent_context'` on all 307 is
correct (suppresses names in chat; commentaries are excluded from answers anyway,
`props=0`). No lost attribution to recover. Residual is structural only (the author
is text metadata under one collection source, not a first-class entity) — deferred,
not a blocker. Audit:
`docs/audits/historical_commentary_attribution_reverification_2026-08-04.md`.

**16. Copyright — C.S. Lewis / Tolkien / Douglas Wilson under the blanket-PD
HistoricalChristianFaith source — OPEN, live exposure.** Re-verified 2026-08-04:
the C.S. Lewis doc (`caedc32c…`) is verbatim *Mere Christianity*, correctly
attributed to Lewis but wrongly tagged `public_domain` (d. 1963, protected ~2033);
Tolkien (d. 1973) and Douglas Wilson (living) are the same class. All three are
retrievable (license gate passes on the source's PD status) and shown BY NAME in
Study Mode. The schema has no per-author license override — a source-level model
can't mark them differently from Augustine. Interim lever: flip the "Historical
Commentaries" `source_toggles` row (`commentary`) to `enabled=false` (currently
true) to pull all 307 from Study retrieval. Durable fix = per-author/per-document
license override (Alex's schema decision). Audit as #15.

---

**17. Live unbacked quote guarantee — CLOSED 2026-08-03 (`b1eccf9`).** The
present-tense character-for-character quote claim on `frontend/app/home/page.tsx`
(~L492) was rewritten to the honest paraphrase-and-roadmap framing; `app/` +
`components/` were swept and the home page was the only remaining live surface
(`/sources`, POSITIONING.md, and `docs/how-rhemata-handles-sources.md` were already
roadmap-framed).

**18. Bevere marketing line + empty-but-servable source — PARTLY CLOSED
2026-08-03; marketing line OPEN.** The empty-author-page surface is now gated:
`/study/teacher/{id}` 404s any curated teacher with zero points, so Bevere's card
no longer serves an empty page (`b1eccf9`). STILL OPEN: the home-page marketing
line (`page.tsx` L489) names "John Bevere" (empty source, 0 props) and "Michael
Koulianos" (NO `sources` row at all — not in the corpus) as "trusted modern-day
teachers"; only Dr. Michael Brown of the three has content. A living-minister
misrepresentation (failure mode 2). Decide: remove/rewrite the marketing line and/or
dark the empty Bevere source (row + 5 aliases intentionally retained for future
blog material).

**19. Pipeline diagram (external, non-repo) is stale in four ways.**
`rhemata-pipeline-diagram.html` lives OUTSIDE the repo (confirmed absent from the
repo and from ~/Desktop, ~/Downloads, ~/Documents). Known inaccuracies, recorded for
if/when it resurfaces (not redrawn this session): (a) shows number/date
verification that does not exist and is held at 100% false positives; (b) states
checks run AFTER the reader sees text — false since buffer-then-verify (2026-08-02,
`9e5fe94`); (c) shows quotes as categorically disallowed with no quote rail —
superseded by Project 3; (d) marks the verse route as unbuilt.

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

1. **Phase 0 — measurement (read-only) — DONE 2026-08-01.**
   `docs/audits/phase0_measurement_2026-08-01.md`. Key results: corrected
   scripture-fabrication rate ~0% (the stale 72-reference number was a
   compact-scanner artifact); teacher-attribution fabrication real but low
   (1/26 baseline, incl. the dangerous verified-link `in_corpus_not_retrieved`
   class — A.W. Tozer passed the SP1 verifier via a nested Precept-Austin quote);
   fabrication is intermittent (3/12 questions flipped across 4 runs, 0/12
   consistent) so single-run rates understate exposure; teacher-name check
   prototype 0% false positives (125 attributions), numbers/absolutes check 100%
   false positives (unusable as prototyped); latency baseline flagged STALE
   (predates 9fdf8d2, local single-request) — **re-run from Railway is an open
   follow-up.** Two unplanned findings were pulled forward and both fixed the same
   day: §7a token-exhaustion (entry above, deployed) and §7b position-paper
   over-matching (entry above). Input to Open Decision #20 (still HELD).
2. **Phase 1 — stop the live contradictions.** Request queuing (1.1) + connection
   handling (1.2) **done 2026-08-01** (see Current state above — re-run Phase 0's
   latency baseline before trusting it). Position-paper over-matching — the
   tongues-paper neutrality breach (1.5), the teacher-question hijack (1.6), the
   wrong-doctrine routing (1.7) — **done 2026-08-01** (see Current state above).
   The normal-path doctrinal fix (1.4) — the system prompt listed
   tongues-as-initial-evidence as an in-house debate — is **done 2026-08-01**
   (build commit `813ae7b`; CLAUDE.md decision #10's conflict flag cleared; see
   Current state above). Next: reverse hidden-by-default + inventory (1.3). See
   PLAN.md.
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
