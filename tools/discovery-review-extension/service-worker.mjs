import {createReviewService} from "./review-service.mjs";

const SERVER_ORIGIN = "http://127.0.0.1:8765";

async function request(path, options = {}) {
  const headers = options.body
    ? {"Content-Type": "application/x-www-form-urlencoded"}
    : undefined;
  const response = await fetch(`${SERVER_ORIGIN}${path}`, {...options, headers});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Review server request failed");
  return payload;
}

const sessionStore = {
  async getActiveTabId() {
    const value = await chrome.storage.session.get("activeReviewTabId");
    return value.activeReviewTabId ?? null;
  },
  async setActiveTabId(tabId) {
    await chrome.storage.session.set({activeReviewTabId: tabId});
  },
};

const service = createReviewService({request, sessionStore});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  service.handle(message, sender.tab?.id)
    .then(sendResponse)
    .catch((error) => sendResponse({error: error.message}));
  return true;
});
