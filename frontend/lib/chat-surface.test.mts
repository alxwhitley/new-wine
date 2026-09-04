import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

// Comments in these files deliberately spell out the rejected approach
// ("NOT mask-image", 'block: "nearest"'), so a bare source search matches the
// explanation rather than the code. Strip comments before asserting absence.
function stripComments(src: string) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

// assert.match on a whole source file prints the entire file on failure, which
// buries the reason. These assertions carry their own message instead.
function assertSource(src: string, pattern: RegExp, message: string) {
  assert.ok(pattern.test(src), `${message}\n  expected to find: ${pattern}`);
}

const chatSource = source("../app/page.tsx");
const chatCode = stripComments(chatSource);
const globalsSource = source("../app/globals.css");
const globalsCode = stripComments(globalsSource);

// ── Item 1: overscroll containment ──────────────────────────────────────────
// Symptom: dragging the thread past its own top translated the WHOLE viewport.
// Three independent contributors, so three separate assertions -- fixing any
// one of them alone does not close it.

test("the document itself never rubber-bands", () => {
  // `overscroll-none` on the fixed shell in page.tsx cannot suppress the ROOT
  // scroller's bounce; only a declaration on html/body reaches it.
  assertSource(
    globalsSource,
    /html,\s*body\s*\{[^}]*overscroll-behavior:\s*none/,
    "globals.css must set overscroll-behavior: none on html, body",
  );
});

test("the message list does not chain its overscroll to the document", () => {
  assertSource(
    chatSource,
    /ref=\{scrollContainerRef\}[\s\S]{0,160}?overscroll-contain/,
    "the message-list scroller must carry overscroll-contain",
  );
});

test("the visual-viewport sync never follows a negative offsetTop", () => {
  // A rubber-band fires visualViewport 'scroll'; without this clamp the shell
  // is repositioned to the bounce offset and visibly rides it. The listener
  // itself stays -- it is load-bearing for iOS toolbar motion.
  assertSource(
    chatSource,
    /Math\.max\(\s*0,\s*Math\.round\(viewport\?\.offsetTop \?\? 0\)\s*\)/,
    "the shell's top must clamp offsetTop at 0",
  );
});

// ── Item 2: floating composer + bottom fade ─────────────────────────────────
// Answers used to stop at a hard edge against an opaque composer. The composer
// now overlays the thread and a gradient dissolves the text beneath it.

const chatInputSource = source("../components/newwine/chat-input.tsx");

test("the composer floats over the thread rather than sitting below it", () => {
  assertSource(
    chatSource,
    /ref=\{composerRef\}[\s\S]{0,160}?absolute inset-x-0 bottom-0/,
    "the composer wrapper must be absolutely positioned over the thread",
  );
});

test("the composer paints no opaque band of its own", () => {
  // With the composer in flow this was bg-background, which is exactly the
  // hard edge the fade replaces. Only the pill keeps a fill.
  assert.ok(
    !/shrink-0 bg-background/.test(chatInputSource),
    "chat-input's outer wrapper must not paint bg-background -- it would reinstate the hard edge",
  );
});

test("the fade is a gradient overlay, not a mask on the scroller", () => {
  // A mask on a scrolling element forces a compositing layer and costs real
  // scroll performance on iOS. The backdrop is bg-background, so an opaque
  // gradient is visually identical to fading to alpha-zero.
  assertSource(
    globalsSource,
    /\.composer-fade\s*\{[^}]*linear-gradient/,
    "globals.css must define .composer-fade as a linear-gradient",
  );
  assert.ok(
    !/mask-image/.test(globalsCode),
    "the fade must not be implemented as a mask",
  );
});

test("the fade and the scroller both size off the composer's real height", () => {
  // composerMaxHeight() lets the textarea grow, so a fixed reservation clips
  // the last line of an answer.
  assertSource(
    globalsSource,
    /\.composer-fade\s*\{[^}]*var\(--composer-h/,
    ".composer-fade must read --composer-h",
  );
  assertSource(
    chatSource,
    /ref=\{scrollContainerRef\}[\s\S]{0,200}?pb-\[calc\(var\(--composer-h/,
    "the scroller must reserve --composer-h as bottom padding",
  );
  assertSource(
    chatCode,
    /setProperty\(\s*"--composer-h"/,
    "--composer-h must be published onto the chat region",
  );
  assertSource(
    chatCode,
    /new ResizeObserver\(sync\)[\s\S]{0,120}?observe\(composer\)/,
    "a ResizeObserver must watch the composer so the reservation tracks its growth",
  );
});

test("the keyboard handler pins the latest turn above the floating composer", () => {
  // block: "nearest" aligns to the scrollport edge, which the composer now
  // overlays -- it would park the newest turn underneath it.
  assert.ok(
    !/block: "nearest"/.test(chatCode),
    'keepLatestVisible must not use block: "nearest" once the composer overlays the scrollport',
  );
  assertSource(
    chatCode,
    /scroller\.scrollTop = scroller\.scrollHeight/,
    "it must scroll explicitly to the end instead",
  );
});
