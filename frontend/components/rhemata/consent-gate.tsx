"use client";

// Consent gate for the search-analytics/corpus-gap feature
// (docs/superpowers/specs/2026-08-27-search-analytics-and-corpus-gap-
// dashboard.md). Mandatory at signup, one-time blocking gate at next
// login for existing accounts -- both cases collapse to the same check:
// "authenticated, no current-version consent yet." Unlike LoginModal,
// this has NO close button and NO backdrop-dismiss -- declining signs the
// user out rather than leaving the gate dismissible.
//
// Copy is the directive's exact wording (POSITIONING.md voice: Grounded,
// Convinced, Warm, Unhurried -- plain and direct, no SaaS-speak). This is
// framed as a condition of private-beta participation, not an optional
// opt-in -- the single action button says "I Understand and Agree," not
// "Allow" or "Enable."

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const API = process.env.NEXT_PUBLIC_API_URL;

interface ConsentGateProps {
  accessToken: string | null;
  hasUser: boolean;
  onDecline: () => void;
}

export function ConsentGate({ accessToken, hasUser, onDecline }: ConsentGateProps) {
  const [status, setStatus] = useState<"checking" | "needed" | "clear">("checking");
  const [policyCopy, setPolicyCopy] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasUser || !accessToken) {
      setStatus("checking");
      return;
    }
    let cancelled = false;
    fetch(`${API}/analytics/consent`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        if (cancelled) return;
        setPolicyCopy(data.policy_copy ?? null);
        setStatus(data.needs_acknowledgment ? "needed" : "clear");
      })
      .catch(() => {
        // Fail open on a transient check failure -- this is a UX gate, not
        // the server-side enforcement point (the backend independently
        // skips occurrence creation for a non-consented account; see the
        // spec's Assumption 4). Never trap a user behind a broken fetch.
        if (!cancelled) setStatus("clear");
      });
    return () => {
      cancelled = true;
    };
  }, [hasUser, accessToken]);

  async function handleAcknowledge() {
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API}/analytics/consent`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error();
      setStatus("clear");
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (status !== "needed") return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="relative w-full max-w-md mx-4 rounded-lg border border-border bg-card shadow-lg p-6">
        <h2 className="font-sans text-xl font-semibold text-foreground mb-1">
          Before you continue
        </h2>
        <p className="text-sm text-muted-foreground mb-4">
          A condition of private-beta participation — not an optional setting.
        </p>
        <p className="text-sm text-foreground leading-relaxed mb-6">
          {policyCopy ??
            "During this private beta, Rhemata tracks the topics you search so we can understand what material is most needed. When Rhemata says it does not have enough material, the wording of that question may be stored after obvious personal details are removed. Your name and email are not shown in analytics. Open gap wording is deleted 30 days after the gap is resolved. Please do not include sensitive personal information in your questions."}
        </p>

        {error && <p className="text-sm text-destructive mb-4">{error}</p>}

        <div className="flex flex-col gap-2">
          <Button onClick={handleAcknowledge} disabled={submitting} className="w-full">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "I Understand and Agree"}
          </Button>
          <button
            onClick={onDecline}
            className="text-sm text-muted-foreground hover:text-foreground text-center cursor-pointer"
          >
            Decline and sign out
          </button>
        </div>
      </div>
    </div>
  );
}
