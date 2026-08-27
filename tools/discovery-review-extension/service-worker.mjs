import {createReviewService} from "./review-service.mjs";

const SERVER_ORIGIN = "http://127.0.0.1:8765";
const SESSION_KEY = "reviewSession";

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
  async getReviewSession() {
    const value = await chrome.storage.session.get(SESSION_KEY);
    return value[SESSION_KEY] ?? null;
  },
  async setReviewSession(reviewSession) {
    await chrome.storage.session.set({[SESSION_KEY]: reviewSession});
  },
};

async function deactivateTab(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, {type: "DEACTIVATE_REVIEW"});
  } catch {
    // The old tab may already be closed, navigating, or without a receiver.
  }
}

const service = createReviewService({request, sessionStore, deactivateTab});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  service.handle(message, sender.tab?.id)
    .then(sendResponse)
    .catch((error) => sendResponse({error: error.message}));
  return true;
});
