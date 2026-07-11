# rhemata-status.md

**As of:** 2026-07-11 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** #5.5's MCP write-gate — ground truth captured this session (verified real tool_name + matcher syntax). Gate logic itself is NOT yet built, by design. #6's two remaining gated writes (aliases, Kneeling Christian reassignment) don't need to wait on that build — faster path available (Supabase SQL editor directly).
- **Next action:** before building the MCP gate, settle the founder question below — it decides what the gate keys on (agent_type scope, not just tool_name).

---

## Founder Decision Needed Before Next Build (Alex, plain English)

Today `executor` and `planner-reviewer` — the two agent types the harness actually governs — have NO MCP tools in their toolset (Read/Grep/Glob/Bash/Edit only). They cannot reach the Supabase MCP connector at all. Only a wider-toolset type (e.g. `general-purpose`) can. So the write-gate build only matters today if a future session dispatches a wider-toolset agent against the DB. **Question: keep executor/planner-reviewer permanently script-only (general-purpose stays the only MCP-DB path), or expect that to loosen later?** Decide before the gate build starts, not mid-stream. No code needed to answer.

---

## MCP Write-Gate — Ground Truth Capture (2026-07-11)

Captured the ground truth the #5.5 diagnostic said was missing. No gate logic built — this was a measurement step only, fully reversible, nothing committed.

- **Method:** installed a throwaway logging probe (`.claude/hooks/_mcp_probe.py`) wired via one new temporary `"mcp__.*"` PreToolUse matcher entry in `settings.json` (existing Edit|Write/Bash entries untouched). Dispatched a live subagent (`general-purpose` — the only type able to reach an MCP tool) to fire one real, harmless Supabase MCP read. Captured the raw payload, read it off disk, deleted the probe, restored `settings.json` from a pristine pre-probe copy with a proven zero-diff (`diff` exit 0), confirmed `git status --short` back to the standing baseline.
- **Verified matcher syntax:** `"mcp__.*"` — confirmed from local Claude Code plugin docs (`hook-development/SKILL.md:415`), not guessed.
- **Verified real tool_name** (captured verbatim from a live call): `mcp__claude_ai_Supabase__list_tables`. Confirms the `mcp__<connector>__<tool>` pattern against real evidence.
- **Verified `tool_input` field shape:** `project_id`, `schemas`, `verbose` — no `command`/`file_path`/`query`. The future gate cannot reuse the existing Bash/Edit field checks; needs tool-specific handling per MCP tool.
- **Verified:** `agent_id`/`agent_type` both present on subagent-originated MCP payloads.
- **Side-finding (shapes next session's scope):** neither `executor` nor `planner-reviewer` has MCP tools today — the "open MCP write door" is latent, not active; it only materializes if a future session dispatches a wider-toolset agent against the DB. See Founder Decision above.
- **Next session's build (Option A, one load-bearing change):** one new `"mcp__.*"` PreToolUse matcher entry + a dispatch branch in `guard_pretooluse.py` (after the agent_type gate, before the final bare `allow()`) that allows MCP reads and denies MCP writes, keyed on the verified name above. Treat `execute_sql`/`apply_migration` as write-class (arbitrary SQL isn't assumable-read-only); `list_*`/`get_*` pass through. Verify via a live subagent: real read PASSES, real write DENIED, both observed off disk. Commit only on confirmed deny+pass.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** unchanged from 2026-07-10 snapshot — DONE (see git history; not restated here).
- **#5.5 (harness hardening, hard prerequisite for #6–13 write steps):**
  - Piece 1 (write-class Edit/Write/Bash recording): DONE (`35ae840`).
  - Piece 2b-i (script-invocation recording): DONE (`8816804`).
  - Piece 2b-ii (gate reads tool-invocation records): DONE (`6379925`).
  - **MCP write-gate ground truth: DONE this session** (see above). **Gate logic: NOT built** — reframed from "deny-all MCP" to "read-open/write-gated," buildable next session against the verified name. Exit condition (b) still OPEN.
  - Exit condition (a) (retire the prose backstop to record-only) — still separately OPEN.
- **#6 Aliases + sentinel cleanup + strict mode:**
  - Two-doc sentinel attribution: **RESOLVED** (Alex, 2026-07-11) — migration `059`, committed `fa47ead`, live-verified.
  - `murray_surrender.pdf` duplicate: **DONE** (Alex, 2026-07-11) — SHA-256-confirmed identical to `murray_absolute_surrender.pdf` (retained); deleted (untracked/gitignored, no commit for the delete). PLAN.md annotated, committed `9e47b4f`. **Also closes PLAN #14's "delete duplicate Murray files" sub-item — confirmed same file** (PLAN.md line 109 names `murray_surrender.pdf` specifically); #14's own text just hasn't been re-annotated to say so yet (see Open Blockers).
  - Strict mode (refuses silent-sentinel by default): **DONE** (Alex, 2026-07-11) — shipped `280b592`. Default ON, `--allow-sentinel` opt-out, skip-and-continue, end-of-run report. **Built and code-verified; not yet exercised on a real ingest** — unproven until it actually refuses a real document.
  - Remaining OPEN: Deere/Brown/Bedford/Church Life Class alias inserts; Kneeling Christian → An Unknown Christian reassignment. Both gated DB writes waiting on MCP coverage — **recommended faster path: run both directly in the Supabase SQL editor** rather than holding #6 hostage to the harness build. Not yet executed.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames + `jewish_perspectives` drop — still genuinely not done. Duplicate Murray file deletion — **CONFIRMED closed**: #14's text (line 109) names `murray_surrender.pdf` specifically, and that exact file was deleted this session under #6 (grep-confirmed same file, not a different suspected pair). #14's committed text (`6325e2b`) still reads "NOT happened" — stale, needs a follow-up annotation.
- **#7–#13, #15–#37:** untouched.

---

## In Progress / Uncommitted Locally

Nothing beyond the accepted standing baseline. Working tree otherwise clean; local `main` == `origin/main` at `9e47b4f8` (confirmed by hash before and after this session's MCP probe work — probe leaves zero trace).

**Accepted standing baseline (intentional carve-out, unchanged across many sessions):** modified `SKILL.md` + untracked `.agents/`, `.claude/skills/`, `skills-lock.json`. Still needs a `.gitignore`-or-commit decision so clean-tree checks stop flagging it.

---

## Open Blockers Awaiting a Decision

- **PLAN.md #14 drift (new):** #14's Murray sub-item names `murray_surrender.pdf` specifically — that file is confirmed deleted (via #6), so #14's "NOT happened" text is now stale for this one sub-item (folder renames + jewish_perspectives drop remain genuinely open). Needs a follow-up annotation — not done this session (out of scope for the turn that closed it).
- **GOVERNED_FILES gap (named, deferred):** `guard_pretooluse.py`/`settings.json` aren't in `GOVERNED_FILES` — a subagent editing the safety machinery itself would only log as a generic write, not deny. Fix: add them. Explicitly a SEPARATE session — do not bundle into the MCP gate build.
- **Founder decision on executor/planner-reviewer MCP scope** — see above; needed before the MCP gate build starts.
- **Three suspected Murray duplicate pairs** (`murray_deeper.pdf`/`murray_deeper_christian_life.pdf`, `murray_waiting.pdf`/`murray_waiting_on_god.pdf`, `murray_prayer.pdf`/`murray_with_christ_in_school_of_prayer.pdf`) — named, NOT verified identical, NOT in any PLAN item. Content-match before any delete.
- Un-ingested `8.21.24 Prophetic Teaching - Prophetic Ministry.docx` — still unconfirmed whether this is "the Bedford docx" #6 refers to.
- `PRODUCT.md` vs. `POSITIONING.md` overlap — still unclear if superseded; needs Alex's call.
- Offsite backup of `sources/` + `ingest_queue.xlsx` — still not independently verified from this Mac.
- `chunks.content` stray `---` separator — still flagged, no owning session decided.
- **Executor garbled final-text reports — still not root-caused.** Recurred multiple times this session. Every result was independently re-verified off disk/direct commands rather than trusted from subagent prose — this kept ground truth reliable despite it.
- `--dangerously-skip-permissions`: keep OFF for live writes (standing rule, unchanged).

---

## Next Session Should

Decide the founder question first (executor/planner-reviewer MCP scope), then build #5.5's read-open/write-gated MCP logic against the verified `mcp__claude_ai_Supabase__list_tables` name and `"mcp__.*"` matcher syntax on record above — one load-bearing change, verified via a live subagent (real read PASSES, real write DENIED, both observed off disk) before committing. Separately, NOT bundled: close #6's two remaining alias/reassignment writes via the Supabase SQL editor, and land the PLAN.md #14 drift correction. GOVERNED_FILES hardening is a separate, later session.
