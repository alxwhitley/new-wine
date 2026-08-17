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

### Product track — B1-B7, after F6

This track may run concurrently with corpus production only after F6 passes.

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

### Corpus track — A1-A6, after F6

Production writes use deterministic, resumable scripts in an attended primary
Codex session. Each source follows: legal/source approval, immutable inventory
and checksum manifest, parser fixtures, dry run, one isolated real write,
reconciliation and sampling, bounded resumable batch, independent database
reconciliation, representative answer/evidence review, then acceptance or
quarantine. No stage transfers automatically from one source to another.

1. **A1 — Beta corpus manifest.** Define minimum teacher/source/content-shape
   coverage; re-query live state; classify candidates; fix order, sampling,
   expected counts, cost/storage estimates, and quarantine path.
2. **A2 — New Wine.** Recount files and live state; create an immutable
   manifest; dry-run all files; prove one write; run bounded reconciled batches;
   review extracted content and served evidence.
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

- F6 remains valid against the release revision.
- B7 and corpus acceptance pass.
- A live census re-queries shown sources, documents, chunks, propositions,
  quotes, licenses, and retrievability.
- Representative answer/evidence review covers the launching corpus shapes.
- Triggered Tier-2 conditions are either dormant or fully satisfied.
- Alex approves the deployment and private-beta audience.

### Separately approved database operation

Migration 088 and its isolated production proof remain Scheduled within the
applicable source-ingestion phase. Listing it here does not authorize the write.

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
cleanup; `jewish_perspectives`; the teacher-card refusal-copy question; shared
BOOK_MAP consolidation; and extraction-attempt history instrumentation.

### Horizon — requires a fresh specification

1. Manna code/repository/domain/copy/visual migration.
2. Verse-linked commentary enrichment with side-by-side modernization review.
3. Feedback-to-reviewable-content flags, never direct eligibility mutation.
4. Consent-based search analytics and corpus-gap alerts.
5. Specific follow-up questions that move users outward.
6. Long-conversation handoff with a token trigger, provenance, privacy, and user control.
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
