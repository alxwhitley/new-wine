import { useCallback, useEffect, useState } from "react";

// SP2 Phase 6: extracted verbatim out of app/study/page.tsx's fetchCommentary
// callback + its triggering effect — see PLAN.md Task 22. sourceKindFilter is
// new (not used by the standalone page, which never passes one — identical
// behavior there), threading through the source_kind_filter param Phase 4's
// Task 9 already added to /study/commentary, for Phase 7/8 to use.

export interface CommentaryResult {
  document_id: string;
  title: string;
  author: string;
  source_kind: string;
  excerpt: string;
  content: string;
}

export function useCommentarySearch(
  verseText: string | null,
  verseId: string | null,
  accessToken: string | null,
  sourceKindFilter?: "commentary" | "sermon_transcript"
): {
  results: CommentaryResult[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  loadMore: () => void;
} {
  const [results, setResults] = useState<CommentaryResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Runs the fetch only -- does NOT set the initial loading/loadingMore
  // flag itself. Callers are responsible for that: the effect below sets
  // it via the render-time-adjustment pattern (react-hooks/set-state-in-effect
  // forbids a synchronous setState call as an effect's own first
  // statement), while loadMore (a real event handler, not an effect) sets
  // it directly, which is fine there.
  const runFetch = useCallback((text: string, off: number, vId?: string) => {
    const isLoadMore = off > 0;
    const params = new URLSearchParams({ verse_text: text, offset: String(off) });
    if (vId) params.set("verse_id", vId);
    if (sourceKindFilter) params.set("source_kind_filter", sourceKindFilter);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/commentary?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => { if (!res.ok) throw new Error("commentary fetch failed"); return res.json(); })
      .then((data) => {
        const newResults = data.results ?? [];
        if (isLoadMore) {
          setResults((prev) => [...prev, ...newResults]);
        } else {
          setResults(newResults);
        }
        setHasMore(data.has_more ?? false);
        setOffset(off);
      })
      .catch(() => { if (!isLoadMore) setResults([]); setHasMore(false); })
      .finally(() => { if (isLoadMore) { setLoadingMore(false); } else { setLoading(false); } });
  }, [accessToken, sourceKindFilter]);

  // Reset/kick off synchronously during render when verseText or verseId
  // change (React's documented "adjusting state when a prop changes"
  // pattern) instead of as the effect's own first statements.
  const key = `${verseText ?? ""}|${verseId ?? ""}`;
  const [resolvedKey, setResolvedKey] = useState(key);
  if (key !== resolvedKey) {
    setResolvedKey(key);
    if (!verseText) {
      setResults([]);
      setOffset(0);
      setHasMore(false);
    } else {
      setLoading(true);
    }
  }

  useEffect(() => {
    if (!verseText) return;
    runFetch(verseText, 0, verseId ?? undefined);
  }, [verseText, verseId, runFetch]);

  const loadMore = useCallback(() => {
    if (!verseText) return;
    setLoadingMore(true);
    runFetch(verseText, offset + 3, verseId ?? undefined);
  }, [verseText, verseId, offset, runFetch]);

  return { results, loading, loadingMore, hasMore, loadMore };
}
