import assert from "node:assert/strict";
import test from "node:test";
import {
  MESSAGE_TYPES,
  createReviewService,
} from "../review-service.mjs";

function harness(responses) {
  const calls = [];
  let activeReviewTabId = null;
  const service = createReviewService({
    request: async (path, options = {}) => {
      calls.push({path, options});
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
    sessionStore: {
      getActiveTabId: async () => activeReviewTabId,
      setActiveTabId: async (tabId) => { activeReviewTabId = tabId; },
    },
  });
  return {service, calls, activeTab: () => activeReviewTabId};
}

test("start activates only after the fixed start endpoint succeeds", async () => {
  const h = harness([{done: false, candidate: {name: "First", link: "https://first.example", remaining: 2}}]);
  const result = await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  assert.equal(h.activeTab(), 41);
  assert.equal(h.calls[0].path, "/api/review/start");
  assert.equal(result.active, true);
});

test("inactive tabs cannot read or decide", async () => {
  const h = harness([{done: false, candidate: {name: "First", link: "https://first.example", remaining: 2}}]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle({type: MESSAGE_TYPES.DECIDE_APPROVE}, 99);
  assert.deepEqual(result, {active: false});
  assert.equal(h.calls.length, 1);
});

test("tracked state request returns structured active server error", async () => {
  const h = harness([
    {done: false, candidate: {name: "First", link: "https://first.example", remaining: 2}},
    new Error("server unavailable"),
  ]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle({type: MESSAGE_TYPES.GET_REVIEW_STATE}, 41);
  assert.deepEqual(result, {active: true, error: "server unavailable"});
});

test("decision messages map to one fixed endpoint and server-owned action", async () => {
  const h = harness([
    {done: false, candidate: {name: "First", link: "https://first.example", remaining: 2}},
    {done: false, candidate: {name: "Second", link: "https://second.example", remaining: 1}},
  ]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle({type: MESSAGE_TYPES.DECIDE_APPROVE, url: "https://evil.example"}, 41);
  assert.equal(h.calls[1].path, "/api/review/decision");
  assert.equal(h.calls[1].options.body, "action=approve");
  assert.equal(result.candidate.name, "Second");
});

test("unknown messages are rejected without a request", async () => {
  const h = harness([]);
  await assert.rejects(
    h.service.handle({type: "FETCH_ARBITRARY_URL", url: "https://evil.example"}, 41),
    /Unknown extension message/,
  );
  assert.equal(h.calls.length, 0);
});
