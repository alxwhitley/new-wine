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

Carried forward, unchanged since 2026-08-16: `codex/source-ingest-runner`
deployed through release `0925c93` (Railway backend/answer-worker + Vercel
all verified successful). Migration 088 is still unapplied, no source-worker
Railway service exists, no live dry run or corpus write has occurred.

The F3 visible-default policy is drafted but awaits Alex's Tier-1/Tier-2
ruling. F2 backup/PITR remains the single active critical-path item because the
2026-08-17 investigation went off-task and produced no recovery evidence.

---

## Classified work

**Blocker — active:** F2 recoverability. Establish authoritative Supabase
backup/PITR, retention, restore scope, RTO/RPO, exclusions, and ownership; test
the safest available restore or record Alex's explicit acceptance.

**Blocker — waiting:** F3 ingestion-default policy awaits Alex's ruling on
whether private beta itself is the Tier-1→Tier-2 trip line. F4's two quality
decisions and the F6 benchmark follow in that order.

**Scheduled:** B1–B7 product work and A1–A6 corpus work begin after F6.
Migration 088 remains a separately approved database-write operation inside
the applicable phase.

**Triggered:** Tier-2 work begins at public signup or more than roughly 20 beta
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

Redo the bounded F2 backup/PITR investigation. Its audit charter is limited to
authoritative recovery facts, the safest permitted restore proof, and the two
F2 exit criteria. Adjacent Supabase, schema, deployment, or harness findings
must be classified and may not expand the session.

Process baseline for this records session: original outcome achieved; zero
unplanned investigations started; zero findings promoted to Blocker; one active
critical-path item.
