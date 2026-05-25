"use client";

import type { CorpusCard } from "./types";

const COLORS = {
  surface: "#262624",
  border: "#3c3c38",
  text: "#e6e6e6",
  textSecondary: "#c1c1b8",
  citationGold: "#d4b96a",
};

function StatusBadge({ status }: { status: CorpusCard["status"] }) {
  const colorMap: Record<string, { bg: string; text: string }> = {
    Complete: { bg: "rgba(34,197,94,0.15)", text: "#22c55e" },
    Ongoing: { bg: "rgba(180,146,56,0.15)", text: "#d4b96a" },
    "Not Started": { bg: "rgba(156,163,175,0.15)", text: "#9ca3af" },
    Partial: { bg: "rgba(245,158,11,0.15)", text: "#f59e0b" },
  };
  const c = colorMap[status];
  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ backgroundColor: c.bg, color: c.text }}
    >
      {status}
    </span>
  );
}

interface CorpusCardProps {
  card: CorpusCard;
  count: number | null;
  lastIngested: string | null;
  pulsing: boolean;
  onClick: () => void;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins} minute${diffMins === 1 ? "" : "s"} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
  if (diffWeeks < 5) return `${diffWeeks} week${diffWeeks === 1 ? "" : "s"} ago`;
  return `${diffMonths} month${diffMonths === 1 ? "" : "s"} ago`;
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
      className="relative rounded-lg p-4 cursor-pointer transition-all hover:brightness-110"
      style={{
        backgroundColor: COLORS.surface,
        border: `1px solid ${COLORS.border}`,
      }}
    >
      {/* Pulsing gold dot */}
      {pulsing && (
        <span
          className="absolute top-3 right-3 h-2.5 w-2.5 rounded-full animate-pulse"
          style={{ backgroundColor: COLORS.citationGold }}
        />
      )}

      <div className="flex items-center gap-2 mb-1">
        <h3
          className={`font-serif font-medium ${isMaintenance ? "text-sm" : "text-base"}`}
          style={{ color: COLORS.text }}
        >
          {card.name}
        </h3>
        <StatusBadge status={card.status} />
      </div>

      {!isMaintenance && count !== null && (
        <p
          className="text-2xl font-bold mb-1"
          style={{ color: COLORS.citationGold }}
        >
          {count.toLocaleString()}
        </p>
      )}

      {/* Progress bar for excerpts */}
      {card.progressTarget && count !== null && !isMaintenance && (
        <div className="mb-2">
          <div
            className="w-full h-1.5 rounded-full overflow-hidden"
            style={{ backgroundColor: COLORS.border }}
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min((count / card.progressTarget) * 100, 100)}%`,
                backgroundColor: COLORS.citationGold,
              }}
            />
          </div>
          <p className="text-xs mt-0.5" style={{ color: COLORS.textSecondary }}>
            {count.toLocaleString()} / {card.progressTarget.toLocaleString()}
          </p>
        </div>
      )}

      {lastIngested && (
        <p
          className="text-xs"
          style={{ color: COLORS.textSecondary }}
          title={new Date(lastIngested).toLocaleString()}
        >
          Last ingested: {formatRelativeTime(lastIngested)}
        </p>
      )}

      {isMaintenance && (
        <p
          className="text-xs mt-1 line-clamp-2"
          style={{ color: COLORS.textSecondary }}
        >
          {card.description}
        </p>
      )}
    </div>
  );
}
