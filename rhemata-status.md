# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** This session
reversed the YouTube-ingestion hold for one channel, found and fixed a silent
content-destruction defect in caption ingestion, and re-ingested and verified
49 CLF sermons. All work committed and pushed through `6d5af3e`.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church sermon ingestion — DONE and source-verified.** Alex reversed the
standing YouTube-ingestion hold (CLAUDE.md Landmines) for his own church's
playlist only. 49 sermons are live, complete, and checked against source.

1. **Found: caption ingestion was silently storing ~1/3 of each sermon.**
   `youtube_ingest.py` requested `--convert-subs srt`, which triplicates
   YouTube's rolling-window captions, then trusted a Groq model to undo that
   while "preserving ALL theological content verbatim." `gpt-oss-120b`
   instead discarded ~60–75% of every sermon. Dated to the model swap rather
   than the code by a historical control: the same path under the retired
   `llama-3.3-70b-versatile` had preserved ~100%. Mechanism and the four
   reusable lessons: CLAUDE.md Landmines.
2. **Fixed (commit `617341c`).** Native `json3` extraction (no duplication
   exists to undo), the LLM cleaning pass removed outright rather than
   re-modelled, and a coverage gate added — captions must span ≥85% of real
   video duration or the video falls back to Whisper instead of being stored
   short. `scripts/test_youtube_caption_extraction.py` is mutation-proven:
   both the coverage threshold and `aAppend` handling fail the suite when
   reverted.
3. **Re-ingested all 49** (`scripts/reingest_clf_youtube_2026-08-29.py`).
   148,617 → 461,931 words like-for-like. Verified by re-fetching every video
   and comparing against stored text: **49/49 exact match to source**, all 49
   at 123–208 wpm against real durations. Zero propositions written (`owned`
   license). Deletes went through direct SQL, never
   `DELETE /admin/document/{id}` — that endpoint writes `removed_urls`, which
   would have permanently blocked re-ingestion.
4. **Scripture audit + remediation (commit `6d5af3e`).** Every one of the 514
   audited references cited a book genuinely named in its transcript; deeper
   checking found two whose specific chapter appears nowhere (`Psalm 2`,
   `Psalm 3`, one document) — removed and independently re-verified on a
   fresh connection, leaving 512. References whose chapter is not literally
   spoken were sampled and found to be correct content-based inference, not
   invention. ~11 cases are the *speaker* misstating a chapter with the
   extractor faithfully recording it — deliberately left as-is (accurate
   transcription; same posture as Settled #27).

**New Wine A2 — unchanged, still NOT ingestion-ready, still deliberately held
by Alex with no next step selected.** Nothing this session touched it. The
three gates (article review never legitimately passed for Issue 02-1973; Opus
not wired into `review_magazine_issue.py`; proposition extraction never
attempted) and the open resume options are in
`docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md` and the
prior status entry in git history. **Do not spend live-call budget there
without a fresh named ceiling** — the $3 approved 2026-08-29 is spent
($0.63 of it) and does not carry forward.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **318 historical YouTube documents carry residual caption duplication**
  (Ravenhill 117, Savchuk 126, Poonen 50, Kolenda 11, Deere 6, Conlon 6).
  Content is COMPLETE — the retired model preserved everything, it only left
  duplicate fragments behind. A different, milder defect than CLF's.
  Re-ingesting them regenerates propositions, so it needs its own cost
  estimate first. Classified in `docs/roadmap.md` Parked; deferred by Alex's
  explicit choice this session.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text. Small, but the same class of LLM over-reach just removed from the
  transcript path — worth knowing before the next large ingestion run.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Live account-deletion verification** — genuinely blocked, needs Alex to
  create a real disposable test account first (Session Routing hard rule).
- **Analytics production smoke sequence** — deferred, Alex's explicit
  decision, not run.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual); staging source name still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` has no grant
  on PII/user tables.

---

## Next single item

**None selected.** Two standing candidates, neither started, no preference
recorded by Alex:

- **New Wine A2** — held (above); resuming requires a fresh named live-call
  ceiling before any paid run.
- **Quote accuracy/relevance repair** — the Scheduled gate blocking any
  attended quote-rail re-enable (`docs/roadmap.md`).
