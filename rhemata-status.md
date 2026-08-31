# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers — B7 is DONE
and live** (migration 095 applied and independently verified, all four Railway
services deployed at `6e0bb4a`). **The product is renamed New Wine and
`newwine.app` is live**; a CORS gap that broke every API call from it was found
and fixed the same session. Also (attended): guarded then renamed the
production-writing metering script (`scripts/verify_metering_live.py`).
Earlier across
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
question, and no trimming step may be built to salvage them. CLAUDE.md +
`docs/audits/2026-08/clf_held_recordings_review_2026-08-30.md`. **The 3 held on
speaker grounds:** Jeremy Porras (not CLF), Angel Woodard, Tiffany Cogdell.

**CLF answers name the individual preacher, not the church — names cleaned
2026-08-31 (7 attended DB writes, 16 → 12 citable, no artifacts left).**
`producer.py` builds `permitted_names` from `documents.author`, so guest
speakers are citable authorities alongside Derek Prince. **Still open:** guest
preachers who spoke once at CLF remain named citable voices without their
knowledge — ranked failure mode #2, live not closed.

**Search analytics: VERIFIED working in production, end to end (2026-08-31).**
Phase A found the pipeline had never had an *opportunity* to run rather than
being broken; two real searches then proved every stage by fresh read-only
query. Both cron services run on schedule. Smoke rows deliberately **kept**.
Evidence and five still-unverified residuals:
`docs/audits/2026-08/analytics_production_smoke_2026-08-31.md`.

**B7 — DONE and live (2026-08-31).** Analytics can no longer cost a user
their answer; both privacy protections are preserved exactly (unknown consent
never resolves to "consented"; nothing is written under a key `withdraw()`
could not find). A 5s budget bounds the path, and a degraded outcome stamps
`answer_jobs.analytics_outcome` — read it with
`scripts/analytics_health_report.py`. **Not claimed:** the marker has never
fired in production, because nothing has degraded since it went live. PLAN.md
B7 and `docs/audits/2026-08/analytics_answer_coupling_2026-08-31.md` hold the
detail.

**Rename to New Wine — decided, barely started.** `newwine.app` is live
(Cloudflare → Vercel), apex and `www`. Settled #25 corrected: it recorded
"Manna", never implemented. The collision with the New Wine *magazine* source
is **accepted** by Alex — do not re-raise. **Renamed so far: nothing** — the
app still says Rhemata in its title, UI, system prompt, and consent copy. 972
hits across 219 files, categorized, three traps flagged:
`docs/audits/2026-08/rename_inventory_2026-08-31.md`.

**CORS fixed 2026-08-31 — Railway config, so nothing in git shows it.**
`ALLOWED_ORIGINS` was `https://rhemata.app` alone while `newwine.app` was
already serving: the page loaded and **every browser API call from it failed**.
Now all three origins (`www` needs its own — distinct origin; `rhemata.app`
kept for the transition). Verified live, including that a foreign origin still
400s. Rollback is one `railway variable set`.

**No privacy policy and no terms of service exist** (route inventory), flagged
by Alex 2026-08-31. **Unclassified** — needs his Blocker/Scheduled call. The
live `consent.py` `POLICY_COPY` is already binding and duplicated in
`consent-gate.tsx`; the two must move together.

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
  decision, not two** — heavy overlap, both Savchuk/Ravenhill/Poonen-dominated.
  The 301 are pre-`617341c` so a fresh fetch will not match and the backfill
  correctly refuses; the 318 carry duplication but COMPLETE content. One
  re-ingest fixes both, costs real money, needs a cost estimate first.
  `docs/roadmap.md` Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — the GitHub repo is PUBLIC and
  `/sources/` is gitignored; committing it would publish the New Wine PDFs,
  Precept Austin, Derek Prince scrapes, and living ministers' transcripts,
  inverting the license gate, safe_mode, hidden staging, and the PA lockout in
  one irreversible move. **Backup gap largely closed 2026-08-30** — copied to
  iCloud Drive (1,150 files, 496 MB, verified); sync, not versioned, so it
  guards against machine loss, not bad edits.
- **11 ingested CLF documents contain an offering appeal**, one an usher
  direction, one a dismissal. Auditing those 11 for named-congregant content
  is open.
- **`bible_refs.py` hallucinated 2 of 514 references (~0.4%)** on real sermon
  text. The 7 sermons added 2026-08-29 audited clean, so the rate stands at
  2 of 625 — extended, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- **Production-writing script guards (2026-08-31, Alex approved).**
  `scripts/verify_metering_live.py` (was `test_metering.py`): `--apply`
  required, import side-effect-free, out of the `test_*.py` namespace. All
  three stand together. `scripts/test_teacher_card.py` shares the shape but
  only `.select()`s — **Alex's decision: leave it alone, accepted not
  pending.**
- Carried, not re-checked: staging source still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` still has no
  grant on PII/user tables — **deliberately deferred and untouched; neither
  the smoke nor B7 needed it.**

---

## Next single item

**Privacy policy + terms of service** — Alex named these 2026-08-31. Drafting
from zero (neither route exists). Blocked on him: legal entity/jurisdiction, a
contact address for data and rights-holder requests, and how the already-live
consent copy folds in. **Needs a Blocker/Scheduled classification first.**

Also open, none started: **rename execution** (scoped, nothing renamed yet);
**guest-speaker attribution** (live product question the 2026-08-31 cleanup did
not answer); **the 301 / 318 re-ingest** (needs a named cost estimate); **New
Wine A2** (needs a fresh live-call ceiling); **quote accuracy/relevance
repair** (the Scheduled gate on any quote-rail re-enable, `docs/roadmap.md`).
