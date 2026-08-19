# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close — repo reorg committed; admin-panel
future-ingest-tracking diagnostic).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers; `docs/roadmap.md` = later work.

**Blocker queue:** still empty (unchanged this session — W1–W9 finish-line
closed 2026-08-19, see PLAN.md). Quote rail live, gold-only,
`QUOTE_SELECTION_ENABLED=true`, W5–W6/W9 web-article work DONE — unchanged
substance, full detail already in PLAN.md, not repeated here.

**Repo reorg — DONE, committed (`9ab7284`, "chore: reorganize repo into
month-bucketed archive structure").** Root/`scripts/`/`docs/audits/`
month-bucketed for findability and future bulk deletion, per Alex's request
and an approved plan. `scripts/`: 74 one-off scripts → `scripts/archive/
2026-{04..08}/` (git first-add date), 47 live modules/entrypoints/documented
tools + all 69 `test_*.py` stayed flat. `docs/audits/`: all 62 files →
`docs/audits/2026-{04,07,08}/`, all 45 citation instances across
CLAUDE.md/PLAN.md/docs/plan-archive.md/this file repointed. Root cleaned:
`_landing-assets/` → `docs/marketing/`; `.git.bfg-report/` →
`docs/audits/2026-04/bfg-report/`; `recovery/` → `local/_backups/` (still
git-tracked); `Temporary-assets/`, `*_review/` dirs, `logs/`,
`license-mapping/` → `local/YYYY-MM/` (gitignored as one line). Exception
left at root: `schemas/harness/v1/` (hardcoded path in
`.claude/harness-selftest/`). `CLAUDE.md`'s root-reserved rule updated to
match (also added `AGENTS.md` to the allow-list). Not yet pushed to origin
— local branch is 1 commit ahead.

**This session — `/remote-control` read-only diagnostic (admin future-ingest
tracking).** Alex asked where the admin panel tracks material earmarked for
future ingestion (websites/articles/blogs), separate from
`source_ingest_queue`/`source_ingest_domain_memory` (Invariant 16) and any
YouTube queue. Searched the admin frontend, backend routers, and queried the
live public schema (44 tables, read-only) directly. **Finding: no database
table for this exists.** The de facto equivalent is `FUTURE_TARGETS` in
`frontend/components/admin/corpus-data.ts` — a hardcoded static array
(6 entries), rendered as the collapsible "Future Corpus Targets" section in
`AdminModal.tsx`, with no API endpoint and no DB backing at all; editing it
means editing that source file directly. Full raw findings (all 44 table
names, full `FUTURE_TARGETS` contents) were delivered to Alex directly in
chat, not saved to a file. Building a real DB-backed tracking table is
unscoped future work, not started, not yet triaged into `docs/roadmap.md`.

**Two things found last session, neither acted on:**
- `npm run lint` (frontend) has 27 pre-existing errors, ~17 files, almost
  all the same `react-hooks/set-state-in-effect` rule (setState in an
  effect's early-return guard, e.g. resetting state before a fetch). Not
  caused by this session; too behavior-adjacent to fix without browser
  testing. Not yet triaged into `docs/roadmap.md`.
- A `git stash` named `unexplained-mutation-2026-08-16-2125-investigate-
  before-deciding` exists on the parked `claude/harness-claude-cli-adapter`
  branch — a small, already-written fix to that branch's own safety
  self-test (tightens an overly broad "forbidden substring" check). Left
  untouched — parked-harness territory, Alex's call per Session Routing.

**Also delivered, not repo state:** a first-pass draft of the B1 private-
beta product contract (`docs/roadmap.md`'s next Scheduled item) was sent to
Alex directly as a file this session — grounded in real code/config, one
open call flagged (delete-account is currently a stub). Not saved in the
repo; if useful going forward it should be formalized as a real file on
request, not assumed to still exist from a scratchpad.

---

## Classified work

**Deferred / non-blocking:** optional staging display rename (“web staging”);
optional async smoke on a new W9 article; the two findings above (lint debt,
harness-adapter stash); a real DB-backed future-ingestion-candidates table
(currently a static frontend list only, see above) — none triaged into
`docs/roadmap.md` yet.

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`.

---

## Next single item

Push `9ab7284` to origin when ready (currently local-only, 1 commit ahead).
Otherwise Alex picks from `docs/roadmap.md` (B1/A1 are the next Scheduled
items) or promotes a deferred item, including whether the future-ingestion
tracking list above is worth a real table. No private-beta blocker remains
on PLAN.md.

Process baseline: reorg shipped as planned, verified, and committed; one
read-only diagnostic delivered (no repo write); three findings recorded, not
pursued (lint debt, harness stash, future-ingest tracking is frontend-only);
zero unapproved investigations beyond what was flagged; no new Blocker
promotion; active blocker count **0**.
