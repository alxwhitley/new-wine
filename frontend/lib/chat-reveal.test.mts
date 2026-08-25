import assert from "node:assert/strict";
import test from "node:test";

import { revealCharsPerSecond } from "./chat-reveal.ts";

test("keeps short answers at the established reading pace", () => {
  assert.equal(revealCharsPerSecond(750), 250);
});

test("caps long-answer reveal time at six seconds without disabling streaming", () => {
  assert.equal(revealCharsPerSecond(2_400), 400);
  assert.equal(revealCharsPerSecond(3_000), 500);
});
