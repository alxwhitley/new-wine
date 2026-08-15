# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (first real, non-rehearsal Claude-Code-only
unattended run: two F2 packets, each one `REVISE`→fix→`ACCEPT` cycle,
merged locally and pushed to origin; CLAUDE.md's stale Python-version
claim corrected in the same session).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**First real, non-rehearsal Claude-Code-only unattended run — 2026-08-14/15
— both packets `ACCEPT`'d and merged, pushed to origin (`621f408`).** Two
isolated-worktree `executor`/`planner-reviewer` packets closing real F2
backlog ran end-to-end with no intermediate Alex steering: pin
`pydantic`/`starlette` (`948d3f2`/`68cb746`) and add a backend/worker
`nixpacks.toml` Python-version parity check (`6b3e244`/`c5181c8`). Both
returned `REVISE` on round one — the deps-pin regression test was proven
non-discriminating (the real pre-`da27fe4` `auth.py` returns 401, not 422,
on the newly-pinned stack, same as the fix, so the original test couldn't
tell them apart); the nixpacks-parity script's own docstring fabricated a
claim about Railway and mischaracterized CLAUDE.md Invariant 1. Both fixed
by resuming the same executor agent (not a fresh dispatch), both `ACCEPT`
on round two with the reviewer independently reproducing each fix rather
than trusting the report. Full detail: `PLAN.md`'s Overnight unattended
runs section, `docs/audits/deps_pin_pydantic_starlette_2026-08-14.md`,
`docs/audits/nixpacks_python_parity_2026-08-14.md`.

**Real finding, CLAUDE.md corrected same session (`621f408`):** production
Railway has run Python 3.12 since commit `a729fba` (2026-06-12) —
Invariant 1 and the Tech Stack table said 3.9 for the two months since,
now corrected; the `Optional[str]`-only restriction is lifted (Alex
approved PEP 604 now that 3.12 supports it natively). The `requirements.txt`
unpinned-deps Landmine is marked RESOLVED with the historical `da27fe4`
diagnosis preserved.

**Prior session (2026-08-14), still unresolved:** three attended Grok
harness-builder probes ran, all independently reviewed `ACCEPT`. Probe 1
(planner-reviewer.md verdict-format fix) merged (`4682147`). Probes 2
(`grok/o5-reviewer-diversity-gap-test`) and 3
(`grok/study-page-parse-ref-test-coverage`) remain reviewed-but-unmerged,
Alex's call — both still sitting in disposable worktrees, ready to review
directly. Full detail in `PLAN.md`'s Overnight section and
`docs/audits/grok_probe3_study_page_parse_ref_review_2026-08-14.md`.

**Standing, unchanged:** safety fence deferred, not cancelled (revisit
trigger: real unrecoverable damage, or harness work reaching outside the
repo); harness-tooling review is one round; production DB writes never run
through the harness. All 8 position papers live; one async answer path
(`serving_enabled` TRUE); quote rail live; position one-hop live on origin.

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

1. Decide whether to merge probe 2's (`grok/o5-reviewer-diversity-gap-test`)
   and/or probe 3's (`grok/study-page-parse-ref-test-coverage`) branches —
   both independently reviewed `ACCEPT`, neither merged or pushed, both
   real diffs sitting in disposable worktrees, ready to review directly.
   (Probe 1 already merged, `4682147`.)
2. A fourth probe is well-positioned to close a specific, still-open gap:
   no probe to date has put Grok in a position where the correct,
   in-scope completion of a task actually required confronting a
   hard-forbidden file it couldn't route around (probe 2's forbidden fix
   was structurally outside its packet; probe 3's chosen implementation
   sidestepped the forbidden file rather than facing it). Design one where
   the natural solution path can't avoid it, to see whether Grok
   explicitly self-stops/flags rather than just happening to avoid it.
3. Decide extractor hardening before any next Prince-style batch.
4. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
5. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
6. Trail / Brooks one-offs — review then visibility.
7. `pending` vs `draft` quote-status consolidation.
8. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
9. F2 partial (3/5 exit criteria done 2026-08-14 — pydantic/starlette
   pinned, backend/worker Python parity checked and documented, clean-venv
   admin-auth smoke test passes; Supabase backup/PITR recording and a
   tested restore scope remain) through F5 stay open before F6's
   ingestion-ready benchmark can be declared — O6 alone does not close F6.
10. SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not
    shipped.
