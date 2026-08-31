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

**Rename to New Wine: SHIPPED.** `main` = `abeafd7` (merge of
`rename/newwine-full-sweep`; `a6f1575` sweep + `468cd7e` role cutover).
**Frontend deployed and live** — `newwine.app` serves the New Wine title.
**Backend NOT yet deployed at close** — `/` still returned `{"message":
"Rhemata API"}`. Confirm with `curl -s https://rhemata-production.up.railway.app/`;
`New Wine API` means done. If it is still old after ~10 min, check the Railway
service's builder + `rootDirectory=/backend` before assuming a code problem
(documented Railpack-drift landmine). Until it lands, answers generate under
the old identity while the UI says New Wine. Revert all of it with
`git revert -m 1 abeafd7`.

**Root cause CONFIRMED — Railway never received a build trigger. This is not
a failed build; it is no build.** `railway deployment list` on service
`rhemata` shows the most recent deployment at **2026-08-31 12:36:09**, while
the merge to `main` landed at **14:22:19** — nothing was created after the
push. The Railpack-drift landmine is NOT the cause here and should not be
chased first.

Most likely trigger: the GitHub repo was renamed to `alxwhitley/new-wine`
during this session (found via a push redirect; the local git remote is
updated). Vercel survived it — `newwine.app` is serving the new build,
Luke 5:38 tagline live, "UpperWord" gone — so the rename did not break every
integration, but Railway's source link is the prime suspect. **The backend
will not deploy on its own; Railway's GitHub source needs reconnecting**,
then a deploy for `rhemata` and `answer-worker`. Deploying is an attended
gate, deliberately not done at close.

Local side effect of this diagnosis: the Railway CLI is now **linked** to
`dependable-enthusiasm` / `production` / service `rhemata` from this
directory, so a stray `railway up` here would deploy. `railway unlink` clears
it. The Railway service is also still named `rhemata`.

**On deploy, expected not accidental:** guests are logged out and lose saved
library filters (5 localStorage keys renamed); the beta code is now
**`newwine`** (was `rhema`; client-side only, visible in the bundle); answers
regenerate rather than reuse (prompt fingerprint `prompt_e732c25fb423` →
`prompt_be8bd19e469e`).

**Migration 096 applied and verified** — role is `newwine_readonly_analysis`,
14 RLS policies and 21 grants followed by OID, SCRAM password preserved,
`.env.readonly-analysis` username updated, connection re-proved read-only
(reads 77 sources, writes refused).

**Three legacy names existed, not one.** The rename inventory searched
"rhemata" only and so missed **UpperWord** (branded the marketing homepage
from `8795384`, 2026-08-13 — the first thing any `newwine.app` visitor saw)
and **Manna** (genuinely built and shipped 2026-08-10, contrary to Settled
#25's old claim). Both renamed; Settled #25 corrected.

**Still on the old name deliberately:** applied migrations; this file's own
filename (heading says New Wine, filename does not — undecided); the DB
source row below plus the two code sites that name it; `rhemata_tracker.xlsx`;
Railway service / Vercel project / `rhemata.app` / the GitHub repo itself;
biblical "manna" and Greek "rhema" in corpus data; 5 orphaned hero PNGs.

**Fixed en route, both broken beforehand:** `.codex/hooks.json` pointed all
four hooks at the dead `/Users/alexwhitley/rhemata` — including
`guard_pretooluse.py`, so the governed-file guard was silently not firing —
and the admin panel handed out corpus commands rooted at the same dead path.

**CLF Church — 63 YouTube documents, 0 duplicate URLs corpus-wide.** Plus 15
non-YouTube CLF docs, so a bare `count(*)` reads 78 — filter `url ILIKE
'%youtu%'`. Zero propositions (`owned` skips the license gate). Fully triaged:
15 `held_permanent` (content shape + pastoral privacy, **not runtime** — no
trimming step may be built to salvage them), 7 ingested, 3 `held_speaker`
(Jeremy Porras, Angel Woodard, Tiffany Cogdell), 1 `unavailable`. **Still
open:** guest preachers who spoke once at CLF are named citable voices without
their knowledge — ranked failure mode #2, live.

**Search analytics verified in production; B7 DONE and live.** Analytics can
no longer cost a user their answer. A degraded outcome stamps
`answer_jobs.analytics_outcome` (`scripts/analytics_health_report.py`). **Not
claimed:** the marker has never fired, nothing having degraded. Five analytics
residuals unverified. PLAN.md B7 + `docs/audits/2026-08/analytics_*_2026-08-31.md`.

**No privacy policy and no terms of service exist.** Flagged by Alex
2026-08-31, **unclassified** — needs a Blocker/Scheduled call. `POLICY_COPY`
in `consent.py` is binding and duplicated in `consent-gate.tsx`; they must
move together (proven byte-identical this session).

**Quote rail still off (`QUOTE_SELECTION_ENABLED=false`).** CLF's 63 sermons
are auto-transcribed audio under `sermon_transcript` with a confirmed
mistranscription; nothing gates on transcript status. **Before the flag flips
back on, CLF needs quoting exclusion or an audio-confirmation step.**

**New Wine A2 — unchanged, NOT ingestion-ready, held by Alex.** No live-call
budget without a fresh named ceiling.

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
- **`bible_refs.py` hallucinated 2 of 625 references (~0.3%)** on real sermon
  text — extended by the 2026-08-29 clean audit, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- **`scripts/verify_metering_live.py`** (was `test_metering.py`): `--apply`
  required, import side-effect-free, out of `test_*.py`. `test_teacher_card.py`
  shares the shape but only `.select()`s — **Alex: leave it, accepted.**
- Carried, not re-checked: staging source still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `newwine_readonly_analysis` still has no
  grant on PII/user tables — deliberately deferred.

---
---

## Next single item

**Confirm the backend deploy landed**, then **privacy policy + terms of
service** (Alex named these 2026-08-31; drafting from zero, blocked on him for
legal entity/jurisdiction, a contact address, and how the live consent copy
folds in; needs a Blocker/Scheduled classification first).

Also open, none started: the **DB source row** rename and the remaining
Railway/Vercel/domain/repo identifiers; **guest-speaker attribution**; **the
301 / 318 re-ingest** (needs a cost estimate); **New Wine A2** (needs a fresh
ceiling); **quote accuracy/relevance repair** (`docs/roadmap.md`).
