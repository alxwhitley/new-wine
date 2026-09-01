# Back-to-Back Completion Queue Implementation Plan

> **For agentic workers:** Execute this queue inline in the primary Codex
> session, one packet at a time. Do not use a subagent for paid model calls,
> deployment, secrets, migrations, or production database operations. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring New Wine A2 to an ingestion-ready state, finish the existing
search-analytics rollout, replace the answer wait copy with an approximate
circular progress indicator, close the material B4/B5 launch risks, and pass a
measured B6/B7 release-candidate gate.

**Architecture:** Preserve one active critical-path item at a time. Finish A2
against the cached Issue 02-1973 transcript first; integrate the already-built
analytics worktree; add the self-contained loading treatment; close dependency,
deletion, abuse, privacy, and logging risks; then perform one release-candidate
verification and attended production rollout. The queue ends A2 at an
ingestion-ready approval packet: it does not itself authorize a production
magazine write.

**Tech Stack:** Python 3.12 review scripts, cached New Wine OCR artifacts, Groq
structured segmentation/review, FastAPI/Postgres/Supabase, Railway,
Next.js/React/TypeScript, SVG progress rings, Node's built-in test runner.

**Specs and governing records:**

- `docs/superpowers/specs/2026-08-25-new-wine-ai-review-design.md`
- `docs/superpowers/plans/2026-08-25-new-wine-ai-review.md`
- Search-analytics worktree:
  `docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-dashboard.md`
- Search-analytics worktree:
  `docs/superpowers/plans/2026-08-27-search-analytics-and-corpus-gap-dashboard.md`
- `CLAUDE.md` Invariant 17 and the New Wine segmentation landmine
- `docs/roadmap.md` A2 and Horizon item 4

## Global constraints

- Keep exactly one packet active. A later packet does not begin until the
  preceding packet's exit criteria pass or Alex explicitly changes the order.
- Never move, rename, archive, or delete any Rhemata file or directory without
  Alex's explicit approval at that moment.
- No New Wine production database write is authorized by this queue. A clean
  review, preview, or reconciliation only prepares a separately approved,
  attended ingest.
- Name the exact provider-call budget and obtain Alex's approval before new paid
  A2 calls. Use cached OCR; do not pay to OCR Issue 02-1973 again.
- Migration 093, Railway environment changes, deployment, production smoke
  writes, and scheduler creation are attended gates.
- Preserve the corrected search-analytics privacy statement: dashboard/API and
  `anon`/`authenticated` roles cannot derive tester identity, but direct
  service-role database access can correlate consent and occurrence rows.
- Do not claim that hallucinations are impossible. Loading copy describes real
  operations and safeguards, not guarantees.
- Keep build/code commits separate from the final docs/session-close commit.
- Preserve all unrelated modified and untracked files in the main worktree.

---

## Packet 1: Finish New Wine A2 to the ingestion-ready gate

**Outcome:** Issue 02-1973 passes the complete no-write OCR, article, and
proposition review pipeline with reconciled artifacts and an exact dry-ingest
preview, so Alex can separately authorize the first magazine ingest.

**Named non-goals:** No database write; no source-file promotion; no file move,
rename, archive, or deletion; no backlog-wide New Wine run; no unrelated
answer-path work.

### Task 1.1: Diagnose the remaining segmentation recurrence

**Audit declaration:**

- **Question:** Why does a large non-article span still absorb part of “The
  Apostle—God's Master Builder,” and what is the smallest evidence-backed
  correction?
- **Surfaces:** `scripts/magazine_review/articles.py`, its targeted tests, the
  cached Issue 02-1973 transcript, raw segmentation spans, and the exact text at
  the failed boundary.
- **Budget:** Begin with one segmentation-only call. Before any further paid
  calls, report the first result and name the remaining call/cost ceiling.
- **Exit:** Either identify a concrete cause and validate its targeted fix, or
  demonstrate that the same input has no stable correctable pattern and return
  to Alex with the evidence. Do not invent a threshold from intuition.

- [ ] Reproduce the latest `non_article_span_implausibly_large` failure using
  the cached transcript and a segmentation-only call.
- [ ] Save and inspect the complete raw article/non-article spans surrounding
  “The Apostle”; compare the boundary text with the issue's table of contents
  and transcript rather than relying on model labels.
- [ ] Classify the result as an instruction defect, deterministic validation
  defect, semantic-review defect, or irreducible model variance.
- [ ] Add a failing fixture/test for the exact observed defect before changing
  `SEGMENTATION_INSTRUCTIONS` or deterministic validation.
- [ ] Implement only the smallest correction supported by the inspected text.
- [ ] Run the targeted article-review tests and the existing magazine-review
  regression suite.
- [ ] Live-validate the corrected target with the approved bounded call budget.
- [ ] Commit the A2 correction as a code-only commit if and only if the target
  defect is materially reduced without a protected regression.

### Task 1.2: Clear the complete no-write issue review

- [ ] Run Issue 02-1973 through the full CLI with cached OCR and database writes
  disabled.
- [ ] Require all 32 OCR pages to reconcile, with page 15 using no more than its
  already-permitted single repair.
- [ ] Require the article gate to recognize the real “Apostle,” “Keeping the
  Unity,” and “New Wine Forum” boundaries without title bleed, invented merged
  titles, fake advertisement spans, overlap, uncovered content, or implausible
  article/non-article spans.
- [ ] Require the fresh whole-issue semantic review to pass every substantive
  article before proposition extraction proceeds.
- [ ] Require each substantive article to produce reviewed propositions whose
  evidence offsets round-trip exactly and whose support, qualification,
  overstatement, and attribution verdicts pass.
- [ ] Record a hard reconciliation: pages attempted/passed/repaired/failed;
  articles proposed/approved/quarantined/errored; propositions proposed/
  approved/refused/errored; database writes exactly zero.
- [ ] If a new failure pattern appears, classify it immediately. Re-enter Task
  1.1 only when direct evidence shows a specific correctable defect; otherwise
  stop for Alex instead of starting an unbounded retry loop.

### Task 1.3: Prove the reviewed-ingest handoff without writing

- [ ] Run the dry-ingest preview against the exact approved artifacts from Task
  1.2.
- [ ] Verify that every previewed proposition is byte-for-byte identical to the
  approved proposition artifact and that every article retains its reviewed
  title, author, source pages, and evidence boundaries.
- [ ] Verify that the reviewed path uses `shared_ingest.ingest_document()` and
  keeps `move_when_done=False`.
- [ ] Confirm the preview performs no embedding call, database write, or source
  file mutation.
- [ ] Produce one ingestion-ready decision packet containing immutable input
  hashes, model/prompt identities, provider spend, reconciliation totals,
  artifact paths, the exact first-write command, rollback/export procedure, and
  a proposed one-issue write ceiling.

**Packet 1 acceptance criteria:**

- [ ] Issue 02-1973 has one complete, clean, no-write end-to-end review.
- [ ] The exact reviewed-ingest preview reconciles with zero production writes.
- [ ] Alex receives a separate attended approval request for the first real
  magazine ingest; no approval is inferred from accepting this queue.

---

## Packet 2: Finish and prepare search analytics for rollout

**Outcome:** The existing `worktree-search-analytics-corpus-gap` branch is
reviewed, integrated, locally reverified, and packaged with accepted privacy,
runtime, smoke, and rollback decisions for Packet 5's attended rollout.

**Named non-goals:** No changes to retrieval, generation, citations, answer
outcomes, or automatic corpus acquisition; no storage of successfully answered
question wording.

### Task 2.1: Resolve the attended policy and runtime decisions

- [ ] Alex explicitly accepts or rejects the disclosed service-role database
  correlation boundary before real analytics data accumulates.
- [ ] Keep the current frontend consent gate unless Alex explicitly requests
  server-side hard refusal for non-consented authenticated users.
- [ ] Choose the finalizer runtime. Recommended default: a dedicated Railway
  worker/poll loop because classification should follow completed answer jobs
  promptly and the implementation already mirrors the answer worker.
- [ ] Choose the retention runtime. Recommended default: one daily scheduled job
  calling the idempotent resolved-gap text purge.

### Task 2.2: Integrate and reverify the completed branch

- [ ] Review the spec, the 22-commit branch diff, migration 093, and the two
  independent privacy/security verdicts.
- [ ] Rebase or merge the analytics branch onto current `main` without touching
  unrelated main-worktree artifacts.
- [ ] Resolve conflicts in favor of current `main` for New Wine work and in
  favor of the verified analytics branch for its scoped files.
- [ ] Re-run all 15 analytics test files and require 132 assertions with zero
  failures.
- [ ] Run frontend tests, TypeScript checking, and lint; distinguish pre-existing
  lint findings from analytics regressions.
- [ ] Run backend import/router mounting checks with no production database
  connection.
- [ ] Commit the integrated build separately from records documentation.

### Task 2.3: Prepare the attended production-rollout packet

- [ ] Verify the migration-apply and fresh-connection verification commands
  without applying migration 093 yet.
- [ ] Name the Railway services that require
  `ANALYTICS_HMAC_SECRET_V1`; verify the secret is never printed or logged.
- [ ] Record the chosen finalizer runtime and daily retention-purge command.
- [ ] Write the exact production smoke sequence for consent, one answered
  occurrence, one safe controlled `no_material` case if available, dashboard
  field allowlists, retest/resolve, and purge metadata.
- [ ] Record rollback triggers and the safe rollback posture for code, workers,
  and migration 093. Do not drop populated analytics tables during a rollback;
  disable collection/finalization and preserve data for an attended decision.
- [ ] Defer migration, environment mutation, scheduler creation, and deployment
  to Packet 5 so every queued code change receives one release-candidate gate.

**Packet 2 acceptance criteria:**

- [ ] Analytics is merged and locally reverified on current `main`.
- [ ] The privacy boundary and runtime decisions are explicitly accepted.
- [ ] Migration, secret, finalizer, retention, smoke, and rollback steps are
  complete enough to execute without reconstructing them from memory.
- [ ] No production mutation or deployment has occurred in this packet.

---

## Packet 3: Add the circular answer-progress treatment

**Outcome:** The waiting state shows a familiar circular progress ring and a
short sequence of truthful phrases, with no supporting sentence and no numeric
percentage.

**Files:**

- Create: `frontend/lib/loading-progress.ts`
- Create: `frontend/lib/loading-progress.test.mts`
- Modify: `frontend/components/rhemata/loading-indicator.tsx`

**Interfaces:**

- `estimateLoadingProgress(elapsedMs: number): number` returns a monotonic value
  from `0.06` through a hard maximum of `0.94` while waiting.
- `loadingPhraseIndex(progress: number): number` returns indices `0..4` and
  never regresses for a monotonic progress input.
- `LoadingIndicator` remains prop-free and starts its elapsed-time estimate when
  mounted. The existing `chatLoading`/empty-answer condition remains the real
  start/completion boundary.

### Task 3.1: Specify and test progress behavior

- [ ] Add Node tests proving the estimate starts above zero, never decreases,
  remains below `0.95` for any waiting duration, and approaches the cap more
  slowly over time.
- [ ] Add tests proving phrase indices advance in order and clamp at the final
  phrase rather than looping back to the beginning.
- [ ] Use this approved phrase sequence exactly:
  1. `Searching the corpus…`
  2. `Reading relevant sources…`
  3. `Building from the evidence…`
  4. `Checking names and attributions…`
  5. `Verifying source references…`
- [ ] Run `npm test` in `frontend` and observe the new tests fail before the
  implementation exists.

### Task 3.2: Implement the estimated circular ring

- [ ] Implement the pure progress functions. Use an eased elapsed-time curve,
  update it on a lightweight interval, and cap it at `0.94` until the waiting
  component unmounts when answer delivery begins.
- [ ] Render a 40×40 SVG ring beside the phrase using the same radius, stroke
  width, muted track, foreground arc, rounded cap, and -90° starting rotation as
  `frontend/components/rhemata/usage-ring.tsx`.
- [ ] Do not render a number or percentage inside the circle.
- [ ] Remove the existing supporting sentence completely.
- [ ] Keep `role="status"`; give the progress graphic an accessible label that
  says progress is estimated, and avoid announcing every timer tick.
- [ ] Honor reduced-motion preferences by removing animated stroke/opacity
  transitions while retaining the same semantic progress and phrase sequence.
- [ ] Keep the layout compact and responsive at the existing desktop and mobile
  answer widths.

### Task 3.3: Verify the waiting experience

- [ ] Run `npm test`, TypeScript checking, and lint for the touched files.
- [ ] In a local browser, submit a representative question and verify the ring
  is visible immediately, fills monotonically, slows near completion, and never
  appears complete before the answer arrives.
- [ ] Verify the five phrases advance once, do not cycle backward, and the final
  phrase remains visible during a long verification wait.
- [ ] Verify the answer replaces the waiting state without layout shift or a
  stale timer update.
- [ ] Check desktop, narrow mobile, keyboard/screen-reader semantics, and reduced
  motion.
- [ ] Commit the loading treatment as its own frontend code commit.

**Packet 3 acceptance criteria:**

- [ ] Circular progress matches the usage-ring visual language.
- [ ] No supporting sentence or numeric percentage appears.
- [ ] The indicator is explicitly approximate, monotonic, capped below complete,
  accessible, and removed only when answer delivery starts.
- [ ] Copy describes operations the production answer path actually performs.

---

## Packet 4: Close B4/B5 launch hardening risks

**Outcome:** No known high-severity dependency, account-lifecycle, unmetered
generation, logging, retention, authorization, CORS, or secrets issue remains
unresolved for the private-beta surface.

**Named non-goals:** No broad refactor; no automatic dependency-force fix; no
new analytics vendor; no production data deletion during testing; no cosmetic
cleanup unrelated to a launch risk.

### Task 4.1: Remediate production dependency advisories

**Evidence entering the task:** On 2026-08-28, `npm audit --omit=dev` against
`frontend/package-lock.json` reported three high-severity production findings
through Next.js `16.2.2` (`next`, its bundled `postcss`, and `sharp`) and
recommended Next `16.3.3`. Treat this as a dated snapshot and re-run the audit.

- [ ] Record the current frontend test, typecheck, build, and audit baselines
  before changing the lockfile.
- [ ] Re-run `npm audit --omit=dev` against the committed lockfile. Do not run
  `npm audit fix --force`.
- [ ] Read the official release notes and migration notes from the installed
  Next version through the audit-recommended patched version.
- [ ] Upgrade only Next and the transitive packages changed by its normal lockfile
  resolution; inspect the entire `package-lock.json` diff for unexpected new
  packages or lifecycle scripts.
- [ ] Run frontend tests, TypeScript checking, a production build, and the core
  browser smoke after the upgrade.
- [ ] Re-run the production dependency audit and require zero critical/high
  advisories, or stop with a reachability analysis and Alex's explicit written
  acceptance of any remaining advisory.
- [ ] Audit `backend/requirements.txt` in an isolated temporary environment with
  a current Python advisory scanner. Do not install audit tooling into the
  project environment or change requirements as a side effect of scanning.
- [ ] Upgrade vulnerable Python packages one focused dependency group at a time,
  with changelog review and the relevant backend regression suite after each.
- [ ] Commit dependency remediation separately from feature and records commits.

### Task 4.2: Make account deletion real and verifiable

**Architectural approval gate:** Before code, write a focused deletion design
that inventories every user-linked table—including analytics consent and
occurrences after Packet 2—defines retained audit/provenance fields, orders
database deletion versus Supabase Auth deletion, specifies retry/idempotency,
and provides a test-account reconciliation. Obtain Alex's approval of that
design before implementation.

- [ ] Read the current deletion scope audit and re-query the current schema
  read-only; do not trust the August 19 table inventory after migration 093.
- [ ] Add a failing test proving that resolving a deletion request cannot succeed
  while owned user data or the Supabase Auth account still exists.
- [ ] Implement the approved deletion orchestrator with explicit per-table
  reconciliation, safe retries, and a terminal failed state distinct from
  `resolved`.
- [ ] Preserve permanent provenance snapshots only where the approved design
  explicitly requires them; remove live account linkage and user-owned content.
- [ ] Use one designated test account to prove conversations, messages, saved
  words, pastoral data, roles, usage, deletion requests, analytics consent/
  occurrences/gap details, and the Auth account reach the approved disposition.
- [ ] Verify another user's data is unchanged and a repeated deletion request is
  idempotent.
- [ ] Update the account UI copy to match the implemented timing and outcome
  exactly; never imply deletion completed when only a request was recorded.
- [ ] Commit account deletion as its own reviewed build change.

### Task 4.3: Close the unmetered teacher-card generation path

- [ ] Confirm structurally and with a bounded test that
  `GET /study/teacher/{source_id}` can still reach a paid Anthropic generation
  without passing an enforceable per-user limit.
- [ ] Present Alex with the smallest two closures: count teacher-card generations
  against the authenticated weekly allowance, or disable generated teacher cards
  for beta. Record the selected policy before changing behavior.
- [ ] Add a failing test proving an over-limit user cannot reach the model call
  and a metering failure fails closed.
- [ ] Implement the selected closure by reusing the canonical metering helper or
  an explicit feature gate; do not create a third independent usage ledger.
- [ ] Verify allowed, over-limit, metering-error, unauthenticated, and repeated
  request behavior.
- [ ] Commit the abuse/cost closure separately.

### Task 4.4: Minimize sensitive logs and establish retention

- [ ] Remove `token[:20]` from failed-auth logging in `backend/app/auth.py` and
  add a regression test that captured auth logs contain no bearer-token bytes.
- [ ] Remove or irreversibly minimize raw IP, anonymous ID, user question, email,
  and account identifier logging on normal and error paths. Preserve only the
  minimum correlation identifier needed for support.
- [ ] Inventory retention-sensitive stores: conversations/messages, answer jobs,
  feedback, usage/metering identifiers, deletion requests, analytics rows, and
  Railway/Vercel logs.
- [ ] Obtain Alex's explicit retention periods and deletion exceptions, then
  implement idempotent purge/reporting jobs for the accepted policy.
- [ ] Prove each purge in a rollback-only transaction or isolated fixture before
  any attended production schedule is created.
- [ ] Document log-provider retention settings and who owns a deletion request.

### Task 4.5: Verify boundaries, headers, and secrets

- [ ] Confirm the live backend `ALLOWED_ORIGINS` value contains only the exact
  production/staging frontend origins and no wildcard.
- [ ] Probe live frontend/backend responses for HSTS, frame protection,
  `nosniff`, referrer policy, permissions policy, and expected CORS allow/deny
  behavior. Keep CSP Scheduled unless direct evidence or a new rendering surface
  promotes it.
- [ ] Run the existing admin-auth and RLS regression suites without using any
  script whose `test_*.py` name hides a production write.
- [ ] Run a repository plus git-history secret scan with an approved scanner. If
  scanner installation is required, ask before installing it; never print a
  discovered secret into chat or logs.
- [ ] Rotate and invalidate any confirmed live secret found in history before
  removing or redacting repository material; do not rewrite git history without
  Alex's explicit approval.

**Packet 4 acceptance criteria:**

- [ ] Production dependency audits have no unaccepted high/critical finding.
- [ ] Account deletion is real, reconciled, idempotent, and honestly described.
- [ ] Every paid generation surface has an enforceable abuse/cost boundary.
- [ ] Sensitive logs and retention behavior match an explicit policy.
- [ ] Auth, RLS, CORS, headers, and secret scans have evidence-backed verdicts.

---

## Packet 5: Pass the B6/B7 release-candidate gate and launch

**Outcome:** The complete queued revision passes code-quality, core-journey,
accessibility, observability, rollback, and attended production checks before
the private beta opens.

**Named non-goals:** No redesign; no generic performance project; no requirement
to remove every lint warning when it has no behavioral consequence; no quote
rail re-enable.

### Task 5.1: Establish a trustworthy code-quality baseline

**Evidence entering the task:** On 2026-08-28, frontend lint reported 25 errors
and 12 warnings. The errors included render-time ref access, impure
`Math.random()` during render, effect/state findings, and navigation/copy rules;
the 26 existing frontend unit tests passed.

- [ ] Re-run lint on the release revision and group findings by behavioral risk,
  accessibility, correctness, and cosmetic style.
- [ ] Fix all lint errors in small behavior-preserving commits, prioritizing
  render purity, stale dependencies, and state synchronization. Keep this
  separate from feature changes.
- [ ] Classify remaining warnings individually and record an owner/revisit trigger
  for every accepted warning; do not blanket-disable rules.
- [ ] Run frontend tests, TypeScript checking, lint, and a production build. The
  release gate requires zero lint errors and no build/typecheck failure.
- [ ] Run targeted backend suites for async answers, auth/roles, metering,
  deletion, analytics, magazine review, and migration verification. Read each
  `scripts/test_*.py` before execution and exclude live-write scripts unless Alex
  separately approves them.

### Task 5.2: Prove the core journey in a real browser

- [ ] Exercise guest entry, authenticated signup/login, analytics consent,
  question submission, the progress ring, checked answer delivery, citations,
  source navigation, feedback, and conversation reload/reconnect.
- [ ] Exercise honest terminal states: `no_material`, attribution refusal,
  weekly/guest limit, queue full, worker timeout, backend unavailable, and a
  recoverable client network interruption. Every state must offer an intelligible
  next action rather than a dead end.
- [ ] Verify account deletion with the designated test account and verify the
  analytics dashboard with only approved/redacted data.
- [ ] Check supported desktop and narrow-mobile sizes, keyboard-only navigation,
  visible focus, modal focus trapping/restoration, screen-reader announcements,
  reduced motion, text zoom, and dark-theme contrast.
- [ ] Run axe and Lighthouse against chat, consent, account, library/source, and
  admin analytics. Fix serious/critical accessibility violations; record measured
  performance regressions with an explicit acceptance or closure.
- [ ] Capture screenshots and a concise pass/fail matrix as release evidence.

### Task 5.3: Make production behavior observable and reversible

- [ ] Add or verify a liveness check and a readiness check that can distinguish a
  running web process from a service unable to reach required database/config
  dependencies, without returning secrets or internal details.
- [ ] Establish dashboards or saved queries for API 5xx rate, answer queue depth,
  failed jobs, expired leases, worker heartbeat, p50/p95 answer latency, and
  analytics-finalizer backlog.
- [ ] Select a client-error reporting path. If it adds an external service or new
  collection, obtain Alex's privacy approval first; `console.error` alone is not
  sufficient launch observability.
- [ ] Set concrete hold/rollback triggers before deployment: any security/privacy
  defect or data-integrity failure; a new client error affecting the core journey;
  API errors above twice baseline; or p95 latency more than 50% above baseline.
- [ ] Write exact rollback steps for frontend, backend, answer worker, analytics
  finalizer, retention scheduler, and migration 093's preserve-data posture.
- [ ] Confirm scheduled backups are current and the accepted RPO/RTO is still
  deliberate. If practical, perform a non-production export/restore round trip
  for representative user and corpus rows.

### Task 5.4: Perform one attended rollout and first-hour watch

- [ ] Obtain Alex's explicit approval for the named migration, Railway secrets,
  scheduler creation, services, deployment revisions, smoke accounts, and any
  controlled production writes.
- [ ] Apply migration 093 and verify tables, RLS, grants, constraints, and indexes
  on a fresh connection.
- [ ] Set `ANALYTICS_HMAC_SECRET_V1` on `rhemata` and `answer-worker` without
  printing it; configure the approved finalizer and retention schedules.
- [ ] Deploy the reviewed backend, worker, and frontend revisions.
- [ ] Verify liveness/readiness, then execute the Packet 2 analytics smoke and
  Packet 5 core-journey smoke. Do not use a magazine ingest as a launch smoke.
- [ ] Confirm one answered analytics occurrence finalizes without storing
  question wording; exercise a controlled `no_material` gap only when its exact
  production write is approved.
- [ ] Watch errors, queue depth, worker health, finalizer backlog, and latency for
  the first hour. Roll back when a predeclared trigger fires; do not improvise a
  new threshold during the incident.
- [ ] Record the release decision as ACCEPT, HOLD, or ROLLBACK with the evidence.

**Packet 5 acceptance criteria:**

- [ ] Tests, typecheck, build, and lint release gates pass.
- [ ] The core journey and terminal-state matrix pass on mobile and desktop.
- [ ] Accessibility has no unaccepted serious/critical violation.
- [ ] Monitoring, support ownership, and rollback instructions are operational.
- [ ] Search analytics and the circular loading treatment are live and verified.
- [ ] The private beta opens only after an explicit ACCEPT decision.

---

## Final checkpoint and session close

- [ ] Re-run one coherent verification cycle for every packet changed since its
  own acceptance checkpoint; do not rerun unrelated suites.
- [ ] Production-smoke the analytics flow and loading indicator after the final
  deploy without using a magazine database write as a smoke test.
- [ ] Update `docs/roadmap.md` by replacing the stale A2 next-step wording and
  marking completed Horizon work accurately rather than stacking corrections.
- [ ] Overwrite `rhemata-status.md` Current state with the achieved outcome,
  classified discoveries, approved scope changes, and the next single item.
- [ ] Record the process measures: original outcome completion, unplanned
  investigations started, findings promoted to Blocker, and active
  critical-path item count.
- [ ] Make one docs-only closeout commit, separate from all code/build commits.

## Queue completion condition

This queue is complete only when A2 is ingestion-ready; search analytics and the
circular loading treatment are operationally live; B4/B5 launch risks are
closed or explicitly accepted with evidence; and the B6/B7 release candidate
has an attended ACCEPT decision. The next action after queue completion is an
explicit Alex decision on the prepared first New Wine production-ingest packet.
