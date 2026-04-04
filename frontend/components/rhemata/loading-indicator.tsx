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
    <p
      className={`text-sm text-muted-foreground italic text-left transition-opacity duration-500 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      {PHRASES[index]}
    </p>
  );
}
