# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has one active blocker: B7, the
fail-closed analytics → answer coupling — code complete, still OPEN.** The
decoupling and the timeout are built and proven; the missing-data marker is
built but **inert until migration 095 is applied**, and none of it is
deployed. Also this session (attended): pushed five commits to `origin/main`,
guarded then renamed the production-writing metering script
(`scripts/verify_metering_live.py`). Earlier across
2026-08-30/31: ruled the 15 held CLF recordings out permanently, cleared and
ingested 7 of the 10 misclassified `unknown` rows (CLF YouTube 56 → 63),
cleaned CLF's citable author names 16 → 12, fixed two ingest defects
(`5c94b3c`, `9224650`), and gave `sources/` its first off-machine backup. The
CLF tab is fully triaged with nothing undecided.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church — 63 YouTube documents (live, 2026-08-31), 0 duplicate URLs
corpus-wide.** Plus 15 pre-existing non-YouTube CLF docs, so a bare `count(*)`
on the source reads 78 — filter on `url ILIKE '%youtu%'` before comparing
against any YouTube figure. Zero propositions throughout: `owned` sources skip
the license gate. Every CLF document has a local file. **The CLF tab is fully
triaged — nothing undecided:** 15 `held_permanent`, 7 ingested and
source-verified, 3 `held_speaker`, 1 `unavailable`; the ingest gate matches 0
rows. Ingest/verification traps live in CLAUDE.md's YouTube landmine.

**The 15 held permanently (Alex, 2026-08-30)** are held on content shape and
pastoral-privacy exposure, **not runtime** — do not reopen as a length
question, and no trimming step may be built to salvage them. Reasoning in
CLAUDE.md, evidence in
`docs/audits/2026-08/clf_held_recordings_review_2026-08-30.md`. **The 3 held
on speaker grounds (Alex, 2026-08-31):** Jeremy Porras (not CLF), Angel
Woodard, Tiffany Cogdell (unresolved against `Tiffany Davis`).

**CLF answers name the individual preacher, not the church — names cleaned
2026-08-31 (7 attended DB writes, 16 → 12 citable, no artifacts left).**
`producer.py` builds `permitted_names` from `documents.author`, so guest
speakers are citable authorities alongside Derek Prince. **Still open:** guest
preachers who spoke once at CLF remain named citable voices without their
knowledge — ranked failure mode #2, live not closed.

**Search analytics: VERIFIED working in production, end to end (2026-08-31,
attended live smoke).** Phase A found the pipeline had never had an
*opportunity* to run rather than being broken; two real searches then proved
every stage by fresh read-only query. Both cron services run on schedule
(`*/5 * * * *` finalizer, `0 6 * * *` retention). The smoke rows were
deliberately **kept** — real searches, and the only evidence it works.
Evidence and five still-unverified residuals:
`docs/audits/2026-08/analytics_production_smoke_2026-08-31.md`.

**Blocker B7 — analytics no longer costs a user their answer (code
complete, NOT closed).** Alex's rule: when analytics cannot be reached or
consent cannot be determined, do not record, answer anyway. Both privacy
protections are preserved exactly — unknown consent never resolves to
"consented," and nothing is written under a key `withdraw()` could not find;
only the consequence of a refusal changed. A 5s budget now bounds the path
(no timeout existed at all before). A degraded outcome stamps
`answer_jobs.analytics_outcome`, so "analytics was down" stops being
indistinguishable from "nobody searched" — read it with
`scripts/analytics_health_report.py`. **Two attended steps remain and B7
stays open until both are done: apply migration 095, then deploy.** Deploy
order is safe either way — without the column the marker write is caught and
degrades to a log line. 50 mutation-verified checks; PLAN.md B7 has the
detail, `docs/audits/2026-08/analytics_answer_coupling_2026-08-31.md` the
diagnosis.

**New Wine A2 — unchanged, still NOT ingestion-ready, still held by Alex, no
next step selected.** Gates and resume options:
`docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md`. **No
live-call budget there without a fresh named ceiling** — the $3 approved
2026-08-29 is spent and does not carry forward.

**Quote rail: still off (`QUOTE_SELECTION_ENABLED=false`) — and a standing
risk became real.** Settled #19's "prospective, not retrospective" framing is
now false; CLAUDE.md is corrected in place. CLF's 63 sermons are
auto-transcribed audio under `sermon_transcript` and a mistranscription is
confirmed present. Nothing gates on transcript status; no exposure only
because the flag is off. **Before it flips back on, CLF needs quoting
exclusion or an audio-confirmation step.**

---

## Findings surfaced, not yet acted on

- **The 301 missing local files and the 318 caption-duplication set are one
  decision, not two** — heavy overlap, both dominated by
  Savchuk/Ravenhill/Poonen. The 301 are pre-`617341c`, so a fresh fetch does
  not match what is stored and the backfill correctly refuses to write; the
  318 carry residual duplication but COMPLETE content. One re-ingest fixes
  both, costs real money, needs a named cost estimate first. `docs/roadmap.md`
  Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — `github.com/alxwhitley/rhemata`
  is PUBLIC and `/sources/` is gitignored; committing it would publish the New
  Wine PDFs, Precept Austin, Derek Prince scrapes, and living ministers'
  transcripts, inverting the license gate, safe_mode, hidden staging, and the
  PA lockout in one irreversible move. **Backup gap largely closed 2026-08-30**
  — copied to iCloud Drive → `Rhemata Backup` (1,150 files, 496 MB, verified);
  it is sync, not versioned, so it guards against machine loss, not bad edits.
- **11 ingested CLF documents contain an offering appeal**, one an usher
  direction, one a dismissal — a milder form of the whole-service problem the
  15 were held for. Auditing those 11 for named-congregant content is open.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text. The 7 sermons added 2026-08-29 audited clean, so the rate stands at
  2 of 625 — extended, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- **Production-writing script guards (2026-08-31, Alex approved).**
  `scripts/verify_metering_live.py` (was `test_metering.py`) is guarded and
  renamed: `--apply` required, import side-effect-free, out of the `test_*.py`
  namespace. All three stand together; do not undo one because the others seem
  to cover it. `scripts/test_teacher_card.py` shares the shape but only
  `.select()`s — **Alex's decision: leave it alone, accepted not pending.** No
  other `scripts/test_*.py` has it.
- Carried, not re-checked: staging source still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` still has no
  grant on PII/user tables — **deliberately deferred and untouched; neither
  the smoke nor B7 needed it.**

---

## Next single item

**Close B7 — two attended steps, both Alex's.** (1) `python3.12
scripts/apply_migration_095.py --apply`, dry-run verified against the live
database (0 columns added, nothing written). (2) Deploy. Until then the
marker is inert and a degraded outcome leaves only a log line. The key-rotation
exposure that previously gated this is closed — see CLAUDE.md's landmine; what
remains there is a data risk, not an outage.

Not started, behind B7:

- **Guest-speaker attribution** — the live product question the 2026-08-31
  cleanup deliberately did not answer (Current state, above). Cheap to scope,
  no writes.
- **The 301 / 318 re-ingest** — needs a named cost estimate before Alex can
  rule (Findings, above).
- **New Wine A2** — needs a fresh named live-call ceiling before any paid run.
- **Quote accuracy/relevance repair** — the Scheduled gate blocking any
  attended quote-rail re-enable (`docs/roadmap.md`).
