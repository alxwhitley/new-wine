# New Wine — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers — B7 is DONE
and live** (migration 095 applied and independently verified, four Railway
services deployed at `6e0bb4a`). **The Rhemata → New Wine rename is EXECUTED in
the codebase** (branch `rename/newwine-full-sweep`, `a6f1575`, NOT pushed) and
migration 096 is applied — see the rename block for what deliberately stays on
the old name. A CORS gap that broke every API call from `newwine.app` was fixed
the same session. Earlier across 2026-08-30/31: held 15 CLF recordings out
permanently, ingested 7 of 10 misclassified `unknown` rows (CLF YouTube
56 → 63), cleaned CLF citable authors 16 → 12, fixed two ingest defects
(`5c94b3c`, `9224650`), first off-machine `sources/` backup, and guarded the
production-writing metering script (`scripts/verify_metering_live.py`).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**CLF Church — 63 YouTube documents (live, 2026-08-31), 0 duplicate URLs
corpus-wide.** Plus 15 pre-existing non-YouTube CLF docs, so a bare `count(*)`
reads 78 — filter on `url ILIKE '%youtu%'` before comparing YouTube figures.
Zero propositions throughout: `owned` sources skip the license gate. **Fully
triaged, nothing undecided:** 15 `held_permanent`, 7 ingested, 3
`held_speaker`, 1 `unavailable`; ingest gate matches 0 rows. Traps: CLAUDE.md's
YouTube landmine.

**The 15 held permanently (Alex, 2026-08-30)** are held on content shape and
pastoral-privacy exposure, **not runtime** — do not reopen as a length
question, and no trimming step may be built to salvage them. CLAUDE.md +
`docs/audits/2026-08/clf_held_recordings_review_2026-08-30.md`. **The 3 held on
speaker grounds:** Jeremy Porras (not CLF), Angel Woodard, Tiffany Cogdell.

**CLF answers name the individual preacher, not the church** — names cleaned
2026-08-31 (16 → 12 citable). `producer.py` builds `permitted_names` from
`documents.author`. **Still open:** guest preachers who spoke once at CLF are
named citable voices without their knowledge — ranked failure mode #2, live.

**Search analytics VERIFIED in production end to end, and B7 DONE and live.**
Analytics can no longer cost a user their answer; both privacy protections
preserved exactly. A 5s budget bounds the path; a degraded outcome stamps
`answer_jobs.analytics_outcome` (read via `scripts/analytics_health_report.py`).
**Not claimed:** the marker has never fired, nothing having degraded since.
Five analytics residuals unverified. Detail: PLAN.md B7 +
`docs/audits/2026-08/analytics_{production_smoke,answer_coupling}_2026-08-31.md`.

**Rename to New Wine — EXECUTED in the codebase, commit `a6f1575` on branch
`rename/newwine-full-sweep` (local, NOT pushed, NOT deployed).** Two passes:
user-facing copy, then identifiers/directories/config. `newwine.app` is live
(Cloudflare → Vercel), apex and `www`. The collision with the New Wine
*magazine* source is **accepted** by Alex — do not re-raise.

**The inventory that scoped this searched "rhemata" only** and so missed two
further live names, both now renamed and both recorded in Settled #25:
**UpperWord** branded the marketing homepage from `8795384` (2026-08-13) —
wordmark, nav, hero, CTA, the first thing any `newwine.app` visitor saw; and
**Manna** was genuinely built and shipped (`df27425`/`d3f7dbf`/`6e9ff7a`), not
"never implemented" as Settled #25 claimed. Future sweeps must search every
legacy name.

Done: component directory, Manna hero files/CSS vars/ARIA id, admin route,
5 localStorage keys (guest sessions logged out, approved), beta code
(`rhema` → **`newwine`**, client-side only, visible in the bundle), Chrome
extension incl. DOM ids, script/CLI/docstring text, governing docs.
**Migration 096 applied and verified live:** role → `newwine_readonly_analysis`,
14 RLS policies and 21 grants followed by OID, SCRAM password preserved,
`.env.readonly-analysis` username updated, connection re-proved read-only
(77 sources readable, writes refused). POSITIONING.md's "A Note on the Name"
(Acts 2:13 / Luke 5:37-38) and the `/home` tagline (`οἶνον νέον εἰς ἀσκοὺς
καινοὺς — Luke 5:38`) both **approved by Alex 2026-08-31**.

**Deliberately still on the old name:** applied migrations (rewriting them
would make the repo claim something was applied that never was); this file's
filename; the DB source row below and the `COLLECTION_SOURCE_HINTS` regex +
`common_religious_vocab.json` provenance that name it;
`sources/magazine/rhemata_tracker.xlsx`; Railway/Vercel/`rhemata.app`; the
biblical word "manna" in corpus data; 5 orphaned hero PNGs, zero references.

**Fixed en route, both broken before this work:** `.codex/hooks.json` pointed
all four hooks at the dead `/Users/alexwhitley/rhemata` — including
`guard_pretooluse.py`, so the governed-file guard was silently not firing —
and the admin panel handed out corpus commands rooted at the same dead path.

**CORS fixed 2026-08-31 — Railway config, so nothing in git shows it.**
`ALLOWED_ORIGINS` was `rhemata.app` alone while `newwine.app` was already
serving, so every browser API call from it failed. Now all three origins
(`www` is a distinct origin and needs its own). Foreign origins still 400.

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
  decision, not two** — heavy overlap, Savchuk/Ravenhill/Poonen-dominated. The
  301 are pre-`617341c` so a fresh fetch won't match; the 318 carry duplication
  but COMPLETE content. One re-ingest fixes both, costs real money, needs a
  cost estimate first. `docs/roadmap.md` Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — the GitHub remote is PUBLIC and
  `/sources/` is gitignored; committing it would publish the magazine PDFs,
  Precept Austin, Derek Prince scrapes and living ministers' transcripts,
  inverting the license gate, safe_mode, hidden staging and the PA lockout in
  one irreversible move. **The same rule keeps the 60 untracked
  `new_wine_issue_02_1973_review_*` dirs out of git** — deliberately untracked,
  and excluded by hand from commit `a6f1575`. Backup: iCloud Drive copy
  2026-08-30 (1,150 files, 496 MB, verified); sync, not versioned.
- **The house source row is still named "Rhemata"** —
  `bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf`, `owned`/`shown`, slug `rhemata`,
  plus one `source_aliases` row (`rhemata`/`Rhemata`). It is the publisher
  container the 8 position papers + "The Gift of Prophecy" were ingested
  under: 9 documents, 70 chunks, **0 citable** (all `silent_context`,
  `author=None`), so it never appears in an answer citation — but it is shown
  and can surface wherever sources are enumerated. Verified 2026-08-31 that no
  live code reads `sources.slug` or matches the literal name, so a rename is
  display-only. Renaming needs `sources.name`, `sources.slug`, and both alias
  columns moved together (Invariant 6: `alias_key` must be lowercase/stripped/
  collapsed — `new wine`). `COLLECTION_SOURCE_HINTS` and
  `common_religious_vocab.json` name this row and follow it, not the product.
  Attended DB write, not done.
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
  required, import side-effect-free, out of `test_*.py`. `test_teacher_card.py`
  shares the shape but only `.select()`s — **Alex: leave it, accepted.**
- Carried, not re-checked: staging source still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `newwine_readonly_analysis` still has no
  grant on PII/user tables — **deliberately deferred and untouched; neither
  the smoke nor B7 needed it.**

---

## Next single item

**Privacy policy + terms of service** — Alex named these 2026-08-31. Drafting
from zero (neither route exists). Blocked on him: legal entity/jurisdiction, a
contact address for data and rights-holder requests, and how the already-live
consent copy folds in. **Needs a Blocker/Scheduled classification first.**

Rename: code done (`a6f1575`, unpushed) — remaining is **push + deploy**, the
DB source row above, and Railway/Vercel/domain identifiers. Also open, none
started: **guest-speaker attribution** (live product question the 2026-08-31 cleanup did
not answer); **the 301 / 318 re-ingest** (needs a named cost estimate); **New
Wine A2** (needs a fresh live-call ceiling); **quote accuracy/relevance
repair** (the Scheduled gate on any quote-rail re-enable, `docs/roadmap.md`).
