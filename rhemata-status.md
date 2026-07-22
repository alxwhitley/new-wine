# Rhemata — Live Status

Point-in-time state only. Overwritten each session. Never durable truth.
Corpus counts are not recorded here — query live.

Last verified: 2026-07-21 (SP panel refinement Phase 2 — floating overlay — build commit `fe310e2`).
Records reconciled: 2026-07-21 (push ladder + SP4 sign-off closure — see the section directly below).

---

## Records reconciliation — push ladder + SP4 sign-off closure (session state, 2026-07-21)

**Push ladder, verified against git, not assumed:** `git rev-parse main` and `git rev-parse origin/main` are identical (`5f2c125`) after an explicit `git fetch`; `git branch -vv` confirms `main` tracks `origin/main` with nothing ahead or behind. Every commit from this cycle — `3f68ddc` (teachers-on-verse removal), `ae7e583`, `65b36e2` (chrome cleanup), `916c883`, `fe310e2` (Phase 2 floating overlay), `5f2c125` — is already on `origin/main`. **This corrects an assumption otherwise carried into this reconciliation that the Phase 2 build might be unpushed/hard-stopped locally — it was not; nothing from this cycle is sitting local-only.**

**SP4 sign-off, confirmed complete:** Alex signed in on `rhemata.app` and ran the full authenticated verification pass. All four checks passed: real card content for a signed-in user, the honest-empty state, nested back-return, and keyboard-only navigation. This closes SP4 teacher-card verification — the "NOT verified this session — needs Alex's own pass" framing in the 2026-07-18 SP4 entry below is superseded by this pass (closing note added there), not deleted.

**This same pass also confirmed, live in production, the two same-day removals below:**
- "Your teachers on this verse" is genuinely gone on `rhemata.app` — closes that section's own "full authenticated production re-verification... has not been done" caveat (closing note added there).
- The dev-trigger button + shortcut and the "Open in Study" link are genuinely gone on `rhemata.app`, and STEPBible/Tyndale attribution still renders correctly — closes that section's equivalent gap (closing note added there).

**Not closed by this pass — stays open:** the Phase 2 floating-overlay build (`fe310e2`) **shipped after** this sign-off pass and has only been verified against local-dev route-interception doubles (see that section's own caveat below, left as-is — still accurate). Its "shipped, build commit `fe310e2`" status is a different claim from "signed off" — don't conflate them. A hands-on authenticated `rhemata.app` pass on the overlay itself is still owed.

**Forward:** SP5 (mobile bottom-sheet, roadmap #43) is next and reuses the overlay's shared open/swap/close model (`page.tsx` state + `PanelBody`'s swap-reset), built presentation-agnostic for exactly this reuse. Two long-standing items remain open, untouched by this session: no real screen-reader pass has ever been run (Open blockers #13), and the Hebrew lexicon permission gate from Online Bible has not been obtained (Open blockers #14).

---

## SP panel refinement — Phase 2: floating overlay (session state, 2026-07-21)

Shipped, build commit `fe310e2` — `frontend/app/page.tsx`, `frontend/components/rhemata/chat-message.tsx`, `frontend/components/rhemata/study-panel.tsx` only. Alex's SP4 sign-off (the gate this phase was waiting on) cleared before this session started. **Goes further than the original Phase 2 scope** (`docs/superpowers/plans/2026-07-19-study-panel-refinement.md`, Tasks 6-9), which was margin/rounding only — this session's explicit spec added non-modal desktop interaction and swap-in-place, superseding that plan's narrower Task 9 assumption (default Radix modal dismiss unmodified).

**Desktop presentation:** the panel is a floating card — `inset-y-2 right-2 rounded-xl border border-border`, reusing the existing `shadow-lg` (all values already in use elsewhere in this codebase, per DESIGN.md's "no new shadows/radii/colors" rule and its own "popovers/sheets are the only lifted surfaces" carve-out) — instead of a docked column flush against the screen edge. `page.tsx`'s reserved-width clamps grew by `+1rem` per bound (`clamp(496px,calc(50vw+1rem),736px)` / `clamp(396px,calc(33vw+1rem),496px)`) so a real gap shows between the chat card and the panel, not an overlap.

**Non-modal + swap-in-place:** `PanelPrimitive.Root` now takes `modal={isMobile}` — desktop is non-modal (Radix's documented `DialogContentNonModal` path, confirmed via `/radix-ui/primitives` docs and the installed `@radix-ui/react-dialog@1.1.16` type declarations before writing any code), and desktop renders no `Overlay` at all. Chat stays fully visible and interactive behind it. `VerseReferenceSpan`/`TeacherReferenceSpan` (`chat-message.tsx`) get a `data-study-trigger` marker; `Content`'s `onPointerDownOutside` checks for it via `event.detail.originalEvent.target.closest(...)` and calls `event.preventDefault()` only for those, letting a second underline click swap `reference` in place (page.tsx's `handleVerseClick` already did this unconditionally — no page.tsx change was needed there) instead of racing Radix's default dismiss into a close-then-reopen. Everything else outside the panel still closes it normally — no blocking layer anywhere (confirmed by grep and by reading the full diff).

**Reset-on-swap:** `PanelBody` now collapses Interlinear and resets scroll to top on every genuine target-identity change (`referenceKey(reference)`, a content-identity string — re-clicking the same target is correctly a no-op), and fades the content subtree in via a `key`-forced remount. This supersedes the old "leave Interlinear open across a verse switch" decision from SP2 Phase 8.

**Shared-model note for SP5:** the target/open/close state (`page.tsx`) and the swap-reset behavior (`PanelBody`) are presentation-agnostic and were already shared between mobile/desktop (single `<StudyPanel>`, branching only on `useIsMobile()`); only the modal/overlay/positioning pieces differ now. A future mobile bottom-sheet build can reuse both without touching this logic — the desktop side-slide and a future mobile bottom-rise are presentation layers over the same shared behavior.

**Live-verified, real evidence (Playwright, local dev, route-interception test doubles for `/chat` and `/study/interlinear` only — same CORS-driven method as the two sessions above):** chat textarea stayed typeable while the panel was open; clicking a second, different verse underline while open swapped content to it in place (screenshot: same panel shell, new verse text, Interlinear auto-collapsed, no flicker/stack); scroll position confirmed reset to 0 after a swap; the X button closed the panel; clicking plain chat text (not a trigger) closed the panel; mobile (iPhone 13 emulation) confirmed **completely unaffected** — full-screen sheet, dark scrim, no rounded corners, no gap, chat hidden underneath, byte-for-byte the same presentation as before.

**Caveat, stated plainly:** as with the two sessions above, this is local-dev verification against route-interception doubles, not a full authenticated pass against `rhemata.app`. That full production re-verification (still owed from the "your teachers on this verse" removal earlier this session too) has not been run yet.

---

## SP2 — Panel chrome cleanup (session state, 2026-07-21)

Three approved UI-only changes, build commit `65b36e2`, `frontend/app/page.tsx` + `frontend/components/rhemata/study-panel.tsx` only:

1. **Removed the floating "Study preview" dev-trigger button and its Cmd/Ctrl+Shift+S shortcut** (`app/page.tsx`) — collided with the chat button and duplicated the panel's one real open path. The panel now opens **only** via a verse/teacher underline click. `NEXT_PUBLIC_STUDY_PANEL_ENABLED` and the underline click-path (`onVerseClick`/`onSelectPin` wiring into `handleVerseClick`) are untouched — confirmed by diff, not by inference.
2. **Removed the "Open in Study" link** from the bottom of the panel (`study-panel.tsx`). The standalone `/study` page remains live and reachable by direct URL as the fallback — confirmed by direct navigation, untouched by this diff.
3. **STEPBible/Tyndale House attribution (CC BY 4.0 license condition) retained, no restyling needed.** All four rendering surfaces — `InterlinearBlocks` (shared by the panel's Interlinear row and the standalone page), the panel's own `WordStudyView`, and the standalone page's `WordStudyPanel`/`InlineWordPanel` — already use `text-xs text-muted-foreground`, DESIGN.md's own documented low-prominence pattern (line 120, same class used for verse-number superscripts). No code changed on this point.

**Live verification method, since local dev is CORS-blocked from the production backend for `/chat`, `/study/interlinear`, and `/study/lexicon` (the same pre-existing constraint noted in the "your teachers on this verse" removal above and in Phase 7/8/9's history):** used Playwright route interception as network-level test doubles for those three endpoints only (synthetic but shape-accurate SSE/JSON responses) — every other request (Commentaries, Pastors' Notes, pins) hit the real backend unmodified. This produced a **genuine click on a real verse-underline** (not the removed dev button) that opened the panel, expanded Interlinear with real-shaped tokens, and opened the word-study view — confirming the attribution renders correctly in both panel surfaces by direct observation, not class-name inspection. Pin click showed the expected guest Beta Access gate, no crash. Standalone `/study` loaded directly with no crash.

**Not touched:** SP4's curated `TeacherCard` path, Commentaries, Pastors' Notes, pins, and all interlinear/lexicon *data* fetching — chrome only, per scope lock.

**Production confirmation, 2026-07-21:** Alex's SP4 authenticated sign-off pass confirmed all three changes live on `rhemata.app` — dev-trigger button and shortcut gone, "Open in Study" link gone, STEPBible/Tyndale attribution still renders correctly. Full detail in the reconciliation entry at the top of this file.

---

## SP2 — "Your teachers on this verse" removed (session state, 2026-07-21)

**Removed, build commit `3f68ddc`, frontend-only diff (99 deletions, `frontend/components/rhemata/study-panel.tsx` only):** `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, and the "Your teachers on this verse" render block. **Reason:** verse-anchored nearest-chunk matching (`source_kind_filter=sermon_transcript`) surfaced irrelevant excerpts under teacher names. Retired pending a possible theme-based approach via the SP4 teacher-card path instead, not replaced same-session.

Preceded by a read-only removal-footprint audit (previous session) that traced the feature to commits `af5be46` (Task 9, backend filter param) and `8698e4a` (Task 11, the panel wiring), then classified every symbol it introduced as UNIQUE (safe to remove) or NOW-SHARED (must stay). That classification held with zero surprises during execution.

**Intentionally preserved as shared infrastructure — zero backend changes this session:**
- `/study/commentary` endpoint, `source_kind_filter` param, and both its conditional branches (`commentary` / `sermon_transcript`) — the sermon-results code path predates this feature entirely (`git log -S match_sermon_chunks_by_ref` traces it to `1375b3f`, well before `af5be46`); the standalone Study page's default (unfiltered) query depends on both branches running together, and `CommentaryAccordionRow` depends on the explicit `commentary` filter.
- The `accessToken` prop chain (`app/page.tsx` → `StudyPanel` → `PanelBody`) — now feeds `TeacherCard`, `CommentaryAccordionRow`, `PastorsNotesSection`, and `useLexiconDefinition`.
- `verseIdStr` — feeds `useInterlinear` and the `selectedStrongs`-reset effect; only the `useTeachersOnVerse` reference to it was removed.

**Proof performed before commit:**
- Zero-hit greps repo-wide for `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, `teacherResults`, `teachersLoading` — confirmed clean.
- `tsc --noEmit` clean; `next build` production build clean.
- Live against local dev (`localhost:3000`, Playwright, guest session): verse card, Interlinear, Commentaries, Pastors' Notes, and pin-click (guest → Beta Access gate, not a crash) all render correctly; "Your teachers on this verse" text confirmed absent; a real Commentaries-row fetch was observed carrying `source_kind_filter=commentary` with **no accompanying `sermon_transcript` request** — direct proof the removed hook no longer fires, not just a code-reading inference. Standalone `/study` page loaded without error, same fail-quiet "No commentary found"/"Couldn't load notes" states as the panel (consistent with this environment's known local-dev-to-production CORS block, not a regression).
- **Caveat, stated plainly:** local dev cannot reach the production backend for authenticated calls (CORS-blocked, a pre-existing constraint this project has hit before — see Phase 7/8/9 entries below, which all needed a real `rhemata.app` session to verify auth-gated behavior). This session's live checks are real but guest/local-only; a full authenticated production re-verification (real commentary/sermon results, Pastors' Notes content) has **not** been done post-removal and would need a push + a real signed-in session on `rhemata.app`, the same as prior SP2/SP4 sessions did.
  - **Closed 2026-07-21** — Alex's SP4 authenticated sign-off pass confirmed this removal live in production (the text is genuinely gone). Full detail in the reconciliation entry at the top of this file.

**Not touched:** SP4's curated `TeacherCard` path (`reference.type === "teacher"`) — a different feature, confirmed unrelated during the audit (disjoint code path, coincidentally similar name).

---

## SP panel refinement — Phase 1: reference-persistence fix (session state, 2026-07-19)

Shipped per `docs/superpowers/plans/2026-07-19-study-panel-refinement.md` (PLAN.md #42.5), following a grill-me interview session that resolved the "clicking does nothing" premise in code before any build work started.

**Root cause, confirmed by direct code trace, not assumed:** `verified_references` (SP1's fail-quiet reference data) and `citations` were computed fresh every chat turn and attached only to that turn's SSE `meta` event (`chat.py:1026-1031`) — never written to the database. `_save_conversation` (`chat.py:445-479`) inserted only `id`, `conversation_id`, `role`, `content` per message; there is no backend `/conversations` endpoint at all — the frontend reads conversation history straight from Supabase (`useConversations.ts`), requesting only `role, content`. Consequence: every reopened conversation lost 100% of its verse/teacher underline clickability and citation pills, regardless of signed-in/guest state or reference type — not the signed-in/guest or verse/teacher distinction the inherited notes assumed. `message_id` turned out to already survive (it's the message row's own `id`); it just wasn't being selected on reload.

**Shipped, commits in order:** plan doc + PLAN.md `#42.5` entry (`0285920`, `166c238`); `.gitignore` entry for `.worktrees/` (`cd9ccd6`); migration `066_messages_reference_data.sql` (`98bb59e` — nullable `messages.citations`, `messages.verified_references` jsonb columns, applied and verified on a fresh connection before commit); `chat.py`'s `_save_conversation` persisting both on the assistant row only (`08b2a7d` — bundled per Alex's explicit call, citations had the identical bug for the identical reason); `useConversations.ts`'s `loadMessages` selecting `id, role, content, citations, verified_references` and mapping them into `Message`'s existing optional fields (`b19f6d0`); this record itself (`a775f86`). Underline's own visual treatment deliberately unchanged (Alex's explicit call — the "not looking tappable" complaint was very likely this same persistence bug, not a separate design issue).

**Live-verified, real evidence (Playwright against `rhemata.app` production, disposable admin-created test account, deleted after — zero residual rows confirmed):**
- Fresh answer to "What does Derek Prince teach about deliverance, based on Romans 8:28?": 4 real underlined spans rendered post-stream (Derek Prince, Romans 8:28 ×2, Joel 2:32); clicking one opened the panel correctly.
- **The actual bug, proven fixed:** clicked "New Chat," then reselected the same conversation from the sidebar — the identical 4 underlines were still present and still genuinely opened the panel on click. This is the literal scenario that was broken before this fix.
- Direct DB query on the same row: `citations` had 8 entries, `verified_references` had 3 (matching the 4 rendered spans — "Romans 8:28" occurs twice in text but resolves to one verified identity, reconciling exactly).
- Guest (unauthenticated) chat streaming confirmed unaffected on production — guests never call `_save_conversation` (`chat.py`'s `if user_id:` branch), so this fix has zero guest-facing surface, confirmed live not just by code-reading.
- Simulated a pre-migration row (nulled `citations`/`verified_references` directly in the DB on a real assistant message) and reloaded it live: zero underlines, plain answer text rendered normally, zero console/page errors. Confirms graceful degradation — this is NOT the same as the spec's "retrofitting old conversations" exclusion (which stays correctly out of scope), it's proof the new code path fails safe on old data shapes.

**Process note:** executed in an isolated git worktree (`.worktrees/sp-panel-refinement-phase1`, branch `sp-panel-refinement-phase1`) per Alex's explicit choice this session (departure from this repo's usual direct-to-main convention), fast-forward-merged into `main` and pushed only after Alex confirmed that was the right way to reach a real deploy for live verification. Worktree removed after merge; branch fully merged, safe to delete.

**Left open, for whoever (or whichever panel) picks this up next:** Phase 2 (floating overlay, desktop only) is scoped and ready in the plan doc but explicitly gated on Alex's own SP4 sign-off (see below) — do not start it before that sign-off is confirmed. Isolated worktree (`sp-panel-refinement-phase1`) and its branch were removed after the fast-forward merge to `main`; nothing dangling. This session did not touch `HARNESS.md` or `ARCHITECTURE.md` — the concurrent records-cleanup session's note below already flags `ARCHITECTURE.md`'s missing `messages.citations`/`verified_references` columns; still true after this session.

---

## Records cleanup + harness write-detection loop fix (session state, 2026-07-19)

Ran chronologically before the SP panel refinement session above (commits
land 15:03–16:02 vs. that session's 17:57–18:44) — inserted here, not at the
top, to keep this file's ordering true to when the work actually happened,
not when it was logged.

**Records-only cleanup — commit `b510b31`.** Reconciled three places PLAN.md
contradicted itself or reality: `sources/` backup marked DONE 2026-07-19
(Google Drive; restore explicitly flagged unverified — not tested), SP2 status
in `docs/inline-study-panel-spec.md` corrected from "NOT yet scheduled or
built" to reflect its actual shipped state, and harness `#5.5` exit condition
(a) corrected from PLAN.md's stale "OPEN" to the CLOSED state confirmed by
direct code read + `git log` (commit `96bc3ff`). No logic/DB changes.

**Read-only PLAN.md-vs-live-DB audit — no file changes, findings unaddressed.**
Compared every DB-checkable claim in PLAN.md against direct live queries.
Most drift is honestly dated-and-labeled (chunk/doc/proposition totals aging
since the 2026-07-14 refresh). Two live findings Alex hasn't acted on yet:
(1) New Wine's "33 articles/9 issues" claim is now 15 docs/8 issues — matches
the SP4 pre-build fix's own 33→15 number below, just never folded back into
PLAN.md `#26`. (2) SermonIndex's "#34 still open" framing is *more* wrong
than PLAN.md itself knows — Carter Conlon (`visibility='shown'`, unlicensed)
now has 6 real ingested documents, contradicting the "only ingested speaker
is hidden, structurally blocked" note under SP2 Phase 7. Propositions count
also dropped 2,488→2,306 since the 07-14 refresh with no documented cause —
worth a look. Full comparison table not persisted anywhere; re-run the audit
if this matters before relying on any PLAN.md count.

**Executor write-detection infinite loop — diagnosed then fixed, commits
`d9ab1cc` (build) + `f1e5184` (records).** Root-caused the 2026-07-18 bug
below by reading the real surviving `/tmp/rhemata-harness-writes` log from
that incident: a benign grep for a bare SQL-verb-shaped pattern
(`"ALTER TABLE..."`) against a directory-only target got recorded as a write
with zero extractable referents, so it could never be "accounted for" by any
report, ever; retries piled up undeduplicated copies of the same
unsatisfiable record forever. Fixed in `deterministic_gate.py` only
(`guard_pretooluse.py` and `check_reconciliation()`'s fallback both
untouched, per explicit scope lock): referent extraction now always yields
something meaningful, and accounting checks the cumulative, deduped text of
everything the finishing agent has said all session, not just its latest
message. Proven via a new `.claude/harness-selftest/test_write_accounting_loop_fix.py`
against the real recorded incident command — loop converges and stays
converged; a genuine undisclosed write still blocks; a genuine disclosed
write still passes. `BASH_WRITE_INDICATORS` deliberately left over-flagging
benign searches (the safe default) — narrowing it is flagged below as its
own future session, not done here.

**Left open, not done this session — flagged for whoever picks this up
next:** `HARNESS.md`'s "Closed" section still doesn't list the loop fix
above (`d9ab1cc`) — that's the durable home for it per HARNESS.md's own
eviction rule; right now the only record is in this file, which gets
reshuffled every session (see this section's own insertion above).
`ARCHITECTURE.md`'s `## Database` table list is also stale — missing
`jewish_perspectives` (still live, 2 rows, confirmed by the audit above),
`study_pins` (SP2 Phase 5), `teacher_profiles` (SP4), and the new
`messages.citations`/`messages.verified_references` columns from the panel
refinement session above. Neither touched this session — Alex hadn't
confirmed he wanted them done yet when this session closed.

---

## SP4 — Teacher Cards (session state, 2026-07-18)

Built per `docs/superpowers/plans/2026-07-18-sp4-teacher-cards.md` (11 tasks),
following the pre-build data fix recorded below. Shipped: migrations `064`
(`teacher_profiles` table + 9-row seed) and `065` (`match_teacher_chunks`
RPC, license-gated); `app/services/llm_client.py` (extracted shared
Anthropic client + guardrails-text loader, also now used by `chat.py`);
`GET /study/teachers` + `GET /study/teacher/{source_id}` (combined
bio/works/live-position-synthesis endpoint, own similarity floor since the
RPC supplies none); frontend curated-teacher detection/verification
(`study-reference.ts`), underline rendering (`chat-message.tsx`), the
`TeacherCard` component, and full wiring through `study-panel.tsx` /
`page.tsx`. All 10 build commits pushed; `origin/main` confirmed at each
step.

**Live-verified, real evidence:**
- Backend: `curl https://rhemata-production.up.railway.app/study/teachers`
  returns all 9 curated teachers with correct `source_id`s, live in
  production — confirmed directly, not assumed from a successful deploy.
- The `TEACHER_POSITION_SIMILARITY_FLOOR = 0.3` value is empirically
  validated against this corpus's real score distribution, not a guess:
  `scripts/test_teacher_card.py` shows an on-topic query's best similarity
  at 0.508 (clears the floor) and an off-topic query's best score at 0.152
  (stays well below it) — this directly closes the gap the 2026-07-18
  pre-build diagnostic flagged (no threshold exists in `match_chunks`/
  `match_teacher_chunks` themselves).
- Frontend, live on `rhemata.app` (real Playwright session, guest/no
  auth): asked "What does Derek Prince teach about deliverance?", waited
  for the real streamed answer to fully stabilize (not a fixed timeout —
  polled until page text stopped changing), confirmed **2 real underlined
  "Derek Prince" buttons** in the rendered answer, exact class match to
  `TeacherReferenceSpan`'s styling. Clicked one: the panel opened with
  header "TEACHER" / "Derek Prince" (confirms correct mode-switch, not the
  verse card, no nesting/back-stack residue). As a guest (no access token),
  the card body read "This teacher's card isn't available right now" —
  honest and non-crashing, not a silently-swallowed fake-empty state (the
  exact bug class Phase 7 found in `pastors_notes.py`), though it doesn't
  specifically prompt sign-in the way some other gated surfaces do — see
  Open Flags below.

**NOT verified this session — needs Alex's own pass, blocked by the Beta
Access gate:** signing up a real disposable test account to check requires
a beta access code this session doesn't have (`Become a test user` → a
`BetaGate` code-entry screen, dead end without the code). Specifically
unverified: (1) real card content for a signed-in user — actual bio text,
a real works-in-corpus list, a real synthesized position; (2) the
Interlinear-width-collapse fix (Task 9) — switching from a verse card with
Interlinear open to a teacher card should snap the panel back to 33vw, not
stay at 50vw; (3) the fail-quiet floor behavior live, end-to-end, on an
authenticated off-topic question (Task 5's script validates the floor
value itself against real scores, but not the full authenticated request
path). None of these are new risks invented for this note — they're the
literal gaps left by not being able to sign in.

**Closed 2026-07-21** — Alex signed in and ran the full authenticated pass:
real card content, the Interlinear-width-collapse behavior, the fail-quiet
floor end-to-end, back-navigation, and keyboard-only nav all confirmed.
Full detail in the reconciliation entry at the top of this file.

---

## SP2 — Inline Study Panel (session state, 2026-07-17)

Phase 7 (Commentaries + Pastors' Notes accordion rows) shipped and live-verified
on `rhemata.app`. Commits `69df175`, `063fcab`, `5c82975`, `0c8b75f`. Separately:
`32f5b25` fixed a Phase 5 defect (pin-cap tooltip still checked `>= 4` after the
real cap moved to 8).

**Found during Phase 7, then fixed same session:** `backend/app/routers/pastors_notes.py`
never imported `get_user_role`, called at 3 sites (`list_cards`, `create_card`,
`update_card`). NameError → 500 on every authenticated `/pastors-notes/cards`
call, 100% reproducible; guests unaffected (they skip that branch). The
frontend's `.catch(() => setCards([]))` silently repainted every crash as an
honest-looking empty state — broken for every signed-in user on the standalone
Study page too, not just the new panel row, for as long as the import gap
existed. Fixed in `5d430b7` (one-line import, plus closes the read-path
silent-swallow with a distinct error state; add/edit/delete already surfaced
real errors correctly and were untouched). Proven live, not just a 200 —
full round trip on `rhemata.app` with a disposable test account (created,
elevated to admin, deleted after): note added, visible after a fresh reload
(real server persistence, not local state), edited, edit visible after a
fresh reload, deleted. Zero residual test data confirmed.

**Attribution correction:** an earlier note this session described leaving
this bug unfixed as "Alex's explicit call." That was wrong — the actual answer
was to a narrower question about touching the backend in that specific moment,
not a decision to leave the bug open. Corrected here; the bug is now fixed.

**Phase 8 (Interlinear + lexicon word study, moved in from the dissolved SP3)
shipped and live-verified on `rhemata.app`, same session.** Commit `9415f11`
— Tasks 28–30 combined into one commit rather than three: the `AccordionRow`
controlled-mode extension and lifting `interlinearOpen` up through
`StudyPanel` to `page.tsx` serve both the row's mount and the width-borrowing
together, and weren't cleanly separable after the fact without redoing
already-correct, already-typechecked work.

- **Interlinear row (Task 28):** `useInterlinear` + `InterlinearBlocks`
  (both Phase 6 extractions), mounted first, before Commentaries. Live on
  Romans 8:28: 18 real Greek tokens rendered, STEPBible/Tyndale House
  attribution visible.
- **Word-study view (Task 29):** tapping a token opens the panel's one
  back-button surface — `WordDefinitionCard` + `useLexiconDefinition`,
  object construction copied exactly from `study/page.tsx`'s own
  interlinear-tap call site (`selectedToken ? {...} : selectedStrongs &&
  lexiconEntry ? {...} : null`). Live: tapped a real token (Strong's
  `G6063`), word-study view opened, Back button returned to the normal row
  view with Interlinear still expanded. STEPBible attribution added to this
  view directly (Phase 2's Task 4 had deferred the panel's copy here) —
  deliberately not baked into `WordDefinitionCard` itself, keeping Phase 6's
  file as Phase 6 left it.
- **Width-borrowing (Task 30):** confirmed live both directions — 422px
  (33vw clamp) collapsed, 640px (50vw clamp) while Interlinear is open,
  automatic, no user toggle.
- **Task 31 (grep):** zero `Translations`/`Cross-references` references
  anywhere in the frontend.
- **Task 32, live, not just structural:** a real, SP1-verified "Genesis
  1:1" underline (from a real streamed chat answer, not the hardcoded dev
  demo reference) opened the panel and showed the honest "No interlinear
  data available for this verse" message — zero fake "coming soon" copy,
  zero Greek tokens for an OT verse. Precept Austin / "From the Library"
  confirmed absent both structurally (`WordDefinitionCard` has no such code
  path — verified by reading its source, not inferred) and live (zero
  matches after tapping a real Greek word).
- **One judgment call made without a plan citation, flagged here rather than
  silently decided:** the word-study view's header has only a Close button,
  no Pin — pins are verse-scoped and still one tap away via Back, so nothing
  is actually lost, just an extra tap. The plan's Task 29 doesn't specify
  either way.

**Phase 9 (keyboard + screen-reader verification) shipped and live-verified on
`rhemata.app`, same session.** Commit `bb8aa43`. Diagnostic-first: audited
read-only, reported 5 confirmed gaps plus 4 confirmed-clean surfaces, stopped
for Alex's go-ahead before touching anything — all 5 confirmed gaps approved
for a fix, all additive, none of the 4 clean surfaces touched.

- **Gap 1 — accordion rows didn't announce open/closed state.** `aria-expanded`
  added to all three `AccordionRow` triggers (Interlinear/Commentaries/
  Pastors' Notes) and to Commentaries' nested per-excerpt toggle. Live,
  before/after a real keyboard toggle: all four went `false → true` correctly.
- **Gap 2 — closing the panel dropped focus to `<body>`.** This panel has no
  `Dialog.Trigger` (opened from verse-underline clicks, the dev button, or a
  keyboard shortcut), so Radix had nothing to restore focus to. Now captures
  `document.activeElement` on open and restores it via `onCloseAutoFocus`
  (Radix's own override point — doesn't touch the focus-trap mechanism, a
  separate concern), falling back to the chat textarea if the original
  element is gone. Live, both close paths tested: clicking the panel's own
  Close button and pressing Escape each correctly returned focus to the
  actual triggering element (the dev button, in both tests).
- **Gap 3 — word-study view lost focus to a generic container, both
  directions.** Entering now focuses the Back button (the one actionable
  element at the top of this back-stack surface); leaving via Back now
  refocuses the *specific* token that was tapped, not just "the row" —
  `data-strongs-token` added to the shared `InterlinearBlocks` (inert
  markup, zero behavior change for the standalone page's existing use),
  read by a `PanelBody` effect that fires once after Back clears the word
  view. Live: tapped a real token (Strong's `G6063`), confirmed focus
  landed on "← Back" on entry, confirmed focus returned to the *exact same*
  `G6063` token button on exit (`data-strongs-token` matched exactly, not
  just "some token"). Falls back to the row view's own container
  (`tabIndex={-1}`) if the exact token isn't found — not separately
  exercised live (no known way to force that path without breaking the
  fetch deliberately), but the fallback ref is real and typechecked.
- **Gap 4 — pin button had no real accessible name, only a `title`
  fallback.** Added `aria-label` mirroring the existing title text. Live:
  confirmed `aria-label="Pin limit reached (8)"` on the live DOM in the
  cap-reached state.
- **Gap 5 — pin-cap message wasn't announced.** Added `role="alert"` (implies
  assertive live-region semantics, fires on insertion — correct for a
  message that auto-dismisses in ~2.5s and can't rely on the user already
  being focused on it). Live: confirmed `role="alert"` on the live DOM
  element, using a real 9th-pin-attempt trigger (8 real seeded pins, a real
  refusal).
- **All 4 previously-clean surfaces re-confirmed unaffected, live:** focus
  trap (25 tabs, no leak), `aria-labelledby`/`aria-describedby` panel
  labeling both present, pin dropdown (real `role="menu"`, opens/closes via
  keyboard), verse underlines (real, keyboard-activatable buttons in a
  fresh answer).
- **Honesty bar, explicit:** every claim above is either real keyboard
  interaction (Tab/Enter/Escape driving the actual page) or live
  accessibility-tree/DOM attribute inspection (`aria-expanded`, `aria-label`,
  `role`, `data-*`) on the deployed site — not source-code inference and not
  a screen-reader run. **No actual screen reader (VoiceOver/NVDA) has been
  run against this panel.** That remains a genuinely open, unproven check —
  logged as a new open flag below, not closed by this session.

**Phase 10 (records correction) DONE, same session — commit `a7417eb`.**
Task 35 (PLAN.md): appended the Phase 7/8/9 completion record to #40 (Steps
1–5 of the task were already recorded by earlier sessions, verified against
PLAN.md's live content rather than assumed — #41's supersession, the
teacher-tap decision, the pin-system redesign, the Precept Austin deferral,
and the Hebrew permission gate were all already present); added the two
still-missing pieces — Step 6 (#33's STEPBible half marked closed, the
openbible.info half stays open) and Step 7 (the SP track intro's "old
/study page untouched" wording marked superseded by Phase 4 + Phase 6,
with the same "behaviorally, not literally" distinction those two phases
already proved live). Task 36 (this file): Open Flags 16/17 were already
closed by the sessions that shipped Phase 1/3 — PLAN.md's own #40 entry
already carries "closes Open Flag 17" inline, nothing further to do there;
added Blocker #14 for the Hebrew permission gate, cross-referencing PLAN.md
Open Decisions #11 per the task's explicit instruction.

**SP2 is now fully done, all 10 phases.** The only two things this build
leaves genuinely open are Blocker #13 (no real screen-reader pass) and
Blocker #14 (Hebrew lexicon permission) — both real, both already logged,
neither invented for this closing note.

---

## SP4 pre-build data fix (session state, 2026-07-18)

5 teachers (Bob Mumford, Ern Baxter, Charles Simpson, Don Basham, Oswald J.
Smith) had no `sources` row and no `source_aliases` entry — all their
documents carried the shared New Wine Magazine `source_id`
(`72b2f583-d7f9-4361-be1c-6d5aebe59fac`). Derek Prince additionally had 5
articles mis-attributed to the same magazine bucket despite having his own
resolved source. Fixed via direct `psycopg2` transactions (one per teacher),
each verified live: licensing columns (`license_status`, `visibility`,
`permission_granted_at`, `permission_contact`, `permission_terms`) copied
verbatim from the magazine row, alias resolution replicated
`reference_verifier.py`'s exact path, identity counts matched, spot-checked
chunks/embeddings unchanged. Independently re-verified against a fresh DB
connection before this record was written, not just taken from the
executor's own report.

- Bob Mumford → new source `e2a4babd-c49f-46b2-940e-9771b95e695f`, 4 docs moved
- Ern Baxter → new source `63bdb33a-f672-415e-a209-0dd12fdf29de`, 2 docs moved
- Charles Simpson → new source `c39c4e62-59f3-4a51-9f86-6d1fbcdc6758`, 4 docs moved
- Don Basham → new source `1870bc05-2583-4f88-a6c3-0f5bd31212b9`, 2 docs moved
- Oswald J. Smith → new source `9baaf49f-f9cd-463c-af8b-88ed5b976eb5`, 1 doc moved
- Derek Prince → 5 stray docs re-pointed to his existing source
  `17be391b-d025-4178-8543-3e84da675c5d`, no new source/alias

New Wine Magazine bucket: 33 → 15 documents. Total `documents` row count
unchanged at 3,817 (no rows created or deleted — every write was a
single-column `source_id` UPDATE). Full 9-teacher audit (identity count vs.
name count) re-run after the fix: every alias resolves, every delta is 0.
SP4 build (#42, teacher card content) is now unblocked on this front — no
remaining hardcoded-bio teacher shares another entity's source_id.

## Known Harness Bugs

- **Executor loop, 2026-07-18 diagnostic — FIXED 2026-07-19, commit
  `d9ab1cc`.** Write-detection gate flagged an already-fully-disclosed
  benign action (failed grep + scratchpad cleanup) for 12 consecutive
  turns, alternating "1 of 9"/"2 of 9" flagged-item counts with no change
  in actions between turns. Root cause, confirmed against the real
  surviving 2026-07-18 write-state log: a benign grep for a bare
  SQL-verb-shaped pattern against a directory-only target got recorded as
  a write with zero extractable referents, so it could never be
  "accounted for" by any report text, and retries piled up undeduplicated
  copies of the same unsatisfiable record forever. Fixed by making
  referent extraction always yield something meaningful (never empty) and
  by checking disclosure cumulatively against everything the finishing
  agent has said all session, deduped, instead of only the latest
  message per turn. Proven via `.claude/harness-selftest/test_write_accounting_loop_fix.py`
  (loop converges and stays converged; a genuine undisclosed write still
  blocks; a genuine disclosed write still passes) — only this is claimed
  fixed, nothing broader. **Does not alter #5.5** — exit condition (a)
  stays closed exactly as PLAN.md records it; this session touched
  neither of its two named bridges. **Does not touch**
  `check_reconciliation()`'s fail-closed fallback (missing session_id /
  unreadable state file) — left exactly as-is, the safe-direction default
  for a different, narrower case.

- **Future session flag: `BASH_WRITE_INDICATORS` still over-flags benign
  searches on purpose.** A grep for a bare SQL-verb-shaped word (e.g.
  "ALTER TABLE") still gets recorded as a write — the 2026-07-19 fix above
  only made that already-flagged record satisfiable and non-looping, it
  did not reduce what gets flagged; over-flagging remains the deliberate
  safe direction (principle 5). Narrowing that classifier so harmless
  searches stop being flagged at all is a separate, higher-risk decision
  (it trades against the explicit "over-recording is safe" design intent)
  — its own dedicated session, weighed on its own, not bundled here.

---

## Open blockers

**1. Dead `~/Desktop/rhemata` path — 8 scripts — DONE 2026-07-22.**
3 scripts (`scrape_youtube.py`, `clean_transcripts.py`, `ingest.py`'s
`DOCS_FOLDER`) had it hardcoded as an actual runtime constant — now derived
from the script's own file location at runtime (`Path(__file__).resolve()`
or the equivalent `os.path` form), so a future repo move can't reintroduce
this. The other 5 (`ingest_tahot.py`, `generate_excerpts.py`,
`extract_book_quotes.py`, `ingest_interlinear.py`,
`test_excerpt_generation.py`) already derived the real path correctly at
runtime — the dead path only appeared in a docstring usage example, replaced
with a relative "run from repo root" instruction. Verified live: each script
runs clean (`--help` or module-level import) from repo root post-fix.
Commit `5bdf720`.

**2. `CommandBlock.tsx` hardcodes `/Users/alexwhitley` — DONE 2026-07-22.**
The file itself no longer exists — it was refactored at some point into
`frontend/components/admin/corpus-data.ts` (data) + `card-modal.tsx`
(rendering), and this blocker's filename had gone stale along with the path
it named. Fixed at the actual current location: 75 command strings in
`corpus-data.ts` had the dead path baked in; centralized into one exported
`REPO_ROOT` constant so a future move is a one-line change instead of a
75-line find/replace. Commit `5bdf720`.

**3. `sources/` backup — DONE 2026-07-19.** Corpus + `ingest_queue.xlsx`
backed up to Google Drive (PLAN.md #1). Restore not yet verified — do not
assume a restore would work until tested. `recovery/` remains a separate,
narrower backup of specific deleted rows only, not the corpus — the two are
not the same thing.

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe, genuinely blocks the 8
further HelloAO commentaries in PLAN.md #27. This is the real chokepoint gap.

**5. `ingest_commentaries.py` — retire-or-rebuild decision, not a conversion.**
Reads a hardcoded `/tmp` SQLite dump; path confirmed absent on this machine.
Hard-shaped to one collection's schema, no scraping or generic-format
capability. Converting it is likely busywork on a script that can no longer run.
Needs a decision from Alex.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace in `docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace in `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill gap.** Unlicensed docs ingested before the wiring have
no propositions. Alias gaps remain for several entities — re-ingesting their
content sentinels silently. Counts unverified; query live.

**9. v4 propositions prompt — decision pending.**
`propositions.py::EXTRACTION_PROMPT_V4` exists (line 76), committed `ff0652c`,
but unwired. v3 remains the default (line 139). Calling v4 requires
`prompt_version="v4"` explicitly. Tested on 18 documents
(`docs/audits/proposition-v3-v4-comparison-2026-07-16.md`): median word count 40 → 60,
still short of the 80–150 target. Adopt, iterate, or discard — and if adopt,
decide on backfill.

**10. Precept Austin raw-source gap.** Fewer raw scrape files remain in
`sources/precept_austin/raw/` than there are ingested documents — some documents
have no local raw backing if re-verification is ever needed. Not cross-checked
against the excerpt-less figure in #8.

**11. `verify_chunk_alignment.py` docstring is stale.** Describes
`shared_ingest.py` insert modes (`psycopg2_batch` / `rest_per_chunk`) that no
longer exist — `insert_mode` was introduced in `fb575ae` (2026-07-13) and
collapsed away in the all-or-nothing rewrite.

**12. `jewish_perspectives` table is orphaned.** 2 rows, zero code references
outside migrations and docs.

**13. SP2 Study Panel — no real screen-reader pass has ever been run.**
Phase 9 (2026-07-17) fixed 5 real keyboard/ARIA gaps and verified them via
real keyboard interaction plus live accessibility-tree/DOM inspection
(`aria-expanded`, `aria-label`, `role`, `data-*` attributes) — that is a
genuine, live-proven check of what a screen reader *would* consume, but it
is not the same as actually running one. No VoiceOver, NVDA, or other
screen reader has been used against this panel. Don't treat Phase 9 as
having closed this — it closed the 5 gaps the structural/keyboard audit
could find and prove; a real screen-reader listen could still surface
things that audit can't (announcement phrasing, reading order, timing).

**14. Hebrew lexicon permission gate — SP2 Study Panel excludes Hebrew
entirely because of this, do not assume it's cleared.** The Hebrew brief
lexicon (TBESH) is NOT covered by the same CC BY 4.0 grant that clears
Greek (TBESG, TFLSJ) — its definitions are third-party (Abridged BDB,
Online Bible) and need Online Bible's own permission before use in any
project. Greek is unaffected; SP2's Interlinear/word-study rows already
only ever render Greek, structurally (confirmed live, Phase 8). Full
reasoning: PLAN.md Open Decisions #11. Gates any future Hebrew
interlinear/word-study work specifically — do not build against TBESH
until that permission is obtained.

---

## Resolved — removed from the blocker list 2026-07-17

- **Quote verifier "blocker" — premise dissolved.** Commit `0af69a6`
  (2026-07-10) retired the verified-verbatim-quote claim from the product
  entirely. `system_prompt.txt`, `POSITIONING.md`, and
  `docs/how-rhemata-handles-sources.md` now state paraphrase-and-cite as the
  live posture and verbatim quoting as future/planned. Nothing is waiting on a
  verifier. The old CLAUDE.md decision entry permitting "verbatim retrieval
  quotes up to 50 words" is stale and was removed.
- **Migration 058 "uncommitted"** — false. Committed `72476b7` (2026-07-09),
  working tree clean.
- **"Only ingest.py converted"** — false. `ingest.py`, `ingest_magazine.py`,
  `ingest_preceptaustin.py`, `ingest_lexicon.py` all route through
  `shared_ingest`. See blockers #4 and #5 for what actually remains.
- **v4 prompt "uncommitted"** — false. Committed `ff0652c`. Unwired is still
  true; see #9.

---

## Undocumented, now known

- `scripts/ingest_lexicon_runner.py` (2026-07-14) — batching/pacing driver over
  `ingest_lexicon`, drives `shared_ingest.ingest_document()` in checkpointed
  slices. Committed, was absent from the scripts table.
- `scripts/verify_chunk_alignment.py` — standalone embedding/content alignment
  spot-checker. Committed, was absent from the scripts table. See #11.

---

## Mobile UI

- **Pass A shipped:** floating-panel chat layout, full-bleed mobile shell,
  bottom tab bar (Study · Chat · Discover) hiding on keyboard focus via
  `ChatFocusContext`, circular floating menu button.
- **Pass B pending:** `UsageRing` was pulled from the mobile top bar and has not
  been remounted in the sidebar drawer.

---

## Next

1. **#13 — route `ingest_helloao.py` through `shared_ingest`.** Sole remaining
   chokepoint conversion. Unblocks HelloAO commentary growth (#27) only, not
   corpus growth generally.
2. **#14 remainder — folder renames** (`lexicon/`→`stepbible/`,
   `documents/`→`inbox/`) + drop `jewish_perspectives` table.
3. **#15 — staging Supabase + backup/restore test.** Gates the core-serving
   band (#16–20).

(#1 — `sources/` backup — DONE 2026-07-19, restore not yet verified; see Open
blockers #3. Oldest item on the plan, no longer next.)

SP track: SP2 done (Phases 1–9), SP3 dissolved 2026-07-15 (absorbed into SP2
Phase 8, shipped `9415f11`). SP4 (teacher card content) shipped 2026-07-18 and
is now fully signed off (Alex's authenticated production pass, 2026-07-21 — all
four checks passed; see the reconciliation entry at the top of this file). SP
panel refinement (#42.5) is also done: Phase 1 (reference-persistence fix)
shipped 2026-07-19; Phase 2 (floating overlay) shipped 2026-07-21 (`fe310e2`),
built but not yet production-verified itself (see above). **Next SP item is #43
(SP5, mobile bottom-sheet)**, which reuses the overlay's shared open/swap/close
model. #38 (SP0 mobile mockup) completion status unverified — confirm before assuming.

#11/#12 are DONE (reuse path resolved 2026-07-13). The old "#11 → #12 → SP3"
chain no longer holds — all three links resolved.
