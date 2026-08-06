"use client";

import { useState } from "react";
import { useCommentarySearch } from "@/hooks/useCommentarySearch";
import { formatCommentaryContent } from "@/lib/format-commentary-content";

// SP2 Task 25: Commentaries accordion row. Unlike the standalone Study
// page's list->detail+Back pattern, tapping an excerpt expands its full
// text inline in place (same tap collapses it) — no screen change, no Back
// link, per Alex's confirmed decision. Flagging UI is deliberately omitted
// here (out of scope for this row, not an oversight).

function stripPrefix(excerpt: string) {
  return excerpt.replace(/^\[.*?\]\s*/, "");
}

export function CommentaryAccordionRow({
  verseText,
  verseIdStr,
  accessToken,
}: {
  verseText: string | null;
  verseIdStr: string | null;
  accessToken?: string | null;
}) {
  const { results, loading, loadingMore, hasMore, loadMore } = useCommentarySearch(
    verseText,
    verseIdStr,
    accessToken ?? null,
    "commentary"
  );
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-4 w-full rounded bg-border" />
        <div className="h-4 w-4/5 rounded bg-border" />
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="text-sm text-muted-foreground leading-relaxed">
        No commentary found for this verse.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {results.map((r) => {
        const isExpanded = expandedId === r.document_id;
        return (
          <div key={r.document_id} className="rounded-lg border border-border bg-card p-3">
            <button
              onClick={() => setExpandedId(isExpanded ? null : r.document_id)}
              aria-expanded={isExpanded}
              className="w-full text-left cursor-pointer"
            >
              <p className="text-sm font-medium text-primary">{r.author}</p>
              <p className="text-xs text-muted-foreground mt-0.5 mb-2">{r.title}</p>
              {!isExpanded && (
                <p className="text-sm text-foreground leading-relaxed">{stripPrefix(r.excerpt)}</p>
              )}
            </button>
            {isExpanded && (
              <div className="mt-4 max-w-2xl font-serif">{formatCommentaryContent(r.content)}</div>
            )}
          </div>
        );
      })}
      {hasMore && (
        <div className="flex justify-center pt-1">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="text-sm text-primary hover:underline underline-offset-4 disabled:opacity-50 cursor-pointer"
          >
            {loadingMore ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
