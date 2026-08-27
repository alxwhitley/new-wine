# Rhemata Roadmap — Later and Dormant Work

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
   Next: diagnose the reviewer stage's `article_failure_reasons_invalid`
   inconsistency and the ad-bleed risk directly (same no-CLI, cached-OCR
   method), then rerun the no-write article/proposition gates, and obtain
   Alex's separate approval before any attended database write. No
   benchmark decision or pipeline fix authorizes a database write or file
   move.
3. **A3 — Existing converted sources and missing combinations.** Reconcile
   Ravenhill, Savchuk, and Poonen visibility/content; preserve the distinction
   between candidate and approved quote; keep the 12 HelloAO missing
   book/commentary combinations quarantined unless a chapter-level contract is
   separately approved.
4. **A4 — Reference datasets.** Treat OpenBible cross-references, Strong's,
   TIPNR, STEP-derived data, and similar sources independently for license,
   attribution, version/checksum, transformation, schema fit, dry run, isolated
   write, rollback, reconciliation, and serving-surface proof.
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
| Manna rebrand | Alex schedules the migration as a bounded product phase |

## Parked

### Recorded decisions and findings

| ID | Item | Current default / closure trigger |
|---|---|---|
| 1 | Cold storage vs visibility gate | Use visibility; deletion remains parked until hardening or legal need |
| 24 | `pending` vs `draft` quote status | Preserve both; check live rows before any decision |
| 26 | `jewish_perspectives` table | Leave in place pending explicit drop-migration approval |

Also parked: the unmerged Claude CLI harness adapter and all harness
improvements; missing-author cleanup; one-off visibility reviews; quote-status
cleanup; `jewish_perspectives`; the teacher-card refusal-copy question; and
extraction-attempt history instrumentation.

### Horizon — requires a fresh specification

1. Manna code/repository/domain/copy/visual migration.
2. Verse-linked commentary enrichment with side-by-side modernization review.
3. Feedback-to-reviewable-content flags, never direct eligibility mutation.
4. ~~Consent-based search analytics and corpus-gap alerts.~~ Specified and
   built 2026-08-27: `docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-dashboard.md`,
   migration 093 (**not applied**), worktree branch
   `worktree-search-analytics-corpus-gap` (22 commits, unmerged/unpushed —
   not on `main`, no deploy). 132 local tests pass; typecheck/lint clean;
   two independent fresh-context privacy/security reviews both returned
   SAFE. Residual: Alex's review + the spec's own 10-step attended rollout
   checklist (migration apply, HMAC secret, finalizer deployment decision,
   retention-job schedule, explicit sign-off on the disclosed
   service-role-DB-access anonymity boundary). See `rhemata-status.md`'s
   2026-08-27 entry.
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
