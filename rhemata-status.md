# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-09 (push + deploy of two Kimi-session commits; live
site healthy). Same-day follow-up DB-write session added two hidden one-off
sources — no deploy involved, live-site status unchanged.

**Session close:** `.claude/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-09, one-off Ryle Ch. XXI source/document add — DB
write).** Added two hidden, `public_domain` sources for the two credited
extracts inside J.C. Ryle's *Holiness* Ch. XXI ("Extracts from Old
Writers"): Robert Trail (`7243551c-9c9f-4edd-ab9f-ff3deb8bb52e`, aliases
"Robert Trail"/"Robert Traill") and Thomas Brooks
(`8d87f5da-2899-4cab-b130-54b0477f19c9`). One document each — "Concerning
Sanctification" (7 chunks) and "The Necessity of Holiness" (6 chunks) —
ingested through `shared_ingest.ingest_document()`
(`scripts/register_ryle_ch21_extracts_2026-08-09.py`, uncommitted). Text
reconstructed from the Ryle document's chunks 569-581 with the chunker's
80-token overlap deduplicated (`documents.full_text` is NULL for this doc,
so a raw newline-join of the raw chunks would have duplicated text at every
boundary). **Zero propositions on both, correctly** — `license_status=
'public_domain'` means Invariant 11's gate skips extraction by design; kept
PD as factually accurate rather than mislabeling `unlicensed` to force
propositions, and Alex confirmed no propositions are needed. Both
`visibility='hidden'` — **not reviewed for serving yet, do not flip without
Alex's explicit call.** Source Ryle document
(`3f05746a-c848-4ecc-9cea-6e1b1559a5dd`) untouched — reverified still 592
chunks after this session's writes.

**Prior session (2026-08-09, push + tracking-doc update).** Pushed two
Kimi-session commits that were ahead of `origin/main`: mobile bottom-sheet
source panel (`frontend/components/rhemata/source-panel.tsx`, commit
`c37200e`, PLAN.md #38) and folder renames (`sources/lexicon/` →
`sources/stepbible/`, `sources/documents/` → `sources/inbox/`, commit
`37fbc08`, PLAN.md #14 rename portion). Deploy verified: Railway `rhemata`
service and `answer-worker` both Online, Vercel deployment live,
`https://rhemata.app` loads with no console errors.

**Prior sessions (2026-08-08, condensed — full detail: git log +
PLAN.md/CLAUDE.md).** Quote-rail sub-chunk exclusion Müller gap closed
(`ca984cb`/`c0c34c7`). Sixteen governance/product decisions recorded
(position-layer governance, quote-rail scope, Manna rename — CLAUDE.md
Settled decisions #20-27); 4 of 6 position-paper editorial markers
resolved, `five_fold_ministry.md`'s left open for Alex. Quote-rail human
approval removed (migration 085). Precept Austin word-study leak closed
(`is_commentary_chunk()` now excludes `source_kind="word_study"`).
`chat.py` deleted — async is the only answer path, `serving_enabled` TRUE.
`ingest_helloao.py` converted to route through `shared_ingest`, Phase 5 #13
closed.

**Still not fully proven at scale:** a real queue+worker run previously hit
local connection-pool exhaustion (`:5432` session pooler capped at 15), read
as a local-dev artifact, not a code regression.

**Still live (product).**

- **Answer path:** ONE path (async; chat.py deleted). `serving_enabled` TRUE =
  live and unpaused; pooler :6543 in prod; 100-dial concurrency unproven at
  scale.
- **Project 2 phase 1:** single-teacher lock + debate classifier; lock rarely
  fires.
- **Project 3 quote rail:** the only path now runs it; few approved quotes;
  threshold 0.40; curation next targets Prince + visible non-book teachers
  (Murray out). Sub-chunk exclusion (translator footnotes, block quotes,
  catechism Q&A sharing a chunk with real teacher material) landed this
  session window via a separate commit (`a2f4573`/`6dba89a`, not this
  session's own work — PLAN.md Phase 4 already reflects it).
- **Position papers:** fence + exclusion + disclaimer fallback; 4 of 5
  found editorial gaps resolved with dated house positions.
- **Position layer one-hop:** matcher + evidence-injection wiring built,
  verified across all six seeded topics, and now live on origin/main
  (commits `eca8070`/`34f6b0b`/`15be1f8`). 3 of 6 topics still no-op today
  (sole evidence source hidden, Phase 1.3). Refresh trigger + versioning
  policy decided (CLAUDE.md #21/#22), neither built yet.
- **Corpus ingestion:** every document-writing ingest script now routes
  through `shared_ingest` (Phase 5 #13 was the last). Props backfill
  complete; book chapters 8/53; counts query live.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at scale.

- Guest→account, auth CTAs, v4 props prompt, **#14 drop `jewish_perspectives`**
  (rename portion is done; table drop still needs Alex's explicit call), SP
  residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag, embedded
  third-party quote spans.
- **Phase 1.3 subset/execution** still open (policy settled 2026-08-01;
  inventory done).
- **Admin-panel notifications** — new build dependency (CLAUDE.md #21;
  PLAN.md Horizon item 4) with no design yet.
- **`five_fold_ministry.md`'s editorial marker** — unresolved, distinct
  question (restored vs. never-ceased offices); needs Alex's call.

---

## Next

1. **`five_fold_ministry.md` editorial decision** — the 5th marker a prior
   session found but didn't guess at.
2. Async concurrency proof at 100-dial (before any speed-optimization work,
   per the 20s-target decision).
3. Phase 1.3 **subset/execution** (Ravenhill/Savchuk/Poonen — which subset,
   never sentinel; policy itself is no longer the open part).
4. **#14 drop `jewish_perspectives`** when Alex says so — use
   `docs/audits/plan14_housekeeping_prep_2026-08-07.md` as the checklist.
   Rename portion is already live.
5. **Quote curation — Derek Prince specifically** (Murray is out, all-book
   with zero non-book material). See PLAN.md Phase 4 for the full
   visible-teacher non-book breakdown.
6. Hygiene: #16 feedback→flag keep/kill (Alex's call, not urgent).
7. **Robert Trail / Thomas Brooks one-off sources** (Ryle Ch. XXI extracts) —
   currently `hidden`, pending Alex's review before any visibility flip.
8. If Alex wants real confidence in the queue+worker path at scale, a
   controlled run against a connection pool that isn't capped at 15 would
   close the "not fully proven" gap above.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek is NOT shipped
(reduced scope — Alex's call whether to finish). Pass B: remount `UsageRing`
in drawer.
