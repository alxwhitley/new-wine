# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to, never
durable truth — the durable records are the code, git history, PLAN.md,
docs/roadmap.md, docs/plan-archive.md, and CLAUDE.md. Counts are NOT recorded
here except as a dated snapshot from a specific live query; treat any count
seen elsewhere as unverified.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.** `main` =
`6e60486`, **ahead 1, NOT pushed**. This session was read-only analysis plus
one repo-only backend build. No database writes, no deploy.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines.

---

## Current state

**Prose-channel quotation guard built and committed, NOT deployed
(`6e60486`).** An audit of the five stored baseline answers found the answer
writer emits verbatim teacher quotations in ordinary prose and nothing checked
the WORDING — 7 quotations, **4 defective**: one fabricated outright under a
living minister's name, one crediting Wayne Grudem's words to the teacher who
was quoting him, one altering Derek Prince and stripping his hedge, one
truncating Kolenda's "the church that I pastor" to "the church".
`backend/app/services/prose_quotation_guard.py` is deterministic (no model —
Settled #4), wired as a third arm in `producer.py`'s existing
`_has_ungrounded()` so it inherits regenerate-once-then-refuse. 23 checks, 5
mutation proofs. On the five real answers: 3 flags, all true positives, zero
false positives. Audit:
`docs/audits/2026-08/scripture_and_quotation_fidelity_2026-08-31.md`.

**One design fact worth not rediscovering.** Punctuation normalization is
load-bearing, not cosmetic — Prince's genuine "'60s … '70s" is stored with
curly `‘` and written with straight `'`, so a raw substring check rejects an
ACCURATE quotation and the guard would have refused correct answers.

**Deliberately NOT covered by that guard**, asserted as tests so it cannot be
mistaken for coverage: nested quotation (Grudem-via-Kolenda passes, because
the words genuinely are in the retrieved chunk), and Scripture entirely.

**Scripture fidelity is unguarded and unchanged.**
`reference_verifier.verify_verse_mention()` is an EXISTENCE check only. All 14
verse references in the sample resolved and every attached claim was
defensible — but 5 were rendered as direct quotations and none matched the WEB
text `study.py` serves on click-through, and 2 Scripture quotations carried no
reference at all (Matt 26:68, 1 Cor 14:31), which puts them outside every
guard since the verifier only sees what the model DECLARES.

**A parallel codex session ran in THIS working tree** on biblical coverage —
`scripts/biblical_coverage_*` + its audit doc are uncommitted output **not
reviewed by this session**. It did not touch `producer.py`. Sharing one
worktree is why this session committed to `main` rather than branching.

**`scripts/sp1_answer_harness.py` does not exercise the real answer path.** It
reimplements generation and never imports `producer.py`, bypassing the
position-paper fence, stored-position evidence, the single-teacher lock and
the single-author attribution contract. Any before/after quality comparison
run through it measures a proxy — relevant to judging the depth work.

**Auth flow rebuilt and live (`df2d5f9`, `5473265`).** Do not revert: beta
access is per-device `localStorage` with trimmed, case-insensitive matching
(Alex accepted 2026-08-31), and `hooks/useAuthGate.ts` is the single owner of
auth-modal state — do not re-copy it into a page. Pre-existing, not ours: a
hydration mismatch from `next-themes`' `forcedTheme="dark"`.

**Every push to `main` deploys production.** All four Railway services rebuild
(`watchPatterns: []`, so even docs-only commits redeploy). Treat backend
pushes as attended gates — including this session's unpushed commit.

**Two traps.** `/async-chat/result` is SSE with JSON spanning multiple `data:`
lines — parse by EVENT, or an answer reads as zero-citation, exactly like an
attribution-guard failure. Railway deployment meta populates progressively;
mid-`BUILDING` `rootDirectory`/`configFile` read null.

**Decided, do not re-raise:** guest-speaker attribution stays as-is;
`/corpus-inventory/export` stays public — never extend it to chunk text,
excerpts, or propositions. Privacy/ToS DEFERRED pending legal entity,
jurisdiction, contact; `POLICY_COPY` in `consent.py` is duplicated in
`consent-gate.tsx` and they move together. Savchuk docs with `author = NULL`
correctly fall back to the source name (HEALTHY); `Jamieson, Fausset & Brown`
is a genuine joint work.

**Quote rail still off (`QUOTE_SELECTION_ENABLED=false`).** CLF's 63 sermons
are auto-transcribed audio under `sermon_transcript` with a confirmed
mistranscription and nothing gates on transcript status — **before the flag
flips back on, CLF needs quoting exclusion or audio confirmation.** 15 further
CLF recordings are `held_permanent` for content shape + pastoral privacy, not
runtime — no trimming step may be built to salvage them.

**Search analytics live; B7 done.** A degraded outcome stamps
`answer_jobs.analytics_outcome` (`scripts/analytics_health_report.py`), but
that marker has never fired. Five residuals unverified. **New Wine A2 is NOT
ingestion-ready** — held by Alex, no live-call budget without a fresh ceiling.

**Still on the old name deliberately:** applied migrations; this filename; the
DB source row + the two code sites naming it; `rhemata_tracker.xlsx`; the
Vercel project; `rhemata.app` (404 — redirect vs retire undecided); the API
hostname `rhemata-production.up.railway.app` (frontend API base URL must move
in lockstep); "manna"/"rhema" in corpus.

---

## Findings surfaced, not yet acted on

- **The prose-channel guard has never run on live traffic.** Its real
  false-positive rate is unmeasured, and the 400-char attribution window and
  surname matching are tuned from five answers. Deploying it alone (before or
  after the biblical-depth work) is the clean way to read that number.
- **Scripture claim fidelity and unreferenced Scripture quotation** — audit
  findings 2 and 3, both unguarded. Exposure grows as scripture density rises.
- **A served citation carried a dangling `chunk_id`** —
  `0b9d1930-7103-4520-8e37-e382dc7b3227` matched zero of 186,944 `chunks` rows
  while its document resolved normally. Needs one check of how `producer.py`
  populates it.
- **The 301 missing local files and the 318 caption-duplication set are one
  decision, not two** — heavy overlap. One re-ingest fixes both, costs real
  money, needs a cost estimate. Parked; deferred by Alex 2026-08-29.
- **`sources/` must never go in this repo** — the remote is PUBLIC. Committing
  it would publish magazine PDFs, Precept Austin, Prince scrapes and living
  ministers' transcripts, irreversibly inverting the license gate, safe_mode,
  hidden staging and the PA lockout. **Same rule keeps the 60 untracked
  `new_wine_issue_02_1973_review_*` dirs out of git.** Backup is an iCloud copy
  (2026-08-30) — sync, not versioned.
- **The house source row is still named "Rhemata"** —
  `bf6d9e28-1cfd-4431-975b-df2ca1b9cfdf`, `owned`/`shown`. 0 citable, so it
  never appears in a citation but shows wherever sources are enumerated.
  Rename needs `sources.name`, `sources.slug` and both alias columns moved
  together (Invariant 6: `alias_key` → `new wine`). Attended DB write.
- **11 ingested CLF documents contain an offering appeal**, one an usher
  direction, one a dismissal. Named-congregant audit still open.
- **`bible_refs.py` hallucinated 2 of 625 references (~0.3%)** on real sermon
  text — extended by the 2026-08-29 clean audit, not re-measured.
- **Live account-deletion verification** — blocked, needs a real disposable
  test account from Alex first (Session Routing hard rule).
- Carried, not re-checked: staging source reads `"Vlad Savchuk (web staging)"`;
  Bonnke URL suspect; `newwine_readonly_analysis` has no grant on PII/user
  tables (deliberate).

---

## Next single item

**None designated — Alex picks.** The one thing this session leaves in an
incomplete state is the unpushed commit: `main` is ahead 1 with a guard on the
live answer path that has never seen real traffic.

Open, unordered: push + deploy the quotation guard and measure its live
false-positive rate; Scripture fidelity (audit findings 2/3); reconcile with
the parallel biblical-depth work once its output is reviewed; the auth
follow-up passes (`audit`, `animate`, `polish`); the `next-themes` hydration
mismatch; the DB source row rename and remaining Vercel/domain/hostname
identifiers; the 301/318 re-ingest (cost estimate first); New Wine A2 (fresh
ceiling); quote accuracy/relevance repair; privacy/ToS drafts.
