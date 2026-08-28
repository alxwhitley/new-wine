import { useEffect, useState } from "react";
import { resolveQuotes, type ResolvedQuote } from "@/lib/api";

export function useResolvedQuotes(quoteIds: string[] | undefined): ResolvedQuote[] {
  const key = quoteIds?.length ? quoteIds.join(",") : "";
  const [quotes, setQuotes] = useState<ResolvedQuote[]>([]);

  // Reset synchronously during render when key changes (React's documented
  // "adjusting state when a prop changes" pattern) rather than in the
  // effect below -- avoids an extra committed render showing stale quotes
  // for the new key.
  const [resolvedKey, setResolvedKey] = useState(key);
  if (key !== resolvedKey) {
    setResolvedKey(key);
    setQuotes([]);
  }

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    resolveQuotes(key.split(","))
      .then((resolved) => {
        if (!cancelled) setQuotes(resolved);
      })
      .catch(() => {
        if (!cancelled) setQuotes([]);
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  return quotes;
}
