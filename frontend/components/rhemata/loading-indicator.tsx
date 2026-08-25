"use client";

import { useState, useEffect } from "react";

const PHRASES = [
  "Searching sources...",
  "Reading theology...",
  "Forming answer...",
];

export function LoadingIndicator() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((prev) => (prev + 1) % PHRASES.length);
        setVisible(true);
      }, 500);
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-1 text-left"
    >
      <p
        aria-hidden="true"
        className={`text-sm text-muted-foreground italic transition-opacity duration-500 motion-reduce:transition-none ${
          visible ? "opacity-100" : "opacity-0"
        }`}
      >
        {PHRASES[index]}
      </p>
      <p className="text-xs text-muted-foreground">
        Thoughtful answers can take about a minute. You can leave and return to this tab.
      </p>
    </div>
  );
}
