# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-03. **PLAN.md has zero active blockers.**

---

## Current state

**A working-tree code review ran, and four of its fifteen findings were fixed
and committed; nothing was deployed and nothing touched the database.**

`bfb6b0c` (frontend): `<AdminModal>` and the contributor `<Sheet>` are hoisted
out of the twice-rendered `sidebarContent` so the tablet header's Open Profile
button no longer opens two portalled dialogs with doubled admin fetches; the
drawer-footer safe-area CSS now ends at 1023px to match the drawer's real
`lg:hidden` breakpoint, so portrait tablets get the clearance (the e2e
threshold that had been accepting 16px there moved with it). Proof: 74/74 unit
tests including a new guard that fails against the old sidebar, clean
TypeScript and ESLint, 16/16 responsive Playwright checks; reverting the CSS
fails the two portrait-iPad projects.

`2149239` (TIPNR tooling): `_stage_batch` re-asserts the hidden, licensed
source on the writing cursor before staging any row, via the canonical
`assert_source()`, restoring what the Phase 8 pilot did in-transaction. Drift
now aborts as `staging_failed` / `source_visibility_drift` (or
`source_license_drift`) with 0 commits, 1 rollback. Four new tests, all of
which fail with the line removed; 124/124 with `TIPNR_TEST_ARTIFACT` set.

This closeout commit corrects the CLAUDE.md landmine's items-vs-rows
arithmetic (3,939 items × 3 = 11,817 rows), fixes `docs/roadmap.md`'s stale
"3,938 remaining", records the seven unfixed tooling findings as Scheduled
inside A4, and parks the four unreproduced frontend findings.

**Not deployed.** Vercel and Railway are unchanged from the 2026-09-03 morning
release (`e45a86e`); production still runs the double-mounted dialog and the
767px footer rule until the next frontend deploy. The TIPNR writer change is
repo-only and needs no deploy — it runs from the terminal.

One false alarm worth remembering: the first e2e run after the CSS fix failed
with the pre-edit value because the Playwright-managed dev server served a
stale Turbopack CSS chunk — exactly `frontend/CLAUDE.md`'s stale-CSS landmine.
Curling the served chunk confirmed it; `rm -rf frontend/.next` and re-run
passed. Not a code problem.

After this closeout, local `main` is 24 commits ahead of `origin/main`; nothing
was pushed. The pre-existing untracked audit, critique, reference-review, and
task artifacts remain uncommitted, deliberately.

---

## Session outcome and measures

- Shipped: two code commits (frontend dialog/footer fix; TIPNR in-transaction
  source assertion) and this records commit.
- Acceptance: passed — every fix mutation-proven in both directions; 74/74
  frontend unit, 16/16 responsive e2e, 124/124 TIPNR suite, 148/148 with the
  pilot suite.
- Unplanned investigations started: **0** (the stale-CSS diagnosis was inside
  the approved fix's own verification).
- Findings promoted to Blocker: **0**. Eleven findings classified: seven
  Scheduled (A4 tooling residuals), four Parked (frontend, unreproduced).
- Scope changes approved by Alex: the four fixes, then commit and close.
- Original outcome completed: **yes**.
- Active critical-path item count: **1** — the attended TIPNR execution.

---

## Next single item

**Re-run the rollback-only TIPNR probe on `2149239`, then continue the attended
execution in the terminal session.** The 2026-09-03 probe (batch 1 staged 600
rows, 0 committed, 1 rolled back, `completed_batches: 0`) predates the
in-transaction source assertion, so the new statement has not yet executed
against the live database. The approval packet for 2026-09-03 exists in
`local/2026-09/`; the packet and batch hashes are unaffected by the code
change. Before trusting the run's own reports, read the two reporting caveats
now recorded under A4 in `docs/roadmap.md` (zero-write failures mislabeled as
unknown-commit; the CLI never reaches the global excluded-identity check).
The completed-answer feedback/Sources footer grouping remains Scheduled and is
not part of this item.
