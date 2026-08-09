# Rhemata — Master Plan (v6.1 · outcome-driven)

> **Purpose:** this file answers four questions only: what outcome is being
> pursued, what blocks it, what happens next, and what still needs Alex's
> decision. Build history and superseded reasoning live in
> `docs/plan-archive.md`; current implementation detail lives in
> `ARCHITECTURE.md`; session state lives in `rhemata-status.md`.
>
> **Authority:** `CLAUDE.md` owns invariants and settled decisions. This plan
> may sequence those decisions but may not reopen or silently reinterpret them.
> Counts and deployment state are evidence, not durable facts: re-query before
> acting when they are load-bearing.

---

## Product outcome and current milestone

Rhemata (future product name: **Manna**) helps a discerning Spirit-filled lay
believer get a fresh, cited answer grounded in real named teachers, then move
toward those teachers, Scripture, and a local church rather than treating the
product as a spiritual authority.

**Current milestone: backend/infra complete, ingestion becomes the normal
operating mode.** This is an engineering readiness milestone, not a launch and
not a claim that the corpus is complete.

### Milestone exit criteria

The milestone is complete only when all of the following are evidenced:

- **Serving:** the sole async answer path survives a controlled production-like
  concurrency window at the 100-generation dial without lost jobs, duplicate
  billing, skipped verification, or unbounded queue growth.
- **Correctness:** every served path preserves the ranked failure-mode order in
  `CLAUDE.md`; no known answer path bypasses license/visibility, commentary,
  attribution, citation, or position-paper guards.
- **Ingestion:** every document-writing ingest path routes through
  `shared_ingest.ingest_document()`; a dry run, one-item proof, batch accounting,
  and DB reconciliation are standard and documented.
- **Recoverability:** production DB backup/PITR status is known, and the restore
  plan has an owner and a tested scope. If a full-project restore cannot be
  tested before this milestone, that limitation must be explicitly accepted by
  Alex rather than silently waived.
- **Operability:** production dependencies are reproducible; failures are visible;
  the remaining known gaps are either closed, explicitly accepted, or moved to a
  later trigger with an owner.
- **Records:** `PLAN.md`, `CLAUDE.md`, `ARCHITECTURE.md`, and
  `rhemata-status.md` agree about live architecture and policy.

### Explicit non-gates

These do **not** block this milestone: completing the corpus; book quote
extraction; the Manna rebrand; public signup; the Tier 2 legal/admin package;
future commentary enrichment; the owned verse-anchored synthesis initiative;
or speculative product features in the Horizon.

---

## Now — ordered execution queue

Only this section defines near-term order. A later item may be researched early,
but it does not displace an earlier gate without updating this plan.

### 1. Prove the 100-generation dial

**Why first:** horizontal scale is the last unproven claim at the center of the
async architecture. Latency optimization before this test risks optimizing the
wrong bottleneck.

**Scope:** design and run a bounded, production-representative concurrency
window. Confirm provider RPM/ITPM/OTPM headroom before the run; define abort and
rollback conditions; do not expose real users to an uncontrolled experiment.

**Acceptance criteria:**

- [ ] The test plan fixes request mix, worker count, ramp shape, duration,
  provider limits, cost ceiling, success thresholds, and abort conditions.
- [ ] At the 100 dial, every accepted submission reconciles to one terminal job
  outcome; no job is lost or permanently stranded.
- [ ] Single-flight behavior, per-caller metering, persistence, retry behavior,
  and verification are checked under concurrency—not inferred from unit tests.
- [ ] Queue wait, generation time, end-to-end p50/p95, error rate, provider
  throttling, and worker utilization are captured.
- [ ] A hard reconciliation reports submitted / deduplicated / completed /
  refused / errored / timed out / persisted.

**Decision after evidence:** only then choose whether the next constraint is
worker count, provider limits, query/generation cost, or answer latency. The
latency target remains **20 seconds**; it is a target, not a milestone gate until
the concurrency evidence shows speed is the limiting risk.

### 2. Close recoverability and reproducibility gaps

This is one readiness checkpoint with two independent strands.

**2A — backup / restore**

- [ ] Determine Supabase project-level backup and PITR status through an
  authoritative account/project surface.
- [ ] Record retention, restore granularity, responsible owner, expected RTO/RPO,
  and what is not covered.
- [ ] Test the safest available restore scope. Record-level restore was proven
  2026-07-24; full-project disaster restore and staging remain unproven.
- [ ] If credentials or plan tier prevent proof, bring Alex an explicit accept /
  upgrade / defer decision with consequences.

**2B — deterministic production dependencies**

- [ ] Pin the production-relevant transitive versions that have already caused
  local/Railway divergence, especially `pydantic` and `starlette`.
- [ ] Rebuild in a clean Python environment and run backend/admin-auth smoke
  tests before deployment.
- [ ] Confirm worker and backend manifests intentionally use their documented
  Python versions; resolve any mismatch between docs and manifests.

### 3. Finish the ingestion-default contract

The chokepoint conversion is complete. The remaining work is to make the
settled “new material defaults visible” policy true without weakening the live
license gate.

**Known state (re-check before write):** Ravenhill, Savchuk, and Poonen were
flipped to `shown` on 2026-08-09; the sentinel remains hidden; the other hidden
rows observed then were empty shells. Schema and registration defaults still
say `hidden`, and `ARCHITECTURE.md` still documents fail-closed registration.

**Acceptance criteria:**

- [ ] Define precisely which newly registered source classes default to
  `shown`, including how the sentinel, unresolved aliases, empty shells, and
  Tier 2 legal review behave.
- [ ] Update schema/defaults and every registration path consistently; do not
  alter `license_status`, `retrievable`, or the serving-gate SQL by accident.
- [ ] Prove one dry run and one isolated real registration through the actual
  chokepoint, then reconcile the resulting source/document/chunk/proposition
  state.
- [ ] Update `ARCHITECTURE.md` in the same session so policy and code agree.

### 4. Decide the remaining pre-milestone quality work

Run a short evidence pass, then make three explicit keep/hold/kill calls. These
are not invitations to build first.

1. **Generation-output verification (Decision 20):** run the already-queued
   read-only false-flag diagnostic against known-good positions. Do not build a
   sixth model-judge variant. Choose: accept the residual risk, retain a narrow
   deterministic check, or define new evidence that would justify reopening.
2. **System-prompt review timing (Decision 18):** review only after the three
   answer-source shapes and concurrency behavior are stable; otherwise the
   review target is moving. Decide whether this is required before milestone
   close or before private beta expansion.
3. **Quote extraction hardening:** before another bulk extraction, decide
   whether to add deterministic majority-Scripture and unbalanced-quotation
   checks based on the 20 Prince review rejects (two batches). No further teacher batch until
   that decision is recorded.

### 5. Declare the milestone or record the exceptions

- [ ] Re-run each exit criterion against repo, deployment, and live DB evidence.
- [ ] List any consciously accepted residual risk with owner and revisit trigger.
- [ ] Move completed narratives to `docs/plan-archive.md`; leave only concise
  evidence pointers here.
- [ ] Update `rhemata-status.md` and make the required docs-only close commit,
  separate from build commits.

---

## Active workstreams outside the critical path

These may proceed when they do not compete with the ordered queue. They do not
define milestone completion.

### Corpus ingestion

- **New Wine (#26):** 167 raw PDFs were unprocessed as of the 2026-08-08
  inventory; 9 had already been ingested. Recount before batching.
- **HelloAO (#27):** conversion is complete. Twelve missing book/commentary
  combinations lack verse-level content or expose only chapter introductions.
  Supporting introductions requires a new chapter-level data/chunk contract;
  it is not a retry of the existing script.
- **Reference datasets (#28):** openbible.info cross-references, Strong's, TIPNR,
  and similar datasets each need a source-specific legal and ingestion plan.
- **PD books / Pentecostal archives (#29):** title-level public-domain checks are
  required for near-boundary works; the legal line changes each January 1.
- **Owned verse-anchored synthesis (#30/#31):** not designed and not schedulable
  until sufficient source material and a written spec exist.

Every batch follows Standing Rules 1–4 below. Corpus counts never become durable
truth in this file.

### Quote rail curation

**Derek Prince non-book curation complete (2026-08-09).** All 496 documents
attempted across two batches (249, then the remaining 247); every candidate
independently reverified against live chunk content and manually screened
for majority-Scripture and incoherent-fragment defects, the two classes the
automated verifier cannot catch. Combined: **477 approved**, 20 rejected
(logged to `quote_verification_log`, left `pending`), 1 untracked pre-run
row left outside scope. **476/496 documents carry ≥1 approved quote — 20 do
not**, because their sole extracted candidate was rejected: extraction
reached all 496 documents, approval did not clear all 496.

A snapshot-capture bug was found and fixed mid-session:
`quote_source_revisions.passage_text` was storing only the candidate span,
not the full chunk, making the DB trigger's substring check a no-op
(CLAUDE.md Landmines). Fixed in commit `4e3a0d1`; the fix's real effect was
proven with a rollback-only transaction test — a fabricated quote passed
under the old convention and was correctly rejected under the fixed one.
**The 239 quotes approved before the fix were NOT regenerated.**
Determination: each was already independently re-verified against LIVE
chunk content by a separate mechanism (`verify_quote_candidate()`) at
approval time, so their current correctness is unaffected — the snapshot's
only remaining job is protecting against *future* chunk-content drift,
which this product has no live mechanism for today. Regenerating them is
optional hygiene, not a correctness requirement. Full evidence:
`rhemata-status.md`.

- Next eligible teachers: Savchuk, Ravenhill, Poonen — no batch scheduled
  until Queue item 4 decides extractor hardening (now informed by 20
  rejects across two batches, not 10).
- **Confirmed 2026-08-09 (read-only): `--per-doc-limit=1` is an explicit,
  working-as-designed cap, not incidental truncation** — the extractor
  ranks every candidate across the whole document before capping to one.
  No recorded reason for the value 1; raising it needs only a CLI flag on
  a future run, no code change. Whether unused quotable material actually
  exists in already-processed chunks was not checked — a separate
  question from why the cap exists. Full detail: `rhemata-status.md`.
- `QUOTE_TOPIC_SIMILARITY_THRESHOLD=0.40` remains provisional. Calibration needs
  real labeled traffic; do not tune from intuition or a synthetic-only set.
- Book-type quote extraction remains tabled. Flat book chunks lack reliable
  body/apparatus and chapter boundaries; human proposals for 18 high-confidence
  books do not resolve Decision 21 or make the detector safe.
- `quotes.status='pending'` and `'draft'` currently express the same waiting
  state. Consolidation is a schema/API migration, not cosmetic cleanup; decide
  compatibility and data migration before acting.

### Position layer

The one-hop stored-position evidence path is built, pushed, and live. Rendered
position text is never served; underlying propositions enter the normal guarded
answer path. V1 contains six seed topics. Durable expansion is deferred pending
real usage.

Before expansion, design the scheduled refresh mechanism and its dependency on
an admin notification surface. Meaningful shifts escalate; routine drift may
update silently; version history is retained; no runtime dominance override is
added. These are settled decisions, not open design options.

### Inline Study Panel

- **#42.5 Phase 2:** floating overlay v3 needs one authenticated production pass;
  local doubles are insufficient.
- **#43:** swipe-to-close is shipped. Alex must decide whether that reduced scope
  is final or whether drag-to-follow-with-peek remains desired.

### Chokepoint residuals

- **`documents.full_text` (#7):** 3,539/3,597 documents were missing it in the
  2026-08-09 census. Before calling this a backfill, identify concrete consumers,
  storage/cost, reconstruction fidelity from chunks, resumability, and rollback.
  If no current consumer needs it, defer explicitly rather than sweeping the DB.
- **`jewish_perspectives` (#14):** two rows, zero runtime references at last
  check. Dropping it requires Alex's explicit approval and a dedicated DB-write
  session; otherwise leave it inert.
- **Feedback-to-flag (#16):** thumbs feedback exists, but there is no proposition
  link or automatic eligibility change. Keep/kill depends on the fuller product
  design in Horizon 3; never make a thumbs-down directly mutate theological
  evidence without a reviewable intermediate state.

---

## Tier 2 gate — before public signup or more than ~20 beta users

Crossing either trigger requires a fresh census and all applicable items below.
This is a launch gate, not near-term active work.

- [ ] STEPBible CC-BY-NC use and attribution audited (#32).
- [ ] openbible.info attribution exists on every surface that serves its data
  (#33); if no cross-reference surface ships, record the item as not applicable.
- [ ] Every shown SermonIndex-derived source is reviewed for visibility/legal
  posture (#34).
- [ ] DMCA agent and documented takedown procedure exist (#35).
- [ ] Guest-limit abuse coverage is tested, not inferred (#36).
- [ ] Admin minimums are complete (#37): actionable contributor activity,
  pending-state visibility where still relevant, real account-deletion workflow,
  and usable mobile navigation. Split these into independent tasks before build.
- [ ] The 100-dial serving proof and quote verifier remain valid against the
  deployed version at launch time.

---

## Open decisions — Alex required

Only genuinely unresolved choices belong here. “Deferred” means the current
default remains in force until its trigger occurs.

| ID | Decision | Current default | Evidence/trigger needed |
|---|---|---|---|
| 1 | Cold storage vs visibility gate | Visibility gate; deletion parked | Revisit only for final hardening or legal need |
| 3 | Near-1930 public-domain works | Do not ingest until title-level verification | Publication evidence per title; annual Jan 1 recheck |
| 10 | Precept Austin word-study rewriting | Do not rewrite | A faithfulness method that avoids meaning drift; separate from retrieval reintroduction |
| 11 | Hebrew lexicon permission (TBESH) | Blocked | Written permission from Online Bible; Greek datasets unaffected |
| 18 | System-prompt review timing | Hold | Queue item 4 after answer shapes/concurrency stabilize |
| 19 | Archaic commentary modernization | Hold | Licensing conversations plus a faithfulness-review design |
| 20 | Generation-output verification guard | Accepted residual gap | Existing direct-contact false-flag diagnostic; no sixth judge variant |
| 21 | Numeral-heading chapter detector | Leave unwired | A per-book validation strategy that survives both known regression classes |
| 23 | Quote extractor hardening before next batch | No further bulk batch | Decide majority-Scripture/unbalanced-quote checks from 20 Prince rejects, and whether to raise the confirmed `--per-doc-limit=1` cap |
| 24 | `pending` vs `draft` quote status | Preserve both for now | Compatibility audit and explicit migration plan |
| 25 | Study-panel drag behavior | Swipe-only remains shipped | Alex decides whether drag-to-follow materially improves mobile use |
| 26 | `jewish_perspectives` table | Leave in place | Alex explicitly approves a dedicated drop migration |

Previously listed items that are not decisions have been removed from this
table: quote serving is structurally on the sole async path; the admin shell is
settled as a modal; Tier 1→2 is a trigger/gate; the V1 topic list is adopted.
Resolved-decision reasoning remains in `CLAUDE.md` and `docs/plan-archive.md`.

---

## Horizon — captured, not scheduled

These ideas require a fresh spec before implementation. Their presence here is
not approval to build.

1. **Manna rebrand and full UI redesign.** Naming is settled; code, repo,
   domain, copy, and visual migration are not scoped. Trigger: backend/infra
   milestone complete and Alex explicitly begins product Phase 2.
2. **Commentary enrichment.** Verse-linked quotes plus faithful modernization of
   public-domain commentary. Requires ingestion-time verse anchors and a
   side-by-side faithfulness review; never infer altered doctrine.
3. **Feedback-to-actionable-content flags.** A thumbs-down should create a
   reviewable content flag with evidence provenance—not directly disable a
   proposition. Needs identity, granularity, notification, adjudication,
   rollback, and audit-log design.
4. **Consent-based search analytics and corpus-gap alerts.** Requires explicit
   per-user consent, retention/deletion policy, an admin notification system,
   and a definition of the honest-empty event.
5. **Specific follow-up questions.** Must help the user reach Scripture or a
   named teacher, not increase time-in-app; measure useful outward navigation,
   not clicks alone.
6. **Long-conversation handoff.** Soft nudge twice, then a hard stop was the
   captured concept. Before build, define a token-based trigger, summary
   provenance, user control, privacy/retention, failure behavior, and whether a
   hard stop is actually warranted.
7. **Precept Austin retrieval reintroduction.** Current hard exclusion remains.
   Any future experiment must be isolated, measurable for meaning drift, and
   must not weaken permanent quote/paraphrase exclusions.
8. **Book structure.** Decide whether reliable per-book boundaries are worth
   building. The 18 human-reviewed proposals are evidence inputs, not an
   automatic migration plan.
9. **Admin notification system.** Shared dependency for position refresh,
   feedback flags, and consented corpus-gap alerts. Define event types,
   severity, deduplication, read/resolved state, retention, and ownership before
   building any dependent feature separately.

### Not doing

- No stored/pre-reviewed answer catalog and no human review gate on serving.
- No sixth probabilistic claim-support judge without new evidence.
- No teacher taxonomy or theological-family labels.
- No synthetic content feed or retention-maximizing roadmap.
- No quote extraction from flat book chunks until attribution boundaries are
  trustworthy.
- No new YouTube ingestion unless Alex explicitly reopens it.
- No direct feedback-to-eligibility mutation.

---

## Standing session rules

1. Read `CLAUDE.md` and this file in full before non-trivial writes. Load other
   canonical docs by task surface.
2. Run read-only diagnostics and confirm the premise before build work.
3. Before a full batch, complete a dry run and one isolated real-item proof.
4. Every batch ends with attempted / stored / errored / skipped reconciliation,
   independently checked against the live DB.
5. Long jobs use resumable, timestamped logs with a bounded cost and abort plan.
6. Any corpus-scale LLM run gets a cost estimate before execution; $50 is the
   ceiling unless Alex explicitly approves more.
7. Database-write sessions use the plain-script path, never the harness.
   Repo-only multi-step builds use the harness contract in `CLAUDE.md`/`HARNESS.md`.
8. Preserve user work in a dirty tree. Git runs from the repo root.
9. Build commits and docs/records commits are always separate.
10. Shipping a fix includes correcting canonical records in the same session.
11. Closed work collapses to one evidence pointer; history belongs in
    `docs/plan-archive.md`, not the active queue.
12. Answers paraphrase and cite; verified verbatim text is served only through
    the quote component. Never claim the free prose channel makes fabrication
    impossible.
13. Side-by-side answer/evidence review—not blind reading—is the required manual
    method for generation leakage checks.
14. Use cheaper mechanical tooling only for non-judgment work. Never delegate
    theological, answer-path, DB-write, or failure-mode judgment to it.

---

## Completed foundation — terse index

The detailed build record, old item numbers, killed designs, and decision history
are in `docs/plan-archive.md`. Current foundations include:

- shared-ingest chokepoint, alias/sentinel model, all-or-nothing writes, and
  proposition provenance;
- full proposition backfill and safe repeated-title chapter extraction subset;
- sole durable async answer path with metering, persistence, worker deployment,
  and transaction-pooler configuration;
- inline study panel, source panels, and teacher-card content gate;
- position-paper fence, contradiction exclusion, guarded fallback, V1 stored-
  position matcher, and one-hop evidence injection;
- commentary/Precept answer exclusion and grounded citation verification;
- quote schema, deterministic verifier, selection, frontend rail, sub-chunk
  exclusion, automatic verifier-gated approval, and complete Derek Prince
  non-book curation (477 approved across all 496 documents attempted);
- Ravenhill, Savchuk, and Poonen Tier 1 visibility flip, verified on the real
  serving path.

---

*v6.1 removes completed narratives and resolved choices from the active sequence,
defines the backend/infra milestone, and converts vague residuals into evidence-
based gates. Git and `docs/plan-archive.md` remain the provenance record.*
