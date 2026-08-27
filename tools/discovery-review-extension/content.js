(() => {
  "use strict";

  const TYPES = Object.freeze({
    START: "START_REVIEW",
    STATE: "GET_REVIEW_STATE",
    APPROVE: "DECIDE_APPROVE",
    REJECT: "DECIDE_REJECT",
  });
  const HOST_ID = "rhemata-discovery-review-host";

  const send = (type) => new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({type}, (response) => {
      const runtimeError = chrome.runtime.lastError;
      if (runtimeError) return reject(new Error(runtimeError.message));
      if (!response || response.error) {
        return reject(new Error(response?.error || "No response from review extension"));
      }
      resolve(response);
    });
  });

  function createElement(tagName, text) {
    const element = document.createElement(tagName);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function prepareToolbar() {
    let host = document.getElementById(HOST_ID);
    if (!host) {
      host = document.createElement("div");
      host.id = HOST_ID;
      document.documentElement.append(host);
    }
    const shadow = host.shadowRoot || host.attachShadow({mode: "open"});
    shadow.replaceChildren();

    const style = createElement("style");
    style.textContent = `
      :host {
        all: initial;
        position: fixed;
        inset: auto 0 0 0;
        z-index: 2147483647;
        height: 64px;
        color: #1c1917;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .bar {
        box-sizing: border-box;
        display: flex;
        align-items: center;
        gap: 16px;
        width: 100%;
        height: 64px;
        padding: 8px 16px;
        background: #fafaf9;
        border-top: 2px solid #292524;
        box-shadow: 0 -2px 8px rgb(28 25 23 / 20%);
      }
      .summary {
        display: flex;
        align-items: baseline;
        gap: 12px;
        min-width: 0;
        flex: 1;
      }
      .name {
        overflow: hidden;
        font-size: 16px;
        font-weight: 700;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .remaining, .status {
        flex: none;
        color: #57534e;
        font-size: 14px;
      }
      .status[aria-invalid="true"] { color: #b91c1c; }
      .actions { display: flex; gap: 8px; }
      button {
        min-height: 44px;
        padding: 8px 16px;
        border: 2px solid #292524;
        border-radius: 6px;
        background: #ffffff;
        color: #1c1917;
        cursor: pointer;
        font: 700 14px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      button.primary { background: #166534; border-color: #166534; color: #ffffff; }
      button:hover:not(:disabled) { filter: brightness(0.9); }
      button:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
      button:disabled { cursor: wait; opacity: 0.55; }
      @media (max-width: 640px) {
        .bar { gap: 8px; padding-inline: 8px; }
        .remaining { display: none; }
        button { padding-inline: 10px; }
      }
    `;

    const bar = createElement("section");
    bar.className = "bar";
    bar.setAttribute("aria-label", "Rhemata discovery review");
    shadow.append(style, bar);
    return bar;
  }

  function setStatus(message, isError) {
    const status = document.getElementById(HOST_ID)?.shadowRoot
      ?.getElementById("rhemata-review-status");
    if (!status) return;
    status.textContent = message;
    status.setAttribute("aria-invalid", String(Boolean(isError)));
  }

  function renderToolbar(candidate) {
    const bar = prepareToolbar();
    const summary = createElement("div");
    summary.className = "summary";

    const name = createElement("strong");
    name.className = "name";
    name.textContent = candidate.name;

    const remaining = createElement("span");
    remaining.className = "remaining";
    remaining.textContent = `${candidate.remaining} left to review`;

    const status = createElement("span");
    status.id = "rhemata-review-status";
    status.className = "status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");

    const actions = createElement("div");
    actions.className = "actions";
    const approve = createElement("button");
    approve.id = "rhemata-review-approve";
    approve.className = "primary";
    approve.type = "button";
    approve.textContent = "Approve";
    const reject = createElement("button");
    reject.id = "rhemata-review-reject";
    reject.type = "button";
    reject.textContent = "Do Not Approve";
    const controls = [approve, reject];

    approve.addEventListener("click", () => decide(TYPES.APPROVE, controls));
    reject.addEventListener("click", () => decide(TYPES.REJECT, controls));
    summary.append(name, remaining, status);
    actions.append(approve, reject);
    bar.append(summary, actions);
  }

  function renderDone() {
    const bar = prepareToolbar();
    const message = createElement("strong", "You're all caught up.");
    message.className = "name";
    const detail = createElement("span", "Nothing left to review right now.");
    detail.className = "remaining";
    bar.append(message, detail);
  }

  function renderError(message) {
    setStatus(message || "The decision could not be saved.", true);
  }

  function renderConnectionError(message) {
    const bar = prepareToolbar();
    const instruction = createElement(
      "strong",
      "Start the Rhemata review server, then retry",
    );
    instruction.className = "name";
    const status = createElement(
      "span",
      message || "The review server is unavailable.",
    );
    status.id = "rhemata-review-status";
    status.className = "status";
    status.setAttribute("role", "status");
    status.setAttribute("aria-invalid", "true");
    const retry = createElement("button", "Retry");
    retry.type = "button";
    retry.addEventListener("click", () => {
      retry.disabled = true;
      boot().catch((error) => {
        retry.disabled = false;
        renderConnectionError(error.message);
      });
    });
    bar.append(instruction, status, retry);
  }

  async function decide(type, controls) {
    controls.forEach((control) => { control.disabled = true; });
    setStatus("Saving decision…", false);
    try {
      const response = await send(type);
      if (response.done) {
        renderDone();
        return;
      }
      location.replace(response.candidate.link);
    } catch (error) {
      controls.forEach((control) => { control.disabled = false; });
      renderError(error.message || "The decision could not be saved.");
    }
  }

  async function boot() {
    const isController = location.origin === "http://127.0.0.1:8765"
      && document.getElementById("review-controller");
    const response = await send(isController ? TYPES.START : TYPES.STATE);
    if (!response.active) return;
    if (response.done) return renderDone();
    if (isController) return location.replace(response.candidate.link);
    renderToolbar(response.candidate);
  }

  boot().catch((error) => {
    if (location.origin === "http://127.0.0.1:8765") {
      console.error("Rhemata review extension:", error);
      return;
    }
    renderConnectionError(error.message || "The review server is unavailable.");
  });
})();
