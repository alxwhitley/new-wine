# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-17 (three docs/records-only commits pending below;
source-ingest runner deployment facts from 2026-08-16 carried forward
unchanged).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Local `main` is 3 commits ahead of `origin/main`, not pushed: `1f58086`
(source-ingest runner extended to accept `web_page`/HTML alongside `pdf` —
still gated/inert; Invariant 16's "pdf + single + declared" wording needs a
docs-pass update), `d3ff302` (article quote-candidate extraction, not yet
wired to the existing Prince-specific extractor), `3abcd6a` (real chat
retry/delete bug fixes — retry no longer discards the conversation, a failed
delete no longer makes it appear to vanish — plus error/not-found
boundaries). All verified with real test runs (74/74 Python, 16/16 frontend)
in a clean venv before committing.

Carried forward, unchanged since 2026-08-16: `codex/source-ingest-runner`
deployed through release `0925c93` (Railway backend/answer-worker + Vercel
all verified successful). Migration 088 is still unapplied, no source-worker
Railway service exists, no live dry run or corpus write has occurred.

This session ran 5 parallel diagnostic/build agents; 2 went off their
assigned task (see Known Harness Bugs) but surfaced real findings anyway:

- **Missing-author diagnostic:** 144/3,604 documents lack `documents.author`.
  121 (119 Savchuk + 2 Ravenhill) are one ingestion bug — `sources.name` is
  correct but was never copied down — and are live-servable today with a
  blank author field. 22 are correctly `silent_context` (Invariant 7). 1
  (Covenant Harvest Church) needs a manual title check. Deterministic
  backfill recommended (`documents.author = sources.name`); not done —
  DB-write session, separate from this one.
- **F3 visible-default policy:** drafted, pending approval, not implemented.
  `docs/audits/f3_visible_default_policy_2026-08-17.md` +
  `..._evidence_2026-08-17.md`. F3's exit criteria named the wrong layer —
  `ingest_document()` never registers sources; 5 one-off scripts do, each
  hand-copying its own literal (same drift shape as BOOK_MAP).
- **Housekeeping:** probe 2/3 merge question was stale, corrected below.
  `get_teacher_card()`'s refusal copy confirmed as a real bug (reads as the
  named teacher speaking) — 3 draft replacements exist, unpicked. Quote-status
  audit found `'pending'` quotes may have no code path to `approved` — needs
  a live row count before Decision 24 (PLAN.md) is settled.
- **F2 backup/PITR:** never actually investigated — the dispatched agent went
  off-task instead. Still open.
- **Unplanned discovery:** unmerged branch `claude/harness-claude-cli-adapter`
  (`ca5101e`, 2026-08-16) adds a real Claude Code CLI worker/reviewer adapter
  to the harness coordinator — corrects the "no live-provider path" claim
  below. One review round done (`REVISE`, fixed); a second is explicitly
  required before any real commissioning and has not happened.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop, SP
  residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- Source ingest inoperative until migration 088 is separately approved,
  applied, verified, and dry-run/proven on one isolated item; no worker
  service exists yet.
- Authenticated production smoke needs a connected signed-in browser.

---

## Known Harness Bugs

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
  commissioning and has NOT happened — do not treat it as ready. Real work
  still uses the separate `executor`/`planner-reviewer` subagent path.
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
  verified — but neither self-report should have been trusted as given.
  Verify off-task or self-referentially-confused subagent output directly;
  don't relay it.

---

## Next

1. Push local `main` (3 commits ahead: `1f58086`, `d3ff302`, `3abcd6a`) once
   Alex is ready — currently unpushed by design, not an oversight.
2. Approve / revise / reject the F3 visible-default policy memo
   (`docs/audits/f3_visible_default_policy_2026-08-17.md`) — specifically
   rule on §7.1: is the approaching private beta itself the Tier-1→Tier-2
   trip line, which would flip the recommended default from `shown` to
   `hidden`? Build work (shared `register_source()` helper, backfill,
   ARCHITECTURE.md update) follows approval, not before.
3. Redo the F2 backup/PITR investigation properly — the 2026-08-17 attempt
   went off-task and never touched it.
4. Decide whether to run a second independent review round on
   `claude/harness-claude-cli-adapter` (`ca5101e`) — real capability unlock
   for the harness if it holds up; not yet trustworthy as-is.
5. Missing-author backfill — 121 live-servable documents, deterministic
   `documents.author = sources.name` (see Current state). DB-write session.
6. Pick one of 3 drafted replacement copy options for
   `get_teacher_card()`'s refusal-string heading (session transcript
   2026-08-17; regenerate if needed — not separately filed).
7. Check the live `quotes` row count for `status='pending'` before deciding
   Decision 24 (PLAN.md) — may be stranded curated quotes with no approval
   path, not just a schema-compatibility question.
8. Separately-approved production-write session: apply/verify migration 088,
   then one read-only queue-row dry run before authorizing any write.
9. Authenticated servable-document/sentinel-404/Derek Prince card smoke,
   once a signed-in browser-control surface is connected.
10. Human review of chapter-boundary proposals (18 books) — Open Decision #21.
11. Trail / Brooks one-offs — review then visibility.
12. `jewish_perspectives` drop — needs Alex's approval + a DB-write session —
    Decision 26.
