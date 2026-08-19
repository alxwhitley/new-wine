# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close). Quote polish + W5 write/eligibility
+ W9 inventory recorded locally (commits through `2a19658` + this close).
`Temporary-assets/` left untracked on purpose. **Not pushed** — `main` ahead
of `origin/main`.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers; `docs/roadmap.md` = later work.

**Quote rail (live):** Gold **28/28** approved + `selection_eligible` +
`quote_quality_v1`. `QUOTE_SELECTION_ENABLED=true`. Settled #28 presentation
polish landed (`9b7fb45` — attribution leads, `bg-popover` card, outline
topic chip). Legacy rows remain selection-ineligible.

**W5–W6 web article:** Vlad Savchuk pastorvlad prayer-language article
ingested under staging source `Vlad Savchuk (web staging)`
(`33cfa6b5-…`, **shown** + unlicensed). Doc `c97533db-…`: 4 chunks, 12
props, **4 eligible** (P1/P3/P7/P12), 0 quotes. Live Savchuk unchanged.
Idempotent rerun proven. Retrieval probe sees all 4 chunks. **Async
answer-integrity smoke still open.**

**Ingest model:** Groq metadata + proposition `EXTRACTION_MODEL` →
`openai/gpt-oss-120b` (`87c192f`) after `llama-3.3-70b-versatile` 404.
`answer_toolbox` query-expansion model not swapped this session.

**W9:** Daily physical backups on, PITR off, ~7-day retention; Alex accepted
~24h RPO / unproven project RTO
(`docs/audits/w9_recoverability_inventory_2026-08-19.md`). Batch half still
queued after W5 close.

**Deploy note (prior):** Railway `rhemata` had briefly drifted to Railpack;
restored NIXPACKS + `/backend`. Confirm builder before trusting a failed
deploy as a code bug.

---

## Classified work

**Blocker — active next:** W5–W6 answer-integrity / article-supported async
smoke.

**Blocker — waiting:** W9 first small web-article batch (after W5 smoke).

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`
(tag soft-boost, full Prince rebuild, New Wine OCR, Manna rebrand, harness
parked, etc.).

---

## Next single item

1. Async answer smoke for the Savchuk web article (confirm citations /
   propositions; optional rename away from “web staging” label).
2. Then W9 batch half when ready.

Process baseline (this close): original parallel tracks (QuoteRail polish
via Claude, W9 inventory, W5 article proof through eligibility+shown)
completed; answer smoke deferred by Alex (“commit and stop”); zero
unapproved investigations; no new Blocker promotion; one active item
(answer-integrity smoke). Local commits not pushed.
