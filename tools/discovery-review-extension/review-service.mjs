export const MESSAGE_TYPES = Object.freeze({
  START_REVIEW: "START_REVIEW",
  GET_REVIEW_STATE: "GET_REVIEW_STATE",
  DECIDE_APPROVE: "DECIDE_APPROVE",
  DECIDE_REJECT: "DECIDE_REJECT",
});

export function createReviewService({request, sessionStore}) {
  async function requireActive(tabId) {
    return Number.isInteger(tabId)
      && (await sessionStore.getActiveTabId()) === tabId;
  }

  return {
    async handle(message, tabId) {
      if (!message || !Object.values(MESSAGE_TYPES).includes(message.type)) {
        throw new Error("Unknown extension message");
      }
      if (!Number.isInteger(tabId)) throw new Error("Missing sender tab");

      if (message.type === MESSAGE_TYPES.START_REVIEW) {
        const payload = await request("/api/review/start", {method: "POST"});
        await sessionStore.setActiveTabId(tabId);
        return {active: true, ...payload};
      }

      if (!(await requireActive(tabId))) return {active: false};

      if (message.type === MESSAGE_TYPES.GET_REVIEW_STATE) {
        const payload = await request("/api/review/current");
        return {active: true, ...payload};
      }

      const action = message.type === MESSAGE_TYPES.DECIDE_APPROVE
        ? "approve"
        : "reject";
      const payload = await request("/api/review/decision", {
        method: "POST",
        body: `action=${action}`,
      });
      return {active: true, ...payload};
    },
  };
}
