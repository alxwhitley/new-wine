import { useEffect, useState } from "react";
import { resolveQuotes, type ResolvedQuote } from "@/lib/api";

export function useResolvedQuotes(quoteIds: string[] | undefined): ResolvedQuote[] {
  const [quotes, setQuotes] = useState<ResolvedQuote[]>([]);
  const key = quoteIds?.length ? quoteIds.join(",") : "";

  useEffect(() => {
    if (!key) {
      setQuotes([]);
      return;
    }
    let cancelled = false;
    setQuotes([]);
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
