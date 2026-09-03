import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/newwine/loading-indicator.tsx", import.meta.url),
  "utf8",
);

test("renders a row per approved step instead of one rotating phrase", () => {
  assert.match(source, /LOADING_STEPS\.map\(/);
  assert.match(source, /activeStepIndex\(/);
});

test("the active step carries motion that a reduced-motion preference disables", () => {
  assert.match(source, /animate-spin/);
  assert.match(source, /motion-reduce:animate-none/);
});

test("completed steps read as done and upcoming steps stay subdued", () => {
  assert.match(source, /\bCheck\b/);
  assert.match(source, /opacity-60/);
});

test("only the active step is announced, and the visual list is hidden from assistive tech", () => {
  assert.match(source, /role="status"/);
  assert.match(source, /aria-hidden="true"/);
  assert.match(source, /sr-only/);
  assert.match(source, /aria-atomic/);
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
