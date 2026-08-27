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
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.shadowRoot = null;
    this.textContent = "";
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, listener) { this[`on${name}`] = listener; }
  attachShadow() {
    this.shadowRoot = new FakeElement("#shadow-root");
    this.shadowRoot.getElementById = (id) => findById(this.shadowRoot, id);
    return this.shadowRoot;
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

async function runContent({controller = false, origin, response, runtimeError}) {
  const documentElement = new FakeElement("html");
  if (controller) {
    const marker = new FakeElement("section");
    marker.id = "review-controller";
    documentElement.append(marker);
  }
  const document = {
    documentElement,
    createElement: (tagName) => new FakeElement(tagName),
    getElementById: (id) => findById(documentElement, id),
  };
  const location = {origin, replace() {}};
  const chrome = {
    runtime: {
      lastError: runtimeError,
      sendMessage(_message, callback) { callback(response); },
    },
  };
  const source = fs.readFileSync(new URL("../content.js", import.meta.url), "utf8");
  vm.runInNewContext(source, {chrome, console: {error() {}}, document, location});
  await new Promise((resolve) => setImmediate(resolve));
  return document;
}

test("tracked localhost candidate gets Retry while controller keeps fallback UI", async () => {
  const serverError = {active: true, error: "server unavailable"};
  const candidate = await runContent({
    origin: "http://127.0.0.1:8765",
    response: serverError,
  });
  const host = candidate.getElementById("rhemata-discovery-review-host");
  assert.ok(host);
  assert.match(visibleText(host.shadowRoot), /Start the Rhemata review server, then retry/);
  assert.match(visibleText(host.shadowRoot), /Retry/);

  const controller = await runContent({
    controller: true,
    origin: "http://127.0.0.1:8765",
    response: serverError,
  });
  assert.equal(controller.getElementById("rhemata-discovery-review-host"), null);
});

test("runtime transport failure cannot add DOM before tracked status is known", async () => {
  const document = await runContent({
    origin: "https://inactive.example",
    runtimeError: {message: "extension context invalidated"},
  });
  assert.equal(document.getElementById("rhemata-discovery-review-host"), null);
});
