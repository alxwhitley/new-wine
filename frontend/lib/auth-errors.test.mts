import assert from "node:assert/strict";
import test from "node:test";

import { humanizeAuthError } from "./auth-errors.ts";

test("never leaks a raw Supabase string to the reader", () => {
  const raws = [
    "Invalid login credentials",
    "Email not confirmed",
    "User already registered",
    "Password should be at least 6 characters",
    "Unable to validate email address: invalid format",
    "Request rate limit reached",
  ];
  for (const raw of raws) {
    const { message } = humanizeAuthError(new Error(raw), "signin");
    assert.notEqual(message, raw, `${raw} reached the user unchanged`);
    assert.match(message, /[a-z]/, "message should be real prose");
  }
});

test("does not attribute a credential failure to a specific field", () => {
  const { message } = humanizeAuthError(new Error("Invalid login credentials"), "signin");
  // Naming the offending field would let someone enumerate which emails exist.
  assert.ok(message.includes("email and password"), "should stay ambiguous across both fields");
});

test("an existing account offers the switch to sign in", () => {
  const copy = humanizeAuthError(new Error("User already registered"), "signup");
  assert.equal(copy.suggestSignIn, true);
  assert.match(copy.message, /already has an account/);
});

test("a credential failure does not offer the sign-in switch", () => {
  const copy = humanizeAuthError(new Error("Invalid login credentials"), "signin");
  assert.equal(copy.suggestSignIn, undefined);
});

test("network failure names the recovery, not the exception", () => {
  const { message } = humanizeAuthError(new Error("Failed to fetch"), "signin");
  assert.match(message, /connection/);
});

test("unknown and empty errors still produce a usable message", () => {
  assert.equal(humanizeAuthError(new Error(""), "signin").message, "Something went wrong. Try again.");
  assert.equal(humanizeAuthError(undefined, "signin").message, "Something went wrong. Try again.");
  assert.match(humanizeAuthError(new Error("kaboom"), "signup").message, /Couldn't create that account/);
});

test("accepts a bare string as well as an Error", () => {
  assert.match(humanizeAuthError("Email not confirmed", "signin").message, /Confirm your email/);
});
