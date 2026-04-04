"use client";

import { useState } from "react";
import { X } from "lucide-react";

interface LoginModalProps {
  onClose: () => void;
  onSignIn: (email: string, password: string) => Promise<void>;
  onSignUp: (email: string, password: string) => Promise<void>;
  reason?: string;
}

export default function LoginModal({ onClose, onSignIn, onSignUp, reason }: LoginModalProps) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [signUpSuccess, setSignUpSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "signin") {
        await onSignIn(email, password);
        onClose();
      } else {
        await onSignUp(email, password);
        setSignUpSuccess(true);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 14px",
    borderRadius: "8px",
    border: "1px solid var(--border)",
    background: "var(--card)",
    color: "var(--foreground)",
    fontSize: "14px",
    fontFamily: "var(--font-inter), Inter, sans-serif",
    outline: "none",
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0, 0, 0, 0.6)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: "380px",
          background: "var(--background)",
          border: "1px solid var(--border)",
          borderRadius: "14px",
          padding: "32px",
          position: "relative",
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "16px",
            right: "16px",
            color: "var(--muted-foreground)",
            cursor: "pointer",
            padding: "4px",
            borderRadius: "6px",
            transition: "color 150ms",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--foreground)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted-foreground)"; }}
        >
          <X size={18} strokeWidth={1.8} />
        </button>

        {reason && (
          <div
            style={{
              padding: "10px 14px",
              borderRadius: "8px",
              background: "var(--card)",
              borderLeft: "3px solid var(--gold)",
              marginBottom: "20px",
              fontSize: "13px",
              lineHeight: "1.5",
              color: "var(--foreground)",
              fontFamily: "var(--font-inter), Inter, sans-serif",
            }}
          >
            {reason}
          </div>
        )}

        <h2
          style={{
            fontFamily: "var(--font-lora), Lora, serif",
            fontSize: "20px",
            fontWeight: 600,
            color: "var(--foreground)",
            marginBottom: "24px",
          }}
        >
          {mode === "signin" ? "Sign in to Rhemata" : "Create an account"}
        </h2>

        {signUpSuccess ? (
          <div style={{ fontFamily: "var(--font-inter), Inter, sans-serif" }}>
            <p style={{ fontSize: "14px", color: "var(--foreground)", marginBottom: "8px" }}>
              Check your email for a confirmation link.
            </p>
            <button
              onClick={() => { setMode("signin"); setSignUpSuccess(false); setError(null); }}
              style={{
                fontSize: "13px",
                color: "var(--gold)",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              style={inputStyle}
            />

            {error && (
              <p style={{ fontSize: "13px", color: "var(--destructive)", margin: 0 }}>{error}</p>
            )}

            <button
              type="submit"
              disabled={submitting}
              style={{
                width: "100%",
                padding: "10px",
                borderRadius: "8px",
                background: submitting ? "var(--gold-hover)" : "var(--gold)",
                color: "var(--primary-foreground)",
                fontSize: "14px",
                fontWeight: 600,
                fontFamily: "var(--font-inter), Inter, sans-serif",
                cursor: submitting ? "default" : "pointer",
                transition: "background 150ms",
                border: "none",
              }}
              onMouseEnter={(e) => { if (!submitting) e.currentTarget.style.background = "var(--gold-hover)"; }}
              onMouseLeave={(e) => { if (!submitting) e.currentTarget.style.background = "var(--gold)"; }}
            >
              {submitting
                ? "..."
                : mode === "signin"
                  ? "Sign in"
                  : "Create account"}
            </button>

            <p
              style={{
                fontSize: "13px",
                color: "var(--muted-foreground)",
                textAlign: "center",
                fontFamily: "var(--font-inter), Inter, sans-serif",
                margin: 0,
              }}
            >
              {mode === "signin" ? "Don't have an account? " : "Already have an account? "}
              <button
                type="button"
                onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(null); }}
                style={{
                  color: "var(--gold)",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontSize: "inherit",
                }}
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
