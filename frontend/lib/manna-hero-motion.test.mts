import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
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
    foregroundOpacity: 0,
    foregroundScale: 1,
    foregroundY: 12,
  });

  assert.deepEqual(getMannaHeroTransforms(0.5), {
    backgroundScale: 1.04,
    backgroundY: -1.5,
    copyOpacity: 0.5,
    copyY: -12,
    productScale: 0.91,
    productY: 17,
    foregroundOpacity: 0.78,
    foregroundScale: 1.04,
    foregroundY: 4,
  });

  assert.deepEqual(getMannaHeroTransforms(1), {
    backgroundScale: 1.08,
    backgroundY: -3,
    copyOpacity: 0,
    copyY: -24,
    productScale: 1,
    productY: 0,
    foregroundOpacity: 0.78,
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
    foregroundOpacity: 0.78,
    foregroundScale: 1,
    foregroundY: 0,
  });
});

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

test("hero uses the versioned predawn master asset", () => {
  const source = readFileSync(
    new URL("../components/marketing/manna-dawn-hero.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /manna-predawn-minimal-v2\.png/);
  assert.match(source, /unoptimized/);
});

test("home page clips horizontal overflow without breaking sticky descendants", () => {
  const source = readFileSync(
    new URL("../app/home/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /overflow-x-clip/);
  assert.doesNotMatch(source, /overflow-x-hidden/);
});
