import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  clampHeroProgress,
  getNewWineHeroTransforms,
} from "./newwine-hero-motion.ts";

test("clamps hero progress to the inclusive zero-to-one range", () => {
  assert.equal(clampHeroProgress(-0.4), 0);
  assert.equal(clampHeroProgress(0.35), 0.35);
  assert.equal(clampHeroProgress(1.4), 1);
});

test("returns the approved start, midpoint, and end transforms", () => {
  assert.deepEqual(getNewWineHeroTransforms(0), {
    backgroundScale: 1,
    backgroundY: 0,
    copyOpacity: 1,
    copyY: 0,
    productScale: 0.82,
    productY: 34,
  });

  assert.deepEqual(getNewWineHeroTransforms(0.5), {
    backgroundScale: 1.04,
    backgroundY: -1.5,
    copyOpacity: 0.5,
    copyY: -12,
    productScale: 0.91,
    productY: 17,
  });

  assert.deepEqual(getNewWineHeroTransforms(1), {
    backgroundScale: 1.08,
    backgroundY: -3,
    copyOpacity: 0,
    copyY: -24,
    productScale: 1,
    productY: 0,
  });
});

test("reduced motion keeps copy visible and disables transforms", () => {
  assert.deepEqual(getNewWineHeroTransforms(0.75, true), {
    backgroundScale: 1,
    backgroundY: 0,
    copyOpacity: 1,
    copyY: 0,
    productScale: 1,
    productY: 0,
  });
});

test("hero component keeps copy semantic and has no fabricated app controls", () => {
  const source = readFileSync(
    new URL("../components/marketing/newwine-dawn-hero.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /<h1/);
  assert.match(source, /Spirit-filled Bible study/);
  assert.match(source, /Go deeper with voices you can trust\./);
  assert.match(source, /New Wine brings Scripture and trusted Spirit-filled teachers/);
  assert.match(source, />Try New Wine</);
  assert.match(source, /href="\/sources"/);
  assert.match(source, />Explore the sources</);
  assert.match(source, /ProductImagePlaceholder/);
  assert.doesNotMatch(source, /Welcome back|Ask anything|Research|Support Ops/);
  assert.doesNotMatch(source, /style=\{\{/);
});

test("hero uses the supplied upper-room video without the old landscape foreground", () => {
  const source = readFileSync(
    new URL("../components/marketing/newwine-dawn-hero.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /upper-room-hero\.mp4/);
  assert.match(source, /autoPlay/);
  assert.match(source, /muted/);
  assert.match(source, /loop/);
  assert.match(source, /playsInline/);
  assert.doesNotMatch(source, /manna-dawn-foreground\.png/);
});

test("home page clips horizontal overflow without breaking sticky descendants", () => {
  const source = readFileSync(
    new URL("../app/home/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /overflow-x-clip/);
  assert.doesNotMatch(source, /overflow-x-hidden/);
});

test("marketing surface reuses neutral placeholders and removes obsolete mockups", () => {
  const page = readFileSync(
    new URL("../app/home/page.tsx", import.meta.url),
    "utf8",
  );
  const placeholder = readFileSync(
    new URL(
      "../components/marketing/product-image-placeholder.tsx",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(page, /home\.module\.css/);
  assert.match(page, /ProductImagePlaceholder/g);
  assert.match(page, /NewWineDawnHero/);
  assert.match(page, /useAuthGate/);
  assert.match(page, /LoginModal/);
  assert.match(page, /Why It Matters/);
  assert.match(page, /Ask Anything/);
  assert.match(page, /The Library Behind It/);
  assert.doesNotMatch(page, /MockSidebar|ChatMockup|StudyMockup|INTERLINEAR/);
  assert.doesNotMatch(page, /gold-light|text-gold|💬|📖|🔡|📌|🏛️|🎙️/u);

  assert.match(placeholder, /Product image coming soon/);
  assert.match(placeholder, /aria-hidden="true"/);
  assert.doesNotMatch(placeholder, /role="img"|aria-label/);
});

test("hero pauses its decorative video for reduced motion", () => {
  const source = readFileSync(
    new URL("../components/marketing/newwine-dawn-hero.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /videoRef/);
  assert.match(source, /motion\.matches/);
  assert.match(source, /\.pause\(\)/);
  assert.match(source, /\.play\(\)/);
  assert.match(source, /ProductImagePlaceholder/);
});
