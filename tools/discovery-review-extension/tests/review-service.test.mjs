import assert from "node:assert/strict";
import test from "node:test";
import {
  MESSAGE_TYPES,
  createReviewService,
} from "../review-service.mjs";

function candidatePayload({
  name = "First",
  link = "https://first.example",
  remaining = 2,
  capability = "capability-abcdefghijklmnopqrstuvwxyz-123456",
  revision = "revision-abcdefghijklmnopqrstuvwxyz-12345678",
} = {}) {
  return {
    done: false,
    candidate: {name, link, remaining},
    capability,
    revision,
  };
}

function donePayload({
  capability = "capability-abcdefghijklmnopqrstuvwxyz-123456",
  revision = "revision-abcdefghijklmnopqrstuvwxyz-12345678",
} = {}) {
  return {done: true, candidate: null, capability, revision};
}

function harness(responses) {
  const calls = [];
  const deactivatedTabs = [];
  let reviewSession = null;
  const service = createReviewService({
    request: async (path, options = {}) => {
      calls.push({path, options});
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
    sessionStore: {
      getReviewSession: async () => reviewSession,
      setReviewSession: async (value) => { reviewSession = value; },
    },
    deactivateTab: async (tabId) => { deactivatedTabs.push(tabId); },
  });
  return {
    service,
    calls,
    deactivatedTabs,
    session: () => reviewSession,
  };
}

test("start retains server tokens in worker state and strips them from content", async () => {
  const raw = candidatePayload();
  const h = harness([raw]);
  const result = await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);

  assert.deepEqual(result, {
    active: true,
    done: false,
    candidate: {
      name: "First",
      link: "https://first.example",
      remaining: 2,
    },
  });
  assert.deepEqual(h.session(), {
    tabId: 41,
    capability: raw.capability,
    revision: raw.revision,
  });
  assert.equal(h.calls[0].path, "/api/review/start");
});

test("inactive tabs cannot read or decide", async () => {
  const h = harness([candidatePayload()]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle({type: MESSAGE_TYPES.DECIDE_APPROVE}, 99);
  assert.deepEqual(result, {active: false});
  assert.equal(h.calls.length, 1);
});

test("decision uses only worker-held capability, revision, and server-owned action", async () => {
  const first = candidatePayload();
  const second = candidatePayload({
    name: "Second",
    link: "http://second.example/path",
    remaining: 1,
    capability: "next-capability-abcdefghijklmnopqrstuvwxyz",
    revision: "next-revision-abcdefghijklmnopqrstuvwxyz-12",
  });
  const h = harness([first, second]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle(
    {
      type: MESSAGE_TYPES.DECIDE_APPROVE,
      name: "Spoofed",
      url: "https://evil.example",
      capability: "page-owned",
      revision: "page-owned",
    },
    41,
  );

  assert.equal(h.calls[1].path, "/api/review/decision");
  assert.equal(h.calls[1].options.method, "POST");
  const body = new URLSearchParams(h.calls[1].options.body);
  assert.equal(body.get("action"), "approve");
  assert.equal(body.get("capability"), first.capability);
  assert.equal(body.get("revision"), first.revision);
  assert.equal(body.has("name"), false);
  assert.equal(body.has("link"), false);
  assert.deepEqual(result, {
    active: true,
    done: false,
    candidate: {
      name: "Second",
      link: "http://second.example/path",
      remaining: 1,
    },
  });
  assert.deepEqual(h.session(), {
    tabId: 41,
    capability: second.capability,
    revision: second.revision,
  });
});

test("tracked current refreshes worker tokens without exposing them", async () => {
  const first = candidatePayload();
  const refreshed = candidatePayload({
    capability: "refreshed-capability-abcdefghijklmnopqrstuvwxyz",
    revision: "refreshed-revision-abcdefghijklmnopqrstuvwxyz",
  });
  const h = harness([first, refreshed]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle(
    {type: MESSAGE_TYPES.GET_REVIEW_STATE},
    41,
  );

  assert.deepEqual(result, {
    active: true,
    done: false,
    candidate: {
      name: "First",
      link: "https://first.example",
      remaining: 2,
    },
  });
  assert.equal(h.session().capability, refreshed.capability);
  assert.equal(h.session().revision, refreshed.revision);
});

test("a successful new start deactivates the previously tracked tab", async () => {
  const h = harness([candidatePayload(), candidatePayload()]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const replacement = await h.service.handle(
    {type: MESSAGE_TYPES.START_REVIEW},
    99,
  );

  assert.equal(replacement.active, true);
  assert.equal(h.session().tabId, 99);
  assert.deepEqual(h.deactivatedTabs, [41]);
  assert.deepEqual(
    await h.service.handle({type: MESSAGE_TYPES.GET_REVIEW_STATE}, 41),
    {active: false},
  );
});

test("terminal payload is exact and tokens remain worker-only", async () => {
  const h = harness([candidatePayload(), donePayload()]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle(
    {type: MESSAGE_TYPES.DECIDE_REJECT},
    41,
  );
  assert.deepEqual(result, {active: true, done: true, candidate: null});
  assert.equal(h.session().revision, donePayload().revision);
});

const malformedPayloads = [
  ["non-object", null],
  ["non-boolean done", {...candidatePayload(), done: "false"}],
  ["wrong candidate branch", {...candidatePayload(), candidate: null}],
  ["non-string name", candidatePayload({name: 7})],
  ["non-integer remaining", candidatePayload({remaining: 1.5})],
  ["zero remaining", candidatePayload({remaining: 0})],
  ["relative URL", candidatePayload({link: "/relative"})],
  ["non-http URL", candidatePayload({link: "javascript:alert(1)"})],
  ["extra top-level field", {...candidatePayload(), extra: true}],
  [
    "extra candidate field",
    {
      ...candidatePayload(),
      candidate: {...candidatePayload().candidate, extra: true},
    },
  ],
  ["non-string capability", {...candidatePayload(), capability: 42}],
  ["blank revision", {...candidatePayload(), revision: ""}],
];

for (const [label, malformed] of malformedPayloads) {
  test(`tracked malformed success becomes an active error: ${label}`, async () => {
    const h = harness([candidatePayload(), malformed]);
    await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
    const result = await h.service.handle(
      {type: MESSAGE_TYPES.GET_REVIEW_STATE},
      41,
    );
    assert.equal(result.active, true);
    assert.match(result.error, /Invalid review server response/);
    assert.equal(h.session().capability, candidatePayload().capability);
  });
}

test("invalid start payload never activates or deactivates a tab", async () => {
  const h = harness([candidatePayload({link: "file:///tmp/candidate"})]);
  await assert.rejects(
    h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41),
    /Invalid review server response/,
  );
  assert.equal(h.session(), null);
  assert.deepEqual(h.deactivatedTabs, []);
});

test("tracked server error remains an active error", async () => {
  const h = harness([candidatePayload(), new Error("server unavailable")]);
  await h.service.handle({type: MESSAGE_TYPES.START_REVIEW}, 41);
  const result = await h.service.handle(
    {type: MESSAGE_TYPES.GET_REVIEW_STATE},
    41,
  );
  assert.deepEqual(result, {active: true, error: "server unavailable"});
});

test("unknown messages are rejected without a request", async () => {
  const h = harness([]);
  await assert.rejects(
    h.service.handle(
      {type: "FETCH_ARBITRARY_URL", url: "https://evil.example"},
      41,
    ),
    /Unknown extension message/,
  );
  assert.equal(h.calls.length, 0);
});
