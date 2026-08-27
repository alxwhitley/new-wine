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
