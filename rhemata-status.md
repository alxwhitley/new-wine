# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-05. **PLAN.md has no active blockers.**

---

## Current state

**Three mobile UI items are DONE and live** (commits `3d7649c`..`4fdf39b`,
design doc `docs/superpowers/specs/2026-09-04-mobile-chat-gestures-design.md`):

1. **Overscroll containment.** Dragging the thread past its own top translated
   the whole viewport. Three independent causes, all live at once: no
   `overscroll-contain` on the message list, no `overscroll-behavior` on
   `html`/`body` (the existing `overscroll-none` sits on a `fixed` element and
   cannot reach the root scroller), and the `visualViewport` sync writing a
   negative `offsetTop` back to the shell so it rode the bounce.
2. **Floating composer with a bottom fade.** The composer now overlays the
   thread and a gradient dissolves text beneath it. Deliberately a gradient
   overlay, not `mask-image` on the scroller. Clearance tracks the composer's
   measured height via `ResizeObserver` → `--composer-h`.
3. **Profile drag-to-dismiss** (`hooks/use-sheet-drag.ts`, `lib/sheet-drag.ts`).
   Mobile only, touch/pen only, dismiss on distance or flick, spring back
   otherwise, backdrop dims with the drag.

**The Git/Vercel backlog is published — this supersedes the previous entry's
posture.** Alex was shown that local `main` was 36 commits ahead of
`origin/main` with work he had deliberately declined to publish one session
earlier, and directed a full push anyway. `origin/main` is now level with local
`main` at `4fdf39b`. The isolated backend-only release described previously is
no longer the state; the whole backlog is on `origin/main` and built by Vercel.
The public API health check passes after the push.

**A green Vercel deploy shipped stale CSS — caught and fixed, not by the build
status.** The first production build reported success in 24s while omitting all
three of this session's `globals.css` blocks; Tailwind utilities from
`page.tsx` shipped, so the page rendered a floating composer with no fade and
no mobile sheet, worse than before the change. Found by byte-comparing the
served bundle against a clean local build (113,839 vs 114,949). Fixed by
setting `VERCEL_FORCE_NO_BUILD_CACHE=1` (Production scope, project `newwine`)
and redeploying; the served bundle is now byte-identical to the clean local
build and every rule was re-verified live. Full mechanism recorded as a landmine
in `frontend/CLAUDE.md`.

**Verification status, stated plainly.** 98/98 frontend unit tests, 20/20
Playwright e2e across four device profiles, lint clean apart from two
pre-existing `/study` warnings. The floating composer's geometry is covered by
a new stubbed-thread e2e spec (`frontend/tests/e2e/chat-fade.spec.ts`) and the
fade was confirmed visually from a captured screenshot. **The two gesture
items — overscroll and the Profile swipe — have NOT been verified on a physical
device.** They are live and unproven on real hardware.

---

## Session outcome and measures

- Original outcome completed: **yes** — all three requested UI items shipped,
  deployed, and independently verified live.
- Unplanned investigations started: **1** — the stale-CSS deploy, which was a
  real production defect introduced by this session's own deploy.
- Findings promoted to Blocker: **0**.
- Scope changes approved by Alex: publishing the full 41-commit backlog to
  `origin/main`, reversing the prior session's isolated-release decision.
- Active critical-path item count: **0**.

---

## Next single item

No active Blocker. Two carried items, neither scheduled:

1. **Device verification** of the overscroll fix and the Profile swipe. If the
   bounce survives, the agreed next step is dropping the `top` write from the
   `visualViewport` scroll listener — Alex's standing instruction is to stop
   and ask before doing it, not to apply it pre-emptively.
2. `frontend/.vercel/project.json` still points at the retired **`rhemata`**
   Vercel project, not `newwine`. A CLI deploy run from `frontend/` targets the
   wrong project; one failed deployment was created there this session.

The next authorized Scheduled item remains the representative Ravenhill
source-quality comparison in `docs/roadmap.md`; any production corpus action
remains an attended gate.
