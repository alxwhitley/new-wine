---
target: frontend/app/library/page.tsx
total_score: 27
p0_count: 0
p1_count: 0
timestamp: 2026-06-15T00-09-05Z
slug: frontend-app-library-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Skeletons + spinners present; per-section discover errors now visible; card-click produces no immediate feedback before spinner |
| 2 | Match System / Real World | 3 | Language is natural for charismatic tradition; "New Wine Archive" and teacher names require prior tradition knowledge |
| 3 | User Control and Freedom | 3 | Filter chips allow single-tap filter dismissal; focus returns to search on article close; no session persistence or undo |
| 4 | Consistency and Standards | 3 | Author metadata normalized across card types; section headings semantic h3; one minor label hierarchy inconsistency ("Browse by author" vs section h3s) |
| 5 | Error Prevention | 3 | 2-step delete confirm; Apply Filters stale-closure bug fixed; inputs are constrained |
| 6 | Recognition Rather Than Recall | 3 | Filter chips show active state; suggestions dropdown; author pills; source kind labels on all cards |
| 7 | Flexibility and Efficiency | 2 | Filter chip dismissal efficient; focus management added; still no `/` keyboard shortcut for search; no session persistence |
| 8 | Aesthetic and Minimalist Design | 3 | Reading experience now excellent (16px, 65ch, text-balance); discover hierarchy earned; source-kind chips are the one deliberate brand pattern |
| 9 | Help Users Recognize / Recover from Errors | 3 | Per-section error states with retry paths; search error with retry; article error with retry; all plain-language messages |
| 10 | Help and Documentation | 1 | No contextual help; no author biographies; no onboarding for first-time users |
| **Total** | | **27/40** | **Acceptable → approaching Good** |

## Anti-Patterns Verdict

**LLM Assessment:** The page no longer reads as generic AI scaffold. The editorial hierarchy is deliberate and earned — no-card hero → supporting → count tiles → flat archive list. The one deliberate uppercase/tracking pattern (source-kind chip on featured and supporting cards) is explicitly contextual — one label per article card, not a section eyebrow above every heading. This reads as voice, not reflex. No gradient text, no glassmorphism, no hero-metric template detected.

**Deterministic scan:** `detect.mjs` returned `[]` — zero findings. All anti-patterns clean.

## Overall Impression

The page has meaningfully graduated in this session. Error recovery is now complete (per-section errors + retry), typography is correctly tuned for reading (16px, 65ch, balanced headings), and the filter state is visible at a glance (chips). The critical valleys are closed: after reading an article, there's now a forward path ("Browse all by [author]") instead of just "Back." The one remaining gap that limits the score ceiling is the help/documentation dimension — first-time users still have no context for teacher names, no onboarding path, and no way to understand the corpus without prior tradition knowledge.

## What's Working

1. **Error recovery ecosystem is complete.** Per-section discover failures each have their own "Couldn't load — check your connection. Try again" with a direct retry. Article load errors, search errors, and delete errors all handled. This went from the P1 gap to a genuine strength.
2. **Article reading experience is properly typeset.** 16px body (up from 14px), 65ch line length (up from ~85ch), `text-balance` on the title, prose-invert correctly configured. The reading experience now matches the "Readwise Reader for reading" aspiration in PRODUCT.md.
3. **Discover hierarchy is compositionally coherent.** Hero (no card wrapper) → supporting (200px image placeholder) → count tiles → author scroll → flat archive list → books shelf. Each level signals its own importance through structure, not decoration.

## Priority Issues

**[P2] No keyboard shortcut to focus the search bar**
- The primary action — searching — has no keyboard accelerator. Users must click the search input or tab to it from the top of the page (multiple stops).
- Why it matters: Any user who knows what they want (the product's primary use case — "a lay reader asks a genuine spiritual question") must mouse to begin. A `/` shortcut is conventional and expected.
- Fix: `useEffect` with a `keydown` listener for `/` that calls `searchInputRef.current?.focus()` when no input is active. Add `aria-keyshortcuts="/"` on the search input.
- Suggested command: /impeccable polish

**[P2] No session persistence for filter selections**
- Repeat users (Margaret) re-select their preferred teachers on every visit. Active filters are now visible (chips), but they reset on page reload. This is the single biggest friction point for weekly users.
- Why it matters: The product's repeat-user scenario (mid-week return for a specific teacher's sermons) hits this every time.
- Fix: On filter change, write `{ selectedAuthors, eraFilter }` to `localStorage`; read on mount. Two `useEffect` calls, no server dependency.
- Suggested command: /impeccable harden

**[P3] No author context for first-time users**
- "Ern Baxter", "Bob Mumford", "Charles Simpson" are meaningful names within the tradition but opaque to newcomers. The filter sheet, author pills, and "More by [author]" footer all assume prior knowledge.
- Why it matters: Jordan (first-timer) sees a featured Ern Baxter article, reads it, searches "Ern Baxter," and doesn't know if they should — they don't know what to expect.
- Fix: One-line author descriptor in the filter sheet (already shows `{author.years}`) — add `{author.tradition}` or `{author.description}` if the `AUTHOR_DATA` constant can be extended. Alternatively, a tooltip on the author pills.
- Suggested command: /impeccable onboard

**[P3] Skip-to-content link absent for keyboard users**
- Sam (screen reader) tabs through sidebar links before reaching main content. The page has no skip link.
- Why it matters: 15–20 tab stops in the sidebar before reaching the search bar on each page load.
- Fix: Add a visually hidden `<a href="#main-content">Skip to content</a>` as the first focusable element in the layout shell, revealed on focus. Standard WCAG technique.
- Suggested command: /impeccable audit

## Persona Red Flags

**Jordan (First-Timer):** Arrives on Discover, sees "Ern Baxter — Christ's Eternal Lordship" featured. Clicks it, reads it, reaches the footer: "Browse all by Ern Baxter →." Clicks through to search results. Sees 20 Baxter articles with no context about who he is or why this matters. The experience delivers content but no frame — no "who is this teacher?", no "why is this tradition significant?" Jordan exits having read one article with no mental model of the corpus.

**Sam (Accessibility-Dependent):** Article h1 receives focus on open (tabIndex={-1}, ref-driven) ✓. Focus returns to search on article close ✓. aria-live result count ✓. sr-only labels on filter chips ✓. aria-label on filter button ✓. h3 headings on section labels ✓. Book cards with document_id render as `<a>` ✓. **Remaining gap:** no skip-to-content link — Sam must tab through the entire sidebar (4+ nav links) before reaching the search bar on each page load.

**Casey (Distracted Mobile):** Bottom sheet for filters on mobile ✓. min-h-[44px] on all tap targets ✓. Author pills scroll horizontally ✓. "Watch source" button now min-h-[44px] ✓. Filter chips are tap-dismissible ✓. **Remaining gap:** if Casey reads an article, locks the phone, and returns to the same URL, the article state is lost — the app reloads in discover mode. State is not persisted to URL or localStorage.

## Minor Observations

- `source_kind` chip in the hero (`tracking-[1.3px] uppercase text-primary`) is a deliberate single-instance brand pattern. The same chip appears on supporting cards. This is correct; the detect.mjs agrees. No change needed.
- The "Browse by author" section label is styled differently from the other three section h3s (smaller, muted, span) — the intent is clear (it's a label for a scroll strip, not a primary section) but the inconsistency is visible on inspection.
- `content_summary` is gated on truthiness, so the featured hero and supporting cards render without excerpt when the field is empty — appropriate behavior.
- The `<a href={/library/book/${document_id}}>` pattern for book cards with a document_id doesn't open in a new tab — consistent with the rest of the in-app navigation. ✓

## Questions to Consider

- "What would the Discover page look like if it opened with a 'Start here' prompt for first-time visitors — a single featured teacher with one line of context — and then progressively revealed the full library hierarchy?"
- "Session filter persistence requires no server infrastructure — is the concern about complexity, or is there a specific reason it hasn't been added?"
- "The skip-to-content pattern is two lines. What's blocking a quick audit pass before the next release?"
