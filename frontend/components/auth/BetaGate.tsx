"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface BetaGateProps {
  onSuccess: () => void;
  onClose: () => void;
}

export default function BetaGate({ onSuccess, onClose }: BetaGateProps) {
  const [code, setCode] = useState("");
  const [error, setError] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (code === "newwine") {
      sessionStorage.setItem("beta_access", "1");
      onSuccess();
    } else {
      setError(true);
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
        <button
          onClick={onClose}
          className="absolute top-4 right-4 h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="font-sans text-xl font-semibold text-foreground mb-1">Beta access</h2>
        <p className="text-sm text-muted-foreground mb-6">Enter your access code to continue.</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="password"
            placeholder="Access code"
            value={code}
            onChange={(e) => { setCode(e.target.value); setError(false); }}
            autoFocus
            className="w-full rounded-md border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
          />
          {error && (
            <p className="text-sm text-destructive">Incorrect access code</p>
          )}
          <Button type="submit" className="w-full mt-1">Continue</Button>
        </form>
      </div>
    </div>
  );
}
