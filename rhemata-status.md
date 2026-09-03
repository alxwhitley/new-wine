# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-03. **PLAN.md has zero active blockers.**

---

## Current state

**A frontend change shipped to production this session** — the first deploy
since 2026-08-31. Production and `origin/main` remain at `bad58f6`; Vercel
production Ready (21s build), Railway `New Wine` settled Online with no builder
drift, `/docs` and `/health` both 200, `newwine.app` 200. No outage; the API
stayed Online throughout its rebuild. No database write, embedding purchase,
or feature-flag change happened.

Local `main` now contains merge commit `4d6813e` and is ahead of `origin/main`.
The reviewed default-off TIPNR execution tooling and its closeout records are
integrated locally but have not been pushed, deployed, or used against
production.

**The answer-wait ring is replaced by a staged step list** (`bad58f6`, four
files). `lib/loading-progress.ts` now exports `LOADING_STEPS` +
`activeStepIndex()` over explicit `STEP_ONSETS_MS` (0 / 1.7 / 4.9 / 9.5 /
18.4s); `estimateLoadingProgress()`, `loadingPhraseIndex()` and
`LOADING_PHRASES` are deleted. Done rows carry a check, the active row a
spinner, upcoming rows a dot at `opacity-60`. The last step never completes —
answer arrival remains the only completion signal. The `<ol>` is `aria-hidden`
with an `sr-only` node in `role="status"` carrying only the active step.
`app/page.tsx` untouched. Re-paced on Alex's call so step 5 is active by
~18.4s, inside the ~20s median; the prior curve did not reach it until 36.8s.

Verified before deploy: 72/72 frontend tests (9 module + 6 component, each
watched failing first), clean `tsc --noEmit`, zero lint findings, and a real
Chromium run against a browser-level mocked delayed response with
`NEXT_PUBLIC_API_URL` pointed at a dead port — transitions observed live at
0.0/1.8/5.2/9.5/18.6s, step 5 active at 20s, single announcement, no digit
rendered, `animationName: none` under reduced motion with the sequence still
advancing, 0 of 32 requests reaching production. Re-verified on main's own base
(58/58) before merging, because main's `page.tsx` differs by 73 lines.

**Prior to that, commit `0e4442a` (the ring) was validated and found correct** —
all seven claims held, no regression, no edits made. That validation is
superseded by the replacement above but the method stands: the ring's own
behaviour was never the problem.

**Branch cleanup: 79 local branches → 6.** Deleted 23 fully-merged, 49
byte-identical `claude/beta-night1-*` duplicates (all the same two commits
`2e654e6`/`295c0c2`), and 4 stale harness-era branches. No remote branch was
touched. Tips saved before deletion; every deleted branch's commits remain
reachable via reflog or origin. Four could not be deleted because Codex
worktrees under `~/.codex/worktrees/` pin them: `codex/b6-answer-latency`,
`codex/biblical-depth-phases-0-3`, `harness/quote-containment-and-staging`
(all merged, safe to delete once released) and `codex/five-user-beta-fast-path`
(stale duplicate). Those 8 Codex worktrees were left alone — not this
session's to remove.

Remaining local branches and why:

| Branch | State |
|---|---|
| `main` | contains local merge `4d6813e`, ahead of deployed `origin/main` |
| `claude/harness-claude-cli-adapter` | 1 ahead — CLAUDE.md: not ready, needs 2nd review round |
| 4 worktree-pinned | see above |

**`codex/biblical-ingestion-completion-queue` was merged locally and deleted.**
The remote branch remains untouched at `77b63d6`; local `main` preserves its
two later closeout commits through `4d6813e`. The redundant loader patch on the
branch resolved as already applied during the merge.

**Tracked working-tree changes are committed at close.** Calendar-dependent
approval fixtures now default to the actual execution day while the explicit
historical-date assertion remains pinned (`17dea65`; verified 31/31 ingestion
and 24/24 pilot checks with the TIPNR artifact). The pre-existing untracked
magazine-review artifacts under `docs/audits/2026-08/` and
`reference_grounding_review/` remain preserved and uncommitted.

---

## Session outcome and measures

- Shipped: loader replacement, deployed and verified in production.
- Acceptance: passed — 72/72 + 58/58 on main's base, mutation-style TDD (every
  test observed red first), live browser proof, deploy confirmed via both CLIs.
- Unplanned investigations started: **1** — the branch inventory surfaced the
  orphaned Discovery data below. Recorded, not acted on.
- Findings promoted to Blocker: **0**.
- Scope changes approved by Alex: the step-pacing re-tune, the frontend-only
  cherry-pick followed later by the verified local ingestion-branch merge,
  local-only branch deletion, and recording (not extracting) the orphaned
  Discovery rows.

---

## Next single item

**Answer the TIPNR approval gate** — unchanged from 2026-09-02, still
unanswered. Five operations at commit `8c99ea1`: rollback-only probe of batch
1; paid embeddings (≤3,939 requests, ≤$0.02441808); twenty batch transactions
(3,939 items, 11,817 rows); the **irreversible** one-row demotion of the stale
Aaron fixture policy (chunk `77f1581b-3225-5110-887b-9b651ebf9adf`); final
fresh read-only reconciliation. A staged "probe only" answer runs operation 1
alone.

Also open, neither scheduled nor blocking:

1. **Recover 75 orphaned Discovery candidates** from
   `origin/cursor/discovery-arthur-hunt-0690` — see the CLAUDE.md landmine.
   Git is currently the only copy.
2. **`docs/roadmap.md` frontend-polish entry, paragraph 2** — the
   feedback/Sources footer grouping — still undone. Paragraph 1 is now shipped.
