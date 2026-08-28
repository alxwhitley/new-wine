"use client";

import { useEffect, useRef, useState } from "react";

import {
  LOADING_PHRASES,
  estimateLoadingProgress,
  loadingPhraseIndex,
} from "@/lib/loading-progress";

const RADIUS = 15;
const STROKE_WIDTH = 4;
const CX = 20;
const CY = 20;
const SIZE = 40;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
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

  const progress = estimateLoadingProgress(elapsedMs);
  const phraseIndex = loadingPhraseIndex(progress);
  const filledOffset = CIRCUMFERENCE * (1 - progress);

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 text-left"
    >
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ transform: "rotate(-90deg)" }}
        className="shrink-0"
        aria-label="Estimated progress"
      >
        {/* Track: faint outline, always visible so the ring never looks empty */}
        <circle
          cx={CX}
          cy={CY}
          r={RADIUS}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={STROKE_WIDTH}
        />
        {/* Arc: estimated progress -- grows monotonically, caps before completion */}
        <circle
          cx={CX}
          cy={CY}
          r={RADIUS}
          fill="none"
          stroke="hsl(var(--foreground))"
          strokeWidth={STROKE_WIDTH}
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={filledOffset}
          className="transition-[stroke-dashoffset] duration-300 ease-out motion-reduce:transition-none"
        />
      </svg>
      <p className="text-sm text-muted-foreground italic">
        {LOADING_PHRASES[phraseIndex]}
      </p>
    </div>
  );
}
