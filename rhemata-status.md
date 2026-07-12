# rhemata-status.md

**As of:** 2026-07-12 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** none on the harness — all three known bugs are closed and #5.5 is DONE end to end (2026-07-13). The only remaining named harness gap is the adjacent, deliberately out-of-scope database-number verification (see "Known Harness Bugs" below). Full trail: CLAUDE.md, "Bug #3 — retired."
- **Next action:** non-harness work is next — #6's two remaining alias/reassignment writes (Supabase SQL editor) and the PLAN.md #14 drift correction are both ready and unblocked.

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

## Known Harness Bugs — ALL CLOSED (2026-07-13)

1. **Write-state log not scoped per-agent — CLOSED (2026-07-12).** The stop-gate now filters the write-state log to only the finishing agent's own records before judging anything, instead of evaluating the whole session's history. Verified both directions: a read-only agent in a session with 7 other agents' write history now passes cleanly first try; a genuine same-agent mismatch is still caught. Full diagnostic trail and fix details: CLAUDE.md, "Bug #1 — diagnosed and fixed."
2. **Report-to-disk / read-only collision — CLOSED BY REMOVAL (2026-07-12).** Was: the mandatory disk-save step added to `executor.md` produced a real write on every report, including read-only ones, which collided with `5b43332`'s write-record/marker check and blocked every honest `WORK_TYPE: read-only` report. Resolved by dropping the report-to-disk feature entirely (see "Harness Scope Decisions" above) rather than building the narrow exemption that would have been needed to keep it. No longer a live bug.
3. **`check_dry_run_before_batch()` (Rule 2) — CLOSED BY RETIREMENT (2026-07-13).** Same unconditional-block-from-prose shape as the original garble bug, triggered by incidental word matches ("backfill," etc.) rather than anything recorded. Retired rather than rebuilt: whether a report is genuinely batch-scale isn't knowable from the write-state log as structured today (a script invocation is one recorded line regardless of volume; a dry-run isn't even distinguishably recorded from a real invocation). Confirmed nothing else depended on it firing — no other code reference anywhere in the repo, no dedicated self-test fixture, all 7 applicable fixtures re-verified unaffected after removal. Full trail: CLAUDE.md, "Bug #3 — retired."

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
  - Exit condition (a) (retire the prose backstop to record-only): **DONE (2026-07-13).** Both prose-trust sites removed: the `WORK_TYPE`-marker cross-check is retired, replaced by a per-write match-check between recorded actions and what the report actually describes; the script-invocation prose bridge is retired, replaced by direct recognition of known write-capable scripts. **#5.5 as a whole is now DONE — every exit condition closed.** Full trail: CLAUDE.md, "Piece A/B — exit condition (a) closed." Adjacent, deliberately out of scope, still open: independently verifying claimed reconciliation numbers against the database — records prove a write happened and can be described, not that a claimed count is correct.
  - Subagent MCP scope: **DECIDED** (script-only for now) — no longer a blocker to sequence around; see CLAUDE.md.
- **#6 Aliases + sentinel cleanup + strict mode: DONE (Alex, 2026-07-12).**
  - Two-doc sentinel attribution: **RESOLVED** (Alex, 2026-07-11) — migration `059`, committed `fa47ead`, live-verified.
  - `murray_surrender.pdf` duplicate: **DONE** (Alex, 2026-07-11) — SHA-256-confirmed identical to `murray_absolute_surrender.pdf` (retained); deleted (untracked/gitignored, no commit for the delete). PLAN.md annotated, committed `9e47b4f`. Also closes PLAN #14's "delete duplicate Murray files" sub-item (confirmed same file) — PLAN.md #14's own text already reads "Duplicate Murray file deletion: DONE"; this file's prior note claiming it "hasn't been re-annotated yet" was itself the stale one, corrected here.
  - Strict mode (refuses silent-sentinel by default): **DONE** (Alex, 2026-07-11) — shipped `280b592`. Default ON, `--allow-sentinel` opt-out, skip-and-continue, end-of-run report. Built and code-verified; not yet exercised on a real ingest — unproven until it actually refuses a real document.
  - Alias inserts + sentinel reassignment: **DONE (Alex, 2026-07-12)** — four `source_aliases` rows inserted (`jack deere`, `michael brown`, `tom bedford`, `church life class`), each independently confirmed by direct DB query to resolve to its intended `sources` row with zero collisions. "The Kneeling Christian" reassigned from the sentinel to "An Unknown Christian" (`public_domain`/`shown`); `citation_mode` deliberately held at `silent_context` per new standing rule — see CLAUDE.md, "Citable requires a real attributable name." Executed as a fail-closed transaction (per-statement rowcount checks, rollback on any mismatch, extra `AND source_id = <sentinel>` guard on the document UPDATE), dispatched through an `executor` subagent so the harness gate had something to supervise — the first live write through the finished #5.5 gate. Verified independently off the database, not from the executor's self-report: all four aliases resolve correctly; the reassigned document points at the right source with `citation_mode` and `author` unchanged; the sentinel row itself untouched, still holding exactly its two permanent documents; `source_aliases` count 95/95 distinct (91 prior + 4 new, zero dupes); `sources` count unchanged at 67.
  - **Harness gate behavior on this write: clean pass, one attempt, no retry** (confirmed via the write-state log). **One harness finding surfaced, not a #6 problem:** direct inspection of Piece A's `_referents_for()` on this write's recorded command showed it extracted only incidental Python-syntax fragments from the Bash-embedded script (`psycopg2.connect`, `.env`, `conn.cursor`, etc.), not semantic content (alias names, table names) — the report's match-check passed because it happened to mention those fragments while describing *how* it connected, not because it named what changed. Outcome was correct and the report was honest, so this did not warrant a stop; it's a real, narrower gap than file-edit-shaped writes have, specific to Bash writes that embed a script. Logged here for whoever next touches gate hardening.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames + `jewish_perspectives` drop — still genuinely not done. Duplicate Murray file deletion — CONFIRMED closed (same file as #6's delete, grep-confirmed) but #14's committed text (`6325e2b`) still reads "NOT happened" — stale, needs a follow-up annotation.
- **#7–#13, #15–#37:** untouched.

---

## In Progress / Uncommitted Locally

The tree currently carries harness rework awaiting commit: the #5.5 exit-condition-(a) rework (Piece A/B) and the bug #3 retirement, both built and verified this session-block but not yet committed as of this snapshot. Beyond the accepted standing baseline (below), nothing else is uncommitted. Verify `git rev-parse HEAD` vs `origin/main` after the next push for the exact current hash — this file doesn't self-reference its own resulting commit.

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
- Executor garbled final-text reports: root cause fixed (`5b43332`). All three follow-on bugs it surfaced are now closed — #1 (per-agent scoping) and #3 (Rule 2's sibling bug) fixed, #2 (report-to-disk collision) closed by removal.
- `--dangerously-skip-permissions`: keep OFF for live writes (standing rule, unchanged).

---

## Next Session Should

No harness-gate work remains open or blocked. Pick up non-harness work: close #6's two remaining alias/reassignment writes via the Supabase SQL editor, and land the PLAN.md #14 drift correction. GOVERNED_FILES hardening is a separate, later session. The founder MCP-scope decision, the report-to-disk keep/drop call, and #5.5 in its entirety (including bug #3) are all closed — do not reopen any of them without a new queued task that genuinely requires it.
