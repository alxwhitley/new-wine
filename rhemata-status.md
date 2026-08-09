# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-09 (session close — Grok read-only book-boundary /
Ryle Ch. XXI attribution chain; same-day Trail/Brooks one-off ingest already
live in DB as hidden).

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**This session (2026-08-08/09, Grok — read-only analysis only; no repo code
changes, no splitting code, no migrations).** Two proposal/check reports
written **outside the repo** under `~/rhemata-analysis/`:

1. **`chapter_boundary_proposals_2026-08-08.md`** — exact ordered chapter
   start/end chunk spans for the **18 HIGH-confidence books** from the prior
   book-structure survey. Per book: front matter (not chapters), chapter
   labels as stored, titles, exclusive chunk ranges, back matter, explicit
   Uncertain notes (running headers, TOC/body share, OCR spellings, etc.).
   Nothing applied to the DB or detector.

2. **`ryle_ch21_attribution_check_2026-08-08.md`** — held-back Chapter XXI
   of Ryle *Holiness* (chunks 569–581). Finding: **exactly two** long
   extracts, both explicitly credited (Robert Trail/Traill; Thomas Brooks);
   **zero uncredited** extracts; neighbor isolation reliable except
   intra-chunk soft edges on 569 and 576. At check time neither writer was a
   corpus source.

**Same-day follow-up (already live — not this Grok session’s write):** those
two extracts registered as hidden `public_domain` one-off sources via
`scripts/register_ryle_ch21_extracts_2026-08-09.py` (uncommitted at last
status): Robert Trail (`7243551c-9c9f-4edd-ab9f-ff3deb8bb52e`) doc
“Concerning Sanctification” (7 chunks); Thomas Brooks
(`8d87f5da-2899-4cab-b130-54b0477f19c9`) doc “The Necessity of Holiness”
(6 chunks). Zero props (PD gate). **Stay `hidden` until Alex reviews.**
Source Ryle document untouched (592 chunks).

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live; few approved quotes; books tabled for quote extraction.
Position one-hop live on origin. Book chapter extraction still 8/53; Open
Decision #21 (numeral detector) still **not decided** — proposals exist for
human review only, detector still unwired.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, **#14 drop `jewish_perspectives`**,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Phase 1.3 subset/execution still open.
- Admin-panel notifications — dependency of refresh (CLAUDE.md #21); no design.
- `five_fold_ministry.md` editorial marker — needs Alex.

---

## Next

1. **`five_fold_ministry.md` editorial decision.**
2. Async concurrency proof at 100-dial (before speed work).
3. Phase 1.3 subset/execution (Ravenhill/Savchuk/Poonen).
4. **#14 drop `jewish_perspectives`** when Alex says so.
5. **Quote curation — Derek Prince** (Murray out; see PLAN.md Phase 4).
6. **Human review of chapter-boundary proposals** (18 books) before any
   apply/wiring decision — Open Decision #21 still open.
7. **Trail / Brooks one-offs** — review then decide visibility; script still
   uncommitted if not yet landed.
8. Hygiene: #16 feedback→flag keep/kill.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
