# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close — W5 smoke + W9 batch/eligibility).
`Temporary-assets/` left untracked on purpose.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers; `docs/roadmap.md` = later work.

**Quote rail (live):** Gold **28/28** approved + `selection_eligible` +
`quote_quality_v1`. `QUOTE_SELECTION_ENABLED=true`. Legacy rows
selection-ineligible.

**W5–W6:** DONE — Savchuk prayer-language article + async smoke
`94cf9284-…` (article cited). Audit:
`docs/audits/w5_savchuk_article_answer_smoke_2026-08-19.md`.

**W9:** DONE — inventory accepted; 3 Vlad pastorvlad articles written
(**3/3/0/0**), staging `shown`, eligibility **12/24** KEEP (Alex-approved).
Lana intrusive-thoughts quarantined. Staging source `33cfa6b5-…` has 4 docs.
Audits: `docs/audits/w9_web_article_batch_*.md`.

**Ingest model:** Groq metadata + prop extract → `openai/gpt-oss-120b`
(stack table in CLAUDE.md already notes query-expansion still on
`llama-3.3-70b-versatile`, unverified).

**Recoverability:** Daily backups on, PITR off; Alex accepted ~24h RPO.

**Blocker queue:** empty (W1–W9 finish-line closed).

---

## Classified work

**Deferred / non-blocking:** optional staging display rename (“web staging”);
optional async smoke on a new W9 article.

**Scheduled / Triggered / Parked:** unchanged in `docs/roadmap.md`.

---

## Next single item

Alex picks from `docs/roadmap.md` (or promotes a deferred item). No private-
beta blocker remains on PLAN.md.

Process baseline: original outcomes (W5 smoke, W9 batch + eligibility)
completed; Lana byline quarantined (classified, not pursued as Vlad); zero
unapproved investigations; no new Blocker promotion; active blocker count **0**.
