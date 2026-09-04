import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(relativePath: string) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

// assert.match on a whole source file prints the entire file on failure, which
// buries the reason. These assertions carry their own message instead.
function assertSource(src: string, pattern: RegExp, message: string) {
  assert.ok(pattern.test(src), `${message}\n  expected to find: ${pattern}`);
}

const chatSource = source("../app/page.tsx");
const globalsSource = source("../app/globals.css");

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
