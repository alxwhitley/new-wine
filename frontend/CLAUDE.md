@AGENTS.md

## Frontend landmines (moved from the root CLAUDE.md, 2026-08-31)

These fire only when working under `frontend/` — they load with this file
rather than costing every session at the repo root.

- **`--primary` (the gold brand token, `frontend/app/globals.css`) is used
  three conflicting ways — no single shade satisfies WCAG AA in all three,
  2026-08-28.** (1) white text on `bg-primary` (`Button`'s default variant,
  `Badge`, 15+ call sites), (2) dark text on `bg-primary` (chat Send button,
  `text-background`), (3) `text-primary` as a plain link/accent color on the
  dark background, 28+ files. A Python WCAG contrast sweep at this hue/
  saturation confirmed the passing ranges for (1) and (2)/(3) don't overlap
  — darkening `--primary` to fix (1) (as first approved and briefly shipped
  this session, then reverted) breaks (2) and (3). The actual fix: leave
  `--primary` untouched, flip `--primary-foreground` from white to the same
  dark shade (2) already used — every `text-primary-foreground` call site is
  paired with `bg-primary` (confirmed by grep), so this fixes (1) by making
  it identical to the already-passing (2) pairing, with zero effect on (2)
  or (3). Before touching either token again, re-read
  `docs/audits/2026-08/b6_accessibility_pass_2026-08-28.md`'s "The
  `--primary` conflict" section — the full math is there, not repeated here.
- **The Next.js/Turbopack dev server can silently serve stale compiled CSS
  after a `globals.css` token edit — 2026-08-28.** Editing a `:root` CSS
  variable and reloading the browser (even with a full process
  kill+restart of `next dev`) served the OLD value from a persistent
  `.next/dev/static/chunks/*.css` cache; confirmed by curling the compiled
  CSS chunk directly and finding the pre-edit value byte-for-byte, twice,
  across two separate restarts. Only `rm -rf .next` before restarting
  actually picked up the change. Any session verifying a CSS token change in
  a real browser must `rm -rf frontend/.next` before restarting `next dev`,
  not just kill and relaunch the process — a plain restart looks like it
  worked (fresh PID, "Ready" banner) but silently isn't.