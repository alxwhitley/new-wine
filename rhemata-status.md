# rhemata-status.md

**As of:** 2026-07-12 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** finish #5.5 exit condition (a) — remove the interim `WORK_TYPE`-marker prose cross-check from `check_recorded_writes()` entirely, per CLAUDE.md's Gate Design Principle 2. Bug #1, the dependency this was blocked on, is now CLOSED (2026-07-12) — see CLAUDE.md "Bug #1 — diagnosed and fixed" for the full trail.
- **Next action:** scope the exit-condition-(a) rework — what replaces the `WORK_TYPE` marker check now that per-agent scoping is correct. This is the harness's last real piece of unfinished work. Bug #3 (Rule 2's sibling unconditional-block bug) remains open and independent — can be picked up separately, in any order relative to (a).

---

## Harness Scope Decisions — Resolved This Session (2026-07-12)

Two things that were open blockers as of the last snapshot are now closed and recorded durably in **CLAUDE.md**, under "Harness / Agentic-Loop — Gate Design Principles → Standing decisions":

- **Subagent scope:** `executor`/`planner-reviewer` stay script-only — no MCP/external-tool access — until a queued task genuinely can't be expressed as a script. Not revisited preemptively.
- **Report-to-disk feature: DROPPED.** The parked backstop-save build (uncommitted changes to `executor.md`/`planner-reviewer.md` from a prior session) has been discarded via `git restore` — both files are back to their last-committed state, nothing of that build remains in the tree. This closes bug #2 below by deletion, not by fix.

Both decisions live in CLAUDE.md now, not here — this file doesn't hold durable decisions, per its own contract above.

---

## MCP Write-Gate — Shipped (`f2378a7`, 2026-07-11)

`settings.json` carries a `mcp__.*` PreToolUse matcher; `guard_pretooluse.py` denies MCP writes (Supabase `execute_sql`, `apply_migration`, and 9 other write-class tools) before execution, for any subagent, while MCP reads pass through. Verified live off disk: `list_tables` ALLOWED (recorded), `execute_sql` DENIED (verbatim deny reason, no execution, no DB mutation). MCP writes are prevented at the guard by deny-before-execution; they are deliberately not recorded for the auditor, because a write that never executed needs no reconciliation. This closes #5.5 exit condition (b). (Full probe-methodology history from the capture session that preceded this build has aged out of this snapshot — see git history, commit `f2378a7` and its parent chain, if the raw methodology is ever needed again.)

---

## Known Harness Bugs (as of `5b43332`, the garble-fix commit)

1. **Write-state log not scoped per-agent — CLOSED (2026-07-12).** The stop-gate now filters the write-state log to only the finishing agent's own records before judging anything, instead of evaluating the whole session's history. Verified both directions: a read-only agent in a session with 7 other agents' write history now passes cleanly first try; a genuine same-agent mismatch is still caught. Full diagnostic trail and fix details: CLAUDE.md, "Bug #1 — diagnosed and fixed."
2. **Report-to-disk / read-only collision — CLOSED BY REMOVAL (2026-07-12).** Was: the mandatory disk-save step added to `executor.md` produced a real write on every report, including read-only ones, which collided with `5b43332`'s write-record/marker check and blocked every honest `WORK_TYPE: read-only` report. Resolved by dropping the report-to-disk feature entirely (see "Harness Scope Decisions" above) rather than building the narrow exemption that would have been needed to keep it. No longer a live bug.
3. **`check_dry_run_before_batch()` (Rule 2) has the same unconditional-block shape as the original garble bug — OPEN, lower urgency.** `BATCH_SCALE_WORDS` (includes "backfill") can match incidentally — e.g. a report that quotes PLAN.md's own Standing Rule 3 text while doing unrelated work trips it, with no way to satisfy the check afterward. Confirmed live: caused 4 consecutive rejections on a task that did no batch work at all. Same unconditional-block pattern as the bug fixed in `5b43332`, different function, not yet touched.

**Known edge, not a bug (flag only, no fix needed today):** if a future MCP write-tool isn't yet added to `guard_pretooluse.py`'s `MCP_WRITE_CLASS_TOOLS` blocklist, it would be allowed through and mis-tagged `"kind": "mcp_read"` — invisible to the auditor's `write_records` filter. Keep the blocklist current as new MCP write tools appear.

None of these are logged in PLAN.md.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening, hard prerequisite for #6–13 write steps):**
  - Piece 1 (write-class Edit/Write/Bash recording): DONE (`35ae840`).
  - Piece 2b-i (script-invocation recording): DONE (`8816804`).
  - Piece 2b-ii (gate reads tool-invocation records): DONE (`6379925`).
  - MCP write-gate: SHIPPED and verified live (`f2378a7`) — exit condition (b) DONE. See above.
  - Exit condition (a) (retire the prose backstop to record-only): **still OPEN.** Scope includes both the original script-invocation prose bridge AND the newer `WORK_TYPE`-marker cross-check `5b43332` added — CLAUDE.md's Gate Design Principle 2 requires removing both before #5.5 is complete. Bug #1 (per-agent scoping), the dependency this was waiting on, is now DONE (2026-07-12). Note for scoping this work: `planner-reviewer` writes into the same shared write-state log as `executor` without ever hitting this gate itself — see CLAUDE.md's Bug #1 entry for why that matters here.
  - Subagent MCP scope: **DECIDED** (script-only for now) — no longer a blocker to sequence around; see CLAUDE.md.
- **#6 Aliases + sentinel cleanup + strict mode:**
  - Two-doc sentinel attribution: **RESOLVED** (Alex, 2026-07-11) — migration `059`, committed `fa47ead`, live-verified.
  - `murray_surrender.pdf` duplicate: **DONE** (Alex, 2026-07-11) — SHA-256-confirmed identical to `murray_absolute_surrender.pdf` (retained); deleted (untracked/gitignored, no commit for the delete). PLAN.md annotated, committed `9e47b4f`. Also closes PLAN #14's "delete duplicate Murray files" sub-item (confirmed same file) — #14's own text just hasn't been re-annotated to say so yet (see Open Blockers).
  - Strict mode (refuses silent-sentinel by default): **DONE** (Alex, 2026-07-11) — shipped `280b592`. Default ON, `--allow-sentinel` opt-out, skip-and-continue, end-of-run report. Built and code-verified; not yet exercised on a real ingest — unproven until it actually refuses a real document.
  - Remaining OPEN: Deere/Brown/Bedford/Church Life Class alias inserts; Kneeling Christian → An Unknown Christian reassignment. Both gated DB writes — **recommended faster path: run both directly in the Supabase SQL editor** rather than holding #6 hostage to the harness build. Not yet executed.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames + `jewish_perspectives` drop — still genuinely not done. Duplicate Murray file deletion — CONFIRMED closed (same file as #6's delete, grep-confirmed) but #14's committed text (`6325e2b`) still reads "NOT happened" — stale, needs a follow-up annotation.
- **#7–#13, #15–#37:** untouched.

---

## In Progress / Uncommitted Locally

As of the commit that produced this snapshot, working tree is clean beyond the standing baseline — the parked report-to-disk build has been discarded (`git restore` on `executor.md`/`planner-reviewer.md`), and this commit itself lands the CLAUDE.md decisions plus this file. Verify `git rev-parse HEAD` vs `origin/main` after push for the exact current hash — this file doesn't self-reference its own resulting commit.

**Accepted standing baseline (intentional carve-out, unchanged across many sessions):** modified `SKILL.md` + untracked `.agents/`, `.claude/skills/`, `skills-lock.json`. Still needs a `.gitignore`-or-commit decision so clean-tree checks stop flagging it.

---

## Open Blockers Awaiting a Decision

- **PLAN.md #14 drift:** #14's Murray sub-item names `murray_surrender.pdf` specifically — that file is confirmed deleted (via #6), so #14's "NOT happened" text is now stale for this one sub-item (folder renames + jewish_perspectives drop remain genuinely open). Needs a follow-up annotation.
- **GOVERNED_FILES gap (named, deferred):** `guard_pretooluse.py`/`settings.json` aren't in `GOVERNED_FILES` — a subagent editing the safety machinery itself would only log as a generic write, not deny. Fix: add them. Explicitly a separate session.
- **Three suspected Murray duplicate pairs** (`murray_deeper.pdf`/`murray_deeper_christian_life.pdf`, `murray_waiting.pdf`/`murray_waiting_on_god.pdf`, `murray_prayer.pdf`/`murray_with_christ_in_school_of_prayer.pdf`) — named, NOT verified identical, NOT in any PLAN item. Content-match before any delete.
- Un-ingested `8.21.24 Prophetic Teaching - Prophetic Ministry.docx` — still unconfirmed whether this is "the Bedford docx" #6 refers to.
- `PRODUCT.md` vs. `POSITIONING.md` overlap — still unclear if superseded; needs Alex's call.
- Offsite backup of `sources/` + `ingest_queue.xlsx` — still not independently verified from this Mac.
- `chunks.content` stray `---` separator — still flagged, no owning session decided.
- Executor garbled final-text reports: root cause fixed (`5b43332`). Of the two follow-on bugs it surfaced, #1 (per-agent scoping) is now CLOSED (2026-07-12); #2 (report-to-disk collision) is closed by removal; #3 (Rule 2's sibling bug) remains OPEN.
- `--dangerously-skip-permissions`: keep OFF for live writes (standing rule, unchanged).

---

## Next Session Should

Scope and land the #5.5 exit-condition-(a) rework — dropping the `WORK_TYPE`-marker prose cross-check `5b43332` added, now that bug #1 (per-agent scoping) is closed and no longer something the rework has to work around. This is the harness's last real piece of unfinished work. Bug #3 (Rule 2's sibling bug) is open and independent — fine to pick up before, after, or alongside (a). Separately, and not bundled: close #6's two remaining alias/reassignment writes via the Supabase SQL editor, and land the PLAN.md #14 drift correction. GOVERNED_FILES hardening is a separate, later session. The founder MCP-scope decision and the report-to-disk keep/drop call are both closed — do not reopen either without a new queued task that genuinely requires it.
