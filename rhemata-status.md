# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-17. Local `main` and `origin/main` were synchronized at
`4f476eb` before this records update. The pre-existing untracked
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

Alex replaced the old F2→F3→F4→F6 order after an ultra adversarial review. The
active path is controlled web-article ingestion: contain the broken quote rail,
pin isolated worker execution to one row, add a staged citable article contract,
and build a full-compute zero-write preview before any production action.

---

## Classified work

**Blocker — active:** W1–W4 repository-only safety block. It may run back to
back for about 3–4 hours, then stops before deployment or production writes.

**Blocker — waiting:** one Alex-approved hidden web article; quote relevance and
answer-integrity repair; recoverability before the first multi-article batch.

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

Execute W1–W4 from
`docs/superpowers/plans/2026-08-17-web-article-beta-fast-path.md`, then stop at
the repository-only checkpoint. Do not deploy, enqueue, ingest, change source
visibility, or alter production configuration in that block.

Process baseline for this records session: original outcome achieved; zero
unplanned investigations started; zero findings promoted to Blocker; one active
critical-path item.
