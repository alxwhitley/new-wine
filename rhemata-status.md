# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close). Q2/Q3 functional re-enable DONE.
`QUOTE_SELECTION_ENABLED=true` on Railway `rhemata` + `answer-worker`. Both
services on commit `ad0dc0a` (NIXPACKS; rhemata root `/backend`). Untracked
local preview/scripts/`Temporary-assets/` deliberately not in this docs
commit.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers; `docs/roadmap.md` = later work.

**Quote rail (live):** Gold set **28/28 approved** + `selection_eligible`
+ `quote_quality_v1`. Selection flag **on**. Smoke answered with
`policy_v3:quote_selection=true` and 3 gold-only quote IDs (resolve carries
teacher · work_title · topic_ids · restated_point). Legacy rows remain
selection-ineligible (migration 089).

**Design residual:** Settled #28 presentation *code* is live; Alex deferred
visual/taste polish to Claude (explicit, same session as re-enable).

**Deploy note (this session):** GitHub deploys for `rhemata` had drifted to
Railpack without `rootDirectory` (deadline/snapshot failures; brief API
outage). Fixed via `serviceInstanceUpdate` to NIXPACKS + `/backend` +
`railway.toml`; image redeploy picked up the flag. Worker stayed Nixpacks
at `/`.

---

## Classified work

**Blocker — active next:** QuoteRail design polish (Claude) on Settled #28
presentation.

**Blocker — waiting (parallel):** W5–W6 quarantined article proof (Alex
source + production approval). W9 recoverability after that path as
applicable.

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`
(tag soft-boost, full Prince rebuild, New Wine OCR, Manna rebrand, harness
parked, etc.).

---

## Next single item

1. Claude QuoteRail design polish (visual separation / attribution taste).
2. Then W5–W6 when Alex picks the article (does not displace design unless
   Alex reorders).

Process baseline (this close): original outcome (approve gold + re-enable +
smoke) completed; visual sign-off cancelled/deferred by Alex; zero unapproved
investigations; no new Blocker promotion; one active critical-path item
(design polish).
