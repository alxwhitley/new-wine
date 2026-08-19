# Claude Code Prompt — Build the Rhemata marketing landing page at /home

Build a new public marketing landing page, reachable at `rhemata.app/home`.

## Inputs (both attached)
1. **`rhemata-landing.html`** — a standalone HTML mockup. This is the **visual spec only**: use it to understand the layout, section order, the three animated product mockups, and the scroll-triggered animation behavior. **Do not paste its raw HTML/CSS into the app.** It uses hand-rolled CSS variables and system fonts that do not belong in our stack.
2. **`rhemata-landing-copy.md`** — the **source of truth for all copy.** Every headline, subhead, and body line on the page must come from this file, not from the HTML (the HTML contains older, outdated copy). Where the two disagree, the copy doc wins.

## Routing
- Add `/home` as a **new public route** — no auth required, it's a marketing page.
- **Leave the root `/` untouched.** Do not redirect, do not change existing routing behavior. `/home` is simply a new reachable page.

## How to build it
- Rebuild the page as a proper page in our existing stack — Next.js, Tailwind, shadcn/ui, Geist font — not as injected raw HTML.
- All colors, radii, spacing, and typography must use our existing DESIGN.md token system (the `hsl(var(--token))` CSS variables already in our globals). No hardcoded hex values. No Lora/Inter or Google Font imports — Geist for UI, system serif only for scripture/reading display, exactly as the rest of the app does.
- Reuse existing components and patterns wherever they fit rather than inventing new ones.
- Match the dark charcoal theme the app already uses.

## Sections (in this order, copy from the copy doc)
1. Top nav — logo + links (About, Features, Discover, Study) + Log in / Start for free
2. Hero — "Faithful answers from sources you can trust." + the approved subhead + two CTAs
3. "Why it matters" problem section — the general-AI-models contrast
4. Feature: Chat
5. Feature: Discover
6. Feature: Study
7. Stats / corpus depth strip (2,600+ / 1,700+ / 186 / Added Daily)
8. "Explore more" six-card grid
9. Final CTA
10. Footer (with the John 6:63 Greek line)

## The three animated product mockups
The HTML contains three faux-UI mockups (Chat, Study, Discover) that animate on scroll into view:
- **Chat** — the answer streams in word by word, with section headers, ending in thumbs up/down.
- **Study** — the interlinear word blocks highlight in sequence, then a word-definition panel appears, then a commentary card fades in.
- **Discover** — the featured article highlights, sermon cards flash in sequence, author pills pulse.

Recreate these as real components styled with our tokens. The animations should trigger once when each mockup scrolls ~30% into view (use an IntersectionObserver or our existing scroll-animation approach), then settle into final state — no looping. These mockups are illustrative recreations of our real UI; keep them faithful to how Chat, Study, and Discover actually look in the app.

## Acceptance checks
- `/home` loads for signed-out users without redirecting to login.
- `/` behaves exactly as it did before.
- No hardcoded hex; everything resolves through existing tokens; light/dark handled by our theme system.
- All visible text matches `rhemata-landing-copy.md` exactly (including the corrected, copyright-safe lines in Chat and Discover — no "read in full" promise on copyrighted/cold-storage sources).
- The three mockups animate on scroll-in and look like the real product surfaces.
