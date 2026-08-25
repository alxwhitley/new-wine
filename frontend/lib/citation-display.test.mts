import assert from "node:assert/strict";
import test from "node:test";

import {
  hasRenderableInlineCitation,
  shouldRenderCitationFallback,
} from "./citation-display.ts";

test("recognizes only citation markers that resolve to supplied sources", () => {
  assert.equal(hasRenderableInlineCitation("A claim [1].", 2), true);
  assert.equal(hasRenderableInlineCitation("A claim [3].", 2), false);
  assert.equal(hasRenderableInlineCitation("No inline source marker.", 2), false);
});

test("shows a source fallback when citations exist but prose has no usable markers", () => {
  assert.equal(shouldRenderCitationFallback("No markers here.", 4), true);
  assert.equal(shouldRenderCitationFallback("Grounded here [1].", 4), false);
  assert.equal(shouldRenderCitationFallback("No sources.", 0), false);
});
