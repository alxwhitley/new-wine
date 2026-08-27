# Discovery Review Browser Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Alex approve or reject each Discovery candidate from a fixed bar on the candidate website, then navigate the same tab to the next candidate.

**Architecture:** The existing loopback-only FastAPI review server remains the sole owner of TSV reads and writes. A Manifest V3 extension injects a Shadow DOM toolbar into one tracked review tab; its service worker sends a fixed message protocol to fixed localhost endpoints and returns the next server-selected candidate after each decision.

**Tech Stack:** Python 3.12, FastAPI, existing escaped-TSV helpers, Chrome Manifest V3, vanilla JavaScript ES modules, `chrome.storage.session`, Node's built-in test runner, Playwright browser verification.

**Spec:** `docs/superpowers/specs/2026-08-27-discovery-review-browser-extension-design.md`

## Global Constraints

- Read `AGENTS.md`, `PLAN.md`, the spec above, and CLAUDE.md Invariant 16 plus the master-ingestion-queue Landmine before editing.
- Do not stage, rewrite, or discard Alex's current changes in `docs/ingestion/master_ingestion_queue_discovery.tsv`.
- Preserve the uncommitted controller work already present in `scripts/review_discovery_candidates.py` and `scripts/test_review_discovery_candidates.py`; Task 1 incorporates it into the build commit.
- `scripts/ingestion_sheet_io.py` remains the only TSV encoder and writer.
- Extension decisions never call the database, `site_ingest_crawler.py`, or any ingestion worker.
- The server selects the current candidate from a fresh TSV read; extension messages never choose a candidate name or URL.
- The extension service worker fetches only `http://127.0.0.1:8765/api/review/*`.
- Candidate strings enter the toolbar through `textContent`, never untrusted `innerHTML`.
- The extension requests no cookies, history, downloads, web-request interception, or production-host permissions.
- Build commits and docs/records commits stay separate.
- All browser tests use throwaway TSV fixtures and local fake candidate pages.

## File Structure

- `scripts/review_discovery_candidates.py` — canonical review selection, TSV decisions, fallback controller, and fixed extension JSON API.
- `scripts/test_review_discovery_candidates.py` — Python behavior and API tests against temporary TSV files.
- `tools/discovery-review-extension/manifest.json` — Manifest V3 permissions and entry points.
- `tools/discovery-review-extension/review-service.mjs` — pure fixed-message protocol and active-tab policy.
- `tools/discovery-review-extension/service-worker.mjs` — Chrome API and fixed localhost-fetch adapter.
- `tools/discovery-review-extension/content.js` — controller handshake, Shadow DOM toolbar, decisions, and same-tab navigation.
- `tools/discovery-review-extension/tests/review-service.test.mjs` — Node tests for message validation, active-tab enforcement, and fixed API paths.
- `tools/discovery-review-extension/tests/manifest.test.mjs` — Node tests for the exact permission boundary.
- `tools/discovery-review-extension/README.md` — unpacked-install and operating instructions.
- `CLAUDE.md` — durable landmine entry describing the local extension and its non-database boundary.

---

### Task 1: Add the server-selected extension review API

**Files:**
- Modify: `scripts/review_discovery_candidates.py:235-485`
- Modify: `scripts/test_review_discovery_candidates.py:221-335`

**Interfaces:**
- Consumes: existing `next_candidate()`, `approve_candidate(name, link)`, and `reject_candidate(name)`.
- Produces: `current_review_payload() -> dict`, `decide_current_and_advance(action: str) -> dict`, `GET /api/review/current`, `POST /api/review/start`, and `POST /api/review/decision`.

- [ ] **Step 1: Add failing tests for server-selected identity and terminal behavior**

Append a new temporary-file test block to `scripts/test_review_discovery_candidates.py`. Use the existing `_build_test_files`, `TestClient`, `check`, and path-restoration pattern. The fixtures must contain `API First` followed by `API Second`.

```python
api_current = client.get("/api/review/current")
check(
    "extension current endpoint returns the first fresh candidate",
    api_current.status_code == 200
    and api_current.json() == {
        "done": False,
        "candidate": {
            "name": "API First",
            "link": "https://api-first.example.com",
            "remaining": 2,
        },
    },
)

before_start_discovery = tool.DISCOVERY_PATH.read_bytes()
before_start_approved = tool.APPROVED_PATH.read_bytes()
api_start = client.post("/api/review/start")
check(
    "extension start is read-only and returns the same candidate",
    api_start.status_code == 200
    and api_start.json() == api_current.json()
    and tool.DISCOVERY_PATH.read_bytes() == before_start_discovery
    and tool.APPROVED_PATH.read_bytes() == before_start_approved,
)

spoofed_approve = client.post(
    "/api/review/decision",
    data={
        "action": "approve",
        "name": "API Second",
        "link": "https://api-second.example.com",
    },
)
check(
    "extension decision ignores caller candidate identity and advances",
    spoofed_approve.status_code == 200
    and spoofed_approve.json()["candidate"]["name"] == "API Second",
)
_, approved_rows = sheet_io.read_tab(tool.APPROVED_PATH)
check(
    "extension approval persists the server-selected first candidate",
    [row["name"] for row in approved_rows] == ["API First"],
)

api_done = client.post(
    "/api/review/decision", data={"action": "reject"}
)
check(
    "extension final decision returns terminal state",
    api_done.status_code == 200
    and api_done.json() == {"done": True, "candidate": None},
)
```

Add a separate invalid-action fixture and assert status 400 plus byte-identical Discovery and Approved Sites files before and after:

```python
before_discovery = tool.DISCOVERY_PATH.read_bytes()
before_approved = tool.APPROVED_PATH.read_bytes()
invalid = client.post("/api/review/decision", data={"action": "skip"})
check("extension rejects unknown action", invalid.status_code == 400)
check(
    "unknown extension action changes no TSV bytes",
    tool.DISCOVERY_PATH.read_bytes() == before_discovery
    and tool.APPROVED_PATH.read_bytes() == before_approved,
)
```

At the API boundary, patch only `decide_current_and_advance` to raise the real
`StaleFileError` type and verify that the route preserves the conflict contract:

```python
from unittest.mock import patch

with patch.object(
    tool,
    "decide_current_and_advance",
    side_effect=tool.StaleFileError("Discovery file changed"),
):
    stale = client.post(
        "/api/review/decision", data={"action": "approve"}
    )
check(
    "extension stale-file refusal is a retryable conflict",
    stale.status_code == 409
    and stale.json() == {"error": "Discovery file changed"},
)
```

- [ ] **Step 2: Run the Python review test and verify RED**

Run:

```bash
python3.12 scripts/test_review_discovery_candidates.py
```

Expected: FAIL because `/api/review/current`, `/api/review/start`, and the server-selected decision route do not exist.

- [ ] **Step 3: Implement current payload and server-selected decisions**

Add these functions beside `decide_and_advance`:

```python
def current_review_payload() -> dict:
    found = next_candidate()
    if found is None:
        return {"done": True, "candidate": None}
    row, link, remaining = found
    return {
        "done": False,
        "candidate": {
            "name": row["name"],
            "link": link,
            "remaining": remaining,
        },
    }


def decide_current_and_advance(action: str) -> dict:
    found = next_candidate()
    if found is None:
        return {"done": True, "candidate": None}
    row, link, _remaining = found
    if action == "approve":
        approve_candidate(row["name"], link)
    elif action == "reject":
        reject_candidate(row["name"])
    else:
        raise ValueError(f"Unknown review action: {action!r}")
    return current_review_payload()
```

Keep the existing `decide_and_advance(action, name, link)` for the fallback controller. Do not route extension messages through caller-provided identity.

- [ ] **Step 4: Add fixed JSON routes**

Register these routes after the existing `/decision` fallback route:

```python
@app.get("/api/review/current", response_class=JSONResponse)
def api_review_current() -> JSONResponse:
    return JSONResponse(current_review_payload())


@app.post("/api/review/start", response_class=JSONResponse)
def api_review_start() -> JSONResponse:
    return JSONResponse(current_review_payload())


@app.post("/api/review/decision", response_class=JSONResponse)
def api_review_decision(action: str = Form(...)) -> JSONResponse:
    try:
        result = decide_current_and_advance(action)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(result)
```

- [ ] **Step 5: Run the focused Python tests and verify GREEN**

Run:

```bash
python3.12 scripts/test_review_discovery_candidates.py
python3.12 scripts/test_ingestion_sheet_io.py
python3.12 scripts/test_check_discovery_blog_links.py
```

Expected: every check passes; the blog-link test explicitly reports that its fixtures were used and no real TSV was written.

- [ ] **Step 6: Review and commit the server slice**

Run:

```bash
git diff --check
git diff -- scripts/review_discovery_candidates.py scripts/test_review_discovery_candidates.py
git status --short
```

Confirm that `docs/ingestion/master_ingestion_queue_discovery.tsv` remains unstaged. Then commit only the two code files:

```bash
git add scripts/review_discovery_candidates.py scripts/test_review_discovery_candidates.py
git commit -m "feat: add extension-safe discovery review API"
```

### Task 2: Build the fixed-message extension service

**Files:**
- Create: `tools/discovery-review-extension/manifest.json`
- Create: `tools/discovery-review-extension/review-service.mjs`
- Create: `tools/discovery-review-extension/service-worker.mjs`
- Create: `tools/discovery-review-extension/tests/review-service.test.mjs`
- Create: `tools/discovery-review-extension/tests/manifest.test.mjs`

**Interfaces:**
- Consumes: fixed server routes from Task 1.
- Produces: `MESSAGE_TYPES`, `createReviewService({request, sessionStore})`, and a Manifest V3 service worker that bridges Chrome messages to the pure service.

- [ ] **Step 1: Write failing protocol tests**

Create `tools/discovery-review-extension/tests/review-service.test.mjs` with Node's built-in test runner. The request fake records `{path, options}`; the session fake stores one `activeReviewTabId` value.

```javascript
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
      return responses.shift();
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
```

- [ ] **Step 2: Write a failing manifest-permission test**

Create `tools/discovery-review-extension/tests/manifest.test.mjs`:

```javascript
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const manifest = JSON.parse(
  fs.readFileSync(new URL("../manifest.json", import.meta.url), "utf8"),
);

test("manifest is MV3 with the narrow non-page permission set", () => {
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ["storage"]);
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:8765/*"]);
  assert.equal(manifest.background.service_worker, "service-worker.mjs");
  assert.equal(manifest.background.type, "module");
});

test("manifest contains no sensitive extension capabilities", () => {
  const forbidden = ["cookies", "history", "downloads", "webRequest", "tabs"];
  assert.deepEqual(
    forbidden.filter((permission) => manifest.permissions.includes(permission)),
    [],
  );
});
```

- [ ] **Step 3: Run Node tests and verify RED**

Run:

```bash
node --test tools/discovery-review-extension/tests/*.test.mjs
```

Expected: FAIL because the extension files do not exist.

- [ ] **Step 4: Implement the pure fixed-message service**

Create `review-service.mjs` with this public shape:

```javascript
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
```

- [ ] **Step 5: Implement the Chrome adapter and manifest**

Create `manifest.json` without a content script yet:

```json
{
  "manifest_version": 3,
  "name": "Rhemata Discovery Review",
  "version": "1.0.0",
  "description": "Review Rhemata ingestion candidates from their websites.",
  "permissions": ["storage"],
  "host_permissions": ["http://127.0.0.1:8765/*"],
  "background": {
    "service_worker": "service-worker.mjs",
    "type": "module"
  }
}
```

Create `service-worker.mjs`. The request adapter must prepend the constant base URL, send form content type only when a body exists, reject non-JSON or non-2xx responses, and never accept a URL from a message:

```javascript
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
```

- [ ] **Step 6: Run Node tests and verify GREEN**

Run:

```bash
node --test tools/discovery-review-extension/tests/*.test.mjs
```

Expected: all tests pass.

- [ ] **Step 7: Review and commit the service slice**

Run `git diff --check` and inspect the manifest permissions plus every string passed to `request()`. Confirm no arbitrary URL fetch exists. Commit only the extension service files and tests:

```bash
git add tools/discovery-review-extension/manifest.json \
  tools/discovery-review-extension/review-service.mjs \
  tools/discovery-review-extension/service-worker.mjs \
  tools/discovery-review-extension/tests/review-service.test.mjs \
  tools/discovery-review-extension/tests/manifest.test.mjs
git commit -m "feat: add fixed discovery review extension protocol"
```

### Task 3: Inject the in-page toolbar and advance the same tab

**Files:**
- Modify: `tools/discovery-review-extension/manifest.json`
- Create: `tools/discovery-review-extension/content.js`
- Modify: `tools/discovery-review-extension/tests/manifest.test.mjs`

**Interfaces:**
- Consumes: Task 2 message enum strings and response shapes.
- Produces: controller auto-start, active-tab-only Shadow DOM toolbar, decision submission, error recovery, and same-tab navigation.

- [ ] **Step 1: Extend the manifest test and verify RED**

Add this test:

```javascript
test("content script is limited to top-level HTTP and HTTPS documents", () => {
  assert.deepEqual(manifest.content_scripts, [{
    matches: ["http://*/*", "https://*/*"],
    js: ["content.js"],
    run_at: "document_idle",
    all_frames: false,
  }]);
});
```

Run:

```bash
node --test tools/discovery-review-extension/tests/*.test.mjs
```

Expected: FAIL because `content_scripts` is absent.

- [ ] **Step 2: Register the content script**

Add this exact block to `manifest.json`:

```json
"content_scripts": [
  {
    "matches": ["http://*/*", "https://*/*"],
    "js": ["content.js"],
    "run_at": "document_idle",
    "all_frames": false
  }
]
```

- [ ] **Step 3: Implement controller handshake and inactive-tab refusal**

Create `content.js` as an IIFE. Define the same four message strings locally; content scripts cannot import the service-worker module directly.

```javascript
(() => {
  "use strict";
  const TYPES = Object.freeze({
    START: "START_REVIEW",
    STATE: "GET_REVIEW_STATE",
    APPROVE: "DECIDE_APPROVE",
    REJECT: "DECIDE_REJECT",
  });

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
```

Do not add any DOM on inactive tabs.

- [ ] **Step 4: Implement the Shadow DOM toolbar**

Inside the IIFE, add `renderToolbar(candidate)`, `renderDone()`, `renderError(message)`, and `renderConnectionError(message)`. Use one host ID (`rhemata-discovery-review-host`), `attachShadow({mode: "open"})`, a fixed bottom position, and DOM creation APIs. Candidate name and remaining count must be assigned through `textContent`.

The toolbar must contain these stable controls for browser verification:

```javascript
approve.id = "rhemata-review-approve";
approve.textContent = "Approve";
reject.id = "rhemata-review-reject";
reject.textContent = "Do Not Approve";
status.id = "rhemata-review-status";
```

Use a `<style>` element inside the shadow root with a 64-pixel fixed bar,
high-contrast buttons, a remaining-count label, and `z-index: 2147483647`.
Do not inspect or copy host-page content.

`renderConnectionError` uses the same Shadow DOM host, displays “Start the
Rhemata review server, then retry,” and provides a **Retry** button. Retry calls
`boot()`; it does not navigate or submit a decision. This recovery bar appears
only when `GET_REVIEW_STATE` failed for the session's tracked tab. The local
controller page keeps its existing fallback UI instead of replacing it with an
extension error bar.

- [ ] **Step 5: Implement decision and navigation behavior**

Both click handlers must call one function:

```javascript
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
    setStatus(error.message || "The decision could not be saved.", true);
  }
}
```

Approve sends only `DECIDE_APPROVE`; reject sends only `DECIDE_REJECT`. Neither message includes page URL, candidate name, page text, or arbitrary request data.

- [ ] **Step 6: Run unit and Python suites**

Run:

```bash
node --test tools/discovery-review-extension/tests/*.test.mjs
python3.12 scripts/test_review_discovery_candidates.py
python3.12 scripts/test_ingestion_sheet_io.py
```

Expected: all tests pass.

- [ ] **Step 7: Run a real extension browser proof with throwaway data**

Create a temporary FastAPI wrapper under `/tmp` that imports the real app,
replaces `DISCOVERY_PATH` and `APPROVED_PATH` with `tempfile.mkdtemp()` TSV
fixtures, and serves two fake sites at
`http://127.0.0.1:8765/fake/first` and `/fake/second`. Do not point the wrapper
at `docs/ingestion/`. Wrap the real `decide_current_and_advance` so its first
call raises `StaleFileError("simulated concurrent edit")`; on later calls,
sleep 500 milliseconds before delegating to the real function. This makes the
browser proof exercise visible error recovery and the pending-control state
without changing production code.

Use Playwright with Chromium persistent context and the unpacked extension:

```javascript
const extensionPath = "/Users/alexwhitley/rhemata/tools/discovery-review-extension";
const context = await chromium.launchPersistentContext("", {
  headless: false,
  args: [
    `--disable-extensions-except=${extensionPath}`,
    `--load-extension=${extensionPath}`,
  ],
});
```

Verify these conditions, waiting on URLs and selectors rather than fixed sleeps:

```javascript
const pages = context.pages();
const page = pages[0] || await context.newPage();
await page.goto("http://127.0.0.1:8765/");
await page.waitForURL("**/fake/first");
const firstHost = page.locator("#rhemata-discovery-review-host");
const inactive = await context.newPage();
await inactive.goto("http://127.0.0.1:8765/fake/unrelated");
if (await inactive.locator("#rhemata-discovery-review-host").count()) {
  throw new Error("Toolbar appeared in a non-review tab");
}

const approve = firstHost.locator("#rhemata-review-approve");
await approve.click();
await firstHost.getByText("simulated concurrent edit").waitFor();
if (!page.url().endsWith("/fake/first") || await approve.isDisabled()) {
  throw new Error("Failed decision advanced or left controls disabled");
}

await approve.click();
if (!(await approve.isDisabled())) {
  throw new Error("Approve remained enabled while the decision was pending");
}
await page.waitForURL("**/fake/second");
await page.locator("#rhemata-discovery-review-host")
  .locator("#rhemata-review-reject").click();
await page.getByText("You're all caught up.").waitFor();
const reviewPages = context.pages().filter((item) => !item.isClosed() && item !== inactive);
if (reviewPages.length !== 1) {
  throw new Error("Review flow opened an additional candidate tab");
}
```

After the browser closes, read the temporary TSVs and assert that candidate one is approved, candidate two is rejected, and no real ingestion file changed.

- [ ] **Step 8: Review and commit the toolbar slice**

Inspect `content.js` for `innerHTML`, page-content reads, arbitrary message fields, and navigation other than the server-returned candidate link. Commit only the toolbar files:

```bash
git add tools/discovery-review-extension/manifest.json \
  tools/discovery-review-extension/content.js \
  tools/discovery-review-extension/tests/manifest.test.mjs
git commit -m "feat: review discovery sites from an in-page toolbar"
```

### Task 4: Document installation and the durable boundary

**Files:**
- Create: `tools/discovery-review-extension/README.md`
- Modify: `CLAUDE.md:987-1045`

**Interfaces:**
- Consumes: the completed extension behavior from Tasks 1-3.
- Produces: user installation/runbook and durable repository knowledge for future agents.

- [ ] **Step 1: Write the extension README**

Document these exact operating steps:

```markdown
# Rhemata Discovery Review Extension

## Install once

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `~/rhemata/tools/discovery-review-extension/`.

## Review candidates

```bash
cd ~/rhemata
python3.12 scripts/review_discovery_candidates.py
```

The first eligible website replaces the local controller tab. Use **Approve**
or **Do Not Approve** in the bottom bar; the same tab advances after each saved
decision.

## Stop

Stop the Python process with `Ctrl-C`. Disable or remove the unpacked extension
from `chrome://extensions` when the review session is finished.

## Safety boundary

The extension writes only through the loopback review server into the tracked
Discovery and Approved Sites TSV files. It never runs ingestion or writes to
the production database.
```

Add this troubleshooting section verbatim, adjusting only Markdown line wraps:

```markdown
## Troubleshooting

- **Server unavailable:** return to Terminal, start the command above, then use
  **Retry** in the bottom bar.
- **Toolbar absent after reloading the extension:** reopen
  `http://127.0.0.1:8765/` to start a fresh tracked review tab.
- **File changed while reviewing:** another process edited an ingestion TSV.
  Reload the review session before deciding so the tool does not overwrite it.
- **Candidate page will not load:** reopen `http://127.0.0.1:8765/` and use the
  fallback controller for that decision.
```

- [ ] **Step 2: Update the master-ingestion-queue Landmine**

In CLAUDE.md's tracked master spreadsheet Landmine, add this paragraph:

```markdown
**2026-08-27: local in-page Discovery review extension.**
`tools/discovery-review-extension/` is an unpacked Manifest V3 extension that
requests content-script access on HTTP/HTTPS pages so it can show a bottom
Approve / Do Not Approve bar, but displays that bar only in the one tab that
started a local review session. Its service worker can call only the fixed
`http://127.0.0.1:8765/api/review/*` contract. The server re-reads and selects
the current candidate at decision time; the page and extension never choose a
row identity. Decisions reuse `review_discovery_candidates.py` and
`ingestion_sheet_io.py` to update only the Discovery and Approved Sites TSVs.
The extension has no database or ingestion authority. The fallback remains
`python3.12 scripts/review_discovery_candidates.py` and its local controller.
```

Do not change Invariant 16's production-write authorization.

- [ ] **Step 3: Run the full coherent verification batch**

Run:

```bash
git diff --check
python3.12 scripts/test_review_discovery_candidates.py
python3.12 scripts/test_ingestion_sheet_io.py
python3.12 scripts/test_check_discovery_blog_links.py
node --test tools/discovery-review-extension/tests/*.test.mjs
```

Repeat the Task 3 Playwright extension proof after any documentation-triggered code correction. Otherwise reference the fresh passing proof from Task 3.

- [ ] **Step 4: Confirm preservation and scope**

Run:

```bash
git status --short
git diff -- docs/ingestion/master_ingestion_queue_discovery.tsv
git diff -- docs/ingestion/master_ingestion_queue_approved_sites.tsv
```

Confirm Alex's Discovery changes are still present and unstaged. Confirm this feature created no migration, database script, crawler invocation, production log, or ingestion artifact.

- [ ] **Step 5: Commit documentation separately**

```bash
git add tools/discovery-review-extension/README.md CLAUDE.md
git commit -m "docs: document discovery review extension"
```

The staged diff must contain only the README and CLAUDE.md.

## Completion Checkpoint

- [ ] The extension loads unpacked without a manifest error.
- [ ] The Python, Node, and browser verification batches pass.
- [ ] One approval and one rejection persist in temporary TSV fixtures.
- [ ] The same browser tab advances between candidates.
- [ ] Non-review tabs receive no visible toolbar.
- [ ] Invalid messages and inactive tabs cannot submit decisions.
- [ ] Service-worker fetches are fixed to loopback review endpoints.
- [ ] Real ingestion TSV decisions are preserved.
- [ ] No production database or ingestion operation ran.
- [ ] Build and docs commits remain separate.
