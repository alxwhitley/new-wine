import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebarSource = readFileSync(
  new URL("../components/newwine/sidebar.tsx", import.meta.url),
  "utf8",
);

test("tablet and desktop sidebar follows the dynamic viewport height", () => {
  assert.match(
    sidebarSource,
    /className="hidden md:flex fixed left-0 top-0 z-40 h-dvh-safe w-64/,
  );
  assert.doesNotMatch(
    sidebarSource,
    /className="hidden md:flex fixed left-0 top-0 z-40 h-screen w-64/,
  );
});

test("account footer has a stable responsive-test target in both auth states", () => {
  assert.match(sidebarSource, /data-testid="sidebar-account-footer"/);
});
