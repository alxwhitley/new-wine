import assert from "node:assert/strict";
import test from "node:test";

import { withoutFailedTurn } from "./chat-recovery.ts";

test("removes the trailing user question + empty assistant placeholder", () => {
  const messages = [
    { role: "user" as const, content: "earlier question" },
    { role: "assistant" as const, content: "earlier answer" },
    { role: "user" as const, content: "failed question" },
    { role: "assistant" as const, content: "" },
  ];

  const result = withoutFailedTurn(messages);

  assert.deepEqual(result, [
    { role: "user", content: "earlier question" },
    { role: "assistant", content: "earlier answer" },
  ]);
});

test("preserves conversation history before the failed turn", () => {
  const messages = [
    { role: "user" as const, content: "q1" },
    { role: "assistant" as const, content: "a1" },
    { role: "user" as const, content: "q2" },
    { role: "assistant" as const, content: "a2" },
    { role: "user" as const, content: "failed q3" },
    { role: "assistant" as const, content: "" },
  ];

  const result = withoutFailedTurn(messages);

  assert.equal(result.length, 4);
  assert.equal(result[3].content, "a2");
});

test("does nothing when the list does not end in a fresh user+assistant pair", () => {
  const successfulExchange = [
    { role: "user" as const, content: "question" },
    { role: "assistant" as const, content: "a complete answer" },
  ];
  assert.deepEqual(withoutFailedTurn(successfulExchange), successfulExchange);

  const onlyUser = [{ role: "user" as const, content: "question" }];
  assert.deepEqual(withoutFailedTurn(onlyUser), onlyUser);

  assert.deepEqual(withoutFailedTurn([]), []);
});

test("does not strip when the trailing pair is two user messages (never a real failed-turn shape)", () => {
  const messages = [
    { role: "user" as const, content: "a" },
    { role: "user" as const, content: "b" },
  ];
  assert.deepEqual(withoutFailedTurn(messages), messages);
});
