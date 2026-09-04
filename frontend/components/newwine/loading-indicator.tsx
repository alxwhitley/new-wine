"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { LOADING_STEPS, activeStepIndex } from "@/lib/loading-progress";

const TICK_MS = 250;

export function LoadingIndicator() {
  const startedAtRef = useRef<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    startedAtRef.current = Date.now();
    const interval = setInterval(() => {
      const startedAt = startedAtRef.current;
      if (startedAt === null) return;
      setElapsedMs(Date.now() - startedAt);
    }, TICK_MS);
    return () => clearInterval(interval);
  }, []);

  const active = activeStepIndex(elapsedMs);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="flex min-h-5 items-center gap-2 text-sm text-foreground"
    >
      <Loader2
        aria-hidden="true"
        className="h-3.5 w-3.5 shrink-0 animate-spin motion-reduce:animate-none"
      />
      <span>{LOADING_STEPS[active]}</span>
    </div>
  );
}
