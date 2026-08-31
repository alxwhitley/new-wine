"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createBrowserClient } from "@supabase/auth-helpers-nextjs";
import { grantBetaAccess, hasBetaAccess, isBetaCodeValid } from "@/lib/beta-access";
import { type AuthErrorCopy, type AuthMode, humanizeAuthError } from "@/lib/auth-errors";

/**
 * One card, never replaced.
 *
 * The frame — position, width, border, background — is stable from first
 * paint to close; everything that changes, changes inside it, adjacent to the
 * control that caused it. That is the whole fix: the previous design swapped
 * two visually identical modals and moved its only mode signal to the
 * opposite end of the card from the link that triggered it, so neither
 * transition was perceptible. The access code is a field here, not a second
 * modal, and it is asked for once per device.
 */

const CONFIRM_DWELL_MS = 1100;

type Mode = AuthMode | "forgot";
type Status = "form" | "signed-in" | "check-email" | "reset-sent";

const FIELD =
  "w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground " +
  "placeholder:text-muted-foreground outline-none transition-colors " +
  "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface LoginModalProps {
  onClose: () => void;
  onSignIn: (email: string, password: string) => Promise<void>;
  onSignUp: (email: string, password: string) => Promise<{ hasSession: boolean }>;
  reason?: string;
  initialMode?: AuthMode;
}

export default function LoginModal({
  onClose,
  onSignIn,
  onSignUp,
  reason,
  initialMode,
}: LoginModalProps) {
  const [mode, setMode] = useState<Mode>(initialMode ?? "signin");
  const [status, setStatus] = useState<Status>("form");

  // Resolved once, on mount. It deliberately does NOT flip to false the moment
  // a valid code is accepted: removing the field mid-form would shift the
  // layout under someone who is still fixing a password. It is simply gone the
  // next time the card opens.
  const [needsCode, setNeedsCode] = useState(false);
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<AuthErrorCopy | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [signedInEmail, setSignedInEmail] = useState("");
  const [announcement, setAnnouncement] = useState("");

  const [resetEmail, setResetEmail] = useState("");
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const titleId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const successCloseRef = useRef(false);

  // Pages pass an inline arrow function as onClose, so its identity changes on
  // every render. Holding it in a ref keeps the confirmation timer from being
  // torn down and restarted forever, which would mean it never fires.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  const isDirty = code !== "" || email !== "" || password !== "" || resetEmail !== "";

  useEffect(() => {
    setNeedsCode(!hasBetaAccess());
  }, []);

  // Focus management: remember where focus came from, put it somewhere useful
  // on open, and give it back on close. After a successful sign-in it goes to
  // the main content instead of the trigger, because the trigger is about to
  // stop saying "Sign in".
  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    return () => {
      if (successCloseRef.current) {
        const main = document.querySelector("main");
        if (main) {
          main.setAttribute("tabindex", "-1");
          main.focus();
          return;
        }
      }
      restoreRef.current?.focus?.();
    };
  }, []);

  useEffect(() => {
    const target = needsCode ? codeRef.current : emailRef.current;
    target?.focus();
  }, [needsCode]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCloseRef.current();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (status !== "signed-in") return;
    const timer = setTimeout(() => {
      successCloseRef.current = true;
      onCloseRef.current();
    }, CONFIRM_DWELL_MS);
    return () => clearTimeout(timer);
  }, [status]);

  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== "Tab") return;
    const root = cardRef.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !root.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const switchMode = useCallback(
    (next: AuthMode) => {
      setMode((current) => {
        if (current === next) return current;
        setPassword("");
        setError(null);
        setAnnouncement(next === "signin" ? "Sign in form" : "Create account form");
        return next;
      });
      requestAnimationFrame(() => {
        if (needsCode && code === "") codeRef.current?.focus();
        else if (email === "") emailRef.current?.focus();
        else passwordRef.current?.focus();
      });
    },
    [needsCode, code, email],
  );

  function onSegmentKeyDown(e: React.KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    switchMode(mode === "signin" ? "signup" : "signin");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // The code is checked locally and first, so a wrong code never costs a
    // network round trip and can never be confused with a wrong password.
    if (needsCode) {
      if (!isBetaCodeValid(code)) {
        setCodeError("That access code isn't right. Check it and try again.");
        codeRef.current?.focus();
        return;
      }
      setCodeError(null);
      grantBetaAccess();
    }

    setSubmitting(true);
    try {
      if (mode === "signin") {
        await onSignIn(email, password);
        setSignedInEmail(email);
        setStatus("signed-in");
      } else {
        const { hasSession } = await onSignUp(email, password);
        if (hasSession) {
          setSignedInEmail(email);
          setStatus("signed-in");
        } else {
          setStatus("check-email");
        }
      }
    } catch (err: unknown) {
      setError(humanizeAuthError(err, mode === "signup" ? "signup" : "signin"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    setResetError(null);
    setResetSubmitting(true);
    try {
      const supabase = createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      );
      const { error: err } = await supabase.auth.resetPasswordForEmail(resetEmail, {
        redirectTo: `${window.location.origin}/auth/callback?next=/auth/update-password`,
      });
      if (err) throw err;
      setStatus("reset-sent");
    } catch (err: unknown) {
      setResetError(humanizeAuthError(err, "signin").message);
    } finally {
      setResetSubmitting(false);
    }
  }

  const heading =
    status === "signed-in"
      ? "You're in"
      : status === "check-email"
        ? "Check your email"
        : status === "reset-sent"
          ? "Check your email"
          : mode === "forgot"
            ? "Reset password"
            : mode === "signin"
              ? "Sign in to New Wine"
              : "Become a test user";

  const subheading =
    mode === "forgot"
      ? "Enter your email and we'll send you a reset link."
      : (reason ?? (mode === "signin" ? "Welcome back." : "Help us build it — create a free account."));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
      onClick={() => {
        // A stray backdrop click must not throw away typed credentials.
        if (!isDirty && status === "form") onClose();
      }}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={trapTab}
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        <span aria-live="polite" className="sr-only">
          {announcement}
        </span>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 id={titleId} className="mb-1 pr-8 font-sans text-xl font-semibold text-foreground">
          {heading}
        </h2>

        {status === "signed-in" ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-background duration-500 animate-in fade-in zoom-in-75 motion-reduce:animate-none">
              <Check className="h-5 w-5" />
            </span>
            <p className="text-sm text-muted-foreground">
              Signed in as <span className="text-foreground">{signedInEmail}</span>
            </p>
          </div>
        ) : status === "check-email" ? (
          <FollowUp
            body="We sent you a confirmation link. Open it, then come back and sign in."
            onBack={() => {
              setStatus("form");
              setMode("signin");
              setError(null);
            }}
          />
        ) : status === "reset-sent" ? (
          <FollowUp
            body="We sent you a reset link. Open it to choose a new password."
            onBack={() => {
              setStatus("form");
              setMode("signin");
              setResetEmail("");
              setResetError(null);
            }}
          />
        ) : mode === "forgot" ? (
          <>
            <p className="mb-6 text-sm text-muted-foreground">{subheading}</p>
            <form onSubmit={handleResetPassword} className="flex flex-col gap-3">
              <input
                type="email"
                name="email"
                autoComplete="email"
                placeholder="Email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                className={FIELD}
              />
              {resetError && <p className="text-sm text-destructive">{resetError}</p>}
              <Button type="submit" disabled={resetSubmitting} className="mt-1 w-full text-background">
                {resetSubmitting ? "Sending…" : "Send reset link"}
              </Button>
              <p className="text-center text-sm">
                <button
                  type="button"
                  onClick={() => {
                    setMode("signin");
                    setResetError(null);
                  }}
                  className="cursor-pointer rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  Back to sign in
                </button>
              </p>
            </form>
          </>
        ) : (
          <>
            <p className="mb-5 text-sm text-muted-foreground">{subheading}</p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              {needsCode && (
                <div className="flex flex-col gap-1.5 rounded-md border border-border bg-muted/40 p-3">
                  <label htmlFor={`${titleId}-code`} className="text-sm text-foreground">
                    Access code
                  </label>
                  <p className="text-xs text-muted-foreground">
                    Enter the access code you were given. You&rsquo;ll only need this once on this device.
                  </p>
                  <input
                    id={`${titleId}-code`}
                    ref={codeRef}
                    type="password"
                    name="access-code"
                    autoComplete="off"
                    placeholder="Access code"
                    value={code}
                    aria-invalid={codeError ? true : undefined}
                    onChange={(e) => {
                      setCode(e.target.value);
                      setCodeError(null);
                    }}
                    required
                    className={`${FIELD} mt-0.5`}
                  />
                  {codeError && <p className="text-sm text-destructive">{codeError}</p>}
                </div>
              )}

              <div
                role="radiogroup"
                aria-label="Sign in or create an account"
                className="flex gap-1 rounded-md border border-border bg-muted p-1"
              >
                {(["signin", "signup"] as const).map((option) => {
                  const selected = mode === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      tabIndex={selected ? 0 : -1}
                      onClick={() => switchMode(option)}
                      onKeyDown={onSegmentKeyDown}
                      className={
                        "flex-1 rounded-sm px-3 py-1.5 text-sm outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 " +
                        (selected
                          ? "border border-border bg-popover font-medium text-foreground shadow-sm"
                          : "border border-transparent text-muted-foreground hover:text-foreground")
                      }
                    >
                      {option === "signin" ? "Sign in" : "Sign up"}
                    </button>
                  );
                })}
              </div>

              <input
                ref={emailRef}
                type="email"
                name="email"
                autoComplete="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className={FIELD}
              />

              <div className="flex flex-col gap-1">
                <input
                  ref={passwordRef}
                  type="password"
                  name="password"
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  className={FIELD}
                />
                {mode === "signin" && (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setMode("forgot");
                        setError(null);
                        setResetEmail(email);
                      }}
                      className="cursor-pointer rounded-sm text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                      Forgot password?
                    </button>
                  </div>
                )}
              </div>

              {error && (
                <div className="flex flex-col items-start gap-1">
                  <p className="text-sm text-destructive">{error.message}</p>
                  {error.suggestSignIn && (
                    <button
                      type="button"
                      onClick={() => switchMode("signin")}
                      className="cursor-pointer rounded-sm text-sm text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                      Sign in instead
                    </button>
                  )}
                </div>
              )}

              <Button type="submit" disabled={submitting} className="mt-1 w-full text-background">
                {submitting
                  ? mode === "signin"
                    ? "Signing in…"
                    : "Creating account…"
                  : mode === "signin"
                    ? "Sign in"
                    : "Become a test user"}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

function FollowUp({ body, onBack }: { body: string; onBack: () => void }) {
  return (
    <div>
      <p className="mb-3 text-sm text-muted-foreground">{body}</p>
      <button
        type="button"
        onClick={onBack}
        className="cursor-pointer rounded-sm text-sm text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        Back to sign in
      </button>
    </div>
  );
}
