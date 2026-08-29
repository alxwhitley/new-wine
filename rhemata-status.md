# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** This session
ingested a second CLF playlist (7 sermons, verified verbatim against source),
held 15 of its entries back as out-of-shape for the corpus, and fixed a
duplicate-document defect in triage. Committed and pushed through `9224650`.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church "Sermon Archive" playlist — 7 ingested and source-verified; 25
deliberately held.** Second playlist under the same one-channel reversal
(CLAUDE.md Landmines). The prior session's 49 from "Sermons" are unchanged.
Live count 2026-08-29: **56 CLF YouTube documents**, 0 duplicate YouTube URLs
corpus-wide.

1. **Triage.** `youtube_triage.py --sheet "CLF Church" --add <playlist>
   --min-duration 300`. 43 playlist entries → 40 unique → 32 net-new rows
   (7 already ingested from "Sermons", 0 already in the DB, 0 blocklisted).
   **Both stages must be `--sheet`-scoped** — a bare `run_queue_ingest.py`
   would have ingested 731 rows across three channels outside the reversal.
2. **Ingested 7** (`youtube_ingest.py --sheet "CLF Church"`): 7 done, 0
   failed, 0 needs_source, all via captions with no Whisper fallback. 189
   chunks. Zero propositions (`owned` license), as expected.
3. **Verified verbatim against source.** Every chunk of all 7 re-checked
   against freshly-fetched captions: **7/7 faithful**, the only difference
   being chunk 0's metadata header. 116–195 wpm against real durations — no
   truncation signature. Note for future verifications: chunks overlap
   (`chunk_text(..., chunk_target=550, overlap=80)`), so concatenating them
   inflates word counts ~17% and cannot be compared to source directly —
   check each chunk as a substring instead.
4. **Scripture audit: 111 references, 111 genuine, 0 fabricated.** The one
   initial flag (`1 Thessalonians 5:17`) resolved as a caption defect, not
   invention — see the quote-rail item below.

**15 long recordings held at `ingest=FALSE`, pending Alex.** They run 92–194
min against a 65-min median for the existing corpus. Sampling the captions
showed they carry the whole service — band sound-check, ushering, welcome,
opening prayer at the front; offering appeal and dismissal at the back —
which would be stored as `sermon_transcript` under a named minister and
become retrievable teaching material. Alex's read was that the excess is
altar-call-after-the-message; the audio contradicts that (it is at both
ends), and that conflict was reported, not resolved unilaterally. **There is
no trimming step in this pipeline and none should be built casually** — a
model deciding where a message ends is the same mechanism that discarded
60–75% of every sermon before `617341c`. One of the 15, *Don't Underestimate
the Power of Obedience* (`qFfoGi7Vexs`), ends on material that does not read
like a CLF service at all (personal greetings, "the shows", a Christmas
gathering) — likely a bad upload; check before ingesting it under any policy.

**Also held:** 10 rows Groq classified `unknown` (several are plainly
sermons, including one titled "Sunday Morning Service") and 1 row still
`needs_source` from the prior session ("Freedom from Guilt, Shame &
Rejection | Scott Woodard") — alias never resolved, never ingested.

**Fixed: triage could create duplicate documents (commit `9224650`).**
`process_sheet()` built its dedup set once from the sheet, so a URL listed
twice in the same playlist appended two rows — and `documents.url` has no
unique constraint, so that becomes two documents with nothing to catch it.
"Sermon Archive" lists three videos twice. Corpus-wide duplicates were 0
before this run, so the defect had never fired.

**New Wine A2 — unchanged, still NOT ingestion-ready, still deliberately held
by Alex with no next step selected.** Nothing this session touched it. The
three gates (article review never legitimately passed for Issue 02-1973; Opus
not wired into `review_magazine_issue.py`; proposition extraction never
attempted) and the open resume options are in
`docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md` and the
prior status entry in git history. **Do not spend live-call budget there
without a fresh named ceiling** — the $3 approved 2026-08-29 is spent
($0.63 of it) and does not carry forward.

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
  Content is COMPLETE — the retired model preserved everything, it only left
  duplicate fragments behind. A different, milder defect than CLF's.
  Re-ingesting them regenerates propositions, so it needs its own cost
  estimate first. Classified in `docs/roadmap.md` Parked; deferred by Alex's
  explicit choice 2026-08-29.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text. Small, but the same class of LLM over-reach just removed from the
  transcript path — worth knowing before the next large ingestion run. The 7
  sermons added 2026-08-29 audited clean (111/111 genuine), so the rate
  remains 2 of 625 across everything checked; not re-measured, just extended.
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
