# Rhemata — Master Plan (v7.0 · build to ingestion-ready beta)

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` when executing approved build packets. Packet
> checkboxes are evidence gates, not permission for production writes.

**Goal:** reach an ingestion-ready platform, then complete the private-beta
product while approved corpus production runs concurrently.

**Architecture:** a resumable coordinator dispatches bounded, isolated packets
to Claude Code, Kimi through OpenCode Go, and Grok. Claude Opus 5 is the sole
judgment/integration layer; Kimi is the primary worker, Claude Sonnet 5 is its
confirmed-exhaustion fallback, and Grok handles bounded research and mechanical
verification.

**Tech stack:** existing Rhemata application and scripts, Git worktrees, Claude
Code subscription CLI, OpenCode Go subscription CLI, Grok subscription CLI,
and deterministic Python orchestration. No model API integration is required.

### Global constraints

- Preserve all `CLAUDE.md` invariants and the hard rules in `AGENTS.md`.
- Never run production DB writes through the agent harness.
- Never infer doctrinal, licensing, destructive, deployment, or migration
  authority from a work packet.
- Keep build commits and docs/records commits separate.
- Do not touch unrelated user changes in the dirty worktree.

> **Purpose:** build everything required to reach a stable ingestion-ready
> platform, then finish the beta product while corpus extraction and ingestion
> run in parallel. When both post-benchmark tracks pass, Rhemata is ready for a
> private beta launch.
>
> **Authority:** `CLAUDE.md` owns invariants and settled decisions.
> `ARCHITECTURE.md` owns current implementation detail. `rhemata-status.md`
> owns current session state. Historical and superseded reasoning belongs in
> `docs/plan-archive.md`.
>
> **Reading rule:** this file is ordered. The build plan ends before the final
> extraction-and-ingestion section. Work in that final section is corpus
> production, not unfinished platform construction.

---

## Outcome

Rhemata (future product name: **Manna**) helps a discerning Spirit-filled lay
believer get a fresh, cited answer grounded in real named teachers, then move
toward those teachers, Scripture, and a local church rather than treating the
product as a spiritual authority.

The immediate objective is a **private-beta launch candidate**, reached in two
stages:

1. Complete the platform foundation and pass the **ingestion-ready benchmark**.
2. Run two independent tracks concurrently:
   - **Product track:** finish and validate the private-beta experience.
   - **Corpus track:** extract, ingest, reconcile, and curate approved material.

The launch candidate exists only when both tracks pass their exit criteria.
Neither a polished product with an inadequate corpus nor a rich corpus on an
unproven product qualifies.

```text
Overnight enablement → Foundation build → Ingestion-ready benchmark
                                             ├─ Product beta build ─────┐
                                             └─ Corpus production ──────┤
                                                                        ↓
                                                        Private-beta launch gate
```

### Target launch date — changed 2026-08-13

**October 2026.** This replaces the mid-2027 target used in prior planning
(`docs/plan-archive.md`). **This is a major compression of the prior
timeline, not a minor schedule adjustment.**

**Reason:** market pressure from fast-moving AI tools, plus a conference in
October 2026 that Alex wants to use as the launch venue.

---

## Execution model

### Model roles

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| **Claude Opus 5 is the judgment layer.** It plans packets, approves parallelism, reviews evidence, resolves conflicts, and returns `ACCEPT`, `REVISE`, `QUARANTINE`, or `HUMAN_REQUIRED`. Claude Sonnet 5 becomes a worker only after confirmed Kimi exhaustion or for a packet explicitly reserved for Claude. | **Primary implementation worker.** It processes eligible build packets through the pinned OpenCode Go Kimi model until confirmed allowance exhaustion. It never makes final architectural, theological, licensing, production-write, or launch judgments. | **Parallel research and verification worker.** It handles inventories, read-only diagnostics, test/log analysis, cross-checks, and other mechanical work with objective outputs. It does not make architectural, theological, licensing, or production-write decisions. |

### Worker fallback

```text
Kimi worker
  └─ confirmed quota/rate-limit exhaustion
       └─ checkpoint packet and requeue to Claude Sonnet 5
            └─ Claude Opus 5 independently judges the result
```

- Ordinary test failures, coding errors, ambiguous output, or permission
  failures do not count as quota exhaustion.
- A partially completed Kimi packet may move to Sonnet only after its changed
  files, journal, last passing checkpoint, and remaining acceptance criteria
  are recorded.
- If Sonnet is also unavailable, the packet is quarantined and the queue moves
  to other independent work. The harness never retries indefinitely.
- Opus does not approve its own unreviewed implementation. If Opus must perform
  emergency implementation, a separate Opus review session or Alex supplies
  the judgment gate.

### What “parallel” means

- Work in the same row may run at the same time only when the packets have
  disjoint file ownership and no unresolved dependency between them.
- A blank or “wait” cell means the lane must not invent work to stay busy.
- Database writes, migrations, deploys, governed-document changes, doctrinal
  choices, and unresolved product decisions are never parallelized implicitly.
- Parallel workers use isolated worktrees. No worker edits the user's current
  dirty worktree.
- Only Opus may accept a packet for integration. Command success alone never
  means completion.

### Required packet contract

Every overnight packet must declare all of the following before dispatch:

- unique packet ID, objective, dependency IDs, and assigned lane;
- permitted worktree, writable file allowlist, and forbidden surfaces;
- required context files and exact starting revision;
- acceptance criteria and deterministic verification commands;
- maximum turns, wall-clock limit, retry limit, and expected cost class;
- whether network access is allowed;
- checkpoint artifacts and structured result schema;
- rollback method and conditions requiring `HUMAN_REQUIRED`;
- whether the packet may be reassigned from Kimi to Sonnet.

Packet states are:

```text
BLOCKED → READY → RUNNING → REVIEW → ACCEPTED
                     ├──────────────→ REVISE → READY
                     ├──────────────→ QUARANTINED
                     └──────────────→ HUMAN_REQUIRED
```

The durable journal records worker, provider/model, timestamps, attempts,
changed files, commands, exit codes, test evidence, fallback reason, Opus
verdict, and integration revision.

---

## Phase 0 — Prepare for long unattended runs

This phase comes first because longer runs must come from a resumable queue of
bounded packets, not one large prompt. Its output is a safe repo-only harness;
it is not an autonomous production operator.

### O1 — Refresh the harness constitution

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus compares `CLAUDE.md`, `PLAN.md`, `HARNESS.md`, agent definitions, and hooks; settles the new authority and review contract. | Inventory stale instructions in the executor/reviewer definitions and propose bounded edits in an isolated worktree. | Read-only inventory of obsolete line references, frozen-script lists, hidden-default assumptions, and routing references. |

**Exit criteria — passed 2026-08-09:**

- [x] Reviewer/executor instructions point to current governing sections, not
  stale line numbers or retired policies.
- [x] The obsolete ingest-freeze list is reconciled with the converted scripts.
  The hook now blocks recognizable production-write commands by task class
  while allowing dry runs, rather than freezing three scripts by name.
- [x] Harness agents no longer hard-code the retired hidden-default policy.
  They defer visibility behavior to F3 and return `HUMAN_REQUIRED` on ambiguity;
  schema, registration, and `ARCHITECTURE.md` alignment remains F3 build work.
- [x] Repo-only harness work and plain-script production DB work remain a hard
  separation.

Evidence: `HARNESS.md`, active local `.Codex/agents/*.toml` and
`.Codex/hooks/*.py`, plus
`.claude/harness-selftest/test_current_routing_contract.py`. All three harness
self-test scripts passed after merge.

### O2 — Build the machine-readable packet and verdict contracts

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus defines schemas, authority boundaries, state transitions, and invalid-state behavior. | Implement parser/validator plus fixtures and tests. | Produce adversarial malformed packets and verify deterministic rejection messages. |

**Exit criteria — passed 2026-08-09:**

- [x] Invalid or incomplete packets fail closed before any worker starts.
- [x] File ownership, dependency, budget, and verification fields are required.
- [x] Worker results and Opus verdicts are structured and replayable.
- [x] `ACCEPT` is impossible without recorded acceptance evidence.

Evidence: strict v1 packet, worker-result, Opus-verdict, and replay-bundle
schemas under `schemas/harness/v1/`; runtime validators and canonical replay
logic under `scripts/harness_contracts/v1/`; and 168 passing O2 harness
self-tests. Fresh Opus adversarial review returned `ACCEPT` after fully rehashed
malformed-bundle checks; all three pre-existing harness self-test scripts also
passed.

### O3 — Add queue, resume, and quarantine behavior

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus specifies scheduling, retry classification, fallback semantics, and morning reconciliation. | Implement durable queue/journal/checkpoint behavior with crash-resume tests. | Build deterministic failure fixtures: timeout, malformed output, quota exhaustion, test failure, and interrupted process. |

**DONE — 2026-08-11:** Repo-only coordinator, crash recovery, quarantine,
one-time fallback, reconciliation/status, and disposable synthetic end-to-end
commissioning completed on `codex/o3-p5-coordinator-loop` (P5D `746bb05`, P5E
`e16920b`, audit `docs/audits/o3_p5_synthetic_commissioning_2026-08-10.md` /
`5322411`; 656 O2/O3 tests, final Opus `ACCEPT`). Integrated locally into
`main` at records close `b580915`; not pushed. Real-provider commissioning
remains `HUMAN_REQUIRED` pending a proven pre-execution sandbox; receipt
recovery does not claim general exactly-once semantics before a receipt exists,
and the optional state-cache invariant remains explicitly unverified.

### O4 — Isolate Git and filesystem ownership

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus approves the integration order and rejects overlapping ownership. | Exercise implementation packets in dedicated worktrees with file allowlists. | Audit changed-file manifests, unexpected untracked files, secret-like diffs, and cross-worktree leakage. |

**DONE — 2026-08-11:** Git/worktree identity, independently bound repository
roots, exclusive write ownership, clean baselines, authoritative postflight
manifests, staged/out-of-allowlist/secret-like change refusal, protected dirty
worktree preservation, mutation-free integration analysis, and crash-safe
evidence reconciliation are implemented on `codex/o4-git-isolation` through
`7ab9f15`. Commissioning evidence is recorded in
`docs/audits/o4_git_filesystem_isolation_2026-08-11.md`; 804 O2/O3/O4 tests,
scoped compilation, diff checks, and all three legacy guards passed. Final
independent review returned Spec PASS, Quality PASS, `ACCEPT`. The harness does
not stage, commit, push, merge, clean, delete, or resolve conflicts; uncertainty
routes to `HUMAN_REQUIRED`. O6 still owns concurrent multi-packet rehearsal.

### O5 — Add budgets and hard stops

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus sets packet risk classes and permitted autonomy for each class. | Implement turn, time, retry, output-size, and queue-wide limits. | Verify stop behavior and that logs contain no credential values or prompt payloads that should remain private. |

**Exit criteria:**

- [ ] Every command has a wall-clock limit and every packet has an attempt cap.
- [ ] Provider allowance errors use a bounded backoff and then fallback/pause;
  no lane loops against a depleted subscription.
- [ ] Production DB writes, migrations, deployment, destructive Git/filesystem
  actions, doctrinal content, licensing determinations, and unapproved scope
  expansion stop for Alex.
- [ ] The coordinator can finish a useful night even when one provider becomes
  unavailable.

### O6 — Rehearse before trusting overnight mode

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus runs the final review and issues the harness readiness verdict. | Complete a disposable multi-packet repo-only rehearsal including a simulated Kimi→Sonnet handoff. | Independently reconcile journal state, changed files, tests, failure classifications, and morning report totals. |

**Exit criteria:**

- [ ] At least two independent packets run concurrently without file collision.
- [ ] Crash/resume, worker failure, quota fallback, quarantine, and human-stop
  paths are demonstrated with fixtures.
- [ ] No production database, deployment, or governed document is changed.
- [ ] Alex can determine what happened, what changed, what passed, and what
  needs attention from one morning report.

---

## Phase 1 — Foundation build to the ingestion-ready benchmark

These waves are ordered. Within a wave, the columns show the maximum safe
parallelism after Opus has issued packets with disjoint ownership.

> **F1 (100-generation/100-user concurrency proof) removed 2026-08-13 —**
> Alex explicitly declined a pre-launch load test. Removed outright, not
> marked done and not skipped silently; the same removal also strikes the
> proof from F6's benchmark pass criteria and from the Tier 2 gate below.

### F2 — Close recoverability and dependency reproducibility

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus owns the backup/restore risk judgment and approves any dependency pin changes. | In parallel, pin proven production-relevant dependency divergences and validate a clean build. | Inventory authoritative backup/PITR facts and independently compare local, backend, worker, and Railway dependency/runtime manifests. |

**Exit criteria:**

- [ ] Supabase backup/PITR status, retention, restore granularity, owner, RTO/RPO,
  and exclusions are recorded from an authoritative surface.
- [ ] The safest available restore scope is tested. If full-project disaster
  restore cannot be proven, Alex explicitly accepts, upgrades, or defers it.
- [ ] Production-relevant versions that caused divergence, especially
  `pydantic` and `starlette`, are deterministic.
- [ ] Backend and worker Python-version differences are intentional and
  documented.
- [ ] Clean-environment backend and admin-auth smoke tests pass.

### F3 — Finish the ingestion-default contract

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus settles the exact visible-default policy and exceptions, then reviews every schema/registration change. | Implement consistent defaults and registration behavior with tests after the policy is fixed. | Inventory every registration path and verify that license, retrievability, serving SQL, sentinel, alias, empty-shell, and Tier 2 behavior did not drift. |

**Exit criteria:**

- [ ] Newly registered source classes default to `shown` under a written rule;
  sentinel, unresolved alias, empty shell, and Tier 2 exceptions are explicit.
- [ ] Schema and registration paths agree without weakening `license_status`,
  `retrievable`, or serving-gate SQL.
- [ ] One dry run and one isolated real registration pass through the actual
  chokepoint and reconcile source/document/chunk/proposition state.
- [ ] `ARCHITECTURE.md` is updated in the separate docs close so policy and code
  agree.

### F4 — Resolve the remaining pre-benchmark quality decisions

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus makes evidence-based keep/hold/kill recommendations; Alex decides any product-risk expansion. | Implement only a narrowly approved deterministic guard, if the evidence calls for one. | Run the queued read-only false-flag diagnostic and quantify the 20 Prince rejection classes without making theological judgments. |

**Required decisions:**

- [ ] **Generation-output verification:** accept the residual risk, retain a
  narrow deterministic check, or define evidence sufficient to reopen it. Do
  not build a sixth probabilistic judge by default.
- [ ] **System-prompt review timing:** decide whether review is required at the
  ingestion-ready benchmark or before private-beta expansion.
- [ ] **Quote hardening:** decide majority-Scripture and unbalanced-quotation
  guards, plus whether to change the proven `--per-doc-limit=1` cap, before any
  further teacher batch.

### F5 — Prove operability and sole-path integrity

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus reviews the ranked failure modes and runs the final architecture judgment. | Close only evidenced repo-level observability or recovery gaps found by the audit. | Trace every served and ingest path read-only; produce bypass, dependency, and failure-visibility inventories. |

**Exit criteria:**

- [ ] No known answer path bypasses license/visibility, commentary, attribution,
  citation, position-paper, or verification guards.
- [ ] Every document-writing ingest path routes through
  `shared_ingest.ingest_document()`.
- [ ] Failure logs identify packet/job/source and support reconciliation without
  exposing secrets.
- [ ] Remaining gaps are closed, explicitly accepted by Alex, or deferred with
  an owner and trigger.

### F6 — Declare the ingestion-ready benchmark

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus re-evaluates every benchmark criterion, records exceptions, and issues `PASS` or `HUMAN_REQUIRED`. | Wait; fix only a rejected packet explicitly returned by Opus. | Independently reproduce counts, test results, changed-path audit, and deployment/DB evidence freshness. |

The benchmark passes only when all are true:

- [ ] **Correctness:** sole-path and ranked failure-mode invariants hold.
- [ ] **Ingestion:** the shared chokepoint, dry-run, one-item proof, accounting,
  and reconciliation contract is operational.
- [ ] **Recoverability:** backup/PITR and restore posture is proven or explicitly
  accepted by Alex.
- [ ] **Operability:** dependencies reproduce and failures are diagnosable.
- [ ] **Harness:** the repo-only overnight rehearsal passes.
- [ ] **Records:** `PLAN.md`, `CLAUDE.md`, `ARCHITECTURE.md`, and
  `rhemata-status.md` agree in a separate docs-only close.

Passing this benchmark freezes platform-building as the default activity.
Subsequent engineering must either serve the beta product track below or fix a
demonstrated regression. Corpus work may now run continuously under the final
section's separate rules.

---

## Phase 2 — Product track: build the private beta

This remains build work. It runs concurrently with the corpus-production
section only after F6 passes.

### B1 — Freeze the private-beta product contract

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus converts `PRODUCT.md`, `POSITIONING.md`, current UI behavior, and settled decisions into a testable beta contract; Alex approves user-facing scope. | Inventory implementation gaps against the approved contract. | Independently inventory routes, surfaces, authentication states, and unresolved copy/assets without proposing scope expansion. |

**Exit criteria:** audience, entry path, supported answer flows, honest-empty
behavior, citation/source navigation, study panel, account boundary, feedback,
privacy posture, and explicit non-goals have testable acceptance criteria.

### B2 — Complete the core user journey

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus owns answer-path, safety, and architectural judgment; Claude implements sensitive slices. | Implement bounded UI/backend gaps outside protected judgment surfaces. | Build route/state matrices and verify happy, empty, refused, errored, retry, and unauthenticated states. |

**Exit criteria:** a beta user can enter, ask, receive an honest guarded answer,
inspect citations/evidence, reach named teachers or Scripture, and recover from
every expected terminal state without a dead end.

### B3 — Finish study, source, and outward-navigation surfaces

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus judges whether the experience reinforces the product's outward-moving purpose. | Complete approved panel/source-card/navigation gaps, including authenticated production behavior. | Run responsive, accessibility, link-target, and state-coverage audits. |

**Exit criteria:** the Inline Study Panel has an authenticated production pass;
swipe-only remains the default unless Alex explicitly reopens drag-to-follow;
citations and teacher/source destinations work on supported mobile and desktop
sizes.

### B4 — Complete private-beta administration and supportability

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus defines the minimum safe operator workflow and reviews identity/data effects. | Implement approved bounded admin, deletion, and contributor-state gaps. | Verify role boundaries, mobile navigation, empty/error states, and auditability using non-destructive fixtures. |

**Exit criteria:** contributor activity is actionable; pending states are
visible where still relevant; account deletion is real and verified; admin
navigation is usable; support can identify failures without direct database
guesswork.

### B5 — Security, privacy, and abuse readiness

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus owns threat-model and launch-risk judgment. | Implement approved bounded mitigations with tests. | Run read-only surface inventory and mechanical abuse/authorization test matrices. |

**Exit criteria:** guest limits, authenticated authorization, deletion,
retention-sensitive data, logging hygiene, secret handling, and common abuse
paths are tested; no unresolved high-severity finding remains.

### B6 — Beta UX, accessibility, and performance pass

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus adjudicates product tradeoffs and regressions. | Fix isolated, approved frontend/backend defects. | Run browser matrices for responsive layout, keyboard access, focus, screen-reader semantics, loading/error states, and measured performance. |

**Exit criteria:** core flows pass supported mobile/desktop browsers and WCAG
essentials; measured regressions are fixed or explicitly accepted; the product
does not imply unsupported authority, certainty, or corpus completeness.

### B7 — Product-track release candidate

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus runs the release review, confirms rollback/monitoring, and issues the product-track verdict. | Fix only rejected release packets. | Independently reproduce the end-to-end test matrix, release artifact/version, known-issue list, and smoke checks. |

**Product-track exit criteria:**

- [ ] All agreed private-beta journeys pass in a production-like environment.
- [ ] Monitoring, operator response, rollback, and user-support ownership exist.
- [ ] No open blocker affects answer integrity, identity/data safety, core
  navigation, or recoverability.
- [ ] Known non-blockers have owner, consequence, and revisit trigger.
- [ ] A final deploy still requires Alex's explicit approval.

---

## Private-beta convergence gate

The private beta is launch-ready only when:

- [ ] F6 ingestion-ready benchmark is still valid against the release revision.
- [ ] B7 product-track release candidate passes.
- [ ] The corpus track below passes its beta corpus acceptance criteria.
- [ ] A live census confirms shown sources, documents, chunks, propositions,
  quotes, licenses, and retrievability; counts are not copied from old notes.
- [ ] Representative answer/evidence review covers the corpus shapes actually
  launching.
- [ ] Tier 2 conditions are either not triggered or fully satisfied.
- [ ] Alex approves the deployment and private-beta audience.

### Tier 2 gate — before public signup or more than ~20 beta users

- [ ] STEPBible CC-BY-NC use and attribution audited.
- [ ] openbible.info attribution exists on every surface that serves its data;
  if no such surface ships, record not applicable.
- [ ] Every shown SermonIndex-derived source is reviewed for visibility/legal
  posture.
- [ ] DMCA agent and documented takedown procedure exist.
- [ ] Guest-limit abuse coverage is tested, not inferred.
- [ ] Admin minimums remain complete against the deployed revision.
- [ ] The quote verifier remains valid.

---

## Open decisions — Alex required

| ID | Decision | Current default | Trigger/evidence |
|---|---|---|---|
| 1 | Cold storage vs visibility gate | Visibility gate; deletion parked | Final hardening or legal need |
| 3 | Near-1930 public-domain works | Do not ingest | Title-level publication evidence; annual January 1 recheck |
| 10 | Precept Austin word-study rewriting | Do not rewrite | Faithfulness method that avoids meaning drift |
| 11 | Hebrew lexicon permission (TBESH) | Blocked | Written permission from Online Bible |
| 18 | System-prompt review timing | Hold | F4 after answer shapes and concurrency stabilize |
| 19 | Archaic commentary modernization | Hold | Licensing plus side-by-side faithfulness-review design |
| 20 | Generation-output verification guard | Accept residual gap | F4 diagnostic; no sixth judge without new evidence |
| 21 | Numeral-heading chapter detector | Leave unwired | Per-book validation surviving both known regressions |
| 23 | Quote hardening before next batch | No further teacher batch | F4 decision from 20 Prince rejects and cap evidence |
| 24 | `pending` vs `draft` quote status | Preserve both | Compatibility audit and migration plan |
| 25 | Study-panel drag behavior | Swipe-only | Alex finds material mobile benefit |
| 26 | `jewish_perspectives` table | Leave in place | Explicit approval for a dedicated drop migration |

---

## Horizon — captured, not scheduled

These require a fresh specification and do not authorize construction:

1. Manna code/repository/domain/copy/visual migration.
2. Verse-linked commentary enrichment with side-by-side modernization review.
3. Feedback-to-reviewable-content flags; never direct eligibility mutation.
4. Consent-based search analytics and corpus-gap alerts.
5. Specific follow-up questions that move users outward, not increase time-in-app.
6. Long-conversation handoff with token trigger, provenance, privacy, and user control.
7. Isolated Precept Austin retrieval experiment without weakening exclusions.
8. Reliable per-book structure and attribution boundaries.
9. Shared admin notification system for position drift and content review events.

### Not doing

- No stored/pre-reviewed answer catalog or human review gate on serving.
- No sixth probabilistic claim-support judge without new evidence.
- No teacher taxonomy or theological-family labels.
- No synthetic feed or retention-maximizing roadmap.
- No quote extraction from flat book chunks without trustworthy boundaries.
- No new YouTube ingestion unless Alex explicitly reopens it.
- No direct feedback-to-eligibility mutation.

---

## Standing rules

1. Read `CLAUDE.md` and this file in full before non-trivial writes; load other
   canonical docs by task surface.
2. Run read-only diagnostics and confirm the premise before build work.
3. Before a full batch, complete a dry run and one isolated real-item proof.
4. Every batch ends with attempted / stored / errored / skipped reconciliation,
   independently checked against the live DB.
5. Long jobs use resumable timestamped logs, checkpoints, bounded retries,
   explicit cost/allowance limits, and abort behavior.
6. Any corpus-scale LLM run gets a cost estimate before execution; $50 is the
   ceiling unless Alex explicitly approves more.
7. Production DB-write sessions use the plain-script path, never the agent
   harness. The harness may build and test those scripts against fixtures but
   may not execute the production write.
8. Preserve user work in a dirty tree. Git runs from the repo root. Parallel
   writers use isolated worktrees and disjoint file ownership.
9. Build commits and docs/records commits are always separate.
10. Shipping a fix includes correcting canonical records in the same session.
11. Closed work collapses to one evidence pointer; history belongs in
    `docs/plan-archive.md`.
12. Answers paraphrase and cite; verified verbatim text is served only through
    the quote component.
13. Side-by-side answer/evidence review, not blind reading, is the manual method
    for generation leakage checks.
14. Mechanical workers never receive theological, answer-path, licensing,
    production-write, or failure-mode judgment authority.
15. No worker result is complete until Opus records a verdict with evidence.
16. Destructive filesystem/Git actions, pushes, deploys, migrations, production
    writes, doctrinal content, and material scope changes require Alex.

---

## Completed foundation — terse index

Full history is in `docs/plan-archive.md`. Current foundations include:

- shared-ingest chokepoint, alias/sentinel model, all-or-nothing writes, and
  proposition provenance;
- proposition backfill and safe repeated-title chapter extraction subset;
- sole durable async answer path with metering, persistence, worker deployment,
  and transaction-pooler configuration;
- inline study panel, source panels, and teacher-card content gate;
- position-paper fence, contradiction exclusion, guarded fallback, V1 stored-
  position matcher, and one-hop evidence injection;
- commentary/Precept answer exclusion and grounded citation verification;
- quote schema, deterministic verifier, selection, frontend rail, sub-chunk
  exclusion, automatic verifier-gated approval, and Derek Prince non-book
  curation (477 approved across 496 documents attempted);
- Ravenhill, Savchuk, and Poonen Tier 1 visibility flip verified on the serving
  path.

---

# After the build plan — extraction and ingestion only

Everything below begins as continuous corpus production after F6 passes. It is
deliberately outside the build plan. If a source reveals a missing platform
capability, quarantine that source and open a separately approved build packet;
do not quietly turn an ingestion run into product development.

## Corpus-track operating contract

The corpus lane uses deterministic, resumable scripts for production writes.
The three-model harness may prepare manifests, perform read-only diagnostics,
review samples, and analyze reconciliation evidence, but it does not execute
production DB writes.

| Claude Code | Kimi via OpenCode Go | Grok |
|---|---|---|
| Opus approves source eligibility, sampling plans, exceptions, and final corpus acceptance. Claude may prepare/review scripts but production writes remain plain-script sessions. | Prepare bounded source manifests, extraction proposals, normalization fixtures, and non-judgment transformations until allowance exhaustion; Sonnet fallback applies. | Inventory files/metadata, validate checksums and counts, inspect logs, compare dry-run/write results, and independently reconcile DB counts. |

Every source moves through:

```text
legal/source approval
→ immutable inventory and checksum manifest
→ parser/extractor fixture tests
→ dry run
→ one isolated real-item write
→ reconciliation and content sampling
→ bounded resumable batch
→ independent DB reconciliation
→ representative answer/evidence review
→ corpus acceptance or quarantine
```

No stage may be skipped because another source previously passed it.

## A1 — Establish the beta corpus manifest

- [ ] Define the minimum source/teacher/content-shape coverage required for
  private beta; corpus size alone is not the acceptance measure.
- [ ] Re-query live source/document/chunk/proposition/quote/license/visibility
  state and attach timestamps.
- [ ] Classify every candidate source as ready, needs legal evidence, needs
  parser work, needs human content judgment, or blocked.
- [ ] Fix batch order, sampling rate, expected counts, cost estimate, storage
  estimate, and quarantine path before processing.

## A2 — New Wine

Known historical evidence: 167 raw PDFs were unprocessed and 9 ingested at the
2026-08-08 inventory. Recount from source files and the live DB before acting.

- [ ] Create an immutable manifest with file identity/checksum and DB match.
- [ ] Dry-run all files and classify parser/extraction failures.
- [ ] Complete one isolated write and reconcile every table touched.
- [ ] Run bounded resumable batches with attempted / stored / errored / skipped
  totals and no silent duplicates.
- [ ] Review representative extracted content and served answer evidence before
  marking the source accepted for beta.

## A3 — Existing converted sources and missing combinations

- [ ] Reconcile Ravenhill, Savchuk, and Poonen visibility and actual retrievable
  content before further quote work.
- [ ] Run further teacher quote extraction only after Decision 23 is closed.
- [ ] Preserve the distinction between “document received a candidate” and
  “document has an approved quote.”
- [ ] For HelloAO, keep the 12 missing book/commentary combinations quarantined:
  verse-level content is absent or only chapter introductions exist. Supporting
  introductions requires a separately approved chapter-level build contract.

## A4 — Reference datasets

OpenBible cross-references, Strong's, TIPNR, STEP-derived data, and similar
sources each require their own legal, attribution, schema-fit, ingestion, and
serving-surface evidence. Approval of one dataset never transfers to another.

- [ ] Record exact upstream version, license, attribution text, retrieval date,
  checksum, transformation, and serving surfaces.
- [ ] Prove source-specific dry run, isolated write, rollback, and reconciliation.
- [ ] Verify required attribution on every surface before the data becomes shown.

## A5 — Public-domain books and Pentecostal archives

- [ ] Perform title-level publication/legal verification, especially near the
  moving January 1 public-domain boundary.
- [ ] Preserve edition and page/provenance metadata sufficient for attribution.
- [ ] Do not extract quotes from flat book chunks until body/apparatus and
  chapter boundaries are trustworthy under Decision 21.
- [ ] Quarantine OCR or structural failures by title; do not lower global
  correctness rules to increase throughput.

## A6 — Owned verse-anchored synthesis

This is not eligible for ingestion until enough source material exists and Alex
approves a written specification covering provenance, attribution, doctrinal
review, update/version behavior, and serving boundaries. It is listed here only
to prevent it from being mistaken for routine extraction.

## Corpus-track beta acceptance

- [ ] The beta manifest's required teachers, source types, and representative
  user-question areas have sufficient retrievable evidence or an explicitly
  honest-empty product behavior.
- [ ] Every accepted source has current license/visibility evidence and required
  attribution.
- [ ] Every production batch has immutable input identity, resumable logs, hard
  reconciliation, and sampled content-quality evidence.
- [ ] No unresolved parser, OCR, attribution, boundary, or theological-review
  defect was hidden by aggregate success counts.
- [ ] Representative answers cite and accurately reflect each launching corpus
  shape under side-by-side evidence review.
- [ ] Opus issues the corpus-track verdict; Alex resolves every
  `HUMAN_REQUIRED` licensing or theological judgment.

---

*v7.0 makes the ingestion-ready benchmark the boundary between foundation work
and continuous corpus production, adds explicit Claude/Kimi/Grok parallel lanes,
pins Opus 5 as judgment authority, defines Kimi→Sonnet fallback, and places all
extraction and ingestion work after the build plan.*
