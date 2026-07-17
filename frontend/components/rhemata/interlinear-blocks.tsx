"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

// SP2 Phase 6: moved verbatim out of app/study/page.tsx, no behavior change —
// see PLAN.md Task 20. Shared between the standalone Study page and (from
// Phase 8) the inline panel.

export interface WordToken {
  greek: string;
  transliteration: string;
  english: string;
  strongs: string;
  morph: string;
}

// ── InterlinearBlocks ─────────────────────────────────────────────────────────

export function InterlinearBlocks({
  tokens, selectedStrongs, onSelect, loading, isNT,
}: {
  tokens: WordToken[]; selectedStrongs: string | null;
  onSelect: (strongs: string | null) => void; loading: boolean; isNT: boolean;
}) {
  const label = (
    <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-2">
      Greek &middot; Interlinear
    </p>
  );

  if (loading) {
    return (
      <div className="mt-4">
        {label}
        <div className="flex gap-3 overflow-x-auto py-1">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="flex shrink-0 flex-col items-center gap-1">
              <Skeleton className="h-5 w-10" />
              <Skeleton className="h-3 w-8" />
              <Skeleton className="h-2.5 w-10" />
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (!isNT) {
    return (
      <div className="mt-4">
        {label}
        <p className="text-sm text-muted-foreground">No interlinear data available for this verse</p>
      </div>
    );
  }
  if (tokens.length === 0) return null;
  return (
    <div className="mt-4">
      {label}
      <div className="flex gap-2 overflow-x-auto py-1">
        {tokens.map((token, i) => {
          const isSelected = selectedStrongs === token.strongs;
          return (
            <button
              key={i}
              onClick={() => onSelect(isSelected ? null : token.strongs)}
              className={cn(
                "shrink-0 rounded-md p-1.5 text-center cursor-pointer transition-colors border min-h-[44px]",
                isSelected ? "border-primary bg-primary/10" : "border-transparent hover:bg-accent"
              )}
            >
              <span className="font-sans text-sm block leading-tight">{token.greek}</span>
              <span className="font-medium text-[11px] block leading-tight text-primary">{token.english}</span>
              <span className="text-[10px] block leading-tight text-muted-foreground font-mono">{token.strongs}</span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)
      </p>
    </div>
  );
}
