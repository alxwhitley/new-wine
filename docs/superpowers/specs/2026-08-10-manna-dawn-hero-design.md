# Manna Dawn Hero Design

**Date:** 2026-08-10

**Status:** Approved design direction; awaiting written-spec review

**Surface:** Public marketing page hero at `/home`

## Objective

Replace the current typography-only Rhemata hero with the visual foundation for
Manna's new interface: a calm dawn wilderness, a product-image placeholder, and
a scroll-driven reveal. The experience should make Manna feel grounded,
contemplative, and connected to the real world rather than presenting it as an
abstract AI oracle.

This scope establishes the hero composition and motion only. The final app
screenshot, broader Manna rebrand, downstream homepage sections, and product UI
redesign are separate work.

## Approved Visual Direction

The setting is a photographically real Judean or Negev highland wilderness at
dawn. It uses rocky, gently undulating terrain, a shallow dry wadi, distant
limestone ridges, sparse scrub, and coarse dry grasses. It is not a Sahara sand
sea and does not depict a literal biblical scene.

The sky transitions from cool predawn blue into restrained apricot and muted
rose immediately above the horizon. The sun remains below the horizon and is
never visible. The scene contains no moon, overt religious symbolism, people,
animals, buildings, tents, ruins, roads, modern landmarks, or narrative props.

The approved master composition is:

`/Users/alexwhitley/.codex/generated_images/019fec93-3f66-7850-83f9-914e53c142fa/exec-ba04d629-1600-4c1e-8775-a963ebfd5e6a.png`

Before implementation, this preview asset must be copied into the repository
under a stable project-owned filename. The application must not reference the
Codex-generated-images directory.

## Layered Composition

The hero consists of three visual planes.

### 1. Background wilderness

The approved dawn image supplies the sky, distant ridges, middle-distance wadi,
and base terrain. It fills the hero and preserves the low-detail sky as the
headline field. It uses cover-style cropping with a deliberate focal position
that keeps the central wadi and horizon stable across supported desktop widths.

### 2. Product placeholder

A real HTML element sits above the background and below the foreground. During
this phase it is a neutral dark matte panel with a `16:10` desktop aspect ratio,
rounded corners, a restrained border, and no fabricated interface controls. On
mobile it shifts to a `4:5` viewport that a later responsive screenshot can
fill. It exists solely to establish scale, placement, clipping, and motion.

The placeholder must be replaceable later by changing its visual content,
without rewriting the hero's layout or scroll choreography.

### 3. Foreground wilderness

A foreground asset derived from the approved master image sits above the lower
and side edges of the placeholder. It contains the near rocky terrain, sparse
shrubs, and grasses with transparent sky and middle distance. Its open center
allows the placeholder to rise while its irregular edges make the interface
feel situated within the landscape.

The foreground must be derived from the same master composition rather than
generated independently, preserving geology, lighting, and perspective.

## Initial View

- The hero occupies at least one viewport and may extend beyond it to provide
  scroll distance for the reveal.
- Navigation remains legible over the dark upper sky.
- The Manna headline, supporting sentence, and primary and secondary actions
  occupy the quiet upper-center region.
- The product placeholder is centered and only partially visible near the
  bottom of the viewport.
- Foreground terrain overlaps the placeholder's lower and lateral edges.
- Copy must remain real HTML and must never be rendered into the landscape.

Final Manna headline and supporting copy are deliberately outside this design.
Implementation should preserve the current copy until a separate copy decision
is approved, except for any mechanically necessary product-name substitution
explicitly scoped at implementation time.

## Scroll Choreography

The hero reveal is controlled by scroll progress through a bounded sticky
sequence. Exact values may be tuned during browser testing, but the intended
motion relationships are fixed:

1. The background slowly scales from approximately `1.00` to `1.08` and shifts
   slightly upward, creating a restrained push into the wilderness.
2. The headline group fades and translates upward after the visitor begins the
   reveal. It remains readable before motion begins and does not disappear
   abruptly.
3. The product placeholder rises from below the fold, scales up, and becomes the
   dominant object in the frame.
4. The foreground terrain scales and translates slightly faster than the
   background, creating parallax without calling attention to the effect.
5. The sequence settles before the next homepage section enters. No element
   continues drifting after the reveal reaches its final state.

Motion should feel slow, physical, and quiet. It must not include springy
bounces, cinematic shake, particles, generated-video motion, or scroll hijacking.
The page remains natively scrollable.

## Responsive Behavior

Desktop and mobile use the same narrative but not necessarily identical crops.
The implementation must provide explicit focal positioning for narrow screens;
it must not rely on an accidental center crop. The distant ridge, central wadi,
headline contrast, and placeholder must remain coherent at supported widths.

On mobile:

- The headline remains above the placeholder rather than overlapping it.
- The placeholder uses the available width with safe side margins.
- Foreground overlap is reduced if necessary to avoid obscuring the future app
  screenshot.
- Scroll distance may be shorter than desktop while preserving the same start
  and end states.

## Accessibility and Performance

- With `prefers-reduced-motion: reduce`, the hero presents a stable final or
  near-final composition without scroll-linked transforms or fading essential
  content.
- All headline and action content remains semantic, keyboard accessible, and
  readable without the imagery.
- The dawn image receives responsive sizing and an efficient web format.
- The foreground asset must be optimized with transparency preserved.
- The hero must avoid layout shift by reserving the placeholder's final aspect
  ratio before assets load.
- The design must remain understandable if either image fails to load.

## Component Boundary

The hero should be isolated from the rest of the existing large home-page file
behind a focused component boundary. Its public inputs should be limited to the
content and actions that the page already owns. Scroll calculations and visual
layering belong inside the hero implementation; authentication behavior remains
owned by the page and existing auth components.

No answer-generation, retrieval, authentication, database, admin, or product-app
behavior is in scope.

## Verification

Implementation acceptance requires:

- Static visual checks at representative desktop and mobile widths.
- Browser verification of the initial, middle, and completed scroll states.
- Confirmation that the placeholder can be replaced without layout changes.
- A reduced-motion check.
- Keyboard and contrast checks for navigation, headline, and actions.
- Confirmation that the next section enters without clipping, blank space, or
  lingering transforms.
- Frontend lint and type checks appropriate to the existing Next.js project.

## Explicit Non-Goals

- Designing or generating the final Manna app screenshot.
- Adding video or an external motion-generation service.
- Rewriting the remainder of the homepage.
- Completing the full Rhemata-to-Manna code, domain, or copy migration.
- Changing product functionality or protected answer/retrieval paths.
