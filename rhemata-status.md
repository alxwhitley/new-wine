# rhemata-status.md

**As of:** 2026-07-14 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

Today ran three sessions back to back: the Inline Study Panel shell (frontend), the lexicon slice-runner (ingest tooling), and a records-vs-database reconciliation (docs only). All three are committed; all commits through this file's own regeneration are about to be pushed. **Nothing corpus-side changed today — every write this session is either code, docs, or already-cleaned-up test data.**

- **No default next action is forced.** Everything below is independent and Alex's call: the Sermonindex volume run, the 2 broken PA docs, the 2 ambiguous reconciliation flags, the optional lexicon restamp, or picking up #10/CLAUDE.md/Study-Panel follow-ups. See "Next Session Should."
- **Boundary that holds across all three sessions today:** where this file states corpus/ingest status, it was verified against the live database or git log at write time, not carried forward from prior text. This file being accurate does **not** mean the corpus itself has been audited end-to-end — the ~3,800 documents with no partial-write-verification signal remain unaudited by any of today's work.

---

## Done today (verified against git log / DB just now, not carried forward)

**Study Panel shell + motion (frontend) — commit `161c4de`, status commit `fc2f273`, both PUSHED LIVE to `origin/main`.**
- Panel slides in over chat from the right (desktop side panel / mobile full-screen sheet), sidebar collapses in the same motion, real trigger (verse references detected in finished chat answers), pin system, honest empty states for ungated content. Confirmed via `git log`: `161c4de` and `fc2f273` are both in `origin/main`'s history (pushed earlier today).
- **Open gap, not closed by anything since:** shipped **without a kill switch / beta flag** — the panel is unconditionally live to any user who taps a detected verse reference (or hits the dev shortcut) in production right now. Also shipped **without the real SP1 pointer backend** — the trigger is a narrow client-side regex over already-rendered text (`lib/study-reference.ts`), not the hidden-pointer, fail-quiet-resolution system PLAN.md's SP1 describes. By PLAN.md's own numbering this build is shaped like **SP2 minus those two pieces**, not SP0 (the brief's original label).

**Lexicon slice-runner — commit `dd609fb`, status commit `5b49eaf`.**
- `scripts/ingest_lexicon_runner.py` built, driving the already-converted `ingest_lexicon.py` through `shared_ingest.ingest_document()` in checkpointed slices with retry→bisect→skip-and-log on a single bad entry. Proven end-to-end on a bounded real slice (initial load, resumability, forced-failure) — all three re-verified by direct DB recomputation, not self-report.
- **Key finding, re-confirmed fresh just now:** all four real STEPBible lexicon documents are still exactly as found — TBESG 11,034 / TBESH 10,258 / TFLSJ(0-5624) 5,709 / TFLSJ(extra) 5,324 chunks, all `ingest_completed_at IS NULL` (unstamped, from the pre-conversion script). **There is no backlog for the runner to run against these four files.** The runner is ready for future lexicon sources, not a queued job for today's four. A deliberate restamp-for-consistency of these four (via `on_existing="delete_and_reingest"`) remains an **open option, not a default next step** — it's a real, brief-outage-shaped write to live production docs that already serve correctly.
- Confirmed fresh: zero leftover test/throwaway documents from this build's proof runs (`RUNNER PROOF` titles) — cleanup was real, not just claimed.

**Records-vs-database reconciliation — commit `4addc06`.**
- Audited every "work remains" claim in `PLAN.md` and `rhemata-status.md` against direct DB/repo queries. **9 stale claims corrected, 2 flagged as ambiguous** (needs Alex, not a build). Headline: the propositions backlog was recorded as ~2,980 unlicensed docs pending — the real, actionable number (re-confirmed fresh just now) is **810** non-PA unlicensed docs; the old figure counted Precept Austin's 2,176 permanently-excluded docs as if they were backlog. Full detail lives in `PLAN.md`'s Ground Truth section and Roadmap #17, not restated here.
- `CLAUDE.md` untouched by design — its "two unconverted scripts" count (`ingest_helloao.py`, `ingest_commentaries.py`) was independently verified accurate via code inspection this session; that specific number needs no fix. Other stale notes in CLAUDE.md remain deferred to its own docs pass.

**Prior thread, already closed, unaffected by today:** the Sermonindex ingest-integrity remediation (all-or-nothing writer `6708060`, redo/reuse dispatcher + completeness stamp `1ec5226`, lexicon conversion `33e92b4`) — confirmed present in `git log` exactly where expected, nothing about them changed today.

---

## Still open (verified against DB/queue just now)

1. **The Sermonindex volume run has not happened.** Queue re-checked fresh: 741 total rows in the `Sermonindex` tab, **553 `triaged`** (ready for ingest, not yet run — "551" in earlier notes was an approximation, off by 2), 173 `done`, 15 `expanded`. The 173 `done` rows are confirmed real: 117 Leonard Ravenhill + 50 Zac Poonen + 6 Carter Conlon docs actually exist in the DB with matching counts. The 553 triaged rows are the real, unstarted volume run.
2. **2 genuinely-broken PA documents** ("Word Study: Fortunes," "Word Study: Innocent" — confirmed fresh, both still zero chunks) still need a REDO through the atomic-swap mechanism (`on_existing="delete_and_reingest"`). Not touched today — real cleanup, deliberately out of scope for a records-only session.
3. **2 ambiguous reconciliation flags, both need Alex, not a build:**
   - Magazine "27 of 27 pending articles contaminated" — the original signal can't be located against current state; closest match is 32 articles across 5 issues sitting in `sources/magazine/02_extracted/` awaiting approval. Needs Alex's memory of what "27 contaminated" originally referred to.
   - PA "survivability guard will rarely fire" — a claim about future behavior under real failure conditions; not something a database query can confirm or refute either way.
4. **Optional lexicon restamp** (see above) — Alex's call, not scheduled.
5. **CLAUDE.md's own docs pass remains deferred** — its unconverted-script count is fine (verified accurate this session); its other stale notes (folder renames, `jewish_perspectives` drop, etc.) are unrelated open items, not touched today.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list, plus the SP track added 2026-07-13 — see PLAN.md itself for full detail; this is a pointer, not a restatement)

- **#1–#14:** all DONE except #10 (`ingest_commentaries.py` conversion, still unstarted) and #14's folder-rename/`jewish_perspectives`-drop remainder.
- **#12's batch-scale companion (the slice-runner) is DONE** — but per above, there's no pending "full run" for the four existing lexicon files specifically.
- **#17 (propositions backfill):** target corrected today to 810 non-PA unlicensed docs (was wrongly recorded as 2,980) — not run, just correctly sized now.
- **SP track:** SP2-shaped shell is live in production (see above) without SP2's own named kill switch or SP1 underneath it. SP3 (tool rows) remains correctly hard-gated, untouched.

---

## Open Flags

**Carried forward, unchanged from before today (still real, none resolved by today's records-only work):**
1. Rule 10 freeze is a bare-substring match, not an invocation check — recurs for `ingest_helloao.py`, `ingest_commentaries.py` only.
2. Magazine queue "27 of 27 pending articles contaminated" — see "Still open" #3 above.
4. Database-number verification gap (independently verifying claimed reconciliation counts against the DB itself — nothing in the harness does this today).
5. `GOVERNED_FILES` gap (`guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`).
6. PLAN.md #5.5 closing line is stale. Needs Alex's explicit go-ahead on replacement wording.
7. PLAN.md #14 drift — folder renames and the `jewish_perspectives` drop still open.
10. CLAUDE.md's own "unconverted scripts" prose is stale in places (says four in its Directory Structure section) even though the true count (two) is confirmed accurate — CLAUDE.md's own docs pass, deferred, not this session's job.
12. PA's 398 "excerpt-less" documents — 396 just need `generate_excerpts.py` (not broken); 2 are the genuinely-broken docs in "Still open" #2 above.
13. PA "survivability guard will rarely fire" — see "Still open" #3 above.
16. No kill switch / beta flag exists for the Study Panel — see "Done today" above.
17. The Study Panel's verse-reference detector is a narrow client-side stand-in, not the real SP1 backend — see "Done today" above.
18. CLAUDE.md and SKILL.md are both stale on the quoting rule (found during SP1 diagnostic, 2026-07-14): both describe verbatim quoting permitted up to 50 words pending a verifier that doesn't exist, while the live system prompt bans reproducing any quote or exact wording in any mode, paraphrase-only always — code is stricter than the docs. For the deferred docs pass, not fixed now.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree carries exactly this and nothing else beyond today's real, committed changes: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed via `git status` immediately before this file was written — nothing else uncommitted, nothing else untracked.

---

## Next Session Should

Alex's call between several fully independent, unblocked options: (a) run the Sermonindex volume batch (553 triaged rows ready), (b) REDO the 2 broken PA docs, (c) resolve the 2 ambiguous reconciliation flags (needs Alex's memory/judgment, not a build), (d) decide on the optional lexicon restamp, (e) #10 — convert `ingest_commentaries.py`, (f) decide the Study Panel's kill-switch/SP1 gaps now that it's live in production, or (g) CLAUDE.md's own docs pass. None block each other.
