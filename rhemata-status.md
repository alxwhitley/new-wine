# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-18. Local `main` fast-forwarded to `origin/main` at
`923f1ed` (PR #1, `harness/quote-containment-and-staging`, closing commit
`a8a7731`) during this records update — the merge was already on
`origin/main` but not yet fast-forwarded locally. The pre-existing untracked
`Temporary-assets/` directory remains untouched.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Rhemata now uses a Beta Critical Path operating model. Codex is the primary
working surface; native agents/worktrees may assist bounded tasks. The custom
multi-provider coordinator and overnight harness are retired from active
development. Their code and history remain intact but no follow-up work is
authorized.

Planning is now split by operational purpose: `PLAN.md` is the short active
Blocker queue; `docs/roadmap.md` contains Scheduled, Triggered, and Parked work;
`docs/plan-archive.md` contains completed and superseded history. Ordinary
sessions do not load the roadmap or archive unless the task needs them.

`codex/source-ingest-runner` is deployed through release `0925c93`. Migration
088 is applied. Queue row `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99` completed an
isolated processor proof into document `35b53381-2153-4936-a97b-641a20e29205`
(two chunks, zero propositions because the source is public domain). No Railway
source-worker service exists; this was not a deployed-worker proof.

Alex replaced the old F2→F3→F4→F6 order after an ultra adversarial review with
the controlled web-article path (PLAN.md W1–W9). **W1–W4 (the repository-only
safety block) merged to `main` 2026-08-18** and is verified live in the code,
not just claimed: quote selection is now contained behind a default-off,
exact-opt-in flag (`QUOTE_SELECTION_ENABLED`) whose effect holds across fresh,
cached, idempotent-redelivery, and in-flight answers; live `--row-id` worker
execution is restricted to `--once` with parameterized, no-fallback single-row
claiming (a target row that isn't claimable returns no row, never a silent
substitute); hidden `web_page + single + declared` staging is now available
for existing non-sentinel sources with `license_status IN
('licensed','unlicensed')`; and a deterministic, zero-database-write
full-compute preview pipeline (metadata → chunks → embeddings →
propositions/provenance → usage evidence → proposal-only quote spans) exists
and is mutation-tested to prove it never writes. Full technical detail:
CLAUDE.md Invariant 16 and the new quote-containment Landmines entry.

---

## Classified work

**Blocker — active:** none. W1–W4 (repository-only) is complete and merged.

**Blocker — waiting:** W5–W6, all human/production-only gates, unchanged by the
merge — Alex selects and approves one hidden web article, confirms
teacher/source and clearance, and approves deploying this merged containment
code to the live Railway backend (repo merge alone does not put it into
production); then approves running a real (non-dry-run) preview; then one
hidden row-pinned write with reconciliation, idempotency, and rollback proof;
then eligibility/visibility/quote-repair decisions. Quote relevance repair
(W7–W8) and recoverability (W9) remain queued behind W5–W6.

**Scheduled:** broad visible-default policy, general prompt/claim-support work,
B1–B7 product work, and remaining corpus work after the web-article proof.

**Triggered:** New Wine PDF ingestion waits for an Alex-accepted blind OCR
benchmark win. Tier-2 work begins at public signup or more than roughly 20 beta
users. Load testing reopens only after measured beta evidence or a demonstrated
concurrency failure. Admin notifications wait for scheduled position-refresh
work. The Manna rebrand waits until Alex schedules it as a bounded product
phase.

**Parked:** custom harness/adapter work, missing-author cleanup, quote-status
cleanup, chapter-detector expansion, one-off visibility work,
`jewish_perspectives`, and other named roadmap entries unless a recorded
trigger fires or Alex explicitly promotes an item.

---

## Next single item

W1–W4 executed and merged (this update). Next is the attended W5–W6 gate from
the same plan doc: Alex selects and approves one hidden web article, approves
deploying quote containment to production, then runs the real preview, the
single hidden row-pinned write, and idempotency/rollback proof, before any
eligibility, visibility, or quote-repair decision. No further repository-only
work is queued ahead of that gate.

Process baseline for this records session: original outcome (verify the merge,
record it) achieved; zero unplanned investigations started; zero findings
promoted to Blocker; zero active blockers, one waiting on Alex.
