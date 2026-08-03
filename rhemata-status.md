# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-03.

Trimmed 2026-08-01 back to live-state-only per the Project Knowledge Read
Contract (the file had grown to ~2,700 lines of accumulated session
narrative). The prior session-by-session history (2026-07-17 → 2026-08-01)
lives in git history; retrieve it there if a past session's detail is needed.

---

## Current state

**Copy-fix — unbacked quote claim removed + zero-point teacher pages gated
(2026-08-03, repo-only code change + read-only DB diagnostic; ZERO DB writes;
plain path, main thread; code commit `b1eccf9`, this records commit separate;
NOT pushed — Alex decides deployment).** Closes Open blocker #17 (the recurring
B5 landmine) and the teacher-side of #18. Two SELECT-only live checks, no writes.

- **TASK 1 — false quote-verification claim removed (`frontend/app/home/page.tsx`
  L492).** The home page carried a present-tense promise ("Every quote is checked
  character-for-character against the source ... a quote cannot exist in Rhemata
  unless the teacher actually said it. ... Rhemata structurally can't") with no
  mechanism behind it — no quote pipeline exists, no quotes are served anywhere.
  Rewrote it to the honest, already-shipped framing: Rhemata paraphrases and
  attributes; verbatim quoting is "software-confirmed against the source ... on
  our roadmap — not live yet" (mirrors `/sources` L40/L43). **Swept `app/` +
  `components/`: the home page was the ONLY live surface still asserting it.**
  `/sources` (L43 roadmap framing, L89 attribution-trust) was already honest and
  left unchanged; `app/library/page.tsx` L641 ("edited transcript — not a
  word-for-word recording") is an accuracy disclaimer, not the claim.
- **TASK 2 — zero-point teacher/source pages now return not-found
  (`backend/app/routers/study.py`, `get_teacher_card`).** `GET
  /study/teacher/{source_id}` returned a live empty card for a curated teacher
  whose source has zero propositions (the "verified link to an empty author
  page" surface). Added a UNIFORM gate (all teachers, not a Bevere patch): a
  single existence probe `propositions.select("id, documents!inner(source_id)")
  .eq("documents.source_id", source_id).limit(1)` → 404 "No content for this
  teacher" if empty. Placed before the servable/works logic so it applies to
  every teacher. Frontend `TeacherCard` renders its "card isn't available right
  now" state on the 404 — a hidden state, not an empty bio page.
- **Who the gate affects (live-verified, `docs/audits` not written — scratchpad
  diagnostic only):** of **9 curated teachers, exactly ONE is hidden today —
  John Bevere (0 docs, 0 props).** The other 8 all have points and are
  unaffected: Derek Prince (5178), Bob Mumford (49), Jack Deere (31), Charles
  Simpson (31), Ern Baxter (26), Don Basham (16), Michael Brown (12), Oswald J.
  Smith (8). The 39 other servable zero-prop sources (A.W. Tozer, Bill Johnson,
  Wommack, Wigglesworth, Precept Austin, the commentary DBs, etc.) are NOT
  curated teachers — the endpoint already 404s them ("Not a curated teacher"), so
  they have no teacher-card page to gate. Gate query shape validated live against
  the real Supabase (Bevere→hidden, Prince→served) and re-checked across all 9.
- **John Bevere source row + 5 aliases intentionally LEFT in place** (per
  instruction) for future blog material; only the empty *page* is hidden.
- **FLAGGED, NOT touched (out of scope per the two-task boundary) — home-page
  marketing line L489.** It names three "trusted modern-day teachers": **John
  Bevere (empty source, 0 props)** and **Michael Koulianos (NO `sources` row at
  all — not in the corpus)**; only **Dr. Michael Brown** of the three has content
  (2 docs / 12 props). A live misrepresentation (failure mode 2) — recommended as
  the immediate copy follow-up. Koulianos's total absence is a NEW finding this
  session (not previously recorded).

**Per-answer cost + latency MEASURED (2026-08-03, measurement/read-only
diagnostic; retrieval reads + LLM generation only, ZERO DB writes; plain path;
~$2.03 total spend, under the $50 ceiling; single records commit; NOT pushed; no
code, no behavior change).** Ran the Project-1 cost measurement flagged OPEN by
the 2026-08-03 build plan, via a faithful offline reproduction of the live
answer path (same chat.py helpers, system blocks, model, retrieval, full
background-paper injection), 23-question real-traffic mix, most run 2–3×. Full
detail + method: `docs/audits/per_answer_cost_measurement_2026-08-03.md`.
- **Normal answer: median $0.039, range $0.030–$0.074 (n=43).** House-voice
  (position-paper) answers ~$0.015, ~12s. The Phase-A estimate ($0.07–0.12) was
  ~2–3× high; the measured median is the sizing basis, retiring the
  partial-extraction figure.
- **Cost is comfortable, NOT the ceiling.** 100-always-in-flight for an hour ≈
  $400/hr (worst $758/hr) but real peaks are bursty; $0.039/answer is cheap.
  Exact-match reuse scales cost by (1 − repeat rate). **The genuine open ceiling
  at 100 concurrent is provider rate limits (RPM/ITPM/OTPM) — unchecked from the
  repo, a commercial conversation with Anthropic, flagged for Alex (C6).**
- **#1 Prompt caching:** the repeated instruction block is 3,656 tokens and IS
  already cache-controlled (corrects the Phase-A "appears not to cache" guess).
  Warm it costs $0.0011 (3% of an answer) vs $0.011 uncached (28%) — a ~$0.0099
  (~25%-of-answer) saving that is **automatic at warm/scale traffic**; at current
  ~zero traffic every answer is a cold write (+$0.0027 premium, harmless). No
  further instruction-block saving to capture; the largest un-cacheable line is
  the per-question retrieved context (~50% of cost, ~6,526 tokens median).
- **#2 Reasoning output** (hidden `<thinking>`/`<research_analysis>`, billed at
  output, discarded) — now a MEASURED variable line item, not a constant: median
  53% of output tokens / 59% of generation wall-clock / 22% of answer cost
  (worst 71% / 73% / 42%); ~$0.0094/answer median. Largest single latency
  component. NOT changed and not proposed for change (accuracy not traded for
  speed — settled decision #4 / Open Decision #20).
- **#3 Teacher cards:** ~$0.015 and ~11–13s per open, NO caching → precompute
  (Project 2 scope) saves the full per-open cost + time at any real view volume.
- **Recommendation (D3):** build per-answer cost/token recording into Project 1
  as standing instrumentation (this session had to reconstruct every figure
  offline because nothing is recorded).
- **Incidental (not in scope):** the scripture question "Romans 8:28" routed to
  the house-voice path — a possible position-paper over-match on a plain
  scripture question. Flagged, not investigated.

**Build-plan reset after two external reviews — three-project sequence adopted;
position layer cut down; quote rail reshaped (2026-08-03, docs/records-only; plain
path per Session Routing, chat-proposes/terminal-commits; single records commit;
NOT pushed; no code, no DB; two SELECT-only live checks with no writes).** Recorded
the new plan from two external adversarial reviews (one correctness-focused, one
scope-cutting) of a written proposal, plus Alex's decisions, correcting-forward
across PLAN.md, CLAUDE.md, and this file. Prior entries kept as written.
- **New build order (supersedes the 2026-08-01 phase ordering + Ordering Call G):**
  Project 1 scalable async answer execution → Project 2 one named voice per answer →
  Project 3 hand-curated, server-gated quote rail. Capacity target 100 concurrent
  generations, a DIAL not a ceiling; **real per-answer cost is OPEN and required
  before Project 1** (do not size from the partial extraction figure). Full detail:
  PLAN.md "CURRENT BUILD SEQUENCE (2026-08-03)"; binding rules in CLAUDE.md's
  2026-08-03 settled decisions.
- **Position layer cut down (B6):** single-voice half → Project 2 (absorbs the
  source-blind path #48); durable-stored-positions half (persistence, rebuild
  triggers, replace-vs-version, review UI, empty states) DEFERRED pending real
  usage. Foundation stays as built — nothing torn out.
- **Corpus-ban framing corrected — chat-side belief was WRONG.** The build prompt
  said the ban "stays in force"; the repo showed it was LIFTED 2026-08-01 (migration
  076; CLAUDE.md Invariant 13). Alex's ruling: repo wins. The lift STANDS; corpus
  positions are simply not being built on (durable work deferred) — a product
  posture, not a re-ban. **Second stale chat-side premise the repo caught in one
  day** (first: the "781" backfill figure) — recorded as a working-pattern landmine
  in CLAUDE.md.
- **Live query (A) — corpus rows are INERT.** `positions` holds 6 draft rows: 4
  teacher-scope + **2 corpus-scope** (`holiness and personal purity`; `can a
  believer lose their salvation`), all `is_current`, all `status='draft'`. Not
  reachable by any live serving path — `backend/app` reads nothing from the
  `positions` table; `scripts/serve_position.py` is standalone and unwired. (Prior
  "3 new drafts" = 1 teacher + 2 corpus, not 3 corpus.)
- **Live query (C) — Bevere ground truth.** Source `John Bevere`
  (`unlicensed`/**`shown`**) + 5 aliases REMAIN, but **0 documents, 0
  propositions** (by author or by source) — material fully deleted 2026-07-25; an
  older "fully processed for propositions" record is stale. Empty-but-servable
  source = the "verified link to an empty author page" surface; the home page also
  markets him as a trusted teacher. Both → copy-fix session (Open blockers #18).
- **Quote rail reshaped (B3):** staged #21–25 superseded; automated extraction +
  whole-corpus backfill DEFERRED (not cancelled). Minimal records (source-revision +
  content hash + quote record with clearance basis/state), content hashing IN SCOPE
  NOW, manual-approval-only, 50–100 first-pass quotes from clean written sources,
  serve-by-ID with one server-side resolution point, revocation = state change.
  Binding eligibility / no-trim / affirmative-clearance rules in CLAUDE.md (B4).
- **Enforceable claim corrected (B5):** the "model never generates a quote → can't
  be fabricated" claim is unenforceable; only the component-based claim is
  permitted. **OPEN, HIGH PRIORITY (report-only this session):** the unbacked
  present-tense claim is STILL SHIPPING on `frontend/app/home/page.tsx` (~L492) —
  recurrence of the B5 landmine — plus the Bevere marketing line; both get a
  dedicated copy-fix session immediately after this one (Open blockers #17/#18).
- **A2 claim-level misattribution reclassified (B7):** previously "structurally
  uncatchable"; now closed STRUCTURALLY by Project 2's design (the other teacher's
  material is never in the generation). Passage-level speaker ownership (the
  Precept-Austin nested-quote class) remains accepted/deferred, handled by
  excluding mixed-voice sources.
- **Pipeline diagram:** `rhemata-pipeline-diagram.html` is NOT a repo artefact
  (confirmed absent from the repo and from ~/Desktop, ~/Downloads, ~/Documents) —
  it lives outside the repo. Its four known inaccuracies are recorded (Open blockers
  #19) so the record exists if it resurfaces; no in-repo "flag stale" action.

**Governing-file reconciliation — stale backfill figure corrected + completed
work recorded (2026-08-03, docs/records-only; plain path per Session Routing,
chat-proposes/terminal-commits; single records commit; NOT pushed; no code, no
DB).** Reconciled the stale backfill figure and today's completed work across
PLAN.md, CLAUDE.md, and this file, from the re-verification
(`docs/audits/backfill_reverification_2026-08-02.md`, `122ad48`) and the
extraction (build `05aa519`, records `f439f72`).
- **Backfill is COMPLETE — 0 genuine documents remaining** (the 7 residuals
  extracted 2026-08-02, 517 propositions). Bevere was already fully extracted —
  never 91% outstanding; his material was deleted 2026-07-25 (absent by decision).
  The "781" figure predated both the 2026-07-30 run and the Precept-Austin
  ingestion and had already been corrected to 564 in PLAN.md — it was never a live
  claim in the governing files; the real correction is simply that the residual is
  now zero.
- **PLAN.md:** #17 closed in place; ACTIVE PHASE SEQUENCE annotated with
  completion status + the three still-open items (A2 misattribution, Precept
  nested-quote mechanism, numbers/absolutes 100%-FP checker); version bumped to
  v5.17 (title had drifted at v5.15).
- **CLAUDE.md:** three landmines added — extraction must target a named ID set,
  never "all zero-prop docs" (2,176 Precept Austin word-studies + license-gated
  material otherwise swept in); the corpus keeps no record of extraction attempts;
  a long model stall can drop the DB connection mid-extraction.
- **Open blockers (below):** #8 updated to reflect 0 remaining; **two LAUNCH
  BLOCKERS logged** (~68s time-to-first-visible-text on the normal path; ~40-chat
  concurrency ceiling) — neither blocks further build work.
- **Flagged, NOT resolved (a task premise was already stale):** the corpus-wide
  positions ban was already LIFTED 2026-08-01 (Alex's explicit call — PLAN.md
  #303 / CLAUDE.md Invariant 13). Its backfill precondition is now fully met, but
  there is no ban to re-decide, so it was left untouched — not re-imposed, not
  re-flagged as awaiting a decision that has already been made.

**7-document backfill residual extracted + JSON-escaping defect fixed
(2026-08-02, repo-only build + targeted corpus write; PLAIN SCRIPT PATH per the
Session Routing DB-write hard rule, never harness; build commit `05aa519`,
separate records commit; DB writes have no commit — the DB is their record; NOT
pushed).** Closes the genuine backfill identified in
`docs/audits/backfill_reverification_2026-08-02.md` (commit `122ad48`): exactly 7
documents, targeted BY ID (never the "all zero-prop docs" query, which would hit
2,176 locked-out Precept Austin word-studies). Not a mass backfill — the mass run
completed 2026-07-30; these 7 were its known residual failures.

- **Root-cause fix (build `05aa519`, `scripts/propositions.py` +
  `scripts/test_proposition_json_repair.py`).** 5 of the 7 (the sermons) failed
  on the documented JSON-escaping defect: `extract_propositions` parsed Groq's
  output with a bare `json.loads`, and a model-emitted nested quotation inside a
  `content` value with unescaped inner quotes (`... says, "My times are in your
  hands," and ...`) raised "Expecting ',' delimiter" → whole document errored.
  **Reproduced live first** (3/5 sermons failed on the first diagnostic round,
  raw captured), then fixed with a deterministic, schema-aware repair
  (`_repair_unescaped_quotes`) run ONLY as a fallback after the first parse fails
  — NOT a model-retry loop (a key requirement). Key strings close before `:`, the
  last `content` value string before `}`/`]`; any other in-string `"` is a
  literal inner quote and is escaped; a still-unparseable repair raises
  `PropositionExtractionFailed` as before (never a silent bad write). Proven
  deterministically against the 3 real captured failures + well-formed/
  already-escaped pass-through, and end-to-end live (below). The pre-existing,
  deliberately-uncommitted numeral-heading book detector in the same file was
  left unstaged — the build commit carries ONLY the JSON fix + its test.

- **Extraction (v3.1, speaker=author, via the vetted `process_document` /
  `process_book_document` paths).** Sermons and books run as SEPARATE passes
  (sermons verified before books, per requirement). **Rows written this session
  (fresh-read verified, not the writer's return value):**
  - Kolenda "Cessationism 9" — 8; Prince "Mary: The Pattern Mother" — 9; Prince
    "Seven Ways To Keep Your Deliverance" — 13; Prince "Who Are The Israel Of
    God?" — 9; Savchuk "God Decides When" — 7. **Sermons = 46 props.**
  - Kreighbaum "Manual Systematic Theology" [book] — 309 (25/25 size-fallback
    chapters stored); Bosworth "Christ the Healer" [book] — 162 (15/16 stored, 1
    front-matter skipped). **Books = 471 props.**
  - **Total written = 517.** All stamped provenance `v3.1` /
    `llama-3.3-70b-versatile` / non-null fingerprint; every doc has a clean
    `1..n` `proposition_index` sequence and zero null embeddings.
- **Corpus before → after (verify live if reused):** documents 3595 → 3595
  (unchanged, no docs added/removed); propositions **10,622 → 11,139 (+517)**;
  docs-with-propositions **857 → 864 (+7)**. **Isolation proven:** the +517 delta
  exactly equals the sum of the 7, and propositions on all other documents stayed
  at 10,622 — nothing outside the 7 was touched.
- **Hand-check (accuracy + attribution, sampled each group; Prince emphasized).**
  All correctly attributed and on-topic: Kolenda→Kolenda (Lucretius/Enlightenment
  cessationism history), the 3 Derek Prince sermons→Derek Prince (Mary/Luke 1:38;
  the Gadarene "my house"; Israel & the Church/Gen 17:8), Savchuk→Savchuk
  (chronos/kairos), Kreighbaum→"Doug Kreighbaum" (theology as study of God, Deut
  29:29), Bosworth→"Bosworth" (faith-for-healing from Scripture). The two sermons
  that broke JSON in diagnosis now correctly preserve their nested quotes
  (`"According to your word,"`, `"my house"`) — the fix works on live data.
- **Transient Savchuk hang (worth recording).** Savchuk's FIRST attempt errored
  after 1543s with "server closed the connection unexpectedly" — a DB connection
  the Supabase pooler dropped after ~26 min of idle during an unusually long LLM/
  reference-grounding stall (NOT the JSON defect; NOT reproducible — a standalone
  re-extract took 4.7s, and a fresh-connection re-run stored 7 in 10.8s). The
  one-off runner lacked the connection-reconnect resilience `run_full_backfill.py`
  has; a future targeted runner should carry it.
- **Cost (req 6): ≈ $0.45** (computed from volumes — no billed token meter):
  Groq Llama-3.3-70b input ≈ 500–580k tokens (~$0.32), output ≈ ~110k (~$0.09),
  OpenAI embeddings for 517 props negligible. A touch above the audit's ~$0.35
  because of the diagnosis rounds, the transient Savchuk retry, per-sub-unit
  prompt overhead on the 41 book chapters, and reference-grounding arbiter calls.
  Far under the $50 ceiling.
- **Disclosed residuals (fail-safe, not fixed):** (a) the book propositions use
  the committed **size_fallback** split (both books had no title-repeat headings),
  so sub-unit boundaries are word-bounded (~5,500 words) not chapter-aligned — a
  sub-unit boundary can fall mid-chapter; labels aren't stored so this affects
  only split boundaries, not attribution/provenance. (b) The JSON repair assumes
  `content` is the last field (as the prompt example dictates); a reordered
  output would fail-safe (raise), never store corrupt content. (c) The genuine
  backfill is now **0 remaining** — a fact the separate, still-pending
  781/91%-Prince+Bevere docs correction (PLAN.md/CLAUDE.md) should reflect. **Not
  pushed** — Alex decides deployment (the code fix would deploy the backend).

**Phase 2 residual closed — prose-attribution scan (2026-08-02, repo-only
multi-step build; harness-row per Session Routing, run as orchestrator +
`planner-reviewer` adversarial gate before commit; zero DB writes — retrieval
reads + LLM generation only; build commit + separate records commit; NOT
pushed).** Closes the last open pure-invention path: the Phase 2 guard (and its
buffer-then-verify resolution) keyed only on the model's own
`<reference_mentions>` self-report, so a teacher credited in the answer PROSE but
omitted from that block went out unchecked (reviewer finding #3 on
`ee3cff4`/`9e5fe94`). **Scope (Alex): FULL PERSONAL NAMES ONLY.** Bare surnames
deliberately out — Phase 0 documented that short forms ("Prince") occur in
ordinary prose and a surname scan would risk false denials.
- **Mechanism (`reference_verifier.py`, additive — zero deletions, so the shipped
  `verify_references`/`verify_teacher_mention` link gate is byte-behavior
  unchanged, req 5).** `ungrounded_prose_teachers(answer, name_universe,
  grounding, db)` = the union of two arms, both grounded by the SAME
  `_is_retrieval_grounded` (req 1) and failing CLOSED (req 3):
  - **Arm 1 — corpus full-name scan.** Prose is scanned for the finite,
    precomputed set of corpus "first + last" names (`build_name_universe`, 65
    names live — orgs/magazines/commentaries filtered out; "Precept Austin" the
    one org-shaped admit, low-risk and correct to flag if credited-unretrieved).
    Position-agnostic, near-zero FP. Catches the in_corpus_not_retrieved class
    credited in prose (the A.W. Tozer symptom).
  - **Arm 2 — attribution-context extraction.** First+last names in explicit
    "According to X" / "X taught" / "X's commentary" constructions, grounding-
    checked. This is what catches OUT-OF-CORPUS inventions (confirmed by query:
    Wiersbe, Stedman, Wilson, Jenkins, Martin, Havner are NOT in the corpus, so
    no allowlist could see them). Person-filtered against biblical figures +
    divine/theological/org/function-word tokens.
- **req 2 (retrieved IDENTITY, not alias resolution):** grounding via
  `_is_retrieval_grounded`'s author-name arm keeps Andrew Murray (retrieved, no
  alias row — the alias-gap Landmine) from being false-flagged. Confirmed by
  trace + deterministic test.
- **req 4 (resolution):** prose flags feed the SAME regenerate-once-then-clean-
  refuse loop as declared flags (`chat.py generate()` now triggers on the union;
  `build_name_universe` built once inside the resolution try, raises→refuse).
  Declared-block guard (`_ungrounded_reference_teachers`) kept and refactored onto
  the shared `resolve_alias_source_id` (one resolution notion, not a fork) — it
  still covers a DECLARED surname the full-name-only prose scan skips.
- **Verification.** Deterministic (`scripts/test_teacher_name_guard.py`, 33/33,
  no cost): all req-8 cases flagged PROSE-ONLY (undeclared) — Wiersbe/Stedman/
  Wilson/Jenkins/Martin/Havner via Arm 2, Tozer via both arms incl. a heading;
  req-9 legit + theological-phrase traps not flagged; req-2 alias-gap not
  flagged; req-3 fail-closed; and four FP-class regressions (below). Regression
  `scripts/test_reference_verifier.py` 24/24 (shipped gate intact).
- **Live (offline harness, `scripts/verify_prose_scan_live.py`, reuses the Phase
  2 harness's real retrieval + generation; applies the SHIPPED guard + simulates
  the served outcome).** Alex chose a LIGHTER smoke (fab ×2 + legit ×1 = 18
  answers/run; ~$2-4 total across two runs, under Phase 2's ~$6). **The first run
  did its job — it found four Arm-2 regex false-positive classes that each caused
  a false denial on a legit answer:** possessive `'s` captured into the name
  ("Derek Prince's" failed to resolve — the TS1 Derek-Prince question refused);
  a token pair joined across a newline/heading ("Battlefield\n\nAccording"); a
  sentence-boundary span ("Prince. He"); and a leading function word ("As
  Prince"). Hardened the token grammar (strict WORD/INITIAL tokens, horizontal-
  whitespace-only joins, trailing-possessive strip, function-word filter) and
  regression-locked all four. **Second run after the fix: req 9 = 0 false denials
  (12/12 legit served clean, 19/19 full-name attributions grounded, 0 fired);
  req 8 = fabrications caught, 0 served with a false credit** (Guzik/MacArthur/
  Evans → regenerated clean; Roberts/Spurgeon/Havner/Finney → refused). req 10
  (multiple passes) reconfirmed Phase 0's intermittency (D2/S2 clean on some
  runs, fabricated on others).
- **req 6 — SURNAME SIZING (the extend/don't-extend evidence, smoke-level).**
  Across the 18 normal answers: full-name prose attributions grounded 28 /
  ungrounded 0; bare-surname attributions ungrounded 18 — but **surname-ONLY
  ungrounded (a surname credit whose full name is NOT also in the answer, i.e.
  the residual a surname scan would NEWLY catch) = 0**. Directional read: the
  observed surname exposure is fully covered by the full-name scan (every
  ungrounded surname co-occurred with its full name). **Caveat: this is a small,
  legit-dominant smoke sample, not a certification** — a larger pass is needed
  before treating "surname-only exposure is negligible" as settled. **Not acted
  on this session (req 7).**
- **planner-reviewer: APPROVE** (all five reqs met, no fail-open, no unbounded
  legit false-denial). Its two actionable findings were fixed before commit:
  **#2** broadened Arm 2's verb set (preached/believed/affirmed/stated/claimed/
  … — an out-of-corpus invention credited with a common speech verb otherwise
  slipped Arm 2); **#3** corrected a code comment that mis-cited CLAUDE.md's
  failure-mode ranking. **Disclosed residuals (fail-safe direction, not fixed):**
  (a) name-variant mismatch — a teacher retrieved as "Charles G. Finney" but
  credited "Charles Finney" is flagged; BOUNDED — regenerate-once under the
  permitted-name constraint fixes it, worst case a clean refusal, never a served
  false credit, and it is the SAME bound the shipped declared arm already
  carries; (b) Arm 2's verb/noun sets are finite (broadened, not exhaustive);
  (c) an undeclared, out-of-corpus name appearing ONLY in a bare markdown heading
  with no attribution verb is caught by neither prose arm (heading extraction was
  rejected — topic headings like "## Spiritual Warfare" would false-flag) — such
  names are, in practice, usually also DECLARED and caught by the declared arm
  (observed live: D2's Guzik/MacArthur/Evans).
- **Deploy-safety (assessed): SAFE to deploy** alongside the currently-unpushed
  Phase-2/buffer-then-verify stack. The change is additive and strictly
  restricting — it can only flag an ungrounded prose credit (→ regenerate/refuse),
  never grant a link, never alter answer text on the served path except via the
  already-shipped refuse/regenerate lever; no schema/DB/env/dependency change;
  fails closed everywhere; Python 3.9 clean (Invariant 1). Two extra bulk SELECTs
  per answer (`build_name_universe`) — negligible beside generation, flagged as a
  possible future cache. **Not pushed** — Alex decides deployment.

**Buffer-then-verify-then-playback + word-study latency fix (2026-08-02,
repo-only multi-step build; harness-row per Session Routing, run as orchestrator
+ `planner-reviewer` adversarial review gate before commit; zero DB writes —
retrieval reads + LLM generation only; build commit `9e5fe94`, this records
commit separate; NOT pushed — Alex decides).** Two pieces built together because
they pull against each other on latency.

**PIECE 1 — nothing unverified reaches the reader.** The normal answer path no
longer streams tokens as they generate (verification used to run *after* the
reader already saw the text, so a fabricated teacher credit stayed visible in the
prose with only its link denied — the Phase 2 residual, `ee3cff4`). `generate()`
now buffers the full answer, runs the Phase 2 grounding guard + `verify_references`
server-side, resolves any ungrounded attribution, and only then reveals the
verified answer as a paced typewriter playback. Change is `chat.py` only —
`reference_verifier.py` is byte-unchanged (Phase 2 guard intact) and the
**frontend is untouched**.
- **New helpers (`chat.py`):** `_stream_answer` (streams from Claude INTERNALLY
  into a buffer, forwarding ONLY `": keepalive"` SSE comment heartbeats so the
  proxy/client connection survives the ~40-55s silent buffer, yielding the result
  out-of-band); `_extract_answer_from_raw` (preserves the Phase 0 §7a guarantees
  on buffered output — never leak `<thinking>`/`<research_analysis>`, clean cutoff
  note only on `max_tokens`); `_ungrounded_reference_teachers`; `_playback_events`
  (byte-exact word-chunked reveal at `PLAYBACK_CHARS_PER_SEC = 250` — a steady,
  reading-comfortable rate, single tunable knob).
- **req 2 (failed-attribution handling) — decided: regenerate-once-then-clean-
  refuse.** On an ungrounded teacher credit in the served prose, regenerate ONCE
  constrained to the retrieved/permitted teacher names; if it STILL credits an
  ungrounded teacher, serve a clean refusal. Never surgically edits prose (no
  mangled sentences). The Phase 2 guard is NOT weakened — the constraint only
  narrows attribution, never widens; `verify_references` still runs.
- **req 1/4:** no answer byte is emitted before verification completes (heartbeats
  are SSE comments carrying no answer text; playback is strictly after verify);
  any generation/verification failure yields a clean error or clean refusal, never
  a partial. **Playback speed chosen: 250 c/s** (brisk, even, ahead of the reader,
  not a jarring instant dump). **During the wait the client shows its existing
  loading state, unchanged** (no tokens arrive until the first playback chunk; no
  new interstitial UI). **Frontend needed no change** — server-paced token events
  drive the existing renderer and the `data:`-only parser ignores the heartbeat
  comments (chosen over frontend-animated playback to avoid touching the Next.js
  16 frontend, per `frontend/AGENTS.md`'s "not the Next.js you know" warning). The
  **position-paper path is unchanged** (house voice, names no teachers, nothing to
  verify) — still streams live and fast.

**PIECE 2 — pre-generation latency.** Measured breakdown (req 5, before any
change): the ~18s Phase 0 flagged is NOT retrieval — it is the model generating
the hidden `<thinking>`/`<research_analysis>` blocks before the first `<answer>`
token (median ~17.7s, network-independent). **Rejected per req 7 (accuracy):**
trimming that reasoning (it is the self-verification pass guarding conflation/
misattribution, and there is no accuracy oracle to validate a trim — decision #4
HELD), a weaker model, retrieval caching. **Implemented (safe win):**
`is_word_study_query` dropped the over-broad bare phrase `"what does"`, which
false-matched ordinary "What does <teacher> teach…" questions and fired an ~8s
lexicon RPC (+ injected irrelevant lexicon context) — retrieval on that class went
**~10s → ~3s**, with a small accuracy *gain* (no spurious lexicon). `"what does
the word"` still catches genuine word studies.

**Verification (offline, zero DB writes).**
- **req 9 — no false credit reaches the screen: PASS (0/6).** teacher/long-
  context/short + the three Phase 0 fabrication-prone questions: every one served
  `[]` false credits. The revival case fabricated on first pass (Evan Roberts,
  Vance Havner) → **regenerated clean** (or, on a prior run, refused) — the false
  credit never reached the served prose either way.
- **req 8 — timing (before → after):** time-to-first-character **~24s → ~28-55s
  (median ~35s)** — roughly doubles, the accepted tradeoff for buffer-then-verify
  (nothing shows until full generation + verification, then playback). Total-to-
  full-answer comparable-to-modestly-higher. The lexicon fix visibly cut retrieval
  on the teacher question (3.3s vs 10s pre-fix). The dominant, req-7-protected
  ~18s reasoning is unchanged, so the wait genuinely rose.
- **req 10 — Phase 2 FP unchanged:** `reference_verifier.py` byte-identical, so the
  55-verified/0-false-denial result holds by construction; 5/6 verification
  questions needed no regeneration (legit attributions untouched).
- **`planner-reviewer`: APPROVE**, no req-1..4 violation, no landmine tripped
  (guard intact, fail-closed everywhere, playback byte-exact, Python 3.9 clean).
  Its one actionable item (**finding #1**: keepalives covered the two generation
  windows but not the post-generation verification window — a proxy drop there
  would lose a fully-generated answer) was **fixed before commit** (heartbeats
  added around the ungrounded-check and `verify_references`).

**Deploy-safety (assessed): SAFE to deploy, with one flagged scale caveat.** Change
is additive to the serving path, `chat.py` only, no schema/DB/env/dependency
change, fails closed, and the Phase 2 guard is untouched. Everything unverified is
withheld; failures serve clean errors/refusals. **Flagged, non-blocking at current
zero-user scale (planner-reviewer #2):** `time.sleep` in the sync generator (the
playback pacing + heartbeat cadence) holds one anyio threadpool worker for the
request's duration (~generation + ~10s playback); at ~40 concurrent chats the
shared pool (cap 40) could starve other work — revisit before real traffic (e.g.
async pacing). **Known residual (planner-reviewer #3, pre-existing, unchanged):**
the guard keys on the model's own `<reference_mentions>` self-report, so a teacher
credited in prose but omitted from that block is invisible — identical to Phase 2,
not widened here. **Not pushed** — Alex decides deployment separately; it would
deploy alongside the already-live Phase 2 (`ee3cff4`) and the three earlier fixes.

**Phase 2 shipped — teacher-name guard: retrieval-grounded naming on the
answer path (2026-08-01, repo-only multi-step build; harness-row per Session
Routing, run as orchestrator + `planner-reviewer` adversarial review gate
before commit; zero DB writes — retrieval reads + LLM generation only; build
commit `ee3cff4`, this records commit separate).** A named teacher earns a
"verified" study-panel link ONLY if that teacher's material was actually
retrieved for that specific question. Closes the Phase 0 `in_corpus_not_
retrieved` hole (§1c): a teacher who resolves to a real servable source (so the
pre-existing `verify_teacher_mention` passed it) but whose source was never
retrieved rendered as a **verified link on unused material** — the A.W. Tozer /
Bevere symptom. **Claim-level A2 misattribution (a claim from retrieved teacher
A credited to retrieved teacher B) is explicitly OUT of scope** — no
"was-it-retrieved" check can catch it (Phase 0 §4a; planner-reviewer finding #1,
a stated residual).
- **Mechanism** (`backend/app/services/reference_verifier.py`): `RetrievalGrounding`
  (source_ids + author_keys + `established`) built by `build_retrieval_grounding(chunks, db)`
  from the exact chunk set the model saw. `verify_references`/`verify_teacher_mention`
  now take a **REQUIRED** `retrieved_grounding` param — a caller cannot skip the
  gate by omission (TypeError before any DB call, the Invariant-10 discipline).
- **Requirement 1 (key on retrieved IDENTITY, not alias resolution):** grounding
  carries both the retrieved documents' `source_id`s and the normalized retrieved
  chunk authors. The author-name arm keeps a legitimately-retrieved teacher with
  NO `source_aliases` row (Andrew Murray, the alias-gap Landmine) from being
  mis-flagged.
- **Link gate is source-id arm ONLY** (`_link_source_retrieved`): a verified link
  points at the alias-resolved source, so that source must have been retrieved.
  The author-name arm is used for DETECTION only (`_is_retrieval_grounded`), NOT
  the link decision — using it for links would grant a link to a not-retrieved
  source B whenever a *different* retrieved source A shares a normalized author
  name (a homonym collision). **This split is the fix for the one actionable
  planner-reviewer finding (#2), a genuine fail-open in the exact class the guard
  prevents; it is closed and regression-tested.**
- **Requirement 3 (fail closed):** `build_retrieval_grounding` returns
  `established=False` on any `documents` lookup failure; `established=False`
  denies every teacher link. Verse verification is untouched (Scripture is
  permitted from model knowledge). No fail-OPEN path survived the review (the
  01ca912-shape hole is not reproduced).
- **Requirement 4 (blocked-attribution handling) — decided: clean LINK denial.**
  The ungrounded name renders as plain text, no verified pointer. NOT text-surgery
  (mangles sentences; also impossible post-stream), NOT regenerate/whole-answer
  refusal — the answer is streamed token-by-token and fully delivered *before*
  `verify_references` runs (`chat.py:1015/1117`), so the only post-stream lever is
  the `verified_references` linkification metadata; buffering every answer to
  enable regeneration/refusal abandons the token stream for a ~40s perceived-
  latency hit (Phase 0 §6), disproportionate to an intermittent low-single-digit
  issue and out of "retrieval-grounded naming only" scope. Residual (reviewer #3,
  disclosed): the misattributing *prose* still stands on a correct denial (as
  Wiersbe's does today) — removing already-streamed text needs a buffer-then-serve
  change, the deliberate follow-up; the guard already *detects* all three
  mechanisms so that follow-up has its signal.
- **Verification.** Deterministic (`scripts/test_teacher_name_guard.py`, 12/12,
  no cost): Tozer DENIED + CONTROL (grounding is the sole differentiator),
  nested-quote DENIED, pure-invention DENIED, Murray grounded-by-name (no
  false-flag), fail-closed denies all, homonym hole closed, structural TypeError
  on omission. Regression (`scripts/test_reference_verifier.py`, 24/24, updated to
  the required-param signature). **Live (requirements 5 & 6),
  `scripts/verify_teacher_name_guard_live.py`:** reproduces `chat.py`'s full
  retrieval + generation offline (real author-cap + Cohere rerank + neighbor
  expansion + background injection — the fabrication mechanism Phase 0 §0 named),
  applies the SHIPPED guard, 36 answers (3 fabrication-prone ×4 + 12 legit ×2 —
  variance per requirement 6). Result: **55 legitimate teachers VERIFIED, 0
  false denials (0 CONSERVATIVE-DENY), 0 fail-closed events**; all 29 fabrications
  link-less (incl. the Phase 0 Ray Stedman and Vance Havner re-firing, plus the
  full Precept-Austin-quoted cast). The intermittent Tozer `in_corpus_not_retrieved`
  class did not re-fire in these 36 runs (a single Phase 0 occurrence) — it is
  proven caught by the deterministic PRIMARY test, not the live sample. Two live
  "mismatches" (G1: Murray/Prince) were the pre-existing SP1 **presence** guard
  (full name in `<reference_mentions>` but the answer prose used the short form),
  not the grounding guard — the harness now attributes presence-drops explicitly.
  **Cost:** ~$4 total across the (killed-and-relaunched) runs, under the ~$6
  Alex approved and the $50 ceiling.
- **Deploy-safety (assessed): SAFE to deploy alongside the three currently-unpushed
  fixes.** The guard is additive and strictly *restricting* — it can only remove a
  verified link, never grant a new one, never alter answer text, no schema/DB/env
  change, no new dependency. It fails closed. It shares `chat.py` with the
  Phase 0 §7a token-budget fix (`0ab9c60`) and the position-paper items, but
  touches a different, later point (post-generation `verify_references` wiring) and
  the `reference_verifier` module those do not touch; the required-param change is
  contained to callers all updated in this commit (grep-confirmed, reviewer
  angle 6). Live run shows zero false denials on 55 legit attributions, so it will
  not suppress legitimate teacher links in production.

**Phase 1.4 closed — normal answer path no longer treats
tongues-as-initial-evidence as a debate (2026-08-01, repo-only, plain/direct
terminal session, zero DB writes; build commit `813ae7b`, this records commit
separate).** The position-paper router was hardened for Alex's 1 Aug tongues
ruling in `01ca912` (items 1.5-1.7); this closes the OTHER code path — the
normal-answer system prompt (`backend/app/system_prompt.txt`), the sole
remaining site (confirmed by a repo-wide sweep) that still listed "whether
tongues is the required initial evidence of Spirit baptism" among the in-house
debates. Two edits: **(1)** removed that item from the in-house debate list —
the three genuine debates (healing mechanics, prophetic accountability,
apostolic authority) plus sanctification/eschatology remain; **(2)** rewrote
the tongues settled-conviction bullet to state the house position —
normal/expected accompanying sign, NOT required initial evidence, absence does
not disqualify — worded to match the shipped tongues position paper
(`sources/documents/speaking_in_tongues.md`) so the normal path and the
position-paper path say the same thing. The guardrails text
(`theological_guardrails.txt`) carried no debate list and was untouched;
background-topic injection is DB-driven and injects the same house-position
paper text, not a debate list. **Proven via the normal answer path**
(`generate_real_answer`-shaped runner: real retrieval + real
`ANSWER_SYSTEM_BLOCKS` + `claude-sonnet-4-5`, direct calls that bypass the
`/chat` position-paper interception, so it exercises the normal path
specifically — and note the canonical tongues question is intercepted by the
position-paper path through the live endpoint, so testing the normal path for
it *requires* this direct call). Same 4 questions and retrieval, before vs.
after the edit: BEFORE, the tongues question answered as a staged two-position
debate ("This is a genuine in-house debate... teachers differ", Michael Brown
vs. Derek Prince, "come to your own conviction"); AFTER, it answers as the
house position ("No — speaking in tongues is not required as initial
evidence... its absence does not disqualify... normal and expected
experience"), no debate framing, and it reframes the same two teachers as
supporting the house position. The three genuine debate topics still present as
debates in both runs (apostolic + prophetic name teachers on multiple sides;
healing presents the range but names no individuals in either run — a
thin-citable-corpus retrieval artifact identical before and after, not a prompt
effect). **Cross-path consistency checked:** tongues = house position, and the
three debates = debates, now agree between the normal path and the
position-paper router (`STANDING_DEBATE_CONTRASTS` = exactly those three,
tongues never among them). **CLAUDE.md decision #10's conflict flag cleared** —
the flag named only the normal-path system prompt, its condition is now false,
so it was removed per the eviction rule (the settled decision itself retained).
The session's before/after runner lived in the scratchpad (not committed); the
repo's own `sp1_answer_harness.py` is stale (imports a renamed `_get_anthropic`
that no longer exists in `chat.py`) and was left untouched — the runner inlined
the current-symbol equivalent rather than modify a committed helper.

**Phase 1.5/1.6/1.7 fixed — position-paper router no longer over-matches
(2026-08-01, repo-only, harness session — executor + planner-reviewer;
build commit `01ca912`, this records commit separate).** Pulled forward on
Alex's ruling, same day as the Phase 0 measurement pass that confirmed it
live (`docs/audits/phase0_measurement_2026-08-01.md` §7b). Three confirmed
symptoms, one root cause: `match_position_paper()` in
`backend/app/services/position_papers.py` intercepted questions it
shouldn't have — a healing/faith question and a "hearing God's voice"
question hijacked into the `speaking_in_tongues` pillar; teacher-named
questions (verified live on Derek Prince and Zac Poonen) intercepted before
the system registered a teacher was named, erasing the teacher entirely;
"can a believer lose their salvation" answered as settled
baptism-of-the-Spirit teaching on a margin under two thousandths between
two phrasings of the same question. **Fixed structurally, not per-symptom**
(the report's own finding was that adding the tongues pillar had silently
broken baptism's routing on three other topics previously — per-pillar
patches don't generalize): two deterministic hard-veto gates
(`_mentions_named_teacher`, `_is_retrieval_intent`) run before any
embedding call and can't be overridden by a pillar's score; a shared
`STANDING_DEBATE_CONTRASTS` list (healing mechanics, prophetic
accountability, apostolic authority — Alex's 1 Aug ruling that these stay
live debates, never settled house teaching) is merged into *every* pillar's
contrast score at match time, not copied per pillar, so a third future
pillar inherits the protection with zero new code; two targeted contrast
anchors (`BAPTISM_CONTRAST_SALVATION`, `TONGUES_CONTRAST_COMMUNION`) close
two genuine anchor-vocabulary contamination cases the same way two prior
2026-07-31 fixes in this file were done (a new contrast anchor, never an
edit to a positive anchor's wording); `MIN_QUALIFY_MARGIN = 0.008` replaces
a bare `pos_sim > contrast_sim` check, calibrated between the real
documented legitimate floor (+0.0113) and the contamination margins found
live. **A planner-reviewer pass caught and this commit includes the fix
for a real bug the first implementation had:** `_mentions_named_teacher`
originally failed *open* on a `source_aliases` load failure (silently
disabling the teacher-name veto — CLAUDE.md ranked failure mode 2, worse
than a generic answer); now fails *closed* (every question treated as if
it might name a teacher, deferring to the normal citation path), verified
directly under a simulated load failure. The reviewer also flagged that
the three debate-topic test cases passed for an unrelated reason (raw
similarity already below threshold) and didn't prove
`STANDING_DEBATE_CONTRASTS` was wired in at all — a direct mechanism check
was added (`scripts/test_position_paper_routing.py`) confirming it's the
binding, highest-scoring contrast for the healing probe, not dead code.
**Verified live** (real OpenAI embeddings, not simulated): all three
reported hijacks (H3, G2, T4), three teacher-named questions across two
teachers and both pillars, both salvation phrasings, and all three debate
probes on both pillars now correctly return no interception; T1-T3 and the
known thinnest legitimate case (P1, baptism) still route correctly.
15/15 in `scripts/test_position_paper_routing.py`. **Scope:** only the two
shipped pillars were hardened, per the session's own instruction — nothing
was built for the six unfiled drafts in `docs/position_papers/`.
`chat.py` needed no change (`match_position_paper`'s call site is
unchanged; confirmed its diff against this session's start is empty — the
only other `chat.py` changes on `main` today are the separate, already-
committed Phase 0 §7a session below, not this one). **Not closed by this
session:** CLAUDE.md's Invariant/decision #10 conflict flag (the live
*normal-path* system prompt/guardrails text still lists "whether tongues is
the required initial evidence" as an in-house debate) is a different code
path (`chat.py`'s system prompt, not the position-paper router) and a
different piece of Phase 1 item 1.4 — **since closed** by the Phase 1.4
session above (build commit `813ae7b`; CLAUDE.md decision #10 flag cleared).

**Phase 0 §7a token-exhaustion degradation fixed — no scratchpad, no answer
truncation on `/chat` (2026-08-01, repo-only, plain/direct terminal session,
zero DB writes; build commit `0ab9c60`, this records commit separate).** Pulled
forward ahead of the rest of Phase 1 on Alex's ruling. The Phase 0 measurement
(`docs/audits/phase0_measurement_2026-08-01.md` §7a) found ~27% of long-context
normal-path answers exhausted the 1500 `max_tokens` budget *inside* the hidden
`<thinking>`/`<research_analysis>` blocks before `<answer>` completed — measured:
`<thinking>` alone consumed up to ~1340 tokens (87% of budget), so the visible
answer was starved, not the cause. Two failure modes reached users: a mid-sentence
truncation, and — worse — raw reasoning scratchpad (no `<answer>` block; the old
`if not answer_parts:` fallback streamed `raw_full` verbatim). Three changes in
`chat.py` `generate()`: **(1) hard guarantee** — the no-`<answer>` fallback never
emits raw model output again; if the raw output carries any reasoning tag it IS
scratchpad → serve a clean honest fallback, regardless of budget (structural, not
probabilistic); **(2)** `max_tokens` 1500 → 3000 (headroom for reasoning + a full
answer + `<reference_mentions>`); **(3)** capture `stop_reason` and append one
clean cutoff sentence if `<answer>` opened but hit the ceiling before `</answer>`
(gated on `stop_reason == max_tokens` so a normal `end_turn` is never
mislabelled). **Proven** offline against a verbatim reproduction of the fixed
streaming logic (SELECT-only): (A) all 7 Phase 0 degraded questions forced to
exhaust at `max_tokens=180` → model produced scratchpad but **0/7 leaked**, all
served the clean fallback; (B) all 7 re-run at 3000, twice each → **14/14 render a
complete clean `<answer>`** (`stop_reason=end_turn`), 0 leaks. **Cost:** raising
the cap costs more only for answers that previously truncated (they now complete,
~+700 output tokens ≈ +$0.01 each; already-clean answers stop naturally under 1500
and are unaffected) — blended ~+$0.003/answer. Only `chat.py` has this
`<answer>`-extraction + raw-fallback shape; `position_papers.py` (2048) and
`study.py` (400) stream plain prose with no hidden blocks and were correctly left
untouched. **Pushed to Railway 2026-08-01** (Alex's call): `git push origin main`
sent this fix (`0ab9c60`) plus the day's committed backlog through `6e48b9e` (10
commits). The only other `backend/app/` runtime change in that push is the Phase
1.1/1.2 concurrency fix (`9fdf8d2`) — both `/chat` fixes are now live-deploying;
the position-layer commits in the same push touch only `scripts/`+`migrations/`
(dormant, not imported by the backend; migrations 076/077 already applied to the
live DB, so no schema drift). Railway auto-deploys from `main`; **build health not
confirmed from this session** — the Railway CLI is present but unauthenticated
(`railway login` needed to poll). First time this fix runs against the real
endpoint (it was proven offline against a verbatim reproduction). The
position-paper over-matching (Phase 0 §7b, plan items 1.5–1.7) was a separate
concurrent session, **since landed** — see the entry above; not touched here.

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
whether or not its material was retrieved — is **now closed for the
retrieval-grounding piece** (Phase 2 shipped `ee3cff4`, 2026-08-01, see Current
state: a name earns a verified link only if its material was retrieved for the
question). The narrower residual — a name whose material *was* retrieved but the
specific claim actually came from a *different* retrieved teacher (the A2
Brown/Kolenda class) — is deliberately still open; no deterministic
"was-it-retrieved" check can catch it. Full
plan folded into PLAN.md (active phase sequence) and CLAUDE.md (ranked failure
modes + 12 settled decisions, conflicts flagged inline). **Phase 0 (read-only
measurement) and Phase 1 (live contradictions) are the queued next sessions;** the
position-layer live cutover is reframed to post-launch (PLAN.md #48). No code, no
DB this session — records only.

**Proposition generation — resumed, current.** Runs on the bypass-proof v3.1
path (named-teacher extraction; provenance stamping structurally required,
CLAUDE.md Invariant 10). The corpus-wide backfill (PLAN.md #17/#49) completed
2026-07-30, and the last residual documents were extracted **2026-08-02 — 0
genuine backfill documents now remain** (the JSON-escaping defect — a
model-emitted unescaped quote inside a nested scripture quotation, present in
v3/v3.1 alike — is fixed with `_repair_unescaped_quotes`, build `05aa519`; the
book-length pair went through the multi-call `process_book_document` path).
Processed/remaining totals: query live.

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
  starves other work. Harmless at zero-user scale; MUST be fixed (e.g. async
  pacing) before real traffic.

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

**17. Live unbacked quote guarantee shipping — HIGH PRIORITY (copy-fix session
next).** `frontend/app/home/page.tsx` (~L492) states, present-tense: "Every quote
is checked character-for-character against the source before it can appear — a
quote cannot exist in Rhemata unless the teacher actually said it… Rhemata
structurally can't." No mechanism backs it (B5). This is a recurrence of the
`/sources` landmine on a separate component — POSITIONING.md (L76/L145), `/sources`
(L43), and `docs/how-rhemata-handles-sources.md` (L19) are already roadmap-framed;
the home page is not. Fix must sweep EVERY surface in the same session. Report-only
2026-08-03.

**18. Bevere marketing line + empty-but-servable source — HIGH PRIORITY (same
copy-fix session).** The home page markets "John Bevere" as a "trusted modern-day
teacher"; live query 2026-08-03 = 0 documents, 0 propositions (deleted 2026-07-25),
but the `sources` row (`unlicensed`/`shown`) + 5 aliases remain → an empty author
page / verified-link-to-nothing, and a living-minister misrepresentation (failure
mode 2). Decide: remove the marketing line and/or dark the empty source. Report-only
2026-08-03.

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
