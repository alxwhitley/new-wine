# rhemata-status.md

**As of:** 2026-07-11 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** #5.5's MCP write-gate — SHIPPED and verified live (`f2378a7`, 2026-07-11); exit condition (b) closed by deny-before-execution (see "Where We Are in the Roadmap" below). #6's two remaining gated writes (aliases, Kneeling Christian reassignment) don't need to wait on that build — faster path available (Supabase SQL editor directly).
- **Next action:** settle the founder question below (still open, though the gate itself already shipped) — it decides what future harness-gate work keys on (agent_type scope, not just tool_name).

---

## Founder Decision Needed Before Next Build (Alex, plain English)

Today `executor` and `planner-reviewer` — the two agent types the harness actually governs — have NO MCP tools in their toolset (Read/Grep/Glob/Bash/Edit only). They cannot reach the Supabase MCP connector at all. Only a wider-toolset type (e.g. `general-purpose`) can. So the write-gate build only matters today if a future session dispatches a wider-toolset agent against the DB. **Question: keep executor/planner-reviewer permanently script-only (general-purpose stays the only MCP-DB path), or expect that to loosen later?** Decide before the gate build starts, not mid-stream. No code needed to answer.

---

## MCP Write-Gate — Ground Truth Capture (2026-07-11)

Captured the ground truth the #5.5 diagnostic said was missing. At the time of THIS entry, no gate logic was built yet — this was a measurement step only, fully reversible, nothing committed. **Superseded:** the gate itself has since shipped (`f2378a7`, same day) — see the corrected #5.5 entry under "Where We Are in the Roadmap" below for current status.

- **Method:** installed a throwaway logging probe (`.claude/hooks/_mcp_probe.py`) wired via one new temporary `"mcp__.*"` PreToolUse matcher entry in `settings.json` (existing Edit|Write/Bash entries untouched). Dispatched a live subagent (`general-purpose` — the only type able to reach an MCP tool) to fire one real, harmless Supabase MCP read. Captured the raw payload, read it off disk, deleted the probe, restored `settings.json` from a pristine pre-probe copy with a proven zero-diff (`diff` exit 0), confirmed `git status --short` back to the standing baseline.
- **Verified matcher syntax:** `"mcp__.*"` — confirmed from local Claude Code plugin docs (`hook-development/SKILL.md:415`), not guessed.
- **Verified real tool_name** (captured verbatim from a live call): `mcp__claude_ai_Supabase__list_tables`. Confirms the `mcp__<connector>__<tool>` pattern against real evidence.
- **Verified `tool_input` field shape:** `project_id`, `schemas`, `verbose` — no `command`/`file_path`/`query`. The future gate cannot reuse the existing Bash/Edit field checks; needs tool-specific handling per MCP tool.
- **Verified:** `agent_id`/`agent_type` both present on subagent-originated MCP payloads.
- **Side-finding (shapes next session's scope):** neither `executor` nor `planner-reviewer` has MCP tools today — the "open MCP write door" is latent, not active; it only materializes if a future session dispatches a wider-toolset agent against the DB. See Founder Decision above.
- **Next session's build (Option A, one load-bearing change) — DONE, shipped `f2378a7` same day:** one new `"mcp__.*"` PreToolUse matcher entry + a dispatch branch in `guard_pretooluse.py` that allows MCP reads and denies MCP writes, keyed on the verified name above. `execute_sql`/`apply_migration` treated as write-class; `list_*`/`get_*` pass through. Verified via a live subagent: real read PASSED, real write DENIED, both observed off disk, exactly as planned here.

---

## Known Harness Bugs — Diagnosed, NOT Fixed (2026-07-11, after garble-fix commit `5b43332`)

Three bugs found via live testing on top of the garble fix (`5b43332`, confirmed live on origin). None are fixed — diagnostic only, per Alex's explicit instruction. Sequencing matters; do not fix out of order.

1. **Write-state log not scoped per-agent — fix this FIRST.** `check_recorded_writes()` (`deterministic_gate.py:189-253`) opens the write-state log keyed by `session_id` only and reads every record in it — never filters to the current agent's own `agent_id`. Any executor dispatched later in a session that already has write history sees every earlier agent's writes as if they were its own. Confirmed live: a report's cited "write-class calls this run" count grew by exactly 1 with each of one agent's own resubmission attempts, and it was blocked citing tool calls (an Edit to `shared_ingest.py`, `rm murray_surrender.pdf`) that belonged to different agents from hours earlier in the same session.
2. **Report-to-disk backstop collides with the garble fix on read-only tasks — fix SECOND, depends on #1.** The mandatory disk-save step added to `executor.md` requires a real Bash write (`mkdir` + `cat >`) on every report, including read-only ones. `guard_pretooluse.py`'s `BASH_WRITE_INDICATORS` (lines 76-85) has no path-awareness — it classifies that save the same as any other write. Combined with `5b43332`'s fix ("write record + read-only marker = block"), every honestly-labeled `WORK_TYPE: read-only` report now gets blocked, because the backstop's own save always produces a write record. Confirmed live: a genuinely read-only task (one `wc -l` command) looped 5 times, final chat response degraded to "Unchanged." — same symptom class as the original garble bug, new cause. Exempting only the backstop's own save is NOT sufficient by itself in any session with existing write history (including this one) — bug #1 must close first, or the exemption only helps in a brand-new empty session. If/when a narrow exemption is built, it must verify the ENTIRE command is nothing but the canonical backstop shape — a substring/contains-style check would be defeatable by chaining an unrelated write onto the same command (e.g. `rm -rf X; mkdir -p ... && cat > ...`). **De-risking note (2026-07-11):** CLAUDE.md's Harness / Agentic-Loop Gate Design Principle 4 ("the machinery is invisible to itself") means this collision is solvable structurally — route the backstop's save off the monitored path entirely — whether the report-to-disk feature is kept or dropped. The earlier "nothing consumes the saved report" drop recommendation still stands on the consumption question alone; this collision is no longer a reason to treat the keep/drop decision as urgent or risky either way.
3. **`check_dry_run_before_batch()` (Rule 2) has the same unconditional-block shape as the original garble bug — fix THIRD, lower urgency.** `BATCH_SCALE_WORDS` (includes "backfill") can match incidentally — e.g. a report that quotes PLAN.md's own Standing Rule 3 text while doing unrelated work trips it, with no way to satisfy the check afterward. Confirmed live: caused 4 consecutive rejections on a task that did no batch work at all. Same unconditional-block pattern as the bug fixed in `5b43332`, different function (`deterministic_gate.py`, `main()`'s check loop, not `check_recorded_writes()`), not yet touched.

**Known edge, not a bug (flag only, no fix needed today):** if a future MCP write-tool isn't yet added to `guard_pretooluse.py`'s `MCP_WRITE_CLASS_TOOLS` blocklist, it would be allowed through and mis-tagged `"kind": "mcp_read"` — invisible to the auditor's `write_records` filter. Keep the blocklist current as new MCP write tools appear.

**Uncommitted right now:** `.claude/agents/executor.md` and `.claude/agents/planner-reviewer.md` carry the report-to-disk build that surfaced bug #2 — left in place, unconfirmed, not committed. See "In Progress / Uncommitted Locally."

None of these three are logged in PLAN.md.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** unchanged from 2026-07-10 snapshot — DONE (see git history; not restated here).
- **#5.5 (harness hardening, hard prerequisite for #6–13 write steps):**
  - Piece 1 (write-class Edit/Write/Bash recording): DONE (`35ae840`).
  - Piece 2b-i (script-invocation recording): DONE (`8816804`).
  - Piece 2b-ii (gate reads tool-invocation records): DONE (`6379925`).
  - **MCP write-gate: SHIPPED and verified live** (`f2378a7`, 2026-07-11) — `settings.json` gained a new `mcp__.*` PreToolUse matcher; `guard_pretooluse.py` denies MCP writes (Supabase `execute_sql`, `apply_migration`, and 9 other write-class tools) before execution, for any subagent, while MCP reads pass through. Verified live off disk: `list_tables` ALLOWED (recorded), `execute_sql` DENIED (verbatim deny reason, no execution, no DB mutation). Exit condition (b) DONE. MCP writes are prevented at the guard by deny-before-execution; they are deliberately not recorded for the auditor, because a write that never executed needs no reconciliation.
  - Exit condition (a) (retire the prose backstop to record-only) — still separately OPEN. #5.5 as a whole NOT DONE until (a) also closes.
- **#6 Aliases + sentinel cleanup + strict mode:**
  - Two-doc sentinel attribution: **RESOLVED** (Alex, 2026-07-11) — migration `059`, committed `fa47ead`, live-verified.
  - `murray_surrender.pdf` duplicate: **DONE** (Alex, 2026-07-11) — SHA-256-confirmed identical to `murray_absolute_surrender.pdf` (retained); deleted (untracked/gitignored, no commit for the delete). PLAN.md annotated, committed `9e47b4f`. **Also closes PLAN #14's "delete duplicate Murray files" sub-item — confirmed same file** (PLAN.md line 109 names `murray_surrender.pdf` specifically); #14's own text just hasn't been re-annotated to say so yet (see Open Blockers).
  - Strict mode (refuses silent-sentinel by default): **DONE** (Alex, 2026-07-11) — shipped `280b592`. Default ON, `--allow-sentinel` opt-out, skip-and-continue, end-of-run report. **Built and code-verified; not yet exercised on a real ingest** — unproven until it actually refuses a real document.
  - Remaining OPEN: Deere/Brown/Bedford/Church Life Class alias inserts; Kneeling Christian → An Unknown Christian reassignment. Both gated DB writes waiting on MCP coverage — **recommended faster path: run both directly in the Supabase SQL editor** rather than holding #6 hostage to the harness build. Not yet executed.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Folder renames + `jewish_perspectives` drop — still genuinely not done. Duplicate Murray file deletion — **CONFIRMED closed**: #14's text (line 109) names `murray_surrender.pdf` specifically, and that exact file was deleted this session under #6 (grep-confirmed same file, not a different suspected pair). #14's committed text (`6325e2b`) still reads "NOT happened" — stale, needs a follow-up annotation.
- **#7–#13, #15–#37:** untouched.

---

## In Progress / Uncommitted Locally

Local `main` == `origin/main` at `5b43332` (the garble-fix commit — confirmed by hash). Beyond the accepted standing baseline, the tree also currently carries **`.claude/agents/executor.md` and `.claude/agents/planner-reviewer.md` modified and uncommitted** — the report-to-disk backstop build, which live-testing showed has the read-only collision described above (bug #2). Not committed; do not commit until #1 and #2 above are resolved together.

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
- **Executor garbled final-text reports — root cause found and fixed (`5b43332`), but two NEW/adjacent bugs surfaced live-testing that fix** — see "Known Harness Bugs" above; not fixed yet.
- `--dangerously-skip-permissions`: keep OFF for live writes (standing rule, unchanged).

---

## Next Session Should

Decide the founder question first (executor/planner-reviewer MCP scope), then build #5.5's read-open/write-gated MCP logic against the verified `mcp__claude_ai_Supabase__list_tables` name and `"mcp__.*"` matcher syntax on record above — one load-bearing change, verified via a live subagent (real read PASSES, real write DENIED, both observed off disk) before committing. Separately, NOT bundled: close #6's two remaining alias/reassignment writes via the Supabase SQL editor, and land the PLAN.md #14 drift correction. GOVERNED_FILES hardening is a separate, later session.
