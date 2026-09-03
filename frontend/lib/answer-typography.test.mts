import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const messageSource = readFileSync(
  new URL("../components/newwine/chat-message.tsx", import.meta.url),
  "utf8",
);

test("answer headings use a medium weight and warm off-white hierarchy", () => {
  assert.match(
    messageSource,
    /<h2 className="font-sans text-\[1\.1rem\] font-medium text-accent-foreground mt-4 mb-2">/,
  );
  assert.match(
    messageSource,
    /<h3 className="font-sans text-base font-medium text-accent-foreground mt-4 mb-2">/,
  );
});
