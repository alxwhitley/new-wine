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
- **A green Vercel deploy can ship stale compiled CSS — the build status is not
  evidence your `globals.css` changes are live, 2026-09-05.** This is the
  entry above's Turbopack cache defect, but on Vercel's restored build cache
  rather than the local dev server, and it reached production. A push added
  three new blocks to `globals.css` plus new Tailwind utilities in
  `app/page.tsx`. The build reported success in 24s; the served bundle
  contained the new **utilities** but none of the three `globals.css` blocks,
  so the page rendered a floating composer with no fade and no mobile sheet —
  visibly worse than before the change. **The cache is not keyed on
  `globals.css` content**: that file had genuinely changed and was still served
  stale, so touching it again (a comment, a whitespace edit) does not bust it.
  Two things follow. (1) **Verify by bytes, not by status.** Run a clean local
  `npm run build` and compare the served chunk's size and rules against
  `.next/static/**/*.css` — the discrepancy here was 113,839 vs 114,949, and
  the 1,110-byte gap was exactly the three missing blocks. Grepping for a rule
  is enough; do not infer presence from a green check or from other rules in
  the same file being present. (2) The fix is disabling the build cache —
  `VERCEL_FORCE_NO_BUILD_CACHE=1` is now set on the `newwine` project
  (Production scope); a cache-free build takes ~52s against ~24s. If that
  variable is ever removed, this failure returns silently. Two traps while
  checking: the minifier collapses `top/right/bottom/left` into `inset:auto 0
  0`, and Tailwind 4 emits `touch-pan-up` as `--tw-pan-y:pan-up` rather than a
  literal `touch-action:pan-up`, so a strict regex reports a false MISSING.
- **`frontend/.vercel/project.json` points at the retired `rhemata` Vercel
  project, not `newwine` — 2026-09-05.** The live project is `newwine`, whose
  Root Directory is `frontend/`, so **the Vercel CLI must be run from the repo
  root**, never from `frontend/`. Running it from `frontend/` picks up that
  stale link and targets the wrong project entirely: it does not error in a way
  that names the real problem, it fails with `The specified Root Directory
  "frontend/" does not exist`, and it creates a failed Production deployment in
  the retired project's history (one exists from this session). A repo-root
  deploy also needs `--archive=tgz`, since the uncompressed upload exceeds
  Vercel's 15,000-file limit — but there is no `.vercelignore`, so that archive
  packs ~549MB of `node_modules`. Prefer `vercel redeploy <url> --target
  production` from the repo root over a fresh CLI upload.
- **Tailwind scans code comments AND markdown under `frontend/`, so
  class-shaped prose ships as real CSS — 2026-09-05, hit twice in one
  session.** Neither instance is visible in a source diff, which is why they
  reach production. (1) A comment in `app/page.tsx` referring to the scroller's
  padding by its utility name — a `pb-` prefix with an arbitrary value in
  brackets — was extracted as a candidate and emitted as a real rule whose
  declaration was **invalid CSS** (a bare custom-property name as a value).
  Caught only by grepping the built bundle. (2) Writing the plain word
  "contents" in this very file generated `.contents` (harmless, 27 bytes, but
  it proves markdown here is scanned). Rule: never write a utility-shaped token
  in a comment or a doc — describe it in words instead — and diff the generated
  CSS after any change that touches comments or `frontend/*.md`, not just after
  changes to class attributes.
