# New Wine — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-31. **PLAN.md has zero active blockers.** The Rhemata →
New Wine rename is shipped, deployed, and its broken auto-deploy repaired;
`main` = `f0b772d` and all four Railway services run it. An author-attribution
audit this session found 7 live citable defects (audit written, fix not
applied). Alex decided four things: guest-speaker attribution stays as-is,
privacy/ToS gets drafted before classification, `/corpus-inventory/export`
stays public (2026-08-17 ruling re-confirmed with full context), and read-only
diagnostics may use `backend/app/.env` SELECT-only.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Rename: SHIPPED, DEPLOYED, auto-deploy REPAIRED.** Frontend and backend both
live — `newwine.app` serves the New Wine title, `/` returns
`{"message": "New Wine API"}`. The rename commit is `abeafd7`; revert it all
with `git revert -m 1 abeafd7`.

**The deploy gap is closed and the cause was ONE service, not the GitHub
integration.** Three of four Railway services had followed the repo rename to
`alxwhitley/new-wine` on their own; only the backend stayed pinned to the dead
`alxwhitley/rhemata` source, so it alone stopped receiving triggers —
production ran split-brain (post-rename worker, pre-rename API) until it was
fixed. Repaired with `railway service source connect --repo alxwhitley/new-wine
--branch main`. Build settings verified intact after: `rootDirectory=/backend`,
`configFile=/backend/railway.toml`, `NIXPACKS`. **Auto-deploy is PROVEN, not
assumed:** push `f0b772d` at 19:37:01Z → deployment created 19:37:04Z → SUCCESS
19:38:37Z, matching the control service to the same second. The dashboard's
"GitHub Repo not found" on the branch link is a stale artifact — behavior is
proven; the UI is not authoritative here.

**CONSEQUENCE, new as of this session — every push to `main` now deploys
production.** All four services rebuild (`watchPatterns: []`, so even docs-only
commits redeploy). Until 2026-08-31 the backend was frozen and pushes were
harmless; that is no longer true. Treat backend pushes as attended gates.
Setting watch patterns would stop docs commits redeploying — not done.

**Two traps that cost real time this session.** (1) `/async-chat/result` is SSE
and its JSON payload spans multiple `data:` lines — parse by EVENT (accumulate
to the blank line), not per line, or the answer reads as zero-citation and
looks exactly like an attribution-guard failure. (2) Railway deployment meta
populates progressively; read mid-`BUILDING` it reports `rootDirectory` and
`configFile` as null, indistinguishable from real Railpack drift. Wait for a
terminal status before judging.

**Post-deploy production proof:** guest submission → `outcome=answered` in
46.4s, 3,106-char answer, 15 citations with real chunk IDs, 4 verified
references (teacher grounded to a real `source_id`), zero attribution retry,
`quote_ids: []` confirming Settled #30's rail-off posture holds live.

**Author attribution — 7 defects found and BOTH HALVES FIXED 2026-08-31.**
`docs/audits/2026-08/author_attribution_audit_2026-08-31.md`. Five title
fragments (`Day Abortion`, `Do This Instead`, `Watch Message`, `Your Porn
Battle Plan`, `This Is How You Should Fight Your Battles`) and two identity
splits (`Vlad`, `Pastor Vlad`) were **citable** under the Vlad Savchuk source,
so each was entering the permitted-name set the answer writer may attribute to.
Root cause: `_extract_speaker()` matches any run of Title-Case words after a
`|`/`-`/`—` (it split "Modern-Day Abortion" mid-phrase), and the `via` value
proving the string never matched an alias was computed then discarded. Fixed
forward in `scripts/youtube_ingest.py::_verified_speaker()` (`fe0718a`,
22-check test with a mutation proof), and the 7 rows repaired by attended write
(`scripts/archive/2026-08/fix_unverified_authors_2026-08-31.py`, `UPDATE 7`,
reconciled from a fresh connection). Citable author groups **55 → 48**.

Three non-problems recorded so nobody "fixes" them: comma-joined authors are
already all `silent_context`; `Jamieson, Fausset & Brown` is a genuine joint
work, not a defect; and Savchuk documents with `author = NULL` correctly fall
back to the source name — that is the HEALTHY state, and repairing them into
per-document strings would recreate this defect at scale.

**Guest-speaker attribution — DECIDED 2026-08-31: leave as-is.** Closed, not an
open finding. Do not re-raise it as a live risk.

**Privacy policy + ToS — DECIDED 2026-08-31: draft first, classify after.**
Still needs legal entity, jurisdiction, and a contact address from Alex.
`POLICY_COPY` in `consent.py` is binding and duplicated in `consent-gate.tsx`;
they must move together (proven byte-identical).

**`/corpus-inventory/export` stays public — 2026-08-17 ruling RE-CONFIRMED
2026-08-31, do not re-raise.** It serves 3,673 rows of author/title/URL with no
auth, deliberately bypassing the license/visibility gate, so an external AI
agent can dedup against the corpus before proposing ingest candidates
(CORPUS-INV-001). A 2026-08-31 review proposed gating it, then found the
missing auth was the decision, not an oversight — Alex re-confirmed public
access knowing that. `scripts/test_corpus_inventory_endpoint.py` Check 1
asserts unauthenticated access and is the guard. The standing limit is
unchanged: **never** extend it to chunk text, excerpts, or proposition
content — that is a policy change, not an implementation detail.

**Migration 096 applied and verified** — role is `newwine_readonly_analysis`,
14 RLS policies and 21 grants followed by OID, connection re-proved read-only.

**Still on the old name deliberately:** applied migrations; this file's own
filename; the DB source row plus the two code sites that name it;
`rhemata_tracker.xlsx`; the Vercel project; `rhemata.app` (currently returns
404 — redirect vs retire undecided); the public API hostname
`rhemata-production.up.railway.app` (changing it requires the frontend's API
base URL to move in lockstep); biblical "manna" and Greek "rhema" in corpus
data; 5 orphaned hero PNGs. The Railway service and the GitHub repo are both
renamed already.

**CLF Church — 63 YouTube documents, 0 duplicate URLs corpus-wide.** Plus 15
non-YouTube CLF docs, so a bare `count(*)` reads 78 — filter `url ILIKE
'%youtu%'`. Zero propositions (`owned` skips the license gate). Fully triaged:
15 `held_permanent` (content shape + pastoral privacy, **not runtime** — no
trimming step may be built to salvage them), 7 ingested, 3 `held_speaker`, 1
`unavailable`.

**Search analytics verified in production; B7 DONE and live.** Analytics can no
longer cost a user their answer; a degraded outcome stamps
`answer_jobs.analytics_outcome` (`scripts/analytics_health_report.py`). **Not
claimed:** the marker has never fired, nothing having degraded. Five analytics
residuals unverified.

**Quote rail still off (`QUOTE_SELECTION_ENABLED=false`).** CLF's 63 sermons
are auto-transcribed audio under `sermon_transcript` with a confirmed
mistranscription; nothing gates on transcript status. **Before the flag flips
back on, CLF needs quoting exclusion or an audio-confirmation step.**

**New Wine A2 — unchanged, NOT ingestion-ready, held by Alex.** No live-call
budget without a fresh named ceiling.

---

## Findings surfaced, not yet acted on

- **A served citation carried a dangling `chunk_id`** — the post-deploy smoke
  answer cited `0b9d1930-7103-4520-8e37-e382dc7b3227`, which matches zero of
  186,944 rows in `chunks`, while its document resolved normally. Either
  citation `chunk_id` does not correspond to `chunks.id` at all (a contract
  question) or a citation can point at unresolvable evidence (which would
  matter for the "inspect citations/evidence" beta journey). Needs one
  deliberate check of how `producer.py` populates the field. Unclassified.
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
  `new_wine_issue_02_1973_review_*` dirs out of git.** Backup: iCloud Drive
  copy 2026-08-30 (1,150 files, 496 MB, verified); sync, not versioned.
- **The house source row is still named "Rhemata"** —
  `bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf`, `owned`/`shown`, slug `rhemata`,
  plus one `source_aliases` row. It is the publisher container for the 8
  position papers + "The Gift of Prophecy": 9 documents, 70 chunks, **0
  citable**, so it never appears in a citation — but it is shown and can
  surface wherever sources are enumerated. No live code reads `sources.slug`
  or matches the literal name, so a rename is display-only. Needs
  `sources.name`, `sources.slug`, and both alias columns moved together
  (Invariant 6: `alias_key` → `new wine`). `COLLECTION_SOURCE_HINTS` and
  `common_religious_vocab.json` name this ROW and follow it, not the product.
  Attended DB write, not done.
- **11 ingested CLF documents contain an offering appeal**, one an usher
  direction, one a dismissal. Auditing those 11 for named-congregant content
  is open.
- **`bible_refs.py` hallucinated 2 of 625 references (~0.3%)** on real sermon
  text — extended by the 2026-08-29 clean audit, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- Carried, not re-checked: staging source still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `newwine_readonly_analysis` still has no
  grant on PII/user tables — deliberately deferred.

---

## Next single item

**Gate `/corpus-inventory/export` behind authentication** (Alex's call
2026-08-31). Backend change, so it ships as an attended production deploy.

Then, in order: root-cause the speaker parser that mints title-fragment
authors (repo-only); the attended DB write fixing the 7 citable rows, with
statements shown to Alex first; privacy/ToS drafts.

Also open, none started: the DB source row rename and remaining
Vercel/domain/hostname identifiers; the 301 / 318 re-ingest (needs a cost
estimate); New Wine A2 (needs a fresh ceiling); quote accuracy/relevance
repair (`docs/roadmap.md`).
