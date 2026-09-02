import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebarSource = readFileSync(
  new URL("../components/newwine/sidebar.tsx", import.meta.url),
  "utf8",
);

const shellSources = [
  "../app/page.tsx",
  "../app/study/page.tsx",
  "../app/library/page.tsx",
  "../app/library/authors/page.tsx",
].map((path) => readFileSync(new URL(path, import.meta.url), "utf8"));

const chatShellSource = shellSources[0];

test("tablet and desktop sidebar follows the dynamic viewport height", () => {
  assert.match(
    sidebarSource,
    /className="hidden lg:flex fixed left-0 top-0 z-40 h-dvh-safe w-64/,
  );
  assert.doesNotMatch(
    sidebarSource,
    /className="hidden lg:flex fixed left-0 top-0 z-40 h-screen w-64/,
  );
});

test("account footer has a stable responsive-test target in both auth states", () => {
  assert.match(sidebarSource, /data-testid="sidebar-account-footer"/);
});

test("portrait tablets use the drawer while landscape tablets keep the fixed sidebar", () => {
  assert.match(
    sidebarSource,
    /className="hidden lg:flex fixed left-0 top-0 z-40 h-dvh-safe w-64/,
  );
  assert.match(sidebarSource, /fixed inset-0 z-40 bg-black\/50 lg:hidden/);
  assert.match(sidebarSource, /h-dvh-safe w-full sm:w-80[^\n]+lg:hidden/);
  assert.doesNotMatch(
    sidebarSource,
    /className="hidden md:flex fixed left-0 top-0 z-40/,
  );
});

test("app shells reserve sidebar space only at the landscape-tablet breakpoint", () => {
  for (const source of shellSources) {
    assert.match(source, /lg:ml-64/);
    assert.doesNotMatch(source, /md:ml-64/);
  }
});

test("the portrait-tablet chat menu is not covered by the desktop top bar", () => {
  assert.match(
    chatShellSource,
    /className="hidden lg:flex h-14 shrink-0 items-center justify-end/,
  );
  assert.doesNotMatch(
    chatShellSource,
    /className="hidden md:flex h-14 shrink-0 items-center justify-end/,
  );
});
