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

test("portalled dialogs mount once, not once per sidebarContent render", () => {
  // sidebarContent is rendered twice -- in the desktop aside and in the
  // drawer. Radix portals to document.body, so a dialog declared inside it
  // escapes both the aside's display:none and the drawer's inert, producing
  // two live dialogs, two focus traps, and doubled admin fetches the moment
  // the tablet header's Open Profile button sets adminOpen.
  const contentStart = sidebarSource.indexOf("const sidebarContent = (");
  assert.ok(contentStart > 0, "sidebarContent must exist");
  const returnStart = sidebarSource.indexOf("\n  return (", contentStart);
  assert.ok(returnStart > contentStart, "component return must follow it");
  const sidebarContent = sidebarSource.slice(contentStart, returnStart);

  assert.ok(
    !sidebarContent.includes("<AdminModal"),
    "AdminModal must not be declared inside the twice-rendered sidebarContent",
  );
  assert.ok(
    !sidebarContent.includes("<Sheet "),
    "the contributor Sheet must not be declared inside sidebarContent",
  );

  // Still rendered -- hoisted, not dropped, and exactly once each.
  assert.equal(sidebarSource.split("<AdminModal").length - 1, 1);
  assert.equal(sidebarSource.split("<Sheet ").length - 1, 1);
  assert.equal(sidebarSource.split("{sidebarContent}").length - 1, 2);
});
