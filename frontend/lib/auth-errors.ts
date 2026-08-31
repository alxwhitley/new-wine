/**
 * Supabase returns operator-facing strings ("Invalid login credentials").
 * Shipping them verbatim is how a lay reader ends up staring at system
 * language with no next step. This maps them to the product's own voice.
 */
export type AuthMode = "signin" | "signup";

export type AuthErrorCopy = {
  message: string;
  /** True when the fastest recovery is switching to the other mode. */
  suggestSignIn?: boolean;
};

const FALLBACK = "Something went wrong. Try again.";

export function humanizeAuthError(raw: unknown, mode: AuthMode): AuthErrorCopy {
  const text = raw instanceof Error ? raw.message : typeof raw === "string" ? raw : "";
  const t = text.toLowerCase();

  // Deliberately NOT attributed to the email or the password field. Supabase
  // withholds which one was wrong so an attacker cannot enumerate accounts;
  // pointing at a field here would give that away.
  if (t.includes("invalid login credentials")) {
    return { message: "That email and password don't match an account. Check both, or reset your password." };
  }
  if (t.includes("email not confirmed")) {
    return { message: "Confirm your email first — open the link we sent, then sign in." };
  }
  if (t.includes("already registered") || t.includes("already been registered")) {
    return { message: "That email already has an account.", suggestSignIn: true };
  }
  if (t.includes("password should be at least")) {
    return { message: "Passwords need at least 6 characters." };
  }
  if (t.includes("unable to validate email") || t.includes("invalid email")) {
    return { message: "That doesn't look like an email address." };
  }
  if (t.includes("rate limit") || t.includes("too many requests")) {
    return { message: "Too many attempts. Wait a minute, then try again." };
  }
  if (t.includes("failed to fetch") || t.includes("networkerror") || t.includes("network request failed")) {
    return { message: "Couldn't reach New Wine. Check your connection and try again." };
  }
  if (!text) {
    return { message: FALLBACK };
  }
  return { message: mode === "signup" ? "Couldn't create that account. Try again." : FALLBACK };
}
