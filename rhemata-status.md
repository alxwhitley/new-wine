# New Wine — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers — B7 is DONE
and live** (migration 095 applied and independently verified). **The Rhemata →
New Wine rename is SHIPPED, pushed, and fully DEPLOYED** — `main` is merged and
pushed, and all four Railway services now run `026039cb`; migration 096 is
applied — see the rename block for what deliberately stays on the old name. A
CORS gap that broke every API call from `newwine.app` was fixed the same
session. Earlier across 2026-08-30/31: held 15 CLF recordings out
permanently, ingested 7 of 10 misclassified `unknown` rows (CLF YouTube
56 → 63), cleaned CLF citable authors 16 → 12, fixed two ingest defects
(`5c94b3c`, `9224650`), first off-machine `sources/` backup, and guarded the
production-writing metering script (`scripts/verify_metering_live.py`).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Rename to New Wine: SHIPPED AND DEPLOYED.** `main` = `026039cb`; the rename
itself is `abeafd7` (merge of `rename/newwine-full-sweep`; `a6f1575` sweep +
`468cd7e` role cutover). **Frontend live** — `newwine.app` serves the New Wine
title. **Backend live** — `/` returns `{"message": "New Wine API"}`. Revert the
rename with `git revert -m 1 abeafd7`.

**The backend deploy gap is CLOSED (2026-08-31, attended) — and the root cause
was narrower than this file previously recorded.** It was never the project's
GitHub integration. Three of the four services (`answer-worker`,
`search-analytics-finalizer`, `search-analytics-retention`) had already followed
the repo rename to `alxwhitley/new-wine` on their own and were deploying
normally. **Only `rhemata` was still pinned to the dead `alxwhitley/rhemata`
source**, so it alone stopped receiving build triggers — which also means
production had been split-brain since the rename: the worker ran post-rename
code while the API served pre-rename code. Last pre-fix deployed commit was
`347d37c`, not `6e0bb4a`.

Fixed with `railway service source connect --repo alxwhitley/new-wine --branch
main --service rhemata`, which auto-triggered a build — no separate deploy call
needed. **Build settings were captured before the change and verified intact
after**, per the Railpack-drift landmine: `rootDirectory=/backend`,
`configFile=/backend/railway.toml`, `builder=NIXPACKS`,
`nixpacksConfigPath=/backend/nixpacks.toml` — all unchanged, no drift. All four
services now report `SUCCESS` on `026039cb`.

**Post-deploy production proof, not inference.** A guest submission through the
live endpoint returned `200 {"reason":"created"}` and completed
`outcome=answered` in 46.4s: 3,106-char answer, **15 citations** carrying real
chunk IDs, **4 verified references** (Matthew 6:16, Mark 2:20, Matthew 4:4, plus
teacher `Vlad Savchuk` grounded to `source_id 74ed5fa1-…`), zero attribution
retry, and **`quote_ids: []`** confirming Settled #30's rail-off posture holds
in production. `evidence_version=corpus_a1a94fa0d95de5fa`. CORS from
`newwine.app` re-verified 200 after the deploy. Re-GETting the same `job_id`
returned the persisted answer without regenerating, so reconnectable delivery is
proven too. **One trap for whoever writes the next smoke:** `/async-chat/result`
is SSE and its JSON payload spans multiple `data:` lines — parse by event
(accumulate to the blank line), not per line, or you will read an answer with
zero citations and think the guard failed.

Local side effect, still true: the Railway CLI is **linked** to
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

The backend deploy is DONE and verified, so the next item is **privacy policy +
terms of service** (Alex named these 2026-08-31; drafting from zero, blocked on
him for legal entity/jurisdiction, a contact address, and how the live consent
copy folds in; needs a Blocker/Scheduled classification first).

Highest-ranked live product risk if that stays blocked: **CLF guest-speaker
attribution** — guest preachers who spoke once at CLF are named citable voices
without their knowledge (ranked failure mode #2, live), on auto-transcribed
audio with a confirmed mistranscription. Repo-only triage of the 12 citable CLF
authors can start without Alex; any silencing is an attended DB write.

Also open, none started: the **DB source row** rename and the remaining
Railway/Vercel/domain/repo identifiers; **the 301 / 318 re-ingest** (needs a
cost estimate); **New Wine A2** (needs a fresh ceiling); **quote
accuracy/relevance repair** (`docs/roadmap.md`).
