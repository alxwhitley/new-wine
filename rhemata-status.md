# Rhemata — Live Status

Point-in-time state only. Overwritten each session. Never durable truth.
Corpus counts are not recorded here — query live.

Last verified: 2026-07-18 (SP4 teacher cards built + partially live-verified).

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

- **Executor loop, 2026-07-18 diagnostic.** Write-detection gate flagged an
  already-fully-disclosed benign action (failed grep + scratchpad cleanup)
  for 12 consecutive turns, alternating "1 of 9"/"2 of 9" flagged-item counts
  with no change in actions between turns. Same general class of issue as
  the `WORK_TYPE`-marker prose-bridge that PLAN.md #5.5 exit condition (a)
  has since closed (commit `96bc3ff`, 2026-07-12) — this 2026-07-18 gap is a
  distinct, unresolved issue, not that bridge reopened. Needs its own
  dedicated harness-fix session — do not bundle into SP4 or any other build
  session.

---

## Open blockers

**1. Dead `~/Desktop/rhemata` path — 8 scripts.** CONFIRMED live.
`scrape_youtube.py` (4 lines), `clean_transcripts.py` (3 lines),
`ingest_tahot.py:9`, `ingest.py:33` (`DOCS_FOLDER`), `generate_excerpts.py:5`,
`extract_book_quotes.py:5`, `ingest_interlinear.py:6`,
`test_excerpt_generation.py:6`. Repo moved to `/Users/alexwhitley/rhemata`
2026-07-06.

**2. `CommandBlock.tsx` hardcodes `/Users/alexwhitley`.** Every pipeline's
command reference in Admin → Corpus → Pipelines — the surface commands actually
get copied from. Separate from #1 and arguably higher-impact. Not previously
documented anywhere.

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
Phase 8, shipped `9415f11`). Next SP item is #42 (SP4, teacher card content) —
its pre-build data-attribution blocker is now fixed (see "SP4 pre-build data
fix" above), so #42 is the live next action with no remaining data blocker.
#38 (SP0 mobile mockup) completion status unverified — confirm before assuming.

#11/#12 are DONE (reuse path resolved 2026-07-13). The old "#11 → #12 → SP3"
chain no longer holds — all three links resolved.
