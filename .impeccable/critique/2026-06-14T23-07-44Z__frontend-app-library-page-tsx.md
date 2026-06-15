---
target: frontend/app/library/page.tsx
total_score: 26
p0_count: 0
p1_count: 1
timestamp: 2026-06-14T23-07-44Z
slug: frontend-app-library-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Skeletons + spinners present; discover API failures swallowed silently (sections appear empty with no error) |
| 2 | Match System / Real World | 3 | Domain language is natural; "Watch source" slightly generic, "New Wine Archive" assumes tradition knowledge |
| 3 | User Control and Freedom | 3 | Clear back nav; active filters not dismissible without reopening the sheet |
| 4 | Consistency and Standards | 3 | Cards consistent in discover; author display inconsistent between search cards (uppercase tracked) and discover cards (plain) |
| 5 | Error Prevention | 3 | Delete is 2-step; retry wired; no invalid combinations possible |
| 6 | Recognition Rather Than Recall | 3 | Suggestions, author pills, type labels help; applied filter state invisible without re-opening sheet |
| 7 | Flexibility and Efficiency | 2 | Enter key + author pills work; no / shortcut, no filter chips, no session persistence |
| 8 | Aesthetic and Minimalist Design | 3 | Hierarchy clear; hero → cards → flat list works; card grid repeats identical structure |
| 9 | Help Users Recognize / Recover from Errors | 2 | Article + search retry added; discover section API failures silently swallowed — empty page, no retry path |
| 10 | Help and Documentation | 1 | No contextual help; no tooltips on corpus terms; no onboarding |
| **Total** | | **26/40** | **Acceptable** |

## Anti-Patterns Verdict

**LLM Assessment:** Page no longer reads as generic AI scaffold. Editorial hierarchy is deliberate and correct. Two residual slop tells: (1) Browse tile sublabels still use `uppercase tracking-wide`; (2) Author metadata in search result cards uses `uppercase tracking-wide`. Both are defensible in context but read as habit rather than choice.

**Deterministic scan:** `detect.mjs` returned `[]` — zero findings. All previously flagged patterns clean.

## Overall Impression

Page is in genuinely solid shape: correct IA, working error states, no AI scaffolding in the structure. Score plateau (24 → 25 → 26) reflects that remaining gaps are interaction depth and edge-case robustness (new code) rather than class tweaks. Biggest single opportunity: filter state visibility.

## What's Working

1. Discover hierarchy is earned — no-card hero → small supporting cards → count tiles → flat archive list, each level correctly signals importance.
2. Skeleton loading is structurally honest — mirrors actual layout proportions.
3. Copy is specific and warm — earned sentences, not placeholder prose.

## Priority Issues

**[P1] Discover section failures are invisible**
- All discover data loads via `Promise.allSettled()` with per-fetch `.catch(() => {})`. API failures render sections empty with no error and no retry. Users see empty library with no path to recover.
- Fix: Per-section error state. Check which sections got data vs failed. Show inline "Couldn't load — try refreshing" for failed sections.
- Suggested command: /impeccable harden

**[P2] Applied filters are invisible**
- Active filter badge shows count (`2`) but not which filters. No chip tags. No way to remove a single filter without reopening the full sheet.
- Fix: Below search bar, render dismissible chips from `selectedAuthors` + `eraFilter`. Each chip clears its own filter and re-fetches.
- Suggested command: /impeccable harden

**[P2] Focus not managed on article view transition**
- React swaps entire layout on article open/close. Focus is not moved. Screen reader users hear nothing; keyboard users lose focus position.
- Fix: On article state → truthy, move focus to article `<h1>` via ref. On close, return focus to the card that launched it.
- Suggested command: /impeccable audit

**[P2] Article reader renders at 14px body text**
- `prose-sm` = 14px base. For a reading-focused experience (Readwise analog per PRODUCT.md), this is minimum legible size.
- Fix: Change `prose-sm` to `prose` (16px base).
- Suggested command: /impeccable typeset

**[P3] No path forward after reading**
- Article reader ends with only "Back to Discover." No "more by this author," no related content, no next article. Emotional valley at the product's peak moment.
- Fix: Footer with 2-3 "More by [author]" cards or a simple "Find more by {author} →" link triggering `handleSuggestionClick(article.author)`.
- Suggested command: /impeccable onboard

## Persona Red Flags

**Jordan (First-Timer):** Sees featured Ern Baxter article with no context about who he is. "New Wine Archive" requires prior tradition knowledge. Reads article, returns to Discover, has no thread to pull. Exits having read one piece with no clear next step.

**Sam (Accessibility):** Focus not moved on article load/close — 15-20 tab stops to reach article content after card click. No `aria-live` for result count announcements. No skip-to-content link. `renderBookCard` is a `<div>`, not a `<button>` — not keyboard-activatable.

**Margaret (Weekly User):** Filter state lost between sessions — re-selects Derek Prince every visit. Applied filters only visible as a count badge. After reading an article, no path to the next one — must navigate back and scan results list manually.

## Minor Observations

- Browse tile sublabels (`uppercase tracking-wide`) and search card author metadata both still use the eyebrow reflex class combination; drop transforms to make the choice deliberate.
- `max-w-2xl` + `max-w-none` prose gives ~85-90ch line length — exceeds 65-75ch spec. Add `max-w-prose` inside article content div.
- "Watch source" link: `px-3 py-1` ≈ 28px height — below 44px touch target. Needs `py-2` minimum.
- `renderBookCard` renders as `<div>` not `<button>` — inconsistent with doc cards, not keyboard activatable.

## Questions to Consider

- "What would it look like if Margaret's last author filter was still there on return — is session persistence worth the complexity?"
- "The article reader ends with a back button. What if it didn't — what if the content page had a footer that felt like an invitation rather than an exit?"
- "The author pills search by name. Is text search the right affordance for author filtering, or should a pill set a persistent author filter?"
