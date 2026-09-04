# New Wine Roadmap — Later and Dormant Work

This file preserves work that matters but is not authorized by the current
private-beta blocker queue. Read `PLAN.md` first. Historical and superseded
reasoning lives in `docs/plan-archive.md`.

Every entry here must be one of:

- **Scheduled:** assigned to a named later phase.
- **Triggered:** dormant until its concrete condition occurs.
- **Parked:** acknowledged, with no current work authorized.

There is no unlabeled open-concern category. Blockers never live here; Alex
promotes them into `PLAN.md` through the rule in `AGENTS.md`.

## Scheduled

### Product track — B1-B7, after the web-article launch gate

This track may run concurrently with later corpus production after W8 passes.

1. **B1 — Freeze the private-beta product contract.** Alex approves testable
   criteria for audience, entry path, answer flows, honest-empty behavior,
   citation/source navigation, study panel, account boundary, feedback, privacy,
   and explicit non-goals.
2. **B2 — Complete the core user journey.** A beta user can enter, ask, receive
   an honest guarded answer, inspect citations/evidence, reach named teachers or
   Scripture, and recover from expected terminal states without a dead end.
3. **B3 — Finish study, source, and outward navigation.** The Inline Study Panel
   gets an authenticated production pass; citations and teacher/source targets
   work on supported mobile and desktop sizes. Swipe-only remains the default
   unless Alex explicitly reopens drag-to-follow.
4. **B4 — Complete beta administration and supportability.** Contributor states
   are actionable, account deletion is real and verified, admin navigation is
   usable, and support can identify failures without database guesswork.
5. **B5 — Security, privacy, and abuse readiness.** Guest limits,
   authorization, deletion, retention-sensitive data, logging hygiene, secrets,
   and common abuse paths are tested; no unresolved high-severity issue remains.
6. **B6 — UX, accessibility, and performance pass.** Core flows pass supported
   mobile/desktop browsers and WCAG essentials; measured regressions are fixed
   or explicitly accepted; copy does not imply unsupported authority,
   certainty, or corpus completeness.
7. **B7 — Product release candidate.** Agreed journeys pass in a production-like
   environment; monitoring, response, rollback, and support ownership exist;
   known non-blockers have consequences and revisit triggers; deployment still
   requires Alex's explicit approval.

### Frontend polish — staged answer-loading treatment

**DONE and live — the final single-phase treatment shipped 2026-09-03
(`bad58f6`, revised by `b666134`).** The ring is replaced by one compact row
that advances through five truthful phases in the answer path's real order of
work. Only the active phase is rendered, with a reduced-motion-safe spinner;
completed and upcoming phases do not accumulate on screen. Timing still uses
explicit `STEP_ONSETS_MS` (0 / 1.7 / 4.9 / 9.5 / 18.4s), so the final phase is
reached inside the ~20s median, and answer arrival remains the only completion
signal. The visible phase is also the single polite, atomic status
announcement. No percentage, meter, or fabricated source count is rendered.

**Still open — the footer half of this entry has not been built.** In the
completed-answer footer, keep the thumbs-up/down controls left-aligned
on their own row directly above the Sources disclosure. Treat feedback and
Sources as one compact footer group: use a tight gap between those two rows,
retain the existing usable touch targets, and let the larger separation occur
between the answer content and the footer group. Do not place feedback opposite
Sources in a shared horizontal row or leave the feedback controls floating in
open vertical space.

### Remaining corpus track — A1-A6, after the web-article proof

Production writes use deterministic, resumable scripts in an attended primary
Codex session. Each source follows: legal/source approval, immutable inventory
and checksum manifest, parser fixtures, dry run, one isolated real write,
reconciliation and sampling, bounded resumable batch, independent database
reconciliation, representative answer/evidence review, then acceptance or
quarantine. No stage transfers automatically from one source to another.

1. **A1 — Beta corpus manifest.** Define minimum teacher/source/content-shape
   coverage; re-query live state; classify candidates; fix order, sampling,
   expected counts, cost/storage estimates, and quarantine path.
2. **A2 — New Wine.** Scheduled and explicitly resumed by Alex. The trigger
   opened on 2026-08-25: a 12-call blind benchmark covered severe-failure pages
   4 and 31 plus good controls 3 and 10 from Issue 02-1973; all results
   reconciled with no retry, actual list-price cost was $0.06754230, and Alex
   accepted Candidate C. Candidate C was then revealed as Gemini
   `gemini-3.7-flash`. The immutable report, manifest, review, and accepted
   decision are in
   `docs/audits/2026-08/new_wine_ocr_benchmark_2026-08-25/`. The approved
   no-write Issue 02-1973 run completed on 2026-08-25 under the $1.25 ceiling:
   all 32 pages passed OCR review, page 15 used the single allowed repair, and
   17 exact-text article candidates reached fresh whole-issue review. That
   review correctly quarantined the issue before proposition extraction: it
   found the omitted `THE APOSTLE—GOD'S MASTER BUILDER` article and missing
   page continuations in two Health and Healing candidates. Reconciliation was
   32 pages / 17 articles / 0 propositions, with zero database writes; the
   conservative cumulative provider-spend bound was $1.08638205. Validated
   terminal artifacts remain local-only and intentionally untracked under
   `docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-25_retry_13/`
   because the Git remote is public.
   **2026-08-27 (pipeline correction, not yet a clean pass):** root-caused
   and fixed the article boundaries defect (segmentation silently stopped
   54% through the issue at low reasoning) plus five further defects found
   through live validation the same day — a full-coverage check, an
   explicit `non_article_spans` mechanism, three rounds of size/fraction
   caps closing gaming patterns the model found live (including one that
   slipped past the semantic reviewer: a single article spanning the whole
   issue), a reasoning bump low→medium→high, strengthened instructions
   requiring fine-grained decomposition, and a per-page OCR cache (all 32
   pages of this issue now cached, $0 OCR cost per retry). 9 commits,
   `37e2746`..`683b973`, 213/214 tests passing. 21 live attempts run
   (~$0.87 confirmed spend, real total likely $1.2–1.5 — the pipeline
   doesn't record cost from a call that raised after being billed).
   **2026-08-27, later same day: two of the suspected recurrence causes
   diagnosed and fixed (commits `d011fac`, `ae37d3b`).** Two standalone
   segmentation-only diagnostic calls against the cached transcript (no CLI,
   no OCR cost) showed `non_article_span_implausibly_large` was not a
   cap-sizing problem: "Keeping the Unity" (a reprint) and "New Wine Forum"
   (a reader Q&A column) were consistently misfiled as non-article material
   instead of recognized as articles — the same two articles the semantic
   reviewer had already confirmed real in `e8ca4a3`. Fixed via explicit
   instruction wording (`d011fac`). Separately, a real live-CLI defect —
   `article_spans_overlap` firing on a genuinely non-overlapping article set,
   3 of 4 real attempts — was root-caused to an ordering bug (the check
   compared each article only to the previous one in the model's raw return
   order instead of sorting by position first) and fixed to match the
   coverage check's existing pattern (`ae37d3b`).
   **Issue 02-1973 still has not cleared the article gate end-to-end** — the
   recurrence is dominated by run-to-run model variance, not one
   deterministic gap. Live samples after both fixes still hit a fresh
   `non_article_span_implausibly_large`, a stochastically inconsistent
   semantic-reviewer stage (`article_failure_reasons_invalid` on an
   identical input twice, then a clean pass on a third identical attempt),
   and one confirmed new risk: a passing review once approved "Spiritual
   Potpourri," a 27K-char span merging real Forum content with what look
   like separate advertisements under one invented title, uncaught by any
   check. Full detail: `rhemata-status.md`'s 2026-08-27 entry and CLAUDE.md's
   New Wine landmine entry.
   **2026-08-27/28 (further diagnosed, two more real causes fixed,
   `d5420e3`, `4bad5b5`):** a `foreign_article_title_in_span` defect (a
   span opening mid-sentence with a different article's own title bleeding
   in) and a second distinct `non_article_span_implausibly_large` cause
   (the "New Wine Forum" reader Q&A column's own continuation mislabeled
   as three separate fake `advertisement` spans, zero commercial language
   in any of them) were both root-caused and fixed. 86 existing unit tests
   still pass; live re-checks show reduced but not eliminated recurrence.
   **Issue 02-1973 still has not cleared the article gate end-to-end** —
   the remaining live failure is a large non-article dump absorbing part
   of "The Apostle" article, plus continued `article_implausibly_long`/
   title-bleed variance. Full trail: CLAUDE.md's New Wine landmine entry.
   **2026-08-29: two more segmentation redesigns proposed and refuted the
   same day, before Alex saw either one.** A chunked/windowed redesign
   (`15f6b1d`) was refuted on measurement: its premise (positional
   grounding degrades late in a long transcript) was directly falsified —
   every proposed boundary in the back 40% of the transcript sat within 31
   chars of a real page marker. A table-of-contents-anchored redesign was
   drafted with per-claim evidence tags specifically to avoid that mistake,
   proactively adversarially reviewed before being shown to Alex, and was
   refuted anyway: a claim tagged verified was false (Issue 02-1980 does
   have a ToC, a 7th distinct format across issues examined), the proposed
   article-end marker doubles as a real subscription-form checkbox in the
   same issue, the discontiguous-span schema had no algorithm that would
   ever populate more than one span, and it contradicted an already-shipped
   instruction (`d011fac`) for Forum-style panel columns. Full detail and
   the properties any future design must satisfy:
   `docs/superpowers/specs/2026-08-29-new-wine-chunked-segmentation-design.md`
   and `docs/superpowers/specs/2026-08-29-new-wine-toc-anchored-segmentation-v2.md`.
   **Separately, discovered the segmentation MODEL itself was never
   actually benchmarked for this task** — `openai/gpt-oss-120b` was a
   forced substitution when Groq retired the prior default, unlike OCR,
   which got a real blind benchmark before a model was chosen. A live
   comparison call (Claude Opus 5, same transcript/schema/deterministic
   validation) produced the first clean pass on Issue 02-1973 recorded
   across the whole A2 effort — correctly discontiguous "The Apostle,"
   correct reprint attribution for "Keeping the Unity," an honest
   collective label for the Forum panel instead of a fabricated single
   author. One run only, not proof of reliability. The test overran its
   approved $1 budget (confirmed $1.4776 + an unmeasured ~$1 estimate from
   a failed attempt) debugging real SDK/schema mechanics against the full
   transcript instead of a cheap dummy request first — recorded in
   CLAUDE.md's Landmines.
   **2026-08-29, continued: Grok-collaborative design pressure-test
   (v1.1→v1.4) plus a $3 live Opus 5 test, both closing this same day.**
   Five rounds of zero-cost fixture-testing against real Issue 02-1973 data
   refined a folio-mapping hatch procedure, a jump-resolution algorithm, and
   marker-exclusion semantics — real defects found and fixed each round,
   none yet implemented in `articles.py`. Full trail:
   `docs/audits/2026-08/new_wine_free_checks_2026-08-29.md`. Separately,
   Alex approved a $3 live test: Claude Opus 5 segmented the full transcript
   through the real, unmodified `segment_articles()` and passed every
   production gate — 10 articles, 24 non-article spans, zero failures,
   correctly handling every previously-failing hard case (both interrupted
   articles, the Keeping the Unity reprint credit, the New Wine Forum
   panel). A second clean pass, moving past n=1. Real usage logged: 52,930
   in / 53,125 out tokens, $1.5928 of the $3 ceiling. A real bug was found,
   not fixed: `segment_articles()` hardcodes the manifest's
   `segmentation_model` to a module constant regardless of which client
   actually ran — this test's own result carries a false provenance stamp.
   Full trail: `docs/audits/2026-08/new_wine_opus_segmentation_e2e_test_2026-08-29.md`.
   Article review, proposition extraction, and the v1.4 design remain
   untested — Issue 02-1973 is still not ingestion-ready. Next model-choice/
   architecture decision is Alex's, not pre-selected; no further live-call
   spend without a fresh named ceiling. No benchmark decision or pipeline
   fix authorizes a database write or file move.
3. **A3 — Existing converted sources and missing combinations.** Reconcile
   Ravenhill, Savchuk, and Poonen visibility/content; preserve the distinction
   between candidate and approved quote; keep the 12 HelloAO missing
   book/commentary combinations quarantined unless a chapter-level contract is
   separately approved.
4. **A4 — Reference datasets — IN PROGRESS.** Biblical-depth Phases 0–8 and the
   verified 20-item hidden TIPNR production pilot merged through PR #3 at
   `ff89ba5` and deployed successfully with the feature default-off; the
   ingestion-ready foundation benchmark is met. Phase 6's attended production
   proof remains exactly one
   hidden `H0175` document, embedded chunk, and current `general_context` policy
   row with no proposition and zero vector/FTS matches. Phase 7's frozen
   full-artifact inventory remains eligible `3,959`, malformed `172`, skipped
   `115`, prohibited `16`, duplicate `0`, with eligible checksum
   `1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2`
   and inventory hash
   `edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040`.

   Phase 8 deterministically selects the first 10 eligible people and first 10
   eligible places by entity ID after excluding `H0175`. Its selection checksum
   is `398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b`;
   packet hash is
   `a48f506a38db740d4d2cd8648c8de95ac7c25cb4550916e236a023738184a1e8`;
   zero-effect preview payload hash is
   `4171181b7003317044edafb8eeb836de7596f795489ba1bc8faafac72d716237`.
   The packet renders 5,463 UTF-8 bytes, conservatively estimates 1,821 tokens
   and USD `0.00003642`, and freezes exactly 20
   `text-embedding-3-small` requests under a USD `0.01` maximum ceiling. Its
   fixed sample is `G0010`, `G0132`, `G0223J`, `G0009`, `G0137`, and `G0494`,
   with sample hash
   `ad2299d96582635f151b885d59f09b722297a10ab00354a46ddd5145c4041515`.

   Preview is network/model/database-incapable. Read-only preflight requires
   exact `H0175` verification plus a unanimous all-clean or all-exact-complete
   candidate state. Apply requires an exact same-day approval, validates all 20
   vectors before opening the write connection, and limits the write to one
   atomic transaction containing 20 documents, 20 chunks, and 20 current
   policies; it neither inserts nor updates the existing source, alias, or
   `H0175`. Fresh reconciliation requires all 20 exact-complete rows, zero
   propositions, and zero matches across 20 vector plus 20 FTS probes.

   The first authorized apply attempt committed no rows but did not preserve
   request counters, so its embedding count is conservatively bounded at 0–20
   under its separate USD `0.01` ceiling. Commit `643c9f1` added structured
   counters and immutable attempt evidence. An authorized rollback-only probe
   exposed a UUID/text completion-stamp mismatch; commit `59dd15d` fixed the
   cast, and a corrected probe staged all 60 rows, made zero model calls, rolled
   back, and left all candidates clean. A separately authorized fresh retry
   then completed exactly 20 `text-embedding-3-small` requests under USD
   `0.01` and committed one atomic transaction containing 20 documents, 20
   chunks, and 20 current policies. Coupled and independent reconciliation both
   passed at attempted `20`, stored `20`, errored `0`, skipped `0`, with zero
   propositions and zero matches across all 40 probes. The final immutable
   evidence file hash is
   `d4ddf85fa2e79f037f15faf2555cc2ea60024fbf3aed520d66a150aabe0a6df5`.

   Deployment verification passed on `ff89ba5`: Vercel was Ready, all four
   Railway services reported `SUCCESS`, the API and website smokes returned
   HTTP 200, and `BIBLICAL_CONTEXT_ANSWER_ENABLED` remained unset on both the
   API and answer worker. The source remains hidden, protected/plural registries
   remain empty, and Phase 4's routing, cache, neighbor, plural-source, and
   house-fence boundaries remain unchanged. The remaining **3,939** eligible
   TIPNR items (not 3,938 — the Phase 6 `H0175` row is a reduced fixture, never
   the artifact record; CLAUDE.md landmine, 2026-09-02) require a separately
   designed, costed, reconciled, and attended packet; the pilot grants no
   automatic authority. Visibility change, feature enablement, live answers,
   doctrinal assignment, and registry assignment remain separately
   unauthorized.

   **Full-batch tooling residuals — Scheduled inside A4, from the 2026-09-03
   working-tree review.** The writer now re-asserts the hidden, licensed
   source on the writing cursor before staging any row (`2149239`); the
   rollback-only probe must be re-run on that code before the first real
   batch, since the 2026-09-03 probe predates it. Seven findings were not
   fixed and none blocks the run, but two weaken the run's own reporting:
   (a) `finalize_batch` labels a definitively zero-write failure (e.g. an
   embedding error before any connection opens) as
   `commit_outcome_unknown_reconciliation_failed`; (b)
   `reconcile_tipnr_full_batch.py` validates `--global` only after loading
   the DB factories and never passes `noneligible_document_ids`, so
   `reconcile_global`'s `excluded_identity_present` check is unreachable from
   the CLI — trust the independent read-only reconciliation counts, not the
   apply script's own label, and treat the excluded-identity check as unrun.
   The rest: preflight buckets fetched chunks by `document_id`, so an orphan
   chunk carrying an expected id under another document reads as `clean`
   (the write's own precheck/PK would still refuse it); the hidden-retrieval
   probe's `CROSS JOIN LATERAL match_chunks(...)` depends on the planner
   restricting `chunks` first, under a 120s timeout; `resolve_batch_vectors`
   embeds 3,939 items one call at a time when `embed_batch` already
   sub-batches 100; preflight refetches every source document's `full_text`
   about five times per apply; and the 120-test suite skips wholesale when
   `TIPNR_TEST_ARTIFACT` is unset, exiting 0 with zero coverage on any
   machine without the untracked 7.9 MB artifact.
5. **A5 — Public-domain books and Pentecostal archives.** Verify publication
   status per title; preserve edition/page provenance; quarantine OCR or
   structural failures; do not extract quotes from flat book chunks without
   trustworthy body/apparatus and chapter boundaries.
6. **A6 — Owned verse-anchored synthesis.** Not eligible until enough source
   material exists and Alex approves a specification for provenance,
   attribution, doctrinal review, versioning, and serving boundaries.

**Corpus acceptance:** required coverage or honest-empty behavior exists; every
source has current legal/visibility/attribution evidence; every batch has
immutable identity, resumable logs, reconciliation, and sampled quality proof;
no parser/OCR/attribution/boundary/theological defect is hidden by aggregate
counts; representative answers accurately reflect each launching corpus shape;
Alex resolves every licensing or theological judgment.

### Private-beta convergence gate

- W8 answer integrity remains valid against the release revision.
- B7 and corpus acceptance pass.
- A live census re-queries shown sources, documents, chunks, propositions,
  quotes, licenses, and retrievability.
- Representative answer/evidence review covers the launching corpus shapes.
- Triggered Tier-2 conditions are either dormant or fully satisfied.
- Alex approves the deployment and private-beta audience.

### Foundation follow-up after the web-article fast path

Broad visible-default policy, general system-prompt review, broad claim-support
refinement, and a general ingestion-ready verdict are Scheduled here. They do
not interrupt the row-pinned hidden article proof without direct Beta Critical
Path evidence. Migration 088 is already applied and its isolated processor proof
is complete; it is not future work.

### Answer-generation latency benchmark — B6

**DONE, live (2026-08-27).** Two attended production mobile queries on
2026-08-25 showed queue time was not the bottleneck: jobs
`8677f62d-7ce9-4c3f-b9a5-dd256566a635` and `71ba8da6-0d81-406f-b01f-e9db0caafc2a`
queued for 0.62s and 0.94s, while worker execution took 61.47s and 64.34s.
Root cause traced to generation itself (median ~35s of that time was the
model's own reasoning before writing). The teacher-specific retrieval
candidate tested that day was rejected as a suite-wide latency direction
(2.81% median improvement against 20% required) and was retained instead as
the separate B6-F1 named-teacher integrity fix. The candidate that actually
closed this: Anthropic's `output_config.effort="medium"`, now hardcoded into
every real answer generation. Measured 25.46% faster median producer time
(49.41s → 36.83s) on the fixed 12-case paired benchmark, 11/12 cases faster,
no p90 regression, and zero hard failures on a targeted 6-pair blind human
quality review across the doctrinally sensitive categories. No prompt
shortening, evidence reduction, or model swap — the same model, less
reasoning depth before answering. Full trail:
`docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

### Dependency and hardening follow-up (from the 2026-08-24 scan)

Scan + exploitability triage: `docs/audits/2026-08/dependency_scan_2026-08-24.md`.
The bumps that were safe shipped 2026-08-24 (`3a30639`, `09b102a`); baseline
security headers shipped the same day (`9b816a8`). What remains, each blocked
on a real coupling rather than on effort:

1. **starlette + fastapi coupled bump.** 7 starlette advisories. All fix
   versions are `>=1.0.0`, but pinned `fastapi==0.128.8` declares
   `starlette<1.0.0` — neither moves alone. This is Invariant 14's landmine
   territory: the `da27fe4` 422-vs-401 admin-auth bug came from exactly this
   version interaction and reproduced locally but NOT in the deployed
   container. **Do the read-only exploitability triage of the 7 advisories
   first** — the same pass done for the Next.js CVEs turned 3 alarming-looking
   entries into zero live attack surface, and may do so here. Triage is cheap;
   the bump is not.
2. **pdfplumber + pdfminer-six coupled bump.** 2 advisories.
   `pdfplumber==0.11.6` exact-pins `pdfminer.six==20250327`. Sits behind PDF
   ingestion, so a bad bump is a corpus-quality risk (altered text extraction),
   not only a security one. Lower urgency — not on the live answer path.
3. **Content-Security-Policy on the frontend.** Deliberately not shipped with
   the other headers. A real CSP on App Router needs per-request middleware to
   mint a nonce, which opts every page out of static prerendering — the live
   homepage currently serves `x-vercel-cache: PRERENDER` and would lose it.
   The injection surface is also minimal today: no `dangerouslySetInnerHTML`
   anywhere, and the markdown renderer escapes HTML by default. Revisit if the
   app ever renders untrusted HTML, or at the Tier 2 gate. Report-only mode was
   considered and rejected as decoration without a reporting endpoint.
4. **Next.js major bump (`16.3.2`).** Alex deferred 2026-08-24 on evidence:
   all 3 next-specific CVEs have zero live attack surface here (no
   `rewrites()`, `dangerouslyAllowSVG` unset, no `"use server"` anywhere). The
   3 residual frontend advisories all sit inside `next`'s own dependency tree
   and only clear with this bump. Revisit at the next planned Next.js upgrade.

### Resolve Ravenhill documents rebuilt from unusable audio

20 Leonard Ravenhill documents were rebuilt on 2026-09-04 from captions that
cannot transcribe 1960s tape — "the lowing of the auction" for "the lowing of
the oxen", "put up some wear it as a cheap suit alive". Backups exist at
`local/2026-09/truncated_youtube_backup_*.json`, but those backups contain the
earlier model-cleaned, truncated text and must not be treated as authoritative.
First compare backup, current json3, and forced Whisper on three representative
documents against human-checked audio spans. Then choose restore, retranscribe,
or remove-from-retrieval. Any production operation is attended and follows dry
run -> one-document proof -> reconciliation -> bounded batch, including derived
propositions and positions. This is accident repair, not a gate: the existing
`≥85%` coverage check measures caption *duration* against video length, not
fidelity, so it cannot catch this class and nothing prevents recurrence on
other old-audio material.

### Answer-level sermon exposure audit — gates any filter work

Before any filter, down-weight, or model-scored quality gate on sermon passages,
audit the existing **20 distinct question groups**, not all 74 repeated answer
jobs as independent exposure. Record whether a kill-grade passage reached top
8 and whether it materially degraded the served answer. Stop when both rates
are known and Alex has made the filter/no-filter decision.

Only if that decision authorizes classifier work, build a source-masked,
randomized calibration set whose size is derived from the observed base rate
and required error bound rather than precommitted at 150. Preserve a redacted
manifest with immutable passage provenance, selection weights, labels and
rubric reasons; group the holdout by document to prevent overlapping-chunk
leakage; and report per-source plus source-held-out performance so a per-passage
classifier cannot silently become the rejected source filter. Predeclare keep
false-exclusion, kill recall, coverage/no-material, and counterfactual answer-
quality gates.

Why the gate exists: the 2026-09-04 baseline of 30 was deliberately stratified,
source-visible, and included eight current passages re-selected by word overlap
after their historical chunks were deleted. It cannot give a base rate or an
exact historical-exposure estimate, and four mechanical detectors built on it
all failed on inspection. Failed detectors may be reused as challenge-set
strata, never as production rules without new evidence. Full evidence and the
reviewed staged plan:
`docs/superpowers/specs/2026-09-04-sermon-passage-quality-design.md`.

### Quote accuracy and relevance repair — before any re-enable

Alex disabled the user-facing chat quote rail on 2026-08-25 because served
quotes were not consistently accurate or relevant enough. Production remains
`QUOTE_SELECTION_ENABLED=false` on both services. This is a Scheduled product-
quality phase, not an active private-beta Blocker: reproduce the concrete bad
cases, define a representative acceptance set before changing selection or
extraction, preserve every existing authenticity/attribution/provenance gate,
and prove the repaired rail against that set while delivery remains off. Any
production re-enable is a separate attended gate requiring Alex's explicit
approval. Quote rows, admin quote tooling, and library excerpts remain intact.

## Triggered

### Tier 2 — public signup or more than roughly 20 beta users

When either condition occurs, audit STEPBible CC-BY-NC use and attribution;
ensure openbible.info attribution on every served surface or record N/A; review
every shown SermonIndex-derived source; establish a DMCA agent and takedown
procedure; test guest-limit abuse; recheck admin minimums and the quote verifier.

### Other triggers

| Work | Trigger |
|---|---|
| Load/concurrency testing | Measured beta evidence or a demonstrated concurrency failure |
| Admin notifications | Scheduled position-refresh/content-review work |
| JWKS unknown-`kid` rate limit | Observed abuse traffic against `/` auth, or Tier 2 below. PyJWT 2.13.0 (shipped `3a30639`) already fixed the amplifying half — the cache-wipe-on-failed-fetch. The residual is un-amplified (one unknown-`kid` token = one outbound JWKS request) and belongs at the edge, not in `auth.py` |
| Custom harness or coordinator | Alex explicitly reverses the 2026-08-17 retirement decision |
| Decision 3: near-1930 public-domain titles | Title-level publication evidence; annual January 1 recheck |
| Decision 11: Hebrew lexicon/TBESH | Written permission from Online Bible |
| Decision 10: Precept Austin rewriting | A faithfulness method that avoids meaning drift |
| Decision 19: commentary modernization | Licensing outcome plus a side-by-side faithfulness-review design |
| Decision 21: numeral-heading chapter detector | Per-book validation survives both known regressions |
| Decision 25: study-panel drag-to-follow | Alex finds material mobile benefit |
| New Wine rebrand — remaining half | Code and copy SHIPPED and DEPLOYED 2026-08-31 (`abeafd7`); GitHub repo and Railway service both renamed. Remaining: DB source row, Vercel project, the public API hostname `rhemata-production.up.railway.app` (frontend API base URL must move in lockstep), `rhemata.app` retirement — it currently returns 404 rather than redirecting — Alex schedules as a bounded phase |

## Parked

### Recorded decisions and findings

| ID | Item | Current default / closure trigger |
|---|---|---|
| 1 | Cold storage vs visibility gate | Use visibility; deletion remains parked until hardening or legal need |
| 24 | `pending` vs `draft` quote status | Preserve both; check live rows before any decision |
| 26 | `jewish_perspectives` table | Leave in place pending explicit drop-migration approval |

Also parked: the unmerged Claude CLI harness adapter and all harness
improvements; missing-author cleanup; one-off visibility reviews; quote-status
cleanup; `jewish_perspectives`; the teacher-card refusal-copy question;
extraction-attempt history instrumentation; and `bible_refs.py`'s measured
~0.4% reference-hallucination rate (2 of 514 on real sermon text, 2026-08-29
— the two bad rows were removed, the extractor itself was not changed).

Also parked, from the 2026-09-03 working-tree review — static findings, none
reproduced on a device, so none meets the Blocker evidence bar: `app/page.tsx`
resizes the shell against `visualViewport` while the sidebar's fixed header/
aside/drawer have no transformed ancestor and stay on the layout viewport
(iOS keyboard + scroll); `keepLatestVisible` snaps the transcript to the
bottom on every `visualViewport` scroll while the composer has focus, which
would fight a pinch-zoom pan back to an earlier paragraph; AdminModal's
edge-to-edge mobile tab strip sits under the 44×44 close button; and
`loading-indicator.spec.ts`'s single-phase loop races the 4.9s step boundary
on slow WebKit. A device reproduction of either `page.tsx` item promotes it.

Also parked: the existing `next-themes` development hydration warning observed
during the 2026-09-01 responsive WebKit pass. All 16 tested mobile/tablet
journeys passed and no production failure was demonstrated; revisit only if it
causes visible theme flicker, incorrect initial styling, or a production error.

### Historical YouTube caption defect — 79 documents rebuilt, remainder left alone

**This entry's former premise was measured and found false, 2026-09-04.** It
previously asserted "content is complete — that model preserved everything and
merely left duplicate fragments behind." Re-fetching every pre-fix video's real
`json3` captions and comparing word counts against stored text showed
otherwise: of 303 verifiable pre-fix documents, **14 held under 55% of what was
said** (worst 37%) and 65 held 55–80%.

**Done** (`b641898`): the 79 documents under 80% were rebuilt, recovering
139,669 words (1.48x), 79/79 reconciled, zero duplicates. Total cost $0.19.
Four wrong author values the re-ingest introduced were repaired, and four
stored positions whose evidence cited truncated-text propositions were rebuilt.

**Deliberately not touched, and this is a decision rather than an omission:**
the 65 documents at 80–90% (consistent with correct filler removal, not loss),
and 15 documents whose captions no longer exist and cannot be verified either
way.

**What the rebuild exposed, recorded so it is weighed before any further
re-ingest:** raw `json3` captions carry no sentence punctuation, which surfaced
Blocker B8. Alex subsequently chose to enforce the existing no-attributed-
quotation prose policy rather than make quotation matching punctuation-
insensitive. The ingest still requires representative source-fidelity checks;
Ravenhill shows that exact storage can faithfully preserve unusable captions.

Three method traps, each of which produced a wrong conclusion before being
caught — see the CLAUDE.md caption landmine for the full form. Briefly: the
Groq model swap does not date the regression; a words-per-second proxy
over-accuses; and triplication *inflates* word count, so a stuttered document
scores as intact.

### Horizon — requires a fresh specification

1. New Wine migration — **code, copy and visual DONE 2026-08-31** (`abeafd7`; the rename also caught two legacy names no document recorded, UpperWord and Manna — see CLAUDE.md Settled #25). Repository, hosting-project and domain identifiers remain.
2. Verse-linked commentary enrichment with side-by-side modernization review.
3. Feedback-to-reviewable-content flags, never direct eligibility mutation.
4. ~~Consent-based search analytics and corpus-gap alerts.~~ Specified,
   built, and **live in production 2026-08-29** (Task 5.4 attended
   rollout, ACCEPTed by Alex): migration 093 applied, `ANALYTICS_HMAC_SECRET_V1`
   set on `rhemata`, finalizer (`*/5 * * * *`) and retention (`0 6 * * *`)
   running as Railway Cron Jobs, both verified via real runs. **Residual,
   Alex's explicit decision, not an oversight:** the production smoke
   sequence never ran, so the feature's core privacy guarantee (no
   question wording stored) is unverified in production. Full sequence
   still available whenever wanted:
   `docs/audits/2026-08/search_analytics_rollout_packet_2026-08-28.md`
   Section 6. See `rhemata-status.md`'s Task 5.4 entry for the rollout
   detail, including a Railway cron-service setup trap worth knowing
   before creating another one (Railpack-builder default, no env-var
   inheritance).
5. Specific follow-up questions that move users outward.
6. ~~Long-conversation handoff with a token trigger, provenance, privacy, and user control.~~ Specified and built 2026-08-26: `docs/superpowers/specs/2026-08-26-long-conversation-handoff.md`, migration 092 (applied live), deployed `70f6a3b`. Residual, not yet done: nudge copy unreviewed; no live/E2E verification. See `rhemata-status.md`'s 2026-08-26 entry.
7. An isolated Precept Austin retrieval experiment without weakening exclusions.
8. Reliable per-book structure and attribution boundaries.
9. Shared admin notifications for position drift and content-review events.

### Explicit exclusions

- No stored/pre-reviewed answer catalog or human review gate on serving.
- No sixth probabilistic claim-support judge without new evidence.
- No teacher taxonomy or theological-family labels.
- No synthetic feed or retention-maximizing roadmap.
- No quote extraction from flat book chunks without trustworthy boundaries.
- No new YouTube ingestion unless Alex explicitly reopens it.
- No direct feedback-to-eligibility mutation.

## Maintenance rule

This file is a registry, not a second active queue. Adding an item requires its
classification and, for Triggered work, an observable trigger. Starting work
requires reaching its Scheduled phase, satisfying its trigger, or Alex
explicitly promoting it. Closed and superseded detail moves to
`docs/plan-archive.md` instead of accumulating inline.
