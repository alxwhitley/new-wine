# Claude Code Prompt — Redesign the "Why It Matters" section on /home

Replace the existing "Why It Matters" section on the `/home` landing page. It's currently a single wall of body text; rebuild it as a two-column contrast that makes the general-AI-vs-Rhemata argument visual.

## Input (attached)
`why-it-matters-preview.html` — a standalone HTML mockup of the new section, built in our DESIGN.md tokens. Use it as the **visual + copy spec**. Do not paste its raw HTML/CSS into the app — rebuild it as a proper component in our stack (Tailwind + shadcn + our existing token variables), consistent with how the rest of `/home` was built.

## What changes
Keep the section's eyebrow label ("Why It Matters") and the serif headline ("When you ask general AI about God, who's actually answering?"). Everything below the headline becomes:

1. **A two-column contrast** (stacks to one column on mobile):
   - **Left column — "General AI models"** (muted treatment, ✕ markers): four points —
     - Averages every tradition, blog, and contradicting opinion into one flattened answer.
     - No source is trusted over another.
     - Applies its own content filters to theology — softening or avoiding positions it's trained to treat as sensitive.
     - No name stands behind the answer.
   - **Right column — "Rhemata"** (subtly lifted: faint gold-tinted border + the darker accent fill, ✓ markers): four points —
     - Drawn only from vetted sources within the charismatic tradition.
     - No hidden filters — your convictions aren't treated as something to soften.
     - Every answer points back to the voices behind it.
     - You always know whose shoulders an answer stands on.
   - Each column has a small tag label at top with a colored dot (muted dot left, gold dot right) and a short serif subhead ("Everything at once. No one in particular." / "A known, trusted lineage.").

2. **A pull-quote** below the columns, centered, serif italic, with "a stranger with no name" emphasized in gold:
   > "You wouldn't take spiritual counsel from a stranger with no name."

3. **A closing resolution line** under the quote, centered, muted:
   > In matters of faith, *who* is speaking matters. Rhemata is built on voices you'd actually choose.

## Styling rules (same as the rest of /home)
- All color via our existing `hsl(var(--token))` variables — no hardcoded hex. Gold accents use the same primary/gold-accent token the page already uses.
- Geist for UI text; system serif only for the headline, column subheads, and pull-quote.
- Flat depth — borders and spacing, not shadows. The right column's "lift" is a faint gold border + accent-fill background, nothing heavier.
- The two columns must be height-matched at desktop width (both have four bullets now).
- Keep it within the existing page's max-width and vertical rhythm.

## Out of scope
- Don't touch any other section, the routing, or the named-voices list in the Chat section (those stay where they are).
- No new fonts, colors, radii, or shadows beyond what's already in the token system.

## Acceptance checks
- Section renders as two columns on desktop, single column stacked on mobile.
- All copy matches the spec above exactly, including the content-filter bullet.
- No hardcoded hex; everything resolves through existing tokens; works in the app's dark theme.
- Column heights match at desktop width.
