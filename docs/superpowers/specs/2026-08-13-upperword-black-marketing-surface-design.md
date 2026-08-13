# UpperWord Black Marketing Surface Design

**Date:** 2026-08-13
**Status:** Approved design, pending written-spec review

## Objective

Adapt the existing `/home` landing page to a near-black, warm-white marketing surface inspired by Powder's restrained editorial presentation. Preserve UpperWord's own identity, content structure, and upper-room hero rather than reproducing the reference site's branding or page architecture.

The immediate goal is to give future gray product screenshots strong separation from the landing-page canvas. Outdated product mockups must not survive this pass.

## Scope

### Preserve

- The current landing-page section order and marketing copy below the hero.
- The upper-room background video and scroll-driven hero product reveal.
- Existing authentication and CTA behavior.
- Current responsive page behavior unless a small correction is required by the visual adaptation.
- Existing semantic heading order, keyboard behavior, and WCAG AA baseline.

### Change

- Restyle the landing page with a local near-black, warm-white, and stone-gray palette.
- Replace gold accents on the landing page with warm white or restrained neutral states.
- Replace every outdated product mockup with an intentional product-image placeholder.
- Remove fabricated UI content and mockup-specific animation code that no longer represents the application.
- Simplify cards, feature treatments, and separators to flat black surfaces with subtle charcoal rules.
- Replace decorative emoji feature icons with neutral monochrome treatments or text-only labels.
- Tighten spacing or hierarchy only where necessary to make the new surface coherent.

### Do Not Change

- The authenticated application design system or its global product colors.
- Backend behavior, data flows, authentication contracts, or answer-generation paths.
- Marketing information architecture, positioning claims, or doctrinal content.
- Static `/sources` and `/beliefs` page design in this pass.
- Product screenshots; none are currently approved for use.

## Visual System

The landing page uses a locally scoped marketing palette:

- **Canvas:** near-black, visually distinct from the application's gray surfaces.
- **Primary text:** warm white rather than pure white.
- **Secondary text:** muted stone gray with WCAG AA contrast at its rendered size.
- **Primary actions:** warm-white fill with near-black text; hover darkens slightly without introducing color.
- **Secondary actions:** transparent or near-black surface with a charcoal border and warm-white text.
- **Rules and frames:** subtle charcoal borders.
- **Product placeholders:** gray surfaces lighter than the page canvas, with a quiet border and no heavy shadow.

No gold, colored gradients, colorful cards, or ornamental accent palette is introduced. The upper-room video's natural light remains the page's only warm chromatic element.

The palette must be scoped to the landing page or its marketing components. It must not mutate the global Lumen tokens used by the application.

## Hero

- Keep the supplied upper-room video as the full cinematic background.
- Keep the existing left-aligned UpperWord copy in the dark wall area.
- Render the eyebrow as restrained uppercase metadata without a colored dot or prominent pill treatment.
- Use a warm-white primary CTA and a quiet neutral secondary CTA.
- Keep the scroll-driven product reveal, but render it as the same intentional placeholder system used below the fold.
- Preserve the video's original loop for this pass; editing its near-black midpoint is separate asset work.
- Maintain sufficient contrast throughout the moving background. A local dark veil may be used only if the text otherwise drops below legible contrast.

## Product Placeholders

Every existing product mockup is obsolete and must be removed from the rendered page.

Each replacement placeholder must:

- Reserve the intended screenshot dimensions and responsive footprint.
- Use a neutral gray surface that separates clearly from the black canvas.
- Include a subtle charcoal border and restrained radius.
- Contain no fabricated controls, messages, metrics, or product claims.
- Carry a small neutral label such as `Product image coming soon` for internal review clarity.
- Be excluded from assistive-technology noise when it conveys no user-facing information, or receive accurate neutral alt text when represented as an image region.
- Use, at most, a restrained entrance transition; no fake typing, tab switching, scanning, or UI choreography.

The placeholder component should be reusable so approved screenshots can replace its interior later without rebuilding section layout.

## Existing Sections

The current below-the-fold content remains in its current order. Its presentation changes as follows:

- Section backgrounds collapse into one continuous near-black canvas, using spacing and rules rather than alternating fills.
- Headings use warm white; supporting copy uses stone gray.
- Existing comparison and feature cards become flat groupings separated by thin rules.
- Emoji icons are removed or replaced with a single consistent monochrome icon treatment already available in the project.
- Existing app demonstrations are replaced with the reusable placeholders.
- The final CTA uses one warm-white primary action and one quiet text or outline action.
- The footer remains structurally intact but adopts the black marketing surface and neutral hierarchy.

## Motion and Reduced Motion

- Preserve the existing hero scroll calculation and product-rise behavior.
- Remove JavaScript and state used only by obsolete mockup animations.
- New placeholder entrances must be CSS-only and subtle, if used at all.
- `prefers-reduced-motion` must leave the hero copy and placeholder visible without required scrolling or animation.
- The background video remains muted and inline. Reduced-motion users receive a stable presentation without parallax transforms; pausing the decorative video is preferred if it can be implemented without adding fragile client state.

## Responsive Behavior

- Desktop keeps the hero copy in the left-side negative space and the window visible on the right.
- Mobile prioritizes readable copy and CTAs; the video may crop more tightly but must retain enough upper-room architecture to remain recognizable.
- Product placeholders become edge-conscious, nearly full-width frames without horizontal overflow.
- Existing breakpoint structure is retained unless visual verification demonstrates a specific failure.

## Accessibility and Performance

- Warm-white buttons must meet at least 4.5:1 text contrast.
- Muted text must meet WCAG AA at its actual size.
- Focus states remain visible against both black and warm-white controls.
- The decorative hero video stays muted, autoplaying, looping, inline, and hidden from accessibility APIs.
- No additional video or large imagery is introduced in this pass.
- Placeholder markup must be lighter than the obsolete animated mockup implementations it replaces.

## Verification

Implementation is accepted when:

1. The `/home` landing page uses the scoped black, warm-white, and stone-gray system without changing global application tokens.
2. No gold marketing accents remain on `/home`.
3. No obsolete or fabricated application mockup renders on `/home`.
4. All reserved product-image locations use the reusable neutral placeholder treatment.
5. The upper-room video and scroll-driven product reveal still work.
6. Existing CTA behavior still works and the Sources action still links to `/sources`.
7. Focused unit tests, lint, and type checking pass.
8. Browser verification passes at representative desktop and mobile widths, including reduced motion and no horizontal overflow.

## Deferred Work

- Replacing placeholders with approved current application screenshots.
- Editing or re-encoding the upper-room video loop.
- Renaming all remaining Rhemata identity across the site and application.
- Applying the marketing palette to `/sources`, `/beliefs`, or authenticated product surfaces.
