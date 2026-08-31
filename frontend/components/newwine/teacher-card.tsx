"use client";

import { useEffect, useState } from "react";

interface TeacherCardData {
  bio: string;
  works: Array<{ id: string; title: string }>;
  position: string | null;
}

function useTeacherCard(
  sourceId: string,
  question: string,
  accessToken: string | null | undefined
): { data: TeacherCardData | null; loading: boolean; error: boolean } {
  const [data, setData] = useState<TeacherCardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // Reset synchronously during render when the (sourceId, question) pair
  // changes (React's documented "adjusting state when a prop changes"
  // pattern) instead of as the effect's own first statements.
  const key = sourceId && question ? `${sourceId}|${question}` : null;
  const [resolvedKey, setResolvedKey] = useState(key);
  if (key !== resolvedKey) {
    setResolvedKey(key);
    if (key) {
      setLoading(true);
      setError(false);
      setData(null);
    }
  }

  useEffect(() => {
    if (!sourceId || !question) return;
    let cancelled = false;
    const params = new URLSearchParams({ question });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/teacher/${sourceId}?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error("teacher card fetch failed");
        return res.json();
      })
      .then((json) => {
        if (cancelled) return;
        setData(json);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, question, accessToken]);

  return { data, loading, error };
}

export function TeacherCard({
  sourceId,
  question,
  accessToken,
}: {
  sourceId: string;
  question: string;
  accessToken?: string | null;
}) {
  const { data, loading, error } = useTeacherCard(sourceId, question, accessToken);

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-4 w-full rounded bg-border" />
        <div className="h-4 w-5/6 rounded bg-border" />
        <div className="h-4 w-2/3 rounded bg-border" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <p className="text-sm text-muted-foreground">
        This teacher&apos;s card isn&apos;t available right now.
      </p>
    );
  }

  return (
    <div>
      <p className="text-sm text-foreground leading-relaxed">{data.bio}</p>

      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Works in the corpus
        </p>
        {data.works.length > 0 ? (
          <ul className="space-y-1">
            {data.works.map((w) => (
              <li key={w.id} className="text-sm text-foreground">
                {w.title}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground leading-relaxed">
            No works from this teacher are available right now.
          </p>
        )}
      </div>

      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Position on this question
        </p>
        {data.position ? (
          <p className="text-sm text-foreground leading-relaxed">{data.position}</p>
        ) : (
          <p className="text-sm text-muted-foreground leading-relaxed">
            No position found on this from this teacher yet.
          </p>
        )}
      </div>
    </div>
  );
}
