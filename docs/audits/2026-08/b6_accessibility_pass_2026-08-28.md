# B6 Task 5.2 — Accessibility pass, 2026-08-28

Part of the back-to-back completion queue, Packet 5 (B6/B7 release-candidate
gate), Task 5.2. Scope: real browser accessibility verification of the
private-beta core journey (Home/chat entry, Study, Library) — automated
scanning plus manual keyboard/focus/zoom checks, real defects fixed with
before/after evidence. Not in scope: full WCAG conformance audit of every
route, admin-only surfaces beyond the one shared `Sheet` bug found.

## Method

- `@axe-core/playwright` against Home, Study, Library (desktop viewport,
  beta-gate bypassed via seeded `sessionStorage`).
- Lighthouse CLI (`accessibility` + `best-practices` categories) against the
  same three routes — Lighthouse's default mobile emulation caught two real
  defects axe's desktop-viewport scan missed entirely (icon-only mobile menu
  toggle, icon-only mobile search button — both `md:hidden`/`sm:hidden`
  responsive variants).
- Manual Playwright scripts: keyboard tab-through + focus-visibility check,
  Radix `Sheet` (modal) focus-trap / Escape / focus-return check, 200%
  text-zoom overflow check (via root font-size scaling, the WCAG 1.4.4
  reflow-relevant proxy — Chromium has no scriptable "real" browser-zoom
  API), and a targeted dialog-accessible-name check (axe/Lighthouse never
  opened the one sheet that had a defect, since both only scan the
  page's *closed* state on load).

## Findings — all fixed

| # | Finding | Severity | Where caught | Fix |
|---|---|---|---|---|
| 1 | Icon-only search button (Study) has no accessible name | Critical (axe `button-name`) | axe | `aria-label="Search verse or word"` — `app/study/page.tsx` |
| 2 | "Couldn't load notes" error text fails contrast (4.02:1) | Serious (axe `color-contrast`) | axe | Scoped `text-[hsl(0_84%_72%)]` override, `--destructive` token left untouched (18 other call sites) — `components/rhemata/pastors-notes.tsx` |
| 3 | App-wide `--primary` (gold) button/text/link color fails WCAG AA in at least one of its 3 conflicting uses no matter which single shade is picked | Serious (axe `color-contrast`), systemic | axe | See "The `--primary` conflict" below — fixed by changing `--primary-foreground` instead of `--primary` |
| 4 | `FooterNav`'s `<nav>` has no accessible name, collides with another unlabeled nav | Moderate (axe `landmark-unique`) | axe | `aria-label="Footer"` — `components/marketing/footer-nav.tsx` |
| 5 | Author avatar `alt` text duplicates the adjacent visible name | Minor (axe `image-redundant-alt`) | axe | `alt=""` (decorative; name already conveyed by sibling text) — `app/library/page.tsx` |
| 6 | Mobile hamburger menu button (`Menu` icon, `md:hidden`) has no accessible name — 2 call sites | Critical equivalent (Lighthouse `button-name`, mobile viewport only) | Lighthouse | `aria-label="Open menu"` — `app/library/page.tsx` (both instances; different indentation meant a `replace_all` only caught one on the first attempt) |
| 7 | Mobile-only icon search button (`sm:hidden`, "Search" text hidden) has no accessible name | Critical equivalent (Lighthouse `button-name`, mobile viewport only) | Lighthouse | `aria-label="Search"` — `app/library/page.tsx` |
| 8 | Main chat textarea has `focus:outline-none` with nothing replacing it — zero visible focus indicator on the single most-used input in the product | Real WCAG 2.4.7 gap, not caught by axe (axe doesn't universally flag missing focus styling) | Manual keyboard tab-through | `focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50` on the outer pill container (textarea itself has no border to ring) — `components/rhemata/chat-input.tsx` |
| 9 | Closing the Library "Filters" sheet (Escape) drops focus to `<body>` instead of returning it to the trigger button | Real WCAG 2.4.3 gap | Manual focus-trap test | `ref` on the trigger button + `onCloseAutoFocus={(e) => { e.preventDefault(); ref.current?.focus(); }}` on `SheetContent` — `app/library/page.tsx` |
| 10 | Library "Filters" sheet has no accessible name at all — `aria-labelledby` pointed at a Radix-generated id with no matching element; Radix itself logs "`DialogContent` requires a `DialogTitle`..." | Real WCAG 4.1.2 gap, invisible to axe/Lighthouse (neither ever opened the sheet) | Manual dialog-name check, prompted by Radix's own console warning | Replaced the plain `<h2>Filters</h2>` with `SheetTitle` (wires the real `aria-labelledby` target) + an `sr-only` `SheetDescription` — `app/library/page.tsx` |

Checked for the same missing-title pattern across every other `Sheet`/
`Dialog`/`AlertDialog` in the app (7 files use `SheetContent`, 4 use
`DialogContent`) — confirmed by exact tag-count, not the misleading
`grep -c` word-count first pass: every other instance already pairs 1:1
with a `SheetTitle`/`DialogTitle`/`AlertDialogTitle`. Finding #10 was a
genuine one-off, not a systemic gap.

## The `--primary` conflict (#3) — why the token wasn't the fix

Alex approved darkening `--primary` from `44.05 73.83% 41.96%` (`#ba901c`,
2.96:1 with white text — the original failing case) to `44.05 73.83% 32%`
(`#8e6e15`, 4.78:1). Applying it and re-scanning surfaced two *new*
failures it hadn't shown before:

| Use of `--primary` | Contrast @ 41.96% L (original) | Contrast @ 32% L (darkened) |
|---|---|---|
| White text on `bg-primary` (`Button`'s default variant, `Badge`, ~15+ call sites) | 2.96 — **fails** | 4.79 — passes |
| Dark text (`text-background`) on `bg-primary` (chat Send button) | 5.12 — passes | 3.16 — **fails** |
| `text-primary` as a link/accent text color on the dark background, 28+ files | 5.12 — passes | 3.16 — **fails** |

A Python contrast sweep (WCAG relative-luminance formula) at this hue/
saturation confirmed no single lightness value satisfies both constraints
simultaneously — white-on-primary only passes at L ≤ ~18.3%, and
primary-vs-dark-background only passes at L ≥ ~26.2%; the ranges don't
overlap, and even the widest reasonable band (L 33–39%) leaves both
underwater.

Reverted `--primary` to its original value. Flagged the full picture back
to Alex in plain language (per Alex's standing instruction this session) —
the fix approved instead: leave `--primary` untouched, and flip
`--primary-foreground` from white (`0 0% 100%`) to the same dark shade the
Send button already uses (`--background`, `60 2.7% 14.51%`). Every
`text-primary-foreground` usage in the codebase is paired with `bg-primary`
(confirmed by grep — no call site puts it on a different background), so
this is a safe, single-token, zero-blast-radius fix: it satisfies case 1
(now the same passing 5.12:1 as case 2, since both are now literally the
same color pairing) without touching cases 2 or 3 at all. Net effect:
every primary-colored button/badge across the app now renders dark text
on gold instead of white text on gold — a real, deliberate visual change
Alex approved knowing the tradeoff, not a silent substitution.

## Verification evidence

- axe: 0 violations (all severities) on Home, Study, and Library — before
  this pass: 1 critical + 2 serious + 1 moderate + 1 minor across the three
  pages.
- Lighthouse accessibility score: Home 100, Study 100, Library 100 (was 94
  on Library, from the 2 mobile-viewport `button-name` failures).
- `npx tsc --noEmit`: clean.
- `npx eslint .`: 0 errors, 2 pre-existing warnings (documented separately
  in the B6 lint-baseline work this same packet — unrelated unused
  variables in `app/study/page.tsx`, deliberately left as-is).
- `npm run build`: clean production build, 18 routes generated.
- Manual checks: keyboard tab-through reaches real interactive elements in
  order; every focused element has a visible ring (confirmed the one
  automated false-negative — the chat textarea's ring lives on its parent
  container, not the textarea itself, verified directly via
  `getComputedStyle` on the container while the textarea holds focus, plus
  a screenshot); `Sheet` focus-trap holds under 15 Tab presses; Escape
  closes and now correctly returns focus to the trigger; 200% text zoom
  produces no horizontal overflow on Study or Library.
- Screenshots: `/tmp/final-home.png`, `/tmp/final-study.png`,
  `/tmp/final-library.png`, `/tmp/final-library-filters-sheet.png`,
  `/tmp/textarea-focus-ring.png` (local temp paths, not committed).

## Explicitly out of scope, not fixed this pass

- `errors-in-console` (Lighthouse best-practices) on all 3 pages: local dev
  fetches hit the production backend (`rhemata-production.up.railway.app`),
  which correctly rejects the `localhost:3000` origin per its
  `ALLOWED_ORIGINS=https://rhemata.app` CORS policy (Task 4.5, this same
  packet) — expected dev-environment noise, not a defect.
- A `<html>` hydration-mismatch console warning (server renders without the
  `dark` class/`color-scheme` style, client adds them) on all 3 pages —
  pre-existing, unrelated to this session's changes, a well-known
  next-themes-style pattern usually resolved with `suppressHydrationWarning`
  on `<html>`. Cosmetic console noise only; DOM is correct after hydration
  completes. Not fixed — architectural call, not a one-line patch, and
  outside this task's approved scope.
- `valid-source-maps` (Lighthouse best-practices): expected in this dev
  build configuration, not evaluated further.
- Screen-reader semantics beyond the one dialog-name defect found, deeper
  color-blindness simulation, and admin-only routes were not separately
  audited this pass.
