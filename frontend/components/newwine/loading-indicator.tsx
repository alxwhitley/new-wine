"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
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
    <div role="status" aria-live="polite" aria-atomic="true">
      {/* The only thing announced. The visual list below repeats every step,
          which a screen reader would re-read on each transition -- so the list
          is hidden and this carries the active step alone. */}
      <span className="sr-only">{LOADING_STEPS[active]}</span>

      <ol aria-hidden="true" className="flex flex-col gap-1.5 text-sm">
        {LOADING_STEPS.map((step, index) => {
          const done = index < active;
          const isActive = index === active;
          return (
            <li
              key={step}
              className={cn(
                "flex items-center gap-2",
                isActive && "text-foreground",
                done && "text-muted-foreground",
                // Upcoming: present but recessive, so the sequence reads as a
                // plan rather than as work already claimed.
                !done && !isActive && "text-muted-foreground opacity-60",
              )}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                {done ? (
                  <Check className="h-3.5 w-3.5" />
                ) : isActive ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              {step}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
