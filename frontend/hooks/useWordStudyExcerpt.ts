import { useEffect, useState } from "react";

// Precept Austin word-study excerpt for a Strong's number. Extracted from the
// inline fetch in app/study/page.tsx so the inline Study Panel and the
// standalone page share one implementation of this contract rather than each
// re-deriving it — same reasoning as useLexiconDefinition (SP2 Phase 6).
//
// GET /study/excerpt requires an authenticated user (Depends(require_user)),
// so a guest gets a 401 here and content stays null. That is the intended
// honest-empty path, not an error to surface.

export interface WordStudyExcerpt {
  content: string | null;
  loading: boolean;
}

export function useWordStudyExcerpt(
  strongs: string | null,
  accessToken: string | null
): WordStudyExcerpt {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!strongs);

  // Adjust synchronously during render when strongs changes, matching
  // useLexiconDefinition's pattern. Two reasons this is not deferred to the
  // effect: the previous word's article would otherwise render under the new
  // word's heading for a frame — on this surface that reads as a real
  // attribution error, not a loading artifact — and setState directly in an
  // effect body is a lint error here.
  const [resolvedStrongs, setResolvedStrongs] = useState(strongs);
  if (strongs !== resolvedStrongs) {
    setResolvedStrongs(strongs);
    setContent(null);
    setLoading(!!strongs);
  }

  useEffect(() => {
    if (!strongs) return;
    let cancelled = false;
    const params = new URLSearchParams({ strongs });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/excerpt?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setContent(data?.content ?? null);
      })
      .catch(() => {
        if (!cancelled) setContent(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [strongs, accessToken]);

  return { content, loading };
}
