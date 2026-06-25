"use client";

import type { CorpusCard } from "./corpus-types";
import { StatusBadge } from "./status-badge";

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? "" : "s"} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  if (diffWeeks < 5) return `${diffWeeks} week${diffWeeks === 1 ? "" : "s"} ago`;
  return `${diffMonths} month${diffMonths === 1 ? "" : "s"} ago`;
}

interface CorpusCardProps {
  card: CorpusCard;
  count: number | null;
  lastIngested: string | null;
  pulsing: boolean;
  onClick: () => void;
}

export default function CorpusCardComponent({
  card,
  count,
  lastIngested,
  pulsing,
  onClick,
}: CorpusCardProps) {
  const isMaintenance = card.isMaintenance;

  return (
    <div
      onClick={onClick}
      className="relative rounded-lg p-4 cursor-pointer transition-colors bg-card border border-border hover:bg-accent"
    >
      {pulsing && (
        <span className="absolute top-3 right-3 h-2.5 w-2.5 rounded-full animate-pulse bg-primary" />
      )}

      <div className="flex items-center gap-2 mb-1">
        <h3 className={`font-sans font-medium text-foreground ${isMaintenance ? "text-sm" : "text-base"}`}>
          {card.name}
        </h3>
        <StatusBadge status={card.status} />
      </div>

      {!isMaintenance && count !== null && (
        <p className="text-2xl font-bold mb-1 text-primary">
          {count.toLocaleString()}
        </p>
      )}

      {card.progressTarget && count !== null && !isMaintenance && (
        <div className="mb-2">
          <div className="w-full h-1.5 rounded-full overflow-hidden bg-border">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.min((count / card.progressTarget) * 100, 100)}%` }}
            />
          </div>
          <p className="text-xs mt-0.5 text-muted-foreground">
            {count.toLocaleString()} / {card.progressTarget.toLocaleString()}
          </p>
        </div>
      )}

      {lastIngested && (
        <p
          className="text-xs text-muted-foreground"
          title={new Date(lastIngested).toLocaleString()}
        >
          Last ingested: {formatRelativeTime(lastIngested)}
        </p>
      )}

      {isMaintenance && (
        <p className="text-xs mt-1 line-clamp-2 text-muted-foreground">
          {card.description}
        </p>
      )}
    </div>
  );
}
