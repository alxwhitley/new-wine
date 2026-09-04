import assert from "node:assert/strict";
import test from "node:test";

import {
  DISMISS_DISTANCE_PX,
  dragOutcome,
  dragTranslate,
  overlayOpacity,
} from "./sheet-drag.ts";

test("a downward drag follows the finger exactly", () => {
  assert.equal(dragTranslate(0), 0);
  assert.equal(dragTranslate(80), 80);
  assert.equal(dragTranslate(400), 400);
});

test("an upward drag is resisted so the sheet never detaches from the top", () => {
  assert.equal(dragTranslate(-40), -10);
  assert.equal(dragTranslate(-400), -100);
});

test("a slow, short drag springs back", () => {
  assert.equal(dragOutcome(20, 0.05), "spring-back");
  assert.equal(dragOutcome(DISMISS_DISTANCE_PX - 1, 0.1), "spring-back");
});

test("a long drag dismisses regardless of speed", () => {
  assert.equal(dragOutcome(DISMISS_DISTANCE_PX, 0), "dismiss");
  assert.equal(dragOutcome(300, 0.01), "dismiss");
});

test("a fast flick dismisses well before the distance threshold", () => {
  // The whole point of tracking velocity: a quick flick should not require
  // dragging a third of the screen.
  assert.equal(dragOutcome(50, 0.9), "dismiss");
});

test("a fast flick that barely moved is still a tap, not a dismissal", () => {
  assert.equal(dragOutcome(6, 2), "spring-back");
});

test("an upward flick never dismisses", () => {
  assert.equal(dragOutcome(-200, 3), "spring-back");
});

test("the overlay dims in step with the drag", () => {
  assert.equal(overlayOpacity(0, 800), 1);
  assert.equal(overlayOpacity(400, 800), 0.5);
  assert.equal(overlayOpacity(800, 800), 0);
});

test("overlay opacity stays in range for overshoot and degenerate heights", () => {
  assert.equal(overlayOpacity(1_200, 800), 0);
  assert.equal(overlayOpacity(-50, 800), 1);
  assert.equal(overlayOpacity(100, 0), 1);
});
