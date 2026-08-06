import assert from "node:assert/strict";
import test from "node:test";

import { detectVerseReferences } from "./study-reference.ts";

test("does not detect a valid book name embedded after an alphabetic prefix", () => {
  assert.deepEqual(detectVerseReferences("I Genesis 1:1"), []);
});

test("detects numeric, Roman-numeral, and spelled recognized book prefixes", () => {
  const cases = [
    { text: "1 Samuel 1:1", raw: "1 Samuel 1:1", book: "1 Samuel", code: "1SA" },
    { text: "II Timothy 2:2", raw: "II Timothy 2:2", book: "II Timothy", code: "2TI" },
    { text: "First Corinthians 1:1", raw: "First Corinthians 1:1", book: "First Corinthians", code: "1CO" },
  ];

  for (const expected of cases) {
    const matches = detectVerseReferences(expected.text);
    assert.equal(matches.length, 1);
    assert.equal(matches[0].raw, expected.raw);
    assert.equal(matches[0].book, expected.book);
    assert.equal(matches[0].code, expected.code);
    assert.equal(matches[0].index, 0);
  }
});

test("detects a normal unprefixed reference", () => {
  const matches = detectVerseReferences("Read John 3:16 today.");

  assert.equal(matches.length, 1);
  assert.equal(matches[0].raw, "John 3:16");
  assert.equal(matches[0].book, "John");
  assert.equal(matches[0].code, "JHN");
  assert.equal(matches[0].index, 5);
});

test("detects a reference after punctuation but not inside an adjacent token", () => {
  assert.equal(detectVerseReferences("(John 3:16)")[0].index, 1);
  assert.deepEqual(detectVerseReferences("notJohn 3:16"), []);
});
