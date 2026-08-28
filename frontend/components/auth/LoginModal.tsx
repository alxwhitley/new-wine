"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createBrowserClient } from "@supabase/auth-helpers-nextjs";

interface LoginModalProps {
  onClose: () => void;
  onSignIn: (email: string, password: string) => Promise<void>;
  onSignUp: (email: string, password: string) => Promise<{ hasSession: boolean }>;
  reason?: string;
  initialMode?: "signin" | "signup";
}

export default function LoginModal({ onClose, onSignIn, onSignUp, reason, initialMode }: LoginModalProps) {
  const [mode, setMode] = useState<"signin" | "signup" | "forgot">(initialMode ?? "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [signUpSuccess, setSignUpSuccess] = useState(false);
  const [resetEmail, setResetEmail] = useState("");
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    setResetError(null);
    setResetSubmitting(true);
    try {
      const supabase = createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
      );
      const { error: err } = await supabase.auth.resetPasswordForEmail(resetEmail, {
        redirectTo: `${window.location.origin}/auth/callback?next=/auth/update-password`,
      });
      if (err) throw err;
      setResetSuccess(true);
    } catch (err: unknown) {
      setResetError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setResetSubmitting(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signin") {
        await onSignIn(email, password);
        onClose();
      } else {
        const { hasSession } = await onSignUp(email, password);
        if (hasSession) {
          onClose();
        } else {
          setSignUpSuccess(true);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-sm mx-4 rounded-lg border border-border bg-card shadow-lg p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Title */}
        <h2 className="font-sans text-xl font-semibold text-foreground mb-1">
          {mode === "forgot" ? "Reset password" : mode === "signin" ? "Sign in to Rhemata" : "Become a test user"}
        </h2>

        {/* Subtitle / reason */}
        <p className="text-sm text-muted-foreground mb-6">
          {mode === "forgot"
            ? "Enter your email and we'll send you a reset link."
            : reason ?? (mode === "signin" ? "Welcome back." : "Create a free account to keep going.")}
        </p>

        {mode === "forgot" ? (
          resetSuccess ? (
            <div>
              <p className="text-sm text-foreground mb-3">
                Check your email for a reset link.
              </p>
              <button
                onClick={() => { setMode("signin"); setResetSuccess(false); setResetEmail(""); setResetError(null); }}
                className="text-sm text-primary hover:underline cursor-pointer"
              >
                Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={handleResetPassword} className="flex flex-col gap-3">
              <input
                type="email"
                placeholder="Email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                className="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
              />

              {resetError && (
                <p className="text-sm text-destructive">{resetError}</p>
              )}

              <Button type="submit" disabled={resetSubmitting} className="w-full mt-1">
                {resetSubmitting ? "Sending…" : "Send reset link"}
              </Button>

              <p className="text-sm text-center">
                <button
                  type="button"
                  onClick={() => { setMode("signin"); setResetError(null); }}
                  className="text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  Back to sign in
                </button>
              </p>
            </form>
          )
        ) : signUpSuccess ? (
          <div>
            <p className="text-sm text-foreground mb-3">
              Check your email for a confirmation link.
            </p>
            <button
              onClick={() => { setMode("signin"); setSignUpSuccess(false); setError(null); }}
              className="text-sm text-primary hover:underline cursor-pointer"
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
            />
            <div className="flex flex-col gap-1">
              <input
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
              />
              {mode === "signin" && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => { setMode("forgot"); setError(null); setResetEmail(email); }}
                    className="text-sm text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    Forgot password?
                  </button>
                </div>
              )}
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            <Button type="submit" disabled={submitting} className="w-full mt-1">
              {submitting ? "…" : mode === "signin" ? "Sign in" : "Become a test user"}
            </Button>

            <p className="text-sm text-muted-foreground text-center">
              {mode === "signin" ? "Don't have an account? " : "Already have an account? "}
              <button
                type="button"
                onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); }}
                className="text-primary hover:underline cursor-pointer"
              >
                {mode === "signin" ? "Sign up" : "Sign in"}
              </button>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
