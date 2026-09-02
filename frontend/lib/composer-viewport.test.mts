import assert from "node:assert/strict";
import test from "node:test";

import { composerMaxHeight } from "./composer-viewport.ts";

test("caps the composer at a comfortable height on phones and tablets", () => {
  assert.equal(composerMaxHeight(844), 192);
  assert.equal(composerMaxHeight(1_180), 192);
});

test("keeps the send control reachable when the software keyboard is tall", () => {
  assert.equal(composerMaxHeight(360), 115);
  assert.equal(composerMaxHeight(240), 96);
});
