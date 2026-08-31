import assert from "node:assert/strict";
import test from "node:test";

import {
  parseGuestChatSession,
  serializeGuestChatSession,
  shouldRetainPendingGuestJob,
  type GuestChatSession,
} from "./guest-chat-session.ts";

test("round-trips completed guest messages and their source metadata", () => {
  const session: GuestChatSession = {
    version: 1,
    messages: [
      { role: "user", content: "What is sanctification?" },
      {
        role: "assistant",
        content: "A completed answer",
        citations: [{
          chunk_id: "chunk-1",
          document_title: "A source",
          author: "A teacher",
          content: "Source excerpt",
          url: null,
        }],
      },
    ],
    topicsEstablished: { sanctification: 0 },
    pendingJob: null,
  };

  assert.deepEqual(parseGuestChatSession(serializeGuestChatSession(session)), session);
});

test("restores the durable job needed to reconnect after a reload", () => {
  const session: GuestChatSession = {
    version: 1,
    messages: [
      { role: "user", content: "A question still running" },
      { role: "assistant", content: "" },
    ],
    topicsEstablished: {},
    pendingJob: {
      jobId: "8677f62d-7ce9-4c3f-b9a5-dd256566a635",
      question: "A question still running",
    },
  };

  assert.deepEqual(parseGuestChatSession(serializeGuestChatSession(session)), session);
});

test("rejects malformed or unsupported guest-session data", () => {
  assert.equal(parseGuestChatSession(null), null);
  assert.equal(parseGuestChatSession("not json"), null);
  assert.equal(parseGuestChatSession(JSON.stringify({ version: 2, messages: [] })), null);
  assert.equal(parseGuestChatSession(JSON.stringify({
    version: 1,
    messages: [{ role: "system", content: "hidden" }],
    topicsEstablished: {},
    pendingJob: null,
  })), null);
  assert.equal(parseGuestChatSession(JSON.stringify({
    version: 1,
    messages: [],
    topicsEstablished: {},
    pendingJob: { jobId: "", question: "missing id" },
  })), null);
  assert.equal(parseGuestChatSession(JSON.stringify({
    version: 1,
    messages: [{ role: "assistant", content: "answer", citations: [null] }],
    topicsEstablished: {},
    pendingJob: null,
  })), null);
  assert.equal(parseGuestChatSession(JSON.stringify({
    version: 1,
    messages: [{
      role: "assistant",
      content: "answer",
      citations: [{
        chunk_id: "chunk-1",
        document_title: "Source",
        author: "Author",
        content: "Excerpt",
        url: "javascript:alert(1)",
      }],
    }],
    topicsEstablished: {},
    pendingJob: null,
  })), null);
});

test("keeps reconnectable jobs only for transient delivery failures", () => {
  assert.equal(shouldRetainPendingGuestJob("New Wine is temporarily unavailable."), true);
  assert.equal(shouldRetainPendingGuestJob("timeout_waiting_for_answer"), true);
  assert.equal(shouldRetainPendingGuestJob("generation_failed"), false);
  assert.equal(shouldRetainPendingGuestJob("generation_canceled"), false);
  assert.equal(shouldRetainPendingGuestJob("job_disappeared"), false);
  assert.equal(shouldRetainPendingGuestJob("result_404"), false);
});
