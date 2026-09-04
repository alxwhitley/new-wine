# Mobile chat gestures & composer treatment — design

Date: 2026-09-04
Status: **Approved by Alex 2026-09-04.** Implementation in progress.
Scope: frontend only. Zero backend, zero DB, zero answer-path changes.

Three edits Alex asked for, in one pass because items 1 and 2 touch the same
viewport code in `frontend/app/page.tsx`.

| # | Ask | Shape |
|---|---|---|
| 1 | Stop the whole screen moving when overscrolling the thread | Containment fix |
| 2 | Bottom of answers should fade, ChatGPT-style | Floating composer + gradient |
| 3 | Swipe down to leave the Profile view | New interactive drag |

---

## Item 1 — overscroll moves the whole screen

### What is actually there now

- `app/page.tsx:446` — app shell is `fixed inset-0 flex h-dvh-safe overflow-hidden
  overscroll-none bg-sidebar`.
- `app/page.tsx:557` — the message list is `flex-1 overflow-y-auto min-h-0`, with
  **no** overscroll containment.
- `app/globals.css` — `html` and `body` carry **no** `overscroll-behavior` at all.
- `app/page.tsx:290–313` — a `visualViewport` effect writes
  `shell.style.top = visualViewport.offsetTop` on every `visualViewport`
  **scroll** event, not just on resize.

### Diagnosis

Three separate contributors, all live at once:

1. **Scroll chaining.** The message list has no `overscroll-behavior`, so once it
   hits `scrollTop 0` and the drag continues, the gesture propagates to the
   document and Safari rubber-bands the viewport. This is the direct cause of
   "scroll above when there's no actual room."
2. **No document-level containment.** `overscroll-none` on line 446 is on a
   `fixed` element; it cannot suppress the *root* scroller's bounce. Safari 16+
   honours `overscroll-behavior` on `html`/`body`, and nothing sets it.
3. **The shell actively tracks the bounce.** A rubber-band fires
   `visualViewport` `scroll`, and the effect above repositions the shell to the
   reported `offsetTop`. This is why the shell visibly *translates* rather than
   merely revealing background behind it.

### Change

1. `app/globals.css` — add, next to the existing unlayered `body` block:
   ```css
   html, body { overscroll-behavior: none; }
   ```
2. `app/page.tsx:557` — add `overscroll-contain` to the message-list scroller.
3. `app/page.tsx:~300` — clamp the positioning write:
   `shell.style.top = Math.max(0, Math.round(viewport?.offsetTop ?? 0)) + "px"`.
   The `scroll` listener stays (it is load-bearing for iOS toolbar motion); only
   the negative excursion is suppressed.

Line 446's `overscroll-none` is **left alone**. `overflow-hidden` still makes
that element a scroll container, so the declaration is not inert — removing it
is a change with no upside.

### Risk

Change 3 is the only one that can regress something. The effect it modifies was
written for the iOS software keyboard. Clamping is the conservative form; if the
bounce survives on device, the next step is dropping `scroll` from the
*positioning* sync while keeping it for height. Device verification is required
before this item is called done.

---

## Item 2 — bottom fade, ChatGPT-style (option B, chosen)

### What is there now

- `chat-input.tsx:84` — the composer is a `shrink-0 bg-background` block in
  normal flex flow, sitting *below* the scroller. Answers terminate at a hard
  edge against it.
- `app/page.tsx:559` — a `sticky top-0` gradient already fades the **top** of the
  thread. There is no bottom equivalent.
- `app/page.tsx:470` — `main` carries `pb-safe` for the iOS home indicator.
- `composer-viewport.ts` — the textarea grows to a computed max (192px on a
  phone-height viewport, less when the keyboard is tall).

### Design

Alex chose **B**: float the composer over the thread, with a real fade, rather
than a fade against a solid bar.

1. **Float the composer.** The chat-region wrapper (`app/page.tsx:487`) is
   already `relative`. `<ChatInput />` moves into
   `absolute inset-x-0 bottom-0 z-20`. Its own container drops `bg-background`
   and becomes transparent; only the pill keeps its `bg-popover` fill.
2. **Fade by gradient overlay, not by mask.** A `pointer-events-none absolute
   inset-x-0 bottom-0 z-10` element sits between content and composer, painting
   `linear-gradient(to top, background 0 → background var(--composer-h) →
   transparent calc(var(--composer-h) + 4rem))`. The backdrop *is*
   `bg-background`, so fading to the background colour is visually identical to
   fading to alpha-zero — and it avoids putting a compositing layer on a
   scrolling element, which costs real scroll performance on iOS.
   Implemented as a `.composer-fade` utility in `globals.css`, consistent with
   the existing `.h-dvh-safe` / `.pb-safe` / `.pb-drawer-footer-safe` pattern.
3. **Dynamic clearance.** A `ResizeObserver` on the composer wrapper writes
   `--composer-h` onto the chat-region element; the scroller takes
   `padding-bottom: calc(var(--composer-h) + 1rem)`. A fixed padding would clip,
   because the textarea grows.
4. **Safe area moves.** `pb-safe` comes off `main` and onto the floating
   composer, which is now the element that actually touches the bottom edge.
5. **Empty state untouched.** There the composer is `embedded` and centred; it
   stays in normal flow.

### Knock-ons that must be re-verified, not assumed

- `keepLatestVisible` (`app/page.tsx:321–341`) uses
  `scrollIntoView({ block: "nearest" })`. With new bottom padding, "nearest"
  resolves differently and may leave the newest turn under the composer. Expect
  to change this to explicit scroll-to-bottom arithmetic.
- The `--composer-h` ceiling is `composerMaxHeight()` + padding, so the fade
  never grows unbounded.
- Desktop: the composer floats inside the chat region, so the study-panel slot
  beside it is unaffected. `max-w-2xl` centring is preserved.

### Deliberately not doing

Folding the existing top fade (`:559`) into the same mechanism. It works; this
plan does not touch it. Raise separately if the two ends should visually match.

---

## Item 3 — swipe down to leave Profile (option B, chosen)

### What is there now

- The Profile view is `AdminModal.tsx:811`, a Radix **`Dialog`** —
  `h-[calc(100dvh-1rem)] w-[calc(100%-1rem)] … sm:h-[85dvh]`. Near-fullscreen on
  mobile, no grab handle, no dismiss gesture. Only the X button.
- The repo already has swipe-to-dismiss in `source-panel.tsx:94–132` and
  `study-panel.tsx:611–645`. Pointer-Events based — deliberately, because React
  marks touch listeners passive and that would silently break `preventDefault`.
  But it is **binary**: 44px threshold, nothing follows the finger.
- `AdminModal.tsx:868` — the right pane is `overflow-y-auto overscroll-contain`.

### Design

Alex chose **B**: a real interactive sheet, not the existing binary threshold.
Hand-rolled rather than adding `vaul` — the drag math is small and this repo
already owns its pointer logic.

**Scope default (correct me if wrong): Profile only.** Source and Study panels
keep their binary behaviour and convert in a follow-up, once the feel is
confirmed on device.

1. **New `hooks/use-sheet-drag.ts`.** Pointer-capture based. Tracks `startY` and
   timestamp; exposes `{ dragHandlers, dragOffset, isDragging }`. Downward drag
   follows 1:1; upward drag gets divide-by-4 resistance so the sheet never
   detaches from the top edge.
2. **Pure decision function, separately testable.**
   `dragOutcome(deltaY, velocityPxPerMs) → "dismiss" | "spring-back"` — dismiss
   on `deltaY >= 120`, or on `velocity >= 0.5` with `deltaY >= 40`. Extracted as
   a pure function so it gets real unit tests, mirroring
   `composer-viewport.ts` / `composer-viewport.test.mts`.
3. **Scroll guard.** The gesture only begins when the nearest scrollable
   ancestor of the event target is at `scrollTop === 0`, so it never fights the
   right pane's scroller.
4. **Radix transform conflict — the real gotcha.** `DialogContent`
   (`dialog.tsx:53`) centres with `translate-x-[-50%] translate-y-[-50%]` and
   animates with `zoom-in-95` / `zoom-out-95`. A raw `transform` written by the
   drag clobbers both. **Resolution: give AdminModal a mobile-only,
   bottom-anchored content class with no centring transform** — closer to a
   native sheet regardless — and leave the desktop centred dialog completely
   untouched. This is preferred over threading the drag through a CSS variable,
   which would still fight the open/close animation classes.
5. **Dismiss unwinds through Radix.** Crossing the threshold calls
   `onOpenChange(false)`, so focus restoration and scroll-lock unwind normally.
   The drag never unmounts anything itself.
6. **Overlay tracks the drag.** Overlay opacity interpolates with drag progress.
   Cheap, and it is a large part of what makes the gesture read as native.
7. **`prefers-reduced-motion`.** Falls back to the existing binary behaviour:
   threshold crossed → close, nothing follows the finger, no spring.
8. **Mobile only**, via the existing `useIsMobile()` (768px). Desktop dialog
   behaviour is byte-for-byte unchanged.

---

## Sequencing

1. **Item 1** first — it is the foundation, and item 2 edits the same
   `visualViewport` code. Landing them together would make a keyboard regression
   impossible to attribute.
2. **Item 2** second.
3. **Item 3** last. It is an independent file set and could run in parallel, but
   sequencing keeps the diffs reviewable.

Each item is a separate commit with its own device check.

---

## Verification

Repo conventions, not new machinery:

- **Source-assertion tests** (`lib/tablet-ux.test.mts` pattern) pinning the
  literals a future sweep could silently drop: `overscroll-behavior: none` in
  `globals.css`, `overscroll-contain` on the scroller, the `--composer-h`
  wiring, the `.composer-fade` utility. This follows CLAUDE.md's standing lesson
  that a swept literal must be pinned by a test, because reading a diff
  demonstrably does not catch that class.
- **Pure unit tests** for `dragOutcome()` and any composer-height arithmetic,
  run by `npm test`.
- **Existing Playwright** `tests/e2e/chat-composer.spec.ts` and
  `sidebar-viewport.spec.ts` must still pass; add one case asserting the
  scroller's bottom padding is at least the composer's measured height.
- **Device check on Alex's iPhone** is the only real proof for items 1 and 3.
  Neither is complete on green tests alone, and this plan does not claim
  otherwise.

---

## Out of scope

- Converting the Source and Study panels to drag-follow (follow-up, pending
  item 3 feeling right).
- The empty-state composer.
- Desktop Profile dialog behaviour.
- The existing top-of-thread fade.
- Any backend, database, answer-path, or governing-doc change.

---

## Resolved by Alex, 2026-09-04

1. **Item 3 scope — Profile only.** Source and Study panels keep their existing
   binary threshold behaviour; converting them is a separate follow-up.
2. **Item 1 fallback — stop and ask.** If clamping `offsetTop` does not fully
   stop the bounce on device, do NOT proceed to dropping the `scroll` listener
   from the positioning sync. Report and wait for Alex.
