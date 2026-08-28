import assert from "node:assert/strict";
import test from "node:test";

import {
  LOADING_PHRASES,
  estimateLoadingProgress,
  loadingPhraseIndex,
} from "./loading-progress.ts";

test("estimate starts above zero and stays below the hard cap", () => {
  const start = estimateLoadingProgress(0);
  assert.ok(start > 0, "must start above zero");
  assert.equal(start, 0.06);

  for (const elapsed of [0, 1000, 5000, 30000, 120000, 10_000_000]) {
    const progress = estimateLoadingProgress(elapsed);
    assert.ok(
      progress < 0.95,
      `progress ${progress} at ${elapsed}ms must stay below 0.95`,
    );
  }
});

test("estimate never decreases as elapsed time increases", () => {
  const samples = [0, 500, 1000, 2000, 5000, 10000, 20000, 40000, 80000, 200000];
  let previous = -Infinity;
  for (const elapsed of samples) {
    const progress = estimateLoadingProgress(elapsed);
    assert.ok(
      progress >= previous,
      `progress must not decrease: ${progress} < ${previous} at ${elapsed}ms`,
    );
    previous = progress;
  }
});

test("estimate approaches the cap more slowly over time", () => {
  const earlyDelta = estimateLoadingProgress(2000) - estimateLoadingProgress(1000);
  const lateDelta = estimateLoadingProgress(41000) - estimateLoadingProgress(40000);
  assert.ok(
    lateDelta < earlyDelta,
    `growth should slow down: early=${earlyDelta} late=${lateDelta}`,
  );
});

test("estimate treats negative elapsed time as zero", () => {
  assert.equal(estimateLoadingProgress(-500), estimateLoadingProgress(0));
});

test("phrase index starts at zero and stays within range", () => {
  assert.equal(loadingPhraseIndex(0.06), 0);
  for (const elapsed of [0, 1000, 10000, 60000, 500000]) {
    const index = loadingPhraseIndex(estimateLoadingProgress(elapsed));
    assert.ok(index >= 0 && index <= LOADING_PHRASES.length - 1);
  }
});

test("phrase index advances in order and never regresses for monotonic progress", () => {
  const elapsedSamples = Array.from({ length: 50 }, (_, i) => i * 3000);
  let previousIndex = -1;
  for (const elapsed of elapsedSamples) {
    const index = loadingPhraseIndex(estimateLoadingProgress(elapsed));
    assert.ok(
      index >= previousIndex,
      `phrase index regressed: ${index} < ${previousIndex}`,
    );
    previousIndex = index;
  }
});

test("phrase index clamps at the final phrase rather than looping back", () => {
  const veryLate = loadingPhraseIndex(estimateLoadingProgress(10_000_000));
  assert.equal(veryLate, LOADING_PHRASES.length - 1);
  assert.equal(loadingPhraseIndex(0.94), LOADING_PHRASES.length - 1);
  assert.equal(loadingPhraseIndex(1), LOADING_PHRASES.length - 1);
});

test("the five approved phrases appear in this exact order", () => {
  assert.deepEqual(LOADING_PHRASES, [
    "Searching the corpus…",
    "Reading relevant sources…",
    "Building from the evidence…",
    "Checking names and attributions…",
    "Verifying source references…",
  ]);
});
