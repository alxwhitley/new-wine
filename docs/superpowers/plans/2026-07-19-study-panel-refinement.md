# Inline Study Panel — Clickability + Floating Overlay Refinement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two real, confirmed problems in the shipped Inline Study Panel (SP2/SP4): (1) verse/teacher reference clickability — and citation pills, and message IDs — silently die the moment a conversation is reopened, because the verification data that makes them clickable is never persisted; (2) the panel visually reads as docked against the chat rail (flush edges, no margin, square corners) instead of floating over it. Both were interviewed with Alex (`docs/intent` not used — confirmed inline, 2026-07-19) before this plan was written. Alex's explicit rule for this refinement: **one load-bearing change per session, build and records commits kept separate.**

**Architecture:** Two independent phases, sequenced by an existing gate — not by this plan.

- **Phase 1 (persistence fix)** is unblocked and ships first. Root cause, confirmed by direct code trace: `verified_references` is computed fresh on every chat turn (`backend/app/routers/chat.py:1002-1007`) and attached only to that turn's SSE `meta` event (`chat.py:1026-1031`). It is never written to the database — `_save_conversation` (`chat.py:445-479`) inserts only `id`, `conversation_id`, `role`, `content` per message. The frontend's conversation-reload path (`frontend/hooks/useConversations.ts:84-93`) reads straight from Supabase and requests only `role, content` — there is no backend `/conversations` endpoint at all. Consequence: the moment a conversation is reopened (switch conversations, refresh, revisit from the sidebar), every verse/teacher underline in it goes dead — not because of signed-in/guest state, not because of verse-vs-teacher, but purely because the reload path never had the data to begin with. `citations` has the exact same gap for the exact same reason and is bundled into this fix per Alex's call. `message_id` turns out to already survive (it's the message row's own `id`, `chat.py:465-471`) — it just isn't being selected on reload.
- **Checkpoint — Alex's own SP4 sign-off** (not a build task, nothing in this plan executes it). Four authenticated checks: real card content for a signed-in user, the honest-empty live test (a curated teacher who doesn't address a topic returns nothing fabricated), nested back-return, keyboard-only navigation. This checkpoint gates Phase 2 only — it does not gate Phase 1.
- **Phase 2 (floating overlay, desktop only)** ships after the checkpoint clears. Root cause, confirmed by direct code trace: the panel (`frontend/components/rhemata/study-panel.tsx:531-544`, desktop branch) is positioned `inset-y-0 right-0`, full viewport height, flush against the screen edge, `border-l` only. The chat area's own reserved space (`frontend/app/page.tsx:411-420`, `md:pr-[clamp(380px,33vw,480px)]`) is sized to match the panel's width exactly, so the chat card's right edge and the panel's left edge land at the identical x-coordinate — a literal, not just visual, seam. Confirmed with Alex: chat is allowed to keep narrowing (no ban on reflow); mobile's existing full-screen, dimmed takeover (`inset-0`, `bg-black/50`) is explicitly untouched. The panel is already ONE shared component branching on `useIsMobile()` (`study-panel.tsx:470-574`) — "design the overlay once, share it across desktop and mobile" is structurally already true; this phase is a desktop-only visual fix plus a live verification pass on the dismiss mechanics, not a rebuild.

**Tech Stack:** Python 3.9 / FastAPI backend (Phase 1), Next.js 16 (React 19) frontend (both phases), Postgres via Supabase (Phase 1 migration). No new dependencies either phase.

## Global Constraints

- **Python 3.9**: `Optional[str]`, never `str | None` (repo invariant #1) — relevant if Phase 1's `_save_conversation` signature needs a new optional param.
- **No semicolons inside `--` SQL comments in migrations** (repo invariant #9) — the multi-statement runner treats them as terminators and rolls back silently. Verify any new column with `SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'` on a **fresh** connection, not the one that ran the DDL.
- **No MCP write tools, ever.** The new migration is applied via direct `psycopg2` against `SUPABASE_DB_URL`, exactly like every other migration in this repo — never a Supabase MCP tool.
- **No automated test framework exists in this repo.** Backend verification is the ad hoc `scripts/test_*.py` `check()`/`sys.exit(1)` pattern if a script is warranted; frontend verification is real-browser manual/Playwright-skill checking, matching every SP2/SP4 phase's own verification style. `localhost:3000` cannot reach the production Railway backend (CORS) — verify against a real deploy, per the standing method this build already established.
- **Next.js 16 / React 19**: `frontend/AGENTS.md` warns this version has breaking changes from training-data expectations — check `node_modules/next/dist/docs/` before assuming an API.
- **DESIGN.md is the sole styling authority for Phase 2.** No hardcoded hex, no new shadows/radii/colors, no JS hover handlers, dark theme only. The floating treatment must reuse tokens already in use elsewhere in this exact codebase (`rounded-xl`, `border-border`, `shadow-lg` — all already present on the chat card and/or the panel itself), not introduce new ones.
- **Two isolated commits per phase**: build separate from the `rhemata-status.md` record correction, per Alex's standing rule and this session's explicit instruction.
- **Out of scope, do not build:** any visual change to the underline treatment itself (Alex confirmed keep-as-is); any change to mobile's full-screen/dimmed panel behavior; retrofitting reference data into conversations created before Phase 1 ships (existing spec exclusion, unaffected — those conversations simply keep degrading to plain text, which is correct); SP4's own teacher-card content work (separate, already-shipped track).

## File Structure

New files:
- `migrations/066_messages_reference_data.sql` — adds `citations` and `verified_references` columns to `messages`

Modified files:
- `backend/app/routers/chat.py` — `_save_conversation` persists `citations` + `verified_references` for the assistant row
- `frontend/hooks/useConversations.ts` — `loadMessages` selects and returns the new columns plus `id`
- `frontend/components/rhemata/study-panel.tsx` — desktop `Content` inset/rounding (Phase 2 only)
- `frontend/app/page.tsx` — reserved-width classes adjusted to match the panel's new footprint (Phase 2 only)

---

## Phase 1 — Reference-persistence fix

### Task 1: Migration — add `citations` and `verified_references` to `messages`

**Files:** Create `migrations/066_messages_reference_data.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Migration 066: persist per-message citations and SP1 verified_references
-- so verse/teacher underlines and citation pills survive a conversation
-- reload. Confirmed by direct code trace (2026-07-19 refinement session):
-- neither column has ever existed on `messages` -- this data has only ever
-- lived in the single SSE meta event for the turn that generated it
-- (backend/app/routers/chat.py:1026-1031), discarded the moment that
-- response ends. Nullable: user-role messages and pre-migration assistant
-- rows never had this data and must keep degrading to plain text, not error.
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS citations jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS verified_references jsonb;
```

- [ ] **Step 2: Apply via psycopg2** (direct connection, autocommit, execute the file's SQL as one script — this repo's standard migration-apply pattern)

- [ ] **Step 3: Verify on a fresh connection**

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'messages' AND column_name IN ('citations', 'verified_references');
-- Expected: both rows present, data_type = 'jsonb'
```

- [ ] **Step 4: Commit**

```bash
git add migrations/066_messages_reference_data.sql
git commit -m "Add citations + verified_references columns to messages"
```

---

### Task 2: Backend — persist citations + verified_references on save

**Files:** Modify `backend/app/routers/chat.py`

**Confirmed exact current code** (read live, 2026-07-19 — re-read before editing, this plan's own line numbers may drift):
- `_save_conversation` signature and body: `chat.py:445-479`. The assistant-row insert dict is `chat.py:470-475`.
- Dispatch site: `chat.py:1013-1019`, `args=(db, user_id, conversation_id, is_new, request.question, answer, message_id)`.
- `citations` is computed once at `chat.py:790` and is already in scope, unchanged, at the dispatch site.
- `verified_references` is computed at `chat.py:1002-1007`, immediately before the dispatch site.

- [ ] **Step 1: Widen `_save_conversation`'s signature**

Change:
```python
def _save_conversation(
    db, user_id: str, conversation_id: str, is_new: bool,
    question: str, answer: str, message_id: str,
) -> None:
```
to:
```python
def _save_conversation(
    db, user_id: str, conversation_id: str, is_new: bool,
    question: str, answer: str, message_id: str,
    citations: list, verified_references: list,
) -> None:
```

- [ ] **Step 2: Add the two fields to the assistant-row insert only** (the user-row insert stays exactly as-is — a user's own question never has citations or verified references)

Change:
```python
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": answer,
            },
```
to:
```python
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": answer,
                "citations": citations,
                "verified_references": verified_references,
            },
```

- [ ] **Step 3: Pass both into the dispatch call**

Change:
```python
            threading.Thread(
                target=_save_conversation,
                args=(db, user_id, conversation_id, is_new, request.question, answer, message_id),
                daemon=True,
            ).start()
```
to:
```python
            threading.Thread(
                target=_save_conversation,
                args=(db, user_id, conversation_id, is_new, request.question, answer, message_id, citations, verified_references),
                daemon=True,
            ).start()
```

- [ ] **Step 4: Manually smoke-test** — start the backend locally, send one real question through `/chat` as an authenticated user, confirm the answer still streams normally (this must be a no-op for existing behavior at the SSE-event level; only the background save gains two new fields).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "Persist citations + verified_references on the assistant message row"
```

---

### Task 3: Frontend — read the persisted data back on conversation reload

**Files:** Modify `frontend/hooks/useConversations.ts`

**Confirmed exact current code** (`useConversations.ts:84-93`):
```ts
  const loadMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    const { data } = await supabase
      .from("messages")
      .select("role, content")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });

    if (!data) return [];
    return data.map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
  }, []);
```

- [ ] **Step 1: Widen the select and the mapping**

```ts
  const loadMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    const { data } = await supabase
      .from("messages")
      .select("id, role, content, citations, verified_references")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });

    if (!data) return [];
    return data.map((m) => ({
      role: m.role as "user" | "assistant",
      content: m.content,
      messageId: m.id,
      citations: m.citations ?? undefined,
      verifiedReferences: m.verified_references ?? undefined,
    }));
  }, []);
```

`Message` (`frontend/hooks/useChat.ts:5-11`) already has `citations`, `messageId`, `verifiedReferences` as optional fields — no type change needed there. Confirm `Citation` and `VerifiedReference`'s shapes match what's stored (they're stored verbatim from the same `meta` event these types were already built to consume, so this should be a direct fit — verify with `npx tsc --noEmit`, not by assumption).

- [ ] **Step 2: Manually verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/hooks/useConversations.ts
git commit -m "Restore citations + verified_references when reloading a conversation"
```

---

### Task 4: Live end-to-end verification — not by reading code

- [ ] **Step 1:** Signed in, ask a real question likely to produce a verified verse or teacher reference. Confirm the underline renders and the click opens the panel correctly (this should already work pre-fix — establishing the baseline).
- [ ] **Step 2:** Switch to a different conversation, then switch back (or refresh the page and reopen the same conversation from the sidebar). Confirm the same verse/teacher underline AND the citation pill are still present and still open the correct panel/source content — this is the actual proof the fix works, not "the code compiles."
- [ ] **Step 3:** Confirm a conversation created **before** this migration shipped still degrades gracefully — plain text, no underline, no crash, no console error. This is the expected, correct behavior (out of scope per spec), not a regression to chase.
- [ ] **Step 4:** Confirm a guest (no auth) conversation still behaves as before — guests don't get saved conversation history at all today (no `user_id` → `_save_conversation` is skipped entirely, `chat.py:1013/1020-1023`), so this fix has no guest-facing effect; verify that assumption holds, don't just state it.
- [ ] **Step 5:** Confirm no regression to the guest-limit or weekly-limit flows (unrelated code paths, but both touch the same `chat.py` request-handling function — a quick smoke check is cheap insurance).

### Task 5: Records correction

- [ ] **Step 1:** Update `rhemata-status.md` — record the fix, the migration number, the confirmed root cause, and the citations/message_id bundling decision, per Standing Rule #12 ("shipping a fix includes correcting the record in the same session").
- [ ] **Step 2:** Commit, separate from Task 1-4's build commits.

```bash
git add rhemata-status.md
git commit -m "Record the reference-persistence fix (migration 066)"
```

---

## CHECKPOINT — Alex's SP4 sign-off

**Nothing in this plan executes this step.** Alex signs in with a real authenticated account and runs four checks: (1) real card content for a signed-in user, (2) the honest-empty live test — a curated teacher asked something they never address returns empty, never a fabricated position, (3) nested back-return, (4) keyboard-only navigation. **This gates Phase 2 below only — it does not gate Phase 1, which ships independently.** Do not begin Phase 2 until Alex confirms this checkpoint has passed.

---

## Phase 2 — Floating overlay (desktop only; mobile untouched)

### Task 6: Read the current exact classes before editing

- [ ] **Step 1:** Re-read `frontend/components/rhemata/study-panel.tsx`'s `PanelPrimitive.Content` className block (currently lines 531-544) and `frontend/app/page.tsx`'s `<main>` className block (currently lines 411-420) in full — confirm exact current wording, since line numbers may have drifted since this plan was written and since Phase 1's changes don't touch these files but other work might have landed in between.

### Task 7: Give the desktop panel the same floating-card treatment the chat window already has

**Files:** Modify `frontend/components/rhemata/study-panel.tsx`

**Confirmed exact current code** (desktop branch only, `study-panel.tsx:538-543`):
```tsx
            isMobile
              ? "inset-0 data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom"
              : cn(
                  "inset-y-0 right-0 border-l border-border data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
                  interlinearOpen ? "w-[50vw] min-w-[480px] max-w-[720px]" : "w-[33vw] min-w-[380px] max-w-[480px]"
                )
```

**Design:** the chat card itself already floats with `md:p-2` margin and `md:rounded-xl md:border md:border-border` (`page.tsx:423`). Give the panel the identical margin and rounding on desktop — `inset-y-2 right-2` instead of `inset-y-0 right-0`, `rounded-xl border border-border` (all four sides) instead of `border-l border-border` — so the two read as two floating cards on the same dark canvas, not one panel welded to the other. **Mobile branch stays byte-for-byte unchanged.**

- [ ] **Step 1: Apply the change**

```tsx
            isMobile
              ? "inset-0 data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom"
              : cn(
                  "inset-y-2 right-2 rounded-xl border border-border shadow-lg data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
                  interlinearOpen ? "w-[50vw] min-w-[480px] max-w-[720px]" : "w-[33vw] min-w-[380px] max-w-[480px]"
                )
```

(`shadow-lg` is already applied at the shared/outer level of this className string — `study-panel.tsx:534` — confirm it isn't now duplicated; keep one copy.)

- [ ] **Step 2: Commit**

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "Desktop Study Panel: floating-card treatment (margin + rounded corners), matching the chat card"
```

---

### Task 8: Widen the chat area's reserved space to keep a visible gap, not an overlap

**Files:** Modify `frontend/app/page.tsx`

**Why this is its own task, not folded into Task 7:** insetting the panel by `right-2`/`inset-y-2` shifts its left edge 0.5rem further left without any other change — which would make it *overlap* the chat card by that same 0.5rem, since the chat card's reserved padding (`page.tsx:416-417`) was sized to match the panel's old flush-edge footprint exactly. The reserved padding must grow by the same amount the panel's own edge-inset consumes, plus the panel's `right-2` margin itself, so a real gap (showing the app's canvas color, `bg-sidebar`, already visible in the margin around the chat card today) appears between the two cards instead of them touching or overlapping.

**Confirmed exact current code** (`page.tsx:414-418`):
```tsx
            studyPanelOpen
              ? interlinearWide
                ? "md:ml-0 md:pr-[clamp(480px,50vw,720px)]"
                : "md:ml-0 md:pr-[clamp(380px,33vw,480px)]"
              : "md:ml-64",
```

- [ ] **Step 1: Add a fixed gap allowance on top of each existing clamp bound** — the panel's `right-2` inset (0.5rem) plus a matching 0.5rem visual gap = 1rem (16px) total to add to every bound of both clamp expressions:

```tsx
            studyPanelOpen
              ? interlinearWide
                ? "md:ml-0 md:pr-[clamp(496px,calc(50vw+1rem),736px)]"
                : "md:ml-0 md:pr-[clamp(396px,calc(33vw+1rem),496px)]"
              : "md:ml-64",
```

- [ ] **Step 2: Verify the exact gap live, in a real browser, not by trusting this arithmetic blindly.** Open the panel, use devtools to measure the actual pixel gap between the chat card's right border and the panel's left border at a few window widths (narrow/mid/wide, and with Interlinear open vs. closed). Adjust the constants above if the measured gap isn't a clean, consistent ~0.5rem — CSS `clamp()`/`calc()` arithmetic is easy to get subtly wrong across the three breakpoints (min/preferred/max), and this is exactly the kind of thing this repo's own convention says to verify empirically rather than assume.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "Widen chat's reserved space to keep a visible gap from the now-inset Study Panel"
```

---

### Task 9: Verify dismiss mechanics live — X and click-outside, both required

**Why this is verification, not a build task:** `PanelPrimitive.Root` (`study-panel.tsx:517`) doesn't set `modal={false}` and doesn't override `onPointerDownOutside`, so Radix Dialog's default behavior — closing when a pointer-down occurs outside `Content` — should already be wired through `onOpenChange` (`if (!open) onClose()`). This has never been proven live; it's inferred from the absence of an override in the code. Prove it, don't assume it.

- [ ] **Step 1:** Open the panel (click a verified verse/teacher underline). Click the X in the panel header. Confirm it closes.
- [ ] **Step 2:** Reopen the panel. Click on visible chat content well outside the panel's bounds (not on the panel itself, not on the dev "Study preview" button). Confirm the panel closes.
- [ ] **Step 3:** Reopen the panel, open the pin dropdown (top bar), confirm clicking outside — including while the dropdown is open — closes the whole panel, dropdown included (this exact interaction was already a named requirement in the original SP2 pin-dropdown work — confirm it still holds after Task 7/8's layout changes, don't assume it's unaffected).
- [ ] **Step 4:** **If either Step 1 or Step 2 fails**, only then add an explicit `onPointerDownOutside`/`onOpenChange` fix — do not pre-build a fix for a problem not yet confirmed to exist.
- [ ] **Step 5:** Confirm mobile is unaffected by any of Task 7/8's changes — open the panel on a real mobile viewport (or Playwright's mobile emulation), confirm it's still a full-screen sheet with the dark scrim, no margin, no rounded corners, chat fully hidden underneath, exactly as before.

### Task 10: Records correction

- [ ] **Step 1:** Update `rhemata-status.md` — record the floating-overlay fix, the confirmed root cause (reserved-width math, not a component rebuild), and the live-verified dismiss mechanics.
- [ ] **Step 2:** Commit, separate from Task 6-9's build commits.

```bash
git add rhemata-status.md
git commit -m "Record the Study Panel floating-overlay fix"
```

---

This refinement is done when both phases have shipped and been live-verified — not assumed — and `rhemata-status.md` reflects both. Explicitly still open after this plan: the underline's own visual treatment (unchanged, by Alex's choice), mobile behavior (unchanged, by Alex's choice), and everything already tracked as open in `rhemata-status.md`'s Open Blockers (screen-reader pass, Hebrew permission gate, etc.) — none of that is this plan's concern.
