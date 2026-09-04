import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

function assertSource(src: string, pattern: RegExp, message: string) {
  assert.ok(pattern.test(src), `${message}\n  expected to find: ${pattern}`);
}

const modalSource = source("../components/admin/AdminModal.tsx");
const hookSource = source("../hooks/use-sheet-drag.ts");
const dialogSource = source("../components/ui/dialog.tsx");
const globalsSource = source("../app/globals.css");

// ── Item 3: swipe down to leave the Profile view ────────────────────────────
// The gesture logic itself is unit-tested in sheet-drag.test.mts. These pin the
// wiring, which is where the failure modes actually live.

test("the Profile sheet's transform replaces the dialog's centring, not fights it", () => {
  // DialogContent centres with translate-x/y-[-50%] and animates with
  // zoom-in-95. A drag transform must own the property outright, which is why
  // the mobile geometry is an unlayered rule rather than Tailwind overrides --
  // class order between a base class and a responsive override is not
  // guaranteed, and losing that race leaves the sheet unmovable.
  assertSource(
    globalsSource,
    /\[data-mobile-sheet\]\s*\{[^}]*transform:\s*translateY\(var\(--sheet-drag-y/,
    "globals.css must drive the sheet transform from --sheet-drag-y",
  );
  assertSource(
    globalsSource,
    /\[data-mobile-sheet\]\s*\{[^}]*top:\s*auto[^}]*bottom:\s*0/,
    "the mobile sheet must be bottom-anchored, not centred",
  );
  assertSource(
    modalSource,
    /"--sheet-drag-y":\s*`\$\{sheet\.offset\}px`/,
    "AdminModal must publish the drag offset as --sheet-drag-y",
  );
});

test("dragging suspends the transition so the sheet tracks the finger 1:1", () => {
  assertSource(
    globalsSource,
    /\[data-sheet-dragging="true"\]\s*\{\s*transition:\s*none/,
    "a dragging sheet must not transition",
  );
  assertSource(
    modalSource,
    /data-sheet-dragging=\{sheet\.dragging/,
    "AdminModal must expose the dragging state to CSS",
  );
});

test("a drag-dismiss slides out before closing rather than snapping back", () => {
  // Closing first would return the sheet to rest for a frame, then play the
  // exit animation from there.
  assertSource(
    globalsSource,
    /\[data-sheet-dismissing="true"\]\s*\{\s*animation:\s*none/,
    "a drag-dismiss must suppress the state animation",
  );
  assertSource(
    hookSource,
    /setDismissing\(true\)[\s\S]{0,200}?setTimeout\(onDismiss/,
    "the hook must slide out, then close",
  );
});

test("the gesture never steals a drag that belongs to a scroller", () => {
  assertSource(
    hookSource,
    /isInsideScrolledRegion/,
    "the hook must refuse to start inside an already-scrolled region",
  );
  assertSource(
    modalSource,
    /isMobile && paneAtTop \? "touch-pan-up" : "touch-pan-y"/,
    "the scrolling pane must yield downward drags only while at its top",
  );
});

test("the sheet gesture is touch-only and mobile-only", () => {
  assertSource(
    hookSource,
    /event\.pointerType === "mouse"/,
    "a mouse drag must not dismiss the dialog",
  );
  assertSource(
    modalSource,
    /useSheetDrag\(\{ open, enabled: isMobile/,
    "the drag must be enabled on mobile only",
  );
  assertSource(
    hookSource,
    /enabled\s*\?\s*\{ onPointerDown/,
    "desktop must receive no pointer handlers at all",
  );
});

test("reduced motion keeps the gesture but drops the animation", () => {
  assertSource(
    hookSource,
    /if \(!reduceMotion\) setOffset\(dragTranslate\(deltaY\)\)/,
    "nothing should follow the finger under reduced motion",
  );
  assertSource(
    globalsSource,
    /prefers-reduced-motion: reduce\)\s*\{\s*\[data-mobile-sheet\]/,
    "globals.css must disable the sheet's motion under reduced motion",
  );
});

test("the backdrop dims with the drag", () => {
  // The overlay is rendered inside DialogContent, so a caller has no other
  // way to reach it.
  assertSource(
    dialogSource,
    /<DialogOverlay className=\{overlayClassName\} style=\{overlayStyle\} \/>/,
    "DialogContent must forward overlay styling",
  );
  assertSource(
    modalSource,
    /overlayStyle=\{\{ opacity: sheet\.overlayOpacity \}\}/,
    "AdminModal must dim the backdrop in step with the drag",
  );
});
