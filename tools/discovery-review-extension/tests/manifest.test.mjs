import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

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

test("content script is limited to top-level HTTP and HTTPS documents", () => {
  assert.deepEqual(manifest.content_scripts, [{
    matches: ["http://*/*", "https://*/*"],
    js: ["content.js"],
    run_at: "document_idle",
    all_frames: false,
  }]);
});

class FakeElement {
  constructor(tagName, environment) {
    this.tagName = tagName;
    this.environment = environment;
    this.children = [];
    this.parentElement = null;
    this.shadowRoot = null;
    this.textContent = "";
    this.listeners = {};
  }

  append(...children) {
    for (const child of children) child.parentElement = this;
    this.children.push(...children);
  }
  replaceChildren(...children) {
    for (const child of children) child.parentElement = this;
    this.children = children;
  }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  attachShadow({mode}) {
    const root = new FakeElement("#shadow-root", this.environment);
    root.getElementById = (id) => findById(root, id);
    this.environment.shadowRoots.push(root);
    this.environment.shadowModes.push(mode);
    if (mode === "open") this.shadowRoot = root;
    return root;
  }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children
      .filter((child) => child !== this);
    this.parentElement = null;
  }
}

function findById(root, id) {
  if (root.id === id) return root;
  for (const child of root.children) {
    const found = findById(child, id);
    if (found) return found;
  }
  return null;
}

function visibleText(root) {
  return [root.textContent, ...root.children.map(visibleText)].join(" ");
}

async function runContent({
  controller = false,
  origin,
  response,
  responses,
  runtimeError,
  hostCollision = false,
}) {
  const environment = {
    messages: [],
    runtimeListeners: [],
    shadowModes: [],
    shadowRoots: [],
  };
  const responseQueue = responses ? [...responses] : [response];
  const documentElement = new FakeElement("html", environment);
  if (controller) {
    const marker = new FakeElement("section", environment);
    marker.id = "review-controller";
    documentElement.append(marker);
  }
  if (hostCollision) {
    const collision = new FakeElement("main", environment);
    collision.id = "newwine-discovery-review-host";
    collision.textContent = "Host page content";
    documentElement.append(collision);
  }
  const document = {
    documentElement,
    createElement: (tagName) => new FakeElement(tagName, environment),
    getElementById: (id) => findById(documentElement, id),
  };
  const location = {
    origin,
    replacedWith: null,
    replace(value) { this.replacedWith = value; },
  };
  const chrome = {
    runtime: {
      lastError: runtimeError,
      onMessage: {
        addListener(listener) { environment.runtimeListeners.push(listener); },
      },
      sendMessage(message, callback) {
        environment.messages.push(message);
        callback(responseQueue.shift());
      },
    },
  };
  const source = fs.readFileSync(new URL("../content.js", import.meta.url), "utf8");
  vm.runInNewContext(source, {chrome, console: {error() {}}, document, location});
  await new Promise((resolve) => setImmediate(resolve));
  return {document, environment, location};
}

test("tracked localhost candidate gets Retry while controller keeps fallback UI", async () => {
  const serverError = {active: true, error: "server unavailable"};
  const candidateRun = await runContent({
    origin: "http://127.0.0.1:8765",
    response: serverError,
  });
  const candidate = candidateRun.document;
  const host = candidate.getElementById("newwine-discovery-review-host");
  assert.ok(host);
  assert.match(
    visibleText(candidateRun.environment.shadowRoots[0]),
    /Start the New Wine review server, then retry/,
  );
  assert.match(visibleText(candidateRun.environment.shadowRoots[0]), /Retry/);

  const controllerRun = await runContent({
    controller: true,
    origin: "http://127.0.0.1:8765",
    response: serverError,
  });
  const controller = controllerRun.document;
  assert.equal(controller.getElementById("newwine-discovery-review-host"), null);
});

test("runtime transport failure cannot add DOM before tracked status is known", async () => {
  const {document} = await runContent({
    origin: "https://inactive.example",
    runtimeError: {message: "extension context invalidated"},
  });
  assert.equal(document.getElementById("newwine-discovery-review-host"), null);
});

test("inactive response does not remove a host-page element with the reserved ID", async () => {
  const {document} = await runContent({
    hostCollision: true,
    origin: "https://inactive.example",
    response: {active: false},
  });
  assert.equal(
    document.getElementById("newwine-discovery-review-host").textContent,
    "Host page content",
  );
});

test("toolbar uses a closed shadow root inaccessible to host-page JavaScript", async () => {
  const run = await runContent({
    origin: "https://candidate.example",
    response: {
      active: true,
      done: false,
      candidate: {
        name: "Candidate",
        link: "https://candidate.example",
        remaining: 1,
      },
    },
  });
  const host = run.document.getElementById("newwine-discovery-review-host");
  assert.ok(host);
  assert.equal(host.shadowRoot, null);
  assert.deepEqual(run.environment.shadowModes, ["closed"]);
});

test("synthetic candidate-page clicks cannot submit a decision", async () => {
  const run = await runContent({
    origin: "https://candidate.example",
    responses: [
      {
        active: true,
        done: false,
        candidate: {
          name: "Candidate",
          link: "https://candidate.example",
          remaining: 1,
        },
      },
      {active: true, done: true, candidate: null},
    ],
  });
  const approve = findById(
    run.environment.shadowRoots[0],
    "newwine-review-approve",
  );
  await approve.listeners.click({isTrusted: false});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(run.environment.messages.length, 1);
  assert.equal(run.environment.messages[0].type, "GET_REVIEW_STATE");
});

test("an active-false operation removes the old toolbar", async () => {
  const run = await runContent({
    origin: "https://candidate.example",
    responses: [
      {
        active: true,
        done: false,
        candidate: {
          name: "Candidate",
          link: "https://candidate.example",
          remaining: 1,
        },
      },
      {active: false},
    ],
  });
  const approve = findById(
    run.environment.shadowRoots[0],
    "newwine-review-approve",
  );
  await approve.listeners.click({isTrusted: true});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(
    run.document.getElementById("newwine-discovery-review-host"),
    null,
  );
  assert.equal(run.location.replacedWith, null);
});

test("worker deactivation message promptly removes the old toolbar", async () => {
  const run = await runContent({
    origin: "https://candidate.example",
    response: {
      active: true,
      done: false,
      candidate: {
        name: "Candidate",
        link: "https://candidate.example",
        remaining: 1,
      },
    },
  });
  assert.equal(run.environment.runtimeListeners.length, 1);
  run.environment.runtimeListeners[0]({type: "DEACTIVATE_REVIEW"});
  assert.equal(
    run.document.getElementById("newwine-discovery-review-host"),
    null,
  );
});
