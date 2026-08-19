# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close — repo cleanup/reorg session).
`Temporary-assets/` no longer untracked-on-purpose — relocated, see below.

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

**Repo reorg (this session, 2026-08-19) — done but NOT YET COMMITTED.**
Root/`scripts/`/`docs/audits/` were month-bucketed for findability and
future bulk deletion, per Alex's request and an approved plan
(`/Users/alexwhitley/.claude/plans/jazzy-enchanting-map.md`):
- `scripts/`: 74 one-off scripts → `scripts/archive/2026-{04..08}/` (git
  first-add date). 47 live modules/entrypoints/documented tools + all 69
  `test_*.py` stayed flat — verified against the internal import graph,
  `nixpacks.toml`'s `answer_worker.py` reference, and ARCHITECTURE.md's
  documented tables. No live script imports an archived one (checked).
- `docs/audits/`: all 62 files → `docs/audits/2026-{04,07,08}/`. 25 were
  cited by exact path in CLAUDE.md/PLAN.md/docs/plan-archive.md/this file —
  all 45 citation instances repointed and verified (zero stale references).
- Root cleaned: `_landing-assets/` → `docs/marketing/`; `.git.bfg-report/` →
  `docs/audits/2026-04/bfg-report/`; `recovery/` → `local/_backups/` (still
  git-tracked); `Temporary-assets/`, the 13 `*_review/` dirs, `logs/`,
  `license-mapping/` → new `local/YYYY-MM/` (gitignored as one line, was
  ~16 separate `.gitignore` patterns).
- Exception, deliberately left at root: `schemas/harness/v1/` — 6 files
  under `.claude/harness-selftest/` hardcode it as `repo_root/schemas/...`;
  moving it means editing the parked harness's own self-tests, so it stayed.
- `CLAUDE.md`'s root-reserved rule updated to describe the new convention
  (also formally added `AGENTS.md`, a real pre-existing root doc that
  wasn't on the old allow-list).
- **Next session: decide whether to commit this.** Nothing was committed —
  145 renames + 6 modified files sit in the working tree, all verified
  (`py_compile` clean, import smoke-checked, `git status` shows clean `R`s,
  no unexpected deletes). Alex was asked and hadn't answered before this
  close.

**Two things found this session, neither acted on:**
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
harness-adapter stash) — neither triaged into `docs/roadmap.md` yet.

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`.

---

## Next single item

Decide whether to commit the repo reorg (see above) — that's the one
concrete open thread from this session. After that, Alex picks from
`docs/roadmap.md` (B1/A1 are the next Scheduled items) or promotes a
deferred item. No private-beta blocker remains on PLAN.md.

Process baseline: reorg shipped as planned and verified; two findings
recorded, not pursued (lint debt, harness stash); zero unapproved
investigations beyond what was flagged; no new Blocker promotion; active
blocker count **0**.
