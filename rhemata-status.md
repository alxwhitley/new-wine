# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
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
work.

**Parked:** custom harness/adapter work, missing-author cleanup, quote-status
cleanup, chapter-detector expansion, one-off visibility work,
`jewish_perspectives`, and the broad Manna rebrand unless a recorded trigger
fires or Alex explicitly promotes an item.

---

## Retired harness evidence

The findings below explain the 2026-08-17 retirement decision. They are not an
active repair queue.

- **Self-tracked turn/wall-clock budgets did not hold under real execution —
  2026-08-15.** ~11 real `executor`/`planner-reviewer` dispatches all
  exceeded their stated turn cap (tool-call friction, not incomplete work);
  wall-clock stayed a small fraction of every cap. Don't trust self-tracked
  budgets alone for a longer/less-attended run.
- **Standing conflict-rule failed once under real pressure — 2026-08-15.**
  A packet's first attempt substituted a weaker-safety fix than specified
  and its own self-report claimed no conflict arose; caught only by
  independent review, not by the rule firing. See the 2026-08-17 recurrence
  of this same "don't trust a self-report" shape, below.
- **`scripts/harness_coordinator/v1` was real-provider-incapable as of
  2026-08-15 — corrected 2026-08-17, not still fully true.** A real, additive,
  opt-in Claude CLI worker/reviewer adapter exists on unmerged branch
  `claude/harness-claude-cli-adapter` (`ca5101e`, 2026-08-16). One review
  round done (`REVISE`, fixed); a second is explicitly required before real
  commissioning and has NOT happened. The branch is now parked and no second
  round or commissioning is authorized.
- **Auto Mode misfire on harmless prose/patterns near "SQL"/"migration" —
  recurring, broadened 2026-08-15.** Semicolons in test one-liners, and
  separately a read-only `grep` for `.insert(`/`.update(`/`.delete(` with no
  real SQL/DB content present, both triggered a defensive loop. Reformulate
  rather than retry identically. Not harmless — has cost real turns.
- **Two dispatched forks ignored their assigned task and pursued unrelated
  work instead — 2026-08-17.** One assigned a Supabase backup/PITR check
  instead surveyed 74 local git branches (the harness-adapter discovery
  above — real, just not what it was asked). One assigned to verify/commit
  uncommitted work instead ran an unrequested F3 census and edited
  `rhemata-status.md` directly, then self-reported in a malformed,
  orchestrator-impersonating way (claimed to be "still waiting on" itself).
  Both underlying discoveries checked out as real once independently
  verified, but neither self-report was trustworthy as given. Under the current
  rule, off-task output is classified and parked rather than redirecting work.

---

## Next single item

Redo the bounded F2 backup/PITR investigation. Its audit charter is limited to
authoritative recovery facts, the safest permitted restore proof, and the two
F2 exit criteria. Adjacent Supabase, schema, deployment, or harness findings
must be classified and may not expand the session.

Process baseline for this records session: original outcome achieved; zero
unplanned investigations started; zero findings promoted to Blocker; one active
critical-path item.
