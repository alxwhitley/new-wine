# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close). Quote-quality track advanced
through Task 5 gold apply + Task 8 Step 1 regressions; `main` tip after
this close commit. Migration 089 applied. `QUOTE_SELECTION_ENABLED` still
**off** (absent on Railway `rhemata` / `answer-worker`). Untracked
`Temporary-assets/` and `docs/audits/quote_quality_sample_2026-08-19.md`
remain deliberately uncommitted.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers; `docs/roadmap.md` = later work.

**Quote quality track (this close):** Tasks 1–7 + Task 8 Step 1 landed in
repo. Attended gold apply on 3 calibration Prince non-book docs DONE:
59 windows → **28 pending** rows (`quote_quality_v1`,
`selection_eligible=true`, `topic_ids` set); refused_quality=11,
refused_verify=3, errors=0; live DB hard-check 28/28. Report (gitignored):
`quote_propose_review/gold_pipeline_apply_20260818T212522Z.json`. Flag-off
regressions: `scripts/test_quote_rail_regressions.py` (`1eec654`).
Presentation UI code present; **Alex visual sign-off still open**.

**Also true:** W1–W4 merged; migration 088 applied; quote selection
passage-relevance + advisory-lock idempotency shipped earlier; Settled
#28/#29 recorded; legacy 793 selection-ineligible via 089.

**Deploy / rail:** Quote rail remains off until Alex flips
`QUOTE_SELECTION_ENABLED=true`. Gold rows are still `pending` — selection
also requires `status=approved`.

---

## Classified work

**Blocker — active next:** QuoteRail visual sign-off → pending→approved
decision for the 28 gold rows → attended rail re-enable + smoke (PLAN.md
Q2 remainder / Q3).

**Blocker — waiting (parallel, not current):** W5–W6 quarantined article
proof (Alex source + production approval). W9 recoverability after that
path as applicable.

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`
(tag soft-boost, full Prince rebuild, New Wine OCR, Manna rebrand, harness
parked, etc.).

---

## Next single item

1. Alex QuoteRail visual sign-off (Settled #28 presentation).
2. Decide pending→approved for the 28 gold rows.
3. Attended `QUOTE_SELECTION_ENABLED=true` + smoke (gold/pipeline IDs only).

Process baseline (this close): original outcome (attended gold write +
session wrap) completed; Task 8 Step 1 regressions completed earlier same
track; zero unapproved investigations; no new Blocker promotion; one
active critical-path item (sign-off → re-enable).
