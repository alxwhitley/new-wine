---
target: frontend/app/library/page.tsx
total_score: 28
p0_count: 0
p1_count: 0
timestamp: 2026-06-15T00-19-00Z
slug: frontend-app-library-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Skeletons + spinners + per-section errors; card-click produces no immediate visual state before spinner |
| 2 | Match System / Real World | 3 | Language natural for charismatic tradition; teacher names and "New Wine Archive" require prior tradition knowledge |
| 3 | User Control and Freedom | 3 | Filter chips allow single-tap dismissal; session-persisted filters retained on return; no URL state for article, no undo |
| 4 | Consistency and Standards | 3 | Author metadata normalized; semantic h3 section headings; minor label hierarchy inconsistency ("Browse by author" styled differently) |
| 5 | Error Prevention | 3 | 2-step delete confirm; Apply Filters stale-closure fixed; constrained inputs |
| 6 | Recognition Rather Than Recall | 3 | Filter chips show active state including on page reload; suggestions dropdown; author pills; source-kind labels |
| 7 | Flexibility and Efficiency | 3 | / shortcut focuses search; session-persistent filters; filter chip dismissal; focus management on article transition |
| 8 | Aesthetic and Minimalist Design | 3 | Reading experience excellent (16px, 65ch, text-balance); discover hierarchy earned; source-kind chips are the one deliberate brand pattern |
| 9 | Help Users Recognize / Recover from Errors | 3 | Per-section error states with retry; search + article + delete errors all plain-language with recovery paths |
| 10 | Help and Documentation | 1 | No contextual help; no author bios; no onboarding for first-time users |
| **Total** | | **28/40** | **Good** |

## Anti-Patterns Verdict

**LLM Assessment:** No AI scaffold tells. The editorial hierarchy is deliberate and structurally varied. The one uppercase/tracking pattern (source-kind chip on featured and supporting cards) is contextual — one label per article, not an eyebrow above every section. No gradient text, no glassmorphism, no hero-metric template.

**Deterministic scan:** `detect.mjs` returned `[]` — zero findings for the fourth consecutive run.

## Overall Impression

The page has crossed into the "Good" band. Six sessions of focused improvement have resolved every P0/P1, both previous P2s, and the major typeset gaps. The reading experience is properly calibrated (16px, 65ch, balanced headings, forward path after reading). The one remaining structural weakness — Help & Documentation (H10 = 1) — cannot be closed with class tweaks; it requires content and flows that don't yet exist. Everything else is P3 polish.

## What's Working

1. **Keyboard efficiency is now real.** `/` focuses search from anywhere, focus returns to search on article close, filter chips dismiss in one tap, and session-persistent filters mean repeat users arrive with their context intact.
2. **Error recovery is complete and honest.** Per-section discover errors, search errors, and article load errors all use plain-language messages ("Couldn't load — check your connection.") with direct retry paths. Nothing fails silently.
3. **The reading experience matches the product promise.** 16px prose, 65ch line length, `text-balance` on the article title, a "More by author" forward path at the end — this now reads like a purpose-built reading tool, not a generic content list.

## Priority Issues

**[P2] Skip-to-content link absent (layout shell)**
- Sam (screen reader / keyboard user) tabs through the full sidebar on every page load before reaching the search bar. The fix is two lines, but it belongs in the layout shell (`frontend/app/layout.tsx` or a shared wrapper), not this file.
- Fix: `<a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-background focus:text-foreground focus:rounded">Skip to content</a>` as the first focusable element in the layout. Add `id="main-content"` to the `<main>` element.
- Suggested command: /impeccable audit

**[P3] No author context for first-time users**
- Teacher names and "New Wine Archive" assume charismatic tradition literacy. Jordan follows "Browse all by Ern Baxter →" to 20 results and still has no frame for who Baxter is or why the corpus is curated.
- Fix: Extend `AUTHOR_DATA` with a `description` field (one line: "Apostolic teacher, New Wine movement, 1970s–80s"). Surface it as a subtitle in the filter sheet (below `{author.years}`) and optionally as a tooltip on author pills.
- Suggested command: /impeccable onboard

**[P3] Article state not URL-persisted**
- Casey reads an article, switches apps, and returns to find the page in Discover mode — the article is gone. Opening a direct link to `/library` never shows the article.
- Fix: Push `?article=<doc.id>` to the URL on article open; read it on mount and trigger `handleCardClick`. Next.js `useSearchParams` + `useRouter.replace` keeps the URL clean without navigation.
- Suggested command: /impeccable harden

**[P3] Help and Documentation remains the score floor**
- H10 = 1 is the only heuristic below 3. There is no in-product help, no onboarding for first-time users, and no contextual tooltips.
- Fix: This is a `/impeccable onboard` scope item, not a polish item. The minimum viable fix: a one-time "first visit" callout on Discover explaining the corpus in two sentences and dismissing permanently to localStorage.
- Suggested command: /impeccable onboard

## Persona Red Flags

**Jordan (First-Timer):** Arrives at Discover. Sees featured "Ern Baxter — Christ's Eternal Lordship." Reads it. Follows "Browse all by Ern Baxter →." Gets 20 results. Has a thread to follow (improvement from run 1). Still has no frame for who Baxter is, what the charismatic tradition is, or what makes this corpus different from a web search. The product delivers content but no onboarding context.

**Sam (Accessibility-Dependent):** `/` now focuses search from anywhere ✓. Article h1 gets focus on open ✓. Focus returns to search on article close ✓. aria-live result count ✓. sr-only filter chip labels ✓. h3 section headings ✓. **Remaining gap:** Still no skip-to-content link — Sam must tab through the sidebar's 4+ nav links before reaching the search bar on each hard page load.

**Casey (Distracted Mobile):** Bottom sheet on mobile ✓. min-h-[44px] throughout ✓. Filter chips tap-dismissible ✓. Session-persistent filters mean the author selection is retained if Casey closes and reopens the tab ✓. **Remaining gap:** The specific article being read is not URL-persisted — a forced page refresh or interrupted session still loses the article view.

## Minor Observations

- The lazy `useState` initializer reads localStorage with an SSR guard (`typeof window === "undefined"`) — technically safe since this is a `"use client"` component, but the guard prevents any hydration surprises.
- `aria-keyshortcuts="/"` is correctly placed on the input element (not a wrapper). Screen readers that support this attribute will announce it.
- The `article` dependency in the slash-shortcut `useEffect` correctly prevents `/` from interfering with the article reader.
- `rhemata:library:authors` and `rhemata:library:era` as storage keys are well-scoped and won't collide with other future library features.

## Questions to Consider

- "What would a two-sentence corpus intro at the top of Discover look like — dismissable, never re-shown — that gives Jordan enough context to understand why they should care about these specific teachers?"
- "Is URL state for the article reader worth the router integration, or is a 'recently read' list in localStorage a lower-effort substitute that serves Casey's recovery scenario equally well?"
- "H10 is the only thing keeping this below 30/40. What's the minimum viable onboarding that could move it from 1 to 2?"
