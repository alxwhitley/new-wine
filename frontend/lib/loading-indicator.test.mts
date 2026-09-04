import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/newwine/loading-indicator.tsx", import.meta.url),
  "utf8",
);

test("renders only the active phase in one compact row", () => {
  assert.match(source, /activeStepIndex\(/);
  assert.match(source, /\{LOADING_STEPS\[active\]\}/);
  assert.doesNotMatch(source, /LOADING_STEPS\.map\(/);
  assert.doesNotMatch(source, /<ol|<li/);
});

test("the active step carries motion that a reduced-motion preference disables", () => {
  assert.match(source, /animate-spin/);
  assert.match(source, /motion-reduce:animate-none/);
});

test("completed and upcoming phases are not rendered", () => {
  assert.doesNotMatch(source, /\bCheck\b/);
  assert.doesNotMatch(source, /opacity-60/);
  assert.doesNotMatch(source, /done|isActive/);
});

test("the visible active phase is announced as one atomic status", () => {
  assert.match(source, /role="status"/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /aria-atomic/);
  assert.doesNotMatch(source, /sr-only/);
});

test("the circular ring and its progress machinery are gone", () => {
  assert.doesNotMatch(source, /strokeDasharray|strokeDashoffset|CIRCUMFERENCE/);
  assert.doesNotMatch(source, /estimateLoadingProgress|loadingPhraseIndex|LOADING_PHRASES/);
});

test("renders no percentage, meter, or fabricated source count", () => {
  assert.doesNotMatch(source, /%/);
  assert.doesNotMatch(source, /toFixed|Math\.round/);
  assert.doesNotMatch(source, /<svg/);
});
