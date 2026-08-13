# UpperWord Black Marketing Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `/home` as the approved near-black UpperWord marketing surface while preserving its copy, section order, authentication behavior, upper-room video, and scroll-driven hero reveal.

**Architecture:** Keep the palette local to `/home` through a page CSS module and hero CSS module. Replace the two obsolete animated application mockups and the hero preview shell with one reusable, decorative `ProductImagePlaceholder` component whose aspect ratio is selected by each placement. Keep client state only for the existing authentication flow and hero scroll calculation.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, CSS Modules, Node test runner

**Spec:** `docs/superpowers/specs/2026-08-13-upperword-black-marketing-surface-design.md`

## Global Constraints

- Preserve the current landing-page section order and marketing copy below the hero.
- Preserve existing authentication, CTA, responsive, semantic heading, keyboard, and WCAG AA behavior.
- Do not change authenticated application tokens, backend/data/auth contracts, `/sources`, `/beliefs`, positioning claims, or doctrinal content.
- Use only locally scoped near-black, warm-white, stone-gray, and charcoal marketing colors; leave the upper-room video as the only warm chromatic element.
- Render no obsolete mockups, fabricated controls, messages, metrics, product claims, emoji feature icons, gold accents, colored gradients, or mockup choreography.
- Reduced motion must keep the hero copy and product placeholder visible, disable parallax transforms, and pause the decorative video when practical without fragile state.

---

### Task 1: Lock the marketing-surface contract with focused tests

**Files:**
- Modify: `frontend/lib/manna-hero-motion.test.mts`

**Interfaces:**
- Consumes: rendered-source contracts for `app/home/page.tsx`, `components/marketing/product-image-placeholder.tsx`, and `components/marketing/manna-dawn-hero.tsx`
- Produces: focused regression coverage for placeholder reuse, obsolete-mockup removal, local palette use, CTA links, hero video semantics, and reduced-motion behavior

- [ ] **Step 1: Add failing assertions for the approved surface**

Assert that `/home` imports and reuses `ProductImagePlaceholder`, contains no mockup component/state/emoji/gold-token implementation, retains its section headings and auth gate, and applies a local CSS-module root. Assert that the placeholder is decorative with the review label, and that the hero uses the placeholder while pausing the video under reduced motion.

- [ ] **Step 2: Run the focused test and confirm the new assertions fail**

Run: `npm test -- --test-name-pattern="marketing surface|placeholder|hero"`

Expected: FAIL because the reusable placeholder and page-local surface do not exist yet.

### Task 2: Build the reusable product-image placeholder and preserve hero motion

**Files:**
- Create: `frontend/components/marketing/product-image-placeholder.tsx`
- Create: `frontend/components/marketing/product-image-placeholder.module.css`
- Modify: `frontend/components/marketing/manna-dawn-hero.tsx`
- Modify: `frontend/components/marketing/manna-dawn-hero.module.css`
- Modify: `frontend/lib/manna-hero-motion.ts`

**Interfaces:**
- Produces: `ProductImagePlaceholder({ className?, ratio?, label? })`, where `ratio` is `"landscape" | "portrait" | "hero"` and the component renders an `aria-hidden` neutral frame with `Product image coming soon`
- Consumes: existing `getMannaHeroTransforms(progress, reducedMotion)` and the supplied `/videos/upper-room-hero.mp4`

- [ ] **Step 1: Add the lightweight placeholder component**

Implement a single decorative frame with a restrained label, charcoal rule, gray fill, and responsive aspect-ratio variants. Do not add controls, imagery, JavaScript animation, or assistive-technology noise.

- [ ] **Step 2: Integrate it into the hero**

Replace the hero preview `div` with `ProductImagePlaceholder`, remove dormant foreground transform fields, restyle the eyebrow and actions with hero-local neutral classes, add a legibility veil, and keep the existing scroll progress for background/copy/product rise.

- [ ] **Step 3: Make reduced motion stable**

When the media query matches, pause the decorative video and keep the copy and placeholder visible without parallax. Resume autoplay only when reduced motion is no longer requested.

- [ ] **Step 4: Run focused hero tests**

Run: `npm test -- --test-name-pattern="placeholder|hero|reduced motion"`

Expected: PASS.

### Task 3: Replace obsolete mockups and apply the scoped black surface

**Files:**
- Create: `frontend/app/home/home.module.css`
- Modify: `frontend/app/home/page.tsx`

**Interfaces:**
- Consumes: `ProductImagePlaceholder` and existing `MannaDawnHero({ onPrimaryAction })`
- Produces: the unchanged `/home` content order and auth interactions on a locally scoped black marketing canvas

- [ ] **Step 1: Remove obsolete mockup implementation code**

Delete inline mock color tokens, `MockSidebar`, `ChatMockup`, `StudyMockup`, their timers/observers/state, and emoji feature metadata. Replace both demonstration placements with the reusable placeholder at the existing responsive footprint.

- [ ] **Step 2: Add the page-local visual system**

Define local custom properties for canvas `#090909`, warm white `#f2efe8`, secondary stone `#aaa7a0`, charcoal rules `#2a2927`, and neutral product surfaces. Apply them through the page CSS module only; use flat groups and rules, neutral CTA treatments, visible focus states, and no gold or colored gradients.

- [ ] **Step 3: Preserve content and behavior**

Keep the current below-hero copy and section order, `openAuthGate`, `BetaGate`, `LoginModal`, conditional Study link, Sources navigation, headings, footer structure, and horizontal clipping. Update only identity labels already established by the approved hero work where required for surface consistency.

- [ ] **Step 4: Run focused marketing tests**

Run: `npm test -- --test-name-pattern="marketing surface|placeholder|home page"`

Expected: PASS.

### Task 4: Verify the completed surface

**Files:**
- Verify only; make narrowly scoped corrections in the files above if evidence finds a defect.

**Interfaces:**
- Consumes: completed `/home` implementation
- Produces: acceptance evidence for code quality, desktop/mobile rendering, reduced motion, overflow, focus, and CTA behavior

- [ ] **Step 1: Run static verification**

Run: `npm test`, `npm run lint`, and `npx tsc --noEmit` from `frontend/`.

Expected: all exit 0.

- [ ] **Step 2: Start the local frontend and verify desktop**

Open `/home` at 1440×900. Confirm the near-black canvas, left-aligned legible hero, upper-room video, placeholder rise, continuous section surface, neutral rules/cards, no obsolete UI, no gold, correct Sources link, visible focus, and zero horizontal overflow.

- [ ] **Step 3: Verify mobile**

Open `/home` at 390×844. Confirm readable hero copy and stacked CTAs, recognizable video crop, nearly full-width placeholders, preserved section order, usable footer, and zero horizontal overflow.

- [ ] **Step 4: Verify reduced motion**

Emulate `prefers-reduced-motion: reduce`. Confirm the hero copy and placeholder are visible without scroll animation, the video is paused, marquee motion is disabled, and the page remains usable.

- [ ] **Step 5: Review the final diff without committing**

Run: `git status --short` and `git diff --check`.

Expected: only the approved plan, existing hero/video work, and landing-page implementation files are changed; no commit is created without Alex's approval.
