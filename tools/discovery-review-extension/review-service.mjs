export const MESSAGE_TYPES = Object.freeze({
  START_REVIEW: "START_REVIEW",
  GET_REVIEW_STATE: "GET_REVIEW_STATE",
  DECIDE_APPROVE: "DECIDE_APPROVE",
  DECIDE_REJECT: "DECIDE_REJECT",
});

const SERVER_RESPONSE_KEYS = [
  "candidate",
  "capability",
  "done",
  "revision",
];
const CANDIDATE_KEYS = ["link", "name", "remaining"];

function hasExactKeys(value, expected) {
  return Object.keys(value).sort().join("\0") === expected.join("\0");
}

function invalidServerResponse() {
  throw new Error("Invalid review server response");
}

function validateServerResponse(value) {
  if (
    !value
    || typeof value !== "object"
    || Array.isArray(value)
    || !hasExactKeys(value, SERVER_RESPONSE_KEYS)
    || typeof value.done !== "boolean"
    || typeof value.capability !== "string"
    || value.capability.length < 32
    || typeof value.revision !== "string"
    || value.revision.length < 32
  ) {
    invalidServerResponse();
  }

  if (value.done) {
    if (value.candidate !== null) invalidServerResponse();
    return {
      publicPayload: {done: true, candidate: null},
      capability: value.capability,
      revision: value.revision,
    };
  }

  const candidate = value.candidate;
  if (
    !candidate
    || typeof candidate !== "object"
    || Array.isArray(candidate)
    || !hasExactKeys(candidate, CANDIDATE_KEYS)
    || typeof candidate.name !== "string"
    || candidate.name.length === 0
    || typeof candidate.link !== "string"
    || !Number.isInteger(candidate.remaining)
    || candidate.remaining < 1
  ) {
    invalidServerResponse();
  }

  let parsedLink;
  try {
    parsedLink = new URL(candidate.link);
  } catch {
    invalidServerResponse();
  }
  if (
    !candidate.link.match(/^https?:\/\//)
    || !["http:", "https:"].includes(parsedLink.protocol)
  ) {
    invalidServerResponse();
  }

  return {
    publicPayload: {
      done: false,
      candidate: {
        name: candidate.name,
        link: candidate.link,
        remaining: candidate.remaining,
      },
    },
    capability: value.capability,
    revision: value.revision,
  };
}

export function createReviewService({request, sessionStore, deactivateTab}) {
  async function activeSession(tabId) {
    if (!Number.isInteger(tabId)) return null;
    const session = await sessionStore.getReviewSession();
    return session?.tabId === tabId ? session : null;
  }

  async function storeValidatedSession(tabId, validated) {
    await sessionStore.setReviewSession({
      tabId,
      capability: validated.capability,
      revision: validated.revision,
    });
  }

  return {
    async handle(message, tabId) {
      if (!message || !Object.values(MESSAGE_TYPES).includes(message.type)) {
        throw new Error("Unknown extension message");
      }
      if (!Number.isInteger(tabId)) throw new Error("Missing sender tab");

      if (message.type === MESSAGE_TYPES.START_REVIEW) {
        const validated = validateServerResponse(
          await request("/api/review/start", {method: "POST"}),
        );
        const previous = await sessionStore.getReviewSession();
        await storeValidatedSession(tabId, validated);
        if (Number.isInteger(previous?.tabId) && previous.tabId !== tabId) {
          try {
            await deactivateTab(previous.tabId);
          } catch {
            // A closed/navigating old tab has nothing left to deactivate.
          }
        }
        return {active: true, ...validated.publicPayload};
      }

      const session = await activeSession(tabId);
      if (!session) return {active: false};

      try {
        if (message.type === MESSAGE_TYPES.GET_REVIEW_STATE) {
          const validated = validateServerResponse(
            await request("/api/review/current"),
          );
          await storeValidatedSession(tabId, validated);
          return {active: true, ...validated.publicPayload};
        }

        const action = message.type === MESSAGE_TYPES.DECIDE_APPROVE
          ? "approve"
          : "reject";
        const body = new URLSearchParams({
          action,
          capability: session.capability,
          revision: session.revision,
        }).toString();
        const validated = validateServerResponse(
          await request("/api/review/decision", {
            method: "POST",
            body,
          }),
        );
        await storeValidatedSession(tabId, validated);
        return {active: true, ...validated.publicPayload};
      } catch (error) {
        return {
          active: true,
          error: error?.message || "Review server request failed",
        };
      }
    },
  };
}
