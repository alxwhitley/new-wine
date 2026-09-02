import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(
  new URL("../app/page.tsx", import.meta.url),
  "utf8",
);
const inputSource = readFileSync(
  new URL("../components/newwine/chat-input.tsx", import.meta.url),
  "utf8",
);

test("empty-state composer and suggestions share one mobile width", () => {
  assert.match(pageSource, /max-w-xl[^>]*>[\s\S]*?<ChatInput[^>]*embedded[\s\S]*?SUGGESTIONS\.map/);
  assert.match(inputSource, /embedded\?: boolean/);
  assert.match(inputSource, /embedded \? undefined : "px-4 pb-2 md:px-12 md:pb-6"/);
});

test("single-line prompt text is vertically centered without changing bottom alignment", () => {
  assert.match(inputSource, /flex items-end/);
  assert.match(inputSource, /min-h-11[^\"]*py-2\.5/);
});

test("composer follows visual viewport changes and scrolls internally at its cap", () => {
  assert.match(inputSource, /window\.visualViewport/);
  assert.match(inputSource, /overflowY = .*auto/);
  assert.match(inputSource, /composerMaxHeight/);
});

test("chat shell follows the visible viewport while the keyboard and Safari chrome move", () => {
  assert.match(pageSource, /window\.visualViewport/);
  assert.match(pageSource, /offsetTop/);
  assert.match(pageSource, /bottomRef\.current\?\.scrollIntoView/);
});
