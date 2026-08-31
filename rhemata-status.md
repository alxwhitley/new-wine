# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers.** Across
2026-08-30/31: ruled the 15 held CLF recordings out permanently, cleared and
ingested 7 of the 10 misclassified `unknown` rows (CLF YouTube 56 → 63),
cleaned CLF's citable author names 16 → 12, fixed two ingest defects
(`5c94b3c`, `9224650`), and gave `sources/` its first off-machine backup. The
CLF tab is now fully triaged with nothing undecided on it.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church — 63 YouTube documents (live, 2026-08-31), 0 duplicate URLs
corpus-wide.** Plus 15 pre-existing non-YouTube CLF docs, so a bare `count(*)`
on the source reads 78 — filter on `url ILIKE '%youtu%'` before comparing
against any YouTube figure. Zero propositions throughout: `owned` sources skip
the license gate. Every CLF document has a local file. **The CLF tab is fully
triaged — nothing on it is undecided:** 15 `held_permanent`, 7 ingested and
source-verified, 3 `held_speaker`, 1 `unavailable`. The ingest gate matches 0
rows on that tab. Ingest/verification traps have moved to CLAUDE.md's YouTube
landmine.

**15 recordings held permanently (Alex, 2026-08-30)** on content shape and
pastoral-privacy exposure, **not runtime** — do not reopen as a length
question, and no trimming step may be built to salvage them. Reasoning in
CLAUDE.md; evidence in
`docs/audits/2026-08/clf_held_recordings_review_2026-08-30.md`.

**3 excluded on speaker grounds (Alex, 2026-08-31):** Jeremy Porras (Raleigh
Dream Center — not CLF), Angel Woodard, Tiffany Cogdell (unresolved against
the existing `Tiffany Davis` identity). `AjyYzuiJo50` is `unavailable` — the
video no longer exists on YouTube; its recorded alias failure was a symptom,
not the cause.

**CLF answers name the individual preacher, not the church — name list cleaned
2026-08-31 (7 attended DB writes, reconciled from a fresh read).**
`producer.py` builds `permitted_names` from `documents.author`, so guest
speakers are citable authorities alongside Derek Prince. Alex's ruling: keep
per-preacher names, fix the data. Citable CLF names **16 → 12**, no artifacts
left. **Still open:** guest preachers who spoke once at CLF remain named
citable voices without their knowledge — ranked failure mode #2. Alex chose
cleanup over resolving that; it is live, not closed.

**New Wine A2 — unchanged, still NOT ingestion-ready, still held by Alex with
no next step selected.** Three gates and the open resume options:
`docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md`. **Do not
spend live-call budget there without a fresh named ceiling** — the $3 approved
2026-08-29 is spent and does not carry forward.

**Quote rail: still off (`QUOTE_SELECTION_ENABLED=false`) — and a standing
risk became real.** Settled #19's residual risk read "prospective, not
retrospective"; that is now false and CLAUDE.md is corrected in place. CLF's
63 sermons are auto-transcribed audio under `sermon_transcript` and a
mistranscription is confirmed present. Nothing gates on transcript status; no
exposure only because the flag is off. **Before it flips back on, CLF needs
exclusion from quoting or an audio-confirmation step.**

---

## Findings surfaced, not yet acted on

- **The 301 missing local files and the 318 caption-duplication set are one
  decision, not two** — heavy overlap, not identical, both dominated by
  Savchuk/Ravenhill/Poonen. The 301 are all pre-`617341c`, so a fresh fetch
  does not match what is stored and the backfill script correctly refuses to
  write; the 318 carry residual duplication but COMPLETE content. One
  re-ingest fixes both, costs real money (non-`owned`, propositions
  regenerate), and needs a named cost estimate first. `docs/roadmap.md`
  Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — `github.com/alxwhitley/rhemata`
  is PUBLIC and `/sources/` is gitignored; committing it would publish the New
  Wine PDFs, Precept Austin, Derek Prince scrapes, and living ministers'
  transcripts, inverting the license gate, safe_mode, hidden staging, and the
  PA lockout in one irreversible move. **Backup gap largely closed 2026-08-30**
  — irreplaceable material now copied to iCloud Drive → `Rhemata Backup`
  (1,150 files, 496 MB, verified); public/re-scrapable data deliberately
  skipped. **Residual risk:** iCloud is sync, not versioned backup — a local
  corruption propagates. Guards against machine loss, not bad edits.
- **11 of the ingested CLF documents contain an offering appeal**, and one
  each an usher direction and a dismissal — a milder, pre-existing form of the
  whole-service problem the 15 were held for. Whether to audit those 11 for
  named-congregant content is open.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text — the same class of LLM over-reach removed from the transcript path.
  The 7 sermons added 2026-08-29 audited clean, so the rate stands at 2 of 625
  checked; extended, not re-measured.
- **Live account-deletion verification** — blocked, needs Alex to create a real
  disposable test account first (Session Routing hard rule).
- **Analytics production smoke sequence** — deferred by Alex, not run.
- Carried, not re-checked: `scripts/test_metering.py` writes live to production
  despite its `test_*.py` name (self-cleans); staging source still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect;
  `rhemata_readonly_analysis` has no grant on PII/user tables.

---

## Next single item

**None selected.** Candidates, none started:

- **Guest-speaker attribution** — the live product question the 2026-08-31
  cleanup deliberately did not answer (Current state, above). Cheap to scope,
  no writes.
- **The 301 / 318 re-ingest** — needs a named cost estimate before Alex can
  rule (Findings, above).
- **New Wine A2** — needs a fresh named live-call ceiling before any paid run.
- **Quote accuracy/relevance repair** — the Scheduled gate blocking any
  attended quote-rail re-enable (`docs/roadmap.md`).
