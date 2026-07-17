# rhemata-status.md

**As of:** 2026-07-17 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

**2026-07-17, seventh session today — SP2 Phase 6 (shared-component extraction) DONE.** Commits `639a734` (Task 20), `d9ba800` (Task 21), `148c435` (Task 22). Pure refactor — three shared pieces pulled out of the standalone Study page (interlinear, lexicon word-definition, commentary search) with zero intended behavior change. Proved it, not asserted it: real before/after capture via the repaired `playwright-skill` across 4 scenarios came back byte-for-byte identical, screenshots included. Also re-verified Phase 5's pin flows still work (zero file overlap, plus a live re-test) since Alex asked for that explicitly. **SP2 Phase 7 (add Commentaries + Pastors' Notes rows) is next in sequence.**

**2026-07-17, sixth session today — SP2 Phase 5 (pin system rebuild) DONE.** Commits `8ec1f5d` (migration), `f4576f4`, `9e17c7f`, `cd2cf7b`, `8e2d4e3`, `8ac2f12`, `7357bad`. Global, account-database-backed pins, cap 8 with a real visible message, top-bar dropdown replacing the edge tab, guest pin → signup → auto-land. Found and fixed a real bug live during verification (guest signup modal was silently unclickable behind the still-open panel) — proved the fix with a real end-to-end signup, not reasoned about. Three deliberate deferrals recorded, not lost — see "Done today" and Open Flags below. **SP2 Phase 6 (shared-component extraction) is next in sequence.**

**2026-07-17, fifth session today — SP2 Phase 4 (fix "your teachers on this verse") DONE.** Commits `af5be46` (Task 9, backend) + `8698e4a` (Task 11, frontend). This was the plan's own highest-priority content fix — the live panel had been unconditionally claiming no teacher addresses any verse, on every verse, without ever checking. Verified live end-to-end in a real signed-in browser session — see "Done today" below. **SP2 Phase 5 (pin system rebuild) is next in sequence.**

**2026-07-17, fourth session today — records/tooling only, no SP2 build work.** Two independent asks, both closed: (1) repaired the `playwright-skill` (it was non-functional — see "Closed today" #24; fixed and committed in the separate `~/.claude/skills` git repo, not this one); (2) reclassified the CORS gap Phase 3's Task 8 found — Alex confirmed it's a non-issue for his actual workflow (deploys straight to Vercel, doesn't run local dev against production) — from an open gap needing a decision to known-and-accepted, records-only, no Railway config touched. See "Closed today" #23–24 below. SP2 Phase 4 is still next whenever build work resumes.

**2026-07-17, third session today — SP2 Phase 3 (SP1 verified-verse swap) DONE, MID-POINT STOP reached.** Commit `da37bba`. Closes Open Flag 17. Verified live in a real headless browser, not just code/curl — see "Done today" below. Found a real, separate CORS gap along the way (not fixed, needs Alex's call). **Everything through the plan's MID-POINT STOP is now shipped: kill switch (Phase 1), attribution (Phase 2), and the real verified-verse trigger (Phase 3). No panel content has changed yet — Phase 4 (fixing the false "your teachers on this verse" claim) is next in sequence, and is explicitly the first thing after the stop per the plan's own sequencing, since that falsehood is live in production right now.**

**2026-07-17, second session today — SP2 Phase 2 (attribution) DONE.** Commits `1000bef` (Task 4) + `d4e1423` (Task 5). Found and fixed a real production bug along the way: the live `/sources` page had been stating a false quote-verification claim for a week — see "Done today" below.

**2026-07-17, first session today — records-correction pass:** no code was written or run — Alex asked for a pure docs-accuracy pass following two corrections surfaced in conversation. Fixed in CLAUDE.md, PLAN.md, and this file: (1) Rule 10's ingest freeze is per-script, not global — the Sermonindex/YouTube growth path was never blocked by #10 or #13; (2) `ingest_commentaries.py` (#10) is reclassified from "pending conversion" to a retire-or-rebuild decision (its source SQLite dump is a hardcoded, ephemeral `/tmp` path, almost certainly gone, and the script can't target any other collection) — new PLAN.md Open Decision #12; (3) `ingest_helloao.py` (#13) is confirmed the one real, live-blocking chokepoint gap, but scoped only to HelloAO-sourced commentary growth (PLAN.md #27), not corpus growth generally.

2026-07-15 (prior session, unaffected by today's work): fixed a real SP1 defect (range/prefix double-count), built and merged SP2 Phase 1 (kill switch), and ran a 10-question live verification of SP1's coverage.

- **No default next action is forced.** Alex's call: continue SP2 (Phase 3 — SP1 verified-verse swap — is next in sequence), or pick up any of the carried-forward items below (Sermonindex volume run, PA redo, ambiguous reconciliation flags, lexicon restamp, `ingest_commentaries.py` retire-or-rebuild decision, `ingest_helloao.py` conversion). None block each other.
- Everything logged below as "done" was verified against real commits, real test output, or real saved data — not carried forward from memory.

---

## Done today (2026-07-17, seventh session — SP2 Phase 6, a pure refactor proven identical, not asserted)

**1. Diagnostic-first, per Alex's instruction — found a real discrepancy before writing any code.**
- Re-read `InterlinearBlocks`, the lexicon-fetch effects, and `fetchCommentary` fresh (line numbers drift session to session; the plan's own numbers were from 2026-07-15). Two things surfaced that weren't obvious from the plan's terse hook signatures: (a) the interlinear fetch effect also reset `selectedStrongs` — page-level state shared by four other features, so it couldn't move into the hook; (b) the colon/dot lexicon-parsing logic appears at **two** call sites with genuinely different output shapes, not one — a naive `useLexiconDefinition` returning a full `WordDefinition` would have silently changed the second site's behavior. Both surfaced and confirmed with Alex before writing anything, per the standing diagnostic-first rule.

**2. Task 20 — `InterlinearBlocks` + its fetch — commit `639a734`.**
- Moved verbatim into `components/rhemata/interlinear-blocks.tsx`; `hooks/useInterlinear.ts` extracts the fetch, now deriving `isNT` internally too (was a separate page-level line). `selectedStrongs`'s reset kept as its own small effect in `page.tsx`, per Alex's approval.

**3. Task 21 — lexicon word-definition fetch/parse — commit `d9ba800`.**
- `useLexiconDefinition(strongs, accessToken)` returns only `{gloss, lexiconDefinition, meaning}` — the parsed pieces, not a full `WordDefinition` — per Alex's explicit approval not to unify the two call sites' differing output shapes. Both sites in `study/page.tsx` still construct their own final object exactly as before. New `WordDefinitionCard` built to spec (word/transliteration/Strong's/gloss/definition/usage, no Precept Austin, no "From the Library") — not consumed anywhere yet, built for Phase 7/8.

**4. Task 22 — commentary search — commit `148c435`.**
- `useCommentarySearch()` extracts `fetchCommentary` + its triggering effect verbatim, plus a `sourceKindFilter` passthrough unused by the standalone page today (no behavior change there). One now-redundant `setCommentaryResults([])` call removed from `handleWordStudySelect` — the hook's own effect already clears results when `verseData` goes null, same end state. Left the `useTeachersOnVerse` consolidation note only, didn't touch Phase 5's shipped `study-panel.tsx`.

**5. Task 23 — proved identical behavior, the strongest evidence used in this build so far.**
- Captured real before/after state for 4 scenarios via the repaired `playwright-skill`: NT interlinear (John 3:16), lexicon panel + full word-study sheet (θεὸς), word-study mode (the one Alex specifically flagged as most at-risk — "Faith"), and mixed commentary+sermon results (Romans 8:28). **All 5 screenshots came back byte-for-byte identical PNG files** (`cmp -s` matched exactly, not just visually similar) and all extracted JSON text/DOM data matched exactly too.
- Also re-verified Phase 5's pin flows per Alex's explicit request, even though Phase 6 never touches `study-panel.tsx`/`app/page.tsx`/`pin-dropdown.tsx` (confirmed via `git diff --stat` across the whole phase — zero overlap): pin/unpin toggle round-tripped correctly with real backend persistence (confirmed via the API, not just the UI), guest pin button stayed visible and un-disabled, and BetaGate opened with the panel correctly closed behind it (Phase 5's bug fix still holds).

---

## Done today (2026-07-17, sixth session — SP2 Phase 5, verified live via the repaired playwright-skill)

**1. Task 13 — `study_pins` migration — commit `8ec1f5d`.**
- Written per the plan exactly. Applied by Alex directly in the Supabase SQL Editor — not by terminal, per the standing MCP-write-tools restriction. Verified live before trusting it: `to_regclass('public.study_pins')` returned the real table, then a full diff of all 5 columns, both unique constraints (id PK, `(user_id, reference_type, verse_id)`), the `user_id` index, the FK to `auth.users` with `ON DELETE CASCADE`, RLS enabled, and the `study_pins_own_rows` policy (`auth.uid() = user_id`, `FOR ALL`) — every piece matched the migration file exactly, not just "no error."

**2. Tasks 14–18 — backend endpoints + full frontend rebuild — commits `f4576f4`, `9e17c7f`, `cd2cf7b`, `8e2d4e3`, `8ac2f12`.**
- Backend: `GET/POST /study/pins`, `DELETE /study/pins/{id}`, cap of 8 enforced server-side (409 on the 9th).
- Frontend: real fetch-on-mount + persist pin state (replacing the in-memory cap-4 array); `referenceFromVerseId()` added to reconstruct a displayable reference from the server's compact `verse_id`; guest pin attempts store the identity in `sessionStorage` and open signup via the existing `LoginModal`/`openAuthGate` mechanism (`LoginModal.tsx` itself untouched, per Alex's explicit call — it's load-bearing); pin button never `disabled` anymore, real visible cap message on a real click; new `pin-dropdown.tsx` reuses the existing shadcn `DropdownMenu` (already used by `sidebar.tsx`) rather than building a new one, mounted in the previously-empty top-bar div; `StudyPanelEdgeTab` deleted entirely.
- Real gap found while building, not anticipated by the plan: right after a guest's signup succeeds, `useAuth`'s `accessToken` hasn't flushed from `onAuthStateChange` yet in that same closure (classic stale-closure issue) — fixed by reading the fresh session directly from the Supabase client instead.

**3. A real bug found live during Task 19, fixed same session — commit `7357bad`.**
- A signed-out guest's Pin click opened `BetaGate`/`LoginModal` while the study panel stayed open behind it. Both are `fixed inset-0 z-50` — tied — and the panel's own Radix Dialog overlay, later in the DOM, painted on top and silently swallowed every click meant for the modal underneath. **Looked completely normal in a screenshot** — the bug was only findable by checking what was actually receiving clicks, not by looking at rendered output.
- Confirmed with `document.elementFromPoint` (ground truth, not inference) plus a real forced mouse click at the exact coordinates before touching any code: the click landed on the panel's overlay, not the Continue button; the BetaGate form was still present afterward, proving the click never reached it.
- Fix: `handleToggleStudyPin`'s guest branch now closes the panel the moment it stores the pending pin and opens the auth gate. **Proved the pending pin survives with a real end-to-end run, not by reasoning about it:** real BetaGate code entry → real LoginModal in signup mode, showing the pin-specific reason text → real signup submitted for a freshly-created test account → real session established (modal auto-closed, no email-confirmation step on this project) → pin dropdown showed exactly `["Romans 8:28"]`, the originally-attempted verse, with zero manual re-pin action from the test. Test account deleted afterward via the admin API.

**4. Task 19 — full live verification, via the repaired `playwright-skill` this time, not a scratchpad workaround.**
- **Persistence across a real page reload:** pinned John 3:16 and Romans 8:28 through the real UI (real chat questions, real verified underlines, real pin-button clicks); dropdown showed both before AND after a real `page.reload()`.
- **Persistence across a fresh session:** a brand-new browser context with freshly-minted tokens for the same user (no localStorage carryover) showed the same 2 pins immediately — proves server-side persistence, not device caching.
- **Cap at 8, real 9th attempt:** seeded 6 more pins to reach 8, then opened a genuinely new, unpinned verse (Philippians 4:13) through a real chat question and clicked Pin for real. Visible message "Pin limit reached (8) — unpin something first" appeared and auto-dismissed after ~2.5s; the verse stayed unpinned; API confirmed the count held at 8 server-side too.
- **Global across conversations:** started a real new conversation — dropdown still showed all 8 pins.
- **Dropdown-open-while-panel-open, determined empirically per Alex's explicit instruction not to assume either way:** `document.elementFromPoint` plus a real forced click proved one real click on the dropdown trigger, while the panel is open, closes the panel but does **not** open the dropdown — a second click is needed. Left as-is, Alex's explicit call — see Open Flags.
- All 8 seeded/test pins deleted from the real account afterward via the API; all scratchpad session files, JWTs, and screenshots deleted (real credentials, never left on disk).

---

## Done today (2026-07-17, fifth session — SP2 Phase 4, verified live in a real signed-in browser)

**1. Task 9 — added `source_kind_filter` to `/study/commentary` — commit `af5be46`.**
- New optional query param (`'commentary' | 'sermon_transcript'`, default `None`). Guarded the existing commentary-query block (book pre-filter + vector search + dedup loop) to skip when the filter excludes it; guarded the sermon-query block the same way. Everything else (scoring, sort, pagination, neighbor-content fetch) untouched.
- Pushed to `main` to deploy — this project has no local backend, so live verification requires the real Railway deploy. First push of the session; flagged transparently before doing it, given the small-but-real blast radius of a production backend deploy (purely additive/backward-compatible change, per the plan's own design).

**2. Task 10 — proved the split doesn't change Study mode's existing behavior.**
- **Honest gap:** the literal pre-push "before" snapshot wasn't captured — Railway's deploy finished by the time verification started (checked via a distinguishing-behavior probe: the filter was already restricting results on first query). Substituted two things instead of assuming: (a) direct code-diff proof that the new guards are unconditionally-true no-ops when `source_kind_filter` is omitted (`None in (None, "commentary")` and `verse_id and None in (None, "sermon_transcript")` both reduce to exactly the original unconditional code); (b) live run-to-run stability proof — the same 3 unfiltered queries (Romans 8:28, John 3:16, Philippians 4:13) returned byte-identical page-level results (document IDs, titles, order) across two separate calls minutes apart; one verse's internal `total` count flickered (13→15) — a known HNSW approximate-search artifact on the untouched vector-search call, not a regression.
- **Split proof (Step 3):** `source_kind_filter=commentary` and `=sermon_transcript` each returned zero cross-contamination across all 3 verses — every result's `source_kind` matched the requested filter, no exceptions.

**3. Task 11 — wired the panel to the real query — commit `8698e4a`.**
- New `useTeachersOnVerse()` hook in `study-panel.tsx`, panel-local per the plan's design note. Replaced the hardcoded, unconditional "None of your teachers address this verse directly yet" text with real loading/results/honest-empty-state rendering, gated on the query genuinely returning zero results.
- Also gated the whole "Your teachers on this verse" block on `reference.type === "verse"` — the original hardcoded version rendered unconditionally, which would have shown a verse-flavored claim even for a (currently unreachable in SP2) teacher-type reference.
- Had to pass `accessToken` into `<StudyPanel>` from `app/page.tsx`, which it never received before — `/study/commentary` requires auth. Guests get the same 401-caught-as-empty-results behavior the standalone Study page's existing commentary fetch already has — not a new gap introduced here.

**4. Task 12 — verified the fix is real, live, in a real signed-in browser — not just relabeled.**
- Used the newly-repaired `playwright-skill` for real this time. Signing in required a workaround: Supabase's magiclink redirect only allowlists the production domain, so a straight redirect-based sign-in never reaches `localhost:3000` (different origin, localStorage doesn't cross). Fixed by minting a real JWT + refresh token server-side (same technique as `scripts/test_metering.py`) and injecting a correctly-shaped session directly into `localhost:3000`'s localStorage before the app loaded.
- **Real content confirmed:** opened the panel on Romans 8:28 (the dev-button's fixed demo verse, which happens to be one of Task 10's 3 confirmed-covered verses) — the panel rendered two genuine Derek Prince excerpts pulled from real sermon transcripts, screenshotted as proof.
- **Genuine empty state confirmed:** 1 Chronicles 1:2 (a genealogy verse, confirmed to have zero sermon coverage via a live query first) returned a real 200-status, zero-result response through the exact same authenticated endpoint call the panel's hook makes — proving the empty state, when it renders, reflects a real query and not a hardcoded or unreachable path.
- **No classical-commentary leakage confirmed:** zero matches for Matthew Henry, Adam Clarke, Jamieson-Fausset-Brown, or HistoricalChristianFaith anywhere in the rendered "Your teachers" section — the exact positioning failure this phase exists to prevent.
- Cleaned up the injected session data and screenshot from disk afterward (real credentials, scratchpad-only).

---

## Done today (2026-07-17, third session — SP2 Phase 3, verified live in a real browser)

**1. Task 6 — confirmed SP1's verified-reference shape live, no deviation from the plan.**
- Ran a real question through the live `/chat` endpoint (curl, SSE stream) and inspected the final meta event directly: `"verified_references": [{"type": "verse", "raw": "John 3:16", "positions": [0, 1589]}]` — matches the plan's assumed shape exactly. No code written against a wrong assumption.

**2. Task 7 — swapped the client-side verse guess for SP1's verified data — commit `da37bba`.**
- `lib/study-reference.ts`: factored the book-name/range parsing out of `detectVerseReferences` into a shared `parseVerseIdentity()` (one parser, used by both detection and verification, per the plan's explicit instruction not to duplicate it); added `isVerified()`.
- `hooks/useChat.ts`: messages now carry `verifiedReferences` from the meta event, same pattern as `citations`/`messageId`.
- `chat-message.tsx`: threads `verifiedReferences` down to the underline branch — a detected candidate only renders as a clickable underline if SP1 verified the same verse identity for that message.
- **Two files beyond the plan's named list, both necessary for the feature to actually work:** `lib/api.ts` (the `onMeta` callback type never had `verified_references` on it, even though the backend has sent it since SP1 shipped) and `app/page.tsx` (nothing passed `message.verifiedReferences` into `<ChatMessage>` — without this the filter always defaults to empty and no verse ever verifies, silently). Included in the same commit since a partial version would have shipped a non-functional feature.
- Confirmed the Phase 1 kill-switch gate (`detectVerses = !isStreaming && isStudyPanelEnabled()`) is untouched — the new filter sits strictly inside the existing `if (detectVerses)` block.
- `tsc --noEmit` clean.

**3. Task 8 — verified fail-quiet end-to-end, live, in a real browser — closes Open Flag 17.**
- Used Playwright directly (the installed `playwright-skill` turned out to be non-functional — see Open Flags below) against the real local dev server calling the real production backend.
- **The clean proof Task 8 Step 3 asks for, found live, not constructed:** one real question produced a backend response with completely empty `verified_references` despite the visible answer containing 12 verse-shaped substrings (Romans 8:28 ×6, Romans 8:16, 1 Thessalonians 3:3 ×2, Romans 8:16-17, Romans 8:17, Romans 8:18) — DOM showed **zero** underlines. A second question verified 4 distinct verses; every occurrence of each (including repeats) underlined correctly, and zero unverified candidates were wrongly underlined.
- Also confirmed live: teacher-type verified references (e.g. `{"type": "teacher", "raw": "John Bevere", ...}`) never render as underlines anywhere — matches the Global Constraint ("No teacher underlines in SP2").

**4. Real bug found during Task 8 verification, not fixed — needs Alex's call.**
- The local dev frontend (`localhost:3000`) cannot call the production Railway backend from an actual browser: the `/chat` preflight `OPTIONS` request fails with no `Access-Control-Allow-Origin` header — Railway's `ALLOWED_ORIGINS` doesn't include `localhost:3000`. `curl` and the SP1 Python test harness never hit this because CORS is a browser-only enforcement; this session's earlier curl-based Task 6 verification was unaffected.
- Worked around it for verification purposes only, in an isolated test browser (`--disable-web-security`, never touched production config) — see Open Flags below for the standing gap.

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
7. **SP2 Phases 7–10** — not started. Phase 2 (attribution) DONE (commits `1000bef`, `d4e1423`); Phase 3 (SP1 verified-verse swap) DONE (commit `da37bba`), MID-POINT STOP reached; Phase 4 (fix "your teachers on this verse") DONE (commits `af5be46`, `8698e4a`); Phase 5 (pin system rebuild) DONE (commits `8ec1f5d`, `f4576f4`, `9e17c7f`, `cd2cf7b`, `8e2d4e3`, `8ac2f12`, `7357bad`); Phase 6 (shared-component extraction) DONE (commits `639a734`, `d9ba800`, `148c435`) — proven byte-for-byte identical before/after, not asserted. Phase 7 (add Commentaries + Pastors' Notes rows) is next in sequence per the committed plan.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list, plus the SP track — see PLAN.md itself for full detail; this is a pointer, not a restatement)

- **#1–#14:** **corrected 2026-07-17** (previously read "all DONE except #10 and #14's remainder" — that implied #13, the `ingest_helloao.py` conversion, was complete; verified false by direct code read: no `shared_ingest` import anywhere in the file, own Supabase REST `.insert()` calls on `documents` and `chunks`). Actual state: all DONE except #10 (`ingest_commentaries.py` conversion, still unstarted), **#13 (`ingest_helloao.py` conversion, still unstarted — not merely undocumented, a real unconverted write path)**, and #14's folder-rename/`jewish_perspectives`-drop remainder. **Second correction, same day:** #10 and #13 are not equivalent-risk items. `ingest_commentaries.py` reads a hardcoded `/tmp` SQLite dump that's almost certainly gone and can't target any other collection — conversion is likely busywork on a script that can't run; reclassified as a retire-or-rebuild decision (PLAN.md Open Decisions #12), not a scheduled build. `ingest_helloao.py` is the real, live gap (live API, resume-safe) — but it blocks only HelloAO-sourced commentary growth (PLAN.md #27), not corpus growth generally. Rule 10's ingest freeze is per-script: the YouTube/Sermonindex path (`youtube_ingest.py` → `ingest_file()` → `shared_ingest`) is fully converted and was never blocked by #10 or #13.
- **#17 (propositions backfill):** 810 non-PA unlicensed docs, correctly sized, not run.
- **SP track:** SP1 (reference-pointer backend) fully built and merged — see PLAN.md #39. SP2 (panel frontend) is a re-planned corrected delta: Phase 1 (kill switch) DONE (2026-07-15); Phase 2 (attribution) DONE (commits `1000bef`, `d4e1423`) — also fixed a real production bug found along the way; Phase 3 (SP1 verified-verse swap) DONE (commit `da37bba`) — closes Open Flag 17, verified live in a real browser, surfaced a CORS gap along the way (reclassified accepted-not-a-blocker, formerly Flag 23). **MID-POINT STOP reached.** Phase 4 (fix "your teachers on this verse") DONE (commits `af5be46`, `8698e4a`) — the plan's own highest-priority content fix, verified live in a real signed-in browser session. Phase 5 (pin system rebuild) DONE (commits `8ec1f5d`, `f4576f4`, `9e17c7f`, `cd2cf7b`, `8e2d4e3`, `8ac2f12`, `7357bad`) — global, account-database-backed pins, cap 8, top-bar dropdown, guest signup auto-land; found and fixed a real click-interception bug live during verification. Phase 6 (shared-component extraction) DONE (commits `639a734`, `d9ba800`, `148c435`) — pure refactor, proven byte-for-byte identical (screenshots included) before/after, not just asserted; Phase 5's pin flows re-verified unaffected. Phases 7–10 not started; Phase 7 is next. SP3 formally dissolved into SP2 (PLAN.md #41) — no longer a separate track.

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
- ~~17. The Study Panel's verse-reference detector is still the narrow client-side stand-in, not SP1's verified-pointer data.~~ **CLOSED — commit `da37bba`, 2026-07-17.** Detected candidates now only underline if SP1 independently verified the same identity. Verified live in a real browser: a case with 12 unverified candidate mentions produced zero underlines; a case with 4 verified verses underlined every occurrence correctly, including repeats.
- ~~23. `localhost:3000` cannot call the production `/chat` endpoint from a real browser (CORS).~~ **RECLASSIFIED 2026-07-17 (records-only, no code touched) — known, accepted, not a blocker.** Alex's call: this is a non-issue for his actual workflow — he deploys straight to Vercel and doesn't run local frontend dev against the production backend as a normal practice; the gap only surfaced because this session specifically drove a real browser against `localhost:3000` → production for SP2 Phase 3's live verification. Railway's `ALLOWED_ORIGINS` is deliberately left untouched — no production config change was made or requested. Standing practice going forward: browser-based live-chat verification from local dev uses the `--disable-web-security` isolated-test-browser workaround (proven this session) when genuinely needed; curl/script-based verification (as Task 6 used) remains the default and is unaffected by this gap either way.
- ~~24. The installed `playwright-skill` is non-functional.~~ **CLOSED — commit `d159611` in the separate `~/.claude/skills` git repo, 2026-07-17.** Root cause: only `SKILL.md` had ever been copied down at install time — `run.js`, `lib/helpers.js`, and `package.json` (the actual executor, helper library, and dependency manifest) never existed on disk, so the skill could not run despite its own documentation assuming a working tool. Identified via web search as `lackeyjb/playwright-skill`; confirmed the installed `SKILL.md` is byte-identical to the upstream source, then restored the three missing files directly from that source rather than reconstructing them from prose. `npm run setup` installed cleanly (Chromium was already cached locally). Verified with a real run, not just install logs: `detectDevServers()` found the live rhemata dev server, and a script executed via the documented `node run.js <file>` command launched headless Chromium, navigated the real `localhost:3000` page, and used the bundled helpers (`createContext`/`takeScreenshot`/`extractTexts`) to pull real page content and save a real screenshot. This supersedes the raw-scratchpad-Playwright workaround Flag 24 previously described — future sessions should use the repaired skill directly.
- ~~25. Guest signup modal (BetaGate/LoginModal) silently unclickable behind the still-open study panel.~~ **FOUND LIVE AND CLOSED SAME SESSION — commit `7357bad`, 2026-07-17.** A signed-out guest's Pin click opened the auth gate while the panel stayed open behind it; both are `fixed inset-0 z-50`, tied, and the panel's overlay (later in DOM) painted on top, silently swallowing every click meant for the modal — invisible in a screenshot, confirmed only via `document.elementFromPoint` plus a real forced click. Fixed by closing the panel the moment the guest pin flow opens the auth gate. The pending pin's survival through that close was proven with a real end-to-end signup, not assumed — see "Done today" above.

**Stays open — do NOT close early:**
(none currently)

**New today (2026-07-15):**
19. **Kill switch is deploy-time, not instant.** `NEXT_PUBLIC_STUDY_PANEL_ENABLED` is a build-time environment variable — flipping it requires a Vercel redeploy to take effect (minutes, not immediate). This differs from `safe_mode`, which is a database row read fresh per request and takes effect instantly. Accepted deliberately for a private beta. A future session must not assume the panel can be pulled instantly in an emergency the way `safe_mode` can.
20. **SP2 Phase 1 verification gap.** ~~The keyboard-shortcut suppression and the live-streamed-answer underline suppression were verified by independent code review plus the same proven flag mechanism — not by a live interactive/browser test, because no browser-automation tool was available in this environment.~~ **Partially superseded 2026-07-17, superseded further same day:** live browser automation is now available and working — first via raw Playwright installed ad hoc in the scratchpad (Phase 3's Task 8), then via the `playwright-skill` itself once repaired (see "Closed today" #24). The original Phase 1 keyboard-shortcut/mid-stream-suppression claims specifically have still not been re-verified live — would need a dedicated pass, not automatically closed by this.
21. **SP1's license/visibility and biblical-figure guards are LAB-PROVEN ONLY, not field-tested.** Today's 10-question live run never actually exercised either guard — the model self-filtered (never proposed a biblical figure as a teacher; never named a hidden/unlicensed teacher even when tempted by Q8) before either guard got the chance to fire. Do not let a future session record or assume these guards have been proven against live traffic — only SP1's own constructed test suite has actually exercised them.
22. **Answer-writing oddity (Q5), minor, not an SP2 issue.** The naming-back rule (PLAN.md #39) can technically pass while placing the named verse only in the closing sign-off line rather than the substantive discussion, producing a technically-correct but poorly-placed underline. Worth a system-prompt tweak whenever answer-writing is next touched — not urgent.

**New today (2026-07-17, SP2 Phase 5 session) — three deliberate deferrals, Alex's explicit call, not oversight:**
26. **No mobile equivalent of the pin dropdown.** The top-bar mount point (`page.tsx`'s previously-empty `div`) is `hidden md:flex` — desktop-only. Ship desktop-only for now; do not build a mobile bookmark-dropdown equivalent in this phase.
27. **The `hasSession: false` signup branch leaves a guest's pending pin unhandled.** If Supabase requires email confirmation (this project's current config does not — confirmed live, the test signup in Task 19 auto-established a session with no confirmation step — but the code path exists for whenever that changes), the pin stays in `sessionStorage` and is never landed; nothing checks for it on a later, separate sign-in. Leave unhandled for now.
28. **Dropdown-open-while-panel-open needs two clicks, not one.** Determined empirically (not assumed): with the study panel open, a single real click on the top-bar pin dropdown trigger closes the panel (via its own transparent overlay, which sits topmost at that screen position) but does not open the dropdown on that same click — confirmed via `document.elementFromPoint` plus a real forced mouse click. A second click, now unobstructed, opens the dropdown normally. This satisfies "clicking outside closes the panel" but means the dropdown can't be opened in one motion while the panel is showing. Accepted as a known, minor UX wrinkle — clunky, not broken — no code change made.

---

## Standing Carve-Out

**Corrected today — the prior note was stale.** `git status` immediately before writing this file shows only untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths, still need a `.gitignore`-or-commit decision) plus this session's own now-committed work. `SKILL.md`, previously noted as modified, is now clean (matches `HEAD`) — the prior session's uncommitted drift there is gone, either committed or reconciled at some point before today; not independently re-diagnosed further, since it's not this session's concern.

---

## Next Session Should

Alex's call between fully independent, unblocked options: (a) SP2 Phase 7 — add the missing Commentaries + Pastors' Notes rows (next in the committed plan sequence, now that Phase 6's extracted pieces exist to build on), (b) run the Sermonindex volume batch (553 triaged rows ready — **confirmed 2026-07-17 this was never gated by #10/#13; routes through the fully-converted YouTube pipeline**), (c) REDO the 2 broken PA docs, (d) resolve the 2 ambiguous reconciliation flags (needs Alex's memory/judgment, not a build), (e) decide on the optional lexicon restamp, (f) decide retire-vs-rebuild on `ingest_commentaries.py` (#10 — reclassified 2026-07-17, its source data is almost certainly gone; see PLAN.md Open Decisions #12), (f2) convert `ingest_helloao.py` (#13 — the one real remaining chokepoint gap, blocks only HelloAO commentary growth at PLAN.md #27), (g) CLAUDE.md's own docs pass. None block each other. (Former options (h) the CORS gap and (i) the broken `playwright-skill` are both closed as of 2026-07-17 — see "Closed today" #23–24 above.)
