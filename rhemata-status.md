# rhemata-status.md

**As of:** 2026-07-14 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority: the Inline Study Panel's frontend shell is live in the app for the first time — commit `161c4de`.** Alex can open `localhost:3000`, tap a real verse reference in a finished chat answer (or the dev-only "Study preview" button / Cmd·Ctrl+Shift+S), and see the actual panel-in / sidebar-out motion. Screenshots + desktop and mobile screen recordings are at `~/Desktop/study-panel-review/` for Alex to judge the motion directly.
- **Naming correction, surfaced not silently absorbed:** the build brief for this session called this work "SP0," but PLAN.md's own numbering says SP0 (#38) is the *mockup* step and what actually got built matches **SP2 (#40) — panel frontend**, minus two things SP2's line item explicitly names that this session did NOT build: no kill switch / feature flag (the panel is unconditionally live for anyone who taps a reference or hits the dev shortcut — there's no beta-gating flag anywhere in this code), and no SP1 (#39) backend reference-pointer system (hidden pointers with fail-quiet resolution against the full verse/teacher corpus). Instead, a much narrower client-side regex detector (`lib/study-reference.ts`) scans already-rendered, finished answer text for explicit `Book Chapter:Verse` patterns. It only catches verses the model happens to spell out in that exact shape — it is not SP1's backend and was never meant to be; it was the cheapest way to give this session one genuine, real (not simulated) trigger without waiting on SP1.
- **SP3 (tool rows: interlinear/translations/cross-references) remains hard-gated and untouched** — its gate is "#12 done (true, see below) + a word-level-tagged licensed text source confirmed (still open, unrelated to this session)." The panel's three tool rows ship as honest, styled "coming soon" stubs, not real content.
- **Carried forward, unrelated track:** PLAN #12 (`ingest_lexicon.py` conversion) finished the session before this one (commit `33e92b4`) — a full lexicon batch run is proven-ready but not scheduled. See "Where We Are in the Roadmap" below; this session did not touch that track at all.

---

## This session (2026-07-14) — Inline Study Panel: shell + motion

**One commit: `161c4de`.** Files: `frontend/app/page.tsx`, `frontend/components/rhemata/chat-message.tsx`, `frontend/components/rhemata/sidebar.tsx` (all modified), `frontend/components/rhemata/study-panel.tsx` + `frontend/lib/study-reference.ts` (new).

**What's real:**
- Verse references in **finished** assistant answers (never mid-stream — underlines only render once `isStreaming` is false) render as tappable underlines via a conservative, fail-quiet regex (`detectVerseReferences` — book name/abbreviation immediately followed by `chapter:verse`, no confident match ever falls back to anything but plain text).
- Tapping one opens the panel and fetches the real verse text from Supabase's `verses` table (public-domain WEB text) — the one genuinely real, non-source-gated content in the shell.
- Desktop: panel slides in from the right (~33vw, clamped 380–480px), transparent overlay (chat stays visible underneath, per spec "expansion not navigation"). Mobile (`useIsMobile`, 768px breakpoint): full-screen sheet with a dark scrim and a grab-handle affordance.
- The left sidebar collapses (`-translate-x-full`) in the same 300ms motion as the panel opening, and the chat's own bordered card now genuinely resizes to occupy the remaining ~two-thirds width (a second-pass self-review catch — see below) rather than staying full-width and having its right edge silently covered by the panel.
- Pin/unpin (cap 4) with a small edge-tab re-entry point that appears only when the panel is closed and at least one pin exists.
- Close via the panel's own close button, backdrop click (mobile), or Escape — all handled by the underlying Radix `Dialog` primitive, which also owns focus-trap and background scroll-lock for free.
- `prefers-reduced-motion` disables all transform/opacity animation via Tailwind's `motion-reduce:` variants.
- A dev-only trigger (bottom-right pill button, and Cmd/Ctrl+Shift+S) opens the panel to a fixed demo reference (Romans 8:28) regardless of chat content, so the motion is demonstrable without needing a real chat turn first.

**What's honest empty state, not real content (all correctly source-gated, none faked):** "Your teachers on this verse" (always says no teacher addresses it yet — no teacher-content backend exists), and the three tool rows (Interlinear / Translations / Cross-references — each expands to a plain "coming soon" line). "Open in Study" is a real link to the untouched old `/study` page, per spec's fallback-surface requirement.

**Self-review loop (spec required at least two full passes before presenting):**
1. **First pass:** caught inconsistent padding (`px-5`/`py-5` instead of the app's established `px-4`/`py-4` convention) in the panel header and body — fixed, re-screenshotted.
2. **Second pass:** caught that the chat's bordered card wasn't actually resizing when the panel opened — it stayed full-width (because only the sidebar's margin collapsed, not the main content's own width), so the panel was silently overlapping and hiding the card's right border/rounded corner instead of the two genuinely resizing side-by-side. Fixed by reserving the panel's own width as right padding on `<main>` when open (`app/page.tsx`, kept in a code comment tied to `study-panel.tsx`'s width so the two don't silently drift apart). Re-screenshotted and confirmed the chat card now visibly meets the panel edge with its own border intact.
3. Also chased down one intermittent Playwright test failure under a `reducedMotion: "reduce"` browser context (1 timeout in an early batch of runs). Direct DOM/computed-style inspection twice confirmed the panel renders correctly under reduced motion (opacity 1, correct position, visible); a follow-up batch of 4 consecutive runs all passed cleanly, and the reduced-motion screenshot itself (`07-reduced-motion-open.png`) shows a clean render. Concluded: dev-server/Turbopack cold-compile timing flakiness in the test harness, not a product defect — not something fixed in the component code because there was nothing there to fix.

**Verified before commit:**
- `tsc --noEmit`: clean.
- `eslint` on all five touched/new files: two `react-hooks/set-state-in-effect` errors, both pre-existing-pattern noise, not something introduced by this session — confirmed by running the same rule against `hooks/useUserRole.ts` (untouched, established code), which trips the identical error on the identical "set loading state at the top of a data-fetching effect" pattern. This rule ships in `eslint-config-next@16.2.2`'s core-web-vitals config but is not part of the actual build gate — Next.js 16 no longer runs `next lint` as part of `next build` (confirmed in `node_modules/next/dist/docs/` per `frontend/AGENTS.md`'s own instruction to check there first).
- Old `/study` page: loaded directly, screenshotted, confirmed visually and functionally unchanged (screenshot `08-old-study-page-untouched.png`). Its only console errors are pre-existing CORS failures against the production Railway backend from localhost — unrelated to this session, present before it.
- Chat view with the panel closed: confirmed visually unchanged from before this session (screenshot `01-desktop-closed.png`).
- The one hydration console warning seen everywhere (including on the closed chat view and the untouched `/study` page) is a pre-existing `next-themes` SSR/client class-mismatch quirk, unrelated to and not introduced by this session.

**Review artifacts (not committed — copied out of the ephemeral scratchpad for Alex):** `~/Desktop/study-panel-review/` — 8 screenshots (desktop closed/open, mobile closed/open, pinned, edge-tab, reduced-motion, old `/study` page) + `desktop-open-close.mp4` + `mobile-open-close.mp4` (the actual open→close motion, converted from Playwright's `.webm` output since macOS QuickTime doesn't play webm natively).

**Deliberately not done this session (explicitly out of scope per the brief):** SP1's real backend reference-pointer system; SP3 interlinear/word-study or any other real study content; any edit to the old `/study` page; a kill switch / beta flag (see the naming-correction note above — this is a real gap against SP2's own line item, not an oversight to gloss over); backend/scripts/ingest work of any kind; the lexicon batch run or Sermonindex batches; CLAUDE.md's stale notes.

**Dev server:** left running at `localhost:3000` (started this session) so Alex can try the real thing immediately, not just watch the recordings.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list, plus the SP track added 2026-07-13)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end.
- **#6 (aliases + sentinel cleanup + strict mode):** DONE.
- **#7 (`documents.full_text` chokepoint):** DONE.
- **#8 (convert `ingest_magazine.py`):** DONE.
- **#9 (build `psycopg2_batch`, convert `ingest_preceptaustin.py`):** DONE. No production PA re-ingest has run.
- **#10 (convert `ingest_commentaries.py`):** still next on this track whenever Alex picks it back up — untouched, independent of the SP track below.
- **#11 (build `on_existing="reuse"` chunk-dedup):** DONE.
- **#12 (convert `ingest_lexicon.py`):** DONE (prior session, commit `33e92b4`). Full batch not run — separate session, unrelated to this one.
- **#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE. Folder renames and the `jewish_perspectives` drop remain open.
- **SP38 (SP0 — finish mockups):** still nominally open per PLAN.md's own line item (mobile bottom-sheet mockup), though this session shipped a working mobile full-screen sheet directly in code — Alex's call whether the mockup step is now moot or still wants doing formally.
- **SP39 (SP1 — reference-pointer backend):** NOT built. This session's client-side regex detector is a narrow stand-in for one trigger path, not this item.
- **SP40 (SP2 — panel frontend):** the shell/motion/pin/close/keyboard piece is now built and live in code (this session, `161c4de`) — but without SP2's own named kill switch / beta flag, and without SP1 underneath it. Whether that's "SP2 done modulo two items" or "a separate pre-SP2 shell pass" is a framing question for Alex, not resolved here.
- **SP41 (SP3 — tool rows):** untouched, correctly hard-gated (see Current Priority above).
- **SP42–43:** untouched.

---

## Open Flags

**New:**
16. **No kill switch / beta flag exists for the Study Panel.** SP2's PLAN.md line item explicitly names "behind kill switch" and "beta-flagged" — this session's build has neither. The panel is unconditionally live to anyone who taps a detected verse reference. Worth an explicit decision before this reaches beyond Alex's own testing.
17. **The verse-reference detector is a narrow client-side stand-in, not SP1.** It only catches explicit `Book Chapter:Verse` text the model happens to print; it does not resolve teacher mentions, does not use fail-quiet corpus matching, and generates no hidden pointers. If SP1 is later built, this detector likely gets replaced rather than extended.
18. **A full lexicon batch run is still ready but not scheduled** (carried from the prior session, untouched here — see PLAN #12 above).
19. **SP3's ingest-layer gate is cleared; its data-source gate is not** (carried from the prior session, untouched here).

**Carried forward, unchanged:**
1. Rule 10 freeze is a bare-substring match, not an invocation check — recurs for `ingest_helloao.py`, `ingest_commentaries.py` only.
2. Magazine queue hard pre-ingest gate — 27 of 27 pending articles contaminated. Unresolved, untouched.
4. Database-number verification gap. Not exercised this session.
5. `GOVERNED_FILES` gap (`guard_pretooluse.py`/`settings.json`). Untouched this session.
6. PLAN.md #5.5 closing line is stale. Needs Alex's explicit go-ahead on replacement wording.
7. PLAN.md #14 drift — folder renames and the `jewish_perspectives` drop still open.
10. CLAUDE.md's "unconverted scripts" count is stale (says four, real count is two: `ingest_helloao.py`, `ingest_commentaries.py`). Untouched this session.
12. PA's ~398 "excerpt-less" documents — unrelated to this session.
13. The "PA's survivability guard will now rarely fire" claim is still unconfirmed against real data.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else beyond a session's real change: modified `SKILL.md` (unrelated pre-existing drift) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision. Confirmed present and unchanged at this session's close — deliberately left out of this session's commit (`161c4de`), which contains only the five Study Panel files.

---

## Next Session Should

Alex's call between several independent, unblocked options: (a) decide on the kill-switch/beta-flag gap flagged above before showing the Study Panel beyond his own testing, (b) schedule the full lexicon batch run (mechanism proven, ready — see PLAN #12 history), (c) the short PA follow-up (`generate_excerpts.py` against 396 complete-but-unexcerpted docs; REDO the 2 broken ones), (d) #10 — convert `ingest_commentaries.py`, or (e) scope SP1's real backend reference-pointer system if the Study Panel direction is confirmed. All are independent.
