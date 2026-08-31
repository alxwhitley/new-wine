import assert from "node:assert/strict";
import test from "node:test";

import {
  BETA_ACCESS_CODE,
  BETA_ACCESS_STORAGE_KEY,
  LEGACY_SESSION_KEY,
  type BetaAccessStores,
  grantBetaAccess,
  hasBetaAccess,
  isBetaCodeValid,
} from "./beta-access.ts";

function memoryStores(seed: Record<string, string> = {}): BetaAccessStores & { dump: () => Record<string, string> } {
  const local = new Map(Object.entries(seed));
  const session = new Map(Object.entries(seed));
  return {
    local: {
      getItem: (k) => local.get(k) ?? null,
      setItem: (k, v) => { local.set(k, v); },
    },
    session: { getItem: (k) => session.get(k) ?? null },
    dump: () => Object.fromEntries(local),
  };
}

function throwingStores(): BetaAccessStores {
  return {
    local: {
      getItem: () => { throw new Error("private mode"); },
      setItem: () => { throw new Error("private mode"); },
    },
    session: { getItem: () => { throw new Error("private mode"); } },
  };
}

// Regression guard. The rename sweep in a6f1575 rewrote this literal to
// "newwine" and shipped it, locking every beta tester out until 5473265.
// A future name sweep must fail here, loudly, instead of in production.
test("the beta access code is exactly 'rhema'", () => {
  assert.equal(BETA_ACCESS_CODE, "rhema");
  assert.ok(isBetaCodeValid("rhema"));
});

test("accepts a code shared verbally, with stray whitespace or casing", () => {
  assert.ok(isBetaCodeValid("  rhema  "));
  assert.ok(isBetaCodeValid("Rhema"));
  assert.ok(isBetaCodeValid("RHEMA"));
  assert.ok(isBetaCodeValid("\tRhEmA\n"));
});

test("rejects anything that is not the code", () => {
  assert.equal(isBetaCodeValid(""), false);
  assert.equal(isBetaCodeValid("   "), false);
  assert.equal(isBetaCodeValid("newwine"), false);
  assert.equal(isBetaCodeValid("rhemata"), false);
  assert.equal(isBetaCodeValid("rhem"), false);
  assert.equal(isBetaCodeValid("rhe ma"), false);
});

test("a fresh device has no access until it is granted", () => {
  const stores = memoryStores();
  assert.equal(hasBetaAccess(stores), false);
  grantBetaAccess(stores);
  assert.equal(hasBetaAccess(stores), true);
  assert.equal(stores.dump()[BETA_ACCESS_STORAGE_KEY], "1");
});

test("a session gated under the old per-tab key keeps access and is upgraded in place", () => {
  const stores = memoryStores();
  stores.session = { getItem: (k) => (k === LEGACY_SESSION_KEY ? "1" : null) };

  assert.equal(hasBetaAccess(stores), true, "legacy per-tab access should still count");
  assert.equal(
    stores.dump()[BETA_ACCESS_STORAGE_KEY],
    "1",
    "legacy access should migrate to the per-device key so nobody is re-prompted",
  );
});

test("an unrelated stored value does not grant access", () => {
  const stores = memoryStores({ [BETA_ACCESS_STORAGE_KEY]: "0" });
  assert.equal(hasBetaAccess(stores), false);
});

test("storage that throws degrades to re-prompting instead of crashing", () => {
  const stores = throwingStores();
  assert.equal(hasBetaAccess(stores), false);
  assert.doesNotThrow(() => grantBetaAccess(stores));
  assert.equal(hasBetaAccess(stores), false);
});

test("server-side rendering has no storage and never crashes", () => {
  const stores: BetaAccessStores = { local: null, session: null };
  assert.equal(hasBetaAccess(stores), false);
  assert.doesNotThrow(() => grantBetaAccess(stores));
});
