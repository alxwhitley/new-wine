# Grok Timeout-Retraction / Resume-Limitation Correction — Independent Review — 2026-08-14

## Boundary

Review of commit `5c765e5` ("fix(harness): correct Grok timeout/kill claim,
document resume limitation") only — the two changed sections of
`HARNESS.md` ("Grok tool-surface facts" / "Session-resume reliability") and
`.grok/agents/harness-builder.md` ("Grok-shaped outer-timeout note"), plus
the two subsequent records-only commits (`9a3b2cc`, `153933c`) skimmed for
scope leakage. No file was edited and no command mutated the repo; the
review was read-only end to end (both full target files read start to
finish, `git show`/`git log`/`grep`/`find` used for evidence, two source
files — `scripts/harness_coordinator/v1/verification_commands.py` and
`scripts/harness_coordinator/v1/process_sidecar.py` — read in full,
`rhemata-status.md` and `PLAN.md` cross-checked for consistency, not
edited).

## Why this review, and why independent

Same standing rule as the precedent review
(`docs/audits/grok_harness_builder_role_review_2026-08-14.md`, itself
reviewed and `ACCEPT`ed earlier the same day): PLAN.md's "no worker result
is complete... no ACCEPT without recorded acceptance evidence." This
commit retracts a factual claim that same precedent review had itself
verified `ACCEPT` — criterion 4 there confirmed the (subsequently
falsified) "genuine SIGTERM→SIGKILL kill on explicit timeout" claim against
a community leaked-schema source, with the caveat "no official confirmation
located." That caveat turned out to matter: a live reproduction later the
same day proved the claim false. A self-graded close of the correction
commit would repeat the same failure mode this review exists to catch —
this pass is a fresh-context Sonnet read, uninvolved in either the original
claim or its retraction, checking the correction against the current repo
state rather than against its own commit message.

## Checklist and evidence

1. **Re-verify the retracted finding against real evidence — PARTIAL,
   evidentiary limitation stated plainly.** No persisted reproducible test
   artifact (script, transcript, or log) for the three sleep-command cases
   exists anywhere in this repository. Searched: `git log --oneline` for
   both changed files (clean history, no orphaned test-script commit);
   full-repo `grep` for the specific numeric markers (`140000`, `20000ms`,
   `sleep 200`, `sleep 60`) — hits only in the prose files themselves
   (`HARNESS.md`, `PLAN.md`, `.grok/agents/harness-builder.md`,
   `.claude/agents/executor.md` (a PLAN.md-unrelated hit), the precedent
   review); `docs/audits/` directory listing — no file dated 2026-08-14
   documents this reproduction as a standalone artifact (only the earlier,
   unrelated role-definition review exists at that date); `find` across
   all seven `.worktrees/` checkouts and the standalone `/private/tmp`
   worktree; every `*.jsonl`/`*transcript*`/`*probe*`/`*grok*` file in the
   repo. All of it comes back empty for this specific reproduction. **This
   review cannot independently re-run or inspect the raw evidence behind
   the 20000ms/60s-actual and 140000ms/200s-actual numbers — it can only
   confirm the prose is internally consistent and consistent with the
   commit message and `rhemata-status.md`'s independent summary** (which
   states the same 140s/60s-over figures in its own words, written by the
   same session but as a separate document — not zero corroboration, but
   not an independent artifact either). Flagged as a real evidentiary gap,
   not glossed over.

   **What CAN be, and was, independently verified from the repo itself:**
   `scripts/harness_coordinator/v1/verification_commands.py`'s
   `run_verification_command()` launches the packet command via
   `subprocess.Popen(..., start_new_session=True)`, and on
   `subprocess.TimeoutExpired` calls
   `process_sidecar.terminate_process_group(process.pid, grace_seconds=_TERMINATE_GRACE_SECONDS)`
   (`_TERMINATE_GRACE_SECONDS = 5.0`). `terminate_process_group()` in
   `process_sidecar.py` does `os.killpg(pgid, signal.SIGTERM)`, polls up to
   `grace_seconds` for group death, then `os.killpg(pgid, signal.SIGKILL)`,
   polls up to a further 2.0s, and returns a bool reflecting whether the
   group actually died — a real, unconditional SIGTERM→SIGKILL
   process-group teardown, not a claim resting on Grok's or any other
   agent's self-report. This part of the corrected text is independently
   confirmed, directly from the code.

2. **Genuine retraction, not a softened restatement — CONFIRMED.** Both
   full sections read end to end. The old sentence claiming a genuine kill
   ("an overrun genuinely gets killed: the process group receives SIGTERM,
   escalated to SIGKILL...") is deleted outright in both files, not
   hedged. The replacement text states affirmatively, twice per file: "does
   NOT prevent backgrounding and does NOT cause a kill at any tested
   value" and "No mechanism was found on this surface that genuinely kills
   an overrunning command at any declared timeout value." A full-file grep
   for `kill|sigterm|sigkill|timeout|backgrounded` in both files (not just
   the diff hunks) returns hits only inside the corrected sections (and,
   for `HARNESS.md`, the unrelated `.claude` hook-scope language at lines
   42/113/120 using "genuinely" in an unconnected sense) — no leftover
   sentence anywhere in either file still implies an explicit timeout
   provides kill protection or backgrounding prevention.

3. **"Only confirmed real kill path" claim — CONFIRMED, with one
   dangling-cross-reference defect found and flagged.** Both files state
   the same conclusion in matching language: `HARNESS.md` — "the ONLY
   confirmed real kill path for a Grok-run verification command"; the
   `.grok` file — "the only confirmed real kill path for an overrunning
   verification command." Consistent, and consistent with finding 1's
   independent code read. **Defect found:** `HARNESS.md` line 196 reads
   "Still always declare an explicit `run_terminal_command` timeout per
   the guidance below" — but nothing below that sentence in `HARNESS.md`
   itself constitutes timeout-value guidance. What immediately follows is
   the unrelated "Session-resume reliability" paragraph, then a `---` and
   `## Closed` (a historical bug tracker). The actual guidance being
   referenced — the `(timeout_seconds + 15) * 1000` margin formula — lives
   only in `.grok/agents/harness-builder.md`, which `HARNESS.md` names
   explicitly two paragraphs *earlier* ("see `.grok/agents/harness-builder.md`
   for the CLI-invocation guidance built on these"), not "below." Confirmed
   this phrase is new to this commit — the pre-correction `HARNESS.md` text
   this replaced (visible in the `5c765e5` diff) never used "below" at all.
   Judged non-blocking: the substantive correction is unaffected, and the
   correct file is named by name earlier in the same paragraph block, so a
   reader isn't actually stranded — but it's a real, commit-introduced
   dangling cross-reference worth fixing on the next touch of this section.

4. **Session-resume documentation — CONFIRMED accurate and appropriately
   hedged.** States exactly two tested conditions: resume "works reliably"
   on a session that "exited on its own" (verified directly, with the
   resumed session showing "real, correct awareness of its own prior
   work"), and fails ("zero output," twice) on a session "externally
   hard-killed mid-execution." The causal mechanism is explicitly bracketed
   as unconfirmed: "The exact mechanism isn't nailed down (plausibly the
   on-disk session transcript is never flushed/finalized before a hard
   kill, but that root cause wasn't independently confirmed) — only the
   practical behavior is established." This is a hedged hypothesis, not a
   stated fact — no sentence anywhere upgrades "plausibly" to a claim of
   proof. The mitigation is a bolded, imperative, unambiguous single
   sentence: "**Treat an externally-killed Grok session as unresumable:
   don't attempt `--resume` on it, restart the packet fresh instead.**" —
   present in `HARNESS.md` only (the `.grok` file's parallel section is the
   timeout note; the resume finding was added to `HARNESS.md` alone, which
   is consistent with `HARNESS.md` being the cross-agent "verified facts"
   home the file's own preceding sentence names it as). `rhemata-status.md`'s
   "Current state" section restates the same two facts in its own words
   with no contradiction and no overclaim of its own.

5. **Scope discipline — CONFIRMED.** `git show --stat 5c765e5`: exactly two
   files changed, `.grok/agents/harness-builder.md` (49 lines) and
   `HARNESS.md` (44 lines) — matching the task brief's stated counts
   exactly. `git show 5c765e5 --name-only` confirms no third file. Both
   diff hunks are contiguous single-region edits inside the named sections;
   no unrelated wording elsewhere in either file was touched opportunistically.
   `git show --stat 9a3b2cc`: `PLAN.md` + `rhemata-status.md` only (neither
   `HARNESS.md` nor the `.grok` file). `git show --stat 153933c`:
   `rhemata-status.md` only. Neither subsequent commit touches either
   target file's substantive content — both are pure records bookkeeping,
   consistent with their own commit messages.

## Final gate

Independent Sonnet review, fresh context, one round (harness-tooling review
is one round per the standing rule; multi-round is reserved for the answer
path):

```
VERDICT: ACCEPT
```

Two non-blocking notes recorded: (1) no persisted reproducible artifact for
the timeout-retraction reproduction exists anywhere in the repository — the
correction rests on prose description (commit message +
two documentation files + `rhemata-status.md`'s independent restatement),
not an inspectable transcript or script; this review could confirm internal
consistency across all four but could not independently re-derive the
20000ms/60s and 140000ms/200s numbers from raw evidence. What could be
independently verified — that `verification_commands.py` really does
implement a genuine, unconditional SIGTERM→SIGKILL process-group teardown —
was verified directly from the code and supports the corrected text's
central practical conclusion regardless. (2) `HARNESS.md` line 196's "per
the guidance below" is a dangling cross-reference introduced by this same
commit — nothing below it in `HARNESS.md` is the referenced guidance; the
actual formula lives in `.grok/agents/harness-builder.md`, named two
paragraphs earlier in the same block. Neither note changes the substance of
the retraction or the resume finding, which read as a genuine, complete
retraction and an appropriately hedged new finding respectively.

## Non-actions

Read-only throughout. No file was edited (including the "guidance below"
defect noted above — flagged for a future touch, not fixed by this review),
no command was run that could mutate the repo or any database, and nothing
was committed or pushed by this review pass. This document is the only
write action taken.
