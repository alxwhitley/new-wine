# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-30. **PLAN.md has zero active blockers.** This session
ingested a second CLF playlist (7 sermons, verified verbatim), held 15
entries back as out-of-shape for the corpus, fixed a duplicate-document
defect in triage, stopped the YouTube path deleting its own transcripts, and
backfilled all 56 CLF local files at zero API cost.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church "Sermon Archive" playlist — 7 ingested and source-verified; 25
deliberately held.** Second playlist under the same one-channel reversal
(CLAUDE.md Landmines). The prior session's 49 from "Sermons" are unchanged.
Live count 2026-08-29: **56 CLF YouTube documents**, 0 duplicate YouTube URLs
corpus-wide.

1. **Triage** (`youtube_triage.py --sheet "CLF Church" --add <playlist>
   --min-duration 300`): 43 entries → 40 unique → 32 net-new rows. **Both
   stages must be `--sheet`-scoped** — a bare `run_queue_ingest.py` would
   have ingested 731 rows across three channels outside the reversal.
2. **Ingested 7** (`youtube_ingest.py --sheet "CLF Church"`): 7 done, 0
   failed, 0 needs_source, all captions, no Whisper. 189 chunks. Zero
   propositions (`owned`), as expected.
3. **Verified verbatim, 7/7**, plus 116–195 wpm against real durations — no
   truncation signature. **Verification gotcha:** chunks overlap
   (`chunk_text(..., chunk_target=550, overlap=80)`), so concatenating them
   inflates ~17% and cannot be compared to source; and chunk 0 carries the
   metadata header, so compare against the composed file, not raw captions.
   Both mistakes were made this session and produced false alarms.
4. **Scripture audit: 111 references, 111 genuine, 0 fabricated.** The one
   flag (`1 Thessalonians 5:17`) was a caption defect, not invention.

**15 long recordings held at `ingest=FALSE`, pending Alex.** 92–194 min
against a 65-min median for the existing corpus. Captions show they carry the
whole service — sound-check, ushering, opening prayer at the front; offering
and dismissal at the back — which would store as `sermon_transcript` under a
named minister and become retrievable teaching material. Alex's read was that
the excess is altar-call-after-the-message; the audio contradicts that (both
ends), and that conflict was reported, not resolved unilaterally. **No
trimming step exists and none should be built casually** — a model deciding
where a message ends is the mechanism that discarded 60–75% of every sermon
before `617341c`. `qFfoGi7Vexs` ends on material that does not read like a CLF
service at all — likely a bad upload; check it before any policy applies.

**Also held:** 10 rows Groq classified `unknown` (several are plainly
sermons, including one titled "Sunday Morning Service") and 1 row still
`needs_source` from the prior session ("Freedom from Guilt, Shame &
Rejection | Scott Woodard") — alias never resolved, never ingested.

**Fixed: the YouTube path deleted its own local transcripts (commit
`5c94b3c`).** `ingest_video()` wrote the transcript to `sources/youtube/
cleaned/`, ingested from it, then unlinked it — deliberate (the docstring
listed "Delete temp .txt" as step 5), but it left stored documents existing
only in Supabase; the archive had been cold since 2026-06-03. A successful
ingest now MOVES the file to `sources/youtube/ingested/`; only a failed one
deletes, so that directory means "this is in the corpus".
`scripts/test_youtube_local_retention.py` is offline and mutation-proven.
**Note `sources/web/` is a different lane** (web scrapes, currently Derek
Prince only) — not where YouTube material belongs.

**Coverage 2026-08-30 — 374 YouTube docs: 56 id-named (all CLF, this
session), 17 old slug-named, 301 with no local file.** Two earlier figures
were wrong and are superseded: 357 (loose title matching) and 318 (id
matching only). **Never split a filename on `_` to recover a video id** — ids
contain underscores (`Al_a7taOEo0`); match the `{video_id}_` prefix.

**CLF fully backfilled: 56/56, zero API cost.** Captions re-fetched via
yt-dlp (no key, no billing; SELECT-only DB access), every stored chunk
verified verbatim against the composed file before keeping it — 0 mismatches,
0 failures. Safe only because these were re-ingested under the fixed json3
path, so a fresh fetch reproduces what is stored.

**The remaining 301 must NOT be done this way.** Savchuk 126, Ravenhill 117,
Poonen 50, Conlon 6, Deere 1, Brown 1 — all pre-`617341c`, so a fresh fetch
does NOT match what is stored and the script correctly refuses to write.
Heavy overlap with, not identical to, the parked 318 caption-duplication set.
Re-ingesting fixes both — and costs real money (non-`owned`, propositions
regenerate). Alex's call.

**Fixed: triage could create duplicate documents (commit `9224650`).**
`process_sheet()` built its dedup set once from the sheet, so a URL listed
twice in the same playlist appended two rows — and `documents.url` has no
unique constraint, so that becomes two documents with nothing to catch it.
"Sermon Archive" lists three videos twice. Corpus-wide duplicates were 0
before this run, so the defect had never fired.

**New Wine A2 — unchanged, still NOT ingestion-ready, still deliberately held
by Alex with no next step selected.** Untouched this session. Three gates and
the open resume options:
`docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md`. **Do not
spend live-call budget there without a fresh named ceiling** — the $3
approved 2026-08-29 is spent and does not carry forward.

**Quote rail: still off (`QUOTE_SELECTION_ENABLED=false`) — and a standing
risk became real this session.** Settled #19's residual risk was recorded as
"prospective, not retrospective"; that is now false and CLAUDE.md is
corrected in place. CLF's 56 sermons are genuinely auto-transcribed audio
under `sermon_transcript`, and a mistranscription is confirmed in the corpus
("ceasing" stored as "seizing"). Nothing gates on transcript status. No live
exposure only because the flag is off. **Before it is flipped back on, CLF
material needs either exclusion from quoting or an audio-confirmation step.**

---

## Findings surfaced, not yet acted on

- **318 historical YouTube documents carry residual caption duplication**
  (Ravenhill 117, Savchuk 126, Poonen 50, Kolenda 11, Deere 6, Conlon 6).
  Content is COMPLETE — a milder defect than CLF's. Re-ingesting regenerates
  propositions, so it needs its own cost estimate first. `docs/roadmap.md`
  Parked; deferred by Alex 2026-08-29. Heavily overlaps the 301 missing local
  files above — decide both together; one re-ingest fixes both.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text — the same class of LLM over-reach removed from the transcript path.
  The 7 sermons added 2026-08-29 audited clean (111/111), so the rate stands
  at 2 of 625 checked; extended, not re-measured.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Live account-deletion verification** — genuinely blocked, needs Alex to
  create a real disposable test account first (Session Routing hard rule).
- **Analytics production smoke sequence** — deferred, Alex's explicit
  decision, not run.
- Carried, not re-checked: `scripts/test_metering.py` writes live to
  production despite its `test_*.py` name (self-cleans); staging source still
  reads `"Vlad Savchuk (web staging)"`; Bonnke URL suspect;
  `rhemata_readonly_analysis` has no grant on PII/user tables.

---

## Next single item

**None selected.** Three standing candidates, none started, no preference
recorded by Alex:

- **The 15 held CLF recordings** (above) — smallest and most concrete.
- **New Wine A2** — held; needs a fresh named live-call ceiling before any
  paid run.
- **Quote accuracy/relevance repair** — the Scheduled gate blocking any
  attended quote-rail re-enable (`docs/roadmap.md`).
