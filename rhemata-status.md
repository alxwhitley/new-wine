# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-26. **PLAN.md has zero active blockers as of today**
— B6-F1 closed this session. A separate repo-infra session also closed today
(ingestion queue TSV conversion, commit `993a3aa`), unrelated.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**B6-F1 — DONE (2026-08-26).** The named-teacher/stored-position route
collision (a Derek Prince deliverance question wrongly refused instead of
answered) is fixed and confirmed live. Alex flipped
`async_answer_config.experimental_teacher_routing_enabled` to `true`
(attended) — it initially had **zero effect**: the wiring code that reads
the flag (`config.py`) and threads it into `produce()` (`answer_worker.py`)
had been drafted but never actually committed/deployed, despite PLAN.md
previously describing it as wired. Found via a live smoke check against the
exact reproduction question, not assumed — it still `refused_attribution`
after the flip. Fixed and deployed same day, commit `77fbb52`. A second live
smoke check confirmed the real fix: `outcome=answered`, 12/12 citations
attributed to Derek Prince alone, zero attribution retry. Full detail:
PLAN.md's B6-F1 entry and
`docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

**Long-conversation-handoff feature — DONE (2026-08-26).** Answers
`docs/roadmap.md` Horizon item 6. Full design:
`docs/superpowers/specs/2026-08-26-long-conversation-handoff.md`. Dismissible
chat nudge fires once a conversation's estimated cumulative generation cost
crosses $0.50 (~13 turns). Migration 092 applied live; code + copy (reviewed
against PRODUCT.md/POSITIONING.md, approved by Alex) deployed. Only Phase F
(observe a real trigger) remains — nothing to act on.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

**New Wine A2:** unchanged. Issue 02-1973 remains `quarantined`, 0
propositions, 0 database writes. Scheduled, no longer behind any active
Blocker.

**Master ingestion queue format conversion — DONE (2026-08-26, commit
`993a3aa`, separate session):** `docs/ingestion/master_ingestion_queue.xlsx`
replaced with four plain-text TSV files via `scripts/ingestion_sheet_io.py`
— lossless round trip proven (87/87 checks). CLAUDE.md's Landmines entry
updated to match.

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, B6): a future suite-wide latency
  candidate still needed — separate question from B6-F1's now-closed
  integrity fix, needs a mechanism addressing the generation bottleneck
  across the whole suite.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** correct the omitted New Wine article + two
  continuations, rerun local no-write gates.
- **Triggered**: JWKS unknown-`kid` rate limit — residual belongs at the
  edge.
- **Process/records note:** two prior sessions had described B6-F1's
  activation wiring as complete when the actual code was only local and
  uncommitted — a real gap between "drafted" and "deployed" that direct
  verification (a live smoke check) caught. Worth remembering generally:
  "the code exists in the repo" is not the same claim as "the code is
  running in production" — check `git status`/deploy state, don't infer
  from a prior session's narrative alone.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual, but read any `scripts/test_*.py` before batch-running it);
  dependency/hardening follow-up (starlette+fastapi, pdfplumber+pdfminer,
  CSP, deferred Next.js major bump); staging source name still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect; no retention/TTL logic
  for user data; `rhemata_readonly_analysis` has no grant on PII/user
  tables; full cascading account deletion still unbuilt.

---

## Next single item

**No active blocker.** Both items opened this session are fully closed and
live. Next work is whatever Alex prioritizes from `docs/roadmap.md`'s
Scheduled list (suite-wide B6 latency, quote accuracy/relevance repair, New
Wine A2 correction) — none is currently authorized as a Blocker. Active
blocker count **0**.
