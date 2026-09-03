import assert from "node:assert/strict";
import test from "node:test";

import {
  LOADING_STEPS,
  activeStepIndex,
} from "./loading-progress.ts";

/** The answer path's median wait. The final step must be reached by here. */
const MEDIAN_WAIT_MS = 20_000;

test("the five approved steps appear in this exact order", () => {
  assert.deepEqual(LOADING_STEPS, [
    "Searching the corpus",
    "Reading relevant sources",
    "Building from the evidence",
    "Checking names and attributions",
    "Verifying source references",
  ]);
});

test("the first step is active immediately on mount", () => {
  assert.equal(activeStepIndex(0), 0);
});

test("negative elapsed time is treated as zero", () => {
  assert.equal(activeStepIndex(-500), activeStepIndex(0));
});

test("the active step never regresses as elapsed time increases", () => {
  let previous = -1;
  for (let elapsed = 0; elapsed <= 120_000; elapsed += 250) {
    const index = activeStepIndex(elapsed);
    assert.ok(
      index >= previous,
      `step regressed: ${index} < ${previous} at ${elapsed}ms`,
    );
    previous = index;
  }
});

test("every step is reachable, in order, with none skipped", () => {
  const seen: number[] = [];
  for (let elapsed = 0; elapsed <= 120_000; elapsed += 100) {
    const index = activeStepIndex(elapsed);
    if (index !== seen[seen.length - 1]) seen.push(index);
  }
  assert.deepEqual(seen, [0, 1, 2, 3, 4]);
});

test("the final step is reached by the median wait", () => {
  assert.equal(
    activeStepIndex(MEDIAN_WAIT_MS),
    LOADING_STEPS.length - 1,
    "a typical answer should land on the last step, not stall short of it",
  );
});

test("the final step is not reached so early that the sequence is meaningless", () => {
  // Guards the opposite failure from the test above: onsets collapsing toward
  // zero would satisfy "reached by 20s" while showing the user nothing.
  assert.ok(
    activeStepIndex(10_000) < LOADING_STEPS.length - 1,
    "the last step must not already be active ten seconds in",
  );
});

test("the active step clamps at the final step rather than looping back", () => {
  for (const elapsed of [60_000, 600_000, 10_000_000]) {
    assert.equal(activeStepIndex(elapsed), LOADING_STEPS.length - 1);
  }
});

test("the active step is always a valid index into the step list", () => {
  for (let elapsed = -10_000; elapsed <= 200_000; elapsed += 137) {
    const index = activeStepIndex(elapsed);
    assert.ok(Number.isInteger(index), `non-integer index ${index}`);
    assert.ok(index >= 0 && index < LOADING_STEPS.length, `out of range: ${index}`);
  }
});
