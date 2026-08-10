# Manna Dawn Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/home` typography-only hero with a layered dawn-wilderness hero whose neutral product placeholder rises through the landscape during native scrolling.

**Architecture:** Copy the approved dawn master into project-owned assets, derive a matching transparent foreground from that master, and render the two image planes around a real HTML placeholder. Keep scroll interpolation in a pure tested utility, let one focused client component write CSS custom properties through a root ref, and leave authentication behavior in the existing page.

**Tech Stack:** Next.js 16.2 App Router, React 19, TypeScript, Tailwind CSS 4, CSS Modules, `next/image`, Node's built-in test runner, existing shadcn `Button`.

## Global Constraints

- The approved source image is `/Users/alexwhitley/.codex/generated_images/019fec93-3f66-7850-83f9-914e53c142fa/exec-ba04d629-1600-4c1e-8775-a963ebfd5e6a.png`.
- The running application must never reference the Codex-generated-images directory.
- Preserve the current hero copy and current authentication actions; the broad Rhemata-to-Manna rename is out of scope.
- Use the current design-system tokens; add no hardcoded hexadecimal colors, new shadow system, font, or animation dependency.
- The placeholder is `16:10` on desktop and `4:5` on mobile, contains no fabricated controls, and must be replaceable without changing layout or motion code.
- The page must retain native scrolling: no wheel interception, scroll locking, generated video, particles, bounce, or camera shake.
- Reduced-motion users see a stable composition with all essential copy visible and no scroll-linked transforms.
- Do not touch answer generation, retrieval, authentication internals, database code, admin code, or downstream homepage sections.
- Preserve every unrelated change in the dirty worktree; stage only files owned by the current task.

---

## File Structure

- Create `frontend/public/images/hero/manna-dawn-master.png` — project-owned approved source and background image.
- Create `frontend/public/images/hero/manna-dawn-foreground.png` — transparent foreground derived from the approved source.
- Create `frontend/lib/manna-hero-motion.ts` — pure interpolation and clamping functions.
- Create `frontend/lib/manna-hero-motion.test.mts` — boundary, midpoint, clamping, and reduced-motion tests.
- Create `frontend/components/marketing/manna-dawn-hero.tsx` — semantic hero markup, scroll measurement, and auth-action handoff.
- Create `frontend/components/marketing/manna-dawn-hero.module.css` — sticky layout, responsive crops, layer transforms, and reduced-motion fallback.
- Modify `frontend/app/home/page.tsx` — replace only the current hero section with `MannaDawnHero`.

---

### Task 1: Prepare the project-owned landscape layers

**Files:**
- Create: `frontend/public/images/hero/manna-dawn-master.png`
- Create: `frontend/public/images/hero/manna-dawn-foreground.png`

**Interfaces:**
- Consumes: approved dawn source image at the absolute path in Global Constraints.
- Produces: `/images/hero/manna-dawn-master.png` and `/images/hero/manna-dawn-foreground.png`, both with intrinsic dimensions recorded by `next/image`; the foreground has an alpha channel and transparent upper/central regions.

- [ ] **Step 1: Copy the approved master into the project**

Run:

```bash
mkdir -p frontend/public/images/hero
cp /Users/alexwhitley/.codex/generated_images/019fec93-3f66-7850-83f9-914e53c142fa/exec-ba04d629-1600-4c1e-8775-a963ebfd5e6a.png frontend/public/images/hero/manna-dawn-master.png
```

Expected: `manna-dawn-master.png` is `1672 × 941`, visually identical to the approved dawn image, and is not a symlink.

- [ ] **Step 2: Generate the foreground extraction from the master**

Use the built-in image editing tool with `manna-dawn-master.png` as the edit target and this exact prompt:

```text
Use case: background-extraction
Asset type: transparent foreground plane for a layered website hero
Primary request: Isolate only the nearest rocky terrain, low thorny shrubs, and dry grasses from the supplied dawn wilderness image. Preserve their original pixels, position, lighting, scale, and 16:9 framing. Remove the sky, distant ridges, middle-distance wadi, and every background area.
Composition: retain the near terrain entering from the lower left, lower right, and bottom edge; preserve the broad open valley shape in the center so an app panel can appear behind it.
Output preparation: place the retained foreground on a perfectly flat solid #ff00ff chroma-key background for later removal. The key background must be uniform with no gradient, shadow, texture, reflection, or color spill.
Constraints: do not add, remove, relocate, relight, or redesign rocks or vegetation; do not invent new terrain; no text, interface, people, animals, buildings, symbols, or watermark; do not use #ff00ff in the retained landscape.
```

Copy the tool's reported output into
`frontend/public/images/hero/manna-dawn-foreground-source.png`, then run the
installed chroma-removal helper:

```bash
python "${CODEX_HOME:-$HOME/.codex}/skills/.system/imagegen/scripts/remove_chroma_key.py" \
  --input frontend/public/images/hero/manna-dawn-foreground-source.png \
  --out frontend/public/images/hero/manna-dawn-foreground.png \
  --auto-key border \
  --soft-matte \
  --transparent-threshold 12 \
  --opaque-threshold 220 \
  --despill
```

Do not switch to a different image model or native-transparency CLI without Alex's approval. Keep the intermediate source until the alpha result is visually approved; then leave it untracked rather than deleting it unless Alex explicitly authorizes deletion.

- [ ] **Step 3: Verify dimensions and transparency**

Run:

```bash
cd frontend
node -e 'const sharp=require("sharp"); Promise.all(["public/images/hero/manna-dawn-master.png","public/images/hero/manna-dawn-foreground.png"].map(async p=>({p,m:await sharp(p).metadata(),s:await sharp(p).stats()}))).then(rows=>{for(const {p,m,s} of rows) console.log(p,m.width,m.height,m.hasAlpha,s.isOpaque)})'
```

Expected:

```text
public/images/hero/manna-dawn-master.png 1672 941 false true
public/images/hero/manna-dawn-foreground.png 1672 941 true false
```

The important foreground requirements are `hasAlpha === true`,
`isOpaque === false`, transparent top corners, and retained terrain across the
bottom.

- [ ] **Step 4: Inspect the foreground over a checkerboard and the master**

Use the local image viewer on both files. Reject and regenerate the foreground if it has magenta fringe, floating vegetation, changed geology, a rectangular top edge, or insufficient open space at the center. If the only defect is a thin magenta fringe, rerun the helper once with `--edge-contract 1`.

- [ ] **Step 5: Commit the approved assets**

```bash
git add frontend/public/images/hero/manna-dawn-master.png frontend/public/images/hero/manna-dawn-foreground.png
git commit -m "feat: add layered Manna dawn hero assets"
```

---

### Task 2: Build and test deterministic hero motion math

**Files:**
- Create: `frontend/lib/manna-hero-motion.ts`
- Create: `frontend/lib/manna-hero-motion.test.mts`

**Interfaces:**
- Consumes: normalized scroll progress as a number and a reduced-motion boolean.
- Produces: `clampHeroProgress(value: number): number` and `getMannaHeroTransforms(progress: number, reducedMotion?: boolean): MannaHeroTransforms`.

- [ ] **Step 1: Write failing boundary and midpoint tests**

Create `frontend/lib/manna-hero-motion.test.mts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import {
  clampHeroProgress,
  getMannaHeroTransforms,
} from "./manna-hero-motion.ts";

test("clamps hero progress to the inclusive zero-to-one range", () => {
  assert.equal(clampHeroProgress(-0.4), 0);
  assert.equal(clampHeroProgress(0.35), 0.35);
  assert.equal(clampHeroProgress(1.4), 1);
});

test("returns the approved start, midpoint, and end transforms", () => {
  assert.deepEqual(getMannaHeroTransforms(0), {
    backgroundScale: 1,
    backgroundY: 0,
    copyOpacity: 1,
    copyY: 0,
    productScale: 0.82,
    productY: 34,
    foregroundScale: 1,
    foregroundY: 0,
  });

  assert.deepEqual(getMannaHeroTransforms(0.5), {
    backgroundScale: 1.04,
    backgroundY: -1.5,
    copyOpacity: 0.5,
    copyY: -12,
    productScale: 0.91,
    productY: 17,
    foregroundScale: 1.04,
    foregroundY: -2,
  });

  assert.deepEqual(getMannaHeroTransforms(1), {
    backgroundScale: 1.08,
    backgroundY: -3,
    copyOpacity: 0,
    copyY: -24,
    productScale: 1,
    productY: 0,
    foregroundScale: 1.08,
    foregroundY: -4,
  });
});

test("reduced motion keeps copy visible and disables transforms", () => {
  assert.deepEqual(getMannaHeroTransforms(0.75, true), {
    backgroundScale: 1,
    backgroundY: 0,
    copyOpacity: 1,
    copyY: 0,
    productScale: 1,
    productY: 0,
    foregroundScale: 1,
    foregroundY: 0,
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd frontend
node --experimental-strip-types --test lib/manna-hero-motion.test.mts
```

Expected: FAIL because `manna-hero-motion.ts` does not exist.

- [ ] **Step 3: Implement the pure interpolation utility**

Create `frontend/lib/manna-hero-motion.ts`:

```ts
export type MannaHeroTransforms = {
  backgroundScale: number;
  backgroundY: number;
  copyOpacity: number;
  copyY: number;
  productScale: number;
  productY: number;
  foregroundScale: number;
  foregroundY: number;
};

const STATIC_TRANSFORMS: MannaHeroTransforms = {
  backgroundScale: 1,
  backgroundY: 0,
  copyOpacity: 1,
  copyY: 0,
  productScale: 1,
  productY: 0,
  foregroundScale: 1,
  foregroundY: 0,
};

export function clampHeroProgress(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function lerp(start: number, end: number, progress: number): number {
  return Number((start + (end - start) * progress).toFixed(4));
}

export function getMannaHeroTransforms(
  progress: number,
  reducedMotion = false,
): MannaHeroTransforms {
  if (reducedMotion) return STATIC_TRANSFORMS;

  const value = clampHeroProgress(progress);

  return {
    backgroundScale: lerp(1, 1.08, value),
    backgroundY: lerp(0, -3, value),
    copyOpacity: lerp(1, 0, value),
    copyY: lerp(0, -24, value),
    productScale: lerp(0.82, 1, value),
    productY: lerp(34, 0, value),
    foregroundScale: lerp(1, 1.08, value),
    foregroundY: lerp(0, -4, value),
  };
}
```

- [ ] **Step 4: Run the focused and full unit suites**

Run:

```bash
cd frontend
node --experimental-strip-types --test lib/manna-hero-motion.test.mts
npm test
```

Expected: the focused file passes all three tests and the full `lib/*.test.mts` suite passes.

- [ ] **Step 5: Commit the tested motion utility**

```bash
git add frontend/lib/manna-hero-motion.ts frontend/lib/manna-hero-motion.test.mts
git commit -m "feat: add tested Manna hero motion model"
```

---

### Task 3: Implement the isolated layered hero component

**Files:**
- Create: `frontend/components/marketing/manna-dawn-hero.tsx`
- Create: `frontend/components/marketing/manna-dawn-hero.module.css`

**Interfaces:**
- Consumes: `onPrimaryAction: () => void`; existing route `/` for the secondary action; `getMannaHeroTransforms(progress, reducedMotion)` from Task 2.
- Produces: `MannaDawnHero({ onPrimaryAction }: MannaDawnHeroProps): React.JSX.Element` with no ownership of authentication state.

- [ ] **Step 1: Add a failing source-contract test**

Add `readFileSync` to the import block at the top of
`frontend/lib/manna-hero-motion.test.mts`:

```ts
import { readFileSync } from "node:fs";
```

Then append this test so the existing test runner can verify the component
boundary without adding a DOM-test dependency:

```ts
test("hero component keeps copy semantic and has no fabricated app controls", () => {
  const source = readFileSync(
    new URL("../components/marketing/manna-dawn-hero.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /<h1/);
  assert.match(source, /aria-label="Manna application preview placeholder"/);
  assert.doesNotMatch(source, /Welcome back|Ask anything|Research|Support Ops/);
  assert.doesNotMatch(source, /style=\{\{/);
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd frontend
node --experimental-strip-types --test lib/manna-hero-motion.test.mts
```

Expected: FAIL with `ENOENT` for `manna-dawn-hero.tsx`.

- [ ] **Step 3: Create the interactive client component**

Create `frontend/components/marketing/manna-dawn-hero.tsx` with this structure and behavior:

```tsx
"use client";

import { useEffect, useRef } from "react";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { getMannaHeroTransforms } from "@/lib/manna-hero-motion";

import styles from "./manna-dawn-hero.module.css";

type MannaDawnHeroProps = {
  onPrimaryAction: () => void;
};

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function writeMotionVariables(root: HTMLElement, reducedMotion: boolean): void {
  const range = Math.max(1, root.offsetHeight - window.innerHeight);
  const progress = -root.getBoundingClientRect().top / range;
  const values = getMannaHeroTransforms(progress, reducedMotion);

  root.style.setProperty("--manna-background-scale", String(values.backgroundScale));
  root.style.setProperty("--manna-background-y", `${values.backgroundY}%`);
  root.style.setProperty("--manna-copy-opacity", String(values.copyOpacity));
  root.style.setProperty("--manna-copy-y", `${values.copyY}px`);
  root.style.setProperty("--manna-product-scale", String(values.productScale));
  root.style.setProperty("--manna-product-y", `${values.productY}vh`);
  root.style.setProperty("--manna-foreground-scale", String(values.foregroundScale));
  root.style.setProperty("--manna-foreground-y", `${values.foregroundY}%`);
}

export function MannaDawnHero({ onPrimaryAction }: MannaDawnHeroProps) {
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const motion = window.matchMedia(MOTION_QUERY);
    let frame = 0;

    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => writeMotionVariables(root, motion.matches));
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    motion.addEventListener("change", update);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      motion.removeEventListener("change", update);
    };
  }, []);

  return (
    <section ref={rootRef} className={styles.root} aria-labelledby="manna-hero-title">
      <div className={styles.stickyFrame}>
        <Image
          className={styles.background}
          src="/images/hero/manna-dawn-master.png"
          alt=""
          fill
          priority
          sizes="100vw"
        />

        <div className={styles.copy}>
          <div className={styles.eyebrow}><span />Now in beta</div>
          <h1 id="manna-hero-title">Faithful answers from sources you can trust.</h1>
          <p>Rhemata is an AI-assisted Bible study tool that answers from trusted sources rooted in the charismatic tradition — now in early beta, and looking for testers.</p>
          <div className={styles.actions}>
            <Button size="lg" onClick={onPrimaryAction}>Become a test user</Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="/">Try it free — no account needed</Link>
            </Button>
          </div>
        </div>

        <div
          className={styles.productPlaceholder}
          role="img"
          aria-label="Manna application preview placeholder"
        />

        <Image
          className={styles.foreground}
          src="/images/hero/manna-dawn-foreground.png"
          alt=""
          fill
          sizes="100vw"
        />
      </div>
    </section>
  );
}
```

If lint requires the decorative placeholder to avoid `role="img"`, retain the
exact accessible label by moving it to a visually hidden `<span>` inside the
placeholder rather than removing the label.

- [ ] **Step 4: Add the complete scoped layout and motion styles**

Create `frontend/components/marketing/manna-dawn-hero.module.css` with these required rules:

```css
.root {
  --manna-background-scale: 1;
  --manna-background-y: 0%;
  --manna-copy-opacity: 1;
  --manna-copy-y: 0px;
  --manna-product-scale: 0.82;
  --manna-product-y: 34vh;
  --manna-foreground-scale: 1;
  --manna-foreground-y: 0%;
  position: relative;
  height: 190vh;
  min-height: 72rem;
  background: hsl(var(--background));
}

.stickyFrame {
  position: sticky;
  top: 0;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  isolation: isolate;
}

.background,
.foreground {
  object-fit: cover;
  object-position: 50% 50%;
  pointer-events: none;
  user-select: none;
  will-change: transform;
}

.background {
  z-index: 0;
  transform: translate3d(0, var(--manna-background-y), 0)
    scale(var(--manna-background-scale));
}

.copy {
  position: relative;
  z-index: 2;
  width: min(100% - 3rem, 53.75rem);
  margin-inline: auto;
  padding-top: clamp(7.75rem, 14vh, 10rem);
  text-align: center;
  opacity: var(--manna-copy-opacity);
  transform: translate3d(0, var(--manna-copy-y), 0);
  will-change: opacity, transform;
}

.copy h1 {
  max-width: 16ch;
  margin: 0 auto 1.25rem;
  color: hsl(var(--card-foreground));
  font-family: var(--font-serif);
  font-size: clamp(2.4rem, 5.5vw, 4.2rem);
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.12;
  text-wrap: balance;
}

.copy p {
  max-width: 36.25rem;
  margin: 0 auto 2rem;
  color: hsl(var(--card-foreground));
  font-size: 1.125rem;
  line-height: 1.75;
  text-wrap: balance;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 1.5rem;
  padding: 0.25rem 0.875rem;
  border: 1px solid hsl(var(--border));
  border-radius: 9999px;
  color: hsl(var(--card-foreground));
  background: hsl(var(--background) / 0.35);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  backdrop-filter: blur(10px);
}

.eyebrow span {
  width: 0.3125rem;
  height: 0.3125rem;
  border-radius: 9999px;
  background: hsl(var(--primary));
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
}

.productPlaceholder {
  position: absolute;
  z-index: 1;
  left: 50%;
  bottom: -5vh;
  width: min(74rem, calc(100% - 4rem));
  aspect-ratio: 16 / 10;
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius-xl);
  background: hsl(var(--sidebar));
  box-shadow: 0 1px 3px hsl(0 0% 0% / 0.1);
  transform: translate3d(-50%, var(--manna-product-y), 0)
    scale(var(--manna-product-scale));
  transform-origin: 50% 100%;
  will-change: transform;
}

.foreground {
  z-index: 3;
  object-position: 50% 50%;
  transform: translate3d(0, var(--manna-foreground-y), 0)
    scale(var(--manna-foreground-scale));
  transform-origin: 50% 100%;
}

@media (max-width: 767px) {
  .root {
    height: 155vh;
    min-height: 58rem;
  }

  .background,
  .foreground {
    object-position: 50% 50%;
  }

  .copy {
    width: min(100% - 2rem, 34rem);
    padding-top: calc(6.5rem + env(safe-area-inset-top));
  }

  .copy h1 {
    font-size: clamp(2.25rem, 11vw, 3.25rem);
  }

  .copy p {
    font-size: 1rem;
    line-height: 1.6;
  }

  .actions {
    gap: 0.5rem;
  }

  .productPlaceholder {
    bottom: -2vh;
    width: calc(100% - 2rem);
    aspect-ratio: 4 / 5;
  }
}

@media (prefers-reduced-motion: reduce) {
  .root {
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
  }

  .stickyFrame {
    position: relative;
  }

  .background,
  .copy,
  .productPlaceholder,
  .foreground {
    will-change: auto;
  }

  .copy {
    opacity: 1;
    transform: none;
  }
}
```

During browser tuning, change numeric composition values only inside this CSS
module or the tested endpoint constants in Task 2; do not add page-level style
props or global selectors.

- [ ] **Step 5: Run the focused test, lint, and type check**

Run:

```bash
cd frontend
node --experimental-strip-types --test lib/manna-hero-motion.test.mts
npm run lint -- components/marketing/manna-dawn-hero.tsx lib/manna-hero-motion.ts lib/manna-hero-motion.test.mts
npx tsc --noEmit
```

Expected: all commands pass with no warnings or errors.

- [ ] **Step 6: Commit the isolated component**

```bash
git add frontend/components/marketing/manna-dawn-hero.tsx frontend/components/marketing/manna-dawn-hero.module.css frontend/lib/manna-hero-motion.test.mts
git commit -m "feat: build layered Manna dawn hero"
```

---

### Task 4: Integrate the hero without changing downstream content

**Files:**
- Modify: `frontend/app/home/page.tsx:1-8`
- Modify: `frontend/app/home/page.tsx:341-406`

**Interfaces:**
- Consumes: `MannaDawnHero({ onPrimaryAction })` from Task 3 and the page's existing `openAuthGate()` callback.
- Produces: `/home` with the fixed navigation, new hero, existing marquee, and every later section preserved in its current order.

- [ ] **Step 1: Add the hero import**

Add beside the existing marketing imports:

```tsx
import { MannaDawnHero } from "@/components/marketing/manna-dawn-hero";
```

- [ ] **Step 2: Replace only the existing hero section**

Replace the block beginning at `{/* ── HERO ── */}` and ending immediately
before `{/* ── MARQUEE ── */}` with:

```tsx
      {/* ── HERO ── */}
      <MannaDawnHero onPrimaryAction={openAuthGate} />

      {/* ── MARQUEE ── */}
```

Do not move the navigation into the component, rename Rhemata elsewhere, edit
`Marquee`, or change any downstream section.

- [ ] **Step 3: Run the complete frontend verification suite**

Run:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

Expected: all unit tests pass, ESLint and TypeScript report no errors, and Next.js produces a successful production build.

- [ ] **Step 4: Inspect the scoped diff**

Run:

```bash
git diff -- frontend/app/home/page.tsx frontend/components/marketing/manna-dawn-hero.tsx frontend/components/marketing/manna-dawn-hero.module.css frontend/lib/manna-hero-motion.ts frontend/lib/manna-hero-motion.test.mts frontend/public/images/hero/
```

Expected: only the old hero is replaced; navigation, marquee, authentication
modals, and all later sections remain unchanged.

- [ ] **Step 5: Commit the page integration**

```bash
git add frontend/app/home/page.tsx
git commit -m "feat: integrate Manna dawn hero on home page"
```

---

### Task 5: Verify and tune the experience in a real browser

**Files:**
- Modify if evidence requires tuning: `frontend/components/marketing/manna-dawn-hero.module.css`
- Modify if endpoint values change: `frontend/lib/manna-hero-motion.ts`
- Modify when endpoint values change: `frontend/lib/manna-hero-motion.test.mts`

**Interfaces:**
- Consumes: completed `/home` implementation from Task 4.
- Produces: evidence that desktop, mobile, reduced-motion, keyboard, and section-transition behavior meet the approved design.

- [ ] **Step 1: Start the existing development server**

Run:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 4321
```

Expected: Next.js reports the local URL without build errors.

- [ ] **Step 2: Verify the desktop start, midpoint, and end states**

Using the browser-testing skill, open `http://127.0.0.1:4321/home` at
`1440 × 900`. Capture and inspect:

- Scroll start: navigation and all hero copy are readable; placeholder is only
  partly visible; dawn image has no loading shift.
- Midpoint: copy is fading upward; background push is subtle; placeholder rises
  through the open wadi; foreground overlaps it without covering its center.
- End: placeholder is dominant; motion has settled; marquee enters without a
  blank gap or clipped foreground.

Reject the implementation if the foreground appears as a pasted cutout, the
background visibly separates from it, or the placeholder resembles a laptop.

- [ ] **Step 3: Verify narrow mobile behavior**

At `390 × 844`, repeat the start and end checks. Confirm:

- no horizontal overflow;
- headline remains above the placeholder;
- CTAs remain tappable and are not obscured by foreground terrain;
- central wadi and horizon remain coherent under the mobile crop;
- the `4:5` placeholder stays within one-rem side margins;
- the fixed navigation does not collide with the safe area.

- [ ] **Step 4: Verify reduced motion and keyboard access**

Enable the browser's reduced-motion emulation and reload `/home`. Confirm the
copy stays visible, every layer is static, native scrolling works, and there is
no opacity-dependent loss of content. Then use keyboard-only navigation to
reach the navigation links and both hero actions with visible focus rings.

- [ ] **Step 5: Tune only from observed evidence**

If a check fails, adjust only the owning values:

- image crop or overlap → CSS module `object-position`, placeholder size, or
  foreground positioning;
- scroll endpoint → `getMannaHeroTransforms()` plus its exact test expectation;
- scroll distance → CSS module `.root` height;
- mobile collision → mobile rules in the CSS module.

After every adjustment run:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
```

- [ ] **Step 6: Run final verification and commit tuning separately**

Run:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

If browser evidence required changes, commit them separately:

```bash
git add frontend/components/marketing/manna-dawn-hero.module.css frontend/lib/manna-hero-motion.ts frontend/lib/manna-hero-motion.test.mts
git commit -m "fix: tune Manna hero motion across viewports"
```

If no tuning was required, do not create a cosmetic commit.

---

## Completion Criteria

- The approved dawn image and matching foreground are project-owned assets.
- `/home` presents the layered sticky reveal with the current copy and auth behavior.
- The placeholder can later be replaced by an app screenshot without changing layout or motion logic.
- Desktop, mobile, reduced-motion, keyboard, and next-section transitions have browser evidence.
- Unit tests, lint, TypeScript, and production build all pass.
- No unrelated files, broader rebrand work, or protected product paths changed.
