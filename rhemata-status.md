# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (mobile answer continuity, source visibility, and
accessibility; code commit `f76e526` shipped and production verified live).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue remains **0** active blockers. The quote
rail remains off under Alex's 2026-08-25 containment decision. This session
completed the recommended mobile hardening pass without changing retrieval,
prompting, model selection, or answer-quality policy.

**Shipped and live:**

1. **Mobile answer continuity** (`f76e526`). Guest conversations survive a
   reload; an in-flight durable job reconnects by ID, clears partial replay
   text, resumes its verified answer, and retains reconnect state across
   transient delivery failures. Authenticated history remains server-owned.
2. **Sources always visible when available.** Answers whose stored citations
   lack usable inline `[N]` markers now show an accessible Sources fallback;
   source metadata is preserved across guest reloads and validated before use.
3. **Mobile accessibility hardened.** Drawer and feedback dialogs expose proper
   semantics, closed navigation is inert, focus returns to the menu trigger,
   interactive targets are at least 44px, and dismissing feedback no longer
   submits a negative rating.
4. **Honest latency presentation.** Long client-paced reveals are capped at six
   seconds without removing streaming or taking scroll control from the reader;
   the loading state says answers may take about a minute and can be left while
   the tab remains open.
5. **Earlier mobile containment remains live.** The PWA shell stays locked to
   the viewport, streaming does not auto-scroll, send reveals a new turn once,
   the multiline composer remains bottom-aligned, and the top-left drawer opens
   from the left (`732bb6d`–`08fc91d`). The quote rail remains disabled.

**Verification:** frontend tests 24/24, scoped changed-file lint, diff check,
Impeccable detector, and the 17-route production build passed. The final
390×844 browser regression verified viewport containment (`390×844`, root
scroll `0,0`), left-opening navigation and focus return, 44px targets, reload
restoration, two-source fallback, feedback Escape with zero submissions, and
durable-job reconnect with pending state cleared. Two read-only production job
diagnoses confirmed 4/6 stored citations despite zero inline markers, queue
under one second, and 61–64s model generation; the remaining model latency is
Scheduled under B6 rather than traded for answer quality. Vercel deployment
`dpl_8pNESAdmJcoJJxv1BkRWBhtSYeoo` reached Ready, was aliased to `rhemata.app`,
and the same 390×844 regression passed against that live alias.

**Session measures:** original outcome completed; unplanned investigations 0;
findings promoted to Blocker 0; active critical-path item count 0. Alex-approved
scope: the full recommended mobile hardening pass and production deployment.

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, new "Dependency and hardening follow-up"
  section): starlette+fastapi coupled bump — do the read-only exploitability
  triage of its 7 advisories first, the same pass that reduced 3 alarming
  Next.js CVEs to zero live attack surface; pdfplumber+pdfminer coupled bump;
  CSP on the frontend; the deferred Next.js major bump.
- **Scheduled** (`docs/roadmap.md`): quote accuracy and relevance repair before
  any attended re-enable; the live rail remains off.
- **Scheduled** (`docs/roadmap.md`, B6): model-generation latency benchmark;
  current production evidence is 61–64s generation with sub-second queue time.
- **Triggered** (`docs/roadmap.md`): JWKS unknown-`kid` rate limit — PyJWT
  2.13.0 already fixed the amplifying half (cache-wipe on failed fetch); the
  residual is un-amplified and belongs at the edge, not in `auth.py`.
- Public `/docs` + `/openapi.json` on the API list every route including
  admin ones. Routes stay auth-gated, so this is a map, not an open door.
  Left as-is deliberately — Alex may use it; not yet formally classified.
- `darlenecunningham.com` confirmed to be an unrelated living romance
  novelist, not the YWAM co-founder. Spreadsheet NOT updated — its Read Me
  reserves `verification_status` for Alex personally, and precedent (Bonnke,
  2026-08-19) is to record and let him mark it.
- Staging source name still reads `"Vlad Savchuk (web staging)"` on
  citations — attended one-row `sources.name` UPDATE whenever Alex wants it.
- Carried, not re-checked this session: Bonnke URL suspect (expired cert, no
  CfaN corroboration); no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII tables; full cascading
  account deletion still unbuilt (migration 090 removed only the DB-level
  blocker — `POST /account/delete-request` is still a stub).

---

## Next single item

Alex's call. The next measured UX item is the B6 answer-generation latency
benchmark; if continuing the quote track instead, define the representative
accuracy/relevance acceptance set before changing selection or extraction.
Active blocker count **0**.
