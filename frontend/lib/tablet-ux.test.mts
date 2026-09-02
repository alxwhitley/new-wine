import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const sidebarSource = source("../components/newwine/sidebar.tsx");
const chatSource = source("../app/page.tsx");
const buttonSource = source("../components/ui/button.tsx");
const profileSource = source("../components/admin/AdminModal.tsx");

test("portrait tablets get a shared app header with menu and account access", () => {
  assert.match(sidebarSource, /onOpen: \(\) => void/);
  assert.match(sidebarSource, /data-testid="tablet-app-header"/);
  assert.match(sidebarSource, /data-testid="tablet-app-header"[\s\S]*md:flex lg:hidden/);
  assert.match(sidebarSource, /aria-label="Open menu"/);
  assert.match(sidebarSource, /aria-label="Open Profile"/);
});

test("the chat empty state uses the portrait-tablet canvas intentionally", () => {
  assert.match(chatSource, /md:max-w-2xl lg:max-w-xl xl:max-w-2xl/);
  assert.match(chatSource, /md:max-lg:gap-3/);
});

test("core buttons and answer suggestions provide touch-down feedback", () => {
  assert.match(buttonSource, /active:scale-\[0\.98\]/);
  assert.match(chatSource, /active:bg-accent active:text-foreground/);
});

test("Profile adapts to a phone-height viewport and tablet navigation", () => {
  assert.match(profileSource, /h-\[calc\(100dvh-1rem\)\]/);
  assert.match(profileSource, /sm:h-\[85dvh\]/);
  assert.match(profileSource, /flex-1 min-h-0 flex-col overflow-hidden md:flex-row/);
  assert.match(profileSource, /overflow-x-auto overscroll-x-contain md:flex-col/);
  assert.match(profileSource, /p-4 sm:p-6/);
});
