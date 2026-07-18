# Rhemata — Live Status

Point-in-time state only. Overwritten each session. Never durable truth.
Corpus counts are not recorded here — query live.

Last verified: 2026-07-17 (read-only audit against the repo).

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

SP2 Phases 1–8 are now all shipped. Remaining: Phase 9 (keyboard/screen-reader
verification) and Phase 10 (records correction per Standing Rule #12 — the
PLAN.md updates Task 35/36 describe, not yet done).

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

**3. `sources/` has no backup.** Gitignored, single remote, no backup script or
config anywhere in the repo. Raw corpus exists only on this Mac. `recovery/`
covers specific deleted rows, not the corpus.

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

PLAN.md #11 (reuse-path fix) → gates #12 (lexicon conversion) and the Inline
Study Panel track (SP3).
