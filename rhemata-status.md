# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-14 (two attended Grok harness-builder probes run,
both independently reviewed `ACCEPT`; two real infrastructure findings from
probe 2 investigated, corrected, pushed to origin, and the correction itself
independently reviewed `ACCEPT`).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Two attended Grok harness-builder probes run and independently reviewed
`ACCEPT` — 2026-08-14, this session.** First real Grok-authored work through
the harness (the prior session's "probes 1–3" were all Claude Code). Both:
isolated worktree, disposable branch, Sonnet review per `HARNESS.md`'s
contract, nothing merged or pushed — Alex's call, still open.

- **Probe 1** — `.claude/agents/planner-reviewer.md`'s stale two-value
  verdict format and 12 hardcoded checklist citations (prior session's Next
  item #10). Fixed the verdict format to match the four-value contract; for
  the 12 citations, correctly found none survive verbatim (the governing
  docs were restructured, not just moved — line numbers alone wouldn't have
  fixed it) and left all 12 unedited, flagged rather than guessed at.
  Branch `grok/planner-reviewer-verdict-citation-cleanup`, worktree
  `.worktrees/grok-planner-reviewer-cleanup`.
- **Probe 2** — deliberately harder: real Python, real tests, real judgment.
  Added one new test to `.claude/harness-selftest/test_o5_reconciliation.py`
  documenting a genuine, already-disclosed, still-open gap in
  `_o5_hop_authorized()` (O5 audit "Residual gaps" #9 — reviewer-diversity
  is exact-pair only, doesn't replicate the live selector's weaker
  provider-family rule). Never touched the forbidden production files
  despite fully understanding how to close the gap. Full suite passes:
  1368 passed, 1 skipped (baseline 1367 passed, 1 skipped + 1, zero
  regressions — independently re-run directly, not self-reported). Branch
  `grok/o5-reviewer-diversity-gap-test`, worktree
  `.worktrees/grok-o5-diversity-gap-test`.

**Two real infrastructure findings from probe 2, investigated and fixed —
pushed to origin, commit `5c765e5`.** (1) `HARNESS.md`'s and
`harness-builder.md`'s claim that an explicit Grok `run_terminal_command`
timeout "genuinely kills" an overrun was FALSE — verified directly by
reproduction (a command ran 60 real seconds past its own declared 140s
timeout and was never killed). `verification_commands.py`'s own
SIGTERM→SIGKILL teardown is now documented as the only confirmed real kill
path on this surface, not a consistency preference. (2) `grok --resume`
works for a cleanly-exited session (verified directly) but not one that was
externally hard-killed mid-execution (two zero-output attempts on the same
session) — documented as a known limitation: restart the packet, don't
attempt `--resume` on a killed session. Both live in `HARNESS.md`'s "Grok
tool-surface facts" note, the existing home for this kind of verified fact.
**The correction commit (`5c765e5`) was itself independently reviewed
`ACCEPT`** — fresh-context Sonnet pass, uninvolved in making the correction
(`docs/audits/grok_timeout_resume_correction_review_2026-08-14.md`).
Confirmed the retraction is genuine (no leftover sentence in either file
still implies explicit-timeout kill protection) and that
`verification_commands.py`'s SIGTERM→SIGKILL teardown is real, read
directly from the code. One evidentiary gap noted, not a blocker: no
persisted test artifact for the underlying sleep-command reproduction
exists in the repo, so that specific claim rests on the prose description,
not an inspectable transcript. One small documentation defect flagged for a
future touch: `HARNESS.md` line 196's "per the guidance below" is a
dangling cross-reference — the actual timeout-margin formula lives in
`.grok/agents/harness-builder.md`, named two paragraphs earlier, not
"below."

**Standing decisions, unchanged:** harness-tooling review is one round
(multi-round stays on the answer path). Safety fence deferred — not
cancelled, not a launch blocker. Path to real overnight workers: narrow
file allowlist + Alex reading the morning report daily for a week.
Revisit trigger: the fence gets built if a real overnight run causes
damage that cannot be recovered from git, or before any harness work
reaches anything outside the repository. Production DB writes never run
through the harness, day or night.

Already true, unchanged: all 8 pillars live; one async answer path
(`serving_enabled` TRUE); quote rail live; position one-hop live on
origin.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- 20 Prince documents with zero approved quotes (2026-08-09).

---

## Known Harness Bugs

- **Auto Mode misfire on harmless prose mentioning "SQL"/"migration"
  — 2026-08-14.** A live `executor` subagent hit this classifier while
  running Python `time.sleep` verification commands — semicolons in the
  test one-liners, combined with the executor's own loaded
  SQL-comment/semicolon instructions (the Migration 051 gotcha), triggered
  a defensive loop explaining a phantom SQL-migration flag instead of
  running the task. Nothing SQL- or migration-related was actually
  present. Worked around per the stall-risk rule: did not retry the
  identical prompt, removed the semicolons, reran once — cleared. A
  future session must not assume this misfire is always harmless — it can
  consume a full turn and block real work; reformulate, don't just retry.

---

## Next

1. Decide whether to merge probe 1's
   (`grok/planner-reviewer-verdict-citation-cleanup`) and/or probe 2's
   (`grok/o5-reviewer-diversity-gap-test`) branches — both independently
   reviewed `ACCEPT`, neither merged or pushed, both real diffs sitting
   in disposable worktrees, ready to review directly.
2. A third attended Grok probe is well-positioned to run next — the two
   real infrastructure gaps probe 2 surfaced (timeout/kill claim,
   session-resume reliability) are now investigated and corrected on
   origin; a third probe would be the first to run against accurate
   documentation of both.
3. First supervised overnight night. Fence stays deferred, unchanged
   revisit trigger (real unrecoverable damage, or harness work
   reaching outside the repo).
4. Decide extractor hardening before any next Prince-style batch.
5. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
6. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
7. Trail / Brooks one-offs — review then visibility.
8. `pending` vs `draft` quote-status consolidation.
9. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
10. F2–F5 remain open before F6's ingestion-ready benchmark can be
    declared — O6 alone does not close F6.
11. SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not
    shipped.
