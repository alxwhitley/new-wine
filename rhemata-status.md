# rhemata-status.md

**As of:** 2026-07-17 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

**2026-07-17, second session today — SP2 Phase 2 (attribution) DONE.** Commits `1000bef` (Task 4) + `d4e1423` (Task 5). Found and fixed a real production bug along the way: the live `/sources` page had been stating a false quote-verification claim for a week — see "Done today" below. **SP2 Phase 3 (SP1 verified-verse swap) is next in sequence per the committed plan.**

**2026-07-17, first session today — records-correction pass:** no code was written or run — Alex asked for a pure docs-accuracy pass following two corrections surfaced in conversation. Fixed in CLAUDE.md, PLAN.md, and this file: (1) Rule 10's ingest freeze is per-script, not global — the Sermonindex/YouTube growth path was never blocked by #10 or #13; (2) `ingest_commentaries.py` (#10) is reclassified from "pending conversion" to a retire-or-rebuild decision (its source SQLite dump is a hardcoded, ephemeral `/tmp` path, almost certainly gone, and the script can't target any other collection) — new PLAN.md Open Decision #12; (3) `ingest_helloao.py` (#13) is confirmed the one real, live-blocking chokepoint gap, but scoped only to HelloAO-sourced commentary growth (PLAN.md #27), not corpus growth generally.

2026-07-15 (prior session, unaffected by today's work): fixed a real SP1 defect (range/prefix double-count), built and merged SP2 Phase 1 (kill switch), and ran a 10-question live verification of SP1's coverage.

- **No default next action is forced.** Alex's call: continue SP2 (Phase 3 — SP1 verified-verse swap — is next in sequence), or pick up any of the carried-forward items below (Sermonindex volume run, PA redo, ambiguous reconciliation flags, lexicon restamp, `ingest_commentaries.py` retire-or-rebuild decision, `ingest_helloao.py` conversion). None block each other.
- Everything logged below as "done" was verified against real commits, real test output, or real saved data — not carried forward from memory.

---

## Done today (2026-07-17, second session — SP2 Phase 2, verified against real commits and a live dev server)

**1. Task 4 — STEPBible/Tyndale House attribution completed — commit `1000bef`.**
- The first pass at Task 4 (`72053ac`, earlier today) added the CC BY 4.0 credit to `WordStudyPanel` and `InterlinearBlocks` in `frontend/app/study/page.tsx` but missed a third spot where lexicon word definitions also render: `InlineWordPanel`. That fix was already drafted, uncommitted, in the working tree at session start — verified correct (matches the exact required wording, matches the styling pattern of the other two instances) and committed as-is.

**2. Task 5 — same credit added to `docs/how-rhemata-handles-sources.md` and the live `/sources` page, plus a real bug found and fixed — commit `d4e1423`.**
- **The plan's assumption was wrong, caught before it caused a silent gap:** Task 5 assumed `frontend/app/sources/page.tsx` renders `docs/how-rhemata-handles-sources.md` automatically. It doesn't — `page.tsx` is a separate hardcoded React component that only started as a copy of the `.md` file's content, on 2026-07-06 (`c47bbd3`).
- **Consequence, discovered while verifying the assumption:** the honesty fix (PLAN.md #2, `0af69a6`, 2026-07-10) corrected `POSITIONING.md`, `system_prompt.txt`, and the `.md` file's quote-verification claim to the real paraphrase-and-cite posture — but never touched `page.tsx`. The live `/sources` page had been stating the false, aspirational claim ("A quotation cannot appear in Rhemata unless our software confirms it is an exact, character-for-character match against the source text") in production for a week, undetected.
- **Fixed, with Alex's explicit go-ahead to bundle it with the credit addition** (asked directly rather than assumed, since it was outside Task 5's literal scope): `page.tsx`'s stale section replaced with the corrected copy matching the `.md` file, plus the STEPBible/Tyndale House credit added to both files.
- **Verified live, not just by code inspection:** curl'd the actual rendered HTML from a running `next dev` server (already running on :3000) — confirmed the corrected heading, the corrected body copy, and the credit line all present in the real response; the old false claim absent.
- PLAN.md's own Ground Truth section had prematurely logged this class of claim as "Closed by #2 (honesty) now" — corrected in the same session, per Standing Rule #12.

---

## Done today (2026-07-15, verified against git log / real data just now)

**1. SP1 range/prefix double-count fix — commit `76105a0`, merged to `main`.**
- **What it fixed:** whenever SP1's writer named a verse range (e.g. "Romans 8:26-28"), it also listed the range's own start verse as a separate line in its private `<reference_mentions>` block — both independently real, both verifying, one textual span producing two verified references. Confirmed live in 2 of 10 real questions (Q3, Q9) during today's verification run, not a rare edge case.
- **Reclassified, not silently fixed:** SP1's own final review had judged this cosmetic and accepted it — correctly, at the time, since nothing consumed `verified_references` yet and both entries were genuinely real (not a false-resolution). It is now reclassified **load-bearing**, because SP2 is the first thing to render this data, and PLAN.md #39's own rule requires "ranges resolve as one reference." Recorded as a reclassification in PLAN.md #39, not backdated as if always known.
- **Generalized beyond ranges:** the fix is a position-overlap de-duplication pass (longer span wins, shorter dropped; exact-length ties drop both, fail-quiet) applied after all four existing verification guards — none weakened. It also covers cross-book nested substrings (confirmed: "John 3:16" is a literal substring of "1 John 3:16") and teacher-name nesting, since both share the same presence-check mechanism as the range case.
- **Proof:** reproduced on the real Q3/Q9 failing cases; confirmed Q9's genuine, non-overlapping second mention of "Matthew 12:31" survives untouched; zero regressions across all 10 real coverage-run questions. 5 new tests added to `scripts/test_reference_verifier.py`, each proven non-tautological by disabling the fix and confirming the test actually flips to FAIL (per SP1's own hard-won lesson — two tautological tests were caught this same way during SP1's original build).

**2. SP2 (Inline Study Panel frontend) plan — written, amended, committed.**
- Lives at `docs/superpowers/plans/2026-07-15-sp2-inline-study-panel-frontend.md`. Written as a corrected delta against the already-live SP2-shaped shell (`161c4de`), not a greenfield build. Committed `a0437d1`; amended once, `29dbdaa` (reorder + endpoint-split protection + guest pin behavior + real cap message).
- **Confirmed from the actual file, not memory:** 10 phases, 36 tasks, strictly ordered — 1 kill switch, 2 attribution, 3 SP1 verified-verse swap, **MID-POINT STOP**, 4 fix "your teachers on this verse" (deliberately moved ahead of the pin system, since the live shell states a falsehood on every verse today), 5 pin system rebuild, 6 shared-component extraction, 7 add Commentaries + Pastors' Notes rows, 8 Interlinear + lexicon word study move-in (SP3 dissolved), 9 keyboard/screen-reader verification, 10 records correction.
- Supersession decisions recorded in PLAN.md #40/#41 and Open Decisions #10/#11 (see PLAN.md itself — not restated here).

**3. SP2 Phase 1 — kill switch — commit `7ca171b`, merged to `main`.**
- `NEXT_PUBLIC_STUDY_PANEL_ENABLED` (`frontend/lib/study-panel-flag.ts`) gates: verse-underline detection in `chat-message.tsx`; the dev "Study preview" button, its Cmd/Ctrl+Shift+S shortcut, and `handleVerseClick` in `page.tsx`. Defaults enabled unless explicitly set to `"false"`.
- **Verified, not assumed:** an independent reviewer read the actual shipped code (not the implementer's report) and confirmed correct guard placement; a real `next dev` server was run twice (flag unset, then `"false"`) and the rendered HTML diffed directly — the dev button is present exactly once when on, zero times when off, confirmed via real curl output, not code inspection.
- **Honest gap, not glossed over:** the keyboard-shortcut no-op and live-answer underline suppression were NOT verified via live interactive/browser test — no browser-automation tool was available in this environment. Confidence rests on the same proven mechanism (identical flag, same code path) plus the independent code review. See Open Flags below.
- Production default confirmed with Alex: left unset (enabled) — beta users get the panel as each phase lands. Documented in `CLAUDE.md`'s Environment Variables section.

**4. 10-question live SP1 verification run (read-only, no commits from the run itself — scratchpad only).**
- Real questions run through the real answer-generation harness (`scripts/sp1_answer_harness.py`), the real verifier (`reference_verifier.py`), and the real, unmodified client-side guesser (`frontend/lib/study-reference.ts`), side by side.
- **Coverage parity, precisely counted:** the guesser detected 28 verse references total across all 10 answers; SP1 independently verified a matching reference for all 28 — **zero misses, full parity.**
- **Teacher resolutions — pure gain over the guesser (which cannot detect teachers at all, by design):** 6 of the 10 questions produced at least one genuine, currently-servable teacher resolution (8 total resolution events across 3 distinct teachers: Derek Prince ×6, Michael Brown ×1, Daniel Kolenda ×1).
- **Correction to how the biblical-figure and license guards were characterized going into this run:** Paul, Thomas, and Peter were named repeatedly across 8 of the 10 real answers. In every case, the model's own writer-level instruction (never propose a biblical figure as a TEACHER line) already prevented them from ever being proposed as a teacher mention — so the verifier's independent biblical-figure backstop guard was **never actually triggered** by this run; it never got the chance to fire. Likewise, Q8 was built specifically to tempt a hidden/unlicensed teacher (F.F. Bosworth), but the model declined to name any individual, so the license/visibility guard was also never reached. **Both guards remain lab-proven only** (SP1's own constructed test suite), not field-proven. Do not record either as "proven live" in a future session — that would overstate this run's actual coverage.
- **One real defect found and now fixed:** the range/prefix double-count (see item 1 above) — found by this run, not assumed.
- **Minor answer-writing oddity, flagged not fixed:** on Q5, the answer discussed "1 Corinthians 12:31" at length but only literally named the verse in its closing "view in the study panel" sign-off line, never in the substantive discussion. PLAN.md #39's naming-back rule technically passed, but the resulting underline would land on the sign-off line rather than the substance. Not an SP2 defect — a system-prompt wording gap, worth a tweak whenever answer-writing is next touched.

---

## Prior session (2026-07-14), unaffected by today, still real

**Study Panel shell + motion — commit `161c4de`, status commit `fc2f273`.** Panel slides in over chat, sidebar collapses, real trigger (client-side regex detector), pin system, honest empty states. **Its two open gaps as of yesterday are now PARTIALLY closed by today's work:** the kill switch now exists (today's item 3, closes Open Flag 16); the real SP1 pointer backend is built and merged but **not yet wired into this shell's trigger** — that's SP2 Phase 3, not yet built (Open Flag 17 stays open — see below).

**Lexicon slice-runner — commit `dd609fb`, status commit `5b49eaf`.** `scripts/ingest_lexicon_runner.py` built and proven end-to-end. All four real STEPBible lexicon documents remain fully ingested with no backlog for the runner to run against — the runner is ready for future sources, not a queued job today. A restamp-for-consistency of the four existing files remains an open option, not a default next step.

**Records-vs-database reconciliation — commit `4addc06`.** 9 stale claims corrected, 2 flagged ambiguous (needs Alex's memory, not a build) — see "Still open" below.

**Older, already closed, unaffected:** Sermonindex ingest-integrity remediation (`6708060`, `1ec5226`, `33e92b4`) — confirmed present in `git log` exactly where expected.

---

## Still open (carried forward — none of these were touched today)

1. **The Sermonindex volume run has not happened.** 553 `triaged` rows ready in the Queue, unstarted.
2. **2 genuinely-broken PA documents** ("Word Study: Fortunes," "Word Study: Innocent") still need a REDO via `on_existing="delete_and_reingest"`.
3. **2 ambiguous reconciliation flags, both need Alex, not a build:** the magazine "27 of 27 contaminated" figure (can't locate the original signal against current state — closest match is 32 articles across 5 issues in `02_extracted/`); the PA "survivability guard will rarely fire" claim (a claim about future behavior, not DB-checkable).
4. **Optional lexicon restamp** — Alex's call, not scheduled.
5. **CLAUDE.md's own docs pass remains deferred** — folder renames, `jewish_perspectives` drop, and other stale notes, unrelated to today's work.
6. **#10 — `ingest_commentaries.py`** — reclassified 2026-07-17 as a retire-or-rebuild decision (PLAN.md Open Decisions #12), not a scheduled conversion. Its source SQLite dump is a hardcoded, ephemeral `/tmp` path and is almost certainly gone; the script can't target any other collection. Alex needs to decide retire vs. rebuild-from-scratch before this is buildable work again.
7. **SP2 Phases 3–10** — not started. Phase 2 (attribution) is DONE (commits `1000bef`, `d4e1423`, this session). Phase 3 (SP1 verified-verse swap) is next in sequence per the committed plan.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list, plus the SP track — see PLAN.md itself for full detail; this is a pointer, not a restatement)

- **#1–#14:** **corrected 2026-07-17** (previously read "all DONE except #10 and #14's remainder" — that implied #13, the `ingest_helloao.py` conversion, was complete; verified false by direct code read: no `shared_ingest` import anywhere in the file, own Supabase REST `.insert()` calls on `documents` and `chunks`). Actual state: all DONE except #10 (`ingest_commentaries.py` conversion, still unstarted), **#13 (`ingest_helloao.py` conversion, still unstarted — not merely undocumented, a real unconverted write path)**, and #14's folder-rename/`jewish_perspectives`-drop remainder. **Second correction, same day:** #10 and #13 are not equivalent-risk items. `ingest_commentaries.py` reads a hardcoded `/tmp` SQLite dump that's almost certainly gone and can't target any other collection — conversion is likely busywork on a script that can't run; reclassified as a retire-or-rebuild decision (PLAN.md Open Decisions #12), not a scheduled build. `ingest_helloao.py` is the real, live gap (live API, resume-safe) — but it blocks only HelloAO-sourced commentary growth (PLAN.md #27), not corpus growth generally. Rule 10's ingest freeze is per-script: the YouTube/Sermonindex path (`youtube_ingest.py` → `ingest_file()` → `shared_ingest`) is fully converted and was never blocked by #10 or #13.
- **#17 (propositions backfill):** 810 non-PA unlicensed docs, correctly sized, not run.
- **SP track:** SP1 (reference-pointer backend) fully built and merged — see PLAN.md #39. SP2 (panel frontend) is a re-planned corrected delta: Phase 1 (kill switch) DONE and merged (2026-07-15); Phase 2 (attribution) DONE (commits `1000bef`, `d4e1423`, 2026-07-17) — also fixed a real production bug found along the way (see "Done today" above). Phases 3–10 not started. SP3 formally dissolved into SP2 (PLAN.md #41) — no longer a separate track.

---

## Open Flags

**Carried forward, unchanged from before today (still real, none resolved by today's records-only work):**
1. Rule 10 freeze is a bare-substring match, not an invocation check — recurs for `ingest_helloao.py`, `ingest_commentaries.py` only. **Scope reminder (2026-07-17): this mechanism gap only matters for content routed through those two specific scripts** — the freeze itself is per-script, not global, and does not touch any already-converted pipeline (e.g. YouTube/Sermonindex).
2. Magazine queue "27 of 27 pending articles contaminated" — see "Still open" #3 above.
4. Database-number verification gap (independently verifying claimed reconciliation counts against the DB itself — nothing in the harness does this today).
5. `GOVERNED_FILES` gap (`guard_pretooluse.py`/`settings.json` not in `GOVERNED_FILES`).
6. PLAN.md #5.5 closing line is stale. Needs Alex's explicit go-ahead on replacement wording.
7. PLAN.md #14 drift — folder renames and the `jewish_perspectives` drop still open.
10. CLAUDE.md's own "unconverted scripts" prose was stale (said four in its Directory Structure section). **Corrected 2026-07-17, re-verified by reading all six real ingest scripts' code directly (the original five plus `ingest_helloao.py`, which this flag and CLAUDE.md had both omitted from the count):** true count of NOT-converted is **two** — `ingest_commentaries.py` and `ingest_helloao.py` (confirmed live: neither file contains any `shared_ingest` import or `ingest_document()` call; commentaries runs its own SQLite-driven psycopg2 INSERTs, helloao runs its own Supabase REST `.insert()` calls). This "two" is a different pair than whatever this flag originally meant (helloao was never counted before) — coincidence of count, not confirmation of the original claim. CLAUDE.md's four flagged locations have now been corrected to match, in this same session — this is no longer deferred to a future docs pass.
12. PA's 398 "excerpt-less" documents — 396 just need `generate_excerpts.py` (not broken); 2 are the genuinely-broken docs in "Still open" #2 above.
13. PA "survivability guard will rarely fire" — see "Still open" #3 above.
18. CLAUDE.md and SKILL.md are both stale on the quoting rule (found 2026-07-14): both describe verbatim quoting permitted up to 50 words pending a verifier that doesn't exist, while the live system prompt bans reproducing any quote or exact wording in any mode. Deferred to the docs pass, not fixed now.

**Closed today:**
- ~~16. No kill switch / beta flag exists for the Study Panel.~~ **CLOSED — commit `7ca171b`.** Built, independently reviewed, and verified via real rendered-HTML diff with the flag on and off.

**Stays open — do NOT close early:**
17. The Study Panel's verse-reference detector is still the narrow client-side stand-in (`lib/study-reference.ts`'s regex guesser), not SP1's verified-pointer data. This closes at SP2 Phase 3 (the guesser→SP1 swap), not before. Today's 10-question run proved SP1's data is ready and has full coverage parity with the guesser — but nothing today wired the panel's actual trigger to it.

**New today:**
19. **Kill switch is deploy-time, not instant.** `NEXT_PUBLIC_STUDY_PANEL_ENABLED` is a build-time environment variable — flipping it requires a Vercel redeploy to take effect (minutes, not immediate). This differs from `safe_mode`, which is a database row read fresh per request and takes effect instantly. Accepted deliberately for a private beta. A future session must not assume the panel can be pulled instantly in an emergency the way `safe_mode` can.
20. **SP2 Phase 1 verification gap.** The keyboard-shortcut suppression and the live-streamed-answer underline suppression were verified by independent code review plus the same proven flag mechanism — not by a live interactive/browser test, because no browser-automation tool was available in this environment. A Playwright skill exists in Alex's skill set and could close this gap cheaply in a future session.
21. **SP1's license/visibility and biblical-figure guards are LAB-PROVEN ONLY, not field-tested.** Today's 10-question live run never actually exercised either guard — the model self-filtered (never proposed a biblical figure as a teacher; never named a hidden/unlicensed teacher even when tempted by Q8) before either guard got the chance to fire. Do not let a future session record or assume these guards have been proven against live traffic — only SP1's own constructed test suite has actually exercised them.
22. **Answer-writing oddity (Q5), minor, not an SP2 issue.** The naming-back rule (PLAN.md #39) can technically pass while placing the named verse only in the closing sign-off line rather than the substantive discussion, producing a technically-correct but poorly-placed underline. Worth a system-prompt tweak whenever answer-writing is next touched — not urgent.

---

## Standing Carve-Out

**Corrected today — the prior note was stale.** `git status` immediately before writing this file shows only untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths, still need a `.gitignore`-or-commit decision) plus this session's own now-committed work. `SKILL.md`, previously noted as modified, is now clean (matches `HEAD`) — the prior session's uncommitted drift there is gone, either committed or reconciled at some point before today; not independently re-diagnosed further, since it's not this session's concern.

---

## Next Session Should

Alex's call between fully independent, unblocked options: (a) SP2 Phase 3 — swap the client-side verse guess for SP1's real verified verses (next in the committed plan sequence, closes Open Flag 17), (b) run the Sermonindex volume batch (553 triaged rows ready — **confirmed 2026-07-17 this was never gated by #10/#13; routes through the fully-converted YouTube pipeline**), (c) REDO the 2 broken PA docs, (d) resolve the 2 ambiguous reconciliation flags (needs Alex's memory/judgment, not a build), (e) decide on the optional lexicon restamp, (f) decide retire-vs-rebuild on `ingest_commentaries.py` (#10 — reclassified 2026-07-17, its source data is almost certainly gone; see PLAN.md Open Decisions #12), (f2) convert `ingest_helloao.py` (#13 — the one real remaining chokepoint gap, blocks only HelloAO commentary growth at PLAN.md #27), (g) CLAUDE.md's own docs pass, (h) close Open Flag 20 with a Playwright-driven interactive pass over SP2 Phase 1's remaining verification gap. None block each other.
