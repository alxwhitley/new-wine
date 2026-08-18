# Rhemata — Private-Beta Blocker Plan

> This is the only active work queue. Later work lives in `docs/roadmap.md`;
> completed and superseded reasoning lives in `docs/plan-archive.md`.

**Goal:** private beta ships with **quoting ON**, so quality quotes (correctly
tagged from the existing taxonomy, safe presentation under open teacher
scope) are on the launch critical path — without compromising propositions,
generated answers, or recoverability. Web-article ingestion remains an
attended parallel track.

**Current item:** **QuoteRail design polish (Claude)** — functional Q2/Q3
re-enable is DONE (28 gold rows approved; `QUOTE_SELECTION_ENABLED=true`;
smoke gold-only). Visual/taste pass on Settled #28 presentation is deferred
to Claude by Alex (2026-08-19). Parallel blocker still waiting: **W5–W6**
quarantined article proof. Plan:
`docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md`.

## Governing boundary

- A new finding interrupts this queue only if it can plausibly cause theological
  error, teacher misrepresentation, data loss, a security/privacy breach, or
  failure of the core beta journey. Everything else is classified Scheduled,
  Triggered, or Parked in `docs/roadmap.md`.
- Audits and implementation tasks use named files, acceptance tests, and a stop
  condition. Adjacent findings are recorded; they do not expand the session.
- Repository-only work may run back to back. Production database writes,
  deployments, source-visibility changes, and quote-rail re-enablement are
  attended gates requiring Alex's explicit approval.
- Every write path follows dry run → one isolated hidden proof → reconciliation
  → explicit release → bounded batch. No general worker may claim an unrelated
  row during the isolated proof.
- Corpus-scale LLM quote propose runs require a **named cost estimate** before
  execution and a **$50 ceiling** unless Alex explicitly approves more.

## Active blocker sequence

### W1–W4 — Safe web-article runway

**Status:** DONE — merged to `main` 2026-08-18 (PR #1
`harness/quote-containment-and-staging`, closing commit `a8a7731`, merge
`923f1ed`). Quote-rail flag (default off), single-row `--row-id` claiming, the
staged web-article contract, and the zero-write preview all verified live
against the merged code. Full detail: CLAUDE.md Invariant 16 + the
quote-containment Landmines entry.

### Q0 — Quote quality design accepted (launch-critical)

**Status:** DONE 2026-08-19 — revised spec committed (`95c7ae0` and follow-ups).
Alex accepted the adversarial revision. Beta **ships with quoting ON**, so this
track is launch-critical (not post-launch).

Decisions locked in the spec + CLAUDE.md Settled #29:

- LLM propose + quality/serveability gate + authenticity verify (quality gate
  is an explicit authorized exception; wrong both ways; logged).
- Topic labels = existing taxonomy (`scripts/taxonomy.py` / `docs/taxonomy.md`),
  passage-level — not a new vocabulary, not document-tag inheritance.
- V1 selection = question ↔ `quote_text` only; tag soft-boost deferred.
- Legacy 793 = **live-but-unserved** while rail is off during build; gold set
  before selection-ineligibility; presentation before re-enable.
- Boundary overrun must be root-caused and hardened **before** rebuild writes.
- Alex authorized Grok to implement this track (2026-08-19); production
  quote writes and rail re-enable remain attended Alex gates.

### Q1 — Pre-implementation gates + implementation plan

**Status:** DONE enough to execute — boundary harden + plan landed 2026-08-19.

- [x] Spec accepted; Settled #29 recorded (quality-gate exception + taxonomy).
- [x] Vocabulary source chosen: reuse `scripts/taxonomy.py` `VALID_TAGS`
  (human ref: `docs/taxonomy.md`) — no second list.
- [x] Implementation plan written (Grok, Alex-authorized):
  `docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md` with named
  gold-slice cost band (~$15–40 / 10 docs; full Prince non-book out of
  ceiling).
- [x] Boundary root-cause + verifier harden (`9a4c141`):
  `internal_paragraph_break` — live evangelist overrun refuses; first
  paragraph control passes; `test_quote_verifier.py` all green.
- [x] Alex authorized Grok to run this plan (this session).

### Q2 — Gold extract + presentation + legacy selection-ineligibility

**Status:** DONE enough for re-enable 2026-08-19. Gold apply + eligibility +
presentation code landed; **visual/taste sign-off deferred to Claude** (Alex)
while the functional rail is live.

- [x] Costed dry-run propose + calibration note (paid #2: 27 verify-pass /
  ~$1.42 / 59 windows) —
  `docs/audits/quote_propose_calibration_note_2026-08-19.md`.
- [x] Schema committed + migration 089 applied (topic_ids /
  quality_pipeline_version / selection_eligible; legacy
  selection_eligible=false).
- [x] Attended gold write on 3 calibration docs (`--limit 3 --apply
  --status pending`) + hard reconciliation — **stored=28**,
  refused_quality=11, refused_verify=3, errors=0; later promoted
  pending→approved (28/28) for re-enable.
- [x] Selection eligibility = new-pipeline/gold only in code.
- [x] Presentation code: visual separation + teacher/source on the quote
  (#28) — **functional fields live**; design polish deferred to Claude.
- [x] Legacy 793 selection-ineligible via migration 089 backfill (rows
  remain; unselectable).

### Q3 — Regressions + attended quote-rail re-enable

**Status:** DONE 2026-08-19 — flag on + smoke gold-only. (Absorbs prior W8
quote proofs.) Residual: QuoteRail design polish (Claude), not a re-enable
gate.

- [x] Flag-off regressions: baptism FP class; honest no-support; exact
  chunk IDs; **no bad quote IDs**; bounded teacher-card (no quote rail);
  eligibility mutation. Article-supported answer proof deferred until
  W5–W6 lands a live article.
- [x] Pending→approved for the 28 gold rows (attended; 28/28 reconciled).
- [x] Attended `QUOTE_SELECTION_ENABLED=true` on Railway `rhemata` +
  `answer-worker` + smoke — job `6e1e0b62-…`,
  `policy_v3:quote_selection=true`, 3 quote IDs all
  `quote_quality_v1` / approved / selection_eligible; resolve returns
  work_title + topic_ids + restated_point.

### W5–W6 — One quarantined article proof

**Status:** WAITING on Alex's source/production approval (W1–W4 prerequisite
is satisfied). **Not the current item** — attended parallel track; does not
displace Q1–Q3 unless Alex reorders. Quote containment deploy remains part of
its checklist where still relevant.

- [ ] Alex selects the exact article, confirms teacher/source and clearance, and
  approves deploying quote containment.
- [ ] Run the full no-write preview and review every proposed proposition beside
  its source passage; proposals remain ineligible and quotes remain proposals.
- [ ] Execute exactly one row-pinned write into a hidden source; reconcile
  attempted/stored/skipped/errored plus document/chunk/proposition state.
- [ ] Prove rerun idempotency and a row-level rollback procedure before release.
- [ ] Promote only propositions that pass the canonical eligibility checks;
  keep the article hidden until answer-integrity review passes.

### W7–W8 — Quote and answer integrity (partially superseded)

**Status:** Relevance + idempotency DONE (`82ec0f5`). Remaining work folded
into Q1–Q3 above.

- [x] Passage-level relevance + deterministic tie-break + idempotent create.
- [x] Teacher scope OPEN — Settled #28; presentation required before re-enable.
- [x] Visible label policy — **semantic topic** (taxonomy tag) on the topic
  chip; **work/source title** on the attribution line (spec).
- [x] Legacy audit ran; disposition = live-but-unserved during build, then
  selection-ineligible before re-enable; rebuild via new pipeline (not
  salvage-in-place as v1).
- [x] Candidate origin for bulk Prince path — **mechanical** (not LLM); closed
  by read-only pipeline map 2026-08-19.
- [ ] Boundary overrun investigation — moved to **Q1** (must precede rebuild).
- [ ] Answer-integrity proofs + re-enable — moved to **Q3**.

### W9 — Recoverability and first small batch

**Status:** QUEUED after article path / Q3 as applicable.

- [ ] Record authoritative Supabase backup/PITR retention, restore granularity,
  owner, RTO/RPO, and exclusions; prove the safest available restore scope or
  record Alex's explicit acceptance.
- [ ] Run one named, costed, resumable web-article batch with immutable inputs,
  logs, hard reconciliation, quality sampling, and an explicit release decision.

## Explicitly outside this finish line

- **Triggered / Scheduled later:** tag soft-boost in quote selection (after
  measurement); full Prince corpus rebuild beyond the gold slice; New Wine OCR
  resume; product B1–B7; corpus A1–A6.
- Migration 088 is already applied. Its isolated processor proof completed on
  queue row `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99`; never reapply it.

## Session close

Record only the original outcome, its acceptance result, classified discoveries,
Alex-approved scope changes, and the next single item. Track: original outcome
completed, unplanned investigations started, findings promoted to Blocker, and
active blocker count. Healthy target: completed, zero, rare, and one.
