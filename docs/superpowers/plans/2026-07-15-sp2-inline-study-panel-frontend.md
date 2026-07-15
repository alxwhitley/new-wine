# SP2 — Inline Study Panel Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the already-live Study Panel shell (commit `161c4de`) up to the corrected SP2 spec: a real kill switch, a real trigger (SP1's verified verse data, not a guess), a fixed "your teachers on this verse" (currently a false claim, not just an unwired one — fixed as early as possible, ahead of everything except the safety phases), a rebuilt global/persisted pin system (real for signed-in users, honestly reachable-but-prompting for guests), and three real accordion rows (Interlinear, Commentaries, Pastors' Notes) built by reusing the standalone Study page's already-working components — not rebuilding them.

**Architecture:** This is a delta plan, not a greenfield build. Ten phases, strictly ordered: three safety/legal/trigger-integrity phases first (kill switch, attribution, real verified-verse trigger) with an explicit mid-point stop; then, immediately after — ahead of every other content change — the fix for the false "your teachers" claim, since that falsehood is live in production right now and must be corrected even if the build stops early; then the pin system rebuild; then shared-component extraction; then the two missing accordion rows; then Interlinear + lexicon word study moving in from the dissolved SP3; then a cross-cutting accessibility pass; then the PLAN.md/rhemata-status.md record corrections this build requires by Standing Rule #12.

**Tech Stack:** Next.js 16 (React 19) frontend, FastAPI backend, Supabase (existing `verses`, `sources`, `source_aliases` tables + one new table for pins), no new frontend dependencies.

## Global Constraints

- **Fail-quiet, always:** no confident match = plain text, ever. This governs both the verse-underline swap (Phase 3) and every accordion row's empty state.
- **The panel never acts on its own:** no auto-open, no auto-update, ever.
- **Underlines fade in only after the answer finishes streaming** — this is already true today for verses (confirmed) and stays true; it is never extended to teachers in this phase (see next point).
- **No teacher underlines in SP2.** SP1 resolves teacher pointers correctly today, but nothing renders from them in this phase. An underline is a promise of something to open; a promise that resolves to "not wired up yet" is worse than no underline. The existing teacher-tap placeholder in `study-panel.tsx` gets removed or left permanently unreachable — it must not become reachable through this build.
- **Every row degrades honestly, never breaks.** Any row whose content the license/visibility gate withholds shows an honest empty state, designed in from the start — never fake content, never placeholder copy implying a gate that isn't real. (This is exactly the bug Phase 4 fixes and exactly the bug Phase 8 removes from the Interlinear row's old copy.)
- **No silent no-ops.** A control that appears interactive but does nothing when clicked is its own small dishonesty — the same principle behind fail-quiet and honest empty states, applied to controls, not just content. This governs both the guest pin button (Phase 5) and the pin cap (Phase 5): both must say something true when clicked, never do nothing.
- **Every piece of content the panel shows passes the same license/visibility gate the rest of retrieval enforces.** The panel must never surface content that isn't servable and must never bypass `safe_mode`. (Commentaries are confirmed `public_domain` — see Findings below — so this is structurally satisfied for that row without extra gating logic; Pastors' Notes already has its own role-based gate, reused as-is.)
- **Reuse, never rebuild.** Interlinear, lexicon word-study data, and commentary retrieval already exist and work on the standalone Study page (`frontend/app/study/page.tsx`). This plan extracts and adapts them; it does not reimplement them.
- **The standalone Study page must behave identically after any change that touches shared code — proven, not assumed.** It is the kill switch's fallback destination — if the switch is off, users land there. This applies to two separate pieces of work, each independently proven and separately committed before anything depends on it: the shared-component extraction (Phase 6) and the `/study/commentary` endpoint split (Phase 4) — the split touches the exact lookup the standalone page's Commentary section uses today, so it gets the identical discipline: real before/after comparison against real verses, its own commit, before the frontend work that depends on it begins. This supersedes the SP track's "the old /study page is untouched" wording — record that supersession in PLAN.md (Phase 10).
- **No DB writes via MCP tools.** The new pins table goes through the normal migration file path (`migrations/063_study_pins.sql`), applied the way every other migration in this repo is applied — not through any MCP database-write tool.
- **Styling:** DESIGN.md is the sole styling authority for every new or touched visual element. No hardcoded hex, no JS hover handlers, no inline styles, dark theme only.
- **Out of scope, do not build:** citation-to-source-passage opening, retrofitting old conversations, in-panel text-selection follow-ups, user-selectable translations, SP4 teacher card content, teacher pinning, SP5's mobile drag-to-close gesture (the existing mobile full-screen-sheet behavior from `161c4de` is untouched), Precept Austin anywhere in the panel, Hebrew interlinear/word study, Translations, Cross-references.

## Findings this plan is built on (confirmed against live code/data before writing this plan — not assumed)

- **Lexicon license:** CC BY 4.0, confirmed directly in the STEPBible source file headers (Greek: TBESG, TFLSJ). Not NC. The Hebrew brief lexicon (TBESH) carries an *additional*, separate requirement — its definitions are third-party (Abridged BDB, Online Bible) and need Online Bible's permission before use in any project. This is unrelated to and does not clear via the CC BY grant. Hebrew is out of scope for this entire plan; this gate is recorded in Phase 10, not resolved here.
- **Attribution:** zero visible STEPBible/Tyndale House credit exists anywhere in the live product today (confirmed by searching every frontend page and doc — the only hit is in an admin-only internal file). Phase 2 closes this.
- **Commentaries:** all four sources (Matthew Henry, Adam Clarke, Jamieson-Fausset-Brown, HistoricalChristianFaith) are `public_domain` in the `sources` table — confirmed live. Always servable, never affected by `safe_mode`.
- **`/study/commentary` is currently a single endpoint that merges two different queries** (commentary-source vector search + `match_sermon_chunks_by_ref` for real teacher sermons) into one sorted, paginated list, with no way to request one without the other. Confirmed directly in `backend/app/routers/study.py:581-724`. This is why "your teachers on this verse" cannot be wired to this endpoint unchanged, and why the split (Phase 4) is treated with the same care as a shared-component extraction — it's the same lookup the standalone page already depends on.
- **Pastors' Notes is already a standalone, reusable component** (`frontend/components/rhemata/pastors-notes.tsx`) — it is NOT embedded inside the Study page and needs no extraction. It is fully real and complete (add/edit/delete, role-gated, pending-review state, honest empty state). It is simply never imported into the panel today.
- **No kill switch exists.** Confirmed directly in `frontend/app/page.tsx`'s own code comment: the current trigger is "not a real feature flag... needs a real kill switch before any beta rollout." The dev-only "Study preview" button (`page.tsx` ~line 408) and the Cmd/Ctrl+Shift+S shortcut (`page.tsx` ~line 128) are both unconditionally live in production today, reachable by any visitor.
- **Pin state today is in-memory only**, explicitly commented as such in the code, uncapped by any server-side check, not scoped per conversation despite the old spec's wording, and has no guest-specific handling at all today (the button is unconditionally rendered regardless of auth state, with no signup prompt).
- **Guests can use the product without an account** (6 free queries, confirmed via `GUEST_QUERY_LIMIT` in `chat.py`), so the panel and its pin button are reachable while signed out today — this is a real, live path, not a hypothetical one.
- **Verse underline fade-in is already correctly post-stream-only** (`chat-message.tsx`: `detectVerses = !isStreaming`) and already handles ranges as one reference. This mechanism is reused, not replaced, in Phase 3 — only its *gate* changes, from "looks like a verse" to "SP1 verified this specific verse."
- **The next available migration number is 063** (`062_documents_ingest_completed_at.sql` is the latest on disk).
- **The app's persistent desktop top bar has an existing, currently-empty mount point**: `frontend/app/page.tsx` ~line 279, `<div className="hidden md:flex h-14 shrink-0 items-center px-6 z-30 border-b border-border" />`. This is where Phase 5's pin dropdown mounts.
- **`LoginModal` already accepts an `initialMode: "signin" | "signup"` prop** and is already wired into `page.tsx` via `openAuthGate(mode)`, used today for the guest-query-limit-reached flow (`loginReason` state carries the message shown). Phase 5 reuses this exact mechanism for the guest-pin-attempt prompt rather than building a new one.

---

## Phase 1 — Kill switch (Tasks 1–3)

### Task 1: Add the kill-switch flag and gate every entry path

**Files:**
- Modify: `frontend/app/page.tsx` (dev button, keyboard shortcut, verse-click handler)
- Modify: `frontend/components/rhemata/chat-message.tsx` (underline suppression when off)

**Design:** A single environment-driven flag, e.g. `NEXT_PUBLIC_STUDY_PANEL_ENABLED` (default `"true"` today; set to `"false"` to kill it). When off:
- `detectVerses` in `chat-message.tsx` must be forced `false` regardless of streaming state — no underlines render at all. This follows the same principle Alex stated for teacher taps: an underline that opens to nothing (because the whole panel is off) is worse than no underline. The switch doesn't just block the click handler; it removes the promise entirely.
- The dev "Study preview" button and the Cmd/Ctrl+Shift+S handler in `page.tsx` do not render/register at all when the flag is off (not just disabled-looking — genuinely absent from the DOM and event listeners).
- `handleVerseClick` becomes a no-op when the flag is off, as defense in depth (in case anything else ever calls it).

- [ ] **Step 1: Read the current three call sites in full** (`page.tsx`'s `handleVerseClick`, the dev button JSX, the keydown effect; `chat-message.tsx`'s `detectVerses` line) to confirm exact current wording before editing — do not guess at line numbers, they may have drifted since this plan was written.
- [ ] **Step 2: Add the flag check** — a small shared helper, e.g. `frontend/lib/study-panel-flag.ts`:

```typescript
export function isStudyPanelEnabled(): boolean {
  return process.env.NEXT_PUBLIC_STUDY_PANEL_ENABLED !== "false";
}
```

(Defaults to enabled unless explicitly set to the string `"false"` — matches this repo's existing flag conventions, e.g. `BILLING_ENABLED` in `weekly-limit-card.tsx`.)

- [ ] **Step 3: Gate `chat-message.tsx`'s underline detection**

Find the line `const detectVerses = !isStreaming;` and change to:

```typescript
const detectVerses = !isStreaming && isStudyPanelEnabled();
```

Import `isStudyPanelEnabled` from the new helper.

- [ ] **Step 4: Gate `page.tsx`'s dev button, keyboard shortcut, and click handler**

Wrap the dev button's JSX in `{isStudyPanelEnabled() && (...)}`. Guard the keydown effect's body with an early return if the flag is off. Guard `handleVerseClick`'s body with an early return if the flag is off.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/study-panel-flag.ts frontend/app/page.tsx frontend/components/rhemata/chat-message.tsx
git commit -m "Add Study Panel kill switch, gating every entry path"
```

---

### Task 2: Verify the switch actually closes every path — not by reading code, by testing it

- [ ] **Step 1:** With the flag unset (default enabled), confirm in a running dev server: verse references underline after streaming, the dev button opens the panel, the keyboard shortcut opens the panel.
- [ ] **Step 2:** Set `NEXT_PUBLIC_STUDY_PANEL_ENABLED=false`, restart the dev server, confirm: no verse reference underlines anywhere in a real chat answer, the dev button is absent from the page, the keyboard shortcut does nothing, and manually calling the click handler (if reachable via devtools) is a no-op.
- [ ] **Step 3:** Restore the flag to enabled, confirm normal operation resumes.
- [ ] **Step 4:** Commit any fixes found during verification, with real before/after evidence in the commit message or an accompanying note — this acceptance bar is "verified, not assumed," per the plan's explicit requirement.

---

### Task 3: Set the production default

- [ ] **Step 1:** Confirm with Alex (or per already-given direction) what the *production* Railway/Vercel environment variable should be set to before this ships — the plan defaults the flag to enabled in local dev for testability, but production should start with the switch in whatever state Alex wants beta users to see. Do not assume; this is a deploy-config decision, not a code decision.
- [ ] **Step 2:** Document the flag name and default in `CLAUDE.md`'s Environment Variables section.

---

## Phase 2 — Attribution (Tasks 4–5)

### Task 4: Add a visible STEPBible/Tyndale House credit where lexicon data appears

**Files:**
- Modify: whichever component renders the interlinear row and the word-study view in the panel (built in Phase 8 — if Phase 8 hasn't landed yet in execution order, add this credit to the *standalone* Study page's existing interlinear/word-study rendering first, since that's where the data visibly appears today; extend to the panel's versions when Phase 8 adds them)

**Exact wording** (verbatim from the license header — do not paraphrase):

> Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)

- [ ] **Step 1:** Read the current interlinear/word-study rendering in `frontend/app/study/page.tsx` to find the right, unobtrusive placement (e.g., a small muted-text line near the interlinear row or the word-study panel's footer) — small and contained, not a redesign.
- [ ] **Step 2:** Add the credit line using the exact wording above, styled per DESIGN.md tokens (muted text, no new colors).
- [ ] **Step 3:** Commit.

```bash
git add frontend/app/study/page.tsx
git commit -m "Add visible STEPBible/Tyndale House attribution where lexicon data appears"
```

### Task 5: Add the same credit to the `/sources` page

**Files:**
- Modify: `docs/how-rhemata-handles-sources.md` (canonical content source per CLAUDE.md's directory notes)
- The rendered `/sources` page picks this up automatically per its existing build

- [ ] **Step 1:** Read the current `docs/how-rhemata-handles-sources.md` to find where lexicon/original-language sources are already discussed (or the natural place to add a short line if not).
- [ ] **Step 2:** Add one line crediting STEPBible/Tyndale House, same exact wording as Task 4.
- [ ] **Step 3:** Confirm the rendered `/sources` page reflects the change.
- [ ] **Step 4:** Commit.

```bash
git add docs/how-rhemata-handles-sources.md
git commit -m "Add STEPBible/Tyndale House credit to the /sources page"
```

---

## Phase 3 — Swap the client-side guess for SP1's real verified verses (Tasks 6–8)

### Task 6: Read SP1's verified-reference shape and confirm where it arrives in the frontend today

**Context:** SP1 (already shipped, `backend/app/routers/chat.py`) attaches a `verified_references` array to the final SSE `meta` event, alongside the existing `citations`/`conversation_id`/`message_id` fields. Each verse entry looks like `{"type": "verse", "raw": "Romans 8:28", "positions": [123]}` (a verse's `raw` text and every character-offset position it occurred at in the model's raw answer text — **not** the rendered markdown text, which can differ from the raw text after `ReactMarkdown` processes it). This plan does **not** try to align those backend character offsets with rendered DOM text — that alignment is fragile and was flagged as an open risk in SP1's own final review. Instead:

**Design — allowlist by identity, not by position.** The existing client-side detector (`detectVerseReferences` in `lib/study-reference.ts`) already correctly finds every occurrence of a verse-shaped pattern in the *rendered* text and parses it into `{code, chapter, verseStart, verseEnd}`. Phase 3 keeps that detector exactly as-is for *finding* candidates, but adds a second, required check: a detected candidate only renders as an underline if its parsed `{code, chapter, verseStart, verseEnd}` matches one of the verse entries SP1 verified for this specific message. This sidesteps the character-offset alignment problem entirely — the backend's job is "is this verse real," the frontend's job (unchanged) is "where does this text appear," and the two are joined by verse identity, not by character position.

- [ ] **Step 1:** Read `frontend/hooks/useChat.ts` in full to find where it currently parses the SSE `meta` event (it already reads `citations`, `conversation_id`, `usage`, etc. — confirm the exact parsing site before adding a new field, since this file wasn't re-read line-by-line for this plan).
- [ ] **Step 2:** Confirm `verified_references` is present on the final meta event by running one real chat question through the live `/chat` endpoint and inspecting the SSE stream directly (`curl` or a browser network tab) — do not assume the shape from memory of SP1's plan; confirm it live, since this is the exact kind of assumption this whole delta-planning exercise exists to catch.
- [ ] **Step 3:** Report back (as part of implementation, not blocking the plan) whether the live shape matches what's described above; if it differs, adjust Task 7 accordingly before writing code against a wrong assumption.

### Task 7: Store verified references per message, filter the underline renderer by identity

**Files:**
- Modify: `frontend/hooks/useChat.ts` (store `verified_references` alongside each assistant message)
- Modify: `frontend/lib/study-reference.ts` (add a verse-identity matcher)
- Modify: `frontend/components/rhemata/chat-message.tsx` (pass verified verses down, filter detected candidates)

- [ ] **Step 1:** In `useChat.ts`, extend whatever message-shape type already carries `citations`/`messageId` to also carry `verifiedReferences: Array<{type: string; raw: string; positions?: number[]; position?: number; source_id?: string}>` (or the exact live shape confirmed in Task 6), populated from the meta event exactly like `citations` already is.
- [ ] **Step 2:** In `study-reference.ts`, add:

```typescript
export function isVerified(
  ref: Extract<StudyReference, { type: "verse" }>,
  verifiedRefs: Array<{ type: string; raw: string }>
): boolean {
  return verifiedRefs.some(
    (v) => v.type === "verse" && parseVerseIdentity(v.raw)?.code === ref.code
      && parseVerseIdentity(v.raw)?.chapter === ref.chapter
      && parseVerseIdentity(v.raw)?.verseStart === ref.verseStart
      && parseVerseIdentity(v.raw)?.verseEnd === ref.verseEnd
  );
}
```

(`parseVerseIdentity` reuses the same book-name/range parsing `detectVerseReferences` already does internally — do not write a second parser; factor the existing regex-match-to-identity logic out of `detectVerseReferences` into a small shared function both can call, so there is exactly one place that turns a string like "Romans 8:26-28" into `{code, chapter, verseStart, verseEnd}`.)

- [ ] **Step 3:** In `chat-message.tsx`, thread the message's `verifiedReferences` down to `renderMessageText`/`processChildren`, and change the verse-rendering branch so a detected candidate only becomes a `VerseReferenceSpan` if `isVerified(ref, verifiedReferences)` is true — otherwise it renders as plain text, same as today's "no match" case.
- [ ] **Step 4:** Confirm the kill-switch gate from Phase 1 still short-circuits before any of this runs.
- [ ] **Step 5:** Commit.

```bash
git add frontend/hooks/useChat.ts frontend/lib/study-reference.ts frontend/components/rhemata/chat-message.tsx
git commit -m "SP2: swap client-side verse guessing for SP1's verified references (verses only)"
```

### Task 8: Verify fail-quiet end to end, close Open Flag 17

- [ ] **Step 1:** Ask a real question likely to produce a genuine, resolvable verse mention — confirm it still underlines (same visible behavior as before this swap, now backed by real verification instead of a guess).
- [ ] **Step 2:** Ask a real question likely to produce a vague reference ("that verse," "the passage we discussed") — confirm no underline, matching fail-quiet.
- [ ] **Step 3:** If reachable in a test setup, confirm a reference the writer proposed but SP1 rejected (e.g. a nonexistent verse) never underlines even though it matches the client-side pattern — this is the actual proof the swap closes Open Flag 17, not just "the code compiles."
- [ ] **Step 4:** Update `rhemata-status.md`'s Open Flag 17 to closed, with the commit reference, per Standing Rule #12 (this specific line edit can ride with Phase 10's broader records pass, or land here — controller's call at execution time).

---

## MID-POINT STOP

Everything up to here is safety, legal, and trigger-integrity work: the panel can be switched off completely and verifiably; the lexicon data has real attribution; and the only thing that can ever underline is something SP1 actually verified. **No panel content has changed yet** — the false "your teachers" claim, the missing rows, and the SP3 tool-row stubs are all still exactly as found. This is a safe, reviewable state to pause. The very next phase after this stop fixes the live falsehood — deliberately sequenced ahead of the pin system and everything else, since that falsehood is in production right now and must be corrected even if the build stops here and doesn't resume for a while.

---

## Phase 4 — Fix "your teachers on this verse" (Tasks 9–12)

**This is the highest-priority content fix in this build, and it runs immediately after the safety phases — ahead of the pin system, ahead of everything else.** The current panel doesn't just lack this feature — it actively states a falsehood ("None of your teachers address this verse directly yet") on every single verse, unconditionally, without ever checking. That's live in production right now, on the line carrying the product's core differentiator. If this build stops early or runs long, this is the one thing that must already be fixed.

The fix requires a small backend change to a shared endpoint (`/study/commentary`) that the standalone Study page's Commentary section also depends on today. That endpoint split gets the same protection as a component extraction: proven not to change the standalone page's behavior, committed on its own, before the frontend fix that depends on it.

### Task 9: Add the source-kind filter to `/study/commentary`

**Files:**
- Modify: `backend/app/routers/study.py` (the `get_commentary` function, `~line 581`)

- [ ] **Step 1:** Read the current function in full (already quoted above in Findings — re-read live to confirm no drift before editing).
- [ ] **Step 2:** Add an optional query parameter:

```python
async def get_commentary(
    verse_text: str = Query(...),
    offset: int = Query(0, ge=0),
    verse_id: Optional[str] = Query(None),
    source_kind_filter: Optional[str] = Query(
        None, description="'commentary' or 'sermon_transcript' — restricts to one source; omit for both (current behavior, unchanged)"
    ),
    user_id: str = Depends(require_user),
):
```

- [ ] **Step 3:** Guard the commentary-query block (`Step 1+2` and `Step 3` in the existing code) with `if source_kind_filter in (None, "commentary"):` — skip entirely when the filter is `"sermon_transcript"`.
- [ ] **Step 4:** Guard the sermon-query block (`--- Sermon results ---`) with `if verse_id and source_kind_filter in (None, "sermon_transcript"):` — skip entirely when the filter is `"commentary"`.
- [ ] **Step 5:** Everything else (scoring, sort, pagination, neighbor-content fetch) stays untouched. When `source_kind_filter` is omitted, the code path is identical to today's — this is what Task 10 proves, not assumes.
- [ ] **Step 6:** Commit — this task is the code change only; do not fold Task 10's proof into this same commit, so the "split landed" and "split proven safe" states are each independently visible in history.

```bash
git add backend/app/routers/study.py
git commit -m "Add optional source_kind_filter to /study/commentary — no change to default behavior"
```

### Task 10: Prove the split doesn't change Study mode's commentary behavior — separately committed, before anything depends on it

**Why this is its own task, not folded into Task 9:** this endpoint is the exact lookup the standalone Study page's Commentary section uses today. If the split is wrong, Study mode's commentary silently loses content or starts showing teachers where commentary should be — and Study mode is exactly where the kill switch sends users when it's off. It cannot be the thing that breaks. This gets the identical discipline as the shared-component extraction in Phase 6: real before/after comparison against real verses, not an assumption that "the code looks right."

- [ ] **Step 1:** Before Task 9's change (or against the pre-split commit), record real behavior for at least three verses confirmed to return a mix of commentary and sermon results today: the exact set of authors, titles, excerpt text, ordering, and `has_more`/pagination state for `verse_text`/`verse_id` with no `source_kind_filter` passed (i.e., exactly how the standalone page calls it).
- [ ] **Step 2:** After Task 9 lands, repeat the exact same three calls (still with no `source_kind_filter` — the standalone page never passes one), and confirm byte-for-byte identical results: same authors, same excerpts, same order, same pagination, nothing added or missing.
- [ ] **Step 3:** Also confirm, for the same three verses, that passing `source_kind_filter=commentary` returns only `source_kind: "commentary"` entries and `source_kind_filter=sermon_transcript` returns only `source_kind: "sermon_transcript"` entries — proving the split actually separates the two, not just that the unfiltered path is unaffected.
- [ ] **Step 4:** Only once both are confirmed, this task is done. Commit a short note recording the specific verses checked and the identical-output confirmation (or fold into the ledger if executed via subagent-driven-development) — this is the acceptance gate for Task 11, which must not begin until this is confirmed.

### Task 11: Wire the panel's verse card to the real, correctly-filtered query

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx` (`PanelBody`'s "Your teachers on this verse" block)

**Design note:** this fix does not wait on or depend on the shared-component extraction (Phase 6) — it uses its own small, self-contained fetch call directly in `study-panel.tsx`, matching the pattern the panel's existing `useVerseText` hook already establishes (a panel-specific fetch hook, not shared with the standalone page). When Phase 6/7 build the Commentaries accordion row with a shared `useCommentarySearch` hook, that hook can optionally be consolidated with this one — not required for correctness, just a nice-to-have noted for whoever does that work.

- [ ] **Step 1:** Read the current hardcoded block (`study-panel.tsx` ~lines 182-190) to confirm exact current text before replacing it.
- [ ] **Step 2:** Add a small fetch hook (e.g. `useTeachersOnVerse(verseText, verseId)`, living directly in `study-panel.tsx` or a small adjacent file) calling `GET /study/commentary?verse_text=...&verse_id=...&source_kind_filter=sermon_transcript`.
- [ ] **Step 3:** Render: loading skeleton while fetching; real results (author, excerpt) when present; the **same honest empty-state wording as today** ("None of your teachers address this verse directly yet. Content is added daily.") only when the real query genuinely returns zero results — not unconditionally.
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: wire 'your teachers on this verse' to a real, teacher-only query"
```

### Task 12: Prove the fix is real, not just relabeled

- [ ] **Step 1:** Find (via a direct DB query or the standalone Study page) a real verse with confirmed sermon-source commentary results today — open that verse in the panel, confirm real teacher content now appears where the false empty state used to be.
- [ ] **Step 2:** Find a verse genuinely without sermon coverage — confirm the honest empty state still appears, and confirm (by checking the network response) that this is because the query returned zero results, not because the code path is unreachable or hardcoded.
- [ ] **Step 3:** Confirm no classical commentary author (Matthew Henry, Adam Clarke, etc.) ever appears under "your teachers on this verse" — this is the exact positioning failure this phase exists to prevent.

---

## Phase 5 — Pin system rebuild (Tasks 13–19)

Global, database-backed, cap of 8, dropdown re-entry — supersedes PLAN.md #40 and the spec's per-conversation/cap-4/edge-tab design entirely (recorded in Phase 10). Verses only; teacher pinning is not built now, since there is nothing yet for a pinned teacher reference to open (SP4's job). Reachable while signed out — the pin button is never hidden from a guest, and a guest attempting to pin is prompted to sign up, not silently ignored.

### Task 13: Migration — `study_pins` table

**Files:**
- Create: `migrations/063_study_pins.sql`

- [ ] **Step 1:** Write the migration

```sql
-- Migration 063: study_pins table for the SP2 global, account-level pin system.
-- Supersedes the SP0/161c4de in-memory, per-session pin state and the
-- inline-study-panel-spec's per-conversation/cap-4 design (see PLAN.md).
-- reference_type is deliberately a checked, extensible column: SP2 only ever
-- writes 'verse'; SP4 adds 'teacher' later without a schema change beyond
-- widening this CHECK constraint.

CREATE TABLE study_pins (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  reference_type  text NOT NULL DEFAULT 'verse' CHECK (reference_type IN ('verse')),
  verse_id        text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, reference_type, verse_id)
);

CREATE INDEX study_pins_user_id_idx ON study_pins (user_id);

ALTER TABLE study_pins ENABLE ROW LEVEL SECURITY;

-- Users manage only their own pins. Service-role (backend) bypasses RLS as usual.
CREATE POLICY study_pins_own_rows ON study_pins
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
```

- [ ] **Step 2:** Apply the migration per this repo's normal path (Supabase SQL editor, per CLAUDE.md's migration convention — not an MCP write tool).
- [ ] **Step 3:** Verify live: `SELECT to_regclass('public.study_pins')` returns non-null, on a fresh connection.
- [ ] **Step 4:** Commit.

```bash
git add migrations/063_study_pins.sql
git commit -m "Add study_pins table for SP2's global, account-level pin system"
```

### Task 14: Backend pin endpoints

**Files:**
- Modify: `backend/app/routers/study.py` (add three routes)

- [ ] **Step 1:** Add, following this file's existing `require_user` pattern (e.g. the `/study/lexicon` route):

```python
class PinCreate(BaseModel):
    verse_id: str


@router.get("/pins")
async def list_pins(user_id: str = Depends(require_user)):
    db = get_supabase()
    result = (
        db.table("study_pins")
        .select("id, verse_id, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    return {"pins": result.data or []}


@router.post("/pins")
async def create_pin(body: PinCreate, user_id: str = Depends(require_user)):
    db = get_supabase()
    existing = db.table("study_pins").select("id").eq("user_id", user_id).execute()
    if len(existing.data or []) >= 8:
        raise HTTPException(status_code=409, detail="pin_cap_reached")
    result = (
        db.table("study_pins")
        .insert({"user_id": user_id, "verse_id": body.verse_id})
        .execute()
    )
    return result.data[0] if result.data else {}


@router.delete("/pins/{pin_id}")
async def delete_pin(pin_id: str, user_id: str = Depends(require_user)):
    db = get_supabase()
    db.table("study_pins").delete().eq("id", pin_id).eq("user_id", user_id).execute()
    return {"ok": True}
```

The cap is enforced **server-side** here, not just in the frontend — matching this project's established fail-closed convention. A straightforward count-then-insert is sufficient here since pin creation isn't a contended, high-frequency path.

- [ ] **Step 2:** Confirm `PinCreate` and `HTTPException` are already imported in `study.py` (they likely are, given the file's existing patterns) — add imports only if actually missing.
- [ ] **Step 3:** Commit.

```bash
git add backend/app/routers/study.py
git commit -m "Add GET/POST /study/pins and DELETE /study/pins/{id}"
```

### Task 15: Frontend — real pin state, fetched and persisted, for signed-in users

**Files:**
- Modify: `frontend/app/page.tsx` (replace in-memory `studyPins` state)

- [ ] **Step 1:** Read the current `studyPins`/`handleToggleStudyPin` block in full (page.tsx ~lines 91-123) to confirm exact current shape before replacing it.
- [ ] **Step 2:** Replace the in-memory `useState<StudyReference[]>([])` with: fetch `GET /study/pins` on mount when a user is authenticated (empty list when signed out — Task 16 handles the guest interaction, not this task).
- [ ] **Step 3:** `handleToggleStudyPin`, for a signed-in user: if already pinned, call `DELETE /study/pins/{id}` and remove from local state; if not pinned and under cap, call `POST /study/pins` and add the server's returned row to local state; if not pinned and at cap (8), do not silently no-op — see Task 17 for the required, real message.
- [ ] **Step 4:** Commit.

```bash
git add frontend/app/page.tsx
git commit -m "SP2: back the pin system with real, persisted account-level storage"
```

### Task 16: Guest pin behavior — visible, never hidden, prompts signup, and lands after signup

**Files:**
- Modify: `frontend/app/page.tsx` (`handleToggleStudyPin`)
- Modify: `frontend/components/rhemata/study-panel.tsx` if the pin button needs any guest-aware prop (likely not — the decision of "signed in or not" belongs in `page.tsx`'s handler, not the button itself)

**Design (Alex's explicit call):** the pin button is never hidden or greyed out for a signed-out guest — it looks and behaves like a normal button. Clicking it as a guest opens the existing `LoginModal` in signup mode (reusing `openAuthGate("signup")`, the same mechanism already used for the guest-query-limit flow), not a new custom prompt. **The pin lands automatically once signup succeeds — the guest does not have to re-pin.** This is a small, contained addition (a single pending-pin value held across the signup interaction), not a large one, so it's built rather than deferred to a re-pin fallback.

- [ ] **Step 1:** Read `page.tsx`'s current `openAuthGate` function and the `onSignUp` wiring passed to `LoginModal` (and `useAuth.ts`'s signup success path) in full, to confirm the exact shape of the success callback before building on top of it — this hasn't been read line-by-line for this plan.
- [ ] **Step 2:** In `handleToggleStudyPin`, when called while signed out: store the reference being pinned in `sessionStorage` under a dedicated key (e.g. `"rhemata_pending_pin"`, storing the verse identity, not the whole `StudyReference` object, to keep it small and unambiguous), then call `openAuthGate("signup")` instead of touching the pin API.
- [ ] **Step 3:** In the signup-success path (wherever `onSignUp`'s success currently resolves in `page.tsx`/`useAuth.ts`), after the user is confirmed authenticated: check for `"rhemata_pending_pin"` in `sessionStorage`; if present, immediately call `POST /study/pins` with it, add the result to local pin state, and clear the sessionStorage key. If the call fails (e.g. cap already reached from another device), fail quietly here — do not block the signup flow itself, just leave the pin unpinned and clear the pending key.
- [ ] **Step 4:** Commit.

```bash
git add frontend/app/page.tsx
git commit -m "SP2: guest pin attempts prompt signup via LoginModal; the pin lands automatically after signup"
```

### Task 17: Pin cap — a real, visible message when the 9th pin is attempted

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx` (the pin/unpin button in `PanelBody`)

**Design:** a disabled button with only a hover tooltip is not enough — a touch user (or anyone who doesn't hover before tapping) would experience it as a silent no-op, which the plan's constraints explicitly forbid. The button stays clickable even at cap; clicking it at cap shows a brief, real, visible message rather than doing nothing. Reuse this codebase's existing lightweight transient-message pattern (`chat-message.tsx`'s `FeedbackButtons` component already shows a brief "Thanks for the feedback" confirmation via a timed state flip — same shape, different text) rather than introducing a new toast system.

- [ ] **Step 1:** Read the current pin button in `PanelBody` (the `Pin`/`PinOff` button, `title={isPinned ? "Unpin" : pinDisabled ? "Pin stack full (4 max)" : "Pin"}`) in full.
- [ ] **Step 2:** Update the cap number in the existing tooltip text from 4 to 8 (tooltip stays as a secondary affordance, not the only one).
- [ ] **Step 3:** Add a transient, visible confirmation: when the button is clicked while at cap, show a brief inline message near the button (e.g. "Pin limit reached (8) — unpin something first") for a couple of seconds, using the same `useState` + `setTimeout` shape `FeedbackButtons` already uses for its own transient message.
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: real, visible message when the pin cap (8) is reached — never a silent no-op"
```

### Task 18: Pin dropdown, replacing the edge tab

**Files:**
- Create: `frontend/components/rhemata/pin-dropdown.tsx`
- Modify: `frontend/app/page.tsx` (mount in the existing empty top-bar div, ~line 279; remove `StudyPanelEdgeTab` usage)
- Modify: `frontend/components/rhemata/study-panel.tsx` (remove the `StudyPanelEdgeTab` export and its component — this is a rebuild, not a tweak, per Alex's explicit instruction)

- [ ] **Step 1:** Build `PinDropdown` — a bookmark-icon button that opens a small dropdown listing current pins (verse reference label per pin), reachable regardless of which conversation is active. Clicking a pinned item calls the same `handleVerseClick`-shaped handler used everywhere else, opening the panel to that reference. For a signed-out guest with no pins, the dropdown can still be present but will simply be empty (or show a short "sign in to save verses" line) — it is not itself the guest-prompt surface; that's the pin button inside the panel (Task 16).
- [ ] **Step 2:** Mount it in `page.tsx`'s existing top-bar div (~line 279), which is currently empty — do not create a new top-bar region.
- [ ] **Step 3:** Confirm clicking outside the panel (including while the pin dropdown is open) closes the whole panel, dropdown included — per Alex's explicit requirement. This likely falls out of the existing Radix Dialog's outside-click behavior if the dropdown is rendered as part of the panel's own interaction tree, or needs an explicit close call if the dropdown is a fully separate component — confirm which, empirically, once built.
- [ ] **Step 4:** Delete `StudyPanelEdgeTab` from `study-panel.tsx` and its import/usage in `page.tsx`.
- [ ] **Step 5:** Commit.

```bash
git add frontend/components/rhemata/pin-dropdown.tsx frontend/app/page.tsx frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: replace the pin edge-tab with a top-bar bookmark dropdown"
```

### Task 19: Verify real persistence, guest behavior, and the cap message — not by code inspection

- [ ] **Step 1:** Signed in: pin two verses, refresh the page, confirm both pins are still present (fetched from the server, not lost).
- [ ] **Step 2:** Sign out and back in (or open a fresh session), confirm the same pins appear — this is the actual proof of "follows you across devices/sessions," not an assumption from reading the endpoint code.
- [ ] **Step 3:** Pin 8 verses, attempt a 9th: confirm the real, visible "limit reached" message appears (Task 17), not a silent no-op.
- [ ] **Step 4:** Switch to a different conversation, confirm the SAME pins still show in the dropdown (global, not per-conversation).
- [ ] **Step 5:** Signed out: confirm the pin button is visibly present and normal-looking (not hidden, not greyed out) on a verse card. Click it, confirm `LoginModal` opens in signup mode. Complete a real signup, confirm the originally-attempted verse is now pinned without any manual re-pinning step.

---

## Phase 6 — Shared-component extraction (Tasks 20–23)

**This is its own phase for a reason stated in the Global Constraints:** the standalone Study page is the kill switch's fallback. Extraction must be proven to leave it behaving identically, committed alone, before Phases 7–8 (which consume the extracted pieces) begin. (The `/study/commentary` endpoint split already received this same discipline in Phase 4, ahead of everything else, since it was the most time-sensitive fix in this build — this phase applies it to the remaining shared frontend pieces.)

**Scope correction from the original framing:** Pastors' Notes needs **no extraction** — it's already a standalone component (`components/rhemata/pastors-notes.tsx`), simply not yet imported into the panel (that happens in Phase 7). Only three things actually need pulling out of `app/study/page.tsx`: the interlinear renderer + its fetch, the lexicon word-definition rendering (deliberately *without* the Precept Austin excerpt block, which stays Study-page-only), and the commentary *data-fetching* (its rendering stays page-specific for the standalone page; the panel gets new inline-expand rendering in Phase 7, per Alex's decision, sharing only the fetch logic).

### Task 20: Extract the interlinear component + fetch

**Files:**
- Create: `frontend/components/rhemata/interlinear-blocks.tsx` (move `InterlinearBlocks` here, unchanged)
- Create: `frontend/hooks/useInterlinear.ts` (extract the `/study/interlinear` fetch effect currently inline in `study/page.tsx`)
- Modify: `frontend/app/study/page.tsx` (import both instead of defining them locally)

- [ ] **Step 1:** Read the current `InterlinearBlocks` function and its surrounding fetch `useEffect` in full (`study/page.tsx` ~lines 506-567 and ~1034-1056) to confirm exact current behavior before moving anything.
- [ ] **Step 2:** Move `InterlinearBlocks` verbatim into the new file, exporting it. Extract the fetch effect into `useInterlinear(verseId: string | null): { tokens: WordToken[]; loading: boolean; isNT: boolean }`, verbatim logic, just relocated.
- [ ] **Step 3:** Update `study/page.tsx` to import both and use the hook instead of its inline effect — no behavior change, purely a relocation.
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/interlinear-blocks.tsx frontend/hooks/useInterlinear.ts frontend/app/study/page.tsx
git commit -m "Extract InterlinearBlocks + its fetch into shared, reusable pieces"
```

### Task 21: Extract the lexicon word-definition rendering (no Precept Austin)

**Files:**
- Create: `frontend/components/rhemata/word-definition-card.tsx`
- Create: `frontend/hooks/useLexiconDefinition.ts`
- Modify: `frontend/app/study/page.tsx`

- [ ] **Step 1:** Read the current lexicon-fetch effects (`study/page.tsx` ~lines 1119-1141) and the definition-parsing logic (~lines 1244-1284) in full.
- [ ] **Step 2:** Extract `useLexiconDefinition(strongs: string | null): WordDefinition | null` — the fetch + the colon/dot parsing logic that turns raw lexicon text into `{gloss, lexiconDefinition, meaning}`, verbatim.
- [ ] **Step 3:** Build `WordDefinitionCard` as a new, small component rendering just: word, transliteration, Strong's number, gloss, definition, usage — the lexicon-only subset of what `InlineWordPanel` currently renders. Deliberately do **not** include the Precept Austin excerpt block or the "From the Library" corpus-results section — those stay exclusively in the standalone page's `InlineWordPanel`, untouched.
- [ ] **Step 4:** Update `study/page.tsx` to use the new hook internally where it previously inlined the same logic (its own rendering, `InlineWordPanel`, stays as-is — only the underlying fetch/parse logic is deduplicated, not the JSX).
- [ ] **Step 5:** Commit.

```bash
git add frontend/components/rhemata/word-definition-card.tsx frontend/hooks/useLexiconDefinition.ts frontend/app/study/page.tsx
git commit -m "Extract lexicon word-definition fetch/parse and a PA-free rendering component"
```

### Task 22: Extract commentary data-fetching (rendering stays page-specific)

**Files:**
- Create: `frontend/hooks/useCommentarySearch.ts`
- Modify: `frontend/app/study/page.tsx`

- [ ] **Step 1:** Read the current `fetchCommentary` callback and its surrounding state (`study/page.tsx` ~lines 1143-1176) in full.
- [ ] **Step 2:** Extract into `useCommentarySearch(verseText: string | null, verseId: string | null, sourceKindFilter?: "commentary" | "sermon_transcript")` returning `{results, loading, loadingMore, hasMore, loadMore}` — verbatim fetch logic, plus passing the `source_kind_filter` param through to the backend call (already live since Phase 4's Task 9).
- [ ] **Step 3:** Update `study/page.tsx`'s `CommentarySection` to consume the hook instead of its inline state/effect — the component's own rendering (list, `activeCommentary` toggle, Back link, flagging) stays completely unchanged. Only the data-fetching moved.
- [ ] **Step 4 (optional, not required for correctness):** if convenient, note whether Phase 4's `useTeachersOnVerse` (Task 11) could be consolidated into this hook (both call the same endpoint with different filters) — leave as a follow-up note if consolidating would require touching Phase 4's already-shipped, already-verified code; do not force it.
- [ ] **Step 5:** Commit.

```bash
git add frontend/hooks/useCommentarySearch.ts frontend/app/study/page.tsx
git commit -m "Extract commentary search into a shared hook; standalone page's rendering unchanged"
```

### Task 23: Prove the standalone Study page behaves identically — the acceptance gate for this whole phase

- [ ] **Step 1:** Before touching anything (or from the pre-extraction commit, via `git stash`/a side-by-side checkout), record real behavior for at least three verses: one NT verse with interlinear tokens, one word with a real lexicon definition and a Precept Austin excerpt, one verse with real commentary results spanning both commentary and sermon sources. Screenshot or transcribe the exact rendered output.
- [ ] **Step 2:** After all three extraction tasks (20–22) land, repeat the exact same three checks against the post-extraction code.
- [ ] **Step 3:** Confirm byte-for-byte/pixel-for-pixel identical output for all three cases. Any difference is a regression in this phase, not something to wave through — fix before proceeding to Phase 7.
- [ ] **Step 4:** Only once confirmed identical, this phase is done — commit a short note (or fold into the ledger if executed via subagent-driven-development) recording the specific verses/words checked and the identical-output confirmation.

---

## Phase 7 — Add the missing rows: Commentaries and Pastors' Notes (Tasks 24–27)

### Task 24: Build the shared accordion row shell

**Files:**
- Create: `frontend/components/rhemata/accordion-row.tsx`
- Modify: `frontend/components/rhemata/study-panel.tsx` (remove `ToolRowStub`, its "coming soon" copy, and its three current usages — Interlinear/Translations/Cross-references)

- [ ] **Step 1:** Build `AccordionRow` — closed by default, a label + chevron that opens/closes on click, matching `ToolRowStub`'s existing visual shape (border-b, chevron rotation) but generic (accepts `children` to render when open, instead of hardcoded "coming soon" text).
- [ ] **Step 2:** Delete `ToolRowStub` and its three call sites in `PanelBody`.
- [ ] **Step 3:** Commit (this task only removes the old stub scaffold and adds the new shell — the real rows are Tasks 25/26 and Phase 8's Task 28).

```bash
git add frontend/components/rhemata/accordion-row.tsx frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: replace ToolRowStub with a real AccordionRow shell; remove Translations/Cross-references"
```

### Task 25: Commentaries accordion row — inline expand/collapse, no Back button

**Files:**
- Create: `frontend/components/rhemata/commentary-accordion-row.tsx`
- Modify: `frontend/components/rhemata/study-panel.tsx` (add the row)

**Design (per Alex's confirmed decision):** unlike the standalone page's list→detail+Back pattern, this row shows the list of commentary excerpts, and tapping one **expands its full text inline in place** (pushing the rest of the row's content down), with the same tap collapsing it again. No screen change, no Back link — this keeps the panel's word-study view (Phase 8) as the only back-button surface.

- [ ] **Step 1:** Build `CommentaryAccordionRow` using `useCommentarySearch(verseText, verseId, "commentary")` (Task 22 + Phase 4's filter).
- [ ] **Step 2:** List view: same excerpt-preview cards as the standalone page's list state (author, title, excerpt), minus the flagging UI (out of scope for this row unless Alex wants it carried over — default to omitting it here, since flagging isn't part of the spec's panel description; note this as a deliberate scope decision, not an oversight).
- [ ] **Step 3:** Tapping an excerpt toggles an expanded state for that specific item, rendering its full content inline (reuse the standalone page's content-formatting logic — the header/lemma-splitting regex block — factored out if practical, or duplicated once with a comment pointing at the original if factoring is awkward given the differing container shapes).
- [ ] **Step 4:** Mount as the second `AccordionRow` in `PanelBody`, after Interlinear (added in Phase 8) — if Phase 8 hasn't landed yet at this point in execution, mount it as the first row and reorder once Interlinear lands, so the final order is Interlinear → Commentaries → Pastors' Notes as specified.
- [ ] **Step 5:** Commit.

```bash
git add frontend/components/rhemata/commentary-accordion-row.tsx frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: add Commentaries accordion row with inline expand/collapse"
```

### Task 26: Pastors' Notes accordion row — direct reuse

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx`

- [ ] **Step 1:** Import the existing `PastorsNotesSection` (`components/rhemata/pastors-notes.tsx`) directly — no extraction needed, confirmed in Phase 6's findings.
- [ ] **Step 2:** Wrap it in an `AccordionRow` labeled "Pastors' Notes," passing the same props the standalone page already passes (`verseId`, `accessToken`, `role`, `userId`) — `PanelBody` will need access to the user's role and access token, which may require threading a bit further down than it currently goes; confirm this against the actual current prop chain before assuming it's a one-line change.
- [ ] **Step 3:** Mount as the third accordion row, after Commentaries.
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: add Pastors' Notes accordion row, reusing the existing component as-is"
```

### Task 27: Verify both rows respect the license/visibility gate

- [ ] **Step 1:** Confirm Commentaries row content never disappears due to `safe_mode` (all four sources are `public_domain`, confirmed in Findings — this should hold structurally, verify it does in practice with `safe_mode` on).
- [ ] **Step 2:** Confirm Pastors' Notes row correctly hides the "add note" affordance for a non-contributor/non-admin user, and shows the honest empty state for a verse with no notes yet — reusing the component's already-correct behavior, not new logic.

---

## Phase 8 — Interlinear + lexicon word study move in from the dissolved SP3 (Tasks 28–32)

### Task 28: Real Interlinear accordion row, remove the false "coming soon" copy

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx`

- [ ] **Step 1:** Replace the Interlinear `ToolRowStub` (already removed structurally in Task 24 — this task adds the real content) with an `AccordionRow` wrapping the extracted `InterlinearBlocks` (Task 20) + `useInterlinear` hook, fed the panel's current verse.
- [ ] **Step 2:** Confirm the false "Coming soon — interlinear needs the original-language corpus fully tagged first" copy is gone from the entire codebase, not just hidden — grep for the string to confirm.
- [ ] **Step 3:** For an OT (Hebrew) verse, confirm the row shows the same honest "No interlinear data available for this verse" message the standalone page already shows for OT books — not a new fake "coming soon" message. This is the correct, honest behavior for a genuinely out-of-scope case, and it already exists; do not build anything new for Hebrew.
- [ ] **Step 4:** Mount as the first accordion row.
- [ ] **Step 5:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: real Interlinear accordion row (Greek), false 'coming soon' copy removed"
```

### Task 29: Lexicon-driven word study — the panel's one back-button surface

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx` (or a new small view component if the back-button state is cleaner as its own piece — controller's call at implementation time, guided by keeping `PanelBody` from growing unwieldy)

- [ ] **Step 1:** When a word in the Interlinear row is tapped, open a view built from `WordDefinitionCard` (Task 21) + `useLexiconDefinition` — root/gloss, Strong's-style ID, parsing (morphology), plain definition. No notable-frequency note exists in the current data shape; note this as a gap if the spec's exact wording requires it (re-check the spec text: "a notable-frequency note when relevant" — this depends on data not currently computed anywhere in this codebase; flag as a real, separate small follow-up rather than fabricating a note with no real backing data).
- [ ] **Step 2:** This is the **only** place in the panel with a back button, per the spec's exact wording ("that's the only place in the panel with a back button") — a simple "← Back" control returning to the interlinear row, matching the pattern already proven on the standalone page's commentary detail view (Task 25 deliberately did *not* reuse this pattern for Commentaries per Alex's decision — Word Study is the one place it's kept).
- [ ] **Step 3:** Confirm no Precept Austin content appears anywhere in this view — this view is lexicon-only, unlike the standalone page's `InlineWordPanel`.
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: lexicon-only word study view, the panel's one back-button surface"
```

### Task 30: Width-borrowing

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx`, possibly `frontend/app/page.tsx` (the `md:pr-[clamp(...)]` width reservation needs to widen in step)

**Spec wording, confirmed verbatim:** "The panel automatically borrows extra width while the interlinear is open, and shrinks back to a third when it's collapsed. Width follows need; there's no user-managed 'wide mode.'"

- [ ] **Step 1:** When the Interlinear row is expanded (open), widen the panel's own width class beyond the current `w-[33vw] min-w-[380px] max-w-[480px]` to something wider (e.g. `w-[50vw]` with adjusted min/max) — and widen `page.tsx`'s matching `md:pr-[clamp(...)]` reservation in step, since that comment already notes it must stay in sync with the panel's own width.
- [ ] **Step 2:** When the Interlinear row collapses (or any other row is what's open), shrink back to the current third-width.
- [ ] **Step 3:** Confirm this is automatic (tied to the accordion's open/close state), not a user-facing toggle — per the spec's explicit "no user-managed wide mode."
- [ ] **Step 4:** Commit.

```bash
git add frontend/components/rhemata/study-panel.tsx frontend/app/page.tsx
git commit -m "SP2: panel borrows width while Interlinear is open, restores on collapse"
```

### Task 31: Confirm Translations and Cross-references are fully deleted

- [ ] **Step 1:** Grep the whole frontend for "Translations" and "Cross-references" as former `ToolRowStub` labels — confirm zero remaining references (Task 24 already removed their call sites; this is a final confirmation, not new work).

### Task 32: Confirm Hebrew and Precept Austin stay excluded, end to end

- [ ] **Step 1:** Open the panel on an OT verse — confirm Interlinear shows the honest "not available" message, nothing else Hebrew-shaped appears anywhere in the panel.
- [ ] **Step 2:** Open the word-study view for several Greek words — confirm no Precept Austin content, no "From the Library" corpus section, anywhere in the panel's version.

---

## Phase 9 — Keyboard and screen-reader verification (Tasks 33–34)

The panel's container (Radix Dialog) already provides real focus-trap, Escape-to-close, and ARIA labeling for free — confirmed in the original diagnostic. What it does **not** cover for free: the verse underlines inside chat answers, the three accordion rows, the pin dropdown, and the word-study back button — all genuinely new or newly-real interactive surfaces this plan adds. This phase tests those specifically, rather than assuming the container's baseline extends to them.

### Task 33: Real verification pass

- [ ] **Step 1:** Tab through a chat answer containing verified verse underlines — confirm each is keyboard-focusable and activates on Enter/Space, not just mouse click.
- [ ] **Step 2:** Tab to each accordion row trigger — confirm `aria-expanded` reflects open/closed state, and Enter/Space toggles it.
- [ ] **Step 3:** Tab into the pin dropdown — confirm it opens via keyboard, lists pins in a focusable order, and each pin activates via Enter/Space.
- [ ] **Step 4:** Tab to the word-study back button — confirm it's reachable and that focus lands somewhere sensible (not lost) after returning to the Interlinear row.
- [ ] **Step 5:** Spot-check with a screen reader (VoiceOver, since this is a Mac-based dev environment) that the accordion rows announce their expanded/collapsed state and the pin dropdown announces its contents.

### Task 34: Fix findings

- [ ] **Step 1:** For each gap found in Task 33 (expect at minimum: missing `aria-expanded` on the new `AccordionRow`, possibly missing keyboard handlers on the pin dropdown's items if built with `onClick`-only divs instead of real `button` elements), fix directly — add proper `aria-expanded`, ensure every interactive element is a real `button`, confirm focus management on the back button's return path.
- [ ] **Step 2:** Re-run Task 33's checklist after fixes, confirm clean.
- [ ] **Step 3:** Commit.

```bash
git add frontend/components/rhemata/accordion-row.tsx frontend/components/rhemata/pin-dropdown.tsx frontend/components/rhemata/study-panel.tsx
git commit -m "SP2: fix keyboard/screen-reader gaps in accordion rows, pin dropdown, back button"
```

---

## Phase 10 — Records correction (Standing Rule #12)

### Task 35: Update PLAN.md

- [ ] **Step 1:** Mark PLAN.md #41 (SP3 — tool rows) as **superseded and dissolved**: Interlinear and lexicon-driven word study absorbed into SP2 (this plan); Translations and Cross-references cut entirely, never built; the old hard gate (lexicon conversion #12 + licensed word-level source) is recorded as satisfied by this plan's own diagnostic (Study Mode's interlinear already renders from real, licensed data) rather than by #12 specifically completing on its own timeline.
- [ ] **Step 2:** Record the teacher-tap decision: SP1's teacher pointers remain resolved-but-unrendered through SP2; no teacher underlines exist until SP4 gives them real content to open.
- [ ] **Step 3:** Record the pin-system redesign as superseding both PLAN.md #40's wording and the spec's pin decisions: global (not per-conversation), account-database-backed (not browser storage), cap of 8 (not 4), bookmark dropdown re-entry (not an edge tab), verses only until SP4, and — new in this design — reachable while signed out, with a guest pin attempt prompting signup (via the existing `LoginModal`) rather than being hidden, and the pin landing automatically once signup completes.
- [ ] **Step 4:** Record the Precept Austin word-study rewrite as a deferred open question, with the exact reasoning: PA is locked out of the propositions layer (2026-07-02 decision — excerpt reuse disproven as near-verbatim, fresh extraction declined); a fresh rewrite carries high meaning-drift risk on word studies specifically, where precision is the content itself, and drifted output would be cited to a real teacher by name. Revisit only after the lexicon-driven word study (this plan) is live, as its own session, demo-before-scale.
- [ ] **Step 5:** Record the Hebrew permission gate as a new, separate decision entry: the Hebrew brief lexicon's definitions are third-party (Abridged BDB, Online Bible) and require Online Bible's permission before use in any project — additional to, not cleared by, #32's CC BY finding. Greek is unaffected. This gates any future Hebrew interlinear/word study work specifically.
- [ ] **Step 6:** Record that this plan's attribution phase (Phase 2) closes #33's STEPBible half; the openbible.info half of #33 stays open (cross-references were cut from the panel entirely, so nothing in this plan touches that half).
- [ ] **Step 7:** Record that the SP track's "the old /study page is untouched" wording is superseded by this plan's Phase 4 (the `/study/commentary` endpoint split) and Phase 6 (the shared-component extraction) — the standalone page is *behaviorally* untouched (proven, not assumed, in both cases) but its code is refactored/extended to support the panel.
- [ ] **Step 8:** Commit (PLAN.md is terminal-committed content but chat-originated per its own writer-rules contract — this plan's content is the prompt for that commit, matching how this whole session has operated).

### Task 36: Update rhemata-status.md's Open Flags

- [ ] **Step 1:** Close Open Flag 16 (no kill switch) once Phase 1 lands, with the commit reference.
- [ ] **Step 2:** Close Open Flag 17 (client-side stand-in) once Phase 3 lands, with the commit reference.
- [ ] **Step 3:** Add a new open flag for the Hebrew Online Bible permission requirement, cross-referencing PLAN.md's new decision entry (Task 35, Step 5) — so a future session doesn't assume Hebrew is clear just because #32's CC BY check passed.
- [ ] **Step 4:** Commit.

---

SP2 is done when Phase 10's records land and every phase's own verification step has been run for real, not assumed. SP3 no longer exists as a separate track — its contents are fully absorbed above or explicitly cut. SP4 (teacher card content, real teacher pinning) and SP5 (mobile drag-to-close) remain separate, unscheduled work.
