# SP4 — Teacher Card Content: Design

Next phase in the Inline Study Panel track (`docs/inline-study-panel-spec.md` line 64) after
SP2's full completion (2026-07-17, all 10 phases). SP3 was already dissolved into SP2 Phase 8
(interlinear/lexicon) — this is genuinely the next open phase, not a renumbering.

## Goal

The panel shows a verse card *or* a teacher card. SP2 built the verse card. This builds the
teacher card: bio, works held in the corpus, and a live-synthesized position on the topic the
user is currently asking about. It also finally wires up teacher-name underlines in chat answers
— SP1 has generated real `{"type": "teacher", ...}` reference pointers since 2026-07-14
(`backend/app/services/reference_verifier.py:249-286`), but SP2 deliberately rendered zero of
them, because there was nothing for a tap to open. There is now.

## Scope decisions (settled during brainstorming, 2026-07-18)

- **Position is live, per-conversation** — synthesized fresh each card-open, not a static bio-level
  summary. Scoped to **the user's current question** (not the specific sentence where the teacher
  was named) — simpler to wire, reuses the same input the main answer already used.
- **Curated subset only** — not every teacher SP1 can resolve gets a card. A teacher needs a real
  `teacher_profiles` row to be tappable at all.
- **Fail-quiet on uncurated teachers** — if SP1 resolves a confident `source_id` match but no
  `teacher_profiles` row exists for it, the mention renders as **plain text**, same treatment as
  an unresolved mention. No half-built cards, no dead taps. This extends the panel's existing hard
  rule ("no confident match = plain text, ever") to mean "no confident *curated* match."
- **Bios are migration/seed-script only this session** — no admin UI. Same authoring model as
  `source_aliases` today (hand-edited/scripted, not a form).
- **One combined endpoint**, not bio+works and position split into two calls. Simpler integration;
  the trade-off is every card-open pays the LLM synthesis cost even if the user never reads that
  far — accepted for v1.
- **No nesting** — the panel shows exactly one card at a time. Tapping a teacher underline while
  a verse card is open replaces it, no back-stack. Matches the spec's literal wording ("a verse
  card... or a teacher card").
- **Planned as one session**, no formal phase-stop boundaries (unlike SP2's 10-phase structure) —
  Alex's call, push through today.

## Data model

New table, one migration:

```sql
CREATE TABLE teacher_profiles (
  source_id   uuid PRIMARY KEY REFERENCES sources(id),
  bio         text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
```

Row exists → teacher is curated → underline is live. No row → plain text. No separate `curated`
flag (dropped during brainstorming — existence of the row *is* the signal).

`source_id` is the same identity SP1's `reference_verifier` already resolves teacher mentions to
via `source_aliases` — no new name-matching layer needed anywhere downstream.

**Migration of existing content:** today's only bios are two hardcoded, duplicated, inconsistently-
shaped arrays: `frontend/app/library/authors/page.tsx:27-37` (`AUTHORS`, has a real `bio` field)
and `frontend/app/library/page.tsx:99+` (`AUTHOR_DATA`, has a `specialty` field instead — not the
same shape, overlapping-but-not-identical set of people). The migration script resolves each name
to its `source_id` via `source_aliases`, prefers the `AUTHORS` array's `bio` field where both exist
(it's the field literally named `bio`), and seeds one row per person into `teacher_profiles`. Any
name that fails to resolve via `source_aliases` gets flagged in the script's output, not silently
dropped or guessed.

## Backend

One new endpoint on the existing `study` router, same home as `/study/commentary` and
`/study/pins`:

```
GET /study/teacher/{source_id}?question=<user's current turn text>
```

Auth: `require_user`, same as `/study/commentary` (Phase 4 precedent) — guests get 401, caught
client-side as an empty/prompt-to-signup state, not a new gap.

Steps, mirroring the existing `/study/commentary` retrieval skeleton
(`backend/app/routers/study.py:582-684`) rather than inventing a new one:

1. **404 if no `teacher_profiles` row** for `source_id` — this endpoint should only ever be
   reachable from an already-curated underline, but defends the contract directly rather than
   trusting the frontend gate alone.
2. **Works in corpus**: query `documents` where `source_id = {source_id}`, applying the exact
   license-gate SQL from `CLAUDE.md` invariant #2 (via the existing `is_chunk_disabled`/gate
   helpers already used in `get_commentary`) — a teacher's gated-off works never appear in the
   list, consistent with every other surface in the product. Capped at 20 titles, most-recent
   first (matches no existing precedent exactly, but is the simplest defensible default — no
   teacher in the corpus today has enough gated-in works for this cap to actually bite; revisit
   if one does).
3. **Position synthesis**:
   - Embed `question` (existing `embed_text`, same as `get_commentary`).
   - Get this teacher's document IDs from step 2 (already gate-filtered), then call
     `match_chunks` with `document_ids` scoped to just those — same `document_ids`-scoping pattern
     already used for commentary's book-level pre-filter (`study.py:628-633`), just scoped by
     source instead of by book.
   - **Fail-quiet on zero relevant chunks**: return `position: null` with an honest empty state
     ("No position found on this from {name}"), not a fabricated-sounding non-answer.
   - One Claude call over the retrieved chunks, **paraphrase-and-cite only** — Rule 11 applies
     here exactly as it does to the main answer stream: no verbatim quotes, ever, grounded
     strictly in chunks belonging to this teacher.
4. Return `{ bio, works: [...], position: str | null }` in one response.

## Frontend

- **Underline gate**: extend `isVerified()` in `frontend/lib/study-reference.ts` — a
  `type: "teacher"` entry only counts as verified-for-underlining if its `source_id` is in a
  curated-set lookup, fetched once per session (same shape as how verse verification already
  works). Everything else about SP1's existing rule (first-mention full-name-underlined, later
  mentions short-form plain) is already correct and untouched — this only adds the curation
  filter on top of it.
- **`TeacherCard` component**: new, lives in the same panel surface as the existing verse card
  (`StudyPanel`/`PanelBody`), not nested under it — tapping a teacher underline replaces whatever
  the panel currently shows. Sections: bio (always present — only curated teachers ever reach this
  component), works-in-corpus (list), position-on-topic (loading → synthesized text, or the fail-
  quiet empty state).
- **Trigger**: tapping a curated teacher underline opens the panel into `TeacherCard` mode, passing
  `source_id` + the current turn's user question (already present in chat state) to the endpoint.
- **Citation styling**: reuse whatever renders paraphrase-and-cite citations in
  `frontend/components/rhemata/chat-message.tsx` for the position text — not a new one-off
  component. Exact reuse point to be confirmed against that file's current structure during
  implementation, not assumed here.

## Error handling / fail-quiet rules (explicit, so none get invented ad hoc later)

- No `teacher_profiles` row → plain text, not an underline. (Frontend gate + backend 404 as a
  defense-in-depth pair.)
- All of a teacher's works gated off under current `safe_mode_on` → works list is empty, position
  synthesis has nothing to draw on → both sections show an honest empty state, not an error.
- Zero relevant chunks for the question → `position: null` + empty-state copy, not a hallucinated
  answer.
- Guest taps a curated teacher underline → same 401-caught-as-empty / signup-prompt pattern as the
  existing "your teachers on this verse" fetch (Phase 4 precedent), not a new auth gap.
- Embedding/search service failure → same 500 pattern already used in `get_commentary`, not a
  silently-swallowed empty state (the exact bug Phase 7 found and fixed in `pastors_notes.py` —
  do not reintroduce a `.catch(() => setEmpty())` that repaints a real error as a fake empty).

## Testing / verification plan

Same live-verification bar the whole SP2 build used — no claim of "done" without it:

- Migration: confirm `teacher_profiles` row count matches resolved-name count from the script's
  own output; spot-check 2-3 rows' `bio` text against the original hardcoded arrays.
- Backend: dry-run the endpoint against a curated teacher with real corpus works, confirm the
  license gate actually excludes a deliberately-gated document (same style of live SQL check
  Phase 7 used before trusting the commentary gate).
- Frontend: real browser session (Playwright, per the CORS-driven pattern established in Phase 3/7
  — localhost can't call production, so this runs against a real deploy), confirming: a curated
  teacher's name underlines and a non-curated one doesn't, in the same real streamed answer;
  tapping opens `TeacherCard` with real bio/works/position; tapping a teacher underline while a
  verse card is open replaces it, no residual verse-card state.
- Keyboard/a11y: extend Phase 9's pattern (aria-expanded, focus capture/restore) to the new card
  rather than treating it as exempt — the panel's existing focus-trap and close-focus-restore
  logic should already generalize, verify it does rather than assuming.

## Explicitly out of scope for this build

- Admin UI for editing bios (deferred — script/SQL only).
- Non-curated teachers ever getting any card (deferred indefinitely, not just this session — the
  product decision is curation-gated, not "curate later, open now").
- Caching/precomputing position synthesis (deferred — on-demand only, per the "keep it simple"
  call on the combined endpoint).
- Mobile-specific teacher card treatment beyond what the existing panel shell already provides.
